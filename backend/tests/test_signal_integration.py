from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import pickle
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from app.db.models import Base, Company, Signal
from app.ml.dataset import build_ml_dataset, prepare_inference_features
from app.ml.training import fit_and_select, predict_selected
from app.services.signal_integration import build_signals, persist_signals
from test_ml_dataset import dataset_inputs
from test_ml_training import FAST, training_frames
from test_core_api import research


@pytest.fixture
def inputs():
    sessions = pd.bdate_range('2023-01-02', periods=300)
    events, features, labels, provenance = dataset_inputs([sessions[200]])
    events['public_event_day'] = sessions[201]
    frames = {}
    for name, field in [('anomaly', 'A'), ('activity', 'activity_score'), ('statistical', 'statistical_score'), ('dislocation', 'dislocation_score')]:
        frame = events.copy()
        frame[field] = 50.
        frame['status'] = 'complete'
        frame['unavailable_reasons' if name == 'dislocation' else 'missing_reasons'] = [[]]
        frames[name] = frame
    frames['statistical']['statistical_score'] = None
    frames['statistical']['status'] = 'insufficient_data'
    frames['statistical']['missing_reasons'] = [['bootstrap:fewer_than_10_eligible_comparable_events', 'randomization:fewer_than_10_eligible_comparable_events']]
    study = events.copy()
    for horizon in (5, 30, 90):
        study[f'car{horizon}'] = None
        study[f'car{horizon}_status'] = 'unavailable'
    return dict(events=events, event_features=features, feature_provenance=provenance,
                selection=fit_and_select(*training_frames(), FAST), **frames,
                event_studies=study, expected_sessions=sessions, observation_cutoff=sessions[200])


def history(inputs):
    sessions = inputs['expected_sessions']
    return pd.DataFrame([dict(research_event_id=f'h:{i}', ticker='ABC', information_date=sessions[i-1],
                             public_event_day=sessions[i], car30=.01, car30_status='complete') for i in range(10, 20)])


def test_prediction_partial_no_fitting_nonmutation(inputs, monkeypatch):
    before = deepcopy(inputs)
    artifact = pickle.dumps(inputs['selection'])
    monkeypatch.setattr('sklearn.pipeline.Pipeline.fit', lambda *a, **k: pytest.fail('no fitting'))
    batch = build_signals(**inputs)
    _, X, _ = prepare_inference_features(inputs['events'], inputs['event_features'], inputs['feature_provenance'])
    p = predict_selected(inputs['selection'], X[list(inputs['selection'].feature_schema)]).iloc[0].probability
    row = batch.payloads[0]
    assert row['model_probability'] == p
    assert row['score_status'] == 'partial'
    assert row['insider_edge_score'] == pytest.approx((.25*50+.15*50+.30*100*p+.15*50)/.85)
    assert row['car30'] is None and row['statistical_score'] is None
    assert pickle.dumps(inputs['selection']) == artifact
    for name, value in inputs.items():
        if isinstance(value, pd.DataFrame): pd.testing.assert_frame_equal(value, before[name])
    assert batch.audit['event:0']['components']['anomaly']['A'] == 50
    assert 'components' not in row


def test_complete_and_history_cutoff(inputs):
    inputs['statistical']['statistical_score'] = Decimal('80')
    inputs['statistical']['status'] = 'complete'
    inputs['statistical']['missing_reasons'] = [[]]
    inputs['statistical']['comparable_event_ids'] = [history(inputs).research_event_id.tolist()]
    inputs['comparable_history'] = history(inputs)
    row = build_signals(**inputs).payloads[0]
    assert row['score_status'] == 'complete'
    assert row['insider_edge_score'] == pytest.approx(.25*50+.15*50+.30*100*row['model_probability']+.15*80+.15*50)
    inputs['comparable_history'].loc[0, 'information_date'] = inputs['expected_sessions'][171]
    inputs['comparable_history'].loc[0, 'public_event_day'] = inputs['expected_sessions'][172]
    with pytest.raises(ValueError, match='comparator'): build_signals(**inputs)


@pytest.mark.parametrize('group', ['market', 'insider', 'buyers', 'categories'])
def test_future_provenance_shared(inputs, group):
    p = inputs['feature_provenance']
    p.loc[p.feature_group.eq(group), 'source_date'] = inputs['events'].iloc[0].information_date + pd.Timedelta(days=1)
    with pytest.raises(ValueError, match='future'): build_signals(**inputs)
    labels = dataset_inputs([inputs['events'].iloc[0].information_date])[2]
    with pytest.raises(ValueError, match='future'):
        build_ml_dataset(inputs['events'], inputs['event_features'], labels, p)


