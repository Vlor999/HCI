"""Hybrid retrieval: dense embeddings + BM25, fused with reciprocal rank fusion."""

import math
import os
import re
from collections import Counter
from collections.abc import Callable, Collection

import numpy as np

from hci.corpus import Chunk

EMBED_MODEL = os.environ.get("HCI_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge query instruction

Embed = Callable[[list[str]], np.ndarray]  # texts -> L2-normalised (n, d)


def default_embedder() -> Embed:
    from sentence_transformers import SentenceTransformer

    from hci.device import torch_device

    model = SentenceTransformer(EMBED_MODEL, device=torch_device())
    return lambda texts: model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)


def tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


class Index:
    # ponytail: brute-force numpy scan, fine up to ~100k chunks; swap for faiss/sqlite-vec past that
    def __init__(self, chunks: list[Chunk], embed: Embed):
        self.chunks, self.embed = chunks, embed
        self.vecs = embed([c.text for c in chunks])
        self.docs = [Counter(tokenize(c.text)) for c in chunks]
        self.lens = np.array([sum(d.values()) for d in self.docs])
        self.df = Counter(t for d in self.docs for t in d)

    def bm25(self, query: str, k1: float = 1.5, b: float = 0.75) -> np.ndarray:
        n, avg = len(self.docs), self.lens.mean()
        scores = np.zeros(n)
        for t in set(tokenize(query)):
            if t not in self.df:
                continue
            idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
            tf = np.array([d[t] for d in self.docs])
            scores += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * self.lens / avg))
        return scores

    def search(self, query: str, k: int = 6, skip: Collection[str] = ()) -> list[Chunk]:
        dense = self.vecs @ self.embed([QUERY_PREFIX + query])[0]
        fused = np.zeros(len(self.chunks))
        for scores in (dense, self.bm25(query)):
            fused[np.argsort(-scores)] += 1 / (60 + np.arange(1, len(scores) + 1))
        ranked = (self.chunks[i] for i in np.argsort(-fused))
        return [c for c in ranked if c.id not in skip][:k]
