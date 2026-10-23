import argparse

from hci import corpus


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
            print(t, end="", flush=True)
        return print()

    for i, s in enumerate(corpus.scenarios()):
        print(f"  {i}: {s.get('description', '')}")
    history: list[tuple[str, str]] = []
    print("Questions, '/fact <text>' to record an update, empty line to quit.")
    while q := input("\n> ").strip():
        if q.startswith("/fact "):
            rag.add_fact(q[6:], a.scenario)
            continue
        out = []
        for t in answer(q, a.scenario, history, propose):
            print(t, end="", flush=True)
            out.append(t)
        history.append((q, "".join(out)))
        print()


if __name__ == "__main__":
    main()
