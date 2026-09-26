# Pre-M9 Stage and Cache Identity Audit

## Scope

This change isolates reusable identities for M6 residual evidence, M7 independent
recurrence, and M8 homology before any M9 protein-search implementation. It does
not change M6–M8 scientific behavior, M8 BLAST settings, or reference semantics.
M9 protein searching and M10 remain out of scope. README and ROADMAP status were
not changed.

The implementation branch is based on synchronized `origin/main` at
`9c64cbb96d4663d0b388b8ca9e0f97403ddaac67`.

## Identity paths audited

| Layer | Identity inputs | Isolation issue and resolution |
| --- | --- | --- |
| Workflow provenance | `reproducibility.environment()` records package source hashes, revision, interpreter, and platform in the workflow manifest. | This remains broad provenance. Scoped M6–M8 cache keys do not use the package-wide source hash as their implementation identity. |
| Workflow stage cache | `_stage_cache_key()` uses a handler's `cache_implementation_identity()` when available; otherwise it falls back to the package source hash. | Scoped stages now include an explicit cache-key schema, a version for shared runner/reuse semantics, and the metadata for that stage's registration only. The complete registry is not fingerprinted. |
| M6 cache and external-tool manifest | M6 fingerprints its adapter and output-producing helpers; the external-tool identity also used the package revision/hash and the full `artifact_contracts.py` file. | M6 replaces the broad contract-module hash with versions for its declared input/output contracts. Its semantic identity keeps interpreter/platform details but excludes package-wide source/revision/version fields. The external-tool manifest still records the complete environment separately for provenance. |
| M7 cache and direct manifest | M7 fingerprints its stage implementation and shared helpers; its direct implementation identity included the full artifact-contract module. | M7 now records selected contract semantics, uses identity schema v2, and no longer hashes unrelated contract definitions. Its direct manifest rejects an identity from the previous schema rather than treating it as equivalent. |
| M8 cache | M8 fingerprints its own search/reference/contract modules and previously hashed all of `artifact_workflow.py` and `artifact_contracts.py`. | M8 now fingerprints its own implementation and selected contract semantics. The stage cache key includes only M8's registration metadata, so adding another stage does not change M8's identity. |
| M8 inputs and runtime | Input digests and the dependency-inspector result are part of the stage key. | Reference snapshot/payload changes and search-runtime/profile changes continue to invalidate M8. |

## Scoped semantic versions

`artifact_contracts.semantic_identity()` returns the shared validator version,
the artifact schema version, and versions only for the named contracts in use.
The defaults are deterministic and adding a new M9 contract does not affect the
M6/M7/M8 contract identities.

Version-bump rules:

- Increment `VALIDATOR_SEMANTIC_VERSION` when common validation behavior changes.
- Increment the entry in `_CONTRACT_SEMANTIC_VERSIONS` when one existing
  contract's validation semantics change.
- Increment `CONTRACT_VERSION` for a change to the shared artifact schema
  semantics.
- Increment `WORKFLOW_CACHE_SEMANTICS_VERSION` when scoped cache-key derivation,
  stage verification, or reuse behavior changes.
- The stage-specific registration descriptor captures changes to that stage's
  kind, version, input fields, optional fields, dynamic-input flag, module,
  external-tool flag, and input/output contract mappings. Descriptive text and
  unrelated registry entries are intentionally excluded.

These versions are an explicit maintenance contract. Changes to a validator's
code must be paired with the corresponding semantic-version bump; hashing the
entire shared module would reintroduce unrelated-stage invalidation.

## Invalidation and compatibility

| Change | Expected effect |
| --- | --- |
| Add an M9-only source file, stage registration, or new contract type | M6, M7, and M8 scoped identities remain stable. M9's own identity changes when its implementation changes. |
| Change M6-only implementation or one of its declared contracts | M6 invalidates; M7/M8 do not unless they independently declare that dependency. |
| Change M7-only implementation or one of its declared contracts | M7 invalidates; unrelated stages do not. |
| Change M8 implementation, an M8 contract, reference payload, or search dependency/profile | M8 invalidates. |
| Change common artifact validation semantics | Every stage that uses the shared validator version invalidates, including M6/M7/M8. |
| Change scoped workflow cache/reuse semantics | Scoped stage keys invalidate through the workflow semantics version. |

The identity-format update deliberately causes a one-time cache-key change for
scoped stages. It does not rewrite prior artifacts or manifests. Old M7 direct
manifests are rejected when their identity differs; M6's identity schema is
explicitly versioned; and workflow outputs are reused only when the new key and
existing output verification both pass. The previous package hash, revision,
and environment remain available in workflow and M6 external-tool provenance,
but no longer make an otherwise-valid M6 result depend on unrelated source
changes.

## Regression coverage

`tests/test_stage_cache_identity.py` covers:

- **A–C:** An M9-only registry/source change leaves M6, M7, and M8 keys stable;
  M6's direct stage identity also excludes package-wide provenance fields.
- **D:** Stable upstream keys still select their previous output directories.
- **E:** Changing an M8-only contract version invalidates M8.
- **F:** Changing an M8 reference payload digest or search-profile dependency
  invalidates M8.
- **G:** Bumping shared artifact-validator or workflow-cache semantics changes
  M6, M7, and M8 keys.
- **H:** Repeated scoped-key calculations are deterministic.
- **I:** An incompatible prior M7 identity is rejected without rewriting its
  output files. Existing M6/M7/M8 tests continue to cover corrupted artifacts
  and failed reuse.
- **J:** Registering an unrelated contract does not change existing semantic
  identities.

The existing workflow suite is also run to check stage execution and reuse
behavior. No scientific result is used as a substitute for identity or integrity
validation.

Validation completed with `python -m unittest discover -s tests`: 456 tests
discovered, 15 skipped, and the suite passed.