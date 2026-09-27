# M12 contract freeze: artifact-bounded read-origin review

**Contract status: APPROVED FOR IMPLEMENTATION OF THE SYNTHETIC/OFFLINE
BASELINE ONLY.**
**Milestone status: PLANNED / NOT IMPLEMENTED until production implementation
is merged.** This specification freezes verification and description of
retained M5/M6 artifacts. Approval is limited to the artifact-bounded
implementation defined here; it does not authorize or define new read
analysis, biological data access, or out-of-scope claims.

## 1. Scope and non-goals

M12 verifies artifact identity, integrity, producer status, read accounting
already recorded by M5/M6, and the scope/limitations of those artifacts. It
links each result to its producer and reports unavailable evidence explicitly.
It does not rerun M5/M6, open read payloads, repeat mapping, or decide candidate
origin.

Out of scope for this contract:

- FASTQ reacquisition or consumption, new mapping, remapping, or assembly.
- New SAM/BAM/CRAM readers, paired-end/control analysis, or control matching.
- Source attribution, contamination verdicts, candidate rejection, or
  interpretation of absence as biological evidence.
- M7–M10 evidence; those are not M12 inputs in this baseline.

## 2. Runner and accepted producer artifacts

The later implementation is an allowlisted workflow stage named `m12_artifact_review`.
It uses the existing artifact-workflow boundary:

```text
python -m satellite_discovery.artifact_workflow \
  --manifest <workflow.json> --output <output-directory>
```

`--preflight` validates the manifest and dependencies without running stages.
There is no M12-specific public CLI, shell command, downloader, or dynamic
module loader. An additive M4 registry entry and additive artifact contracts
will be required before a production workflow can invoke M12; this document
does not add them.

An M12 input may reference only these upstream artifact types:

| Producer | Accepted artifact type | Use |
| --- | --- | --- |
| M5 DVG caller run | `dvg_evidence_summary` | Required when an M5 run is listed; preserve caller/run status and accounting. |
| M5 DVG caller run | `dvg_parameters` | Required when an M5 run is listed; binds caller, inputs, and settings. |
| M5 DVG caller run | `dvg_evidence` | Conditional event evidence; preserve rows exactly. |
| M5 DVG caller run | `dvg_raw_output` | Optional retained raw caller output; integrity/provenance only. |
| M6 residual/support run | `residual_read_manifest` | Required when an M6 run is listed; preserve reference scope and accounting. |
| M6 residual/support run | `read_triage_table` | Optional retained per-read technical triage. |
| M6 residual/support run | `read_alignment_sam` | Optional retained screen/read-back SAM; do not remap or reinterpret. |
| M6 residual/support run | `read_support_evidence`, `read_support_table` | Optional retained read-back evidence; same eligible reads are not independent evidence. |
| M6 residual/support run | `reconstruction_evidence` | Optional retained reconstruction result and limitations. |
| M6 candidate handoff | `m8_candidate_sequence_set` | Optional identity/linkage only; no sequence analysis. |

Each listed run must be produced by the named M5 or M6 contract and be
integrity-verifiable from its producer manifest. Types from M7–M10, arbitrary
JSON/CSV, raw sequence files, and user-selected files are rejected as M12
evidence inputs. A future additive input needs a new reviewed contract version.

### Same-workflow binding for the core baseline

For `m12-input-v1`, every listed producer artifact must be an explicitly
declared typed handoff from an earlier M5 or M6 stage in the same
`artifact-workflow-v1` invocation. The M12 manifest is itself a required direct
typed input of type `m12_input_manifest`; it is not an M5/M6 output. Each
`ArtifactRef` must match exactly one declared `{ "stage": ..., "artifact": ... }`
handoff, and each such handoff must match exactly one reference. Match the
producer stage ID, the artifact path relative to that stage's output root, the
artifact type and exact artifact-contract/semantic version, content digest,
producer-run-manifest digest, and raw producer status. Reject missing,
duplicate, ambiguous, unlisted, or extra handoffs.

The workflow's exact producer stage record and `output_path` determine the
producer root. The existing workflow resolver verifies the completed stage
manifest and output digest and supplies the resolved file and typed descriptor;
M12 verifies those values against the `ArtifactRef` before interpreting any
payload. Any producer-root or run-manifest metadata M12 needs must come from
that resolved handoff's workflow record. Do not search directories, infer roots
from stage IDs, or resolve producer-relative paths against the M12 manifest's
directory.

