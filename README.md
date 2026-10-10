# InsiderEdge

InsiderEdge turns public SEC insider transactions into a statistically validated, machine-learning-assisted research queue for identifying potentially important market dislocations.

**Higher research priority means a reason to investigate—not a buy/sell recommendation, investment advice, or evidence that insider purchases cause future returns.**

[Live application](https://insider-edge-omega.vercel.app) · [Backend](https://insideredge-api.onrender.com) · [Interactive API docs](https://insideredge-api.onrender.com/docs) · [Methodology](docs/MODEL_SPEC.md)

## Why InsiderEdge

A Form 4 feed shows what insiders reported. An analyst still needs to ask whether an event is unusual, how activity has changed, whether the stock is dislocated versus its sector, and how much historical evidence supports further research.

InsiderEdge brings those questions into one workflow:

```text
Public SEC purchase evidence → company research event
  → anomaly / activity / market context / historical statistical evidence
  → model outperformance probability → research-priority score
  → Gemini explanation → optional ElevenLabs analyst brief
```

Its differentiation is this integrated, inspectable workflow—not exclusive access to SEC data or a claim to be the first insider tracker. The Radar links to company research with insider provenance, adjustment-aware price charts, component diagnostics, CAR horizons, bootstrap intervals, randomization p-values, and model evidence. Missing results remain visibly unavailable.

### Current demo status

Issue #35 prepared real historical data, resolved the approved Decimal/Boolean integration bugs, and persisted 39 post-selection Signals, including 14 complete research-priority scores. AXP is the completeness-selected demo company; its local and production read endpoints, production chart, and direct refresh have passed verification. Final live Gemini explanation and ElevenLabs audio verification passed with exactly one authorized request to each provider. Held-out API metrics remain unavailable. See [the verified demo state and remaining checks](docs/DEMO_PLAN.md).

**Issue #35 owns historical-data preparation, populated-event validation, and final demo-ticker selection.** AXP is selected by evidence completeness; this README does not claim that every event is fully scored.

## Data and the information boundary

| Source | Use |
| --- | --- |
| SEC Insider Transactions Data Sets and recent EDGAR Form 4 XML | Historical transactions and recent filing gap fill, with source provenance |
| SEC CompanyFacts | Optional, point-in-time fundamentals selected by eligible filing date |
| Yahoo Finance through yfinance | Separate daily-price ingestion for stocks, SPY, and sector ETFs |
| Tiger Data / PostgreSQL | Persisted transactions, research events, prices, fundamentals, and current signals |

The frozen S&P 100 universe contains **101 securities**. Ticker identifies the security; shared issuer CIKs such as GOOG/GOOGL are supported without silently choosing a share class. This current-universe sample is not a historical index reconstruction and can introduce survivorship/selection bias.

Qualifying P0 event sources are **Form 4, non-derivative / Table I, transaction code P, acquired/disposed A**. Code P covers **open-market or private purchases**; it does not establish exchange-only execution. Amendments remain in raw provenance and are excluded from independent research-event construction pending reconciliation.

- `transaction_date` and `filing_date` remain separate. Filing/public availability establishes the information boundary.
- `public_event_day` (`t=0`) is the first trading session strictly after filing date.
- One research event represents one `ticker + public_event_day`; multiple filings can collapse into that event. Its `information_date` is the **latest contributing filing date**.
- Raw SEC transactions remain separate from research events; one ML row represents one `research_event_id`.
- Predictive market features stop at the last completed session **strictly before `information_date`**. Eligible fundamentals must have been filed by that boundary.
- Stocks, SPY, and sector ETFs use persisted adjusted close as `analysis_price`. Missing adjusted close remains missing; raw close is not substituted.

Research events cover 2020 onward. Price preparation starts in 2019 to support early-2020 estimation history, subject to actual provider coverage. **Production quantitative reads use persisted data; they do not download SEC or yfinance data during the demo.**

See [data sources](docs/DATA_SOURCES.md), [schema](docs/DATA_SCHEMA.md), and the [SEC](backend/SEC_INGESTION.md), [market](backend/MARKET_INGESTION.md), [event dataset](backend/EVENT_DATASET.md), and [fundamentals](backend/FUNDAMENTALS.md) guides.

## Quantitative and statistical evidence

| Component | Implemented policy |
| --- | --- |
| Anomaly | Regularized Mahalanobis distance with chi-square score mapping; prior same-sector events, then prior frozen-universe events; minimum 30 usable reference events |
| Activity | Recent 30-calendar-day research-event rate versus the preceding 365 days, excluding the recent window; buyer-count and rate-ratio percentiles use prior company history, then sector history |
| Buyer identity | Transaction-associated canonical evidence only. Names or joint-filer groups alone do not establish buyers; incomplete identity coverage stays unknown, never synthetic zero |
| Market dislocation | Pre-event 90-session sector underperformance and drawdown magnitude, mapped to frozen-universe percentiles with 60% / 40% weights; insufficient coverage leaves the score unavailable |
| Historical comparators | Same sector + broad role, falling back to same sector; minimum 10 eligible events. Comparator information and its entire CAR30 outcome must precede the focal information date |
| Bootstrap | 95% percentile interval for comparable-event mean CAR30; default 1,000 resamples, seed 13 |
| Randomized timing | Event-level pseudo dates for the same ticker/year, excluding actual insider-event dates; complete pseudo CAR30 outcomes must precede the focal boundary. Default 1,000 valid replicates, seed 13 |

Unavailable randomization leaves the combined statistical score unavailable; any valid bootstrap evidence remains visible. Missing data, insufficient references, or failure to establish the required valid replicates never become invented estimates. Historical associations and p-values do not establish causation or guaranteed returns.

### Event study

The market model estimates stock returns against **SPY**, using sessions **[-120, -21]** relative to `t=0`, with at least **60 valid paired estimation observations**. Abnormal return is observed return minus the fitted market-model return.

| Outcome | Exact trading-session window |
| --- | --- |
| CAR5 | Sum of abnormal returns over `0..4` |
| CAR30 | Sum over `0..29`; primary research horizon |
| CAR90 | Sum over `0..89` |

Current-event CAR is retrospective evidence, not a prediction-time feature. Incomplete horizons remain null until observable; current-event realized CAR is excluded from AI information-time evidence even when it can be displayed retrospectively.

## Machine learning

The target is whether the stock's compounded return over the same **30 sessions `t=0..29` exceeds SPY**. Ties are not outperformance.

- **Models:** Logistic Regression baseline and XGBoost candidate; XGBoost is not assumed to win.
- **Preferred chronological split:** train 2020–2024, validation 2025, test the feasible completed-outcome 2026 subset. An explicitly selected approximately 70/15/15 chronological alternative is supported; sparsity does not silently switch the split.
- **Preprocessing and selection:** learned preprocessing fits training data only. Validation selects the model/configuration; test data is reserved for frozen evaluation. The current default classification threshold is 0.50, with its provenance exposed when persisted.
- **Leakage guards:** recent unlabeled events are excluded from supervised evaluation; earlier-split outcomes touching the next split are purged. Future outcomes, raw identifiers, and A/C/S/D/IES composite scores are excluded from predictive inputs. Buyer features retain canonical-identity provenance checks.

**Final held-out metrics are intentionally not reported yet:** no durable frozen evaluation artifact is currently available. The prediction API leaves metrics null rather than substituting validation results or recomputing test performance from live data. Model probability is not a guarantee.

## InsiderEdge research-priority score

All components are on a 0–100 scale; `M` is the selected model probability multiplied by 100:

```text
IES = 0.25 × Anomaly
    + 0.15 × Activity
    + 0.30 × Model
    + 0.15 × Statistical Validation
    + 0.15 × Dislocation
```

These are transparent hackathon heuristic weights, not optimized investment weights. When **S alone** is unavailable because comparable-event history is insufficient, the backend divides the remaining weighted sum by `0.85` and marks the score `partial`. Missing A, C, M, or D leaves the final score unavailable (`insufficient_data`). Missing values are never treated as zero; genuine zero remains zero.

**Gemini and ElevenLabs contribute zero to scoring and model prediction.**

## Explanation and audio

Gemini receives structured, validated persisted backend evidence and returns five explanation sections: why flagged, supportive evidence, risk evidence, uncertainty, and limitations. It is instructed not to invent figures, create missing evidence, recalculate statistics/scores/probabilities, provide trading recommendations, or make causal claims. Application-side schema/content checks reject malformed or unsafe responses; quantitative endpoints remain usable if explanation fails.

The backend independently creates a deterministic analyst-brief transcript from the same evidence. ElevenLabs performs text-to-speech only. If audio is unavailable, the transcript remains available with `audio_unavailable` status. Human review remains necessary: validation does not prove every generated statement is factually grounded.

## Architecture and API

```text
SEC / CompanyFacts + yfinance → offline preparation → Tiger PostgreSQL
                                                    ↕
                                      Python quant / ML integration
                                                    ↕
React + TypeScript + Vite + Recharts ↔ FastAPI ↔ Gemini / ElevenLabs
               Vercel                  Render       explanation / voice
```

The backend is a modular monolith using Python, FastAPI, Pydantic, SQLAlchemy, and psycopg. NumPy, pandas, and SciPy support quantitative work; scikit-learn and XGBoost support ML. The frontend presents backend-calculated evidence and never receives provider or database credentials.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Process health; does not prove database readiness |
| GET | `/api/radar` | Latest-event research-priority queue |
| GET | `/api/companies/{ticker}` | Metadata and latest signal summary |
| GET | `/api/companies/{ticker}/prices` | Persisted chart history |
| GET | `/api/companies/{ticker}/insiders` | Raw transaction and research-event provenance |
| GET | `/api/companies/{ticker}/statistics` | Anomaly, activity, CAR, validation, and market evidence |
| GET | `/api/companies/{ticker}/prediction` | Selected model probability, threshold, and nullable held-out metrics |
| POST | `/api/companies/{ticker}/explain` | Validated Gemini explanation |
| POST | `/api/companies/{ticker}/brief` | Transcript and optional MP3 audio |

Signals must match the latest research event exactly; a newer unscored event never borrows an older signal. Unknown tickers return 404. Statistics/prediction return 404 when a known ticker has no research event, and honest null/status responses when an event exists but evidence is unavailable. Legacy richer evidence requires an explicit validated rebuild.

Response shapes are defined in [API_CONTRACT.md](docs/API_CONTRACT.md). See [CORE_API.md](backend/CORE_API.md), [RESEARCH_API.md](backend/RESEARCH_API.md), and [AI_SERVICES.md](backend/AI_SERVICES.md) for implementation and failure behavior.

## Run locally

Use Python **3.13**, PostgreSQL/Tiger access, and Node **22.13+ within Node 22**, or Node 24. The following commands use PowerShell from a local repository checkout.

### Backend

```powershell
# Repository root
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Configure the ignored **root `.env`** locally with your database connection, retaining provider-required TLS options. Never commit or share its contents. Process environment takes precedence; the application itself does not automatically discover `.env`.

For a **new empty database**, initialize the existing schema explicitly:

```powershell
cd backend
..\.venv\Scripts\python -c "from dotenv import load_dotenv; load_dotenv('../.env'); from scripts.init_db import main; main()"
```

Initialization creates missing tables without populating data or upgrading existing definitions. Existing databases require review of the documented guarded migrations; see [deployment/schema guidance](DEPLOYMENT.md#tiger-schema-and-persisted-data). Do not reset a production database.

Start the API from `backend/`:

```powershell
..\.venv\Scripts\python -m uvicorn app.main:app --env-file ..\.env --reload
```

Local API docs: `http://localhost:8000/docs`. Data ingestion and validated signal preparation are separate operations; starting the server does not manufacture research results. Follow the linked backend guides for those operations.

### Frontend

In a separate terminal:

```powershell
cd frontend
npm ci
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run dev
```

The frontend example sets `VITE_USE_MOCKS=false` to use real backend data. Without that setting, development mode defaults to clearly labeled mocks; statistical/model fetches are unavailable rather than invented. Production always disables development mocks.

An empty `VITE_API_BASE_URL` falls back to `http://localhost:8000` in development. For production builds it must be an explicit HTTPS backend **origin**, without `/api`, credentials, query, or fragment; the build rejects missing/invalid values. Configure it in the frontend environment and rebuild after changes.

### Environment variables

Templates: [root `.env.example`](.env.example) and [frontend `.env.example`](frontend/.env.example). Credentials belong on the backend only.

| Variable | Requirement / behavior |
| --- | --- |
| `DATABASE_URL` | Required for database-backed reads/preparation; not required by process-only `/health` |
| `SEC_USER_AGENT` | Required for SEC ingestion; descriptive project/contact identification, not needed for persisted reads |
| `CORS_ORIGINS` | Comma-separated explicit browser origins; defaults to local development origins; configure the actual frontend origin in production |
| `GEMINI_API_KEY` | Required only for live explanation |
| `GEMINI_MODEL` | Optional override; default `gemini-3.8-flash` |
| `GEMINI_TIMEOUT_SECONDS` | Optional; default 30, supported range 1–60 |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | Required only for live audio; otherwise transcript fallback remains available |
| `ELEVENLABS_MODEL` | Optional override; default `eleven_multilingual_v2` |
| `ELEVENLABS_TIMEOUT_SECONDS` | Optional; default 30, supported range 1–60 |
| `VITE_API_BASE_URL` | Public frontend build-time configuration; never put secrets in `VITE_` variables |
| `VITE_USE_MOCKS` | Local development only; set `false` for real backend reads |

### Validation

```powershell
# From backend/
..\.venv\Scripts\python -m pytest -q
# From frontend/
npm test
npm run build  # Requires the HTTPS VITE_API_BASE_URL described above
# From repository root
git diff --check
```

Normal automated tests use synthetic data/mocked providers; they do not require paid live Gemini or ElevenLabs calls. Live provider checks are separate, deliberate operations.

## Production

- **Frontend:** [insider-edge-omega.vercel.app](https://insider-edge-omega.vercel.app), Vercel root `frontend`, Vite build and SPA fallback.
- **Backend:** [insideredge-api.onrender.com](https://insideredge-api.onrender.com), Render root at the repository; build `pip install -r backend/requirements.txt`, start `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
- **Database:** Tiger Cloud PostgreSQL; credentials remain server-side. Explicit-origin CORS connects the frontend to the API. Startup performs no automatic ingestion, training, or destructive database initialization.

Hosting response times and availability are not guaranteed. See [DEPLOYMENT.md](DEPLOYMENT.md) for environment configuration, routing, and smoke checks.

## Repository and team

```text
backend/app/        API, persistence, services, quant, and ML
backend/scripts/    Explicit initialization, migrations, and ingestion commands
backend/tests/      Backend regression tests and synthetic fixtures
frontend/src/       React pages, evidence components, typed API client, tests
config/             Frozen universe and mapping documentation
docs/               Authoritative product, schema, API, and methodology contracts
DEPLOYMENT.md       Hosting and operational verification
render.yaml         Render service configuration
```

Ownership follows [TEAM_ROLES.md](docs/TEAM_ROLES.md):

| Role | Responsibility |
| --- | --- |
| Person 1 — Backend + Data Engineer | SEC/market ingestion, company mapping, Tiger persistence, FastAPI, optional fundamentals, AI-service backend |
| Person 2 — Quant + ML Engineer | Features, anomaly/activity, event studies, statistical validation, dislocation, ML, and final score methodology |
| Person 3 — Frontend Core Engineer | Typed API wiring, Radar/company functionality, charts, evidence panels, and frontend smoke tests |
| Person 4 — Frontend + Product Engineer | Shared visual/motion system, score/evidence UX, explanation/audio UX, accessibility, resilience, and demo polish |

## Foundations and limitations

The project connects probability/covariance and multivariate statistics, inference, bootstrap/randomization, and predictive validation from Math 340–343 with financial event-study methods. Event aggregation, exact horizons, cohort rules, support mappings, and score weights are InsiderEdge design choices—not claims of theoretically optimal methods. See [COURSEWORK_MAPPING.md](docs/COURSEWORK_MAPPING.md) for that distinction.

Public filings can be delayed or amended; reporting owners do not always identify the underlying buyers reliably. Sparse events, missing market coverage, or insufficient reference populations can prevent scores and statistics. Daily timing is a conservative public-information approximation, not intraday reconstruction. CompanyFacts duration values retain their actual periods and are not automatically quarterly or TTM.

The frozen current universe introduces selection/survivorship considerations. Anomaly calibration and historical comparator analysis depend on statistical assumptions and data quality. Research-priority scores are heuristics, not causal estimates or trading instructions. Future CAR is unavailable until realized, held-out metrics await a durable verified artifact, and external explanation/audio services may fail independently.

Final populated-event validation and demo selection remain **Issue #35** work.
