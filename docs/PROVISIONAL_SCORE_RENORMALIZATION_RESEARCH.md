# Provisional-score renormalization research — Phase 3 Step 1

## 1. Executive summary and baseline

Research baseline: `7e7698a7a878f8d363788f577da33a6ec9d8c4c7`, refreshed main;
branch `quant/phase3-provisional-score-research`, isolated worktree
`/tmp/ie-phase3-provisional-research`. Phase 2 diagnostics merged through PR #92
(`4416d7e`); its implementation commit `c201a45` is an ancestor of this baseline.
No production behavior is changed. This document proposes no approved new policy.

**No-go for production implementation now.** Retain Policy D (current policy).
Policy A (C alone missing) is the preferred next research hypothesis, not a
production recommendation: it targets observed coverage without dropping the
largest or predictive component. Evidence is too small and selectively observed
to justify a displayed or default-ranked provisional estimate.

## 2. Verified scoring contract

Sources: `docs/MODEL_SPEC.md` §§4–12; `docs/DECISIONS.md`;
`backend/app/quant/insideredge_score.py:12–16,48–106`; corresponding tests;
`backend/app/services/signal_integration.py`; API/DATA_SCHEMA contracts.

| Component | Valid composite input | Construction and historical boundary |
| --- | --- | --- |
| A | 0–100 | Five-dimensional Mahalanobis anomaly, chi-square df=5; strictly earlier reference events, sector/frozen-universe fallback. |
| C | 0–100 | Mean buyer/rate-ratio weak empirical percentiles; recent [t−29,t], historical [t−394,t−30], earlier-only references; minimum 10 usable values per component. Zero historical baseline is undefined, not zero support. |
| M | 0–100 | Selected model event probability in [0,1] multiplied by 100 exactly once. Raw pre-event predictors, training-only preprocessing and purged temporal splits; artifact availability is caller-attested. |
| S | 0–100 | Equal bootstrap/randomization supports using eligible historical CAR30 comparisons; full outcomes must predate focal information date. Focal future CAR30 is not required. |
| D | 0–100 | 60% sector-gap90 percentile plus 40% drawdown-magnitude percentile; aligned prices strictly before filing information date; frozen universe and minimum 10 valid component references. |

Official `IES = .25 A + .15 C + .30 M + .15 S + .15 D`.
Complete requires all five components. The sole permitted partial is S unavailable
with reason strings restricted to `fewer_than_10_eligible_comparable_events` and
its `bootstrap:`/`randomization:` prefixes. Its denominator is .85. Other S
failures, or any unavailable A/C/M/D, produce null `insider_edge_score` and
`score_status=insufficient_data`. Missing components and reasons are retained.
None is missing; NaN/infinity, bools and out-of-range inputs are rejected by the
composite scorer. Valid zero is observed evidence. No premature score rounding.

`core_reads.py:12–42` binds the latest event to its exact Signal; no Signal yields
`availability_status=not_scored` while retaining legacy
`score_status=insufficient_data`. This is distinct from evaluated failures; no
event is distinct again. No older Signal is borrowed for a newer event.

Frontend presentation uses two decimals. At this baseline the score card also
uses direct `toFixed(2)` calls, while shared `utils/format.ts` handles other
numerical displays, missing values, negative zero and small p-values. That is a
presentation consistency concern, not a change to scoring arithmetic. Sorting
must continue to use raw numeric values, never formatted strings.

Signal columns retain component scores, probability, official score and status.
Event metadata retains bound contract evidence and historical provenance; full
`SignalBatch.audit` is transient. Original reference membership, source identity
mapping and complete run evidence cannot be reconstructed from Signal columns.
Code-level temporal guards do not prove original input/calendar completeness or
that a model artifact existed at every historical cutoff. No formula mismatch
was found; new provisional behavior would require explicit contract approval.

## 3. Available data inventory

No new external API or production DB reads were made. Inventory below uses the
retained sanitized `/tmp/ie-phase2-audit/companies.json`, `summary.json` and the
committed `docs/ACTIVITY_SCORE_COVERAGE_AUDIT.md`. Collection was public GETs on
2026-10-10 19:32:32–19:33:39 UTC, not an atomic snapshot. Dataset hashes and
per-event C diagnostics are recorded in that audit. These are later API extracts,
**not original scoring-run artifacts or full historical Signal inventory**.

| Observed inventory | Count |
| --- | ---: |
| Latest events inspected across Radar tickers | 80 |
| Matching latest Signals | 25 |
| No matching latest Signal | 55 |
| Complete vectors / official complete | 9 |
| Official partial | 0 |
| Official insufficient_data | 16 |
| Missing A / C / M / S / D among stored latest Signals | 0 / 16 / 0 / 2 / 0 |
| Missing C only | 14 |
| Missing C and S | 2 |
| Missing multiple components | 2 |
| Research events in public ticker histories | 458 |

