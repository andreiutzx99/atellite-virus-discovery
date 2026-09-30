# M14 final implementation readiness

- **Review date:** 30 September 2026
- **Authority snapshot:** synchronized `main` at `291884c25a4ce5cb203a2cae5ee03dd2d1271f03`
- **Scope:** frozen descriptive synthetic/offline M14 baseline only

**Review result:** the M14 contract clarification resolves the identified
readiness questions; the final clarification verdict appears at the end.

## Executive disposition

The M14 contract's three implementation blockers are resolved in the
[normative contract clarification](M14_CONTRACT_CLARIFICATION.md), and the
[M14 freeze](../M14_CONTRACT_FREEZE.md) and
[implementation execution plan](M14_IMPLEMENTATION_EXECUTION_PLAN.md) now
point to those decisions. M14 remains **PLANNED / NOT IMPLEMENTED**.

The existing workflow/artifact infrastructure is a viable additive host. It
already supplies typed M4/M7 artifacts, stage and workflow lifecycle records,
completed-stage manifests, checksums, path containment, contract validation,
stage-scoped cache hooks, and verified cache reuse. The missing M14 behavior is
local: its schema/validator, explicit optional-source resolver, result bundle,
counting logic, and registration do not yet exist. The generic M1 input path
does not deliver a failed or missing optional artifact to a handler, but the
existing configuration-validation and dependency-inspection hooks support an
M14-local resolution path. Cache isolation also uses the existing legacy
source-digest compatibility hook: future M14-only package changes must refresh
its accepted LF/CRLF digests while preserving the legacy baseline. No new
shared cache capability is required.

No M14 stage, production code, tests, CI, M13 implementation, README, ROADMAP,
or real-data access was changed. No publication or merge was performed.

## 1. Authority set and M13 sequencing check

The frozen authority is the
[M14 contract freeze](../M14_CONTRACT_FREEZE.md). The
[pre-contract readiness](M14_PRECONTRACT_READINESS.md) and
[helper-association design research](M14_HELPER_ASSOCIATION_DESIGN_RESEARCH.md)
provide context and deferred directions; they do not override the freeze.
The [M12–M16 independent audit](M12_M16_INDEPENDENT_CONTRACT_AUDIT.md),
[fixture matrix](M12_M16_FIXTURE_MATRIX.md),
[validation logistics](M12_M16_VALIDATION_LOGISTICS.md),
[resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md), and
[decision register](M12_M16_DECISION_REGISTER.md) constrain synthetic
acceptance and resource boundaries. The
[M13 contract freeze](../M13_CONTRACT_FREEZE.md) and
[M13 handoff gap resolution](M13_HANDOFF_GAP_RESOLUTION.md) were checked only
to confirm the M14 boundary; no M13 implementation behavior is an M14 input.

At the audited main snapshot, the current
[roadmap](../ROADMAP.md) lists M1–M13 as implemented and M14–M16 as planned.
The separate M13 freeze and handoff retain earlier `PLANNED / NOT IMPLEMENTED`
wording. That status inconsistency is outside this M14 clarification. Either
status yields the same sequencing conclusion: the M14 freeze accepts only
caller-authored observations and the exact M4/M7 types in §2. It names no M13
producer or artifact type. **M13 is not a sequencing dependency.** Do not add
an M13 dependency to implementation order.

The final contract clarification changes only M14 documentation. It makes
normative the optional-source record, frame/result precedence, and canonical
identity defined below; it does not expand the M14 source allowlist or change
the descriptive/experimental claim boundary.

## 2. Input boundary and producer/run handoffs

M14 uses the existing allowlisted workflow runner,
`python -m satellite_discovery.artifact_workflow --manifest … --output …`.
Its required scientific input is a caller-authored `m14-input-v1` manifest
embedded in stage configuration. M4/M7 references are optional provenance and
context. M14 does not derive candidate/helper observations, methods, tested
flags, detection scopes, or denominators from their IDs or omitted rows.

