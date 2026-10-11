# Signal coverage: Phase 1 and proposed follow-ups

Only Phase 1 is implemented. Priorities 2–4 are proposals, not scoring policy.

## Phase 1

Current Radar items emit availability_status: not_scored when the latest event
has no exact matching Signal, otherwise the persisted score_status. The legacy
three-value score_status enum and fallback unavailable_components list remain
unchanged for compatibility. For not_scored, that list is not evidence of
component failures and is hidden. Older payloads without the new field retain
legacy presentation; they do not prove the scoring process ran. Company
latest_signal stays null for unscored events, distinguished from no event by
latest_public_event_day. No database or scoring-policy change is needed.

An October 10, 2026 public Radar refresh returned 80 rows: 9 complete, 71
insufficient_data, zero partial; 55 had all five component values null. Radar
alone cannot distinguish absent rows from stored all-null Signals. The preceding
company-endpoint investigation established 55 absent matching Signals and 16
stored insufficient-data Signals (14 missing C, two missing C and S). Those
company-level counts are a historical observation, not a new database inventory.

Public statistics GETs in this phase show ADBE:2026-06-29 has
zero_historical_rate (historical rate 0, recent rate 1/30, one buyer), a
confirmed legitimate unavailable-C case under the current formula.
AMT:2026-08-26 has historical rate 2/365, recent rate 1/30, ratio
6.083333333333333 and one buyer but status insufficient_data. Its exact
reference-value failure reason is not exposed; do not assume missing identities
or a zero baseline. Obtain per-component reference counts/reasons.

## Priority 2: diagnose C, then repair verified gaps

activity.py reports zero historical rate, missing canonical identities, missing
sector fallback and insufficient valid buyer/rate-ratio references. The owner
adapter accepts verified single-owner source filings and does not invent
transaction attribution for ambiguous owners or use names as identity keys.

build_signals retains original missing_reasons in transient audit; persist_signals
stores selected statistics/provenance, not the full missing-reason audit. Public
statistics provide status/rates/buyers/population, insufficient to identify every
root cause. Recover the original runner audit, or separately authorize diagnostic
recomputation against a pinned snapshot without persistence.

Required per-event diagnostics: exact ID/information date/model version; recent
and historical inclusive windows, qualifying event counts/rates; missing owner
transaction IDs and accession/source provenance; reference company/sector
membership and finite buyer/ratio sample counts; complete status and reason lists.
Do not infer an exact cause from null C alone.

| Cause | Classification | Safe action |
| --- | --- | --- |
| Missing verified owner/source cache | Recoverable source gap if evidence exists | Retrieve/reconcile authoritative sources in a separately approved task |
| Omitted valid references or incorrect sector mapping | Recoverable processing gap if demonstrated | Repair mapping/orchestration with temporal tests |
| Zero historical rate or fewer than 10 usable references | Genuine insufficient evidence | Preserve unavailable C and null IES |
| Multiple owners without verified transaction attribution | Genuine ambiguity unless linkage exists | Preserve missing identity; never use names |
| Null C without original reasons | Unknown pending diagnostics | Obtain reasons before choosing a repair |

Do not lower thresholds, fabricate a baseline, or use future reference data.

## Priority 3: provisional policy research, not implementation

Keep the S-only insufficient-history partial exception unchanged. Recommend
available-component evidence without a new composite until diagnostics and
research validation are approved. A possible first research candidate is C alone
missing for an explicitly recoverable gap with valid A/M/S/D. Missing C+S is
weaker; missing M is especially unsuitable for a model-assisted composite.
None of these combinations is currently permitted by MODEL_SPEC §12.

Options: evidence-only display (safest); separately labeled, unranked provisional
composite; or ranked provisional output after explicit model-spec approval.
Renormalization increases remaining weights and changes comparability. Report
missing reasons/components, original weight coverage (.85 without C), effective
weights and policy version. Weight coverage is not confidence. Do not mix a new
provisional score into the standard complete/approved-partial ranking.