The 55 no-Signal events have **unknown unevaluated component availability**; do
not count them as five observed component failures. The 25 Signal public days
range from 2026-01-16 to 2026-09-22. Full global historical vector counts, earlier
Signals, exact original reasons and eligible historical evaluation counts are
unknown. DEMO_PLAN's 39 Signals/14 complete observations describe a different
historical run inventory and must not be added to these 25/9 counts.

Nine C-unavailable cases explicitly report zero historical rate; seven have
reference limitations consistent with current public history. The latter are
inferred diagnostics, not recovered original reason arrays. A/C/M/S/D missingness
is structured by history, identity, sample size, calendar and model availability,
not random censoring. Frozen-universe selection/survivorship bias and latest-only
sampling further limit representativeness. Tests are synthetic behavioral evidence,
not measured real-world performance. Original runner/cache/manifests/mappings are
absent locally per Phase 2 recovery inventory; no missing artifacts were recreated.

## 4. Research-only formula and worked examples

For valid observed components O, original weights w and coverage W=sum(w_i,i∈O):

`P = sum(w_i*x_i,i∈O) / W`, only when W>0.

Require finite [0,100] components and affirmative availability; null/nonfinite,
malformed, imputed or unverified values do not enter O. M is already probability
×100 in the component vector; never multiply that value again. Missingness is not
evidence of a low/high value. Invalid records should fail research eligibility,
not silently become a different missingness pattern.

If omitted components have weighted mean U, complete score F satisfies
`F = W*P + (1-W)*U`; therefore `P-F = (1-W)*(P-U)` and
`|P-F| <= 100*(1-W)`. Given observed evidence alone, the hypothetical complete
score lies in `[W*P, W*P + 100*(1-W)]`. This is a deterministic identification
bound, **not** a confidence interval or an imputation.

| Sole omitted component | W | Effective weights of retained components | Worst-case absolute error bound |
| --- | ---: | --- | ---: |
| A | .75 | Original weights divided by .75 | 25 |
| C | .85 | Original weights divided by .85 | 15 |
| M | .70 | Original weights divided by .70 | 30 |
| S | .85 | Original weights divided by .85 | 15 |
| D | .85 | Original weights divided by .85 | 15 |

Synthetic example: A=80,C=20,M=60,S=40,D=70 gives F=57.5.
Mask C: numerator=54.5, W=.85, P≈64.117647; error≈+6.617647.
Mask M: numerator=39.5, W=.70, P≈56.428571; error≈−1.071429.
Small error in that M example is accidental, not evidence that missing M is safe.
Mask C and S: numerator=48.5,W=.70,P≈69.285714; error≈+11.785714.
These are illustrative arithmetic, not historical simulation results.

Missing C may encode a zero baseline or unsupported identities, while missing M
removes the largest component and the only explicit learned event probability.
Renormalization changes the estimand to the observed subset; identical totals
can summarize different evidence. Multiple missing components increase the bound,
change relative influence and make cross-pattern rankings difficult to interpret.
No fixed scaling restores the omitted information.

## 5. Candidate eligibility policies

| Policy | Criteria / coverage | Advantage | Risks, requirements and rejection conditions |
| --- | --- | --- | --- |
| A: conservative research | C alone absent; valid A/M/S/D; W=.85 | Targets 14 observed latest cases without dropping M | Requires recorded C reasons, historical provenance and adequate complete-case evaluation. Reject unknown corruption, invalid retained inputs, weak comparability or unacceptable rank distortion. Not official S-only partial. |
| B: one missing | Exactly one component absent; W=.70,.75 or .85 | Simple broader eligibility | Analyze each component separately. Missing M must not imply an ML-assisted complete equivalent; exclude from default display absent separate evidence. Missing S for approved history reason already uses official partial; other S failures must not be laundered. Reject unsupported component strata. |
| C: weight minimum | Explore W≥.90,.85,.80,.75, with explicit allowed patterns | Transparent evidence coverage | .90 admits only complete; .85 admits C/S/D-only omissions; .80 same discrete patterns; .75 additionally A-only; .70 admits M-only and pairs among C/S/D. Weight alone ignores evidence quality. Requires pattern-specific validation; reject thresholds chosen for coverage alone. |
| D: current baseline | Complete or narrowly permitted S-only partial; otherwise null | Preserves approved interpretation | Retains unavailable official scores; communicate not-scored separately. Preferred production policy until evidence supports a change. |

No minimum-weight or distinct-ticker threshold is approved by this research.
Observed-weight coverage is not statistical confidence. Even Policy A eligibility
counts are provisional data checks, not a projection of reliable future coverage.

## 6. Leakage-safe evaluation design and evidence decision

