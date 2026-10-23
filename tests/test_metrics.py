"""Tests for hci.metrics: latency math, the answer tracker, event records, rotation and privacy."""

import json
import threading
from collections.abc import Iterator

import pytest

from hci import metrics
from hci.config import get_settings
from hci.constants import MetricSource
from hci.rag import status
from hci.types import CostBreakdown, RequestEvent, RetrievalEvent, ToolEvent


class FakeClock:
    """Clock that moves only when told: each call returns the next scripted time."""

    def __init__(self, *times: float) -> None:
        self.times = list(times)

    def __call__(self) -> float:
        return self.times.pop(0)


def _make_stream(*pieces: str) -> Iterator[str]:
    yield from pieces


def _read(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize(
    ("values", "q", "expected"),
    [([], 50, None), ([4.0], 95, 4.0), ([1.0, 2.0, 3.0, 4.0], 50, 2.5), ([10.0] * 19 + [100.0], 95, 14.5)],
    ids=["empty", "single", "median-even", "p95-interpolated"],
)
def test_percentile_interpolates_linearly(values, q, expected):
    """Percentiles interpolate between ranks; no value gives None."""
    # Act / Assert
    assert metrics.percentile(values, q) == (None if expected is None else pytest.approx(expected))


class TestFillTiming:
    def test_ttft_and_gaps_come_from_text_pieces(self):
        """TTFT is the first text piece; gaps are between successive text pieces."""
        # Arrange
        request = RequestEvent(output_tokens=40)
        # Act
        metrics.fill_timing(request, start=0.0, text_times=[0.5, 0.6, 0.8, 1.3], end=1.5)
        # Assert
        assert (request.ttft_ms, request.total_ms, request.output_pieces) == (500.0, 1500.0, 4)
        assert (request.itl_mean_ms, request.itl_p50_ms, request.itl_max_ms) == (266.7, 200.0, 500.0)
        assert request.tokens_per_s == 50.0  # 40 tokens over 0.8 s of text

    def test_claude_rate_uses_model_time(self):
        """With Claude's model time known, tokens/s divides by it, not by a burst of text pieces."""
        # Arrange
        request = RequestEvent(output_tokens=40, model_ms=2000.0)
        # Act
        metrics.fill_timing(request, start=0.0, text_times=[5.0, 5.001], end=5.002)
        # Assert
        assert request.tokens_per_s == 20.0

    def test_no_text_leaves_text_metrics_empty(self):
        """A stream with only steps has a total time but no TTFT, gaps or rate."""
        # Arrange
        request = RequestEvent(output_tokens=3)
        # Act
        metrics.fill_timing(request, start=1.0, text_times=[], end=1.2)
        # Assert
        assert request.total_ms == 200.0
        assert request.ttft_ms is request.itl_p50_ms is request.tokens_per_s is None


class TestTrack:
    def test_ttft_skips_step_lines(self, tmp_path):
        """With a controlled clock, the first step line does not count as the first token."""
        # Arrange: start, then one clock read per text piece, then the end
        clock = FakeClock(0.0, 0.3, 0.35, 0.5)
        stream = _make_stream(status("Searching"), "Take ", "path C.")
        # Act
        pieces = list(metrics.track(stream, MetricSource.CLI, "why?", 0, clock=clock))
        # Assert
        assert pieces == [status("Searching"), "Take ", "path C."]
        record = _read(get_settings().metrics_file)[0]
        assert record["kind"] == "request" and record["source"] == "cli"
        assert (record["ttft_ms"], record["itl_max_ms"], record["total_ms"]) == (300.0, 50.0, 500.0)

    def test_inner_events_share_the_request_id(self):
        """Events written while the answer streams carry its request id, even from another thread's next()."""

        # Arrange
        def answer() -> Iterator[str]:
            metrics.emit(RetrievalEvent(latency_ms=1, k=6, chunks=3, pinned=1, judged=False, answerable=True))
            metrics.update(provider="mlx", model="m")
            yield "text"

        tracked = metrics.track(answer(), MetricSource.SERVER, "q", None)
        # Act: Starlette resumes a sync stream from worker threads, one next() per piece
        out: list[str] = []
        for _ in range(2):
            worker = threading.Thread(target=lambda: out.extend(next(tracked, [])))
            worker.start()
            worker.join()
        # Assert
        retrieval, request = _read(get_settings().metrics_file)
        assert retrieval["request_id"] == request["request_id"] is not None
        assert (request["provider"], request["model"], request["source"]) == ("mlx", "m", "server")

    def test_error_is_recorded_and_reraised(self):
        """An exception ending the stream is logged by class and still reaches the caller."""

        # Arrange
        def answer() -> Iterator[str]:
            yield "partial"
            raise RuntimeError("boom")

        # Act
        with pytest.raises(RuntimeError):
            list(metrics.track(answer(), MetricSource.CLI, "q", None))
        # Assert
        assert _read(get_settings().metrics_file)[0]["error"] == "RuntimeError"

    def test_question_text_is_not_logged_by_default(self):
        """Only the question length is written unless `metrics_log_questions` is on."""
        # Act
        list(metrics.track(_make_stream("a"), MetricSource.CLI, "Is path B flooded?", None))
        # Assert
        text = get_settings().metrics_file.read_text()
        assert "flooded" not in text
        assert json.loads(text)["question_chars"] == 18

    def test_question_text_is_logged_when_enabled(self, monkeypatch):
        """With `metrics_log_questions` on, the question text is in the request event."""
        # Arrange
        monkeypatch.setenv("HCI_METRICS_LOG_QUESTIONS", "true")
        get_settings.cache_clear()
        # Act
        list(metrics.track(_make_stream("a"), MetricSource.CLI, "Is path B flooded?", None))
        # Assert
        assert _read(get_settings().metrics_file)[0]["question"] == "Is path B flooded?"


def test_record_wraps_payload_in_envelope():
    """A record is kind, timestamp, request id and source, then the event fields."""
    # Act
    record = metrics.record(ToolEvent(tool="list_scenarios", duration_ms=1.5, result_chars=20), None)
    # Assert
    assert record.pop("ts") > 0
    assert record == {
        "kind": "tool",
        "request_id": None,
        "conversation_id": None,
        "source": None,
        "tool": "list_scenarios",
        "duration_ms": 1.5,
        "ok": True,
        "result_chars": 20,
        "passages": None,
    }


def test_disabled_writes_nothing(monkeypatch):
    """With `metrics_enabled` off, no file is created."""
    # Arrange
    monkeypatch.setenv("HCI_METRICS_ENABLED", "false")
    get_settings.cache_clear()
    # Act
    list(metrics.track(_make_stream("a"), MetricSource.CLI, "q", None))
    # Assert
    assert not get_settings().metrics_file.exists()


def test_settings_secrets_never_logged(monkeypatch):
    """API keys and the token appear in no event."""
    # Arrange
    for name, value in (
        ("ANTHROPIC_API_KEY", "sk-secret"),
        ("TYPESAFE_API_KEY", "ts-secret"),
        ("HCI_TOKEN", "hci-secret-token"),
    ):
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    # Act
    list(metrics.track(_make_stream("a"), MetricSource.SERVER, "q", None))
    # Assert
    text = get_settings().metrics_file.read_text()
    assert not any(secret in text for secret in ("sk-secret", "ts-secret", "hci-secret-token"))


class TestRotation:
    def test_full_file_moves_to_backup(self, monkeypatch):
        """Past `metrics_max_mb`, the file becomes `<name>.1` and a new one starts."""
        # Arrange
        monkeypatch.setenv("HCI_METRICS_MAX_MB", "0.0001")  # ~105 bytes: one record fills it
        get_settings.cache_clear()
        path = get_settings().metrics_file
        # Act
        for name in ("a", "b", "c"):
            metrics.emit(ToolEvent(tool=name))
        # Assert
        assert [r["tool"] for r in _read(path.with_name(path.name + ".1"))] == ["b"]
        assert [r["tool"] for r in _read(path)] == ["c"]

    def test_read_spans_backup_and_current(self, monkeypatch):
        """Reading returns the backup's events then the current file's, filtered by time and limit."""
        # Arrange
        monkeypatch.setenv("HCI_METRICS_MAX_MB", "0.0001")
        get_settings.cache_clear()
        for name in ("a", "b"):
            metrics.emit(ToolEvent(tool=name))
        # Act
        events = metrics.read()
        # Assert
        assert [e["tool"] for e in events] == ["a", "b"]
        assert [e["tool"] for e in metrics.read(limit=1)] == ["b"]
        assert metrics.read(since=events[-1]["ts"]) == []


def test_read_skips_malformed_lines():
    """A truncated line (crash mid-write) is skipped, not fatal."""
    # Arrange
    metrics.emit(ToolEvent(tool="a"))
    with get_settings().metrics_file.open("a") as f:
        f.write('{"kind": "to')
    # Act / Assert
    assert [e["tool"] for e in metrics.read()] == ["a"]


class TestCost:
    def test_local_answer_costs_nothing(self):
        """An answer with no priced call (local model) costs 0 USD, not unknown."""
        # Act
        list(metrics.track(_make_stream("a"), MetricSource.CLI, "q", None, "conv-1"))
        # Assert
        record = _read(get_settings().metrics_file)[0]
        assert (record["cost_usd"], record["price_unknown"], record["conversation_id"]) == (0.0, False, "conv-1")

    def test_unpriced_only_is_null(self):
        """When every priced call had no price, the answer's cost is null and flagged."""
        # Act
        with metrics.scope(MetricSource.CLI) as current:
            metrics.add_cost(None)
        metrics.fill_cost(current.request)
        # Assert
        assert (current.request.cost_usd, current.request.price_unknown) == (None, True)

    def test_partial_price_keeps_known_parts(self):
        """A priced Claude turn plus an unpriced Jev call gives the Claude cost, flagged as partial."""
        # Act
        with metrics.scope(MetricSource.CLI) as current:
            metrics.add_cost(CostBreakdown(input_usd=0.002, output_usd=0.01))
            metrics.add_cost(None)
        metrics.fill_cost(current.request)
        # Assert
        assert (current.request.cost_usd, current.request.price_unknown) == (0.012, True)


def test_unserializable_event_is_dropped_not_raised():
    """An event that cannot be written as JSON is logged and dropped; the answer goes on."""
    # Act
    metrics.emit(ToolEvent(tool=object()))  # ty: ignore[invalid-argument-type]
    # Assert
    assert not get_settings().metrics_file.exists()


def test_timestamp_is_taken_under_the_write_lock(monkeypatch):
    """`ts` is read while the write lock is held, so timestamps follow the file order."""
    # Arrange
    held = []
    record = metrics.record
    monkeypatch.setattr(
        metrics, "record", lambda event, scope: held.append(metrics._write_lock.locked()) or record(event, scope)
    )
    # Act
    metrics.emit(ToolEvent(tool="a"))
    # Assert
    assert held == [True]


class TestReadCache:
    def test_unchanged_file_is_not_parsed_again(self, monkeypatch):
        """A poll on an unchanged file reuses the parsed events; a new line makes it parse again."""
        # Arrange
        metrics.emit(ToolEvent(tool="a"))
        calls = []
        parse = metrics._parse
        monkeypatch.setattr(metrics, "_parse", lambda text: calls.append(1) or parse(text))
        # Act
        metrics.read()
        metrics.read()
        metrics.emit(ToolEvent(tool="b"))
        events = metrics.read()
        # Assert
        assert len(calls) == 2
        assert [e["tool"] for e in events] == ["a", "b"]

    def test_file_rotated_away_mid_read_gives_nothing(self, monkeypatch):
        """A file that disappears between its stat and its read (another process rotated it) is skipped."""
        # Arrange
        metrics.emit(ToolEvent(tool="a"))
        monkeypatch.setattr(
            metrics.Path, "read_text", lambda self, **kwargs: (_ for _ in ()).throw(FileNotFoundError())
        )
        # Act / Assert
        assert metrics.read() == []


def test_rotation_raced_by_another_process_still_writes(monkeypatch):
    """When another process rotated the file first (replace finds nothing), the event is still appended."""
    # Arrange
    monkeypatch.setenv("HCI_METRICS_MAX_MB", "0.0001")
    get_settings.cache_clear()
    metrics.emit(ToolEvent(tool="a"))
    monkeypatch.setattr(metrics.Path, "replace", lambda self, target: (_ for _ in ()).throw(FileNotFoundError()))
    # Act
    metrics.emit(ToolEvent(tool="b"))
    # Assert
    assert [e["tool"] for e in _read(get_settings().metrics_file)] == ["a", "b"]
