# M16 implementation execution plan

**Status:** M16 planning only. The separate cache/source-identity prerequisite
is implemented on an unmerged infrastructure branch; M16 implementation must
wait until that prerequisite is reviewed, merged, and passes its full regression
and CI gates. This plan does not select a dataset, assign a holdout, or
authorize empirical execution.

This plan covers the frozen generic synthetic benchmark and leakage harness.
The contract explicitly separates software correctness from benchmark
performance, biological validation, and experimental confirmation
([M16 contract](../M16_CONTRACT_FREEZE.md), lines 1–29;
[M16 readiness](M16_PRECONTRACT_READINESS.md), lines 8–26). All fixtures and
expected outcomes described here are software-contract fixtures, not biological
truth.

The cache prerequisite's scope, identity migration, and pending gates are
recorded in [M16 registration/cache decoupling](M16_REGISTRATION_CACHE_DECOUPLING.md).
Its branch implementation does not register or implement M16.

## 1. Frozen implementation boundary

Implement only the allowlisted `m16_synthetic_benchmark` stage through the
existing artifact-workflow manifest runner and preflight path. Do not add a
top-level command, dynamic loader, arbitrary command execution, biological-data
loader, external caller, sequence/read retrieval, or empirical benchmark path
([M16 contract](../M16_CONTRACT_FREEZE.md), lines 31–37).

The evaluator must accept only frozen, identity-bound result bundles from:

- M12: `m12_result_bundle`;
- M13: `m13_result_bundle`;
- M14: `m14_result_bundle`;
- M15: `m15_result_bundle`.

Each target reference must carry the producer stage, producer run-manifest
SHA-256, artifact type and semantic version, relative path, output SHA-256, and
exact target implementation/configuration identity
([M16 contract](../M16_CONTRACT_FREEZE.md), lines 39–52).

**Integration gate:** M16 evaluator integration must wait until the M12–M15
result bundle artifact contracts, registrations, schemas, semantic versions,
and identity behavior are frozen and available. A target must be frozen before
fixture predictions are generated. M16 may develop its standalone manifest,
leakage, custody, serializer, and metric mechanics with generated fixtures in
parallel, but it must not invent substitute upstream bundles or silently accept
untyped placeholders. The broader sequence places M15 integration after M12–M14
schemas and M16 final evaluator integration after M12–M15 bundles
([implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md), lines 93–118).
The shared cache/source-identity prerequisite is an additional gate: it must be
merged with the M1–M15 regression boundary passing before M16 implementation
begins. Final M16 integration still requires an actual offline synthetic M15
execution, its authenticated `m15_result_bundle`, and M16 consuming that exact
bundle; mocks do not satisfy this gate.

Reject `dataset_kind = "EMPIRICAL"` as `OUT_OF_SCOPE`; empirical labels,
biological truth tiers, actual development/tuning/holdout membership, and
holdout assignments are forbidden in this implementation
([M16 contract](../M16_CONTRACT_FREEZE.md), lines 16–29;
 [M16 readiness](M16_PRECONTRACT_READINESS.md), lines 131–149).

## 2. Proposed modules and additive registration

### New modules

Create the following only when implementation begins:

1. `satellite_discovery/m16_contracts.py`
   - Validate the public manifest, sealed synthetic key, target references,
     prediction rows, leakage report, custody events, metric summary, and
     result bundle.
   - Own exact enums, unknown-field policy, SHA-256/path containment checks,
     fixture-set/key coverage, synthetic provenance, group/split validation,
     and canonical serialization helpers.
   - Keep label states separate from execution and outcome states.
2. `satellite_discovery/m16_stage.py`
   - Implement the trusted stage handler and stage-scoped implementation
     identity.
   - Separate public target execution from post-commit scoring.
   - Enforce the custody state machine, leakage gate, prediction commitment,
     sealed-key access boundary, deterministic metric accounting, and output
     writing.
3. Test-only fixture adapter/factory under `tests/` (for example,
   `tests/m16_fixture_adapter.py`).
   - Generate synthetic inputs and opaque software outcomes.
   - It must never provide biological labels, retrieve payloads, or infer
     positive/negative meaning. A contract-approved adapter ID/version is part
     of the synthetic identity.

Do not broaden `satellite_discovery/artifact_benchmark.py` into M16. Its older
role/classification fields and supplied-digest behavior are not the M16
public/sealed-key contract; use it only as a historical workflow pattern
([artifact benchmark](../../satellite_discovery/artifact_benchmark.py), lines
1–10, 17–24, 64–73).

### Additive shared changes

When the new modules exist, make additive changes only:

