---
name: mr-review
description: Review a GitHub pull request of the HCI repo (Vlor999/HCI) against the project rules, and report findings ranked by severity. Use when the user explicitly requests a review of a pull request (by number or the current branch).
disable-model-invocation: false
---

# Pull Request Review

Reviews a GitHub pull request and produces findings prioritized by importance and relevance to the code changes.

**Read-only mode.** When the review is delegated (a sub-agent reviewing for an orchestrator) or the user asks for read-only: do not write the review file, do not spawn sub-agents (do one careful pass, and validate each finding yourself against the code), do not commit, do not post on GitHub, do not change the infrastructure. Return the review table in the final report instead of Step 5.

---

## Workflow

1. **Preflight** - Ensure that the repository is in a clean state, target pull request is correctly identified and local branch is up to date.
2. **Rule Gathering** - Collect all rules applicable to this project from design, architecture and coding standards.
3. **Code Review** - Spawn multiple agents to review the code in concert and consolidate result in a single comprehensive document.
4. **Technical Validation** -- Perform necessary technical validation by a separate agent.
5. **Feedback** - Generate a markdown file with prioritized review comments and share it with the user for review and action.

---

## Step 1 — Preflight

- Identify the pull request: `gh pr view <number> -R Vlor999/HCI` gives its source and target branches and its body; `gh pr diff <number>` gives the diff. Without a number, assume the source branch is the current branch and the target is `main`, and confirm with the user (AskUserQuestion).
- Run a git fetch command to make sure the local repository is up to date with the remote branches. NEVER overwrite an existing review file without user confirmation.
- Check the working tree. If modified or staged files exist, determine whether they affect the PR review. If they do not affect the review, continue without modifying them. If they affect the reviewed changes or prevent reliable comparison, ask the user to resolve the state before proceeding.

If fetch fails, or if local changes affect the review, prompt the user to resolve these issues before proceeding with the review.

---

## Step 2 — Rule Gathering

- Look at the codebase for any design, architecture or coding standards that are applicable to this project, this includes the root `CLAUDE.md` (product constraints), `.agents/rules/*.instructions.md` and `README.md`.
If none are found, prompt the user to provide any relevant rules or guidelines that should be considered during the code review. Especially considering the following aspects :
- Software Architecture
- Coding Standards (ex: SOLID, pure functional etc...)

Also analyse the maturity of the project and Ask the user to confirm if you are making correct assumptions about the level of requirement applicable to the repository.

---

## Step 3 — Code Review

- Spawn 3 sub-agents (`model: "sonnet"`) simultaneously to review the code in parallel, they must review the whole of changes in the pull request, and provide detailed feedback on potential issues, improvements, and adherence to project rules. The goal of spawning several agent to do the same task is to select only relevant candidates for the final consolidated review.
    - Sub-agents should review the code that was changed and its dependencies
    - A finding is blocking only when the PR introduces or activates the issue. A pre-existing issue should be reported as contextual information, but must not be classified as a blocking finding unless the PR changes its reachability, severity, or impact.
    - Be extra mindful of afferent and efferent dependencies in the code. Make sure to consider how changes in the codebase can affect other parts

- Consolidate the feedback from all sub-agents into a single comprehensive review document. The rules to consolidate are as follows:
    - If 2/3 agents picked up on the issue, it will remain
    - If only 1/3 agents picked up on the issue and it is not minor (level 🔴, 🟠), spawn a new agent (`model: "opus"`) whose prompt it is to specifically debunk the issue and determine its validity. if this agent comes back with confirmation, the issue will remain; otherwise, it will be discarded.
    - If only 1/3 agents picked up on the issue and it is minor (level 🟡), it can be discarded without spawning a new agent.


The review table should be as follows:

| Criticity | Problem Description | Location | Condition | Impact | Changes Required | PR Comment Branding |
|-----------|---------------------|----------|-----------|--------|------------------|----------------------|
| 🔴, 🟠, 🟡 | What is technically wrong. | File path and relevant symbol, function, class, or configuration entry. | The condition(s) under which the issue occurs. | The concrete effect of the issue. | Nature of the required change, without code. | `!!!` Cross-cutting impact · `!` Blocking · `#` Comment/knowledge sharing · `?` Question/clarification · `*` Nice to have · `**` Super nice to have |


---

## Step 4 — Technical Validation

Spawn a sub-agent (`model: "sonnet"`) that will verify that each issue identified in the review table is technically valid and reproducible.

- Verify each issue against the codebase and its dependencies.
- Confirm that the issue is introduced or activated by the PR.
- Reject findings that cannot be reproduced or supported by concrete evidence.
- Adjust the criticity if the actual impact differs from the initial assessment.
- Update the review table with the validated findings only.

A finding must not be retained based only on agent consensus; it must be supported by evidence from the codebase.

---

## Step 5 — Feedback

Generate a markdown file at the root, this file should be named (`<source_branch>_TO_<target_branch>_review.md`), with branch names in lowercase and `/` replaced by `-`, at the root of the repo. The file is gitignored (`*_review.md`). Do not commit it.
- The content of the markdown file should include the consolidated review from Step 3.
- Ensure that all feedback, including criticity, problem description, changes required, and PR comment branding, is properly formatted in the markdown file.

Do not add qualitative feedback in the document, it should be strictly factual and based on the review table from Step 4.

the document should follow this template:

```markdown
# PR Review

Source: feature/foo
Target: main
Reviewed commit: abc123
Merge base: def456

## Findings

| Criticity | Problem Description | Location | Condition | Impact | Changes Required | PR Comment Branding |
|-----------|---------------------|----------|-----------|--------|------------------|---------------------|
```

Use ASD-STE100 Simplified Technical English for all descriptions and explanations in the review document.
Do not use `--` in prose.

