# Phase 3 Step 2 — offline C-only masking evaluation

## Executive summary and environment

**No-go for production provisional scoring.** The offline harness is ready for
review, but no primary historical dataset meets the evidence gate. No empirical
accuracy or ranking-stability estimates are claimed. Missing evidence was not
repaired, invented or replaced with synthetic records.

Pinned main: `fbdb88a13bbec160af6d715e7d42b64f8827df1d`.
Branch: `quant/phase3-renormalization-evaluation`; isolated worktree:
`/tmp/ie-phase3-renormalization-evaluation`. Step 1 merged as PR #97 and its
research document is on main. Existing backend virtual environment, Python 3.13
on macOS; no dependency changes. The original checkout remains untouched.

## Evidence inventory and provenance assessment

Only authorized local/repository sources were inspected. No fresh external data
or production DB requests were made. Credential/private teammate directories were
not searched. Snapshot collection dates/hashes are in the committed activity audit.

| Candidate source | Record inventory | Primary-evaluation assessment |
| --- | --- | --- |
| `/tmp/ie-phase2-audit/companies.json`, `summary.json` | 80 latest events, 25 Signals: 9 complete, 14 missing C only, 2 missing C/S; 55 no matching Signal | Public GET snapshot 2026-10-10 19:32:32–19:33:39 UTC; Signal public days 2026-01-16–2026-09-22. Component/run cutoff attestations absent; zero established eligible records. |
| Retained histories/history summary and activity audit | 458 distinct research-event IDs and ticker/public-day groups | Event inventory, not 458 scored vectors. Historical Signal-vector coverage/cutoffs unknown. |
| `docs/DEMO_PLAN.md` | Historical account of 39 Signals, 14 complete | Narrative, not immutable row-level run evidence; not additive to snapshot counts. |
| Original `data/sec_cache/issue35_prepare_quant.py`, run/cache/mapping artifacts | Absent locally; original checkout has no `data/` directory | Not recreated. Record/vector counts unavailable. |
| Phase 2 exporter and validation manifests | Code/file hashes and synthetic tests | Not scoring-run observations. |
| Existing composite tests and new evaluation tests | Synthetic fixtures, including fake historical attestations for routing tests | Numerical correctness only; zero real observations. |

For the 80 latest-event observations, 16 fail complete-vector eligibility, 55
lack Signals, and nine complete cases lack sufficient historical provenance.
Thus **0/80 is established as primary eligible**. These are inventory exclusions,
not output from feeding reconstructed records to the harness. No actual historical
vectors were supplied to it in this task. Full/earlier Signal inventory remains
unknown, not zero. Prior audit verified unique snapshot event IDs; no silent
harness deduplication is allowed.

Snapshots are latest-only, non-atomic and selected by Radar coverage, frozen
universe, original model cutoff and component availability. They do not attest
original transaction-owner mapping, reference membership or model chronology.
Event dates alone do not establish absence of look-ahead. Original records were
not invented or reconstructed.

## Strict input and eligibility contract

`backend/research/provisional_score_evaluation.py` imports no production modules
and performs no IO. `evaluate_c_masking(records, *, minimum_group_size, top_k)`
accepts explicit mappings:

- Unique nonempty `research_event_id`, `ticker`, `ranking_context` strings.
- Strict ISO `information_date` as the historical cutoff.
- `evidence_kind`: `historical` or `synthetic`.
- `components`: exactly A/C/M/S/D, numeric finite [0,100], already scaled.
- Optional `official_score`: must match complete formula within absolute 1e-9.
  Without it, the formula defines the verified complete reference.
- Optional `provenance`: `reviewed_no_lookahead: true`, nonempty `run_id` and
  `artifact_id`, ISO `model_available_at` no later than information date, and
  `components` mapping each component to `observed: true` and ISO `available_at`
  no later than information date.

An authorized reviewer must bind those assertions to original component values,
source references and model timeline. This utility checks assertions, **not their
authenticity**. Upstream strict pre-filing market sessions and completed historical
S-outcome rules remain part of that review. It cannot reconstruct features or
independently prove source/calendar completeness.

