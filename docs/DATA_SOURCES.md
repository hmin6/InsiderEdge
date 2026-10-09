# InsiderEdge Data Sources

## 1. SEC insider transactions

### Historical source

Official **SEC Insider Transactions Data Sets** quarterly bulk files.

Reference page from the master plan:

- https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets

At the plan revision time, the SEC bulk page listed data through 2026 Q2. The implementation must detect/report the newest bulk quarter actually available at ingestion time rather than hard-code an assumption.

Historical project range: **2020-01-01 to current available data**.

Important bulk tables include submission/filing metadata, reporting owners, and non-derivative transactions. Join using documented SEC keys and record the source tables used.

### Recent source

Recent **EDGAR Form 4 XML / filing metadata** fills the gap after the newest available quarterly bulk data.

Use a descriptive SEC `User-Agent`, bounded request rate, retry/backoff appropriate for the hackathon, and explicit error reporting.

### P0 qualifying transaction semantics

SEC transaction code `P` means an **open-market or private purchase** of a non-derivative or derivative security. Do not label every code-P row as exchange-only open-market execution.

P0 qualifying purchase records are:

- Form 4 records; preserve Form 4/A amendment metadata;
- non-derivative / Table I rows;
- `transaction_code == "P"`;
- `acquired_or_disposed == "A"`.

Preserve `security_title`. Do not silently infer execution venue.

### Temporal fields

Keep these separate:

- `transaction_date`: when the transaction occurred;
- `filing_date`: P0 historical public-information boundary;
- `accepted_at`: exact EDGAR acceptance timestamp when available;
- `public_event_day`: first trading day after `filing_date` under the daily-data convention.

Never replace `filing_date` with `transaction_date` in backtesting or predictive-feature timing.

### Amendments / duplicates

- Preserve amendments for provenance.
- Do not blindly count a Form 4/A as a new research event.
- Ingestion must be idempotent.
- Deduplicate records that appear through both bulk and EDGAR using stable/canonical filing-transaction identity.
- Surface malformed/unmappable records rather than invent values.

## 2. S&P 100 universe and company mapping

The project universe is a **frozen S&P 100 snapshot at hackathon start**.

`config/universe.csv` should contain at minimum:

- `ticker`
- `cik`
- `company_name`
- `sector`
- `industry` when available

Normalize CIK formatting consistently and handle special ticker naming safely.

This is **not** a point-in-time historical index reconstruction. Historical 2020–current analysis using a current/frozen S&P 100 sample can contain survivorship/selection bias, and that limitation must be documented.

The master plan does not lock a single external provider for the S&P 100 membership list; choose the source before dataset generation and then freeze the result.

## 3. Market data

Provider: **yfinance** behind a service/provider abstraction.

Price range: **2019-01-01 to current available date**.

Why 2019: early-2020 events need pre-event estimation history.

Required symbols:

- all frozen S&P 100 stocks;
- SPY;
- sector ETFs: `XLK`, `XLF`, `XLV`, `XLE`, `XLI`, `XLY`, `XLP`, `XLU`, `XLB`, `XLRE`, `XLC`.

Store daily:

- ticker;
- date/timestamp;
- open;
- high;
- low;
- close;
- adjusted close / explicitly adjustment-aware `analysis_price`;
- volume.

Explicitly configure provider adjustment behavior. Do not rely on a changing library default. All stock, SPY, and sector-return calculations must use the same adjustment-aware price convention.

Persist/cache market data in Tiger Data/PostgreSQL. The live demo must not depend on a fresh yfinance request.

## 4. SEC CompanyFacts (P1)

Optional/P1 fundamentals source: SEC CompanyFacts.

Prioritize a small reliable set:

- cash;
- total debt;
- equity;
- revenue;
- current assets;
- current liabilities;
- operating income.

Preserve report period and `filed_date`. A statement cannot be used for an event before it became public, and a later filing must never be backward-filled into an earlier event.

Missing fundamentals must not block a P0 signal.

## 5. Derived datasets

Derived project datasets are not external sources:

- `research_events`: one row per `ticker + public_event_day` for quant/inference/ML;
- `signals`: persisted anomaly/activity/statistical/dislocation/model/IES outputs.

Raw SEC transactions remain separately preserved for provenance and UI display.
