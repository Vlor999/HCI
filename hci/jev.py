"""Optional Jev judge (TypeSafe AI): filters retrieved passages and gates unanswerable questions.

Enabled when TYPESAFE_API_KEY is set. One request judges every passage plus answerability.
API: POST https://api.typesafe.ai/v1/systemone, see docs.typesafe.ai/primitives.
"""

import atexit
import time
from functools import cache

import httpx
from loguru import logger

from hci import metrics
from hci.config import get_settings
from hci.constants import JEV_ANSWERABLE_QUESTION, JEV_PASSAGE_QUESTION, JEV_URL
from hci.types import JevEvent, RecordChunk


def enabled() -> bool:
    """Whether the judge can run.

    Returns:
        True when a non-empty TypeSafe API key is configured.
    """
    key = get_settings().typesafe_api_key
    return bool(key and key.get_secret_value())


def request(question: str, chunks: list[RecordChunk]) -> dict:
    """Build the Jev request body: one relevance question per passage, plus answerability.

    Args:
        question: The user question.
        chunks: Passages to judge; passage `i` is keyed `p{i}`.

    Returns:
        The JSON body for `JEV_URL`.
    """
    questions = {
        f"p{i}": {"type": "noul", "instructions": JEV_PASSAGE_QUESTION.format(key=f"p{i}")} for i in range(len(chunks))
    }
    questions["answerable"] = {
        "type": "noul",
        "instructions": JEV_ANSWERABLE_QUESTION,
    }
    return {
        "model": get_settings().jev_model,
        "state": {"query": question, "passages": {f"p{i}": c.text for i, c in enumerate(chunks)}},
        "questions": questions,
    }


def parse(answers: dict, chunks: list[RecordChunk]) -> tuple[set[str], bool]:
    """Apply the keep and answerable thresholds to Jev's answers.

    Args:
        answers: The `answers` object of the Jev response.
        chunks: The passages sent in the request, in the same order.

    Returns:
        The ids of the relevant chunks, and whether the question is answerable.

    Raises:
        KeyError: An expected answer is missing.
    """
    settings = get_settings()
    keep = {c.id for i, c in enumerate(chunks) if answers[f"p{i}"]["noul"] >= settings.jev_keep}
    return keep, answers["answerable"]["noul"] >= settings.jev_answerable


@cache
def client() -> httpx.Client:
    """The keep-alive HTTP client for Jev, closed at interpreter exit.

    One connection is reused across calls, which saves the TCP and TLS handshakes of a fresh `httpx.post`.

    Returns:
        The process-wide client.
    """
    jev_client = httpx.Client()
    atexit.register(jev_client.close)
    return jev_client


def _post(question: str, chunks: list[RecordChunk]) -> httpx.Response:
    settings = get_settings()
    key = settings.typesafe_api_key.get_secret_value() if settings.typesafe_api_key else ""
    response = client().post(
        JEV_URL,
        json=request(question, chunks),
        headers={"Authorization": f"Bearer {key}"},
        timeout=settings.jev_timeout,
    )
    response.raise_for_status()
    return response


def _note_response(event: JevEvent, response: httpx.Response, body: dict) -> None:
    """Copy the network time, answerability, usage and model of a Jev response into its event."""
    event.network_ms = round(response.elapsed.total_seconds() * 1000, 1)
    event.answerable_p = body["answers"]["answerable"]["noul"]
    usage = body.get("usage")
    if isinstance(usage, dict):
        event.input_tokens, event.output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    event.model = body.get("model")


def judge(question: str, chunks: list[RecordChunk]) -> tuple[set[str], bool]:
    """Ask Jev which passages help and whether they answer the question, and write a `jev` metric event.

    A Jev outage or a malformed response never blocks an answer: it is logged and every passage is kept.

    Args:
        question: The user question.
        chunks: Passages to judge.

    Returns:
        The ids of the relevant chunks, and whether the question is answerable.
    """
    event, start = JevEvent(questions=len(chunks) + 1, passages_total=len(chunks)), time.perf_counter()
    try:
        response = _post(question, chunks)
        body = response.json()
        keep, answerable = parse(body["answers"], chunks)
        _note_response(event, response, body)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
        logger.warning("Jev failed, keeping every passage: {!r}", e)
        keep, answerable = {c.id for c in chunks}, True
        event.fallback, event.error = True, type(e).__name__
    event.latency_ms, event.passages_kept = metrics.elapsed_ms(start), len(keep)
    metrics.emit(event)
    return keep, answerable
