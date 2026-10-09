# InsiderEdge Test Plan

Testing should be lightweight enough for a 48-hour hackathon but strong around temporal correctness, data normalization, quantitative formulas, API contracts, and the demo path.

## Data tests

Validate:

- SEC bulk/EDGAR normalization;
- code-P non-derivative acquisition filtering;
- code-P derivative exclusion from P0;
- non-P handling;
- Form 4/A amendment preservation without duplicate event creation;
- duplicate bulk/EDGAR handling;
- malformed numeric fields;
- missing transaction price;
- ticker/CIK mapping;
- leading-zero CIK normalization;
- filing date versus transaction date separation;
- accepted timestamp when available;
- first-trading-day `public_event_day` derivation;
- weekend/holiday filing behavior;
- source-filing identity;
- adjustment-aware price storage;
- price gaps/provider failures;
- chronological sorting;
- current-S&P-100 survivorship limitation is documented rather than hidden.

Required aggregation test:

`test_research_event_aggregation.py` proves multiple same-ticker/same-public-day source rows become one research event while raw transactions remain preserved.

## Quant tests

Use small manually checkable fixtures for:

- returns;
- volatility;
- drawdown;
- z-scores where used;
- Mahalanobis distance;
- same-sector/all-universe anomaly-reference fallback;
- singular covariance fallback;
- activity windows and percentiles;
- recent/historical rate calculation;
- market-model alpha/beta;
- abnormal returns;
- comparable-cohort selection;
- comparator outcome availability;
- bootstrap reproducibility;
- randomized-timing-null reproducibility;
- market-dislocation formula;
- score ranges;
- partial/insufficient-data states.

Required:

- `test_car_window_lengths.py`: CAR5 exactly 5 sessions, CAR30 exactly 30, CAR90 exactly 90.
- `test_comparator_availability.py`: reject comparator events whose full CAR30 outcome was not observable before the current event.

## ML tests

Create `test_no_future_leakage.py`.

Verify:

- feature timestamps do not exceed event information time;
- future returns are target-only;
- preprocessing fits on training data only;
- splits remain chronological;
- target columns are excluded;
- identifiers are excluded from predictive features;
- A/C/S/D/IES composite scores never enter the feature matrix;
- no unexpected NaN/inf reaches models;
- probabilities remain in `[0,1]`.

Create `test_split_outcome_overlap.py`.

Verify the 30-trading-day label window ends before the next evaluation split begins.

Add a guard proving final test metrics are not consumed by model-selection or threshold-tuning code.

## Backend tests

Cover:

- `GET /health`;
- `GET /api/radar`;
- company endpoint;
- prices endpoint;
- insiders endpoint;
- statistics endpoint;
- prediction endpoint;
- Gemini explanation endpoint;
- ElevenLabs brief endpoint when implemented;
- controlled 404 for unknown ticker;
- ticker normalization/validation;
- insufficient-data behavior;
- provider timeout/failure behavior;
- database configuration without exposing credentials;
- server-side credential configuration;
- CORS configuration where practical.

## Frontend smoke tests

Primary flow:

```text
Radar -> company page -> price chart -> statistical evidence -> ML prediction
```

Test:

1. Radar renders API items.
2. Radar default ranking/navigation works.
3. Company page renders headline score/status.
4. Statistics section renders.
5. Prediction section renders.
6. Empty optional fields do not crash.
7. `insufficient_data` is displayed correctly.
8. API failure produces a useful error state.
9. Unknown company does not produce a blank screen.
10. Missing price history is controlled.
11. No recent insider events is controlled.
12. Gemini failure leaves quant results visible.
13. ElevenLabs failure leaves text/quant results visible.
14. Reduced-motion mode does not break layout or interaction.

Always run `npm run build` after frontend changes that affect production output.

## Graceful degradation

- Gemini failure -> quantitative results still display.
- ElevenLabs failure -> transcript/quantitative results remain usable.
- Live market provider failure -> cached persisted data powers the demo.
- Missing statistical component -> Radar/company page shows explicit partial/insufficient status; never fake zero.
- Rate limiting, if added after the MVP is stable, returns a controlled response rather than breaking the app.
- No stack traces or credentials are shown to end users.
