# Production deployment — Issue #32

Vercel serves the Vite SPA, Render runs FastAPI, and Tiger PostgreSQL holds the
persisted research data. No hosting resources are created by these files.
No API/schema/model methodology changes or automatic ingestion are required.

## Render backend

Create a Python web service from the reviewed repository revision, or import the
root `render.yaml` Blueprint. For an existing service, enter missing secrets in
its Environment settings; `sync: false` only prompts during initial Blueprint
creation. Select the service plan/region in the dashboard before deployment.

| Setting | Value |
|---|---|
| Root directory | Repository root (leave blank), **not backend/** |
| Python | 3.13; root `.python-version` selects the latest 3.13 patch |
| Build | `pip install -r backend/requirements.txt` |
| Start | `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health check | `/health` |

The repository root must remain available because the frozen universe lives in
`config/universe.csv`. Production installs runtime requirements only, not pytest
or httpx from requirements-dev. No SEC, Yahoo, CompanyFacts, Gemini or ElevenLabs
request occurs at startup. `/health` returns `{"status":"ok"}` without opening
the database; it verifies process health, not database readiness. Check the read
endpoints separately after each deploy.

Set these variables in Render, never in Vercel:

| Variable | Requirement / default |
|---|---|
| `DATABASE_URL` | Required Tiger PostgreSQL connection string, with Tiger's TLS parameters retained |
| `CORS_ORIGINS` | Required production frontend origin, e.g. `https://your-project.vercel.app` |
| `SEC_USER_AGENT` | Existing SEC configuration; only needed for separate ingestion jobs |
| `GEMINI_API_KEY` | Needed for live explanation; optional for quantitative reads |
| `GEMINI_MODEL` | `gemini-3.8-flash` |
| `GEMINI_TIMEOUT_SECONDS` | `30` (supported range 1–60) |
| `ELEVENLABS_API_KEY` | Optional audio credential |
| `ELEVENLABS_VOICE_ID` | Required for live audio; keep server-side |
| `ELEVENLABS_MODEL` | `eleven_multilingual_v2` |
| `ELEVENLABS_TIMEOUT_SECONDS` | `30` (supported range 1–60) |

Render supplies `PORT`. The app reads process environment, so production needs
no `.env` file. The PostgreSQL layer accepts postgres/postgresql URLs and uses
psycopg, pool pre-ping and hidden SQL parameters. Retain Tiger's TLS configuration
and authorize Render connectivity in Tiger networking settings if restricted.
Do not print the connection string while troubleshooting.

## Vercel frontend

Import the same reviewed repository revision and set Root Directory to `frontend`.
Use the Vite preset and a current Node 22 patch (at least 22.13.0) or Node 24.
The checked-in `frontend/vercel.json` defines:

| Setting | Value |
|---|---|
| Install | `npm ci` |
| Build | `npm run build` |
| Output | `dist` |
| SPA fallback | `/(.*)` → `/index.html` |

Set **only** `VITE_API_BASE_URL` to the actual HTTPS Render backend origin, with
no `/api` suffix, credentials, query or fragment. Set it separately for each
Vercel environment used (Production and any permitted Preview). This is public
build-time configuration. Redeploy after changing it. Builds fail if it is missing,
uses HTTP/loopback, or is not an origin. Core reads, explanation and audio use
the same normalized base URL. No backend secret belongs in any `VITE_` variable.
Development mocks are disabled by Vite's production flag regardless of
`VITE_USE_MOCKS`; no fake statistics/model outputs are introduced.

The SPA rewrite permits direct entry and refresh on `/company/:ticker` while
existing generated assets remain served normally. Verify on Vercel after deployment;
a local Vite preview is not proof of Vercel routing.

## CORS and deployment order

1. Create the Render service and record its actual HTTPS origin.
2. Create the Vercel project with that origin in `VITE_API_BASE_URL`.
3. Set Render `CORS_ORIGINS` to the actual Vercel origin and restart/redeploy Render.
4. Deploy the frontend and complete the smoke checks below.

Origins are comma-separated, without paths or trailing slashes. To retain local
browser access, explicitly include
`http://localhost:5173,http://127.0.0.1:5173` alongside the production origin.
Preview domains need individual explicit approval/configuration; wildcard origins
are rejected. Existing GET/POST, Accept/Content-Type and credentials-disabled
policy is unchanged. Include any custom frontend domain explicitly.

## Tiger schema and persisted data

Existing initialized Tiger databases need no deployment migration. For a new
database only, open a Render shell and run the repository's existing initialization:

```sh
cd backend
python -m scripts.init_db
```

This uses SQLAlchemy `create_all`: repeatable creation of missing tables, with
no reset, deletion or alteration of existing columns. It does not populate data
and is not an upgrade mechanism. Keep initialization out of the start command.
For an older schema that has not received the already-approved corrections,
review it first, then use the existing guarded migrations in the same directory:

```sh
python -m scripts.migrate_company_cik
python -m scripts.migrate_event_buyers
```

These replace CIK uniqueness with an ordinary index and allow unknown buyer
counts respectively. They are guarded/repeatable and do not require new changes
for deployment. No initialization or migration was run during Issue #32 checks.

Populate/validate the real frozen universe, market history, transactions, events
and signals through the existing offline pipeline before the demo. Production
GET paths read persisted data; they never download yfinance or SEC data. They do
not train models or create signals. Statistics/prediction may honestly contain
null/unavailable outputs, as documented in `backend/RESEARCH_API.md`. Legacy richer
evidence needs an explicit validated rebuild. Held-out metrics stay null until
a durable frozen evaluation artifact exists. Do not fabricate or backfill these
values during deployment.

## Local development and verification

The ignored root `.env` remains local backend configuration. From `backend`:

```powershell
..\.venv\Scripts\python -m uvicorn app.main:app --env-file ..\.env --reload
```

From `frontend`, `npm run dev` retains the localhost backend fallback. Optionally
copy `frontend/.env.example` to ignored `frontend/.env.local`; set
`VITE_USE_MOCKS=false` to use the real local backend instead of development mocks.
All `.env.*` files are ignored except `.env.example`; Vercel local metadata is
also ignored. No real secret is present in examples or hosting configuration.

Validation commands:

```powershell
# From backend
..\.venv\Scripts\python -m pytest -q
# From frontend
npm ci
npm test
$env:VITE_API_BASE_URL = 'https://your-real-render-host.onrender.com'
npm run build
# From repository root
git diff --check
```

An HTTPS `.example.test` origin may be used for an offline build check, but such
an artifact is not a production deployment. The build does not contact that origin.

## Production smoke checklist

Choose a real persisted team-approved demo ticker. CRM is the existing documented
**small smoke sample**, not a claim that a fully scored demo company is selected.
Verify the selected company's persisted price coverage, event/signal identity,
scores, probability and honest unavailable fields before the presentation.

Use the actual backend URL below; this read-only loop makes no provider requests:

```powershell
$backendOrigin = 'https://your-real-render-host.onrender.com'
$demoTicker = 'CRM' # Replace with the team's selected real persisted sample.
$readPaths = @('/health', '/api/radar', "/api/companies/$demoTicker",
  "/api/companies/$demoTicker/prices", "/api/companies/$demoTicker/insiders",
  "/api/companies/$demoTicker/statistics", "/api/companies/$demoTicker/prediction")
foreach ($path in $readPaths) {
  $response = Invoke-WebRequest -Uri "$backendOrigin$path"
  "$path : $($response.StatusCode)"
}
```

Confirm latest-event matching and null versus zero behavior in the JSON. Unknown
ticker returns 404; a known ticker without an event returns a documented 404 on
statistics/prediction. Insufficient evidence for an existing event returns 200
with explicit unavailable statuses.

Open Vercel `/`, navigate to the selected company, then directly open and refresh
`/company/<ticker>`. Confirm Radar, chart, insider table, statistics and prediction
panels render measured values or honest unavailable states. In browser Network,
confirm every API request targets Render and no server credentials appear. Check
explicit-origin preflight/GET behavior and rejection of an unlisted origin.

Only after separate human approval for billable requests, make one
`POST /api/companies/<ticker>/explain` and one `/brief` (or use their UI buttons).
Check explanation sections and research-only language. For audio, verify MP3
playback or preserved transcript with `audio_unavailable`. Gemini failure returns
sanitized 503 and does not affect quantitative reads; audio failure returns 200
with transcript and null audio fields. Brief does not depend on Gemini. Never
loop paid requests. See `backend/AI_SERVICES.md` for provider validation details.

Recheck health and read endpoints after any provider failure. Hosted deep links,
browser CORS, audio playback, Render Linux dependency installation and real public
URLs still require manual platform verification; local checks do not deploy them.

## References

- [Render FastAPI](https://render.com/docs/deploy-fastapi)
- [Render monorepo files/root directory](https://render.com/docs/monorepo-support)
- [Render Python versions](https://render.com/docs/python-version)
- [Render Blueprint secret prompts](https://render.com/docs/blueprint-spec)
- [Vercel Vite SPA routing](https://vercel.com/docs/frameworks/frontend/vite)
