# External producer-stage authentication

**Verdict: EXTERNAL PRODUCER-STAGE AUTHENTICATION: IMPLEMENTED — READY FOR REVIEW**

This report records the shared external-artifact provenance design and its
implementation. It does not implement M15 or M16, change their frozen
contracts, establish a biological result, or prove the identity of a signer.

## 1. Authoritative baseline and current status

After PR #45 merged, the implementation branch was synchronized to GitHub
`main` at commit `0255359aac335a1224107d25e3d490212246277e`, tree
`9a6d1200e9b14b1337d3b90457468b2d81018a3b`. This was the authoritative
starting snapshot for the code audit; PR #45’s unmerged branch was not used as
a base.

During validation, PR
[#47](https://github.com/andreiutzx99/atellite-virus-discovery/pull/47)
merged at 2026-10-01 08:09:07 UTC. It changed only `README.md` and
`docs/ROADMAP.md`, reconciling their M14 status with the merged M14
implementation. Current GitHub `main` is
`048d569129d11deecfad8ebf3b9ff890d62322bd`, tree
`57b315ba28ee71919a56a3126762f62a883858a0`. The shared-provenance branch is
rebased onto that current `main` before publication.

PR [#46](https://github.com/andreiutzx99/atellite-virus-discovery/pull/46)
remains open and unmerged. Its head was `901e18bd126b3f619ef1ea22feca652c6b2d6d8c`
when checked, and its base remains `c2a3fcee204faa199f2abfa50a65800ab9996ee1`.
No PR #46 files or commits were changed or used as implementation evidence.

Relevant versions on the recorded main snapshot:

| Interface | Mainline version/status |
| --- | --- |
| Artifact workflow record | `artifact-workflow-manifest-v2` |
| Typed artifact descriptor | `artifact-contract-v1`, contract version `1` |
| Workflow/stage lifecycle vocabulary | `workflow_states.py`; raw values include `pending`, `running`, `complete`, `skipped`, `dependency_missing`, `external_module_required`, `failed`, `interrupted`, and workflow-only `partial` |
| M13 external M5 outcome | `m5-execution-outcome-v1`; intentionally M5-specific |
| M15 input contract | Frozen `m15-input-v1` |
| M16 synthetic public input | Frozen `m16-public-manifest-v1`; M16 remains planned |

Current main’s README and roadmap mark M1–M14 implemented and M15–M16 planned.
The roadmap says M15 remains blocked pending shared producer-stage
authentication; this separate review PR does not change that milestone status.
The M14 implementation and tests are present after PR #45. The header in
[`M14_CONTRACT_FREEZE.md`](../M14_CONTRACT_FREEZE.md) still says
“PLANNED / NOT IMPLEMENTED”; the roadmap was reconciled by PR #47, but this
contract/header discrepancy remains. This report records the discrepancy; it
does not change milestone status or the M14 contract.

## 2. Existing provenance chains

| Producer path | Existing evidence | What it proves | Limit for external producer authentication |
| --- | --- | --- | --- |
| Same-workflow M1 handoff | The workflow runner resolves a prior completed stage, reads its `manifest.json`, checks `output_sha256`, hashes the artifact bytes, and verifies a typed descriptor when present ([`artifact_workflow.py`](../../satellite_discovery/artifact_workflow.py#L645), [`artifact_contracts.py`](../../satellite_discovery/artifact_contracts.py#L860)). | A stage/artifact handoff inside the active workflow execution. | It uses the active workflow result and output root; it is not an external reference verifier for a separately supplied workflow snapshot. |
| M1 producer record | `workflow.json` records workflow ID/status, stage ID/kind/status/output path, stage-manifest digest, output inventory, and typed artifact descriptors. `_verify_stage_outputs` validates stage files before the runner records them ([`artifact_workflow.py`](../../satellite_discovery/artifact_workflow.py#L1706)). | The producer’s own workflow row links a completed stage to its manifest digest and typed outputs. | A direct/external artifact reference must pin the exact workflow bytes and compare the selected row’s manifest digest to the manifest actually read. |
| M5 execution outcome / M13 | `execution_outcome.py` defines M5 execution outcomes; M13 requires M5 workflow and outcome references ([`execution_outcome.py`](../../satellite_discovery/execution_outcome.py#L448), [`m13_stage.py`](../../satellite_discovery/m13_stage.py#L386), [`M13_CONTRACT_FREEZE.md`](../M13_CONTRACT_FREEZE.md)). | M5-specific raw lifecycle states and their workflow/outcome references for M13. | It does not define a generic external artifact ownership contract for M1–M14. Extending it would change an M5-specific interface and risk changing its meaning. |
| M14 external sources | Mainline M14 resolves an explicit workflow path, checks workflow ID and M4/M7 stage identity, reads the stage manifest, and validates M14 source artifact references ([`m14_descriptive_observations.py`](../../satellite_discovery/m14_descriptive_observations.py#L617)). | M14-scoped source outcomes under its allowlisted M4/M7 inputs. | Its reference is M14-specific. It does not carry a digest of raw `workflow.json` and does not compare the selected workflow row’s `stage_manifest_sha256` with the manifest bytes it reads. It is not a generic shared verifier and is not changed here. |
| Frozen M15 external/direct refs | `m15-input-v1` names producer/stage/run-manifest digest and artifact fields; it allows workflow links for provenance ([`M15_CONTRACT_FREEZE.md`](../M15_CONTRACT_FREEZE.md#2-runner-and-accepted-artifact-types)). | Caller-supplied producer metadata and artifact identity as declared by that contract. | The external reference does not independently verify that the supplied producer stage owns the supplied stage manifest and artifact. A real digest can accompany a fabricated stage claim. |
| Frozen M16 target | The target reference names producer/stage/run digest, type/version/path/output digest, and target implementation/config identity ([`M16_CONTRACT_FREEZE.md`](../M16_CONTRACT_FREEZE.md#2-runner-and-accepted-target-artifacts)). | The frozen target bundle and implementation identity requirements for synthetic benchmark mechanics. | This does not add an external workflow-to-stage verifier and is not changed here. |

The shared gap is between a caller’s producer-stage claim and the authoritative
M1 workflow row. M1 already writes the data needed to close it; the gap is that
no versioned, reusable external reference pins and checks the entire chain:

> exact workflow bytes → selected workflow stage row → exact stage manifest →
> typed artifact descriptor and inventory → exact artifact bytes

The M13 handoff research correctly distinguishes a digest integrity link from a
signature of origin ([`M13_HANDOFF_GAP_RESOLUTION.md`](M13_HANDOFF_GAP_RESOLUTION.md#1-finding)).
This implementation preserves that boundary.

## 3. Designs considered

| Design | Correctness for external ownership | Compatibility and implementation size | Duplication/cache/packaging | M15 and later M16 |
| --- | --- | --- | --- | --- |
| **A. Reuse or extend M5 execution outcomes** | Insufficient as-is: M5 outcomes are not the general source of M1–M14 artifact ownership. Extending them would need a new cross-milestone contract. | Changes a frozen M5-specific interface or adds a second meaning to it. | Would couple generic provenance to M5 code and cache/source identity. | Poor fit for non-M5 M15 artifacts and future M16 external-run targets. |
| **B. Add a versioned producer execution reference** | Sufficient when it pins the raw M1 workflow record and the verifier checks the selected workflow row, stage manifest, descriptor, inventory, and bytes. | Additive `producer-execution-ref-v1`; no existing producer schema or scientific behavior changes. | One small shared verifier, focused tests, and LF/CRLF cache compatibility refresh; no runner sidecar or new dependency. | Direct fit for a future versioned M15 input extension and reusable for M16/external runs. |
| **C. Add a runner-generated stage attestation** | Could carry the same bindings, but the workflow record already contains the stage/manifest/artifact link. A new unsigned sidecar would still need a trusted digest reference. | Changes M1 runner outputs, execution behavior, and existing producer packaging; broader than needed. | Duplicates workflow fields, creates another artifact/cache lifecycle, and requires runner/backward-compatibility work. | Possible, but unnecessary unless a future producer needs an independent signed attestation. |
| **D. Reuse the current M14 helper** | Not sufficient as a shared contract. It is M14-scoped, accepts M4/M7 source specs, has no raw workflow digest in its reference, and omits the workflow-row-to-stage-manifest-digest equality check. | Reusing it would either retain those limitations or change M14’s frozen identity/cache behavior. | Avoids some code but couples M15/M16 to a domain-specific implementation and duplicates no shared schema. | Poor fit outside the M14 source path. |

**Selected: B.** It reuses authoritative M1 records without changing their
producer behavior, and does not rely on stage names, type allowlists, paths, or
directory layout as ownership proof.

## 4. Versioned reference and verification behavior

The shared module is
[`producer_provenance.py`](../../satellite_discovery/producer_provenance.py).
Its `producer-execution-ref-v1` object is separate from the caller’s existing
artifact reference:

```json
{
  "schema": "producer-execution-ref-v1",
  "producer_workflow_ref": {
    "path": "runs/run-17/workflow.json",
    "sha256": "<raw workflow.json SHA-256>",
    "workflow_id": "workflow-17"
  },
  "producer_stage_id": "m7-independent-recurrence",
  "producer_stage_kind": "independent_recurrence",
  "producer_stage_manifest_sha256": "<raw stage manifest SHA-256>"
}
```

The caller supplies the bundle root explicitly, along with the artifact’s
relative path, type, contract version, expected SHA-256, and its location in
that bundle. The verifier:

1. Rejects unknown reference shapes/versions, absolute paths, traversal,
   backslashes, symlinks, and non-regular files.
2. Hashes the exact raw `workflow.json` bytes, compares the pinned digest and
   workflow ID, and selects exactly one matching stage ID/kind.
3. Preserves the raw workflow status. A completed stage may still be verified
   when an unrelated later stage made the overall workflow `partial` or
   `failed`.
4. Requires the selected stage’s raw status to be `complete`; otherwise raises
   a typed `INCOMPLETE` result carrying the producer’s original status.
5. Hashes `manifest.json` and requires the same digest in both the reference
   and the selected workflow stage row’s `stage_manifest_sha256`. It also
   compares stage status and `stage_manifest_identity` when that field exists.
6. Requires the artifact path/digest in the stage manifest inventory, M1
   workflow output inventory, and typed `artifact-contract-v1` descriptor to
   agree. It hashes both the producer artifact and supplied consumer copy.
7. Returns the raw workflow/stage statuses, workflow/stage/artifact digests,
   typed artifact identity, and a canonical `binding_sha256`.

The M1 `workflow.json` is in the producer output root; the schema uses its
parent directory as the stage-output root. References are relative to the
explicit caller-selected bundle root. Physical paths are not part of the
binding hash; the workflow digest, workflow/stage identity, raw statuses,
stage-manifest digest, artifact relative name/type/version, and artifact digest
are. M1 does not expose a separate immutable run ID, so the exact workflow-file
digest is the run-snapshot identity. Repeated runs with the same workflow ID
remain distinct when their workflow bytes differ.

This is a deterministic integrity chain, **not a digital signature**. It
proves the selected stage/artifact agree with the exact workflow bytes named by
the reference. It does not prove who supplied those bytes or prevent an actor
who can replace the workflow, reference, and expected digest together. The
workflow digest must therefore arrive through the trusted producer handoff or
another trusted channel. Adding signing keys or a remote attestation system is
not part of this change.

## 5. State and scientific boundaries

`verify_producer_artifact` returns or raises only provenance/lifecycle
information:

| Condition | Verifier result | Meaning |
| --- | --- | --- |
| Complete stage, matching manifests/descriptors/bytes | Verified binding | Provenance chain is internally consistent. |
| Producer workflow/artifact is missing or unreadable | `UNAVAILABLE` | No verified link was established; not a negative result. |
| Selected stage is pending, running, skipped, dependency-missing, failed, or interrupted | `INCOMPLETE`, with raw status | Producer execution state is retained; no scientific interpretation. |
| Malformed, stale, conflicting, unsafe, or mismatched record | `INVALID` | No verified link was established; not evidence of absence. |
| No reference was supplied | The caller does not invoke the verifier | Omission remains omission; it does not become an empty/negative artifact. |

This layer does not make scientific claims. A verified binding does not prove
biological authenticity, DVG or satellite identity, helper dependence,
novelty, function, or biological absence. It checks that the artifact type and
contract version agree across the reference, inventory, and typed descriptor;
it does not decide whether an otherwise well-formed type is registered or
validate the artifact’s scientific schema. The consuming milestone must run
its own contract validator.

## 6. Cache, relocation, and serialization

| Change | Provenance binding behavior | Existing M1–M14 cache behavior |
| --- | --- | --- |
| Move an intact bundle under a different filesystem root | Same binding; absolute locations are excluded and relative paths resolve under the explicit root. | No change. |
| Reorder/pretty-print the reference JSON or use LF versus CRLF for that reference file | Same result after parsing; the canonical identity projection uses sorted keys and fixed separators. | No change. |
| Change raw `workflow.json` LF to CRLF | The old reference fails unless its workflow digest is refreshed. With a refreshed reference, the new raw workflow digest and binding are distinct. | No change. |
| Change unrelated workflow metadata | The whole raw workflow digest changes, so the new binding changes conservatively. | Old stage keys remain mapped to their pre-change legacy digests. |
| Change workflow ID/run snapshot, stage ID/kind/status, stage manifest, artifact path/type/version, or artifact bytes | The link is rejected if it conflicts with the pinned records; a valid new run/artifact has a different binding. | No retroactive change to old milestones. |
| Use Windows/Linux path separators | References require normalized POSIX-relative paths; absolute/drive/backslash paths are rejected. Hashes are over exact file bytes. | Package source LF/CRLF compatibility is covered below. |

Adding a Python module changes the repository’s whole-package source
fingerprint used by unscoped legacy stages. The accepted M12 compatibility
digests were refreshed for both LF and CRLF source inventories while preserving
the existing `legacy_source_sha256` values. The M12 regression tests recompute
both source inventories and verify that unscoped M1–M12 cache keys still map
to the same legacy digest. M14 retains its separately scoped implementation
identity and cache behavior. No stage cache or scientific artifact was
rewritten.

The new module has no additional package dependency or external resource.
It is ordinary package Python source and must be present in the built wheel.

## 7. Synthetic acceptance matrix

| # | Synthetic case | Expected result |
| ---: | --- | --- |
| 1 | Valid workflow, stage, stage manifest, descriptor, inventory, and artifact copy | Verified binding. |
| 2 | Fabricated stage ID with otherwise genuine artifact | `INVALID`; stage is not found in the pinned workflow. |
| 3 | Wrong stage kind | `INVALID`; selected workflow row does not match. |
| 4 | Wrong workflow ID or different run snapshot digest | `INVALID`; workflow identity/digest mismatch. |
| 5 | Genuine manifest from another real stage relabelled as this stage’s manifest | `INVALID`; workflow stage row digest does not match. |
| 6 | Stage-manifest digest differs between reference, workflow row, and file bytes | `INVALID`. |
| 7 | Artifact digest differs in any inventory, descriptor, producer file, or supplied copy | `INVALID`. |
| 8 | Unknown reference schema or artifact type/version disagrees with the typed descriptor | `INVALID`; unknown but well-formed artifact types are not rejected by this provenance-only layer. |
| 9 | Missing producer workflow record | Typed `UNAVAILABLE`. |
| 10 | Corrupt producer workflow JSON | Typed `INVALID`. |
| 11 | Absolute/traversal/backslash path | `INVALID`. |
| 12 | Symlinked workflow/artifact or a path that escapes the selected bundle root | `INVALID`. |
| 13 | Byte-identical bundle relocated to another filesystem root | Same deterministic binding. |
| 14 | Equivalent reference-object serialization/LF/CRLF after parsing | Same binding; raw producer workflow LF/CRLF variation remains integrity-significant. |
| 15 | Two otherwise same-shaped runs with different raw workflow snapshots | Different workflow and binding digests. |
| 16 | One invalid reference followed by an independent valid reference | The invalid call has no shared mutable state; the valid reference still verifies. |

These cases are covered by
[`test_producer_provenance.py`](../../tests/test_producer_provenance.py) and
the LF/CRLF cache regression in
[`test_m12_artifact_review.py`](../../tests/test_m12_artifact_review.py).

## 8. M15 integration requirements

The frozen [`m15-input-v1`](../M15_CONTRACT_FREEZE.md) must not be silently
reinterpreted. A future M15 implementation that authenticates direct/external
producer artifacts should carry this typed reference either per artifact or
per producer-stage group, invoke the shared verifier before accepting the
artifact, and preserve the verifier’s raw workflow/stage statuses separately
from scientific evidence states.

Because `m15-input-v1` has no `producer-execution-ref-v1` field and its
artifact references have their own frozen producer-run digest semantics, the
M15 integration must use a new input/reference version or a separately frozen,
explicitly versioned additive extension. It must not substitute this workflow
digest for an existing M15 run-manifest digest. It must also preserve external
artifact support: the caller supplies an explicit bundle root and verified
references; the implementation does not search for producer directories or
infer roots.

This PR does not change PR #46, M15 code, M15 tests, the M15 frozen contract,
README, roadmap, or milestone status.

## 9. M16 and external resources

The frozen [`M16 target reference`](../M16_CONTRACT_FREEZE.md#2-runner-and-accepted-target-artifacts)
still needs its target bundle’s producer/stage/run digest, artifact
type/version/path/digest, and implementation/configuration identity. This
shared verifier can support a future M16 external target handoff, but its
binding alone does not satisfy the M16 target contract and does not modify
M16’s target or label-isolation rules.

The synthetic baseline requires no external data, references, biological
sequences, reads, network access, or third-party executables. No resource was
retrieved, provisioned, licensed, or approved during this work.

## 10. M15 readiness report location

`docs/research/M15_FINAL_IMPLEMENTATION_READINESS.md` is absent from the
recorded `main` tree. The exact prior file exists in local commit
`e3aa9439e0b4588ad07bab1ea578592244ba2e20`, titled “Add M15 implementation
readiness audit,” on local refs `feature/m14-offline-baseline` and
`replit-agent`; that commit is not an ancestor of current `main`. The file’s
SHA-256 is
`94b6a0a67692bb97e19bf3dc73d491fb71cea64eac8a7c433bcc694101ddc523`.
It was not reconstructed or copied into this implementation branch.

## 11. Implementation and validation scope

The shared change is limited to a new verifier module, focused synthetic tests,
an LF/CRLF legacy-cache compatibility refresh, its regression test, and this
design report. It does not change M1–M14 producer behavior, M5 outcome
semantics, M14 cache identity, M15/M16 implementation, or external data
access.

Validation passed: 22 focused producer-provenance tests; 8 M12 artifact-review
and cache-compatibility tests; the full suite (622 tests, 15 skipped); Python
compileall; `pip check`; wheel build and isolated install with the new module
verified inside the wheel; and the installed `satellite-discovery --help`
smoke check. Local Markdown targets/anchors, the 16-row acceptance matrix,
terminology checks, and `git diff --check` also passed. The full suite ran
again on the branch rebased onto current main; PR #47’s mainline delta was
limited to README/roadmap status documentation.