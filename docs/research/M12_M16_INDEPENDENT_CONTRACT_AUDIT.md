# Independent audit of frozen M12–M16 contracts

**Audit type:** adversarial, read-only contract review
**Disposition:** no blocking contract defect found; all five contracts are
approved only for their stated synthetic/offline baselines.

## Scope and conclusion

This review compared the five frozen contracts and their
[cross-check](M12_M16_CONTRACT_CROSSCHECK.md) with the M12–M16 design research,
pre-contract readiness reports, [resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md),
[validation logistics](M12_M16_VALIDATION_LOGISTICS.md),
[decision register](M12_M16_DECISION_REGISTER.md),
[implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md), the current
[roadmap](../ROADMAP.md), and the implemented M1–M11 contract boundaries.

No blocking defect was found in the frozen synthetic/offline scope. The
contracts preserve the distinction between software state and biological
conclusion, do not make optional callers or data mandatory, and do not introduce
an M11 dependency or a cycle. The concerns below merit clarification before
implementing or extending the affected interfaces, but they do not invalidate
the explicitly bounded offline baselines.

Approval does **not** approve new real-data access, external-caller
provisioning, biological classification or dependence claims, empirical
holdouts, or performance claims. M12–M16 remain **PLANNED / NOT IMPLEMENTED**;
these freezes define implementable software baselines, not completed milestones
([roadmap](../ROADMAP.md), lines 24–35).

## Milestone dispositions

| Milestone | Independent verdict | Exact approval boundary |
| --- | --- | --- |
| M12 | **APPROVED FOR SYNTHETIC/OFFLINE IMPLEMENTATION** | Verify and describe retained M5/M6 artifacts only. No new read analysis, controls interpretation, source attribution, or candidate rejection. |
| M13 | **APPROVED FOR SYNTHETIC/OFFLINE IMPLEMENTATION** | Preserve M5 caller-scoped records in an unresolved dossier. No cross-caller comparison, universal DVG class, function, or dependence claim. |
| M14 | **APPROVED FOR SYNTHETIC/OFFLINE IMPLEMENTATION** | Validate declared observation frames and report descriptive counts. No inferential association, verified independence by identifier, or dependence claim. |
| M15 | **APPROVED FOR SYNTHETIC/OFFLINE IMPLEMENTATION** | Preserve typed upstream evidence and dependencies in a descriptive dossier. The frozen baseline excludes M11 input. No ranking, classifier, or restricted-data export authorization. |
| M16 | **APPROVED FOR SYNTHETIC/OFFLINE IMPLEMENTATION** | Test generated-fixture split, custody, prediction, and metric mechanics only. No empirical labels, actual holdout assignment, or biological performance claim. |

## Findings and clarifications

### BLOCKING — None found

### RESOLVED AFTER THIS AUDIT — M12 semantic-axis detail

