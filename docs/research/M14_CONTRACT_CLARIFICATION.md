# M14 final contract clarification

**Decision:** the M14 descriptive synthetic/offline baseline is ready for
implementation under the normative decisions below.
**Milestone status:** M14 remains **PLANNED / NOT IMPLEMENTED**.
**Scope:** this note clarifies the frozen M14 contract; it does not implement
M14, authorize real-data use, or change M1–M13 behavior.

This clarification is normative for the specific ambiguities identified here.
All other scope, fields, counting rules, and claim limits remain governed by
the [M14 contract freeze](../M14_CONTRACT_FREEZE.md).

## 1. Input boundary and optional-source records

The M14 stage accepts only the caller-authored `m14-input-v1` observation
manifest and the M4/M7 producer/type pairs in the freeze. M13 is not an input
or sequencing prerequisite. M4 and M7 sources remain optional context and
provenance; neither supplies or completes M14's declared candidate/helper
observation frame by implication.

Add a required top-level `source_outcomes` array. Keep
`source_artifacts` for actual artifact references only. A source-outcome row
is typed metadata about one optional producer run or an explicit
`NOT_SUPPLIED`/`NOT_RUN` declaration; it is not a scientific artifact and has no
placeholder file.

The allowed `source_kind` values are:

| `source_kind` | Producer and accepted types |
| --- | --- |
| `M4_CATALOGUE_OBSERVATIONS` | M4 `catalogue_observations`; `sample_table`, `observation_table`, `occurrence_table`, or `occurrence_summary`. |
| `M4_OBSERVATIONS` | M4 `observations`; `occurrence_table` or `occurrence_summary`. |
| `M7_INDEPENDENT_RECURRENCE` | M7 `independent_recurrence`; `m7_observation_table`, `m7_exact_recurrence_table`, `m7_independence_summary`, `m7_validation_report`, or `m7_provenance_manifest`. |

Each row has the following exact semantic fields:

| Field | Contract |
| --- | --- |
| `source_id` | Stable unique caller-declared token. It identifies this source slot/run, not a biological entity. |
| `source_kind` | One of the three values above. |
| `source_state` | `NOT_SUPPLIED`, `AVAILABLE`, `UNAVAILABLE`, `NOT_RUN`, `FAILED`, `INTERRUPTED`, `INCOMPLETE`, or `INVALID`. |
| `workflow_ref` | Null only for `NOT_SUPPLIED` or a source explicitly declared `NOT_RUN`; otherwise `{"relative_path": ..., "workflow_id": ...}`. The path points to the relevant M1 `workflow.json`; expected ID may be null only when that record cannot be read. |
| `producer_stage` | Null only for `NOT_SUPPLIED` or `NOT_RUN`; otherwise `{"stage_id": ..., "stage_kind": ..., "raw_status": ..., "manifest_sha256": ...}`. Expected ID/kind are retained even when the record is unreadable; actual status/hash are null unless verified. Never replace raw status with an inferred scientific state. |
| `artifact_refs` | IDs of verified `ArtifactRef` entries for this source run. Non-empty only for `AVAILABLE`. |
| `artifact_attempts` | Explicit attempted artifact metadata for non-available sources, including declared type/version, path when one exists, expected digest when one was declared, and stable validation reason code. These are references only; they are not consumed artifacts. |
| `producer_result_status` | The exact validated producer-native status when the accepted artifact supplies one; otherwise null. It is not an M14 observation state. |
| `producer_completeness` | `COMPLETE`, `PARTIAL`, `UNKNOWN`, or `NOT_REPORTED`, when a validated producer output reports completeness. |
| `reason_code` | Stable reason code for non-available outcomes; null for a valid available source. Free-form diagnostic text is not an identity key. |

Use exactly these source-outcome keys:

