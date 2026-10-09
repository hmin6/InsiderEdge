# InsiderEdge Agent Instructions

This repository is a 48-hour financial-research hackathon project. These instructions apply to every coding-agent session and every human implementation branch.

## Mission

InsiderEdge turns public SEC insider purchase transactions into a statistically validated, machine-learning-assisted **research-priority queue** for identifying potentially important market dislocations. It is not an automated trading system, not personalized investment advice, and not a claim that insider buying causes future returns.

## Read before editing

Before modifying code, read these files in this order:

1. `AGENTS.md`
2. `docs/DECISIONS.md`
3. `docs/PRD.md`
4. `docs/ARCHITECTURE.md`
5. `docs/DATA_SOURCES.md`
6. `docs/DATA_SCHEMA.md`
7. `docs/MODEL_SPEC.md`
8. `docs/API_CONTRACT.md`
9. the assigned GitHub issue
10. the exact issue-specific implementation prompt from the master plan

`docs/API_CONTRACT.md`, `docs/DATA_SCHEMA.md`, and `docs/MODEL_SPEC.md` are hard implementation contracts. If documentation conflicts with code or an issue prompt, stop and report the conflict rather than silently choosing a new design.

## Git / GitHub workflow

The default workflow is **one shared main repository with one branch per issue**.

Before editing:

- confirm the GitHub issue number and human owner;
- sync the latest `main`;
- create/check out the documented issue branch;
- confirm you are **not** on `main`.

Branch format:

```text
<area>/<issue-number>-<short-description>
```

Examples:

```text
data/2-sec-form4-ingestion
quant/12-event-study
ml/16-model-training
frontend/20-radar
```

One issue maps to one human owner, one issue branch, one active coding agent, and one pull request. Do not mix unrelated issue work into a branch or PR.

The intended integration path is:

```text
GitHub issue
  -> issue branch
  -> coding agent + human review
  -> tests/build
  -> push branch
  -> pull request into main
  -> PR review
  -> merge into main
  -> linked issue closes
```

The PR description should include the matching closing line, for example:

```text
Closes #20
```

Finishing code does not close the issue. Opening a PR does not close the issue. A linked issue closes automatically only after the PR is merged into the default branch with a supported closing keyword such as `Closes #N`, `Fixes #N`, or `Resolves #N`.

Agents must not merge to `main` or close GitHub issues unless the human owner explicitly asks them to perform that action.

## Project rules

1. Work only on the assigned GitHub issue.
2. Do not expand project scope.
3. Do not redesign unrelated parts of the repository.
4. Do not change `API_CONTRACT.md`, `DATA_SCHEMA.md`, or `MODEL_SPEC.md` unless the issue explicitly requires it.
5. If documentation conflicts with existing code, stop and report the conflict.
6. Never commit, print, or hard-code API keys, database passwords, or other secrets.
7. Use environment variables for credentials.
8. Use parameterized ORM/query APIs; never interpolate user-controlled values into SQL.
9. Preserve temporal ordering in all financial calculations.
10. `filing_date` / public availability is the information boundary for insider-event prediction.
11. With P0 daily data, market features stop at the last completed trading day strictly before `filing_date`.
12. Never use future information in predictive features.
13. With daily market data, event day `t=0` is the first trading day after `filing_date`.
14. Preserve raw SEC transactions separately from the one-`ticker` + `public_event_day` research-event table used for inference/ML.
15. Enforce the 30-trading-day outcome-window split guard documented in `MODEL_SPEC.md`.
16. Comparable historical events may contribute CAR30 evidence only if the entire CAR30 outcome was complete before the current event information date.
17. Do not use A, C, S, D, or IES composite scores as ML input features.
18. Gemini must never calculate or alter the InsiderEdge Score or ML prediction.
19. Preserve the locked team structure: Persons 1–2 backend/data/quant/ML; Persons 3–4 frontend/product.
20. Prefer simple, readable implementations appropriate for a 48-hour hackathon.
21. Add relevant tests.
22. Run relevant tests/build commands before declaring an issue complete.
23. Do not add major dependencies without explaining why.
24. Preserve existing working behavior.
25. Do not create fake model results, fake company results, or placeholder metrics that could be mistaken for measured output.
26. Work only on the assigned issue branch in the shared repository; never implement directly on `main`.
27. Keep one issue per branch and one issue per PR.
28. Do not merge or close the issue yourself unless the human owner explicitly requests it.
29. At completion, remind the human reviewer to include `Closes #<issue-number>` in the PR description.

## Frontend product rules

- React + TypeScript + Vite are locked.
- Recharts is the single chart library.
- Use a professional quantitative/research-dashboard visual language, not a casino/trading-game aesthetic.
- Motion should be subtle and functional: generally 150–300 ms.
- Prefer CSS transitions/animations and existing Recharts behavior before adding a new animation dependency.
- Respect `prefers-reduced-motion` and visible keyboard focus.
- High InsiderEdge Score means **research priority**, never “Buy,” “Sell,” or “Strong Buy.”
- Frontend never calls Gemini or ElevenLabs directly.

## Completion report

When finished, report:

1. files changed;
2. implementation summary;
3. tests/build commands run;
4. test/build results;
5. assumptions made;
6. unresolved issues or risks;
7. anything the human reviewer should manually verify;
8. recommended PR target (`main`) and the exact closing line, e.g. `Closes #20`.
