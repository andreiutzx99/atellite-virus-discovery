# M12–M16 synthetic/offline contract cross-check

**Status: historical cross-contract consistency review.** This document checks
the five contract freezes against the [roadmap](../ROADMAP.md), M1–M11
boundaries, and the completed readiness/resource reports. M11 is implemented
but was not re-audited here; the M15 freeze deliberately excludes M11 artifacts.
M12–M16 remain **PLANNED / NOT IMPLEMENTED**. This review makes no
implementation, data-access, licensing, or biological-policy decision.

## 1. Contract set and dependencies

| Contract | Baseline producer inputs | Output types | Required before execution |
| --- | --- | --- | --- |
| [M12](../M12_CONTRACT_FREEZE.md) | M5 caller artifacts and M6 retained residual/support/reconstruction artifacts only. | `m12_artifact_review_table`, `m12_summary`, `m12_result_bundle` | M5/M6 artifacts are optional individually; empty input is explicitly not evaluated. |
| [M13](../M13_CONTRACT_FREEZE.md) | M5 `dvg_parameters`, `dvg_evidence_summary`, and completed-run `dvg_evidence` (empty event array for a completed zero); optional `dvg_raw_output`. | `m13_event_index`, `m13_hypothesis_matrix`, `m13_summary`, `m13_result_bundle` | At least one M5 run identity; no other caller or comparator. |
| [M14](../M14_CONTRACT_FREEZE.md) | Explicit caller observation table; optional M4 `catalogue_observations`/`observations` outputs and M7 `independent_recurrence` artifacts. | `m14_observation_table`, `m14_descriptive_summary`, `m14_result_bundle` | Explicit unit frame and tested states; empty observations are not negative. |
| [M15](../M15_CONTRACT_FREEZE.md) | Immutable M5–M10 and any present M12–M14 typed outputs. | `m15_evidence_envelope`, `m15_dependency_edges`, `m15_dossier_summary`, `m15_result_bundle` | No stage is required solely to fill an optional evidence slot. |
| [M16](../M16_CONTRACT_FREEZE.md) | Frozen M12–M15 result bundles and synthetic fixtures only. | `m16_prediction_table`, `m16_leakage_report`, `m16_custody_log`, `m16_metric_summary`, `m16_result_bundle` | Target identity frozen; hidden synthetic key withheld until prediction commitment. |

Dependency direction is acyclic:

```text
M5/M6 -> M12
M5 -> M13
M4 supplied observations and M7 declared metadata -> M14
M5–M10 plus any present M12–M14 -> M15
frozen M12–M15 outputs plus synthetic fixtures -> M16
```

M16 is terminal validation output and never an input to M12–M15. M15 never
feeds M12, M13, or M14. M11 is outside this contract set; its absent output is
not required by these freezes. In particular, the frozen M15 baseline
deliberately excludes M11 artifacts.

## 2. Shared state terminology

The M1 stage/workflow lifecycle remains authoritative:

- Stage: `pending`, `running`, `complete`, `skipped`,
  `dependency_missing`, `external_module_required`, `failed`, `interrupted`.
- Workflow aggregation may additionally be `partial`.
- `BLOCKED` is explanatory language, not a new lifecycle enum. Preflight
  blocking maps to `dependency_missing` or `external_module_required`.

Evidence/availability states are separate from lifecycle:

| Term | Meaning across contracts |
| --- | --- |
| `NOT_DETECTED_WITHIN_SCOPE` | An explicitly tested unit/branch produced no signal within a declared method/reference scope with complete accounting. Never a candidate-wide negative. M5/M6 raw result codes remain unchanged. |
| `UNKNOWN` | Supplied evidence does not determine presence or absence, or status cannot be losslessly mapped. |
| `NOT_SUPPLIED` | An optional artifact/data item was not included in the input manifest. |
| `UNAVAILABLE` | A declared source/dependency could not be obtained or run. Record authorization/technical reason where known. |
| `NOT_APPLICABLE` | Explicitly outside the scope of this item/branch; not a synonym for missing. |
| `FAILED` / `INTERRUPTED` | An attempted stage/branch failed or was interrupted. Preserve partial valid artifacts separately. |
| `INCOMPLETE` / `TRUNCATED` | Declared accounting/output scope was not fully observed or retained. No scoped negative is permitted. |
| `INVALID` | Schema, identity, integrity, or validation failed. Invalid evidence cannot support a result. |

An optional branch may be `NOT_SUPPLIED`, `UNAVAILABLE`, or
`NOT_APPLICABLE` while the stage completes a valid partial-scope dossier.
Required-input absence blocks execution; it does not yield an empty successful
scientific result. No state is silently coerced to `NOT_DETECTED`.

## 3. M1–M11 compatibility and M4 registration

The contracts consume the current M1 typed stage/status/provenance/reuse
framework; M2 immutable supplied-reference snapshots; M3 validated assembly
artifacts; and M4 allowlisted workflow/table handoffs. M5’s exact caller status
and events, M6’s reference-scoped primary accounting and same-read read-back,
M7’s exact recurrence and unverified declared independence, M8’s role-scoped
homology, M9’s policy-bound ORF/protein output, and M10’s exact-first
architecture remain unchanged. M11 is an optional RNA-fold prediction stage;
none of these contracts requires its artifacts, and M15 deliberately excludes
them.

