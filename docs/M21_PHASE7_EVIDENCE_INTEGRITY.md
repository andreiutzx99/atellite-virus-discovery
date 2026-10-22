# M21 Phase 7 — evidence integrity (draft)

This milestone uses synthetic fixtures only. It does not retrieve biological
sequences, run biological workflows, modify scoring rules, or authorize
biological execution.

## Multi-artifact reference panels

`verify_multi_artifact_reference_panel` first validates the signed Phase 4
reference manifest, then requires every regular file under the reference root
to appear exactly once in that manifest. It verifies per-file bytes and
digests, rejects duplicate paths and cross-file reference identifiers, and
runs the unchanged Phase 5 exclusion algorithm for every FASTA artifact. A
shared alignment-cell budget and aggregate byte, base, reference, and artifact
limits apply across the panel. Limits cannot exceed the corresponding signed
Phase 5 policy ceilings. The canonical inventory sorts by safe relative path
and binds the snapshot, manifest digest, exact policy, aggregate limits, and
per-artifact exclusion evidence.

`verify_multi_artifact_scientific_approval` recomputes the panel result before
accepting approvals. Separate signed approval sets bind the snapshot,
inventory, policy, aggregate exclusion evidence, and exact scientific-review
record. Approval identity is not evidence of scientific appropriateness.

## Independently retained custody

`verify_independent_custody` accepts a local audit chain and checkpoint history
separately from an out-of-band retained checkpoint history. It verifies
Ed25519 approval scope, trust-store identity, sequence, time ordering,
previous-checkpoint links, event count, and chain head. It detects rollback,
replacement, missing history, and reordering. With no retained checkpoint it
reports `UNANCHORED`; a locally stored signature alone never means independent
retention. The caller must establish the out-of-band source and custody
process; this package provides no external service.

## Artifact-backed transitions

`verify_artifact_backed_transitions` requires a full signed state sequence,
typed required artifacts, safe paths inside a declared root, matching
receipt-bound digests, parseable structured artifacts, and trusted
application-supplied stage verifiers. The verifier callbacks are code and must
reopen inputs and rerun the relevant Phase 4–6 semantic checks. Embedded
`PASS` strings are not used as semantic evidence. This draft API does not yet
ship a canonical application adapter set; until those adapters are wired into
the production caller, artifact-backed governance readiness remains
`PENDING`.

## Filesystem assumptions and residual risks

Files are hashed before and after Phase 5 validation and reopened for final
digest comparison. This detects ordinary modification during a check, but
does not provide an atomic filesystem snapshot or protect against a
privileged ABA change that alters and restores bytes between observations.
Callers should use immutable/content-addressed snapshots. No tamper-proof
storage or independent anchoring is claimed.

All benchmark-facing results remain
`BLOCKED_FOR_BENCHMARK_EXECUTION`.
