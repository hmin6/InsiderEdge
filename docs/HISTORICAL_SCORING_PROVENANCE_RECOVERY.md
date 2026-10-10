# Phase 3 Step 3 — historical scoring provenance recovery

## 1. Executive summary and audit scope

Pinned main: `ee1abd746808a844be0e3e95c856296590f07120`.
Branch: `quant/phase3-historical-evidence-recovery`; isolated worktree:
`/tmp/ie-phase3-historical-evidence-recovery`. Phase 3 Step 1 merged as PR #97;
Step 2 merged as PR #102 (`8d54434`), containing `cd56b88` and the offline harness.

**Zero historical component vectors have independently verified provenance;
zero primary-evaluation records are established as eligible.** Nine complete
latest-event vectors remain candidates, not eligible historical evidence.
Production provisional scoring remains no-go.

This is a documentation-only local/repository audit. It used committed source,
documentation, known project worktrees and retained `/tmp/ie-phase2-audit/`
extracts. No private teammate directories, credentials, production databases or
external data services were accessed. Git metadata was fetched only to verify
main and merged research. No original scoring jobs, backfills or training ran.

## 2. Artifact inventory

Status terms: **Verified** means directly inspected existence/content or code
behavior; **Partially verified** means some evidence exists but original temporal
lineage is missing; **Unavailable** means absent in authorized local locations;
**Not assessed** means no authorized access attempted. File hashes establish
local content identity, not authenticity of original scoring inputs.

| Location / type / schema | Coverage and dates | Run/model/cutoff evidence | Classification / status |
| --- | --- | --- | --- |
| `/tmp/ie-phase2-audit/companies.json`, JSON list of ticker/sector/latest-day/latest_signal | 80 ticker records; 25 latest Signals, 9 complete. Signal public days 2026-01-16–2026-09-22 | No run_id, model artifact, information_date or per-component availability in this extract | Later sanitized public-API extract; existence/counts Verified, historical lineage Partially verified |
| `/tmp/ie-phase2-audit/radar.json`, JSON object containing Radar items | 80 latest events; 9 complete, 16 insufficient, 55 not_scored availability | Current display values/status, not original run identity | Later extract, Partially verified |
| `/tmp/ie-phase2-audit/histories.json`, JSON keyed by 80 tickers | Prior audit: 458 distinct event IDs and ticker/public-day pairs; information dates 2020-01-06–2026-09-21 | Event information dates, not component-generation attestations or full Signal history | Later extract, Partially verified |
| `/tmp/ie-phase2-audit/cases.json`, list; `cases_enriched.json`, list | 16 missing-C latest-event cases | API evidence plus derived reference-count diagnostics; not archived original reasons | Later/derived, Partially verified |
| `/tmp/ie-phase2-audit/summary.json`, object; `history_summary.json`, object | 10 and 7 top-level summary fields respectively; aggregate counts above | Collection timestamps and counts only | Derived summary, Verified locally; not original scoring manifest |
| `docs/ACTIVITY_SCORE_COVERAGE_AUDIT.md` | Per-case audit and original-source limitations | Documents explicit zero baselines and inferred reference limitations | Committed derived report, not original run output |
| `docs/DEMO_PLAN.md:113–215` | Narrative: 458 feature rows; 39 persisted Signals, 14 complete | Logistic Regression C=.1; last validation outcome 2026-01-14; subsequent-only probabilities described | Historical operational account, Partially verified; original execution not independently reproduced |
| `data/sec_cache/issue35_prepare_quant.py`, original price/event/run manifests, model/evaluation checkpoints | No files available; original checkout has no `data/` directory | Original run IDs/artifact hashes unknown | Unavailable locally; not proof of loss elsewhere |
| Known `/tmp/ie-activity-diagnostics-*` manifests/backups/worktrees | Three implementation-file hashes and tested Git bases | Code validation, not scoring data/model provenance | Verified implementation artifacts; ineligible as historical observations |
| Known Phase 3 worktrees, research code/tests | Synthetic fixtures and research documentation | Fake attestations explicitly labelled synthetic | Synthetic, Verified; no real historical observations |
| Current or historical production DB, operator workstation, object-store/backups | Counts/history not read in this task | Unknown until authorized recovery | Not assessed |

No original scoring-run output, full `SignalBatch.audit`, original canonical-owner
map or fitted model checkpoint was recovered. Repository filename search including
ignored files (excluding environments, generated caches and secret configuration)
found only the authoritative documentation manifest, not a scoring manifest.

Retained extract content hashes (SHA-256):

