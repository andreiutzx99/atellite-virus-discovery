# M15 implementation execution plan

**Status:** implementation planning only. M15 remains planned and this document
does not implement or alter the frozen contract.

This plan covers the descriptive, lossless dossier baseline. It does not add
ranking, scoring, classification, M11 support, biological interpretation, or
restricted-data export. The contract explicitly preserves producer records and
does not convert correlated evidence into independent votes
([M15 contract](../M15_CONTRACT_FREEZE.md), lines 1–18).

## 1. Implementation boundary and runner

Implement M15 as the allowlisted `m15_evidence_dossier` stage in the existing
artifact-workflow runner. Do not add a dedicated command, arbitrary importer,
per-milestone executable, or dynamic module loader
([M15 contract](../M15_CONTRACT_FREEZE.md), lines 20–25).

The implementation should continue to use:

```text
python -m satellite_discovery.artifact_workflow \
  --manifest <workflow.json> --output <output-directory>
```

The stage receives an `m15-input-v1` manifest with an opaque `candidate_id`,
zero or more immutable `artifact_refs`, and exactly the M12/M13/M14 optional
stage-state fields. Zero references are valid and produce `NOT_EVALUATED`;
`PRESENT` requires a matching valid reference, while failed or incomplete
optional branches may coexist with valid partial references
([M15 contract](../M15_CONTRACT_FREEZE.md), lines 56–82).

M15 is downstream-only. It must never rerun, remap, reparse, normalize, or
rewrite an upstream producer. A malformed required M15 manifest fails
preflight; a valid partial set remains usable and records the failed or
unavailable branch explicitly ([M15 contract](../M15_CONTRACT_FREEZE.md),
lines 139–158).

## 2. New modules and additive integration points

### New production modules

1. **`satellite_discovery/m15_contracts.py`**
   - Validate `m15-input-v1`, immutable `ArtifactRef` objects, exact
     producer/type pairs, optional-stage states, semantic-axis objects,
     dependency edges, duplicate references, and integrity failures.
   - Validate each M15 output contract without changing upstream validators.
   - Provide M15-local canonical JSON and stable identity helpers if the
     existing generic writer cannot guarantee the M15 byte rules.
   - Preserve unknown producer statuses and schemas rather than coercing them
     to a known state.

2. **`satellite_discovery/m15_stage.py`**
   - Implement the trusted stage handler, input resolution, producer
     validation, lossless envelope construction, dependency-edge construction,
     summary generation, result-bundle generation, and output-manifest
     writing.
   - Expose a stage version, configuration validator, and scoped
     `cache_implementation_identity` compatible with the existing workflow
     cache path.
   - Keep raw producer payloads external and retrievable by immutable reference;
     do not copy or rewrite them as normalized evidence.

These module boundaries follow the existing M10 stage pattern for stage-local
versioning, canonical serialization, implementation identity, output
contracts, and cache hooks ([M10 stage](../../satellite_discovery/m10_stage.py),
lines 15–34, 84–92, 212–231, 242–243, 501–504).

### Additive shared-file changes

- **`satellite_discovery/artifact_contracts.py`**
  - Add the four M15 output names and descriptions:
    `m15_evidence_envelope`, `m15_dependency_edges`,
    `m15_dossier_summary`, and `m15_result_bundle`.
  - Add per-contract semantic versions and dispatch to M15 validators.
  - Reuse `validate_artifact`, `describe_artifact`, `verify_descriptor`,
    `known_contract`, `checksum`, and `semantic_identity`.
  - Do not increment the shared `VALIDATOR_SEMANTIC_VERSION` for an M15-only
    addition. The existing identity policy says adding an unrelated contract
    must not alter existing stage identities
    ([artifact contracts](../../satellite_discovery/artifact_contracts.py),
    lines 19–21, 99–134).

