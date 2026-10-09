# InsiderEdge Architecture

## Architecture style

InsiderEdge is a **modular monolith** for the hackathon. Do not introduce microservices, Redis, queues, or other infrastructure unless a measured need justifies them and a human reviewer approves the scope change.

## High-level flow

```text
SEC Form 4 bulk + recent EDGAR XML      yfinance stocks / SPY / sector ETFs
                 \                         /
                  \                       /
                    Python ETL / normalization
                              |
                       Tiger Data / PostgreSQL
                       /          |          \
              Quant engine    FastAPI      ML engine
            SciPy/statsmodels    |       sklearn/XGBoost
                       \          |          /
                         FastAPI services
                         /      |       \
             React/TS/Recharts Gemini  ElevenLabs(P1)
```

## Repository layout

```text
InsiderEdge/
|-- README.md
|-- AGENTS.md
|-- .gitignore
|-- .env.example
|-- docker-compose.yml
|-- config/
|   `-- universe.csv
|-- docs/
|   |-- DECISIONS.md
|   |-- PRD.md
|   |-- ARCHITECTURE.md
|   |-- DATA_SOURCES.md
|   |-- DATA_SCHEMA.md
|   |-- MODEL_SPEC.md
|   |-- API_CONTRACT.md
|   |-- TEAM_ROLES.md
|   |-- GITHUB_WORKFLOW.md
|   |-- TEST_PLAN.md
|   |-- HACKATHON_PLAN.md
|   |-- DEMO_PLAN.md
|   `-- COURSEWORK_MAPPING.md
|-- backend/
|   |-- app/
|   |   |-- main.py
|   |   |-- api/
|   |   |-- db/
|   |   |-- services/
|   |   |-- quant/
|   |   |-- ml/
|   |   `-- schemas/
|   |-- scripts/
|   |-- tests/
|   `-- requirements.txt
`-- frontend/
    |-- src/
    |   |-- api/
    |   |-- components/
    |   |-- pages/
    |   |-- hooks/
    |   `-- types/
    `-- package.json
```

## Component responsibilities

### Data ingestion

- SEC bulk historical loader and recent EDGAR gap-fill loader normalize into a common insider transaction representation.
- S&P 100 mapping provides stable ticker/CIK/company/sector metadata.
- yfinance ingestion writes daily OHLCV and an adjustment-aware analysis price to the database.
- CompanyFacts is P1 and must preserve filed/public dates.

### Persistence

Tiger Data/PostgreSQL stores:

- `companies`
- `insider_transactions`
- `research_events`
- `prices`
- `fundamentals`
- `signals`

The live demo reads persisted data and must not depend on a fresh yfinance request.

### Quant engine

Lives under `backend/app/quant/` or equivalent service modules. It computes features, anomaly/activity, event study, bootstrap/randomization evidence, market dislocation, and final score. Do not place full quant logic in route handlers.

### ML engine

Lives under `backend/app/ml/` or equivalent service modules. It builds the approved raw pre-event feature matrix, enforces chronological splits/outcome guards, trains Logistic Regression/XGBoost, and emits probabilities and held-out metrics.

### FastAPI

FastAPI is the integration layer between persisted data/quant/ML outputs and the frontend. Route handlers remain thin and call service/repository layers.

### Frontend

React + TypeScript + Vite. Recharts is the single chart library. The frontend renders backend-provided values and **does not recalculate InsiderEdge Score**.

### Gemini / ElevenLabs

The browser never calls these providers directly. FastAPI sends structured quantitative output to provider services. API keys remain server-side.

Gemini explanation must not change any statistical result, model probability, or InsiderEdge Score.

## Security and operational rules

- Credentials are environment variables only.
- Never commit secrets.
- Use parameterized ORM/query APIs; never interpolate user-controlled values into raw SQL.
- Normalize/validate ticker input against the known universe before data access.
- Production CORS should allow the deployed frontend origin plus explicit development origins, not an unrestricted wildcard.
- Provider timeouts/failures degrade gracefully.

## Authoritative contracts

The following documents are hard contracts:

- `docs/API_CONTRACT.md`
- `docs/DATA_SCHEMA.md`
- `docs/MODEL_SPEC.md`

If implementation and contract disagree, report the mismatch before changing either side.

## Deployment default

```text
Vercel frontend
    -> Render FastAPI backend
        -> Tiger Data / Tiger Cloud PostgreSQL
```

Required deployment environment variables include `VITE_API_BASE_URL`, `DATABASE_URL`, `GEMINI_API_KEY`, and `ELEVENLABS_API_KEY` when the optional voice feature is enabled.
