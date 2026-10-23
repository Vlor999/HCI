"""Tests for hci.rag: pinning, scenario isolation, history, the Jev gate and the prompt."""

from unittest.mock import MagicMock, patch

import pytest

from hci.config import get_settings
from hci.constants import NOT_FOUND, STEP_MARKER, Source
from hci.rag import ExplanationPipeline, status, text_only
from hci.types import RecordChunk


def _make_chunk(id: str, source: Source = Source.PATH, text: str = "text") -> RecordChunk:
    return RecordChunk(id, text, source)


def _ids(rag: ExplanationPipeline, question: str, scenario: int | None, **kwargs) -> list[str]:
    return [c.id for c in rag.retrieve(question, scenario, **kwargs).chunks]


class TestRetrieve:
    def test_current_scenario_pinned_first(self, rag):
        """The current scenario's steps open the context, whatever the question."""
        # Act
        ids = _ids(rag, "battery recharge", 0)
        # Assert
        assert ids[:3] == ["data/paths.json#0/A", "data/paths.json#0/B", "data/paths.json#0/C"]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("question", ["path Y heavy load", "winter snow on path P", "which path is fastest?"])
    def test_other_scenarios_never_in_context(self, rag, question):
        """Steps of other scenarios are never searched, even when the question names them."""
        # Act
        ids = _ids(rag, question, 0)
        # Assert
        assert not [i for i in ids if i.startswith(("data/paths.json#1/", "data/paths.json#2/"))]

    def test_scenario_and_global_facts_pinned(self, rag):
        """The scenario's facts and facts without scenario are pinned; other scenarios' facts are not."""
        # Arrange
        rag.add_fact("Path A is flooded", 0)
        rag.add_fact("Path Y is closed", 1)
        rag.add_fact("The forest is closed today", None)
        # Act
        ids = _ids(rag, "battery recharge", 0, k=0)
        # Assert
        assert ids == ["data/paths.json#0/A", "data/paths.json#0/B", "data/paths.json#0/C", "fact-0", "fact-2"]

    def test_follow_up_searched_with_previous_question(self, rag):
        """A follow-up is searched together with the previous question."""
        # Arrange
        history = [("energy recharge power source?", "The station.")]
        # Act
        without, with_history = _ids(rag, "and then?", None, k=3), _ids(rag, "and then?", None, history=history, k=3)
        # Assert
        assert "data/documents/sample_manual.md#1" not in without
        assert "data/documents/sample_manual.md#1" in with_history


class TestJevGate:
    def test_unanswerable_question_gets_not_found(self, rag):
        """When Jev says the records don't answer, the LLM is skipped and NOT_FOUND is the answer."""
        # Arrange
        rag.judge = True
        llm = MagicMock()
        # Act
        with patch("hci.rag.jev.judge", return_value=(set(), False)):
            answer = text_only(rag.answer("weather on mars?", llm))
        # Assert
        assert answer == NOT_FOUND
        llm.assert_not_called()

    def test_irrelevant_hits_dropped_pinned_kept(self, rag):
        """Jev filters search hits only; pinned scenario steps always stay."""
        # Arrange
        rag.judge = True
        # Act
        with patch("hci.rag.jev.judge", return_value=({"data/documents/sample_manual.md#1"}, True)) as judge:
            ids = _ids(rag, "energy recharge power source", 0)
        # Assert
        assert ids == [
            "data/paths.json#0/A",
            "data/paths.json#0/B",
            "data/paths.json#0/C",
            "data/documents/sample_manual.md#1",
        ]
        judge.assert_called_once()


class TestPrompt:
    def test_facts_get_their_own_section_first(self, rag):
        """Operator updates sit in a section above the records, numbered like the context."""
        # Arrange
        ctx = [
            _make_chunk("data/paths.json#0/A", text="Path A"),
            _make_chunk("fact-0", Source.FACT, "Path A is flooded"),
        ]
        # Act
        prompt = rag.prompt("why?", ctx)
        # Assert
        updates, records = prompt.split("[2] Path A is flooded")
        assert "OPERATOR UPDATES" in updates
        assert "[1] (path) Path A" in records

    def test_no_updates_section_without_facts(self, rag):
        """Without facts, the prompt has no operator updates header."""
        # Act
        prompt = rag.prompt("why?", [_make_chunk("data/paths.json#0/A")])
        # Assert
        assert "OPERATOR UPDATES" not in prompt
        assert prompt.endswith("Question: why?")

    def test_history_limited_to_recent_turns(self, rag, monkeypatch):
        """Only the last `history_turns` turns are included, oldest dropped."""
        # Arrange
        monkeypatch.setenv("HCI_HISTORY_TURNS", "2")
        get_settings.cache_clear()
        history = [("q1", "a1"), ("q2", "a2"), ("q3", "a3")]
        # Act
        prompt = rag.prompt("why?", [_make_chunk("data/paths.json#0/A")], history)
        # Assert
        assert "Q: q1" not in prompt
        assert "Earlier in this conversation:\nQ: q2\nA: a2\nQ: q3\nA: a3\n" in prompt


def test_answer_streams_steps_then_llm_text(rag):
    """The stream starts with step lines, then the generator's text built from the grounded prompt."""
    # Arrange
    llm = MagicMock(return_value=iter(["Take A."]))
    # Act
    pieces = list(rag.answer("why A?", llm, scenario=0))
    # Assert
    assert pieces[0] == status("Searching the records")
    assert text_only(pieces) == "Take A."
    assert all(p.startswith(STEP_MARKER) for p in pieces[:-1])
    assert llm.call_args.args[1].endswith("Question: why A?")
