# Backend foundation — Issue #1

SEC bulk/XML ingestion instructions: [SEC_INGESTION.md](SEC_INGESTION.md).
Frozen company universe and the existing-database CIK correction: [config/README.md](../config/README.md).

From the repository root (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend/requirements-dev.txt
cd backend
..\.venv\Scripts\python -m uvicorn app.main:app --reload
```

`GET /health` returns `{"status":"ok"}`. This is a process health check;
it does not connect to the database or prove database readiness.

Set `DATABASE_URL` in the process environment using your local PostgreSQL or
Tiger Cloud connection configuration. `.env.example` is a template only;
the application does not automatically load `.env` files. Never commit credentials.
Supported URL schemes are `postgresql://`, `postgres://`, and
`postgresql+psycopg://`; all use the psycopg 3 driver. Preserve provider-required
connection options such as `sslmode=require` in the URL.

From `backend/`, initialize an empty database:

```powershell
..\.venv\Scripts\python -m scripts.init_db
..\.venv\Scripts\python -m pytest -q
```

Initialization uses SQLAlchemy `create_all` and can be repeated without dropping
data. It creates missing tables, but does **not** migrate existing table definitions.
Existing databases need the reviewed Issue #3 CIK migration linked above before
inserting shared issuer CIKs. Other schema evolution requires reviewed migrations. No Timescale
extension or hypertable is required for this initial PostgreSQL schema.

SQLAlchemy provides parameterized persistence and pooled connections; psycopg
provides PostgreSQL/Tiger Data connectivity. FastAPI/Pydantic and Uvicorn provide
the API and server. Pytest and HTTPX are development-only test dependencies.

Database access belongs in services using `Database.session()`. It commits on
success, rolls back on failure, and closes the session. The owner of a `Database`
instance must call `close()` at shutdown. Configuration is lazy and SQL logging
is disabled with bound parameters hidden. Do not log raw connection exceptions
or URLs in future routes/services. Initialization emits a sanitized error on failure.

All six contract tables are represented, including the explicitly approved
`research_events` schema dependency. Schema initialization performs no ingestion,
aggregation, feature, quant, or ML calculations and inserts no data. Missing numeric
values remain nullable, with no invented defaults. IDs and normalized tickers
are supplied by future ingestion/services. Numeric values use exact database
NUMERIC types; timestamps use timezone-aware PostgreSQL types. Prices intentionally
have no companies foreign key, allowing benchmark and sector ETF symbols.

Signals use one current row per research event (unique `research_event_id`).
Future persistence should update that row by event ID within a transaction;
version fields describe that current output, not a historical version archive.
Fundamentals use the recommended composite uniqueness; nullable fiscal periods
follow PostgreSQL NULL uniqueness semantics. Future ingestion must use stable
`fundamental_id` values to deduplicate records with missing fiscal periods.

Tests use synthetic fixtures in an isolated SQLite database for constraints and
transaction lifecycle, and compile all DDL using the PostgreSQL dialect. They
do not replace live Tiger Data verification: initialize twice against a disposable
PostgreSQL database, verify the tables/indexes, and verify persistence across restarts
before review. Never run destructive test operations against production data.
