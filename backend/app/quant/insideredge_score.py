"""Pure research-priority heuristic; no training, metrics, fetching or persistence.

A/C/S/D are 0–100, selected event probability is 0–1. None is unavailable;
NaN/inf are invalid. API spelling insider_edge_score is preserved. Production
adapters must align evidence IDs before constructing a single event record.
"""
from dataclasses import dataclass
from numbers import Real
from typing import Sequence
import math

WEIGHTS = {'A': .25, 'C': .15, 'M': .30, 'S': .15, 'D': .15}
_HISTORY = 'fewer_than_10_eligible_comparable_events'
# Exact selector reason and the prefixes emitted by Issue #13's combiner.
PARTIAL_REASONS = frozenset((_HISTORY, f'bootstrap:{_HISTORY}', f'randomization:{_HISTORY}'))


@dataclass(frozen=True)
class Component:
    """Available value, or None with exact nonempty upstream reason strings."""
    value: float | None
    reasons: tuple[str, ...] = ()
    research_event_id: str | None = None

    def __post_init__(self):
        if not isinstance(self.reasons, tuple) or any(not isinstance(r, str) or not r.strip() for r in self.reasons):
            raise ValueError('reasons must be a tuple of nonempty strings')
        if (self.value is None) != bool(self.reasons):
            raise ValueError('only unavailable components must have reasons')


@dataclass(frozen=True)
class ScoreInput:
    """One aligned event; optional model provenance is supplied by the caller.

    probability must be an event prediction, never a classification or metric.
    No independently keyed evidence is joined here. Issue #18 owns adapters.
    """
    research_event_id: str
    A: Component
    C: Component
    probability: Component
    S: Component
    D: Component
    model_name: str | None = None
    model_version: str | None = None


def _number(component: Component, name: str, maximum: float) -> float | None:
    if not isinstance(component, Component):
        raise ValueError(f'{name} must be a Component')
    value = component.value
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f'{name} must be numeric')
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= maximum:
        raise ValueError(f'{name} must be finite and in [0,{maximum}]')
    return value


def score_event(event: ScoreInput) -> dict:
    """Complete, S-history-only partial, or null insufficient_data result.

    applied_weights are normalized effective weights; original_weight_total is
    .85 for permitted partial, 1 for complete, None for no calculation. Only
    the exact insufficient-comparator reason permits partial normalization;
    metadata/calculation/randomization failures do not. No premature rounding.
    """
    if not isinstance(event.research_event_id, str) or not event.research_event_id.strip():
        raise ValueError('research_event_id must be a nonempty string')
    for name in ('model_name', 'model_version'):
        value = getattr(event, name)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f'{name} must be a nonempty string or None')
    inputs = {'A': event.A, 'C': event.C, 'M': event.probability, 'S': event.S, 'D': event.D}
    for name, component in inputs.items():
        if isinstance(component, Component) and component.research_event_id is not None:
            if component.research_event_id != event.research_event_id:
                raise ValueError(f'{name} research_event_id does not match scoring event')
    values = {name: _number(component, name, 1 if name == 'M' else 100) for name, component in inputs.items()}
    probability = values['M']
    if probability is not None:
        values['M'] = probability * 100
    missing = [name for name in WEIGHTS if values[name] is None]
    reasons = {name: list(inputs[name].reasons) for name in missing}
    partial = missing == ['S'] and set(event.S.reasons).issubset(PARTIAL_REASONS)
    status = 'complete' if not missing else ('partial' if partial else 'insufficient_data')
    score, total, applied = None, None, {}
    if status != 'insufficient_data':
        total = .85 if partial else 1.0
        applied = {name: weight / total for name, weight in WEIGHTS.items() if name not in missing}
        score = sum(WEIGHTS[name] * values[name] for name in applied) / total
        if not math.isfinite(score) or not -1e-12 <= score <= 100 + 1e-12:
            raise ArithmeticError('invalid final score')
    return dict(research_event_id=event.research_event_id, insider_edge_score=score,
                score_status=status, components=values, weights=dict(WEIGHTS),
                applied_weights=applied, original_weight_total=total,
                unavailable_components=missing, missing_reasons=reasons,
                ml_outperformance_probability=probability,
                model_name=event.model_name, model_version=event.model_version)


def build_insideredge_scores(events: Sequence[ScoreInput]) -> list[dict]:
    """Exactly one result per event sorted by ID; duplicates are invalid."""
    ids = [event.research_event_id for event in events]
    if any(not isinstance(identity, str) or not identity.strip() for identity in ids):
        raise ValueError('research_event_id must be a nonempty string')
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate research_event_id')
    return [score_event(event) for event in sorted(events, key=lambda event: event.research_event_id)]
