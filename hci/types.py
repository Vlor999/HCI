"""Type aliases, protocols and domain dataclasses shared across the package."""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from hci.constants import Source

Embed = Callable[[list[str]], np.ndarray]  # texts -> L2-normalised (n, d)
Generate = Callable[[str, str], Iterator[str]]  # (system, user) -> text pieces


@dataclass(frozen=True)
class RecordChunk:
    """One retrievable passage of the robot's records."""

    id: str
    text: str
    source: Source
    scenario: int | None = None


@dataclass(frozen=True)
class Retrieval:
    """Result of a retrieval: the context passages and whether the question can be answered from them."""

    chunks: list[RecordChunk]
    answerable: bool = True


class Propose(Protocol):
    """Asks the operator to approve a fact; returns the tool result shown to the model."""

    def __call__(self, text: str, scenario: int | None) -> str: ...


class Answer(Protocol):
    """Streams an answer: text pieces and step lines (starting with `STEP_MARKER`)."""

    def __call__(
        self,
        question: str,
        scenario: int | None = None,
        history: Sequence[tuple[str, str]] = (),
        propose: Propose = ...,
    ) -> Iterator[str]: ...