## 3. Input manifest

The UTF-8 JSON manifest has `schema = "m12-input-v1"` and exactly these
top-level fields:

```json
{
  "schema": "m12-input-v1",
  "candidate_id": "stable caller-supplied identifier",
  "producer_artifacts": [],
  "external_evidence": {
    "source_reads": {"state": "NOT_SUPPLIED", "note": null},
    "controls": {"state": "NOT_SUPPLIED", "note": null},
    "sample_metadata": {"state": "NOT_SUPPLIED", "note": null},
    "independent_evidence": {"state": "NOT_SUPPLIED", "note": null}
  }
}
```

`candidate_id` is required, non-empty, and opaque: M12 does not validate
taxonomy or biological identity. `producer_artifacts` is an array of
`ArtifactRef` objects. It may be empty, in which case the valid result is
`NOT_EVALUATED` with no evidence rows, not a completed negative.

An `ArtifactRef` contains:

| Field | Requirement |
| --- | --- |
| `producer_milestone` | Exactly `M5` or `M6`, matching the type below. |
| `producer_stage_id` | Exact allowlisted stage ID from the producer workflow manifest. |
| `producer_run_manifest_sha256` | SHA-256 of the immutable producer run manifest. |
| `producer_status` | Exact raw terminal state from the producer; never normalized in place. |
| `artifact_type` | One of the accepted types in section 2. |
| `relative_path` | Normalized relative path inside the producer output; no symlink or path escape. |
| `sha256` | Lowercase 64-character digest matching the bytes. |
| `artifact_contract_version` | Exact producer contract/semantic version for this artifact type. |

Duplicate references to the same `(producer_run_manifest_sha256, artifact_type,
sha256)` are invalid. Distinct artifacts from one run may be listed. The
`external_evidence` object and its four keys are required even when evidence is
missing. `state` is one of `PRESENT_NOT_CONSUMED`, `NOT_SUPPLIED`,
`NOT_AUTHORIZED`, `UNAVAILABLE`, `NOT_APPLICABLE`, or `UNKNOWN`. `note` is
either null or a short, non-sensitive explanation. This baseline never accepts
the payload behind those external-evidence entries.

The `m12-input-v1` fields and `ArtifactRef` identity remain unchanged by the
same-workflow binding rule. A reference is a claim to check against the
workflow-declared handoff, not a path-search instruction. No location field,
sidecar, or prior-run locator is part of this schema.

## 4. Outputs and domain states

Proposed future artifact types (not yet registered) are:

- `m12_artifact_review_table` — JSON array of per-artifact review records.
- `m12_summary` — JSON summary of reviewed and unassessed dimensions,
  including `review_completeness`.
- `m12_result_bundle` — JSON manifest binding inputs, outputs, and provenance.

Each review record contains `candidate_id`, `artifact_ref`, `review_state`,
`producer_status_raw`, `scope`, `analysis_execution_status`,
`accounting_status`, `observation_status`, `limitations`, and
`dependency_refs`. `review_state` is one of `VERIFIED`, `NOT_EVALUATED`,
`UNAVAILABLE`, `NOT_APPLICABLE`, `INVALID`, `INCOMPLETE`, `FAILED`, or
`INTERRUPTED`. `producer_status_raw` is copied byte-for-byte as a string/value
from the verified producer manifest. M12 does not create a source, origin, or
artifact classification.

The summary repeats the four external-evidence states, counts M5/M6 artifacts
by producer and review state, and includes `biological_conclusion = "NONE"`.
`review_completeness` is `COMPLETE_WITHIN_SUPPLIED_ARTIFACT_SCOPE` when every
listed artifact validates, `PARTIAL` when any listed artifact is
invalid/unavailable/incomplete or otherwise cannot be verified while a valid
summary is still produced, `NOT_EVALUATED` when no artifacts were supplied, or
`INVALID` when the required manifest itself fails validation. Missing external
evidence does not change artifact-scope completeness; it remains visible in
its own availability field.
M5 `NO_DVG_EVIDENCE_DETECTED` remains a caller-scoped M5 result; M6 residual
means unmapped under its declared reference/settings. Neither is a source
negative or candidate rejection.

### 4.1 Semantic clarification (contract erratum)

This clarification defines deterministic summary states for the existing
synthetic/offline M5/M6 artifact boundary. It does not change upstream
contracts, accept new inputs, consume external-evidence payloads, or authorize
read analysis. The detailed rationale and worked cases are in the
[semantic-axis resolution](research/M12_SEMANTIC_AXIS_RESOLUTION.md).

