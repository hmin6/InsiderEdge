# InsiderEdge GitHub Workflow

This is the team’s locked workflow for the 48-hour hackathon.

## Repository model

Use **one shared main repository with a separate branch for each issue**. Add all four teammates as collaborators.

Forks are compatible with GitHub, but they are not the default for this team because a shared-repository branch workflow reduces synchronization overhead.

## Project board

```text
BACKLOG -> READY -> IN PROGRESS -> IN REVIEW -> DONE
```

## Labels

Areas:

```text
data
backend
database
quant
ml
frontend-core
frontend-product
ai
testing
integration
```

Priorities:

```text
P0
P1
P2
```

Context:

```text
bug
blocked
```

## Issue numbering

Create planned issues in the same order as the master plan so GitHub assigns the expected issue numbers.

It is acceptable to create the issues **with titles only first** to preserve numbering. Before implementation starts, the owner may add the clean human-readable issue description/acceptance criteria.

The coding agent receives:

```text
Global Coding-Agent Prompt
+
exact issue-specific implementation prompt from the master plan
```

The GitHub issue description and the coding-agent implementation prompt serve different purposes; they do not need to be identical text.

## Branch naming

```text
<area>/<issue-number>-<short-description>
```

Examples:

```text
backend/1-foundation
data/2-sec-form4-ingestion
data/4-market-prices
quant/12-event-study
ml/16-model-training
frontend/20-radar
```

Each issue branch is created from the latest `main`.

Never implement an issue directly on `main`.

Never mix unrelated issues into the same branch.

## Issue-to-merge flow

1. Create/confirm the numbered GitHub issue.
2. Assign one human owner.
3. Sync latest `main`.
4. Create/check out the documented issue branch.
5. Start the coding-agent session with the Global Prompt + exact issue prompt.
6. Human owner reviews generated changes.
7. Run required tests/build and fix obvious mistakes.
8. Commit and push the issue branch to the shared repository.
9. Open a pull request from the issue branch **into `main`**.
10. Put the closing reference in the PR description, e.g. `Closes #20`.
11. Review the PR and confirm tests/acceptance criteria.
12. Merge the PR into `main`.
13. GitHub automatically closes the linked issue.
14. Move the project card to DONE.
15. Delete the merged branch if desired/recommended.

### Important closure rule

Coding completion does **not** close the issue.

Opening the PR does **not** close the issue.

The issue closes automatically only when a PR targeting the default branch is merged and the PR contains a supported keyword such as:

```text
Closes #20
Fixes #20
Resolves #20
```

## Operating rule

```text
one issue -> one human owner -> one issue branch -> one active coding agent -> one PR
```

A second agent may review the diff but should not concurrently rewrite the same feature. Human teammates own review and merge decisions.

## Before starting an issue

```bash
git checkout main
git pull origin main
git checkout -b <documented-issue-branch>
```

If the branch already exists remotely:

```bash
git fetch origin
git checkout <documented-issue-branch>
git pull origin <documented-issue-branch>
```

Confirm:

```bash
git status
git branch --show-current
```

The current branch must match the assigned issue and must not be `main`.

## Pull-request template

Use a concise PR description like:

```md
## Summary
- <what changed>
- <what changed>

## Tests
- `<command>` — pass/fail
- `<command>` — pass/fail

## Manual verification
- <anything the reviewer should check>

## Risks / assumptions
- <remaining risk or assumption>

Closes #<issue-number>
```

## Review expectations

Before merge, verify:

- issue scope only;
- required tests/build pass;
- no secrets committed;
- no unrelated files changed;
- documentation contracts are respected;
- temporal/leakage rules are respected for financial logic;
- API response types still match frontend/backend contract;
- UI still handles missing/insufficient data cleanly.
