# Phase 3 Step 4 — immutable scoring evidence retention design

## 1. Executive summary and baseline

**Design proposal only; not an implemented storage guarantee or contract change.**
Pinned main: `810d998ab2c4225673106bc0bdbd1d572670147c`.
Design branch: `quant/phase3-evidence-retention-design`; isolated worktree:
`/tmp/ie-phase3-evidence-retention-design`. Phase 3 research, offline evaluation,
and historical provenance recovery documents are present on this baseline.

Future scoring runs should publish independently verifiable, append-only evidence
bundles before their results become eligible for research. The current Signal
remains a mutable serving projection, not the historical evidence archive.
No scoring formula, threshold, partial-score rule, API or database schema changes
are proposed here. Production provisional scoring remains **no-go**.

The retained inventory has 80 latest-event observations: 55 without matching
Signals, 16 incomplete vectors and nine complete but provenance-unverified vectors.
Zero primary-evaluation records are established as eligible. These are retained
snapshot findings, not a fresh production inventory. Original artifacts were not
recovered in the authorized local search; their existence elsewhere is unknown.
This design cannot repair those records or establish earlier availability.

## 2. Existing architecture and capture boundaries

Paths below refer to the pinned baseline. Capture means copying supplied inputs
and original outputs, not calculating a second set of scores.

| Boundary | Existing implementation | Proposed retained evidence |
| --- | --- | --- |
| Source normalization and event aggregation | `backend/app/services/events/build.py:build_dataset`; `events/repository.py:build_from_database` | Immutable normalized source snapshot, qualifying/excluded membership, amendment/dedup policies, exact research-event membership and metadata |
| Buyer association | `backend/app/services/events/buyers.py:cached_buyers` | Transaction-bound canonical reporting-owner evidence, unsupported associations and reasons, source hashes, mapping implementation version |
| Raw features | `backend/app/quant/features.py:build_event_features`, `build_market_feature_snapshot`; `backend/app/ml/dataset.py:prepare_inference_features` | Original feature rows, availability/provenance rows, schemas, market cutoffs, universe and sector mappings |
| A/C/D calculators | `anomaly.py:build_anomaly_scores`, `activity.py:build_activity_scores`, `dislocation.py:build_dislocation_scores` | Full original result frames including references, fallback rules, counts, missing reasons and diagnostics; referenced populations retained separately |
| Event study and S | `event_study.py:build_event_studies`; `statistical_validation.py:select_comparable_events`, `build_statistical_validations` | Session calendar, fitted-model diagnostics, horizon statuses, selected comparator IDs/outcome endpoints, actual outcomes, seeds and randomization diagnostics |
| ML selection and prediction | `backend/app/ml/training.py:ModelSelection`, `train_dataset`, `predict_selected`; `evaluation.py` | Fitted pipeline including preprocessing, feature order/exclusions, candidate/validation decisions, purged split membership, threshold, dependency versions and predictions |
| Composite integration | `backend/app/services/signal_integration.py:build_signals`; `backend/app/quant/insideredge_score.py:score_event` | Exact returned payloads and full `SignalBatch.audit` before any persistence/projection normalization |
| Current serving projection | `signal_integration.py:persist_signals`; `research_reads.py:EVIDENCE_KEY` | Separate persistence receipt and value binding; never use current rows as an immutable archive |

`persist_signals` replaces current nullable fields and namespaced event evidence;
existing signal ID/created_at survive updates. Full component audit is transient.
This permits revisions but does not prove any historical overwrite occurred.
`research_reads.signal_binding` rounds values for serving bindings; archive the
original numerical values instead of using that binding as the research source.

`ModelSelection` holds fitted pipelines in memory. DEMO_PLAN describes ignored
operational runners/checkpoints; a durable application-integrated model artifact
loader is not established. Introduce capture at an explicitly reviewed runner
boundary, not a route, import hook or startup task. No automatic scoring scheduler
is assumed. Exact capture hooks require a later implementation review.

## 3. Proposed schemas

