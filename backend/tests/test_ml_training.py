import numpy as np
import pandas as pd
import pytest

from app.ml.dataset import build_ml_dataset, split_temporally
from app.ml.training import (TrainingConfig, candidate_rank, fit_and_select,
                             predict_selected, train_dataset)
from test_ml_dataset import dataset_inputs

FAST = TrainingConfig(logistic_c=(1.,), xgboost_depth=(2,), n_estimators=12)


def training_frames():
    train = pd.DataFrame({'prior_return_5d': [-3., -2., -1., -.5, .5, 1., 2., 3.],
                          'sector': ['Tech', 'Tech', None, 'Energy'] * 2}, index=[f'train:{i}' for i in range(8)])
    valid = pd.DataFrame({'prior_return_5d': [-2.5, -1., 1., 2.5], 'sector': ['Tech', 'NEW', None, 'Energy']}, index=[f'valid:{i}' for i in range(4)])
    return train, pd.Series([0] * 4 + [1] * 4, index=train.index), valid, pd.Series([0, 0, 1, 1], index=valid.index)


def test_both_models_and_selection():
    result = fit_and_select(*training_frames(), FAST)
    assert result.status == 'complete' and len(result.pipelines) == 2
    assert {r['model_name'] for r in result.candidates} == {'logistic_regression', 'xgboost'}
    assert result.selected_candidate == min(result.candidates, key=candidate_rank)['candidate_id']
    assert result.seed == 42 and result.threshold == .5
    assert set(result.dependency_versions) == {'scikit-learn', 'xgboost', 'numpy', 'pandas', 'scipy'}
    xgb = next(p['model'] for p in result.pipelines.values() if p['model'].__class__.__name__ == 'XGBClassifier')
    assert xgb.n_jobs == 1 and xgb.random_state == 42
    assert xgb.get_params()['early_stopping_rounds'] is None
    assert all(r['metrics']['sample_count'] == 4 for r in result.candidates)


def test_default_grid():
    result = fit_and_select(*training_frames())
    assert len(result.candidates) == 5
    assert [r['parameters']['C'] for r in result.candidates[:3]] == [.1, 1., 10.]
    assert [r['parameters']['max_depth'] for r in result.candidates[3:]] == [2, 3]


def test_training_only_preprocessing():
    train, y, valid, vy = training_frames()
    train.loc['train:0', 'prior_return_5d'] = np.nan
    valid['prior_return_5d'] = [-1000., -500., 500., 1000.]
    result = fit_and_select(train, y, valid, vy, FAST)
    for pipeline in result.pipelines.values():
        pre = pipeline['preprocessor']
        numeric = pre.named_transformers_['numeric']
        median = train.prior_return_5d.median()
        assert numeric['imputer'].statistics_[0] == median
        if 'scaler' in numeric.named_steps:
            assert numeric['scaler'].mean_[0] == pytest.approx(train.prior_return_5d.fillna(median).mean())
        categories = pre.named_transformers_['categories']['encoder'].categories_[0]
        assert 'NEW' not in categories and '__MISSING__' in categories
        assert np.isfinite(pre.transform(valid)).all()


def test_excluded_training_columns_and_unusable_rows():
    train, y, valid, vy = training_frames()
    train['prior_return_30d'] = np.nan
    valid['prior_return_30d'] = 1e10
    train.loc['train:0'] = [np.nan, None, np.nan]
    valid.loc['valid:0', ['prior_return_5d', 'sector']] = [np.nan, None]
    result = fit_and_select(train, y, valid, vy, FAST)
    assert result.status == 'complete' and result.excluded_features == ('prior_return_30d',)
    assert result.excluded_rows == {'train': ('train:0',), 'validation': ('valid:0',)}
    assert all(r['metrics']['sample_count'] == 3 for r in result.candidates)
    predictions = predict_selected(result, valid)
    assert pd.isna(predictions.loc['valid:0', 'probability'])
    assert predictions.loc['valid:0', 'missing_reasons'] == ['no_usable_predictors']
    changed = valid.copy()
    changed['prior_return_30d'] = -1e10
    pd.testing.assert_frame_equal(predictions, predict_selected(result, changed))


