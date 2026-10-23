"""HTTP API + mobile web app. The phone talks to this server; generation runs here (on-prem) or on Anthropic."""

import json
import os
import secrets
import threading
from functools import cache

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from hci import corpus
from hci.agent import Answer, answerer
from hci.constants import PROPOSALS_MARKER, WEB_PAGE
from hci.device import backend
from hci.rag import RAG
from hci.schemas import AskRequest, FactRequest

TOKEN = os.environ.get("HCI_TOKEN") or secrets.token_urlsafe(16)
PROVIDERS = [backend(), "anthropic"]

app = FastAPI(title="HCI robot explainer")
answerers: dict[str, Answer] = {}
lock = threading.Lock()  # ponytail: one generation at a time; local models aren't thread-safe, fine for one robot


@cache
def get_rag() -> RAG:
    return RAG()


def auth(authorization: str = Header("")) -> None:
    if not secrets.compare_digest(authorization, f"Bearer {TOKEN}"):
        raise HTTPException(401, "bad token")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_PAGE)


@app.get("/api/info", dependencies=[Depends(auth)])
def info() -> dict:
    return {"providers": PROVIDERS, "scenarios": [s.get("description", "") for s in corpus.scenarios()]}


@app.post("/api/ask", dependencies=[Depends(auth)])
def ask(req: AskRequest) -> StreamingResponse:
    provider = req.provider or PROVIDERS[0]
    if provider not in PROVIDERS:
        raise HTTPException(400, f"provider must be one of {PROVIDERS}")

    proposals: list[dict] = []

    def propose(text: str, scenario: int | None) -> str:
        proposals.append({"text": text, "scenario": scenario})
        return "Proposed: the operator will approve or reject it on the phone."

    def stream():
        with lock:
            if provider not in answerers:
                answerers[provider] = answerer(get_rag(), provider)
            yield from answerers[provider](req.question, req.scenario, req.history, propose)
        if proposals:  # facts the agent wants to save; the page shows approve buttons
            yield PROPOSALS_MARKER + json.dumps(proposals)

    return StreamingResponse(stream(), media_type="text/plain; charset=utf-8")


@app.post("/api/facts", dependencies=[Depends(auth)])
def add_fact(fact: FactRequest) -> dict:
    with lock:
        get_rag().add_fact(fact.text, fact.scenario)
    return {"ok": True}


def run(host: str, port: int) -> None:
    import socket

    import uvicorn

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))  # no packet sent, just picks the LAN interface
        ip = s.getsockname()[0] if host == "0.0.0.0" else host
    print(f"Open on your phone (same Wi-Fi): http://{ip}:{port}/#{TOKEN}")
    uvicorn.run(app, host=host, port=port)
