"""HTTP contracts and durable validated evidence; isolated synthetic data only."""
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app.api.schemas import StatisticsResponse, PredictionResponse
from app.db.models import Base, Company, ResearchEvent, Signal
from app.services import research_reads
from app.services.signal_integration import build_signals, persist_signals
from test_core_api import setup, seed, research
from test_signal_integration import inputs, history


@pytest.mark.parametrize('suffix', ['statistics', 'prediction'])
def test_routes_unknown_and_no_event(setup, suffix):
    client, _, app = setup
    assert f'/api/companies/{{ticker}}/{suffix}' in app.openapi()['paths']
    assert client.get(f'/api/companies/UNKNOWN/{suffix}').json() == {'detail': 'Unknown ticker'}
    assert client.get(f'/api/companies/UNKNOWN/{suffix}').status_code == 404
    assert client.get(f'/api/companies/AAPL/{suffix}').status_code == 404


def test_legacy_signal_exact_shapes_and_honest_unavailability(setup):
    client, engine, _ = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        row = research()
        session.add(row)
        session.flush()
        session.add(Signal(signal_id='signal', research_event_id=row.research_event_id, ticker='AAPL',
                           public_event_day=row.public_event_day, score_status='partial', unavailable_components=['S'],
                           anomaly_score=0, activity_score=20, model_probability=0, model_name='logistic_regression',
                           car30=.5, mean_car30=.9, statistical_score=80))
    stats_response = client.get('/api/companies/AAPL/statistics')
    pred_response = client.get('/api/companies/AAPL/prediction')
    assert stats_response.status_code == pred_response.status_code == 200
    stats, pred = stats_response.json(), pred_response.json()
    StatisticsResponse.model_validate(stats)
    PredictionResponse.model_validate(pred)
    assert set(stats) == set(StatisticsResponse.model_fields)
    assert set(pred) == set(PredictionResponse.model_fields)
    assert stats['anomaly']['score'] == 0
    assert stats['anomaly']['mahalanobis_distance'] is None
    assert stats['event_study']['car30'] is None  # no outcome-availability provenance
    assert stats['statistical_validation']['mean_car30'] is None
    assert pred['outperformance_probability'] == 0
    assert pred['classification_threshold'] is None and pred['metrics'] is None
    assert pred['status'] == 'partial_evaluation_unavailable'
    with Session(engine) as session, session.begin():
        session.add(research(day=date(2026, 10, 5)))
    stats = client.get('/api/companies/AAPL/statistics').json()
    pred = client.get('/api/companies/AAPL/prediction').json()
    assert stats['research_event_id'] == pred['research_event_id'] == 'AAPL:2026-10-05'
    assert stats['anomaly']['score'] is None and pred['outperformance_probability'] is None
    assert client.get('/api/companies/AAPL').json()['latest_signal'] is None
    assert client.get('/api/radar').json()['items'][0]['insider_edge_score'] is None


@pytest.mark.parametrize('probability', [-.01, 1.01, float('inf')])
def test_invalid_probability_rejected(probability):
    with pytest.raises(ValidationError):
        PredictionResponse(ticker='AAPL', research_event_id='event', model_name=None,
                           outperformance_probability=probability, classification_threshold=None,
                           metrics=None, status='unavailable')


def test_statistics_section_shapes(setup):
    client, engine, _ = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        session.add(research())
    data = client.get('/api/companies/AAPL/statistics').json()
    expected = {
        'anomaly': {'score', 'mahalanobis_distance', 'reference_population', 'reference_count', 'status'},
        'activity': {'score', 'recent_purchase_rate', 'historical_purchase_rate', 'rate_ratio', 'buyers_30d', 'reference_population', 'status'},
        'event_study': {'car5', 'car30', 'car90', 'status'},
        'statistical_validation': {'comparable_event_count', 'cohort_definition', 'mean_car30', 'bootstrap_ci_95', 'randomization_p_value', 'statistical_score', 'status'},
        'market': {'stock_return_90d', 'sector_return_90d', 'drawdown', 'dislocation_score', 'status'},
    }
    for section, keys in expected.items():
        assert set(data[section]) == keys
        assert all(value is None for key, value in data[section].items() if key != 'status')


