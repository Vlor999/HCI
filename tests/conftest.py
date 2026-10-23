"""Shared fixtures: isolated settings and facts file, a deterministic embedder, a fake answerer."""

import zlib
from collections.abc import Iterator, Sequence
from pathlib import Path

import numpy as np
import pytest

from hci.agent import reject
from hci.config import get_settings
from hci.index import tokenize
from hci.rag import ExplanationPipeline, status
from hci.types import Embed, Propose

EMBED_DIM = 256


def _embed(texts: list[str]) -> np.ndarray:
    """Hashed bag of words with a stable hash (`zlib.crc32`), so results do not change between runs."""
    vecs = np.zeros((len(texts), EMBED_DIM))
    for i, text in enumerate(texts):
        for word in tokenize(text):
            vecs[i, zlib.crc32(word.encode()) % EMBED_DIM] += 1
    return vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)


@pytest.fixture(autouse=True)
def facts_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Every test gets fresh settings, no API key from the shell, and its own facts file."""
    for name in ("ANTHROPIC_API_KEY", "TYPESAFE_API_KEY", "HCI_PROVIDER", "HCI_MODEL", "HCI_TOKEN", "HCI_K"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "facts.json"
    monkeypatch.setenv("HCI_FACTS_FILE", str(path))
    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


@pytest.fixture
def fake_embed() -> Embed:
    """Deterministic embedder: no model download."""
    return _embed


@pytest.fixture
def rag(fake_embed: Embed) -> ExplanationPipeline:
    """Pipeline over the repo's data with the fake embedder and no Jev judge."""
    return ExplanationPipeline(embed=fake_embed, judge=False)


def _fake_answer(
    question: str, scenario: int | None = None, history: Sequence[tuple[str, str]] = (), propose: Propose = reject
) -> Iterator[str]:
    yield status("Searching")
    yield f"answer to {question}"


@pytest.fixture
def fake_answer():
    """Answerer that yields one step line, then `answer to <question>`."""
    return _fake_answer
