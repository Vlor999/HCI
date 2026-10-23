"""Tests for hci.corpus: chunking the records and storing operator facts."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from hci import corpus
from hci.constants import Source


def _make_step(**fields: object) -> dict:
    return {"location": "A", "timestamp": "2024-01-01", "context": "muddy", **fields}


class TestStepText:
    @pytest.mark.parametrize(
        ("fields", "expected"),
        [
            ({"length": 120, "average_speed": 1.2}, "travel time 6.0 min"),
            ({"length": 300, "average_speed": 2.5}, "travel time 7.2 min"),
        ],
    )
    def test_precomputes_travel_time(self, fields, expected):
        """Travel time is d / v in minutes, computed at indexing time."""
        # Act
        text = corpus.step_text("Default", _make_step(**fields))
        # Assert
        assert expected in text

    def test_no_travel_time_without_speed(self):
        """A step without a speed gets no travel time instead of a division error."""
        # Act
        text = corpus.step_text("Default", _make_step(length=120))
        # Assert
        assert "travel time" not in text


class TestLoad:
    def test_chunk_ids_follow_their_source(self):
        """Ids encode source, scenario and location, and are unique."""
        # Act
        chunks = corpus.load()
        # Assert
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))
        assert {"path-0-A", "path-2-R", "manual-1", "correction-correction_1", "example-0"} <= set(ids)

    def test_facts_come_last_with_their_scenario(self):
        """Approved facts are appended as `fact-<n>` chunks carrying their scenario."""
        # Arrange
        corpus.add_fact("Path B is flooded", 0)
        # Act
        last = corpus.load()[-1]
        # Assert
        assert (last.id, last.source, last.scenario) == ("fact-0", Source.FACT, 0)
        assert last.text == "Operator update: Path B is flooded"


class TestFacts:
    def test_add_fact_appends_in_order(self):
        """Facts accumulate in the order they were approved."""
        # Act
        corpus.add_fact("first", None)
        corpus.add_fact("second", 1)
        # Assert
        assert corpus.load_facts() == [{"text": "first", "scenario": None}, {"text": "second", "scenario": 1}]

    def test_corrupt_file_is_moved_aside(self, facts_file: Path):
        """A corrupt facts file reads as empty and is renamed, keeping the operator's data."""
        # Arrange
        facts_file.write_text("{not json")
        # Act
        facts = corpus.load_facts()
        # Assert
        backups = list(facts_file.parent.glob("facts.json.corrupt-*"))
        assert facts == []
        assert not facts_file.exists()
        assert [b.read_text() for b in backups] == ["{not json"]

    def test_add_fact_after_corruption_keeps_backup(self, facts_file: Path):
        """The next approved fact starts a new file and leaves the corrupt one untouched."""
        # Arrange
        facts_file.write_text("{not json")
        # Act
        corpus.add_fact("Path C is closed", 0)
        # Assert
        assert json.loads(facts_file.read_text()) == [{"text": "Path C is closed", "scenario": 0}]
        assert [b.read_text() for b in facts_file.parent.glob("facts.json.corrupt-*")] == ["{not json"]

    def test_failed_write_keeps_old_file(self, facts_file: Path):
        """A crash before the rename leaves the previous facts file intact."""
        # Arrange
        corpus.add_fact("kept", None)
        before = facts_file.read_text()
        # Act
        with patch("hci.corpus.os.replace", side_effect=OSError("disk full")), pytest.raises(OSError):
            corpus.add_fact("lost", None)
        # Assert
        assert facts_file.read_text() == before


def test_stamp_of_empty_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """An empty data dir stamps 0.0 instead of raising."""
    # Arrange
    monkeypatch.setattr(corpus, "DATA_DIR", tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    # Act / Assert
    assert corpus.stamp() == 0.0
