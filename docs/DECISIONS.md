# InsiderEdge Locked Decisions

This file records decisions that are considered locked for the hackathon unless real data exposes a concrete blocker. Do not silently substitute a different design.

## Product and scope

| Area | Locked decision | Notes |
|---|---|---|
| Product | Research-prioritization platform | Not automated trading or personalized advice. |
| Core question | Which newly public insider events deserve deeper analyst attention? | Evidence and uncertainty must remain visible. |
| Primary event | SEC Form 4 purchase transactions | P0 filter is non-derivative acquisitions with transaction code `P`; code P may be open-market **or private**. |
| Insider-event range | 2020 to current | Main research/ML event range. |
| Price range | 2019 to current | Needed for pre-event history for early-2020 events. |
| Universe | S&P 100 | Freeze at hackathon start; historical analysis is not a point-in-time index reconstruction and may have survivorship/selection bias. |
| Benchmark | SPY | Primary market-model benchmark. |
| Sector context | Sector ETFs | `XLK`, `XLF`, `XLV`, `XLE`, `XLI`, `XLY`, `XLP`, `XLU`, `XLB`, `XLRE`, `XLC`. |
| Fundamentals | SEC CompanyFacts, P1 | Cut before it blocks P0. |

## Information-time decisions

- Keep `transaction_date` and `filing_date` separate.
- `filing_date` / public availability is the P0 historical information boundary.
- With daily data, predictive market features use only the last fully completed trading day **strictly before** `filing_date`.
- `public_event_day` is the first trading day after `filing_date`.
- Recent EDGAR data may retain `accepted_at` for provenance, but P0 does not require intraday reconstruction.
- One inference/ML unit is one `ticker + public_event_day` research event; raw transactions remain separately stored.

## Technical stack

| Layer | Locked decision |
|---|---|
| Backend | Python + FastAPI + Pydantic |
| Database | Tiger Data / PostgreSQL |
| Statistics | NumPy, SciPy, statsmodels |
| ML | scikit-learn + XGBoost |
| Frontend | React + TypeScript + Vite |
| Charts | Recharts only |
| Market ingestion | yfinance, persisted in the database |
| AI | Gemini explanation only |
| Voice | ElevenLabs, P1 |
| Deployment default | Vercel frontend + Render backend + Tiger Cloud database |

## Quant / ML decisions

- Use a Logistic Regression baseline and XGBoost candidate; do not assume XGBoost wins.
- Use chronological validation, not random 80/20 as the primary evaluation.
- Preferred split is train 2020–2024, validation 2025, test 2026; if too sparse, use an approximately 70/15/15 chronological split.
- Enforce the 30-trading-day outcome-window split guard.
- A/C/S/D/IES composite scores are excluded from the ML feature matrix.
- CAR windows are exactly 5, 30, and 90 trading sessions beginning at event day `t=0`.
- The primary research horizon is CAR30.
- InsiderEdge Score weights are a transparent hackathon heuristic, not theoretically optimized.

## Product experience and motion

The finished application should feel like a sleek institutional research product: data-dense, calm, and demo-readable.

- Dark navy/charcoal navigation or shell with a light research workspace.
- Blue as the main interaction color; restrained green/red only when the underlying metric truly has positive/negative semantics.
- Moderate corner radii, subtle shadows, high-contrast readable typography.
- Subtle 150–300 ms transitions for hover/focus, row selection, section reveal, score visualization, and loading-state changes.
- Recharts may use a smooth initial line reveal and subtle insider-event marker emphasis.
- Score count-up/ring/component-bar animation is allowed if practical, but values must remain exactly backend-provided.
- Prefer content-shaped skeleton loading over page-level spinners.
- Respect `prefers-reduced-motion`; avoid constant or pulsing animation.
- Prefer CSS transitions/animations and existing Recharts behavior. Do not add Framer Motion or another major animation/UI dependency without a concrete need and human approval.

## Originality / differentiation boundary

Insider-trading tracking is an established category. InsiderEdge must **not** claim that Form 4 tracking, transaction filtering, scoring, AI explanation, or backtesting alone is novel.

The defensible differentiation is the integrated workflow:

```text
public Form 4 event
-> public-information-time boundary
-> company-level research-event aggregation
-> anomaly detection
-> activity/cluster context
-> market dislocation
-> comparable-event CAR analysis
-> bootstrap uncertainty
-> randomized-timing null
-> leakage-aware ML
-> transparent research-priority score
-> Gemini explanation of already-computed evidence
```

Pitch the product as a research-prioritization workflow that starts where a basic Form 4 tracker stops.

## Team / GitHub workflow

- One shared main repository is the default.
- One GitHub issue -> one human owner -> one issue branch -> one active coding agent -> one pull request.
- Never implement directly on `main`.
- PRs target `main` and should include `Closes #N`.
- Human review and merge decisions are required.
- The issue closes after the linked PR is merged into the default branch, not when coding finishes.
