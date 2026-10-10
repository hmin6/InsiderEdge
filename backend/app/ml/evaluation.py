"""Frozen-model evaluation; no fitting, selection, or threshold tuning."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss, roc_auc_score

if TYPE_CHECKING:
    from app.ml.training import ModelSelection


@dataclass(frozen=True)
class EvaluationResult:
    predictions: pd.DataFrame
    metrics: dict[str, float | int | str | None]
    metric_reasons: dict[str, str]
    status: str
    reasons: tuple[str, ...]


def probability_metrics(y: pd.Series, probabilities: np.ndarray,
                        threshold: float = 0.50) -> tuple[dict, dict]:
    """Metrics on observed predictions; undefined metrics are null, never fake zero.

    Precision needs predicted positives, recall needs actual positives, and F1
    needs a nonzero 2TP+FP+FN denominator. AUC needs both actual classes.
    """
    values = np.asarray(probabilities, dtype=float)
    if len(values) != len(y) or not y.isin([0, 1]).all() or y.isna().any():
        raise ValueError('metrics require aligned binary labels and probabilities')
    if values.ndim != 1 or not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError('probabilities must be finite and in [0,1]')
    metrics = dict.fromkeys(('roc_auc', 'brier_score', 'precision', 'recall', 'f1'))
    reasons = {}
    metrics.update(sample_count=len(y), positive_class_prevalence=float(y.mean()) if len(y) else None,
                   classification_threshold=threshold)
    if not len(y):
        return metrics, {name: 'no_available_predictions' for name in metrics if name != 'sample_count' and name != 'classification_threshold'}
    actual = y.to_numpy(dtype=int)
    predicted = values >= threshold
    tp = int(((actual == 1) & predicted).sum())
    fp = int(((actual == 0) & predicted).sum())
    fn = int(((actual == 1) & ~predicted).sum())
    metrics['brier_score'] = float(brier_score_loss(actual, values))
    if y.nunique() == 2:
        metrics['roc_auc'] = float(roc_auc_score(actual, values))
    else:
        reasons['roc_auc'] = 'single_class_labels'
    for name, numerator, denominator in [('precision', tp, tp + fp), ('recall', tp, tp + fn), ('f1', 2 * tp, 2 * tp + fp + fn)]:
        if denominator:
            metrics[name] = numerator / denominator
        else:
            reasons[name] = 'undefined_zero_denominator'
    return metrics, reasons


def evaluate_frozen_model(selection: ModelSelection, X_test: pd.DataFrame,
                          y_test: pd.Series, metadata: pd.DataFrame) -> EvaluationResult:
    """Evaluate once after selection is frozen; repeat-call discipline is caller-owned.

    Metadata must be indexed by event ID, matching X/y exactly, and contain
    information_date. Split dates describe ALL supplied evaluation events;
    sample_count counts only rows with available predictions. No target is used
    to obtain probabilities. The fitted pipeline is never refitted here.
    """
    from app.ml.training import predict_selected, validate_labels

    validate_labels(X_test, y_test)
    if not metadata.index.equals(X_test.index) or 'information_date' not in metadata:
        raise ValueError('evaluation metadata must align by event ID and include information_date')
    dates = pd.to_datetime(metadata['information_date'], errors='coerce')
    if dates.isna().any():
        raise ValueError('evaluation metadata contains invalid information dates')
    predictions = predict_selected(selection, X_test)
    available = predictions['status'].eq('complete')
    metrics, reasons = probability_metrics(y_test.loc[available], predictions.loc[available, 'probability'].to_numpy(dtype=float))
    metrics.update(split_start=dates.min().date().isoformat() if len(dates) else None,
                   split_end=dates.max().date().isoformat() if len(dates) else None)
    status = 'unavailable' if not available.any() else ('partial' if not available.all() or reasons else 'complete')
    result_reasons = []
    if not available.all() or not len(X_test):
        result_reasons.append('some_or_all_predictions_unavailable')
    if reasons:
        result_reasons.append('some_metrics_unavailable')
    return EvaluationResult(predictions, metrics, reasons, status, tuple(result_reasons))


def evaluate_dataset(selection, dataset, split) -> EvaluationResult:
    """Consume only the approved split's supervised test rows."""
    from app.ml.training import supervised_partition

    X, y, metadata = supervised_partition(dataset, split, 'test')
    return evaluate_frozen_model(selection, X, y, metadata)