- **`satellite_discovery/artifact_workflow.py`**
  - Import the new M15 stage module.
  - Register `m15_evidence_dossier` with dynamic typed inputs, its configuration
    validator, accepted input contract map, and four output contracts.
  - Add M15 output types to the consolidated report allowlist only if the
    report stage is intentionally extended; the dossier itself remains the
    authoritative lossless output.
  - Reuse existing typed handoff resolution, completed-stage checks, path
    containment, output inventory, and output-contract verification.

- **`satellite_discovery/stage_registry.py`**
  - No semantic change is expected. Its existing dynamic-input registration,
    input/output contract maps, versioning, and handler validation are
    sufficient.

- **`satellite_discovery/workflow_states.py`**
  - No change. M15 dossier completeness is an artifact-level value
    (`COMPLETE_WITHIN_SUPPLIED_SCOPE`, `PARTIAL`, `NOT_EVALUATED`, or
    `INVALID`); workflow lifecycle remains the existing M1 state set
    ([M15 contract](../M15_CONTRACT_FREEZE.md), lines 139–158).

## 3. Accepted inputs and output artifacts

### Accepted producer/type pairs

The input validator must enforce the complete allowlist rather than accepting
arbitrary report text:

| Producer | Accepted artifact types |
| --- | --- |
| M5 ViReMa | `dvg_raw_output`, `dvg_evidence`, `dvg_evidence_summary`, `dvg_parameters` |
| M6 residual/support | `residual_read_manifest`, `read_triage_table`, `read_alignment_sam`, `read_support_evidence`, `read_support_table`, `reconstruction_evidence`, `m8_candidate_sequence_set` |
| M7 recurrence | `m7_observation_table`, `m7_exact_recurrence_table`, `m7_independence_summary`, `m7_validation_report`, `m7_provenance_manifest` |
| M8 homology | `m8_raw_blast_output`, `m8_query_status`, `m8_match_evidence`, `m8_summary`, `m8_search_commands`, and the snapshot manifest `m8_reference_snapshot_manifest` |
| M9 ORF/protein | `m9_orf_results`, `m9_protein_fasta`, `m9_orf_bundle`, `m9_protein_search_status`, `m9_protein_match_evidence`, `m9_protein_summary`, `m9_search_commands`, `m9_output_bundle`, `m9_raw_blast_output`, and the snapshot manifest `m9_protein_reference_manifest` |
| M10 exact-first | `m10_candidate_accounting`, `m10_repeat_evidence`, `m10_result_bundle` |
| M12 artifact review | `m12_artifact_review_table`, `m12_summary`, `m12_result_bundle` |
| M13 M5 dossier | `m13_event_index`, `m13_hypothesis_matrix`, `m13_summary`, `m13_result_bundle` |
| M14 observations | `m14_observation_table`, `m14_descriptive_summary`, `m14_result_bundle` |

The exact producer stage, producer-run manifest digest, artifact type and
semantic version, relative path, SHA-256, and raw producer status are mandatory
on every reference. M1–M4 manifests may be linked for provenance but are not
interpreted as evidence rows. M11 is deliberately excluded by the frozen M15
contract; inclusion requires a separately reviewed M15 contract version
([M15 contract](../M15_CONTRACT_FREEZE.md), lines 27–54).

### Output contracts

The stage should emit these four typed outputs:

1. **`m15_evidence_envelope`** — one record per accepted artifact or source row,
   retaining `evidence_id`, candidate ID, producer reference, exact raw status
   and schema, optional source-row reference, all semantic axes, and dependency
   edge IDs.
2. **`m15_dependency_edges`** — explicit, source-supported relationships such
   as `DERIVED_FROM`, `SAME_INPUT`, `SAME_READ_SOURCE`,
   `SHARED_REFERENCE`, `SAME_DECLARED_UNIT`, `POTENTIAL_OVERLAP`, or
   `UNKNOWN`, with verification state. Edges are not independence assertions.
3. **`m15_dossier_summary`** — supplied, absent, invalid, incomplete,
   unavailable, unresolved, and conflict counts, without a score or class.
