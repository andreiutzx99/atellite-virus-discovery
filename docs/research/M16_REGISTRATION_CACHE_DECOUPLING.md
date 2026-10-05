# M16 registration and cache-identity decoupling

**Status:** The shared cache/source-identity prerequisite is implemented on the
separate `feature/m16-cache-identity-prerequisite` branch. It is not merged.
M16 remains planned and blocked from implementation until this prerequisite
passes review and CI on its infrastructure PR.

This report records the implementation boundary and verification evidence. It
does not change a frozen contract, authorize empirical work, or claim that
synthetic software results establish biological truth.

## 1. Authoritative baseline

The authoritative GitHub `main` baseline is commit
[`06738d8ff91792f7e66acc13603353586e9748a1`](https://github.com/andreiutzx99/atellite-virus-discovery/commit/06738d8ff91792f7e66acc13603353586e9748a1),
tree `6612597eb06fdd7275d37687017a635d4349f840`. The implementation branch is
based directly on that commit and tree; no divergent feature branch is treated
as the source of truth.

The authoritative first-parent history includes:

| Change | Merge commit | Evidence |
| --- | --- | --- |
| M14 offline descriptive baseline | `0255359aac335a1224107d25e3d490212246277e` (PR #45) | [M14 contract](../M14_CONTRACT_FREEZE.md) and M14 source/tests on `main` |
| Shared authenticated producer-execution references | `07274f79668f2f3d974584451a493fff6046071f` (PR #48) | [producer verifier](../../satellite_discovery/producer_provenance.py), called by M15 |
| M15 synthetic evidence dossier | `94e70be946f011786baacd86f3624b69f3d383c0` (PR #46) | [M15 contract](../M15_CONTRACT_FREEZE.md), implementation, and workflow tests |
| M15 implemented / M16 planned status | `06738d8ff91792f7e66acc13603353586e9748a1` (PR #49) | [roadmap](../ROADMAP.md) |

The baseline records M1–M15 as implemented and M16 as planned. It has no M16
stage, M16 artifact contracts, or M16 implementation module. The original
baseline cache keys were independently recomputed from an isolated archive of
that exact `main` tree.

## 2. Source hierarchy

The [M16 contract freeze](../M16_CONTRACT_FREEZE.md) and
[M15 contract freeze](../M15_CONTRACT_FREEZE.md) are the normative interfaces.
They govern exact inputs, output contracts, status/state distinctions,
identity, and scientific-claim limits.

The [M16 implementation plan](M16_IMPLEMENTATION_EXECUTION_PLAN.md), the
[pre-contract readiness report](M16_PRECONTRACT_READINESS.md), and the
[M12–M16 research materials](M12_M16_IMPLEMENTATION_SEQUENCE.md) are planning
and research records. They help explain intended sequencing and test design;
they do not override either freeze, turn a proposal into a requirement, or
authorize M16 or empirical implementation.

This report covers only the shared cache/source-identity prerequisite. The
separate M16 requirement for a real offline synthetic M15 execution that
produces an authenticated `m15_result_bundle`, followed by M16 consuming that
exact bundle, remains a later integration gate. A mocked bundle is not
sufficient.

## 3. Baseline coupling and the handoff

The baseline runner formed cache keys from selected stage registration,
configuration, input descriptors, dependencies, and either a scoped
`cache_implementation_identity` or a package-wide source digest. The latter
inventoried package `.py` and `.json` files. A new M16 module therefore changed
unscoped cache keys even though those stages did not depend on it.

The merged M12, M13, and M15 result bundles also included implementation
identities derived from broad shared-module byte hashes. An M16-only contract
or registry addition consequently changed those identities. M14 already had a
stage-scoped implementation identity, but it did not bind the selected output
contract semantic identity.

M15's actual provenance verifier is
[`producer_provenance.py`](../../satellite_discovery/producer_provenance.py).
The M15 stage imports and calls that verifier, but the previous M15
implementation source list did not include it. Preserving the previous M15
identity across verifier changes could therefore reuse provenance-sensitive
outputs under an identity that omitted a real behavior dependency.

The prerequisite replaces incidental package/shared-file coupling with a
stage-owned identity. M16-only source, contract, or registration additions do
not enter upstream identities unless they change a selected contract or a
shared behavior that those stages actually use.

## 4. Implemented identity composition

`stage_cache_identity.py` composes a deterministic identity from:

1. The selected stage kind, stage version, registration projection, and handler
   descriptor.
2. The handler's transitive first-party import closure, using logical module
   names and normalized source content rather than checkout paths.
3. Adjacent `.py`, `.json`, or `.txt` resources named literally by trusted
   stage code.
4. The selected input/output artifact-contract semantic identity, including the
   shared validator semantic version.
5. Shared workflow cache functions, the workflow cache semantic version, and
   the stage-registry source used by all stages.
6. An explicit identity algorithm version.

CRLF is normalized for canonical new identities. The source line-ending
profile is tracked separately for the finite historical-alias lookup. Immutable
closure values are represented; mutable closure objects are not treated as
implementation identity because they can be runtime state (for example, a
workflow handler's invocation counter). Behaviorally relevant mutable state
must instead be represented by the explicit stage version, registration, or
trusted identity descriptor. The current implementation is
`stage-source-identity-v2`; changing this composition requires an algorithm
version change.

The compatibility resource pins the exact baseline identity for each of the
24 registered stages that previously used the package-wide fallback. Only an
exact stage-kind, identity, and supported LF/CRLF match may map back to the
existing package digest. Unknown identities fail closed. The existing
`m12_legacy_cache_compatibility.txt` is unchanged.

M12 and M13 result-bundle implementation fields preserve their exact accepted
baseline hashes when the complete selected identity matches. M12 continues to
distinguish its LF and CRLF legacy source hashes. M13's existing canonical LF
and CRLF source identity remains the same. Their cache keys are also unchanged
for the authoritative baseline.

M15 intentionally does **not** receive a historical identity alias. Its new
identity includes the producer verifier through the import closure, so M15
cache entries are invalidated once and rebuilt with authenticated producer
verification represented. M14's cache identity now includes selected output
contract semantics; this also causes a one-time cache refresh and ensures a
future relevant contract-version change cannot reuse a stale M14 result.

## 5. Baseline and migration evidence

The following keys were computed with the same default registry, stage ID,
empty configuration/input/dependency descriptors, and the real
`reproducibility.environment()` on an isolated baseline archive and this
implementation branch:

| Stage | `main` key | Branch key | Result |
| --- | --- | --- | --- |
| M12 | `1cd7e6f3358f842f7fb27a077d7b1ae9b2143c723036542a6cf9f3ffcf4ddd33` | same | Preserved |
| M13 | `e8043cda62471e6507a991014ee0a8c99950669b82ffa469effc7ea2e5979b4a` | same | Preserved |
| M14 | `abbabffc5cfa82c36d1b89b0dce7942b3a3f27ffccee68ae24b0b262b8a3aca4` | `3a2d6c23b653f68f70c3cbd9ebef14ceca83107ae11eccbbc6c7047d0296bb39` | One-time refresh for selected output-contract semantics |
| M15 | `abbad132d8db37ceb2407e93c2f0aee357661635d4fe2de9d4a240e16b8d8295` | `06db192ff9636c0e67cd5607a33f61a1cecdffcd5211eefc59a493b6ad2ad7f6` | One-time refresh; producer verifier is now a dependency |
| Unscoped `inventory` | `9e904e65e0cc74aca50166976af41c102d36ffc1351529d0cbde15c0827bd011` | same | Preserved by exact baseline alias |
| Unscoped `alignment` | `731dda994142aa915da3364f1029a1b406d52197fb3fa615931f55bb2b4c6821` | same | Preserved by exact baseline alias |

The same probe confirmed M12's prior implementation source hash
`e1556fe2a3825c57ad36708fba8c0bebdcef2eb20e3745911416f595e511123d` and
M13's `2e77e4caf95d1c03f71fee88bcf54fd5931ca97ff2588674129f69978291b12e`
remain unchanged. M15's source hash changes from
`ea034e12babd134617fc3072e6c9cb7ff1c7fd12fa207846cd6fc2760ba1c9c9` to
`b31a200288f44d48ba15fef6e0df1ee05907881d347989cff0eb952db0adf70e`,
reflecting the added verifier dependency. These are identity/cache transitions
only; the prerequisite does not alter any milestone's scientific behavior or
artifact schema.

## 6. Acceptance coverage

`tests/test_stage_identity_decoupling.py` exercises the following:

| Case | Required result |
| --- | --- |
| Add only a downstream contract, stage registration, and module | All existing 36 stage keys and M12/M13/M15 source identities remain stable |
| Change M12, M13, or M15 implementation source | Only the corresponding selected implementation identity changes |
| Change M15 producer verifier source | M15 identity changes |
| Change a milestone registration/version or selected contract semantic | That stage identity changes |
| Change shared workflow cache semantics or validator semantics | Each dependent scoped and unscoped identity changes |
| Change M14-only implementation source | Unscoped upstream identity remains stable |
| Modify an identity without a matching exact compatibility pin | No historical alias is returned |
| Relocate the package checkout | Canonical identities and keys remain stable |
| Convert source/resources to CRLF | Canonical identity stays stable; only the declared historical line-ending alias varies |
| Add mutable state to a handler closure during execution | Cache identity remains stable across repeated stage runs |

Local verification completed:

- `python -m unittest discover -s tests -q`: 650 passed, 16 skipped.
- Focused stage-identity, cache, M12, M13/M5, M14, and M15 suites passed.
- `compileall` and `python -m satellite_discovery.artifact_workflow --help`
  passed.
- A built wheel included the compatibility resource; cache keys and M12/M13/M15
  implementation identities from the source checkout matched those from the
  extracted wheel.
- Markdown local links/anchors and whitespace checks passed.

The full suite's acquisition and tool-boundary cases use synthetic fixtures;
no biological sequences, reads, datasets, or external biological inference
were retrieved or run. Linux/Windows CI and PR review remain required before
this prerequisite is considered merged or available to M16.

## 7. Files and boundaries

The infrastructure change is limited to:

- `satellite_discovery/stage_cache_identity.py` and its packaged exact-alias
  resource;
- cache-key composition in `artifact_workflow.py`;
- M12/M13/M15 stage identity composition and M14 selected-contract cache
  identity;
- `pyproject.toml` package-data declaration;
- focused regression tests for the affected identities and cache boundaries;
- this report and the M16 readiness/implementation-plan status notes.

It does not modify the M16 or M15 frozen contracts, README, ROADMAP, CI,
workflow schemas, artifact schemas, M1–M15 scientific implementation, or any
biological data or tool configuration. It adds no M16 stage, M16 tests, public
CLI, dynamic loader, external caller, or benchmark.

## 8. Verdict and remaining gates

**Infrastructure verdict: CONDITIONALLY READY, pending full validation, CI,
review, and merge of the separate infrastructure PR.** The implementation now
has explicit stage-owned source dependencies, exact baseline aliases,
relocation/line-ending coverage, and a tested M15-verifier dependency. The
reported one-time M14 and M15 cache refreshes are deliberate and visible.

**M16 implementation verdict: BLOCKED until the infrastructure prerequisite is
merged and its checks pass.** Afterwards, M16 still requires a real offline
synthetic M15 execution, an authenticated `m15_result_bundle`, and a test in
which M16 consumes that exact artifact. None of these gates authorizes
biological data retrieval, external biological inference, or an empirical
benchmark.
