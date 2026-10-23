"""Agent loop for cloud models: Claude searches and updates the robot's memory through tools.

The model never writes memory by itself: `add_context` goes through `propose`, which asks the operator.
Per-request state (search count, pending steps, `propose`) lives on an `AgentRun`, never on the shared agent.
"""

import json
from collections.abc import Iterator, Sequence

import anthropic
from anthropic import beta_tool
from anthropic.lib.streaming import BetaMessageStream
from anthropic.lib.tools import BetaStreamingToolRunner
from anthropic.types import AnthropicBetaParam
from anthropic.types.beta import BetaMessageParam
from loguru import logger

from hci import corpus, llm
from hci.config import get_settings
from hci.constants import (
    AGENT_BETAS,
    AGENT_NO_OPERATOR,
    AGENT_NO_SCENARIO_NOTE,
    AGENT_NOTHING_FOUND,
    AGENT_REFUSAL,
    AGENT_SCENARIO_NOTE,
    AGENT_STEP_FOUND,
    AGENT_STEP_REASONING,
    AGENT_STEP_THINKING,
    AGENT_SYSTEM,
    AGENT_TOOL_STEP_DEFAULT,
    AGENT_TOOL_STEP_SCENARIO,
    AGENT_TOOL_STEPS,
)
from hci.rag import ExplanationPipeline, status
from hci.types import Answer, Propose


def reject(text: str, scenario: int | None) -> str:
    """Default `propose` when no operator can approve facts.

    Args:
        text: the proposed fact.
        scenario: scenario it applies to, or None.

    Returns:
        The tool result telling the model nothing was saved.
    """
    return AGENT_NO_OPERATOR


def list_scenarios() -> str:
    """List the known scenarios with their index."""
    return json.dumps({i: s.get("description", "") for i, s in enumerate(corpus.scenarios())})


class AgentRun:
    """State of one answer: the tools Claude calls and the steps they report.

    Attributes:
        rag: pipeline the search tool reads from.
        propose: callback asking the operator to approve a fact.
        searches: number of searches so far; numbers the passages as [search.passage].
        events: tool results not yet shown as steps.
        tools: the runnable tools bound to this run.
    """

    def __init__(self, rag: ExplanationPipeline, propose: Propose = reject):
        self.rag, self.propose = rag, propose
        self.searches = 0
        self.events: list[str] = []
        self.tools = [beta_tool(self.query_context), beta_tool(self.add_context), beta_tool(list_scenarios)]

    def query_context(self, query: str, scenario: int | None = None) -> str:
        """Search the robot's records: past paths, operating manual, past corrections, operator facts.

        Args:
            query: what to look for, in plain words.
            scenario: scenario index to focus on; its path steps and facts are always returned. Omit for all.
        """
        self.searches += 1
        chunks = self.rag.retrieve(query, scenario).chunks
        self.events.append(AGENT_STEP_FOUND.format(len(chunks)))
        if not chunks:
            return AGENT_NOTHING_FOUND
        return "\n".join(f"[{self.searches}.{i}] ({c.source}) {c.text}" for i, c in enumerate(chunks, 1))

    def add_context(self, text: str, scenario: int | None = None) -> str:
        """Propose a new fact for the robot's memory (operator approval required).

        Args:
            text: the fact, one self-contained sentence, e.g. "Path C is blocked by a fallen tree."
            scenario: scenario index it applies to; omit if it applies everywhere.
        """
        return self.propose(text, scenario)

    def drain_steps(self) -> Iterator[str]:
        """Yield the pending tool results as step lines, then forget them.

        Yields:
            Step lines (`STEP_MARKER` prefixed).
        """
        yield from (status(e) for e in self.events)
        self.events.clear()


