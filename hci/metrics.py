"""Live metrics: every answer appends structured events to a JSONL file (`metrics_file`).

`track` wraps an answer stream. It gives the answer a request id, times its text pieces and writes a `request`
event when the stream ends. Code running inside the stream (retrieval, Jev, agent tools and turns) calls `emit`,
`update` and `add`; their events carry the same request id. No question text (unless `metrics_log_questions`),
document content, tool input, key or token is ever written.
"""

import contextvars
import json
import threading
import time
import uuid
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import numpy as np
from loguru import logger

from hci.config import get_settings
from hci.constants import STEP_MARKER
from hci.types import CostBreakdown, MetricEvent, MetricScope, RequestEvent, ToolEvent

# ponytail: one lock per process; `hci serve` and `hci eval` writing at once rely on small O_APPEND writes not
# interleaving. A queue to one writer if lines ever get large.
_write_lock = threading.Lock()
_scope: contextvars.ContextVar[MetricScope | None] = contextvars.ContextVar("metric_scope", default=None)
_parsed: dict[Path, tuple[tuple[int, int], list[dict]]] = {}  # path -> ((mtime_ns, size), events)


def percentile(values: Sequence[float], q: float) -> float | None:
    """Percentile with linear interpolation between ranks.

    Args:
        values: The sample.
        q: Percentile, 0 to 100.

    Returns:
        The percentile, or None for an empty sample.
    """
    return float(np.percentile(values, q)) if len(values) else None


def elapsed_ms(start: float, end: float | None = None) -> float:
    """Milliseconds between two `time.perf_counter` readings, rounded to 0.1 ms.

    Args:
        start: The first reading.
        end: The second one; None reads the clock now.

    Returns:
        The elapsed time in ms.
    """
    return round(((time.perf_counter() if end is None else end) - start) * 1000, 1)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def fill_timing(request: RequestEvent, start: float, text_times: list[float], end: float) -> None:
    """Set the latency fields of a request from its clock readings.

    Args:
        request: The event to fill.
        start: Clock when the answer started.
        text_times: Clock at each answer text piece (step lines excluded).
        end: Clock when the stream ended.
    """
    request.total_ms = elapsed_ms(start, end)
    request.output_pieces = len(text_times)
    if not text_times:
        return
    request.ttft_ms = elapsed_ms(start, text_times[0])
    gaps = [(b - a) * 1000 for a, b in zip(text_times, text_times[1:])]
    if gaps:
        request.itl_mean_ms = _round(sum(gaps) / len(gaps))
        request.itl_p50_ms, request.itl_p95_ms = _round(percentile(gaps, 50)), _round(percentile(gaps, 95))
        request.itl_max_ms = _round(max(gaps))
    # Claude's text can reach us in one burst after the turn, so its rate is over model time, not the text span
    span = request.model_ms / 1000 if request.model_ms else text_times[-1] - text_times[0]
    if request.output_tokens and span > 0:
        request.tokens_per_s = _round(request.output_tokens / span)


def record(event: MetricEvent, scope: MetricScope | None) -> dict:
    """The JSON record of an event: kind, timestamp (now), request, conversation and source, then its fields.

    Args:
        event: The event.
        scope: The answer it belongs to; None outside an answer.

    Returns:
        A JSON-ready dict.
    """
    envelope = {
        "kind": event.kind,
        "ts": round(time.time(), 6),
        "request_id": scope.request_id if scope else None,
        "conversation_id": scope.conversation_id if scope else None,
        "source": scope.source if scope else None,
    }
    return envelope | asdict(event)


def emit(event: MetricEvent) -> None:
    """Append an event to the metrics file, rotating it first when full.

    Metrics never break an answer: a disk error or an event that cannot be serialized is logged and dropped. The
    timestamp is taken under the write lock, so timestamps follow the file order and the page's `since` cursor
    never skips a line.

    Args:
        event: The event; it joins the current answer's request id, if any.
    """
    settings = get_settings()
    if not settings.metrics_enabled:
        return
    scope, path = _scope.get(), settings.metrics_file
    try:
        with _write_lock:
            line = json.dumps(record(event, scope)) + "\n"
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate(path, settings.metrics_max_mb)
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
    except (OSError, TypeError, ValueError) as e:
        logger.warning("Metric event dropped ({}): {!r}", path, e)


def _backup(path: Path) -> Path:
    return path.with_name(path.name + ".1")


def _rotate(path: Path, max_mb: float) -> None:
    # ponytail: the lock is per process; two processes rotating at once can still lose one backup. A file lock
    # (fcntl.flock) if several writers ever share a file at its limit.
    try:
        full = path.stat().st_size >= max_mb * 1024 * 1024  # checked under the lock, right before the replace
        if full:
            path.replace(_backup(path))
    except FileNotFoundError:  # not created yet, or rotated away by another process in between
        return


def read(since: float | None = None, limit: int | None = None) -> list[dict]:
    """Events of the backup then the current metrics file, oldest first.

    Args:
        since: Only events with a timestamp after this one (epoch seconds).
        limit: Only the last `limit` events.

    Returns:
        The events; malformed lines are skipped.
    """
    path = get_settings().metrics_file
    events = [e for p in (_backup(path), path) for e in _cached(p)]
    if since is not None:
        events = [e for e in events if e.get("ts", 0) > since]
    return events[-limit:] if limit else events