4. **`m15_result_bundle`** — exact input, producer, dependency, output-digest,
   implementation, schema, and provenance binding.

The envelope and dependency structures must preserve multiple records sharing a
source. They must not collapse them or count them as independent confirmations
([M15 contract](../M15_CONTRACT_FREEZE.md), lines 84–137).

## 4. Validation and semantic axes

### Upstream validation to reuse

Before constructing an envelope, use the existing typed-artifact path:

1. Resolve direct typed paths or completed-stage handoffs through
   `artifact_workflow`’s input resolver.
2. Verify producer stage identity, producer-run manifest digest, relative
   containment, regular-file status, SHA-256, artifact type, and semantic
   version.
3. Dispatch each payload to `artifact_contracts.validate_artifact`, which in
   turn remains authoritative for M5–M10 payload structure.
4. Preserve the resulting producer schema, raw status, validation metadata,
   provenance, and source references in the M15 record.

Do not duplicate M5 event accounting, M6 residual/read-support validation, M7
recurrence semantics, M8 homology state handling, M9 ORF/protein semantics, or
M10 exact-first rules. The cross-milestone boundary requires linking those
outputs without changing their status or cache identity
([implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md), lines 15–35;
[M15 readiness](M15_PRECONTRACT_READINESS.md), lines 118–129).

M12–M14 validators become required inputs only when those stages exist:

- M12 records remain artifact-bounded and preserve M5/M6 scope, limitations,
  and shared-read caveats.
- M13 records remain M5 caller-scoped and must not be normalized across
  callers.
- M14 records remain descriptive observations with declared units and
  denominators; M7’s declared independence is not upgraded to verified
  independence.

### Lossless semantic axes

Every envelope record contains all six axes. Their values and mapping rules are
fixed by the contract:

- `artifact_validity`: `VALID`, `INVALID`, or `UNKNOWN`; M15 can assert valid
  or invalid only from its own integrity/schema checks.
- `applicability`: `APPLICABLE`, `NOT_APPLICABLE`, or `UNKNOWN`; absence does
  not imply not-applicable.
- `execution`: an existing M1 lifecycle value or `UNKNOWN`; do not infer
  completion from an evidence result code.
- `completeness`: `COMPLETE`, `INCOMPLETE`, `TRUNCATED`, or `UNKNOWN`; copy
  only explicit producer accounting.
- `observation`: `OBSERVED`, `NOT_DETECTED_WITHIN_SCOPE`,
  `NO_OBSERVATION`, or `UNKNOWN`; map only a producer-defined scoped result
  with valid accounting.
- `interpretation`: `SUPPORTS`, `CONFLICTS`, `UNRESOLVED`, or
  `NOT_INTERPRETED`; map only explicit hypothesis-linked interpretation.

Raw status and schema remain authoritative beside these axes. Unknown,
unavailable, failed, incomplete, invalid, truncated, or missing evidence must
never become a completed no-signal ([M15 contract](../M15_CONTRACT_FREEZE.md),
lines 114–128; [M15 readiness](M15_PRECONTRACT_READINESS.md), lines 36–56).

## 5. Serialization, provenance, and cache identity

Use a local M15 canonical serializer unless a shared helper can be proven to
meet every frozen rule:

- UTF-8 JSON, no BOM, LF line endings, exactly one final newline;
- sorted object keys and no non-finite numbers;
- envelope rows ordered by `evidence_id`;
- dependency edges ordered by source ID, relation, then target ID;
- summaries ordered by producer and state;
- source payload bytes unchanged and referenced by digest.

The result bundle/cache identity must include:

- candidate ID and exact `m15-input-v1` manifest digest;
- every producer milestone/stage, producer-run manifest digest, artifact type,
  semantic version, content digest, raw status, and source-row identity;
- optional M12/M13/M14 states;
- source-access/terms references when supplied;
- dependency-edge source and relation;
- M15 axis-mapping semantic version;
- only the consumed artifact-contract semantic identities;
- implementation/source digest and all output digests.

