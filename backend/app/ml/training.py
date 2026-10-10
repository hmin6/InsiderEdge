"""Train-only preprocessing and validation-only Logistic/XGBoost selection.

All inputs must originate from Issue #15's provenance-validated MLDataset.
Raw frame APIs enforce its allowlist, but cannot independently attest timestamps.
Frozen-universe survivorship/selection bias remains. Artifacts stay in memory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import version
import warnings

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits
from xgboost import XGBClassifier

from app.ml.dataset import FEATURE_COLUMNS, MLDataset, TemporalSplit
from app.ml.evaluation import probability_metrics

CATEGORIES = ('sector', 'role_bucket')
SEED = 42
THRESHOLD = 0.50


@dataclass(frozen=True)
class TrainingConfig:
    """Small fixed-order grid: three regularization strengths and two tree depths.

    CPU histogram trees, 100 boosting rounds and learning rate .05 constrain
    complexity/runtime. No class weights, calibration, early stopping, or CV.
    Grid order breaks within-model exact ties. Seed/threshold are locked.
    """
    logistic_c: tuple[float, ...] = (0.1, 1.0, 10.0)
    xgboost_depth: tuple[int, ...] = (2, 3)
    n_estimators: int = 100
    learning_rate: float = 0.05

    def __post_init__(self):
        if not self.logistic_c or not self.xgboost_depth:
            raise ValueError('both model families require a nonempty candidate grid')
        if any(not np.isfinite(c) or c <= 0 for c in self.logistic_c):
            raise ValueError('logistic C must be positive and finite')
        if any(not isinstance(d, int) or isinstance(d, bool) or d < 1 for d in self.xgboost_depth):
            raise ValueError('tree depths must be positive integers')
        if not isinstance(self.n_estimators, int) or isinstance(self.n_estimators, bool) or self.n_estimators < 1:
            raise ValueError('n_estimators must be a positive integer')
        if not np.isfinite(self.learning_rate) or not 0 < self.learning_rate <= 1:
            raise ValueError('learning_rate must be in (0,1]')


@dataclass(frozen=True)
class ModelSelection:
    """Fitted training-only artifacts and validation diagnostics; no test metrics.

    Candidate records contain model_name, parameters, status/reasons and metrics.
    feature_schema is the original input schema; excluded_features lists numeric
    columns entirely missing in training. Row exclusions contain event IDs only.
    """
    status: str
    reasons: tuple[str, ...]
    feature_schema: tuple[str, ...]
    excluded_features: tuple[str, ...]
    pipelines: dict[str, Pipeline] = field(default_factory=dict)
    candidates: tuple[dict, ...] = ()
    selected_candidate: str | None = None
    selected_model: str | None = None
    selected_parameters: dict = field(default_factory=dict)
    excluded_rows: dict[str, tuple] = field(default_factory=dict)
    seed: int = SEED
    threshold: float = THRESHOLD
    dependency_versions: dict[str, str] = field(default_factory=dict)


def prepare_features(X: pd.DataFrame, schema: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Validate allowed predictors; normalize missing categories, never fit anything."""
    if X.columns.has_duplicates or X.index.has_duplicates or X.index.isna().any():
        raise ValueError('features require unique columns and non-null unique event IDs')
    forbidden = set(X.columns) - set(FEATURE_COLUMNS)
    if forbidden:
        raise ValueError(f'forbidden predictors: {sorted(forbidden)}')
    if schema is not None and set(X.columns) != set(schema):
        raise ValueError('feature schema does not match fitted input columns')
    names = schema if schema is not None else tuple(name for name in FEATURE_COLUMNS if name in X)
    result = X.loc[:, list(names)].copy()
    for name in names:
        if name in CATEGORIES:
            values = result[name].astype('string').str.strip().replace('', pd.NA)
            result[name] = values.astype(object).where(values.notna(), np.nan)
        else:
            try:
                values = pd.to_numeric(result[name], errors='raise').to_numpy(dtype=float, na_value=np.nan)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'invalid numeric predictor: {name}') from exc
            if np.isinf(values).any():
                raise ValueError(f'infinite numeric predictor: {name}')
            result[name] = values
    return result


def validate_labels(X: pd.DataFrame, y: pd.Series) -> None:
    if not isinstance(y, pd.Series) or not X.index.equals(y.index):
        raise ValueError('labels must align exactly with feature event IDs')
    if y.isna().any() or not y.isin([0, 1]).all():
        raise ValueError('supervised labels must be observed binary outcomes')


