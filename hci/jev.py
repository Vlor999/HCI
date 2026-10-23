"""Optional Jev judge (TypeSafe AI): filters retrieved passages and gates unanswerable questions.

Enabled when TYPESAFE_API_KEY is set. One request judges every passage plus answerability.
API: POST https://api.typesafe.ai/v1/systemone, see docs.typesafe.ai/primitives.
"""

import os

import httpx

from hci.constants import JEV_ANSWERABLE_QUESTION, JEV_PASSAGE_QUESTION, JEV_URL
from hci.types import RecordChunk

MODEL = os.environ.get("HCI_JEV_MODEL", "jev-latest")
KEEP = float(os.environ.get("HCI_JEV_KEEP", "0.5"))  # min P(relevant) to keep a passage
ANSWERABLE = float(os.environ.get("HCI_JEV_ANSWERABLE", "0.3"))  # tune on questions absent from the docs


def enabled() -> bool:
    return bool(os.environ.get("TYPESAFE_API_KEY"))


def request(question: str, chunks: list[RecordChunk]) -> dict:
    questions = {
        f"p{i}": {"type": "noul", "instructions": JEV_PASSAGE_QUESTION.format(key=f"p{i}")} for i in range(len(chunks))
    }
    questions["answerable"] = {
        "type": "noul",
        "instructions": JEV_ANSWERABLE_QUESTION,
    }
    return {
        "model": MODEL,
        "state": {"query": question, "passages": {f"p{i}": c.text for i, c in enumerate(chunks)}},
        "questions": questions,
    }


def parse(answers: dict, chunks: list[RecordChunk]) -> tuple[set[str], bool]:
    """-> (ids of relevant chunks, is the question answerable)."""
    keep = {c.id for i, c in enumerate(chunks) if answers[f"p{i}"]["noul"] >= KEEP}
    return keep, answers["answerable"]["noul"] >= ANSWERABLE


def judge(question: str, chunks: list[RecordChunk]) -> tuple[set[str], bool]:
    r = httpx.post(
        JEV_URL,
        json=request(question, chunks),
        headers={"Authorization": f"Bearer {os.environ['TYPESAFE_API_KEY']}"},
        timeout=10,
    )
    r.raise_for_status()
    return parse(r.json()["answers"], chunks)
