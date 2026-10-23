"""Type aliases, protocols and domain dataclasses shared across the package."""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass, field
from typing import ClassVar, Protocol

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
class ParsedDocument:
    """The chunks of one document file at one version, cached until the file changes.

    Attributes:
        version: `(mtime_ns, size)` of the file when it was parsed.
        chunks: Its chunks; empty when it could not be read.
        error: Why it gave no chunks; None when it gave some.
    """

    version: tuple[int, int]
    chunks: list[RecordChunk]
    error: str | None = None


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


# --- metrics -----------------------------------------------------------------


@dataclass
class RequestEvent:
    """One answer, end to end; filled while it streams, written when it ends.

    Attributes:
        provider: Where generation ran (`mlx`, `cuda`, `cpu`, `anthropic`).
        model: Model name or Claude model id.
        scenario: Current scenario index.
        question_chars: Length of the question.
        question: The question text, only when `metrics_log_questions` is on.
        ttft_ms: Time to the first answer text piece (step lines do not count).
        total_ms: Time to the end of the stream.
        itl_mean_ms: Mean gap between successive answer text pieces.
        itl_p50_ms: Median gap between pieces.
        itl_p95_ms: 95th percentile gap between pieces.
        itl_max_ms: Largest gap between pieces.
        output_pieces: Answer text pieces streamed.
        output_tokens: Tokens generated, as counted by the model (all Claude turns summed).
        tokens_per_s: `output_tokens` over `model_ms` for Claude, else over the first-to-last text piece span.
        model_ms: Claude: time in model turns, request sent to final message, tools excluded. None locally.
        tool_ms: Claude: time in agent tools.
        input_tokens: Prompt tokens (all Claude turns summed, cache excluded).
        cache_creation_input_tokens: Claude prompt tokens written to the cache.
        cache_read_input_tokens: Claude prompt tokens read from the cache.
        stop_reason: Why generation stopped (last Claude turn, or the MLX finish reason).
        refusal: Claude stopped with `refusal`.
        fallback_model: Model that served the turn when Claude fell back server-side.
        error: Class of the error that ended the answer.
    """

    kind: ClassVar[str] = "request"
    provider: str | None = None
    model: str | None = None
    scenario: int | None = None
    question_chars: int = 0
    question: str | None = None
    ttft_ms: float | None = None
    total_ms: float | None = None
    itl_mean_ms: float | None = None
    itl_p50_ms: float | None = None
    itl_p95_ms: float | None = None
    itl_max_ms: float | None = None
    output_pieces: int = 0
    output_tokens: int | None = None
    tokens_per_s: float | None = None
    model_ms: float | None = None
    tool_ms: float | None = None
    input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    cache_read_input_tokens: int | None = None
    stop_reason: str | None = None
    refusal: bool = False
    fallback_model: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RetrievalEvent:
    """One retrieval.

    Attributes:
        latency_ms: Time spent, Jev included.
        k: Searched passages asked for, on top of the pinned ones.
        chunks: Passages returned.
        pinned: Pinned passages (scenario steps and facts).
        judged: Whether Jev filtered the passages.
        answerable: Whether the question was found answerable.
    """

    kind: ClassVar[str] = "retrieval"
    latency_ms: float
    k: int
    chunks: int
    pinned: int
    judged: bool
    answerable: bool


@dataclass
class JevEvent:
    """One Jev judge call.

    Attributes:
        latency_ms: Whole call: request, network and parsing.
        network_ms: Time from sending the request to the end of the response (httpx `elapsed`).
        questions: Questions asked (one per passage, plus answerability).
        passages_total: Passages sent.
        passages_kept: Passages kept (all of them on a fallback).
        answerable_p: Jev's probability that the passages answer the question; None on a fallback.
        input_tokens: Jev usage, input side.
        output_tokens: Jev usage, output side.
        model: Jev model that answered.
        fallback: Jev failed and every passage was kept.
        error: Class of the error behind the fallback.
    """

    kind: ClassVar[str] = "jev"
    latency_ms: float = 0
    network_ms: float | None = None
    questions: int = 0
    passages_total: int = 0
    passages_kept: int = 0
    answerable_p: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    fallback: bool = False
    error: str | None = None


@dataclass
class ToolEvent:
    """One agent tool call. Never holds the tool input or result, only their size.

    Attributes:
        tool: Tool name.
        duration_ms: Time spent in the tool.
        ok: The tool returned without raising.
        result_chars: Length of the result sent back to Claude.
        passages: Passages found, for `query_context`.
    """

    kind: ClassVar[str] = "tool"
    tool: str
    duration_ms: float = 0
    ok: bool = True
    result_chars: int = 0
    passages: int | None = None


@dataclass(frozen=True)
class ModelTurnEvent:
    """One Claude turn of the agent loop.

    Attributes:
        duration_ms: Time from sending the turn's request to its final message, tools excluded.
        model: Model that answered.
        input_tokens: Prompt tokens, cache excluded.
        output_tokens: Generated tokens, thinking and tool calls included.
        cache_creation_input_tokens: Prompt tokens written to the cache.
        cache_read_input_tokens: Prompt tokens read from the cache.
        stop_reason: Why the turn ended.
        fallback_model: Model that served the turn after a server-side fallback.
    """

    kind: ClassVar[str] = "model_turn"
    duration_ms: float
    model: str | None
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int | None
    cache_read_input_tokens: int | None
    stop_reason: str | None
    fallback_model: str | None = None


MetricEvent = RequestEvent | RetrievalEvent | JevEvent | ToolEvent | ModelTurnEvent


@dataclass(frozen=True)
class MetricScope:
    """The answer the events being written belong to.

    Attributes:
        request_id: Ties the events of one answer together.
        source: `cli`, `server` or `eval`.
        request: The answer's request event, filled as it streams.
    """

    request_id: str
    source: str
    request: RequestEvent = field(default_factory=RequestEvent)