There is no required upstream behavior or enum migration. M15 keeps the exact
producer status/schema and maps an axis only when equivalence is explicit.
Future workflow invocation of M12–M16 requires **additive** allowlist stage
definitions and new artifact type validators/semantic identities in the M4
workflow/artifact-contract registry. It does not authorize dynamic import,
arbitrary shell execution, or new external modules. The current
`artifact_workflow` manifest runner and preflight interface remain the only
proposed workflow boundary.

Current source contracts: [M1 foundation](../M1_FOUNDATION.md),
[M2 reference/acquisition](../M2_REFERENCE_ACQUISITION.md),
[M3 assembly](../M3_ASSEMBLY.md),
[M4 integrated workflow](../M4_INTEGRATED_WORKFLOW.md),
[M5 DVG evidence](../M5_DVG_EVIDENCE.md),
[M6 residual support](../M6_RESIDUAL_ASSEMBLY_SUPPORT.md),
[M7 recurrence](../M7_INDEPENDENT_RECURRENCE.md),
[M8 nucleotide homology](../M8_REFERENCE_AND_HOMOLOGY_SPEC.md),
[M9 contract](../M9_CONTRACT_FREEZE.md), [M10 contract](../M10_CONTRACT_FREEZE.md),
and [M11 contract](../M11_CONTRACT_FREEZE.md). The current
[artifact type registry](../../satellite_discovery/artifact_contracts.py),
[workflow registry](../../satellite_discovery/artifact_workflow.py), and
[lifecycle states](../../satellite_discovery/workflow_states.py) are the
implementation references for any later registration.

## 4. Optional resources and deferred decisions

No optional tool or real dataset is promoted to a required dependency:

- M12 requires no new FASTQ, SAM/BAM/CRAM reader, mapping, control, or metadata;
  its accepted evidence is retained M5/M6 artifacts.
- M13 requires no DI-tector, VODKA/VODKA2, DVGfinder, cross-caller
  normalization, or comparator payload.
- M14 requires no external statistical model, sequence database, or empirical
  cohort for descriptive summaries.
- M15 requires no M11 result and has no ranking, score, or classifier.
- M16 accepts only synthetic software-contract fixtures in this version.

The following remain named deferred decisions rather than being resolved by
these contracts:

| Deferred decision | Scope blocked |
| --- | --- |
| M12 source-read/control access, matching/adequacy, panel, and attribution language | Real-data execution and control/source-attribution claims only. |
| M13 caller rights/provisioning, cross-caller equivalence, and curated comparator membership | Optional caller comparison or empirical performance/class claims only. |
| M14 dataset-specific purpose/access/terms/privacy approval, independence verification, inferential profile, and dependence assay | Real-data execution, inference, and experimental claims only; the synthetic/offline descriptive baseline is not blocked. |
| M15 ranking objective, weights/calibration, and restricted-data export | Optional ranking/export only. |
| M16 empirical truth tiers, holdout membership/custody, thresholds, metrics/uncertainty profile, and stop rules | Final empirical benchmark and claim-specific performance validation only. |

## 5. Required consistency checks

| Check | Contract result |
| --- | --- |
| Missing evidence is never negative evidence | M12 distinguishes external availability; M13 preserves raw M5 zero semantics; M14 requires tested denominator; M15 preserves missingness; M16 excludes unknown/not-applicable labels from synthetic denominators. |
| No biological claim beyond current research | M12 does not attribute source; M13 does not classify/functionally confirm; M14 is descriptive only; M15 has no winner; M16 outcomes are software-fixture agreement only. |
| Cache/provenance prevent stale reuse | Every bundle binds input schema, exact consumed producer run/artifact IDs and hashes, semantic versions, implementation/configuration, and output integrity. Stage-local changes invalidate that stage only. |
| M15 losslessly consumes partial M12–M14 inputs | Explicit per-stage availability plus raw producer status/schema; unknown axes stay unknown; valid rows survive another branch’s failure. |
| M16 does not see hidden labels during target execution | Public manifest and sealed key are separate; key is opened only after prediction digest commitment and blinding/leakage checks. |
| No circular dependency | M15 is downstream of M12–M14; M16 is terminal and cannot feed the stages it evaluates. |
| No external resources are implicit | All external callers, controls, databases, empirical datasets, and holdouts are absent from the required synthetic dependency graph. |

## 6. Validation boundary

The contract files are specifications only. This cross-check validates their
terminology, declared artifact references, and dependency direction; it does
not assert that an M12–M16 implementation, registry entry, production CI job,
biological truth set, or real-data authorization exists. The current roadmap
marks M1–M11 implemented and M12–M16 **PLANNED / NOT IMPLEMENTED**.

Readiness and resource records checked: [M12 contract](../M12_CONTRACT_FREEZE.md),
[M12 implementation plan](M12_IMPLEMENTATION_EXECUTION_PLAN.md),
[M12 semantic-axis resolution](M12_SEMANTIC_AXIS_RESOLUTION.md),
[M13 readiness](M13_PRECONTRACT_READINESS.md),
[M14 readiness](M14_PRECONTRACT_READINESS.md),
[M15 readiness](M15_PRECONTRACT_READINESS.md),
[M16 readiness](M16_PRECONTRACT_READINESS.md),
[implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md),
[decision register](M12_M16_DECISION_REGISTER.md),
[resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md), and
[validation logistics](M12_M16_VALIDATION_LOGISTICS.md).
