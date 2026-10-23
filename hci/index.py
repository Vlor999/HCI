"""Hybrid retrieval: dense embeddings + BM25, fused with reciprocal rank fusion."""

import math
import re
from collections import Counter
from collections.abc import Collection

import numpy as np

# Module level although it adds ~2.5 s to `import hci.index`: every entry point that imports this module
# (server, ask, chat, eval, the case tests) builds the embedder right after, so a lazy import saves nothing.
from sentence_transformers import SentenceTransformer

from hci.config import get_settings
from hci.constants import BM25_B, BM25_K1, QUERY_PREFIX, RRF_K
from hci.device import torch_device
from hci.types import Embed, RecordChunk


def default_embedder() -> Embed:
    """Sentence-transformers embedder named by the `embed_model` setting, on the torch device.

    Returns:
        A `texts -> L2-normalised (n, d) array` callable.
    """
    model = SentenceTransformer(get_settings().embed_model, device=torch_device())
    return lambda texts: model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens for BM25.

    Args:
        text: Text to split.

    Returns:
        The tokens, in order.
    """
    return re.findall(r"\w+", text.lower())


class HybridIndex:
    """Dense + BM25 index over record chunks, fused with reciprocal rank fusion."""

    # ponytail: brute-force numpy scan, fine up to ~100k chunks; swap for faiss/sqlite-vec past that
    def __init__(self, chunks: list[RecordChunk], embed: Embed) -> None:
        """Embed and tokenize every chunk.

        Args:
            chunks: The chunks to index.
            embed: Embedder used for the chunks and for queries.
        """
        self.chunks, self.embed = chunks, embed
        self.vecs = embed([c.text for c in chunks])
        self.docs = [Counter(tokenize(c.text)) for c in chunks]
        self.lens = np.array([sum(d.values()) for d in self.docs])
        self.df = Counter(t for d in self.docs for t in d)

    def bm25(self, query: str, k1: float = BM25_K1, b: float = BM25_B) -> np.ndarray:
        """BM25 score of every chunk.

        Args:
            query: The search query.
            k1: Term frequency saturation.
            b: Length normalisation.

        Returns:
            One score per chunk, in index order.
        """
        n, avg = len(self.docs), self.lens.mean()
        scores = np.zeros(n)
        for t in set(tokenize(query)):
            if t not in self.df:
                continue
            idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
            tf = np.array([d[t] for d in self.docs])
            scores += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * self.lens / avg))
        return scores

    def search(self, query: str, k: int, skip: Collection[str] = ()) -> list[RecordChunk]:
        """Top chunks by fused dense and BM25 rank.

        Args:
            query: The search query.
            k: Number of chunks to return.
            skip: Chunk ids to leave out.

        Returns:
            Up to `k` chunks, best first.
        """
        dense = self.vecs @ self.embed([QUERY_PREFIX + query])[0]
        fused = np.zeros(len(self.chunks))
        for scores in (dense, self.bm25(query)):
            fused[np.argsort(-scores)] += 1 / (RRF_K + np.arange(1, len(scores) + 1))
        ranked = (self.chunks[i] for i in np.argsort(-fused))
        return [c for c in ranked if c.id not in skip][:k]