def test_shared_features_and_forbidden_exclusion(inputs):
    labels = dataset_inputs([inputs['events'].iloc[0].information_date])[2]
    for name in ('car30', 'Y', 'insider_edge_score'): inputs['event_features'][name] = 1e99
    dataset = build_ml_dataset(inputs['events'], inputs['event_features'], labels, inputs['feature_provenance'])
    _, X, availability = prepare_inference_features(inputs['events'], inputs['event_features'], inputs['feature_provenance'])
    pd.testing.assert_frame_equal(X, dataset.features)
    pd.testing.assert_frame_equal(availability, dataset.availability)
    assert 'Y' not in X and 'car30' not in X
    assert build_signals(**inputs).payloads[0]['score_status'] == 'partial'


@pytest.mark.parametrize('value', [None, np.nan, pd.NA, pd.NaT])
def test_missing_normalization(inputs, value):
    inputs['anomaly']['A'] = value
    inputs['anomaly']['status'] = 'missing_features'
    inputs['anomaly']['missing_reasons'] = [['missing_feature:drawdown_90d']]
    row = build_signals(**inputs).payloads[0]
    assert row['anomaly_score'] is None and row['insider_edge_score'] is None
    assert row['unavailable_components'] == ['A', 'S']


@pytest.mark.parametrize('value', [np.inf, -np.inf, 'bad', True, 101])
def test_invalid_component(inputs, value):
    inputs['anomaly']['A'] = value
    with pytest.raises(ValueError): build_signals(**inputs)


def test_decimal_and_nonhistory_failure(inputs):
    inputs['dislocation']['dislocation_score'] = Decimal('12.5')
    inputs['statistical']['missing_reasons'] = [['randomization:no_eligible_pseudo_event_dates']]
    row = build_signals(**inputs).payloads[0]
    assert row['dislocation_score'] == 12.5 and row['score_status'] == 'insufficient_data'


@pytest.mark.parametrize('change', ['duplicate', 'unknown', 'missing', 'ticker', 'date'])
def test_bad_identity(inputs, change):
    frame = inputs['activity']
    if change == 'duplicate': inputs['activity'] = pd.concat([frame, frame])
    elif change == 'unknown': frame.loc[0, 'research_event_id'] = 'wrong'
    elif change == 'missing': inputs['activity'] = frame.iloc[:0]
    elif change == 'ticker': frame.loc[0, 'ticker'] = 'XYZ'
    else: frame.loc[0, 'information_date'] += pd.Timedelta(days=1)
    with pytest.raises(ValueError): build_signals(**inputs)


def test_unavailable_model_and_metrics_rejection(inputs):
    inputs['selection'] = replace(inputs['selection'], status='insufficient_data', reasons=('no_model',))
    row = build_signals(**inputs).payloads[0]
    assert row['model_probability'] is None and row['score_status'] == 'insufficient_data'
    inputs['selection'] = {'roc_auc': .99, 'probability': .99}
    with pytest.raises(ValueError, match='ModelSelection'): build_signals(**inputs)


def test_outcome_cutoff(inputs):
    inputs['event_studies']['car5'] = .1
    inputs['event_studies']['car5_status'] = 'complete'
    with pytest.raises(ValueError, match='observable'): build_signals(**inputs)
    inputs['observation_cutoff'] = inputs['expected_sessions'][205]
    assert build_signals(**inputs).payloads[0]['car5'] == .1


def test_invalid_provenance(inputs):
    inputs['feature_provenance'].loc[0, 'verified'] = False
    with pytest.raises(ValueError, match='provenance'): build_signals(**inputs)


def test_idempotency_rescore_and_rollback(inputs):
    engine = create_engine('sqlite://', connect_args={'autocommit': False})
    Base.metadata.create_all(engine)
    batch = build_signals(**inputs)
    event = inputs['events'].iloc[0]
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='ABC', company_name='Synthetic ABC'))
        session.add(research(ticker='ABC', day=event.public_event_day.date(), research_event_id='event:0', information_date=event.information_date.date()))
    with Session(engine) as session, session.begin():
        persist_signals(session, batch)
        persist_signals(session, batch)
        assert session.scalar(select(func.count()).select_from(Signal)) == 1
    inputs['anomaly']['A'] = 80
    with Session(engine) as session, session.begin(): persist_signals(session, build_signals(**inputs))
    with pytest.raises(RuntimeError):
        with Session(engine) as session, session.begin():
            persist_signals(session, batch)
            raise RuntimeError('rollback caller')
    with Session(engine) as session: assert session.scalar(select(Signal)).anomaly_score == 80
    engine.dispose()


