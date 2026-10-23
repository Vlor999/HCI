"""Tests for hci.agent: the per-run tools, step labels and Anthropic error handling."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import anthropic
import httpx2  # the HTTP client the Anthropic SDK builds its errors on
import pytest

from hci import agent
from hci.config import get_settings
from hci.constants import (
    AGENT_ERRORS,
    AGENT_NO_KEY,
    AGENT_NO_OPERATOR,
    AGENT_STEP_ERROR,
    AGENT_STEP_FOUND,
    AGENT_STEP_REASONING,
    AGENT_STEP_THINKING,
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