- `satellite_discovery/artifact_contracts.py`: register
  `m16_prediction_table`, `m16_leakage_report`, `m16_custody_log`,
  `m16_metric_summary`, and `m16_result_bundle`; add per-contract validators
  and semantic versions. Do not change the shared validator semantic version
  for M16-only behavior.
- `satellite_discovery/artifact_workflow.py`: import/register
  `m16_synthetic_benchmark` in `build_default_registry()`, declare its typed
  inputs and five outputs, and add only any required report allowlist entries.
  The existing registry supports dynamic inputs, config validation, and typed
  output maps ([workflow registration](../../satellite_discovery/artifact_workflow.py),
  lines 46–124, 293–318).
- `tests/test_artifact_validation.py` and
  `tests/test_stage_cache_identity.py`: add focused M16 validator and
  stage-local cache-isolation coverage.
- Do not change `stage_cache_identity.py` or broaden the compatibility aliases
  for M16. M16-only contracts, implementation sources, and registry entries
  must leave existing M1–M15 identities stable; only a genuinely shared
  behavior change may invalidate stages that depend on it.
- Existing `workflow_states.py` should not change. Custody states are artifact
  events; workflow lifecycle remains the M1 state set
  ([M16 contract](../M16_CONTRACT_FREEZE.md), lines 120–124, 161–179).

No `pyproject.toml` dependency, package-data, entry point, or public CLI change
is expected. Package discovery already includes new `satellite_discovery`
modules, and the existing artifact-workflow runner remains the interface.

## 3. Inputs and output artifact names

### Public manifest

Validate UTF-8 JSON with schema `m16-public-manifest-v1` and fields:
`dataset_kind`, `fixture_set_id`, `target_ref`, `adapter_id`,
`adapter_version`, and `items`. Each item has a unique `item_id`, hash-bound
synthetic `target_input_ref`, sorted `group_ids`, a generic `split_role`,
`label_state`, and explicit synthetic fixture provenance
([M16 contract](../M16_CONTRACT_FREEZE.md), lines 54–71, 84–93).

Allowed split roles are `DEVELOPMENT`, `TUNING`, `SYNTHETIC_HOLDOUT`, and
`UNASSIGNED`. They exercise generic split mechanics only; they do not select
real partitions.

### Sealed synthetic key

Validate separately hashed UTF-8 JSON with schema `m16-synthetic-key-v1`,
matching `fixture_set_id`, and one entry per labelled item. Each entry has
`item_id`, an adapter-defined opaque `expected_software_outcome`, and
`label_scope = "SOFTWARE_CONTRACT"`. `UNKNOWN` and `NOT_APPLICABLE` items have
no expected outcome. The public target path must never receive key contents or
an expected-outcome path ([M16 contract](../M16_CONTRACT_FREEZE.md), lines
73–105).

### Output artifacts

Register these exact output types:

| Artifact | Required contents |
| --- | --- |
| `m16_prediction_table` | One prediction row per public item, target provenance, execution/outcome state, and no emitted value for non-completed rows. |
| `m16_leakage_report` | Group/split checks, offending IDs, deterministic status, and score-blocking reason when leakage is detected. |
| `m16_custody_log` | Append-only, sequence-numbered transitions with actor/tool identity, relevant digests, and reason. |
| `m16_metric_summary` | Independent item/prediction and label axes, exact counts, denominator-aware rates, and software-fixture scope. |
| `m16_result_bundle` | Public/key commitments, target and adapter identities, prediction/scoring digests, custody evidence, output references, and cache-relevant identity. |

The output filenames should be fixed in the stage registration to avoid
ambiguous output discovery. The bundle must not become an upstream M12–M15
input.

## 4. Validators and serializers

### Validation responsibilities

`m16_contracts.py` should validate, before execution where possible:

- exact schemas and allowed fields;
- `SYNTHETIC_FIXTURE` dataset kind and fixture provenance;
- unique item IDs and one key row per labelled item;
- matching public/key fixture-set IDs;
- accepted M12–M15 target type, producer identity, run-manifest digest,
  semantic version, output digest, relative path, and target implementation/
  configuration identity;
- adapter registration and immutable adapter version;
- sorted group IDs and valid split roles;
- no expected outcome or key path in public inputs;
- prediction coverage: exactly one row per public item;
- completed outcome states (`EMITTED`, `ABSTAINED`, `NOT_APPLICABLE`,
  `UNKNOWN`) versus null/unknown outcomes for non-completed execution;
- independent item-state and label-state partitions;
- custody transition order and terminal integrity failure;
- no metrics after leakage, blinding, target-digest, key, or prediction
  integrity failure.

All shared artifact descriptors should use existing digest, path containment,
and typed-contract validation patterns. Do not use a missing or unknown label
as a negative label.

