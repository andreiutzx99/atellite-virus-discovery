# M12 implementation execution plan

**Status: APPROVED IMPLEMENTATION PLAN FOR THE FROZEN SYNTHETIC/OFFLINE
BASELINE. M12 remains PLANNED / NOT IMPLEMENTED until production implementation
is merged.** This plan records the approved artifact-bounded review of retained
M5/M6 outputs; it contains no production implementation. It does not expand the
approved boundary to new reads, remapping, controls, source attribution, or
candidate rejection ([M12 contract](../M12_CONTRACT_FREEZE.md), lines 1–22;
[roadmap](../ROADMAP.md), lines 24–35).

This plan is subordinate to the contract. The semantic-axis clarification and
`m12-input-v1` registration decision are **RESOLVED** for the synthetic/offline
baseline. M12 remains PLANNED / NOT IMPLEMENTED until production implementation
is merged. This plan records the approved baseline but contains no production
implementation:

1. The M12 semantic-axis/record schema gap is **resolved by the contract
   erratum** and [semantic-axis resolution](M12_SEMANTIC_AXIS_RESOLUTION.md).
   The normative mappings are now fixed for the synthetic/offline baseline.
2. Keep the input document schema `m12-input-v1` and expose the caller-supplied
   manifest as a required direct typed input of type `m12_input_manifest`.
   Retain the `artifact-contract-v1` descriptor format; the new input contract
   starts at semantic version `1`, independent of the M12 stage version.
3. Every `ArtifactRef` must map one-to-one to an explicitly declared typed
   `{stage, artifact}` handoff from an earlier M5/M6 stage in the same workflow
   run. Use the workflow's exact producer stage record and output root to bind
   its manifest digest, output name, content digest, exact artifact-contract/
   semantic version, and status. The input schema itself is unchanged; its
   references are not path-search hints. Do not scan directories or infer roots
   from stage IDs.
4. Prior-run/reanalysis inputs are deferred. If authorized later, add a
   versioned, explicit location binding in a new M12 input schema and resolve it
   in an M12-specific adapter. Preserve the producer artifact contracts and
   scientific semantics; do not build a general locator framework.

This uses the existing typed direct-manifest pattern
(`reference_snapshot_config`), stage/artifact handoffs, and stage-scoped
contract/cache identities. The M12 workflow validation and handler additions
are additive; no `WorkflowStageRegistry` API change is needed.

