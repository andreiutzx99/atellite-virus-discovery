# M12–M16 implementation parallelization plan

**Status:** proposal for documentation-only planning. No implementation,
branch, merge, PR, data access, tool installation, or CI change is performed
by this document.

The five milestone plans are the intended workstream documents:
[M12](M12_IMPLEMENTATION_EXECUTION_PLAN.md),
[M13](M13_IMPLEMENTATION_EXECUTION_PLAN.md),
[M14](M14_IMPLEMENTATION_EXECUTION_PLAN.md),
[M15](M15_IMPLEMENTATION_EXECUTION_PLAN.md), and
[M16](M16_IMPLEMENTATION_EXECUTION_PLAN.md). This plan follows the dependency
graph and phases in the [implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md)
(lines 37–128). The current M12 semantic-axis and M15 interface resolutions
are recorded in the [independent audit](M12_M16_INDEPENDENT_CONTRACT_AUDIT.md)
(lines 44–84); neither is an open prerequisite.

## Answers to the ten execution questions

### 1. Which milestones can be implemented independently?

M13’s M5-only dossier, M14’s descriptive observation core, and M16’s generic
synthetic manifest/leakage/custody/metric mechanics can be developed
independently using generated fixtures. M12’s artifact-only baseline and
resolved semantic-axis mappings can also be developed independently. The
sequence explicitly lists
M12, M13, M14, and M16 as parallel synthetic workstreams
([sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md#phase-b--implement-independent-synthetic-baselines-in-parallel),
lines 93–105).

M15’s schema and envelope mechanics can begin independently, but its
integration and acceptance fixtures depend on stable M12–M14 output names,
schemas, semantic identities, and provenance states.

### 2. Which should wait for earlier milestone artifact contracts?

- **M12:** the approved semantic-axis clarification is available for its
  artifact-only baseline. Optional readers, controls, and real-data access
  remain separately gated. It consumes existing validated M5/M6 artifact types
  ([M12 contract](../M12_CONTRACT_FREEZE.md#2-runner-and-accepted-producer-artifacts),
  lines 40–58).
- **M13:** waits for existing M5 contracts only; it does not wait for M12,
  external callers, or comparator data. It preserves native event rows and
  raw status ([M13 contract](../M13_CONTRACT_FREEZE.md#2-runner-and-accepted-producer-artifacts),
  lines 38–49).
- **M14:** waits for no M12/M13 output. Its caller-authored observation table
  and optional M4/M7 refs are sufficient ([M14 contract](../M14_CONTRACT_FREEZE.md#2-runner-and-accepted-upstream-artifacts),
  lines 42–53).
- **M15:** its core schema may start early, but integration waits for the
  M12/M13/M14 output contracts and registrations to stabilize. It must not
  invent absent optional-stage records.
- **M16:** generic mechanics can start independently; target integration waits
  for frozen M12–M15 result-bundle types and identities. Empirical evaluation
  remains separately gated and is not part of this plan.

### 3. Can M12 and M13 safely be implemented in parallel?

Yes, subject to the M12 clarification gate. They consume different typed
surfaces and have no runtime dependency: M12 links M5/M6 retained artifacts,
while M13 imports only M5 caller-scoped records. M12 must not normalize M13
events, and M13 must not consume M12 output as a required input. Their shared
technical dependencies are validators, ArtifactRef/hash helpers, the workflow
runner, and test conventions—not shared scientific semantics.

### 4. What part of M14 can proceed independently?

All descriptive core mechanics can proceed: exact input shape, unit and
relationship validation, explicit tested/missing states, denominator frame,
four-cell descriptive counts, conflict handling, canonical serialization,
provenance, and stage-local cache identity. Synthetic M4/M7 references may be
generated or omitted. Inference, normalization, association statistics,
control adequacy, independence verification, and dependence experiments must
remain separate optional branches ([M14 contract](../M14_CONTRACT_FREEZE.md#1-scope-and-non-goals),
lines 8–26, and lines 183–191).

### 5. What exactly must M15 wait for?

M15 must wait for the *frozen interfaces*, not necessarily completed real-data
work:

1. M12–M14 artifact names, schemas, validators, producer-stage identities,
   semantic versions, and result-bundle identity rules.
2. Stable raw-status and missingness behavior for partial, failed,
   unavailable, incomplete, and invalid records.
3. M12's approved semantic-axis mappings when M15 maps M12 records beyond
   integrity/accounting fields.
4. Synthetic fixtures covering shared dependencies and unknown axes.

M15 must not wait for optional callers, real cohorts, ranking objectives, M11,
or restricted-data export. Its contract excludes M11 and preserves missing
optional branches explicitly ([M15 contract](../M15_CONTRACT_FREEZE.md#1-scope-and-non-goals),
lines 8–18).

The decision register marks M15's canonical axes/interface resolved by the
frozen contract. Ranking and restricted export remain deferred; neither blocks
the descriptive dossier
([audit](M12_M16_INDEPENDENT_CONTRACT_AUDIT.md#resolved--m15-decision-register-reconciliation),
lines 66–84).

### 6. What exactly must M16 wait for?

M16 generic public/sealed manifest, leakage, custody, execution-state, and
zero-denominator mechanics do not wait. M16 target integration must wait for:

- frozen M12–M15 result-bundle artifact types and validators;
- exact producer run-manifest, output digest, implementation/configuration
  identities;
- a synthetic target fixture and adapter identity;
- stable prediction commitment and sealed-key custody behavior.

M16 must not wait for, select, or represent empirical truth labels,
holdouts, biological thresholds, or external callers. The contract rejects
`EMPIRICAL` input and defines only software-contract expectations
([M16 contract](../M16_CONTRACT_FREEZE.md#1-scope-and-non-goals), lines 8–29).

### 7. Which shared files would cause branch/merge conflicts?

Highest-risk shared files are:

- `satellite_discovery/artifact_contracts.py`: global contract names,
  semantic versions, validator dispatch, and artifact validation. Avoid
  changing `VALIDATOR_SEMANTIC_VERSION`; per-contract additions must preserve
  unrelated cache identities.
- `satellite_discovery/artifact_workflow.py`: `build_default_registry`,
  typed input/output maps, stage handlers, report allowlists, and cache/reuse
  integration.
- `tests/test_stage_cache_identity.py`: shared scoped-invalidation regression
  tests; append focused cases rather than refactoring the file.
- `tests/test_artifact_validation.py` and workflow regression modules:
  shared validator and registration coverage.
- Lower-risk but still shared: `stage_registry.py`, `workflow_states.py`,
  `reproducibility.py`, and `sequence_downloader.py`. No change is expected
  unless a real generic gap is demonstrated; all contracts reuse existing M1
  lifecycle states.

Each milestone should put core logic in a new `satellite_discovery/m12_*`
through `m16_*` module and tests in new `tests/test_m12_*` through
`test_m16_*` modules. This minimizes collisions with M1–M11 code.

### 8. Which branch/PR sequence minimizes conflicts?

This is a proposal only; no branches or PRs are created here.

1. **Resolved contract decisions:** use the approved M12 semantic-axis
   clarification and the resolved M15 interface row. These decisions do not
   imply implementation; the milestones remain planned.
2. **Independent implementation branches:** develop M12, M13, M14, and M16
   core modules/tests on separate branches. M16 may remain mechanics-only.
3. **One shared-surface registration change at a time:** merge each branch’s
   additive artifact-contract entries and workflow registration serially,
   rebasing the next branch. Do not merge concurrent edits to
   `artifact_contracts.py` or `artifact_workflow.py` without rebasing.
4. **M15 integration branch:** begin schema work early, but merge its
   integration after M12–M14 names, validators, and result-bundle identities
   are stable.
5. **M16 integration branch:** connect M16 to M12–M15 bundles only after M15
   target references validate. Keep empirical benchmark authorization outside
   the merge sequence.

This order preserves the sequence’s rule that M12–M14 outputs feed M15 and
M16 is terminal ([sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md#phase-c--integrate-and-validate-handoffs),
lines 107–118).

### 9. Which tests should gate each merge?

Every merge gate includes the full offline suite:
`python -m unittest discover -s tests -v`, package installation,
`satellite-reviews --help`, and `python -I scripts/check_installed.py`.
The required CI matrix is Ubuntu and Windows × Python 3.11 and 3.12
([tests workflow](../../.github/workflows/tests.yml), lines 4–20).

| Merge | Focused gate before merge |
| --- | --- |
| M12 | Valid M5/M6 refs; completed-zero preservation; same-read dependency; empty `NOT_EVALUATED`; explicit external states; bad ref/path/digest/type/version; partial valid+corrupt input; resolved semantic-axis mappings; deterministic output, scoped cache mutation, verified reuse, and tamper rejection |
| M13 | Native M5 event bytes/order; completed caller zero; failed/interrupted/incomplete/unavailable states; optional raw absence; duplicate identity and accounting mismatch rejection; no cross-caller normalization; deterministic reuse |
| M14 | Four hand-counted 2×2 cells; tested denominator; missing/unknown/unavailable/not-applicable/conflicting rows; duplicate IDs and incomplete frames; M7 `UNVERIFIED` preservation; null ordering; descriptive-only output |
| M15 | Mixed M5–M14 records; raw schema/status round-trip; six semantic axes; unknown/unmapped values; `SAME_READ_SOURCE` and shared-reference edges; partial/invalid/conflicting refs; empty dossier; deterministic output/reuse and no ranking |
| M16 | Public/sealed separation; key commitment; group leakage; custody transitions; exact item/label axes; zero-denominator null rates; prediction/target digest mismatch; post-commit tamper; `EMPIRICAL` rejection and no metrics after integrity failure |

These focused gates should be added to the ordinary offline test discovery
only when the corresponding implementation exists. Optional biological tools,
databases, private reads, and truth payloads must never be merge gates
([validation logistics](M12_M16_VALIDATION_LOGISTICS.md#provisioning-recommendation),
lines 278–294).

### 10. Which work can run concurrently without changing the same shared files?

The following can run concurrently:

- M12 core parser/review tests, M13 M5 dossier tests, M14 descriptive
  normalization/count tests, and M16 synthetic manifest/leakage/custody/metric
  tests, provided each uses its own new module and test files.
- M15 contract/schema design and serializer prototypes can run concurrently,
  but not its final integration fixtures or registrations.
- Shared fixture-generator design can proceed in a neutral test helper or,
  preferably, as duplicated small local builders until a generic helper is
  justified. A shared helper must not encode milestone-specific state mapping.
- Documentation review, link checking, and cache-key test design can run in
  parallel with milestone-local implementation.

The following must be serialized or rebased:

- edits to `artifact_contracts.py`, `artifact_workflow.py`, and shared cache or
  validator tests;
- M15 integration against M12–M14 output contracts;
- M16 target integration against M15 and upstream result bundles;
- M12 shared implementation work that changes frozen semantic-axis mappings;
  such a contract change requires separate review.

## Conventions and non-negotiable boundaries

- Use `unittest`, temporary directories, generated deterministic fixtures, and
  hash-bound files, following [M10 workflow tests](../../tests/test_m10_workflow.py#L106-L181)
  and [cache identity tests](../../tests/test_stage_cache_identity.py#L46-L93).
- Use the existing allowlisted `artifact_workflow` runner and `--preflight`;
  do not add milestone-specific public CLIs, arbitrary loaders, or dynamic
  commands. This is explicit for M12–M16, e.g. M12 lines 24–38 and M16 lines
  31–37.
- Keep package dependencies unchanged. Required CI is offline and deterministic
  on Ubuntu/Windows with Python 3.11/3.12; optional Linux-only tools remain
  separate and unresolved resources are not promoted to core requirements
  ([resource/tool audit](M12_M16_RESOURCE_TOOL_AUDIT.md#4-resources-deliberately-not-selected),
  lines 231–241).
- Do not retrieve biological datasets, install optional callers, run candidate
  searches, assign holdouts, or claim biological performance. M1–M11 behavior,
  statuses, provenance, and cache identities remain unchanged.
- The matrix’s reusable fixture families are technical scaffolding only:
  [M12–M16 fixture matrix](M12_M16_FIXTURE_MATRIX.md) must be consulted when
  sharing bytes across workstreams.

M12–M16 implementation execution pack: READY
