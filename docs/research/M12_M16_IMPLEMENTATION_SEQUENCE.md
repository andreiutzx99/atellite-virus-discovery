# M12–M16 implementation sequence and parallel work

**Status: proposed order for synthetic/offline development only.** This
sequence reconciles the five readiness reports with the current
[roadmap](../ROADMAP.md), which marks M1–M11 implemented and M12–M16
**PLANNED / NOT IMPLEMENTED**.
It does not implement a stage, authorize data access, select a comparator, or
assign benchmark holdouts.

## 1. Current M1–M11 boundary

M11 is an implemented optional RNA-fold prediction stage. The M12–M16
contracts in this package do not make M11 a required input.

All M12–M16 work should consume existing typed artifacts and preserve their
stage identities. No upstream scientific-behavior change is required for the
synthetic baselines.

| Existing milestone | Stable interface relevant downstream | Required M12–M16 treatment |
| --- | --- | --- |
| M1 Foundation | Registered stages, typed artifact contracts, explicit lifecycle/failure states, provenance, verified reuse. | Preserve declared stage identity and failure states; do not invoke arbitrary commands or treat blocked work as success. |
| M2 Reference/acquisition | Supplied/imported reference snapshots and source/role/digest metadata; optional public-read acquisition paths. | Link immutable snapshots by identity. New source/reference acquisition is separately authorized and never required by offline CI. |
| M3 Assembly | Validated single/paired FASTQ, layout, registered assemblers, declared settings, validated assembly outputs. | Link existing assembly evidence; do not change assembly behavior or call read-back independent. |
| M4 Integrated workflow | Allowlisted stage graph, typed handoffs, manifests/reports, observations/context/QC/import stages. | Additive future registrations only if needed; no M4 semantic change for synthetic dossiers. |
| M5 DVG evidence | Single-end caller-scoped ViReMa events, accounting, status and provenance. | M13 preserves native M5 records; completed zero remains caller/method scoped. |
| M6 Residual support | QC-bound FASTQ, declared reference/roles, primary-mapping accounting, residual and eligible/unassembled FASTQ, triage, optional assembly/read-back. | M12 links persisted outputs; residual means unmapped under that declared reference/settings only; read-back reuses eligible reads. |
| M7 Recurrence | Stable observations, exact sequence recurrence, declared sample/run/study metadata and explicit technical states. | M14 may link IDs but must not treat declared independence as independently verified. |
| M8 Nucleotide homology | Candidate plus caller-supplied role-scoped snapshot, branch-specific outputs and scoped no-hit/failure/incomplete states. | Link as comparative context, not source attribution. No reference database is required for synthetic M12–M16. |
| M9 ORF/protein evidence | M6 candidate handoff, deterministic ORF hypotheses, optional supplied protein snapshot and typed BLASTP results. | Link as computational evidence only; no protein hit, no-ORF, or no-hit is a biological classification. |
| M10 Architecture/topology | Immutable candidate handoff, exact-first repeat branches and typed scoped results; optional M7–M9 context. | Link exact sequence-pattern evidence only; do not alter topology/function or classification boundaries. |

The [M1–M10 contract documents](../M1_FOUNDATION.md),
[M2](../M2_REFERENCE_ACQUISITION.md), [M3](../M3_ASSEMBLY.md),
[M4](../M4_INTEGRATED_WORKFLOW.md), [M5](../M5_DVG_EVIDENCE.md),
[M6](../M6_RESIDUAL_ASSEMBLY_SUPPORT.md), [M7](../M7_INDEPENDENT_RECURRENCE.md),
[M8](../M8_REFERENCE_AND_HOMOLOGY_SPEC.md), [M9](../M9_CONTRACT_FREEZE.md),
and [M10](../M10_CONTRACT_FREEZE.md), define the existing boundaries.
Historical status text that calls M9/M10 planned is superseded by the current
roadmap. Do not edit that text as part of this sequence.

## 2. Dependency graph

```text
                         ┌── M12 artifact-only review ─────┐
M1–M10 typed outputs ────┼── M13 M5-only evidence matrix ───┼── M15 dossier integration
                         ├── M14 descriptive observations ─┘
                         └── M16 manifest/leakage harness ───────┐
                                                                 └── final evaluation
M12/M13/M14/M15 frozen run identities and authorized truth/profile ─┘
```

This graph distinguishes software dependencies from optional evidence
dependencies:

- M12’s offline baseline consumes retained M5/M6 artifacts; real source-read,
  control, or batch analysis waits on data authorization and a claim-scoped
  control profile.
- M13’s core consumes M5 without cross-caller normalization. It may link M6–M12
  context when available. Optional callers and curated comparators are not
  prerequisites.
- M14’s descriptive table can be built independently. Actual inference waits
  for a justified unit map, matched observations/controls, and an analysis
  profile; experimental dependence evidence is separate.
- M15’s schema/dossier envelope can be defined early. Complete integration
  consumes the frozen output records of whichever upstream stages are present;
  absent optional stages remain explicit.
- M16’s manifest, leakage, and metric mechanics can be implemented in parallel
  using generated fixtures. Final evaluation waits for the evaluated workflow
  and interpretation policy to be frozen and for authorized/adjudicated truth,
  split grouping, independent custody, and blinding to be ready.

