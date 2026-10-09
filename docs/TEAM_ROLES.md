# InsiderEdge Team Roles

Roles define accountability, not hard walls. Preserve the locked structure: Persons 1–2 are the backend/data/quant/ML side; Persons 3–4 are the frontend/product side.

## Person 1 — Backend + Data Engineer

Ownership flow:

```text
SEC -> market data -> company mapping -> Tiger Data -> FastAPI -> AI-service backend
```

Primary responsibilities:

- FastAPI foundation and database persistence;
- Tiger Data/PostgreSQL integration;
- SEC bulk + recent EDGAR ingestion;
- S&P 100 universe / ticker-CIK mapping;
- market-data ingestion;
- merged raw-transaction + research-event dataset;
- core data APIs;
- optional CompanyFacts fundamentals;
- server-side Gemini/ElevenLabs plumbing.

Person 1 may help Person 2 with engineering/integration after the P0 data pipeline is stable, while Person 2 remains methodological owner of quant/ML decisions.

## Person 2 — Quant + ML Engineer

Ownership flow:

```text
research events -> features -> anomaly/activity -> event study -> inference -> ML -> final score
```

Primary responsibilities:

- leakage-safe event feature engineering;
- activity/cluster score;
- Mahalanobis anomaly score;
- event-study implementation and CAR5/CAR30/CAR90;
- comparable-event cohort logic;
- bootstrap and randomized-timing validation;
- market-dislocation score;
- ML dataset and chronological split/outcome guard;
- Logistic Regression/XGBoost training and selection;
- final InsiderEdge Score;
- quant/ML production signal integration support.

## Person 3 — Frontend Core Engineer

Ownership flow:

```text
frontend foundation -> Radar -> company research -> charts/panels -> live API
```

Primary responsibilities:

- React/TypeScript/Vite foundation;
- shared API types and typed client;
- Market Dislocation Radar business logic;
- Company Research Page business logic;
- Recharts price chart and insider-event markers;
- statistical/model panels;
- live FastAPI integration;
- frontend smoke tests;
- functional interaction states that expose Person 4's shared visual/motion components.

Person 3 owns functionality and data wiring; Person 4 owns the shared product/visual-motion system. Avoid rewriting each other's business logic.

## Person 4 — Frontend + Product Engineer

Ownership flow:

```text
application shell -> visual/motion system -> score/evidence UX -> AI/audio UX -> resilience -> demo polish
```

Primary responsibilities:

- application shell and navigation;
- visual design system;
- typography, spacing, cards, status badges;
- dark-nav/light-workspace product direction;
- motion/microinteraction system;
- skeleton/loading/error/empty states;
- InsiderEdge Score visualization;
- score count-up/ring/component-bar motion where practical;
- Gemini explanation UX;
- optional ElevenLabs UI;
- reduced-motion and keyboard-focus accessibility;
- final demo polish and final click path.

## Shared operating rule

```text
one issue -> one human owner -> one issue branch -> one active coding agent -> one PR
```

A second agent may review the diff but should not concurrently rewrite the same feature.
