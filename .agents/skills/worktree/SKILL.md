---
name: worktree
description: Implement one task in an isolated git worktree, from branch to GitHub PR (tests, logical commits, push, PR on the base branch). Use when asked to implement a task in a worktree.
user-invocable: true
---

Implement one task in an isolated worktree, up to the PR.
One task = one worktree = one PR. Full protocol: `.agents/rules/subagents.instructions.md`.

**Signature:** `/worktree <task description> <base branch>`

If the task or the base branch is missing, ask before continuing.

## 1. Understand the task

Read the task description and the code it touches. If the work already exists on the base branch, say so and do only what is left.

## 2. Create the worktree

Branch: `<scope>/<feature-slug>`.

```bash
git fetch origin
git worktree add .worktrees/<feature-slug> -b <branch> origin/<base>
```

Work only inside this worktree.

## 3. Implement

- Load `ponytail` first: simplest thing that works, reuse what the repo has.
- Follow `CLAUDE.md` and `.agents/rules/`, in particular `coding-standards.instructions.md` (constants, settings and types placement).
- Stay inside the task scope. No unrequested refactor.

## 4. Verify

Run `make check-all` until green. Never push red, never `--no-verify`.

## 5. Commit and push

Use `logical-commit-sequencer`: atomic commits ordered by dependency, Conventional Commits.

```bash
git push -u origin <branch>
```

## 6. Open the PR

```bash
gh pr create --base <base> --title "<conventional commit>" --body "..."
```

Body:

```
## Intent
<What the PR does and why, 1-2 sentences.>

## Choices and points of attention
- <Each decision taken, as a statement.>
```

- No AI attribution: no "Generated with Claude Code" line, no `Co-Authored-By: Claude` trailer.
- No question in the body. An open decision is settled with the user before the PR is opened.

## 7. Report

Give the PR URL, the decisions taken, and the work left after the PR.
