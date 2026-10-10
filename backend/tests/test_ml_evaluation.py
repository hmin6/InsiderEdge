import pickle
import numpy as np
import pandas as pd
import pytest
from app.ml.evaluation import evaluate_frozen_model, probability_metrics
from app.ml.training import fit_and_select, predict_selected
from test_ml_training import FAST, training_frames


def test_hand_calculated_metrics():
    metrics, reasons = probability_metrics(pd.Series([0, 0, 1, 1]), np.array([.1, .6, .5, .9]))
    assert metrics['brier_score'] == pytest.approx((.01 + .36 + .25 + .01) / 4)
    assert metrics['roc_auc'] == .75 and metrics['precision'] == pytest.approx(2 / 3)
    assert metrics['recall'] == 1. and metrics['f1'] == .8
    assert metrics['sample_count'] == 4 and metrics['positive_class_prevalence'] == .5 and not reasons


def test_single_class_defined_and_undefined_metrics():
    metrics, reasons = probability_metrics(pd.Series([0, 0]), np.array([.1, .2]))
    assert metrics['roc_auc'] is None and reasons['roc_auc'] == 'single_class_labels'
    assert metrics['brier_score'] == pytest.approx(.025)
    assert all(metrics[n] is None and n in reasons for n in ['precision', 'recall', 'f1'])
    metrics, _ = probability_metrics(pd.Series([1, 1]), np.array([.1, .2]))
    assert metrics['recall'] == 0 and metrics['f1'] == 0


@pytest.mark.parametrize('values', [[np.nan], [np.inf], [-.1], [1.1]])
def test_invalid_probability(values):
    with pytest.raises(ValueError, match='probabilities'): probability_metrics(pd.Series([1]), np.array(values))


def test_frozen_evaluation_does_not_change_selection():
    train, y, test, ty = training_frames()
    selection = fit_and_select(train, y, test, ty, FAST)
    test = test.rename(index=lambda identity: identity.replace('valid', 'test'))
    ty.index = test.index
    metadata = pd.DataFrame({'information_date': pd.date_range('2026-01-02', periods=4)}, index=test.index)
    before = pickle.dumps(selection)
    result = evaluate_frozen_model(selection, test, ty, metadata)
    assert pickle.dumps(selection) == before
    assert result.metrics['split_start'] == '2026-01-02' and result.metrics['split_end'] == '2026-01-05'
    assert result.metrics['sample_count'] == 4 and result.predictions.probability.between(0, 1).all()
    pd.testing.assert_frame_equal(result.predictions, predict_selected(selection, test))
    changed = evaluate_frozen_model(selection, test, 1 - ty, metadata)
    pd.testing.assert_frame_equal(result.predictions, changed.predictions)
    assert pickle.dumps(selection) == before


def test_partial_evaluation():
    frames = training_frames()
    selection = fit_and_select(*frames, FAST)
    test = frames[2].copy()
    test.loc['valid:0'] = [np.nan, None]
    metadata = pd.DataFrame({'information_date': pd.Timestamp('2026-01-01')}, index=test.index)
    result = evaluate_frozen_model(selection, test, pd.Series(0, index=test.index), metadata)
    assert result.status == 'partial' and len(result.predictions) == 4
    assert result.metrics['sample_count'] == 3 and result.metrics['roc_auc'] is None
    assert result.metric_reasons['roc_auc'] == 'single_class_labels' and result.metrics['brier_score'] is not None
    assert pd.isna(result.predictions.loc['valid:0', 'probability'])


def test_empty_and_unusable_evaluation():
    frames = training_frames()
    selection = fit_and_select(*frames, FAST)
    test = frames[2].copy()
    test[:] = np.nan
    metadata = pd.DataFrame({'information_date': pd.Timestamp('2026-01-01')}, index=test.index)
    result = evaluate_frozen_model(selection, test, frames[3], metadata)
    assert result.status == 'unavailable' and result.metrics['sample_count'] == 0 and result.predictions.probability.isna().all()
    empty = evaluate_frozen_model(selection, test.iloc[:0], frames[3].iloc[:0], metadata.iloc[:0])
    assert empty.status == 'unavailable' and empty.metrics['split_start'] is None


def test_unavailable_selection_predictions():
    train, y, test, ty = training_frames()
    selection = fit_and_select(train, y * 0, test, ty, FAST)
    result = predict_selected(selection, test)
    assert result.probability.isna().all() and result.status.eq('unavailable').all()
    assert all('model_selection_unavailable' in reasons for reasons in result.missing_reasons)


def test_metadata_alignment():
    train, y, test, ty = training_frames()
    selection = fit_and_select(train, y, test, ty, FAST)
    metadata = pd.DataFrame({'information_date': ['2026-01-01'] * 4}, index=test.index[::-1])
    with pytest.raises(ValueError, match='metadata'): evaluate_frozen_model(selection, test, ty, metadata)
