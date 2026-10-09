# InsiderEdge Quantitative and ML Model Specification

This file is an authoritative contract for timing, formulas, cohorts, targets, score construction, and validation.

## 1. Information boundary

For a research event with filing/public-information time `t`:

- `filing_date` / public availability is the information boundary.
- `transaction_date` never substitutes for `filing_date` in historical prediction logic.
- With P0 daily bars, predictive market features use data only through the last fully completed trading day **strictly before** `filing_date`.
- Event day `t=0` is the first trading day after `filing_date`.
- One inference/ML unit is one `research_event_id = ticker + public_event_day`.
- Raw SEC transactions remain separately stored.

## 2. Preferred temporal split

Preferred:

```text
TRAIN: 2020–2024
VALIDATION: 2025
TEST: 2026
```

If too sparse after filtering, use an approximately 70/15/15 chronological split.

Do not use random 80/20 as the primary evaluation.

Only events whose full future 30-trading-day label is complete may be labeled. Very recent events may still be scored live without a realized future outcome.

### Outcome-window split guard

A training event is eligible only if its complete 30-trading-day outcome window ends before validation begins. A validation event is eligible only if its complete outcome window ends before the test period begins. Apply the same rule to fallback chronological boundaries.

This prevents a late earlier-split label from consuming market outcomes inside a later evaluation period.

## 3. Core pre-event features

All features must be available by the information boundary.

### Market

- prior 5-session return;
- prior 30-session return;
- prior 90-session return;
- prior 30-session volatility;
- drawdown;
- volume-based signal/anomaly;
- SPY-relative performance;
- sector-relative performance.

### Insider / research-event

- aggregate transaction value;
- log aggregate transaction value where valid;
- optional `max_valid_ownership_change_pct`;
- `any_new_position_flag`;
- executive indicator;
- CFO indicator when derivable;
- director indicator;
- broad role bucket;
- unique insider buyers over prior/current 7 and 30 calendar days;
- total qualifying purchase value over prior/current 7 and 30 calendar days;
- recent purchase rate;
- historical purchase rate.

All stock/SPY/sector returns use the same adjustment-aware `analysis_price` convention from the market-ingestion layer.

## 4. Mahalanobis anomaly score (A)

For feature vector `x`, historical mean `mu`, and covariance matrix `Sigma`:

```text
D_M^2 = (x - mu)^T Sigma^-1 (x - mu)
D_M   = sqrt(D_M^2)
```

With `k` anomaly features:

```text
A = 100 * F_chi2_k(D_M^2)
```

Reference population:

1. same-sector historical research events whose information was available before the current event;
2. require `MIN_ANOMALY_REFERENCE = 30`;
3. if too sparse, fall back to all prior S&P 100 research events and report the fallback.

Use a documented regularization or pseudo-inverse fallback for singular covariance matrices.

If real data later makes the theoretical chi-square calibration clearly inappropriate, an empirical-percentile normalization is a post-MVP adaptation and must be explicitly documented rather than silently substituted.

## 5. Insider activity / cluster score (C)

Information date: current research-event filing date.

- Recent window: 30 calendar days ending on the current filing date.
- Historical-rate window: preceding 365 calendar days excluding the recent 30-day window.
- Recent purchase rate: qualifying company research events in recent 30 days / 30.
- Historical purchase rate: qualifying company research events in historical 365-day window / 365.
- Rate ratio: recent rate / historical rate.

If historical rate is zero, return a documented capped/insufficient state rather than divide by zero.

Let:

- `BuyerCountPercentile` = empirical percentile of current `buyers_30d` among earlier research events for the same company;
- `RateRatioPercentile` = empirical percentile of current rate ratio among earlier research events for the same company.

Reference fallback:

1. prior same-company events;
2. if fewer than `MIN_ACTIVITY_REFERENCE = 10`, use prior same-sector research events;
3. if still too small, return `insufficient_data`.

Score:

```text
C = 0.50 * BuyerCountPercentile + 0.50 * RateRatioPercentile
```

Percentiles are on 0–100 scale.

## 6. Event study

Primary benchmark: SPY.

Estimation window: trading days `[-120, -21]`, with at least 60 paired stock/benchmark observations.

Market model:

```text
R_i,t = alpha_i + beta_i * R_m,t + epsilon_i,t
expected_i,t = alpha_hat_i + beta_hat_i * R_m,t
AR_i,t = R_i,t - expected_i,t
```

Exact CAR windows:

```text
CAR5  = sum AR over t = 0..4
CAR30 = sum AR over t = 0..29
CAR90 = sum AR over t = 0..89
```

Primary research horizon: CAR30.

These exact 5/30/90-session horizons are InsiderEdge design choices.

## 7. Comparable-event cohort

Comparable events must satisfy both:

- filing/public information was available before the current event; and
- the **entire CAR30 outcome window** was already complete before the current event information date.

Cohort hierarchy:

1. same sector + same broad insider-role bucket;
2. if too sparse, same sector regardless of role;
3. if still below `MIN_COMPARABLE_EVENTS = 10`, return `insufficient_data`.

The cohort rule is fixed before observing CAR30 outcomes and must be returned in the API/UI with sample size.

Broad role hierarchy is `Executive > Director > Other` while underlying role flags remain preserved.

## 8. Bootstrap evidence

Inference unit: one company-event CAR30, not one raw transaction.

Default:

```text
B = 1000 resamples
95% percentile confidence interval
```

If `q` is the fraction of bootstrap mean-CAR30 estimates above zero:

