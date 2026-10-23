"""HTTP API + mobile web app. The phone talks to this server; generation runs here (on-prem) or on Anthropic.

Stream protocol of `/api/ask`: answer text, step lines prefixed by `STEP_MARKER`, then optionally
`PROPOSALS_MARKER` followed by a JSON list of facts the agent proposes (see `hci/constants.py`).
"""

import json
import secrets
import socket
import threading
from collections.abc import Iterator
from contextlib import nullcontext
from functools import cache, partial

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger

from hci import corpus
from hci.agent import answerer
from hci.config import get_settings
from hci.constants import AGENT_PROPOSED_ON_PHONE, PROPOSALS_MARKER, WEB_PAGE
from hci.device import backend
from hci.rag import ExplanationPipeline
from hci.schemas import AskRequest, FactRequest, Provider
from hci.types import Answer

app = FastAPI(title="HCI robot explainer")
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


def auth(authorization: str = Header("")) -> None:
    """Check the bearer token, comparing bytes so any header value gives 401 on mismatch.

    Args:
        authorization: the `Authorization` header.

    Raises:
        HTTPException: 401 when the token is missing or wrong.
    """
    expected = f"Bearer {get_settings().token}".encode()
    if not secrets.compare_digest(authorization.encode(), expected):
        raise HTTPException(401, "Missing or wrong token. Open the link printed by `hci serve`.")


@app.get("/")
def index() -> FileResponse:
    """Serve the phone web app.

    Returns:
        The page.
    """
    return FileResponse(WEB_PAGE)


@app.get("/api/info", dependencies=[Depends(auth)])
def info() -> dict:
    """List providers and scenarios for the page's pickers.

    Returns:
        `providers` (default first) and scenario descriptions by index.
    """
    return {"providers": providers(), "scenarios": [s.get("description", "") for s in corpus.scenarios()]}


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
        yield from answer(req.question, req.scenario, req.history, partial(_propose, proposals))
    if proposals:  # facts the agent wants to save; the page shows approve buttons
        yield PROPOSALS_MARKER + json.dumps(proposals)


def _lan_ip(host: str) -> str:
    if host != "0.0.0.0":
        return host
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # no packet sent, just picks the LAN interface
        return s.getsockname()[0]


def run(host: str, port: int) -> None:
    """Start the server and print the link to open on the phone.

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
    print(f"Open on your phone (same Wi-Fi): http://{_lan_ip(host)}:{port}/#{get_settings().token}")
    uvicorn.run(app, host=host, port=port)
