"""Tests for hci.evaluate: report shape, per-case fact isolation and pass rates."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hci import evaluate, jev
from hci.config import get_settings
from hci.constants import NOT_FOUND

FACT_CASE = {
    "id": "with-fact",
    "question": "is path B flooded?",
    "scenario": 0,
    "facts": [{"text": "Path B is flooded", "scenario": 0}],
    "expect": {"retrieved": ["fact-0"]},
}
NO_FACT_CASE = {
    "id": "no-fact",
    "question": "is path B flooded?",
    "scenario": 0,
    "expect": {"not_retrieved": ["fact-0"]},
}
FAILING_CASE = {
    "id": "fails",
    "question": "why A?",
    "scenario": 0,
    "expect": {"retrieved": ["no-such-chunk"], "answer_contains": ["answer"]},
}


def _make_cases_dir(tmp_path: Path, *cases: dict) -> Path:
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "cases.json").write_text(json.dumps(list(cases)))
    (cases_dir / "schema.json").write_text("{}")  # skipped by load_cases
    return cases_dir


@pytest.fixture(autouse=True)
def offline(monkeypatch: pytest.MonkeyPatch, fake_embed, fake_answer) -> None:
    """The eval runs on the fake embedder and the fake answerer: no model is loaded."""
    monkeypatch.setattr(evaluate, "default_embedder", lambda: fake_embed)
    monkeypatch.setattr(evaluate, "answerer", lambda rag, provider, model: fake_answer)


def test_report_has_every_key(tmp_path):
    """The JSON report carries quality, latency and failures."""
    # Act
    report = evaluate.run("cpu", None, answers=False, cases_dir=_make_cases_dir(tmp_path, NO_FACT_CASE))
    # Assert
    assert set(report) == {
        "provider",
        "cases",
        "retrieval_pass_rate",
        "recall",
        "answer_pass_rate",
        "latency_ms",
        "tokens_per_s_p50",
        "failures",
    }
    assert set(report["latency_ms"]) == {"load_embedder", "load_llm", "retrieve_p50", "first_token_p50"}


def test_case_facts_are_isolated(tmp_path, monkeypatch, facts_file):
    """Each case sees only its own facts, in a temp dir removed afterwards; the real facts file is untouched."""
    # Arrange
    temp_root = tmp_path / "temp"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
    cases_dir = _make_cases_dir(tmp_path, FACT_CASE, NO_FACT_CASE)
    # Act
    report = evaluate.run("cpu", None, answers=False, cases_dir=cases_dir)
    # Assert
    assert report["retrieval_pass_rate"] == 1.0
    assert list(temp_root.iterdir()) == []
    assert get_settings().facts_file == facts_file
    assert not facts_file.exists()


def test_rates_skip_cases_without_the_check(tmp_path):
    """Recall and answer rates average only the cases that expect them; failures list the failing case."""
    # Arrange
    cases_dir = _make_cases_dir(tmp_path, FACT_CASE, NO_FACT_CASE, FAILING_CASE)
    # Act
    report = evaluate.run("cpu", None, answers=True, cases_dir=cases_dir)
    # Assert
    assert report["retrieval_pass_rate"] == 0.667
    assert report["recall"] == 0.5  # 1.0 and 0.0; the no-fact case expects no chunk
    assert report["answer_pass_rate"] == 1.0  # only the failing case has answer checks
    assert report["failures"] == [{"id": "fails", "recall": 0.0, "retrieval_ok": False, "answer_ok": True}]


@pytest.mark.parametrize(("markers", "passes"), [(["no record", "answer to"], True), (["no record"], False)])
def test_answer_contains_any(tmp_path, markers, passes):
    """`answer_contains_any` passes when at least one marker appears in the answer, case-insensitively."""
    # Arrange
    case = {"id": "any", "question": "Why A?", "scenario": 0, "expect": {"answer_contains_any": markers}}
    # Act
    report = evaluate.run("cpu", None, answers=True, cases_dir=_make_cases_dir(tmp_path, case))
    # Assert
    assert report["answer_pass_rate"] == (1.0 if passes else 0.0)


UNANSWERABLE_CASE = {
    "id": "unanswerable",
    "question": "How long is path D?",
    "scenario": 0,
    "unanswerable": True,
    "expect": {"first": ["no-such-chunk"]},
}


@pytest.mark.parametrize(("answerable", "passes"), [(False, True), (True, False)])
def test_unanswerable_with_judge_passes_iff_jev_refuses(tmp_path, monkeypatch, answerable, passes):
    """With the judge on, an unanswerable case passes retrieval iff Jev refuses; its pinning expectations are skipped.

    A Jev refusal streams `NOT_FOUND`, which satisfies the default refusal markers.
    """
    # Arrange
    monkeypatch.setattr(jev, "judge", lambda query, chunks: ({c.id for c in chunks}, answerable))
    monkeypatch.setattr(
        evaluate, "answerer", lambda rag, provider, model: lambda q, s, h: rag.answer(q, MagicMock(), s, h)
    )
    # Act
    report = evaluate.run("cpu", None, cases_dir=_make_cases_dir(tmp_path, UNANSWERABLE_CASE), judge=True)
    # Assert
    assert report["retrieval_pass_rate"] == (1.0 if passes else 0.0)
    if passes:
        assert report["answer_pass_rate"] == 1.0


def test_unanswerable_without_judge_uses_retrieval_expectations(tmp_path):
    """With the judge off, an unanswerable case is scored on its normal retrieval expectations."""
    # Act
    report = evaluate.run("cpu", None, answers=False, cases_dir=_make_cases_dir(tmp_path, UNANSWERABLE_CASE))
    # Assert
    assert report["retrieval_pass_rate"] == 0.0


@pytest.mark.parametrize(
    ("answer", "marker"),
    [("I can’t say", "can't say"), ("I can‘t say", "can't say"), ("I can't say", "can’t say")],
)
def test_curly_apostrophes_match_straight_ones(answer, marker):
    """Curly apostrophes match straight ones, in the answer and in the case strings."""
    # Arrange
    case = {"expect": {"answer_contains_any": [marker]}}
    # Act / Assert
    assert evaluate._answer_ok(answer, case)


OUT_OF_SCOPE = {c["id"]: c for c in evaluate.load_cases() if "out-of-scope" in c.get("tags", [])}


@pytest.mark.parametrize(
    ("case_id", "answer", "passes"),
    [
        ("oos-nonexistent-path", "Path D takes 12 s, but I can't confirm it.", False),
        ("oos-nonexistent-path", "Path D is about 200 m. I don't know more from the records.", False),
        ("oos-stock-market", "The market will go up, I cannot be sure.", False),
        ("oos-capital-of-france", "Paris, but I don't know it from the robot's records.", False),
        ("oos-stock-market", "I can't say whether the market will go up tomorrow from the robot's records.", True),
        ("oos-nonexistent-path", "Path D is not mentioned in the context. Paths A, B and C are.", True),
        ("oos-capital-of-france", NOT_FOUND, True),
    ],
)
def test_out_of_scope_answers(case_id, answer, passes):
    """A refusal passes even when it restates the question; a hedged or fabricated answer fails."""
    # Act / Assert
    assert evaluate._answer_ok(answer, OUT_OF_SCOPE[case_id]) is passes