def test_multiple_events_deterministic_and_duplicate_rejection(inputs):
    for name in ('events', 'event_features', 'feature_provenance', 'anomaly', 'activity', 'statistical', 'dislocation', 'event_studies'):
        clone = inputs[name].copy(deep=True)
        clone['research_event_id'] = 'event:1'
        if 'information_date' in clone: clone['information_date'] = inputs['expected_sessions'][202]
        if 'public_event_day' in clone: clone['public_event_day'] = inputs['expected_sessions'][203]
        inputs[name] = pd.concat([clone, inputs[name]], ignore_index=True)
    first = build_signals(**inputs)
    assert [row['research_event_id'] for row in first.payloads] == ['event:0', 'event:1']
    for name in ('events', 'event_features', 'feature_provenance', 'anomaly', 'activity', 'statistical', 'dislocation', 'event_studies'):
        inputs[name] = inputs[name].iloc[::-1]
    assert build_signals(**inputs).payloads == first.payloads
    inputs['events'] = pd.concat([inputs['events'], inputs['events'].iloc[:1]])
    with pytest.raises(ValueError, match='duplicate'): build_signals(**inputs)


@pytest.mark.parametrize('field', ['activity', 'dislocation'])
def test_missing_other_required_components(inputs, field):
    score = 'activity_score' if field == 'activity' else 'dislocation_score'
    reason = 'missing_reasons' if field == 'activity' else 'unavailable_reasons'
    inputs[field][score] = None
    inputs[field]['status'] = 'insufficient_data'
    inputs[field][reason] = [['missing_source']]
    batch = build_signals(**inputs)
    assert batch.payloads[0]['insider_edge_score'] is None
    assert batch.audit['event:0']['score']['missing_reasons']['C' if field == 'activity' else 'D'] == ['missing_source']


def test_invalid_numeric_feature(inputs):
    inputs['event_features']['prior_return_5d'] = np.inf
    with pytest.raises(ValueError, match='numeric feature'): build_signals(**inputs)


def test_database_error_savepoint_does_not_erase_existing_signal(inputs):
    from sqlalchemy.exc import IntegrityError
    engine = create_engine('sqlite://', connect_args={'autocommit': False})
    Base.metadata.create_all(engine)
    batch = build_signals(**inputs)
    event = inputs['events'].iloc[0]
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='ABC', company_name='Synthetic ABC'))
        session.add(research(ticker='ABC', day=event.public_event_day.date(), research_event_id='event:0', information_date=event.information_date.date()))
    with Session(engine) as session, session.begin(): persist_signals(session, batch)
    corrupt = deepcopy(batch)
    corrupt.payloads[0]['score_status'] = 'invalid'
    corrupt.payloads[0]['anomaly_score'] = 99
    with Session(engine) as session, session.begin():
        with pytest.raises(IntegrityError): persist_signals(session, corrupt)
        assert session.scalar(select(Signal)).anomaly_score == 50
    engine.dispose()


def test_feature_metadata_mismatch_and_market_boundary(inputs):
    inputs['event_features']['ticker'] = 'OTHER'
    with pytest.raises(ValueError, match='metadata mismatch'): build_signals(**inputs)
    inputs['event_features'] = inputs['event_features'].drop(columns='ticker')
    p = inputs['feature_provenance']
    p.loc[p.feature_group.eq('market'), 'source_date'] = inputs['events'].iloc[0].information_date
    with pytest.raises(ValueError, match='future'): build_signals(**inputs)


# Use the actual Issue #13 result combiner to pin partial-output field shapes.
def statistical_partial(inputs, successful):
    from app.quant.statistical_validation import _combine_result
    h = history(inputs)
    event = inputs['events'].iloc[0]
    selection = pd.Series(dict(research_event_id=event.research_event_id, ticker=event.ticker,
                               information_date=event.information_date,
                               comparable_event_ids=h.research_event_id.tolist(),
                               comparable_event_count=10, cohort_definition='same_sector'))
    bootstrap = dict(status='complete', missing_reasons=[], mean_car30=.01,
                     bootstrap_ci_lower=.005, bootstrap_ci_upper=.015, bootstrap_q=1., B_support=100.)
    randomization = dict(status='complete', missing_reasons=[], T_obs=.01,
                         randomization_p_value=.02, P_support=80.)
    failed = dict(status='unavailable', missing_reasons=['calculation_failed'])
    row = _combine_result(selection, bootstrap if successful == 'bootstrap' else failed,
                          randomization if successful == 'randomization' else failed)
    inputs['statistical'] = pd.DataFrame([row])
    inputs['comparable_history'] = h


