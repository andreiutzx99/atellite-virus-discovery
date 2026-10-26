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

Key rotation currently fails closed as `INCOMPLETE`: the bundle format does not
yet provide the prior registry needed to prove that the old key was the key
authorized by the previously pinned state. A valid signature from an arbitrary
old key is not enough.

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

Omit the previous-checkpoint option only for generation 1. The command also
requires GitHub CLI verification of the attested CI result bytes.

## Current verification boundary

The current command verifies archive membership and digests, the external trust
anchor and checkpoint pins, and the GitHub CI attestation. It deliberately
returns `INCOMPLETE` after those checks: canonical replay adapters for the
reference panel, scientific approval, control qualification, transition
receipts, custody history and reviewer approvals are not yet wired into the ZIP
reader. Key rotation also remains `INCOMPLETE` until authenticated historical
registry evidence is supplied and linked. The verifier does not accept
serialized `PASS` fields as a substitute.

Consequently, this code does not establish M21 closure readiness. The decision
remains `INCOMPLETE`, overall state remains
`BLOCKED_FOR_BENCHMARK_EXECUTION`, and biological execution is never authorized.
All fixtures and tests must remain synthetic. Do not use biological data,
provision operational reviewer/custodian identities, or start a biological
benchmark as part of this work.
