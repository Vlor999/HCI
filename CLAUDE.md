# Agent Instructions & Guidelines for HCI

RAG that explains why a forest robot picked a path, from its own records. Details in `README.md`.

## Python Execution & Make

All execution MUST go through [`uv`](https://github.com/astral-sh/uv). Never bare `python`, `pytest`, `ruff`, `ty`, never `pip`.

- `make install`, `make format-fix`, `make lint-fix`, `make test`, `make eval`, `make check-all` (see `.agents/rules/tooling.instructions.md`).
- Run `make check-all` before every push.
- One-off: `uv run hci ...`. Packages: `uv add <pkg>` / `uv add --dev <pkg>`.

## Project Structure

```
HCI (root)
├── hci/        # package: corpus, documents, index, rag, agent, llm, device, jev, metrics, auth, server, dashboard, cli, evaluate
│   ├── constants.py   # immutable values (URLs, model ids, prompts, labels, markers)
│   ├── config.py      # pydantic-settings Settings + get_settings()
│   ├── types.py       # type aliases, protocols, domain dataclasses
│   └── schemas.py     # API request/response pydantic models
├── tests/      # test_<module>.py, test_cases.py, cases/*.json + schema.json
├── web/        # phone UI (index.html), metrics dashboard (dashboard.html), vendor/ pinned JS libs
├── logs/       # metrics.jsonl and dashboard.log (git-ignored)
├── data/       # paths, documents (manual, uploads), corrections
├── doc/        # LaTeX report
└── .agents/    # rules and skills (.claude/ symlinks here)
```

## Rules

Read before coding: `.agents/rules/coding-standards.instructions.md` (placement of constants, config, types; function size; naming; lazy-import exception), `testing.instructions.md`, `tooling.instructions.md`, `subagents.instructions.md`.

## Product Constraints (non-negotiable)

- **Answers are grounded in the robot's records only** (paths, manual, corrections, operator updates). No record, no answer: say "I don't know".
- **Facts are never written to memory without operator approval.** CLI asks `[y/N]`, phone shows Approve / Reject.
- **API keys stay server-side.** Never in the web page, never in a response. The phone authenticates with the `HCI_TOKEN`.
- **Local-first, Claude optional.** Local providers (MLX, CUDA, CPU) must keep working with no key; Anthropic agent mode is opt-in.
- **Tests never call paid APIs** (Anthropic, TypeSafe/Jev) nor download models.
