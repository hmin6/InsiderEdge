"""Synthetic preparation only; no production provenance or publication claims."""
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import subprocess
import sys

import pytest

from app.quant.evidence import canonical_bytes, parse_json
from app.quant.evidence.schemas import DatasetManifest, EventEvidence, TimeEvidence
from app.quant.evidence.capture import ArtifactSpec, PinnedArtifact, prepare_capture
from app.quant.evidence.verify import verify_bundle
from app.quant.insideredge_score import Component, ScoreInput, score_event
from test_evidence_schemas import bundle, unknown


@dataclass
class Batch:
    payloads: tuple
    audit: dict


@pytest.fixture
def inputs():
    data = bundle()
    refs = data['run'].pop('artifacts')
    raw = b'original pinned input\x00\xff\n'
    content = next(a for a in refs if a['artifact_id'] == 'input-data')
    content = {**content, 'byte_count': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    data['datasets'][0]['content'] = content
    event = EventEvidence.model_validate(data['events'][0])
    identity = event.research_event_id
    score = score_event(ScoreInput(identity, Component(50), Component(50), Component(.5), Component(50), Component(50)))
    payload = dict(research_event_id=identity, ticker='SYN', public_event_day=date(2026, 1, 2),
                   anomaly_score=50, activity_score=50, statistical_score=50, dislocation_score=50,
                   model_probability=.5, insider_edge_score=50, score_status='complete', unavailable_components=[],
                   model_name=None, model_version=None)
    outputs = {name: {field: 50, 'status': 'complete', reason: []} for name, field, reason in (
        ('anomaly', 'A', 'missing_reasons'), ('activity', 'activity_score', 'missing_reasons'),
        ('statistical', 'statistical_score', 'missing_reasons'), ('dislocation', 'dislocation_score', 'unavailable_reasons'))}
    outputs['event_study'] = {'car30': None, 'car30_status': 'unavailable'}
    prediction = {'probability': .5, 'status': 'complete', 'missing_reasons': []}
    audit = {'score': score, 'components': deepcopy(outputs), 'prediction': prediction}
    specs = tuple(ArtifactSpec(a['artifact_id'], a['path'],
        'scoring-evidence/input/v1' if a['artifact_id'] == 'dataset' else
        'scoring-evidence/event/v1' if a['artifact_id'] == 'output' else a['schema_version'],
        TimeEvidence.model_validate(a['created_at'])) for a in refs)
    pinned = tuple(PinnedArtifact(a.artifact_id, raw) for a in specs if a.artifact_id not in ('dataset', 'output'))
    return dict(run_context=data['run'], artifact_specs=specs, pinned_artifacts=pinned,
                datasets=(DatasetManifest.model_validate(data['datasets'][0]),), events=(event,),
                event_artifact_ids={identity: 'output'}, original_component_outputs={identity: outputs},
                signal_batch=Batch((payload,), {identity: audit}))


def test_prepared_archive_interoperates_and_preserves_bytes(inputs, tmp_path):
    prepared = prepare_capture(**inputs)
    assert prepared == prepare_capture(**inputs)
    assert prepared.manifest_sha256 == hashlib.sha256(prepared.manifest_bytes).hexdigest()
    for artifact in prepared.artifacts:
        assert artifact.reference.sha256 == hashlib.sha256(artifact.content).hexdigest()
        assert artifact.reference.byte_count == len(artifact.content)
        path = tmp_path / artifact.reference.path
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(artifact.content)
    (tmp_path / prepared.manifest_path).write_bytes(prepared.manifest_bytes)
    report = verify_bundle(tmp_path)
    assert report.status == report.structural_status == report.byte_integrity_status == 'valid'
    assert report.authenticated_publication == report.historical_eligibility == 'not_evaluated'
    assert {a.reference.artifact_id for a in prepared.artifacts} == {a.artifact_id for a in inputs['artifact_specs']}
    assert next(a.content for a in prepared.artifacts if a.reference.artifact_id == 'input-data') == inputs['pinned_artifacts'][0].content


@pytest.mark.parametrize('value', [True, 1, 1.0, Decimal('1.234567890123456789'), date(2026, 1, 1),
    datetime(2026, 1, 1, tzinfo=timezone.utc), {'$evidence/v1': ['decimal','1']}, None])
def test_original_typed_audit_roundtrip(inputs, value):
    identity = inputs['events'][0].research_event_id
    inputs['signal_batch'].audit[identity]['extra'] = {'nested': [value]}
    prepared = prepare_capture(**inputs)
    decoded = prepared.bundle.events[0].original_audit['signal_audit']['extra']['nested'][0]
    assert canonical_bytes(decoded) == canonical_bytes(value)
    assert type(decoded) is type(value)


def test_mutation_and_insertion_order_do_not_change_prepared_bytes(inputs):
    before = deepcopy(inputs)
    prepared = prepare_capture(**inputs)
    assert inputs == before
    reversed_inputs = {**inputs, 'run_context': dict(reversed(list(inputs['run_context'].items()))),
                       'artifact_specs': tuple(reversed(inputs['artifact_specs'])),
                       'pinned_artifacts': tuple(reversed(inputs['pinned_artifacts']))}
    assert prepare_capture(**reversed_inputs) == prepared
    inputs['signal_batch'].audit[next(iter(inputs['signal_batch'].audit))]['extra'] = 'changed'
    inputs['events'][0].original_audit['changed'] = True
    detached = prepared.bundle
    detached.events[0].original_audit['changed'] = True
    assert prepared.manifest_bytes == prepare_capture(**before).manifest_bytes
    assert 'changed' not in prepared.bundle.events[0].original_audit


def missing(inputs, name, reason):
    event = inputs['events'][0].model_dump(mode='python')
    event['components'][name].update(value=None, status='unavailable', reasons=(reason,),
                                    raw_missingness={'kind': 'nan', 'reason': 'producer_observed_nan'})
    values = {k: Component(c['value'], tuple(c['reasons'])) for k, c in event['components'].items()}
    probability = Component(None, (reason,)) if name == 'M' else Component(.5)
    score = score_event(ScoreInput(event['research_event_id'], values['A'], values['C'], probability, values['S'], values['D']))
    event.update(insider_edge_score=score['insider_edge_score'], score_status=score['score_status'],
                 applied_weights=score['applied_weights'], original_weight_total=score['original_weight_total'])
    if name == 'M': event['model_probability'] = None
    inputs['events'] = (EventEvidence.model_validate(event),)
    payload = inputs['signal_batch'].payloads[0]
    field = {'A':'anomaly_score','C':'activity_score','S':'statistical_score','D':'dislocation_score','M':'model_probability'}[name]
    payload.update({field:None, 'insider_edge_score':score['insider_edge_score'], 'score_status':score['score_status'], 'unavailable_components':[name]})
    identity = event['research_event_id']; audit = inputs['signal_batch'].audit[identity];audit['score'] = score
    if name == 'M':
        audit['prediction'] = {'probability': None, 'status': 'insufficient_data', 'missing_reasons': [reason]}
    else:
        section, field, reason_field = {'A':('anomaly','A','missing_reasons'), 'C':('activity','activity_score','missing_reasons'),
            'S':('statistical','statistical_score','missing_reasons'), 'D':('dislocation','dislocation_score','unavailable_reasons')}[name]
        inputs['original_component_outputs'][identity][section].update({field:None, 'status':'insufficient_data',reason_field:[reason]})
        audit['components'] = deepcopy(inputs['original_component_outputs'][identity])


@pytest.mark.parametrize('name,reason,status', [('S','fewer_than_10_eligible_comparable_events','partial'),
    ('S','invalid_randomization','insufficient_data'), ('C','missing_identity','insufficient_data'),
    ('A','missing_features','insufficient_data'), ('M','missing_model','insufficient_data'), ('D','missing_prices','insufficient_data')])
def test_existing_missing_policies_and_raw_missingness(inputs, name, reason, status):
    missing(inputs, name, reason)
    event = prepare_capture(**inputs).bundle.events[0]
    assert event.score_status == status
    assert event.components[name].raw_missingness.kind == 'nan'
    assert event.components[name].reasons == (reason,)
    assert event.insider_edge_score == (50 if status == 'partial' else None)


@pytest.mark.parametrize('field,value', [('model_probability',50),('insider_edge_score',51),
    ('activity_score',None),('model_probability',True),('score_status','partial'),('ticker','OTHER')])
def test_payload_contradictions_rejected(inputs, field, value):
    inputs['signal_batch'].payloads[0][field] = value
    with pytest.raises(ValueError): prepare_capture(**inputs)


@pytest.mark.parametrize('kind', ['duplicate_spec','duplicate_pinned','missing_bytes','conflicting_bytes',
                                 'duplicate_event','unknown_event','missing_model','wrong_digest','traversal','path_alias','wrong_output'])
def test_registry_and_identity_failures(inputs, kind):
    if kind == 'duplicate_spec': inputs['artifact_specs'] += (inputs['artifact_specs'][0],)
    elif kind == 'duplicate_pinned': inputs['pinned_artifacts'] += (inputs['pinned_artifacts'][0],)
    elif kind == 'missing_bytes': inputs['pinned_artifacts'] = inputs['pinned_artifacts'][1:]
    elif kind == 'conflicting_bytes': inputs['pinned_artifacts'] += (PinnedArtifact('output',b'conflict'),)
    elif kind == 'duplicate_event': inputs['events'] += inputs['events']
    elif kind == 'unknown_event': inputs['event_artifact_ids']['other'] = 'output'
    elif kind == 'missing_model': inputs['run_context']['model'] = {'artifact_id':None,'reason':'unknown'}
    elif kind == 'wrong_digest':
        inputs['pinned_artifacts'] = tuple(PinnedArtifact(a.artifact_id,b'changed') if a.artifact_id=='input-data' else a for a in inputs['pinned_artifacts'])
    elif kind == 'traversal': inputs['artifact_specs'] = (replace(inputs['artifact_specs'][0],path='../outside'),) + inputs['artifact_specs'][1:]
    elif kind == 'path_alias': inputs['artifact_specs'] = (replace(inputs['artifact_specs'][0],path=inputs['artifact_specs'][1].path.upper()),) + inputs['artifact_specs'][1:]
    else: inputs['run_context']['outputs'] = ('model',)
    with pytest.raises(ValueError): prepare_capture(**inputs)


@pytest.mark.parametrize('value', [object(), float('nan'), float('inf'), {1:'bad'}, datetime(2026,1,1)])
def test_unsupported_audit_not_coerced(inputs, value):
    next(iter(inputs['signal_batch'].audit.values()))['extra'] = value
    with pytest.raises(ValueError): prepare_capture(**inputs)


@pytest.mark.parametrize('field,value', [('max_artifact_bytes',1),('max_total_bytes',1),('max_artifact_bytes',True),('max_total_bytes',0)])
def test_size_bounds(inputs, field, value):
    with pytest.raises(ValueError): prepare_capture(**inputs, **{field:value})


def test_unknown_chronology_stays_unknown_and_contradiction_fails(inputs):
    prepared = prepare_capture(**inputs)
    assert prepared.bundle.run.model_timeline.available_at.state == 'unknown'
    inputs['run_context']['model_timeline']['selected_at'] = {'state':'claimed','value':'2027-01-01T00:00:00Z','reason':None,'evidence_refs':()}
    with pytest.raises(ValueError): prepare_capture(**inputs)


def test_import_has_no_io_or_model_dependencies():
    code = '''import sys
from app.quant.evidence.capture import prepare_capture
assert not any(n in sys.modules for n in ('sqlalchemy', 'sklearn', 'xgboost', 'app.services.signal_integration'))
'''
    result = subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('field,value', [('weights', {'A':1}), ('applied_weights', {}),
    ('original_weight_total',.85), ('ml_outperformance_probability',50),
    ('unavailable_components',['S']), ('missing_reasons',{'S':['invented']}),
    ('research_event_id','other'), ('model_version','contradiction')])
def test_score_audit_contradictions(inputs, field, value):
    next(iter(inputs['signal_batch'].audit.values()))['score'][field] = value
    with pytest.raises(ValueError): prepare_capture(**inputs)


@pytest.mark.parametrize('name', ['anomaly','activity','statistical','dislocation'])
def test_original_output_mismatch_is_not_repaired(inputs, name):
    identity = inputs['events'][0].research_event_id
    inputs['original_component_outputs'][identity][name]['extra'] = 'contradiction'
    with pytest.raises(ValueError, match='original component outputs'): prepare_capture(**inputs)


def test_size_limits_at_boundary(inputs):
    prepared = prepare_capture(**inputs)
    total = len(prepared.manifest_bytes) + sum(len(a.content) for a in prepared.artifacts)
    maximum = max([len(prepared.manifest_bytes)] + [len(a.content) for a in prepared.artifacts])
    assert prepare_capture(**inputs, max_total_bytes=total, max_artifact_bytes=maximum) == prepared
    for limits in ({'max_total_bytes': total-1}, {'max_artifact_bytes': maximum-1}):
        with pytest.raises(ValueError): prepare_capture(**inputs, **limits)


def test_preparation_performs_no_io(inputs, monkeypatch):
    import builtins
    import socket
    from pathlib import Path
    def forbidden(*args, **kwargs):
        pytest.fail('preparation must not perform IO')
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(Path, 'write_bytes', forbidden)
    monkeypatch.setattr(socket, 'socket', forbidden)
    assert prepare_capture(**inputs).bundle.run.run_kind == 'synthetic'


def test_actual_signal_batch_structural_interface(inputs):
    from app.services.signal_integration import SignalBatch
    batch = inputs['signal_batch']
    inputs['signal_batch'] = SignalBatch(batch.payloads, batch.audit)
    assert prepare_capture(**inputs).bundle.events[0].insider_edge_score == 50


@pytest.mark.parametrize('name', ['training_cutoff','selected_at','activated_at'])
def test_known_model_times_cannot_exceed_execution(inputs, name):
    inputs['run_context']['model_timeline'][name] = {
        'state':'claimed','value':'2027-01-01T00:00:00Z','reason':None,'evidence_refs':()}
    with pytest.raises(ValueError): prepare_capture(**inputs)


def set_complete_score_boundary(inputs, value):
    event = inputs['events'][0].model_dump(mode='python')
    for c in event['components'].values(): c['value'] = value
    event.update(model_probability=value/100, insider_edge_score=value)
    inputs['events'] = (EventEvidence.model_validate(event),)
    identity = event['research_event_id']; audit = inputs['signal_batch'].audit[identity]
    for name, field in [('anomaly','A'),('activity','activity_score'),('statistical','statistical_score'),('dislocation','dislocation_score')]:
        inputs['original_component_outputs'][identity][name][field] = value
    audit['components'] = deepcopy(inputs['original_component_outputs'][identity])
    audit['prediction']['probability'] = value/100
    audit['score']['components'] = {k:value for k in 'ACMSD'}
    audit['score'].update(insider_edge_score=value, ml_outperformance_probability=value/100)
    payload = inputs['signal_batch'].payloads[0]
    for field in ('anomaly_score','activity_score','statistical_score','dislocation_score','insider_edge_score'): payload[field] = value
    payload['model_probability'] = value/100


@pytest.mark.parametrize('value', [0, 100])
def test_complete_score_boundaries(inputs, value):
    set_complete_score_boundary(inputs, value)
    assert prepare_capture(**inputs).bundle.events[0].insider_edge_score == value


def test_multiple_events_deterministic_and_complete(inputs):
    first = inputs['events'][0]; other = first.model_dump(mode='python')
    other.update(research_event_id='OTHER:2026-01-02', ticker='OTHER')
    second = EventEvidence.model_validate(other)
    inputs['events'] = (second, first)
    identity = second.research_event_id
    payload = deepcopy(inputs['signal_batch'].payloads[0]);payload.update(research_event_id=identity,ticker='OTHER')
    inputs['signal_batch'].payloads += (payload,)
    audit = deepcopy(inputs['signal_batch'].audit[first.research_event_id]);audit['score']['research_event_id'] = identity
    inputs['signal_batch'].audit[identity] = audit
    inputs['original_component_outputs'][identity] = deepcopy(inputs['original_component_outputs'][first.research_event_id])
    inputs['event_artifact_ids'][identity] = 'output-other'
    inputs['artifact_specs'] += (ArtifactSpec('output-other','objects/output-other.json','scoring-evidence/event/v1',TimeEvidence.model_validate(unknown())),)
    inputs['run_context']['outputs'] += ('output-other',)
    prepared = prepare_capture(**inputs)
    assert [e.research_event_id for e in prepared.bundle.events] == sorted([first.research_event_id,identity])
    inputs['events'] = tuple(reversed(inputs['events']))
    inputs['signal_batch'].payloads = tuple(reversed(inputs['signal_batch'].payloads))
    assert prepare_capture(**inputs) == prepared


def test_missing_reasons_and_status_cannot_be_invented(inputs):
    missing(inputs,'C','missing_identity')
    identity = inputs['events'][0].research_event_id
    for source in (inputs['original_component_outputs'][identity],inputs['signal_batch'].audit[identity]['components']):
        del source['activity']['missing_reasons']
    with pytest.raises(ValueError, match='missing original reasons'): prepare_capture(**inputs)


def test_original_typed_conflict_is_not_python_equality(inputs):
    identity = inputs['events'][0].research_event_id
    inputs['original_component_outputs'][identity]['activity']['extra'] = True
    inputs['signal_batch'].audit[identity]['components']['activity']['extra'] = 1
    with pytest.raises(ValueError, match='original component outputs'): prepare_capture(**inputs)


@pytest.mark.parametrize('section', ['anomaly', 'activity', 'statistical', 'dislocation', 'event_study', 'prediction'])
@pytest.mark.parametrize('field,value', [('research_event_id', 'OTHER'), ('ticker', 'OTHER'),
    ('information_date', date(2027, 1, 1)), ('public_event_day', date(2027, 1, 2))])
def test_all_supplied_source_identities_must_match(inputs, section, field, value):
    identity = inputs['events'][0].research_event_id
    audit = inputs['signal_batch'].audit[identity]
    if section == 'prediction':
        audit['prediction'][field] = value
    else:
        inputs['original_component_outputs'][identity][section][field] = value
        audit['components'] = deepcopy(inputs['original_component_outputs'][identity])
    with pytest.raises(ValueError, match=field + ': contradictory evidence'):
        prepare_capture(**inputs)


def test_optional_identities_absent_or_matching_are_preserved(inputs):
    event = inputs['events'][0]
    identity = event.research_event_id
    prepared = prepare_capture(**inputs)
    original = prepared.bundle.events[0].original_audit['original_component_outputs']
    assert 'public_event_day' not in original['activity']
    assert 'research_event_id' not in original['event_study']
    fields = {field: getattr(event, field) for field in
              ('research_event_id', 'ticker', 'information_date', 'public_event_day')}
    for record in inputs['original_component_outputs'][identity].values():
        record.update(fields)
    audit = inputs['signal_batch'].audit[identity]
    audit['components'] = deepcopy(inputs['original_component_outputs'][identity])
    audit['prediction'].update(fields)
    assert prepare_capture(**inputs).bundle.events[0].insider_edge_score == 50


@pytest.mark.parametrize('record', ['payload', 'score'])
@pytest.mark.parametrize('field', ['ticker', 'information_date', 'public_event_day'])
def test_additional_batch_identity_fields_checked(inputs, record, field):
    identity = inputs['events'][0].research_event_id
    target = inputs['signal_batch'].payloads[0] if record == 'payload' else inputs['signal_batch'].audit[identity]['score']
    target[field] = 'OTHER' if field == 'ticker' else date(2027, 1, 1)
    with pytest.raises(ValueError, match=field): prepare_capture(**inputs)


@pytest.mark.parametrize('value', [None, [], 'not a record'])
def test_malformed_event_study_record_rejected(inputs, value):
    identity = inputs['events'][0].research_event_id
    inputs['original_component_outputs'][identity]['event_study'] = value
    inputs['signal_batch'].audit[identity]['components']['event_study'] = value
    with pytest.raises(ValueError, match='original event_study: expected mapping'):
        prepare_capture(**inputs)


@pytest.mark.parametrize('boundary', [0, 100])
@pytest.mark.parametrize('location', ['prediction', 'payload_probability', 'score_probability',
    'original_score', 'payload_score', 'audit_component', 'payload_final', 'audit_final'])
@pytest.mark.parametrize('numeric_type', [float, Decimal])
def test_original_bounds_are_strict_before_tolerance(inputs, boundary, location, numeric_type):
    # Use the same valid endpoint fixture as the existing acceptance test.
    set_complete_score_boundary(inputs, boundary)
    identity = inputs['events'][0].research_event_id
    audit = inputs['signal_batch'].audit[identity]
    probability = location in ('prediction', 'payload_probability', 'score_probability')
    endpoint = Decimal(boundary) / 100 if probability else Decimal(boundary)
    invalid = numeric_type(endpoint + (Decimal('-5e-13') if boundary == 0 else Decimal('5e-13')))
    if location == 'prediction': audit['prediction']['probability'] = invalid
    elif location == 'payload_probability': inputs['signal_batch'].payloads[0]['model_probability'] = invalid
    elif location == 'score_probability': audit['score']['ml_outperformance_probability'] = invalid
    elif location == 'original_score':
        inputs['original_component_outputs'][identity]['activity']['activity_score'] = invalid
        audit['components'] = deepcopy(inputs['original_component_outputs'][identity])
    elif location == 'payload_score': inputs['signal_batch'].payloads[0]['activity_score'] = invalid
    elif location == 'audit_component': audit['score']['components']['M'] = invalid
    elif location == 'payload_final': inputs['signal_batch'].payloads[0]['insider_edge_score'] = invalid
    else: audit['score']['insider_edge_score'] = invalid
    with pytest.raises(ValueError, match='numeric evidence'): prepare_capture(**inputs)


@pytest.mark.parametrize('value', [[], {}, True, None, '', 'bad/id'])
@pytest.mark.parametrize('location', ['spec', 'pinned', 'event_artifact', 'run_output', 'payload'])
def test_malformed_identifiers_raise_validation_errors(inputs, value, location):
    identity = inputs['events'][0].research_event_id
    if location == 'spec':
        inputs['artifact_specs'] = (replace(inputs['artifact_specs'][0], artifact_id=value),) + inputs['artifact_specs'][1:]
    elif location == 'pinned':
        inputs['pinned_artifacts'] = (PinnedArtifact(value, b'bytes'),) + inputs['pinned_artifacts'][1:]
    elif location == 'event_artifact': inputs['event_artifact_ids'][identity] = value
    elif location == 'run_output': inputs['run_context']['outputs'] = (value,)
    else: inputs['signal_batch'].payloads[0]['research_event_id'] = value
    with pytest.raises(ValueError): prepare_capture(**inputs)
