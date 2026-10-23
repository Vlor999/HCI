import argparse

from hci import corpus
from hci.constants import COMMANDS, STEP_MARKER


def main() -> None:
    p = argparse.ArgumentParser(prog="hci", description="Ask a robot why it chose its path.")
    p.add_argument("-p", "--provider", help="mlx | cuda | cpu | anthropic (default: fastest local)")
    p.add_argument("-m", "--model", help="model name/path for the provider")
    p.add_argument("-s", "--scenario", type=int, help="current scenario index in data/paths.json")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ask").add_argument("question")
    sub.add_parser("chat")
    sub.add_parser("fact").add_argument("text")
    sub.add_parser("eval", help="run tests/cases end to end, print a JSON report").add_argument(
        "--no-answers", action="store_true", help="retrieval only, no LLM"
    )
    serve = sub.add_parser("serve", help="HTTP API + phone web app")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    a = p.parse_args()

    if a.cmd == "serve":
        from hci.server import run

        return run(a.host, a.port)
    if a.cmd == "eval":
        import json

        from hci.evaluate import run

        return print(json.dumps(run(a.provider, a.model, not a.no_answers), indent=2))
    if a.cmd == "fact":
        return corpus.add_fact(a.text, a.scenario)

    from hci.agent import answerer
    from hci.rag import RAG

    def propose(text: str, scenario: int | None) -> str:
        if input(f"\nSave fact for scenario {scenario}: {text!r}? [y/N] ").strip().lower() != "y":
            return "The operator rejected this fact. Do not propose it again."
        rag.add_fact(text, scenario)
        return "Saved."

    rag = RAG()
    answer = answerer(rag, a.provider, a.model)
    if a.cmd == "ask":
        for t in answer(a.question, a.scenario, (), propose):
            show(t)
        return print()

    chat(answer, rag, a.scenario, propose)


def show(t: str) -> str:
    if t.startswith(STEP_MARKER):
        print(f"\n\033[2m· {t[1:].strip()}\033[0m", flush=True)
        return ""
    print(t, end="", flush=True)
    return t


def chat(answer, rag, scenario: int | None, propose) -> None:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, FuzzyWordCompleter

    class Slash(Completer):  # fuzzy menu of commands while the line is a bare "/word"
        fuzzy = FuzzyWordCompleter(list(COMMANDS), meta_dict=COMMANDS, WORD=True)

        def get_completions(self, document, event):
            text = document.text_before_cursor
            if text.startswith("/") and " " not in text:
                yield from self.fuzzy.get_completions(document, event)

    names = [s.get("description", "") for s in corpus.scenarios()]
    print("\n".join(f"  {i}: {d}" for i, d in enumerate(names)))
    print("Ask a question, or type / for commands.")
    session, history = PromptSession(completer=Slash(), complete_while_typing=True), []
    while True:
        try:
            q = session.prompt(f"\n[{'-' if scenario is None else scenario}]> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        cmd, _, arg = q.partition(" ")
        if not q:
            continue
        if cmd == "/exit":
            return
        if cmd == "/clear":
            history.clear()
            print("Conversation cleared.")
        elif cmd == "/fact" and arg.strip():
            rag.add_fact(arg.strip(), scenario)
            print("Fact saved.")
        elif cmd == "/scenario":
            if arg.strip().isdigit() and int(arg) < len(names):
                scenario, history = int(arg), []
            print(f"Scenario: {scenario if scenario is None else f'{scenario} ({names[scenario]})'}")
        elif cmd.startswith("/"):
            print("\n".join(f"  {c:<10} {d}" for c, d in COMMANDS.items()))
        else:
            out = [show(t) for t in answer(q, scenario, history, propose)]
            history.append((q, "".join(out).strip()))
            print()


if __name__ == "__main__":
    main()
