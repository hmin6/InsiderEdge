"""Synthetic evidence only; no historical records, services or model loading."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError
from app.quant.evidence import (
    ArtifactReference, ComponentEvidence, DatasetManifest, EventEvidence,
    EvidenceBundle, RunManifest, TimeEvidence, canonical_bytes, content_digest, parse_json,
)


def unknown():
    return dict(state='unknown', value=None, reason='synthetic_not_supplied', evidence_refs=())


def claimed(day='2026-01-01'):
    return dict(state='claimed', value=day + 'T00:00:00Z', reason=None, evidence_refs=())


def slot(identity=None):
    return dict(artifact_id=identity, reason='synthetic_unavailable' if identity is None else None)


def artifact(identity):
    return dict(artifact_id=identity, path='objects/' + identity + '.json', sha256='a' * 64,
                byte_count=10, schema_version='synthetic/payload/v1', row_count=None, created_at=unknown())


def component(value=50):
    return dict(value=value, status='available' if value is not None else 'unavailable',
                reasons=() if value is not None else ('synthetic_missing',),
                raw_missingness=None if value is not None else dict(kind='null', reason='original_null'),
                implementation=slot('implementation'), inputs=('input-data',), computed_at=claimed(),
                source_available_at=unknown(), system_first_observed_at=unknown(), historical_available_at=unknown())


def event(identity='SYN:2026-01-02'):
    return dict(schema_version='scoring-evidence/event/v1', run_id='synthetic-run',
                research_event_id=identity, ticker='SYN', public_event_day='2026-01-02',
                information_date='2026-01-01', observation_cutoff='2026-01-01',
                source_transaction_refs=('source',), event_input='input-data',
                components={k: component() for k in 'ACMSD'}, model_probability=.5,
                model_reference=slot('model'), preprocessing_reference=slot('preprocessing'),
                insider_edge_score=50, score_status='complete',
                applied_weights=dict(A=.25, C=.15, M=.30, S=.15, D=.15), original_weight_total=1,
                ranking_context='context', ranking_membership='included', ranking_reason=None,
                input_lineage=('input-data',), scoring_policy='policy',
                original_audit={'synthetic': True, 'nested': {'b': [1, None], 'a': 'é'}})


def dataset():
    return dict(schema_version='scoring-evidence/input/v1', dataset_id='dataset', dataset_type='prices',
                source_reference=slot('source'), snapshot_id='snapshot', content=artifact('input-data'),
                source_available_at=unknown(), snapshot_created_at=claimed(), calendar_policy=slot('calendar'),
                adjustment_policy=slot('adjustment'), transformation=slot(), limitations=('synthetic',))


def run():
    names = ['source', 'dataset', 'input-data', 'implementation', 'model', 'preprocessing',
             'policy', 'context', 'calendar', 'adjustment', 'identity', 'universe', 'eligibility', 'output']
    return dict(schema_version='scoring-evidence/run/v1', run_id='synthetic-run', runner_version='v1',
                code_commit_sha='a' * 40, code_state='clean', source_patch=slot(), run_kind='synthetic',
                execution_started_at='2026-01-01T00:00:00Z', execution_finished_at='2026-01-03T00:00:00Z',
                historical_information_cutoff='2026-01-01', observation_cutoff='2026-01-01',
                environment_id='synthetic-test', environment_manifest=slot(), scoring_policy='policy',
                model=slot('model'), preprocessing=slot('preprocessing'),
                model_timeline={k: unknown() for k in ('training_cutoff', 'validation_outcome_end',
                    'selected_at', 'frozen_at', 'activated_at', 'available_at')},
                input_manifests=('dataset',), identity_mapping=slot('identity'), universe=slot('universe'),
                eligibility_policy=slot('eligibility'), calendar_policy=slot('calendar'),
                adjustment_policy=slot('adjustment'), ranking_contexts=('context',), outputs=('output',),
                artifacts=tuple(artifact(n) for n in names), randomness={'model_seed': 42}, lineage=slot(),
                limitations=('synthetic_only',))


def bundle():
    return dict(schema_version='scoring-evidence/bundle/v1', run=run(), datasets=(dataset(),), events=(event(),))


def test_valid_schemas_and_bundle_roundtrip():
    for schema, payload in [(RunManifest, run()), (DatasetManifest, dataset()),
                            (EventEvidence, event()), (EvidenceBundle, bundle())]:
        model = schema.model_validate(payload)
        assert canonical_bytes(schema.model_validate_json(canonical_bytes(model))) == canonical_bytes(model)


def test_known_canonical_bytes_and_hash():
    value = {'z': [None, True], 'é': '你好', 'a': 1.25}
    expected = '{"a":1.25,"z":[null,true],"é":"你好"}\n'.encode()
    assert canonical_bytes(value) == expected
    assert content_digest(value) == hashlib.sha256(expected).hexdigest()
    assert canonical_bytes(dict(reversed(list(value.items())))) == expected
    assert parse_json(expected) == value


def test_timestamp_timezone_and_decimal_equivalence():
    a = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert canonical_bytes(a) == canonical_bytes(a.astimezone(timezone(timedelta(hours=-5))))
    assert parse_json(canonical_bytes(a)) == a
    assert parse_json(canonical_bytes(date(2026, 1, 1))) == date(2026, 1, 1)
    assert canonical_bytes(Decimal('1.200')) == canonical_bytes(Decimal('1.2'))
    assert canonical_bytes(-0.0) == canonical_bytes(0.0)
    assert canonical_bytes([1, 2]) != canonical_bytes([2, 1])


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'), Decimal('NaN'),
                                   object(), {1: 'not-string'}, {1, 2}, datetime(2026, 1, 1)])
def test_unsupported_canonical_values(value):
    with pytest.raises(ValueError): canonical_bytes({'nested': value})


@pytest.mark.parametrize('text', ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}', '{"a":1e999}'])
def test_strict_json_parser(text):
    with pytest.raises(ValueError): parse_json(text)


def test_cycle_rejected_without_mutation():
    value = []; value.append(value)
    with pytest.raises(ValueError, match='cyclic'): canonical_bytes(value)
    assert value[0] is value


@pytest.mark.parametrize('kind', ['null', 'nan', 'positive_infinity', 'negative_infinity', 'unavailable', 'not_supplied'])
def test_raw_missingness_is_explicit_and_distinct(kind):
    data = component(None); data['raw_missingness']['kind'] = kind
    obj = ComponentEvidence.model_validate(data)
    assert obj.value is None and obj.raw_missingness.kind == kind
    assert parse_json(canonical_bytes(obj))['raw_missingness']['kind'] == kind


@pytest.mark.parametrize('value', [True, False, '50', 'bad', float('nan'), float('inf'), -float('inf'), -1, 101])
def test_invalid_available_component_values(value):
    with pytest.raises(ValidationError): ComponentEvidence.model_validate(component(value))


@pytest.mark.parametrize('value', [0, 100])
def test_valid_component_boundaries(value):
    assert ComponentEvidence.model_validate(component(value)).value == value


@pytest.mark.parametrize('change', [dict(value=None), dict(status='unavailable'),
    dict(reasons=('wrong',)), dict(raw_missingness={'kind':'nan', 'reason':'wrong'})])
def test_contradictory_availability(change):
    data = component(); data.update(change)
    with pytest.raises(ValidationError): ComponentEvidence.model_validate(data)


@pytest.mark.parametrize('probability', [True, '0.5', -1, 1.01, 50, None, float('nan')])
def test_probability_validation(probability):
    data = event(); data['model_probability'] = probability
    with pytest.raises(ValidationError): EventEvidence.model_validate(data)


def test_probability_mismatch_and_missing_model():
    for field, value in [('model_probability', .6), ('model_reference', slot()), ('preprocessing_reference', slot())]:
        data = event(); data[field] = value
        with pytest.raises(ValidationError): EventEvidence.model_validate(data)


def test_complete_and_partial_arithmetic():
    data = event(); data['components'] = {k: component(v) for k,v in dict(A=20,C=40,M=60,S=80,D=100).items()}
    data.update(model_probability=.6, insider_edge_score=56)
    assert EventEvidence.model_validate(data).insider_edge_score == 56
    data['components']['S'] = component(None)
    data['components']['S']['reasons'] = ('fewer_than_10_eligible_comparable_events',)
    data.update(insider_edge_score=44/.85, score_status='partial', original_weight_total=.85,
                applied_weights={k:w/.85 for k,w in dict(A=.25,C=.15,M=.30,D=.15).items()})
    assert EventEvidence.model_validate(data).score_status == 'partial'
    data['components']['S']['reasons'] = ('randomization_failed',)
    with pytest.raises(ValidationError): EventEvidence.model_validate(data)


def test_insufficient_score_never_fills_zero():
    data = event(); data['components']['C'] = component(None)
    data.update(score_status='insufficient_data', insider_edge_score=None, applied_weights={}, original_weight_total=None)
    assert EventEvidence.model_validate(data).insider_edge_score is None
    data['insider_edge_score'] = 0
    with pytest.raises(ValidationError): EventEvidence.model_validate(data)


@pytest.mark.parametrize('field,value', [('insider_edge_score',49), ('applied_weights',{}),
    ('original_weight_total',.85), ('score_status','partial'), ('components',{'A':component()}),
    ('public_event_day','2026-01-01'), ('ticker','syn'), ('information_date','not-date')])
def test_invalid_event_contract(field,value):
    data=event(); data[field]=value
    with pytest.raises(ValidationError): EventEvidence.model_validate(data)


@pytest.mark.parametrize('schema,payload', [(RunManifest,run),(EventEvidence,event),(DatasetManifest,dataset),(EvidenceBundle,bundle)])
def test_unknown_versions_and_extra_fields(schema,payload):
    data=payload(); data['schema_version']='future/v99'
    with pytest.raises(ValidationError): schema.model_validate(data)
    data=payload(); data['extra']='unrecognized'
    with pytest.raises(ValidationError): schema.model_validate(data)


@pytest.mark.parametrize('path', ['/absolute', '../escape', 'a/../b', 'a/./b', 'a//b',
    'C:/secret', 'a\\b', 'https://host/file', '%2e%2e/x', 'a\x00b', ''])
def test_unsafe_paths(path):
    data=artifact('x'); data['path']=path
    with pytest.raises(ValidationError): ArtifactReference.model_validate(data)


@pytest.mark.parametrize('field,value', [('sha256','f'*63),('sha256','A'*64),('sha256','bad'),
    ('byte_count',True),('byte_count',-1),('row_count',-1),('artifact_id','../x')])
def test_artifact_validation(field,value):
    data=artifact('x'); data[field]=value
    with pytest.raises(ValidationError): ArtifactReference.model_validate(data)


def test_duplicate_event_dataset_artifact_ids_and_paths():
    data=bundle(); data['events']*=2
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)
    data=bundle(); data['datasets']*=2
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)
    data=run(); data['artifacts']+=(deepcopy(data['artifacts'][0]),)
    with pytest.raises(ValidationError): RunManifest.model_validate(data)
    data=run(); data['artifacts'][1]['path']=data['artifacts'][0]['path']
    with pytest.raises(ValidationError): RunManifest.model_validate(data)


@pytest.mark.parametrize('field,value', [('event_input','missing'), ('run_id','other'),
    ('scoring_policy','other'), ('ranking_context','absent'), ('model_reference',slot('source')),
    ('input_lineage',('absent',)), ('source_transaction_refs',('absent',))])
def test_event_reference_closure(field,value):
    data=bundle(); data['events'][0][field]=value
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)


def test_missing_manifest_and_contradictory_dataset_reference():
    data=bundle(); data['datasets']=()
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)
    data=bundle(); data['datasets'][0]['content']['sha256']='b'*64
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)
    data=run(); data['outputs']=('missing',)
    with pytest.raises(ValidationError): RunManifest.model_validate(data)


def test_time_claims_and_attestations_do_not_prove_trust():
    assert TimeEvidence.model_validate(unknown()).state == 'unknown'
    assert TimeEvidence.model_validate(claimed()).state == 'claimed'
    data=claimed(); data.update(state='attested', authority='synthetic-authority', evidence_refs=('source',))
    assert TimeEvidence.model_validate(data).state == 'attested'
    data['authority']=None
    with pytest.raises(ValidationError): TimeEvidence.model_validate(data)


@pytest.mark.parametrize('value', ['2026-01-01', 'bad', datetime(2026,1,1), True])
def test_invalid_timestamp(value):
    data=claimed(); data['value']=value
    with pytest.raises(ValidationError): TimeEvidence.model_validate(data)


def test_unknown_timestamp_cannot_hide_claim():
    data=unknown(); data['value']='2026-01-01T00:00:00Z'
    with pytest.raises(ValidationError): TimeEvidence.model_validate(data)


@pytest.mark.parametrize('earlier,later', [('training_cutoff','validation_outcome_end'),
    ('validation_outcome_end','selected_at'), ('selected_at','frozen_at'), ('frozen_at','activated_at'),
    ('frozen_at','available_at')])
def test_model_chronology(earlier,later):
    data=run(); data['model_timeline'][earlier]=claimed('2026-01-02');data['model_timeline'][later]=claimed()
    with pytest.raises(ValidationError): RunManifest.model_validate(data)


def test_execution_and_source_chronology():
    data=run(); data['execution_finished_at']='2025-01-01T00:00:00Z'
    with pytest.raises(ValidationError): RunManifest.model_validate(data)
    data=dataset(); data['source_available_at']=claimed('2026-01-02')
    with pytest.raises(ValidationError): DatasetManifest.model_validate(data)
    data=component(); data['source_available_at']=claimed('2026-01-02')
    with pytest.raises(ValidationError): ComponentEvidence.model_validate(data)
    data=bundle(); data['events'][0]['components']['A']['computed_at']=claimed('2026-01-04')
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)


def test_legitimate_retrospective_run_retains_late_model_without_eligibility_claim():
    data=bundle(); data['run']['run_kind']='retrospective'
    data['run']['execution_started_at']='2026-02-01T00:00:00Z'
    data['run']['execution_finished_at']='2026-02-02T00:00:00Z'
    data['run']['model_timeline']['available_at']=claimed('2026-02-01')
    result=EvidenceBundle.model_validate(data)
    assert result.run.model_timeline.available_at.value.date() > result.events[0].information_date
    assert not hasattr(result,'historically_verified')


def test_heterogeneous_cutoffs_and_deterministic_event_order():
    data=bundle(); early=event('SYN:2025-12-31')
    early.update(information_date='2025-12-30',public_event_day='2025-12-31',observation_cutoff='2025-12-30')
    data['events']+=(early,)
    a=EvidenceBundle.model_validate(data)
    data['events']=tuple(reversed(data['events']))
    assert canonical_bytes(a)==canonical_bytes(EvidenceBundle.model_validate(data))
    assert a.events[0].information_date==date(2025,12,30)
    data['events'][0]['information_date']='2026-01-02'; data['events'][0]['public_event_day']='2026-01-03'
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)


def test_observation_upper_bound():
    data=bundle(); data['events'][0]['observation_cutoff']='2026-01-02'
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)


def test_nested_audit_determinism_and_no_mutation():
    data=bundle(); before=deepcopy(data)
    obj=EvidenceBundle.model_validate(data); encoded=canonical_bytes(obj)
    data['events'][0]['original_audit']['nested']={'a':'é','b':[1,None]}
    assert canonical_bytes(EvidenceBundle.model_validate(data))==encoded
    assert before==data
    assert content_digest(obj)==hashlib.sha256(encoded).hexdigest()


def test_mutated_nested_model_is_revalidated_before_serialization():
    obj=EventEvidence.model_validate(event()); obj.components.pop('A')
    with pytest.raises(ValidationError): canonical_bytes(obj)


def test_import_has_no_production_dependencies_or_io():
    script='''
import sys
from pydantic import BaseModel
import json, hashlib, decimal, datetime
sys.dont_write_bytecode = True

def deny(event, args):
    if event.startswith(('socket.', 'subprocess.')):
        raise AssertionError(event)
    if event == 'open' and len(args)>1 and isinstance(args[1],str) and any(c in args[1] for c in 'wax+'):
        raise AssertionError('write')
sys.addaudithook(deny)
import app.quant.evidence
assert not any(n.startswith(('sqlalchemy','sklearn','xgboost','app.services','app.db')) for n in sys.modules)
'''
    result=subprocess.run([sys.executable,'-B','-c',script], capture_output=True, text=True,
                          cwd=Path(__file__).resolve().parents[1])
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('field', ['code_commit_sha', 'execution_started_at', 'model_timeline', 'scoring_policy'])
def test_missing_required_run_fields(field):
    data = run(); del data[field]
    with pytest.raises(ValidationError): RunManifest.model_validate(data)


@pytest.mark.parametrize('value', ['a'*64, 'b'*39, 'B'*40, True])
def test_invalid_git_commits(value):
    data = run(); data['code_commit_sha'] = value
    with pytest.raises(ValidationError): RunManifest.model_validate(data)


@pytest.mark.parametrize('field', ['training_cutoff', 'validation_outcome_end', 'selected_at',
                                   'frozen_at', 'activated_at', 'available_at'])
def test_model_times_cannot_follow_completed_run(field):
    data = run(); data['model_timeline'][field] = claimed('2026-01-04')
    with pytest.raises(ValidationError): RunManifest.model_validate(data)


@pytest.mark.parametrize('field', ['historical_information_cutoff', 'observation_cutoff'])
def test_run_cannot_claim_future_cutoffs(field):
    data = run(); data[field] = '2026-01-04'
    with pytest.raises(ValidationError): RunManifest.model_validate(data)


def test_snapshot_cannot_follow_run_finish():
    data = bundle(); data['datasets'][0]['snapshot_created_at'] = claimed('2026-01-04')
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)


def test_unknown_reasons_are_required_not_defaulted():
    for schema, data in [(TimeEvidence, unknown()), (ComponentEvidence, component(None))]:
        if schema is TimeEvidence:
            data['reason'] = None
        else:
            data['reasons'] = ()
        with pytest.raises(ValidationError): schema.model_validate(data)


def test_attestation_reference_closure():
    data = bundle()
    data['events'][0]['components']['A']['historical_available_at'].update(
        state='attested', value='2026-01-01T00:00:00Z', reason=None,
        authority='synthetic-authority', evidence_refs=('absent',))
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)


def test_registry_and_reference_order_is_canonical():
    data = bundle(); data['events'][0]['input_lineage'] = ('source', 'input-data')
    expected = canonical_bytes(EvidenceBundle.model_validate(data))
    data['run']['artifacts'] = tuple(reversed(data['run']['artifacts']))
    data['events'][0]['input_lineage'] = ('input-data', 'source')
    assert canonical_bytes(EvidenceBundle.model_validate(data)) == expected


def test_duplicate_reference_rejected():
    data = event(); data['input_lineage'] *= 2
    with pytest.raises(ValidationError): EventEvidence.model_validate(data)


def test_unknown_provenance_preserved_even_for_complete_scores():
    obj = EvidenceBundle.model_validate(bundle())
    assert obj.events[0].score_status == 'complete'
    assert obj.events[0].components['A'].historical_available_at.state == 'unknown'
    assert obj.run.model_timeline.available_at.state == 'unknown'
    # Numerically complete is deliberately not a historical eligibility verdict.


def test_matches_existing_complete_partial_and_insufficient_score_contract():
    from app.quant.insideredge_score import Component, ScoreInput, score_event
    for missing, reasons in [(None, ()), ('S', ('fewer_than_10_eligible_comparable_events',)),
                             ('S', ('randomization_failed',)), ('C', ('missing_identity',))]:
        raw = {k: Component(None, reasons) if k == missing else Component(50) for k in 'ACMSD'}
        actual = score_event(ScoreInput('SYN:2026-01-02', raw['A'], raw['C'], Component(.5), raw['S'], raw['D']))
        data = event()
        if missing:
            data['components'][missing] = component(None)
            data['components'][missing]['reasons'] = reasons
        for field in ('insider_edge_score','score_status','applied_weights','original_weight_total'):
            data[field] = actual[field]
        assert EventEvidence.model_validate(data).score_status == actual['score_status']


def test_schema_json_parser_rejects_duplicate_keys():
    payload = canonical_bytes(RunManifest.model_validate(run())).decode()
    payload = payload.replace('"run_id":"synthetic-run"', '"run_id":"wrong","run_id":"synthetic-run"')
    with pytest.raises(ValueError, match='duplicate'):
        RunManifest.model_validate_json(payload)


def test_unrepresentable_integer_score_has_controlled_validation_error():
    with pytest.raises(ValidationError):
        ComponentEvidence.model_validate(component(10**500))


def test_offset_times_are_normalized_before_cutoff_checks():
    data = run()
    # Same instant as 2026-01-03T00:00:00Z, not Jan 2 in archive UTC semantics.
    data['execution_finished_at'] = '2026-01-02T19:00:00-05:00'
    data['observation_cutoff'] = '2026-01-03'
    obj = RunManifest.model_validate(data)
    assert obj.execution_finished_at.date() == date(2026,1,3)


def test_nested_audit_preserves_typed_missingness_and_decimal():
    data = event()
    data['original_audit'] = {'original': {'kind':'nan','reason':'synthetic_nan'}, 'decimal':Decimal('0.12300')}
    obj = EventEvidence.model_validate(data)
    raw = parse_json(canonical_bytes(obj))['original_audit']
    assert raw == {'original':{'kind':'nan','reason':'synthetic_nan'}, 'decimal':Decimal('0.123')}
    data['original_audit']['original'] = float('nan')
    with pytest.raises(ValidationError): EventEvidence.model_validate(data)


@pytest.mark.parametrize('typed,ordinary', [
    (Decimal('1.2'), {'$decimal': '1.2'}),
    (Decimal('1.2'), {'$evidence/v1': ['decimal', '1.2']}),
    (datetime(2026, 1, 1, tzinfo=timezone.utc), '2026-01-01T00:00:00.000000Z'),
    (date(2026, 1, 1), '2026-01-01'),
])
def test_typed_audits_do_not_collide(typed, ordinary):
    assert canonical_bytes(typed) != canonical_bytes(ordinary)
    for value in (typed, ordinary):
        data = event(); data['original_audit'] = {'nested': [value, None, {'kind': 'nan'}]}
        before = deepcopy(data)
        obj = EventEvidence.model_validate(data)
        restored = EventEvidence.model_validate_json(canonical_bytes(obj))
        assert restored.original_audit == data['original_audit']
        assert data == before
    a = event(); b = event()
    a['original_audit'] = {'value': typed}; b['original_audit'] = {'value': ordinary}
    assert content_digest(EventEvidence.model_validate(a)) != content_digest(EventEvidence.model_validate(b))


@pytest.mark.parametrize('tag', [[], ['decimal'], ['unknown', 'x'], ['decimal', 'NaN'],
    ['decimal', '1.20'], ['datetime', '2026-01-01'], ['mapping', {}], ['date', 1]])
def test_malformed_typed_tags_rejected(tag):
    import json
    with pytest.raises(ValueError): parse_json(json.dumps({'$evidence/v1': tag}))


@pytest.mark.parametrize('state', ['claimed', 'attested'])
@pytest.mark.parametrize('target', ['component_source', 'dataset_source', 'historical'])
def test_direct_chronology_with_unknown_intermediates(state, target):
    data = bundle(); future = claimed('2026-01-04')
    if state == 'attested':
        future.update(state=state, authority='synthetic-authority', evidence_refs=('source',))
    if target == 'component_source':
        data['events'][0]['components']['A'].update(computed_at=unknown(), source_available_at=future)
    elif target == 'dataset_source':
        data['datasets'][0].update(snapshot_created_at=unknown(), source_available_at=future)
    else:
        earlier = claimed('2026-01-01')
        if state == 'attested': earlier.update(state=state, authority='synthetic-authority', evidence_refs=('source',))
        data['events'][0]['components']['A'].update(computed_at=unknown(),
            source_available_at=claimed('2026-01-02'), historical_available_at=earlier)
    with pytest.raises(ValidationError): EvidenceBundle.model_validate(data)


@pytest.mark.parametrize('path', ['CON', 'nul.json', 'a/COM1.txt', 'LPT9', 'a/file.', 'a/file '])
def test_portable_paths_reject_windows_aliases(path):
    data = artifact('x'); data['path'] = path
    with pytest.raises(ValidationError): ArtifactReference.model_validate(data)


def test_case_insensitive_path_aliases_rejected():
    data = run(); items = list(data['artifacts'])
    items[1]['path'] = items[0]['path'].upper(); data['artifacts'] = tuple(items)
    with pytest.raises(ValidationError): RunManifest.model_validate(data)


def test_resource_boundaries():
    from app.quant.evidence.serialization import MAX_DEPTH, MAX_NODES, MAX_BYTES, MAX_DECIMAL_DIGITS
    value = None
    for _ in range(MAX_DEPTH): value = [value]
    assert parse_json(canonical_bytes(value)) == value
    with pytest.raises(ValueError): canonical_bytes([value])
    assert canonical_bytes([None] * (MAX_NODES - 1))
    with pytest.raises(ValueError): canonical_bytes([None] * MAX_NODES)
    assert canonical_bytes(Decimal('1e' + str(MAX_DECIMAL_DIGITS - 1)))
    with pytest.raises(ValueError): canonical_bytes(Decimal('1e' + str(MAX_DECIMAL_DIGITS)))
    assert len(canonical_bytes('x' * (MAX_BYTES - 3))) == MAX_BYTES
    with pytest.raises(ValueError): canonical_bytes('x' * (MAX_BYTES - 2))
    with pytest.raises(ValueError): parse_json(' ' * (MAX_BYTES + 1))
    with pytest.raises(ValueError): parse_json('[' * 2000 + '0' + ']' * 2000)


@pytest.mark.parametrize('missing', [('C', 'S'), ('M',)])
def test_multiple_missing_and_probability_absence(missing):
    data = event()
    for name in missing: data['components'][name] = component(None)
    if 'M' in missing: data['model_probability'] = None
    data.update(score_status='insufficient_data', insider_edge_score=None,
                applied_weights={}, original_weight_total=None)
    assert EventEvidence.model_validate(data).insider_edge_score is None
    if 'M' in missing:
        data['model_probability'] = .5
        with pytest.raises(ValidationError): EventEvidence.model_validate(data)


@pytest.mark.parametrize('value', [0, 100])
@pytest.mark.parametrize('partial', [False, True])
def test_composite_boundaries(value, partial):
    data = event(); data['components'] = {k: component(value) for k in 'ACMSD'}
    data.update(model_probability=value / 100, insider_edge_score=value)
    if partial:
        data['components']['S'] = component(None)
        data['components']['S']['reasons'] = ('fewer_than_10_eligible_comparable_events',)
        data.update(score_status='partial', original_weight_total=.85,
                    applied_weights={k: w / .85 for k, w in dict(A=.25,C=.15,M=.30,D=.15).items()})
    assert EventEvidence.model_validate(data).insider_edge_score == value


def test_required_dataset_source_bounds_component_history():
    data = bundle()
    data['datasets'][0]['source_available_at'] = claimed('2026-01-02')
    data['datasets'][0]['snapshot_created_at'] = unknown()
    c = data['events'][0]['components']['A']
    c.update(source_available_at=unknown(), computed_at=unknown(), historical_available_at=claimed())
    with pytest.raises(ValidationError, match='chronology'): EvidenceBundle.model_validate(data)


def test_nested_missingness_and_reserved_mapping_roundtrip():
    value = {'null': None, 'missing': [{'kind': kind, 'reason': 'synthetic'} for kind in
             ('nan', 'positive_infinity', 'negative_infinity', 'not_supplied')],
             '$evidence/v1': {'$evidence/v1': ['unknown', 'ordinary']}}
    before = deepcopy(value)
    assert parse_json(canonical_bytes(value)) == before
    assert canonical_bytes(parse_json(canonical_bytes(value))) == canonical_bytes(value)
    assert value == before


@pytest.mark.parametrize('prerequisite', ['training_cutoff', 'validation_outcome_end',
                                         'selected_at', 'frozen_at'])
@pytest.mark.parametrize('states', [('claimed', 'claimed'), ('attested', 'attested'),
                                   ('claimed', 'attested'), ('attested', 'claimed')])
def test_model_availability_cannot_precede_known_prerequisite(prerequisite, states):
    data = run()
    for field, day, state in [(prerequisite, '2026-01-02', states[0]),
                              ('available_at', '2026-01-01', states[1])]:
        time = claimed(day)
        if state == 'attested':
            time.update(state=state, authority='synthetic-authority', evidence_refs=('source',))
        data['model_timeline'][field] = time
    # All other fields, including intervening timestamps, remain explicitly unknown.
    with pytest.raises(ValidationError, match='contradictory chronology'):
        RunManifest.model_validate(data)


def test_complete_model_chronology_preserves_distinct_availability_and_activation():
    data = run()
    data['execution_finished_at'] = '2026-01-10T00:00:00Z'
    for field, day in [('training_cutoff', '2026-01-01'),
                       ('validation_outcome_end', '2026-01-02'),
                       ('selected_at', '2026-01-03'), ('frozen_at', '2026-01-04'),
                       ('available_at', '2026-01-05'), ('activated_at', '2026-01-06')]:
        data['model_timeline'][field] = claimed(day)
    model = RunManifest.model_validate(data)
    assert model.model_timeline.available_at.value.date() == date(2026, 1, 5)
    assert model.model_timeline.activated_at.value.date() == date(2026, 1, 6)
    # Independent availability evidence can also be recorded after local activation.
    data['model_timeline']['available_at'] = claimed('2026-01-07')
    assert RunManifest.model_validate(data).model_timeline.available_at.value.date() == date(2026, 1, 7)


def test_valid_sparse_model_chronology_and_unknown_availability():
    data = run()
    data['model_timeline']['training_cutoff'] = claimed('2026-01-01')
    data['model_timeline']['available_at'] = claimed('2026-01-02')
    obj = RunManifest.model_validate(data)
    assert obj.model_timeline.frozen_at.value is None
    assert obj.model_timeline.selected_at.state == 'unknown'
    data['model_timeline']['available_at'] = unknown()
    obj = RunManifest.model_validate(data)
    assert obj.model_timeline.available_at.value is None
    assert obj.model_timeline.available_at.reason == 'synthetic_not_supplied'


@pytest.mark.parametrize('prerequisite', ['training_cutoff', 'validation_outcome_end', 'selected_at'])
def test_activation_still_cannot_precede_known_prerequisite(prerequisite):
    data = run()
    data['model_timeline'][prerequisite] = claimed('2026-01-02')
    data['model_timeline']['activated_at'] = claimed('2026-01-01')
    with pytest.raises(ValidationError, match='contradictory chronology'):
        RunManifest.model_validate(data)


def test_versioned_typed_encoding_known_bytes():
    value = {'decimal': Decimal('1.20'), 'timestamp': datetime(2026, 1, 1, tzinfo=timezone.utc),
             'literal': {'$evidence/v1': ['decimal', '1.2']}}
    expected = (b'{"decimal":{"$evidence/v1":["decimal","1.2"]},'
                b'"literal":{"$evidence/v1":["mapping",{"$evidence/v1":["decimal","1.2"]}]},'
                b'"timestamp":{"$evidence/v1":["datetime","2026-01-01T00:00:00.000000Z"]}}\n')
    assert canonical_bytes(value) == expected
    assert parse_json(expected) == value
    assert content_digest(value) == hashlib.sha256(expected).hexdigest()
