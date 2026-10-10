"""Validated signal construction and existing-schema persistence.

No model fitting or quant formula duplication. Callers supply trusted component
outputs, source provenance, and a complete independent session calendar. Audit
contains available evidence that has no Signal column; it is NOT durable.
The caller owns the outer transaction; persistence uses a savepoint for batch
atomicity and replaces all supported fields of one current row per event.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from numbers import Real
from typing import Sequence
import math

import numpy as np
import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sklearn.utils.validation import check_is_fitted

from app.db.models import ResearchEvent, Signal
from app.ml.dataset import prepare_inference_features, _events, _ids
from app.ml.training import ModelSelection, predict_selected
from app.quant.event_study import _prepare_expected_sessions, _normalized_dates
from app.quant.insideredge_score import Component, ScoreInput, score_event

KEY = 'research_event_id'
SCORE_VERSION = 'ies-v1'
# All numerical historical measurements emitted by Issue #13, whether persisted
# or retained only in audit. Seeds/attempt counts are diagnostics, not outcomes.
HISTORICAL_MEASUREMENTS = (
    'statistical_score', 'mean_car30', 'bootstrap_ci_lower', 'bootstrap_ci_upper',
    'bootstrap_q', 'B_support', 'T_obs', 'randomization_p_value', 'P_support',
)


@dataclass(frozen=True)
class SignalBatch:
    """payloads are persistable; audit retains transient detailed evidence.

    Neither includes held-out metrics unless separately supplied downstream.
    No claim is made that full statistics/prediction API responses can be
    reconstructed from Signal, which lacks component diagnostics and metrics.
    """
    payloads: tuple[dict, ...]
    audit: dict[str, dict]


def number(value, name: str, bounds=None):
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if not isinstance(value, (Real, Decimal)) or isinstance(value, (bool, np.bool_)):
        raise ValueError(f'{name}: invalid numeric value')
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f'{name}: invalid numeric value') from exc
    if math.isnan(result):
        return None
    if not math.isfinite(result) or (bounds and not bounds[0] <= result <= bounds[1]):
        raise ValueError(f'{name}: nonfinite or out-of-range value')
    return result


def _frame(frame, name, metadata):
    if frame.columns.has_duplicates:
        raise ValueError(f'{name}: duplicate columns')
    _ids(frame, name, metadata.index, complete=True)
    result = frame.set_index(KEY).reindex(metadata.index).copy()
    # Real upstream components all supply ticker and information_date.
    for field in ('ticker', 'information_date'):
        if field not in result:
            raise ValueError(f'{name}: missing {field}')
    if result.ticker.isna().any() or not result.ticker.eq(metadata.ticker).fillna(False).all():
        raise ValueError(f'{name}: ticker mismatch')
    for field in ('information_date', 'public_event_day'):
        if field in result:
            dates = _normalized_dates(result[field])
            if dates.isna().any() or not dates.eq(metadata[field]).fillna(False).all():
                raise ValueError(f'{name}: {field} mismatch')
    return result


def _component(row, field, reason_field, event_id):
    raw = row.get(reason_field, [])
    if not isinstance(raw, (list, tuple)) or any(not isinstance(r, str) or not r.strip() for r in raw):
        raise ValueError(f'{field}: invalid reasons')
    reasons = tuple(raw)
    value = number(row.get(field), field, (0, 1 if field == 'probability' else 100))
    status = row.get('status')
    if value is not None and status != 'complete':
        raise ValueError(f'{field}: numeric value contradicts status')
    if value is not None and reasons:
        raise ValueError(f'{field}: available value contradicts reasons')
    if value is None:
        if status == 'complete':
            raise ValueError(f'{field}: complete status without value')
        reasons = reasons or (f'{field}_unavailable',)
    return Component(value, reasons, event_id)


def build_signals(events: pd.DataFrame, event_features: pd.DataFrame,
                  feature_provenance: pd.DataFrame, selection: ModelSelection, *,
                  anomaly: pd.DataFrame, activity: pd.DataFrame,
                  statistical: pd.DataFrame, dislocation: pd.DataFrame,
                  event_studies: pd.DataFrame, expected_sessions: Sequence[object],
                  observation_cutoff: object, comparable_history: pd.DataFrame | None = None,
                  model_version: str | None = None) -> SignalBatch:
    """Predict from validated raw X, adapt existing outputs, return signal/audit.

    comparable_history must contain metadata, car30 and car30_status for every
    claimed comparator whenever S is available. Full outcomes must predate the
    focal information date. Component calculations and cohort selection remain
    trusted upstream responsibilities; no arbitrary predictions are accepted.
    observation_cutoff is the inclusive last completed session for CAR display.
    """
    if not isinstance(selection, ModelSelection):
        raise ValueError('selection must be an existing ModelSelection')
    if selection.status == 'complete':
        pipeline = selection.pipelines.get(selection.selected_candidate)
        if pipeline is None or selection.selected_model not in ('logistic_regression', 'xgboost'):
            raise ValueError('complete selection requires a selected fitted pipeline')
        check_is_fitted(pipeline)
    metadata, features, availability = prepare_inference_features(events, event_features, feature_provenance)
    sessions = _prepare_expected_sessions(expected_sessions)
    positions = {day: i for i, day in enumerate(sessions)}
    cutoff = _normalized_dates(pd.Series([observation_cutoff])).iloc[0]
    if pd.isna(cutoff):
        raise ValueError('invalid observation_cutoff')
    for _, event in metadata.iterrows():
        index = positions.get(event.public_event_day)
        if index is None or index == 0 or sessions[index - 1] > event.information_date:
            raise ValueError('public_event_day must be first expected session after information_date')
    frames = {name: _frame(frame, name, metadata) for name, frame in
              [('anomaly', anomaly), ('activity', activity), ('statistical', statistical),
               ('dislocation', dislocation), ('event_study', event_studies)]}
    if not set(selection.feature_schema).issubset(features.columns):
        raise ValueError('selected model feature schema is incompatible with validated predictors')
    predictions = predict_selected(selection, features.loc[:, list(selection.feature_schema)])
    if predictions.index.has_duplicates or not predictions.index.equals(metadata.index):
        raise ValueError('prediction IDs do not match research events')
    history = None
    if comparable_history is not None:
        if not {'car30', 'car30_status'}.issubset(comparable_history.columns):
            raise ValueError('comparable_history requires car30 and car30_status')
        history = _events(comparable_history)
        history = history.join(comparable_history.set_index(KEY)[['car30', 'car30_status']])
    payloads, audits = [], {}
    for identity, event in metadata.iterrows():
        a, c, s, d = (frames[name].loc[identity] for name in ('anomaly', 'activity', 'statistical', 'dislocation'))
        components = [_component(row, field, reason, identity) for row, field, reason in
                      [(a, 'A', 'missing_reasons'), (c, 'activity_score', 'missing_reasons'),
                       (s, 'statistical_score', 'missing_reasons'), (d, 'dislocation_score', 'unavailable_reasons')]]
        retained_measurements = any(number(s.get(field), field) is not None
                                    for field in HISTORICAL_MEASUREMENTS)
        component_succeeded = any(s.get(field) == 'complete' for field in
                                  ('bootstrap_status', 'randomization_status'))
        ids = s.get('comparable_event_ids', [])
        if not isinstance(ids, (tuple, list)):
            raise ValueError('comparable_event_ids must be a list or tuple')
        count = number(s.get('comparable_event_count'), 'comparable_event_count')
        if count is not None and count != len(ids):
            raise ValueError('comparable_event_count contradicts comparator IDs')
        if retained_measurements or component_succeeded or ids or (count is not None and count > 0):
            minimum = 10 if retained_measurements or component_succeeded else 1
            if len(ids) < minimum or history is None:
                raise ValueError('retained historical evidence requires eligible comparator history')
            if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != len(ids):
                raise ValueError('invalid or duplicate comparator IDs')
            for comparator in ids:
                if comparator == identity or comparator not in history.index:
                    raise ValueError('unknown or self comparator')
                row = history.loc[comparator]
                index = positions.get(row.public_event_day)
                if (row.information_date >= event.information_date or index is None or index + 29 >= len(sessions)
                        or sessions[index + 29] >= event.information_date or row.car30_status != 'complete'
                        or number(row.car30, 'comparator CAR30') is None):
                    raise ValueError('comparator outcome unavailable before focal information date')
        prediction = _component(predictions.loc[identity], 'probability', 'missing_reasons', identity)
        score = score_event(ScoreInput(identity, components[0], components[1], prediction,
                                      components[2], components[3], selection.selected_model, model_version))
        payload = dict(signal_id=f'signal:{identity}', research_event_id=identity, ticker=event.ticker,
                       public_event_day=event.public_event_day.date(), anomaly_score=components[0].value,
                       activity_score=components[1].value, statistical_score=components[2].value,
                       dislocation_score=components[3].value, model_probability=prediction.value,
                       insider_edge_score=score['insider_edge_score'], score_status=score['score_status'],
                       unavailable_components=score['unavailable_components'], model_name=selection.selected_model,
                       model_version=model_version, score_version=SCORE_VERSION)
        study = frames['event_study'].loc[identity]
        for horizon in (5, 30, 90):
            field = f'car{horizon}'
            value = number(study.get(field), field)
            index = positions[event.public_event_day]
            complete = study.get(f'{field}_status') == 'complete'
            if complete and (value is None or index + horizon - 1 >= len(sessions)
                             or sessions[index + horizon - 1] > cutoff):
                raise ValueError(f'{field}: complete outcome not observable by cutoff')
            if not complete and value is not None:
                raise ValueError(f'{field}: value contradicts unavailable status')
            payload[field] = value
        for source, target in [('comparable_event_count', 'comparable_event_count'),
                               ('mean_car30', 'mean_car30'), ('bootstrap_ci_lower', 'bootstrap_ci_lower'),
                               ('bootstrap_ci_upper', 'bootstrap_ci_upper'), ('randomization_p_value', 'randomization_p_value')]:
            payload[target] = number(s.get(source), source, (0, 1) if source == 'randomization_p_value' else None)
        count = payload['comparable_event_count']
        if count is not None and (count < 0 or count != int(count)):
            raise ValueError('invalid comparable_event_count')
        if count is not None:
            payload['comparable_event_count'] = int(count)
        payload['comparable_cohort'] = s.get('cohort_definition')
        payloads.append(payload)
        audits[identity] = deepcopy(dict(score=score, feature_availability=availability.loc[identity].to_dict(),
                                        components={name: frame.loc[identity].to_dict() for name, frame in frames.items()},
                                        prediction=predictions.loc[identity].to_dict(),
                                        persisted_fields=tuple(payload),
                                        evidence_storage='detailed evidence is in-memory only'))
    return SignalBatch(tuple(payloads), audits)


def persist_signals(session: Session, batch: SignalBatch) -> int:
    """Atomic full replacement of current Signal fields; never commit externally.

    Parent Database.session owns commit/rollback. A savepoint rolls back the
    whole batch on failure. Existing signal_id/created_at are retained on update.
    Validate persisted event identity and information date from audit first.
    """
    dialect = session.get_bind().dialect.name
    if dialect not in ('sqlite', 'postgresql'):
        raise ValueError('unsupported signal persistence dialect')
    ids = [row[KEY] for row in batch.payloads]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate signal event IDs')
    with session.begin_nested():
        for row in batch.payloads:
            event = session.get(ResearchEvent, row[KEY])
            if event is None or event.ticker != row['ticker'] or event.public_event_day != row['public_event_day']:
                raise ValueError('persisted research event identity mismatch')
            info = batch.audit[row[KEY]]['components']['event_study']['information_date']
            if pd.Timestamp(event.information_date) != pd.Timestamp(info):
                raise ValueError('persisted research event information date mismatch')
        for row in batch.payloads:
            statement = (pg_insert if dialect == 'postgresql' else sqlite_insert)(Signal).values(**row)
            session.execute(statement.on_conflict_do_update(index_elements=[KEY], set_={
                name: getattr(statement.excluded, name) for name in row if name not in ('signal_id', KEY)}))
    return len(ids)
