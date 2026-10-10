"""Issue #6 read and Issue #8 AI response shapes from docs/API_CONTRACT.md."""
from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

Score = Annotated[float, Field(ge=0, le=100)]
Probability = Annotated[float, Field(ge=0, le=1)]


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, allow_inf_nan=False)


class RadarItem(ResponseModel):
    ticker: str
    company_name: str
    sector: str | None
    public_event_day: date
    insider_signal_summary: str | None
    insider_edge_score: Score | None
    anomaly_score: Score | None
    activity_score: Score | None
    statistical_score: Score | None
    dislocation_score: Score | None
    ml_outperformance_probability: Probability | None
    score_status: Literal['complete', 'partial', 'insufficient_data']
    unavailable_components: list[str]


class RadarResponse(ResponseModel):
    items: list[RadarItem]


class CompanyResponse(ResponseModel):
    ticker: str
    cik: str | None
    company_name: str
    sector: str | None
    industry: str | None
    latest_public_event_day: date | None
    latest_signal: RadarItem | None


class PricePoint(ResponseModel):
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adjusted_close: float | None
    analysis_price: float | None
    volume: int | None


class PricesResponse(ResponseModel):
    ticker: str
    prices: list[PricePoint]


class InsiderTransaction(ResponseModel):
    transaction_id: str
    accession_number: str
    source_type: Literal['bulk', 'edgar']
    document_type: str | None
    insider_name: str | None
    insider_role: str | None
    transaction_date: date
    filing_date: date
    accepted_at: AwareDatetime | None
    public_event_day: date | None
    transaction_code: str
    acquired_or_disposed: str
    derivative_flag: bool
    security_title: str | None
    shares: float | None
    price: float | None
    transaction_value: float | None
    shares_owned_after: float | None
    direct_or_indirect: str | None
    aff10b5one: bool | None
    is_amendment: bool
    is_p0_qualifying: bool


class ResearchEventSummary(ResponseModel):
    research_event_id: str
    public_event_day: date
    information_date: date
    source_transaction_count: int
    source_filing_count: int
    aggregate_purchase_value: float | None
    unique_buyer_count: int | None
    role_bucket: Literal['Executive', 'Director', 'Other']
    has_executive: bool
    has_director: bool
    has_other: bool
    has_cfo: bool | None
    max_valid_ownership_change_pct: float | None
    any_new_position_flag: bool | None


class InsidersResponse(ResponseModel):
    ticker: str
    transactions: list[InsiderTransaction]
    research_events: list[ResearchEventSummary]


class ExplainResponse(ResponseModel):
    ticker: str
    why_flagged: list[str]
    supportive_evidence: list[str]
    risk_evidence: list[str]
    uncertainty: list[str]
    limitations: list[str]


class BriefResponse(ResponseModel):
    ticker: str
    transcript: str
    audio_base64: str | None
    audio_mime_type: str | None
    status: Literal['ok', 'audio_unavailable']


class AnomalyResponse(ResponseModel):
    score: Score | None
    mahalanobis_distance: float | None
    reference_population: str | None
    reference_count: int | None
    status: str


class ActivityResponse(ResponseModel):
    score: Score | None
    recent_purchase_rate: float | None
    historical_purchase_rate: float | None
    rate_ratio: float | None
    buyers_30d: int | None
    reference_population: str | None
    status: str


class EventStudyResponse(ResponseModel):
    car5: float | None
    car30: float | None
    car90: float | None
    status: str


class ConfidenceInterval(ResponseModel):
    lower: float
    upper: float


class StatisticalValidationResponse(ResponseModel):
    comparable_event_count: int | None
    cohort_definition: str | None
    mean_car30: float | None
    bootstrap_ci_95: ConfidenceInterval | None
    randomization_p_value: Probability | None
    statistical_score: Score | None
    status: str


class MarketResponse(ResponseModel):
    stock_return_90d: float | None
    sector_return_90d: float | None
    drawdown: float | None
    dislocation_score: Score | None
    status: str


class StatisticsResponse(ResponseModel):
    ticker: str
    research_event_id: str
    public_event_day: date
    anomaly: AnomalyResponse
    activity: ActivityResponse
    event_study: EventStudyResponse
    statistical_validation: StatisticalValidationResponse
    market: MarketResponse


class PredictionMetrics(ResponseModel):
    roc_auc: Probability | None
    brier_score: Probability | None
    precision: Probability | None
    recall: Probability | None
    f1: Probability | None
    sample_count: int | None
    positive_class_prevalence: Probability | None
    split_start: date | None
    split_end: date | None


class PredictionResponse(ResponseModel):
    ticker: str
    research_event_id: str
    model_name: str | None
    outperformance_probability: Probability | None
    classification_threshold: Probability | None
    metrics: PredictionMetrics | None
    status: str