`review_state` is the M12 artifact-review outcome, not the producer's analysis
result: `VERIFIED` means identity, integrity, and applicable schema checks pass;
`UNAVAILABLE` means a referenced artifact cannot be read; `INVALID` means an
identity/schema/status check fails; `INCOMPLETE` means accounting is explicitly
incomplete; `NOT_EVALUATED` means no review/result was performed;
`NOT_APPLICABLE` requires an explicit producer declaration and is never inferred
from omission; `FAILED` and `INTERRUPTED` describe the M12 review operation.
None of these states establishes biological validity.

`analysis_execution_status` is one of `COMPLETED`, `NOT_STARTED`,
`DEPENDENCY_UNAVAILABLE`, `FAILED`, `INTERRUPTED`, `UNKNOWN`, or
`NOT_APPLICABLE`. Use the recognized artifact-level status for that exact
analysis dimension; otherwise use a verified terminal M1 producer lifecycle.
Keep the exact enclosing producer lifecycle in `producer_status_raw`. A
failure in one M6 branch does not rewrite a separately verified completed
branch.

`accounting_status` is one of `COMPLETE`, `INCOMPLETE`, `TRUNCATED`, `INVALID`,
`UNKNOWN`, or `NOT_APPLICABLE`. `COMPLETE` requires explicit accounting for
the declared scope; `TRUNCATED` requires explicit or verified truncation;
`UNKNOWN` is used when completeness is not proved; `NOT_APPLICABLE` is reserved
for artifacts that do not represent counted analyses. A failed parser or
missing file alone does not prove truncation.

`observation_status` is one of `OBSERVATION_REPORTED`,
`NO_SIGNAL_WITHIN_SCOPE`, `NO_OBSERVATION`, `UNKNOWN`, or `NOT_APPLICABLE`.
`NO_SIGNAL_WITHIN_SCOPE` requires a recognized completed producer zero,
`accounting_status = COMPLETE`, and satisfied method prerequisites. It names
only the method/input/reference scope; it is not biological absence. Signals
explicitly reported by a valid producer may be retained independently of
another failed branch. Unknown or conflicting statuses never map to a zero.

`NO_SIGNAL_WITHIN_SCOPE` is a canonical `observation_status` value, not a new
producer status or a source/artifact classification. It does not alter or
replace `producer_status_raw`.

Apply these producer mappings after validating artifact identity, digest,
contract version, and applicable upstream consistency:

The status names below are typed artifact-payload statuses. The enclosing
`ArtifactRef.producer_status` remains the exact raw M1 lifecycle value and is
used only as the documented fallback.

| Producer status/artifact | `analysis_execution_status` | `accounting_status` | `observation_status` |
| --- | --- | --- | --- |
| M5 `DVG_EVIDENCE_DETECTED` | `COMPLETED` | `COMPLETE` | `OBSERVATION_REPORTED` |
| M5 `NO_DVG_EVIDENCE_DETECTED` | `COMPLETED` | `COMPLETE` | `NO_SIGNAL_WITHIN_SCOPE` |
| M5 `NOT_EVALUATED` | `NOT_STARTED` | `UNKNOWN` | `NO_OBSERVATION` |
| M5 `ANALYSIS_UNAVAILABLE` | `DEPENDENCY_UNAVAILABLE` | `UNKNOWN` | `NO_OBSERVATION` |
| M5 `ANALYSIS_FAILED` | `FAILED` | `UNKNOWN` | `NO_OBSERVATION` |
| M5 `INVALID_RESULT` | `FAILED` | `INVALID` | `NO_OBSERVATION` |
| M6 residual manifest with `comparison.status = complete`, equal input/accounted counts, and positive `counts.residual_fragments` | `COMPLETED` | `COMPLETE` | `OBSERVATION_REPORTED` |
| M6 residual manifest with the same complete accounting and `counts.residual_fragments = 0` | `COMPLETED` | `COMPLETE` | `NO_SIGNAL_WITHIN_SCOPE` |
| M6 `read_support_evidence` `READ_SUPPORTED_ASSEMBLY` | `COMPLETED` | `COMPLETE` only when required query accounting validates; otherwise `UNKNOWN`/`INVALID` | `OBSERVATION_REPORTED` |
| M6 `read_support_evidence` `NO_SUPPORTED_ASSEMBLY` | `COMPLETED` | `COMPLETE` only when required query accounting validates; otherwise `UNKNOWN`/`INVALID` | `NO_SIGNAL_WITHIN_SCOPE` only for the completed read-support test |
| M6 `NOT_EVALUATED` / `ASSEMBLY_NOT_ATTEMPTED` | `NOT_STARTED` | `UNKNOWN` or `NOT_APPLICABLE` by artifact type | `NO_OBSERVATION` |
| M6 `DEPENDENCY_UNAVAILABLE` | `DEPENDENCY_UNAVAILABLE` | `UNKNOWN` | `NO_OBSERVATION` |
| M6 `EXECUTION_FAILED`, `READ_SUPPORT_FAILED`, `INVALID_OUTPUT`, or `INVALID_SUPPORT_OUTPUT` | `FAILED` | `INCOMPLETE`, `INVALID`, or `UNKNOWN` only as explicitly established; otherwise `UNKNOWN` | `NO_OBSERVATION` |
| M6 `INTERRUPTED` | `INTERRUPTED` | `INCOMPLETE` only when explicitly established; otherwise `UNKNOWN` | `NO_OBSERVATION` |