These are versioned **artifact** schemas, separate from DATA_SCHEMA/API_CONTRACT.
No migration is necessary for the initial archive. All required fields must be
present; unknown facts are explicit nulls with reason codes, never invented values.
A structurally valid but incomplete bundle is preservable and research-ineligible.
Invalid types, contradictory lineage, duplicate event IDs or invalid available
canonical scores fail validation. Raw missingness follows Section 3.3. Unknown schema versions fail closed in the verifier.

### 3.1 Run manifest: `scoring-evidence/run/v1`

| Required field/group | Meaning |
| --- | --- |
| `schema_version`, `run_id`, `runner_version` | Fixed schema ID, opaque unique execution ID, runner version; not derived from a backdated cutoff |
| `execution_started_at`, `execution_finished_at`, `run_kind` | UTC timestamps; kind `prospective`, `retrospective` or `synthetic`; classification does not confer eligibility |
| `code_commit_sha`, `code_state` | Exact commit and clean/dirty status; retain an allowlisted source patch/hash for dirty runs or mark unverifiable |
| `environment` | Nonsecret environment label, Python/platform, exact dependency inventory/hash, relevant numeric/thread settings |
| `historical_information_cutoff`, `observation_cutoff` | Run-level upper bounds on per-event decision-time cutoffs and outcome-display sessions, respectively; never defaults that replace explicit per-event cutoffs |
| `scoring_policy` | Version/hash of formulas, weights, missingness policy and component configurations |
| `model`, `preprocessing` | Content-addressed artifact references; selected candidate, feature schema, fitted preprocessing, threshold and parameters; explicit unavailable reason if no fitted model |
| `model_timeline` | Train/validation ranges, maximum label endpoints, selection/freeze/activation timestamps, independently supported model availability, evidence references; test evaluation recorded separately |
| `inputs` | Manifest references for SEC/source rows, transactions, events, features/provenance, prices, expected sessions, company/sector universe and mappings |
| `calendar_policy`, `price_adjustment_policy` | Provider/source/version/hash, coverage, exchange/timezone, analysis_price semantics and adjustment/revision policy |
| `identity_mapping` | Version/hash, source references and unknown/ambiguous association policy; distinguish reporting-owner from issuer CIK |
| `ranking_contexts` | Explicit context IDs, information cutoffs, full eligible population, scored/unscored/excluded membership and policy references |
| `randomness` | Bootstrap/randomization/model seeds, RNG/library versions, configured/valid/attempted replicate counts and algorithm version |
| `outputs` | Relative artifact paths, media/schema types, SHA-256, byte sizes and row counts for every retained output |
| `lineage` | Parent/superseded run references, revision reason; null for an original run |
| `limitations`, `verification_state` | Evidence gaps, frozen-universe bias, caller attestations; publication is not independent verification |

An artifact reference contains `artifact_id` (content identity), safe relative
`path`, `sha256`, `byte_count`, `schema_version` and, for tabular data, `row_count`.
Referenced external objects require immutable version identifiers plus hashes and
an authorized retrieval mechanism. A hash alone without retained bytes is not
recoverable evidence. Never embed credentials or signed access URLs.

Temporal definitions apply consistently to run, event and receipt schemas:

- `historical_information_cutoff`: claimed decision-time information boundary,
  not execution or artifact creation time. In multi-event batches the run value
  is an upper bound; each event retains its own explicit information_date.
- `source_available_at`: when the exact source version became publicly available,
  with supporting evidence, distinct from occurrence, retrieval and observation.
- `model_selected_at`: when validation-based candidate selection completed.
  `model_frozen_at` records the frozen pipeline/threshold decision.
- `model_activated_at`: when the exact model version was enabled for the named
  scoring environment; activation is not selection or proof of earlier availability.
- `artifact_created_at`: when retained bytes were created, separate from the dates
  represented by their contents and any original source artifact creation time.
- `published_at`: when the publication authority issued the final receipt; an
  authority claim requires verification and is not an independent time anchor.

Chronology fields carry evidence references or null plus an explicit unknown reason.
A later activation does not imply that an artifact was unavailable elsewhere earlier;
any such earlier availability requires separate evidence. Self-reported timestamps
alone never prove historical availability. A run observation_cutoff bounds explicit
per-event outcome-display cutoffs and cannot authorize future predictive inputs.

