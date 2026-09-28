# M13 contract freeze: M5-only DVG evidence dossier

**Contract status: FROZEN FOR THE SYNTHETIC/OFFLINE BASELINE ONLY.** M13 is
**PLANNED / NOT IMPLEMENTED**. This specification organizes M5 caller-scoped
observations without creating a DVG taxonomy or cross-caller comparison.

This M5-only freeze is a preparatory synthetic/offline baseline, not the full
M13 differential evidence layer in the current [roadmap](ROADMAP.md), which
states that M5 caller output alone is insufficient. Any broader comparator or
independent-example analysis requires a separately reviewed extension.

## 1. Scope and non-goals

M13 imports validated M5 run summaries and caller-reported event rows, keeps
the caller/reference/run scope attached, and emits an unresolved descriptive
evidence matrix. The baseline uses one or more M5 runs only. It does not run
another caller, normalize event coordinates across callers, infer biological
class, or calculate agreement.

Explicit non-goals:

- DI-tector, VODKA/VODKA2, DVGfinder, or any external executable/model/database.
- Universal DVG/satellite/subviral labels or an automatic classifier.
- Cross-caller event identity, coordinate conversion, vote counting, or
  agreement semantics.
- Inference of interference, replication, helper dependence, or function.
- M12–M16, M6–M10, or comparator datasets as required inputs.

## 2. Runner and accepted producer artifacts

The future stage is `m13_m5_evidence_matrix`, invoked only through the
allowlisted artifact-workflow manifest runner:

```text
python -m satellite_discovery.artifact_workflow \
  --manifest <workflow.json> --output <output-directory>
```

There is no M13-specific command or external caller invocation. An additive
M4 stage registration and additive M13 artifact contracts are required before
workflow use; none are added here.

Only M5 ViReMa-run artifacts are accepted:

| Artifact type | Requirement and use |
| --- | --- |
| `dvg_parameters` | Required per run; exact caller, input/reference identity, and settings. |
| `dvg_evidence_summary` | Required per run; exact raw M5 terminal state and accounting. |
| `dvg_evidence` | Required for completed runs; the validated `events` array is empty for a completed zero. |
| `dvg_raw_output` | Optional; integrity/provenance reference only, never reparsed by M13. |

The producer must be the M5 contract and its validated manifest. No arbitrary
caller table, M6-derived event, external caller output, or copied literature
label can masquerade as an M5 artifact.

## 3. Input manifest and event identity

The UTF-8 JSON manifest has `schema = "m13-input-v1"`:

```json
{
  "schema": "m13-input-v1",
  "candidate_id": "stable caller-supplied identifier",
  "m5_runs": [],
  "hypotheses": []
}
```

`candidate_id` is required and opaque. `m5_runs` is an ordered array of
`M5RunRef` objects. Each contains the M5 producer stage ID, run-manifest
SHA-256, exact raw terminal status, zero or more `ArtifactRef` objects, and an
`artifact_states` object with exactly these keys: `dvg_parameters`,
`dvg_evidence_summary`, `dvg_evidence`, and `dvg_raw_output`. Each state is
`PRESENT`, `NOT_PRODUCED`, `UNAVAILABLE`, `NOT_APPLICABLE`, or `UNKNOWN`;
`PRESENT` requires exactly one matching reference, and every non-present state
requires none. Artifact refs use the same immutable fields and path/integrity
rules as [M12](M12_CONTRACT_FREEZE.md). A completed M5 run requires
`dvg_parameters`, `dvg_evidence_summary`, and `dvg_evidence`; a completed zero
has a present, validated evidence document whose `events` array is empty. A
failed, interrupted, incomplete, or unavailable run may omit artifacts only
with explicit non-present states. At least one M5 run entry is required.

An M5 event is identified only by
`(producer_run_manifest_sha256, dvg_evidence_sha256, source_row_index)`.
M13 copies the entire source event object and source-row order. It does not
derive a stable biological event identity. Existing ViReMa fields such as
`reference_id`, `acceptor_reference_id`, `breakpoint_1/2`, `orientation`,
`supporting_read_count`, `raw_entry`, `raw_line_number`, `raw_library`, and
`event_type` remain producer fields; M13 does not rewrite them.

`hypotheses` is optional and defaults to an empty array. If supplied, each row
requires a unique opaque `hypothesis_id`, curator/source-defined `label`,
`scope`, and provenance reference. `scope` is one of `STRUCTURAL_OBSERVATION`,
`BIOLOGICAL_IDENTITY`, `FUNCTION_OR_INTERFERENCE`, `SOURCE_ORIGIN`, or
`OTHER`. These are evidence-question scopes, not a DVG taxonomy. No label is
inferred from an M5 event.

## 4. Outputs and states

Proposed future output artifact types:

- `m13_event_index` — copied caller-specific M5 event rows plus immutable
  source-row references.
- `m13_hypothesis_matrix` — hypothesis/evidence links and unresolved states.
- `m13_summary` — per-run status and completeness summary.
- `m13_result_bundle` — input/output/provenance manifest.