@pytest.mark.parametrize('successful', ['bootstrap', 'randomization'])
@pytest.mark.parametrize('future', [False, True])
def test_partial_statistics_validate_history_without_s(inputs, successful, future):
    statistical_partial(inputs, successful)
    if future:
        inputs['comparable_history'].loc[0, 'information_date'] = inputs['expected_sessions'][171]
        inputs['comparable_history'].loc[0, 'public_event_day'] = inputs['expected_sessions'][172]
        with pytest.raises(ValueError, match='comparator outcome'): build_signals(**inputs)
    else:
        batch = build_signals(**inputs)
        row = batch.payloads[0]
        assert row['statistical_score'] is None and row['score_status'] == 'insufficient_data'
        if successful == 'bootstrap':
            assert row['mean_car30'] == .01 and row['bootstrap_ci_lower'] == .005
        else:
            assert row['randomization_p_value'] == .02
            assert batch.audit['event:0']['components']['statistical']['P_support'] == 80


@pytest.mark.parametrize('bad', ['no_history', 'no_outcome', 'missing_date', 'outside_calendar', 'unknown_id'])
def test_retained_history_requires_complete_metadata(inputs, bad):
    statistical_partial(inputs, 'bootstrap')
    if bad == 'no_history': inputs['comparable_history'] = None
    elif bad == 'no_outcome': inputs['comparable_history'] = inputs['comparable_history'].drop(columns='car30_status')
    elif bad == 'missing_date': inputs['comparable_history'].loc[0, 'public_event_day'] = pd.NaT
    elif bad == 'outside_calendar':
        inputs['comparable_history'].loc[0, 'information_date'] = pd.Timestamp('2020-01-01')
        inputs['comparable_history'].loc[0, 'public_event_day'] = pd.Timestamp('2020-01-02')
    else: inputs['statistical'].at[0, 'comparable_event_ids'] = ['missing'] + history(inputs).research_event_id.tolist()[1:]
    with pytest.raises(ValueError): build_signals(**inputs)


@pytest.mark.parametrize('measurement', ['mean_car30', 'bootstrap_ci_lower', 'bootstrap_ci_upper', 'bootstrap_q', 'B_support', 'T_obs', 'randomization_p_value', 'P_support'])
def test_each_retained_measurement_triggers_guard(inputs, measurement):
    inputs['statistical'][measurement] = .01
    with pytest.raises(ValueError, match='historical evidence'): build_signals(**inputs)


def test_fully_unavailable_statistics_without_history_remains_partial(inputs):
    assert build_signals(**inputs).payloads[0]['score_status'] == 'partial'


@pytest.mark.parametrize('dtype,value', [('string', pd.NA), ('object', None), ('object', np.nan), ('string', ''), ('object', ' ')])
@pytest.mark.parametrize('target', ['activity', 'event_features'])
def test_missing_explicit_ticker_metadata(inputs, dtype, value, target):
    inputs[target]['ticker'] = pd.Series([value], dtype=dtype)
    with pytest.raises(ValueError, match='ticker'): build_signals(**inputs)


@pytest.mark.parametrize('dtype', ['string', 'object'])
def test_valid_ticker_dtype(inputs, dtype):
    inputs['activity']['ticker'] = inputs['activity'].ticker.astype(dtype)
    inputs['event_features']['ticker'] = inputs['events'].ticker.astype(dtype)
    assert build_signals(**inputs).payloads[0]['score_status'] == 'partial'


@pytest.mark.parametrize('target', ['activity', 'event_features'])
def test_mixed_valid_missing_tickers(inputs, target):
    for name in ('events', 'event_features', 'feature_provenance', 'anomaly', 'activity', 'statistical', 'dislocation', 'event_studies'):
        clone = inputs[name].copy()
        clone['research_event_id'] = 'event:1'
        if 'information_date' in clone: clone['information_date'] = inputs['expected_sessions'][202]
        if 'public_event_day' in clone: clone['public_event_day'] = inputs['expected_sessions'][203]
        inputs[name] = pd.concat([inputs[name], clone], ignore_index=True)
    inputs[target]['ticker'] = pd.Series(['ABC', pd.NA], dtype='string')
    with pytest.raises(ValueError, match='ticker'): build_signals(**inputs)