| Frozen M14 source | Actual producer and typed interface | What it can establish | M14 handoff rule and current gap |
| --- | --- | --- | --- |
| M4 `catalogue_observations`: `sample_table`, `observation_table`, `occurrence_table`, `occurrence_summary` | Registered in `artifact_workflow.py` as dynamic-input `catalogue_observations`; `artifact_stage_handlers.catalogue_observations` reads explicitly supplied catalogues and emits `samples.csv`, `observations.csv`, `occurrences.csv`, `summary.json`, recurrence/comparison tables, and a report. M4 output contracts validate table shape and summary JSON. | Catalogue-derived presence and occurrence records, with source catalogue/FASTA provenance. The handler explicitly says it does not infer absence, read-level detection, independence, or function. | Accept only the frozen M4/type pairs. M4 does not supply M14's tested method/scope or complete candidate/helper pair/unit denominator. Empty/omitted M4 rows are not M14 negatives. |
| M4 `observations`: `occurrence_table`, `occurrence_summary` | The registered legacy `observations` stage consumes typed `sample_table` and `observation_table`; its outputs are a summary and descriptive recurrence/comparison tables. | A report over declared M4 observations, not the M14 pair/unit row contract. | Preserve as optional context only. Its output validators do not establish M14 methods, tested denominators, or state invariants. |
| M7 `independent_recurrence`: `m7_observation_table`, `m7_exact_recurrence_table`, `m7_independence_summary`, `m7_validation_report`, `m7_provenance_manifest` | `independent_recurrence.py` is registered as a dynamic-input stage. It consumes typed M6 reconstruction evidence, residual manifests, and optional canonical contigs, and writes the five typed M7 outputs plus a report. | Exact recurrence among individually supported M6 contigs and declared sample/run/study metadata. M7 can emit a complete, valid accounting whose `analysis_completeness` is `PARTIAL` because upstream M6 inputs were unavailable or failed. | Preserve M7 result, completeness, and provenance as M7-scoped context. `PARTIAL` does not mean the M7 file is truncated; M7 identifiers do not verify biological independence or create an M14 observation. |
| Caller-authored `sampling_units`, `evaluated_pairs`, `observations` | No current M4/M7 producer or M1 workflow artifact. The `m14-input-v1` parser, validator, and counter are not implemented. | Declares units, full pair/unit scope, one observation per pair/unit, method/scope, states, and provenance. | M14 must validate and count these rows directly. Missing rows never become negatives. |
| Optional-source outcome and source-reference record | Current M1 workflow manifests contain workflow and per-stage lifecycle state; completed stage manifests contain output inventories/digests. `artifact_contracts` supplies M4/M7 validators and `semantic_identity`. | A committed and integrity-checked artifact can be bound to its selected producer stage/run. Noncompleted source states can be read from explicit M1 workflow records. | Add M14-local `source_outcomes` and an explicit-reference resolver. Generic M1 typed inputs reject noncompleted/missing sources before handler entry, so they cannot alone implement optional-state reporting. Do not use filesystem discovery or invent absent artifact paths. |

