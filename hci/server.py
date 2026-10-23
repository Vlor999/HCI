"""HTTP API + mobile web app. The phone talks to this server; generation runs here (on-prem) or on Anthropic.

Stream protocol of `/api/ask`: answer text, step lines prefixed by `STEP_MARKER`, then optionally
`PROPOSALS_MARKER` followed by a JSON list of facts the agent proposes (see `hci/constants.py`).
"""

import json
import socket
import threading
from collections.abc import Iterator
from contextlib import nullcontext
from functools import cache, partial
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from hci import corpus, dashboard, documents, metrics
from hci.agent import answerer
from hci.auth import auth
from hci.config import get_settings
from hci.constants import (
    AGENT_PROPOSED_ON_PHONE,
    DOCUMENT_EXTENSIONS,
    PROPOSALS_MARKER,
    UPLOAD_OVERHEAD_BYTES,
    UPLOADS_ROUTE,
    VENDOR_DIR,
    WEB_PAGE,
    MetricSource,
)
from hci.device import backend
from hci.rag import ExplanationPipeline
from hci.schemas import AskRequest, DocumentInfo, FactRequest, Provider
from hci.types import Answer, RecordChunk

app = FastAPI(title="HCI robot explainer")
app.mount("/vendor", StaticFiles(directory=VENDOR_DIR), name="vendor")
dashboard.add_routes(app, require_token=True)
answerers: dict[str, Answer] = {}
# ponytail: one local generation at a time (local models aren't thread-safe), fine for one robot; a queue per backend
# if several phones share a GPU. Claude requests and fact writes never wait for it.
local_lock = threading.Lock()
facts_lock = threading.Lock()  # serializes read-modify-write of the facts file


@cache
def get_rag() -> ExplanationPipeline:
    """The shared pipeline, built on first use.

    Returns:
        The process-wide `ExplanationPipeline`.
    """
    return ExplanationPipeline()


def providers() -> list[str]:
    """Providers this server can run: the local backend, plus Anthropic when a key is configured.

    Returns:
        Provider names, the default first.
    """
    return [backend()] + ([Provider.ANTHROPIC] if get_settings().anthropic_api_key else [])


@app.middleware("http")
async def guard_uploads(request: Request, call_next) -> Response:
    """Check the token and the declared size of a document upload from its headers, before the body is read.

    FastAPI parses (and spools) a multipart body before running dependencies, so `auth` alone comes too late.

    Args:
        request: the incoming request.
        call_next: the rest of the app.

    Returns:
        A 401, 411 or 413 response, or the app's response.
    """
    if request.method == "POST" and request.url.path == UPLOADS_ROUTE:
        rejection = _upload_rejection(request.headers.get("authorization", ""), request.headers.get("content-length"))
        if rejection:
            return rejection
    return await call_next(request)


def _upload_rejection(authorization: str, content_length: str | None) -> JSONResponse | None:
    try:
        auth(authorization)
    except HTTPException as e:
        return JSONResponse({"detail": e.detail}, e.status_code)
    if content_length is None or not content_length.isdigit():
        return JSONResponse({"detail": "Content-Length required for uploads."}, 411)
    if int(content_length) > _upload_limit() + UPLOAD_OVERHEAD_BYTES:
        return JSONResponse({"detail": _too_large()}, 413)
    return None


def _upload_limit() -> int:
    return int(get_settings().max_upload_mb * 1024 * 1024)


def _too_large() -> str:
    return f"File too large: the limit is {get_settings().max_upload_mb:g} MB."


@app.get("/")
def index() -> FileResponse:
    """Serve the phone web app.

    Returns:
        The page.
    """
    return FileResponse(WEB_PAGE)


@app.get("/api/info", dependencies=[Depends(auth)])
def info() -> dict:
    """List providers, scenarios and accepted document types for the page's pickers.

    Returns:
        `providers` (default first), scenario descriptions by index and `document_types` (file extensions).
    """
    return {
        "providers": providers(),
        "scenarios": [s.get("description", "") for s in corpus.scenarios()],
        "document_types": list(DOCUMENT_EXTENSIONS),
    }


@app.post("/api/ask", dependencies=[Depends(auth)])
def ask(req: AskRequest) -> StreamingResponse:
    """Stream an answer to a question.

    Args:
        req: the question, scenario, provider and history.

    Returns:
        A text stream following the protocol in the module docstring.

    Raises:
        HTTPException: 400 when the provider is not available on this server.
    """
    available = providers()
    provider = req.provider or available[0]
    if provider not in available:
        raise HTTPException(400, f"Provider must be one of {available}.")
    return StreamingResponse(_answer_stream(provider, req), media_type="text/plain; charset=utf-8")