The M12 fixture requirements and semantic distinctions are specified in the
[M12 contract](../M12_CONTRACT_FREEZE.md#7-synthetic-acceptance-fixtures) and
[semantic-axis resolution](M12_SEMANTIC_AXIS_RESOLUTION.md). This execution
plan does not depend on cross-milestone planning material.

## 1. Frozen scope and implementation gate

| Item | Plan |
| --- | --- |
| Stage | `m12_artifact_review`, through the existing allowlisted artifact-workflow runner |
| Runner | `python -m satellite_discovery.artifact_workflow --manifest <workflow.json> --output <directory>`; `--preflight` remains available |
| Core input | Required typed `m12-input-v1` manifest plus one-to-one, integrity-verified same-workflow M5/M6 artifact handoffs |
| Accepted producers | M5: `dvg_evidence_summary`, `dvg_parameters`, optional `dvg_evidence`, `dvg_raw_output`; M6: `residual_read_manifest`, optional `read_triage_table`, `read_alignment_sam`, `read_support_evidence`, `read_support_table`, `reconstruction_evidence`; optional M6 candidate linkage `m8_candidate_sequence_set` |
| Outputs | `m12_artifact_review_table`, `m12_summary`, `m12_result_bundle` (specified but not yet registered) |
| Explicit exclusions | M7–M10 evidence, arbitrary files, raw sequence readers, new mapping, assembly, paired/control analysis, source attribution, contamination verdicts, and biological rejection |
| Registration gate | Resolved: typed manifest plus explicit same-workflow producer handoffs. Production artifact-contract, workflow-registry, and handler changes remain unimplemented. |

The accepted artifact list and rejection boundary are frozen in the
[M12 contract](../M12_CONTRACT_FREEZE.md), lines 24–58. The useful offline
baseline is verification, provenance, missingness, and transparent summaries
of retained artifacts, not a new origin analysis.

## 2. Semantic-axis clarification: resolved for the offline baseline

The previously considered separate state dimensions are resolved for the
permitted artifact-only baseline by the [M12 contract erratum](../M12_CONTRACT_FREEZE.md#41-semantic-clarification-contract-erratum)
and [semantic-axis resolution](M12_SEMANTIC_AXIS_RESOLUTION.md). They define
the record fields, canonical values, M5/M6 mappings, scope, and non-inference
rules while retaining exact raw producer status.

The resolution intentionally does not add source-origin, control-adequacy,
metadata-completeness, or biological-interpretation axes: the baseline does not
consume those payloads. Any earlier finding that these dimensions required
further resolution is resolved for this baseline; it does not authorize
control analysis or change upstream behavior.

## 3. Proposed implementation surface

### New modules

| Module | Responsibility | Gate |
| --- | --- | --- |
| `satellite_discovery/m12_artifact_review.py` | Parse the approved manifest boundary, link each `ArtifactRef` to its matching resolved workflow handoff, perform cross-artifact M5/M6 consistency checks, produce review rows/summary/bundle, and expose stage-local identity hooks. It must not search for files or rerun adapters. | Registration decision is resolved; production implementation remains pending. Use the normative axes now defined by the erratum. |
| `satellite_discovery/m12_contracts.py` (optional separation) | M12-only manifest/output schemas and cross-artifact rules, if these should not be embedded in the shared registry. | Do not choose a new contract shape here; use only after input registration is resolved. |

No new read, SAM/BAM/CRAM, remapping, assembly, caller, downloader, or
dynamic-loader module is justified. Existing M5/M6 adapters remain producers,
not M12 implementation dependencies to rerun.

### Additive shared changes

| Existing module | Additive change after gate | Required non-change |
| --- | --- | --- |
| `satellite_discovery/artifact_contracts.py` | Add `m12_input_manifest` validation for the exact `m12-input-v1` document and register semantic identity for the M12 input and three outputs. | Do not alter M5/M6 validators or global validator semantics. |
| `satellite_discovery/artifact_workflow.py` | Add M12-scoped validation requiring the typed `manifest` and an exact one-to-one set of explicit typed producer handoffs; pass their already verified producer stage/run identity and output-root metadata to M12. Register typed outputs, handler, and any approved report allowlist entry. | Do not change the `WorkflowStageRegistry` API or add a public M12 CLI, general artifact locator, or dynamic module execution. |
| `satellite_discovery/stage_registry.py` | No change expected; existing typed/dynamic registration should suffice. | Do not broaden registry safety rules for M12. |
| `satellite_discovery/workflow_states.py` | No change expected; use existing lifecycle states. | Domain review states are artifact fields, not new persisted lifecycle enums. |
| `pyproject.toml` | No change expected; package discovery already includes project modules. | No runtime dependency or entry point. |

The existing stage registry, workflow resolver, and cache path are the intended
extension points. All changes are additive and stage-scoped.

## 4. Artifact registration and validation design

### Outputs

Register the exact frozen output names only:

- `m12_artifact_review_table`: per-artifact records containing the frozen
  fields, the erratum-defined execution/accounting/observation axes, raw
  producer status, source reference, limitations, and dependency links. Do not
  add further unapproved axes.
- `m12_summary`: four external-evidence entries/states, counts by producer and
  review state, review completeness, and `biological_conclusion = "NONE"`.
- `m12_result_bundle`: input digest, consumed producer references/statuses,
  output digests, schema/implementation identity, and provenance.

The output contract and completeness rules are specified at
[M12 contract](../M12_CONTRACT_FREEZE.md), lines 105–140 and 165–184.

### Input boundary

The implementation must validate, before payload interpretation:

1. exact manifest fields and external-evidence keys/states;
2. M5/M6 producer milestone and stage pairing;
3. producer run-manifest digest and artifact contract version;
4. normalized relative path, regular non-symlink file, and SHA-256;
5. duplicate reference identity; and
6. upstream status/accounting consistency.

The manifest’s schema is frozen at the
[M12 contract](../M12_CONTRACT_FREEZE.md), lines 60–103. The decision that it
is a required direct typed input with artifact-contract version 1 is resolved;
actual registration in code remains unimplemented. Preserve this
design-versus-implementation distinction in review.

The direct `manifest` input is resolved through the existing artifact-workflow
typed-input boundary. Its artifact-contract validator checks the
`m12-input-v1` document shape and schema identifier. Each producer artifact is
also declared as an explicit typed stage handoff. M12-specific workflow
validation matches every handoff to exactly one `ArtifactRef` by producer stage,
relative output name, artifact type, exact contract/semantic version, and
content digest; it rejects unmatched refs and extra handoffs.

The workflow resolver supplies each artifact from the exact completed
producer's `output_path`, verifies its stage manifest and output digest, and
provides the producer stage-manifest digest and typed descriptor to M12. M12
checks those identities against `producer_run_manifest_sha256`,
`producer_status`, and the remaining reference fields before payload
interpretation. Neither the artifact-contract validator nor M12 searches for
files or resolves a producer path relative to the input manifest.

Keep the input artifact type `m12_input_manifest` separate from the embedded
document schema `m12-input-v1`, and from the M12 stage version. The input
validator must reject unknown fields and unsupported schema identifiers rather
than silently accepting a future shape. An incompatible document change uses
an explicit new schema identifier (for example, `m12-input-v2`) and an updated
input-contract semantic version; it does not revise M5/M6 contract identities
or the shared `artifact-contract-v1` descriptor schema.

## 5. Reusable infrastructure and identity

### Validators and provenance

Reuse, rather than duplicate:

- `artifact_contracts.validate_artifact` for M5 DVG summary/evidence/parameters
  and M6 manifest, triage, SAM, support, and reconstruction contracts;
- `describe_artifact` and `verify_descriptor` for safe paths, size, digest,
  regular-file, and contract-envelope checks;
- existing workflow upstream resolution for producer-manifest containment,
  completion, and digest verification;
- existing M1 lifecycle and workflow failure/interrupt handling.

M12 must preserve native producer rows/order and exact raw status. It must never
call M5/M6 adapters, normalize their statuses into a new biological result, or
use a shared-read M6 read-back as independent evidence
([M12 contract](../M12_CONTRACT_FREEZE.md), lines 144–163).

### Serialization

Use an M12-local canonical writer unless a future approved shared helper exactly
matches the contract: UTF-8, no BOM, LF line endings, one trailing newline,
sorted object keys, and no NaN/Infinity. Sort review rows by candidate,
producer milestone, producer stage, artifact type, then digest; preserve
producer-native order within copied payloads
([M12 contract](../M12_CONTRACT_FREEZE.md), lines 186–190).

Plannable serializer tests:

- repeated execution produces byte-identical outputs and hashes;
- input object/key ordering does not change semantic bytes;
- CRLF, BOM, missing final newline, NaN, and Infinity are rejected or never
  emitted;
- source event order is preserved inside an otherwise sorted result; and
- timestamps and absolute output paths do not affect bytes.

### Cache identity

The stage-local identity must include the approved M12 schema/semantic version,
candidate ID, all four external state/note fields, every consumed producer
stage/run/artifact/type/version/status/content digest, consumed contract
semantic identities, implementation/source digest, and output schema version.
It must exclude timestamps and output-directory paths
([M12 contract](../M12_CONTRACT_FREEZE.md), lines 165–184).

The typed manifest's content digest and `m12_input_manifest` contract identity
belong in the M12 cache identity. The actual digest and contract identity of
every referenced M5/M6 artifact, plus each producer stage-manifest digest and
raw status, must also reach that key through the verified same-run handoffs.
The nested digest strings in the manifest alone are not proof that referenced
files still match. Compute this M12-only cache context from the exact resolved
producer stage records before cache reuse: include each actual stage-manifest
digest, stage ID, artifact name, content digest, contract identity, and status.
If needed, add a M12-scoped context path in `artifact_workflow.py`; do not
change shared cache semantics or other stages' keys. Absolute roots remain
excluded. Do not cache solely on the manifest file.

Cache-isolation tests must show that:

- changing M12 manifest, external state, implementation, or output schema
  invalidates M12 only;
- changing a consumed M5/M6 artifact invalidates M12 through its digest but
  does not rewrite or invalidate the producer stage;
- changing a consumed producer stage manifest or handoff identity invalidates
  M12 without changing the producer's scientific semantics;
- unrelated contract registration does not alter existing M1–M10 identities;
  and
- reused outputs reverify all descriptors and output digests, rejecting
  tampered files.

## 6. Tests and exact synthetic fixtures

### Proposed test modules

- `tests/test_m12_artifact_review.py`: domain records, manifest rules,
  partial input, state preservation, serializer, and cache identity.
- `tests/test_m12_contracts.py`: output validators and the eventually approved
  input-boundary contract.
- `tests/test_m12_workflow.py`: registry/preflight, typed producer handoffs,
  first execution, verified reuse, tamper rejection, failure, and interruption.
- Extend `tests/test_artifact_validation.py` only for additive M12 contract
  dispatch, and `tests/test_stage_cache_identity.py` only for scoped
  invalidation. Do not alter existing M5/M6 test semantics.

### Contract-derived fixtures

| Fixture | Required assertion |
| --- | --- |
| Valid M5 detected run + valid M6 manifest | Two producer-scoped rows with exact hashes/statuses; no combined source verdict. |
| Valid completed M5 zero | Preserve `NO_DVG_EVIDENCE_DETECTED`, caller/input scope, and no candidate-negative result. |
| M6 read-back + reconstruction from assembly-eligible reads | Explicit shared-read dependency; never independent confirmation. |
| Empty producer list + four `NOT_SUPPLIED` external states | Valid `NOT_EVALUATED` result, not zero evidence. |
| Missing controls, metadata, or source reads marked `NOT_AUTHORIZED`/`UNKNOWN` | Exact state retained; no clean-control or source-negative finding. |
| Wrong producer/type, bad digest, path traversal, symlink, duplicate ref | Preflight/input rejection as invalid. |
| Incomplete M5 accounting or M6 manifest | Preserve incomplete/invalid source state; never emit scoped no-signal. |
| Valid M5 plus corrupted optional M6 | Preserve valid row, mark M6 invalid, summary `PARTIAL`. |
| Malformed required manifest | Fail before stage execution. |
| Runtime exception and `KeyboardInterrupt`/process interruption | Existing M1 `failed` versus `interrupted`; no partial output inventoried as success. |
| Permuted equivalent inputs and repeated run | Byte-identical canonical outputs and verified reuse. |

These fixtures are also constrained by the
[M12 contract's synthetic acceptance fixtures](../M12_CONTRACT_FREEZE.md#7-synthetic-acceptance-fixtures);
this plan must not turn them into real reads, controls, or biological truth.

## 7. Failure, interruption, and incompleteness

Manifest/schema/enum errors fail closed before artifact reading. Producer
manifest, type, version, path, digest, or status mismatches are rejected at the
typed workflow/M12 input boundary; the payload must not be interpreted as
biological evidence. Valid rows may survive a separately invalid optional
artifact discovered during M12 review, producing `PARTIAL`.

An empty valid input completes with `NOT_EVALUATED`. Missing optional artifacts
remain unassessed; listed unavailable/corrupt artifacts remain explicit if
reached by M12 validation. If an upstream stage or required handoff fails
before M12 runs, preserve its existing typed workflow lifecycle; do not emit an
M12 no-signal. Incomplete or truncated producer accounting is never rewritten
as completed no-signal. A required dependency maps to existing
`dependency_missing` or `external_module_required`; process failure maps to
`failed`; interruption maps to `interrupted`
([M12 contract](../M12_CONTRACT_FREEZE.md), lines 135–163).

## 8. M1–M10 regression surfaces

- **M1/M4:** stage allowlist, typed handoffs, lifecycle, manifests, safe
  containment, verified reuse, and cache identity remain unchanged except for
  additive M12 registration.
- **M2/M3:** M12 only links immutable identities; it does not acquire
  references, consume new reads, assemble, or rerun mapping.
- **M5:** caller-scoped event rows, accounting, parameters, raw output, and
  completed-zero semantics remain byte/meaning preserving.
- **M6:** reference/settings scope, residual accounting, read-back provenance,
  and shared eligible-read dependency remain unchanged; no independent
  evidence is manufactured.
- **M7–M10:** reject their artifacts as M12 evidence, except the explicitly
  allowed M8 candidate-set identity linkage; existing tests and cache keys must
  remain stable.

Run the existing full unittest suite and M1–M10 workflow/cache/validation
tests as merge gates. Required CI remains synthetic/offline on the existing
Python/platform matrix; no external callers, private reads, databases, or
benchmark payloads are introduced.

## 9. Package, CLI, CI, and implementation order

No M12-specific command, package dependency, script, or CI job is planned.
Use the existing artifact-workflow CLI and add only deterministic synthetic
tests to ordinary discovery. Optional native tools remain outside required CI
([M12 contract](../M12_CONTRACT_FREEZE.md), lines 24–38).

Recommended order:

1. Carry the published semantic-axis erratum and frozen same-workflow
   `m12-input-v1` binding rules into the planned schemas and fixtures. The
   input-registration blocker is resolved; do not add prior-run location
   support to the baseline.
2. Prepare fixture factories and validator test cases that exercise the
   normative mappings while preserving raw producer states.
3. Implement the isolated M12 domain/parser and canonical serializer.
4. Add output validators and semantic versions without changing M5/M6
   validators.
5. Add the approved workflow registration and handler.
6. Add workflow, reuse, tamper, interruption, and cache-isolation tests.
7. Run the full regression suite on the existing required CI matrix.

## 10. Contract invariants and scientific boundary

Tests must enforce that M12:

- preserves producer identity, raw status, schema, scope, accounting, hashes,
  and native row order;
- distinguishes missing, unavailable, invalid, incomplete, failed,
  interrupted, and not-evaluated states;
- never treats missing controls, metadata, reads, or optional branches as a
  negative or candidate rejection;
- never reruns upstream analysis or broadens a method/reference scope;
- never counts M6 read-back over assembly-eligible reads as independent;
- emits `biological_conclusion = "NONE"` and no source classifier; and
- changes only M12 cache identity when M12-local inputs or implementation
  change.

M12 software output can support artifact integrity review and transparent,
method-scoped provenance. It cannot establish read origin, contamination,
biological identity, DVG/satellite class, helper dependence, function,
independence, or candidate rejection. Real-data access, matched controls,
source attribution, and any stronger biological claim require separate
authorization and claim-specific evidence.

M12 IMPLEMENTATION BASELINE APPROVED; INPUT REGISTRATION RESOLVED;
IMPLEMENTATION REMAINS PLANNED / NOT IMPLEMENTED
