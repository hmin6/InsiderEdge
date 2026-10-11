# Pure scoring evidence capture preparation

## Scope

`backend/app/quant/evidence/capture.py` is an offline preparation library supporting
Issue #81. It does not resolve missing historical evidence or scoring coverage.
It does not execute scoring, inference or training, access a database/network,
read/write files, publish artifacts or emit transaction receipts. Existing scoring
and persistence callers remain unchanged. No dependency is added.

A = anomaly, C = activity/cluster, M = probability times 100, S = statistical
evidence, D = market dislocation. Existing complete, S-history-only partial and
insufficient-data policies remain enforced by Stage 1 EventEvidence validation.
Preparation does not introduce C-only partial scoring or imputation.

## Public interface and explicit ownership

Call `prepare_capture` with keyword-only arguments:

| Argument | Required evidence |
| --- | --- |
| `run_context` | Mapping containing all RunManifest fields except `artifacts`; explicit run ID, execution times, cutoffs, code/environment/model/policy/lineage references and limitations |
| `artifact_specs` | Sequence of ArtifactSpec: artifact ID, portable path, schema version, explicit TimeEvidence creation state, optional row count |
| `pinned_artifacts` | Sequence of PinnedArtifact: unique artifact ID and exact immutable bytes for every opaque registry entry |
| `datasets` | Validated Stage 1 DatasetManifest objects; their content references must already match the supplied pinned bytes |
| `events` | Validated Stage 1 EventEvidence objects containing explicit identities, chronology, normalized component evidence, model/preprocessing references, ranking membership and original audit |
| `event_artifact_ids` | Exact event-ID to generated event-artifact-ID mapping, matching run outputs |
| `original_component_outputs` | Event-keyed original record mappings, matching each batch audit's `components` |
| `signal_batch` | Structural interface with `payloads` and `audit`, compatible with SignalBatch; no service import or execution required |

The caller owns snapshot selection and source attestation. Supply the exact
consumed input bytes, never a later database re-query. This library cannot establish
that supplied bytes actually produced the supplied scores or that no sources were
omitted. Opaque model bytes are neither produced nor loaded here.

The module generates canonical dataset and event manifests. Dataset artifact IDs
are the dataset IDs. Event artifact IDs are explicitly supplied. All remaining
registry entries require pinned bytes; generated IDs cannot also be pinned. The
registry's hashes and byte counts are computed from these exact bytes, not copied
from unverified declarations. Dataset content declarations must agree with the
computed registry; inconsistencies are rejected rather than repaired.

Run model/policy slots and event model/preprocessing slots are the existing Stage 1
reference types, not a parallel model format. Known references must close over the
registry. Missing model/preprocessing references cannot accompany available M.

## Output and artifact layout

PreparedCapture contains:

- `manifest_path` (default `bundle.json`), immutable canonical envelope bytes and
  their SHA-256 digest;
- a sorted tuple of PreparedArtifact entries, with Stage 1 ArtifactReference and
  immutable content bytes;
- `bundle`, a fresh validated EvidenceBundle reconstructed on each access.

Nested bundle dictionaries are mutable only in that returned defensive copy.
Changing caller inputs or a returned bundle does not change prepared bytes. The
module does not keep a live reference to caller-owned mutable audit data.

Paths are explicitly supplied and validated; the root manifest cannot alias a
registered artifact. There is no implied filesystem publication layout beyond
these paths. The archive consists of one canonical bundle envelope, generated
canonical input/event manifests, and the supplied opaque artifacts. No JSONL or
publication-receipt format is introduced.

Each captured event's original_audit contains four separately named records:
`event_audit`, `signal_payload`, `signal_audit`, and `original_component_outputs`.
This retains the caller's original event audit without replacing it with serving
metadata. Entire payloads and audits are preserved, including additional fields.

## Original values and validation

Stage 1 canonical encoding preserves Boolean/integer/float/Decimal/date/aware
datetime distinctions, nested values and ordinary reserved-key mappings. Decimal
trailing zeros and timezone-equivalent instants intentionally canonicalize alike.
Dictionary insertion order does not affect bytes; meaningful array order remains.
No presentation rounding occurs.

