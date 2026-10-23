"""Runs every case in tests/cases/*.json against the real retriever (no LLM). See tests/cases/schema.json."""

import json
from functools import cache
from pathlib import Path

import jsonschema
import pytest

from hci import corpus
from hci.rag import RAG

CASES_DIR = Path(__file__).parent / "cases"
SCHEMA = json.loads((CASES_DIR / "schema.json").read_text())
FILES = sorted(p for p in CASES_DIR.glob("*.json") if p.name != "schema.json")
CASES = [(f.stem, case) for f in FILES for case in json.loads(f.read_text())]


@cache
def embedder():
    from hci.index import default_embedder

    return default_embedder()


@pytest.mark.parametrize("path", FILES, ids=[f.stem for f in FILES])
def test_schema(path):
    jsonschema.validate(json.loads(path.read_text()), SCHEMA)


def test_unique_ids():
    ids = [c["id"] for _, c in CASES]
    assert len(ids) == len(set(ids))


def context(case, tmp_path, monkeypatch) -> list[str]:
    monkeypatch.setattr(corpus, "FACTS", tmp_path / "facts.json")
    rag = RAG(embed=embedder(), judge=False)
    for fact in case.get("facts", []):
        rag.add_fact(fact["text"], fact.get("scenario"))
    return [c.id for c in rag.retrieve(case["question"], case.get("scenario"), case.get("history", [])).chunks]


@pytest.mark.parametrize("case", [c for _, c in CASES], ids=[f"{f}/{c['id']}" for f, c in CASES])
def test_case(case, tmp_path, monkeypatch, request):
    if "xfail" in case:
        request.applymarker(pytest.mark.xfail(reason=case["xfail"]))
    ids = context(case, tmp_path, monkeypatch)
    expect = case["expect"]
    assert not set(expect.get("retrieved", [])) - set(ids), ids
    assert not set(expect.get("not_retrieved", [])) & set(ids), ids
    assert ids[: len(expect.get("first", []))] == expect.get("first", []), ids
