---
description: "pytest conventions, mocking strategy and JSON case format for HCI."
applyTo: "{tests/**/*.py,**/conftest.py}"
paths:
  - "tests/**/*.py"
  - "**/conftest.py"
---

# Testing

## Setup

- **pytest**, run through `make test` (`uv run pytest`).
- Shared fixtures live in `tests/conftest.py`.
- **No real network calls.** Anthropic, TypeSafe/Jev and Hugging Face downloads are mocked or skipped. Tests never call paid APIs. The real local embedder is allowed only in the JSON case runner (`tests/test_cases.py`).

## Structure

- Mirror modules: `hci/rag.py` -> `tests/test_rag.py`.
- Group related cases in a class (`class TestHybridIndex:`); standalone functions for single-case tests.
- **One behavior per test**, with a docstring saying what it verifies. Tests are independent.
- `@pytest.mark.parametrize` for several inputs, never copy-paste tests.
- `_make_*` factory functions build test data (`_make_chunk()`, `_make_settings()`). `tmp_path` for files.

### AAA pattern

```python
def test_rrf_ranks_shared_hit_first():
    """A chunk found by both retrievers outranks single-source chunks."""
    # Arrange
    dense, sparse = ["a", "b"], ["b", "c"]
    # Act
    fused = reciprocal_rank_fusion([dense, sparse])
    # Assert
    assert fused[0] == "b"
```

## Mocking

- **Mock at the consumption site**, not the definition: `@patch("hci.agent.Anthropic")`, not `anthropic.Anthropic`.
- `MagicMock` for sync, `AsyncMock` for async dependencies. `side_effect` for errors or successive returns.
- Env settings: `monkeypatch.setenv(...)` then `get_settings.cache_clear()`.
- Assert return values AND interactions (`assert_called_once_with`, `call_count`).

## JSON cases

- Cases live in `tests/cases/*.json`, validated by `tests/cases/schema.json`. Each file is a list of objects:
  - `id` (kebab-case), `question`, `expect` (required); `description`, `tags`, `scenario` (index or null), `history` (list of `[question, answer]`), `facts` (`{text, scenario}`, recorded before the question as `fact-0`, `fact-1`, ...), `xfail` (reason for a known failure), `unanswerable` (out-of-scope: the answer must refuse; with `--jev`, retrieval passes iff Jev refuses).
  - `expect` keys: `retrieved`, `not_retrieved`, `first` (chunk ids), `answer_contains`, `answer_contains_any`, `answer_excludes` (answer checks run in `hci eval` only, they need an LLM). `answer_excludes` holds only strings that prove the model answered, never words a refusal restates.
- Add a case rather than a Python test when the check is "question X retrieves chunk Y".
