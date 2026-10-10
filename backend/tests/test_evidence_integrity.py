"""Synthetic local archives only; no services or real historical evidence."""
from copy import deepcopy
import hashlib
import json
import os

import pytest

from app.quant.evidence import EvidenceBundle, canonical_bytes
from app.quant.evidence.verify import verify_bundle
from test_evidence_schemas import bundle, DatasetManifest, EventEvidence


def save(root, data):
    (root / 'bundle.json').write_bytes(canonical_bytes(EvidenceBundle.model_validate(data)))


@pytest.fixture
def archive(tmp_path):
    data = bundle()
    refs = {a['artifact_id']: a for a in data['run']['artifacts']}
    for ref in refs.values():
        raw = b'synthetic opaque bytes\x00\xff\n'
        path = tmp_path / ref['path']; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        ref.update(sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw))
    data['datasets'][0]['content'] = deepcopy(refs['input-data'])
    for identity, schema, model in [('dataset', 'scoring-evidence/input/v1',
                                   DatasetManifest.model_validate(data['datasets'][0])),
                                  ('output', 'scoring-evidence/event/v1',
                                   EventEvidence.model_validate(data['events'][0]))]:
        raw = canonical_bytes(model); ref = refs[identity]
        (tmp_path / ref['path']).write_bytes(raw)
        ref.update(schema_version=schema, sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw))
    save(tmp_path, data)
    return tmp_path, data


def codes(report):
    return [item.code for item in report.findings]


def test_valid_archive_is_integrity_only_and_read_only(archive):
    root, _ = archive
    before = {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    result = verify_bundle(root)
    assert result.status == result.structural_status == result.byte_integrity_status == 'valid'
    assert result.artifacts_checked == 14
    assert result.manifest_sha256 == hashlib.sha256((root / 'bundle.json').read_bytes()).hexdigest()
    assert result.authenticated_publication == result.historical_eligibility == 'not_evaluated'
    assert result.findings == ()
    assert json.loads(json.dumps(result.to_dict()))['status'] == 'valid'
    assert result == verify_bundle(root)
    after = {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    assert before == after


@pytest.mark.parametrize('change,expected', [('corrupt','digest_mismatch'), ('digest','digest_mismatch'),
                                           ('missing','missing_file'), ('size','size_mismatch')])
def test_artifact_failures(archive, change, expected):
    root, data = archive
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'model')
    path = root / ref['path']
    if change == 'corrupt': path.write_bytes(b'X' * ref['byte_count'])
    elif change == 'digest': ref['sha256'] = '0' * 64; save(root, data)
    elif change == 'missing': path.unlink()
    else: path.write_bytes(b'short')
    report = verify_bundle(root)
    assert report.status == 'invalid' and expected in codes(report)
    assert report.findings[0].artifact_id == 'model'
    assert str(root) not in json.dumps(report.to_dict())


@pytest.mark.parametrize('raw', [b'{', b'{"schema_version":1,"schema_version":2}',
    b'{"$evidence/v1":["unknown","x"]}', b'{"schema_version":"scoring-evidence/bundle/v99"}'])
def test_malformed_root_manifest(archive, raw):
    root, _ = archive; (root / 'bundle.json').write_bytes(raw)
    report = verify_bundle(root)
    assert report.status == 'invalid' and codes(report) == ['invalid_manifest']
    assert report.artifacts_checked == 0


@pytest.mark.parametrize('change', ['spaces','missing_newline','extra_newline','bom'])
def test_noncanonical_manifest(archive, change):
    root, _ = archive; p = root / 'bundle.json'; raw=p.read_bytes()
    if change == 'spaces': raw=json.dumps(json.loads(raw), indent=2).encode()+b'\n'
    elif change == 'missing_newline': raw=raw[:-1]
    elif change == 'extra_newline': raw+=b'\n'
    else: raw=b'\xef\xbb\xbf'+raw
    p.write_bytes(raw)
    assert codes(verify_bundle(root))[0] in ('noncanonical_manifest','invalid_manifest')


@pytest.mark.parametrize('kind', ['duplicate_id','case_alias','unclosed','traversal'])
def test_conflicting_or_unsafe_references(archive, kind):
    root, data = archive
    if kind == 'duplicate_id': data['run']['artifacts'] += (deepcopy(data['run']['artifacts'][0]),)
    elif kind == 'case_alias': data['run']['artifacts'][1]['path'] = data['run']['artifacts'][0]['path'].upper()
    elif kind == 'unclosed': data['events'][0]['event_input'] = 'unregistered'
    else: data['run']['artifacts'][0]['path'] = '../outside'
    (root / 'bundle.json').write_bytes(canonical_bytes(data))
    assert codes(verify_bundle(root)) == ['invalid_manifest']


@pytest.mark.parametrize('path', ['../outside','/outside','C:/outside',r'\\host\share','a/../bundle.json','NUL.json'])
def test_unsafe_requested_manifest_path(archive, path):
    assert codes(verify_bundle(archive[0], path)) == ['unsafe_manifest_path']


@pytest.mark.parametrize('kind', ['outside_symlink','inside_symlink','directory','fifo','hardlink'])
def test_unexpected_artifact_types(archive, kind):
    root, data = archive
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'model')
    path=root / ref['path']; raw=path.read_bytes();path.unlink()
    target=root / 'unregistered'; target.write_bytes(raw)
    if kind == 'outside_symlink': path.symlink_to('/dev/null')
    elif kind == 'inside_symlink': path.symlink_to(target)
    elif kind == 'directory': path.mkdir()
    elif kind == 'fifo': os.mkfifo(path)
    else: os.link(target,path)
    report=verify_bundle(root)
    assert report.status == 'invalid' and 'unsafe_file_type' in codes(report)


