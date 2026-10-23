"""The pipeline: retrieve -> (Jev judge) -> grounded prompt -> generate."""

from collections.abc import Iterator, Sequence

from hci import corpus, jev
from hci.config import get_settings
from hci.constants import NOT_FOUND, STEP_MARKER, SYSTEM, Source
from hci.index import Index, default_embedder
from hci.types import Embed, Generate, RecordChunk, Retrieval


def status(step: str) -> str:
    return f"{STEP_MARKER}{step}\n"


def text_only(pieces) -> str:
    return "".join(p for p in pieces if not p.startswith(STEP_MARKER))


class RAG:
    def __init__(self, embed: Embed | None = None, judge: bool | None = None):
        self.embed = embed or default_embedder()
        self.judge = jev.enabled() if judge is None else judge
        self.reload()

    def reload(self) -> None:
        self.stamp = corpus.stamp()
        self.chunks = corpus.load()
        self.index = Index(self.chunks, self.embed)

    def add_fact(self, text: str, scenario: int | None = None) -> None:
        corpus.add_fact(text, scenario)
        self.reload()

    def retrieve(
        self, question: str, scenario: int | None = None, history: Sequence[tuple[str, str]] = (), k: int | None = None
    ) -> Retrieval:
        """Pinned: the scenario's steps and facts, then facts that apply everywhere. Other scenarios are never searched.
        Not answerable (Jev) -> empty chunks, `answerable=False`."""
        if corpus.stamp() != self.stamp:
            self.reload()
        scoped = [c for c in self.chunks if c.source in (Source.PATH, Source.FACT)]
        pinned = [c for c in scoped if c.scenario == scenario] + [
            c for c in scoped if c.source == Source.FACT and c.scenario is None and scenario is not None
        ]
        other = {c.id for c in scoped if scenario is not None and c.scenario not in (None, scenario)}
        # follow-ups like "what does it compare it against?" only make sense with the previous question
        query = f"{history[-1][0]} {question}" if history else question
        hits = self.index.search(query, get_settings().k if k is None else k, skip=other | {c.id for c in pinned})
        if self.judge:
            keep, answerable = jev.judge(query, pinned + hits)
            if not answerable:
                return Retrieval([], answerable=False)
            hits = [c for c in hits if c.id in keep]
        return Retrieval(pinned + hits)

    def prompt(self, question: str, ctx: list[RecordChunk], history: Sequence[tuple[str, str]] = ()) -> str:
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
