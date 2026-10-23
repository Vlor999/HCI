"""The pipeline: retrieve -> (Jev judge) -> grounded prompt -> generate."""

from collections.abc import Iterator, Sequence

from hci import corpus, jev
from hci.index import Embed, Index, default_embedder
from hci.llm import Generate

SYSTEM = """You are the explanation module of a mobile robot that navigates a forest with LIDAR, camera and IMU.
Explain its path choices to a human using only the numbered context passages.
- Operator updates are the newest information: when they contradict a record, follow the update.
- Reason about safety, terrain, energy and ecological impact; give the decision first, then the justification.
- Travel times are precomputed in the passages; use them instead of recomputing.
- Cite the passages you rely on like [2]. If the context does not answer the question, say so."""

NOT_FOUND = "I can't answer that from the robot's records."


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
        self, question: str, scenario: int | None = None, history: Sequence[tuple[str, str]] = (), k: int = 6
    ) -> list[corpus.Chunk] | None:
        """Pinned: the scenario's steps and facts, then facts that apply everywhere. Other scenarios are never searched.
        None = not answerable."""
        if corpus.stamp() != self.stamp:
            self.reload()
        scoped = [c for c in self.chunks if c.source in ("path", "fact")]
        pinned = [c for c in scoped if c.scenario == scenario] + [
            c for c in scoped if c.source == "fact" and c.scenario is None and scenario is not None
        ]
        other = {c.id for c in scoped if scenario is not None and c.scenario not in (None, scenario)}
        # follow-ups like "what does it compare it against?" only make sense with the previous question
        query = f"{history[-1][0]} {question}" if history else question
        hits = self.index.search(query, k, skip=other | {c.id for c in pinned})
        if self.judge:
            keep, answerable = jev.judge(query, pinned + hits)
            if not answerable:
                return None
            hits = [c for c in hits if c.id in keep]
        return pinned + hits

    def prompt(self, question: str, ctx: list[corpus.Chunk], history: Sequence[tuple[str, str]] = ()) -> str:
        n = dict(zip((c.id for c in ctx), range(1, len(ctx) + 1)))
        passages = "\n".join(f"[{n[c.id]}] ({c.source}) {c.text}" for c in ctx if c.source != "fact")
        updates = "\n".join(f"[{n[c.id]}] {c.text}" for c in ctx if c.source == "fact")
        if updates:  # small models skim past facts buried among records, so they get their own section
            passages = (
                f"OPERATOR UPDATES (newest information, they override the records below):\n{updates}\n\n{passages}"
            )
        past = "".join(f"Q: {q}\nA: {a}\n" for q, a in history[-3:])
        return (
            f"Context:\n{passages}\n\n"
            + (f"Earlier in this conversation:\n{past}\n" if past else "")
            + f"Question: {question}"
        )

    def answer(
        self, question: str, llm: Generate, scenario: int | None = None, history: Sequence[tuple[str, str]] = ()
    ) -> Iterator[str]:
        ctx = self.retrieve(question, scenario, history)
        if ctx is None:
            yield NOT_FOUND
            return
        yield from llm(SYSTEM, self.prompt(question, ctx, history))
