# InsiderEdge API Contract

This file is an authoritative backend/frontend contract.

The master plan locks the endpoints, semantics, visible fields, units, and failure behavior but does not spell out every JSON wrapper. The concrete response shapes below are the **minimal project contract used to operationalize those requirements**. Change them only through an explicit coordinated contract update before implementation proceeds.

## Global conventions

- JSON keys use `snake_case`.
- Returns are decimal returns: `0.047` means 4.7%.
- Scores use 0–100.
- Model probabilities use 0–1.
- Missing optional values are `null`, never fake zeroes.
- Dates are ISO `YYYY-MM-DD`.
- Timestamps are ISO-8601 with timezone when available.
- `score_status` is one of `complete`, `partial`, `insufficient_data`.
- Unknown ticker -> controlled HTTP 404.
- Insufficient historical statistics -> HTTP 200 with an explicit status, not a server failure.
- Illustrative/mock values must be clearly development-only and never presented as measured results.

## `GET /health`

Response:

```json
{"status":"ok"}
```

## `GET /api/radar`

Purpose: ranked current signals for the Market Dislocation Radar.

Response:

```ts
type RadarResponse = {
  items: RadarItem[]
}

type RadarItem = {
  ticker: string
  company_name: string
  sector: string | null
  public_event_day: string
  insider_signal_summary: string | null
  insider_edge_score: number | null
  anomaly_score: number | null
  activity_score: number | null
  statistical_score: number | null
  dislocation_score: number | null
  ml_outperformance_probability: number | null
  score_status: "complete" | "partial" | "insufficient_data"
  unavailable_components: string[]
  availability_status?: "not_scored" | "complete" | "partial" | "insufficient_data" | null
}
```

`availability_status` is an additive read-model field emitted by current servers.
`not_scored` means the latest event has no exact matching persisted Signal; the other
values copy the persisted Signal status. It does not assert why scoring has not run.
Older payloads may omit it (or deserialize as null); consumers then use legacy
`score_status` without inferring that a Signal exists. The legacy `score_status`
and `unavailable_components` fallback remain unchanged for compatibility, but when
`availability_status = "not_scored"`, the component list is not evidence of evaluated
failures and must not be presented that way. Company responses retain
`latest_signal: null` for an unscored latest event; no event remains distinguished
by `latest_public_event_day: null`. No persisted schema or scoring policy changes.

Default frontend order: descending `insider_edge_score`, with unavailable scores handled explicitly rather than coerced to zero.

## `GET /api/companies/{ticker}`

Purpose: company metadata and latest signal summary.

```ts
type CompanyResponse = {
  ticker: string
  cik: string | null
  company_name: string
  sector: string | null
  industry: string | null
  latest_public_event_day: string | null
  latest_signal: RadarItem | null
}
```

## `GET /api/companies/{ticker}/prices`

Purpose: historical price series used for the company chart.

```ts
type PricesResponse = {
  ticker: string
  prices: PricePoint[]
}

type PricePoint = {
  date: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  adjusted_close: number | null
  analysis_price: number | null
  volume: number | null
}
```

Frontend charting should prefer the same adjustment-aware `analysis_price` series used by quant/ML.

## `GET /api/companies/{ticker}/insiders`

Purpose: transaction/event history for provenance, table display, and chart markers.

```ts
type InsidersResponse = {
  ticker: string
  transactions: InsiderTransaction[]
  research_events: ResearchEventSummary[]
}

type InsiderTransaction = {
  transaction_id: string
  accession_number: string
  source_type: "bulk" | "edgar"
  document_type: string | null
  insider_name: string | null
  insider_role: string | null
  transaction_date: string
  filing_date: string
  accepted_at: string | null
  public_event_day: string | null
  transaction_code: string
  acquired_or_disposed: string
  derivative_flag: boolean
  security_title: string | null
  shares: number | null
  price: number | null
  transaction_value: number | null
  shares_owned_after: number | null
  direct_or_indirect: string | null
  aff10b5one: boolean | null
  is_amendment: boolean
  is_p0_qualifying: boolean
}

type ResearchEventSummary = {
  research_event_id: string
  public_event_day: string
  information_date: string
  source_transaction_count: number
  source_filing_count: number
  aggregate_purchase_value: number | null
  unique_buyer_count: number | null
  role_bucket: "Executive" | "Director" | "Other"
  has_executive: boolean
  has_director: boolean
  has_other: boolean
  has_cfo: boolean | null
  max_valid_ownership_change_pct: number | null
  any_new_position_flag: boolean | null
}
```

