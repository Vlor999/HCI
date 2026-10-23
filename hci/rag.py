"""The pipeline: retrieve -> (Jev judge) -> grounded prompt -> generate."""

import threading
from collections.abc import Iterable, Iterator, Sequence

from hci import corpus, jev
from hci.config import get_settings
from hci.constants import NOT_FOUND, STEP_MARKER, SYSTEM, Source
from hci.index import HybridIndex, default_embedder
from hci.types import Embed, Generate, RecordChunk, Retrieval


def status(step: str) -> str:
    """Encode a progress step as a stream line.

    Args:
        step: Human-readable step.

    Returns:
        The step prefixed with `STEP_MARKER`, newline-terminated.
    """
    return f"{STEP_MARKER}{step}\n"


def text_only(pieces: Iterable[str]) -> str:
    """Join the answer text of a stream, dropping step lines.

    Args:
        pieces: Stream pieces, as yielded by `ExplanationPipeline.answer`.

    Returns:
        The answer text.
    """
    return "".join(p for p in pieces if not p.startswith(STEP_MARKER))


class ExplanationPipeline:
    """Retrieval-augmented explanations of the robot's path choices, grounded in its records."""

    def __init__(self, embed: Embed | None = None, judge: bool | None = None) -> None:
        """Load the corpus and build the index.

        Args:
            embed: Embedder; None loads `default_embedder()`.
            judge: Use the Jev judge; None enables it when a TypeSafe key is set.
        """
        self.embed = embed or default_embedder()
        self.judge = jev.enabled() if judge is None else judge
        self.reload_lock = threading.Lock()  # one reload at a time; a refresh waits for a running reload
        self.reload()

    def reload(self) -> None:
        """Reload the corpus from data/ and rebuild the index."""
        with self.reload_lock:
            self._load()

    def refresh(self) -> None:
        """Reload the corpus if data/, the documents folder or the facts file changed since the last load."""
        with self.reload_lock:
            if corpus.stamp() != self.stamp:
                self._load()

    def _load(self) -> None:
        """Build chunks and index aside, then swap; the stamp moves only on success, so a failed load is retried."""
        stamp = corpus.stamp()  # taken first: a change made during the load triggers the next one
        chunks = corpus.load()
        index = HybridIndex(chunks, self.embed)
        self.chunks, self.index, self.stamp = chunks, index, stamp

    def add_fact(self, text: str, scenario: int | None = None) -> None:
        """Save an operator-approved fact and reindex.

        Args:
            text: The fact, one self-contained sentence.
            scenario: Scenario it applies to; None for everywhere.
        """
        corpus.add_fact(text, scenario)
        self.reload()

    def retrieve(
        self, question: str, scenario: int | None = None, history: Sequence[tuple[str, str]] = (), k: int | None = None
    ) -> Retrieval:
        """Context passages for a question, reloading the corpus first if data/ changed.

        Pinned first: the scenario's steps and facts, then facts that apply everywhere. Other scenarios are never
        searched. With the Jev judge on, irrelevant hits are dropped and an unanswerable question gets no chunks.

        Args:
            question: The user question.
            scenario: Current scenario index; None for no scenario.
            history: Previous (question, answer) turns, oldest first.
            k: Number of searched passages; None uses the `k` setting.

        Returns:
            The pinned passages then the search hits, and whether the question is answerable.
        """
        self.refresh()
        pinned = self._pinned(scenario)
        # follow-ups like "what does it compare it against?" only make sense with the previous question
        query = f"{history[-1][0]} {question}" if history else question
        skip = self._other_scenarios(scenario) | {c.id for c in pinned}
        hits = self.index.search(query, get_settings().k if k is None else k, skip=skip)
        return self._judged(query, pinned, hits) if self.judge else Retrieval(pinned + hits)

    def _scoped(self) -> list[RecordChunk]:
        return [c for c in self.chunks if c.source in (Source.PATH, Source.FACT)]

    def _pinned(self, scenario: int | None) -> list[RecordChunk]:
        scoped = self._scoped()
        own = [c for c in scoped if c.scenario == scenario]
        if scenario is None:
            return own
        return own + [c for c in scoped if c.source == Source.FACT and c.scenario is None]

    def _other_scenarios(self, scenario: int | None) -> set[str]:
        if scenario is None:
            return set()
        return {c.id for c in self._scoped() if c.scenario not in (None, scenario)}

    def _judged(self, query: str, pinned: list[RecordChunk], hits: list[RecordChunk]) -> Retrieval:
        keep, answerable = jev.judge(query, pinned + hits)
        if not answerable:
            return Retrieval([], answerable=False)
        return Retrieval(pinned + [c for c in hits if c.id in keep])

    def prompt(self, question: str, ctx: list[RecordChunk], history: Sequence[tuple[str, str]] = ()) -> str:
        """Build the grounded user prompt: numbered passages, operator updates first, recent turns, question.

        Args:
            question: The user question.
            ctx: Context passages, numbered from 1 in this order.
            history: Previous (question, answer) turns, oldest first.

        Returns:
            The user prompt.
        """
        n = dict(zip((c.id for c in ctx), range(1, len(ctx) + 1)))
        passages = "\n".join(f"[{n[c.id]}] ({c.source}) {c.text}" for c in ctx if c.source != Source.FACT)
        updates = "\n".join(f"[{n[c.id]}] {c.text}" for c in ctx if c.source == Source.FACT)
        if updates:  # small models skim past facts buried among records, so they get their own section
            passages = (
                f"OPERATOR UPDATES (newest information, they override the records below):\n{updates}\n\n{passages}"
            )
        past = "".join(f"Q: {q}\nA: {a}\n" for q, a in history[-get_settings().history_turns :])
        return (
            f"Context:\n{passages}\n\n"
            + (f"Earlier in this conversation:\n{past}\n" if past else "")
            + f"Question: {question}"
        )

    def answer(
        self, question: str, llm: Generate, scenario: int | None = None, history: Sequence[tuple[str, str]] = ()
    ) -> Iterator[str]:
        """Retrieve, then stream a grounded answer, or `NOT_FOUND` when Jev says the records don't answer.

        Args:
            question: The user question.
            llm: Generator called with the system and user prompts.
            scenario: Current scenario index; None for no scenario.
            history: Previous (question, answer) turns, oldest first.

        Yields:
            Step lines (see `status`) and answer text pieces.
        """
        yield status("Searching the records")
        retrieval = self.retrieve(question, scenario, history)
        if not retrieval.answerable:
            yield status("Jev: the records don't answer this")
            yield NOT_FOUND
            return
        ctx = retrieval.chunks
        yield status(f"{len(ctx)} passages in context" + (", filtered by Jev" if self.judge else ""))
        yield status("Writing the answer")
        yield from llm(SYSTEM, self.prompt(question, ctx, history))