At the time of this review, the question was whether M12's frozen artifact
records explicitly represented validity, applicability, execution,
completeness, observation, and interpretation states. That concern is
superseded for the frozen baseline by the approved [M12 contract semantic
clarification](../M12_CONTRACT_FREEZE.md#41-semantic-clarification-contract-erratum)
and [semantic-axis resolution](M12_SEMANTIC_AXIS_RESOLUTION.md), which define
the axes and mappings while retaining producer states. The [current M12
implementation plan](M12_IMPLEMENTATION_EXECUTION_PLAN.md) records the
resolution. This does not authorize new read/control analysis or expand the
artifact-only baseline. M12 remains PLANNED / NOT IMPLEMENTED.

### RESOLVED — M15 decision-register reconciliation

The M15 readiness report explicitly resolves the raw-status/interface choice
and marks the descriptive dossier ready for contract freeze
([M15 readiness](M15_PRECONTRACT_READINESS.md), lines 97–116); the
implementation sequence likewise says to freeze the lossless envelope and
proceed with synthetic fixtures ([implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md),
lines 73–105). The frozen contract now defines the raw-preserving envelope and
semantic axes ([M15 freeze](../M15_CONTRACT_FREEZE.md), lines 94–137).

The decision register now marks M15's canonical axes/interface as resolved,
and the frozen contract defines the raw-preserving envelope and semantic axes.
This closes the earlier reconciliation item; ranking and restricted export
remain separately deferred. M15 remains PLANNED / NOT IMPLEMENTED.

### NON-BLOCKING — M15 artifact-retention boundary

M15 requires immutable producer references with paths and digests and states
that the source object remains retrievable unchanged through `producer_ref`
([M15 freeze](../M15_CONTRACT_FREEZE.md), lines 44–54 and 109–112). That is
consistent with the readiness requirement to retain raw status, payload
references, and provenance ([M15 readiness](M15_PRECONTRACT_READINESS.md),
lines 10–34). The freeze does not specify a retention lifetime or custody
behavior if a referenced producer artifact later disappears. For the local
offline baseline, the immutable reference plus integrity check is sufficient;
before remote/export or long-term archival use, specify retention and
unavailable-versus-corrupt handling. The freeze does not grant permission or
infer redistribution rights; any export remains separately authorized.

### NON-BLOCKING — M12 four evidence slots and six state values

The input declares four external-evidence entries, and each entry can take one
of six listed states ([M12 freeze](../M12_CONTRACT_FREEZE.md), lines 97–103).
The summary and provenance language says it repeats/records “the four”
external-evidence states (lines 122–130 and 167–170). Read in context, “four”
refers to the four evidence entries, not a reduced four-value enum; the cache
identity includes each entry’s complete state and note (lines 173–180).
Clarifying the wording as “all four entries with their six-value states” would
prevent misreading, but no dropped state is required by the schema.

## Deferred by design, not defects

- **M12:** New FASTQ, SAM/BAM/CRAM readers, remapping, controls, batches, and
  sensitive metadata remain optional and authorization-gated. The frozen
  baseline is explicitly limited to retained M5/M6 artifacts
  ([M12 contract](../M12_CONTRACT_FREEZE.md) and
  [decision register](M12_M16_DECISION_REGISTER.md)).
- **M13:** The design research discusses future caller comparison, but the
  readiness report explicitly permits the M5-only dossier to freeze without
  cross-caller normalization or external tools
  ([M13 readiness](M13_PRECONTRACT_READINESS.md), lines 118–152; [M13 design
  research](M13_DVG_DIFFERENTIAL_DESIGN_RESEARCH.md), lines 91–99;
  [M13 freeze](../M13_CONTRACT_FREEZE.md), lines 15–49). This baseline is a
  descriptive input layer, not completion of the roadmap’s biological
  DVG-versus-satellite question.
- **M14:** Dataset permissions, verified independence, matched real cohorts,
  controls, inferential models, and dependence experiments remain separate
  decisions. The contract distinguishes explicit tested denominators from
  missingness and keeps association separate from dependence
  ([M14 readiness](M14_PRECONTRACT_READINESS.md), lines 126–137;
  [validation logistics](M12_M16_VALIDATION_LOGISTICS.md), lines 150–158).
- **M15:** The research/readiness package permits M11 only as a future optional
  source. The freeze correctly requires a separately frozen type/version
  before admitting it and does not make M11 a dependency
  ([M15 readiness](M15_PRECONTRACT_READINESS.md), lines 25–27;
  [M15 freeze](../M15_CONTRACT_FREEZE.md), lines 16–18).
  Ranking objectives and restricted-data export remain optional/deferred.
- **M16:** Group membership is supplied in synthetic fixtures; the contract
  checks split consistency for declared non-empty group IDs, not biological
  duplicate discovery or completeness of an empirical grouping graph
  ([M16 freeze](../M16_CONTRACT_FREEZE.md), lines 84–102 and 152–159). Actual
  duplicate/near-duplicate curation, highest-dependence grouping, truth tiers,
  custodians, and holdout assignments remain deferred
  ([M16 readiness](M16_PRECONTRACT_READINESS.md), lines 82–96 and 131–149).

## Cross-contract and implementation-boundary checks

- **No negative inference from missing evidence:** M12 preserves explicit
  external states; M13 confines a completed zero to its M5 scope; M14 requires
  a declared pair/unit frame; M15 preserves missing and unknown states; M16
  separates prediction counts from synthetic-label counts
  ([cross-check](M12_M16_CONTRACT_CROSSCHECK.md), lines 42–59 and 120–128).
- **Failure and incompleteness remain distinct:** The contracts preserve raw
  producer status and separate failure, interruption, incomplete, invalid,
  unavailable, and no-result handling where applicable. The M12 axis precision
  and M15 artifact-retrieval clarifications are recorded above. No missing
  branch is silently rewritten as a completed no-signal.
- **M1–M11 compatibility:** The contracts consume existing typed artifacts
  and lifecycle states; M13 does not normalize coordinate conventions, M14
  does not upgrade M7’s declared independence, and M15 links rather than
  reclassifies upstream evidence. M15 deliberately excludes M11 artifacts.
  No M1–M11 scientific-behavior change is
  required ([implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md),
  lines 15–35; [cross-check](M12_M16_CONTRACT_CROSSCHECK.md), lines 60–92).
- **No cycle or required M11 dependency:** M12/M13/M14 feed M15; M16 is
  terminal; M11 is not part of the frozen M15 input set
  ([cross-check](M12_M16_CONTRACT_CROSSCHECK.md), lines 18–30;
  [implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md), lines 37–69).
- **No mandatory external resources or CI mismatch:** Required validation is
  synthetic/offline; optional callers, biological databases, private reads,
  and real benchmark payloads are not required
  ([resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md), lines 231–241;
  [validation logistics](M12_M16_VALIDATION_LOGISTICS.md), lines 278–294).
- **Provenance, cache identity, and deterministic ordering:** Each contract
  binds its consumed inputs and output hashes and defines stable serialization
  or ordering. No coordinate normalization or shared-evidence vote inflation
  is introduced in the offline baselines.

No contract was edited during this audit. The only deliverable from this review
is this report.

M12–M16 synthetic/offline contracts: APPROVED FOR IMPLEMENTATION ONLY;
M12–M16 remain PLANNED / NOT IMPLEMENTED.
