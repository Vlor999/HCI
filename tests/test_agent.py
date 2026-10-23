"""Tests for hci.agent: the per-run tools, step labels, Anthropic error handling and metric events."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import httpx2  # the HTTP client the Anthropic SDK builds its errors on
import pytest

from hci import agent, metrics
from hci.config import get_settings
from hci.constants import (
    AGENT_ERRORS,
    AGENT_NO_KEY,
    AGENT_NO_OPERATOR,
    AGENT_REFUSAL,
    AGENT_STEP_ERROR,
    AGENT_STEP_FOUND,
    AGENT_STEP_REASONING,
    AGENT_STEP_THINKING,
    MetricSource,
)
from hci.rag import status

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _make_status_error(cls: type[anthropic.APIStatusError], code: int) -> anthropic.APIStatusError:
    return cls("error", response=httpx2.Response(code, request=REQUEST), body=None)


def _call(run: agent.AgentRun, tool: str, args: dict) -> str:
    result = next(t for t in run.tools if t.name == tool).call(args)
    assert isinstance(result, str)
    return result


class TestAgentRun:
    def test_exposes_the_three_tools(self, rag):
        """Claude gets exactly the search, propose and list tools."""
        # Act
        names = {t.name for t in agent.AgentRun(rag).tools}
        # Assert
        assert names == {"query_context", "add_context", "list_scenarios"}

    def test_query_context_numbers_passages_per_search(self, rag):
        """Passages are cited as [search.passage], restarting at each search."""
        # Arrange
        run = agent.AgentRun(rag)
        # Act
        first = _call(run, "query_context", {"query": "fastest path", "scenario": 0})
        second = _call(run, "query_context", {"query": "battery", "scenario": 0})
        # Assert
        assert first.startswith("[1.1] (path)") and "travel time" in first
        assert second.startswith("[2.1] (path)")
        assert list(run.drain_steps()) == [status(AGENT_STEP_FOUND.format(9))] * 2

    def test_add_context_only_proposes(self, rag, facts_file):
        """`add_context` hands the fact to `propose` and writes nothing itself."""
        # Arrange
        propose = MagicMock(return_value="Proposed.")
        run = agent.AgentRun(rag, propose)
        # Act
        result = _call(run, "add_context", {"text": "Path C is closed.", "scenario": 0})
        # Assert
        assert result == "Proposed."
        propose.assert_called_once_with("Path C is closed.", 0)
        assert not facts_file.exists()

    def test_add_context_without_operator_saves_nothing(self, rag, facts_file):
        """With no operator to approve, the model is told nothing was saved."""
        # Act
        result = _call(agent.AgentRun(rag), "add_context", {"text": "Path C is closed."})
        # Assert
        assert result == AGENT_NO_OPERATOR
        assert not facts_file.exists()

    def test_list_scenarios_names_them_by_index(self, rag):
        """`list_scenarios` maps each index to its description."""
        # Act
        result = _call(agent.AgentRun(rag), "list_scenarios", {})
        # Assert
        assert '"2": "Winter scenario"' in result


@pytest.mark.parametrize(
    ("tool", "args", "label"),
    [
        ("query_context", {"query": "mud", "scenario": 1}, 'Searching: "mud" (scenario 1)'),
        ("query_context", {"query": "mud"}, 'Searching: "mud"'),
        (
            "add_context",
            {"text": "Path C is closed.", "scenario": 0},
            'Proposing fact: "Path C is closed." (scenario 0)',
        ),
        ("list_scenarios", {}, "Listing scenarios"),
        ("new_tool", {"query": "x"}, "Running tool new_tool"),
    ],
)
def test_describe_labels_tool_calls(tool, args, label):
    """Each tool call gets its own step label; an unknown tool is named, not mislabelled."""
    # Act / Assert
    assert agent.describe(tool, args) == label


def test_map_events_turns_stream_into_text_and_steps():
    """Thinking starts a Reasoning step, text deltas pass through, a finished tool call becomes a step."""
    # Arrange
    events = [
        SimpleNamespace(type="content_block_start", content_block=SimpleNamespace(type="thinking")),
        SimpleNamespace(type="text", text="Take A."),
        SimpleNamespace(
            type="content_block_stop",
            content_block=SimpleNamespace(type="tool_use", name="list_scenarios", input={}),
        ),
    ]
    # Act
    pieces = list(agent.map_events(iter(events)))  # ty: ignore[invalid-argument-type]
    # Assert
    assert pieces == [status(AGENT_STEP_REASONING), "Take A.", status("Listing scenarios")]


class TestClaudeMemoryAgent:
    def test_no_key_gives_message_without_calling_claude(self, rag):
        """Without ANTHROPIC_API_KEY the stream ends with an error step and AGENT_NO_KEY."""
        # Act
        with patch("hci.agent.anthropic.Anthropic") as client_cls:
            client_cls.return_value.api_key = None
            pieces = list(agent.ClaudeMemoryAgent(rag).answer("q"))
        # Assert
        assert pieces == [status(AGENT_STEP_ERROR), AGENT_NO_KEY]
        client_cls.return_value.beta.messages.tool_runner.assert_not_called()

    @pytest.mark.parametrize(
        ("error", "message"),
        [
            (_make_status_error(anthropic.AuthenticationError, 401), AGENT_ERRORS["AuthenticationError"]),
            (_make_status_error(anthropic.RateLimitError, 429), AGENT_ERRORS["RateLimitError"]),
            (_make_status_error(anthropic.InternalServerError, 500), AGENT_ERRORS["APIStatusError"]),
            (anthropic.APIConnectionError(request=REQUEST), AGENT_ERRORS["APIConnectionError"]),
            (anthropic.APITimeoutError(REQUEST), AGENT_ERRORS["APIConnectionError"]),
        ],
        ids=["auth", "rate-limit", "server", "connection", "timeout"],
    )
    def test_anthropic_error_ends_stream_with_message(self, rag, monkeypatch, error, message):
        """Each Anthropic error class ends the stream with the error step and its own user message."""
        # Arrange
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        get_settings.cache_clear()
        # Act
        with patch("hci.agent.anthropic.Anthropic") as client_cls:
            client_cls.return_value.beta.messages.tool_runner.side_effect = error
            pieces = list(agent.ClaudeMemoryAgent(rag).answer("q"))
        # Assert
        assert pieces == [status(AGENT_STEP_THINKING), status(AGENT_STEP_ERROR), "\n" + message]
        client_cls.assert_called_once_with(api_key="sk-test")


def test_build_messages_alternates_history_and_states_scenario():
    """History becomes user/assistant turns; the last user turn states the scenario."""
    # Act
    messages = agent.build_messages("why?", 2, [("q1", "a1")])
    # Assert
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert messages[-1]["content"] == "The current scenario is 2.\n\nwhy?"


def _make_turn(text: str, stop_reason: str, fallback: str | None = None) -> MagicMock:
    """One model turn: a stream of one text delta and a final message with usage, answered by the fallback if any."""
    iterations = [SimpleNamespace(type="fallback_message", model=fallback)] if fallback else None
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=20,
        cache_creation_input_tokens=50,
        cache_read_input_tokens=400,
        iterations=iterations,
    )
    stream = MagicMock()
    stream.__iter__.return_value = iter([SimpleNamespace(type="text", text=text)])
    stream.get_final_message.return_value = SimpleNamespace(
        stop_reason=stop_reason, model=fallback or "claude-sonnet-5-5", usage=usage
    )
    return stream


def _fake_runner(turns: list[MagicMock]):
    """`tool_runner` stand-in: yields each turn and, between turns, calls `query_context` like the SDK does."""

    def runner(**kwargs):
        tools = {t.name: t for t in kwargs["tools"]}
        for i, turn in enumerate(turns):
            if i:
                tools["query_context"].call({"query": "fastest path", "scenario": 0})
            yield turn

    return runner


class TestAgentMetrics:
    @pytest.fixture
    def answer_events(self, rag, monkeypatch):
        """Run one tracked agent answer (tool use, then a final turn) and return the written events."""

        def run(final_stop: str = "end_turn", fallback: str | None = None) -> tuple[list[str], list[dict]]:
            monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
            get_settings.cache_clear()
            turns = [_make_turn("", "tool_use"), _make_turn("Take C.", final_stop, fallback)]
            with patch("hci.agent.anthropic.Anthropic") as client_cls:
                client_cls.return_value.beta.messages.tool_runner.side_effect = _fake_runner(turns)
                stream = agent.ClaudeMemoryAgent(rag).answer("why?", 0)
                pieces = list(metrics.track(stream, MetricSource.SERVER, "why?", 0))
            lines = get_settings().metrics_file.read_text().splitlines()
            return pieces, [json.loads(line) for line in lines]

        return run

    def test_turns_and_tool_share_the_request_id(self, answer_events):
        """Each Claude turn and the tool call between them are logged under the answer's request id."""
        # Act
        _, events = answer_events()
        # Assert
        assert [e["kind"] for e in events] == ["model_turn", "retrieval", "tool", "model_turn", "request"]
        assert len({e["request_id"] for e in events}) == 1
        tool = events[2]
        assert (tool["tool"], tool["ok"], tool["passages"]) == ("query_context", True, 9)
        assert tool["result_chars"] > 0 and tool["duration_ms"] >= 0

    def test_request_sums_usage_over_turns(self, answer_events):
        """The request event sums Claude's usage over turns and keeps the last stop reason."""
        # Act
        _, events = answer_events()
        # Assert
        request = events[-1]
        assert (request["provider"], request["model"]) == ("anthropic", "claude-sonnet-5-5")
        assert (request["input_tokens"], request["output_tokens"]) == (200, 40)
        assert (request["cache_creation_input_tokens"], request["cache_read_input_tokens"]) == (100, 800)
        assert request["stop_reason"] == "end_turn" and request["refusal"] is False
        assert request["model_ms"] >= 0 and request["tool_ms"] >= 0

    def test_refusal_and_fallback_are_flagged(self, answer_events):
        """A refusal stop and a server-side fallback model are recorded on the request."""
        # Act
        pieces, events = answer_events(final_stop="refusal", fallback="claude-opus-4-8")
        # Assert
        assert pieces[-1] == AGENT_REFUSAL
        request, turn = events[-1], events[-2]
        assert (request["refusal"], request["fallback_model"]) == (True, "claude-opus-4-8")
        assert turn["fallback_model"] == "claude-opus-4-8"

    def test_cost_per_turn_and_request(self, answer_events):
        """Each turn is priced from its usage; the request sums the turns, component by component."""
        # Act
        _, events = answer_events()
        # Assert: 100 in, 20 out, 50 cache write, 400 cache read per turn, Sonnet 5.5 prices
        turn, request = events[0], events[-1]
        assert turn["cost"] == {
            "input_usd": 0.0002,
            "output_usd": 0.0002,
            "cache_write_usd": 0.000125,
            "cache_read_usd": 0.00008,
            "jev_usd": 0,
        }
        assert turn["cost_usd"] == pytest.approx(0.000605)
        assert request["cost_usd"] == pytest.approx(0.00121) and request["price_unknown"] is False

    def test_fallback_turn_is_priced_by_the_model_that_answered(self, answer_events):
        """A turn served by the fallback model is priced at that model's prices, not the requested one's."""
        # Act
        _, events = answer_events(fallback="claude-opus-4-8")
        # Assert: Opus 4.8 lists no cache read price, and the turn read from the cache
        turn = events[-2]
        assert (turn["model"], turn["cost_usd"], turn["price_unknown"]) == ("claude-opus-4-8", None, True)
        assert events[-1]["price_unknown"] is True

    def test_anthropic_error_class_is_recorded(self, rag, monkeypatch):
        """An Anthropic error, turned into a message for the user, is still logged by class."""
        # Arrange
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        get_settings.cache_clear()
        # Act
        with patch("hci.agent.anthropic.Anthropic") as client_cls:
            client_cls.return_value.beta.messages.tool_runner.side_effect = _make_status_error(
                anthropic.RateLimitError, 429
            )
            list(metrics.track(agent.ClaudeMemoryAgent(rag).answer("q"), MetricSource.CLI, "q", None))
        # Assert
        (request,) = [json.loads(line) for line in get_settings().metrics_file.read_text().splitlines()]
        assert request["error"] == "RateLimitError"
