# InsiderEdge Data Schema

This is an authoritative implementation contract for the hackathon database. The master plan defines the required tables and fields; this document concretizes keys/constraints so the team can implement them consistently.

## Conventions

- Tickers are stored uppercase in canonical project form.
- CIKs are normalized consistently; retain a string representation so leading zeros can be preserved when needed.
- Dates use ISO calendar dates; timestamps are timezone-aware where available.
- Monetary values are decimal/numeric, not binary floating point where database precision matters.
- Missing source data remains `NULL`; do not invent zeroes.
- `transaction_date`, `filing_date`, and `public_event_day` are distinct fields.
- One ML/inference row corresponds to one `research_event_id`, not a raw transaction or daily price row.

## `companies`

Purpose: stable identifier and sector metadata for the frozen hackathon universe.

Required fields:

| Field | Type/meaning |
|---|---|
| `ticker` | text, primary key |
| `cik` | text, normalized issuer CIK when known; nullable and non-unique across share classes |
| `company_name` | text |
| `sector` | text, nullable only when genuinely unavailable |
| `industry` | text, nullable |

Recommended indexes: non-unique `cik`; index `sector`.

`ticker` remains the unique company/security identifier. Multiple tickers may share
one issuer CIK (for example, GOOG and GOOGL). CIK-only lookup returns a ticker only
when exactly one matches; otherwise surface ambiguity and expose all matching
tickers. Never arbitrarily select a share class. This narrow correction was
approved during Issue #3 after real-data validation.

## `insider_transactions`

Purpose: normalized SEC transaction-level provenance/UI records.

Required fields:

| Field | Meaning |
|---|---|
| `transaction_id` | stable project primary key |
| `canonical_transaction_key` | stable deduplication identity across bulk/EDGAR, unique |
| `accession_number` | SEC accession / source filing identifier |
| `source_type` | `bulk` or `edgar` |
| `document_type` | Form `4` / `4-A` where represented |
| `ticker` | mapped ticker, nullable only when unmapped and surfaced as such |
| `cik` | issuer CIK |
| `company_name` | issuer name |
| `insider_name` | reporting owner name |
| `insider_role` | normalized/raw owner relationship text |
| `transaction_date` | date transaction occurred |
| `filing_date` | daily-data public-information boundary |
| `accepted_at` | EDGAR acceptance timestamp when available |
| `public_event_day` | first trading day after filing date when derivable |
| `transaction_code` | SEC transaction code |
| `acquired_or_disposed` | A/D flag |
| `derivative_flag` | whether derivative/source table is derivative |
| `source_table` | source SEC table / XML section |
| `security_title` | security title |
| `shares` | transaction shares, nullable |
| `price` | per-share transaction price, nullable |
| `transaction_value` | derived only when shares and price are valid |
| `shares_owned_after` | post-transaction ownership, nullable |
| `direct_or_indirect` | ownership nature when available |
| `aff10b5one` | 10b5-1 indicator when available |
| `is_amendment` | amendment metadata |
| `is_p0_qualifying` | normalized P0 inclusion flag |

`transaction_id` may be a UUID/text identifier. `canonical_transaction_key` must be deterministic enough to prevent the same filing transaction from being inserted twice when encountered through different ingestion paths. The exact source-row signature is an ingestion implementation detail, but its policy must be documented by Issue #2.

Recommended indexes:

- `(ticker, filing_date)`
- `(ticker, transaction_date)`
- `accession_number`
- `cik`
- `public_event_day`
- `is_p0_qualifying`

## `research_events`

Purpose: one company-level modeling/inference event per `ticker + public_event_day`.

Required fields:

| Field | Meaning |
|---|---|
| `research_event_id` | primary key; stable identity for `ticker + public_event_day` |
| `ticker` | company ticker |
| `public_event_day` | first trading day after filing-date information boundary |
| `information_date` | filing-date/company-day information boundary used for the event |
| `source_transaction_count` | number of qualifying underlying transactions |
| `source_filing_count` | number of source filings |
| `aggregate_purchase_value` | sum of valid transaction values |
| `unique_buyer_count` | unique underlying buyers |
| `role_bucket` | `Executive`, `Director`, or `Other` |
| `has_executive` | boolean |
| `has_director` | boolean |
| `has_other` | boolean |
| `has_cfo` | boolean when derivable |
| `max_valid_ownership_change_pct` | nullable |
| `any_new_position_flag` | boolean/nullable when source ownership data allows |
| `feature_metadata` | JSON/JSONB for documented derivation/status metadata if used |

