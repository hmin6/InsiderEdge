"""Issue #6 response shapes from docs/API_CONTRACT.md."""
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
