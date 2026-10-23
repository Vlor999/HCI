import json

import numpy as np

from hci import corpus, jev
from hci.index import Index, tokenize
from hci.rag import NOT_FOUND, RAG, text_only


def fake_embed(texts):
    """Hashed bag of words: deterministic, no model download."""
    v = np.zeros((len(texts), 256))
    for i, t in enumerate(texts):
        for w in tokenize(t):
            v[i, hash(w) % 256] += 1
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


def test_rag(tmp_path, monkeypatch):
    monkeypatch.setattr(corpus, "FACTS", tmp_path / "facts.json")
    chunks = corpus.load()
    assert {c.source for c in chunks} == {"path", "manual", "correction", "example"}
    step_a = next(c for c in chunks if c.id == "path-0-A")
    assert "travel time 6.0 min" in step_a.text  # 120 m at 1.2 km/h

    top = Index(chunks, fake_embed).search("energy recharge power source", k=3)
    assert any(c.id == "manual-1" for c in top), [c.id for c in top]

    rag = RAG(embed=fake_embed, judge=False)
    ctx = rag.retrieve("which path is fastest?", scenario=0)
    assert [c.id for c in ctx[:3]] == ["path-0-A", "path-0-B", "path-0-C"]  # current scenario pinned first
    assert len({c.id for c in ctx}) == len(ctx)

    rag.add_fact("Path B is flooded", scenario=0)
    assert json.loads(corpus.FACTS.read_text())[0]["text"] == "Path B is flooded"
    assert any(c.source == "fact" for c in rag.retrieve("anything", scenario=0))

    seen = {}

    def gen(system, user):
        return iter([seen.setdefault("user", user)])

    assert "Question: why C?" in text_only(rag.answer("why C?", gen, scenario=0))
    assert "[1] (path)" in seen["user"]

    # Jev: request shape + gating
    body = jev.request("q", ctx[:2])
    assert set(body["questions"]) == {"p0", "p1", "answerable"} and body["state"]["passages"]["p0"] == ctx[0].text
    keep, ok = jev.parse({"p0": {"noul": 0.9}, "p1": {"noul": 0.1}, "answerable": {"noul": 0.8}}, ctx[:2])
    assert keep == {ctx[0].id} and ok

    rag.judge = True
    monkeypatch.setattr(jev, "judge", lambda q, c: (set(), False))
    assert text_only(rag.answer("weather on mars?", gen)) == NOT_FOUND


def test_agent_tools(tmp_path, monkeypatch):
    from hci.agent import Agent

    monkeypatch.setattr(corpus, "FACTS", tmp_path / "facts.json")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    agent = Agent(RAG(embed=fake_embed, judge=False))
    tools = {t.name: t for t in agent.tools}
    assert set(tools) == {"query_context", "add_context", "list_scenarios"}

    out = tools["query_context"].call({"query": "fastest path", "scenario": 0})
    assert out.startswith("[1.1] (path)") and "travel time" in out

    # add_context only proposes; the operator callback decides
    seen = []
    agent.propose = lambda text, scenario: seen.append((text, scenario)) or "Proposed."
    assert tools["add_context"].call({"text": "Path C is closed.", "scenario": 0}) == "Proposed."
    assert seen == [("Path C is closed.", 0)] and not corpus.FACTS.exists()
    assert "Winter scenario" in tools["list_scenarios"].call({})
