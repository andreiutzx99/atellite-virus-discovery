# M13 implementation execution plan

**Status:** planning only; M13 remains planned and is approved for the
synthetic/offline baseline, not implemented production behavior. This plan
does not authorize external callers, biological datasets, candidate searches,
or a DVG/satellite classifier.

**Contract boundary:** M13 is an M5-only descriptive dossier. It imports
validated ViReMa records, preserves caller/reference/run scope, and emits an
unresolved evidence matrix. It does not rerun M5, reparse native output,
normalize coordinates, merge events across callers, calculate agreement, or
issue DVG, satellite, interference, helper-dependence, or function claims
([M13 contract](../M13_CONTRACT_FREEZE.md), lines 1–22, 38–49, 181–189).

This document is an execution plan only. No production code, tests, CI,
contract, README, or roadmap file is changed by this plan.

## 1. Implementation boundary and runner

The stage should be registered as `m13_m5_evidence_matrix` and invoked only by
the existing allowlisted artifact-workflow runner:

```text
python -m satellite_discovery.artifact_workflow \
  --manifest <workflow.json> --output <output-directory>
```

There is no M13-specific CLI, external-caller invocation, arbitrary importer,
or dynamic module loader. Implementation requires additive M4 workflow
registration and additive artifact contracts; it must not change M5 scientific
behavior. The metadata-only execution-outcome prerequisite is defined in
section 12, the [M13 contract](../M13_CONTRACT_FREEZE.md), and the
[M13 readiness audit](M13_FINAL_IMPLEMENTATION_READINESS.md).

The input manifest is `m13-input-v1` with an opaque `candidate_id`, at least
one ordered `m5_runs` entry, and optional `hypotheses`. Each run carries the
M5 producer stage identity, producer run-manifest SHA-256, exact raw terminal
status, four artifact-state fields, and immutable artifact references. States
are `PRESENT`, `NOT_PRODUCED`, `UNAVAILABLE`, `NOT_APPLICABLE`, and `UNKNOWN`;
`PRESENT` has exactly one matching reference and non-present states have none.
Completed runs require parameters, summary, and evidence; completed zero runs
require valid empty evidence and exact `NO_DVG_EVIDENCE_DETECTED` accounting
([M13 contract](../M13_CONTRACT_FREEZE.md), lines 51–84).

## 2. New and additive implementation surface

### 2.1 New modules

Create the following modules during implementation:

- `satellite_discovery/m13_contracts.py`
  - Validate `m13-input-v1`, run references, artifact-state consistency,
    hypothesis rows, immutable paths/digests, candidate/run linkage, and
    accepted producer/type pairs.
  - Validate M13 output schemas and enums without imposing a second event
    taxonomy.
  - Reuse the existing M5 validator for source documents; do not duplicate or
    weaken M5 event validation.
  - Provide M13-local canonical JSON serialization if the existing general
    writer does not meet the frozen newline/order requirements.
- `satellite_discovery/m13_stage.py`
  - Implement the trusted `m13_m5_evidence_matrix` handler.
  - Resolve and verify the input manifest and M5 artifact references.
  - Copy validated M5 event objects unchanged, preserving native event-array
    order and adding only M13 source-row/run references.
  - Produce event index, optional hypothesis matrix, per-run summary, result
    bundle, output hashes, and scoped implementation identity.
  - Never invoke ViReMa, inspect an external executable, reparse
    `dvg_raw_output`, or consume M6–M12 evidence.

The exact module split is an implementation choice within the frozen schemas;
it must not become a reason to add an external dependency or a new public
entry point.

### 2.2 Additive shared-module changes

- `satellite_discovery/artifact_contracts.py`
  - Add contract registrations and validators for:
    `m13_input_manifest`, `m13_event_index`,
    `m13_hypothesis_matrix`, `m13_summary`, and `m13_result_bundle`.
  - Add M13-specific semantic versions and dispatch to
    `m13_contracts.py`.
  - Do not change existing M5 validators or the package-wide validator
    semantic version for an M13-only addition.
