# M14 implementation execution plan

**Status:** planning only. M14 remains planned and this document does not
implement a production stage, select a dataset, or authorize real-data use.
The approved baseline is a descriptive, synthetic/offline observation-table
validator and transparent count report ([M14 contract freeze](../M14_CONTRACT_FREEZE.md),
lines 1–17, 193–213).

## 1. Implementation boundary

The implementation should add the allowlisted `m14_descriptive_observations`
stage behind the existing artifact-workflow runner. It must consume a
caller-authored `m14-input-v1` manifest, validate the declared sampling frame,
normalize accepted observations, and emit descriptive counts. It must not infer
independence, treat missing rows as negatives, fit a model, normalize abundance,
or establish helper dependence ([contract freeze](../M14_CONTRACT_FREEZE.md),
lines 8–26, 50–78; [readiness](M14_PRECONTRACT_READINESS.md), lines 8–19,
26–31).

The only accepted upstream references are the frozen M4 table types and M7
recurrence outputs. They are provenance/context links; M7's declared
independence remains unverified unless the M14 manifest supplies a separate
verification record ([contract freeze](../M14_CONTRACT_FREEZE.md), lines
28–53, 71–78). No raw reads, sequence database, M5/M8/M9 result, public
cohort, or external statistics package is required.

## 2. Likely implementation surface

### New modules

1. `satellite_discovery/m14_descriptive_observations.py`
   - Own the `m14-input-v1` configuration validator and stage handler.
   - Validate exact fields, enums, IDs, foreign keys, pair/unit frames,
     `MethodRef`, `DetectionLimit`, source references, and state/tested
     invariants.
   - Normalize rows without changing source-declared values.
   - Calculate only the specified tested counts, missingness counts, conflict
     counts, and four evaluable 2×2 cells.
   - Emit the three output documents, provenance, lifecycle/result state, and
     stage-scoped implementation identity.
   - Keep the module analogous in structure to
     `satellite_discovery/independent_recurrence.py`, which already provides
     stage versioning, config validation, dynamic inputs, canonical JSON,
     input-contract checking, provenance, and cache identity (see
     `independent_recurrence.py`, lines 19–52, 125–139, 241–267).

2. A local canonical serializer may be kept in the M14 module rather than
   changing the shared `sequence_downloader.write_json`. It must produce UTF-8
   JSON with no BOM, LF line endings, one trailing newline, sorted object keys,
   and no NaN/Infinity ([contract freeze](../M14_CONTRACT_FREEZE.md), lines
   215–219). Do not change the shared serializer merely for M14.

### Additive shared changes

- `satellite_discovery/artifact_contracts.py`: add descriptions, semantic
  versions, and validator dispatch for:
  `m14_observation_table`, `m14_descriptive_summary`, and
  `m14_result_bundle`. Reuse `validate_artifact`, `describe_artifact`,
  `verify_descriptor`, `checksum`, `semantic_identity`, and the existing M4/M7
  validators. Do not change existing M4/M7 validation semantics.
- `satellite_discovery/artifact_workflow.py`: import the new module and add one
  `m14_descriptive_observations` registration with dynamic typed inputs,
  config validation, input contract allowlist, and the three output contracts.
  If the consolidated `workflow_report` is extended, add the new M14 types
  additively and preserve its existing behavior.
- `satellite_discovery/stage_registry.py` should not need semantic changes:
  its existing dynamic-input, config-validator, input-contract, and
  output-contract interfaces are sufficient. Likewise, no
  `workflow_states.py` change is needed; M14 result states are artifact fields,
  while workflow lifecycle remains the M1 state set.
- No changes are expected in M4 producers, M7 recurrence, M5/M6 adapters, or
  M8–M10 modules. M14 links their typed outputs only and never reruns or
  relabels them ([readiness](M14_PRECONTRACT_READINESS.md), lines 139–147).

## 3. Stage, artifact, and input registration

Register stage kind `m14_descriptive_observations`, using the existing
`python -m satellite_discovery.artifact_workflow --manifest <workflow.json>
--output <directory>` runner. No M14-specific CLI, unrestricted file reader,
or dynamic module loader is allowed ([contract freeze](../M14_CONTRACT_FREEZE.md),
lines 28–40).

The output map should register exactly:

| Output artifact | Contract role |
| --- | --- |
| `m14_observation_table` | normalized observation rows and exact source-row references |
| `m14_descriptive_summary` | counts, strata, states, and denominators only |
| `m14_result_bundle` | input, output, provenance, semantic, and integrity binding |

The input manifest remains embedded configuration, not a new M14 input artifact.
It contains `dataset_id`, `source_artifacts`, `sampling_units`,
`evaluated_pairs`, `observations`, and a null `analysis_profile`
([contract freeze](../M14_CONTRACT_FREEZE.md), lines 55–78).

The dynamic source-artifact allowlist must enforce the exact producer/type pairs:

