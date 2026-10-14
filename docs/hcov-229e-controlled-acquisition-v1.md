# HCoV-229E controlled acquisition v1

**Status: BLOCKED by default.** This release contains a separate signed-approval and bounded-transfer implementation, but the live CLI deliberately blocks until a fresh GEO/BioSample/publication evidence retriever is implemented and independently reviewed. No approvals, signing keys, or operator authorizations are included.

## Supported run

Only SRR12424250 / SRX8920123 / SAMN15776099 / GSM4718636 from GSE155986, PRJNA656274, SRP276927 is allowed. The FASTQ must remain `SRR12424250.fastq.gz`, exactly 680,887,913 compressed bytes with archive MD5 `9ac379cab68b8b5e2862ec167e95d3c9`; its canonical manifest SHA256 is `8af1155a0ff3d65d2d32bb62560b2db37c22fb5f37c6b38a684a72747e4e9fe0`. The run limit is one, the compressed cap is 1,000,000,000 bytes, and approved storage must cover at least 2,311,099,195 bytes.

Reported 24-hour HCoV-229E exposure is evidence about study treatment, not proof that viral reads are present. The strict `public-virus-v1` result remains insufficient and HELD. This feature never runs QC, alignment, assembly, or discovery.

## Trust and scientific decisions

The maintained `cryptography` package verifies Ed25519 signatures over canonical UTF-8 JSON (sorted keys, compact separators, no NaN). A signed scientific payload must bind the exact scope, policy and evidence digests, complete FASTQ manifest digest, technical-pilot purpose, resource limits, unresolved limitations, and separate owner and independent-reviewer decisions. The verification store assigns trusted public keys to the `owner`, `independent_reviewer`, or `operator` role. Role reuse is rejected.

Provision `trusted_keys.json` in a protected directory outside the checkout. Example structure:

```json
{
  "schema": "hcov-229e-trust-store-v1",
  "keys": [
    {"key_id": "owner-2026", "role": "owner", "public_key": "<base64 raw Ed25519 public key>"},
    {"key_id": "reviewer-2026", "role": "independent_reviewer", "public_key": "<base64 raw Ed25519 public key>"},
    {"key_id": "operator-2026", "role": "operator", "public_key": "<base64 raw Ed25519 public key>"}
  ]
}
```

Create and retain private keys using an organization-approved key-management process on separately controlled systems; never place them in this repository or in application configuration. Trust-store administrators must verify key ownership and role assignment out of band. On POSIX, the trust directory and file must not be group/world writable. Windows ACLs require separate administrator review. Removing a public key revokes it for subsequent runs; a consumed authorization remains consumed.

Owner and independent reviewer sign the same scientific payload using their own keys. The key IDs map to the two distinct trust roles; the signed owner/reviewer identifiers must also differ. A local `APPROVED` JSON value without valid signatures is not accepted. This mechanism authenticates possession of configured keys; it does not establish that a reviewer is scientifically competent or that the host is uncompromised.

The operator separately signs an authorization bound to the same run, scientific evidence, policy, manifest, resource limits, and the exact approved storage-root path. It contains an operator identity, unique authorization ID, nonce, issue time, and expiry no more than 15 minutes later. SQLite `BEGIN IMMEDIATE`, unique constraints and a durable commit consume the authorization before transfer. Concurrent attempts serialize; a repeated ID or nonce is blocked. A crash after consumption requires a new authorization.

## Readiness and execution

The installed command is `satellite-controlled-exploratory-fastq`. Its default mode reports `signatures_valid_fresh_revalidation_required` with `can_execute: false`; valid signatures are not an execution approval. `--execute` additionally requires a TTY, fresh archive revalidation, and the operator to type the exact run, compressed-byte cap, and storage headroom. There is no noninteractive confirmation bypass.

Before execution, the implementation must refresh SRA/ENA metadata, preserve bounded exact-byte archive snapshots, recompute strict identity and technical suitability, verify exact accessions, one-file manifest, URL, filename, MD5, byte count, canonical digest, storage cap and destination headroom. **The production-owned GEO/BioSample/publication refresher is not implemented. The acquisition path therefore blocks before any source request or FASTQ transfer; no caller-provided callback can replace it.** Changed or unavailable evidence requires new human review and signatures; it is never auto-accepted.

Once the missing evidence-refresh component is implemented and reviewed, transfer must use HTTPS to allowlisted ENA hosts, validate every redirect, stream bounded chunks to a temporary file, verify exact size and MD5, compute SHA256, and finalize without overwriting an existing output. A per-destination exclusive lock, pre-transfer durable audit, destination containment checks, symlink/junction checks, and a disk-headroom recheck immediately before transfer are applied. The legacy controlled acquisition API remains fail-closed and unchanged.

## Failures and audit

The audit is created before authorization consumption. The authorization is reverified at consumption and transfer boundaries, and the exact verified payload is recorded under the trust directory's replay database. Transfer, audit, network, checksum, space, lock, output collision, or interruption failures do not permit silent retry or partial-file reuse. Inspect `acquisition.json` and the external replay database; a new operator authorization is required after any consumed attempt. The audit records the exact run, signer key IDs, authorization ID, strict HELD status, manifest, byte count, MD5 and SHA256. Do not edit or delete the replay database to restore an authorization.

The trust store and replay database are local trust anchors. Their protection, backups, clock accuracy, and host integrity are operational responsibilities. No live acquisition should be enabled until the missing fresh treatment-evidence retriever and its source parsing, retention, and withdrawal/conflict tests receive independent review. No genuine FASTQ was downloaded during development or testing.