**No historical performance estimates produced.** Nine latest complete vectors,
without original run provenance or independent temporal cohorts, cannot support
credible sector/time stratification, tail-error estimation or policy selection.
Arithmetic masking could be calculated, but would be exploratory in-sample
sensitivity only, not evidence for deployment. Do not fabricate MAE/RMSE/ranks.

Recover immutable event-level vectors, information dates, component statuses and
reasons, run/policy/model IDs, training/selection timeline, calendar evidence and
reference membership first. Verify one row per event and official formula;
separate official partial from complete reference targets. Require contemporaneous
component availability, not hindsight-generated predictions. Historical S may use
only comparator outcomes completed strictly before the focal information date.
No focal future outcome is needed for the score-fidelity masking experiment.

Pre-register allowed missingness patterns and acceptance criteria with maintainers
before looking at held-out results. Split chronologically by information date,
keep same-date groups together, and purge outcome overlap if downstream predictive
labels are used. Choose policy/thresholds on development periods only. Freeze
before held-out evaluation; account for repeated ticker dependence and overlapping
histories in uncertainty reporting. Never fit preprocessing/imputation on holdout.

For each complete vector, mask one component and predefined multiple patterns;
compare P to its original official F. Report paired MAE, median absolute error,
RMSE, signed and high-percentile errors, Spearman rank correlation (ties explicit),
ranking inversions, and top-k overlap with predeclared k and tie rules. Compare
within historically available cross-sections, not events pooled across years.
Report by component/pattern, period and sector only with adequate group sizes;
record sample counts and no-estimate cases. Bootstrap uncertainty must respect
company dependence; the exact evaluation sample requirement needs research approval.
Score fidelity is not future-return validity or a causal inference.

Artificial masking does not reproduce genuine MNAR missingness. Compare retained
feature/sector/time distributions of complete and missing cases, report unsupported
strata, and do not extrapolate complete-case error estimates without justification.
Follow genuinely missing observations prospectively without manufacturing their
unobserved scores. A later repaired score is not automatically a valid historical
reference if its evidence/model was unavailable then.

## 7. Proposed future display/API contract — not implemented

Keep `insider_edge_score`, `score_status` and `availability_status` unchanged.
A separately versioned optional `provisional_estimate` object could contain:
value, method (`observed_weight_renormalization`), policy version, eligible flag,
observed components, unavailable components and original reasons, observed weight,
effective weights, evidence/run identifiers, and explicit eligibility limitations.
Its absence means no estimate; distinguish ineligible from not evaluated inside
that future object. A no-Signal event must not gain a fabricated estimate.

Label: **Experimental provisional estimate — incomplete evidence**, disclose
missing components and observed weight percent, and state it is not the official
IES, confidence, return probability or investment recommendation. Preserve the
existing official partial badge without double-counting it as experimental.
Two-decimal formatting is presentation only; show null as unavailable.

Do **not** mix provisional and official scores in default Radar ranking now.
If a future study justifies deployment, prefer separate explicit sorting/filtering
modes with status and coverage visible; cross-pattern sorting should require an
explicit opt-in and warning. Default provisional display remains conditional on
approval and must not silently substitute into official sorting fields. Events
with insufficient valid retained evidence keep an unavailable result and reasons.
Accessibility must expose labels/coverage as text, not color-only indicators.

## 8. Go/no-go and evidence requirements

Go: recover original run artifacts; retain Policy D; pre-register an offline
Policy A study and component-specific comparisons. No-go: production provisional
calculation, default ranking or broader partial normalization at this stage.

Needed decisions: acceptable error/rank distortion, sample/independent-period
requirements, eligible missing reasons, inclusion/exclusion of M-absent cases,
allowed patterns, UI separation and audit retention. No existing hard contract
is changed by this document. Data-repair, new statuses, API wiring, persistence
and retrospective rescoring require separate authorization.

## 9. Future imputation appendix

Random-forest/MissForest-style methods may model nonlinear component relations,
but history/identity-driven MNAR cannot be solved by predictive fit alone. Any
future training must use historically eligible information and fit within training
partitions only, with temporal validation and company-dependence analysis. Model
uncertainty, selection effects and extrapolation need explicit reporting. Predicting
C accurately is a different objective from preserving IES rankings; assess both
against a justified reference. Imputed components must remain visibly distinct
from observed evidence, never satisfying an observed-weight rule. No imputation
model, dependency or training experiment is introduced here.

## 10. Validation and safety

Only this research document was added on the isolated branch. No production source,
API, UI, schema, tests or official scoring contract changed. Existing scoring tests
and Markdown/new-file whitespace checks are run as the accompanying review checks;
results are reported with the task handoff. Original unrelated files remain in
the original checkout. No external research-service/DB requests or scoring jobs
were executed; tests use synthetic fixtures.