### Canonical serialization

Use an M16-local serializer rather than changing a shared serializer used by
M1–M11. It must emit UTF-8 JSON without BOM, LF line endings, one trailing
newline, sorted object keys, and no NaN/Infinity. Sort public items and
predictions by `item_id`, group checks by group and split, custody events by
sequence number, and metric rows by adapter-defined outcome
([M16 contract](../M16_CONTRACT_FREEZE.md), lines 181–208).

## 5. Cache and provenance identity

Use the existing stage-scoped cache machinery and output verification. The M16
identity must bind:

- public-manifest digest and fixture-set ID;
- exact M12–M15 target producer/run/artifact/output digests;
- target implementation/configuration identity;
- adapter ID/version;
- group graph, split roles, and label-state summary;
- sealed-key commitment;
- prediction digest;
- scoring implementation/version;
- M16 contract semantic version;
- every output digest.

M16 implementation may use the shared stage-source identity composition only
after its infrastructure prerequisite has merged. M16 must own its source and
contract dependencies; do not add M16 source files to upstream inventories or
preserve the pre-prerequisite M15 identity that omitted producer-verification
behavior.

Target execution identity excludes sealed key content and expected outcomes,
but includes the sealed-key commitment. Scoring identity additionally binds the
sealed-key and prediction digests. Any target, fixture, adapter, config,
scoring, or contract change invalidates M16 only; it must not rewrite or
invalidate M12–M15 outputs ([M16 contract](../M16_CONTRACT_FREEZE.md), lines
210–223). Add a test proving that an unrelated new contract does not alter
existing stage identities, following `tests/test_stage_cache_identity.py`.

## 6. Synthetic fixture and adapter matrix

The fixture adapter must generate only opaque software-contract expectations.
The following cases are required:

| Fixture family | Required cases and assertions |
| --- | --- |
| Label-state isolation | `SEALED_SYNTHETIC_EXPECTATION`, `UNKNOWN`, and `NOT_APPLICABLE`; unknown/N/A never enter `n_labelled` or a negative denominator. No empirical positive/negative labels. |
| Matching outcomes | Fully synthetic expected outcomes with exact emitted predictions; hand-calculate `n_labelled`, `n_emitted`, `n_exact_match`, coverage, and both fixture rates. |
| Leakage groups | Exact duplicate, near-duplicate/family, sample/run/study/lab-like groups; shared non-empty group across split roles yields `LEAKAGE_DETECTED` and blocks scoring. |
| Custody/blinding | Key unavailable to target; valid `SEALED → PREDICTIONS_COMMITTED → BLINDED_CHECKED → SCORED`; premature key access, changed identity, wrong commitment, corrupt key, or post-commit prediction mutation yields terminal `INTEGRITY_FAILED` and no metrics. |
| Execution states | Completed emitted/abstained/unknown/N/A plus `NOT_EVALUATED`, `DEPENDENCY_UNAVAILABLE`, `FAILED`, `INTERRUPTED`, `INCOMPLETE`, `TRUNCATED`, and `INVALID_INPUT`; every item remains counted once. |
| Denominators/rates | `n_items` item axis and three-way label axis each sum correctly; zero labelled/emitted denominators serialize null rates, never zero or divide-by-zero. |
| Target refs | Each accepted M12–M15 bundle type; wrong type/schema/version, missing path, changed upstream bytes, or target identity mismatch is rejected. |
| Input integrity | Duplicate item/key IDs, malformed group IDs, unsorted group IDs, fixture mismatch, BOM/CRLF/NaN, empirical dataset kind, biological label claim, and unsafe paths are rejected. |

The cross-milestone fixture reuse rules belong in
[M12–M16 fixture matrix](M12_M16_FIXTURE_MATRIX.md); sequencing and shared-file
ownership belong in [parallelization plan](M12_M16_PARALLELIZATION_PLAN.md).
Reuse must preserve M16 label, custody, and metric semantics rather than
conflating M14 observation states or M15 dossier axes with benchmark truth.

## 7. Failure, interruption, and incomplete behavior

- Invalid public/key manifest, target reference, adapter, hash, schema, path,
  or fixture provenance fails before target execution.
- Missing target dependencies map to existing M1 `dependency_missing` or
  `external_module_required`; do not create a new workflow state.
- Leakage, hidden-label access, target identity mismatch, corrupt key, or
  changed prediction digest yields `INTEGRITY_FAILED`, M1 `failed`, and no
  metric artifact.
- Per-item unavailable, failed, interrupted, incomplete, truncated, or
  abstained states remain in the prediction table and denominators; rows are
  never silently dropped.
- A target interruption must not leave a committed prediction artifact that
  can be scored. Custody transitions and output writing should be atomic enough
  that an incomplete run cannot be mistaken for `SCORED`.
