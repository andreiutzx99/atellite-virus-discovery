# M12–M16 synthetic fixture matrix

**Status:** implementation-planning artifact only. This document defines
reusable *technical* fixture construction, not shared biological meaning,
empirical labels, benchmark holdouts, or a new contract. M12–M16 remain
planned and the matrix must be used with the five frozen implementation plans:
[M12](M12_IMPLEMENTATION_EXECUTION_PLAN.md),
[M13](M13_IMPLEMENTATION_EXECUTION_PLAN.md),
[M14](M14_IMPLEMENTATION_EXECUTION_PLAN.md),
[M15](M15_IMPLEMENTATION_EXECUTION_PLAN.md), and
[M16](M16_IMPLEMENTATION_EXECUTION_PLAN.md).

The contracts require generated, deterministic, offline fixtures and preserve
producer-scoped states rather than converting missingness into a negative
[implementation sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md#phase-b--implement-independent-synthetic-baselines-in-parallel)
(lines 93–105). A shared generator may provide hashes, paths, manifests,
ArtifactRefs, canonical JSON, and lifecycle scaffolding, but each milestone
must validate and interpret the fixture only under its own contract.

## Reuse rules

1. Every fixture instance has a stable fixture-family ID, generator version,
   source/provenance declaration, and content digest. The generator is
   technical provenance, not biological truth.
2. A derived fixture records the exact milestone schema and semantic version.
   Reusing bytes is safe; reusing a result, state mapping, denominator, or
   claim is not.
3. Synthetic records may use opaque IDs such as `sample-a` or `group-1`.
   They must not be described as real samples, controls, positives, negatives,
   independent replicates, or biological labels.
4. Mutations are deliberate and named: digest mutation, path mutation,
   status mutation, missing field, truncation, duplicate, split leakage, or
   post-commit tamper. A mutation must not silently become a different
   milestone’s semantic case.
5. The same fixture can gate several implementations only when each gate
   checks its own expected state. For example, M5 completed-zero is a
   caller-scoped observation for M12/M13/M15 and is never an M14 or M16
   negative label.

## Matrix

| Fixture family | Exact per-milestone use | Safe shared generator / provenance | Semantics that must not be conflated | Expected gate |
| --- | --- | --- | --- | --- |
| **Canonical artifact envelope**: UTF-8 JSON, relative path, SHA-256, producer stage/run manifest, artifact type/version, raw status | M12 verifies retained M5/M6 refs; M13 verifies M5 run refs; M14 validates optional M4/M7 source refs; M15 preserves all accepted producer refs; M16 validates M12–M15 target refs | One hash/path/ArtifactRef builder with immutable fixture root, schema-specific wrapper, and recorded generator version. Reuse `describe_artifact`/`verify_descriptor` behavior; see M1–M11 boundary in [sequence](M12_M16_IMPLEMENTATION_SEQUENCE.md#1-current-m1m11-boundary) (lines 15–35) | A valid file is not a valid biological observation. Producer status is not an output interpretation; M16 target validity is not a label. | All contract validators; path containment, digest, producer/type pairing, deterministic serialization, and cache identity tests |
| **M5 completed event**: validated `dvg_parameters`, summary, evidence with one native event | M12 one verified M5 row; M13 copies the event and native order; M15 one raw-preserved envelope; M16 only through a frozen downstream bundle target | Build from the M5 contract fixture shape and preserve source row, caller, reference, run digest, and event bytes; do not invoke ViReMa | A caller event is not cross-caller agreement, DVG taxonomy, helper dependence, or a biological winner. M12 does not rerun M5 | M12/M13 import and provenance gates; M15 raw round-trip; M16 accepted target-ref mechanics only |
| **M5 completed-zero**: valid empty evidence plus exact `NO_DVG_EVIDENCE_DETECTED` accounting | M12 retains raw status and caller/input scope; M13 emits `IMPORTED_COMPLETED_ZERO`; M15 maps only explicitly supported axes; M14 must not consume it; M16 must not make it a label | Reuse one valid M5 producer fixture, changing only event count and exact producer accounting. Record producer contract version and scope | “No event from this caller/run” is not DVG-negative, satellite-negative, source-negative, or an M16 negative label; see M13 contract (lines 113–119) | M12/M13 zero-preservation and M15 no-negative-axis tests; explicit rejection of broadened interpretation |
| **M6 same-read-source**: residual/read-back/reconstruction records share assembly-eligible-read provenance | M12 links the shared eligible-read dependency and does not count independent confirmation; M15 emits `SAME_READ_SOURCE`; M13/M14 do not reinterpret it; M16 may only receive it through an upstream bundle | Generate one immutable eligible-read/source digest and multiple typed M6 refs with declared dependency metadata; reuse M6 provenance, not read payloads | Read-back and reconstruction from shared reads are not independent biological replicates or independent votes; M14 declared units are not upgraded | M12 dependency and M15 edge tests; regression that no independent count or denominator is added |
| **Absent / not supplied / unavailable / not applicable / unknown**: explicit state with optional note | M12 four external-evidence entries; M13 per-artifact states; M14 observation states and optional source absence; M15 optional M12–M14 states and semantic axes; M16 unknown/not-applicable label and execution states | Shared enum/state fixture builder, but each schema supplies its own exact enum and required reason fields | `NOT_SUPPLIED` ≠ `UNAVAILABLE` ≠ `NOT_APPLICABLE` ≠ `UNKNOWN`; none is a completed no-signal or biological negative. M16 unknown label is not an unknown prediction outcome | State preservation, denominator exclusion, explicit summary counts, and no synthetic negative rows |
| **Failure / interruption / incomplete / truncated**: raw producer or execution status plus partial artifacts where allowed | M12 preserves invalid/incomplete producer accounting and maps process failure/interruption to existing M1 lifecycle; M13 retains run import state; M14 reports incomplete/failed/interrupted; M15 preserves partial valid records; M16 retains item execution states and blocks scoring when integrity fails | Generate status mutations against an otherwise valid fixture, plus atomic-output/interruption harness. Keep raw status and mutation reason in provenance | Failure is not zero events; incomplete is not complete; M16 `INTEGRITY_FAILED` is custody/result behavior, not a global new lifecycle enum | Fail-closed validation, valid-row retention for partial inputs, no metrics after M16 integrity failure, interruption/reuse tests |
| **Bad ArtifactRef**: wrong producer/type, digest, version, path escape, symlink, duplicate, malformed ref | M12 rejects M7–M10/arbitrary inputs and malformed refs; M13 rejects invalid M5 run linkage; M14 rejects unsupported sources; M15 records invalid ref without ingesting payload; M16 rejects wrong upstream bundle target | One mutation library operates on immutable valid refs; each mutation gets a distinct name and digest | “Invalid reference” is not “unavailable evidence”; a rejected ref cannot be interpreted as a source observation or a missing biological result | Preflight rejection, integrity-error records where contract permits, no payload reads, cache mutation tests |
| **Deterministic/cache mutation**: permutation, canonical-byte change, source digest change, config/schema change, output tamper | M12–M16 each proves byte-stable output, scoped cache invalidation, verified reuse, and tamper rejection | Shared canonical serializer test helper and cache-key mutation table; use existing stage-cache patterns in `tests/test_stage_cache_identity.py` (lines 46–93, 120–212, 252–257) | Changing an upstream digest invalidates downstream identity; it must not rewrite producer history. An unrelated contract must not invalidate existing stages | Repeat-run/reuse, exact-byte, output-hash, stage-local invalidation, and unrelated-contract stability gates |
| **M14 2×2 observation frame**: four unique opaque units covering both-present, candidate-present/helper-not-detected, candidate-not-detected/helper-present, both-not-detected | M14 alone computes exact four cells and jointly tested denominator 4; M15 may preserve the M14 result; M16 may target the resulting bundle only | Generate `sampling_units`, one complete `evaluated_pairs` frame, methods/detection scopes, and exactly one row per pair/unit as specified by [M14](../M14_CONTRACT_FREEZE.md#4-outputs-and-exact-counting-rules) (lines 150–180) | Scoped `NOT_DETECTED_WITHIN_SCOPE` requires tested method/scope; it is not a universal negative. M14 descriptive cells are not an association estimate or M16 performance metric | Exact hand-count, denominator, permutation, and M15 preservation gates |
| **M14 missingness/conflict frame**: missing row, UNKNOWN, UNAVAILABLE, NOT_APPLICABLE, CONFLICTING | M14 separates counts and excludes non-evaluable/conflicting rows; M15 preserves the result and provenance; other milestones do not convert these into event or label states | Reuse opaque unit IDs and source refs, but construct state-specific observation rows under M14’s required reasons and tested flags | Missing row ≠ `NOT_DETECTED`; `CONFLICTING` is not resolved by row order; M7 `UNVERIFIED` independence is not verified by M14 | M14 validation/denominator gate; M15 raw-state and dependency preservation |
| **M15 shared dependency / unknown axes**: two records share source/reference/read dependency; producer status cannot map losslessly | M15 emits both records, supported dependency edge, raw status/schema, and explicit `UNKNOWN`/`NOT_INTERPRETED` axes; M16 may consume only the resulting bundle | Build producer refs and edge provenance from the same immutable source digest; axis fixture lists explicit mapping versus unmappable status | Shared evidence is not an independent vote; unknown is not absent, failure, no-hit, or negative; M15 does not rank | Lossless envelope, edge, axis round-trip, partial dossier, and no-vote-inflation gates |
| **M16 public-vs-sealed key**: public synthetic manifest and separately hashed sealed software-expectation key | M16 target sees public manifest only; scorer sees key after prediction commit; upstream milestones do not read or interpret key outcomes | Shared synthetic fixture generator emits public/key pair with matching fixture-set ID, separate digests, and `SOFTWARE_CONTRACT` scope | Sealed software expectation is not empirical truth, positive/negative biology, or a public input; key access before commit is integrity failure | Blinding, commitment, key coverage, target identity, and no-metrics-on-integrity-failure gates |
| **M16 group leakage**: shared group across split roles, duplicate/near-duplicate synthetic IDs | M16 rejects leakage and blocks scoring; M15 may preserve group/provenance only if present in an upstream record; no M12–M14 denominator change | Generate sorted opaque group IDs and split roles with a graph fixture; provenance says generated duplicate/family mechanics only | A synthetic group is not an empirical family/study/sample relationship; leakage rejection is not biological dissimilarity | Group consistency, transitive overlap, duplicate ID, deterministic leakage-report gates |
| **M16 custody and zero denominator**: custody transition sequence plus zero labelled/emitted cases | M16 enforces `SEALED → PREDICTIONS_COMMITTED → BLINDED_CHECKED → SCORED`, terminal integrity failure, and null rates for zero denominators; no upstream interpretation | Generate append-only sequence-numbered custody events and hand-calculated item/label axes; no timestamps required for deterministic output | Custody state is not M1 lifecycle; null rate is not zero performance; synthetic agreement is not biological accuracy | State-machine, exact accounting, null-rate, post-commit tamper, and no-score gates |

## Shared fixture gate policy

- Fixture files belong in temporary test roots or a clearly named synthetic
  fixture directory; do not add biological payloads. Existing tests use
  `unittest`, temporary directories, and generated deterministic files
  ([M10 workflow pattern](../../tests/test_m10_workflow.py), lines 106–181;
  [fixture README](../../tests/fixtures/artifact_workflow/README.md), lines 1–17).
- Each milestone must run its own contract validator before consuming a shared
  fixture. A fixture that fails one contract is not silently downgraded to an
  absent fixture.
- Required CI remains the existing offline matrix: Ubuntu and Windows with
  Python 3.11 and 3.12, package install, installed-package smoke checks, and
  `unittest` discovery ([tests workflow](../../.github/workflows/tests.yml),
  lines 4–20). No external caller, database, private read, benchmark truth
  payload, or optional biological resource is required
  ([validation logistics](M12_M16_VALIDATION_LOGISTICS.md), lines 278–294).
- M12 fixtures should exercise the resolved semantic-axis mappings described
  in the [independent audit](M12_M16_INDEPENDENT_CONTRACT_AUDIT.md#resolved-after-this-audit--m12-semantic-axis-detail)
  (lines 44–64), alongside artifact integrity and accounting.