Null components are explicitly excluded, never zero-filled. Malformed, boolean,
nonfinite/out-of-range components, ambiguous schemas, duplicate IDs, inconsistent
official scores and future-dated provenance raise errors. Missing provenance or
observed attestations excludes primary eligibility. Synthetic, provenance-incomplete
and attested historical rows remain distinct. Fake attestations in tests are not
real evidence. Missing original artifacts cannot be replaced by a model name.

## Method and output

`F=.25*A+.15*C+.30*M+.15*S+.15*D`.
Artificially mask C:
`P=(.25*A+.30*M+.15*S+.15*D)/.85`.

M is already on 0–100; never multiply it again. Full precision is retained.
Per-row output includes identity, ticker, cutoff and context, evidence category,
exclusion reasons, F/P, signed error P−F, absolute error, masked C and .85 coverage.
Output structures do not reference source mappings. Missing-component exclusions
are separate. No official scores are overwritten or production policies changed.

Summary controls are mandatory: `minimum_group_size>=2`, `1<=top_k<minimum_group_size`.
There is no default sample size claimed as scientifically sufficient. Maintainers
must preregister settings, uncertainty/error requirements and ranking contexts
before inspecting real results. Two-row tests are arithmetic fixtures only.

Groups are **ranking_context plus information_date**: unrelated dates never pool.
Caller must attest that observations actually competed at that cutoff; equal dates
alone do not establish that. Repeated tickers across dates are permitted and
require dependence-aware interpretation. Predeclared sector/time contexts may
stratify analysis; the harness does not automatically infer or pool strata.

Adequately sized historical groups report MAE, median absolute error, RMSE,
maximum absolute error, linearly interpolated p90/p95 errors and signed bias;
average-rank Spearman, strict inversions, comparable pair counts, tied-pair counts,
and top-k overlap count/fraction. Exact ties receive average ranks; constant ranks
produce null correlation with `constant_ranks`. Top-k ties break by ascending ID.
Undersized groups return null metrics/ranking and `insufficient_data`. Overall
`available` means at least one group meets caller settings, not production approval.
No empirical confidence intervals are claimed.

## Mathematical sensitivity, not empirical performance

`F=.85*P+.15*C`; hence `P−F=.15*(P−C)` and `|P−F|<=15`.
The bound is attained at observed A/M/S/D=100,C=0 (F=85,P=100) and
observed A/M/S/D=0,C=100 (F=15,P=0). Tests check both extremes and all-zero/all-100
cases. Synthetic inversion fixtures demonstrate possible rank reversals, not their
real-world frequency. This bound does not imply small typical error or stable ranks.

## Reproducible procedure and validation

From the isolated checkout's `backend/`:

```python
from research.provisional_score_evaluation import evaluate_c_masking

# Explicit immutable authorized evidence; settings must be preregistered.
result = evaluate_c_masking(records, minimum_group_size=approved_minimum,
                           top_k=approved_top_k)
```

Retain input hashes, source commit, reviewer attestations and context/threshold
policy with results. The function does not open files, query DBs, call networks,
fit models or write outputs. Local export is caller-owned. No later-model
probabilities may be backfilled into historical records.

Focused synthetic coverage includes formula/.85, M scaling, official verification,
missing C, boundaries, malformed/nonfinite inputs, duplicate IDs, temporal
provenance, synthetic separation, context/date grouping, metric arithmetic,
inversions/ties, deterministic JSON, nonmutation and blocked file/network IO.
Exact command results are appended below after validation.

## Historical findings, limitations and Phase 3 Step 3

**No empirical MAE, RMSE, rank correlation, inversion or overlap estimates are
reported.** No sufficiently attested historical input dataset exists locally.
Synthetic results, mathematical properties and real evidence remain separate.

Complete-case observations need not represent genuine C missingness. Zero baseline,
identity uncertainty and reference scarcity create structured, potentially MNAR
selection. Frozen-universe survivorship bias, repeated firms, overlapping histories
and retrospective attestation add risks. Do not tune thresholds to maximize coverage.

Next: recover original run/component snapshots, canonical mapping/adapter evidence,
policy/model IDs and training/selection timeline. Have an authorized reviewer bind
attestations to immutable vectors. Preregister contexts, sample/independence
requirements, top-k, accuracy/rank acceptance criteria and held-out time periods.
Then run masking, with genuinely missing cases assessed separately. Use same-day
grouping and outcome purging if future-return validation is added; focal future
outcomes are not required for score-fidelity masking itself.

