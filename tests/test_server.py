"""Tests for hci.server: auth, providers, request validation, the stream protocol and locking."""

import json
import threading
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from hci import server
from hci.agent import reject
from hci.config import get_settings
from hci.constants import AGENT_PROPOSED_ON_PHONE, PROPOSALS_MARKER, STEP_MARKER
from hci.rag import ExplanationPipeline, status
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


@pytest.mark.parametrize("path", ["/vendor/marked.min.js", "/vendor/purify.min.js", "/vendor/chart.umd.min.js"])
def test_markdown_libraries_are_served_locally(client: TestClient, path: str):
    """The page renders Markdown offline: marked and DOMPurify come from the server, not a CDN."""
    # Act
    response = client.get(path)

    # Assert
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_answer_writes_a_server_request_event(client):
    """Each `/api/ask` answer appends a `request` event with source `server` and no question text."""
    # Act
    client.post("/api/ask", headers=AUTH, json={"question": "why path A?", "scenario": 1})
    # Assert
    (event,) = [json.loads(line) for line in get_settings().metrics_file.read_text().splitlines()]
    assert (event["kind"], event["source"], event["scenario"], event["question_chars"]) == ("request", "server", 1, 11)
    assert "why path A" not in json.dumps(event)


class TestMetrics:
    def test_metrics_needs_token(self, client):
        """`/api/metrics` on `hci serve` is behind the same token as the API."""
        # Act / Assert
        assert client.get("/api/metrics").status_code == 401

    def test_metrics_filters_by_since_and_limit(self, client):
        """`since` keeps later events, `limit` the last N."""
        # Arrange
        for question in ("a", "b", "c"):
            client.post("/api/ask", headers=AUTH, json={"question": question})
        events = client.get("/api/metrics", headers=AUTH).json()
        # Act
        later = client.get("/api/metrics", headers=AUTH, params={"since": events[0]["ts"]}).json()
        last = client.get("/api/metrics", headers=AUTH, params={"limit": 1}).json()
        # Assert
        assert len(events) == 3
        assert later == [e for e in events if e["ts"] > events[0]["ts"]]
        assert last == events[-1:]

    def test_dashboard_page_is_served(self, client):
        """`/dashboard` serves the page; its data needs the token, the page itself does not."""
        # Act
        response = client.get("/dashboard")
        # Assert
        assert response.status_code == 200
        assert "/vendor/chart.umd.min.js" in response.text