```json
{
  "source_id": "stable caller-declared token",
  "source_kind": "M4_CATALOGUE_OBSERVATIONS",
  "source_state": "AVAILABLE",
  "workflow_ref": {
    "relative_path": "runs/m4/workflow.json",
    "workflow_id": "producer-workflow-id"
  },
  "producer_stage": {
    "stage_id": "catalogue",
    "stage_kind": "catalogue_observations",
    "raw_status": "complete",
    "manifest_sha256": "64 lowercase hexadecimal characters"
  },
  "artifact_refs": ["sample-table-ref", "occurrence-summary-ref"],
  "artifact_attempts": [],
  "producer_result_status": null,
  "producer_completeness": "NOT_REPORTED",
  "reason_code": null
}
```

Each `ArtifactRef` has exactly these identity fields:
`artifact_id`, `source_id`, `producer_milestone`, `producer_stage_kind`,
`producer_stage_id`, `producer_workflow_id`,
`producer_run_manifest_sha256`, `artifact_type`, `contract_version`,
`relative_path`, `content_sha256`, and `raw_producer_status`.
`relative_path` is relative to the producer stage output directory; the
workflow record's declared `output_path` identifies that directory. An
`artifact_attempt` has `artifact_type`, `contract_version`, `relative_path`,
`expected_content_sha256`, and `reason_code`; nullable path/digest means no
such value was declared or no artifact path existed, never an invented path.
Every ID in `source_outcomes[].artifact_refs` resolves to exactly one
top-level `ArtifactRef`, and every top-level ref is listed by exactly one
source outcome. Its `source_id`, workflow ID, producer milestone/stage
kind/stage ID, raw status, and `producer_run_manifest_sha256` must equal the
selected source outcome and its verified M1 stage record; the latter digest
must equal `producer_stage.manifest_sha256`. Its path must appear in that
stage manifest's output inventory with the same content digest. Observation,
method, unit, control, and independence refs must be explicit as required by
their frozen field schemas. Any such ref to an optional M4/M7 source must
resolve to that source outcome's verified `ArtifactRef`; never resolve these
references by filesystem search.

`producer_completeness` is exactly `COMPLETE`, `PARTIAL`, `UNKNOWN`, or
`NOT_REPORTED`. `producer_result_status` is null or the validated
producer-native enum/string; M14 must not rewrite its scope or semantics.
`reason_code` is null only for `AVAILABLE`. For other states, use:

| Source state | Allowed reason codes |
| --- | --- |
| `NOT_SUPPLIED` | `NOT_SUPPLIED` |
| `NOT_RUN` | `PRODUCER_NOT_RUN` |
| `UNAVAILABLE` | `WORKFLOW_UNAVAILABLE`, `DEPENDENCY_UNAVAILABLE`, `ARTIFACT_UNAVAILABLE` |
| `FAILED` | `PRODUCER_FAILED` |
| `INTERRUPTED` | `PRODUCER_INTERRUPTED` |
| `INCOMPLETE` | `PRODUCER_NONTERMINAL`, `OUTPUT_INCOMPLETE` |
| `INVALID` | `PRODUCER_STAGE_NOT_FOUND`, `PRODUCER_IDENTITY_MISMATCH`, `UNSUPPORTED_PRODUCER_TYPE`, `ARTIFACT_VERSION_MISMATCH`, `ARTIFACT_DIGEST_MISMATCH`, `ARTIFACT_SCHEMA_INVALID`, `ARTIFACT_PATH_UNSAFE`, `ARTIFACT_INTEGRITY_FAILED`, `SOURCE_OUTCOME_INVALID` |

For `NOT_SUPPLIED`, `workflow_ref` and `producer_stage` are null. `NOT_RUN`
also has null references when no M1 workflow exists; if M1 records a skipped
producer stage, retain its workflow reference and raw `skipped` status.
Both states have empty artifact arrays, null producer result,
`NOT_REPORTED` completeness, and their state-specific reason code. For
`AVAILABLE`, workflow and producer-stage records are verified, raw stage
status is `complete`, the stage-manifest digest is present, at least one
`ArtifactRef` is present, attempted artifacts are empty, and reason is null.
For all other states, `artifact_refs` is empty and the reason code is
required. `UNAVAILABLE`, `FAILED`, `INTERRUPTED`, `INCOMPLETE`, and `INVALID`
retain the explicit workflow reference; `producer_stage.raw_status` and
`manifest_sha256` are null only when they cannot be read or do not exist.
`INCOMPLETE` may retain an `artifact_attempt` only when its format validator
positively identifies incompleteness; it is never consumed.

