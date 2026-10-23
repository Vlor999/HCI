"""Command-line interface: ask one question, chat, record a fact, run the evaluation, or serve the phone app."""

import argparse
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import CompleteEvent, Completer, Completion, FuzzyWordCompleter
from prompt_toolkit.document import Document

from hci import corpus, evaluate, metrics, server
from hci.agent import answerer
from hci.config import get_settings
from hci.constants import COMMANDS, STEP_MARKER, MetricSource
from hci.rag import ExplanationPipeline
from hci.types import Answer


def show(piece: str) -> str:
    """Print one streamed piece: step lines dimmed on their own line, answer text inline.

    Args:
        piece: A text piece or a step line (starting with `STEP_MARKER`).

    Returns:
        The piece if it is answer text, "" for a step line.
    """
    if piece.startswith(STEP_MARKER):
        print(f"\n\033[2m· {piece[1:].strip()}\033[0m", flush=True)
        return ""
    print(piece, end="", flush=True)
    return piece


class SlashCommandCompleter(Completer):
    """Fuzzy menu of the chat commands while the line is a bare `/word`."""

    def __init__(self) -> None:
        """Build the fuzzy matcher over `COMMANDS`, with help texts as menu meta."""
        self.fuzzy = FuzzyWordCompleter(list(COMMANDS), meta_dict=COMMANDS, WORD=True)

    def get_completions(self, document: Document, complete_event: CompleteEvent) -> Iterable[Completion]:
        """Yield fuzzy command matches, nothing once the line has a space or is not a command.

        Args:
            document: The current input line.
            complete_event: How the completion was triggered.

        Yields:
            Matching commands.
        """
        text = document.text_before_cursor
        if text.startswith("/") and " " not in text:
            yield from self.fuzzy.get_completions(document, complete_event)


@dataclass
class ChatSession:
    """One conversation: the answerer, the current scenario and the previous turns.

    Attributes:
        rag: Pipeline that stores approved facts.
        answer: Streams answers.
        scenario: Current scenario index, None for no scenario.
        history: Previous (question, answer) turns, oldest first.
        names: Scenario descriptions, by index.
    """

    rag: ExplanationPipeline
    answer: Answer
    scenario: int | None = None
    history: list[tuple[str, str]] = field(default_factory=list)
    names: list[str] = field(default_factory=lambda: [s.get("description", "") for s in corpus.scenarios()])

    def propose(self, text: str, scenario: int | None) -> str:
        """Ask the operator to approve a fact the model proposes; save it on `y`.

        Args:
            text: The proposed fact.
            scenario: Scenario it applies to, None for everywhere.

        Returns:
            The tool result shown to the model.
        """
        if input(f"\nSave fact for scenario {scenario}: {text!r}? [y/N] ").strip().lower() != "y":
            return "The operator rejected this fact. Do not propose it again."
        self.rag.add_fact(text, scenario)
        return "Saved."

    def ask(self, question: str) -> None:
        """Stream the answer to `question`, record the turn and its metrics.

        Args:
            question: The user's question.
        """
        stream = self.answer(question, self.scenario, self.history, self.propose)
        pieces = [show(p) for p in metrics.track(stream, MetricSource.CLI, question, self.scenario)]
        self.history.append((question, "".join(pieces).strip()))
        print()

    def handle(self, line: str) -> bool:
        """Run a slash command or ask a question.

        Args:
            line: One stripped, non-empty input line.

        Returns:
            False when the chat should end.
        """
        if not line.startswith("/"):
            self.ask(line)
            return True
        command, _, arg = line.partition(" ")
        handler = SLASH_COMMANDS.get(command)
        if handler is None:
            print(f"Unknown command {command}.")
            return self.cmd_help("")
        return handler(self, arg.strip())

    def cmd_fact(self, arg: str) -> bool:
        """Save an operator update for the current scenario (the operator typed it, no approval asked)."""
        if not arg:
            print(f"Usage: {COMMANDS['/fact']}")
            return True
        self.rag.add_fact(arg, self.scenario)
        print("Fact saved.")
        return True

    def cmd_scenario(self, arg: str) -> bool:
        """Switch to scenario `arg` (clears the conversation), or show the current one when `arg` is empty."""
        if arg:
            if not (arg.isdigit() and int(arg) < len(self.names)):
                print(f"No scenario {arg!r}: pick 0 to {len(self.names) - 1}.")
                return True
            self.scenario, self.history = int(arg), []
        current = "none" if self.scenario is None else f"{self.scenario} ({self.names[self.scenario]})"
        print(f"Scenario: {current}")
        return True

    def cmd_clear(self, arg: str) -> bool:
        """Forget the conversation."""
        self.history.clear()
        print("Conversation cleared.")
        return True

    def cmd_help(self, arg: str) -> bool:
        """List the commands."""
        print("\n".join(f"  {command:<10} {text}" for command, text in COMMANDS.items()))
        return True

    def cmd_exit(self, arg: str) -> bool:
        """End the chat."""
        return False


