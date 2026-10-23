"""Agent loop for cloud models: Claude searches and updates the robot's memory through tools.

The model never writes memory by itself: add_context goes through `propose`, which asks the operator.
"""

import json
import os
import sys
from collections.abc import Callable, Iterator, Sequence

import anthropic
from anthropic import beta_tool

from hci import corpus, llm
from hci.rag import RAG, SYSTEM

MODEL = "claude-sonnet-5-5"
Propose = Callable[[str, int | None], str]  # (fact, scenario) -> tool result shown to the model
Answer = Callable[..., Iterator[str]]  # (question, scenario=None, history=(), propose=reject)


def reject(text: str, scenario: int | None) -> str:
    return "Not saved: no operator available to approve facts here."


AGENT_SYSTEM = (
    SYSTEM
    + """

You have tools over the robot's memory:
- query_context: search the records. Call it before answering, as often as needed (paths, manual, past corrections).
- add_context: when the user reports a new observation or change (a closed path, new weather, a repair), propose it
  as a fact. The operator approves it; do not claim it is saved unless the tool says so.
Passage numbers restart at each search; cite them as [search.passage], e.g. [1.2]."""
)


class Agent:
    def __init__(self, rag: RAG, model: str = MODEL):
        self.rag, self.model, self.propose = rag, model, reject
        self.client = anthropic.Anthropic()
        self.searches = 0

        @beta_tool
        def query_context(query: str, scenario: int | None = None) -> str:
            """Search the robot's records: past paths, operating manual, past corrections, operator facts.

            Args:
                query: what to look for, in plain words.
                scenario: scenario index to focus on; its path steps and facts are always returned. Omit for all.
            """
            self.searches += 1
            ctx = self.rag.retrieve(query, scenario)
            if not ctx:
                return "Nothing relevant in the records."
            return "\n".join(f"[{self.searches}.{i}] ({c.source}) {c.text}" for i, c in enumerate(ctx, 1))

        @beta_tool
        def add_context(text: str, scenario: int | None = None) -> str:
            """Propose a new fact for the robot's memory (operator approval required).

            Args:
                text: the fact, one self-contained sentence, e.g. "Path C is blocked by a fallen tree."
                scenario: scenario index it applies to; omit if it applies everywhere.
            """
            return self.propose(text, scenario)

        @beta_tool
        def list_scenarios() -> str:
            """List the known scenarios with their index."""
            return json.dumps({i: s.get("description", "") for i, s in enumerate(corpus.scenarios())})

        self.tools = [query_context, add_context, list_scenarios]

    def answer(
        self,
        question: str,
        scenario: int | None = None,
        history: Sequence[tuple[str, str]] = (),
        propose: Propose = reject,
    ) -> Iterator[str]:
        self.searches, self.propose = 0, propose
        messages = [
            m for q, a in history for m in ({"role": "user", "content": q}, {"role": "assistant", "content": a})
        ]
        where = f"The current scenario is {scenario}." if scenario is not None else "No current scenario."
        messages.append({"role": "user", "content": f"{where}\n\n{question}"})
        runner = self.client.beta.messages.tool_runner(
            model=self.model,
            max_tokens=16000,
            system=AGENT_SYSTEM,
            tools=self.tools,
            messages=messages,
            max_iterations=8,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        for message in runner:
            for block in message.content:
                if block.type == "text":
                    yield block.text
            if message.stop_reason == "refusal":
                yield "\n[The model declined to answer.]"


def answerer(rag: RAG, provider: str | None = None, model: str | None = None) -> Answer:
    """Claude runs the agent loop; local models run the fixed RAG pipeline (too small for reliable tool use)."""
    if (provider or os.environ.get("HCI_PROVIDER")) == "anthropic":
        print(f"Model: {model or MODEL} (Anthropic, agent mode)", file=sys.stderr)
        return Agent(rag, model or MODEL).answer
    gen = llm.load(provider, model)
    return lambda question, scenario=None, history=(), propose=reject: rag.answer(question, gen, scenario, history)
