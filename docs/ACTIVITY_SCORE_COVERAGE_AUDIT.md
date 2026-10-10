# Phase 2: Activity-score coverage audit

## 1. Executive summary

Audit branch: `quant/activity-score-coverage`, base
`50b9bf2fcc4f9ab8963b654cf5d8b4459a1d6832` (Phase 1 merged as PR #87).
This is a diagnostic report; no scoring, API, persistence or ingestion code changed.

Public unauthenticated GET observations on **2026-10-10, 19:32:32–19:33:39 UTC**:

| Scope | Count |
| --- | ---: |
| Radar/latest research events examined | 80 |
| Matching latest-event persisted Signals | 25 |
| Latest Signals with C available | 9 |
| Latest Signals with C unavailable | 16 |
| Latest events without a matching Signal (`not_scored`) | 55 |
| Complete / partial / insufficient-data latest Signals | 9 / 0 / 16 |
| All research events in the 80 public ticker histories | 458 |
| Distinct research-event IDs in those histories | 458 |
| Raw transactions in those ticker responses | 1,051 |
| Research events with null event-level buyer counts | 6 |

The 16 missing-C latest Signals have **9 explicit zero-historical-rate states**
and **7 reference-limited cases** consistent with current code and public history.
All 16 are **legitimately unavailable under current methodology on the observed
input inventory**. This is not proof that upstream SEC coverage is complete.
No recoverable production data or scoring implementation defect was established.
Exact archived missing-reason lists and identity-map coverage remain unverified.

The 55 `not_scored` events are not 55 activity failures. Their latest public dates
are all no later than 2025-12-02. Do not backfill their probabilities with a model
selected later. No inference or signal-generation job was executed for this audit.

## 2. Sources, scope and limitations

Read-only sources:

- `https://insideredge-api.onrender.com/api/radar`
- `/api/companies/{ticker}` for all 80 Radar tickers
- `/api/companies/{ticker}/statistics` for the 16 persisted missing-C cases
- `/api/companies/{ticker}/insiders` for the same 80 tickers
- Repository specifications, source, tests and `docs/DEMO_PLAN.md`.

All requests were unauthenticated GETs, TLS-verified, at most four concurrent,
with bounded timeouts and no automatic retries. No endpoint fetch failed. No
production credential, database connection, provider POST, ingestion or scoring
job was used. Raw insider names and reporting-owner identifiers were not retained
in the diagnostic extracts. Source-type counts in the examined transactions are
1,050 bulk and one EDGAR; this describes current persisted rows, not source
completeness or the canonical-owner evidence used by the original runner.

The requests are not an atomic database snapshot. Statistics IDs/public dates
match the corresponding latest Signals; reconstructed recent/historical event
counts reproduce all 16 persisted rates, and reference choices also agree. This
cross-check supports the reference-limit findings, but does not establish the
original run's exact reference membership or complete upstream ingestion.

The public history endpoint has no pagination/cap in
`backend/app/services/core_reads.py:73–81`; it returns persisted rows for each
ticker. No claim is made about unexposed transactions outside the 80 tickers,
other historical Signals, or SEC filings missing from the database. DEMO_PLAN's
39 total Signals / 14 valid C values are historical runner observations, not a
fresh global Signal-table count. The API exposes only the latest Signal per ticker.
The older documented 1,229-transaction global inventory is not directly comparable
to this 1,051-transaction ticker-scoped read.

Sanitized local evidence and read-only collection scripts are retained under
`/tmp/ie-phase2-audit/` for this review (temporary, not durable repository assets).
This report embeds the relevant per-event results so it does not depend on those
files surviving. Evidence hashes:

- `summary.json`: `2b0f35f9cb679244394da7b6a018e15a2ef99231c99c900d175ac8319d2fdc53`
- `history_summary.json`: `ac044dd140f28f29ae09cf41d91853800ede0940d4ea9da913383639d7d50e46`
- `cases_enriched.json`: `675f64e1c0e93d88e5a921aed4bb1afa5d1faedaa59a2f5a5e4378c88abed944`

## 3. Current pipeline, inputs, formulas and thresholds

```text
normalized SEC transactions + persisted market sessions + frozen universe
  -> cached_buyers: verified transaction-associated reporting-owner CIK evidence
  -> build_dataset: one ticker/public-day research event; raw rows retained
  -> build_event_features: raw pre-event features, BuyerEvidence diagnostics
  -> build_activity_scores: separate transaction-ID -> canonical-ID mapping
  -> build_signals: aligned precomputed components + provenance + frozen model
  -> persist_signals: Signal columns + bound contract evidence in event metadata
  -> read-only Radar/company/statistics endpoints
```

The arrows above describe intended composition, not a discovered committed
production runner. `build_activity_scores` takes research-event and transaction
DataFrames, ticker/sector company metadata, and an explicit identity map
(`backend/app/quant/activity.py:143–192`). Mandatory columns are checked there.
Normalized `ticker`, not issuer CIK or name, is the company key. Input events must
represent qualifying company-days; the scorer cannot attest their completeness.

`MODEL_SPEC.md` §5 and `activity.py:91–139,159–164,213–297` implement:

- Information boundary `t` = research-event `information_date` (filing availability).
- Recent: **[t−29, t]**, inclusive, 30 calendar dates.
- Historical: **[t−394, t−30]**, inclusive, 365 calendar dates. No overlap.
- Rates = distinct qualifying company public-event-day counts / 30 and / 365.
- Ratio = recent rate / historical rate; historical zero leaves ratio and C null,
  with `zero_historical_rate`. No epsilon, capped invented value or division by zero.
- Buyers = distinct canonical insiders across qualifying recent filings; any
  missing transaction identity leaves the buyer count unavailable, never a guess.
- Prior references require `reference.information_date < focal.information_date`;
  equal-date and later events cannot contribute. Each reference's metrics are
  calculated at its own information date.
- Use earlier same-company events when there are at least **10 raw event rows**;
  otherwise use earlier same-sector events. Sector fallback includes the company's
  own earlier events. Company selection is not revisited merely because some of
  its metric values are missing.
- Require at least **10 nonmissing reference values independently** for buyers
  and for rate ratio. Earlier events with zero historical rate cannot contribute
  a rate-ratio value. Both percentiles must exist.
- Activity percentiles use the weak empirical CDF
  `100 * count(reference <= current) / n`: **upper ranks for ties**, not the
  dislocation module's midrank convention.
- `C = 0.50 * BuyerCountPercentile + 0.50 * RateRatioPercentile` on 0–100.

Raw event IDs must be unique. Company/public-day duplicates are collapsed before
counts/references (`activity.py:179–184`). Buyer identities use a set, so repeated
transactions by one insider cannot inflate unique buyers. Missing company/date,
missing transaction/canonical ID, insufficient buyer/ratio references, missing
sector fallback and zero baseline have explicit `missing_reasons` outputs.

### Canonical identity and qualifying-source boundary

`events/buyers.py:20–98` reads existing source caches only. XML validates issuer
and canonical transaction membership; a single reporting owner with a valid CIK
can be attributed. Bulk REPORTINGOWNER evidence requires one unambiguous owner.
Invalid, absent or multi-owner evidence remains unknown. Names are never keys.
`features.py:164–187` accepts `BuyerEvidence`, retains source diagnostics, and
requires support for every transaction in the requested window.

The activity scorer expects scalar canonical-ID strings rather than BuyerEvidence
objects; the operational caller must bridge these contracts correctly and only
from verified transaction-associated evidence. No committed adapter/production
caller was found. Do not stringify BuyerEvidence objects or tuples as identities,
or choose one owner from an ambiguous group. Event-level counts alone cannot
establish unique buyers across several events.

Event building excludes unresolved amendments and deduplicates canonical source
transactions (`events/build.py:70–114`). Activity's P0 transaction filter honors
`is_p0_qualifying` or P/A/non-derivative flags (`activity.py:27–45`); it does not
itself reconcile amendments or require event-source membership. The raw normalized
P0 flag can also be true on Form 4/A (`sec/normalize.py:134–136`). Verify which
transaction subset the original runner supplied before alleging an amendment
bug or changing this boundary. This is an integration risk, not an established
cause for the 16 cases.

### Evidence retention and persistence

`signal_integration.py:87–102,153–156` rejects contradictory numeric/status/reason
inputs. C is copied directly into the payload (`:185–191`); no weight adjustment
or recomputation occurs. Full component dictionaries, including missing reasons,
are retained in `SignalBatch.audit` (`:215–229`). Persistence upserts nullable C
and binds validated API evidence to the event (`:233–272`).

`research_reads.py:38–78` persists/maps activity rates, ratio, buyers, chosen
population and status. It does **not** retain the full activity missing-reason
list, raw counts, both population memberships, reference-value counts or component
percentiles in the public statistics contract. Original transient audit is needed
for those exact historical fields. DB access alone cannot recover discarded audit.
No evidence of computed valid C being lost in persistence was found; current
API C values agree between Radar, company and statistics for all 16 missing cases.

## 4. Per-event evidence table

All 16 rows below have a persisted Signal with null C and final
`score_status=insufficient_data`. IDs use the displayed public day:
`research_event_id = TICKER:public_day`. `info` is the filing/company information
boundary, **not** public day. Rates below are displayed rounded to six decimals;
local arithmetic used full API precision. Counts R/H are independently counted
from current public research-event history, not guessed from frontend labels.

| Ticker | Info | Public day | Sector | R/H events | Recent/historical rate | Ratio | Buyers30 | Activity status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ADBE | 2026-06-26 | 2026-06-29 | Information Technology | 1/0 | 0.033333/0.000000 | null | 1 | zero_historical_rate |
| AMT | 2026-08-25 | 2026-08-26 | Real Estate | 1/2 | 0.033333/0.005479 | 6.083333 | 1 | insufficient_data |
| AVGO | 2026-06-15 | 2026-06-16 | Information Technology | 1/2 | 0.033333/0.005479 | 6.083333 | 1 | insufficient_data |
| CRM | 2026-09-21 | 2026-09-22 | Information Technology | 1/5 | 0.033333/0.013699 | 2.433333 | 1 | insufficient_data |
| CVS | 2026-01-27 | 2026-01-28 | Health Care | 1/3 | 0.033333/0.008219 | 4.055556 | 1 | insufficient_data |
| DIS | 2026-02-17 | 2026-02-18 | Communication Services | 1/1 | 0.033333/0.002740 | 12.166667 | 1 | insufficient_data |
| IBM | 2026-02-25 | 2026-02-26 | Information Technology | 2/1 | 0.066667/0.002740 | 24.333333 | 3 | insufficient_data |
| INTU | 2026-05-26 | 2026-05-27 | Information Technology | 1/0 | 0.033333/0.000000 | null | 1 | zero_historical_rate |
| LIN | 2026-08-19 | 2026-08-20 | Materials | 1/1 | 0.033333/0.002740 | 12.166667 | 1 | insufficient_data |
| MMM | 2026-04-09 | 2026-04-10 | Industrials | 1/0 | 0.033333/0.000000 | null | 1 | zero_historical_rate |
| MO | 2026-09-11 | 2026-09-14 | Consumer Staples | 1/0 | 0.033333/0.000000 | null | 1 | zero_historical_rate |
| MU | 2026-01-15 | 2026-01-16 | Information Technology | 1/0 | 0.033333/0.000000 | null | 1 | zero_historical_rate |
| NOW | 2026-03-02 | 2026-03-03 | Information Technology | 1/0 | 0.033333/0.000000 | null | 1 | zero_historical_rate |
| PANW | 2026-03-27 | 2026-03-30 | Information Technology | 1/0 | 0.033333/0.000000 | null | 1 | zero_historical_rate |
| PFE | 2026-08-12 | 2026-08-13 | Health Care | 2/0 | 0.066667/0.000000 | null | 3 | zero_historical_rate |
| SCHW | 2026-05-28 | 2026-05-29 | Financials | 1/0 | 0.033333/0.000000 | null | 1 | zero_historical_rate |

### Reference reconstruction and root-cause classification

`N/Q` = earlier raw event count / events with a nonzero historical rate (and hence
an available finite ratio under the current rate formula). Both populations use
strictly earlier information dates; each Q is computed at that reference's own
information boundary. These are current-public-inventory diagnostics, **not
retrieved archived scorer reference counts**. Actual buyer-reference sizes and
percentiles are unexposed. Every nonzero-current-ratio case has selected Q < 10,
which by itself is sufficient to prevent C irrespective of buyer availability.

| Ticker | Company N/Q | Sector N/Q | Selected population | Supported limitation | Classification / confidence |
| --- | --- | --- | --- | --- | --- |
| ADBE | 7/6 | 111/72 | sector | Current historical rate = 0 (explicit API status) | Legitimately unavailable on observed inputs / High; explicit status |
| AMT | 5/3 | 5/3 | sector | Selected population has 5 earlier events (<10) | Legitimately unavailable on observed inputs / High for observed inventory |
| AVGO | 14/9 | 110/71 | company | Selected ratio references at most 9 (<10) | Legitimately unavailable on observed inputs / High for observed inventory |
| CRM | 12/9 | 113/73 | company | Selected ratio references at most 9 (<10) | Legitimately unavailable on observed inputs / High for observed inventory |
| CVS | 10/8 | 57/25 | company | Selected ratio references at most 8 (<10) | Legitimately unavailable on observed inputs / High for observed inventory |
| DIS | 4/2 | 18/9 | sector | Selected ratio references at most 9 (<10) | Legitimately unavailable on observed inputs / High for observed inventory |
| IBM | 11/5 | 104/68 | company | Selected ratio references at most 5 (<10) | Legitimately unavailable on observed inputs / High for observed inventory |
| INTU | 0/0 | 109/71 | sector | Current historical rate = 0 (explicit API status) | Legitimately unavailable on observed inputs / High; explicit status |
| LIN | 9/4 | 9/4 | sector | Selected population has 9 earlier events (<10) | Legitimately unavailable on observed inputs / High for observed inventory |
| MMM | 0/0 | 79/48 | sector | Current historical rate = 0 (explicit API status) | Legitimately unavailable on observed inputs / High; explicit status |
| MO | 2/0 | 16/6 | sector | Current historical rate = 0 (explicit API status) | Legitimately unavailable on observed inputs / High; explicit status |
| MU | 0/0 | 100/66 | sector | Current historical rate = 0 (explicit API status) | Legitimately unavailable on observed inputs / High; explicit status |
| NOW | 1/0 | 105/69 | sector | Current historical rate = 0 (explicit API status) | Legitimately unavailable on observed inputs / High; explicit status |
| PANW | 2/0 | 108/71 | sector | Current historical rate = 0 (explicit API status) | Legitimately unavailable on observed inputs / High; explicit status |
| PFE | 7/4 | 63/29 | sector | Current historical rate = 0 (explicit API status) | Legitimately unavailable on observed inputs / High; explicit status |
| SCHW | 16/10 | 64/29 | company | Current historical rate = 0 (explicit API status) | Legitimately unavailable on observed inputs / High; explicit status |

Counts by primary limitation: 9 current zero baselines; 2 insufficient selected
raw populations (AMT, LIN); 5 insufficient selected ratio populations despite at
least 10 raw reference events (AVGO, CRM, CVS, DIS, IBM). Limitations can coexist.
Four of the five latter cases select company history; DIS already uses sector.

No case is classified as a confirmed recoverable data/implementation defect.
Whether additional authoritative filings are missing is **unresolved** for all
cases. The exact original reason list and buyer-percentile availability remain
**unresolved**, even where a sufficient rate-based explanation is established.

## 5. Case studies

### ADBE:2026-06-29

Information date 2026-06-26. Recent window 2026-05-28 through 2026-06-26;
historical window 2025-05-28 through 2026-05-27. One recent event, no historical
events, buyers30=1, ratio=null, explicit `zero_historical_rate`. The public history
has seven earlier company events and 111 earlier IT-sector events (72 eligible
ratio values), so adding sector references would not fix ADBE's own undefined
ratio. This is a legitimate mathematical limitation on current data. Establish
source completeness before describing the absence as an exhaustive SEC fact.

### AMT:2026-08-26

Information date 2026-08-25. One recent and two historical events; rates 1/30 and
2/365; ratio 6.083333333333333; buyers30=1. Five earlier company events, and only
five earlier Real Estate events across all examined ticker histories, with three
nonzero historical-rate reference values. Thus sector fallback cannot reach 10.
This directly supports a reference-history limitation, unlike the earlier
unresolved hypothesis. It does not establish an original buyer-reference count
or prove that no qualifying SEC filings were missed upstream.

### AVGO / CRM / CVS / IBM: company selected but fewer usable ratios

Earlier company event counts are 14, 12, 10 and 11, respectively; available ratio
counts are only 9, 9, 8 and 5. The code selects company history on raw event count
and then applies per-component minima. It does not fallback on usable-value
counts. This matches the current documented raw-event hierarchy; do not label it
a proven bug or silently replace it with per-component/complete-case fallback.
Their sectors have more ratio observations, but changing when/how fallback occurs
would require a maintainer interpretation/contract decision and independent buyer
coverage verification. No coverage gain is asserted.

### DIS and LIN

DIS has 18 earlier Communication Services events but only nine usable ratio
values, so C remains unavailable at the component-value minimum. LIN has only
nine earlier Materials events and four usable ratios. Neither is fixed by
repairing the current event's already-available buyer count.

### Identity/source examples

Six event-level buyer counts are null: BAC:2020-07-23, BAC:2020-07-28,
BAC:2020-07-31, BAC:2020-08-05, CRM:2024-06-06 and CRM:2025-12-09.
These demonstrate historical identity uncertainty, not an exact missing-ID count
or a proven source-recovery opportunity. All 16 focal buyers30 values are present;
two CRM reference event counts are null, potentially further limiting its buyer
references, but its ratio minimum already fails. Obtain transaction-associated
owner evidence before proposing repairs. Never sum event buyer counts to dedupe
people across events or use names as a replacement.

## 6. Category assessment and temporal safeguards

| Category | Evidence / conclusion |
| --- | --- |
| A: zero baseline | Nine explicit API cases; null ratio/C is correct. No denominator adjustment. |
| B: reference history | Seven nonzero-ratio cases have a sufficient current-inventory reference explanation. Original detailed audit still needed. |
| C: canonical identities | Current buyers30 present for all 16; six historical event buyer counts null. Exact map coverage and recoverability unexposed. |
| D: sectors | All 80 public sector values populated and match the frozen CSV exactly. No metadata mismatch found; historical point-in-time taxonomy is not established. |
| E: event coverage | 458 unique IDs, no repeated public ticker/day groups, no duplicate transaction IDs within ticker responses. Rates match current history. Canonical-source duplication and omitted filings cannot be ruled out through these API fields. |
| F: integration | Direct C copying and nullable upsert verified by inspection/tests; no demonstrated lost valid C. Fifty-five latest events lack Signals and are reported separately. |

The 30/365 inclusive windows and strict reference cutoff are explicit in code and
existing activity tests. References with the same information date are excluded.
Duplicate transactions map to a set of supported owners; missing identity makes
the count unavailable. Event builder amendments/canonical deduplication must be
preserved in any runner input adapter. Source/calendar completeness remains an
upstream attestation; a missing filing can change both rate counts and references.

IES formula and S-only partial exception remain unchanged
(`MODEL_SPEC.md` §12; `quant/insideredge_score.py:65–102`). Missing C must not be
renormalized away. `build_signals` accepts a fitted model and provenance but cannot
establish the historical availability of an externally supplied trained artifact.
DEMO_PLAN:184–215 documents a last-validation-outcome cutoff of 2026-01-14 and
only 39 later Signals. That is historical operational evidence, not a fresh model
artifact verification. Require a trusted fitting/selection timeline before any
historical recomputation; do not infer it from a model name or a missing Signal.

## 7. Proposed repairs, ranked by evidence and risk

| Priority | Root cause / action | Modules / minimal change | Expected coverage effect | Tests / leakage risk | Migration or recomputation |
| --- | --- | --- | --- | --- | --- |
| 1 | Original detailed activity diagnostics are not public/durable in full; recover original audit and inputs | Recover ignored runner/audit first; propose a pure `services/activity_diagnostics.py` formatter consuming existing activity outputs/audit and supplied provenance, with file-only `scripts/audit_activity_coverage.py` wrapper | Observability only; no score increase promised | Exact ID binding, null vs zero, raw/usable counts, reasons, deterministic sanitized output, nonmutation, future/equal-date exclusion | No DB migration or production recomputation; recovered audit can be formatted offline |
| 2 | Possible missing authoritative owner/source data, not yet confirmed | `events/buyers.py` and source-cache adapter only after validating affected transaction/source IDs; bridge single supported canonical IDs explicitly | Unknown until original missing-ID inventory/source evidence reviewed | Repeated owner, different owners, multi-owner ambiguity, source mismatch, missing cache, original filing-time provenance | Source/event changes may need explicit invalidation and bounded historical rescoring; no migration assumed |
| 3 | Possible omitted/incorrect qualifying historical events, not established | Existing SEC normalization/event-builder/repository path, only for independently demonstrated omissions or duplicates | Unknown; do not invent estimated gains | Amendment/idempotency/canonical dedup, date boundaries, missing SPY session, same-day aggregation | Existing downstream-signal guard requires explicit invalidation plan; source repair and any recomputation separately authorized |
| Decision only | Raw-company count vs usable-component count fallback | Clarify MODEL_SPEC §5 before any `activity.py` behavior change; preserve minimum 10 and time cutoffs | Not estimated; sector ratio sufficiency alone does not prove buyer sufficiency | 10 raw / 9 valid company ratios with ample sector data, independent minima, tied cutoffs, reason transparency | If policy changes, explicit contract/version and bounded historical recomputation approval; not a data repair |

No sector repair or C persistence fix is recommended without additional evidence.
Do not broaden the S-only partial rule, cap ratios to force a value, or feed future
filings/references into historical events. Frozen-universe survivorship/selection
bias remains; the current universe is not historical index reconstruction.

## 8. Required tests for a separately authorized implementation

- Diagnostic export preserves existing activity score/status/reasons, missing vs
  zero, event identity, dates and raw/usable population counts without rescoring.
- No mutation of events, transactions, audit, model or source cache; no database,
  network, ingestion, fitting or persistence in the default diagnostic path.
- Current/public snapshot diagnostics clearly distinguished from archived outputs;
  absent audit/reference/provenance fields stay unknown, never inferred identities.
- Deterministic ordering/output; no owner names, credentials or secret config in logs.
- Canonical identity adapter only accepts supported transaction-associated source
  evidence; rejects ambiguous/missing owners; repeated transactions do not inflate
  buyers. Do not pass BuyerEvidence/tuple string representations as identities.
- Existing 29/30/394/395-day and equal/future information-date guards remain locked.
- Regression fixture: at least 10 raw company events but 9 valid ratio values,
  adequate sector references; pin current behavior until a fallback decision is made.
- If any source repair is approved, test event canonical dedup/amendments, affected
  reference propagation, explicit downstream invalidation and atomic rescoring.
- Preserve frozen-model historical selection cutoff and S-only partial scoring.

## 9. Additional evidence needed (no DB access performed)

Request the original `issue35_prepare_quant.py` harness, immutable run/input hashes,
full `SignalBatch.audit`, exact transaction-to-canonical-owner mapping with source
attestation, both reference memberships/usable-value counts, event-builder reports,
and model artifact training/selection/outcome cutoff. The ignored harness is
absent from this checkout. Committed references to scoring entry points are tests
and definitions, not a scheduled production caller. Render starts uvicorn only.

If a human authorizes DB inspection, use a read-only transaction on a replica or
read-only account, bounded statement timeout, and return aggregated/non-personal
fields. Example **not executed** (PostgreSQL):

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '10s';
SELECT count(*) AS stored_signals,
       count(activity_score) AS with_c,
       count(*) FILTER (WHERE activity_score IS NULL) AS without_c
FROM signals;
SELECT e.research_event_id, e.ticker, e.information_date, e.public_event_day,
       e.feature_metadata ->> 'buyer_identity_status' AS buyer_identity_status,
       s.activity_score, s.score_status, s.model_version, s.score_version
FROM research_events AS e
JOIN signals AS s ON s.research_event_id = e.research_event_id
WHERE s.activity_score IS NULL
ORDER BY e.information_date, e.research_event_id;
ROLLBACK;
```

A second targeted query should bind approved event IDs via parameterized ORM/
array parameters, not string interpolation. Avoid dumping complete feature JSON
or owner details. A read of current metadata cannot reconstruct reasons that the
original persistence mapper never stored.

## 10. Validation and recommended next task

Executed from `backend/`:

```text
.venv/bin/python -m pytest -q tests/test_activity.py tests/test_signal_integration.py tests/test_research_api.py tests/test_research_event_aggregation.py
155 passed in 15.76s
```

These synthetic/local tests cover activity formula, upper-rank ties, inclusive
windows, future exclusion, duplicate buyers, zero baseline, missing IDs/sectors;
event/source identity and amendments; signal persistence and API evidence. They
are not proof of production source completeness or the original runner adapter.
`.venv/bin/python -m compileall -q app tests` passed. `git diff --check` and
`git diff --no-index --check /dev/null docs/ACTIVITY_SCORE_COVERAGE_AUDIT.md`
produced no whitespace diagnostics (the new-file comparison returned the expected
exit code 1 for differing files). Nothing was staged; unrelated local file hashes
were verified unchanged.

**Recommended exact Phase 2 Step 2 scope:** recover and inspect the original
activity audit/runner/input manifest, then add a read-only offline diagnostic
formatter over already-computed activity outputs and supplied identity/provenance
metadata. Keep it file/snapshot-based, deterministic and sanitized; no new API or
schema, no live DB access, no scores/model fitting, no altered thresholds/fallback,
no persistence or production recomputation. First answer the original missing-ID
and buyer/ratio reference counts. Any data repair or fallback-policy change is a
separate, evidence-gated authorization. No scoring fix is justified yet.

## 11. Step 2 — original evidence recovery and offline exporter

### Recovery inventory

Local inspection on 2026-10-10 found the committed activity implementation,
canonical-owner cache reader, event builder, signal-integration adapter and their
tests, plus the operational account in `docs/DEMO_PLAN.md`. The documented ignored
runner `data/sec_cache/issue35_prepare_quant.py` does **not** exist in this checkout;
neither `data/` nor `data/sec_cache/` exists. A repository filename search found no
original activity-output file, input manifest, canonical-ID mapping export, frozen
reference snapshot, model artifact or scoring-run diagnostic archive. These are
unavailable locally, not proven lost everywhere.

The retained `/tmp/ie-phase2-audit/` JSON files are the later public API audit
snapshots described above. They are **not** original runner inputs/outputs and
cannot recover the original missing-reason lists or prove source completeness.
No historical jobs were executed and no production database was accessed.

Remote metadata refresh succeeded. `origin/main` advanced from this branch's
`50b9bf2` base to `cbf71c7` (PR #89, Snowflake failure diagnostics). Its three changed
files do not overlap this exporter, the activity scorer, or the hard contracts.
The branch has not been merged or rebased; validation below is on its existing base.

### Interface and evidence schema

`backend/app/quant/activity_diagnostics.py` provides:

- `build_activity_diagnostics(activity_records, *, metadata_records=())`: detached,
  deterministic records, sorted lexically by research-event ID.
- `activity_diagnostics_json(...)`: strict JSON text; performs no file I/O.

Inputs are iterables of mappings with unique nonempty string `research_event_id`.
An existing scorer DataFrame can be supplied with `to_dict(orient="records")`;
this does not invoke scoring. Optional metadata uses the same IDs, with no
unmatched IDs. Conflicting supplied fields raise an error, including null versus
non-null: metadata cannot overwrite original unavailable evidence.

Each output contains `research_event_id` and `fields`. The fixed field allowlist
in `DIAGNOSTIC_FIELDS` covers scorer metrics, dates/windows, reference counts and
percentiles, plus explicitly supplied identity status, snapshot ID, policy version
and source provenance. Company/sector candidate counts are not currently emitted
by the scorer, so remain absent unless separately supplied. No counts, reasons,
percentiles, identity attestation or source metadata are reconstructed.

Each field has `state`, `value`, and `source`:

| State | Meaning |
| --- | --- |
| `observed` | Supplied non-null evidence; zero and empty lists are preserved. |
| `unavailable` | Explicit null, pandas missing scalar, NaN or infinity. |
| `not_supplied` | Field absent from both inputs; not a scoring failure. |

`source` is `activity_records`, `metadata_records`, or null. These labels describe
where the value was supplied, not independently verified lineage. `observed` does
not certify statistical validity. Date values serialize as ISO strings; finite
Decimals serialize as exact strings to avoid rounding evidence. Unsupported
objects raise errors rather than being stringified. Nested supplied evidence is
copied, not mutated. Nonfinite values become explicit unavailable evidence rather
than invalid JSON; nested nulls remain nested nulls.

Original `status` and `missing_reasons` are retained verbatim (apart from JSON
scalar conversion). A null score without reasons remains unexplained, not inferred
as zero baseline or insufficient reference history. Missing identity **evidence**
is distinct from an original `missing_canonical_insider_identifier` scoring reason.
This is an evidence formatter, not an input validator or recalculation service.
Names and canonical owner identifiers are not export fields. Callers must sanitize
free-form provenance/reasons before export; the utility is not a secret scanner.

### Usage and synthetic example

```python
from app.quant.activity_diagnostics import activity_diagnostics_json

# SYNTHETIC: demonstrates explicit unavailability versus absent provenance.
text = activity_diagnostics_json([{
    "research_event_id": "SYNTHETIC:1",
    "ticker": "SYNTHETIC",
    "activity_score": None,
    "status": "zero_historical_rate",
    "historical_rate": 0,
    "missing_reasons": ["zero_historical_rate"],
}])
```

Selected fields from that **synthetic**, non-production output:

```json
{
  "research_event_id": "SYNTHETIC:1",
  "fields": {
    "activity_score": {"state": "unavailable", "value": null, "source": "activity_records"},
    "historical_rate": {"state": "observed", "value": 0, "source": "activity_records"},
    "source_provenance": {"state": "not_supplied", "value": null, "source": null}
  }
}
```

For real diagnostics, pass **existing archived** activity records and attested
per-event metadata. Do not present newly scored or synthetic records as original
run evidence. The utility intentionally has no database adapter, CLI, network
client, persistence hook, or dependency additions.

### Remaining evidence and next recovery action

Ask the authorized operator of the original demo run for its ignored harness,
immutable input/output snapshots and hashes, verified transaction-to-owner mapping
and adapter, company/sector reference inventories, original activity missing
reasons, and run/policy/model identifiers. Recover these from their workstation or
approved artifact archive; no credentials or personal owner names are needed in
the diagnostic export. Retain original files unchanged, then format those records
through this utility. Missing artifacts cannot be recovered from persisted
Signal columns alone.

No new source-completeness defect was established by this step. The previously
identified amendment-input and canonical-mapping adapter questions remain
unverified until original inputs are recovered. No scoring, fallback, temporal,
threshold, persistence, API or IES policy was changed. This exporter improves
evidence retention only; it does not promise increased activity-score coverage.

### Step 2 validation

From `backend/`:

```text
.venv/bin/python -m pytest -q tests/test_activity_diagnostics.py tests/test_activity.py tests/test_signal_integration.py
108 passed in 15.61s

.venv/bin/python -m pytest -q
775 passed, 6 subtests passed in 34.07s

.venv/bin/python -m compileall -q app tests
passed
```

No warnings were reported. The exporter contributes 23 synthetic test cases,
covering all supplied fields, unavailable-score reasons, zero baseline, insufficient
references, absent versus null evidence, missing identity/provenance evidence,
nonfinite/pandas missing scalars, IDs and conflicts, deterministic strict JSON,
nonmutation, and forbidden file/network/database entry points. Existing activity
and persistence tests passed unchanged.

Tracked `git diff --check` passed. Separate `git diff --no-index --check /dev/null`
checks for the exporter, its tests and this untracked document produced no
whitespace diagnostics; exit code 1 reflects new-file differences. The full new
files were reviewed. Nothing is staged. SHA-256 checks confirm `.DS_Store`,
`backend/requirements-dev.txt` and `.vscode/settings.json` are unchanged from the
pre-Step-2 preserved hashes. No existing scorer or persistence module changed.

## 12. Final review improvements and latest-main integration

The exporter now rejects non-mapping rows with the collection name and zero-based
row index (for example, `metadata_records[1]: expected a mapping`). Invalid or
duplicate event-ID errors also include that location. Error messages do not echo
record contents or event IDs; cross-input errors identify the collections/field.
`observed` means supplied non-null evidence, **not necessarily type-valid**:
`activity_score="bad"` remains observed text, never a coerced score or invented
scoring failure. Field-specific scoring validation is intentionally out of scope.
Nested missing values serialize to null within observed container evidence.
Matching metadata is accepted; original activity fields retain their source label.

Synthetic fixtures now use realistic dates, counts, rates and percentile types.
Additional regressions cover malformed rows in both collections, observed text,
pandas timestamps (including timezone preservation), matching metadata, non-string
nested keys, nested missing values, deterministic JSON and detached nested output.

The refreshed integration target is `51c5b3552d501c6a619c0d743e8ae297e6c44d03` (see retained manifest for the full
SHA). It includes newer Snowflake diagnostics/numeric normalization and frontend
layout changes; none overlaps the three intended files. The original audit branch
remains at `50b9bf2`, with no merge or rebase. The exact three files are tested in
a detached temporary worktree based on refreshed main; the retained file manifest
binds their SHA-256 contents to that base. Earlier validation counts above remain
historical, rather than claims about this newer integration.

Final integrated validation on that refreshed main base, using the existing
compatible backend virtual environment from the isolated worktree's `backend/`:

```text
/Users/allen/InsiderEdge/backend/.venv/bin/python -m pytest -q tests/test_activity_diagnostics.py tests/test_activity.py tests/test_signal_integration.py
120 passed in 15.62s

/Users/allen/InsiderEdge/backend/.venv/bin/python -m pytest -q
817 passed, 6 subtests passed in 34.71s

/Users/allen/InsiderEdge/backend/.venv/bin/python -m compileall -q app tests
passed
```

No warnings or regressions were reported. The exporter now has 35 synthetic test
cases. Imports were verified to resolve to the isolated worktree, not the original
checkout. No integration conflicts occurred: all three files are new on main.
Tracked and separate new-file whitespace checks passed. Original unrelated files
remain hash-identical to their preserved versions, with nothing staged.

Retained validation assets: `/tmp/ie-activity-diagnostics-validation/worktree`,
`approved.patch`, and `manifest.json` in its parent directory. The manifest records
the tested base and SHA-256 of each of the three files. These temporary assets are
not durable original scoring-run evidence; preserve them until the authorized
transfer/commit review. This step did not update the original feature branch's base.