def _cached(path: Path) -> list[dict]:
    """The file's events, parsed again only when its (mtime, size) changed; none when it does not exist."""
    try:
        stat = path.stat()
        version = (stat.st_mtime_ns, stat.st_size)
        if path in _parsed and _parsed[path][0] == version:
            return _parsed[path][1]
        events = list(_parse(path.read_text(encoding="utf-8")))
    except FileNotFoundError:  # rotated or not created yet
        return []
    _parsed[path] = (version, events)
    return events


def _parse(text: str) -> Iterator[dict]:
    # ponytail: the current file is parsed again whenever it grows, bounded by metrics_max_mb; parse only the new
    # bytes from the last offset if polling gets slow
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def _pull(stream: Iterator[str]) -> str | None:
    return next(stream, None)


def new_id() -> str:
    """A short random id for a request or a conversation.

    Returns:
        12 hex characters.
    """
    return uuid.uuid4().hex[:12]


def _new_scope(source: str, question: str, scenario: int | None, conversation_id: str | None) -> MetricScope:
    logged = question if get_settings().metrics_log_questions else None
    request = RequestEvent(scenario=scenario, question_chars=len(question), question=logged)
    return MetricScope(new_id(), source, conversation_id, request)


@contextmanager
def scope(
    source: str, question: str = "", scenario: int | None = None, conversation_id: str | None = None
) -> Generator[MetricScope]:
    """Give the events written in a block their own request id, without a request event.

    Args:
        source: `cli`, `server` or `eval`.
        question: The question, for its length.
        scenario: Current scenario index.
        conversation_id: Conversation the block belongs to.

    Yields:
        The scope.
    """
    current = _new_scope(source, question, scenario, conversation_id)
    token = _scope.set(current)
    try:
        yield current
    finally:
        _scope.reset(token)


def track(
    pieces: Iterable[str],
    source: str,
    question: str,
    scenario: int | None,
    conversation_id: str | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> Iterator[str]:
    """Pass an answer stream through, timing it, and write its `request` event when it ends.

    Each piece is pulled inside the answer's own context, so code running in the stream sees its scope even when a
    server resumes the stream from different worker threads.

    Args:
        pieces: The answer stream (text pieces and step lines).
        source: `cli`, `server` or `eval`.
        question: The question, for its length (and text, when `metrics_log_questions` is on).
        scenario: Current scenario index.
        conversation_id: Conversation the answer belongs to.
        clock: Monotonic clock in seconds.

    Yields:
        The pieces, unchanged.
    """
    current = _new_scope(source, question, scenario, conversation_id)
    context = contextvars.copy_context()
    context.run(_scope.set, current)
    stream, text_times, start = iter(pieces), [], clock()
    try:
        while (piece := context.run(_pull, stream)) is not None:
            if piece and not piece.startswith(STEP_MARKER):  # empty pieces carry no text
                text_times.append(clock())
            yield piece
    except Exception as e:
        current.request.error = type(e).__name__
        raise
    finally:
        fill_timing(current.request, start, text_times, clock())
        fill_cost(current.request)
        context.run(emit, current.request)


def update(**fields: object) -> None:
    """Set fields of the current answer's request event; no-op outside an answer.

    Args:
        **fields: `RequestEvent` field values.
    """
    current = _scope.get()
    if current is None:
        return
    for name, value in fields.items():
        setattr(current.request, name, value)


def fill_cost(request: RequestEvent) -> None:
    """Set the request's total cost from its priced components: None when nothing could be priced.

    Args:
        request: The event to fill.
    """
    priced = request.cost != CostBreakdown() or not request.price_unknown
    request.cost_usd = request.cost.total if priced else None


def add_cost(cost: CostBreakdown | None) -> None:
    """Add a call's cost to the current answer, or flag it as partly unpriced when the cost is unknown.

    Args:
        cost: The call's cost; None when its price is unknown.
    """
    request = current()
    if request is None:
        return
    if cost is None:
        request.price_unknown = True
    else:
        request.cost = request.cost.plus(cost)


def current() -> RequestEvent | None:
    """The request event of the answer streaming in this context.

    Returns:
        It, or None outside an answer.
    """
    scope = _scope.get()
    return scope.request if scope else None


def add(**counts: float | None) -> None:
    """Add to counters of the current answer's request event (unknown counters start at 0); None is skipped.

    Args:
        **counts: `RequestEvent` token and time counters.
    """
    current = _scope.get()
    if current is None:
        return
    for name, value in counts.items():
        if value is not None:
            setattr(current.request, name, (getattr(current.request, name) or 0) + value)


@contextmanager
def tool(name: str) -> Generator[ToolEvent]:
    """Time an agent tool call and write its event, `ok` False if it raised.

    Args:
        name: Tool name.

    Yields:
        The event; the tool sets `result_chars` and `passages`.
    """
    event, start = ToolEvent(tool=name), time.perf_counter()
    try:
        yield event
    except Exception:
        event.ok = False
        raise
    finally:
        event.duration_ms = elapsed_ms(start)
        add(tool_ms=event.duration_ms)
        emit(event)