def test_symlink_directory_cannot_be_followed(archive):
    root, _ = archive
    (root / 'objects').rename(root / 'retained')
    (root / 'objects').symlink_to(root / 'retained', target_is_directory=True)
    report=verify_bundle(root)
    assert report.status == 'invalid' and report.artifacts_checked == 0


def test_symlink_root_rejected(archive, tmp_path_factory):
    link=tmp_path_factory.mktemp('links') / 'root'; link.symlink_to(archive[0], target_is_directory=True)
    assert verify_bundle(link).status == 'invalid'


def test_oversized_root_manifest(archive):
    from app.quant.evidence.serialization import MAX_BYTES
    root, _ = archive
    (root / 'bundle.json').write_bytes(b' ' * (MAX_BYTES+1))
    assert codes(verify_bundle(root)) == ['size_limit']


def test_operational_artifact_budget_is_unverifiable(archive):
    report=verify_bundle(archive[0], max_artifact_bytes=1)
    assert report.status == report.byte_integrity_status == 'unverifiable'
    assert report.structural_status == 'unverifiable' and set(codes(report)) == {'artifact_budget'}


def test_total_budget_is_unverifiable(archive):
    assert verify_bundle(archive[0],max_total_bytes=1).status == 'unverifiable'


@pytest.mark.parametrize('kind', ['conflict','noncanonical','unsupported','malformed'])
def test_referenced_manifest_validation(archive,kind):
    root,data=archive
    ref=next(a for a in data['run']['artifacts'] if a['artifact_id']=='output')
    model=deepcopy(data['events'][0])
    if kind=='conflict': model['original_audit']={'synthetic':'different'}
    raw=canonical_bytes(EventEvidence.model_validate(model))
    if kind=='noncanonical': raw=raw.rstrip(b'\n')
    elif kind=='unsupported': ref['schema_version']='scoring-evidence/event/v99'
    elif kind=='malformed': raw=b'{"x":1,"x":2}'
    (root/ref['path']).write_bytes(raw)
    ref.update(sha256=hashlib.sha256(raw).hexdigest(),byte_count=len(raw));save(root,data)
    report=verify_bundle(root)
    assert report.status == report.structural_status == 'invalid'
    assert report.byte_integrity_status == 'valid'
    assert codes(report)==[{'conflict':'manifest_conflict','noncanonical':'noncanonical_manifest',
                           'unsupported':'unsupported_schema','malformed':'invalid_manifest'}[kind]]


def test_report_order_is_deterministic(archive):
    root,data=archive
    for ref in data['run']['artifacts']:
        if ref['artifact_id'] in ('source','model'): (root/ref['path']).unlink()
    first=verify_bundle(root).to_dict()
    assert [x['artifact_id'] for x in first['findings']]==['model','source']
    assert first==verify_bundle(root).to_dict()