M11 is now implemented as an optional RNA-fold prediction stage. The frozen
M15 contract deliberately excludes M11 artifacts; adding them to M15 or M16
requires a separately reviewed contract version.

## 3. Recommended sequence

### Phase A — software-only interfaces frozen

The M12–M16 contract freezes now define these synthetic/offline interfaces;
this does not imply that any of the milestones is implemented:

1. M12: artifact-bounded inputs, explicit missing/invalid/failure semantics,
   and no unapproved raw-data readers.
2. M13: M5-only record preservation, with cross-caller event matching out of
   scope.
3. M14: declared observation units, tested denominators, and descriptive
   counts; no inferential profile or dependence claim.
4. M15: lossless evidence envelope and semantic axes; no ranking or M11 input.
5. M16: synthetic label/split manifests, leakage checks, custody events,
   execution states, and denominator/coverage mechanics; no empirical holdouts.

These decisions do not change M1–M11 inputs, outputs, scientific behavior, or
cache identity. Stage-local schemas and implementations receive their own
identity; a truly shared contract/validator semantic change follows the
existing invalidation policy.

### Phase B — implement independent synthetic baselines in parallel

| Workstream | Minimum offline deliverable | Can proceed in parallel? |
| --- | --- | --- |
| M12 | Verify/link M5/M6 artifact manifests; report scoped observations, missingness, and shared-read limitations. | Yes, alongside M13/M14/M16. |
| M13 | Preserve M5 events and build unresolved hypothesis rows with synthetic parser/accounting fixtures. | Yes; M12 and external callers are optional inputs. |
| M14 | Validate observation IDs, unit relationships, denominators, unknown states, and deterministic descriptive counts. | Yes; no public cohort or statistics package required. |
| M15 | Validate lossless envelope, state-axis separation, dependency graph, and duplicate/shared-source handling on typed fixtures. | Schema can proceed in parallel; integration fixtures wait for M12–M14 output schemas. |
| M16 | Validate label-state handling, duplicate/group leakage prevention, hidden-label/custody mechanics, and hand-calculated metric denominators. | Yes with generated data; final run is separately gated. |

All tests in this phase use synthetic payloads. Required CI stays deterministic,
offline, and free of private reads, biological databases, unresolved callers,
or benchmark payloads.

### Phase C — integrate and validate handoffs

1. Confirm M12/M13/M14 output schemas and identities independently.
2. Integrate only records actually present into M15; test partial inputs,
   conflicts, failures, unavailable branches, shared dependencies, and
   deterministic output.
3. Connect M16’s synthetic evaluator to frozen M12–M15 output bundles. Verify
   exact run/profile/reference identities and leakage rejection before any
   source-data evaluation.
4. Preserve upstream outputs as immutable references; a changed producer
   artifact changes downstream identity through its hash rather than rewriting
   the producer’s history.

### Phase D — authorize real-data work separately

Only after explicit approval, select a specific optional branch and document
its source, terms, access/privacy scope, retention, exact tool/reference
versions, and validation criteria. Then separately define matched controls,
independence/denominator rules, truth-label tiers, leakage groups, holdout
custody/blinding, metric profile, and claim-specific experimental needs.
Unresolved optional resources remain unavailable/unassessed; they do not become
core blockers or candidate rejections.

## 4. Readiness summary

The baseline contracts are now frozen, but none of M12–M16 is implemented.
The readiness dispositions below do not authorize work outside those baselines.

| Milestone | Disposition | Frozen baseline | What remains gated |
| --- | --- | --- | --- |
| M12 | READY FOR SYNTHETIC IMPLEMENTATION WITH DEFERRED REAL-DATA DECISIONS | Artifact-bounded envelope and semantic axes are frozen. | Source-data authorization, matched-control policy, optional readers/panels, source-attribution claims. |
| M13 | READY FOR SYNTHETIC IMPLEMENTATION WITH DEFERRED REAL-DATA DECISIONS | M5-only synthetic/offline dossier is frozen; no cross-caller normalization. | Optional callers/terms, cross-caller event identity, curated empirical comparators, biological class/interference claims. |
| M14 | READY FOR CONTRACT FREEZE | Descriptive observation schema, declared unit type, denominator and unknown-state rules are frozen. | Dataset-specific independence, matched real data, optional inferential model, dependence experiments. |
| M15 | READY FOR CONTRACT FREEZE | Lossless descriptive evidence envelope is frozen; it excludes M11 and ranking. | Optional ranking objective/calibration and export of restricted source data. |
| M16 | READY FOR SYNTHETIC IMPLEMENTATION WITH DEFERRED REAL-DATA DECISIONS | Generic synthetic manifest, leakage, custody, and metric mechanics are frozen. | Claim-specific truth/labels, actual grouping/splits, independent custodian, final metrics/stop rules, real performance and experimental claims. |

## 5. Scope and required non-changes

- No production code, tests, CI, README, ROADMAP, or existing research file is
  changed by these readiness reports.
- No M11 implementation work, biological dataset retrieval, sequence-database retrieval,
  candidate-data analysis, unresolved tool installation, or benchmark holdout
  assignment is performed.
- No M1–M11 scientific behavior or interface change is required for the
  synthetic baselines. Any additive future stage registration must remain
  typed, stage-scoped, and optional where the evidence itself is optional.
- A missing source, caller, control, metadata field, or benchmark label remains
  missing/unassessed. It is never converted into candidate rejection.
