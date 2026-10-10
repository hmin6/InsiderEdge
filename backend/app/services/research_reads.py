"""Read persisted results only; never fit, evaluate, fetch or select a model."""
from datetime import date
from decimal import Decimal
import math

from fastapi import HTTPException

from app.api.schemas import PredictionResponse, StatisticsResponse
from app.services.core_reads import latest_events

EVIDENCE_KEY = 'signal_api_evidence_v1'


def signal_binding(row):
    names = ('research_event_id', 'ticker', 'public_event_day', 'model_version', 'model_name',
             'model_probability', 'score_version', 'anomaly_score', 'activity_score',
             'dislocation_score', 'statistical_score', 'car5', 'car30', 'car90',
             'comparable_event_count', 'comparable_cohort', 'mean_car30',
             'bootstrap_ci_lower', 'bootstrap_ci_upper', 'randomization_p_value')
    values = {name: row[name] if isinstance(row, dict) else getattr(row, name) for name in names}
    return {name: value.isoformat() if isinstance(value, date) else round(float(value), 10) if isinstance(value, (float, Decimal)) else value
            for name, value in values.items()}


def empty_section(model, status='unavailable_not_persisted'):
    return {name: status if name == 'status' else None for name in model.model_fields}


def optional_number(value):
    """DataFrame missing scalars remain JSON null, including pandas NA/NaN."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def statistics_values(row, components=None):
    from app.api.schemas import (AnomalyResponse, ActivityResponse, EventStudyResponse,
                                 StatisticalValidationResponse, MarketResponse)
    sections = dict(anomaly=empty_section(AnomalyResponse), activity=empty_section(ActivityResponse),
                    event_study=empty_section(EventStudyResponse),
                    statistical_validation=empty_section(StatisticalValidationResponse),
                    market=empty_section(MarketResponse))
    if row is None:
        return sections
    for section, field, target in [('anomaly', 'anomaly_score', 'score'),
                                    ('activity', 'activity_score', 'score'),
                                    ('market', 'dislocation_score', 'dislocation_score')]:
        sections[section][target] = row[field]
        if row[field] is not None:
            sections[section]['status'] = 'partial_diagnostics_unavailable'
    if components is None:
        # Legacy rows have no durable comparator/outcome-availability provenance.
        return sections
    a, c, s, d = (components[key] for key in ('anomaly', 'activity', 'statistical', 'dislocation'))
    for section, source, mapping in [
        ('anomaly', a, {'mahalanobis_distance': 'D', 'reference_population': 'reference_rule',
                        'reference_count': 'reference_sample_size'}),
        ('activity', c, {'recent_purchase_rate': 'recent_rate', 'historical_purchase_rate': 'historical_rate',
                         'rate_ratio': 'rate_ratio', 'buyers_30d': 'buyers_30d', 'reference_population': 'reference_rule'}),
        ('market', d, {'stock_return_90d': 'stock_return_90d', 'sector_return_90d': 'sector_return_90d',
                       'drawdown': 'drawdown_90d'}),
    ]:
        sections[section].update({target: source.get(key) if target == 'reference_population'
                                 else optional_number(source.get(key)) for target, key in mapping.items()})
        sections[section]['status'] = source['status']
    sections['event_study'].update({key: row[key] for key in ('car5', 'car30', 'car90')})
    available = sum(row[key] is not None for key in ('car5', 'car30', 'car90'))
    sections['event_study']['status'] = 'complete' if available == 3 else ('partial' if available else 'unavailable')
    validation = sections['statistical_validation']
    for key in ('comparable_event_count', 'mean_car30', 'randomization_p_value', 'statistical_score'):
        validation[key] = row[key]
    validation['cohort_definition'] = row['comparable_cohort']
    lower, upper = row['bootstrap_ci_lower'], row['bootstrap_ci_upper']
    validation['bootstrap_ci_95'] = dict(lower=lower, upper=upper) if lower is not None and upper is not None else None
    validation['status'] = s['status']
    return sections


def latest(session, frozen):
    result = session.execute(latest_events([frozen.ticker])).first()
    if result is None:
        # Contract event identity is non-null; do not invent an event ID.
        raise HTTPException(404, 'No research event available')
    event, signal, _ = result
    evidence = (event.feature_metadata or {}).get(EVIDENCE_KEY)
    if signal is None or not isinstance(evidence, dict):
        return event, signal, None
    # Bind evidence to the exact persisted signal and event information boundary.
    binding = signal_binding(signal)
    if (evidence.get('information_date') != event.information_date.isoformat()
            or evidence.get('binding') != binding or not binding):
        evidence = None
    return event, signal, evidence


def statistics(session, frozen):
    event, signal, evidence = latest(session, frozen)
    if evidence:
        response = StatisticsResponse.model_validate(evidence['statistics'])
        # Outcomes are retrospective display only; never forward to predictive inputs.
        if date.fromisoformat(evidence['observation_cutoff']) >= date.today():
            response.event_study = type(response.event_study)(**empty_section(type(response.event_study), 'unavailable_future_cutoff'))
        return response
    row = {name: getattr(signal, name) for name in ('anomaly_score', 'activity_score', 'dislocation_score')} if signal else None
    return StatisticsResponse(ticker=frozen.ticker, research_event_id=event.research_event_id,
                              public_event_day=event.public_event_day, **statistics_values(row))


def prediction(session, frozen):
    event, signal, evidence = latest(session, frozen)
    return PredictionResponse(
        ticker=frozen.ticker, research_event_id=event.research_event_id,
        model_name=signal.model_name if signal else None,
        outperformance_probability=signal.model_probability if signal else None,
        classification_threshold=evidence['classification_threshold'] if evidence else None,
        # No frozen held-out artifact is persisted. Never replace it with validation metrics.
        metrics=None, status='partial_evaluation_unavailable' if signal and signal.model_probability is not None else 'unavailable',
    )