For each source kind with no supplied run, include exactly one row: use
`NOT_SUPPLIED` when the optional source was not provided, or `NOT_RUN` when a
source slot was declared but its producer was not executed. Do not include
both. `NOT_SUPPLIED` has no workflow reference, producer/run identity,
artifact reference, attempted artifact, path, or digest. `NOT_RUN` has none
unless M1 records the real producer stage as `skipped`; in that case retain
the actual workflow/stage reference and raw status. If one or more runs of a
source kind are declared, represent each run separately and do not add a
competing absence row for that kind. Multiple M4/M7 runs are allowed. An
omitted source kind is a malformed M14 manifest, not an implicit absence.

`NOT_RUN` means the caller declared a source slot but did not execute its
producer; it carries no invented workflow, stage, artifact, or filesystem
path. If a workflow records the producer stage as `skipped`, retain that real
workflow/stage reference and raw status under `NOT_RUN`. `UNAVAILABLE` means
an explicit source reference exists but its workflow, dependency, or artifact
cannot be read or obtained; retain the declared reference and a stable reason.
These states are not interchangeable.

### 1.1 Verification and source-state rules

All paths in M14 source references use forward-slash, workspace-relative
syntax rooted at the process working directory used to invoke the workflow.
Reject absolute paths, drive/UNC paths, traversal outside that root, symbolic
links, and paths not explicitly bound by the source outcome, workflow record,
or producer stage manifest. Resolve only those exact references; never scan
directories or search for a missing artifact.
`workflow_ref.relative_path` is relative to that root and points to
`workflow.json`; `ArtifactRef.relative_path` and
`artifact_attempt.relative_path` are relative to the producer stage output
directory. Moving the workspace root while keeping the same relative layout
does not change source identity.

An `ArtifactRef` in `source_artifacts` is a verified artifact, not an
assertion. It must bind `source_id`, producer milestone/stage kind and stage
ID, workflow ID, completed producer-stage manifest digest, exact artifact
type and contract version, relative artifact path, content SHA-256, and raw
producer stage status. Verify the workflow/stage relationship, stage manifest
status and output inventory, path containment, artifact digest, accepted
producer/type pair, and the current artifact validator before consuming it.
The referenced producer stage must be `complete`; the whole producer workflow
may have another terminal or active stage without changing this
stage-specific result.

| `source_state` | Required evidence and interpretation |
| --- | --- |
| `NOT_SUPPLIED` | Explicit source-kind metadata only. No artifact, path, run identity, or negative observation exists. |
| `AVAILABLE` | A completed producer stage and its stage manifest are verified; every referenced artifact has the accepted type/version and passes digest and schema validation. Preserve a producer's valid `PARTIAL` completeness separately; a complete M7 report of partial M6 inputs is still an available, validated M7 artifact. |
| `UNAVAILABLE` | An explicit reference is present, but a workflow/artifact/dependency cannot be obtained. Preserve a stable reason and any verifiable identity. No artifact rows are consumed. |
| `NOT_RUN` | The source was declared but no producer run was made. No path or fabricated run identity is allowed; if M1 records a real skipped stage, retain that workflow/stage reference and raw status. |
| `FAILED` | A verified M1 producer stage has raw status `failed`. Preserve that status and stable M14 reason `PRODUCER_FAILED`; consume no uncommitted output. |
| `INTERRUPTED` | A verified M1 producer stage has raw status `interrupted`. Preserve it separately from `failed`; consume no uncommitted output. |
| `INCOMPLETE` | The referenced producer stage is `pending`/`running`, or a format validator positively identifies an explicit incomplete/truncated outcome. Preserve available metadata, but consume no uncommitted or incomplete artifact. The selected stage's raw status controls; an unrelated active workflow stage does not change a completed or skipped source outcome. |
| `INVALID` | A reference is readable but incompatible, corrupt, or inconsistent: wrong producer/type/version, stage/run mismatch, bad digest, unsafe path, invalid schema, or integrity failure. Preserve the attempted reference and reason; consume no invalid artifact. |

