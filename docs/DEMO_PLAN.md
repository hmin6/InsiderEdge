# InsiderEdge Demo and Presentation Plan

## Issue #35 verification — 2026-10-10

**Status: DEMO READY.** The approved Decimal and Boolean fixes pass tests and
real-data checks. AXP has complete persisted quantitative evidence, verified
local/production reads and browser navigation, and successful final live Gemini
and ElevenLabs verification. Exactly one request was made to each provider after
explicit human authorization; neither was retried.

Production frontend: https://insideredge.work

Fallback frontend: https://insider-edge-omega.vercel.app

Production backend: https://insideredge-api.onrender.com

### Verified preparation

| Persisted data | Before preparation | After preparation |
| --- | ---: | ---: |
| Prices | 34 | 217,418 |
| Raw insider transactions | 30 | 1,229 |
| Research events | 1 | 458 |
| Signals | 0 | 39 |

Market preparation covers all 101 frozen securities, SPY, and 11 sector ETFs.
Prices run from 2019-01-02 through 2026-10-09 where the security has history;
GEV starts 2024-03-27, PLTR 2020-09-30, SNDK 2025-02-13, and UBER 2019-05-10.
Every persisted price has `analysis_price`; raw Close was not substituted.
The independent XNYS schedule from exchange_calendars 4.13.2 contains 1,954
sessions and exactly matches persisted SPY dates, including the 2025-01-09
closure. Calendar references: [exchange_calendars](https://github.com/gerrymanoim/exchange_calendars)
and [NYSE trading hours and holidays](https://www.nyse.com/markets/hours-calendars).
Calendar/browser tools were isolated in ignored local cache directories;
application dependencies were not changed.

SEC preparation used all 27 published quarters from 2020Q1 through 2026Q3.
Existing parser outputs were restricted to complete filings containing a purchase
flag for an issuer in the frozen universe, including amendments as raw provenance.
This selected 519 filings / 1,200 normalized rows: 1,199 inserts and one canonical
duplicate. Full official source ZIPs remain cached. The 21 archive-wide parser
diagnostics concern invalid/missing transaction codes or acquisition/disposition;
none attach to the selected filings. The recent EDGAR gap after 2026Q3 was not
imported; this is a historical preparation snapshot, not a real-time completeness
claim.

The existing event builder accepted 1,049 original Form 4/Table I/code-P/acquisition
transactions, producing 458 events across 80 tickers. Information dates span
2020-01-06 through 2026-09-21. It preserved transaction dates separately from
filing dates and used the first persisted SPY session strictly after filing.
Seven amendments remain raw and excluded pending reconciliation. Six events
have unknown buyer counts and explicit buyer/role diagnostics. The 29 previously
unmapped smoke rows and one transaction dated after its filing remain excluded.
No share-class mapping was guessed. Quant input preparation used the existing
builder's accepted transaction output, not the broader amendment-inclusive raw
SEC purchase flag.

The configured Tiger database was intentionally modified through existing
persistence functions, without schema changes, deletes, resets, or synthetic data.
Its initial CRM inventory matched the production API; production connection-string
identity was not independently inspected. Post-persistence production AXP
statistics and prediction now match local responses exactly. Credentials were not displayed; root `.env` remains ignored and
unstaged.

### Operations used

Run market/event commands from `backend` with the repository virtual environment:

```powershell
..\.venv\Scripts\python -m scripts.ingest_prices --validate-only --ticker SPY --start 2019-01-01 --end 2026-10-10 --report ..\data\sec_cache\issue35_market_preflight.json
..\.venv\Scripts\python -m scripts.ingest_prices --start 2019-01-01 --end 2026-10-10 --report ..\data\sec_cache\issue35_market_report.json
..\.venv\Scripts\python -m scripts.build_event_dataset --start 2020-01-01 --end 2026-10-10 --dry-run --report ..\data\sec_cache\issue35_event_dry_run.json
..\.venv\Scripts\python -m scripts.build_event_dataset --start 2020-01-01 --end 2026-10-10 --report ..\data\sec_cache\issue35_event_report.json
..\.venv\Scripts\python -m scripts.build_event_dataset --start 2020-01-01 --end 2026-10-10 --report ..\data\sec_cache\issue35_event_repeat_report.json
```

SEC preparation used an ignored local operational harness, invoked from the root
as `.\.venv\Scripts\python data/sec_cache/issue35_prepare_sec.py`. It composed
existing `SecClient`, `discover_quarters`, `parse_bulk`, `Universe.cik_to_tickers`,
and `sec.repository.persist` functions: discover/download official quarters with
normal throttling/retries; parse each complete archive before filtering so canonical
identities remain intact; select all normalized rows for accessions containing a
purchase-flag row for a frozen-universe issuer; commit each source atomically via
canonical-key conflict handling. No CLI ticker-filter flag was invented. The local
harness is not a tracked application command; retain the cache/report or reproduce
this documented composition rather than assuming that file exists in a checkout.

Market upserts were verified by replaying six unchanged persisted SPY rows twice:
217,418 rows before and after, zero duplicate ticker/date groups. The second full
event build reported 458 unchanged events, zero inserts/updates/enrichments, and
zero overlap blocks. Final read-only checks found zero duplicate canonical
transactions, zero duplicate ticker/event-day pairs, and zero canonical source
transactions associated with multiple retained events. Existing CRM was retained.

### Approved Decimal fix and verified offline results

Tiger `NUMERIC` prices load as `decimal.Decimal`. Aligned benchmark arrays had
object dtype when `np.isfinite` ran. The approved fix changes the two affected
sector/SPY array conversions in `backend/app/quant/features.py` to
`to_numpy(dtype=float)` before finite checks. Formulas, windows, zero/missing
semantics, temporal boundaries, and contracts are unchanged.

Four regression tests cover Decimal/mixed inputs versus floats, genuine zero and
zero denominators, missing/non-finite filtering, and exclusion of boundary/future
prices. From `backend`:

- `..\.venv\Scripts\python -m pytest -q tests/test_features.py`: **19 passed,
  6 subtests passed in 9.21s**.
- `..\.venv\Scripts\python -m pytest -q`: **647 passed, 1 warning,
  6 subtests passed in 96.71s**. The warning is the existing TestClient/httpx
  deprecation; tests made no live AI requests.

The ignored operational harness
`.\.venv\Scripts\python data/sec_cache/issue35_prepare_quant.py --features-only`
then built all **458** actual event feature rows in a read-only database
transaction. Before Signal persistence, inventory was **217,418 prices / 113
symbols, 1,229 raw transactions, 458 events / 80 tickers, and 0 Signals**. No
historical ingestion was repeated. Later writes were limited to the existing
Signal integration and its namespaced event evidence.

Running the same harness without `--features-only` used existing offline quant
and ML functions. Full-set offline availability (only eligible post-selection Signals were later persisted):

| Evidence | Events available |
| --- | ---: |
| Anomaly | 420 |
| Activity | 132 |
| Market/dislocation | 458 |
| CAR5 | 458 |
| CAR30 | 454 |
| CAR90 | 445 |
| Eligible comparable cohort (minimum 10, existing availability cutoff) | 345 |

CAR outcomes are retrospective labels/evidence, not prediction-time inputs.
Statistical processing is now complete for all 458 events: **345** have bootstrap
intervals, randomization p-values, and statistical scores; **113** remain
`insufficient_data`. Existing 1,000-resample/replicate settings, seeds, eligibility,
and score formulas were retained. The ignored operational runner reused original
event-study results only for identical price/calendar/event inputs and cached
paired returns within calls sharing the same immutable inputs. Five sampled
cached outputs matched fresh uncached calculations; the price snapshot was
unchanged. This is local execution caching, not an application/methodology change.

The supervised dataset has **458 candidates, 454 labeled and 4 unlabeled**.
Temporal outcome guards purged 15 rows (9 train, 6 validation). Usable splits:

| Split | Rows | Positive | Negative |
| --- | ---: | ---: | ---: |
| Train 2020–2024 | 343 | 173 | 170 |
| Validation 2025 | 61 | 38 | 23 |
| Completed 2026 test subset | 35 | 17 | 18 |

Existing readiness guards passed. Train-only preprocessing and validation-only
selection chose **Logistic Regression, C=0.1** from the existing candidates.
The frozen test was evaluated once after selection: ROC AUC
**0.565359477124183**, Brier **0.2628824726893451**, precision **0.6**, recall
**0.5294117647058824**, and F1 **0.5625**, at threshold **0.5**, on 35 rows.
These modest results have a small test sample; they do not establish strong
predictive performance. Local fitted/evaluation checkpoints are ignored under
`data/sec_cache/`; no application-integrated durable frozen evaluation artifact
loader exists. API held-out metrics therefore remain null. Validation metrics
must not be substituted.

### Approved Boolean fix and Signal persistence

Strict inference in `backend/app/ml/dataset.py` previously rejected booleans for
all numeric predictors even though `build_event_features` emits Boolean flags.
The approved correction permits `bool`/`np.bool_` only for
`any_new_position_flag`, `has_executive`, `has_cfo`, and `has_director`. The existing
shared training/inference conversion supplies numeric `0.0`/`1.0`. Continuous
Boolean inputs still fail. Null/NaN remain missing under existing behavior;
infinity/invalid objects remain rejected. Feature ordering, canonical buyer
checks, source-date boundaries, and preprocessing methodology are unchanged.

Thirty-five parameterized regression cases cover all four flags and Boolean
types/values, equivalence with training and numeric inputs, continuous-Boolean
rejection, missing/invalid values, and provenance/temporal guards. From `backend`:

- `..\.venv\Scripts\python -m pytest -q tests/test_ml_dataset.py tests/test_ml_training.py tests/test_ml_evaluation.py tests/test_signal_integration.py`:
  **194 passed, 1 existing warning in 31.63s**.
- `..\.venv\Scripts\python -m pytest -q`:
  **682 passed, 1 existing warning, 6 subtests passed in 59.28s**.

A fresh read-only Tiger check confirmed the original price/event snapshot still
matches. All **39** events after the last validation outcome (2026-01-14) passed
strict inference and generated bounded probabilities. The **419 earlier events
were not assigned production probabilities from this later-selected model**.
The frozen fitted selection was reused; neither model selection nor test
assessment was repeated or driven by demo outcomes.

The existing `build_signals` / `persist_signals` path wrote **39 Signals**, bound
to exact event ID/ticker/public day/information boundary and model version.
Validated response evidence is stored in `feature_metadata.signal_api_evidence_v1`;
unrelated metadata keys are preserved. Current-event outcomes are retrospective
API display only; AI evidence excludes them. Comparator CAR30 endpoints must
strictly precede the focal information date. Held-out API metrics remain null.

Building and persisting the same batch twice produced identical state, zero
duplicate event Signals, unchanged raw transactions/prices, and unchanged event
fields outside the intended metadata namespace. Final inventory is **217,418
prices / 113 symbols; 1,229 transactions; 458 events / 80 tickers; 39 Signals**.
Signal availability is distinct from full-set offline coverage:

| Evidence | Persisted Signals with value |
| --- | ---: |
| Anomaly | 39 |
| Activity | 14 |
| Market/dislocation | 39 |
| CAR5 / CAR30 / CAR90 | 39 / 35 / 26 |
| Bootstrap / randomization / statistical score | 36 / 36 / 36 |
| Model probability | 39 |
| Final IES | 14 |

Fourteen Signals are `complete`; 25 are honestly `insufficient_data`, primarily
because activity is unavailable. No missing component was replaced with zero.

### Final demo selection

Compare latest company events only; never borrow an older Signal for a newer
unscored event. Twenty-five latest-event candidates have post-selection Signals.
Ranked by presence of 13 evidence items, **AXP, BA, CAT, MSFT, and TMUS each have
13/13**. Alphabetical ticker order resolves the tie. Scores, probability values,
and future return signs/magnitudes do not participate in selection.

**Final ticker: AXP — American Express.**

- `research_event_id`: `AXP:2026-03-16`.
- `information_date`: **2026-03-13**.
- `public_event_day`: **2026-03-16**.
- Seven qualifying original Form 4/Table I/code-P/acquisition transactions,
  one filing (`0000004962-26-000116`), one supported underlying buyer, Executive
  role. Code P does not establish exchange-only execution.
- Anomaly, activity, pre-event market/dislocation, CAR5/30/90, 17 eligible
  same-sector-and-role comparators, bootstrap, randomization, model probability,
  and complete IES are available.
- The statistical score is a **genuine zero**, not missing. The historical CI
  crosses zero and randomization evidence is weak; explain those limitations.
- Model probability is about **40.01%**, below the fixed 50% threshold. This
  candidate was selected for evidence completeness, not a favorable prediction.
- API held-out metrics remain null. Do not substitute validation metrics.

Show live API values rather than treating rounded presentation examples as fixed
outputs. CRM is no longer the final demo choice; it remains a secondary historical
smoke example.

### Verified local and production flow

Local FastAPI checks against Tiger returned 200 for health, Radar, company,
prices, insiders, statistics, and prediction. Contract shapes and exact event
identity were validated; unknown ticker statistics/prediction returned 404.
Deliberately unavailable dependency overrides verified local AI fallback: explain
503, brief 200 with transcript and `audio_unavailable`, with **zero live provider
calls**. These fallback checks are not live provider success claims.

Production read endpoints all returned 200. AXP statistics/prediction exactly
matched local evidence; its price endpoint returned 1,954 bars, insider endpoint
11 raw rows, and Radar 80 companies. Production CORS and POST preflight allowed
the explicit Vercel origin. The first `/health` request took about 32 seconds;
subsequent reads were quick, supporting the warm-up procedure below.

A real headless browser followed Radar → AXP, rendered the historical chart and
quant/model panels, and refreshed `/company/AXP` directly with HTTP 200. No
localhost requests, failed requests, JavaScript page errors, or console errors
were observed. API traffic used only `insideredge-api.onrender.com`. Existing
presentation caveats: the full-precision score wraps inside its ring, the insider
summary is generic because no textual summary is persisted (inspect the insider
API for row-level provenance), and the tab title is still “InsiderEdge · Visual
system preview.” No frontend files were changed.

### Final live provider verification

After explicit human authorization for the selected event's external evidence
transmission, production `/health` was used to wake Render. Exactly one request
was made to each existing backend integration, without retries:

- `POST /api/companies/AXP/explain`: **HTTP 200**, ticker AXP, exactly the existing
  five string-array explanation sections. Supporting/risk statements and rounded
  figures match the persisted event, component scores, probability, pre-event
  market context, and validated historical comparators. The response explicitly
  identifies the small cohort, CI crossing zero, unavailable fundamentals, and
  unavailable held-out metrics. It contains no trade recommendation, causal
  claim, or invented held-out result. The genuine zero statistical score is
  preserved rather than treated as missing.
- `POST /api/companies/AXP/brief`: **HTTP 200**, ticker AXP, `status="ok"`,
  `audio_mime_type="audio/mpeg"`, and a non-empty validated MP3 payload. The
  deterministic transcript exactly matches the preview assembled from persisted
  AXP evidence. ElevenLabs only synthesizes that supplied text.

Company, statistics, and prediction responses were identical before and after
both calls. Provider route/service inspection confirms read-only evidence
assembly and no Signal/scoring role. Credentials/environment values were not
included in submitted evidence or displayed. The earlier automatic approval
rejection was resolved by explicit human authorization; it no longer blocks
verification.

The saved MP3 decoded and played locally in a muted headless browser without an
error or any external request. This confirms browser-compatible audio, not a
human listening review. Listen once to the saved clip before presenting; no
additional provider request is needed. Ignored local reports/audio are under
`data/sec_cache/issue35_provider_results.json`, `issue35_provider_attempts.json`,
`issue35_audio_check.json`, and `issue35_axp_brief.mp3`.

The final verified path is Radar → AXP → insider provenance → anomaly → activity
→ market/dislocation → CAR5/30/90 → historical bootstrap/randomization → model
probability → complete IES → Gemini explanation → ElevenLabs audio. Core UI and
direct refresh were verified in production; final provider outputs were verified
through production endpoints. The generic insider summary can be supplemented
with the existing insider endpoint for exact source rows. Preserve the documented
null held-out metrics and research-priority framing throughout.

## Expected click path

1. Market Dislocation Radar.
2. Open AXP, the completeness-selected company (it need not lead the score ranking).
3. Show qualifying code-P insider purchase events and filing/public-information dates.
4. Show anomaly score.
5. Show activity/cluster shift.
6. Show stock versus sector dislocation.
7. Show CAR results.
8. Show comparable-event definition and sample size.
9. Show bootstrap confidence interval.
10. Show randomized-timing-null p-value.
11. Show the actual ML outperformance probability; show held-out metrics only if a valid durable frozen artifact is integrated, otherwise explain the unavailable state.
12. Show final InsiderEdge Score and component breakdown.
13. Click **Explain Signal**; emphasize that Gemini explains rather than creates the signal.
14. Play ElevenLabs Analyst Brief only if stable.

## Thirty-second pitch

> InsiderEdge starts where a basic Form 4 tracker stops. We take newly public insider purchase events and combine unusual-activity detection, market and sector dislocation, comparable-event CAR analysis, bootstrap and randomized-timing validation, and leakage-aware machine learning to rank which events deserve deeper research. The result is a transparent InsiderEdge research-priority score with the underlying evidence visible, while Gemini explains the model-generated evidence rather than creating the signal. ElevenLabs can optionally turn that evidence into an analyst briefing.

## Presentation structure

1. Problem.
2. Solution.
3. Competitive differentiation: why this is more than a Form 4 tracker.
4. Data and public-information boundary.
5. Quantitative methodology and coursework mapping.
6. ML and chronological validation, including outcome-window split guard.
7. Live product demo — largest share of time.
8. Architecture / sponsor technology.
9. Closing: research prioritization, uncertainty, limitations, and scalability.

## Product-visual presentation goals

The final UI should look like a sleek institutional research product.

- Calm dark navy/charcoal shell with a light research workspace.
- Prominent but analytically honest InsiderEdge Score.
- Component breakdown understandable in seconds.
- Smooth, restrained 150–300 ms interactions.
- Subtle table-row hover/selection.
- Recharts line reveal and insider-event marker emphasis where practical.
- Skeleton loading rather than distracting page spinners.
- Gemini explanation expands/reveals without hiding quantitative evidence.
- No “BUY”, “SELL”, “Strong Buy”, casino, confetti, bouncing cards, or constantly pulsing UI.

## Critical presentation language

Use:

- “research priority” rather than “recommendation”;
- “qualifying code-P insider purchase events” rather than claiming every code-P transaction was exchange-only open-market execution;
- “Gemini explains the signal; it does not generate it.”
- “The model was selected on validation; the final test set was left untouched until the pipeline was frozen.” This local run verified training and evaluation; held-out API metrics are still unavailable.
- “The frozen current-S&P-100 historical sample may contain survivorship/selection bias.”

## Likely judge questions

### Is this investment advice?

No. It is a research-prioritization tool that surfaces evidence and uncertainty.

### Does Gemini predict the stock?

No. Statistical and ML code computes every quantitative result; Gemini explains structured outputs.

### How do you prevent leakage?

Features use only information available by filing/public-information time, model evaluation is chronological, and 30-trading-day outcome windows cannot cross into the next evaluation split.

### Why bootstrap / randomized timing?

To quantify uncertainty around historical comparable-event evidence and compare the observed historical effect with a randomized timing null.

### What counts as a comparable event?

The cohort rule is fixed in advance: same sector + same broad insider-role bucket, then same-sector fallback, with a minimum sample size. The selected rule and `n` are shown to the user.

### Why are A/C/S/D not ML inputs?

To keep the model probability a more distinct component and avoid intentionally feeding final-score components back into the model.

### Why Tiger Data?

Prices, insider events, rolling metrics, and historical signals are time-oriented data that benefit from persistent time-series querying.

### Why XGBoost?

It can capture nonlinearities/interactions, but it is retained only if validation results justify it versus Logistic Regression.

### Are all code-P transactions “open-market” trades?

No. SEC code P can represent an open-market or private purchase. P0 uses non-derivative code-P acquisitions and does not claim execution venue unless the filing establishes it.

## Failure fallback

The populated read flow and both live providers are verified. Local provider-outage
paths also passed with deliberately unavailable adapters.

1. Shortly before presenting, request production `/health` to wake Render Free.
   Allow a cold start; then open Radar and pre-open the chosen company page.
   Verify the event ID and live values again. Do not ingest/train during judging.
2. If Render/network is slow, wait for existing loading/error states and use Retry.
   If persisted API reads remain unavailable, explain the limitation and use the
   methodology walkthrough; do not claim live evidence was shown.
3. If Gemini fails, continue using visible quantitative evidence. Explain Signal
   may return controlled 503; Gemini is optional and never generates the score.
   Avoid repeated paid requests during preparation or presentation.
4. If ElevenLabs fails, its endpoint preserves the deterministic transcript with
   `audio_unavailable` and null audio fields. Read that transcript when available.
   If the entire request fails, continue with the visible evidence panels.
5. If a provider-dependent request fails in the frontend, leave that panel and
   continue the independent data panels. It must not replace their evidence.
6. If one component is unavailable, state its reason and show its null/status.
   Never replace missing values with zero, an older event's Signal, or a different
   cohort/model. Show a final score only if the actual pipeline produced it.
7. Use persisted prices/SEC/evidence rather than a fresh market-provider request.
   Keep AI/audio optional. Do not substitute fabricated screenshots or values.

Required caveats: research prioritization, not investment advice; code P is a
qualifying open-market **or private** purchase; no causation claim; frozen-current-
universe survivorship/selection bias; historical SEC snapshot freshness; unknown
buyer identities remain unknown; realized CAR is retrospective and excluded from
prediction-time/AI evidence; held-out metrics require a durable valid artifact.
