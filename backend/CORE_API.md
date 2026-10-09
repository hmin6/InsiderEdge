# Core FastAPI read endpoints — Issue #6

The four read endpoints follow `docs/API_CONTRACT.md` without frontend or
authoritative-contract changes:

| Endpoint | Source / behavior |
| --- | --- |
| `GET /api/radar` | Latest persisted research event per frozen-universe ticker, with its matching precomputed signal when available. |
| `GET /api/companies/{ticker}` | Stored company metadata or frozen-universe fallback, latest event date and that event's stored signal if present. |
| `GET /api/companies/{ticker}/prices` | Persisted Issue #4 prices, ascending date. |
| `GET /api/companies/{ticker}/insiders` | Stored Issue #2 transactions and Issue #5 research events, in chronological order. |

`GET /health` remains an independent process health check. No request downloads
SEC/yfinance data, rebuilds events, writes business data, or runs quant/ML/scoring.

## Run and configure

From `backend/`:

```powershell
..\.venv\Scripts\python -m uvicorn app.main:app --env-file ..\.env --reload
```

The verified Uvicorn `--env-file` option loads the ignored repository-root `.env`.
The application itself reads process environment and does not load a file.
Production should supply environment variables through its hosting configuration.
`DATABASE_URL` uses the existing PostgreSQL/psycopg session layer. Initialize the
schema and apply the documented Issue #3/#5 migrations before serving existing
databases. No dependency or schema change is introduced by Issue #6.

`CORS_ORIGINS` is a comma-separated list of explicit HTTP(S) frontend origins.
When unset, it defaults to `http://localhost:5173,http://127.0.0.1:5173`.
An explicitly empty value disables cross-origin allowances. Set the deployed
frontend's exact origin in production. Wildcards, credentials in origins and
paths are rejected; GET/POST and Accept/Content-Type are allowed, without
credentialed CORS (POST supports the Issue #8 AI endpoints).
`.env.example` contains only safe localhost examples. Restart after configuration
changes, including changes to database credentials or allowed origins.

Database initialization is lazy, preserving `/health` without database settings.
An application-owned pool is reused and closed on shutdown. Routes call read
services using request-scoped sessions and parameterized ORM queries. Radar uses
one joined/window query rather than one query per company. Session completion
does not imply business writes; these endpoints execute reads only.

## Mapping and empty/error behavior

Ticker validation uses the frozen Issue #3 universe: trim/uppercase, explicit
BRK-B/BRK B -> BRK.B aliases, and distinct GOOG/GOOGL records. Invalid or unknown
tickers, including out-of-universe database records, receive HTTP 404
`{"detail":"Unknown ticker"}`. No CIK-only share-class guess is made.

Known companies without database company rows use real frozen metadata, with
industry NULL. Known companies without prices/insiders/events receive HTTP 200
and empty arrays. Companies without events have NULL latest date/signal. An empty
event dataset yields `{"items":[]}` from Radar. Database/service availability or
invalid stored-response data yields a sanitized HTTP 503
`{"detail":"Research data unavailable"}`; raw exceptions/URLs are not returned.

Radar shows only the latest stored event per ticker. Scores are forwarded from
its matching stored signal, including genuine zero values. `model_probability`
maps directly to `ml_outperformance_probability`; it is not multiplied by 100.
If that event has no stored signal, score fields are NULL, status is
`insufficient_data`, and unavailable components are A/C/M/S/D. This is an explicit
availability state, not a calculated score or mock result. There is currently no
stored textual `insider_signal_summary`, so it is NULL. Sorting is descending
IES, with NULL last and ticker as a deterministic tie-breaker.

The company response's latest signal is NULL when its latest event is unscored;
an older event's scores are not attached to the newer event. Signal joins require
matching event ID, ticker and event date. Stored statuses/components otherwise
remain unchanged, leaving later signal integration replaceable.

Pydantic models preserve every documented field and nullable value, and validate
source/status/role literals and score/probability ranges. Decimal database values
are serialized as JSON numbers, matching the contract; database precision is
unchanged. Dates use ISO dates; available acceptance timestamps require timezone
information. Extra database provenance/internal metadata is not added to public
response shapes.

Transactions keep their distinct execution and filing dates. Research events
keep their persisted information date and public event day. Unknown buyer count
stays NULL. Raw amendments remain visible with their stored flags; the read layer
does not turn them into events or reinterpret Issue #2's qualification flag.
Use the existing research-event representation for Issue #5 inclusion, rather
than counting raw amendment flags as additional purchases. No aggregation occurs.
Retained/stale events follow the existing Issue #5 reconciliation policy; review
that dataset before treating the API as a corrected historical snapshot.

## Frontend compatibility follow-up (Person 3)

Backend implementation follows the authoritative contract, as explicitly approved.
No frontend file is changed. Current `frontend/src/types/api.ts` has stale types:

- Price/volume fields need `number | null` instead of `number`.
- Transaction document type, owner name and role need `string | null`.
- `aff10b5one` needs `boolean | null`.
- Accession and acquired/disposed fields are required strings, not nullable.
- Source type is the `bulk | edgar` literal union rather than unrestricted string.
- `research_events` needs the documented `ResearchEventSummary[]`, including
  nullable `unique_buyer_count`, rather than `any[]`.

Person 3 should align those interfaces and check null rendering before replacing
mocks. Configure its existing API base URL and disable development mocks when
performing integration validation. This issue does not add the later statistics,
prediction, explanation or audio endpoints.

## Verification

```powershell
..\.venv\Scripts\python -m pytest -q tests/test_core_api.py
..\.venv\Scripts\python -m pytest -q
```

Tests use synthetic SQLite records, mocked provider access and explicit checks
against authoritative TypeScript declarations. They cover empty collections,
normalization, nullable values, timestamps/literals, precomputed and missing
signals, ordering, CORS, sanitized errors, pool lifecycle and Radar query count.

A read-only Tiger smoke check on October 9, 2026 returned HTTP 200 for health and
all four endpoints using the existing CRM sample: one Radar item, eight prices,
one raw transaction and one research event. Separate execution/filing dates and
the September 21 information boundary were preserved. Unknown ticker returned
404. No ingestion or database data changes were performed for this check.