- `satellite_discovery/artifact_workflow.py`
  - Import and register `m13_m5_evidence_matrix` in the default allowlisted
    registry.
  - Declare its typed input/output contracts, configuration validation, and
    handler.
  - Add M13 output types to any report allowlist only if the existing
    workflow-report contract needs to consume them; do not broaden report
    inputs to arbitrary files.
- `tests/test_stage_cache_identity.py` (additive regression assertions only)
  - Verify M13 changes invalidate M13 identity only and do not change M5–M10
    identities.
- Do not change M5 event parsing, accepted event semantics, scientific status
  values, or output schemas. If stable failure codes require a narrow change at
  an M5 parser/adapter error boundary, it is metadata-only, must be reviewed as
  part of the shared handoff prerequisite, and must preserve successful M5
  cache identities. See the
  [handoff gap resolution](M13_HANDOFF_GAP_RESOLUTION.md).

`stage_registry.py` and `workflow_states.py` should not require semantic
changes. The existing registry supports typed dynamic inputs, handlers,
configuration validators, and output contracts; existing M1 lifecycle states
already cover complete, dependency-missing, failed, and interrupted execution
([implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md), lines 15–35,
73–105).

## 3. Accepted inputs and output artifacts

### 3.1 Accepted producer artifacts

Only these M5 ViReMa artifact types are accepted:

| Artifact type | Requirement | M13 treatment |
| --- | --- | --- |
| `dvg_parameters` | Required for a completed/imported run | Preserve caller, input/reference identity, settings, and provenance. |
| `dvg_evidence_summary` | Required for a completed/imported run | Preserve terminal status, event count, accounting, and caller scope. |
| `dvg_evidence` | Required for a completed run | Validate and copy the `events` array exactly, including order. |
| `dvg_raw_output` | Optional | Integrity/provenance reference only; never reparse it. |

The producer must be the validated M5 contract and its producer manifest.
M6-derived events, arbitrary caller tables, external caller output, and
copied literature labels must be rejected
([M13 contract](../M13_CONTRACT_FREEZE.md), lines 38–49).

### 3.2 Output artifact types

Register exactly these stage outputs:

| Artifact type | Required contents |
| --- | --- |
| `m13_event_index` | Candidate, M5 run reference, source row index, optional source event ID, and unchanged source event object. |
| `m13_hypothesis_matrix` | Supplied hypothesis ID/scope, evidence references, unresolved state, and reason; no invented hypotheses. |
| `m13_summary` | Per-run raw status, import state, completeness, counts, and explicit missing/unavailable branches. |
| `m13_result_bundle` | Input identity, producer references, M13 schema/semantic/implementation identity, output hashes, and provenance. |

Event identity is only
`(producer_run_manifest_sha256, dvg_evidence_sha256, source_row_index)`.
Similar coordinates in different runs remain separate observations. Existing
producer fields such as reference IDs, breakpoints, orientation, support,
raw-entry fields, and event type remain unchanged
([M13 contract](../M13_CONTRACT_FREEZE.md), lines 78–111).

## 4. Reusable M5 validation and provenance

M13 must call, rather than reproduce, the following M5 validation boundaries:

- `satellite_discovery.dvg_evidence.validate_evidence_document` validates
  schema, caller, status, bounded event arrays, coordinates, reference
  bounds, event fields, hashes, and status/event consistency
  (`satellite_discovery/dvg_evidence.py`, lines 211–289).
- `satellite_discovery.dvg_evidence.validate_summary` validates summary
  schema, caller, status, non-negative event count, and status/count
  consistency (`satellite_discovery/dvg_evidence.py`, lines 292–314).
- M5’s existing output validation rechecks native-output integrity,
  normalized event correspondence, summary/event-count agreement, caller,
  sample, parser, and parameter provenance. M13 consumes the resulting typed
  artifacts and does not rerun that adapter
  (`satellite_discovery/virema_adapter.py`, lines 522–602).
- `artifact_contracts.validate_artifact`,
  `describe_artifact`, and `verify_descriptor` should provide contract
  dispatch, regular-file/non-symlink checks, relative-path containment,
  SHA-256 verification, and producer descriptor handling.
