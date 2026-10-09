# Merged insider event dataset — Issue #5

This offline build joins existing Issue #2 `insider_transactions`, Issue #3's
frozen `config/universe.csv`, and Issue #4 `prices`. It writes `research_events`
using the existing database/session layer. No SEC or yfinance request occurs
during a build, and no returns, predictive market features, CAR, scores, ML,
or API endpoints are implemented here.

## Run and migrate

From `backend/`, with `DATABASE_URL` configured locally in the ignored root
`.env` or process environment (process values take precedence):

```powershell
..\.venv\Scripts\python -m scripts.migrate_event_buyers
..\.venv\Scripts\python -m scripts.build_event_dataset --dry-run
..\.venv\Scripts\python -m scripts.build_event_dataset
```

Initialize an empty database with the existing foundation initializer first.
New databases use the corrected model automatically. Existing PostgreSQL/Tiger
databases require `migrate_event_buyers`: its only DDL is
`ALTER TABLE research_events ALTER COLUMN unique_buyer_count DROP NOT NULL`.
It inspects the column and does nothing when already nullable. No data, other
columns, constraints or indexes are altered. It uses the configured database
search path, like the foundation models. Run against the intended schema; the
ALTER may briefly lock the table and requires the appropriate database privilege.
The approved contract correction also makes this same API response field nullable.

For a limited build:

```powershell
..\.venv\Scripts\python -m scripts.build_event_dataset --ticker CRM --start 2026-09-21 --end 2026-09-21
```

`--ticker` may be repeated for frozen-universe securities only. Default event
information-date range is 2020-01-01 through today's New York date, inclusive.
`--cache` defaults to `../data/sec_cache`; `--report` defaults to ignored
`../data/event_dataset_report.json`. `--dry-run` reads/builds/reports without
database writes. Reports contain event aggregates, statuses and join diagnostics,
never environment values or raw database exceptions. No new dependency is added.

## Inclusion, joins and timing

Recheck the underlying predicate: document type `4`, `NONDERIV_TRANS`/Table I,
non-derivative, code `P`, acquisition flag `A`; transaction and filing dates
must both be 2020 or later and transaction date must not exceed filing date.
Describe these as **code-P purchase transactions**, since P also permits private
purchases. Amendments (`4-A`/`4/A`) stay in the source table but are excluded from
event aggregation with a reconciliation diagnostic; do not guess their connection
to originals or count them as independent new purchases.

Reuse `Universe.resolve_issuer(cik, ticker)`: compatible exact canonical ticker,
otherwise unique normalized issuer CIK; shared-CIK ambiguity, conflicting
identifiers and unknown issuers produce explicit diagnostics and no event.
GOOG/GOOGL remain distinct; BRK-B aliases to canonical BRK.B through Issue #3.
Derived transaction output includes frozen company metadata separately from SEC
company/name/owner provenance. Missing company rows needed by accepted events
are inserted from the frozen snapshot; existing company metadata is preserved,
and a conflicting known issuer CIK fails the transaction for human review.

`transaction_date` remains the execution date; `filing_date` is the P0 public
information boundary. `public_event_day` is the first persisted SPY session date
strictly after filing date. Friday/weekend/holiday dates therefore align using
observations rather than adding one calendar day. A preceding calendar observation
is required. No next observation or a gap greater than seven calendar days on
either side is reported as insufficient coverage rather than jumping weeks.
If another persisted symbol reveals a session missing from SPY before the chosen
day, the event is blocked with a diagnostic.

This requires a reasonably complete persisted SPY calendar. A session missing
from every symbol within the seven-day guard cannot be detected from observations
alone; this builder does not claim to reconstruct an independent exchange calendar.
Review price coverage before a production-wide build.

One group is one `ticker + public_event_day`, with stable ID `TICKER:YYYY-MM-DD`.
`information_date` is the latest contributing filing date, so every included
transaction is public by that boundary. The output range filters this date.
Builds read all persisted transactions through `--end` before grouping; a start
date between Friday and weekend filings cannot accidentally split their group.
An earlier `--end` is an as-of filing cutoff and does not include later filings.

## Aggregates and buyer evidence

`source_transaction_count` counts distinct canonical Issue #2 transaction keys;
`source_filing_count` counts distinct accessions. Duplicate input keys are skipped
with diagnostics, preserving the existing identity and legitimate occurrence
counter. `aggregate_purchase_value` sums valid Decimal values, NULL if none are
available. A partial sum is explicitly marked `purchase_value_incomplete`.

`unique_buyer_count` counts distinct **supported underlying identities** only when
every included transaction has reliable buyer evidence. Otherwise it is NULL,
with `buyer_identity_unknown` status and transaction diagnostics. Unknown never
becomes zero. Names, pipe-delimited groups and all owners of a joint filing are
never treated as buyer identities.

