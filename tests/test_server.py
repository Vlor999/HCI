"""Tests for hci.server: auth, providers, request validation, the stream protocol and locking."""

import json
import threading
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from hci import server
from hci.agent import reject
from hci.config import get_settings
from hci.constants import AGENT_PROPOSED_ON_PHONE, PROPOSALS_MARKER, STEP_MARKER
from hci.rag import status
from hci.types import Propose

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def fake_rag() -> MagicMock:
    """Stand-in pipeline recording `add_fact` calls."""
    return MagicMock()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_rag: MagicMock, fake_answer) -> TestClient:
    """Client with a known token, a fake pipeline and the fake answerer for every provider."""
    monkeypatch.setenv("HCI_TOKEN", TOKEN)
    get_settings.cache_clear()
    monkeypatch.setattr(server, "get_rag", lambda: fake_rag)
    monkeypatch.setattr(server, "answerer", lambda rag, provider: fake_answer)
    monkeypatch.setattr(server, "answerers", {})
    return TestClient(server.app)


def _with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    get_settings.cache_clear()


class TestAuth:
    @pytest.mark.parametrize(
        "headers",
        [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Bearer tök".encode("latin-1")}],
        ids=["missing", "wrong", "non-ascii"],
    )
    def test_bad_token_is_401(self, client, headers):
        """A missing, wrong or non-ASCII token gives 401, never 500."""
        # Act
        response = client.get("/api/info", headers=headers)
        # Assert
        assert response.status_code == 401


class TestProviders:
    def test_without_key_only_local(self, client):
        """Without ANTHROPIC_API_KEY only the local backend is offered."""
        # Act
        providers = client.get("/api/info", headers=AUTH).json()["providers"]
        # Assert
        assert providers == [server.backend()]

    def test_with_key_adds_anthropic(self, client, monkeypatch):
        """With ANTHROPIC_API_KEY, `anthropic` is offered after the local default."""
        # Arrange
        _with_key(monkeypatch)
        # Act
        providers = client.get("/api/info", headers=AUTH).json()["providers"]
        # Assert
        assert providers == [server.backend(), "anthropic"]

    def test_anthropic_without_key_is_400(self, client):
        """Asking for Claude on a server without a key is rejected before streaming."""
        # Act
        response = client.post("/api/ask", headers=AUTH, json={"question": "q", "provider": "anthropic"})
        # Assert
        assert response.status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {"question": "q", "provider": "bogus"},
        {"question": ""},
        {"question": "q", "scenario": -1},
        {"question": "q", "history": [["q", "a"]] * 11},
    ],
    ids=["provider", "empty-question", "negative-scenario", "long-history"],
)
def test_invalid_ask_is_422(client, body):
    """Request bodies outside the schema are rejected with 422."""
    # Act / Assert
    assert client.post("/api/ask", headers=AUTH, json=body).status_code == 422


def _proposing_answer(question: str, scenario=None, history=(), propose: Propose = reject) -> Iterator[str]:
    yield status("Searching")
    yield "Path C " + propose("Path C is closed.", 0)


def test_stream_carries_steps_text_and_proposals(client, monkeypatch):
    """The body has step lines, the answer, then the proposals marker with the facts as JSON."""
    # Arrange
    monkeypatch.setattr(server, "answerer", lambda rag, provider: _proposing_answer)
    # Act
    body = client.post("/api/ask", headers=AUTH, json={"question": "q"}).text
    # Assert
    text, proposals = body.split(PROPOSALS_MARKER)
    assert text == f"{STEP_MARKER}Searching\nPath C {AGENT_PROPOSED_ON_PHONE}"
    assert json.loads(proposals) == [{"text": "Path C is closed.", "scenario": 0}]


def test_stream_without_proposals_has_no_marker(client):
    """A plain answer ends without the proposals marker."""
    # Act
    body = client.post("/api/ask", headers=AUTH, json={"question": "q"}).text
    # Assert
    assert body == f"{STEP_MARKER}Searching\nanswer to q"


def test_add_fact_saves_through_pipeline(client, fake_rag):
    """`/api/facts` saves the approved fact through the pipeline."""
    # Act
    response = client.post("/api/facts", headers=AUTH, json={"text": "Path C is closed.", "scenario": 0})
    # Assert
    assert response.json() == {"ok": True}
    fake_rag.add_fact.assert_called_once_with("Path C is closed.", 0)


def test_fact_approval_does_not_wait_for_local_stream(client, monkeypatch, fake_rag):
    """A fact approval goes through while a local answer still holds the generation lock."""
    # Arrange
    started, release = threading.Event(), threading.Event()

    def slow_answer(question, scenario=None, history=(), propose=None):
        started.set()
        release.wait(5)
        yield "done"

    monkeypatch.setattr(server, "answerer", lambda rag, provider: slow_answer)
    stream = threading.Thread(
        target=client.post, args=("/api/ask",), kwargs={"headers": AUTH, "json": {"question": "q"}}
    )
    stream.start()
    started.wait(5)
    # Act
    response = client.post("/api/facts", headers=AUTH, json={"text": "f"})
    # Assert
    assert response.status_code == 200
    assert server.local_lock.locked() and stream.is_alive()
    fake_rag.add_fact.assert_called_once_with("f", None)
    release.set()
    stream.join(5)
