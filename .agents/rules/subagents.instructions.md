---
description: "Protocol for launching implementation sub-agents: worktree, branch, model, skills, output requirements and PR."
---

# Implementation sub-agents (task -> PR)

**One task = one sub-agent = one worktree = one PR.** Mandatory protocol whenever sub-agents implement a task.

## Launch

- **Model**: chosen per task, never the orchestrator's by default. Set the `model` parameter of the Agent tool on every launch.
  - Opus: implementation (code, tests, PR), design, architecture decisions, validation of review findings, bugs with unknown cause.
  - Sonnet: bounded mechanical work (docs, renames, repetitive migrations) and reviewers.
  - Haiku: read-only exploration and search.
  When in doubt between two models, take the more capable.
- **Isolation**: one worktree per task, from the base branch:
  `git worktree add .worktrees/<slug> -b <branch> origin/<base>`.
  Never two agents on the same files.
- **Branch**: `<scope>/<feature-slug>` (e.g. `rag/hybrid-index-split`).
- **Context in the prompt**: task description, applicable rules (`.agents/rules/`, `CLAUDE.md`, README) and known entry files. The agent guesses nothing.

## Skills to always give

- **`ponytail`**: simplest solution that works, plus the placement rules of `coding-standards.instructions.md` (no inline constant, settings in `Settings`, reuse existing code). Never omit.
- **`logical-commit-sequencer`**: atomic commits ordered by dependency before the push. Never omit.
- Task-specific skills (`tdd`, etc.).

## Output requirements

1. **`make check-all` green before push.**
2. **PR on GitHub**: `gh pr create --base <base>`, title = conventional commit. Body: intent, then choices and points of attention.
   **No AI attribution**: no "Generated with Claude Code" line in PR bodies, no `Co-Authored-By: Claude` trailer in commits.
   **The PR body never asks a question.** An open decision goes to the user in the conversation and is settled before the PR is opened.
3. **Document decisions** (parameter, library, deviation, assumption) in the PR body and in the README or `doc/` when they affect usage.
4. **Remaining work** goes back to the orchestrator in the final report.

## After review

- A sub-agent does not launch agents: the orchestrator launches reviewers (`mr-review`) and consolidates findings.
- Review comments go back to the original agent (it has the context). It fixes, pushes on the same branch with new commits (no amend, no force-push after the first push) and **answers each comment on GitHub**.
- After merge: remove the worktree (`git worktree remove .worktrees/<slug>`).