For M6 `reconstruction_evidence`, do not map a top-level
`NO_SUPPORTED_ASSEMBLY` to a completed no-signal unless a linked
`read_support_evidence` artifact proves that the support test ran with its
required input accounting. The reconstruction status can also arise when no
eligible reads were available. Preserve per-contig statuses such as
`LOW_SUPPORT_ASSEMBLY`, `UNSUPPORTED_ASSEMBLY`, and `AMBIGUOUS_ASSEMBLY` as
producer-native technical observations; they are not M12 artifact
classifications.

For configuration/identity artifacts that do not represent an analysis,
`analysis_execution_status`, `accounting_status`, and `observation_status` are
`NOT_APPLICABLE`. For raw or per-read artifacts without a summary outcome,
`observation_status` is `NOT_APPLICABLE` only for the normalized aggregate
field; retain the raw records unchanged. Their execution/accounting states are
`UNKNOWN` unless a linked typed producer record establishes them. This does not
mean that a per-read artifact contains no observations.

The four external-evidence entries retain their exact existing six-value state
enums. They report availability only; `PRESENT_NOT_CONSUMED` is not a finding.
M12 adds no source-origin, technical-artifact, control-adequacy,
metadata-completeness, or interpretation axis. The summary keeps
`biological_conclusion = "NONE"`.

Stage execution uses the existing M1 lifecycle values: `pending`, `running`,
`complete`, `skipped`, `dependency_missing`, `external_module_required`,
`failed`, or `interrupted`; workflow aggregation may be `partial`. There is no
new persisted `blocked` lifecycle state. A required dependency that prevents
execution maps to M1 `dependency_missing` or `external_module_required`.
Missing optional artifacts are output states, not lifecycle failures.

## 5. Validation, partial inputs, and failures

- Validate manifest schema and enum values before reading artifacts.
- Verify producer manifest digest, declared stage/type pairing, artifact
  contract version, safe relative path, file digest, and producer-declared
  status. A mismatch is `INVALID`; do not inspect the payload as biological
  evidence.
- Validate M5 summary/event consistency and M6 manifest/accounting integrity
  using the upstream validators. Do not replace an upstream invalid or
  incomplete status with a successful M12 status.
- A valid manifest with no artifacts completes with `NOT_EVALUATED` records.
  A missing optional artifact remains unassessed. If M12 can inspect a listed
  artifact and finds it unavailable or corrupted, it records that failure while
  preserving other verified rows. If the workflow resolver rejects the
  required handoff before M12 starts, the workflow lifecycle records the
  failure and M12 emits no biological conclusion.
- A failure to parse the required M12 manifest fails before stage execution.
  A failed M12 process uses M1 `failed`; interruption uses `interrupted`.
- No artifact state, missing control, absent metadata, or failed optional
  branch can become a candidate rejection or a completed biological negative.

In the same-workflow baseline, a producer stage that is missing, skipped,
failed, interrupted, or dependency-unavailable retains its existing M1
workflow state. A required handoff that cannot be resolved prevents M12 from
running; it is not converted into a zero or a biological negative. Omitted
optional handoffs remain unassessed. A contract, identity, or integrity
mismatch fails closed as invalid at the workflow/M12 input boundary, with no
payload-derived observation. These workflow-level states do not replace the
M12 review states for artifacts that are successfully handed to M12.