```text
companies.json e17df990f64d92fec30ca39f813dd892cff9877af3ef394a7a37a19f72b04f75
histories.json 24be80c04e0aee316db5459fd78a5d82673dccdd1dfd736ca5516b9cb4904fd4
radar.json ce43d60b07b69ca7df46875618b39d9166758a675dd2fd91924b312778ecbc4a
cases.json e3083f05e75a4639752b7245859835d33830639b9279697442680a243c380743
cases_enriched.json 675f64e1c0e93d88e5a921aed4bb1afa5d1faedaa59a2f5a5e4378c88abed944
summary.json 2b0f35f9cb679244394da7b6a018e15a2ef99231c99c900d175ac8319d2fdc53
history_summary.json ac044dd140f28f29ae09cf41d91853800ede0940d4ea9da913383639d7d50e46
```

Collection was 2026-10-10 19:32:32–19:33:39 UTC. Temporary paths are not durable
archives. Do not infer a historical cutoff from collection or filesystem times.

## 3. Historical pipeline map and component lineage

```text
SEC normalized raw transactions + cached reporting-owner evidence
  + frozen ticker/sector universe + adjustment-aware price/session observations
  -> events.build.build_dataset / repository.build_from_database
  -> research events, source-transaction membership, feature metadata
  -> quant.features.build_event_features
  -> A: anomaly.build_anomaly_scores
     C: activity.build_activity_scores (explicit scalar canonical-ID map)
     D: dislocation.build_dislocation_scores
     event_study -> CAR30 -> statistical_validation.build_statistical_validations -> S
     ml.dataset -> purged splits -> training.train_dataset -> frozen selection
     training.predict_selected -> event probability -> M=probability*100
  -> signal_integration.build_signals -> official composite score + transient audit
  -> persist_signals -> Signal + bound contract evidence in event metadata
```

These entry points are verified in source; the original invocation/adapter belongs
to the absent ignored harness. Do not treat this diagram as recovered execution
logs. A uses five-dimensional Mahalanobis/chi-square calibration; C uses buyer/rate
percentiles; D uses sector-gap/drawdown percentiles; S uses historical bootstrap
and randomized timing. No calculators were executed during recovery.

Event building selects qualifying P purchases, excludes unresolved amendments,
deduplicates source keys and groups ticker/public day (`events/build.py:70–114`).
It retains source transaction IDs/accessions and filing dates in feature metadata
(`:165–178`). Owner evidence uses supported reporting-owner CIKs, never names.
The C adapter's original mapping remains unavailable; do not invent it from counts.

`ResearchEvent` has unique ticker/public-day and primary research-event ID;
`Signal.research_event_id` is unique and foreign-key bound (`db/models.py:65–82,
125`). Signal persistence checks event ID/ticker/public day/information date
(`signal_integration.py:247–253`). This establishes intended join integrity, not
original-run provenance for a later snapshot. API extracts may omit event IDs;
any recovered ID must be verified against original metadata, not inferred solely
from a display ticker/date convention.

## 4. Model, dataset and cutoff findings

DEMO_PLAN:145–160 describes 343 train (2020–2024), 61 validation (2025), 35 completed
2026 test rows after purging 15 rows. It reports Logistic Regression C=.1 selected
on validation, threshold .5 and once-only frozen test evaluation. Checkpoints are
explicitly ignored under `data/sec_cache/`; exact filenames/hashes/run identity
are not supplied. This account is useful recovery guidance, not an independently
verified artifact timeline.

DEMO_PLAN:184–215 says only 39 events after last validation outcome 2026-01-14
received production probabilities; 419 earlier events were not backfilled with
that later-selected model. Recover the model selection/freeze time and original
39-event membership before attesting this claim. An information boundary after
the validation outcome is necessary but does not prove actual artifact availability.

Verified integration guards: label-independent raw-feature provenance, exact
component alignment and first post-information session (`signal_integration.py:
130–144`); comparator metadata and complete outcome strictly before focal
information date (`:157–180`), including retained partial statistical evidence;
current CAR display cannot exceed observation cutoff. These guards do not certify
input origin, historical price revisions, calendar completeness or model freeze time.

`persist_signals` performs full replacement/upsert of current nullable fields and
bound event evidence (`:233–271`); existing signal ID/created_at are retained.
Therefore code **permits** later revisions without a full version history. Whether
any original production evidence was overwritten is **Not assessed**, not a
confirmed fact. A preserved created_at cannot certify current component values
existed at that time. Full component dictionaries in `SignalBatch.audit` are
transient; only contract evidence and comparator provenance are persisted.

Frozen `config/universe.csv` supplies current company/sector references. It is
not historical membership reconstruction. Actual historical ranking candidates,
filters and run membership are absent; latest Radar rows are not that universe.
Retrospective CARs are display/outcome evidence, not prediction-time inputs.
Recomputing historical features with revised prices or a later model would create
new research results, not recover the original records.

## 5. Verification checklist and harness representation