class ClaudeMemoryAgent:
    """Claude with tools over the robot's memory. Safe to share across requests: it holds no per-request state.

    Args:
        rag: pipeline the search tool reads from.
        model: Claude model id; None uses `Settings.claude_model`.
    """

    def __init__(self, rag: ExplanationPipeline, model: str | None = None):
        self.rag, self.model = rag, model or get_settings().claude_model
        key = get_settings().anthropic_api_key
        self.client = anthropic.Anthropic(api_key=key.get_secret_value() if key else None)

    def answer(
        self,
        question: str,
        scenario: int | None = None,
        history: Sequence[tuple[str, str]] = (),
        propose: Propose = reject,
    ) -> Iterator[str]:
        """Stream an answer.

        Args:
            question: the user's question.
            scenario: current scenario index, or None.
            history: previous (question, answer) turns, oldest first.
            propose: callback asking the operator to approve a fact.

        Yields:
            Answer text pieces and step lines.
        """
        yield status(AGENT_STEP_THINKING)
        yield from self._stream(AgentRun(self.rag, propose), build_messages(question, scenario, history))

    def _stream(self, run: AgentRun, messages: list[BetaMessageParam]) -> Iterator[str]:
        for stream in self._runner(run, messages):  # one stream per model turn; tools run between turns
            yield from run.drain_steps()
            yield from map_events(stream)
            if stream.get_final_message().stop_reason == "refusal":
                yield AGENT_REFUSAL

    def _runner(self, run: AgentRun, messages: list[BetaMessageParam]) -> BetaStreamingToolRunner:
        settings = get_settings()
        betas: list[AnthropicBetaParam] = list(AGENT_BETAS)
        return self.client.beta.messages.tool_runner(
            model=self.model,
            max_tokens=settings.agent_max_tokens,
            system=AGENT_SYSTEM,
            tools=run.tools,
            messages=messages,
            max_iterations=settings.agent_max_iterations,
            output_config={"effort": settings.agent_effort},
            betas=betas,
            fallbacks="default",
            stream=True,
        )


def build_messages(question: str, scenario: int | None, history: Sequence[tuple[str, str]]) -> list[BetaMessageParam]:
    """Turn history and the question into Messages API turns.

    Args:
        question: the user's question.
        scenario: current scenario index, or None; stated in the last user turn.
        history: previous (question, answer) turns, oldest first.

    Returns:
        Alternating user/assistant messages ending with the question.
    """
    messages: list[BetaMessageParam] = []
    for q, a in history:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    where = AGENT_SCENARIO_NOTE.format(scenario) if scenario is not None else AGENT_NO_SCENARIO_NOTE
    messages.append({"role": "user", "content": f"{where}\n\n{question}"})
    return messages


def map_events(stream: BetaMessageStream) -> Iterator[str]:
    """Map one model turn's stream events to answer text and step lines.

    Args:
        stream: the stream of one model turn.

    Yields:
        Text deltas, plus a step when thinking starts and when a tool call is complete.
    """
    for event in stream:
        if event.type == "content_block_start" and event.content_block.type == "thinking":
            yield status(AGENT_STEP_REASONING)
        elif event.type == "text":
            yield event.text
        elif event.type == "content_block_stop" and event.content_block.type == "tool_use":
            yield status(describe(event.content_block.name, event.content_block.input))


def describe(tool: str, args: dict) -> str:
    """Step label for a tool call.

    Args:
        tool: tool name.
        args: tool input.

    Returns:
        The label from `AGENT_TOOL_STEPS`, or `AGENT_TOOL_STEP_DEFAULT` for an unknown tool.
    """
    template = AGENT_TOOL_STEPS.get(tool)
    if template is None:
        return AGENT_TOOL_STEP_DEFAULT.format(tool=tool)
    where = AGENT_TOOL_STEP_SCENARIO.format(args["scenario"]) if args.get("scenario") is not None else ""
    return template.format(query=args.get("query", ""), text=args.get("text", "")) + where


def answerer(rag: ExplanationPipeline, provider: str | None = None, model: str | None = None) -> Answer:
    """Pick the answer function for a provider.

    Claude runs the agent loop; local models run the fixed RAG pipeline (too small for reliable tool use).

    Args:
        rag: the shared pipeline.
        provider: mlx | cuda | cpu | anthropic; None uses `Settings.provider`, then the fastest local backend.
        model: model name for the provider; None uses the default.

    Returns:
        A function streaming answer text pieces and step lines.
    """
    if (provider or get_settings().provider) == "anthropic":
        logger.info("Model: {} (Anthropic, agent mode)", model or get_settings().claude_model)
        return ClaudeMemoryAgent(rag, model).answer
    gen = llm.load(provider, model)
    return lambda question, scenario=None, history=(), propose=reject: rag.answer(question, gen, scenario, history)