**No-go for API/UI or production provisional scoring.** Retain current complete,
S-only permitted partial and insufficient-data policy. Phase 3 Step 3 should focus
on evidence recovery and preregistered evaluation, not imputation or deployment.

### Executed validation

Using `/Users/allen/InsiderEdge/backend/.venv/bin/python` from the isolated
checkout's `backend/`:

```text
-m pytest -q tests/test_provisional_score_evaluation.py tests/test_insideredge_score.py
128 passed in 0.25s (52 new synthetic cases; 76 existing composite cases)

-m pytest -q
906 passed, 6 subtests passed in 34.77s

-m compileall -q research tests
passed
```

No warnings were reported. Tracked and individual untracked-file whitespace checks
passed; no-index new-file comparisons return difference exit code 1 without
whitespace diagnostics. Markdown fence/EOF checks passed. Only the research module,
its tests and this report are new; production code is unchanged. Nothing staged,
committed or pushed. The baseline was pinned throughout testing.

## Final research hardening (additive output changes)

Eligible historical rows now include `provenance_references`: supplied `run_id`,
`artifact_id`, `model_available_at` and a detached `component_available_at` mapping.
Other row categories have null references; absent evidence is never inferred.
Only these fields are copied, not raw provenance/source contents. Identifiers must
match `[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}`; supplied malformed/empty identifiers
raise sanitized errors, while absent/null identifiers exclude historical eligibility.
This bounds format, **not confidentiality**: operators must supply non-sensitive
artifact references, never credentials. The utility cannot authenticate identifiers
or recognize every secret embedded in an otherwise valid identifier.

Missing-component exclusions additionally preserve supplied valid `ranking_context`
and `information_date` for per-context exclusion accounting. Missing/invalid
context/date still fails validation rather than inventing grouping metadata.
Provenance-incomplete complete rows retain their existing category/reasons and
context; neither category of exclusion contributes primary summaries.

Pairwise ranking now uses streaming counters with O(1) extra pair-count memory,
instead of O(n²) pair lists. Exact runtime remains O(n²), with O(n) rank/top-k
storage. Correlation, strict inversions, tie counts, top-k and grouping semantics
are unchanged. Existing output fields are preserved; provenance and exclusion
metadata fields are additive research-schema changes.

New synthetic regressions cover detached provenance references and raw-source
omission, missing individual provenance fields, malformed structures/sanitized
errors, missing context/date, empty input, mixed eligible/excluded accounting,
partial ties (hand-derived Spearman 5/6), streaming/list-reference equivalence,
and hand-calculable median/max/p90/p95 errors. These are correctness tests, not
historical evidence. Zero historically eligible observations remain established;
production implementation remains no-go.

Latest observed main is `01876a4dbf81f6549e04807134ef688cce778d03`: newer Snowflake
year-context diagnostics and Radar styling changes, with no overlap in research
files, dependencies or scoring contracts. This hardening stays pinned to
`fbdb88a`; it is not integration validation against the newer main.

Hardening validation, same existing virtual environment and pinned baseline:

```text
-m pytest -q tests/test_provisional_score_evaluation.py tests/test_insideredge_score.py
145 passed in 0.14s (69 research cases; 76 composite cases)

-m pytest -q
923 passed, 6 subtests passed in 34.29s

-m compileall -q backend/research backend/tests
passed (run from worktree root)
```

No warnings reported. Tracked/new-file whitespace and Markdown structure checks
passed. Original unrelated-file hashes remain unchanged. No production files,
dependencies or official scoring policies changed; nothing staged or committed.

## Pre-PR integration validation

The research branch fast-forwarded safely to main
`01876a4dbf81f6549e04807134ef688cce778d03` before committing. No overlapping
research, scoring-contract, test-infrastructure or dependency changes were found.
The original research baseline above remains the audit source reference.

Using the existing backend virtual environment from the updated worktree:

```text
-m pytest -q tests/test_provisional_score_evaluation.py tests/test_insideredge_score.py
145 passed in 0.11s

-m pytest -q
969 passed, 6 subtests passed in 35.69s

-m compileall -q research tests
passed
```

No warnings were reported. Markdown and tracked/new-file whitespace checks passed.
Production source/contracts/dependencies match main unchanged. These tests validate
research tooling, not historical evidence or production provisional-score readiness.