- Existing workflow input resolution should verify completed producer
  manifests and output inventory rather than duplicating path or digest logic
  (`satellite_discovery/artifact_workflow.py`, lines 591–671).

The M5 implementation already records caller, caller version, parser version,
read/reference identity, raw output reference, event IDs, and settings
(`satellite_discovery/virema_adapter.py`, lines 339–387, 408–464). M13 must
retain these fields as source data and add only the frozen M13 envelope.

## 5. Serialization and cache identity

### 5.1 Deterministic serialization

Every M13 JSON output should be UTF-8, sorted by object keys, LF-terminated
with exactly one trailing newline, and free of NaN or infinite values.

- Sort run summaries by producer stage ID and producer run-manifest digest.
- Preserve each M5 event array in its native order.
- Sort hypothesis rows by `hypothesis_id`, then source reference.
- Do not sort, normalize, or rewrite source event objects.

The existing general JSON writer may not guarantee every M13 canonical
requirement; use a local M13 serializer or a narrowly scoped canonical helper.
Do not change shared serialization in a way that rewrites M1–M10 artifacts
([M13 contract](../M13_CONTRACT_FREEZE.md), lines 148–152).

### 5.2 Cache identity and isolation

M13 identity must bind:

- input-manifest digest and opaque candidate ID;
- every consumed M5 stage ID, producer run-manifest digest, raw status,
  artifact type/version/digest, and artifact-state value;
- hypothesis definitions and provenance;
- M13 schema/semantic version and consumed artifact-contract semantic
  identities;
- M13 implementation/source digest and output hashes.

It must exclude timestamps, host-specific absolute paths, and optional
external-tool versions. The existing stage cache key and verified-output
reuse machinery should remain the outer mechanism
([M13 contract](../M13_CONTRACT_FREEZE.md), lines 154–166).

Required isolation assertions:

1. Changing an M5 input digest, source status, event document, or supplied
   hypothesis changes only the M13 cache key.
2. Changing M13 schema, serializer, or implementation identity invalidates
   M13 reuse only.
3. M5 cache keys and M5 output bytes remain unchanged.
4. Repeated execution with identical inputs produces byte-identical outputs
   and verified reuse.
5. Mutating an inventoried output, source digest, or producer manifest rejects
   reuse rather than producing a new no-event result.

## 6. Proposed tests and synthetic fixtures

Add focused tests; do not modify existing M5 tests except for shared regression
coverage if necessary:

- `tests/test_m13_contracts.py`
  - input/output schema, enums, artifact-state/ref rules, producer/type
    allowlist, candidate/run linkage, hypothesis validation, and canonical
    serialization;
- `tests/test_m13_stage.py`
  - event copying, hypothesis linking, summaries, partial imports, failure
    state handling, and result-bundle provenance;
- `tests/test_m13_workflow.py`
  - registry/preflight, typed handoff, producer manifest verification,
    first-run execution, verified reuse, output tamper rejection, and
    stage-level failure/interruption behavior;
- `tests/test_stage_cache_identity.py`
  - M13-only cache invalidation and unrelated M5–M10 identity stability.

Use temporary synthetic files and the existing `unittest`/scratch-directory
patterns from `tests/test_dvg_evidence.py` and `tests/test_virema_adapter.py`.
Do not invoke ViReMa or require its installation for M13 tests.

Required contract-derived fixtures:

1. **Completed event run:** one valid M5 event; assert byte-equivalent source
   event, native order, caller/reference/run scope, source row index, and
   immutable source digest.
2. **Completed caller zero:** valid empty evidence and
   `NO_DVG_EVIDENCE_DETECTED`; assert `IMPORTED_COMPLETED_ZERO`, no biological
   negative, and no invented hypothesis.
3. **Noncompleted runs:** separately cover not-started, unavailable,
   runtime-failed, interrupted, truncated/incomplete, and malformed/corrupt
   M5 outcomes. Preserve both raw M1 and M5 states and emit no inferred event.
   Use the handoff record and exact expectations in the
   [handoff gap resolution](M13_HANDOFF_GAP_RESOLUTION.md).
