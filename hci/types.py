"""Type aliases, protocols and domain dataclasses shared across the package."""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np

from hci.constants import Source

Embed = Callable[[list[str]], np.ndarray]  # texts -> L2-normalised (n, d)
Generate = Callable[[str, str], Iterator[str]]  # (system, user) -> text pieces


@dataclass(frozen=True)
class RecordChunk:
    """One retrievable passage of the robot's records."""

    id: str
    text: str
    source: Source
    scenario: int | None = None


@dataclass(frozen=True)
class DocumentSection:
    """A structural part of a document, before it is cut to size.

    Attributes:
        title: Heading path (`Manual > Safety`) or page (`page 3`); empty when the document has no structure.
        paragraphs: The section's paragraphs, whitespace-normalised.
    """

    title: str
    paragraphs: list[str]


@dataclass(frozen=True)
class Retrieval:
    """Result of a retrieval: the context passages and whether the question can be answered from them."""

    chunks: list[RecordChunk]
    answerable: bool = True


class Propose(Protocol):
    """Asks the operator to approve a fact; returns the tool result shown to the model."""

    def __call__(self, text: str, scenario: int | None) -> str: ...


class Answer(Protocol):
    """Streams an answer: text pieces and step lines (starting with `STEP_MARKER`)."""

    def __call__(
        self,
        question: str,
        scenario: int | None = None,
        history: Sequence[tuple[str, str]] = (),
        propose: Propose = ...,
    ) -> Iterator[str]: ...


# --- evaluate ----------------------------------------------------------------


@dataclass(frozen=True)
class CaseResult:
    """Outcome of one eval case.

    Attributes:
        id: Case id.
        recall: Share of the expected chunks that were retrieved; None when the case expects none.
        retrieval_ok: Whether every retrieval expectation held.
        answer_ok: Whether the answer checks held; None when no answer was generated.
    """

    id: str
    recall: float | None
    retrieval_ok: bool
    answer_ok: bool | None = None


@dataclass(frozen=True)
class EvalLatency:
    """Latencies of an eval run, in milliseconds.

    Attributes:
        load_embedder: Embedder load time.
        load_llm: Generator load time.
        retrieve_p50: Median retrieval time; None without cases.
        first_token_p50: Median time to the first answer piece; None without answers.
    """

    load_embedder: float
    load_llm: float
    retrieve_p50: float | None
    first_token_p50: float | None


@dataclass(frozen=True)
class EvalReport:
    """Quality and latency of an eval run.

    Attributes:
        provider: Generation provider used.
        cases: Number of cases run.
        retrieval_pass_rate: Share of cases whose retrieval checks held.
        recall: Mean recall over cases that expect chunks.
        answer_pass_rate: Share of answered cases whose answer checks held.
        latency_ms: Load and per-question latencies.
        tokens_per_s_p50: Median generation speed.
        failures: Cases whose retrieval or answer checks failed.
    """

    provider: str
    cases: int
    retrieval_pass_rate: float | None
    recall: float | None
    answer_pass_rate: float | None
    latency_ms: EvalLatency
    tokens_per_s_p50: float | None
    failures: list[CaseResult]

    def to_dict(self) -> dict:
        """JSON-ready report; `answer_ok` is left out of failures that were not answered.

        Returns:
            The report as nested plain dicts.
        """
        report = asdict(self)
        report["failures"] = [
            {k: v for k, v in f.items() if k != "answer_ok" or v is not None} for f in report["failures"]
        ]
        return report