# One handler per entry of `COMMANDS`: a command added there without a `cmd_<name>` method fails at import.
SLASH_COMMANDS: dict[str, Callable[[ChatSession, str], bool]] = {
    command: getattr(ChatSession, f"cmd_{command[1:]}") for command in COMMANDS
}


def run_chat(session: ChatSession) -> None:
    """Interactive loop: read lines until `/exit`, Ctrl-D or Ctrl-C.

    Args:
        session: The conversation to drive.
    """
    print("\n".join(f"  {i}: {name}" for i, name in enumerate(session.names)))
    print("Ask a question, or type / for commands.")
    prompt = PromptSession(completer=SlashCommandCompleter(), complete_while_typing=True)
    while True:
        try:
            line = prompt.prompt(f"\n[{'-' if session.scenario is None else session.scenario}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if line and not session.handle(line):
            return


def _session(args: argparse.Namespace) -> ChatSession:
    """Load the pipeline and the answerer chosen on the command line."""
    rag = ExplanationPipeline()
    return ChatSession(rag, answerer(rag, args.provider, args.model), args.scenario)


def _ask(args: argparse.Namespace) -> None:
    """`hci ask`: answer one question."""
    _session(args).ask(args.question)


def _chat(args: argparse.Namespace) -> None:
    """`hci chat`: interactive conversation."""
    run_chat(_session(args))


def _fact(args: argparse.Namespace) -> None:
    """`hci fact`: save an operator update."""
    corpus.add_fact(args.text, args.scenario)


def _eval(args: argparse.Namespace) -> None:
    """`hci eval`: run the cases end to end, print the JSON report."""
    print(json.dumps(evaluate.run(args.provider, args.model, not args.no_answers, judge=args.jev), indent=2))


def _serve(args: argparse.Namespace) -> None:
    """`hci serve`: HTTP API and phone web app."""
    server.run(args.host, args.port)


HANDLERS: dict[str, Callable[[argparse.Namespace], None]] = {
    "ask": _ask,
    "chat": _chat,
    "fact": _fact,
    "eval": _eval,
    "serve": _serve,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the `hci` argument parser, one sub-command per entry of `HANDLERS`.

    Returns:
        The parser.
    """
    parser = argparse.ArgumentParser(prog="hci", description="Ask a robot why it chose its path.")
    parser.add_argument("-p", "--provider", help="mlx | cuda | cpu | anthropic (default: fastest local)")
    parser.add_argument("-m", "--model", help="model name/path for the provider")
    parser.add_argument("-s", "--scenario", type=int, help="current scenario index in data/paths.json")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ask", help="answer one question").add_argument("question")
    sub.add_parser("chat", help="interactive conversation")
    sub.add_parser("fact", help="save an operator update").add_argument("text")
    evaluation = sub.add_parser("eval", help="run tests/cases end to end, print a JSON report")
    evaluation.add_argument("--no-answers", action="store_true", help="retrieval only, no LLM")
    evaluation.add_argument("--jev", action="store_true", help="filter retrieval with the Jev judge (paid)")
    serve = sub.add_parser("serve", help="HTTP API + phone web app")
    serve.add_argument("--host", default=get_settings().host)
    serve.add_argument("--port", type=int, default=get_settings().port)
    return parser


def main() -> None:
    """Parse the command line and run the chosen sub-command."""
    args = build_parser().parse_args()
    HANDLERS[args.cmd](args)


if __name__ == "__main__":
    main()