@pytest.mark.parametrize('field', ['research_event_id', 'information_date', 'public_event_day'])
def test_missing_identity_fields(inputs, field):
    inputs['event_studies'][field] = pd.NA
    with pytest.raises(ValueError): build_signals(**inputs)


def test_empty_integration(inputs):
    for name in ('events', 'event_features', 'feature_provenance', 'anomaly', 'activity', 'statistical', 'dislocation', 'event_studies'):
        inputs[name] = inputs[name].iloc[:0]
    batch = build_signals(**inputs)
    assert batch.payloads == () and batch.audit == {}


@pytest.mark.parametrize('bad', ['missing_group', 'bad_date', 'duplicate', 'unverified_buyer'])
def test_bad_provenance_cannot_enter_inference(inputs, bad):
    p = inputs['feature_provenance']
    if bad == 'missing_group': inputs['feature_provenance'] = p.iloc[1:]
    elif bad == 'bad_date':
        p['source_date'] = p.source_date.astype(object)
        p.loc[0, 'source_date'] = 'bad'
    elif bad == 'duplicate': inputs['feature_provenance'] = pd.concat([p, p.iloc[:1]])
    else: p.loc[p.feature_group.eq('buyers'), 'canonical_identity_verified'] = False
    with pytest.raises(ValueError): build_signals(**inputs)


def test_rescore_clears_nullable_fields(inputs):
    engine = create_engine('sqlite://', connect_args={'autocommit': False})
    Base.metadata.create_all(engine)
    event = inputs['events'].iloc[0]
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='ABC', company_name='Synthetic ABC'))
        session.add(research(ticker='ABC', day=event.public_event_day.date(), research_event_id='event:0', information_date=event.information_date.date()))
    inputs['event_studies']['car5'] = .1
    inputs['event_studies']['car5_status'] = 'complete'
    inputs['observation_cutoff'] = inputs['expected_sessions'][205]
    with Session(engine) as session, session.begin(): persist_signals(session, build_signals(**inputs))
    inputs['event_studies']['car5'] = None
    inputs['event_studies']['car5_status'] = 'unavailable'
    inputs['anomaly']['A'] = None
    inputs['anomaly']['status'] = 'missing_features'
    inputs['anomaly']['missing_reasons'] = [['missing_source']]
    with Session(engine) as session, session.begin(): persist_signals(session, build_signals(**inputs))
    with Session(engine) as session:
        row = session.scalar(select(Signal))
        assert row.car5 is None and row.anomaly_score is None and row.insider_edge_score is None
    engine.dispose()


def test_later_database_failure_rolls_back_earlier_signal_and_preserves_caller_work(inputs):
    from sqlalchemy.exc import IntegrityError
    for name in ('events', 'event_features', 'feature_provenance', 'anomaly', 'activity', 'statistical', 'dislocation', 'event_studies'):
        clone = inputs[name].copy()
        clone['research_event_id'] = 'event:1'
        if 'information_date' in clone: clone['information_date'] = inputs['expected_sessions'][202]
        if 'public_event_day' in clone: clone['public_event_day'] = inputs['expected_sessions'][203]
        inputs[name] = pd.concat([inputs[name], clone], ignore_index=True)
    engine = create_engine('sqlite://', connect_args={'autocommit': False})
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='ABC', company_name='Synthetic ABC'))
        for _, event in inputs['events'].iterrows():
            session.add(research(ticker='ABC', day=event.public_event_day.date(), research_event_id=event.research_event_id, information_date=event.information_date.date()))
    good = build_signals(**inputs)
    with Session(engine) as session, session.begin(): persist_signals(session, good)
    bad = deepcopy(good)
    bad.payloads[0]['anomaly_score'] = 99
    bad.payloads[1]['score_status'] = 'invalid'
    with Session(engine) as session, session.begin():
        session.add(Company(ticker='OTHER', company_name='Unrelated caller work'))
        with pytest.raises(IntegrityError): persist_signals(session, bad)
        assert session.scalar(select(Signal).where(Signal.research_event_id == 'event:0')).anomaly_score == 50
    with Session(engine) as session:
        assert session.get(Company, 'OTHER') is not None
        assert session.scalar(select(func.count()).select_from(Signal)) == 2
    engine.dispose()
