"""Versioned supplied-evidence contracts, not publication or provenance proof.

All fields are required unless explicitly given a default. Unknown chronology
uses TimeEvidence(state='unknown', value=None, reason=..., evidence_refs=()).
Attested means a supplied authority claim, NOT that this library authenticated it.
Reference closure validates an in-memory registry, never retained artifact bytes.
No scoring module imports: arithmetic below validates an archived claim only.
Use model_validate for typed Python mappings (tuple collections) or
model_validate_json for JSON arrays. Bare canonical_bytes(mapping) is a JSON
utility, not schema validation. Portable paths reject Windows device names,
trailing dots/spaces, and case-insensitive registry aliases. Safe paths are lexical only; no symlink checks
or artifact byte verification occur in this stage. Full audits/randomness may
contain only serialization-supported values; callers supply typed raw missingness
instead of bare nonfinite values. Artifact payload schema_version is opaque;
only this library's run/input/event/bundle top-level versions are interpreted.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import math
import re
from typing import Annotated, Any, Literal, get_args, get_origin

from pydantic import BaseModel, BeforeValidator, ConfigDict, field_validator, model_validator

from .serialization import canonical_bytes, parse_json


def _identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value):
        raise ValueError('expected bounded non-sensitive identifier')
    return value


def _text(value):
    if type(value) is not str or not value.strip():
        raise ValueError('expected nonempty string')
    return value


def _day(value):
    if type(value) is date:
        return value
    if type(value) is str:
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise ValueError('expected ISO calendar date')


def _timestamp(value):
    if type(value) is str:
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError('expected aware ISO timestamp') from None
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('expected timezone-aware timestamp')
    return value.astimezone(timezone.utc)


def _numeric(value):
    if type(value) not in (int, float):
        raise ValueError('expected finite number, not boolean/string')
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError('expected finite representable number')
    return float(value)


def _digest(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('expected lowercase SHA-256 digest')
    return value


def _commit(value):
    if type(value) is not str or not re.fullmatch("[0-9a-f]{40}", value):
        raise ValueError("expected full lowercase Git commit SHA")
    return value


def _path(value):
    if (type(value) is not str or not value or
            any(part in ('', '.', '..') for part in value.split('/')) or
            not re.fullmatch(r'[A-Za-z0-9_./-]+', value)):
        raise ValueError('expected safe relative POSIX path')
    if any(part.endswith(('.', ' ')) or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I) for part in value.split('/')):
        raise ValueError('nonportable artifact path')
    return value


Id = Annotated[str, BeforeValidator(_identifier)]
Text = Annotated[str, BeforeValidator(_text)]
Day = Annotated[date, BeforeValidator(_day)]
Timestamp = Annotated[datetime, BeforeValidator(_timestamp)]
Number = Annotated[float, BeforeValidator(_numeric)]
Digest = Annotated[str, BeforeValidator(_digest)]
SafePath = Annotated[str, BeforeValidator(_path)]
ComponentName = Literal['A', 'C', 'M', 'S', 'D']
WEIGHTS = {'A': .25, 'C': .15, 'M': .30, 'S': .15, 'D': .15}
_HISTORY = 'fewer_than_10_eligible_comparable_events'
PARTIAL_REASONS = {_HISTORY, 'bootstrap:' + _HISTORY, 'randomization:' + _HISTORY}


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True,
                              revalidate_instances='always', hide_input_in_errors=True)

    @classmethod
    def model_validate_json(cls, json_data: str | bytes, **kwargs):
        # Decode typed audit values and reject duplicate keys before strict
        # schema validation; restore only schema-declared tuple collections.
        return cls.model_validate(_json_collections(parse_json(json_data), cls), **kwargs)


def _json_collections(value, annotation):
    """Restore JSON arrays only where the strict schema declares tuples.

    Any-valued original audits retain their decoded list/mapping/scalar types.
    """
    if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(value, dict):
        return {key: _json_collections(item, annotation.model_fields[key].annotation)
                if key in annotation.model_fields else item for key, item in value.items()}
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is tuple and isinstance(value, list):
        return tuple(_json_collections(item, args[0]) for item in value)
    if origin is dict and isinstance(value, dict):
        return {key: _json_collections(item, args[1]) for key, item in value.items()}
    return value


class TimeEvidence(EvidenceModel):
    """A chronology claim, not automatic authentication or eligibility."""
    state: Literal['claimed', 'attested', 'unknown']
    value: Timestamp | None
    reason: Text | None
    evidence_refs: tuple[Id, ...]
    authority: Id | None = None

    @field_validator('evidence_refs')
    @classmethod
    def reference_order(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('duplicate time evidence references')
        return tuple(sorted(value))

    @model_validator(mode='after')
    def consistency(self):
        if self.state == 'unknown':
            if self.value is not None or self.reason is None or self.evidence_refs or self.authority:
                raise ValueError('unknown time requires null value, reason and no attestation')
        elif self.value is None or self.reason is not None:
            raise ValueError('known time requires value and no unknown reason')
        if self.state == 'attested' and (not self.evidence_refs or not self.authority):
            raise ValueError('attested time requires authority and evidence references')
        return self


def _ordered(*times):
    known = [time.value for time in times if time.value is not None]
    if any(a > b for a, b in zip(known, known[1:])):
        raise ValueError('contradictory chronology')


class ArtifactReference(EvidenceModel):
    artifact_id: Id
    path: SafePath
    sha256: Digest
    byte_count: int
    schema_version: Text  # Opaque referenced payload version; not a schema to load.
    row_count: int | None
    created_at: TimeEvidence

    @model_validator(mode='after')
    def counts(self):
        if self.byte_count < 0 or (self.row_count is not None and self.row_count < 0):
            raise ValueError('artifact counts must be nonnegative')
        return self


class ReferenceSlot(EvidenceModel):
    """Explicit unavailable reference; no invented placeholder artifact ID."""
    artifact_id: Id | None
    reason: Text | None

    @model_validator(mode='after')
    def consistency(self):
        if (self.artifact_id is None) != (self.reason is not None):
            raise ValueError('only missing reference requires reason')
        return self


class ModelTimeline(EvidenceModel):
    training_cutoff: TimeEvidence
    validation_outcome_end: TimeEvidence
    selected_at: TimeEvidence
    frozen_at: TimeEvidence
    activated_at: TimeEvidence
    available_at: TimeEvidence

    @model_validator(mode='after')
    def chronology(self):
        _ordered(self.training_cutoff, self.validation_outcome_end, self.selected_at,
                 self.frozen_at, self.activated_at)
        # Availability elsewhere need not equal activation in this environment.
        # Compare every known prerequisite even when freeze is unknown.
        # Availability elsewhere and local activation are separate branches:
        # neither is automatically ordered relative to the other.
        _ordered(self.training_cutoff, self.validation_outcome_end, self.selected_at,
                 self.frozen_at, self.available_at)
        return self


class DatasetManifest(EvidenceModel):
    schema_version: Literal['scoring-evidence/input/v1']
    dataset_id: Id
    dataset_type: Literal['prices', 'calendar', 'events', 'transactions', 'features',
                          'feature_provenance', 'identity_mapping', 'universe', 'source', 'other']
    source_reference: ReferenceSlot
    snapshot_id: Id
    content: ArtifactReference
    source_available_at: TimeEvidence
    snapshot_created_at: TimeEvidence
    calendar_policy: ReferenceSlot
    adjustment_policy: ReferenceSlot
    transformation: ReferenceSlot
    limitations: tuple[Text, ...]

    @model_validator(mode='after')
    def chronology(self):
        _ordered(self.source_available_at, self.snapshot_created_at)
        return self


class RawMissingness(EvidenceModel):
    """Original null/nonfinite/absent/unavailable evidence; never a score."""
    kind: Literal['null', 'nan', 'positive_infinity', 'negative_infinity',
                  'unavailable', 'not_supplied']
    reason: Text


class ComponentEvidence(EvidenceModel):
    value: Number | None  # Always 0–100, including M.
    status: Literal['available', 'unavailable']
    reasons: tuple[Text, ...]
    raw_missingness: RawMissingness | None
    implementation: ReferenceSlot
    inputs: tuple[Id, ...]
    computed_at: TimeEvidence
    source_available_at: TimeEvidence
    system_first_observed_at: TimeEvidence
    historical_available_at: TimeEvidence

    @field_validator('inputs')
    @classmethod
    def input_order(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('duplicate component input references')
        return tuple(sorted(value))

    @model_validator(mode='after')
    def consistency(self):
        if (self.value is None) != (self.status == 'unavailable'):
            raise ValueError('score contradicts component availability')
        if (self.value is None) != bool(self.reasons):
            raise ValueError('only unavailable score requires reasons')
        if self.value is not None and not 0 <= self.value <= 100:
            raise ValueError('component outside [0,100]')
        if self.value is not None and self.raw_missingness is not None:
            raise ValueError('available score cannot claim raw missingness')
        _ordered(self.source_available_at, self.computed_at, self.system_first_observed_at)
        _ordered(self.source_available_at, self.computed_at, self.historical_available_at)
        return self


class EventEvidence(EvidenceModel):
    schema_version: Literal['scoring-evidence/event/v1']
    run_id: Id
    research_event_id: Id
    ticker: Id
    public_event_day: Day
    information_date: Day
    observation_cutoff: Day
    source_transaction_refs: tuple[Id, ...]
    event_input: Id
    components: dict[ComponentName, ComponentEvidence]
    model_probability: Number | None
    model_reference: ReferenceSlot
    preprocessing_reference: ReferenceSlot
    insider_edge_score: Number | None
    score_status: Literal['complete', 'partial', 'insufficient_data']
    applied_weights: dict[ComponentName, Number]
    original_weight_total: Number | None
    ranking_context: Id
    ranking_membership: Literal['included', 'excluded', 'unscored']
    ranking_reason: Text | None
    input_lineage: tuple[Id, ...]
    scoring_policy: Id
    original_audit: dict[str, Any]

    @field_validator('source_transaction_refs', 'input_lineage')
    @classmethod
    def reference_order(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('duplicate event references')
        return tuple(sorted(value))

    @model_validator(mode='after')
    def consistency(self):
        if self.ticker != self.ticker.upper() or self.public_event_day <= self.information_date:
            raise ValueError('invalid ticker or public event timing')
        if set(self.components) != set(WEIGHTS):
            raise ValueError('exactly A/C/M/S/D components required')
        m = self.components['M'].value
        if (m is None) != (self.model_probability is None):
            raise ValueError('probability and M availability differ')
        if self.model_probability is not None:
            if not 0 <= self.model_probability <= 1 or not math.isclose(m, self.model_probability * 100, rel_tol=0, abs_tol=1e-12):
                raise ValueError('probability scaling inconsistent')
            if self.model_reference.artifact_id is None or self.preprocessing_reference.artifact_id is None:
                raise ValueError('available M requires model and preprocessing references')
        missing = {k for k, v in self.components.items() if v.value is None}
        partial = missing == {'S'} and set(self.components['S'].reasons) <= PARTIAL_REASONS
        status = 'complete' if not missing else ('partial' if partial else 'insufficient_data')
        if self.score_status != status:
            raise ValueError('composite status contradicts missing components')
        if status == 'insufficient_data':
            if self.insider_edge_score is not None or self.applied_weights or self.original_weight_total is not None:
                raise ValueError('insufficient score must be null with no applied weights')
        else:
            total = .85 if partial else 1.0
            weights = {k: w / total for k, w in WEIGHTS.items() if k not in missing}
            if self.original_weight_total != total or self.applied_weights != weights:
                raise ValueError('invalid applied weights or denominator')
            expected = sum(WEIGHTS[k] * self.components[k].value for k in weights) / total
            if self.insider_edge_score is None or not 0 <= self.insider_edge_score <= 100 or not math.isclose(self.insider_edge_score, expected, rel_tol=0, abs_tol=1e-9):
                raise ValueError('archived composite contradicts formula')
        if (self.ranking_membership == 'included') != (self.ranking_reason is None):
            raise ValueError('excluded/unscored membership requires reason')
        canonical_bytes(self.original_audit)  # No unsupported objects/nonfinite coercion.
        return self


class RunManifest(EvidenceModel):
    schema_version: Literal['scoring-evidence/run/v1']
    run_id: Id
    runner_version: Id
    code_commit_sha: Annotated[str, BeforeValidator(_commit)]
    code_state: Literal['clean', 'dirty']
    source_patch: ReferenceSlot
    run_kind: Literal['prospective', 'retrospective', 'synthetic']
    execution_started_at: Timestamp
    execution_finished_at: Timestamp
    historical_information_cutoff: Day
    observation_cutoff: Day
    environment_id: Id
    environment_manifest: ReferenceSlot
    scoring_policy: Id
    model: ReferenceSlot
    preprocessing: ReferenceSlot
    model_timeline: ModelTimeline
    input_manifests: tuple[Id, ...]
    identity_mapping: ReferenceSlot
    universe: ReferenceSlot
    eligibility_policy: ReferenceSlot
    calendar_policy: ReferenceSlot
    adjustment_policy: ReferenceSlot
    ranking_contexts: tuple[Id, ...]
    outputs: tuple[Id, ...]
    artifacts: tuple[ArtifactReference, ...]
    randomness: dict[str, Any]
    lineage: ReferenceSlot
    limitations: tuple[Text, ...]

    @field_validator('input_manifests', 'ranking_contexts', 'outputs')
    @classmethod
    def sorted_references(cls, value):
        return tuple(sorted(value))

    @field_validator('artifacts')
    @classmethod
    def sorted_artifacts(cls, value):
        return tuple(sorted(value, key=lambda artifact: artifact.artifact_id))

    @model_validator(mode='after')
    def consistency(self):
        if self.execution_finished_at < self.execution_started_at:
            raise ValueError('execution finish precedes start')
        if self.historical_information_cutoff > self.execution_finished_at.date() or self.observation_cutoff > self.execution_finished_at.date():
            raise ValueError('claimed cutoff exceeds execution date')
        for field in ('training_cutoff', 'validation_outcome_end', 'selected_at', 'frozen_at', 'activated_at', 'available_at'):
            value = getattr(self.model_timeline, field).value
            if value is not None and value > self.execution_finished_at:
                raise ValueError('model chronology exceeds run finish')
        if self.code_state == 'clean' and self.source_patch.artifact_id is not None:
            raise ValueError('clean code cannot have source patch')
        ids = [a.artifact_id for a in self.artifacts]
        paths = [a.path.casefold() for a in self.artifacts]
        if len(set(ids)) != len(ids) or len(set(paths)) != len(paths):
            raise ValueError('duplicate artifact identifiers or paths')
        for values in (self.input_manifests, self.outputs, self.ranking_contexts):
            if len(set(values)) != len(values):
                raise ValueError('duplicate reference IDs')
        if set(self.input_manifests) & set(self.outputs):
            raise ValueError('input manifest cannot also be output')
        refs = list(self.input_manifests + self.outputs + self.ranking_contexts) + [self.scoring_policy]
        for slot in (self.source_patch, self.environment_manifest, self.model, self.preprocessing,
                     self.identity_mapping, self.universe, self.eligibility_policy,
                     self.calendar_policy, self.adjustment_policy, self.lineage):
            if slot.artifact_id is not None:
                refs.append(slot.artifact_id)
        _require_refs(refs, set(ids))
        _time_refs(self.model_timeline, set(ids))
        for artifact in self.artifacts:
            if artifact.created_at.value is not None and artifact.created_at.value > self.execution_finished_at:
                raise ValueError('artifact created after run finish')
            _time_refs(artifact.created_at, set(ids))
        canonical_bytes(self.randomness)
        return self


def _require_refs(refs, ids):
    if any(ref not in ids for ref in refs):
        raise ValueError('reference absent from supplied artifact registry')


def _time_refs(value, ids):
    if isinstance(value, TimeEvidence):
        _require_refs(value.evidence_refs, ids)
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            _time_refs(getattr(value, name), ids)
    elif isinstance(value, dict):
        for item in value.values():
            _time_refs(item, ids)


class EvidenceBundle(EvidenceModel):
    """Validate supplied identities/reference closure; no IO or eligibility verdict.

    Registry membership proves neither matching bytes nor source authenticity.
    Null chronology is preservable. Model/source dates after historical cutoff
    are retained for retrospective runs, not misclassified as eligible evidence.
    """
    schema_version: Literal['scoring-evidence/bundle/v1']
    run: RunManifest
    datasets: tuple[DatasetManifest, ...]
    events: tuple[EventEvidence, ...]

    @field_validator('events')
    @classmethod
    def sorted_events(cls, value):
        return tuple(sorted(value, key=lambda event: event.research_event_id))

    @field_validator('datasets')
    @classmethod
    def sorted_datasets(cls, value):
        return tuple(sorted(value, key=lambda dataset: dataset.dataset_id))

    @model_validator(mode='after')
    def consistency(self):
        registry = {a.artifact_id: a for a in self.run.artifacts}
        ids = set(registry)
        event_ids = [e.research_event_id for e in self.events]
        dataset_ids = [d.dataset_id for d in self.datasets]
        if len(set(event_ids)) != len(event_ids) or len(set(dataset_ids)) != len(dataset_ids):
            raise ValueError('duplicate event or dataset IDs')
        if set(dataset_ids) != set(self.run.input_manifests):
            raise ValueError('dataset manifests do not match run inputs')
        for dataset in self.datasets:
            if dataset.content.artifact_id not in ids or dataset.content != registry[dataset.content.artifact_id]:
                raise ValueError('dataset content reference contradicts registry')
            _time_refs(dataset, ids)
            if dataset.source_available_at.value is not None and dataset.source_available_at.value > self.run.execution_finished_at:
                raise ValueError('input source available after run finish')
            if dataset.snapshot_created_at.value is not None and dataset.snapshot_created_at.value > self.run.execution_finished_at:
                raise ValueError('input snapshot created after run finish')
            for slot in (dataset.source_reference, dataset.calendar_policy,
                         dataset.adjustment_policy, dataset.transformation):
                if slot.artifact_id is not None:
                    _require_refs([slot.artifact_id], ids)
        for event in self.events:
            if event.run_id != self.run.run_id or event.scoring_policy != self.run.scoring_policy:
                raise ValueError('event run/policy mismatch')
            if event.information_date > self.run.historical_information_cutoff or event.observation_cutoff > self.run.observation_cutoff:
                raise ValueError('event cutoff exceeds run upper bound')
            if event.ranking_context not in self.run.ranking_contexts:
                raise ValueError('event ranking context absent from run')
            if event.model_reference != self.run.model or event.preprocessing_reference != self.run.preprocessing:
                raise ValueError('event model/preprocessing reference mismatch')
            _require_refs([event.event_input, *event.source_transaction_refs, *event.input_lineage], ids)
            for component in event.components.values():
                _require_refs(component.inputs, ids)
                for dataset in self.datasets:
                    if dataset.dataset_id in component.inputs or dataset.content.artifact_id in component.inputs:
                        _ordered(dataset.source_available_at, component.computed_at)
                        _ordered(dataset.source_available_at, component.historical_available_at)
                if component.implementation.artifact_id is not None:
                    _require_refs([component.implementation.artifact_id], ids)
                for time in (component.source_available_at, component.historical_available_at, component.system_first_observed_at):
                    if time.value is not None and time.value > self.run.execution_finished_at:
                        raise ValueError('component chronology exceeds run finish')
                if component.computed_at.value is not None and component.computed_at.value > self.run.execution_finished_at:
                    raise ValueError('component computed after run finished')
            _time_refs(event.components, ids)
        return self
