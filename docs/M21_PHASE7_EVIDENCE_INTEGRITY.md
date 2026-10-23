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
previous-checkpoint links, event count, and the matching local event digest.
The local event chain may contain a valid uncheckpointed suffix after the last
retained checkpoint. Required local checkpoint history must match the retained
prefix; missing, replaced, reordered, stale, expired, or revoked records fail.
With no retained checkpoint it
reports `UNANCHORED`; a locally stored signature alone never means independent
retention. The caller must establish the out-of-band source and custody
process. The verifier cannot prove where supplied retained bytes came from, and
this package provides no external retention service.

## Artifact-backed transitions

`verify_artifact_backed_transitions` requires a full signed state sequence,
typed required artifacts, safe paths inside a declared root, matching
receipt-bound digests, parseable structured artifacts, and resource caps.
Caller-provided callbacks are not executed or treated as authoritative. The
built-in five-stage registry calls the existing signed Phase 4 qualification,
Phase 5 reference-exclusion and scoring validators, and Phase 6 approval and
transition validators. It recomputes the panel and scoring outputs, checks
analysis and truth bindings, and rejects reuse of reviewer identities across
qualification, reference, and unblinding decisions.

The stage payload contract is defined in
`m21_phase7_transition_evidence.schema.json`. Every package carries the same
synthetic benchmark snapshot; the reference snapshot, qualified samples,
analysis digest, approval digests, and scoring result are chained explicitly.
Qualification packages may contain multiple signed control records with a
digest-addressed evidence bundle.

## Readiness and adversarial evidence

The readiness report accepts only in-process results returned by the canonical
Phase 7 verifiers; plain dictionaries containing `PASS` strings remain
`INCOMPLETE`. The 27 named adversarial cases are in
`M21_PHASE7_ACCEPTANCE_MATRIX.md`. A matrix result must match the exact ordered
case registry and be signed by two distinct trusted governance reviewers before
it can contribute to a readiness `PASS`. A readiness `PASS` is infrastructure
readiness for the synthetic scope only; it never authorizes biological work.

## Filesystem assumptions and residual risks

Files are hashed before and after Phase 5 validation and reopened for final
digest comparison. This detects ordinary modification during a check, but
does not provide an atomic filesystem snapshot or protect against a
privileged ABA change that alters and restores bytes between observations.
Callers should use immutable/content-addressed snapshots. No tamper-proof
storage or independent anchoring is claimed.

All benchmark-facing results remain
`BLOCKED_FOR_BENCHMARK_EXECUTION`.
