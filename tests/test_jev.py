"""Tests for hci.jev: request shape, thresholds and the fallback when Jev fails."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from hci import jev
from hci.config import get_settings
from hci.constants import JEV_URL, Source
from hci.types import RecordChunk


def _make_chunks(n: int = 2) -> list[RecordChunk]:
    return [RecordChunk(f"c{i}", f"passage {i}", Source.DOCUMENT) for i in range(n)]


def _make_answers(*scores: float, answerable: float = 0.9) -> dict:
    return {f"p{i}": {"noul": s} for i, s in enumerate(scores)} | {"answerable": {"noul": answerable}}


def _make_response(body: object) -> MagicMock:
    response = MagicMock()
    response.json.return_value = body
    return response


@pytest.fixture
def jev_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """A TypeSafe key in the settings."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-key")
    get_settings.cache_clear()
    return "ts-key"


@pytest.mark.parametrize(("key", "expected"), [(None, False), ("", False), ("ts-key", True)])
def test_enabled_needs_non_empty_key(monkeypatch, key, expected):
    """The judge runs only with a non-empty TypeSafe key."""
    # Arrange
    if key is not None:
        monkeypatch.setenv("TYPESAFE_API_KEY", key)
    get_settings.cache_clear()
    # Act / Assert
    assert jev.enabled() is expected


def test_request_asks_one_question_per_passage_plus_answerable():
    """The body keys passages `p<i>` in state and asks relevance for each, plus answerability."""
    # Arrange
    chunks = _make_chunks(2)
    # Act
    body = jev.request("q", chunks)
    # Assert
    assert body["model"] == get_settings().jev_model
    assert body["state"] == {"query": "q", "passages": {"p0": "passage 0", "p1": "passage 1"}}
    assert set(body["questions"]) == {"p0", "p1", "answerable"}


class TestParse:
    @pytest.mark.parametrize(("score", "kept"), [(0.5, True), (0.49, False), (0.9, True)])
    def test_keep_threshold_is_inclusive(self, score, kept):
        """A passage is kept when its score reaches `jev_keep` (0.5)."""
        # Act
        keep, _ = jev.parse(_make_answers(score), _make_chunks(1))
        # Assert
        assert (keep == {"c0"}) is kept

    @pytest.mark.parametrize(("score", "answerable"), [(0.3, True), (0.29, False)])
    def test_answerable_threshold_is_inclusive(self, score, answerable):
        """The question is answerable when its score reaches `jev_answerable` (0.3)."""
        # Act
        _, ok = jev.parse(_make_answers(answerable=score), [])
        # Assert
        assert ok is answerable


class TestJudge:
    def test_posts_request_with_key(self, jev_key):
        """One authenticated POST to the Jev URL, with the configured timeout; its answers are parsed."""
        # Arrange
        chunks = _make_chunks(2)
        # Act
        with patch("hci.jev.httpx.post", return_value=_make_response({"answers": _make_answers(0.9, 0.1)})) as post:
            result = jev.judge("q", chunks)
        # Assert
        assert result == ({"c0"}, True)
        post.assert_called_once_with(
            JEV_URL,
            json=jev.request("q", chunks),
            headers={"Authorization": f"Bearer {jev_key}"},
            timeout=get_settings().jev_timeout,
        )

    @pytest.mark.parametrize(
        "post",
        [
            MagicMock(side_effect=httpx.ConnectError("down")),
            MagicMock(side_effect=httpx.ReadTimeout("slow")),
            MagicMock(
                return_value=MagicMock(
                    raise_for_status=MagicMock(
                        side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
                    )
                )
            ),
        ],
        ids=["connect", "timeout", "http-500"],
    )
    def test_http_error_keeps_every_passage(self, jev_key, post):
        """A Jev outage keeps every passage and lets the question through."""
        # Act
        with patch("hci.jev.httpx.post", post):
            result = jev.judge("q", _make_chunks(2))
        # Assert
        assert result == ({"c0", "c1"}, True)

    @pytest.mark.parametrize("body", [{}, {"answers": None}, {"answers": {"p0": {}}}, ["not", "a", "dict"]], ids=str)
    def test_malformed_response_keeps_every_passage(self, jev_key, body):
        """A response missing answers or scores is treated like an outage."""
        # Act
        with patch("hci.jev.httpx.post", return_value=_make_response(body)):
            result = jev.judge("q", _make_chunks(2))
        # Assert
        assert result == ({"c0", "c1"}, True)

    def test_invalid_json_keeps_every_passage(self, jev_key):
        """A body that is not JSON is treated like an outage."""
        # Arrange
        response = MagicMock()
        response.json.side_effect = ValueError("no json")
        # Act
        with patch("hci.jev.httpx.post", return_value=response):
            result = jev.judge("q", _make_chunks(1))
        # Assert
        assert result == ({"c0"}, True)
