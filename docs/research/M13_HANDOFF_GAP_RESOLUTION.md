# M13 M5 failure-state handoff gap resolution

**Decision: SHARED HANDOFF IMPLEMENTED — M13 REMAINS UNIMPLEMENTED.**

M13 remains planned and not implemented. The shared handoff is implemented as
workflow metadata with stable failure codes; it does not change M5 scientific
behavior or existing M1–M12 scientific artifacts.

## 1. Finding

The current workflow record is useful but does not satisfy the full frozen M13
state matrix:

- [`artifact_workflow.py`](../../satellite_discovery/artifact_workflow.py)
  writes `workflow.json` with a workflow ID, configuration identity, workflow
  state, and per-stage lifecycle state. Its DVG projection also distinguishes
  completed evidence, completed zero, unavailable, failed, invalid, and
  not-evaluated outcomes. The stage lifecycle must be read alongside the DVG
  projection: `failed` and `interrupted` both project to
  `ANALYSIS_FAILED`, while their M1 stage states remain distinct.
- The runner records `dependency_missing`, `external_module_required`,
  `failed`, and `interrupted` stage states; skipped and not-reached stages are
  also visible as `skipped` or `pending`. For completed DVG stages,
  `write_status` rechecks the summary digest and validates the summary before
  recording its status and event count. A validated `NO_DVG_EVIDENCE_DETECTED`
  result with count zero is therefore distinguishable from a failed or
  unavailable execution.
- [`dvg_evidence.py`](../../satellite_discovery/dvg_evidence.py) raises the same
  `InvalidDVGResultError` for truncated ViReMa output and malformed output.
  The workflow record projects these cases to `INVALID_RESULT`. The exception
  text is diagnostic free text, not a stable code that M13 can safely use to
  distinguish incomplete/truncated output from malformed/corrupt output.
- The current M13 input has a producer stage ID, caller-supplied manifest
  digest/status, and artifact references, but no explicit reference to the
  producer `workflow.json` or a typed terminal execution record. The M13
  earlier readiness review correctly notes that caller assertions alone do
  not verify the producer stage or its terminal state.

An explicit workflow-record path and digest in `M5RunRef` would let M13 inspect
the existing lifecycle data without searching directories or inferring an
output root. M13 could then verify most broad states by checking the exact
record bytes and matching workflow/stage identity. That contract-only change
would still leave truncated/incomplete output indistinguishable from
malformed/corrupt output. Reading or pattern-matching `failure.error` would
make M13 depend on unstable text, so it is not an acceptable substitute.

The expected workflow-manifest digest can bind the exact supplied file bytes;
it is an integrity check, not a cryptographic signature of the record's
origin. The design below makes no stronger authenticity claim than the
existing local artifact workflow.

## 2. Minimum additive design

### 2.1 Versioned execution-outcome record

Add a non-scientific `m5-execution-outcome-v1` JSON sidecar to the shared
workflow handoff. The runner writes one record per M5 DVG stage after the final
`workflow.json` has been written, including for stages that were skipped, not
reached, unavailable, failed, interrupted, or completed. The record is
workflow metadata, not a DVG evidence artifact; it must not be added to the
M5 scientific output inventory or create placeholder parameters, summaries,
event rows, or raw-output artifacts.

The record must preserve these separate fields:

- workflow ID, workflow configuration/specification digest, producer stage ID
  and kind, and the SHA-256 of the final `workflow.json` it describes;
- the raw M1 stage lifecycle state, unchanged;
- the raw M5 DVG-evaluation status, unchanged;
- a stable `outcome_code` distinguishing `COMPLETED_EVENTS`,
  `COMPLETED_ZERO`, `NOT_STARTED`, `UNAVAILABLE`, `FAILED`, `INTERRUPTED`,
  `INCOMPLETE_OUTPUT`, and `INVALID_OUTPUT`;
- for an M5 `INVALID_RESULT`, a stable machine-readable `failure_code` that
  distinguishes truncation/incomplete accounting from malformed/corrupt
  output. Use `TRUNCATED_OUTPUT` and `INCOMPLETE_ACCOUNTING` for the
  `INCOMPLETE` outcome; use `MALFORMED_OUTPUT`, `CORRUPT_OUTPUT`,
  `INVALID_M5_CONTRACT`, or `UNCLASSIFIED_INVALID_RESULT` for `INVALID`.
  Do not derive this code from free-text error messages.

