"""Pure preparation of explicitly supplied evidence; no IO or scoring execution.

Run metadata excludes ``artifacts``: the registry is derived from supplied bytes
and generated Stage 1 manifests. All chronology/identity/policy claims are caller
supplied, never authenticated here. See SCORING_EVIDENCE_CAPTURE_CONTRACT.md.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import math
from typing import Protocol

from .schemas import (ArtifactReference, DatasetManifest, EventEvidence,
                      EvidenceBundle, Id, SafePath, TimeEvidence, WEIGHTS)
from .serialization import MAX_BYTES, canonical_bytes
from pydantic import TypeAdapter


class SignalBatchLike(Protocol):
    """Structural interface; avoids importing scoring, ML or database modules."""
    payloads: tuple[dict, ...]
    audit: dict[str, dict]


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_id: str
    path: str
    schema_version: str
    created_at: TimeEvidence
    row_count: int | None = None


@dataclass(frozen=True)
class PinnedArtifact:
    artifact_id: str
    content: bytes


@dataclass(frozen=True)
class PreparedArtifact:
    reference: ArtifactReference
    content: bytes


@dataclass(frozen=True)
class PreparedCapture:
    """Bytes are authoritative; bundle returns a fresh defensive reconstruction."""
    manifest_path: str
    manifest_bytes: bytes
    manifest_sha256: str
    artifacts: tuple[PreparedArtifact, ...]

    @property
    def bundle(self) -> EvidenceBundle:
        return EvidenceBundle.model_validate_json(self.manifest_bytes)


def _equal(left, right, label):
    if canonical_bytes(left) != canonical_bytes(right):
        raise ValueError(f'{label}: contradictory evidence')


def _number_equal(left, right, label, upper=100):
    if left is None or right is None:
        if left is not None or right is not None:
            raise ValueError(f'{label}: contradictory missingness')
        return
    if type(left) not in (int, float, Decimal) or type(right) not in (int, float, Decimal):
        raise ValueError(f'{label}: expected finite numeric evidence')
    try:
        valid = (math.isfinite(left) and math.isfinite(right)
                 and 0 <= left <= upper and 0 <= right <= upper
                 and math.isclose(left, right, rel_tol=0, abs_tol=1e-12))
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise ValueError(f'{label}: contradictory or nonfinite numeric evidence')


def _identity(record, event, label):
    if not isinstance(record, Mapping):
        raise ValueError(f'{label}: expected mapping')
    for field in ('research_event_id', 'ticker', 'information_date', 'public_event_day'):
        if field in record:
            _equal(record[field], getattr(event, field), f'{label} {field}')


def _identifier(value):
    # Validate before hashing, sorting or set construction; never coerce IDs.
    return TypeAdapter(Id).validate_python(value)


def _records(rows, label):
    result = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f'{label}[{index}]: expected mapping')
        identity = row.get('research_event_id')
        if type(identity) is not str or not identity.strip() or identity in result:
            raise ValueError(f'{label}[{index}]: invalid or duplicate event ID')
        result[identity] = row
    return result


def _check_event(event, payload, audit, outputs):
    if not isinstance(audit, Mapping) or not isinstance(outputs, Mapping):
        raise ValueError('event audit and component outputs must be mappings')
    required = ('score', 'components', 'prediction')
    if any(key not in audit for key in required):
        raise ValueError('signal audit requires score, components and prediction')
    _equal(audit['components'], outputs, 'original component outputs')
    for section in ('anomaly', 'activity', 'statistical', 'dislocation', 'event_study'):
        if section in outputs:
            _identity(outputs[section], event, f'original {section}')
    _identity(audit['prediction'], event, 'original M')
    _identity(payload, event, 'payload')
    score = audit['score']
    if not isinstance(score, Mapping) or not isinstance(audit['prediction'], Mapping):
        raise ValueError('score and prediction audit must be mappings')
    _identity(score, event, 'score audit')
    for key, expected in [('research_event_id', event.research_event_id),
                          ('ticker', event.ticker), ('public_event_day', event.public_event_day),
                          ('score_status', event.score_status)]:
        if key not in payload:
            raise ValueError(f'payload requires {key}')
        _equal(payload[key], expected, f'payload {key}')
    for key in ('research_event_id', 'score_status', 'applied_weights', 'original_weight_total'):
        if key not in score:
            raise ValueError(f'score audit requires {key}')
    _equal(score['research_event_id'], event.research_event_id, 'score event ID')
    _equal(score['score_status'], event.score_status, 'score status')
    # Numeric schema fields normalize to float; compare arithmetic numerically,
    # while original audit identity remains typed and byte-exact.
    _equal(_sorted_missing(score.get('unavailable_components')), sorted(k for k, c in event.components.items() if c.value is None), 'score missing components')
    _equal(_sorted_missing(payload.get('unavailable_components')), sorted(k for k, c in event.components.items() if c.value is None), 'payload missing components')
    for field, expected in [('weights', WEIGHTS), ('applied_weights', event.applied_weights)]:
        values = score.get(field)
        if not isinstance(values, Mapping) or set(values) != set(expected):
            raise ValueError(f'score {field}: invalid keys')
        for key in expected:
            _number_equal(values[key], expected[key], f'score {field}', upper=1)
    _number_equal(score['original_weight_total'], event.original_weight_total, 'score denominator', upper=1)
    for record, field in ((payload, 'insider_edge_score'), (score, 'insider_edge_score')):
        if field not in record: raise ValueError(f'requires {field}')
        _number_equal(record[field], event.insider_edge_score, field)
    values = score.get('components')
    reasons = score.get('missing_reasons')
    if not isinstance(values, Mapping) or set(values) != set(WEIGHTS) or not isinstance(reasons, Mapping):
        raise ValueError('score requires all component values and missing reasons')
    missing = {k: list(c.reasons) for k, c in event.components.items() if c.value is None}
    _equal(reasons, missing, 'component missing reasons')
    fields = {'A': ('anomaly', 'A', 'anomaly_score', 'missing_reasons'),
              'C': ('activity', 'activity_score', 'activity_score', 'missing_reasons'),
              'S': ('statistical', 'statistical_score', 'statistical_score', 'missing_reasons'),
              'D': ('dislocation', 'dislocation_score', 'dislocation_score', 'unavailable_reasons')}
    for name, component in event.components.items():
        _number_equal(values[name], component.value, f'score {name}')
        if name == 'M':
            source, source_field, payload_field, reason_field = audit['prediction'], 'probability', 'model_probability', 'missing_reasons'
            expected = event.model_probability
        else:
            section, source_field, payload_field, reason_field = fields[name]
            source = outputs.get(section)
            expected = component.value
        if not isinstance(source, Mapping) or source_field not in source or payload_field not in payload:
            raise ValueError(f'{name}: missing original output or payload field')
        upper = 1 if name == 'M' else 100
        _number_equal(source[source_field], expected, f'original {name}', upper=upper)
        _number_equal(payload[payload_field], expected, f'payload {name}', upper=upper)
        if expected is not None:
            if source.get('status') != 'complete' or source.get(reason_field) not in ([], ()):
                raise ValueError(f'{name}: contradictory original availability')
        else:
            if type(source.get('status')) is not str or not source['status'].strip():
                raise ValueError(f'{name}: missing original availability status')
            if not isinstance(source.get(reason_field), (list, tuple)):
                raise ValueError(f'{name}: missing original reasons')
            if source.get('status') == 'complete':
                raise ValueError(f'{name}: contradictory original availability')
            _equal(list(source.get(reason_field, ())), list(component.reasons), f'original {name} reasons')
    if 'ml_outperformance_probability' not in score:
        raise ValueError('score audit requires probability')
    _number_equal(score['ml_outperformance_probability'], event.model_probability, 'score probability', upper=1)
    for field in ('model_name', 'model_version'):
        if field not in score or field not in payload:
            raise ValueError(f'requires {field}')
        _equal(score[field], payload[field], field)


def _sorted_missing(value):
    if not isinstance(value, (list, tuple)) or any(type(k) is not str for k in value) or len(set(value)) != len(value):
        raise ValueError('unavailable components must be unique string IDs')
    return sorted(value)


def prepare_capture(*, run_context: Mapping[str, object],
                    artifact_specs: Sequence[ArtifactSpec],
                    pinned_artifacts: Sequence[PinnedArtifact],
                    datasets: Sequence[DatasetManifest], events: Sequence[EventEvidence],
                    event_artifact_ids: Mapping[str, str],
                    original_component_outputs: Mapping[str, Mapping],
                    signal_batch: SignalBatchLike,
                    manifest_path: str = 'bundle.json',
                    max_artifact_bytes: int = 16_000_000,
                    max_total_bytes: int = 64_000_000) -> PreparedCapture:
    """Prepare exact bytes plus generated manifests; no writes or recomputation.

    run_context supplies every RunManifest field except artifacts. Dataset
    content references must already agree with the supplied pinned bytes.
    event_artifact_ids explicitly assigns every event to one run output.
    Existing event audits are retained alongside batch audit/component records.
    Nonfinite/unsupported audit values fail: supply explicit RawMissingness
    records with producer reasons before serving normalization loses evidence.
    Default bounds apply to all prepared bytes, including the root manifest.
    """
    for value in (max_artifact_bytes, max_total_bytes):
        if type(value) is not int or value <= 0: raise ValueError('preparation limits must be positive integers')
    TypeAdapter(SafePath).validate_python(manifest_path)
    if not isinstance(run_context, Mapping) or 'artifacts' in run_context:
        raise ValueError('run_context must be a mapping excluding artifacts')
    specs = {}
    for spec in artifact_specs:
        if not isinstance(spec, ArtifactSpec):
            raise ValueError('invalid artifact specification')
        _identifier(spec.artifact_id)
        if type(spec.schema_version) is not str:
            raise ValueError('artifact schema version must be a string')
        if spec.artifact_id in specs:
            raise ValueError('invalid or duplicate artifact specification')
        specs[spec.artifact_id] = spec
    contents = {}
    for artifact in pinned_artifacts:
        if not isinstance(artifact, PinnedArtifact) or type(artifact.content) is not bytes:
            raise ValueError('pinned artifacts require immutable bytes')
        _identifier(artifact.artifact_id)
        if artifact.artifact_id in contents: raise ValueError('duplicate pinned artifact ID')
        contents[artifact.artifact_id] = artifact.content
    datasets = tuple(DatasetManifest.model_validate(d) for d in datasets)
    events = tuple(EventEvidence.model_validate(e) for e in events)
    ids = [e.research_event_id for e in events]
    if len(set(ids)) != len(ids): raise ValueError('duplicate event ID')
    payloads = _records(signal_batch.payloads, 'payloads')
    audits = signal_batch.audit
    for mapping in (payloads, audits, original_component_outputs, event_artifact_ids):
        if not isinstance(mapping, Mapping) or set(mapping) != set(ids):
            raise ValueError('capture event IDs must match exactly')
    for value in event_artifact_ids.values():
        _identifier(value)
    outputs = run_context.get('outputs', ())
    if not isinstance(outputs, (list, tuple)):
        raise ValueError('run outputs must be a sequence of identifiers')
    for value in outputs:
        _identifier(value)
    if len(set(event_artifact_ids.values())) != len(ids): raise ValueError('duplicate event artifact ID')
    generated = {}
    for dataset in datasets:
        if dataset.dataset_id in generated: raise ValueError('duplicate dataset ID')
        generated[dataset.dataset_id] = ('scoring-evidence/input/v1', canonical_bytes(dataset))
    captured_events = []
    for event in events:
        identity = event.research_event_id
        _check_event(event, payloads[identity], audits[identity], original_component_outputs[identity])
        data = event.model_dump(mode='python')
        data['original_audit'] = dict(event_audit=event.original_audit, signal_payload=payloads[identity],
                                     signal_audit=audits[identity], original_component_outputs=original_component_outputs[identity])
        captured = EventEvidence.model_validate(data)
        captured_events.append(captured)
        artifact_id = event_artifact_ids[identity]
        if artifact_id in generated: raise ValueError('conflicting generated artifact ID')
        generated[artifact_id] = ('scoring-evidence/event/v1', canonical_bytes(captured))
    if set(contents) & set(generated): raise ValueError('pinned bytes conflict with generated manifest ID')
    if set(specs) != set(contents) | set(generated): raise ValueError('artifact specifications do not match complete byte registry')
    if set(event_artifact_ids.values()) != set(run_context.get('outputs', ())):
        raise ValueError('run outputs must match event artifact IDs')
    prepared = []
    total = 0
    for identity in sorted(specs):
        spec = specs[identity]
        if identity in generated:
            version, raw = generated[identity]
            if spec.schema_version != version: raise ValueError('generated manifest schema mismatch')
        else:
            raw = contents[identity]
            if spec.schema_version.startswith('scoring-evidence/'):
                raise ValueError('pinned artifacts must be opaque, not evidence manifests')
        if len(raw) > max_artifact_bytes: raise ValueError('artifact preparation size limit exceeded')
        total += len(raw)
        if total > max_total_bytes: raise ValueError('total preparation size limit exceeded')
        reference = ArtifactReference(artifact_id=identity, path=spec.path, schema_version=spec.schema_version,
                                      created_at=spec.created_at, row_count=spec.row_count,
                                      byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        if reference.path.casefold() == manifest_path.casefold(): raise ValueError('manifest path aliases artifact')
        prepared.append(PreparedArtifact(reference, raw))
    bundle = EvidenceBundle.model_validate(dict(schema_version='scoring-evidence/bundle/v1',
        run={**run_context, 'artifacts': tuple(a.reference for a in prepared)}, datasets=datasets, events=tuple(captured_events)))
    raw = canonical_bytes(bundle)
    if len(raw) > min(MAX_BYTES, max_artifact_bytes) or total + len(raw) > max_total_bytes:
        raise ValueError('manifest or total preparation size limit exceeded')
    # Detach nested mutable schema containers from callers; bytes are immutable.
    detached = tuple(PreparedArtifact(ArtifactReference.model_validate_json(canonical_bytes(a.reference)), a.content) for a in prepared)
    return PreparedCapture(manifest_path, raw, hashlib.sha256(raw).hexdigest(), detached)