- A completed item has exactly one outcome state. A non-completed item has a
  null/unknown outcome and is counted by execution state
  ([M16 contract](../M16_CONTRACT_FREEZE.md), lines 181–202).

## 8. Test modules and regression gates

Add focused `unittest` modules:

- `tests/test_m16_contracts.py`: schemas, enums, unknown fields, hashes,
  target refs, public/sealed separation, adapter registration, and bundle
  validation.
- `tests/test_m16_leakage.py`: transitive group overlap, duplicate/near-
  duplicate synthetic groups, split consistency, malformed IDs, deterministic
  reports.
- `tests/test_m16_custody.py`: state transitions, key-access audit,
  commit-before-score, tampering, integrity terminal behavior, and
  interruption/failure recovery.
- `tests/test_m16_metrics.py`: hand-calculated item/label axes, exact-match
  counts, null denominators, all execution states, and outcome handling.
- `tests/test_m16_serialization.py`: byte identity, ordering, newline/BOM,
  NaN/Infinity rejection, and repeated-run hashes.
- `tests/test_m16_workflow.py`: registration, preflight, typed target handoff,
  synthetic execution, verified reuse, output tamper rejection, and
  stage-local cache invalidation.

Extend `tests/test_artifact_validation.py` for output contracts and
`tests/test_stage_cache_identity.py` for M16-only invalidation. The M1–M11
regression suite must remain unchanged and pass, including M4 workflow/
artifact validation, M5 DVG, M6 residual/read support, M7 recurrence/cache,
M8 homology, M9 ORF/protein, M10 topology, and M11 RNA-fold prediction tests.
Specifically assert:

- no M12–M15 artifact is rewritten;
- M5 completed-zero remains caller-scoped;
- M6 same-read provenance is not counted as independent evidence;
- M7 declared independence is not upgraded;
- M8/M9 no-hit and failure states remain method-scoped;
- M10 exact architecture remains non-biological.

## 9. CLI, package, and CI implications

Use only:

```text
python -m satellite_discovery.artifact_workflow \
  --manifest <workflow.json> --output <output-directory>
```

No M16-specific CLI, dependency, external tool, database, payload, or package
data is required. Add synthetic tests to existing offline unittest discovery.
Required CI remains Ubuntu/Windows × Python 3.11/3.12 with package install and
the existing installed-package smoke checks
([tests workflow](../../.github/workflows/tests.yml), lines 4–20). Do not add
private reads, empirical labels, holdouts, biological databases, or optional
callers to required CI. Optional-tool CI remains separate and is not an M16
gate ([validation logistics](M12_M16_VALIDATION_LOGISTICS.md), lines 278–294).

## 10. Implementation order and invariants

0. Verify the shared cache/source-identity prerequisite is merged and its
   required Linux/Windows and M1–M15 regression checks pass.
1. Build the test-only synthetic fixture adapter and local canonical serializer.
2. Implement standalone public/key/target schemas and validators.
3. Implement group/leakage checks and independent state partitions.
4. Implement prediction commitment, custody/blinding transitions, and
   integrity-failure handling.
5. Implement deterministic metric accounting and result-bundle identity.
6. Add artifact-contract registrations and validators.
7. Add the allowlisted workflow registration and preflight/typed handoffs.
8. Add workflow, reuse, tamper, interruption, and cache-isolation tests.
9. Integrate target references only after M12–M15 result bundle identities and
   registrations are frozen; then run the full offline regression suite.

Tests must enforce these invariants:

- synthetic expectations are never biological truth;
- public execution never receives sealed key contents;
- leakage blocks scoring rather than becoming a negative result;
- every public item is counted exactly once on the prediction axis;
- label counts are independent of prediction execution counts;
- zero denominators produce null rates;
- non-completed outcomes are not emitted;
- integrity failure produces no metrics;
- deterministic inputs produce byte-identical outputs;
- M16 cache changes do not rewrite upstream M12–M15 artifacts;
- empirical labels, empirical holdouts, and biological performance claims are
  rejected or deferred, never silently approximated.

M16 implementation remains a synthetic software harness. It cannot establish
identity, source, DVG/satellite status, helper dependence, function,
sensitivity, specificity, accuracy, calibration, or any other biological
claim. Claim-specific truth tiers, grouping policy, custodian, actual holdout,
metrics, uncertainty, stop rules, rights, privacy, and assays require separate
decisions before any empirical evaluation
([M16 readiness](M16_PRECONTRACT_READINESS.md), lines 131–159;
[benchmark research](M16_VALIDATION_BENCHMARK_DESIGN_RESEARCH.md), lines
163–175).