Map a verified raw M1 producer-stage status without reinterpretation:
`skipped` → `NOT_RUN`; `dependency_missing` or
`external_module_required` → `UNAVAILABLE`; `pending` or `running` →
`INCOMPLETE`; `failed` → `FAILED`; `interrupted` → `INTERRUPTED`.
`complete` becomes `AVAILABLE` only when the referenced stage manifest and
accepted artifact verify. If the completed stage did not declare the requested
artifact, use `UNAVAILABLE/ARTIFACT_UNAVAILABLE`. If its stage manifest
declares the artifact but the file is missing, changed, corrupt, or fails its
validator, use `INVALID` with the matching integrity/schema reason. A missing
or unreadable explicitly referenced workflow file is `UNAVAILABLE`; a
readable but malformed workflow/stage record is `INVALID`.

If a stage is complete and its M7 validation report says `partial` because
some M6 inputs were unavailable or failed, the M7 artifacts remain
`AVAILABLE`; set `producer_completeness=PARTIAL` and preserve the M7 result
status. Do not relabel a valid, complete accounting of partial upstream
evidence as a truncated M7 artifact. M4/M7 currently have no general
truncation outcome record. A malformed or truncated byte stream without a
validated format-level incomplete marker is `INVALID`, not a guessed
`INCOMPLETE`.

Only a producer-native, validated result that explicitly names its scope may
be represented as `NO_SCOPED_SIGNAL`. For example, M7
`NO_RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS` is scoped to that M7
comparison. An empty M4 table or an omitted source row is not a negative
observation. `NO_SCOPED_SIGNAL` is producer-result context, never a synonym
for `NOT_SUPPLIED`, `NOT_DETECTED_WITHIN_SCOPE`, or “no association.”

Invalid, unavailable, failed, interrupted, not-run, and incomplete optional
sources do not block valid independent sources. Keep each outcome in the
result bundle; exclude only artifacts that did not verify. If a caller-authored
M14 observation cites a source artifact that did not verify, that observation
cannot be counted: retain the validation finding, and resolve the frame using
the precedence in §2. Conflicting but individually valid evidence remains
`CONFLICTING`, not `INVALID`.

## 2. Frame, evidence, and result precedence

Keep four axes separate:

1. **M1 execution lifecycle:** `complete`, `failed`, `interrupted`, and the
   other existing workflow states. This reports whether the handler ran and
   committed outputs.
2. **Optional-source outcome:** the source state and producer-native
   completeness/result described in §1.
3. **M14 frame/evidence state:** whether the caller-declared pair/unit frame is
   empty, complete, incomplete, or structurally invalid, and the explicit
   candidate/helper row states.
4. **M14 computation result:** one of the frozen M14 result states.

Optional M4/M7 sources never become required M1 stage inputs. M1's ordinary
typed handoff requires a completed stage and rejects a missing, failed,
interrupted, or corrupt input before the M14 handler can classify it. M14
therefore resolves optional sources from its explicit manifest references
with its own `dependency_inspector(config)` and handler, using the existing
workflow records, stage manifests, checksums, path rules, and artifact
validators. Per-source problems remain nested under a top-level dependency
status of `available`, so one optional failure does not become M1
`dependency_missing`.

Use this exact frame/result precedence:

1. A runtime exception or process interruption of the M14 handler leaves M1
   `failed` or `interrupted` respectively; do not publish or reuse an M14
   result bundle.
2. A structurally invalid caller manifest (top-level schema, duplicate
   identity, or foreign-key failure that prevents the declared frame from
   being interpreted) yields M14 `INVALID_INPUT`.