The record is final only when the enclosing workflow is terminal. The runner
must not emit a final outcome record for a `workflow.json` that still says
`running`; that is not proof of an interrupted or failed M5 run. M13 must
report such a handoff as incomplete and import no events. For a terminal
workflow, a pending or skipped M5 stage may be recorded as `NOT_STARTED`;
preserve `pending` and `skipped` as distinct raw M1 states.

The shared workflow now emits this record and carries structured M5 failure
codes. That classification is metadata only: existing M5 DVG status values,
event fields, parsing behavior, and scientific meaning remain unchanged. The
sidecar schema is versioned; the existing `workflow.json` schema is unchanged.
The sidecar is written after the final workflow manifest, is not listed as a
scientific stage output, and binds to that manifest by its digest. Synthetic
tests cover terminal-state emission, raw-status preservation, failure mapping,
explicit-reference integrity, and cache compatibility. M13 itself is not
implemented.

### 2.2 Explicit M13 reference

Amend the pre-implementation `m13-input-v1` contract before its first
implementation. A non-completed `M5RunRef` must include explicit
`producer_workflow_ref` and `execution_record_ref` objects. They contain:

- `producer_workflow_ref`: a normalized relative path to the exact
  `workflow.json`, its expected SHA-256, and the expected workflow ID;
- `execution_record_ref`: a normalized relative path to the exact sidecar,
  its expected SHA-256, and schema `m5-execution-outcome-v1`.

For example, the reference shape is:

```json
{
  "producer_workflow_ref": {
    "path": "m5-run/workflow.json",
    "sha256": "<64 lowercase hexadecimal characters>",
    "workflow_id": "<workflow id>"
  },
  "execution_record_ref": {
    "path": "m5-run/execution-outcomes/m5-stage.json",
    "sha256": "<64 lowercase hexadecimal characters>",
    "schema": "m5-execution-outcome-v1"
  }
}
```

Resolve both paths only relative to the M13 input manifest. Reject absolute
paths, traversal, symlinks, non-regular files, hash mismatches, duplicate
stage IDs, inconsistent workflow/stage identity, or inconsistent status
fields. The sidecar's `workflow_manifest_sha256` must equal the digest
computed from the explicitly referenced `workflow.json`. Do not scan for
either file, infer a producer root, or accept a caller-supplied status without
reading and validating both records. The workflow ID plus exact manifest
digest and producer stage ID identify the supplied run snapshot; the workflow
ID alone is not a unique run identity because it can be reused across
executions.

For completed runs, keep the existing verified M5 stage-manifest and typed
artifact path. Do not require completed M5 artifacts to be regenerated just
to add an outcome record. For non-completed runs, the M5 stage-manifest digest
may be absent; the two explicit record references identify the execution,
while artifact states remain explicitly non-present.

If the record cannot be read, M13 may report the record as unavailable but
must not claim a verified M5 state. A readable record with an invalid digest,
schema, or identity is invalid. Neither case may become a completed zero.

## 3. Required state mapping

M13 must preserve both the raw M1 execution state and raw M5 evidence status.
`producer_status_raw` remains the M5 evidence status; use
`producer_execution_status_raw` for the exact M1 stage status rather than
collapsing the two.

| Verified producer record | M13 `run_import_state` | Required interpretation |
| --- | --- | --- |
| M1 stage `complete`; M5 status `DVG_EVIDENCE_DETECTED`; validated non-empty evidence and exact accounting | `IMPORTED_WITH_EVENTS` | Import only the validated caller observations. |
| M1 stage `complete`; M5 status `NO_DVG_EVIDENCE_DETECTED`; validated empty evidence and exact accounting | `IMPORTED_COMPLETED_ZERO` | No event was reported by this caller in this run; never a biological negative. |
| Terminal workflow proves the M5 stage was `pending` or `skipped` and not started | `NOT_SUPPLIED` | Preserve the raw stage state and reason; do not create evidence. |
| M5 stage `dependency_missing` or `external_module_required` | `UNAVAILABLE` | Preserve the exact M1 state and M5 `ANALYSIS_UNAVAILABLE` status. |
| M5 stage `failed` for a runtime failure | `IMPORTED_NONCOMPLETED` | Preserve the failure; no inferred event or zero. |
| M5 stage `interrupted` | `INTERRUPTED` | Preserve the interruption even though the M5 projection may say `ANALYSIS_FAILED`. |
| Structured failure code identifies truncated output or incomplete accounting | `INCOMPLETE` | Preserve `INVALID_RESULT` if that is the raw M5 status and retain the structured reason code. |
| M1 stage `failed` with `INVALID_RESULT`, or a completed stage whose summary verification yields `INVALID_RESULT`; structured code identifies malformed/corrupt output or invalid M5 contract data | `INVALID` | Reject that run import; do not reinterpret it as zero. |
| Referenced workflow is still `running` | `INCOMPLETE` | No accepted M5 result; do not infer that the process was interrupted. |
| Workflow/outcome record is readable but has a bad digest, schema, or identity | `INVALID` | Reject the run reference; retain independent valid runs if applicable. |
| Workflow/outcome record is absent or unreadable | `UNAVAILABLE` | State only that the execution record could not be verified; do not assert an M5 result. |