- M4 `catalogue_observations`: `sample_table`, `observation_table`,
  `occurrence_table`, `occurrence_summary`;
- M4 `observations`: `occurrence_table`, `occurrence_summary`;
- M7 `independent_recurrence`: `m7_observation_table`,
  `m7_exact_recurrence_table`, `m7_independence_summary`,
  `m7_validation_report`, `m7_provenance_manifest`.

Unrecognized producer/type pairs, arbitrary reports, M5/M8/M9 results, raw
reads, and sequence databases must fail validation ([contract freeze](../M14_CONTRACT_FREEZE.md),
lines 42–53, 193–213).

## 4. Validation and counting plan

Implement validation in this order:

1. Validate exact top-level fields, `m14-input-v1`, bounded UTF-8 JSON, stable
   `dataset_id`, required arrays, null `analysis_profile`, and immutable source
   references.
2. Validate unique opaque `unit_id` values, allowed `unit_type`, required
   `OTHER_DECLARED` label, sorted parent IDs, explicit independence state, and
   integrity-bound `independence_ref` only for
   `VERIFIED_WITH_PROVENANCE`. Preserve null study IDs and source-declared
   control roles; do not normalize control adequacy.
3. Validate each pair's candidate/helper IDs and complete sorted unit frame.
   Every pair/unit must have exactly one observation. Missing rows are
   invalid/incomplete, never implicit negatives.
4. Validate observation IDs, foreign keys, state reasons, tested flags, method
   references, detection limits, and provenance. Enforce:
   `PRESENT` and `NOT_DETECTED_WITHIN_SCOPE` require tested=true and a method;
   scoped non-detection additionally requires detection scope;
   `UNAVAILABLE`/`NOT_APPLICABLE` require tested=false and a reason;
   `UNKNOWN` may be tested or untested; `CONFLICTING` requires distinct
   incompatible provenance and is excluded from the 2×2 cells
   ([contract freeze](../M14_CONTRACT_FREEZE.md), lines 80–140).
5. Normalize only for deterministic ordering. Count `n_rows`,
   `n_unique_units`, tested counts, jointly tested rows, unknown/unavailable,
   not-applicable, conflicting, and excluded rows. The four cells include
   only jointly tested rows whose two states are present or valid scoped
   non-detection. The denominator is exactly the declared pair/unit frame
   ([contract freeze](../M14_CONTRACT_FREEZE.md), lines 142–181).
6. Return `NOT_EVALUATED` for a valid empty frame; return
   `INSUFFICIENT_MATCHED_EVIDENCE` where the schema-valid frame has no eligible
   units; never manufacture an association estimate or negative result.

## 5. Upstream reuse, provenance, and cache identity

Reuse the shared artifact primitives for regular-file, path, digest, contract,
and producer-manifest checks. Preserve producer stage/run manifest digest,
artifact type/version, relative path, content digest, and raw status in every
source reference. M7 links must retain declared metadata and limitations
without upgrading `UNVERIFIED` independence ([contract freeze](../M14_CONTRACT_FREEZE.md),
lines 71–73, 122–125, 251–257).

The result bundle and stage identity must bind:

- manifest and dataset identifiers;
- every consumed source artifact's producer stage/run/type/version/status and
  content digest;
- normalized observation-row digests;
- all unit, parent, study, independence, control-role, method, detection-limit,
  and state fields affecting grouping or validity;
- denominator and counting rules;
- M14 schema/semantic version, consumed artifact-contract semantic identities,
  implementation/source digest, and output hashes.

Exclude generated timestamps and absolute paths. A change to unit relationships,
states, denominator membership, source bytes, or contract semantics invalidates
M14 only and must not rewrite M7. Reuse requires matching identity plus output
hash verification ([contract freeze](../M14_CONTRACT_FREEZE.md), lines 221–234).

## 6. Tests and synthetic fixtures

Add focused modules:

- `tests/test_m14_descriptive_observations.py`: validation, normalization,
  counting, state handling, canonical bytes, failures, and cache behavior.
- `tests/test_m14_contracts.py`: output validators and exact accepted
  producer/type pairs.
- `tests/test_m14_workflow.py`: registry, typed direct inputs and handoffs,
  preflight, completed-stage provenance, output manifests, reuse, and tamper
  rejection.
- Extend `tests/test_artifact_validation.py` for M14 output contracts and
  `tests/test_stage_cache_identity.py` for M14-only invalidation. Preserve the
  existing M7 workflow/cache patterns in
  `tests/test_independent_recurrence.py`, lines 410–515, and the M10
  first-run/reuse/tamper pattern in `tests/test_m10_workflow.py`, lines
  106–181.

Required synthetic fixture names and assertions:

| Fixture | Required assertion |
| --- | --- |
| `four_valid_unit_combinations` | Four unique units cover all 2×2 cells; jointly tested denominator is exactly 4. |
| `scoped_not_detected_without_test_method_or_scope` | Reject; it never enters a negative cell. |
| `multiple_runs_and_libraries_one_declared_unit` | Parent relationships remain visible; runs/libraries are not silently independent units. |
| `missing_vs_unknown_vs_unavailable_vs_not_applicable` | Separate explicit counts; none becomes scoped non-detection. |
| `conflicting_pair_unit_sources` | Preserve distinct provenance and exclude the row from all four cells. |
| `m7_unverified_recurrence_link` | Preserve M7 metadata; emit no verified-independence conclusion. |
| `empty_observation_frame` | Valid `NOT_EVALUATED`, denominator zero, no negative association. |
| `nonnull_analysis_profile` | Reject; never select a default model. |
| `unsupported_source_artifact` | Reject producer/type mismatch before execution. |
| `duplicate_ids_and_pair_units` | Reject duplicate observation IDs and duplicate pair/unit rows. |
| `invalid_verified_independence_ref` | Reject missing or corrupt verification evidence. |
| `permuted_input_order` | Produce byte-identical canonical outputs and hashes. |

Also test incomplete pair frames, missing state reasons, malformed methods or
detection limits, bad artifact references/digests, corrupt outputs, changed
source bytes, runtime failure, interruption, and unavailable optional M4/M7
sources. Invalid required input fails before execution; safe invalid optional
rows retain explicit reasons; absence never becomes zero
([contract freeze](../M14_CONTRACT_FREEZE.md), lines 193–219).

## 7. Determinism, isolation, and regression surfaces

Run the same manifest twice and compare every output byte, row order, summary
stratum order, result-bundle digest, and output manifest. Reorder input arrays
and verify identical output. Change one source byte, unit relationship, state,
denominator, method scope, or contract version and verify an M14 cache miss
while M7 outputs remain unchanged.

The regression gate must preserve:

- M1 workflow lifecycle, typed handoffs, output manifests, verified reuse,
  containment, and cache identity;
- M4 sample/observation/occurrence validation and report behavior;
- M5/M6 evidence boundaries and all existing artifact contracts;
- M7 exact recurrence, declared metadata, unverified independence, and
  same-source limitations;
- M8/M9 scoped computational evidence and M10 exact-first evidence.

M14 must not read raw reads, invoke upstream stages, infer omitted rows, or
alter any M1–M10 contract. Run the complete existing unittest suite in
addition to the focused M14 tests.

## 8. Package, CLI, and CI implications

The implementation should remain standard-library-only and require no public
dataset, sequence database, statistical package, external executable, network
access, or new package entry point. The existing artifact-workflow CLI is the
only invocation. Add synthetic tests to ordinary unittest discovery and the
existing Python 3.11/3.12, Linux/Windows required matrix; do not add optional
tool or real-data jobs ([readiness](M14_PRECONTRACT_READINESS.md), lines 26–31,
119–137; [validation logistics](M12_M16_VALIDATION_LOGISTICS.md), lines
278–294).

## 9. Suggested implementation order

1. Implement the pure manifest/state/unit/pair validator and canonical
   descriptive counting core with synthetic tests.
2. Add M14-local serialization and result-bundle/cache identity tests.
3. Add artifact-contract entries and validators without changing shared
   validator semantics.
4. Add the `m14_descriptive_observations` registry entry and typed workflow
   handoff.
5. Add workflow preflight, completed-stage, reuse, tamper, failure, and
   interruption tests.
6. Run M14 tests plus the complete M1–M11 regression suite and required
   offline CI matrix.
7. Keep any future inference or experiment work in a separately approved
   contract and implementation; it is not a follow-on hidden mode of this
   stage.

M12–M16 fixture reuse and semantic separation are tracked in the
[cross-milestone fixture matrix](M12_M16_FIXTURE_MATRIX.md), and branch/merge
ordering is tracked in the [parallelization plan](M12_M16_PARALLELIZATION_PLAN.md).

## 10. Descriptive core versus deferred branches

**Descriptive core:** typed caller-authored observations; declared unit and
pair frames; explicit tested denominators; present/scoped-not-detected,
unknown, unavailable, not-applicable, and conflicting states; provenance;
deterministic summaries; lifecycle/failure handling; and scoped language such
as “co-detected in X/Y evaluable units.”

**Optional/deferred:** statistical association models, abundance
normalization, uncertainty, sparse-data policy beyond the frozen descriptive
rules, control matching/adequacy, public or private cohort selection, sequence
interpretation, taxonomic labels, and perturbation/rescue experiments. These
require separately justified units, matched data, controls, model/profile,
permissions, or claim-appropriate experiments. M14 must not silently select a
default model or emit `DEPENDENCE_DEMONSTRATED`
([design research](M14_HELPER_ASSOCIATION_DESIGN_RESEARCH.md), lines 34–59,
69–101, 117–131).

M14 implementation execution plan: READY FOR REVIEW
