# Statistics and prediction reads

`GET /api/companies/{ticker}/statistics` and `/prediction` implement the existing
`docs/API_CONTRACT.md` shapes. Both use the latest persisted research event and
join a signal only on matching event ID, ticker and public event day. An unknown
ticker returns 404 `Unknown ticker`; a known ticker without any research event
returns 404 `No research event available` because contract event identity fields
are non-null. An unscored event returns 200 with null outputs and explicit statuses.

## Evidence sources

| API fields | Source / availability |
|---|---|
| ticker, event ID, event day | Persisted research event |
| anomaly/activity/dislocation scores | Matching Signal columns |
| anomaly distance, reference population/count | Validated anomaly output: D, reference_rule, reference_sample_size |
| activity rates, ratio, buyers, reference population | Validated activity output: recent_rate, historical_rate, rate_ratio, buyers_30d, reference_rule |
| stock/sector return, drawdown | Validated dislocation output: stock_return_90d, sector_return_90d, drawdown_90d |
| CAR5/30/90 | Signal columns, exposed only with persisted build-time outcome-availability provenance |
| comparator count/cohort/mean, CI, p-value, statistical score | Signal columns, exposed only with persisted validated comparator provenance |
| model name/probability | Matching Signal columns |
| classification threshold | Actual selected ModelSelection.threshold persisted at signal build |
| held-out metrics | null: EvaluationResult is currently in memory only; no durable frozen evaluation artifact is available |

Market features and rate counts can be reproduced from complete persisted prices,
events and verified buyer identities by the existing offline quant functions.
This API does not recompute them against potentially changed source data.
Buyer names are never substituted for verified identities. Reference diagnostics
require the original reference run; they cannot be inferred from scores alone.
Model/evaluation artifacts currently have no repository persistence loader.
No default threshold or validation-set metrics are substituted for missing evidence.

## Minimal persistence

`persist_signals` atomically stores a validated API snapshot under the existing
`ResearchEvent.feature_metadata.signal_api_evidence_v1` JSON namespace alongside
the Signal upsert. No table, column or migration is added. Existing source-owner
metadata is preserved. The snapshot contains component results, selected threshold,
observation cutoff, comparator identities/information dates/CAR30 completion dates,
and a binding to the exact event information boundary and persisted signal fields,
including model/score version. Repeating the same build replaces the same namespace
and signal row; it creates no duplicates. This follows the existing one-current-
signal-per-event replacement policy, rather than claiming to archive model history.

Legacy rows without this namespace return `unavailable_not_persisted` for missing
evidence and `partial_diagnostics_unavailable` when a component score is available
without its diagnostics. Historical statistical values and CAR remain null until
an explicit validated rebuild; no backfill is performed on a GET request. Mismatched
signal bindings/information dates invalidate the snapshot rather than reusing it.

The existing signal builder validates feature provenance, prior comparator information,
and complete comparator CAR30 outcomes strictly before the focal information date.
CAR display is retrospective, uses the build's completed-session cutoff, and remains
null for incomplete horizons. A future/current-date cutoff is conservatively hidden
on reads. CAR is never added to predictive features or AI evidence. Model selection,
test-set isolation and evaluation methodology are unchanged. Prediction status is
`partial_evaluation_unavailable` when a probability exists without held-out metrics;
otherwise `unavailable`.

Routes perform no ingestion, training, model selection, evaluation or provider calls.