4. **Two same-shaped runs:** matching-looking events retain two distinct
   identities; no merge, vote, or agreement row.
5. **Hypotheses absent:** event index may be populated, but hypothesis matrix
   has explicit absence and no default taxonomy.
6. **Supplied structural hypothesis:** link the exact hypothesis ID and
   `STRUCTURAL_OBSERVATION` scope; retain unresolved semantics and do not
   elevate it to biological identity.
7. **Optional raw output absent:** import valid normalized evidence and mark
   raw output unavailable.
8. **Invalid run:** bad artifact hash, wrong producer/type, candidate mismatch,
   malformed event, duplicate composite identity, summary/event-count mismatch,
   invalid coordinates, or completed zero with nonempty events; reject or mark
   only the invalid run while retaining independent valid runs.
9. **Unsafe and malformed input:** unknown fields rejected only where the
   frozen manifest contract requires it; unsafe paths, symlinks, traversal,
   duplicate refs, missing required fields, and invalid state/ref combinations
   fail closed.
10. **Determinism:** reorder manifest run entries and verify prescribed
    summary ordering while preserving each native event array; repeat execution
    and compare bytes and hashes.

These fixtures are software mechanics only. The research also names generated
deletion-, copy-back-, and snap-back-like junctions as parser fixtures, but
M13 must use them only as synthetic source-event payloads and must not infer
class or biological function ([M13 readiness](M13_PRECONTRACT_READINESS.md),
lines 96–116).

## 7. Failure, interruption, and incomplete behavior

- Malformed required input, missing required declared artifact, unsafe path,
  invalid producer identity, hash mismatch, or impossible candidate linkage
  fails closed before successful output.
- A missing required workflow dependency uses existing M1
  `dependency_missing`; no new lifecycle enum is introduced.
- A producer’s failed, interrupted, incomplete, unavailable, or invalid state
  remains explicitly represented in `run_import_state` and
  `producer_status_raw`; it is never rewritten as a completed zero.
- A valid run remains in the bundle when another run is invalid or incomplete,
  subject to the contract’s partial-bundle behavior.
- Missing optional `dvg_raw_output` is unavailable but does not fail an
  otherwise valid import.
- Runtime failure maps to the existing M1 failed state; interruption maps to
  the existing interrupted state. Atomic output handling must prevent partial
  files from being inventoried as complete.
- No failure, missing hypothesis, absent event, or unavailable caller may
  reject a candidate ([M13 contract](../M13_CONTRACT_FREEZE.md), lines
  113–146).

## 8. M1–M11 regression surfaces

The implementation must preserve:

- **M1:** typed stage registration, allowlisted execution, lifecycle states,
  provenance, output inventory, verified reuse, and scoped cache identity.
- **M2–M4:** no reference/read acquisition or arbitrary-file import; M13
  remains inside the existing artifact-workflow boundary.
- **M5:** caller-specific event fields, raw status, completion/accounting
  semantics, zero-event meaning, parser version, and provenance. Do not call
  `dvg_evidence.aggregate_evaluations`, because M13 does not normalize
  multi-caller classifications. The shared handoff may add failure-reason
  metadata only; it must not change those scientific behaviors or status
  values.
- **M6:** no M6-derived event input is accepted and no read-back evidence is
  silently counted as an M5 event.
- **M7–M10:** no upstream rerun or interpretation is introduced; these
  milestones are not M13 required inputs.
- **M11:** its optional RNA-fold prediction output is not an M13 input and is
  unchanged.

Run the existing M1–M11 regression suite unchanged, especially
`tests/test_dvg_evidence.py`, `tests/test_virema_adapter.py`,
`tests/test_dvg_workflow.py`, artifact-contract tests, workflow tests, and
cache-identity tests. M13 contract registration must not alter unrelated
semantic identities or output bytes. The M5 tests already cover positive and
zero fixtures, malformed/truncated native output, accounting mismatches,
failure, interruption, and verified reuse
([M5 contract](../M5_DVG_EVIDENCE.md), lines 19–23, 31–59;
`tests/test_dvg_evidence.py`, lines 20–236;
`tests/test_virema_adapter.py`, lines 161–289).

