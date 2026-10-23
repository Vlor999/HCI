---
name: logical-commit-sequencer
description: Split ongoing work into a clean sequence of logical commits with clear intent and dependency order. Use when the user asks to organize WIP into atomic commits, prepare history before a PR, or separate mixed changes safely.
---

Turn mixed WIP into an ordered commit plan that is easy to review.

Use this workflow:
1. Inspect repository state with `git status --short`, `git diff --staged`, and `git diff`.
2. Also check for untracked new files with `git ls-files --others --exclude-standard` — they must be staged before they can be committed, so include them in the plan.
3. Group changes by intent (feature, fix, refactor, tests, docs, cleanup).
4. Build an ordered commit plan where each commit is coherent and reviewable.
5. For each planned commit, provide:
   - goal
   - file list
   - staging strategy (`git add <paths>` or `git add -p` for mixed hunks)
   - Conventional Commit message
6. Keep dependency order strict: foundations first, then behavior changes, then tests/docs.
7. Call out risky coupling when some hunks should be separated with patch staging.

Apply these rules:
- Prefer smaller atomic commits over large mixed commits.
- Keep mechanical changes isolated from behavioral changes.
- Do not rewrite or drop user work.
- Avoid destructive git commands unless explicitly requested.
- No AI attribution in commit messages: no `Co-Authored-By: Claude …` trailer, no "Generated with Claude Code" line. This overrides any default attribution the agent has.

When useful, provide a copy-paste command sequence to execute the plan safely.