### 3.2 Dataset manifest: `scoring-evidence/input/v1`

Retain dataset schema/units, stable ordering/key rules, row count, exact byte hash,
source/provider/version, retrieval timestamp, source publication/availability
facts with supporting references, coverage, transformation code/configuration,
revision/adjustment policy, missingness and exclusions. Large inputs may be
content-addressed shared objects, but the complete dependency closure must remain
retained and independently retrievable.

For prices retain ticker/session keys, original supplied analysis_price and
adjustment flags. For calendars retain the actual expected-session index, source
and asserted completeness; timestamps/hashes cannot validate that completeness.
For SEC retain filing/accession/source transaction references and relevant public
availability evidence. Keep source occurrence time, source publication time,
retrieval time and system observation time distinct. Record mapping uncertainties;
never infer canonical identities from names or reconstruct unsupported associations.

### 3.3 Event evidence: `scoring-evidence/event/v1`

One unique record per research_event_id within a run:

- Identity: research_event_id, ticker, public_event_day, information_date, source
  transaction/accession references and event-input hash.
- Components A/C/M/S/D: original value, scale, status, exact missingness reasons,
  implementation version/config hash, source input references, reference population
  membership and full original diagnostics/audit reference.
- M: preserve original probability on [0,1] and its derived M on [0,100], explicitly
  linked to the selected fitted pipeline; conversion occurs exactly once.
- Temporal evidence per component: computed_at, source_available_at,
  source_availability_evidence, system_first_observed_at, historical availability
  claim and verification basis. Unknown timestamps remain null with reasons.
  Computation time is never backdated to information_date.
- S: selected comparator IDs, information dates, actual CAR30 completion endpoints,
  cohort fallback, minimum/count, bootstrap/randomization component statuses,
  parameters and seed diagnostics. Preserve successful partial evidence.
- Final: insider_edge_score, score_status, unavailable components/reasons, original
  applied weights and permitted normalization denominator. Retain exact output;
  never broaden S-only partial policy or fill missing components with zero.
- Context: ranking_context identifier, context manifest reference, exact population
  membership/exclusion reason and evaluation cutoff. Multiple contexts may reference
  the same event but must not duplicate its identity within a context.
- Full original audit plus normalized research view, with explicit transformation
  version and hashes for both. A normalized view must not replace the original.

Raw evidence distinguishes original null, NaN, positive infinity and negative
infinity using typed missingness records, retaining normalization metadata and
source references. Canonical score fields accept only finite numbers or explicit
null; a nonfinite or otherwise invalid score claimed available fails validation.
Normalized missing score fields use null rather than NaN/Infinity, with links to
the original typed missingness evidence. A serializer must preserve supplied
missing reasons and report any normalization. Unsupported objects cause a clear
error, not lossy str(object) conversion. Decimal values use tagged exact decimal
strings; floating-point values use round-trip binary64 representations without
presentation rounding. An adapter explicitly validates/converts these types.

### 3.4 Publication and verification receipts

Minimum publication receipt fields: receipt schema version, run_id, manifest
SHA-256 digest, published_at, publication authority or signer identity,
trust-policy reference/version and verification_scope. Authenticated receipts
add signature algorithm/key identifier and signature over defined canonical bytes
(excluding the signature itself), or a verifiable independent ledger reference.
Unknown authority/time evidence is explicit and cannot pass authentication checks.
Verification receipts additionally bind their own ID, reviewer/verifier version,
review time, referenced publication receipt/hash, evidence references, findings
and per-scope decisions with reasons. Never mutate an earlier receipt.

Scopes are separate: `byte_integrity` checks retained bytes and hash closure;
`authenticated_publication` checks authority and trusted receipt binding;
`reviewed_historical_eligibility` checks original source/model chronology and
research eligibility. Passing one does not pass the others. Even a valid signature
or receipt does not independently prove source or model availability.

## 4. Artifact layout and deterministic serialization

Proposed private storage namespace, outside Git and the public web root:

```text
scoring-evidence/
  objects/sha256/<digest>                 # immutable input/model bytes
  staging/<run-id>/<attempt-id>/          # unpublished partial capture
  runs/<run-id>/
    manifest.json
    events.jsonl
    original-audit.jsonl
    features.jsonl
    references.jsonl
    ranking-contexts.json
  publications/<run-id>.json              # immutable final receipt
  verifications/<verification-id>.json    # independent signed/identified review
  projections/<receipt-id>.json           # append-only DB write/reconciliation receipt
  evaluations/<evaluation-id>/            # inputs, exclusions, config and results
```

Every run file except manifest is listed and hashed by manifest. The publication
receipt references manifest's hash; avoid a manifest self-hash/circular reference.
Shared objects are referenced by content hash, never by a mutable latest alias.

Specify canonical UTF-8 JSON: sorted string keys, fixed separators, no BOM,
normalized UTC timestamps, ISO dates, strict finite numbers and one LF terminator.
JSONL sorts by stable event ID; semantically unordered ID collections sort, while
feature order/session order and other meaningful arrays remain preserved.
Reject duplicate JSON keys, path traversal, absolute paths and symlink escape.
Preserve original raw input bytes as separate hashed objects where normalized
serialization could otherwise hide source differences. Determinism applies to
identical logical contents, not distinct execution IDs/timestamps.

## 5. Immutability, publication and failure recovery

Recommended minimal implementation is local append-only bundles for nonproduction
validation, with no claim that filesystem permissions are tamper-proof. Production
storage choice requires approval: durable versioned object storage with enforced
write-once retention/access policy is preferable to ephemeral Render or /tmp disk.
Hashes detect changed bytes relative to a trusted root; they do not establish
originality, chronology or protect against replacing both manifest and receipt.
Anchor receipt hashes in an independently controlled append-only ledger and/or
signed operator/verifier receipts with controlled keys. Never store keys in bundles.

Publication protocol:

1. Reserve a fresh opaque run ID; capture in a unique staging attempt. Pin or
   capture immutable input snapshots before calculation, recording the exact
   snapshots consumed. Do not archive inputs by re-querying mutable sources after
   scoring. Include model/preprocessing and mapping snapshots in this binding.
2. Copy exact inputs/model/audits, validate schema, referential integrity, numeric
   scales and temporal claims. Missing evidence is recorded, not fabricated.
3. Hash final bytes, write manifest last, flush/fsync where supported and verify
   dependency closure by re-reading retained objects. Verify their digests against
   the pinned consumed snapshots; fail publication if they differ.
4. Publish using create-if-absent semantics: atomic rename with no replacement
   on a supported same-filesystem backend, or conditional receipt creation after
   immutable object upload on object storage. Ordinary overwrite-capable rename
   is insufficient; storage adapter must test collision/race behavior.
5. Readers discover only valid final receipts and verify every referenced hash.
   Final bundles are never edited, including status fields.

A repeated ID with identical manifest hash is an idempotent retry; different
contents fail as a collision. Corrections/backfills use a new run ID and lineage
link, preserving the old run and reasons. Failed attempts stay unpublished and
are recorded separately; cleanup only follows approved retention policy.

Archive publication and PostgreSQL commit cannot form one atomic transaction.
Proposed later integration: archive validated computation first, then call existing
caller-owned persistence, then append a persistence receipt only after the outer
transaction commits. `persist_signals()` performs a savepoint and flush, not the
final commit; returning from it is not evidence of durable persistence.
Persistence receipts distinguish `write_attempted`, `commit_confirmed` and
`unknown`, each bound to the run/payload digest and transaction attempt.
A successful `commit_confirmed` receipt must never precede outer commit.
If the outer transaction rolls back after a successful helper return, retain only
attempt/failure evidence, not a success receipt. A crash before commit leaves an
attempt whose durable outcome is unknown until authorized reconciliation.
If DB write fails,
the archived run remains valid computation evidence but not evidence of serving.
If receipt recording fails or the process crashes after DB commit, projection
state is unknown to the archive until
an authorized reconciliation verifies it; never rerun scoring to repair a receipt.
A publication failure blocks that runner's persistence path under a separately
approved operational policy, without changing calculators or existing callers.
Do not introduce a hidden commit, route side effect or scheduled job.