class TestDocuments:
    @pytest.fixture
    def docs_client(self, client: TestClient, tmp_path, monkeypatch: pytest.MonkeyPatch, fake_embed) -> TestClient:
        """Client over a real pipeline (fake embedder) whose documents folder is empty and temporary."""
        monkeypatch.setenv("HCI_DOCUMENTS_DIR", str(tmp_path / "documents"))
        monkeypatch.setenv("HCI_MAX_UPLOAD_MB", "0.001")
        get_settings.cache_clear()
        rag = ExplanationPipeline(embed=fake_embed, judge=False)
        monkeypatch.setattr(server, "get_rag", lambda: rag)
        return client

    def _upload(self, client: TestClient, name: str, data: bytes = b"Path Q floods every spring.", headers=AUTH):
        return client.post("/api/documents", headers=headers, files={"file": (name, data)})

    def test_upload_needs_token(self, docs_client: TestClient):
        """An upload without the token is refused with 401."""
        # Act / Assert
        assert self._upload(docs_client, "notes.md", headers={}).status_code == 401

    def test_unsupported_type_is_415(self, docs_client: TestClient, tmp_path):
        """A file type the index cannot read is refused with 415 and not saved."""
        # Act
        response = self._upload(docs_client, "photo.png")
        # Assert
        assert response.status_code == 415
        assert not (tmp_path / "documents").exists()

    def test_too_large_is_413(self, docs_client: TestClient):
        """A file above `max_upload_mb` is refused with 413."""
        # Act / Assert
        assert self._upload(docs_client, "big.txt", b"word " * 400).status_code == 413

    def test_traversal_name_stays_in_uploads(self, docs_client: TestClient, tmp_path):
        """A name with `..` and folders is reduced to its base name inside the uploads folder."""
        # Act
        response = self._upload(docs_client, "../../.evil.md")
        # Assert
        assert response.json() == {"name": "uploads/evil.md", "chunks": 1}
        assert [p.name for p in tmp_path.rglob("*.md")] == ["evil.md"]

    def test_same_name_gets_a_unique_name(self, docs_client: TestClient):
        """A second upload with the same name is saved next to the first, never over it."""
        # Arrange
        self._upload(docs_client, "notes.md")
        # Act
        response = self._upload(docs_client, "notes.md")
        # Assert
        assert response.json()["name"] == "uploads/notes-1.md"

    def test_unreadable_file_is_422_and_removed(self, docs_client: TestClient, tmp_path):
        """A file with no readable text is refused with 422 and deleted."""
        # Act
        response = self._upload(docs_client, "scan.pdf", b"not a pdf")
        # Assert
        assert response.status_code == 422
        assert response.json()["detail"].startswith("Could not index scan.pdf: ")
        assert not list((tmp_path / "documents").rglob("*.pdf"))

    def test_uploaded_document_is_retrievable(self, docs_client: TestClient):
        """Once uploaded, the document's chunk is in the context of a question it answers."""
        # Arrange
        self._upload(docs_client, "flood.md")
        # Act
        ids = [c.id for c in server.get_rag().retrieve("When does path Q flood?").chunks]
        # Assert
        assert any(i.endswith("uploads/flood.md#1") for i in ids)

    @pytest.mark.parametrize(("headers", "status"), [({}, 401), (AUTH, 413)], ids=["no-token", "token"])
    def test_oversized_body_is_refused_before_parsing(self, docs_client: TestClient, headers: dict, status: int):
        """A body declared above the limit is refused from its headers: 401 without token, 413 with; never parsed."""
        # Act
        with patch("starlette.requests.MultiPartParser") as parser:
            response = self._upload(docs_client, "big.md", b"x" * 200_000, headers=headers)
        # Assert
        assert response.status_code == status
        parser.assert_not_called()

    def test_upload_without_length_is_411(self, docs_client: TestClient):
        """A streamed upload without Content-Length is refused, so its size is always known up front."""
        # Act
        response = docs_client.post("/api/documents", headers=AUTH, content=iter([b"--x\r\n"]))
        # Assert
        assert response.status_code == 411

    def test_long_name_is_shortened(self, docs_client: TestClient):
        """A file name too long for the file system is cut, keeping its extension."""
        # Act
        response = self._upload(docs_client, "a" * 300 + ".md")
        # Assert
        assert response.status_code == 200
        assert response.json()["name"] == "uploads/" + "a" * 120 + ".md"

    def test_write_failure_is_500_without_partial_file(self, docs_client: TestClient, tmp_path):
        """A disk error while saving gives a clear 500 and leaves nothing in the uploads folder."""
        # Arrange
        uploads = tmp_path / "documents" / "uploads"
        uploads.mkdir(parents=True)
        uploads.chmod(0o500)
        # Act
        response = self._upload(docs_client, "notes.md")
        # Assert
        uploads.chmod(0o700)
        assert response.status_code == 500
        assert response.json()["detail"] == "Could not save the file on the server."
        assert not list(uploads.iterdir())

    def test_list_shows_indexed_documents(self, docs_client: TestClient):
        """`GET /api/documents` lists each document with its chunk count."""
        # Arrange
        self._upload(docs_client, "flood.md")
        # Act
        listed = docs_client.get("/api/documents", headers=AUTH).json()
        # Assert
        assert listed == [{"name": "uploads/flood.md", "chunks": 1}]
