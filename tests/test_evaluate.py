"""Tests for hci.evaluate: report shape, per-case fact isolation and pass rates."""

import json
import tempfile
from pathlib import Path

import pytest

from hci import evaluate
from hci.config import get_settings

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


def test_eval_events_carry_the_eval_source(tmp_path):
    """Eval retrievals and answers are logged with source `eval`; the answer keeps its own request id."""
    # Arrange
    cases_dir = _make_cases_dir(tmp_path, FAILING_CASE)
    # Act
    evaluate.run("cpu", None, answers=True, cases_dir=cases_dir)
    # Assert
    events = [json.loads(line) for line in get_settings().metrics_file.read_text().splitlines()]
    assert [e["kind"] for e in events] == ["retrieval", "request"]
    assert {e["source"] for e in events} == {"eval"}
    assert events[0]["request_id"] != events[1]["request_id"]