Security: separate writer/verifier/reader roles, private encrypted storage,
allowlisted fields, no credentials/DSNs/environment dumps/owner names in public
artifacts. Keep restricted source evidence in controlled storage and publish only
redacted derivatives with their own hashes and lineage. Establish retention,
backup restore tests, access logging and approved deletion/legal-hold policy before
production; deletions create independent tombstones, never rewrite retained runs.

## 6. Temporal availability and leakage safeguards

- Record execution time independently of historical cutoff. A retrospective run
  with today's model cannot become historically eligible by changing a date.
- For predictive market inputs verify strictly pre-information-date prices;
  public_event_day must be the first supplied expected session after information.
  Validate source publication and revision evidence separately from price dates.
- Preserve training/validation membership and outcome endpoints; verify the strict
  30-session purge before the next partition. Test data never participates in
  model selection. Record selection/freeze chronology and preprocessing identity.
- Historical comparators require both earlier public information and complete CAR30
  strictly before the focal information date, including retained partial S evidence.
  Retain pseudo-event eligibility, calendar coverage and replicate diagnostics.
- Focal future CAR is a later outcome, not a prediction-time predictor. Store newly
  observed outcomes in a new linked artifact/version, never add them to the frozen
  decision evidence or require focal future CAR for contemporaneous scoring.
- Separate financial source availability from system computation/first observation.
  A newly computed value can derive solely from earlier data, but is not proof an
  original score existed earlier. Reviewer classification must distinguish original
  prospective observations, retrospective reconstruction and synthetic fixtures.
- Frozen S&P 100 membership remains survivorship/selection biased. Retain the exact
  universe/sector map and disclosure; do not label it historical index membership.

## 7. Offline evaluation integration

Keep `backend/research/provisional_score_evaluation.py:evaluate_c_masking` unchanged.
A future separate read-only adapter/verifier should:

1. Verify trusted publication root, schemas, complete hash closure, unique identities,
   source binding and temporal/model evidence. Hash validity is necessary, insufficient.
2. Produce a reviewer-controlled verification receipt listing each decision,
   evidence reference, verifier/version and exclusions. Never set approval flags
   merely because supplied timestamps precede a cutoff.
3. Map only supported records as follows; incomplete vectors remain exclusions.

| Harness input | Verified artifact source |
| --- | --- |
| research_event_id / ticker / information_date | Event identity and verified original cutoff |
| ranking_context | Context manifest identity plus verified membership; group by context AND information_date |
| evidence_kind | Historical only after verified origin classification; synthetic stays synthetic; reconstructed records are excluded from primary historical evaluation |
| components A/C/M/S/D | Exact original finite [0,100] values, M already scaled |
| official_score | Original insider_edge_score, with existing 1e-9 formula agreement |
| provenance.run_id / artifact_id | Original run ID and event-evidence artifact reference (bounded safe identifiers) |
| provenance.model_available_at | Supported model availability date, not training date or model name |
| provenance.components[name].observed / available_at | Reviewed original observed evidence and supported historical availability; no default true |
| provenance.reviewed_no_lookahead | Authorized independent temporal review result, not automatic schema success |

The harness accepts date-only fields and does not authenticate them. Preserve full
UTC timestamps in the archive; reject unsupported intraday claims rather than hide
them through date truncation. Retrospective reconstructed evidence must remain
outside primary evaluation even if its inputs were historically public.

Retain evaluation input bytes/hashes, source manifests/verification receipts,
preregistered minimum_group_size/top_k, harness commit/configuration, exclusions
and result hashes. No cross-date ranking comparison or outcome-dependent selection.
Track missing and unsuitable groups explicitly. Successful verification does not
remove selection bias, dependence or guarantee adequate sample size.

## 8. Staged implementation plan (not executed)

