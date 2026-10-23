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
from hci.constants import AGENT_BETAS, AGENT_SYSTEM, CLAUDE_MODEL
from hci.rag import RAG, status

Propose = Callable[[str, int | None], str]  # (fact, scenario) -> tool result shown to the model
Answer = Callable[..., Iterator[str]]  # (question, scenario=None, history=(), propose=reject)


def reject(text: str, scenario: int | None) -> str:
    return "Not saved: no operator available to approve facts here."


class Agent:
    def __init__(self, rag: RAG, model: str = CLAUDE_MODEL):
        self.rag, self.model, self.propose = rag, model, reject
        self.client = anthropic.Anthropic()
        self.searches, self.events = 0, []  # events: tool results, shown as steps

        @beta_tool
        def query_context(query: str, scenario: int | None = None) -> str:
            """Search the robot's records: past paths, operating manual, past corrections, operator facts.

            Args:
                query: what to look for, in plain words.
                scenario: scenario index to focus on; its path steps and facts are always returned. Omit for all.
            """
            self.searches += 1
            ctx = self.rag.retrieve(query, scenario)
            self.events.append(f"Found {len(ctx or [])} passages")
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
        self.searches, self.events, self.propose = 0, [], propose
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
            betas=list(AGENT_BETAS),
            fallbacks="default",
            stream=True,
        )
        yield status("Thinking")
        for stream in runner:  # one stream per model turn; tools run between turns
            yield from (status(e) for e in self.events)
            self.events.clear()
            for event in stream:
                if event.type == "content_block_start" and event.content_block.type == "thinking":
                    yield status("Reasoning")
                elif event.type == "text":
                    yield event.text
                elif event.type == "content_block_stop" and event.content_block.type == "tool_use":
                    yield status(describe(event.content_block.name, event.content_block.input))
            if stream.get_final_message().stop_reason == "refusal":
                yield "\n[The model declined to answer.]"


def describe(tool: str, args: dict) -> str:
    where = f" (scenario {args['scenario']})" if args.get("scenario") is not None else ""
    if tool == "query_context":
        return f'Searching: "{args.get("query", "")}"{where}'
    if tool == "add_context":
        return f'Proposing fact: "{args.get("text", "")}"{where}'
    return "Listing scenarios"


def answerer(rag: RAG, provider: str | None = None, model: str | None = None) -> Answer:
    """Claude runs the agent loop; local models run the fixed RAG pipeline (too small for reliable tool use)."""
    if (provider or os.environ.get("HCI_PROVIDER")) == "anthropic":
        print(f"Model: {model or CLAUDE_MODEL} (Anthropic, agent mode)", file=sys.stderr)
        return Agent(rag, model or CLAUDE_MODEL).answer
    gen = llm.load(provider, model)
    return lambda question, scenario=None, history=(), propose=reject: rag.answer(question, gen, scenario, history)