@pytest.mark.parametrize('name', ['Y', 'car30', 'ticker', 'research_event_id', 'insider_name', 'anomaly_score', 'activity_score', 'statistical_score', 'dislocation_score', 'insider_edge_score'])
def test_forbidden_predictors(name):
    train, y, valid, vy = training_frames()
    train[name] = 1
    with pytest.raises(ValueError, match='forbidden'):
        fit_and_select(train, y, valid, vy, FAST)


@pytest.mark.parametrize('which', ['train', 'validation'])
@pytest.mark.parametrize('case', ['empty', 'single_class', 'no_predictors'])
def test_insufficient_data(which, case):
    frames = list(training_frames())
    i = 0 if which == 'train' else 2
    if case == 'empty':
        frames[i], frames[i + 1] = frames[i].iloc[:0], frames[i + 1].iloc[:0]
    elif case == 'single_class':
        frames[i + 1][:] = 0
    else:
        frames[i][:] = np.nan
    result = fit_and_select(*frames, FAST)
    assert result.status == 'insufficient_data' and not result.pipelines and result.selected_model is None
    assert any(reason.startswith(which) for reason in result.reasons)


def test_reproducibility_and_column_order():
    frames = training_frames()
    first, second = fit_and_select(*frames, FAST), fit_and_select(*frames, FAST)
    assert first.candidates == second.candidates and first.selected_candidate == second.selected_candidate
    pd.testing.assert_frame_equal(predict_selected(first, frames[2]), predict_selected(second, frames[2].iloc[:, ::-1]))


def test_ranking_ties():
    lr = dict(model_name='logistic_regression', metrics=dict(brier_score=.2, roc_auc=.7))
    xgb = dict(model_name='xgboost', metrics=dict(brier_score=.2, roc_auc=.7))
    assert min([xgb, lr], key=candidate_rank) is lr
    xgb['metrics']['roc_auc'] = .8
    assert min([lr, xgb], key=candidate_rank) is xgb
    xgb['metrics']['brier_score'] = .3
    assert min([lr, xgb], key=candidate_rank) is lr


@pytest.mark.parametrize('case', ['inf', 'bad_number', 'unaligned', 'null_label', 'overlap', 'schema', 'duplicate'])
def test_invalid_inputs(case):
    train, y, valid, vy = training_frames()
    if case == 'inf': train.iloc[0, 0] = np.inf
    elif case == 'bad_number': train['prior_return_5d'] = 'bad'
    elif case == 'unaligned': y = y.iloc[::-1]
    elif case == 'null_label':
        y = y.astype(float)
        y.iloc[0] = np.nan
    elif case == 'overlap':
        valid.index = train.index[:4]
        vy.index = valid.index
    elif case == 'schema': valid = valid.drop(columns='sector')
    else:
        train.index = ['duplicate'] * len(train)
        y.index = train.index
    with pytest.raises(ValueError): fit_and_select(train, y, valid, vy, FAST)


def temporal_dataset():
    dates = ['2024-03-01', '2024-04-01', '2024-05-01', '2024-06-01', '2024-12-01',
             '2025-03-01', '2025-04-01', '2025-05-01', '2025-06-01', '2025-12-01',
             '2026-03-01', '2026-04-01', '2026-05-01']
    inputs = list(dataset_inputs(dates))
    inputs[1]['prior_return_5d'] = np.arange(len(dates), dtype=float)
    inputs[2].loc[4, 'outcome_end'] = pd.Timestamp('2025-03-01')
    inputs[2].loc[9, 'outcome_end'] = pd.Timestamp('2026-03-01')
    inputs[2].loc[12, 'label_status'] = 'unavailable'
    inputs[2].loc[12, 'Y'] = None
    dataset = build_ml_dataset(*inputs)
    return dataset, split_temporally(dataset)


def test_purged_integration_and_test_data_isolation():
    from app.ml.evaluation import evaluate_dataset
    dataset, split = temporal_dataset()
    assert 'event:4' not in split.partitions['train'] and 'event:9' not in split.partitions['validation']
    result = train_dataset(dataset, split, FAST)
    for pipeline in result.pipelines.values():
        numeric = pipeline['preprocessor'].named_transformers_['numeric']
        assert numeric['imputer'].statistics_[0] == pytest.approx(1.5)
    evaluation = evaluate_dataset(result, dataset, split)
    assert evaluation.predictions.index.tolist() == ['event:10', 'event:11']
    assert evaluation.metrics['sample_count'] == 2
    dataset.features.loc[split.partitions['test'], 'prior_return_5d'] = np.inf
    dataset.targets.loc[split.partitions['test'], 'Y'] = pd.NA
    changed = train_dataset(dataset, split, FAST)
    assert result.candidates == changed.candidates


