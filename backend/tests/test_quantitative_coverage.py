"""Synthetic read-only source consistency tests, not historical provenance proof."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from app.services.quantitative_coverage import quantitative_coverage


def inputs():
    event = NS(research_event_id='SYN:2024-01-03', ticker='SYN', information_date=date(2024, 1, 2), public_event_day=date(2024, 1, 3),
               source_transaction_count=1, source_filing_count=1, aggregate_purchase_value=Decimal('0'),
               feature_metadata={'builder_version': 'issue5-v1', 'source_transaction_ids': ['tx'], 'source_accessions': ['acc']})
    row = NS(document_type='4', source_table='NONDERIV_TRANS', ticker='SYN', public_event_day=event.public_event_day, accession_number='acc',
             transaction_value=Decimal('0'), filing_date=event.information_date,
             transaction_date=date(2024, 1, 1), is_p0_qualifying=True, transaction_code='P',
             acquired_or_disposed='A', derivative_flag=False, is_amendment=False)
    session = Mock()
    session.scalars.return_value = [row]
    return session, event, row


def test_descriptive_zero_and_nonmutation():
    session, event, row = inputs()
    before = deepcopy(vars(event))
    result = quantitative_coverage(session, event, None)
    assert result['status'] == 'descriptive_only'
    assert result['purchase_count'] == 1 and result['purchase_value'] == 0
    assert result['partial_index'] is None
    assert result['coverage_weight'] == 0
    assert vars(event) == before
    session.commit.assert_not_called()
    session.execute.assert_not_called()


@pytest.mark.parametrize('field,value', [
    ('ticker', 'OTHER'), ('filing_date', date(2024, 1, 3)),
    ('public_event_day', date(2024, 1, 4)), ('transaction_date', date(2024, 1, 3)),
    ('is_p0_qualifying', False), ('transaction_code', 'S'), ('derivative_flag', True),
    ('is_amendment', True), ('accession_number', 'wrong'),
    ('document_type', '4/A'), ('source_table', 'DERIV_TRANS'),
])
def test_inconsistent_sources_unavailable(field, value):
    session, event, row = inputs()
    setattr(row, field, value)
    result = quantitative_coverage(session, event, None)
    assert result['status'] == 'unavailable'
    assert result['purchase_count'] is None and result['purchase_value'] is None


@pytest.mark.parametrize('value', [None, Decimal('-1'), Decimal('NaN'), Decimal('Infinity'), Decimal('1')])
def test_invalid_or_incomplete_value_preserves_only_count(value):
    session, event, row = inputs()
    row.transaction_value = value
    result = quantitative_coverage(session, event, None)
    assert result['purchase_count'] == 1
    assert result['purchase_value'] is None
    assert 'purchase_value_missing_or_inconsistent' in result['reasons']


@pytest.mark.parametrize('metadata', [None, {}, {'source_transaction_ids': []},
    {'builder_version': 'issue5-v1', 'source_transaction_ids': [['bad']], 'source_accessions': ['acc']}])
def test_no_verified_lineage(metadata):
    session, event, _ = inputs()
    event.feature_metadata = metadata
    result = quantitative_coverage(session, event, None)
    assert result['status'] == 'unavailable'
    session.scalars.assert_not_called()


def test_complete_signal_unchanged():
    session, event, _ = inputs()
    assert quantitative_coverage(session, event, NS(score_status='complete')) is None
    session.scalars.assert_not_called()



def test_future_boundary_rejected():
    session, event, row = inputs()
    event.information_date = date.max
    event.public_event_day = date.max
    assert quantitative_coverage(session, event, None)['status'] == 'unavailable'


def signal(event, **changes):
    values = dict(research_event_id=event.research_event_id, ticker=event.ticker,
                  public_event_day=event.public_event_day, score_status='insufficient_data',
                  unavailable_components=['C', 'S'], anomaly_score=0, activity_score=None,
                  model_probability=.5, statistical_score=None, dislocation_score=100)
    values.update(changes)
    return NS(**values)


def test_partial_formula_missing_zero_and_no_imputation():
    session, event, _ = inputs()
    result = quantitative_coverage(session, event, signal(event))
    assert result['status'] == 'provisional'
    assert result['coverage_weight'] == pytest.approx(.70)
    assert result['partial_index'] == pytest.approx(30 / .70)
    assert result['available_components'] == ['A', 'M', 'D']
    assert result['missing_components'] == ['C', 'S']
    assert result['imputed_components'] == [] and result['imputation_method'] is None


@pytest.mark.parametrize('changes,expected', [
    ({'activity_score': 20, 'unavailable_components': ['S']}, 33 / .85),
    ({'dislocation_score': None, 'unavailable_components': ['C', 'S', 'D']}, 15 / .55),
    ({'model_probability': None, 'unavailable_components': ['C', 'M', 'S']}, None),
    ({'anomaly_score': None, 'dislocation_score': None, 'unavailable_components': ['A', 'C', 'S', 'D']}, None),
    ({'anomaly_score': None, 'activity_score': 0, 'statistical_score': 100, 'model_probability': None,
      'unavailable_components': ['A', 'M']}, None),
])
def test_component_and_weight_thresholds(changes, expected):
    session, event, _ = inputs()
    result = quantitative_coverage(session, event, signal(event, **changes))
    if expected is None:
        assert result['partial_index'] is None
    else:
        assert result['partial_index'] == pytest.approx(expected)


@pytest.mark.parametrize('changes', [
    {'anomaly_score': True}, {'anomaly_score': -1}, {'dislocation_score': 101},
    {'model_probability': 1.01}, {'model_probability': float('nan')},
    {'anomaly_score': Decimal('Infinity')}, {'anomaly_score': '50'},
    {'unavailable_components': ['A', 'C', 'S']}, {'ticker': 'OTHER'},
    {'anomaly_score': None},
])
def test_invalid_or_contradictory_components_reject_index(changes):
    session, event, _ = inputs()
    assert quantitative_coverage(session, event, signal(event, **changes))['partial_index'] is None


@pytest.mark.parametrize('metadata', [
    {'model_available_at': '2024-01-04'}, {'source_date': '2024-01-04'},
    {'component_available_at': {'A': '2024-01-04'}},
    {'signal_api_evidence_v1': {}}, {'available_at': 'bad'},
    {'available_at': '2024-01-01garbage'},
    {'market_history': {'last_valid_stock_date': '2024-01-02'}},
    {'historical_provenance': {'comparators': [{'research_event_id': 'OTHER',
      'information_date': '2024-01-03', 'car30_end': '2024-01-01'}]}},
])
def test_known_future_or_inconsistent_evidence_rejected(metadata):
    session, event, _ = inputs()
    event.feature_metadata.update(metadata)
    assert quantitative_coverage(session, event, signal(event))['partial_index'] is None


def test_all_five_do_not_create_replacement_index():
    session, event, _ = inputs()
    result = quantitative_coverage(session, event, signal(event, activity_score=10,
                                   statistical_score=10, unavailable_components=[]))
    assert result['partial_index'] is None


def test_no_source_lineage_does_not_invalidate_signal_bound_partial():
    session, event, _ = inputs()
    event.feature_metadata = None
    result = quantitative_coverage(session, event, signal(event))
    assert result['partial_index'] == pytest.approx(30 / .70)
    assert result['purchase_count'] is None
    session.scalars.assert_not_called()


@pytest.mark.parametrize('value', [Decimal('-1e-999'), Decimal('1.000000000000000000001')])
def test_probability_bounds_checked_before_float_rounding(value):
    session, event, _ = inputs()
    assert quantitative_coverage(session, event, signal(event, model_probability=value))['partial_index'] is None


def test_weight_threshold_and_zero_boundary():
    session, event, _ = inputs()
    row = signal(event, anomaly_score=None, activity_score=0, model_probability=None,
                 statistical_score=0, dislocation_score=0, unavailable_components=['A', 'M'])
    # .15 + .15 + .15 is below the threshold, even with three observations.
    assert quantitative_coverage(session, event, row)['partial_index'] is None
    # A+C+S=.55 qualifies without inventing a model probability.
    row.anomaly_score = 0
    row.dislocation_score = None
    row.unavailable_components = ['M', 'D']
    result = quantitative_coverage(session, event, row)
    assert result['partial_index'] == 0 and result['coverage_weight'] == pytest.approx(.55)


@pytest.mark.parametrize('count,value,expected', [(0, 0, 0), (1, 0, 6), (5, 99999999, 100),
    (10, 100000000, 100), (2, 9999, 47), (1, 999999, 58.5)])
def test_fixed_activity_formula(count, value, expected):
    from app.services.quantitative_coverage import estimated_activity_index
    assert estimated_activity_index(count, value) == pytest.approx(expected)


@pytest.mark.parametrize('count,value', [(None, 1), (1, None), (-1, 1), (1, -1),
    (True, 1), (1, True), (1.5, 1), (1, '100'), (1, float('nan')),
    (1, Decimal('Infinity')), (1, Decimal('-1e-999'))])
def test_fixed_activity_rejects_invalid(count, value):
    from app.services.quantitative_coverage import estimated_activity_index
    assert estimated_activity_index(count, value) is None


def test_estimate_requires_validated_source_value_and_preserves_canonical_fields():
    session, event, row = inputs()
    result = quantitative_coverage(session, event, None)
    assert result['estimated_activity_index'] == 6
    assert result['partial_index'] is None and 'insider_edge_score' not in result
    row.document_type = '4/A'
    assert quantitative_coverage(session, event, None)['estimated_activity_index'] is None
    row.document_type = '4'
    row.transaction_value = Decimal('1')  # contradicts aggregate, not a new observation
    assert quantitative_coverage(session, event, None)['estimated_activity_index'] is None


def test_estimate_independent_of_display_population():
    session, event, _ = inputs()
    first = quantitative_coverage(session, event, None)
    assert quantitative_coverage(session, event, None)['estimated_activity_index'] == first['estimated_activity_index']


def test_estimated_fields_survive_api_serialization():
    from app.api.schemas import QuantitativeCoverage
    session, event, _ = inputs()
    payload = QuantitativeCoverage.model_validate(quantitative_coverage(session, event, None)).model_dump(mode='json')
    assert payload['estimated_activity_index'] == 6
    assert payload['estimated_activity_method'] == 'fixed_activity_v1'
    assert payload['partial_index'] is None
