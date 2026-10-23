# Example — Mixed WIP: dependency bump + new module + feature + docs

## Repository state

```bash
$ git status --short
 M pyproject.toml
 M src/services/export.py
?? src/services/validators.py
 M tests/test_export.py
?? tests/test_validators.py
 M docs/services/export.md

$ git ls-files --others --exclude-standard
src/services/validators.py
tests/test_validators.py
```

```diff
# pyproject.toml (excerpt)
-anthropic = "^0.20.0"
+anthropic = "^0.25.0"
```

---

## Grouping by intent

| Group | Files | Rationale |
|---|---|---|
| 1 — Dependency bump | `pyproject.toml` | Mechanical, fully isolated |
| 2 — New validator module | `src/services/validators.py`, `tests/test_validators.py` | Foundation — must come before export |
| 3 — Export service update | `src/services/export.py`, `tests/test_export.py` | Uses the new validators |
| 4 — Docs | `docs/services/export.md` | Follows the implementation |

---

## Ordered commit plan

### Commit 1
**Goal**: isolate the dependency bump so it's reviewable and revertable on its own.
```bash
git add pyproject.toml
git commit -m "build(deps): bump anthropic to ^0.25.0"
```

### Commit 2
**Goal**: land the new validator module as a standalone, testable unit.
```bash
git add src/services/validators.py tests/test_validators.py
git commit -m "feat(validators): add input validators for export pipeline"
```

### Commit 3
**Goal**: update the export service to use the new validators.
```bash
git add src/services/export.py tests/test_export.py
git commit -m "feat(export): validate inputs using new validators module"
```

### Commit 4
**Goal**: keep documentation in sync with the implementation.
```bash
git add docs/services/export.md
git commit -m "docs(export): update service documentation"
```

---

## Full command sequence (copy-paste)

```bash
git add pyproject.toml && git commit -m "build(deps): bump anthropic to ^0.25.0"
git add src/services/validators.py tests/test_validators.py && git commit -m "feat(validators): add input validators for export pipeline"
git add src/services/export.py tests/test_export.py && git commit -m "feat(export): validate inputs using new validators module"
git add docs/services/export.md && git commit -m "docs(export): update service documentation"
```