The pure builder accepts an explicit transaction-id -> `BuyerEvidence` mapping;
the caller is responsible for source-supported transaction association. The CLI
uses retained SEC sources conservatively: complete single-reporting-owner XML
or single-owner bulk filing evidence supports association to that one reporting
owner CIK. XML issuer CIK and canonical transaction signatures are checked against
the stored transaction. Multiple owners, missing CIKs, absent/invalid sources or
unsupported associations leave count unknown. XML ambiguity does not fall back
to bulk/name guessing. The cache is the retained, trusted Issue #2 source archive;
no owner schema or Issue #2 parser is redesigned. Two independently supported
buyers across filings count as two; the same CIK counts once.

Preserve raw names/roles and source files. Role flags reflect preserved SEC
relationship/title evidence (`OFFICER`/executive titles, `DIRECTOR`, `OTHER`/
ten-percent-owner); the broad bucket is Executive > Director > Other. CFO is
recognized where the reported role supports it. Missing roles are marked
`role_information_incomplete`. When buyer association is unknown, the metadata
also marks `role_attribution_unverified`; filing-wide relationships cannot prove
which joint filer bought a particular transaction. Review those events before
using their role flags for research. Raw source strings remain available.

## Ownership and market coverage

For valid nonnegative acquired shares and shares owned after:

```text
prior_shares = shares_owned_after - acquired_shares
ownership_change_pct = acquired_shares / prior_shares  (prior_shares > 0)
```

The percentage is a ratio, not multiplied by 100. If prior shares are zero, the
ratio is NULL and `new_position_flag=true`. Negative prior shares or missing/
invalid inputs leave ownership results unknown, never fabricated.

Event ownership is the maximum valid ratio. `any_new_position_flag` is true if
any supported transaction starts a position, false only when all are known and
none does, otherwise NULL. Incomplete evidence is flagged. Per-transaction
derived ownership is retained as documented string-encoded Decimal values in
`feature_metadata.transaction_ownership`; raw ownership amounts remain unchanged.

Market checks inspect persisted adjustment-aware price availability only. The
metadata reports valid stock sessions strictly before `information_date` and
their last date. For the locked `[-120,-21]` estimation range, it checks paired
stock/SPY current and previous price inputs without calculating returns, flagging
fewer than 60 complete input pairs as `insufficient_market_history`. Missing
stock event-day analysis price is also explicit. These are coverage checks,
not calculated quant features or a guarantee that a later model fit will succeed.

## Persistence, rebuilding and limits

Parameterized PostgreSQL upserts enforce `(ticker, public_event_day)` uniqueness;
SQLite equivalents are used only for tests. An entire selected build commits
atomically through `Database.session()`, or rolls back on error. Research events
update in place with stable IDs as additional transactions/evidence arrive.
Unrelated existing metadata keys are preserved. A changed event already linked
to downstream signals fails for explicit invalidation/review, preventing silent
stale scores. Use one builder at a time for this hackathon workflow.

Underlying `insider_transactions` are never collapsed, deleted or re-identified.
Only a missing mapped ticker and the derived `public_event_day` are enriched;
valid source dates, amounts, owner details, amendment metadata and keys remain.

Rebuilding identical input leaves one unchanged event and adds no transactions.
The builder does not automatically delete older events that become unbuildable
after source/calendar removals or corrections. Diagnostics and the report are
the current build result; reconcile any previously persisted stale events
manually with downstream dependencies before treating the database as a fresh
snapshot. This conservative policy avoids deleting valid provenance/signals.

Before writing, a cross-event overlap guard compares proposed source canonical
transaction keys with all retained event associations. Existing metadata IDs are
resolved through Issue #2's transaction identity; new event metadata also retains
the canonical keys. If a source already belongs to a different retained event,
the entire proposed event is blocked, including its transaction enrichments.
The old event and any downstream signals remain untouched; other nonconflicting
events may persist. `events_blocked` reports the blocked count, and each overlap
diagnostic includes the canonical key, source transaction ID, existing event ID,
proposed event ID and the requirement for explicit reconciliation. The report's
`events` list includes built proposals; blocked proposals were not persisted.
Thus a remapped public event day cannot silently duplicate a retained source
association. Rebuilding the same event identity remains valid and idempotent.

The frozen current S&P 100 snapshot is not point-in-time historical membership;
historical analysis retains survivorship/selection bias. Joint filings and SEC
source corrections require review. No full backfill is performed by this command.

## Verification

```powershell
..\.venv\Scripts\python -m pytest -q tests/test_research_event_aggregation.py
..\.venv\Scripts\python -m pytest -q
```

Tests use synthetic records and isolated SQLite. On October 9, 2026, a small
live validation retrieved CRM accession `0001108524-26-000212`, one code-P purchase,
and persisted eight CRM and eight SPY daily observations for September 14–23.
The builder produced `CRM:2026-09-22`, information date September 21, preserving
the September 18 transaction date. Single-owner XML supported buyer count 1.
The first build inserted one event; the repeat left it unchanged with zero new
events or raw transaction enrichments. A fresh PostgreSQL query found zero
duplicate event groups. The intentionally short sample reported insufficient
market history. The approved migration ran twice successfully. Credentials were
never displayed and no historical backfill was performed.
