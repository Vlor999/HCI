"""HTTP API + mobile web app. The phone talks to this server; generation runs here (on-prem) or on Anthropic."""

import os
import secrets
import threading
from functools import cache
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from hci import corpus, llm
from hci.device import backend
from hci.rag import RAG

TOKEN = os.environ.get("HCI_TOKEN") or secrets.token_urlsafe(16)
PROVIDERS = [backend(), "anthropic"]
WEB = Path(__file__).resolve().parent.parent / "web" / "index.html"

app = FastAPI(title="HCI robot explainer")
models: dict[str, llm.Generate] = {}
lock = threading.Lock()  # ponytail: one generation at a time; local models aren't thread-safe, fine for one robot


@cache
def get_rag() -> RAG:
    return RAG()


def auth(authorization: str = Header("")) -> None:
    if not secrets.compare_digest(authorization, f"Bearer {TOKEN}"):
        raise HTTPException(401, "bad token")


class Ask(BaseModel):
    question: str
    scenario: int | None = None
    provider: str = PROVIDERS[0]
    history: list[tuple[str, str]] = []


class Fact(BaseModel):
    text: str
    scenario: int | None = None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB)


@app.get("/api/info", dependencies=[Depends(auth)])
def info() -> dict:
    return {"providers": PROVIDERS, "scenarios": [s.get("description", "") for s in corpus.scenarios()]}


@app.post("/api/ask", dependencies=[Depends(auth)])
def ask(req: Ask) -> StreamingResponse:
    if req.provider not in PROVIDERS:
        raise HTTPException(400, f"provider must be one of {PROVIDERS}")

    def stream():
        with lock:
            if req.provider not in models:
                models[req.provider] = llm.load(req.provider)
            yield from get_rag().answer(req.question, models[req.provider], req.scenario, req.history)

    return StreamingResponse(stream(), media_type="text/plain; charset=utf-8")


@app.post("/api/facts", dependencies=[Depends(auth)])
def add_fact(fact: Fact) -> dict:
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