3. In a nonempty declared pair/unit frame, reject row-level invalid states or
   provenance and retain independently valid rows. If at least one supplied
   observation row remains accepted but any declared pair/unit is missing or
   rejected, yield M14 `INCOMPLETE`; if every nonempty supplied observation
   row is rejected, yield `INVALID_INPUT`. An empty observation list against a
   nonempty frame is `INCOMPLETE`. For `INCOMPLETE`, report accepted counts as
   observed only with `frame_complete=false`, never as a complete denominator.
4. `NOT_EVALUATED` applies only when no pair/unit is in scope and no
   observation row is supplied. This includes an all-empty baseline and an
   explicitly declared zero-unit scope.
5. A complete, nonempty frame with zero jointly tested/evaluable pair/unit
   rows yields `INSUFFICIENT_MATCHED_EVIDENCE`.
6. A complete frame with at least one jointly tested/evaluable pair/unit row
   yields `COMPLETED_DESCRIPTIVE`, even when a 2×2 cell is zero or valid
   conflicting/non-evaluable rows are also present.

An invalid optional source is an outcome about that source; it does not by
itself make the caller-authored frame invalid. If an invalid optional
reference prevents a row from being counted, reject that row and apply step 3
above. A missing required row is never filled with
`NOT_DETECTED_WITHIN_SCOPE`.

| Case | Source state | Frame/evidence state | M14 result |
| --- | --- | --- | --- |
| Valid caller frame; optional M4/M7 not supplied | `NOT_SUPPLIED` | Complete; caller states determine evaluability | `COMPLETED_DESCRIPTIVE` or `INSUFFICIENT_MATCHED_EVIDENCE`; never a negative from absence |
| Valid caller frame; optional source unavailable, not run, failed, interrupted, incomplete, or invalid | Exact source outcome retained | Complete if every required pair/unit row is valid; otherwise incomplete | From the caller frame; optional status does not override it |
| Required caller manifest structurally invalid; optional source valid | Optional source remains `AVAILABLE` | Invalid required input | `INVALID_INPUT` |
| Required M14 handler fails or is interrupted | Any source states already verified remain provenance only | No committed M14 frame result | M1 `failed` or `interrupted`; no M14 output reuse |
| Required frame has a scoped non-detection and optional source is absent | `NOT_SUPPLIED` | Complete and evaluable under the declared method/scope | `COMPLETED_DESCRIPTIVE`; report the corresponding cell, not “no association” |
| Required frame has missing rows while an optional source is valid | `AVAILABLE` for valid source | Incomplete; keep valid observed rows, exclude missing units | `INCOMPLETE` |
| Two individually valid records conflict for one pair/unit | Both sources remain `AVAILABLE` | One explicit `CONFLICTING` observation with at least two distinct provenance refs; excluded from 2×2 cells | `COMPLETED_DESCRIPTIVE` if another row is evaluable; otherwise `INSUFFICIENT_MATCHED_EVIDENCE` |
| Corrupt optional source plus an independent valid source | `INVALID` plus `AVAILABLE` | Count only caller rows with verified provenance | Result follows frame precedence; the corrupt source is not a negative |
| All optional sources unavailable; complete caller frame | All `UNAVAILABLE` | Caller frame/evaluability unchanged | `COMPLETED_DESCRIPTIVE` or `INSUFFICIENT_MATCHED_EVIDENCE` |
| Selected producer stage is nonterminal | `INCOMPLETE`; do not consume output | Reject any row claiming a state from its uncommitted artifact; valid rows remain, and the declared frame has a hole | `INCOMPLETE` when accepted rows remain; `INVALID_INPUT` only if every nonempty supplied row is rejected |
| M7 has a valid partial report due to M6 gaps | `AVAILABLE`, completeness `PARTIAL` | M14 caller frame remains independently assessed | Result follows frame precedence; preserve M7 gap status without converting it to an M14 negative |