`source_outcomes` is required metadata, not a new scientific artifact. For each
source kind with no supplied run, it contains either one `NOT_SUPPLIED` record
(source not provided) or one `NOT_RUN` record (declared slot but no producer
execution); never both. These records do not invent a path. A skipped M1
producer may retain its real workflow/stage reference under `NOT_RUN`. For
each supplied run, the record binds the exact workflow reference and stage
identity/status; an `AVAILABLE` run additionally binds the completed
stage-manifest digest and every consumed `ArtifactRef`. Invalid attempts
retain reference metadata and stable reason codes but are never consumed.
Multiple runs are separate source outcomes. The exact field and path rules are in the
[contract clarification, §1](M14_CONTRACT_CLARIFICATION.md#1-input-boundary-and-optional-source-records).

### Current workflow, artifact, and execution-outcome representation

* `stage_registry.py` provides `dynamic_inputs`, `config_validator`,
  `input_contracts`, `output_contracts`, and `dependency_inspector`. Its
  `validate_config` returns the normalized configuration that the runner uses.
  The M14 validator must preserve serializable semantic findings for the
  handler to report as `INVALID_INPUT`; only unparseable/non-object/non-JSON-safe
  configuration is rejected at M1 preflight.
* `artifact_workflow._resolve_stage_input` accepts direct typed files or
  earlier completed-stage artifacts. For same-workflow references it checks
  producer completion, manifest inventory, output path containment, digest,
  and artifact descriptor. It rejects a noncompleted producer rather than
  handing its state to the consumer.
* The runner's lifecycle states are `pending`, `running`, `complete`,
  `skipped`, `dependency_missing`, `external_module_required`, `failed`, and
  `interrupted`; workflow status can also be `partial`. There is no general M1
  `incomplete` or `corrupt` lifecycle state.
* `artifact_contracts` already knows the M4/M7 types. M4 table validators
  check declared CSV columns and M7 validators check M7-specific schemas,
  counts, statuses, and hashes. No `m14_observation_table`,
  `m14_descriptive_summary`, or `m14_result_bundle` contract/validator exists.
* The workflow cache builder includes stage ID/kind/version, normalized
  configuration, typed input digests/types, dependency-inspector output, and
  stage registration. When a handler supplies a scoped implementation
  identity it avoids the legacy whole-package source digest and supports
  input-contract semantic identity. `artifact_contracts.semantic_identity`
  isolates a stage to the contract types it consumes.
* `reproducibility.environment()` hashes all package `.py`/`.json` files.
  Handlers without scoped identities use that package digest via
  `_legacy_package_cache_digest`; the existing
  `m12_legacy_cache_compatibility.txt` maps accepted LF/CRLF digests to the
  preserved legacy digest. It can preserve earlier unscoped stage keys across
  M14-only source changes when its accepted digests are refreshed; the M14
  handler itself must use a scoped implementation identity.
* `execution_outcome.py` implements `m5-execution-outcome-v1`, with an
  explicit M13/M5 reference verifier. It is not a general M4/M7 outcome
  interface. M14 must read the generic M1 workflow/stage status and apply its
  own source-state mapping; it must not import, extend, or depend on the
  M5-only sidecar.

These are implementation gaps, not architectural blockers. M14 can keep all
optional source references in its configuration, register an M14-local
`dependency_inspector(config)` and config normalizer, return top-level
dependency status `available`, and nest each per-source outcome under its
source ID. The handler must re-read and verify every explicit reference before
consumption. Existing file, checksum, path, artifact-contract, and legacy
cache-compatibility primitives are sufficient; no shared handler-signature,
workflow-state, or cache-algorithm change is required. Refreshing the existing
compatibility entry for both line-ending forms is required for an M14-only
implementation release; it must preserve the current legacy baseline.

## 3. Source and observation state map

### Optional M4/M7 source outcomes

| M14 source state | Required evidence / validity | Current infrastructure representation | Invalid, conflicting, or incomplete variant |
| --- | --- | --- | --- |
| `NOT_SUPPLIED` | Explicit source-kind metadata only; no path, artifact, producer ID, or digest. | No current M1 stage state; M14 must add the typed record. | Omitted source-kind record is malformed input, not `NOT_SUPPLIED`. |
| `AVAILABLE` | Producer stage `complete`; completed stage manifest and every explicit artifact reference pass producer/type/version, path, digest, and schema checks. | M1 workflow stage status, stage manifest output hashes, M4/M7 artifact validators, and checksums exist. | Wrong workflow/stage/run, unsupported type, schema failure, path escape, symlink, or digest mismatch is `INVALID`, not absence. |
| `AVAILABLE` + producer `NO_SCOPED_SIGNAL` | Preserve the exact producer-native status and its explicit scope. | M7 summary can say `NO_RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS`; M4 empty tables do not establish tested absence. | Do not map an empty/omitted M4 row, M7 unavailable/failed input, or `NOT_SUPPLIED` to producer no-signal. |
| `AVAILABLE` + `PARTIAL` completeness | Producer emitted a valid completed artifact that explicitly accounts for upstream gaps. | M7 `m7_validation_report.status=partial` and summary `analysis_completeness=PARTIAL` are validator-accepted. | Preserve partial upstream statuses. Do not call it a truncated M7 artifact or use it to complete M14's frame. |
| `UNAVAILABLE` | Explicit attempted reference; workflow/dependency/artifact cannot be obtained; stable reason code and any verifiable identity retained. | M1 has `dependency_missing` and `external_module_required`; unreadable/missing files are caught by existing path operations. | Distinct from an absent source declaration and a producer result with no signal. |
| `NOT_RUN` | Source slot was declared but its producer did not execute; no invented workflow or artifact path. | M1 `skipped` is terminal and maps to `NOT_RUN`; if no workflow was created, keep both references null. | A missing workflow reference with no declaration is not enough to claim `NOT_RUN`. |
| `FAILED` | Verified producer stage raw status is `failed`; no uncommitted outputs consumed. | M1 stage lifecycle records `failed`; M4/M7 do not use a general typed failure sidecar. | Keep separate from `INTERRUPTED`, `INVALID`, and `NO_SCOPED_SIGNAL`. |
| `INTERRUPTED` | Verified producer stage raw status is `interrupted`; no uncommitted outputs consumed. | M1 stage lifecycle records `interrupted`. | Never collapse to generic failure or negative evidence. |
| `INCOMPLETE` | Selected producer stage is pending/running or a format validator positively identifies an incomplete/truncated status. No incomplete artifact is consumed. | M1 `pending`/`running` represent nonterminal work; M4/M7 have no general truncation outcome code. | A malformed byte stream without a verified incomplete marker is `INVALID`. A valid M7 partial accounting remains `AVAILABLE` + `PARTIAL`. |
| `INVALID` | Explicit attempt fails path, workflow/stage identity, producer/type/version, digest, schema, or integrity checks. Preserve stable reason and attempted reference; consume no invalid artifact. | Existing M1 and artifact validators detect many integrity/schema failures; M14 must translate them into its per-source outcome. | `CONFLICTING` valid observations are not invalid artifacts. Corruption is not `UNAVAILABLE` or no-signal. |

The M14 source resolver is explicit-reference-only. The workflow reference path
is workspace-relative to the runner's working directory; an artifact path is
relative to the producer stage output directory. Absolute paths, traversal,
symlinks, and directory searching are rejected. `NOT_SUPPLIED` and `NOT_RUN`
do not create fake paths. Existing M1 execution outcome records do not
provide an M4/M7 truncation code, so only a verified nonterminal stage or a
format-specific positive marker may become `INCOMPLETE`; otherwise malformed
or digest-mismatched content is `INVALID`.

The exact M1 status mapping is: `skipped` → `NOT_RUN`;
`dependency_missing`/`external_module_required` → `UNAVAILABLE`;
`pending`/`running` → `INCOMPLETE`; `failed` → `FAILED`;
`interrupted` → `INTERRUPTED`. `complete` yields `AVAILABLE` only after
manifest and artifact verification. A completed stage that did not declare
the requested output yields `UNAVAILABLE/ARTIFACT_UNAVAILABLE`; a declared
output that is missing, changed, or invalid is `INVALID`. A missing/unreadable
explicit workflow reference is `UNAVAILABLE`; a readable malformed workflow
or stage record is `INVALID`.

### Candidate/helper observation states

| Observation state | Required M14 evidence | Current upstream representation | Counting and invalid variant |
| --- | --- | --- | --- |
| `PRESENT` | `*_tested=true`; valid `MethodRef`, scope and method/run provenance; no reason. | M4 may report supplied presence but not the full M14 method/tested contract. | Evaluable only with a valid jointly tested counterpart. Reject untested, methodless, reason-bearing, or out-of-frame rows. |
| `NOT_DETECTED_WITHIN_SCOPE` | `*_tested=true`; valid `MethodRef`; explicit detection scope; no reason. | Neither M4 nor M7 provides this M14 scoped negative row. | Enters a 2×2 cell only with denominator membership and a jointly tested/evaluable counterpart. Never infer from omitted rows. |
| `UNKNOWN` | Non-empty source-grounded reason; method ref required if tested. | Upstream null/unknown metadata may remain unknown but is not an M14 row. | Separate count; never a negative. |
| `UNAVAILABLE` | Non-empty reason; `*_tested=false`. | M7 can preserve unavailable M6 input status inside a completed M7 output; M1 can report dependency absence. | Separate count; never a negative. |
| `NOT_APPLICABLE` | Explicit declaration, non-empty reason, `*_tested=false`. | No equivalent M14 row in M4/M7. | Separate count; not a synonym for missing or untested. |
| `CONFLICTING` | At least two distinct provenance refs support incompatible observations; reason; `*_tested=false`. | M4/M7 can contain source rows but do not provide this M14 conflict row. | Valid conflict is counted separately and excluded from all four cells. Never resolve by row order. |

The candidate/helper states describe declared observations under a stated
method/scope, not biological classification. A source outcome belongs to a
different axis. A valid optional source with no scoped signal cannot create a
`NOT_DETECTED_WITHIN_SCOPE` row. Parent relationships, run IDs, study IDs,
controls, and M7 recurrence do not imply independence or a universal
observational unit.

## 4. Frame/result precedence and mixed-source behavior

The exact precedence is normative in the
[contract clarification, §2](M14_CONTRACT_CLARIFICATION.md#2-frame-evidence-and-result-precedence).
In brief:

1. M1 handler runtime failure/interruption remains M1 `failed`/`interrupted`;
   no M14 result artifact is reusable.
2. Invalid required M14 structure, duplicated identities, invalid required
   states, or bad required provenance yields typed M14 `INVALID_INPUT`.
3. A nonempty declared frame with a missing/rejected pair/unit row yields
   `INCOMPLETE`. Keep independent accepted rows; label their counts observed
   only, not as a complete declared denominator.
4. A zero-unit declared scope yields `NOT_EVALUATED`.
5. A complete nonempty frame with no jointly tested/evaluable rows yields
   `INSUFFICIENT_MATCHED_EVIDENCE`.
6. A complete frame with at least one jointly tested/evaluable row yields
   `COMPLETED_DESCRIPTIVE`.

An optional-source error does not automatically invalidate the caller-authored
frame. If a row cites an invalid source, reject that row; retain other valid
rows. A remaining frame gap is `INCOMPLETE`; if every nonempty supplied row
is rejected, use `INVALID_INPUT`. Valid but conflicting source evidence is
represented as one `CONFLICTING` observation with distinct provenance, not as
an invalid artifact. Optional source states never override the frame result.

| Mixed case | Required typed result |
| --- | --- |
| Required caller frame valid; optional source absent, unavailable, failed, interrupted, not run, incomplete, or invalid | If the frame is complete and evaluable: `COMPLETED_DESCRIPTIVE`; if complete and non-evaluable: `INSUFFICIENT_MATCHED_EVIDENCE`; the source state remains separately visible. |
| Required caller row is scoped non-detection; optional source absent | Complete evaluable frame; `COMPLETED_DESCRIPTIVE`; report the cell, not “no association.” |
| Required frame incomplete; optional source valid | `INCOMPLETE`; retain valid rows/source refs, and do not imply missing units are negative. |
| Required manifest invalid; optional source valid | `INVALID_INPUT`; optional evidence cannot repair required M14 structure. |
| Two valid sources conflict for a pair/unit | One `CONFLICTING` row; descriptive result only if another row is evaluable, otherwise `INSUFFICIENT_MATCHED_EVIDENCE`. |
| Corrupt optional source plus independent valid source | Corrupt source `INVALID`, independent source `AVAILABLE`; consume only verified artifacts and follow caller-frame precedence. |
| All optional sources unavailable | Complete caller frame still computes; no optional-source failure becomes a negative or aggregate unavailable result. |
| Selected producer stage is pending/running | Source `INCOMPLETE`; a row claiming a state from that uncommitted artifact is `INVALID_INPUT`; otherwise a missing row leaves the frame `INCOMPLETE`. |
| M7 valid partial accounting | Source `AVAILABLE`, completeness `PARTIAL`; M14 result remains based on caller rows. |

## 5. Acceptance traceability matrix

Each row below is an offline synthetic acceptance case. The state tuple is
**source state → frame state → evidence state → aggregate M14 result**. M1
lifecycle is listed separately where it is not `complete`. These are required
tests for the next implementation task; they are not claimed as existing M14
tests.
For any complete frame, the result is `COMPLETED_DESCRIPTIVE` when at least
one pair/unit row is jointly tested and evaluable; otherwise it is
`INSUFFICIENT_MATCHED_EVIDENCE`.

| Fixture | Source state | Frame state | Evidence state | Expected typed outcome |
| --- | --- | --- | --- | --- |
| `optional_supplied_valid_m4` | `AVAILABLE` | Complete | Valid caller rows; source refs verify | `COMPLETED_DESCRIPTIVE` when any jointly evaluable row exists; M1 `complete`. |
| `optional_supplied_valid_m7` | `AVAILABLE` | Complete | M7 metadata retained; no independence upgrade | `COMPLETED_DESCRIPTIVE` if any row is jointly evaluable, otherwise `INSUFFICIENT_MATCHED_EVIDENCE`; M1 `complete`. |
| `optional_not_supplied` | `NOT_SUPPLIED` | Complete | Caller rows independently evaluable | `COMPLETED_DESCRIPTIVE`; no path or artifact is created. |
| `optional_not_supplied_zero_scope` | `NOT_SUPPLIED` | Zero-unit | No observation rows | `NOT_EVALUATED`; denominator zero. |
| `optional_valid_no_scoped_signal` | `AVAILABLE` with producer-native scoped no-signal | Complete | M7 recurrence status retained; no M14 negative inferred | `COMPLETED_DESCRIPTIVE` if any row is jointly evaluable, otherwise `INSUFFICIENT_MATCHED_EVIDENCE`; M1 `complete`. |
| `producer_result_metadata_change_only` | Same `AVAILABLE` source kind/type/state | Same complete frame | M7 result/completeness metadata changes but caller rows do not | Same semantic digest and counts; provenance/composite identity changes and result bundle refreshes. |
| `optional_unavailable` | `UNAVAILABLE` | Complete | Caller evidence independent of missing source | `COMPLETED_DESCRIPTIVE` if any row is jointly evaluable, otherwise `INSUFFICIENT_MATCHED_EVIDENCE`; no negative. |
| `optional_dependency_missing` | `UNAVAILABLE` | Complete | M1 `dependency_missing` preserved as source metadata | Same complete-frame result rule; M14 dependency inspector remains top-level `available`. |
| `optional_not_run` | `NOT_RUN` | Complete | No producer execution; if M1 records `skipped`, retain that real workflow/stage reference | Same complete-frame result rule; distinct from `NOT_SUPPLIED`. |
| `optional_failed` | `FAILED` | Complete | M1 stage status `failed`; no partial output consumed | Same complete-frame result rule; source failure preserved. |
| `optional_interrupted` | `INTERRUPTED` | Complete | M1 stage status `interrupted`; no partial output consumed | Same complete-frame result rule; source interruption preserved. |
| `optional_nonterminal_source` | `INCOMPLETE` | Complete or incomplete as declared | Do not consume uncommitted artifacts; reject rows that cite them | If no rows depend on it, use the complete-frame result rule; if rejected rows leave holes, `INCOMPLETE` when accepted rows remain, otherwise `INVALID_INPUT`. |
| `optional_explicit_truncated_marker` | `INCOMPLETE` | Complete | Positive format-level incomplete marker; no source rows consumed | Same complete-frame result rule; source incompleteness preserved. |
| `optional_malformed_truncated_bytes` | `INVALID` | Complete | Parse/schema/digest failure, not a verified incomplete marker | Same complete-frame result rule if caller rows are independent; invalid source excluded. |
| `optional_invalid_type_or_version` | `INVALID` | Complete | Producer/type/version mismatch | Same complete-frame result rule; no incompatible rows consumed. |
| `required_no_signal_with_optional_absent` | `NOT_SUPPLIED` | Complete | Scoped `NOT_DETECTED_WITHIN_SCOPE` rows with method/test/scope | `COMPLETED_DESCRIPTIVE`; exact cells only, no no-association label. |
| `required_all_unknown_unavailable_conflicting` | Any valid optional mix | Complete | No jointly evaluable row | `INSUFFICIENT_MATCHED_EVIDENCE`; all row states remain separate. |
| `required_failure_invalid_manifest` | Any valid optional mix | Invalid | Duplicate IDs, bad required state/method/ref | M14 `INVALID_INPUT`; optional data cannot repair it. |
| `handler_runtime_failure` | Any | No committed frame | Runtime exception | M1 `failed`; no M14 result bundle or reusable output. |
| `handler_interruption` | Any | No committed frame | Interrupted execution | M1 `interrupted`; no M14 result bundle or reusable output. |
| `mixed_valid_and_failed_source` | `AVAILABLE` + `FAILED` | Complete if all rows remain covered; otherwise incomplete | Valid independent rows retained | `COMPLETED_DESCRIPTIVE` or `INSUFFICIENT_MATCHED_EVIDENCE` for a complete frame; `INCOMPLETE` for a frame hole. |
| `mixed_valid_and_invalid_source` | `AVAILABLE` + `INVALID` | Complete if all rows remain covered; otherwise incomplete | Invalid-source-dependent rows rejected; independent rows retained | `COMPLETED_DESCRIPTIVE`, `INSUFFICIENT_MATCHED_EVIDENCE`, or `INCOMPLETE` from frame/evaluability. |
| `conflicting_valid_sources` | Both `AVAILABLE` | Complete | One `CONFLICTING` row with at least two distinct refs | `COMPLETED_DESCRIPTIVE` if another row is evaluable; otherwise `INSUFFICIENT_MATCHED_EVIDENCE`. |
| `corrupt_plus_independent_valid_source` | `INVALID` + `AVAILABLE` | Complete | Only verified source refs count | `COMPLETED_DESCRIPTIVE` if any row is jointly evaluable, otherwise `INSUFFICIENT_MATCHED_EVIDENCE`; corruption is not absence. |
| `missing_pair_unit_row` | Any | Incomplete | Missing row is not a negative | M14 `INCOMPLETE`; M1 `complete` if handler emits valid outputs. |
| `all_supplied_rows_rejected` | One or more `INVALID` | Invalid supplied evidence | No accepted observation row remains | M14 `INVALID_INPUT`; never successful empty output. |
| `multiple_helpers_same_candidate` | Available/absent mix | Complete | Separate helper strata and denominators | `COMPLETED_DESCRIPTIVE` or `INSUFFICIENT_MATCHED_EVIDENCE`; no helper pooling. |
| `multiple_runs_and_libraries_one_declared_unit` | Multiple available source runs | Complete | Parent/run relationships retained; count the declared unit, not each run | Frame-derived result; no inferred independence. |
| `multiple_studies_and_null_study` | Any valid mix | Complete | Distinct study strata; null remains explicit | Frame-derived result; no null/value merging. |
| `zero_scoped_pair` | Any | Zero-unit scope | No evaluated unit and no observation rows | `NOT_EVALUATED`; no negative claim. |
| `permuted_unordered_inputs` | Same source states | Same frame | Same normalized evidence | Same semantic digest, output order, output bytes and hashes. |
| `equivalent_detection_limit_tokens` | Same source states | Same frame | Numeric inputs `1`, `1.0`, and `1e0` represent the same limit | Same normalized semantic digest and canonical output bytes; JSON output remains a number. |
| `equivalent_workspace_relocation` | Same source refs/digests, relative layout preserved | Same frame | Same semantic rows | Same semantic identity and cache dependency; no absolute path emitted. |
| `source_state_identity_change` | `NOT_SUPPLIED` versus `UNAVAILABLE` for the same optional kind | Same caller frame | Caller rows unchanged | Semantic and composite identities differ because source state differs; result counts do not become negative. |
| `verified_source_type_change` | Same kind/state, different accepted M4/M7 type | Same caller frame | Same caller rows; both source types validate | Semantic and composite identities differ; counts follow caller rows. |
| `source_or_run_id_change_only` | Same kind/state/types/content; caller source/run IDs and references consistently renamed | Same caller frame | Same normalized evidence | Semantic identity and counts stay equal; provenance/composite identities differ and result bundle refreshes. |
| `lf_crlf_manifest_and_source` | Same logical source, raw text digest may differ | Same frame | Same parsed observation semantics | Same scientific semantic identity/counts; raw provenance digest exact; a provenance-refresh cache miss is allowed. |
| `m14_configuration_change` | Same sources | Same frame | A changed M14 semantic/config value | M14 cache miss; no M1–M13 identity change. |
| `relevant_upstream_artifact_change` | Changed verified content digest or producer-stage manifest | Same caller frame | Referenced source changed | M14 cache miss; M4/M7 stage outputs are not rewritten by M14. |
| `irrelevant_metadata_change` | Same selected stage manifest and artifacts | Same frame | Workflow-level timestamp, host root, unrelated stage metadata, or unreferenced artifact changes | Same semantic, provenance, and composite identities; none is added to the M14 projection. |
| `producer_workflow_or_stage_mismatch` | `INVALID` | Complete unless a dependent row is rejected | Workflow ID, stage ID/kind/status, or stage-manifest binding disagrees | If independent rows suffice, apply the complete-frame result rule; a dependent-row hole is `INCOMPLETE` if accepted rows remain, otherwise `INVALID_INPUT`. |
| `artifact_integrity_mismatch` | `INVALID` | Complete unless a dependent row is rejected | Artifact digest/schema/path check fails | Same dependent-row precedence; invalid content never becomes a negative. |
| `first_run_then_verified_reuse` | Same available outcomes | Same complete frame | Same identity | Reuse only after stage/output/contract/result-bundle verification; identical output hashes. |
| `tampered_or_stale_m14_output` | Any | Any | Stage manifest, output digest, contract, or bundle hash mismatch | Reject reuse and recompute; never return corrupted output as complete. |
| `linux_windows_python311_python312` | Identical canonical fixture bytes (fixed LF, written in binary) | Same frame | Same canonical ordering and serialized documents | Same semantic digest and M14 output bytes; no external resource or network access. |

Existing tests demonstrate reusable mechanics, not M14 acceptance:
[M4 artifact workflow tests](../../tests/test_artifact_workflow_m4.py) cover
typed handoffs, stage failures/interruption, integrity, and reuse;
[M7 recurrence tests](../../tests/test_independent_recurrence.py) cover typed
M6 input validation, provenance, unavailable/failed M6 inputs, and output
hashes; [stage cache identity tests](../../tests/test_stage_cache_identity.py)
cover stage-scoped identities and isolation. There are no M14-specific
contracts, stage, fixtures, or tests on the audited main snapshot.

## 6. Cache identity, provenance, and deterministic output

The normative cache contract is in
[M14 contract clarification §3](M14_CONTRACT_CLARIFICATION.md#3-canonical-m14-identity-reuse-and-serialization).
It defines three identities:

* `m14_semantic_input_sha256` covers dataset and M14 schema/semantic versions,
  normalized sampling-unit/pair/observation fields and reasons, methods,
  scopes, limits, denominator membership, each source kind/state, and
  verified artifact types. Producer-native result/completeness is provenance
  only in this baseline because M14 does not use it to interpret caller
  observations. It excludes source IDs, workflow/run IDs, row-level
  provenance reference IDs, source byte digests, paths, timestamps,
  host/platform, unreferenced files, and irrelevant workflow fields.
* `m14_provenance_sha256` binds source IDs/kinds/states, producer
  workflow/run/stage IDs and raw statuses, producer result/completeness,
  stage-manifest digests, accepted artifact types/versions/raw content
  digests, validation state/reason codes, non-available artifact-attempt
  type/version/expected-digest/reason fields, and row-bound unit/observation/
  method/control/independence provenance refs. It excludes paths, workspace
  root, standalone workflow timestamp fields, and unrelated stage rows; the
  exact selected stage-manifest digest remains provenance.
* `m14_cache_identity_sha256` canonically binds the semantic and provenance
  hashes to stage ID `m14_descriptive_observations`, stage version `1`, the
  existing stage-registration identity digest, the explicitly listed digest
  for `satellite_discovery/m14_descriptive_observations.py` (CRLF normalized
  to LF), and
  `artifact_contracts.semantic_identity()` for exactly the consumed M4/M7
  contracts and M14 output contracts. The exact key set and JSON encoding are
  stated in the clarification.

The M14 semantic projection excludes absolute paths, workspace root,
host/platform, generated timestamps, unrelated producer workflow stages,
unreferenced source files, M13 inputs, whole-package hashes, and filesystem
searches. The composite identity binds provenance as well as semantics, so a
change to the exact selected producer-stage manifest digest can change the
composite identity without changing scientific semantics or counts. The
generic M1 operational key remains unchanged. Use normalized
workspace-relative refs for its config/dependency inputs; keep all
semantically unordered arrays canonical before `_stage_cache_key` sees them.
Raw artifact content hashes remain exact integrity and provenance values.
LF/CRLF-only changes preserve the scientific semantic digest; when raw
provenance bytes change, refresh the result bundle rather than reuse stale
provenance. This is distinct from a change to scientific observations.

The existing M1 stage key includes stage ID, kind, version, normalized config,
dependency report, registration, and stage-scoped implementation identity.
The M14 semantic projection excludes workflow metadata unrelated to M14; the
generic M14 stage key may conservatively miss on a changed explicit locator
but cannot return a result for a different verified content digest. M1–M13
stages without scoped identities use the all-package source digest. Preserve
their keys for an M14-only source change by refreshing the accepted LF and
CRLF digests in the existing
`satellite_discovery/m12_legacy_cache_compatibility.txt`, keeping its legacy
baseline. If a non-M14 change is included, use the existing compatibility
rebaseline rather than masking it. Do not change the shared cache algorithm
or M1–M13 identity definitions.

For verified reuse, require identity match; a complete M1 stage manifest;
exact output inventory; regular-file and containment checks; exact output
hashes; all three M14 output validators; and the M14 result bundle's recorded
input/output identities. A missing, tampered, stale, incompatible, or
digest-mismatched artifact is a cache miss/rejection, never a zero or a
negative. Existing M1 stage manifests and `artifact_contracts.semantic_identity`
provide the primitives; M14 must add its own result-bundle validator and
explicit-source fingerprint.

## 7. Scientific and resource boundary

The baseline can say only that candidates and helpers were co-detected in a
specified number of evaluable, caller-declared units under named methods and
scope. It does not infer a universal biological unit or independence, fit an
association model, normalize abundance, establish control adequacy, infer
taxonomy, or establish helper dependence. Co-detection, repeated co-detection,
M7 recurrence, sequence similarity, and correlation are not dependence
evidence.

A future helper-dependence claim requires a separate claim-appropriate
experimental evidence class establishing a causal requirement, such as
intervention with a suitable comparison and rescue or equivalent measured
evidence. This does not specify a wet-lab protocol and is not an M14
implementation or synthetic-acceptance requirement.

| Resource class | Readiness boundary |
| --- | --- |
| Required for synthetic baseline | Generated offline fixtures, Python standard library, existing artifact-workflow runner, existing synthetic CI matrix. |
| Optional source | M4 and M7 typed artifacts only; caller observations remain primary. |
| Deferred | Inference/modeling, normalization, uncertainty, control matching/adequacy, cohort choice, taxonomy/classification, external executables, sequence databases, and raw reads. |
| Real-data-only gate | Separate purpose/access/terms/privacy approval and an independently justified dataset; none is selected or accessed here. |
| Experimentally required | Claim-appropriate causal/dependence evidence only for a future helper-dependence claim, not for this software baseline. |

This agrees with the
[resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md#4-resources-deliberately-not-selected)
and [validation logistics](M12_M16_VALIDATION_LOGISTICS.md#6-platform-and-ci-matrix).
No biological data, external tool, or private metadata is needed for the next
implementation task.

## 8. Exact next implementation task

Implement only the approved synthetic/offline M14 stage:

1. Add an M14-local `m14-input-v1` validator/normalizer, explicit
   `source_outcomes` resolver and dependency inspector, deterministic
   observation counter/serializer, result-bundle writer, and scoped cache
   identity. Keep runtime logic in the single named M14 module; bump contract
   semantic versions for changes to M14 validator behavior.
2. Add the three M14 output contracts and one allowlisted
   `m14_descriptive_observations` registration using the existing workflow
   runner. Keep optional-source errors per-source and keep M1 lifecycle
   separate from M14 result states. Refresh both accepted LF/CRLF source
   digests in the existing legacy-cache compatibility file while preserving
   its baseline, because this package change is M14-only.
3. Add the synthetic acceptance cases in §5, including reuse/tamper,
   ordering, LF/CRLF, platform, and M14-only cache-isolation tests. Prove the
   compatibility mapping leaves earlier unscoped stage keys unchanged while
   the M14 scoped identity changes.
4. Run focused M14 tests and the existing regression suite on the current
   offline Linux/Windows, Python 3.11/3.12 matrix.

Do not select real data, add external tools, implement inference or
dependence, change M13, or modify README/ROADMAP status. M14 remains planned
until that implementation and its acceptance suite are completed.

M14 CONTRACT CLARIFICATION: APPROVED — READY FOR IMPLEMENTATION