It must exclude timestamps, absolute paths, display formatting, and unreferenced
evidence. A changed producer invalidates M15 through its digest; an M15-only
change must not invalidate upstream stages. Reuse requires exact identity and
verified output hashes ([M15 contract](../M15_CONTRACT_FREEZE.md), lines
160–178).

## 6. Tests and synthetic fixtures

Add focused tests rather than changing existing producer tests:

- `tests/test_m15_contracts.py` — manifest shape, exact producer/type allowlist,
  immutable references, all axis values, unknown mapping, raw status/schema
  round-trip, duplicate references, conflict retention, optional-state
  consistency, and invalid integrity records.
- `tests/test_m15_workflow.py` — stage registration, direct typed inputs,
  upstream stage handoffs, output-contract verification, partial dossier,
  failure/interruption lifecycle, verified reuse, and tamper rejection.
- Extend `tests/test_artifact_validation.py` for the four M15 output contracts.
- Extend `tests/test_stage_cache_identity.py` for M15-only identity changes and
  upstream identity isolation.

The required fixture set is:

1. Mixed synthetic M5–M14 records containing positive/scoped no-signal,
   missing, not-applicable, unavailable, failed, interrupted, incomplete,
   truncated, invalid, conflicting, and unresolved states.
2. Raw producer status/schema and artifact references round-tripped byte-for-
   byte without lossy coercion.
3. M5 completed caller zero, retained as method-scoped observation only.
4. M8 no-hit alongside failed and incomplete branches, with no failure-to-
   no-hit conversion.
5. Missing M12/M13/M14 branches explicitly marked `NOT_SUPPLIED`.
6. M6 assembly and read-back from the same eligible reads, producing a
   `SAME_READ_SOURCE` edge but no independent-vote count.
7. Two records sharing a reference or source event, both retained with one
   supported dependency edge and no deduplication.
8. Unknown producer status, with raw value retained and affected axes
   `UNKNOWN`/`NOT_INTERPRETED`.
9. Corrupt artifact, duplicate reference, mismatched digest, wrong producer
   type, unsafe path, and invalid schema; valid records survive in a `PARTIAL`
   dossier while invalid payloads are not ingested.
10. Empty artifact list producing `NOT_EVALUATED` and no synthetic evidence.
11. Malformed required manifest, runtime failure, and interruption. Verify
    failed/interrupted lifecycle reporting and that partial output is never
    mistaken for a completed dossier.

These fixtures are directly derived from the frozen acceptance table
([M15 contract](../M15_CONTRACT_FREEZE.md), lines 180–192) and readiness
requirements ([M15 readiness](M15_PRECONTRACT_READINESS.md), lines 78–95).
The cross-milestone reusable fixture mapping is maintained in the planned
[fixture matrix](M12_M16_FIXTURE_MATRIX.md).

### Determinism and cache-isolation tests

- Permute input reference order and verify byte-identical semantic outputs.
- Verify stable evidence IDs, edge ordering, summary ordering, final newline,
  and output hashes across repeated runs.
- Mutate one producer digest/status/schema, optional-stage state, dependency
  relation, axis-mapping version, or M15 implementation and assert only the
  M15 cache key changes.
- Add an unrelated contract to `artifact_contracts._CONTRACTS` and assert
  existing M1–M10 identities remain unchanged.
- Tamper with an output or producer after the first run and verify reuse
  rejects it rather than rewriting upstream outputs.
- Run the same synthetic workflow twice and assert `verified_reuse`, following
  the established M10 workflow pattern
  ([M10 workflow tests](../../tests/test_m10_workflow.py), lines 106–181;
  [cache tests](../../tests/test_stage_cache_identity.py), lines 46–93,
  120–212, 252–257).

## 7. M1–M11 regression surfaces

The full existing suite must remain green. Specifically:

- **M1/M4:** registry validation, typed handoffs, lifecycle transitions,
  manifests, path containment, output inventory, verified reuse, and
  deterministic workflow identity.
