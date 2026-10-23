---
description: "uv, make and quality tooling rules. Always use make targets first; never invoke python directly or use pip."
applyTo: "**"
---

# Tooling

**Prefer `make` targets over raw commands. Use `uv run` when no target exists. Never invoke `python`, `pytest`, `ruff` or `ty` bare. Never `pip`.**

## Quality tools

- `ruff`: formatter and linter (line length 120, set in `pyproject.toml`).
- `ty`: type checker. Added with `uv add --dev ty`.

## Make targets

Defined in the root `Makefile` (each wraps `uv run`). Check it before suggesting a command.

| Command | Purpose |
|---|---|
| `make install` | Install dependencies (`uv sync`) |
| `make format-check` | `ruff format --check` |
| `make format-fix` | `ruff format` |
| `make lint-check` | `ruff check` |
| `make lint-fix` | `ruff check --fix` |
| `make type-check` | `ty check` |
| `make test` | `pytest` |
| `make eval` | `hci eval`: end-to-end cases, needs an LLM (not in `check-all`) |
| `make check-all` | `format-check` + `lint-check` + `type-check` + `test` |

Run `make check-all` before every push. A missing target is not added on the fly: use `uv run` for a one-off need.

## uv

- `uv run <command>` when no target covers the need (e.g. `uv run hci -s 0 ask "..."`).
- `uv add <package>` / `uv add --dev <package>` to manage dependencies; `uv sync` to install from the lockfile.
- No `pip install`, no manual virtualenv, no bare `python`.
- API keys go in `.env` (git-ignored): `uv run --env-file .env hci ...`.