| Stage | Likely files | Dependencies and tests | Risks, rollback and coordination |
| --- | --- | --- | --- |
| 1. Artifact schemas/validation | New `backend/app/evidence/schemas.py`, `serialization.py`; `backend/tests/test_evidence_schema.py`; design refinement | No required new dependency; test required/null fields, units, duplicates, canonical bytes, numeric round trips, path safety, schema evolution | Person 2 owns quant fields; Person 1 reviews source/security. Revert new module without changing scoring; approve schema before capture |
| 2. Read-only integrity verifier | New `backend/app/evidence/verification.py`, `backend/scripts/verify_scoring_evidence.py`, focused tests | Stage 1; test corrupt/missing objects, replaced roots, unknown versions, temporal contradictions, untrusted attestations, no writes/network by default | Trust-root/storage approval required. Remove standalone tool without affecting serving |
| 3. Capture/publication integration | New `backend/app/evidence/capture.py`, storage adapter and explicit runner; narrowly reviewed hooks around `build_signals`/`persist_signals`; tests | Stages 1–2 and approved durable storage/model serializer; golden output equality, unchanged score/payloads, incomplete evidence, crashes/collisions/concurrency, DB/receipt divergence and rollback | Person 1 transaction/storage coordination, Person 2 ML serialization; no database/API changes unless separately approved. Disable new runner/capture hook; retain published artifacts |
| 4. Authorized prospective nonproduction validation | New test fixtures/integration tests and runbook | Explicit authorization, sanitized immutable test inputs; restore/reverify, missing components, calendar gaps, unsupported mappings, reproducibility and failure injection | Synthetic tests prove software only. Separate authorized real prospective runs from fixtures. Stop capture/persistence on failure; no production rollback or historical backfill |
| 5. Verified offline evaluation | New `backend/research/verified_evidence_adapter.py`, adapter tests, research report | Independent verification receipts and sufficient original complete records; mapping/scaling, exclusions, mixed contexts, future models, revisions and reproducible results | Reviewer preregisters populations/thresholds; no score-policy change. Withdraw evaluation version by append-only notice, retain originals |

No implementation stage authorizes production access, artifact deserialization,
model fitting, ingestion, migrations or scheduling. Serialized sklearn pipelines
may require executable pickle-compatible formats; choose a reviewed format,
restricted trusted-artifact loader and exact compatibility constraints before use.
Integrity verification alone should hash model bytes without deserializing them.

## 9. Open maintainer decisions

1. Durable storage backend, trusted root/signing mechanism, retention period,
   restoration objectives and operator/verifier access responsibilities.
2. Exact runner ownership and opt-in archive-before-persistence failure policy;
   reconciliation mechanism for independent archive and DB transactions.
3. Model/preprocessing serialization and dependency compatibility; no current
   model loader should be assumed sufficient for archival replay.
4. Availability attestation standard, evidence authority and review process,
   including source revisions and original versus reconstructed classifications.
5. Allowed source evidence/redaction fields, private canonical-identity handling,
   archive volume and secure retention of complete dependency closure.
6. Ranking-context policy/version, population membership and preregistered
   research criteria. No new numerical minimum or renormalization rule is proposed.
7. Issue numbers/human owners for the small implementation PRs. This document
   has no assigned new issue number; do not invent a closing line.

## 10. Acceptance criteria and design validation

- Original run/evidence/model/input bytes remain retrievable by immutable references;
  a second run/revision cannot overwrite an earlier bundle.
- Independent verifier detects corruption, broken lineage, missing dependencies,
  identity/cutoff contradictions and unsupported provenance without scoring or writes.
- Timestamps distinguish execution, source availability and claimed historical
  decision time; unknown evidence cannot pass primary evaluation gates.
- Capture retains all original statuses/reasons/audits and matches existing scoring
  results exactly; current serving persistence remains a separate projection.
- Failure/collision/restore tests demonstrate publication atomicity at the chosen
  backend and explicit unknown persistence states.
- Evaluation inputs bind to reviewed original runs and compatible ranking contexts;
  synthetic/reconstructed/incomplete/unverified records do not enter primary summaries.
- No production provisional-score change follows from adopting archive tooling.

This deliverable is one documentation file. Validate Markdown section/table/fence
structure, final newline, new-file whitespace and Git scope. Backend tests are not
required because no executable source, dependencies or contracts are changed.
No scoring, training, ingestion, deployment or historical artifact reconstruction
is part of this step. Await review before any commit, push or implementation.