Original output records must explicitly supply score fields, availability statuses
and reasons. Available component outputs require `complete` and empty reasons;
unavailable outputs require a nonempty status and exactly matching supplied reasons.
No fallback missing reason is invented. Additional upstream metadata is retained;
this module does not independently validate every statistical diagnostic.

Payload identity, statuses, component values, probability, final score, missing
components and model metadata must agree with the score audit and event manifest.
Audit weights, denominator and missing reasons are checked. Numeric agreement uses
an absolute tolerance of 1e-12 after independently enforcing [0,100] score
bounds and [0,1] probability bounds; Stage 1 validates score arithmetic and probability
scaling. Numeric audit comparison allows schema-normalized int/float/Decimal values,
while archived original audit types remain distinct canonical evidence. Booleans
are not numerical score inputs. Model names/versions are checked against the batch
score audit; provenance linkage still depends on explicit caller references.

Every supplied `research_event_id`, `ticker`, `information_date`, and
`public_event_day` in A/C/M/S/D and event-study records must match EventEvidence,
as must supplied identity fields in payloads and score audits. Optional identities
may remain absent; they are never fabricated. Date comparisons preserve typed dates. This is a typed-record API, not an automatic DataFrame adapter.
Arbitrary pandas/NumPy objects, naive timestamps and bare nonfinite audit values are
not silently coerced. In particular, this API is not guaranteed to accept an
unadapted SignalBatch from every upstream DataFrame calculation.

### Missingness and unknown evidence

Supply Stage 1 RawMissingness records with original producer reasons to distinguish
null, NaN, positive/negative infinity, unavailable and not-supplied values. Normalized
component fields are finite or null. Bare NaN/Infinity in audit records fail Stage 1
canonical serialization. If an upstream representation needs normalization, the
caller must retain original bytes and provide an explicit, reviewed transformation
and missingness record; this module does not invent those records or erase values.

Unknown chronology uses existing TimeEvidence(state='unknown', value=None, reason,
evidence_refs=()). Unknown references use ReferenceSlot with null artifact ID and
a reason where Stage 1 permits it. Unknown values never become fabricated timestamps,
identity mappings, ranking populations or approval flags. Missing required schema
fields and known chronological contradictions fail.

## Limits and failures

Defaults: 16,000,000 bytes per prepared artifact and 64,000,000 bytes total, including
the root manifest. Canonical manifests retain Stage 1's 4,000,000-byte, depth-64,
100,000-node and Decimal-expansion limits. Caller byte limits must be positive
integers. Boundary equality is accepted. These are validation bounds, not strict
peak-memory guarantees; caller inputs and canonical intermediate objects already
occupy memory. No data is truncated.

Validation rejects duplicate IDs/paths, unsafe paths, missing/extra registry bytes,
conflicting pinned/generated IDs, unsupported canonical objects, mismatched event
sets, incomplete reference closure and contradictory supplied scoring evidence.
Malformed identifiers are validated before hashing or set construction and raise
ValueError, including unhashable identifier values. ValueError (including Pydantic
validation errors) reports failed contracts; errors
are not a publication or persistence receipt. Do not expose validation errors or
private audit contents in public logs without redaction.

## Verification and later publisher

Synthetic tests materialize prepared bytes in test-owned temporary directories and
invoke public `verify_bundle()`. Complete synthetic archives must pass structural
and byte verification. Authenticated publication and historical eligibility remain
`not_evaluated`. Passing these tests proves software interoperability, not historical
validity or an authorized production run.

A future separately approved nonproduction publisher can consume prepared paths
and bytes, stage them, re-read and verify the complete archive, and publish with
no-replace semantics. It must implement crash recovery, permissions, retention and
publication policy independently. PreparedCapture is not a signed receipt, durable
archive, database commit, or evidence that current mutable Signals existed earlier.
No production storage provider, model serializer or commit-reconciliation mechanism
is selected by this implementation.