Every event-index row includes `candidate_id`, `m5_run_ref`, `source_row_index`,
`source_event_id` if provided by M5, and `source_event` copied without
normalization. Every matrix row includes `hypothesis_id` (or null),
`question_scope`, `evidence_refs`, `evidence_state`, and a reason.
`evidence_state` is `OBSERVED`, `CONFLICTING`, `UNRESOLVED`, or
`NOT_ASSESSED`. `OBSERVED` means only that a cited M5 artifact contains a
validated caller observation relevant to the explicitly supplied question; it
is not a biological class call. With no hypothesis supplied, M13 emits event
rows and no invented hypothesis rows.

Keep raw M5 status exactly in `producer_status_raw`. M13’s `run_import_state`
is one of `IMPORTED_WITH_EVENTS`, `IMPORTED_COMPLETED_ZERO`,
`IMPORTED_NONCOMPLETED`, `NOT_SUPPLIED`, `UNAVAILABLE`, `NOT_APPLICABLE`,
`INVALID`, `INCOMPLETE`, or `INTERRUPTED`. `IMPORTED_COMPLETED_ZERO` is
permitted only for exact M5 `NO_DVG_EVIDENCE_DETECTED` with valid complete
accounting. It means no event was reported by that caller within that run; it
does not mean the biological sample is DVG-negative or a satellite.

Stage lifecycle is the existing M1 state set. Missing optional raw output does
not fail an otherwise valid M5 import. Invalid required M5 identity/accounting
blocks that run import, but other valid runs remain in the bundle.

## 5. Validation, failures, and deterministic behavior

- Require producer/type pairs exactly as listed above; verify every hash,
  run-manifest identity, M5 contract version, and candidate/run linkage.
- Require parameter and summary records for completed runs. For
  non-completed runs, preserve absent artifacts through `artifact_states`.
  Validate event rows with the M5 validator and require exact
  summary/event-count agreement, including the empty evidence document for a
  completed zero.
- Preserve M5 source status. Never reconstruct missing events from raw output,
  turn malformed output into zero events, or accept a failed/incomplete run as
  completed.
- Duplicate `(run manifest, evidence artifact, source row index)` is invalid.
  Similar coordinates in different runs remain different source observations.
- Reject unknown event fields only if the M5 producer validator rejects them;
  M13 must preserve the validated source object rather than impose a second
  event taxonomy.
- A missing run dependency maps to M1 `dependency_missing` only when it is
  required by the input manifest. An absent optional raw output is explicitly
  unavailable. Failed/interrupted/incomplete producer results remain such.
- No failure, missing hypothesis, no event, or unavailable caller may produce
  a candidate rejection.

Serialize UTF-8 JSON with sorted object keys, LF, one trailing newline, and no
non-finite numbers. Sort run summaries by producer stage ID and run-manifest
digest; within each run preserve native event-row order. Sort hypothesis rows
by `hypothesis_id`, then source reference. Do not sort or rewrite a source
event array. This gives deterministic output without changing event semantics.

## 6. Provenance and cache identity

Bind `m13_result_bundle` to the M13 input-manifest digest; candidate ID; each
M5 stage ID, run-manifest digest, raw status, artifact type/version/digest;
hypothesis definitions and their provenance; the M13 schema/semantic version;
consumed artifact-contract semantic identities; implementation/source digest;
and output hashes. Do not include optional external-tool versions because no
such tools are run.

Changing an M5 run, event artifact, hypothesis definition, or M13
implementation invalidates M13 only. Do not rerun or invalidate M5. Generated
timestamps and host-specific paths are excluded. Reuse requires exact identity
and output hash validation.

## 7. Synthetic acceptance fixtures

| Fixture | Required result |
| --- | --- |
| M5 completed event run | Byte-equivalent event objects in native order, with caller/reference/run refs. |
| M5 completed zero with complete accounting | `IMPORTED_COMPLETED_ZERO`; no biological negative, class, interference, or satellite label. |
| M5 unavailable/failed/interrupted/incomplete run | Preserve exact raw M5 status and M13 import state; no event inference from missing output. |
| Same-shaped event from two M5 runs | Two distinct source-row identities; no merge or cross-caller agreement. |
| Hypothesis list absent | Empty matrix with explicit absence; no default taxonomy. |
| User-supplied structural hypothesis | Link event evidence to that exact ID and `STRUCTURAL_OBSERVATION`; do not elevate to biological identity. |
| Duplicate event identity, bad hash, mismatched summary count, invalid coordinates | Reject the invalid run import; preserve independent valid runs. |
| Optional raw output absent | M13 continues with validated normalized M5 evidence and marks raw output unavailable. |

## 8. Compatibility and claim boundary

M13 depends only on M5 artifacts `dvg_parameters`, `dvg_evidence_summary`,
`dvg_evidence`, and optional `dvg_raw_output` in
[`artifact_contracts.py`](../satellite_discovery/artifact_contracts.py).
There is no required change to M5 semantics, event fields, or ViReMa
provisioning. A later M4 allowlist/producer registration is additive. M13
records caller observations and hypotheses; it does not establish DVG
identity, satellite status, interference, helper dependence, or function.