`CONFLICTING_VALID_EVIDENCE != INVALID_EVIDENCE`.
`INCOMPLETE_FRAME != NO_ASSOCIATION_SIGNAL`.
`FAILED_SOURCE != NO_ASSOCIATION_SIGNAL`.
`OPTIONAL_NOT_SUPPLIED != NO_ASSOCIATION_SIGNAL`.
`NOT_SUPPLIED != UNAVAILABLE != NO_SCOPED_SIGNAL`.
`ASSOCIATION != DEPENDENCE`.

The only countable “not detected” cell remains a caller-authored
`NOT_DETECTED_WITHIN_SCOPE` row with `tested=true`, a valid `MethodRef`, a
declared detection scope, and declared denominator membership. No source
outcome, zero-row artifact, failed run, or absent reference can create it.

## 3. Canonical M14 identity, reuse, and serialization

Define three related identities and do not conflate them:

* `m14_semantic_input_sha256` is SHA-256 over the canonical, validated M14
  semantic projection. It covers dataset/schema/semantic versions, normalized
  caller observations and reasons, unit and parent relationships, study and
  control labels, method/scope/detection-limit fields, pair membership and
  denominators, each declared source kind/state, and verified artifact types.
  Producer-native result/completeness is provenance-only in this baseline
  because M14 preserves but does not use those fields to interpret caller
  observations. It excludes
  producer run IDs, raw stage-manifest/content digests, filesystem roots,
  absolute/relative paths, timestamps, host/platform values, workflow fields
  unrelated to the selected stage, unreferenced artifacts, and input array
  order where the freeze defines that array as unordered.
* `m14_provenance_sha256` is SHA-256 over every declared source outcome and
  selected artifact: stable source IDs/kinds/states, workflow IDs, producer
  stage IDs/kinds/raw statuses, producer-native result/completeness,
  stage-manifest digests, artifact IDs/types/versions/raw content digests,
  validation state/reason codes, and row-bound provenance refs. It excludes
  paths, workspace roots, standalone workflow timestamp fields, unrelated
  workflow-stage rows, and unreferenced files. The exact digest of a selected
  stage manifest remains provenance; changing any bytes in that selected
  manifest therefore changes provenance/composite identity, even when
  scientific meaning is unchanged.
  Different producer runs or exact source bytes can therefore have the same
  scientific semantic identity but a different provenance identity.
* `m14_cache_identity_sha256` is SHA-256 over the canonical JSON object with
  exactly these keys and value types:
  `{"schema":"m14-cache-identity-v1","stage_id":"m14_descriptive_observations","stage_version":"1","stage_registration_sha256":<64 lowercase hex>,"semantic_input_sha256":<64 lowercase hex>,"provenance_sha256":<64 lowercase hex>,"implementation_sha256":{"satellite_discovery/m14_descriptive_observations.py":<64 lowercase hex>},"contract_semantics":<artifact_contracts.semantic_identity result for the sorted set of verified consumed M4/M7 types plus all three M14 output types>}`.
  This binds scientific meaning to exact verified evidence and implementation
  without treating file locations as scientific data.
* The M1 stage cache key is the existing stage-scoped operational key. It
  additionally partitions by M14 stage ID/version/registration and hashes the
  normalized config and dependency-inspector report. M14 must normalize
  workspace-relative references and all unordered arrays before this key is
  built. Moving the workspace root with the same relative layout does not
  alter either identity. An internal reference-path change may cause a
  conservative cache miss, but never changes `m14_semantic_input_sha256`.

The dependency inspector projects only the explicitly selected M1 workflow
and producer-stage record; workflow-level timestamps, host fields, unrelated
stage rows, and unreferenced artifacts are excluded. The exact digest of a
selected producer-stage manifest remains source provenance: changing that
selected manifest changes provenance/composite identity even if the scientific
semantic projection and counts stay the same. It is not a scientific change.

