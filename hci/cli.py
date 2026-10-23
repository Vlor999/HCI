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
    serve = sub.add_parser("serve", help="HTTP API + phone web app")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8000)
    a = p.parse_args()

    if a.cmd == "serve":
        from hci.server import run

        return run(a.host, a.port)
    if a.cmd == "fact":
        return corpus.add_fact(a.text, a.scenario)

    from hci import llm
    from hci.rag import RAG

    rag, gen = RAG(), llm.load(a.provider, a.model)
    if a.cmd == "ask":
        for t in rag.answer(a.question, gen, a.scenario):
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
        for t in rag.answer(q, gen, a.scenario, history):
            print(t, end="", flush=True)
            out.append(t)
        history.append((q, "".join(out)))
        print()


if __name__ == "__main__":
    main()