## 9. Package, CLI, and CI implications

- No runtime dependency, external caller, biological database, reference
  snapshot, or license payload is added.
- No `pyproject.toml` dependency, package-data, script, or top-level CLI
  change is required; package discovery already includes new
  `satellite_discovery` modules.
- Add M13 synthetic tests to ordinary unittest discovery.
- Required CI remains offline and cross-platform; do not make optional
  ViReMa provisioning or any DI-tector/VODKA/VODKA2/DVGfinder installation a
  required gate.
- Optional caller provisioning remains separately gated by source, license,
  dependency, platform, and input review. It is not part of this M5-only
  implementation ([M13 design research](M13_DVG_DIFFERENTIAL_DESIGN_RESEARCH.md),
  lines 91–117).

## 10. Likely implementation order

1. Confirm the frozen input/output schemas and add no semantics beyond them.
2. Implement M13-local contracts, immutable reference checks, and canonical
   serialization using synthetic JSON fixtures.
3. Implement event-index copying and per-run import-state summaries.
4. Implement optional hypothesis linking without inventing hypotheses or
   classifications.
5. Add artifact-contract registrations and validators.
6. Add the allowlisted workflow registration and typed handoff/preflight.
7. Add cache identity, verified reuse, tamper, failure, interruption, and
   deterministic workflow tests.
8. Run the complete existing regression suite and required offline CI matrix.

After the shared handoff prerequisite in section 12 is met, M13 can proceed
independently of M12 and M14. It consumes existing M5 scientific artifacts
plus the non-scientific M5 outcome record, not M12 outputs. M15 may design its
envelope in parallel but should integrate M13 only after these output schemas
and artifact identities are stable. M16’s generic fixture mechanics can also
proceed independently; its final integration waits for frozen upstream result
bundles.
See the [cross-milestone fixture matrix](M12_M16_FIXTURE_MATRIX.md) and
[parallelization plan](M12_M16_PARALLELIZATION_PLAN.md).

## 11. Invariants and scientific-claim boundary

Tests must enforce these invariants:

1. Every accepted source event retains its entire M5 object, original order,
   caller, reference, run, and source-row provenance.
2. Event identity is run/evidence/source-row scoped, never a biological
   identity.
3. A completed zero is only an exact, accounted M5 caller result.
4. Missing, unavailable, failed, interrupted, incomplete, invalid, and
   optional evidence states remain explicit and distinct.
5. No cross-caller normalization, coordinate conversion, vote counting, or
   agreement is performed.
6. No hypothesis row is invented when hypotheses are absent.
7. A supplied hypothesis is a question scope, not a classifier label.
8. M13-only changes invalidate M13 only; upstream M5 artifacts and identities
   are not rewritten.
9. Deterministic output ordering never changes native event semantics.
10. No missing branch or failed caller becomes candidate rejection.

M13 software output can report caller-scoped observations such as “this
validated M5 run contained these event rows” or “this configured caller
reported no supported events within this run.” It cannot establish DVG
identity, satellite/subviral identity, helper origin, interference,
dependence, function, source attribution, caller sensitivity, or biological
absence. Those claims remain outside this baseline
([M13 contract](../M13_CONTRACT_FREEZE.md), lines 113–119, 181–189;
[M13 readiness](M13_PRECONTRACT_READINESS.md), lines 118–142).

## 12. Shared handoff prerequisite

The shared workflow runner now emits the versioned `m5-execution-outcome-v1`
record and stable failure codes described in the
[handoff gap resolution](M13_HANDOFF_GAP_RESOLUTION.md). Existing M1
`workflow.json` records remain unchanged; the sidecar preserves raw lifecycle
state and distinguishes truncated/incomplete output from malformed/corrupt
output without free-text parsing or filesystem search.

The shared metadata change and its cache-isolation tests are complete. M1–M12
scientific artifacts and M5 event semantics remain unchanged. The readiness
audit still needs reconciliation before any M13 code is started.

M13 implementation execution plan: SHARED HANDOFF PREREQUISITE COMPLETE — M13 NOT IMPLEMENTED
