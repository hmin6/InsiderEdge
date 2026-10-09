"""Read-only evidence boundary for AI; never calculate quant/ML outputs."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.api.schemas import Probability, RadarItem, ResearchEventSummary
from app.db.models import Company
from app.services.companyfacts import METRICS, as_of
from app.services.core_reads import latest_events, radar_item


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)
    ticker: str
    company_name: str
    sector: str | None
    information_date: date | None
    event: ResearchEventSummary | None
    event_diagnostics: dict
    precomputed_signal: RadarItem | None
    model_name: str | None
    model_version: str | None
    model_probability: Probability | None
    historical_statistics: dict
    market_context: dict
    fundamentals: dict
    limitations: list[str]
    purpose: Literal['research_priority_explanation'] = 'research_priority_explanation'


def assemble(session, frozen, universe):
    """One replaceable assembly interface for future Person 2 persisted outputs."""
    latest = session.execute(latest_events([frozen.ticker])).first()
    event, signal, stored = latest if latest else (None, None, session.get(Company, frozen.ticker))
    limitations = [
        'Research priority is not an investment recommendation or evidence of causation.',
        'Frozen current-universe historical research can have survivorship/selection bias.',
        'Current-event realized CAR5/CAR30/CAR90 outcomes are excluded from information-time evidence.',
        'Historical comparable-outcome statistics are unavailable pending verified outcome-availability provenance.',
        'Pre-event stock return, sector return and drawdown are not yet integrated as persisted evidence.',
        'Held-out model evaluation metrics are not yet integrated as persisted evidence.',
    ]
    if event is None:
        limitations.append('No persisted research event is available; no event-time fundamentals can be selected.')
    if signal is None:
        limitations.append('No matching persisted signal/model prediction is available; missing scores are unknown, not zero.')
    else:
        missing = [name for name in ('anomaly_score', 'activity_score', 'statistical_score',
                                    'dislocation_score', 'model_probability', 'insider_edge_score')
                   if getattr(signal, name) is None]
        if missing:
            limitations.append('Unavailable persisted signal fields: ' + ', '.join(missing) + '.')
    facts = {metric: as_of(session, universe, frozen.ticker, metric, event.information_date)
             if event else None for metric in METRICS}
    missing_facts = [metric for metric, observation in facts.items()
                     if observation is None or observation['value'] is None]
    if missing_facts:
        limitations.append('Unavailable point-in-time fundamentals: ' + ', '.join(missing_facts) + '.')
    metadata = (event.feature_metadata or {}) if event else {}
    # Never forward arbitrary raw source text or unknown metadata as instructions.
    diagnostics = {key: metadata[key] for key in (
        'buyer_identity_status', 'buyer_identity_unknown', 'role_attribution_unverified',
        'purchase_value_incomplete', 'role_information_incomplete',
    ) if key in metadata}
    supported_statuses = {'buyer_identity_unknown', 'role_attribution_unverified',
                          'purchase_value_incomplete', 'role_information_incomplete',
                          'insufficient_market_history', 'missing_stock_event_price'}
    diagnostics['statuses'] = [status for status in metadata.get('statuses', [])
                               if status in supported_statuses]
    if diagnostics['statuses']:
        limitations.append('Persisted event diagnostics: ' + ', '.join(diagnostics['statuses']) + '.')
    if event and event.unique_buyer_count is None:
        limitations.append('Underlying unique buyer identity/count is unknown; filing-wide owners are not a buyer count.')
    return Evidence(
        ticker=frozen.ticker, company_name=stored.company_name if stored else frozen.company_name,
        sector=stored.sector if stored else frozen.sector,
        information_date=event.information_date if event else None,
        event=ResearchEventSummary.model_validate(event) if event else None,
        event_diagnostics=diagnostics,
        precomputed_signal=radar_item(event, signal, stored, frozen) if event else None,
        model_name=signal.model_name if signal else None,
        model_version=signal.model_version if signal else None,
        model_probability=signal.model_probability if signal else None,
        historical_statistics={
            'status': 'unavailable_pending_outcome_availability_provenance',
            'comparable_event_count': None, 'cohort_definition': None, 'mean_car30': None,
            'bootstrap_ci_95': None, 'randomization_p_value': None,
        },
        market_context={'status': 'unavailable', 'stock_return_90d': None,
                        'sector_return_90d': None, 'drawdown': None},
        fundamentals=facts, limitations=limitations,
    )