```text
B_support = 100 * clip((q - 0.5) / 0.5, 0, 1)
```

Return/display raw comparable-event count, cohort definition, mean CAR30, and CI.

## 9. Randomized-timing null

For each historical comparable company-event, assign an eligible pseudo-event day for the same ticker and calendar year, then recompute CAR30 with the same event-study logic.

Empirical one-sided p-value:

```text
p = (1 + count(T* >= T_obs)) / (B + 1)
```

Support mapping:

```text
P_support = 100 * clip(1 - p / 0.10, 0, 1)
S = 0.50 * B_support + 0.50 * P_support
```

Raw p-value remains visible. Never translate a p-value into guaranteed language.

## 10. Market-dislocation score (D)

Define 90-day sector underperformance:

```text
sector_gap90 = R_sector,90 - R_stock,90
```

Convert sector gap and drawdown magnitude to empirical percentiles across the universe:

```text
D = 0.60 * SectorGapPercentile + 0.40 * DrawdownPercentile
```

The reference cross-section is the ticker list in the repository's frozen
`config/universe.csv`, with one observation per ticker. This frozen membership
is used for every scoring date; it is **not** a historical point-in-time index
reconstruction and can create survivorship/selection bias. For each event,
reference features are recomputed using only valid `analysis_price` observations
strictly before that event's `information_date`. The stock and its mapped sector
ETF must have the required 91 aligned observations for their 90-session returns;
drawdown is calculated from the stock's same 91 pre-information-date prices.
Missing ticker-to-sector-ETF mapping or price coverage leaves the sector gap
unavailable.

Each component percentile is computed independently from its finite values in
the frozen-universe cross-section at that event's information date. The target
ticker is included when its component value is valid. Use the empirical midrank
percentile:

```text
100 * (count(reference < value) + 0.5 * count(reference == value)) / n
```

Values outside the reference range map to 0 or 100. Ties therefore receive the
average empirical rank. Require at least
`MIN_DISLOCATION_REFERENCE = 10` valid values for **each** component. If either
the target component or its reference distribution is unavailable/insufficient,
`D` is unavailable; do not impute zero or renormalize the 60/40 weights.

The existing `drawdown_90d` is zero or negative (`last_price / trailing_peak -
1`), so drawdown magnitude for the percentile is `abs(drawdown_90d)`. A larger
`D` indicates greater dislocation / research priority, not a trading
recommendation.

## 11. ML target

One ML row is the same company research event used by quant/inference.

Target:

```text
Y = 1 if stock outperforms SPY over the same next 30 trading sessions t=0..29
Y = 0 otherwise
```

Use one documented return convention for stock and SPY over that horizon.

### Models

Required:

1. Logistic Regression baseline;
2. XGBoost classifier candidate.

Do not assume XGBoost is better.

### Model selection

- Learned preprocessing is fit on training data only.
- Hyperparameters/model/threshold are selected using train + validation only as documented.
- Test data does not influence feature choice, preprocessing, hyperparameters, model choice, or threshold.
- After freezing the pipeline, evaluate once on test.
- Default classification threshold is 0.50 unless an alternative is selected on validation only and then frozen.

### Metrics

Report:

- ROC-AUC;
- Brier score;
- precision;
- recall;
- F1;
- classification threshold;
- sample count;
- positive-class prevalence;
- split dates.

### Feature exclusions

Never include:

- future CAR/outcome columns;
- target labels;
- A anomaly score;
- C activity score;
- S statistical score;
- D dislocation score;
- IES;
- raw identifiers such as `research_event_id`, ticker, CIK, or raw insider name as predictive features.

Sector and broad role category may be used only if encoded from pre-event information and approved in the feature contract.

## 12. Final InsiderEdge Score

All components are 0–100:

- `A`: anomaly score;
- `C`: activity/cluster score;
- `M`: selected ML model probability × 100;
- `S`: statistical evidence score;
- `D`: market-dislocation score.

Locked default:

```text
IES = 0.25*A + 0.15*C + 0.30*M + 0.15*S + 0.15*D
```

The weights are a transparent hackathon heuristic, not theoretically optimized.

Gemini/LLMs have zero role in score calculation.

### Missing-component policy

The master plan explicitly allows a partial score when statistical evidence is unavailable from insufficient comparable-event history. This document locks the minimal P0 behavior:

- Never treat an unavailable component as zero.
- If **S alone** is unavailable because comparable-event/statistical history is insufficient, renormalize the remaining A/C/M/D weights over their original total `0.85`:

```text
IES_partial = (0.25*A + 0.15*C + 0.30*M + 0.15*D) / 0.85
```

- Set `score_status = "partial"` and include `S` in `unavailable_components`.
- If A, C, M, or D is unavailable, return `insufficient_data` for the final IES rather than inventing a broader renormalization policy during P0.
- `complete` means all A/C/M/S/D components are available.

This concretization is intentionally conservative and should not be expanded without an explicit contract change.

## 13. Provenance categories

Keep these categories explicit in code comments/docs/presentation:

- **Coursework-derived:** covariance/Mahalanobis concepts, statistical inference, bootstrap/permutation concepts, Logistic Regression/validation/metrics.
- **Finance/time-series extension:** market-model event study, abnormal returns/CAR, timing/overlap considerations.
- **InsiderEdge-specific design:** exact CAR horizons, research-event aggregation, cohort hierarchy, randomization-null construction, activity/dislocation formulas, score support mappings, and final IES weights.
