"""The pipeline: retrieve -> (Jev judge) -> grounded prompt -> generate."""

from collections.abc import Iterator, Sequence

from hci import corpus, jev
from hci.index import Embed, Index, default_embedder
from hci.llm import Generate

SYSTEM = """You are the explanation module of a mobile robot that navigates a forest with LIDAR, camera and IMU.
Explain its path choices to a human using only the numbered context passages.
- Prefer recent sensor data and operator updates over older records.
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
        self.chunks = corpus.load()
        self.index = Index(self.chunks, self.embed)

    def add_fact(self, text: str, scenario: int | None = None) -> None:
        corpus.add_fact(text, scenario)
        self.reload()

    def retrieve(self, question: str, scenario: int | None = None, k: int = 6) -> list[corpus.Chunk] | None:
        """Current scenario steps and facts are always in context; the rest is searched. None = not answerable."""
        pinned = [c for c in self.chunks if c.source in ("path", "fact") and c.scenario == scenario]
        hits = self.index.search(question, k, skip={c.id for c in pinned})
        if self.judge:
            keep, answerable = jev.judge(question, pinned + hits)
            if not answerable:
                return None
            hits = [c for c in hits if c.id in keep]
        return pinned + hits

    def prompt(self, question: str, ctx: list[corpus.Chunk], history: Sequence[tuple[str, str]] = ()) -> str:
        passages = "\n".join(f"[{i}] ({c.source}) {c.text}" for i, c in enumerate(ctx, 1))
        past = "".join(f"Q: {q}\nA: {a}\n" for q, a in history[-3:])
        return (
            f"Context:\n{passages}\n\n"
            + (f"Earlier in this conversation:\n{past}\n" if past else "")
            + f"Question: {question}"
        )

    def answer(
        self, question: str, llm: Generate, scenario: int | None = None, history: Sequence[tuple[str, str]] = ()
    ) -> Iterator[str]:
        ctx = self.retrieve(question, scenario)
        if ctx is None:
            yield NOT_FOUND
            return
        yield from llm(SYSTEM, self.prompt(question, ctx, history))