The distinction between execution and evidence is mandatory. For example,
`stage_status=interrupted` plus `m5_evidence_status=ANALYSIS_FAILED` remains an
interrupted execution, not a generic failed result. Likewise,
`stage_status=failed`, `m5_evidence_status=INVALID_RESULT`, and
`failure_code=TRUNCATED_OUTPUT` maps to M13 `INCOMPLETE`, while a
`failure_code=MALFORMED_OUTPUT` maps to `INVALID`. Neither maps to
`IMPORTED_COMPLETED_ZERO`.

## 4. Cache identity and compatibility

The outcome record is consumed by M13 only. Bind the exact workflow-manifest
digest, outcome-record digest and schema/version, raw M1 state, raw M5 status,
and structured failure code into M13's scoped identity context and result
bundle. These opaque digests identify the exact supplied run snapshot and may
change when the producer manifest changes; that is an M13 input change, not an
M5 cache change. Do not copy raw timestamps or host-specific paths into the
sidecar or M13 outputs. Changes to the record or its interpretation must
invalidate M13, not rerun M5 or rewrite M1–M12 scientific artifacts.

Do not add this metadata as an M5 scientific output, M5 input, or M5 artifact
contract semantic dependency. Do not bump global cache semantics for this
M13-only handoff. The current M5 adapter identity includes adapter, executor,
and parser source digests; changing parser code can therefore change M5 cache
keys even if event output semantics do not change. Any implementation of the
structured failure codes must explicitly test cache-key stability and preserve
existing successful M5 cache identities; do not blanket-bump M5 or global
cache semantics for metadata-only classification. Unrelated M1–M12 cache keys
and output bytes must remain stable.

## 5. Synthetic acceptance tests

Use synthetic records/files only. These are the twelve frozen acceptance cases,
classified by the layer that owns their decisive assertion:

1. **M13 IMPLEMENTATION ACCEPTANCE — completed events.** Future M13 tests must
   verify byte-equivalent source events in order, stage/run identity, evidence
   digest, and `IMPORTED_WITH_EVENTS`. The shared prerequisite is covered by
   `tests/test_execution_outcome.py::test_terminal_sidecar_binds_raw_statuses_and_explicit_references`
   and `tests/test_dvg_workflow.py::test_positive_handoff_reports_raw_link_and_resolved_catalogue_identity`.
2. **M13 IMPLEMENTATION ACCEPTANCE — completed zero.** Future M13 tests must
   require validated empty events and exact accounting, then assert
   `IMPORTED_COMPLETED_ZERO` without a biological negative or invented
   hypothesis. The shared M5 zero path is covered by
   `tests/test_dvg_workflow.py::test_zero_events_are_not_a_non_dvg_classification`.
3. **HANDOFF-INFRASTRUCTURE ACCEPTANCE — not started.** Test terminal `pending`
   and `skipped` separately; preserve both raw M1 states and raw
   `NOT_EVALUATED`, with `NOT_STARTED` rather than zero. Covered by
   `tests/test_execution_outcome.py::test_terminal_pending_skipped_and_unavailable_states_remain_distinct`.
   Future M13 tests must also preserve the distinction and import no events.
4. **HANDOFF-INFRASTRUCTURE ACCEPTANCE — unavailable.** Test both
   `dependency_missing` and `external_module_required`; preserve each raw M1
   state and `ANALYSIS_UNAVAILABLE`, with `UNAVAILABLE` rather than zero. The
   same shared-layer test above covers these states. Future M13 tests must
   preserve each state and import no events.