- **M2/M3:** immutable reference and assembly links remain provenance only;
  M15 must not acquire reads, references, assemble, or remap.
- **M5:** caller-specific event rows, raw status, accounting, and completed
  zero remain unchanged and scoped to the producing caller/run.
- **M6:** residual/read-support/reconstruction accounting and the
  same-eligible-read relationship remain unchanged; M15 must not recount
  read-back as independent evidence.
- **M7:** exact recurrence and declared metadata remain separate from verified
  independence.
- **M8:** role-scoped match, no-hit, incomplete, unavailable, and failure
  states remain scoped to their supplied snapshot and method.
- **M9:** ORF/protein results remain computational evidence only.
- **M10:** exact-first architecture evidence remains exact-pattern evidence and
  is not promoted to topology, function, or classification.
- **M11:** optional RNA-fold prediction is not an M15 input and remains
  unchanged.

Adding M15 contracts or registration must not change existing M1–M11
contract-semantic identities or cache keys. The implementation sequence
requires no upstream scientific-behavior or interface change
([implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md), lines 9–35,
88–91).

## 8. CLI, package, CI, and implementation order

No new runtime dependency, package entry point, public CLI, database, external
tool, or biological payload is required. New modules are included by the
existing package discovery. Required CI should run synthetic, offline
`unittest` discovery on the existing Python/platform matrix. Do not provision
private reads, biological databases, unresolved callers, or benchmark payloads
in required CI ([implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md),
lines 93–105; [validation logistics](M12_M16_VALIDATION_LOGISTICS.md), lines
278–294).

Recommended order:

1. Implement and test M15 schema/normalization helpers in isolation, including
   canonical serialization and exact axis mapping.
2. Add M15 contract validators and synthetic contract tests.
3. Add stage-local dossier assembly, provenance, result bundle, and scoped
   cache identity.
4. Add the additive artifact-contract entries and one workflow registry entry.
5. Add direct-input, typed-handoff, partial-input, reuse, tamper, and lifecycle
   workflow tests.
6. Run the full M1–M11 regression suite and installed-package/offline smoke
   checks.
7. Integrate M12–M14 outputs only after their artifact contracts and identities
   are independently frozen; then exercise mixed M5–M14 fixtures.

M15 schema mechanics can proceed in parallel with M12–M14, but complete
integration fixtures must wait for those upstream output schemas. The detailed
branch and gate sequence is in the planned
[parallelization plan](M12_M16_PARALLELIZATION_PLAN.md), and the dependency
graph is explicit in the [implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md),
lines 37–69 and 107–118.

## 9. Stale decision-register row and claim boundary

Row 47 of `docs/research/M12_M16_DECISION_REGISTER.md` is stale. It still says
that canonical cross-stage state axes and evidence-link/interface semantics
**BLOCK CONTRACT FREEZE** and **BLOCK CORE IMPLEMENTATION**. The M15 readiness
review resolved that software choice: retain exact producer status/schema and
add lossless orthogonal semantic axes, without an enum migration or biological
interpretation rule ([M15 readiness](M15_PRECONTRACT_READINESS.md), lines
97–116). The implementation sequence then explicitly instructed freezing the
lossless envelope and semantic axes ([implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md),
lines 73–91), and the frozen contract now defines the axes, dependency
relations, partial-input behavior, serialization, and identity
([M15 contract](../M15_CONTRACT_FREEZE.md), lines 114–178).

The document to reconcile later is exactly
`docs/research/M12_M16_DECISION_REGISTER.md`. This plan does not edit that
register or the contract. The remaining M15 decisions are optional ranking
objective/calibration and restricted export; neither blocks the descriptive
dossier. Ranking, M11, classification, biological winners, independent-vote
counts, source attribution, function, and dependence claims are outside this
implementation plan ([M15 readiness](M15_PRECONTRACT_READINESS.md), lines
58–61, 105–116).

M15 implementation execution plan: READY FOR SYNTHETIC/OFFLINE PREPARATION
