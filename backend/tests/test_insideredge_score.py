from dataclasses import replace
from copy import deepcopy
import pytest
from app.quant.insideredge_score import Component, ScoreInput, score_event, build_insideredge_scores


def event():
    return ScoreInput('event:1', Component(20), Component(40), Component(.6),
                      Component(80), Component(100), 'logistic_regression', 'v1')


def test_full_formula_and_probability_conversion():
    result = score_event(event())
    assert result['insider_edge_score'] == 56
    assert result['components']['M'] == 60
    assert result['ml_outperformance_probability'] == .6
    assert result['score_status'] == 'complete'
    assert result['unavailable_components'] == []
    assert result['applied_weights'] == result['weights']
    assert result['original_weight_total'] == 1


def test_partial_preserves_actual_upstream_reasons():
    reasons = ('bootstrap:fewer_than_10_eligible_comparable_events',
               'randomization:fewer_than_10_eligible_comparable_events')
    result = score_event(replace(event(), S=Component(None, reasons)))
    assert result['insider_edge_score'] == pytest.approx(44 / .85)
    assert result['score_status'] == 'partial'
    assert result['components']['S'] is None
    assert result['unavailable_components'] == ['S']
    assert result['missing_reasons'] == {'S': list(reasons)}
    assert result['original_weight_total'] == .85
    assert sum(result['applied_weights'].values()) == pytest.approx(1)


@pytest.mark.parametrize('reasons', [('randomization:no_eligible_pseudo_event_dates',),
    ('bootstrap:bootstrap_calculation_failed',), ('missing_focal_sector',),
    ('fewer_than_10_eligible_comparable_events', 'unknown_failure')])
def test_other_statistical_failures(reasons):
    result = score_event(replace(event(), S=Component(None, reasons)))
    assert result['score_status'] == 'insufficient_data'
    assert result['insider_edge_score'] is None and result['applied_weights'] == {}


@pytest.mark.parametrize('name', ['A', 'C', 'probability', 'D'])
def test_required_missing(name):
    result = score_event(replace(event(), **{name: Component(None, ('missing_input',))}))
    assert result['insider_edge_score'] is None
    assert result['score_status'] == 'insufficient_data'
    assert result['unavailable_components'] == ['M' if name == 'probability' else name]


def test_multiple_missing_and_zero_distinction():
    result = score_event(replace(event(), A=Component(0), C=Component(None, ('identity_missing',)),
                                 S=Component(None, ('fewer_than_10_eligible_comparable_events',))))
    assert result['components']['A'] == 0
    assert result['unavailable_components'] == ['C', 'S']
    assert result['insider_edge_score'] is None


@pytest.mark.parametrize('value', [0, 100])
def test_endpoints(value):
    result = score_event(ScoreInput('x', Component(value), Component(value), Component(value / 100),
                                   Component(value), Component(value)))
    assert result['insider_edge_score'] == value


@pytest.mark.parametrize('name', ['A', 'C', 'probability', 'S', 'D'])
@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), True, False, '20', 'bad', -1, 101])
def test_invalid_available_values(name, value):
    with pytest.raises(ValueError):
        score_event(replace(event(), **{name: Component(value)}))


@pytest.mark.parametrize('value', [1.01, 60])
def test_probability_is_not_percentage(value):
    with pytest.raises(ValueError):
        score_event(replace(event(), probability=Component(value)))


@pytest.mark.parametrize('factory', [lambda: Component(None), lambda: Component(5, ('failed',)),
    lambda: Component(None, ('',)), lambda: Component(None, ['failed'])])
def test_invalid_reasons(factory):
    with pytest.raises(ValueError):
        factory()


def test_order_integrity_provenance_and_no_mutation():
    inputs = [replace(event(), research_event_id='z'), event()]
    before = deepcopy(inputs)
    result = build_insideredge_scores(inputs)
    assert inputs == before
    assert [row['research_event_id'] for row in result] == ['event:1', 'z']
    assert result[0]['model_name'] == 'logistic_regression'
    assert result[0]['model_version'] == 'v1'
    assert build_insideredge_scores([]) == []
    with pytest.raises(ValueError, match='duplicate'):
        build_insideredge_scores([event(), event()])
    result[0]['weights']['A'] = 999
    assert score_event(event())['weights']['A'] == .25


@pytest.mark.parametrize('identity', [None, '', ' ', 123])
def test_invalid_ids(identity):
    with pytest.raises(ValueError):
        build_insideredge_scores([replace(event(), research_event_id=identity)])


def test_no_metrics_or_classification_interface():
    with pytest.raises(TypeError):
        ScoreInput(**dict(event().__dict__, metrics={'roc_auc': .99}))
    with pytest.raises(TypeError):
        ScoreInput(**dict(event().__dict__, classification=1))


@pytest.mark.parametrize('name', ['A', 'C', 'probability', 'S', 'D'])
def test_mismatched_component_ids_rejected(name):
    original = event()
    component = replace(getattr(original, name), research_event_id='another:event')
    with pytest.raises(ValueError, match='does not match'):
        score_event(replace(original, **{name: component}))


def test_matching_component_id_and_unrounded_result():
    result = score_event(replace(event(), A=Component(20.123456789, research_event_id='event:1')))
    assert result['insider_edge_score'] == pytest.approx(56 + .25 * .123456789, abs=1e-12)