`NOT_DETECTED_WITHIN_SCOPE` is not an M12-generated producer status. The
separate `observation_status = NO_SIGNAL_WITHIN_SCOPE` value is permitted only
under the semantic clarification in section 4.1. Preserve the producer's exact
raw status and scope; do not broaden either one. `NO_SIGNAL_WITHIN_SCOPE` is not
`ABSENT`; `UNKNOWN`, unavailable, not-applicable, failed, interrupted, invalid,
incomplete, and truncated states remain distinct and never map to a completed
no-signal.

## 6. Provenance, identity, and deterministic output

The result bundle records the M12 schema/semantic version, implementation
source digest, exact input-manifest digest, every consumed producer run
manifest and artifact digest/type/version/raw status, all four external
availability states, and the output artifact digests. Do not store secrets,
restricted read payloads, or absolute host paths.

For the core baseline, producer-run identity is the digest of the exact
completed upstream stage `manifest.json` resolved by the declared handoff.
The recorded `relative_path` is checked against that handoff's artifact name
relative to its known stage output root. Absolute roots are runtime resolution
details and are not serialized into M12 results.

The M12 cache identity includes:

1. M12 input schema and semantic version.
2. Candidate ID and the complete external-evidence state/note fields.
3. Every consumed artifact’s producer milestone/stage ID, run-manifest digest,
   type, contract version, content digest, and raw producer status.
4. The semantic identities of only the artifact contracts consumed, the M12
   implementation/source digest, and the normalized output-schema version.

Generated timestamps and output-directory paths are excluded. Changing an M12
input or implementation invalidates M12 only; it does not rerun or invalidate
M5/M6. A reused M12 bundle must reverify its identity and all output digests.

Serialize JSON as UTF-8, no BOM, LF, one trailing newline, sorted object keys,
and no NaN/Infinity. Sort review rows by candidate ID, producer milestone,
producer stage ID, artifact type, then digest. Preserve any producer-native row
order inside copied payloads. The same identity and inputs must produce
byte-identical semantic outputs.

## 7. Synthetic acceptance fixtures

| Fixture | Required result |
| --- | --- |
| Valid M5 detected run plus valid M6 manifest | Two producer-scoped rows with exact hashes/statuses; no combined source verdict. |
| Valid M5 completed zero | Raw `NO_DVG_EVIDENCE_DETECTED` retained with caller/input scope; not reported as candidate-negative. |
| M6 read-back and reconstruction from assembly-eligible reads | Dependency link identifies shared reads; not independent confirmation. |
| Empty `producer_artifacts`, all external fields `NOT_SUPPLIED` | `NOT_EVALUATED`; zero artifacts are not zero biological evidence. |
| Missing controls/metadata/source reads marked `NOT_AUTHORIZED` or `UNKNOWN` | Exact availability retained; no clean-control/source-negative finding. |
| Wrong producer/type, bad digest, path traversal, symlink, duplicate reference, malformed manifest | Preflight/input validation rejects the affected run as invalid. |
| Incomplete M5 accounting or M6 manifest | Source status remains incomplete/invalid; no scoped no-signal is added. |
| One valid M5 artifact and one corrupted optional M6 artifact | Preserve the valid row; mark the M6 row invalid and overall evidence coverage incomplete. |

## 8. Compatibility and claim boundary

This stage consumes existing M5/M6 artifact contracts listed in
[`artifact_contracts.py`](../satellite_discovery/artifact_contracts.py) and
the current M1 lifecycle in
[`workflow_states.py`](../satellite_discovery/workflow_states.py). It requires
no M1–M11 scientific behavior or identity change. Registration is additive and
M12-scoped: add the M12 artifact contracts and workflow-stage validation and
handler; do not change the `WorkflowStageRegistry` API or create a general
external artifact-location framework. M12 outputs support artifact provenance
review, not read-origin attribution, contamination, biological identity, or
candidate rejection.

Prior-run and reanalysis support is a future optional extension, not a
`m12-input-v1` requirement. If authorized later, introduce a new input schema
and M12 input-contract semantic version with explicit, validated location
bindings (for example, a versioned M12 sidecar or schema field), while keeping
the existing producer/run/artifact digests, contract identities, review axes,
and scientific interpretations unchanged. Resolve those locations only in an
M12-specific adapter. Do not implement or generalize that locator for this
baseline.
