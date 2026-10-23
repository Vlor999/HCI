"""Tests for hci.cli: chat commands, operator approval and the slash command completer."""

import json
from unittest.mock import MagicMock

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from hci.cli import ChatSession, SlashCommandCompleter
from hci.config import get_settings
from hci.constants import COMMANDS

NAMES = ["Default", "Heavy load", "Winter"]


def _make_session(answer, scenario: int | None = None) -> tuple[ChatSession, MagicMock]:
    rag = MagicMock()
    return ChatSession(rag, answer, scenario, names=list(NAMES)), rag


def _complete(text: str) -> list[str]:
    return [c.text for c in SlashCommandCompleter().get_completions(Document(text), CompleteEvent())]


class TestChatSession:
    def test_question_is_answered_and_recorded(self, fake_answer, capsys):
        """A plain line is answered; the turn is kept without step lines."""
        # Arrange
        session, rag = _make_session(fake_answer)
        # Act
        keep_going = session.handle("why A?")
        # Assert
        assert keep_going
        assert session.history == [("why A?", "answer to why A?")]
        assert "answer to why A?" in capsys.readouterr().out

    def test_question_writes_a_cli_request_event(self, fake_answer):
        """Each answered question appends a `request` event with source `cli`."""
        # Arrange
        session, rag = _make_session(fake_answer, scenario=1)
        # Act
        session.handle("why A?")
        # Assert
        (event,) = [json.loads(line) for line in get_settings().metrics_file.read_text().splitlines()]
        assert (event["kind"], event["source"], event["scenario"], event["output_pieces"]) == ("request", "cli", 1, 1)

    def test_session_keeps_one_conversation_id(self, fake_answer):
        """Every answer of a chat session carries the same conversation id; a new session gets a new one."""
        # Arrange
        session, _ = _make_session(fake_answer)
        # Act
        session.handle("why A?")
        session.handle("and B?")
        _make_session(fake_answer)[0].handle("why C?")
        # Assert
        ids = [json.loads(line)["conversation_id"] for line in get_settings().metrics_file.read_text().splitlines()]
        assert ids[0] == ids[1] != ids[2]

    def test_fact_saves_for_current_scenario(self, fake_answer):
        """`/fact <text>` saves the operator's text for the current scenario."""
        # Arrange
        session, rag = _make_session(fake_answer, scenario=2)
        # Act
        session.handle("/fact Path Q is icy")
        # Assert
        rag.add_fact.assert_called_once_with("Path Q is icy", 2)

    def test_fact_without_text_prints_usage(self, fake_answer, capsys):
        """`/fact` alone prints its usage and saves nothing."""
        # Arrange
        session, rag = _make_session(fake_answer)
        # Act
        session.handle("/fact")
        # Assert
        assert f"Usage: {COMMANDS['/fact']}" in capsys.readouterr().out
        rag.add_fact.assert_not_called()

    def test_scenario_switch_clears_history(self, fake_answer):
        """`/scenario <n>` switches scenario and starts a fresh conversation."""
        # Arrange
        session, rag = _make_session(fake_answer)
        session.history.append(("q", "a"))
        # Act
        session.handle("/scenario 2")
        # Assert
        assert (session.scenario, session.history) == (2, [])

    @pytest.mark.parametrize("arg", ["3", "x", "-1", "1.5"])
    def test_invalid_scenario_is_refused(self, fake_answer, capsys, arg):
        """An out-of-range or non-numeric scenario keeps the current one and says why."""
        # Arrange
        session, rag = _make_session(fake_answer, scenario=0)
        # Act
        session.handle(f"/scenario {arg}")
        # Assert
        assert session.scenario == 0
        assert "pick 0 to 2" in capsys.readouterr().out

    def test_clear_forgets_history(self, fake_answer):
        """`/clear` empties the conversation."""
        # Arrange
        session, rag = _make_session(fake_answer)
        session.history.append(("q", "a"))
        # Act
        session.handle("/clear")
        # Assert
        assert session.history == []

    def test_exit_ends_chat(self, fake_answer):
        """`/exit` is the only command that ends the chat."""
        # Act / Assert
        assert _make_session(fake_answer)[0].handle("/exit") is False

    def test_unknown_command_lists_commands(self, fake_answer, capsys):
        """An unknown command is reported, followed by the help, and is not sent as a question."""
        # Arrange
        answer = MagicMock()
        session, rag = _make_session(answer)
        # Act
        keep_going = session.handle("/nope")
        # Assert
        out = capsys.readouterr().out
        assert keep_going
        assert "Unknown command /nope." in out and all(command in out for command in COMMANDS)
        answer.assert_not_called()

    @pytest.mark.parametrize(("reply", "saved"), [("y", True), ("Y ", True), ("", False), ("n", False)])
    def test_propose_saves_only_on_yes(self, fake_answer, monkeypatch, reply, saved):
        """A fact the model proposes is saved only when the operator answers y."""
        # Arrange
        session, rag = _make_session(fake_answer)
        monkeypatch.setattr("builtins.input", lambda prompt: reply)
        # Act
        session.propose("Path C is closed.", 0)
        # Assert
        assert rag.add_fact.called is saved


class TestSlashCommandCompleter:
    @pytest.mark.parametrize(("text", "first"), [("/fc", "/fact"), ("/sc", "/scenario"), ("/", "/fact")])
    def test_fuzzy_matches_commands(self, text, first):
        """A partial `/word` fuzzy-matches the commands."""
        # Act / Assert
        assert _complete(text)[0] == first

    @pytest.mark.parametrize("text", ["/fact Path", "why /fact"])
    def test_silent_outside_a_bare_command(self, text):
        """No menu once the line has a space or does not start with `/`."""
        # Act / Assert
        assert _complete(text) == []