The canonical semantic projection uses schema tag
`m14-semantic-input-v1`; the provenance projection uses
`m14-provenance-v1`. Both use UTF-8 JSON, sorted object keys, compact
separators, `ensure_ascii=false`, and rejection of NaN/Infinity. The semantic
projection has exactly these top-level keys: `schema`, `dataset_id`,
`input_schema`, `semantic_version`, `sampling_units`, `evaluated_pairs`,
`observations`, and `source_semantics`. Project unit rows without
`source_refs`, `independence_ref`, or a control-role provenance ref; project
observation rows without `source_refs` or method provenance refs. Retain all
other normalized fields used by validation, grouping, or counting.
For this freeze, `input_schema` is `m14-input-v1` and `semantic_version` is the
string `"1"`. Increment the semantic version when normalization, denominator,
state, or counting interpretation changes without an input-schema change.

`source_semantics` contains one object per declared source run, sorted by
canonical serialized object bytes and retaining duplicates. Each object has
exactly `source_kind`, `source_state`, and sorted
`verified_artifact_types`. For non-available outcomes, the type list is
empty. Exclude source IDs,
workflow/run IDs, reference IDs, file paths, reason codes, and raw file
digests from this projection. In this baseline, do not include
`producer_result_status` or `producer_completeness`; keep them in provenance.
If a future M14 computation uses either value to interpret evidence, bump the
semantic version and add that field explicitly.

The provenance projection contains source/artifact IDs and states,
workflow/run/stage IDs and raw statuses, producer-native
result/completeness, stage-manifest digests, artifact
type/version/content digests, validation state/reason codes, non-available
`artifact_attempts` type/version/expected digest/reason fields, and row-bound
unit/observation/method/control/independence provenance references. Exclude
paths, workspace roots, timestamps, unrelated workflow-stage rows, and
unreferenced files. This keeps producer identity and exact source bytes in
provenance without making them scientific inputs.

Sort source outcomes by `(source_kind, source_id)`; source/artifact references
by stable IDs; units by `unit_id`; evaluated pairs by
`(candidate_id, helper_id)`; each pair's `unit_ids`, parent IDs, and
provenance-ref lists lexicographically; observation rows by the freeze's
null-first study/unit/candidate/helper/observation key; and strata/cells by
their declared key fields with null before declared values. Reject duplicate
values where the freeze requires uniqueness; do not silently deduplicate.
Preserve order only for arrays explicitly declared ordered by a producer
contract.

Parse each finite detection-limit value as an exact decimal. Normalize it to
base 10 with no exponent or insignificant trailing zeroes in both the
semantic projection and emitted JSON number; `1`, `1.0`, and `1e0` therefore
serialize identically as `1`. The M14 local serializer must emit normalized
decimal tokens as JSON numbers. Canonical M14 document serialization is UTF-8
with no BOM, LF line endings, exactly one trailing newline, sorted object
keys, and no NaN/Infinity; row/stratum ordering is defined above. Hash the
exact serialized output bytes.

All three identity JSON objects use the canonical encoding above. Compute
`stage_registration_sha256` from the existing
`_stage_cache_registration_identity` object using that encoding. Keep M14
runtime logic in the named M14 module; M14 artifact-validator behavior is
versioned by its contract semantic identities, and registration behavior is
bound by the stage-registration digest. If an additional M14-owned runtime
module is introduced, bump `m14-cache-identity-v1` and list that file
explicitly before using it.

Outer JSON whitespace and LF/CRLF differences do not change the semantic
projection. For text source artifacts, the raw content digest remains an
integrity/provenance field; a line-ending-only byte change may require a
provenance refresh/cache miss, but does not change the scientific semantic
identity or descriptive counts. M14 implementation-source identity must
normalize CRLF to LF before hashing its explicitly listed M14-owned source
files. Do not normalize arbitrary source bytes or alter existing M1–M13
identity rules.

The identity must include the M14-local schema/semantic version, M14 stage
version, exact M4/M7 contract semantic identities actually consumed, and a
stage-scoped implementation digest. It must not include M13 types/code,
whole-package source digests, `workflow.json` fields for unrelated stages,
generated times, machine paths, or unreferenced optional files. A change to
M14 rules or a referenced upstream artifact invalidates M14 only. Keep
M1–M13 identities unchanged for M14-only package changes by maintaining the
existing accepted LF/CRLF source-digest mapping described in §4; do not alter
their cache algorithms or semantic identities.