def _usable(X: pd.DataFrame, excluded: tuple[str, ...]) -> pd.Series:
    active = X.drop(columns=list(excluded))
    return active.notna().any(axis=1)


def _pipeline(numeric, categories, estimator, scale):
    transforms = []
    if numeric:
        steps = [('imputer', SimpleImputer(strategy='median'))]
        if scale:
            steps.append(('scaler', StandardScaler()))
        transforms.append(('numeric', Pipeline(steps), numeric))
    if categories:
        transforms.append(('categories', Pipeline([
            ('imputer', SimpleImputer(strategy='constant', fill_value='__MISSING__', keep_empty_features=True)),
            ('encoder', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
        ]), categories))
    return Pipeline([('preprocessor', ColumnTransformer(transforms, remainder='drop')),
                     ('model', estimator)])


def candidate_rank(record: dict) -> tuple:
    """Exact Brier tie -> AUC -> Logistic; stable grid order is last tie-break."""
    return (record['metrics']['brier_score'], -record['metrics']['roc_auc'],
            record['model_name'] != 'logistic_regression')


def fit_and_select(X_train: pd.DataFrame, y_train: pd.Series,
                   X_validation: pd.DataFrame, y_validation: pd.Series,
                   config: TrainingConfig | None = None) -> ModelSelection:
    """Fit only training rows, select by validation Brier/AUC/Logistic preference.

    No test arguments exist. Rows without any observed active predictors are
    excluded, audited and never imputed into fabricated predictions. Both
    retained training and validation rows must contain both classes.
    """
    config = config or TrainingConfig()
    train = prepare_features(X_train)
    schema = tuple(train.columns)
    valid = prepare_features(X_validation, schema)
    validate_labels(train, y_train)
    validate_labels(valid, y_validation)
    if len(train.index.intersection(valid.index)):
        raise ValueError('training and validation event IDs must be disjoint')
    excluded = tuple(name for name in schema if name not in CATEGORIES and train[name].isna().all())
    train_ok, valid_ok = _usable(train, excluded), _usable(valid, excluded)
    diagnostics = {'train': tuple(train.index[~train_ok]), 'validation': tuple(valid.index[~valid_ok])}
    common = dict(feature_schema=schema, excluded_features=excluded, excluded_rows=diagnostics,
                  dependency_versions={p: version(p) for p in ('scikit-learn', 'xgboost', 'numpy', 'pandas', 'scipy')})
    reasons = tuple(f'{name}_requires_two_classes_with_usable_predictors'
                    for name, y, mask in [('train', y_train, train_ok), ('validation', y_validation, valid_ok)]
                    if y.loc[mask].nunique() != 2)
    if reasons:
        return ModelSelection(status='insufficient_data', reasons=reasons, **common)
    numeric = [name for name in schema if name not in CATEGORIES and name not in excluded]
    categories = [name for name in schema if name in CATEGORIES]
    definitions = []
    for c in config.logistic_c:
        params = {'C': c}
        definitions.append(('logistic_regression', params, LogisticRegression(C=c, solver='liblinear', random_state=SEED, max_iter=1000), True))
    for depth in config.xgboost_depth:
        params = {'max_depth': depth, 'n_estimators': config.n_estimators, 'learning_rate': config.learning_rate}
        definitions.append(('xgboost', params, XGBClassifier(**params, objective='binary:logistic', eval_metric='logloss',
                            tree_method='hist', n_jobs=1, random_state=SEED, subsample=1.0, colsample_bytree=1.0), False))
    pipelines, records = {}, []
    with threadpool_limits(limits=1):
        for i, (name, params, estimator, scale) in enumerate(definitions):
            key = f'{name}:{i}'
            pipeline = _pipeline(numeric, categories, estimator, scale)
            record = dict(candidate_id=key, model_name=name, parameters=params, status='complete', reasons=[], metrics=None)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', ConvergenceWarning)
                    pipeline.fit(train.loc[train_ok], y_train.loc[train_ok].astype(int))
                probabilities = pipeline.predict_proba(valid.loc[valid_ok])[:, 1]
                metrics, metric_reasons = probability_metrics(y_validation.loc[valid_ok], probabilities)
                record.update(metrics=metrics, metric_reasons=metric_reasons)
                pipelines[key] = pipeline
            except ConvergenceWarning:
                record.update(status='unavailable', reasons=['model_did_not_converge'])
            records.append(record)
    available = [record for record in records if record['status'] == 'complete']
    if not available:
        return ModelSelection(status='unavailable', reasons=('no_valid_candidate',), candidates=tuple(records), **common)
    best = min(available, key=candidate_rank)
    return ModelSelection(status='complete', reasons=(), pipelines=pipelines, candidates=tuple(records),
                          selected_candidate=best['candidate_id'], selected_model=best['model_name'],
                          selected_parameters=best['parameters'], **common)


def predict_selected(selection: ModelSelection, X: pd.DataFrame) -> pd.DataFrame:
    """One probability/status record per event; unavailable predictions stay null."""
    frame = prepare_features(X, selection.feature_schema)
    usable = _usable(frame, selection.excluded_features)
    result = pd.DataFrame(index=frame.index)
    result['probability'] = np.nan
    result['classification'] = pd.Series(pd.NA, index=frame.index, dtype='Int64')
    result['status'] = 'unavailable'
    result['missing_reasons'] = [['no_usable_predictors'] for _ in range(len(frame))]
    if selection.status != 'complete':
        result['missing_reasons'] = [['model_selection_unavailable', *selection.reasons] for _ in range(len(frame))]
        return result
    if usable.any():
        with threadpool_limits(limits=1):
            probabilities = selection.pipelines[selection.selected_candidate].predict_proba(frame.loc[usable])[:, 1]
        if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
            raise ValueError('model produced invalid probabilities')
        result.loc[usable, 'probability'] = probabilities
        result.loc[usable, 'classification'] = (probabilities >= selection.threshold).astype(int)
        result.loc[usable, 'status'] = 'complete'
        for identity in frame.index[usable]:
            result.at[identity, 'missing_reasons'] = []
    return result


def supervised_partition(dataset: MLDataset, split: TemporalSplit, name: str):
    """Read only requested supervised rows; reject tampered inclusion/overlap.

    Reuse Issue #15's indices and audit, not a second splitting algorithm.
    Guard against stale/mutated targets using metadata and requested outcomes;
    selection never reads test labels or test predictor values.
    """
    if name not in ('train', 'validation', 'test'):
        raise ValueError('unknown supervised partition')
    indices = split.partitions[name]
    if indices.has_duplicates or not indices.isin(dataset.metadata.index).all():
        raise ValueError('invalid supervised event indices')
    if not split.audit.index.equals(dataset.metadata.index):
        raise ValueError('split audit and dataset event indices differ')
    expected = split.audit.index[split.audit['partition'].eq(name) & split.audit['included']]
    if not indices.equals(expected):
        raise ValueError('split indices contradict inclusion audit')
    for other, other_indices in split.partitions.items():
        if other != name and len(indices.intersection(other_indices)):
            raise ValueError('supervised partitions overlap')
    if not dataset.features.index.equals(dataset.metadata.index) or not dataset.targets.index.equals(dataset.metadata.index):
        raise ValueError('dataset frames are misaligned')
    targets = dataset.targets.loc[indices]
    if not targets['label_status'].eq('complete').all():
        raise ValueError('unavailable labels included in supervised partition')
    dates = dataset.metadata['information_date']
    names = ['train', 'validation', 'test', 'end']
    position = names.index(name)
    if not (dates.loc[indices].ge(split.boundaries[name]) & dates.loc[indices].lt(split.boundaries[names[position + 1]])).all():
        raise ValueError('supervised events fall outside partition boundaries')
    if name != 'test':
        next_name = names[position + 1]
        next_dates = dates.loc[dates.ge(split.boundaries[next_name]) & dates.lt(split.boundaries[names[position + 2]])]
        guard = next_dates.min() if len(next_dates) else split.boundaries[next_name]
        if targets['outcome_end'].isna().any() or targets['outcome_end'].ge(guard).any():
            raise ValueError('supervised outcome overlaps next evaluation partition')
    return dataset.features.loc[indices], targets['Y'], dataset.metadata.loc[indices]


def train_dataset(dataset: MLDataset, split: TemporalSplit,
                  config: TrainingConfig | None = None) -> ModelSelection:
    """Fit/select from Issue #15's purged train and validation rows only."""
    train, y_train, _ = supervised_partition(dataset, split, 'train')
    valid, y_valid, _ = supervised_partition(dataset, split, 'validation')
    return fit_and_select(train, y_train, valid, y_valid, config)
