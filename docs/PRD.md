# InsiderEdge Product Requirements Document

## Product definition

InsiderEdge is a quantitative research platform for finding potentially important insider-purchase signals and market dislocations. It transforms public SEC filings into a statistically prioritized research queue.

It does **not** automate trading, replace an analyst, or provide personalized investment advice.

### Core question

> Which insider events look unusual and potentially meaningful enough that an analyst should investigate them further?

## Problem

Raw Form 4 data is abundant, but a basic transaction feed does not answer whether a newly public insider event is unusual, whether the company is dislocated versus its market/sector context, how comparable historical events performed, how uncertain that evidence is, or whether a leakage-aware model sees elevated benchmark-outperformance probability.

## Product thesis

InsiderEdge starts where a basic Form 4 tracker stops. It combines:

1. qualifying SEC Form 4 purchase transactions;
2. market and sector context;
3. covariance-aware anomaly detection;
4. insider activity / cluster change;
5. event-study CAR5/CAR30/CAR90;
6. bootstrap confidence intervals;
7. randomized-timing null testing;
8. leakage-aware ML with chronological validation;
9. a transparent 0–100 InsiderEdge research-priority score;
10. Gemini explanation of the already-computed evidence;
11. optional ElevenLabs analyst audio brief.

## Target user

A technically oriented analyst, researcher, or judge who wants to quickly identify insider events that deserve deeper investigation and then inspect the evidence behind the ranking.

## Primary user flow

```text
Market Dislocation Radar
-> select a ranked company
-> Company Research Page
-> inspect qualifying code-P insider purchase events
-> inspect anomaly/activity and stock-vs-sector dislocation
-> inspect event-study CAR evidence
-> inspect comparable-event sample size
-> inspect bootstrap CI and randomized-timing p-value
-> inspect ML probability and held-out metrics
-> inspect InsiderEdge Score and components
-> optionally request Gemini explanation
-> optionally play ElevenLabs brief if stable
```

## P0 product requirements

### Data and backend

- SEC historical insider ingestion plus recent EDGAR gap fill.
- Frozen S&P 100 universe and ticker/CIK mapping.
- Historical daily stock/SPY/sector-ETF price ingestion persisted to Tiger Data/PostgreSQL.
- Separate `insider_transactions` and `research_events` representations.
- FastAPI read endpoints for Radar, company, prices, insiders, statistics, and prediction.
- Gemini backend endpoint for explanation.

### Quant / ML

- Pre-event market and insider features with no future leakage.
- Mahalanobis anomaly score.
- Insider activity / cluster score.
- Market-model event study with CAR5/CAR30/CAR90.
- Comparable-event selection with outcome-availability guard.
- Bootstrap 95% confidence interval.
- Randomized-timing null p-value.
- Market-dislocation score.
- Logistic Regression baseline and XGBoost candidate.
- Chronological validation and 30-session outcome-window split guard.
- Final 0–100 InsiderEdge Score.

### Frontend

- React/TypeScript/Vite application.
- `/` Market Dislocation Radar.
- `/company/:ticker` Company Research Page.
- Recharts historical price chart with insider-event markers.
- Quant/statistical/ML panels.
- Live FastAPI integration.
- Shared product shell and professional visual system.
- Sleek, restrained motion/microinteractions.
- Score visualization.
- Loading/error/empty states.
- Gemini explanation UX.
- Frontend smoke tests.

## P1 requirements

- SEC CompanyFacts fundamentals.
- ElevenLabs analyst audio brief.

P1 work must be cut before it threatens the P0 demo.

## Stretch / cut-first work

Cut in this order when time is going badly:

1. Solana;
2. Snowflake;
3. extensive fundamentals;
4. secondary model work;
5. FDR UI;
6. advanced Bayesian/change-point work;
7. nonessential animation flourishes;
8. fancy responsiveness;
9. secondary charts.

Never remove before emergency fallback: SEC data, market data, anomaly, event study/CAR, one uncertainty method, one ML model, final score, Radar, company page, Tiger Data, and Gemini.

## Research framing

A high InsiderEdge Score means **higher research priority**, not a buy recommendation, confidence guarantee, or causal claim.

The application must keep raw/statistical evidence visible even when a 0–100 score exists.

Gemini explains structured evidence only; it never generates or modifies the signal.

## Competitive differentiation

Insider trading trackers already exist. InsiderEdge should not claim to be the first Form 4 tracker or the only product with ranking, AI, backtesting, or statistical analysis.

The differentiated product story is the integrated, transparent, public-information-time-aware research workflow from filing -> event aggregation -> anomaly/activity -> dislocation -> historical CAR evidence -> uncertainty validation -> ML -> research-priority ranking -> explanation.

## UX requirements

- Professional quantitative/research dashboard.
- Dark navy/charcoal application shell with a light research workspace is the default direction.
- Clear visual hierarchy; Radar first, then Company Research Page.
- InsiderEdge Score is prominent but does not hide the evidence.
- No casino/trading-game aesthetics, bright “BUY NOW” presentation, or exaggerated causal visuals.
- Motion generally 150–300 ms and used to clarify state changes.
- Prefer skeleton loading and subtle chart/marker/score transitions.
- Respect reduced-motion preferences and keyboard focus.

## Definition of done

A public demo can move from a real Radar ranking to one real company, display persisted insider and market data, quantitative/statistical evidence, a trained model prediction, the final InsiderEdge Score, and a Gemini explanation without relying on a fresh live market-data download. The primary flow remains usable when Gemini or ElevenLabs fails.