Role hierarchy for the single broad bucket is `Executive > Director > Other`, while underlying flags remain preserved.

Suggested primary-key value:

```text
<TICKER>:<YYYY-MM-DD public_event_day>
```

A different deterministic encoding is acceptable only if all services use the same stable identity.

Recommended unique constraint: `(ticker, public_event_day)`.

Recommended indexes: `(ticker, public_event_day)`, `public_event_day`, `role_bucket`.

## `prices`

Purpose: persisted daily market data.

Required fields:

| Field | Meaning |
|---|---|
| `ticker` | stock/benchmark/ETF symbol |
| `date` | market session date |
| `open` | raw provider open |
| `high` | raw provider high |
| `low` | raw provider low |
| `close` | raw provider close |
| `adjusted_close` | adjusted close when provider supplies it |
| `analysis_price` | single adjustment-aware price series used by quant/ML |
| `volume` | volume |

Primary key / unique constraint: `(ticker, date)`.

Indexes: `date`; `(ticker, date)`.

All stock, SPY, and sector-return calculations use `analysis_price` (or the exact locked equivalent) consistently.

## `fundamentals` (P1)

Purpose: public company facts with temporal provenance.

Required/priority fields:

- `fundamental_id` primary key;
- `ticker`;
- `cik`;
- `report_period`;
- `filed_date`;
- `fiscal_year` / `fiscal_period` when available;
- `cash`;
- `total_debt`;
- `equity`;
- `revenue`;
- `current_assets`;
- `current_liabilities`;
- `operating_income`;
- normalized unit/currency metadata.

Recommended uniqueness: `(ticker, report_period, filed_date, fiscal_period)` or another deterministic CompanyFacts identity documented by the ingestion implementation.

Never backward-fill a later filing into an earlier research event.

## `signals`

Purpose: persisted research outputs for a research event.

Required fields:

| Field | Meaning |
|---|---|
| `signal_id` | primary key |
| `research_event_id` | foreign key to research event |
| `ticker` | company ticker |
| `public_event_day` | event date |
| `anomaly_score` | A, 0–100, nullable when unavailable |
| `activity_score` | C, 0–100, nullable |
| `statistical_score` | S, 0–100, nullable |
| `dislocation_score` | D, 0–100, nullable |
| `model_probability` | M/100, 0–1, nullable |
| `insider_edge_score` | IES, 0–100, nullable |
| `score_status` | `complete`, `partial`, or `insufficient_data` |
| `unavailable_components` | JSON/array if supported |
| `car5` | decimal return, nullable |
| `car30` | decimal return, nullable |
| `car90` | decimal return, nullable |
| `comparable_event_count` | integer, nullable |
| `comparable_cohort` | text/JSON, nullable |
| `mean_car30` | decimal, nullable |
| `bootstrap_ci_lower` | decimal, nullable |
| `bootstrap_ci_upper` | decimal, nullable |
| `randomization_p_value` | decimal 0–1, nullable |
| `model_name` | selected model name, nullable |
| `model_version` | optional version string |
| `score_version` | optional version string |
| `created_at` | output creation timestamp |

Recommended uniqueness: `(research_event_id, score_version, model_version)` when versions are used; otherwise one current signal row per research event with an explicit update policy.

Indexes: `(ticker, public_event_day)`, `insider_edge_score`, `score_status`.

## Ownership-change policy

Per qualifying acquisition transaction, when values are valid:

```text
prior_shares = shares_owned_after - acquired_shares
```

If `prior_shares > 0`:

```text
ownership_change_pct = acquired_shares / prior_shares
```

If `prior_shares == 0`:

- `ownership_change_pct = NULL`
- `new_position_flag = true`

At the research-event level use `max_valid_ownership_change_pct` plus `any_new_position_flag`. Do not fabricate the feature when source ownership data is missing.
