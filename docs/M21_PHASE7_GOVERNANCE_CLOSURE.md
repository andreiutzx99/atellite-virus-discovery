# M21 Phase 7 governance closure

## Trust model

The closure verifier separates four claims: the acceptance-result bytes are
complete; GitHub's attestation authenticates those bytes and the named workflow;
reviewers approve one content-addressed package; and a custodian signs a
checkpoint package retrieved from an HTTPS source. Each claim is recomputed
from supplied bytes. A caller-provided `PASS` value is not evidence.

`verify_ci_acceptance` checks the exact 27 ordered synthetic cases, canonical
result bytes, run statement, subject digest, predicate, repository, workflow,
tested commit, run ID and attempt. It then invokes `gh attestation verify` with
the retained bundle, repository, workflow identity and predicate type. If the
CLI is unavailable or times out, the result is `INCOMPLETE`; a malformed,
mismatched or rejected attestation is `FAIL`.
It also retrieves the specific GitHub run attempt and its jobs, requiring the
expected event, revision, workflow path, completed successful run, and exactly
one successful `phase7-acceptance-evidence` job.

Two distinct Ed25519 reviewer approvals must bind the same closure-package
digest and verification-evidence digest. Trust records enforce key validity,
revocation, role and scope. A package signed by synthetic test identities is
never reported as operational `PASS`.
The trust-store field `identity_class: HUMAN` is only an assertion in the
supplied trust store; it does not verify a person's identity. Reviewer and
custodian trust roots must be provisioned outside this repository and
authenticated independently.

## Independently retained checkpoints

The checkpoint package binds the synthetic snapshot, dataset, chain, signed
checkpoint history and a custodian-signed retention receipt. Verification
checks the HTTPS source, retrieval identity, receipt signature, checkpoint
sequence and continuity against the local audit chain. It detects truncation,
rollback, replacement, reordered or conflicting history and permits a valid
uncheckpointed local suffix.

A signed file alone does not prove independent custody. The custodian key and
retention source must be provisioned independently; the verifier does not
claim immutable storage, trusted timestamps, or third-party retention merely
because an HTTPS URL or signature is present. Synthetic custody fixtures are
tests only and cannot produce operational readiness `PASS`.

## Package and decisions

`m21-phase7-closure-v1` is content-addressed using canonical JSON. It binds the
software revision, canonical Phase 7 verification outputs, verified CI result,
verified checkpoint package, policy version, expiry and explicit limitations.
Schema validation is provided by `m21_phase7_closure.schema.json`. Review
approvals sign both the package digest and the recomputed evidence digest.
The package uses content-addressed evidence references; the corresponding raw
CI, checkpoint, and Phase 7 inputs must remain available for independent
reverification.

- `PASS`: intended only after all component verifiers pass, GitHub attestation
  succeeds, and reviewer identity plus custody-source provenance are
  independently established. The current verifier does not authenticate those
  trust-root origins and therefore deliberately does not emit operational `PASS`.
- `INCOMPLETE`: required evidence or an authoritative verifier is unavailable,
  identity is only asserted by a trust-store record, custody independence is
  not established, or only synthetic reviewer/custody identities are present.
- `FAIL`: evidence is malformed, altered, expired, revoked, inconsistent, or
  fails cryptographic or continuity verification.

Even a closure `PASS` leaves
`BLOCKED_FOR_BENCHMARK_EXECUTION` and
`biological_execution_authorized: false`. It is not scientific approval for
biological testing.

## Procedure and limitations

1. Obtain the matrix results, CI run statement and attestation bundle from the
   successful GitHub Actions run for the exact software revision.
2. Run the closure verifier in an environment with a trusted GitHub CLI and
   reviewer/custodian trust roots provisioned outside the repository and
   independently authenticated.
3. Obtain the checkpoint package from the independently controlled retention
   source and record who retrieved it and when.
4. Assemble and sign the closure package only after all underlying verifiers
   succeed. Re-run verification after any evidence or revision changes.

This repository contains synthetic signing identities and simulated sources
only for adversarial tests. It does not contain real reviewer signatures,
external custody evidence, or a real operational closure package. Until those
inputs are supplied and verified, closure remains `INCOMPLETE`.