@app.post("/api/facts", dependencies=[Depends(auth)])
def add_fact(fact: FactRequest) -> dict:
    """Save an operator-approved fact.

    Args:
        fact: the fact and its scenario.

    Returns:
        `{"ok": True}`.
    """
    with facts_lock:
        get_rag().add_fact(fact.text, fact.scenario)
    return {"ok": True}


@app.get(UPLOADS_ROUTE, dependencies=[Depends(auth)])
def list_documents() -> list[DocumentInfo]:
    """List the documents of the documents folder with their number of indexed chunks.

    Returns:
        One entry per supported file, in path order.
    """
    rag = get_rag()
    rag.refresh()
    return [_document_info(path, rag.chunks) for path in documents.document_files()]


@app.post(UPLOADS_ROUTE, dependencies=[Depends(auth)])
def upload_document(file: UploadFile) -> DocumentInfo:
    """Save an uploaded document in the uploads folder and index it. Token and size are checked by `guard_uploads`.

    Args:
        file: the multipart file.

    Returns:
        The saved name and its number of chunks.

    Raises:
        HTTPException: 415 for an unsupported type, 413 above `max_upload_mb`, 422 when the file cannot be indexed
            (it is removed), 500 when it cannot be saved.
    """
    name = documents.safe_name(file.filename or "")
    if Path(name).suffix.lower() not in DOCUMENT_EXTENSIONS:
        raise HTTPException(415, f"Unsupported file type. Send one of: {', '.join(DOCUMENT_EXTENSIONS)}.")
    data = _read_upload(file)
    try:
        path = documents.save_upload(name, data)
    except OSError as e:
        raise HTTPException(500, "Could not save the file on the server.") from e
    chunks = documents.load_document(path)  # cached: the refresh below reuses it
    if not chunks:
        error = documents.document_error(path)
        path.unlink(missing_ok=True)
        raise HTTPException(422, f"Could not index {path.name}: {error}.")
    get_rag().refresh()
    logger.info("Indexed upload {} ({} chunks)", path, len(chunks))
    return _document_info(path, chunks)


def _read_upload(file: UploadFile) -> bytes:
    limit = _upload_limit()
    data = file.file.read(limit + 1)  # one byte past the limit is enough to know it is too big
    if len(data) > limit:
        raise HTTPException(413, _too_large())
    return data


def _document_info(path: Path, chunks: list[RecordChunk]) -> DocumentInfo:
    prefix = documents.file_ref(path) + "#"
    name = path.relative_to(get_settings().documents_dir).as_posix()
    return DocumentInfo(name=name, chunks=sum(c.id.startswith(prefix) for c in chunks))


def _propose(proposals: list[dict], text: str, scenario: int | None) -> str:
    proposals.append({"text": text, "scenario": scenario})
    return AGENT_PROPOSED_ON_PHONE


def _get_answerer(provider: str) -> Answer:
    if provider not in answerers:
        answerers[provider] = answerer(get_rag(), provider)
    return answerers[provider]


def _answer_stream(provider: str, req: AskRequest) -> Iterator[str]:
    proposals: list[dict] = []
    with nullcontext() if provider == Provider.ANTHROPIC else local_lock:
        answer = _get_answerer(provider)
        stream = answer(req.question, req.scenario, req.history, partial(_propose, proposals))
        yield from metrics.track(stream, MetricSource.SERVER, req.question, req.scenario, req.conversation_id)
    if proposals:  # facts the agent wants to save; the page shows approve buttons
        yield PROPOSALS_MARKER + json.dumps(proposals)


def _lan_ip(host: str) -> str:
    if host != "0.0.0.0":
        return host
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # no packet sent, just picks the LAN interface
        return s.getsockname()[0]


def run(host: str, port: int) -> None:
    """Start the server and print the links to the phone app and the metrics dashboard.

    Args:
        host: bind address (0.0.0.0 for phone access on the LAN).
        port: port.
    """
    logger.warning(
        "Serving plain HTTP on {}:{}: the token and answers travel unencrypted, so anyone on this network can read "
        "them. Use a trusted network, or put a TLS reverse proxy in front.",
        host,
        port,
    )
    token, lan_ip = get_settings().token, _lan_ip(host)
    print(f"Open on your phone (same Wi-Fi): http://{lan_ip}:{port}/#{token}")
    print(f"Metrics dashboard: http://{lan_ip}:{port}/dashboard#{token}")
    uvicorn.run(app, host=host, port=port)
