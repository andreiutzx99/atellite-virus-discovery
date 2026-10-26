# M21 Phase 7B trust roots and evidence replay

## Trust inputs

The evidence archive is not a trust store. Before verification, provision these
values through an independent channel:

- A trust-anchor JSON file stored outside the repository and archive.
- Its SHA-256 public-key fingerprint.
- The SHA-256 digest of the current signed trust-state checkpoint.
- For registry generations after 1, the independently retained digest of the
  previous checkpoint.

The anchor signs the identity registry and state checkpoint. The first registry
generation is explicitly bootstrapped by that pinned anchor. Later generations
require two distinct, non-self `trust_admin` approvals with the
`trust_registry_enrollment` scope. The verifier checks key uniqueness, validity
windows, revocation, role/scope, checkpoint linkage and registry expiry. A
registry that cannot be connected to the externally pinned checkpoint is not
accepted.

Identity-verification method, authority and evidence digest are assertions made
by the pinned root. They are not independent proof by themselves. Provisioning
and authenticating the root remain operational responsibilities; synthetic
fixture keys must never be used as operational credentials.

For a rotated identity, include one `trust_registry_history` artifact containing
the ordered signed registry bundles from generation 1 through the generation
before the current registry. The verifier authenticates each generation under
the pinned root, checks checkpoint continuity and binds each old key fingerprint
to the prior signed identity record. Missing history is `INCOMPLETE`; reordered,
conflicting, revoked, or discontinuous history is `FAIL`.

## Evidence archive and replay command

The archive is a ZIP containing `manifest.json` and only the files listed in
its manifest. Every artifact descriptor binds an ID, relative path, kind,
uncompressed size and SHA-256 digest. The reader rejects unsafe paths,
duplicate or unlisted members, symlinks, oversized files, excessive compression
ratios and malformed inventories. The schema is
`m21_phase7b_evidence_package.schema.json`.

Archive membership, declared sizes and digests are checked before attempting to
load the independently provisioned trust anchor. A missing schema validator or
external anchor therefore cannot turn known-invalid archive content into an
`INCOMPLETE` result.

Example:

```text
satellite-m21-phase7b-replay verify evidence.zip \
  --trust-anchor /independent/trust/anchor.json \
  --trust-anchor-fingerprint <externally-pinned-sha256> \
  --trust-state-checkpoint-sha256 <externally-pinned-checkpoint-sha256> \
  --previous-trust-state-checkpoint-sha256 <prior-checkpoint-sha256>
```

Omit the previous-checkpoint option only for generation 1. The archive's
`replay_inputs` artifact has this shape; the empty stage maps below are
placeholders, and a valid package must supply every required artifact type for
every state:

```json
{
  "schema_version": "m21-phase7b-replay-inputs-v1",
  "transition_receipts": [],
  "stage_artifact_ids": {
    "QUALIFIED": {"control_qualification": "artifact-id", "qualification_evidence": "artifact-id"},
    "REFERENCE_APPROVED": {},
    "BLINDED_ANALYSIS_VERIFIED": {},
    "UNBLINDING_AUTHORISED": {},
    "SYNTHETIC_SCORING_COMPLETE": {}
  },
  "chain_id": "synthetic-chain-id",
  "local_checkpoints": []
}
```

Each stage map must name every typed artifact required by the canonical Phase 7
transition verifier. IDs resolve only to manifest-listed, digest-verified
members. `checkpoint_history`, `audit_chain`, and `custody_receipt` contain the
retained custody evidence. `reviewer_approvals` contains `closure_package` and
its signed `approvals`. Reviewer gate roles are projected from scopes in the
authenticated registry; package-supplied roles cannot extend those scopes.
The command also requires GitHub CLI verification of the exact attested CI
result bytes and run attempt.

## Current verification boundary

The integrated synthetic ZIP test runs the real trust-history, canonical
transition, reference/control/scientific approval, custody-retention,
CI-statement, and closure validators against archived bytes. Its offline CI
fixture replaces only the GitHub CLI/API response boundary: run identity, run
attempt, job results, attestation payload structure, and matrix digests are
still checked by the real internal verifier. This test boundary is test-only;
operational replay must use authoritative GitHub attestation verification.
Complete-package mutations rehash their changed manifest entries and must still
be rejected for invalid approvals, reference/control substitutions, changed
transition receipts, custody checkpoints, reviewer signatures, CI attempts,
and cross-snapshot evidence. A fixed verification time is injected to compare
repeat reports deterministically.

The Ubuntu/Windows offline-test matrix installs the `phase7-schema-validation`
extra before running the complete suite, so these replay tests exercise the
required schemas. The optional-tools job intentionally keeps its minimal
dependencies; it skips only the complete ZIP-replay test class while retaining
the fail-closed missing-validator checks. The schema-enabled offline matrix is
the authoritative CI run for the full Phase 7B replay tests.

The command invokes the canonical Phase 7 transition adapter, which recomputes
reference-panel exclusions, scientific approvals, signed control qualifications,
blinded analysis, unblinding authorization, and synthetic scoring from retained
bytes. It then invokes the independent checkpoint-custody and closure-review
validators, and verifies exact CI run, attempt, acceptance results, and GitHub
attestation. Stored `PASS` fields are not used as evidence.

Even a technically passing synthetic replay cannot establish operational
readiness: the closure verifier deliberately returns `INCOMPLETE` until its
trust roots, reviewer identities, and custody source are independently
authenticated. Overall state remains `BLOCKED_FOR_BENCHMARK_EXECUTION`, and
`biological_execution_authorized` remains false. All fixtures and tests must
remain synthetic. Do not use biological data, provision operational
reviewer/custodian identities, or start a biological benchmark as part of this
work.
