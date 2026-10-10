"""Read-only structural and byte verification of Stage 1 EvidenceBundle archives.

verify_bundle(root, manifest_path='bundle.json') consumes the existing bundle
schema, not a publication receipt or a new archive envelope. Inline run/input/
event manifests are authoritative. Registered artifacts with known Stage 1
schema IDs are also parsed, checked for canonical bytes, and matched to their
inline counterpart. IDs in run.input_manifests must retain canonical input/v1
manifests with matching dataset IDs, not opaque substitutes. Other payload
schemas are opaque: only their bytes are
verified, never deserialized (in particular, models are never loaded). JSONL
layouts, external object stores and trust receipts are outside this API.

The explicit root is caller-selected. Its final component and all paths beneath
it must be nonsymlink directories/regular files. Descriptor-relative O_NOFOLLOW
opens pin parents and prevent symlink substitution. Hard links are rejected.
Before/after file metadata checks detect ordinary concurrent mutation, but this
is not a filesystem snapshot or protection against a privileged adversary.
Callers should supply a quiescent archive. Unregistered files are not traversed
or endorsed. Matching hashes do NOT establish authenticity or historical time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import errno
import hashlib
import os
from pathlib import Path
import stat
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from .schemas import DatasetManifest, EventEvidence, EvidenceBundle, RunManifest, SafePath
from .serialization import MAX_BYTES, canonical_bytes

Status = Literal['valid', 'invalid', 'unverifiable']
SCHEMAS = {
    'scoring-evidence/bundle/v1': EvidenceBundle,
    'scoring-evidence/run/v1': RunManifest,
    'scoring-evidence/input/v1': DatasetManifest,
    'scoring-evidence/event/v1': EventEvidence,
}


@dataclass(frozen=True)
class Finding:
    code: str
    status: Literal['invalid', 'unverifiable']
    message: str
    artifact_id: str | None = None
    path: str | None = None


@dataclass(frozen=True)
class VerificationReport:
    """Independent statuses for structure and bytes; invalid dominates unavailable.

    artifacts_checked counts successfully verified registered files, excluding
    the root manifest. manifest_sha256 binds the bytes read, not a trusted root.
    Findings contain only supplied bounded IDs/relative paths and fixed messages.
    """
    status: Status
    structural_status: Status
    byte_integrity_status: Status
    artifacts_checked: int
    manifest_sha256: str | None
    findings: tuple[Finding, ...]
    scope: tuple[str, ...] = ('structural_validity', 'byte_integrity')
    authenticated_publication: str = 'not_evaluated'
    historical_eligibility: str = 'not_evaluated'

    def to_dict(self) -> dict:
        """JSON-compatible report; no raw evidence, host paths or OS messages."""
        result = asdict(self)
        result['findings'] = [asdict(finding) for finding in self.findings]
        result['scope'] = list(self.scope)
        return result


class _Failure(Exception):
    def __init__(self, code: str, message: str, status: Status = 'invalid'):
        self.code, self.message, self.status = code, message, status


def _os_failure(error: OSError) -> _Failure:
    if error.errno in (errno.EACCES, errno.EPERM):
        return _Failure('access_unavailable', 'Required archive bytes are not readable.', 'unverifiable')
    if error.errno == errno.ENOENT:
        return _Failure('missing_file', 'A required archive path is missing.')
    if error.errno in (errno.ELOOP, errno.ENOTDIR, errno.ENXIO, errno.ENODEV):
        return _Failure('unsafe_file_type', 'A required path is a symlink or unexpected file type.')
    return _Failure('io_unavailable', 'Required archive bytes could not be read.', 'unverifiable')


def _open_file(root_fd: int, path: str) -> int:
    parent = os.dup(root_fd)
    try:
        parts = path.split('/')
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise _Failure('unsafe_file_type', 'Only regular, non-hard-linked artifact files are supported.')
        except BaseException:
            os.close(fd)
            raise
        return fd
    finally:
        os.close(parent)


def _read_file(root_fd: int, path: str, limit: int, identities: set,
               *, collect: bool, expected_size: int | None = None) -> tuple[bytes, str]:
    fd = _open_file(root_fd, path)
    try:
        before = os.fstat(fd)
        identity = (before.st_dev, before.st_ino)
        if identity in identities:
            raise _Failure('aliased_file', 'Multiple references resolve to the same file.')
        identities.add(identity)
        if before.st_size > limit:
            raise _Failure('size_limit', 'File exceeds the configured verification size bound.')
        if expected_size is not None and before.st_size != expected_size:
            raise _Failure('size_mismatch', 'Retained byte count differs from the declared count.')
        digest = hashlib.sha256()
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, min(64 * 1024, limit - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise _Failure('size_limit', 'File exceeds the configured verification size bound.')
            digest.update(chunk)
            if collect:
                chunks.append(chunk)
        after = os.fstat(fd)
        def signature(info):
            return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if signature(before) != signature(after) or total != before.st_size:
            raise _Failure('file_changed', 'File changed while it was being verified.', 'unverifiable')
        return b''.join(chunks), digest.hexdigest()
    finally:
        os.close(fd)


def _manifest(data: bytes, schema):
    try:
        model = schema.model_validate_json(data)
        if canonical_bytes(model) != data:
            raise _Failure('noncanonical_manifest', 'Manifest bytes are not the Stage 1 canonical encoding.')
        return model
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise _Failure('invalid_manifest', 'Manifest schema, JSON, typed encoding or chronology is invalid.') from None


def _matches_inline(model, bundle: EvidenceBundle, artifact_id: str) -> bool:
    if isinstance(model, EvidenceBundle):
        return canonical_bytes(model) == canonical_bytes(bundle)
    if isinstance(model, RunManifest):
        return canonical_bytes(model) == canonical_bytes(bundle.run)
    if isinstance(model, DatasetManifest):
        return model.dataset_id == artifact_id and any(canonical_bytes(model) == canonical_bytes(item) for item in bundle.datasets)
    return any(canonical_bytes(model) == canonical_bytes(item) for item in bundle.events)


def verify_bundle(archive_root: str | Path, manifest_path: str = 'bundle.json', *,
                  max_artifact_bytes: int = 1_000_000_000,
                  max_total_bytes: int = 4_000_000_000) -> VerificationReport:
    """Verify a caller-selected archive without writes, network or model loading.

    Manifests are bounded by Stage 1 MAX_BYTES; opaque files use chunked hashing.
    Binary/total bounds are configurable operational limits, not model thresholds.
    Exceeding these yields unverifiable; malformed/oversized manifests are invalid.
    Definite failure takes precedence over unavailable checks. Neither a valid
    result nor its locally calculated root digest authenticates the archive.
    """
    for bound in (max_artifact_bytes, max_total_bytes):
        if type(bound) is not int or bound <= 0:
            raise ValueError('verification byte limits must be positive integers')
    findings: list[Finding] = []
    structural: Status = 'unverifiable'
    integrity: Status = 'unverifiable'
    checked = 0
    root_digest = None
    root_fd = None
    identities: set = set()
    try:
        try:
            TypeAdapter(SafePath).validate_python(manifest_path)
        except ValidationError:
            raise _Failure('unsafe_manifest_path', 'Manifest path must be a portable relative path.') from None
        if not all(hasattr(os, flag) for flag in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_NONBLOCK')) or os.open not in os.supports_dir_fd:
            raise _Failure('unsupported_filesystem', 'Safe descriptor-relative reads are unavailable.', 'unverifiable')
        root_fd = os.open(archive_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        data, root_digest = _read_file(root_fd, manifest_path, MAX_BYTES, identities, collect=True)
        bundle = _manifest(data, EvidenceBundle)
        structural = 'valid'
        integrity = 'valid'
        total = len(data)
        if total > max_total_bytes:
            raise _Failure('artifact_budget', 'Manifest bytes exceed the total verification limit.', 'unverifiable')
        def aggregate(left: Status, right: Status) -> Status:
            return max((left, right), key={'valid': 0, 'unverifiable': 1, 'invalid': 2}.__getitem__)

        for artifact in bundle.run.artifacts:
            schema = SCHEMAS.get(artifact.schema_version)
            requires_structure = schema is not None or artifact.schema_version.startswith('scoring-evidence/')
            artifact_structure: Status = 'valid'
            artifact_bytes: Status = 'unverifiable'

            def record(failure):
                findings.append(Finding(failure.code, failure.status, failure.message, artifact.artifact_id, artifact.path))

            if artifact.artifact_id in bundle.run.input_manifests and artifact.schema_version != 'scoring-evidence/input/v1':
                artifact_structure = 'invalid'
                record(_Failure('manifest_type_mismatch', 'Required input manifest reference must declare the input/v1 schema.'))
            elif artifact.schema_version.startswith('scoring-evidence/') and schema is None:
                artifact_structure = 'invalid'
                record(_Failure('unsupported_schema', 'Referenced evidence schema version is unsupported.'))
            try:
                if artifact.path.casefold() == manifest_path.casefold():
                    raise _Failure('manifest_alias', 'Artifact cannot also be the top-level manifest.')
                limit = min(MAX_BYTES, max_artifact_bytes) if schema else max_artifact_bytes
                if artifact.byte_count > limit or total + artifact.byte_count > max_total_bytes:
                    raise _Failure('artifact_budget', 'Declared artifact bytes exceed verification limits.', 'unverifiable')
                total += artifact.byte_count
                retained, digest = _read_file(root_fd, artifact.path, limit, identities,
                                               collect=schema is not None, expected_size=artifact.byte_count)
                artifact_bytes = 'valid'
                if digest != artifact.sha256:
                    artifact_bytes = 'invalid'
                    record(_Failure('digest_mismatch', 'Retained SHA-256 differs from the declared digest.'))
            except (OSError, _Failure) as error:
                failure = _os_failure(error) if isinstance(error, OSError) else error
                record(failure)
                artifact_bytes = failure.status
                if requires_structure and artifact_structure != 'invalid':
                    artifact_structure = 'unverifiable'
            else:
                # Structure and byte agreement are independent: inspect readable
                # manifests even when their declared digest is incorrect.
                if schema:
                    try:
                        model = _manifest(retained, schema)
                        if not _matches_inline(model, bundle, artifact.artifact_id):
                            raise _Failure('manifest_conflict', 'Referenced manifest conflicts with the inline bundle manifests.')
                    except _Failure as failure:
                        record(failure)
                        artifact_structure = 'invalid'
            structural = aggregate(structural, artifact_structure)
            integrity = aggregate(integrity, artifact_bytes)
            if artifact_structure == artifact_bytes == 'valid':
                checked += 1
    except (OSError, _Failure) as error:
        failure = _os_failure(error) if isinstance(error, OSError) else error
        findings.append(Finding(failure.code, failure.status, failure.message))
        structural = failure.status
        integrity = 'unverifiable'
    finally:
        if root_fd is not None:
            os.close(root_fd)
    findings.sort(key=lambda item: (item.artifact_id or '', item.path or '', item.code))
    status: Status = 'invalid' if any(item.status == 'invalid' for item in findings) else ('unverifiable' if findings else 'valid')
    return VerificationReport(status, structural, integrity, checked, root_digest, tuple(findings))
