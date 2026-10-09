# Historical daily market ingestion — Issue #4

From `backend/`, install `requirements-dev.txt`, configure the existing PostgreSQL
`DATABASE_URL` in the local environment or ignored root `.env`, and initialize
the foundation schema. Then run:

```powershell
..\.venv\Scripts\python -m scripts.ingest_prices
```

The script loads root `.env` without overriding existing environment variables.
It uses `Universe.from_csv()` and the frozen 101 securities in
`config/universe.csv`, plus SPY and XLK, XLF, XLV, XLE, XLI, XLY, XLP, XLU,
XLB, XLRE, XLC: 113 unique targets. There is no new universe download.
Internal tickers remain canonical; only BRK.B is explicitly translated to Yahoo's
BRK-B. GOOG and GOOGL remain separate securities.

The default range is 2019-01-01 inclusive through today's New York date exclusive.
This conservatively excludes today's possibly incomplete session, including when
run after the close. Run the next day to include that bar. `--start` and `--end`
accept ISO dates; end is exclusive and cannot exceed today. Actual history begins
at the first available bar, including later IPOs. No missing sessions are fabricated.

For a small download without database writes:

```powershell
..\.venv\Scripts\python -m scripts.ingest_prices --validate-only --ticker AAPL --ticker SPY --ticker XLK --ticker BRK.B --start 2024-01-01 --end 2024-02-01
```

Omit `--validate-only` to persist. Repeated `--ticker` options select a subset of
the frozen universe/benchmarks; other symbols are rejected before downloading.
The JSON report defaults to ignored `data/market_ingestion_report.json` and is
checkpointed after each symbol. `--report` changes its path. Reports contain
normalized/written counts, date coverage, diagnostics and safe failure statuses.
Written counts mean rows submitted to upsert, not newly inserted rows.
Partial records are explicitly reported; complete symbol failures produce exit 1.

## Provider and adjustment convention

The single provider adapter uses yfinance (`>=0.2.66,<2`; locally tested with
1.7.0), calling once per symbol:

```python
yf.download(
    tickers=provider_symbol(ticker), start=start.isoformat(), end=end.isoformat(),
    interval='1d', auto_adjust=False, back_adjust=False, repair=False,
    actions=False, keepna=True, prepost=False, rounding=False,
    threads=False, progress=False, ignore_tz=False,
    multi_level_index=False, timeout=30,
)
```

Raw Open/High/Low/Close map directly to their nullable columns. `Adj Close` maps
to both `adjusted_close` and `analysis_price`, for stocks, SPY and every sector
ETF. Missing adjusted close leaves both NULL with a diagnostic; raw Close is
never substituted. Missing individual fields remain NULL. Invalid/nonfinite or
nonpositive prices and negative/fractional/out-of-range volumes become NULL;
fully empty observations are skipped. Zero volume is valid.

Timezone-aware daily labels convert to America/New_York before extracting a
SQL DATE; naive labels are already session dates. Numeric/invalid labels and
observations outside the requested window are skipped with diagnostics. Records
sort by ascending date. This is not an exchange holiday/calendar validator and
does not infer missing trading sessions or calculate market features.

Identical duplicate dates collapse; conflicting duplicates cause all observations
for that date in that download to be skipped and reported. Existing persisted
rows for skipped dates remain unchanged. No arbitrary conflicting row wins.

The provider makes at most three attempts for exceptions or empty responses,
with 1/2-second backoff, a minimum 0.5-second interval between request starts,
and a 30-second provider timeout. Symbols run sequentially. Yahoo may perform
multiple internal HTTP requests, so these are adapter-level bounds rather than
a total wall-clock deadline. No infinite retries occur. Failures do not abort
other symbols; raw database/provider exceptions are omitted from reports.

## Persistence and offline use

The existing `Price` model and `Database.session()` are reused with no schema
change. Parameterized PostgreSQL `INSERT ... ON CONFLICT (ticker, date) DO UPDATE`
in chunks of 100 commits atomically per symbol. All value fields are replaced
together, including NULLs, to avoid combining old adjusted data with new raw
values. Repeated ingestion keeps one row per ticker/date and permits corrections.
SQLite uses the equivalent upsert only for isolated tests.

Yahoo can revise adjusted history after corporate actions. Refresh the full
historical range when consistent adjustment vintages are required; a narrow
incremental refresh cannot guarantee consistency across older rows. Provider
quality and coverage require review; no repair or synthetic history is applied.

Downstream services can call `read_prices(session, ticker, start=None, end=None)`
from `app.services.market.repository`. It queries only persisted data, sorts
chronologically, and uses inclusive start/exclusive end. Application startup and
the demo do not download prices. No API endpoints or quant calculations are added.

Run `..\.venv\Scripts\python -m pytest -q` from `backend/`. Market tests use
synthetic observations and mocked downloads. Before deployment, manually ingest
a small subset into a disposable PostgreSQL/Tiger database twice and verify
row counts, corrections, NULL handling and offline reads across restarts.
SQLite tests do not replace this live database check.