def test_validated_comparator_summary_durable_and_version_bound(inputs):
    inputs['comparable_history'] = history(inputs)
    stats = inputs['statistical']
    stats['comparable_event_ids'] = [history(inputs).research_event_id.tolist()]
    stats['comparable_event_count'] = 10
    stats['cohort_definition'] = 'same_sector'
    stats['mean_car30'] = 0.
    stats['bootstrap_ci_lower'] = -.02
    stats['bootstrap_ci_upper'] = .03
    stats['randomization_p_value'] = .1
    stats['status'] = 'partial'
    inputs['model_version'] = 'frozen-1'
    batch = build_signals(**inputs)
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    event = inputs['events'].iloc[0]
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='ABC', company_name='Synthetic'))
        session.add(research(ticker='ABC', day=event.public_event_day.date(), research_event_id='event:0',
                             information_date=event.information_date.date()))
    with Session(engine) as session, session.begin():
        persist_signals(session, batch)
    with Session(engine) as session:
        response = research_reads.statistics(session, SimpleNamespace(ticker='ABC'))
        result = response.statistical_validation
        assert result.mean_car30 == 0 and result.comparable_event_count == 10
        assert result.bootstrap_ci_95.model_dump() == {'lower': -.02, 'upper': .03}
        assert result.randomization_p_value == .1 and result.statistical_score is None
        evidence = session.get(ResearchEvent, 'event:0').feature_metadata[research_reads.EVIDENCE_KEY]
        comparators = evidence['historical_provenance']['comparators']
        assert len(comparators) == 10
        assert all(row['car30_end'] < evidence['information_date'] for row in comparators)
        session.scalar(select(Signal)).model_version = 'different-version'
        session.flush()
        assert research_reads.statistics(session, SimpleNamespace(ticker='ABC')).statistical_validation.mean_car30 is None
    engine.dispose()


def test_persisted_evidence_fresh_session_idempotent(inputs):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    event = inputs['events'].iloc[0]
    inputs['anomaly']['D'] = 2.5
    inputs['anomaly']['reference_rule'] = 'sector'
    inputs['anomaly']['reference_sample_size'] = 30
    inputs['activity']['recent_rate'] = 0
    inputs['activity']['buyers_30d'] = None
    inputs['dislocation']['stock_return_90d'] = -.2
    inputs['event_studies']['car5'] = .1
    inputs['event_studies']['car5_status'] = 'complete'
    inputs['observation_cutoff'] = inputs['expected_sessions'][205]
    batch = build_signals(**inputs)
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='ABC', company_name='Synthetic'))
        session.add(research(ticker='ABC', day=event.public_event_day.date(), research_event_id='event:0',
                             information_date=event.information_date.date(), feature_metadata={'source': 'preserved'}))
    for _ in range(2):
        with Session(engine) as session, session.begin():
            persist_signals(session, batch)
    with Session(engine) as session:
        frozen = SimpleNamespace(ticker='ABC')
        stats = research_reads.statistics(session, frozen)
        pred = research_reads.prediction(session, frozen)
        assert stats.anomaly.mahalanobis_distance == 2.5 and stats.anomaly.reference_count == 30
        assert stats.activity.recent_purchase_rate == 0 and stats.activity.buyers_30d is None
        assert stats.market.stock_return_90d == -.2
        assert stats.event_study.car5 == .1 and stats.event_study.car30 is None
        assert stats.statistical_validation.status == 'insufficient_data'
        assert pred.classification_threshold == inputs['selection'].threshold
        assert 0 <= pred.outperformance_probability <= 1 and pred.metrics is None
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
        stored = session.get(ResearchEvent, 'event:0')
        assert stored.feature_metadata['source'] == 'preserved'
        original = stored.feature_metadata[research_reads.EVIDENCE_KEY]
        stored.feature_metadata = {**stored.feature_metadata, research_reads.EVIDENCE_KEY: {
            **original, 'observation_cutoff': '2099-01-01'}}
        assert research_reads.statistics(session, frozen).event_study.car5 is None
        stored.feature_metadata = {**stored.feature_metadata, research_reads.EVIDENCE_KEY: {
            **original, 'information_date': '2099-01-01'}}
        assert research_reads.statistics(session, frozen).anomaly.mahalanobis_distance is None
    engine.dispose()