def test_stale_outcome_overlap_rejected():
    dataset, split = temporal_dataset()
    dataset.targets.loc['event:0', 'outcome_end'] = pd.Timestamp('2025-03-01')
    with pytest.raises(ValueError, match='overlaps'): train_dataset(dataset, split, FAST)


def test_tampered_inclusion_rejected():
    dataset, split = temporal_dataset()
    split.partitions['train'] = split.partitions['train'].append(pd.Index(['event:4']))
    with pytest.raises(ValueError, match='audit'): train_dataset(dataset, split, FAST)


@pytest.mark.parametrize('kwargs', [dict(logistic_c=()), dict(logistic_c=(-1.,)), dict(xgboost_depth=(0,)), dict(n_estimators=0), dict(learning_rate=np.nan)])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError): TrainingConfig(**kwargs)


def test_entirely_missing_category_has_explicit_training_missing_level():
    train, y, valid, vy = training_frames()
    train['sector'] = None
    result = fit_and_select(train, y, valid, vy, FAST)
    for pipeline in result.pipelines.values():
        encoder = pipeline['preprocessor'].named_transformers_['categories']['encoder']
        assert encoder.categories_[0].tolist() == ['__MISSING__']
    assert predict_selected(result, valid).probability.notna().all()


def test_validation_values_and_labels_cannot_change_fitted_artifacts():
    import pickle

    train, y, valid, vy = training_frames()
    before = fit_and_select(train, y, valid, vy, FAST)
    changed = valid.copy()
    changed['prior_return_5d'] = [100., 200., 300., 400.]
    changed['sector'] = ['FUTURE_ONLY'] * len(changed)
    after = fit_and_select(train, y, changed, 1 - vy, FAST)
    for key in before.pipelines:
        assert pickle.dumps(before.pipelines[key]) == pickle.dumps(after.pipelines[key])


def test_no_feature_columns_produces_insufficient_data():
    train, y, valid, vy = training_frames()
    result = fit_and_select(train.iloc[:, :0], y, valid.iloc[:, :0], vy, FAST)
    assert result.status == 'insufficient_data'


def test_partial_rows_cannot_hide_single_class_after_exclusion():
    train, y, valid, vy = training_frames()
    valid.loc[vy.eq(1)] = [np.nan, None]
    result = fit_and_select(train, y, valid, vy, FAST)
    assert result.status == 'insufficient_data'
    assert result.reasons == ('validation_requires_two_classes_with_usable_predictors',)


def test_predict_rejects_forbidden_or_missing_fitted_columns():
    frames = training_frames()
    result = fit_and_select(*frames, FAST)
    for X in (frames[2].assign(Y=1), frames[2].drop(columns='sector')):
        with pytest.raises(ValueError):
            predict_selected(result, X)


def test_chronological_split_integration():
    inputs = list(dataset_inputs(pd.date_range('2020-01-01', periods=20, freq='60D')))
    inputs[1]['prior_return_5d'] = np.arange(20, dtype=float)
    dataset = build_ml_dataset(*inputs)
    split = split_temporally(dataset, mode='chronological')
    result = train_dataset(dataset, split, FAST)
    assert result.status == 'complete'
    assert all(record['metrics']['sample_count'] == len(split.partitions['validation']) for record in result.candidates)


@pytest.mark.parametrize('columns', [['prior_return_5d'], ['sector']])
def test_numeric_only_and_categorical_only_pipelines(columns):
    train, y, valid, vy = training_frames()
    result = fit_and_select(train[columns], y, valid[columns], vy, FAST)
    assert result.status == 'complete'
    predictions = predict_selected(result, valid[columns])
    usable = valid[columns].notna().any(axis=1)
    assert predictions.loc[usable, 'probability'].between(0, 1).all()
    assert predictions.loc[~usable, 'probability'].isna().all()
    assert predictions.loc[~usable, 'status'].eq('unavailable').all()
