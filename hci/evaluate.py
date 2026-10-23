"""`hci eval`: runs tests/cases/*.json end to end (real embedder + LLM) and reports quality and latency as JSON."""

import json
import statistics
import tempfile
import time
from pathlib import Path

from hci.agent import answerer
from hci.config import get_settings
from hci.constants import CASES_DIR, STEP_MARKER
from hci.device import backend
from hci.index import default_embedder
from hci.rag import ExplanationPipeline, text_only


def cases() -> list[dict]:
    return [c for f in sorted(CASES_DIR.glob("*.json")) if f.name != "schema.json" for c in json.loads(f.read_text())]


def ms(seconds: float) -> float:
    return round(seconds * 1000, 1)


def run(provider: str | None, model: str | None, answers: bool = True) -> dict:
    t0 = time.perf_counter()
    embed = default_embedder()
    load_embed = time.perf_counter() - t0
    settings = get_settings()
    facts_file = settings.facts_file
    settings.facts_file = Path(tempfile.mkdtemp()) / "facts.json"  # never touch real facts
    rag = ExplanationPipeline(embed=embed, judge=False)
    t0 = time.perf_counter()
    answer = answerer(rag, provider, model) if answers else None
    load_llm = time.perf_counter() - t0

    rows, retrieve_t, first_t, tok_s = [], [], [], []
    try:
        for case in cases():
            settings.facts_file.unlink(missing_ok=True)
            rag.reload()
            for fact in case.get("facts", []):
                rag.add_fact(fact["text"], fact.get("scenario"))
            expect, row = case["expect"], {"id": case["id"]}

            t0 = time.perf_counter()
            ids = [c.id for c in rag.retrieve(case["question"], case.get("scenario"), case.get("history", [])).chunks]
            retrieve_t.append(time.perf_counter() - t0)
            want = expect.get("retrieved", [])
            row["recall"] = len(set(want) & set(ids)) / len(want) if want else None
            row["retrieval_ok"] = (
                not set(want) - set(ids)
                and not set(expect.get("not_retrieved", [])) & set(ids)
                and ids[: len(expect.get("first", []))] == expect.get("first", [])
            )

            if answer and ("answer_contains" in expect or "answer_excludes" in expect):
                t0, first, pieces = time.perf_counter(), None, []
                for p in answer(case["question"], case.get("scenario"), case.get("history", [])):
                    if not p.startswith(STEP_MARKER):
                        first = first or time.perf_counter()
                        pieces.append(p)
                end, text = time.perf_counter(), text_only(pieces).lower()
                first = first or end
                first_t.append(first - t0)
                if end > first and len(pieces) > 1:
                    tok_s.append((len(pieces) - 1) / (end - first))  # mlx/hf stream ~1 token per piece
                row["answer_ok"] = all(s.lower() in text for s in expect.get("answer_contains", [])) and not any(
                    s.lower() in text for s in expect.get("answer_excludes", [])
                )
            rows.append(row)
    finally:
        settings.facts_file = facts_file

    def rate(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 3) if vals else None

    return {
        "provider": provider or backend(),
        "cases": len(rows),
        "retrieval_pass_rate": rate("retrieval_ok"),
        "recall": rate("recall"),
        "answer_pass_rate": rate("answer_ok"),
        "latency_ms": {
            "load_embedder": ms(load_embed),
            "load_llm": ms(load_llm),
            "retrieve_p50": ms(statistics.median(retrieve_t)) if retrieve_t else None,
            "first_token_p50": ms(statistics.median(first_t)) if first_t else None,
        },
        "tokens_per_s_p50": round(statistics.median(tok_s), 1) if tok_s else None,
        "failures": [r for r in rows if r["retrieval_ok"] is False or r.get("answer_ok") is False],
    }