Validate using time-held-out masking of complete Signals, realistic missingness,
rank correlation, top-k overlap, uncertainty and sector/time stratification.
IES is a research-priority heuristic, not a probability: calibrate M separately;
never present IES as a calibrated probability. Do not tune on the frozen test or
use future outcomes to determine historical eligibility. Small samples and frozen
universe bias limit evidence. Maintainer approval is needed for missing-component
combinations, formulas, coverage thresholds, ranking and display policies.

## Priority 4: reproducible offline orchestration, not execution

Committed functions cover features, A/C/S/D, event studies, datasets/purged splits,
model selection, inference and persistence. Committed scripts ingest data/build
events; no production caller of build_signals/persist_signals was found. Startup
and render.yaml only serve the API. DEMO_PLAN records an ignored
issue35_prepare_quant.py harness and 39 post-selection Signals. That harness is
absent here: recover and review it before duplicating orchestration.

Proposed future command: `python -m scripts.generate_signals`.

1. Require selected event IDs, immutable input snapshot, observation cutoff,
   trusted expected sessions, frozen universe/ETF mapping, canonical owner evidence,
   feature provenance and a trusted versioned fitted-model artifact.
2. Validate artifact feature schema, dependencies, preprocessing, threshold and
   latest information used for fitting/selection, including validation outcomes.
   Establish model availability before each focal information boundary; report
   excluded events separately from evaluated failures. Never backfill old events
   with a later-selected model. Historical inference requires approved walk-forward
   artifacts. Never load an untrusted serialized artifact.
3. Compose existing calculations with all feature/reference/outcome cutoffs. Current
   CAR outcomes are retrospective display only, never predictors. Preserve existing
   bootstrap/randomization counts, seeds and missing-data behavior.
4. Default dry-run performs no persistence, ingestion or training. Emit a versioned
   report with input hashes, eligibility/exclusion counts, per-event component
   statuses/reasons, model/config versions and replicate diagnostics. Preserve valid
   components; distinguish skipped/not_scored from evaluated insufficient_data.
5. Explicit write mode calls persist_signals in a caller-owned transaction after
   preflight, verifies unchanged inputs, and keeps event binding/idempotent upserts.
   Retain an immutable run/audit manifest and before-images for authorized recovery;
   existing API evidence snapshots are not complete operational audit storage.
6. Test dry-run nonmutation, replay determinism, model-time eligibility, malformed
   artifacts, missing inputs, temporal guards, repeated writes and late-batch
   rollback. Verify PostgreSQL/concurrent-upsert behavior before scheduling.
7. Failed batches roll back. Post-commit recovery requires approved restoration of
   exact previous Signal and namespaced event evidence; never blanket-delete or
   silently rerun an obsolete model.

Sequence: recover harness/artifacts → approve artifact/model-time/report contracts
→ implement/test dry-run → approve bounded writes/PostgreSQL checks → controlled
persistence → optional scheduler with locking, retries and alerts. Never score on
GET/startup. Keep credentials server-side and exclude secrets from reports/logs.


## Issue #81: truthful missing-Signal explanation

The retained 80-company snapshot contains 55 latest events without matching
Signals, 16 persisted insufficient-data Signals, and nine complete Signals.
All 55 missing-Signal events have information dates on or before the documented
last validation outcome, January 14, 2026. This is consistent with the documented
deliberate eligibility exclusion in the ignored operational runner, but individual
reasons remain unverified: original run membership, exclusion records, and model
availability evidence have not been recovered. Dates and documentation alone do
not establish why an individual Signal is absent.

The current read path has no trustworthy event-level exclusion record or verified
exclusion contract. `feature_metadata` is not an authenticated exclusion record.
No new exclusion status is introduced. Missing exact latest-event Signals remain
`not_scored` regardless of event year or unverified metadata claims. UI copy says
that no persisted Signal is available and the reason has not been verified; it
must not claim scoring never ran or that all five components were evaluated.
Persisted complete, partial, and insufficient-data statuses remain unchanged.

A future verified-exclusion display requires a separately reviewed evidence
contract binding the event ID, original run, policy, and model availability to
an explicit exclusion decision and its verification authority. This change adds
no scoring runner, historical backfill, model training, or production access.