The chart should use filing/public-information timing for the primary research-event marker. Transaction date may appear in tooltip detail.

## `GET /api/companies/{ticker}/statistics`

Purpose: anomaly, activity, event-study, bootstrap/randomization-null, and market-dislocation results for the selected/latest event.

```ts
type StatisticsResponse = {
  ticker: string
  research_event_id: string
  public_event_day: string
  anomaly: {
    score: number | null
    mahalanobis_distance: number | null
    reference_population: string | null
    reference_count: number | null
    status: string
  }
  activity: {
    score: number | null
    recent_purchase_rate: number | null
    historical_purchase_rate: number | null
    rate_ratio: number | null
    buyers_30d: number | null
    reference_population: string | null
    status: string
  }
  event_study: {
    car5: number | null
    car30: number | null
    car90: number | null
    status: string
  }
  statistical_validation: {
    comparable_event_count: number | null
    cohort_definition: string | null
    mean_car30: number | null
    bootstrap_ci_95: { lower: number, upper: number } | null
    randomization_p_value: number | null
    statistical_score: number | null
    status: string
  }
  market: {
    stock_return_90d: number | null
    sector_return_90d: number | null
    drawdown: number | null
    dislocation_score: number | null
    status: string
  }
}
```

Unavailable CAR horizons for recent events remain `null` with status; never pretend future CAR is known.

## `GET /api/companies/{ticker}/prediction`

Purpose: selected model probability and held-out model metrics.

```ts
type PredictionResponse = {
  ticker: string
  research_event_id: string
  model_name: string | null
  outperformance_probability: number | null
  classification_threshold: number | null
  metrics: {
    roc_auc: number | null
    brier_score: number | null
    precision: number | null
    recall: number | null
    f1: number | null
    sample_count: number | null
    positive_class_prevalence: number | null
    split_start: string | null
    split_end: string | null
  } | null
  status: string
}
```

## `POST /api/companies/{ticker}/explain`

Purpose: Gemini explanation of existing structured evidence.

The backend supplies structured quantitative evidence to Gemini. Gemini does not calculate or modify scores/predictions.

Response:

```ts
type ExplainResponse = {
  ticker: string
  why_flagged: string[]
  supportive_evidence: string[]
  risk_evidence: string[]
  uncertainty: string[]
  limitations: string[]
}
```

Failure of this endpoint must not affect quantitative endpoints or hide existing quantitative UI.

## `POST /api/companies/{ticker}/brief` (P1)

Purpose: optional ElevenLabs analyst brief based on the same structured research output.

To keep the hackathon contract self-contained without requiring a separate media route, the default concrete response is:

```ts
type BriefResponse = {
  ticker: string
  transcript: string
  audio_base64: string | null
  audio_mime_type: string | null
  status: "ok" | "audio_unavailable"
}
```

If the team intentionally changes to a stored audio URL/blob route, update this contract and frontend type together before implementation. Do not silently diverge.

## Error behavior

### Unknown ticker

HTTP 404:

```json
{"detail":"Unknown ticker"}
```

Exact wording may remain FastAPI-standard as long as frontend behavior is controlled and not blank.

### Provider/AI failure

Return a controlled API error appropriate to the endpoint. Do not leak stack traces, secrets, or provider credentials. Gemini/ElevenLabs failures do not invalidate already-computed quantitative data.