@pytest.mark.parametrize('value', [0,-1,True,1.5])
def test_invalid_configuration(archive,value):
    with pytest.raises(ValueError): verify_bundle(archive[0],max_artifact_bytes=value)


def test_no_model_deserialization(archive):
    import sys
    before=set(sys.modules)
    assert verify_bundle(archive[0]).status=='valid'
    assert not any(name.startswith(('sklearn','xgboost','sqlalchemy')) for name in set(sys.modules)-before)


def test_permission_failure_is_unverifiable_without_os_details(archive, monkeypatch):
    import errno
    from app.quant.evidence import verify
    original = verify._open_file
    def unavailable(root, path):
        if path.endswith('/model.json'):
            raise PermissionError(errno.EACCES, 'sensitive host detail')
        return original(root, path)
    monkeypatch.setattr(verify, '_open_file', unavailable)
    report = verify_bundle(archive[0])
    assert report.status == 'unverifiable'
    assert codes(report) == ['access_unavailable']
    assert 'sensitive' not in json.dumps(report.to_dict())


def test_platform_without_safe_opens_is_unverifiable(archive, monkeypatch):
    monkeypatch.setattr(os, 'supports_dir_fd', set())
    assert codes(verify_bundle(archive[0])) == ['unsupported_filesystem']
    assert verify_bundle(archive[0]).status == 'unverifiable'


def test_binary_hashing_uses_bounded_reads(archive, monkeypatch):
    from app.quant.evidence import verify
    root, data = archive
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'model')
    raw = b'\xff\x00' * 100_000
    (root / ref['path']).write_bytes(raw)
    ref.update(byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest()); save(root, data)
    sizes = []
    original = os.read
    def tracked(fd, amount):
        sizes.append(amount)
        return original(fd, amount)
    monkeypatch.setattr(verify.os, 'read', tracked)
    assert verify_bundle(root).status == 'valid'
    assert max(sizes) <= 64 * 1024
    assert sizes.count(64 * 1024) >= 3


def test_concurrent_change_is_not_reported_valid(archive, monkeypatch):
    from app.quant.evidence import verify
    root, data = archive
    path = root / next(a['path'] for a in data['run']['artifacts'] if a['artifact_id'] == 'model')
    original_open, original_read = verify._open_file, os.read
    target_fds = set()
    def opened(root_fd, relative):
        fd = original_open(root_fd, relative)
        if relative.endswith('/model.json'): target_fds.add(fd)
        return fd
    def changing(fd, amount):
        chunk = original_read(fd, amount)
        if fd in target_fds and chunk:
            info = path.stat()
            os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns + 1_000_000_000))
            target_fds.remove(fd)
        return chunk
    monkeypatch.setattr(verify, '_open_file', opened)
    monkeypatch.setattr(verify.os, 'read', changing)
    report = verify_bundle(root)
    assert report.status == 'unverifiable' and codes(report) == ['file_changed']


def test_manifest_cannot_be_registered_as_artifact(archive):
    root, data = archive
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'model')
    ref['path'] = 'bundle.json'; save(root, data)
    assert 'manifest_alias' in codes(verify_bundle(root))


def test_invalid_takes_precedence_over_unverifiable(archive, monkeypatch):
    import errno
    from app.quant.evidence import verify
    root, data = archive
    (root / next(a['path'] for a in data['run']['artifacts'] if a['artifact_id'] == 'source')).unlink()
    original = verify._open_file
    def unavailable(root_fd, path):
        if path.endswith('/model.json'): raise PermissionError(errno.EACCES, 'private')
        return original(root_fd, path)
    monkeypatch.setattr(verify, '_open_file', unavailable)
    report = verify_bundle(root)
    assert report.status == report.byte_integrity_status == 'invalid'
    assert codes(report) == ['access_unavailable', 'missing_file']


def test_input_manifest_cannot_be_hidden_as_opaque_payload(archive):
    root, data = archive
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'dataset')
    ref['schema_version'] = 'synthetic/opaque/v1'; save(root, data)
    result = verify_bundle(root)
    assert result.status == result.structural_status == 'invalid'
    assert codes(result) == ['manifest_type_mismatch']


