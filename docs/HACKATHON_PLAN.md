# InsiderEdge 48-Hour Hackathon Plan

## Timing rule

Team coding start: **October 9, 2026 at 12:00 PM ET**.

Official deadline: **October 11, 2026 at 10:00 AM ET**.

The project should be submission-ready before the official deadline.

## Timeline

| Time | Target |
|---|---|
| Oct 9, 12 PM | Create repository, commit authoritative docs, project board, labels, milestones, issues, owners, initial branches. |
| Oct 9, 12–2 PM | Four parallel foundations: backend/database, quant fixtures, React/API mocks, product shell. |
| Oct 9, 2–4 PM | Lock data/event/API/model contracts, including comparable-event and temporal-split rules. |
| Oct 9, 4–8 PM | First real pipeline: SEC + prices; returns/anomaly/CAR; Radar/company mock; score/evidence UI. |
| Oct 9, 8 PM–12 AM | Integrate real database -> FastAPI -> quant result -> React. One real company must work end-to-end on `main`. |
| Oct 10 morning | Bootstrap, randomized-timing null, improved anomaly, activity score, evidence panels. |
| Oct 10 midday/afternoon | ML dataset, leakage audit, outcome-window guard, chronological split, Logistic, XGBoost, metrics. |
| Oct 10 afternoon | Final score + Radar ranking. |
| Oct 10 evening | Gemini, optional ElevenLabs, deployment, polish. Add only cheap hardening after the full MVP is stable. |
| Oct 10, 8–10 PM | Feature freeze. No new architecture, major model, provider, page, or post-MVP infrastructure. |
| Oct 11, 7 AM | Demo freeze; choose a stable real company and verify calculations. |
| Oct 11, 8 AM | README, screenshots, submission text, production verification complete. |
| Oct 11, 8:30–9:15 AM | Rehearse happy path, slow network, and external-service failure. |
| Oct 11, 9:30 AM | Hard code freeze; only catastrophic fixes. |
| Oct 11, 10 AM | Official deadline / submission-ready cutoff. |

## GitHub setup order before implementation

1. Create the shared repository and default `main` branch.
2. Commit `AGENTS.md` and all authoritative `docs/*.md` files to `main`.
3. Create project board/labels.
4. Create planned GitHub issues in numerical order; titles-only first is acceptable to preserve numbering.
5. Assign owners.
6. Create issue branches from latest `main`.
7. Only then start coding-agent implementation sessions.

## Cut order

If time is going badly, cut in this order:

1. Solana;
2. Snowflake;
3. extensive fundamentals;
4. secondary model work;
5. FDR UI;
6. advanced Bayesian/change-point work;
7. nonessential animation flourishes;
8. fancy responsiveness;
9. secondary charts.

Never remove before emergency fallback:

- SEC data;
- market data;
- anomaly;
- event study/CAR;
- one uncertainty method;
- one ML model;
- final score;
- Radar;
- company page;
- Tiger Data;
- Gemini.

Post-MVP hardening must never delay the original hackathon definition of done.