Before reuse, verify the M14 cache identity; stage manifest, exact output
inventory, regular-file/path containment, output SHA-256 values, M14 output
contract validators, and the result bundle's output hashes. Reject and
recompute on any mismatch, missing file, wrong type/version, changed source
digest, stage/run mismatch, or post-commit tampering. Keep input identity
separate from output hashes to avoid self-reference. These checksum checks
establish local integrity and consistency, not a cryptographic signature or
external producer authenticity.

The result bundle records hashes for `m14_observation_table` and
`m14_descriptive_summary`, not its own file. The M1 stage manifest records
hashes for all three outputs, including `m14_result_bundle`; verify both
layers before reuse.

## 4. Infrastructure decision and claim boundary

No shared architectural capability is missing. The current registry supports
M14-local config normalization, dynamic stage registration, a
`dependency_inspector(config)`, typed input/output contract declarations, and
a handler-scoped `cache_implementation_identity`. The workflow runner records
stage lifecycle and verifies completed stage manifests, output digests,
contracts, and reuse. `artifact_contracts.semantic_identity()` is scoped to
the contract types a stage consumes.

Cache isolation also uses one existing compatibility hook.
`reproducibility.environment()` fingerprints all package `.py`/`.json` files.
A stage without `cache_implementation_identity` uses that package digest
through `_legacy_package_cache_digest`;
`m12_legacy_cache_compatibility.txt` maps an accepted current LF/CRLF source
digest to the preserved legacy digest. The M14 handler will be scoped, so its
own key uses its exact M14-owned source-file digests and selected contract
semantics instead of the package digest.

To keep unscoped M1–M13 stage keys stable for an M14-only source change, the
implementation release must refresh both accepted LF and CRLF digests in that
existing compatibility file while preserving the current legacy baseline. If
a non-M14 implementation change is part of the same update, use the normal
compatibility rebaseline that invalidates affected earlier stages. Future
M14-only code changes must refresh the accepted digest again; this is
maintenance through an existing versioned hook, not a new workflow/cache
capability. The synthetic gate must verify both source-line-ending mappings
and prove that only M14's scoped key changes. If this compatibility record
cannot be safely maintained, the cache-isolation claim is not met.

The generic M1 typed-input resolver only hands a stage completed, verified
artifacts; it does not deliver unavailable/failed/incomplete optional inputs
to the handler. That is a known integration limit, not a shared blocker:
M14 keeps optional outcomes in its own explicit manifest records and uses an
M14-local resolver/inspector to verify only declared workspace-relative
references. A non-available per-source state must not be returned as the
dependency inspector's top-level failure status. M14 must not use or extend
the M5-only execution-outcome sidecar and must not depend on M13. To preserve
typed `INVALID_INPUT`, the M14 config validator must retain JSON-serializable
semantic validation findings in the normalized config instead of raising for
those findings; the handler then emits a valid M14 error-result bundle. Only
an unparseable, non-object, or non-JSON-safe config that cannot be handed to a
stage is rejected by M1 preflight before an M14 result can exist.

M14 remains descriptive. It may report scoped co-detection counts and retain
source association context. Repeated co-detection, M7 recurrence, similarity,
or correlation is not evidence that a candidate depends on a proposed helper.
A future dependence claim requires claim-appropriate experimental evidence
establishing a causal requirement (for example, intervention with a suitable
comparison and rescue or equivalent evidence). This names an evidence class,
not a wet-lab protocol, and is not part of M14 implementation or acceptance.

For the synthetic baseline, required resources are only the Python
standard-library runtime, the existing artifact-workflow runner, and generated
offline fixtures. M4/M7 references are optional. Statistical models,
normalization, cohort selection, control adequacy, taxonomy/classification,
external callers, sequence databases, raw reads, and real datasets are
deferred or out of scope. Any real-data execution still requires a separate
purpose/access/terms/privacy approval. Experiments are not required to
implement this descriptive baseline; they are required only for any future
dependence claim.