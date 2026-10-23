---
description: "Python coding standards for HCI: syntax, naming, imports, placement of constants/config/types, function size, logging, Pydantic v2."
applyTo: "**/*.py"
paths:
  - "**/*.py"
---

# Coding Standards

## Python Syntax

- **Python 3.12**: `str | None` (not `Optional[str]`), `list[str]` (not `List[str]`).
- **Type annotations everywhere**: parameters, return types, class attributes. No `Any` unless unavoidable.
- **`from __future__ import annotations`** and `TYPE_CHECKING` guard only for forward references or circular imports.
- **Google-style docstrings**: `Args:`, `Returns:`, `Raises:`, `Yields:`. Required on every public function, method and class, and on every module (module docstring). Omit on trivial private helpers.

## Naming

| Construct | Convention | Example |
|---|---|---|
| Classes | `PascalCase`, explicit domain name | `HybridIndex`, `RobotMemory`, `ClaudeMemoryAgent`, `SlashCommandCompleter` |
| Functions / methods | `snake_case` | `build_prompt`, `reciprocal_rank_fusion` |
| Private helpers | `_snake_case` | `_split_chunks`, `_parse_step` |
| Module-level constants | `UPPER_SNAKE_CASE` | `STEP_MARKER`, `SYSTEM_PROMPT` |
| Enum members | `UPPER_SNAKE_CASE` | `MLX`, `ANTHROPIC` |
| Settings fields | `snake_case` (env name via prefix/alias) | `provider`, `jev_keep` |

- Never generic class names (`RAG`, `Agent`, `Index`, `R`): the name says what the object is in the domain.
- Names are clear and self-describing. Acceptable abbreviations: `id`, `url`, `api`, `http`, `llm`, `k`.

## Imports

- **Absolute imports only** from `hci.*`. No relative imports.
- Order: standard library, third-party, local (ruff rule `I`).
- **No lazy imports.** All imports at module level. ONE exception: platform-specific optional backends that cannot import everywhere (e.g. `mlx_lm` only on Apple Silicon, heavy `torch`/`transformers` loading for an unused backend). Such an import sits in the one function that needs it, with a comment saying why.
- **No `__all__` in `__init__.py`**: import from the module that defines the symbol.

## Constants & Placement

- **Immutable values** (URLs, model ids, prompts, labels, command tables, markers) live in `hci/constants.py`.
- **Tunable values** (thresholds, model names, timeouts, `k`, ports, env-driven settings such as `HCI_PROVIDER`, `HCI_MODEL`, `HCI_EMBED_MODEL`, `HCI_JEV_*`, `HCI_TOKEN`) are fields of a `pydantic-settings` `Settings` in `hci/config.py`, each with a default and a `description`. An env change never requires a code change.
- Settings are read through `get_settings()` (`@lru_cache`). Never instantiate `Settings` elsewhere. **Never `os.environ.get` in modules.** Tests override with `monkeypatch.setenv` plus `get_settings.cache_clear()`.
- **Type aliases, protocols and domain dataclasses** live in `hci/types.py`. **API request/response pydantic models** live in `hci/schemas.py`.
- **One declaration per object**: grep for an existing client, helper, prompt or value before writing one. A value declared twice is a review reject.

## Functions and Classes

- A function does one thing. Aim at 20 lines of body or fewer, hard limit about 30. Split into named private helpers.
- No nested function definitions, except tiny closures that capture state on purpose.
- Domain data holders: `@dataclass` (`frozen=True` when immutable), no Pydantic validation needed.

## Pydantic (v2)

- `Field(...)` for required fields; `Field(default=..., description=...)` for optional ones. **Every schema and settings field carries `Field(description=...)`.**
- `@model_validator(mode="after")` for cross-field validation, raise `ValueError`.
- `.model_validate(data)`, not `.parse_obj()`.

## Enums

- `StrEnum` for string-valued enums, `Enum` for structured ones.

## Output and Logging

- `print` only for CLI user-facing output.
- Diagnostics go through `loguru` (`from loguru import logger`), `{}` placeholders, never f-strings: `logger.info("Indexed {} chunks", count)`. Never import `logging`.

## Error Handling

- API layer: raise `HTTPException` with explicit `status_code` and user-friendly `detail`.
- I/O boundaries (LLM, Jev, disk): catch, log, return a safe fallback. Never swallow silently.
- Pydantic validators raise `ValueError`. No custom exception hierarchy.

## Sync / Async

- FastAPI handlers stay sync: generation is blocking and streamed (`StreamingResponse` over a generator).

## Ponytail Comments

- `# ponytail: <ceiling>, <upgrade path>` marks a deliberate simplification. Keep it accurate: update or delete it when the code changes.
