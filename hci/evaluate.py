"""`hci eval`: runs the JSON cases end to end (real embedder + LLM) and reports quality and latency."""

import json
import statistics
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from hci.agent import answerer
from hci.config import get_settings
from hci.constants import CASES_DIR, STEP_MARKER
from hci.device import backend
from hci.index import default_embedder
from hci.rag import ExplanationPipeline, text_only
from hci.types import Answer, CaseResult, EvalLatency, EvalReport


def load_cases(cases_dir: Path = CASES_DIR) -> list[dict]:
    """Reads every case file of a directory, skipping the JSON schema.

    Args:
        cases_dir: Directory holding the `*.json` case files.

    Returns:
        The cases, file by file in name order.
    """
    files = sorted(f for f in cases_dir.glob("*.json") if f.name != "schema.json")
    return [case for f in files for case in json.loads(f.read_text())]


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 1)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _rate(values: list[float | bool | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(sum(known) / len(known), 3) if known else None


@contextmanager
def _isolated_facts(rag: ExplanationPipeline, case: dict) -> Generator[None]:
    """Points the facts file at a fresh temp dir holding only the case's facts, so real facts are never touched."""
    settings = get_settings()
    saved = settings.facts_file
    with tempfile.TemporaryDirectory() as tmp:
        settings.facts_file = Path(tmp) / "facts.json"
        try:
            rag.reload()
            for fact in case.get("facts", []):
                rag.add_fact(fact["text"], fact.get("scenario"))
            yield
        finally:
            settings.facts_file = saved


def _score_retrieval(ids: list[str], expect: dict) -> tuple[float | None, bool]:
    """Recall of the expected chunks, and whether all retrieval expectations hold."""
    want, got = set(expect.get("retrieved", [])), set(ids)
    first = expect.get("first", [])
    recall = len(want & got) / len(want) if want else None
    return recall, not want - got and not set(expect.get("not_retrieved", [])) & got and ids[: len(first)] == first


def _time_answer(answer: Answer, case: dict) -> tuple[bool, float, float | None]:
    """Streams one answer; returns whether it passes, the first-token delay and tokens per second."""
    t0, first, pieces = time.perf_counter(), None, []
    for piece in answer(case["question"], case.get("scenario"), case.get("history", [])):
        if not piece.startswith(STEP_MARKER):
            first = first or time.perf_counter()
            pieces.append(piece)
    end, text = time.perf_counter(), text_only(pieces).lower()
    first = first or end
    tok_s = (len(pieces) - 1) / (end - first) if end > first and len(pieces) > 1 else None  # ~1 token per piece
    expect = case["expect"]
    ok = all(s.lower() in text for s in expect.get("answer_contains", [])) and not any(
        s.lower() in text for s in expect.get("answer_excludes", [])
    )
    return ok, first - t0, tok_s


def _run_case(
    rag: ExplanationPipeline, answer: Answer | None, case: dict
) -> tuple[CaseResult, float, tuple[float, float | None] | None]:
    """Runs one case with its own facts; returns its result, retrieval time and (first token, tokens/s) if answered."""
    expect = case["expect"]
    with _isolated_facts(rag, case):
        t0 = time.perf_counter()
        retrieval = rag.retrieve(case["question"], case.get("scenario"), case.get("history", []))
        retrieve_s = time.perf_counter() - t0
        recall, retrieval_ok = _score_retrieval([c.id for c in retrieval.chunks], expect)
        if not answer or not {"answer_contains", "answer_excludes"} & expect.keys():
            return CaseResult(case["id"], recall, retrieval_ok), retrieve_s, None
        answer_ok, first_s, tok_s = _time_answer(answer, case)
    return CaseResult(case["id"], recall, retrieval_ok, answer_ok), retrieve_s, (first_s, tok_s)


def _report(
    provider: str,
    results: list[CaseResult],
    loads: tuple[float, float],
    retrieve_t: list[float],
    answer_t: list[tuple[float, float | None]],
) -> EvalReport:
    """Aggregates per-case results and timings into the report."""
    first_t = [first for first, _ in answer_t]
    tok_s = [t for _, t in answer_t if t is not None]
    retrieve_p50, first_p50, tok_p50 = _median(retrieve_t), _median(first_t), _median(tok_s)
    latency = EvalLatency(
        load_embedder=_ms(loads[0]),
        load_llm=_ms(loads[1]),
        retrieve_p50=None if retrieve_p50 is None else _ms(retrieve_p50),
        first_token_p50=None if first_p50 is None else _ms(first_p50),
    )
    return EvalReport(
        provider=provider,
        cases=len(results),
        retrieval_pass_rate=_rate([r.retrieval_ok for r in results]),
        recall=_rate([r.recall for r in results]),
        answer_pass_rate=_rate([r.answer_ok for r in results]),
        latency_ms=latency,
        tokens_per_s_p50=None if tok_p50 is None else round(tok_p50, 1),
        failures=[r for r in results if not r.retrieval_ok or r.answer_ok is False],
    )


def run(provider: str | None, model: str | None, answers: bool = True, cases_dir: Path = CASES_DIR) -> dict:
    """Runs every case end to end and reports quality and latency.

    Args:
        provider: Generation provider; None picks the local backend.
        model: Model name or path; None uses the provider default.
        answers: Whether to generate and check answers (slow), or only retrieval.
        cases_dir: Directory holding the `*.json` case files.

    Returns:
        The `EvalReport` as a JSON-ready dict.
    """
    t0 = time.perf_counter()
    embed = default_embedder()
    load_embed = time.perf_counter() - t0
    rag = ExplanationPipeline(embed=embed, judge=False)
    t0 = time.perf_counter()
    answer = answerer(rag, provider, model) if answers else None
    load_llm = time.perf_counter() - t0
    runs = [_run_case(rag, answer, case) for case in load_cases(cases_dir)]
    results, retrieve_t = [r for r, _, _ in runs], [t for _, t, _ in runs]
    answer_t = [a for _, _, a in runs if a is not None]
    return _report(provider or backend(), results, (load_embed, load_llm), retrieve_t, answer_t).to_dict()
