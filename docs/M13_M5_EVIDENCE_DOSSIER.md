# M13 M5-only evidence dossier

This is a maintainer reference for the M13 evidence contract. It does not change
the project-level implementation status recorded in `README` or `ROADMAP`.

## Scope

M13 imports only caller-reported M5 ViReMa artifacts: normalized DVG evidence,
its summary and parameters, and optionally the raw caller output. It preserves
the source event objects and row order. It does not add callers, reference
search, M6–M12 evidence, cross-caller comparisons, or claims about biological
identity, function, or helper dependence.

The workflow stage kind is `m13_m5_evidence_matrix`. Its direct `manifest`
input is a typed `m13_input_manifest`. Every M5 artifact declared in that
manifest must also be supplied to the stage as a typed input. Input names are
deterministic; for run 0 they are `m5_0000_dvg_parameters`,
`m5_0000_dvg_evidence_summary`, `m5_0000_dvg_evidence`, and, when supplied,
`m5_0000_dvg_raw_output`.

## Input contract

An `m13-input-v1` manifest contains:

- `candidate_id`
- `m5_runs`, in caller-supplied order
- `hypotheses`, which may be empty

Each M5 run declares the M1 producer stage ID and lifecycle status, the
SHA-256 digest of the producer `manifest.json` when completed, typed `ArtifactRef`
records, and an `artifact_states` entry for each of the four M5 artifact types.
For a completed run, M13 requires `dvg_parameters`, `dvg_evidence_summary`,
and `dvg_evidence`; `dvg_raw_output` is optional. An artifact reference binds
the milestone, stage ID, producer status, producer manifest digest, artifact
type, path relative to the M5 stage output, content digest, and contract
version.

For a noncompleted run, M13 uses the optional `producer_workflow_ref` and
`execution_record_ref` fields to verify the M1 workflow snapshot and the
execution-outcome record. Both paths are relative to the M13 input manifest.
Completed artifact paths are relative to their M5 stage output. M13 does not
search directories or infer artifact paths.

Each supplied hypothesis has an ID, label, provenance reference, and a scope
from `STRUCTURAL_OBSERVATION`, `SOURCE_ORIGIN`, `FUNCTION_OR_INTERFERENCE`,
`BIOLOGICAL_IDENTITY`, or `OTHER`. Hypotheses are questions to organize
evidence, not conclusions. Only a structural-observation hypothesis can be
marked `OBSERVED`, and only when a validated M5 event is linked to it. Other
scopes remain `UNRESOLVED`; a completed zero-event run is not evidence of
biological absence.

## Run-state interpretation

M13 keeps the raw M1 lifecycle state separate from M5 evidence status. Examples:

| M1 producer state | M5 evidence status | M13 import state |
| --- | --- | --- |
| `complete` with caller events | `DVG_EVIDENCE_DETECTED` | `IMPORTED_WITH_EVENTS` |
| `complete` with no caller events | `NO_DVG_EVIDENCE_DETECTED` | `IMPORTED_COMPLETED_ZERO` |
| `skipped` | `NOT_EVALUATED` | `NOT_SUPPLIED` |
| `running` | `NOT_EVALUATED` | `INCOMPLETE` |
| `failed` after caller execution error | `ANALYSIS_FAILED` | `IMPORTED_NONCOMPLETED` |
| `failed` with invalid caller output | `INVALID_RESULT` | `INVALID` |

An invalid or unavailable run does not remove rows from independent valid runs.
For completed runs, M13 validates the producer manifest, artifact digests, and
artifact contracts before importing events. For noncompleted runs, it verifies
the workflow snapshot and execution-outcome reference instead.

## Outputs

The stage writes:

- `event_index.json` — original M5 event object, its native row index, caller
  version, reference digest, candidate ID, and typed M5 run reference.
- `hypothesis_matrix.json` — supplied hypotheses, scoped evidence state, and
  event references.
- `summary.json` — per-run raw statuses, import state, completeness, and
  imported event count.
- `result_bundle.json` — input, producer, implementation, cache-context, and
  output digests.

All four outputs use contract version `2`. Output reuse is allowed only when
the stage cache identity, output hashes, and cross-artifact references still
validate.

## Offline checks

The synthetic M13 coverage runs with the existing Python test environment:

```sh
PYTHONPATH=tests python -m unittest test_m13_m5_evidence
PYTHONPATH=tests python -m unittest test_virema_adapter test_dvg_workflow
```

The M13 tests use the deterministic local ViReMa fixture and do not retrieve
biological data or invoke an external caller.