| Requirement | Existing harness representation | Current evidence status |
| --- | --- | --- |
| Valid unique event identity | Nonempty ID/ticker; duplicate IDs rejected | Snapshot inventory partly verified; original source binding unavailable |
| Complete observed A/C/M/S/D | Exact five finite [0,100] values; observed attestations | Nine latest complete candidates; original observed lineage unavailable |
| Complete IES arithmetic | Formula check/optional official-score agreement | Can verify numerical consistency only; not historical availability |
| Original scoring-run identity | Supplied run_id; output provenance reference | Unavailable |
| Artifact/model reference | artifact_id and model_available_at | Original checkpoint and timeline unavailable; artifact role requires reviewer explanation |
| Known information cutoff | Strict ISO information_date | Historical event dates partly available; component binding unverified |
| Per-component availability | observed/available_at with no future dates | Unavailable in retained complete-vector extract |
| No temporal leakage | reviewed_no_lookahead plus date checks | Caller attestation, not independent verification |
| Ranking universe/context | context + information date grouping | Context string representable; original membership/policy manifest unavailable |
| Evidence authenticity/revisions | Caller retains immutable manifest/hash and reviewer evidence | Harness does not authenticate or version records |

The harness can represent supplied assertions and references, but cannot verify
that an ID is a real original event, that an artifact is authentic, that context
members actually competed, or that a revised value was known then. Do not weaken
gates or set review flags based on timestamps alone. No contract changes proposed.

## 6. Reconcile the retained 80-observation inventory

- 55 latest events have no matching Signal: component availability unevaluated.
- 16 stored latest Signals are incomplete: 14 missing C alone, two missing C/S.
- Nine have complete vectors: ABT, AXP, BA, BRK.B, CAT, INTC, MSFT, TMUS, UBER.
- Zero of these nine gained original run/component/model provenance in this audit.
- Zero observations are established as eligible for primary offline evaluation.

DEMO_PLAN's 39/14 inventory and current snapshot's 25/9 describe different scopes;
do not add them or assume the other five complete historical records are lost.
Full historical Signal history requires separately authorized access.

## 7. Recovery requests and responsible systems

Role ownership follows the locked Person 1 data/backend, Person 2 quant/ML split;
the identity of the original demo operator is not established. Ask the team who
ran the ignored harness rather than assuming a named operator.

| Required evidence | Why / likely project system | Accessible now / safe next request |
| --- | --- | --- |
| Exact ignored runner and run log/manifest | Reconstruct invocation, event selection, code version; original demo operator/Person 2 | Absent; request immutable redacted files and hashes, no execution |
| Original components and full audit for nine candidate IDs | Bind values/status/reasons to run and cutoff; quant-run archive | Absent; request targeted allowlisted export, not unrestricted source dumps |
| Frozen model/checkpoint and selection timeline | Prove model availability and preprocessing; Person 2 ML artifacts | Absent; request hash, feature schema, training/validation endpoints and freeze record; no retraining |
| Original price/calendar/event input manifests | Verify matching immutable inputs and completed sessions; Person 1 data/operator | Absent; request snapshot hashes, date coverage, provider adjustment policy and revision history |
| Transaction-owner adapter/source evidence | Verify unique buyers and no invented identities; Person 1 cache + Person 2 adapter | Absent; request transaction-bound evidence status/hash, not owner names or credentials |
| Ranking universe/run membership | Define legitimate cross-sectional populations; run operator/backend product | Absent; request member IDs, context/as-of date and filter policy |
| Original DB evidence/history or backup | Assess revisions/current bound metadata; authorized DB administrator | Not assessed; ask for bounded read-only redacted export or immutable backup extract, never credentials |

Recommended request: “For the nine candidate events, please provide existing
original run/component audit files, their hashes and input/model manifest
references, plus the contemporaneous cutoff and ranking membership policy.
Do not rerun scoring, backfill models or alter production to produce this evidence.
Redact credentials and personal owner details. If artifacts were not retained,
state that explicitly; retrospective reconstruction must be labelled separately.”

DB/object-store/operator-workstation reads need explicit authorization and can be
read-only; no such access is performed here. Prefer small redacted manifests over
unrestricted exports. Even a current DB export cannot recover audit never retained.

## 8. Remaining risks and next research step

Current fields and code tests do not independently establish original lineage.
Residual risks include retrospective model use, revised price inputs, incomplete
calendars/filings, missing owner mappings, overwritten audit, context-selection
bias, complete-case MNAR, frozen-universe survivorship and company dependence.

Next step: contact the original operator through the human owner with the bounded
request above. Hash recovered originals, verify value/source/cutoff binding, and
have an authorized reviewer attest only supported records. Preregister group sizes,
top-k and acceptance criteria before evaluating. If originals cannot be recovered,
retain the no-go decision; prospectively collect immutable evidence under a
separately approved workflow. Do not fabricate historical provenance to make the
harness return an available result.

## 9. Validation and safety

Documentation-only: no verification utility needed because no original artifacts
were found. Markdown structure/EOF and tracked/new-file whitespace checks are the
applicable checks. Production code, research harness and dependencies are unchanged.
No tests or scoring jobs are needed for this documentation-only change. Git status
and original unrelated-file hashes are verified at handoff. Nothing staged,
committed, pushed or deployed.
