"""Runs every case in tests/cases/*.json against the real retriever (no LLM). See tests/cases/schema.json."""

import json
from functools import cache
from pathlib import Path

import jsonschema
import pytest

from hci import corpus
from hci.config import get_settings
from hci.constants import DOCUMENTS_DIR, ROOT_DIR, UPLOADS_DIRNAME
from hci.documents import file_ref
from hci.index import default_embedder
from hci.rag import ExplanationPipeline
from hci.types import Embed

CASES_DIR = Path(__file__).parent / "cases"
SCHEMA = json.loads((CASES_DIR / "schema.json").read_text())
FILES = sorted(p for p in CASES_DIR.glob("*.json") if p.name != "schema.json")
CASES = [(f.stem, case) for f in FILES for case in json.loads(f.read_text())]
EXPECT_ID_KEYS = ("retrieved", "not_retrieved", "first")


@cache
def _embedder() -> Embed:
    return default_embedder()


def _context(case: dict) -> list[str]:
    rag = ExplanationPipeline(embed=_embedder(), judge=False)
    for fact in case.get("facts", []):
        rag.add_fact(fact["text"], fact.get("scenario"))
    return [c.id for c in rag.retrieve(case["question"], case.get("scenario"), case.get("history", [])).chunks]


@pytest.mark.parametrize("path", FILES, ids=[f.stem for f in FILES])
def test_schema(path):
    """Every case file follows tests/cases/schema.json."""
    jsonschema.validate(json.loads(path.read_text()), SCHEMA)


def test_unique_ids():
    """Case ids are unique across files."""
    ids = [c["id"] for _, c in CASES]
    assert len(ids) == len(set(ids))


UPLOADS_REF = file_ref(DOCUMENTS_DIR / UPLOADS_DIRNAME) + "/"


def _repo_ids() -> frozenset[str]:
    """Chunk ids of the repo's data; local phone uploads are git-ignored, so they are left out."""
    return frozenset(c.id for c in corpus.load() if not c.id.startswith(UPLOADS_REF))


def _bad_reference(case: dict, ref: str, repo_ids: frozenset[str]) -> str | None:
    """Why a chunk id of a case does not resolve, or None when it does."""
    if ref.startswith("fact-"):  # facts live in a runtime file, not in git: `fact-<n>` is the case's n-th fact
        n = ref.removeprefix("fact-")
        return None if n.isdigit() and int(n) < len(case.get("facts", [])) else "no such fact in the case"
    if ref.startswith(UPLOADS_REF):
        return "points at a git-ignored upload"
    if not (ROOT_DIR / ref.split("#")[0]).is_file():
        return "file not found"
    return None if ref in repo_ids else "no such chunk in corpus.load()"


@pytest.mark.parametrize("case", [c for _, c in CASES], ids=[f"{f}/{c['id']}" for f, c in CASES])
def test_references_resolve(case, monkeypatch):
    """Every chunk id a case expects is an existing file of the repo and a chunk that `corpus.load()` produces."""
    # Arrange
    monkeypatch.setenv("HCI_DOCUMENTS_DIR", str(DOCUMENTS_DIR))
    get_settings.cache_clear()
    refs = {ref for key in EXPECT_ID_KEYS for ref in case["expect"].get(key, [])}
    repo_ids = _repo_ids()
    # Act
    bad = {ref: why for ref in sorted(refs) if (why := _bad_reference(case, ref, repo_ids))}
    # Assert
    assert not bad, f"case {case['id']}: bad references {bad}"


@pytest.mark.embedder
@pytest.mark.parametrize("case", [c for _, c in CASES], ids=[f"{f}/{c['id']}" for f, c in CASES])
def test_case(case, request):
    """The case's question retrieves the expected chunks, in its scenario, with its history and facts."""
    # Arrange
    if "xfail" in case:
        request.applymarker(pytest.mark.xfail(reason=case["xfail"]))
    expect = case["expect"]
    # Act
    ids = _context(case)
    # Assert
    assert not set(expect.get("retrieved", [])) - set(ids), ids
    assert not set(expect.get("not_retrieved", [])) & set(ids), ids
    assert ids[: len(expect.get("first", []))] == expect.get("first", []), ids