def test_input_manifest_identity_must_match_its_reference(archive):
    root, data = archive
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'dataset')
    copy = deepcopy(data['datasets'][0]); copy['dataset_id'] = 'other-dataset'
    raw = canonical_bytes(DatasetManifest.model_validate(copy))
    (root / ref['path']).write_bytes(raw)
    ref.update(byte_count=len(raw), sha256=hashlib.sha256(raw).hexdigest()); save(root, data)
    assert codes(verify_bundle(root)) == ['manifest_conflict']


def test_unread_retained_manifest_structure_is_not_claimed_valid(archive):
    root, data = archive
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'dataset')
    (root / ref['path']).unlink()
    result = verify_bundle(root)
    assert result.status == result.byte_integrity_status == 'invalid'
    assert result.structural_status == 'unverifiable'
    assert codes(result) == ['missing_file']


@pytest.mark.parametrize('left,right,equivalent', [(True, 1, False), (1, 1.0, False), ('decimal', 1, False), ('decimal-equal', 'decimal-equal', True), ('utc', 'utc', True)])
def test_nested_canonical_identity(archive, left, right, equivalent):
    from decimal import Decimal
    from datetime import datetime, timezone, timedelta
    if left == 'decimal': left = Decimal('1')
    elif left == 'decimal-equal': left, right = Decimal('1.200'), Decimal('1.2')
    elif left == 'utc':
        left = datetime(2020, 1, 1, tzinfo=timezone.utc)
        right = datetime(2019, 12, 31, 19, tzinfo=timezone(timedelta(hours=-5)))
    root, data = archive
    data['events'][0]['original_audit'] = {'nested': [{'value': left}]}
    other = deepcopy(data['events'][0])
    other['original_audit']['nested'][0]['value'] = right
    before = deepcopy(other)
    raw = canonical_bytes(EventEvidence.model_validate(other))
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'output')
    (root / ref['path']).write_bytes(raw)
    ref.update(sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw))
    save(root, data)
    snapshot = deepcopy(data)
    report = verify_bundle(root)
    assert report.byte_integrity_status == 'valid'
    assert report.structural_status == report.status == ('valid' if equivalent else 'invalid')
    assert codes(report) == ([] if equivalent else ['manifest_conflict'])
    assert other == before and data == snapshot


@pytest.mark.parametrize('structure,byte', [(True, False), (False, True), (True, True)])
def test_independent_scope_aggregation(archive, structure, byte):
    root, data = archive
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'output')
    other = deepcopy(data['events'][0])
    if structure: other['original_audit'] = {'different': True}
    raw = canonical_bytes(EventEvidence.model_validate(other))
    (root / ref['path']).write_bytes(raw)
    ref.update(sha256='0' * 64 if byte else hashlib.sha256(raw).hexdigest(), byte_count=len(raw))
    save(root, data)
    report = verify_bundle(root)
    assert report.status == 'invalid'
    assert report.structural_status == ('invalid' if structure else 'valid')
    assert report.byte_integrity_status == ('invalid' if byte else 'valid')
    assert set(codes(report)) == ({'manifest_conflict'} if structure else set()) | ({'digest_mismatch'} if byte else set())


def test_structural_invalid_dominates_missing_manifest(archive):
    root, data = archive
    ref = next(a for a in data['run']['artifacts'] if a['artifact_id'] == 'output')
    ref['schema_version'] = 'scoring-evidence/event/v99'
    (root / ref['path']).unlink(); save(root, data)
    report = verify_bundle(root)
    assert report.status == report.structural_status == report.byte_integrity_status == 'invalid'
    assert set(codes(report)) == {'unsupported_schema', 'missing_file'}


@pytest.mark.parametrize('identity,structural', [('model', 'valid'), ('dataset', 'unverifiable')])
def test_unreadable_scope_statuses(archive, monkeypatch, identity, structural):
    import errno
    from app.quant.evidence import verify
    root, data = archive
    path = next(a['path'] for a in data['run']['artifacts'] if a['artifact_id'] == identity)
    original = verify._open_file
    def unreadable(root_fd, relative):
        if relative == path:
            raise PermissionError(errno.EACCES, 'not included in report')
        return original(root_fd, relative)
    monkeypatch.setattr(verify, '_open_file', unreadable)
    report = verify_bundle(root)
    assert report.structural_status == structural
    assert report.status == report.byte_integrity_status == 'unverifiable'
    assert codes(report) == ['access_unavailable']