5. **M13 IMPLEMENTATION ACCEPTANCE — runtime failure.** Future M13 tests must
   preserve `failed` plus `ANALYSIS_FAILED` as `IMPORTED_NONCOMPLETED`, with no
   inferred event or completed zero. The shared `FAILED` mapping is covered by
   `tests/test_execution_outcome.py::test_terminal_interruption_is_distinct_from_runtime_failure_and_zero`
   and `tests/test_dvg_workflow.py::test_skip_is_not_evaluated_and_malformed_and_exit_failure_are_distinct`.
6. **HANDOFF-INFRASTRUCTURE ACCEPTANCE — interruption.** Verify terminal M1
   `interrupted` remains distinct from `failed` even when both retain M5
   `ANALYSIS_FAILED`; the shared outcome must be `INTERRUPTED`, never zero.
   Covered by
   `tests/test_execution_outcome.py::test_terminal_interruption_is_distinct_from_runtime_failure_and_zero`.
   Future M13 tests must map that verified record to `INTERRUPTED`.
7. **M13 IMPLEMENTATION ACCEPTANCE — truncated/incomplete output.** Future M13
   tests must use stable `TRUNCATED_OUTPUT` or `INCOMPLETE_ACCOUNTING` and
   report `INCOMPLETE`, never zero. Shared classification is covered by
   `tests/test_execution_outcome.py::test_skipped_and_invalid_results_have_distinct_outcome_classes`.
8. **M13 IMPLEMENTATION ACCEPTANCE — malformed/corrupt output.** Future M13
   tests must retain a distinct stable failure code and report `INVALID`, never
   zero. Shared classification is covered by the same execution-outcome test.
9. **M13 IMPLEMENTATION ACCEPTANCE — nonterminal workflow.** A `running`
   workflow with a pending/running M5 stage must produce M13 `INCOMPLETE`, not
   `INTERRUPTED`. The shared writer/verifier must not accept a final outcome;
   covered by
   `tests/test_execution_outcome.py::test_nonterminal_workflow_does_not_emit_final_sidecar`
   and `::test_nonterminal_referenced_workflow_is_incomplete`.
10. **HANDOFF-INFRASTRUCTURE ACCEPTANCE — handoff integrity.** Missing/unreadable
    referenced records are unavailable; digest, schema, workflow-ID, stage-ID,
    or status mismatch is invalid. Reject a missing caller reference and a
    sidecar bound to different workflow bytes. Covered by
    `tests/test_execution_outcome.py::test_missing_workflow_and_terminal_outcome_are_unavailable`,
    `::test_tampered_malformed_and_wrong_schema_records_are_invalid`,
    `::test_workflow_record_and_expected_stage_identity_mismatches_are_invalid`,
    `::test_explicit_references_reject_traversal_and_symlinks`, and
    `::test_record_cannot_be_reused_after_workflow_manifest_changes`.
11. **M13 IMPLEMENTATION ACCEPTANCE — partial bundle.** An invalid/incomplete
    run must not erase independent valid runs; no failed run may produce a
    placeholder scientific artifact.
12. **M13 IMPLEMENTATION ACCEPTANCE — cache isolation.** Changing only M13
    outcome-record interpretation must change the M13 key while leaving
    unrelated M1–M12 keys and scientific artifact bytes unchanged. The sidecar
    remains additive metadata; the M13 key test belongs to M13 implementation.

The shared-layer tests for structured codes also prove `FAILED`,
`INTERRUPTED`, `INCOMPLETE_OUTPUT`, `UNAVAILABLE`, and `INVALID_OUTPUT` are
distinct from `COMPLETED_ZERO`. Deterministic serialization, exact cache
compatibility, and unchanged reused M5 artifact bytes are checked separately.
Shared-layer coverage is not a substitute for the M13 assertions above. Do not
invoke ViReMa, retrieve biological data, or install optional DVG callers to
exercise either layer.

## 6. Implementation gate

The shared versioned execution record and structured failure codes pass the
synthetic handoff/cache tests listed above. The infrastructure cases are
complete; the M13 implementation cases remain mandatory future acceptance.
This does not mark the full M13 readiness review complete or authorize
implementation of M13.

M13 HANDOFF GAP: SHARED INFRASTRUCTURE COMPLETE — M13 NOT IMPLEMENTED