# SEC CompanyFacts fundamentals — Issue #7 (P1)

This optional ingestion module is independent of the P0 event builder, API and
quant/ML paths. Missing fundamentals never block those paths. No schema, model,
frontend, API contract or dependency change is required.

## Source and commands

Official source: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`.
See [SEC API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).
`CompanyFactsProvider` reuses `SecClient`: configured `SEC_USER_AGENT`, sequential
requests at most twice per second, existing timeout and bounded retries. Run one
loader process at a time. No API request path downloads CompanyFacts.

From `backend/`, with the existing schema initialized and local root `.env`:

```powershell
..\.venv\Scripts\python -m scripts.ingest_fundamentals --ticker AAPL --validate-only
..\.venv\Scripts\python -m scripts.ingest_fundamentals --ticker AAPL
..\.venv\Scripts\python -m scripts.ingest_fundamentals --ticker GOOG --ticker GOOGL
```

The CLI loads root `.env` without overriding process environment. It never prints
credentials or raw exception strings. `--through YYYY-MM-DD` is an inclusive
filing cutoff (default today, future dates rejected). `--report` changes the JSON
report path, default ignored `data/fundamentals_report.json`. A company failure
does not abort other companies; failures/unavailable observations exit nonzero.
Reports distinguish retrieval, normalization and persistence failures, and list
missing concepts, unsupported units, malformed observations and ambiguity.

Batch ingestion requires explicit `--all`; do not run it until the reviewer has
accepted the small sample. Companies come exclusively from `Universe.from_csv()`.
Unknown tickers/missing CIKs reject selection before requests. Duplicate ticker
arguments collapse. Shared issuer CIKs are fetched once per batch, then explicitly
attached to each selected share-class ticker. These are issuer-level fundamentals,
not share-class-specific capitalizations; no CIK-only ticker guess is made.

## Small metric set

Only `us-gaap` entity facts, USD values and forms `10-K`, `10-Q`, `10-K/A`,
`10-Q/A` are supported. No currency conversion or thousands/millions rescaling
is performed: SEC USD values are stored as Decimal dollar amounts.

| Metric | Accepted tags, in preference order | Period |
| --- | --- | --- |
| cash | `CashAndCashEquivalentsAtCarryingValue` | Instant |
| total_debt | `DebtCurrent` + `LongTermDebtNoncurrent` | Same instant/filing |
| equity | `StockholdersEquity` | Instant |
| revenue | `RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, `SalesRevenueNet` | Duration |
| current_assets | `AssetsCurrent` | Instant |
| current_liabilities | `LiabilitiesCurrent` | Instant |
| operating_income | `OperatingIncomeLoss` | Duration |

Total debt is supported only when BOTH non-overlapping current/noncurrent debt
components are disclosed with identical accession, form, report end and filing
date. Missing components are not assumed zero. This limited mapping does not
claim to reconcile every issuer's lease/debt taxonomy; it deliberately leaves
many issuers missing. Equity excludes noncontrolling interests. Cash excludes
restricted cash and investments. No market capitalization or debt/equity ratio
is implemented.

Instant facts must have no start date. Duration facts require a start date and
60–380 days between start/end; start/end are retained. At a given report end and
filing, the highest-priority available tag wins, then the shortest reported
duration. This may be quarterly, YTD or annual depending on actual disclosures;
do not treat all returned revenue/operating-income values as equal-length quarters
or TTM. No quarter subtraction or annualization is performed. Lower-priority tags
are never summed with the preferred tag or substituted after preferred-candidate
ambiguity. Unsupported/custom tags and other forms are intentionally excluded.

Exact repeated candidates collapse. Conflicting values OR provenance at the
preferred tag/duration produce NULL plus an explicit normalization diagnostic;
no arbitrary accession wins. Negative operating income/equity are valid. Negative
assets, liabilities, revenue/debt, booleans, nonfinite or malformed numbers are
rejected. Malformed dates/provenance are diagnosed; future disclosures are ignored.

## Persistence and information boundary

The existing wide `fundamentals` table stores historical snapshots, not one
current value. Identity `cf1:<SHA256>` encodes canonical ticker, report end,
filed date and fiscal period. It respects the existing snapshot uniqueness rule.
`unit_metadata.metrics` stores each metric's taxonomy/tag, USD unit, start/end,
filed date, form, accession and fiscal labels. Debt retains both component
provenances. Unsupported/ambiguous observations retain unknown status where a
snapshot exists; normalization details are in the ingestion report. Snapshot
fiscal year is NULL if contributing metric fiscal years disagree; metric-level
labels remain preserved. Fiscal year/period labels describe the source filing,
which can contain comparative periods, not a reclassification of report end.

Retain disclosures filed from 2020 onward, plus the latest eligible pre-2020
baseline per metric (including ambiguity ties) for early-2020 lookup. This is
not a complete pre-2020 history service. A late filing restating an older period
remains a separate observation with its actual later availability date.

Parameterized PostgreSQL upserts replace the whole normalized snapshot,
including NULLs, by deterministic primary key. They never merge stale components
into a refreshed snapshot. Repeated identical data produces no duplicate rows.
Each ticker commits atomically through `Database.session()`; SQLite is only for
tests. Missing company rows are inserted from the frozen universe. Existing
company metadata is preserved; a conflicting existing CIK blocks persistence.
Use one ingestion process; legacy/non-`cf1` fundamentals require explicit review
if they collide with the existing snapshot uniqueness constraint. No migrations
or automatic legacy data deletions are attempted.

`as_of(session, universe, ticker, metric, information_date)` reads PostgreSQL only:

1. Require `filed_date <= information_date` and report end <= information date.
2. Among observations carrying that metric's evidence, prefer newest report end,
   then newest eligible filing date. An old comparative period refiled recently
   does not replace a newer reporting period.
3. Return value, report period, filed date and provenance. No eligible observation
   returns None. A preferred unknown snapshot returns value None, not an older
   valid revision. Conflicting eligible fiscal-period ties return explicit
   ambiguous status with value None.

Amendments are eligible only on/after their own filing dates. Later SEC filings
are never backward-filled. The daily convention is inclusive on filing date;
it does not promise intraday acceptance-time reconstruction. Missing values are
never zero or positive/negative signal evidence.

`current_ratio(...)` uses those point-in-time asset/liability observations only
if accession, report end, filed date and unit match, and denominator is positive.
Otherwise it returns None. It never combines incompatible reporting periods or
filings. No ratio is added to existing ML features or API responses.

## Validation and limits

```powershell
..\.venv\Scripts\python -m pytest -q tests/test_companyfacts.py
..\.venv\Scripts\python -m pytest -q
```

Ordinary tests use synthetic payloads, mocked providers and SQLite; no SEC/Tiger
connection is needed. Frozen current membership retains the project's documented
survivorship bias. SEC extraction can omit or revise facts; inspect original
filings before relying on unusual taxonomy/period choices. This module does not
claim complete company coverage or complete financial statement reconciliation.

On October 9, 2026, one live AAPL request succeeded using configured credentials
without displaying them. Three snapshots for report ends March 28 and June 27,
2020 (filing cutoff August 10, 2020) were selected for Tiger persistence. Counts
were 0 before, 3 after first write, and 3 after identical repeat, with zero
duplicate snapshot groups. Six priority metrics were present; total debt was
missing because compatible components were unavailable. Current ratio was
available. July 30 lookup used the March report; July 31 lookup could use the
June report disclosed that day. A fresh Python process verified those results
without SEC access. No full universe ingestion or historical backfill ran.
