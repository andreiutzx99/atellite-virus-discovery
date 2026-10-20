# M21 Phase 3 — manifest, approval and blinding specification

**Scope:** offline governance software and synthetic tests only. This does not authorize sequencing-data retrieval, biological pipeline execution, or discovery.

## Manifest

The versioned schema is `satellite_discovery/m21_benchmark_manifest.schema.json`; the offline checker is `satellite-discovery m21-readiness validate` (or `python -m satellite_discovery.m21_benchmark_readiness validate`). The operator manifest contains only opaque dataset/sample IDs, a source-catalog name, and opaque custodian/accession references. It rejects biological accession patterns, sample-name/truth-label fields, expected sequence fields, and unknown properties.

Metadata verification and byte verification are separate signed gates. A metadata record, archive hash field, declared byte count, or `METADATA_ONLY` status cannot satisfy byte verification. To pass the byte gate, the local file must exist under the supplied analysis root, match the declared size and SHA-256, and be marked `VERIFIED`. Paired layouts require exactly R1 and R2.

The mandatory signed gates are metadata verification, file-byte verification, data-use approval, technical-QC approval, reference-panel approval, blinding approval, ground-truth review, negative-control review, and execution authorization. A gate is accepted only when its record is structurally valid, unexpired, signed with Ed25519, and signed by a reviewer in a separately supplied public-key trust store. Each signature binds an evidence digest and the canonical digest of every non-gate manifest field, including provenance, read layout and byte digests, ground-truth statuses, and the reference-panel digest. Changing any such field invalidates the signatures. Reviewers remain responsible for examining referenced evidence before signing. Private signing keys must never be placed in the repository or operator workspace.

Ground-truth review uses separate, non-label-bearing statuses for assayed-region evidence, full-length reconstruction evidence, and negative-control assessment. A reviewed assayed region is not proof of full-length reconstruction. A negative-control claim cannot be represented by a truth label in the operator manifest; the independent signed negative-control review must attest to adequate orthogonal evidence and stated detection limits. `NOT_APPLICABLE` is allowed only for a signed-off decision that no negative-control claim is being made.

## Blinding and truth-key custody

- Generate random `BLD-` identifiers with `generate_opaque_sample_id`; validation rejects malformed and duplicate IDs.
- `write_sealed_truth_key` refuses a path inside the declared analysis workspace, creates the key exclusively, and enforces owner read/write mode on POSIX. Production truth-key creation is prohibited on Windows because this implementation does not verify secure ACLs. Custodian-controlled storage, backup, access logging, and deletion remain operational responsibilities.
- The required operator-artifact scan checks filenames and text artifacts for sample/truth fields, public accession patterns, private-key blocks, and optional custodian-provided disclosure tokens. The `validate` command requires `--scan-root`; omission is a command-line error, and the underlying readiness function also fails closed without a scan root. The scan can be rerun independently against the same artifact tree. The custodian must supply sensitive terms from outside the operator workspace.
- The scan is a safeguard, not a proof against deliberate or transformed leakage. Review filenames, metadata, configuration, caches, logs, and derived artifacts before unblinding.

## Reference-panel approval

The reference-panel schema requires provenance, a snapshot ID, target-exclusion policy ID, per-reference relative byte path, byte count and SHA-256, and a signed independent metadata approval with expiry. The signature binds the complete reference-panel metadata. `reference-check` and `validate` independently read each local reference under `--reference-root` and compare actual bytes; metadata approval alone cannot establish byte integrity. `validate` also requires the reference-panel manifest digest bound into the signed benchmark manifest. No reference sequence is downloaded or searched in this phase.

## Command behavior

The checker defaults to `BLOCKED`. It emits a human-readable summary and can write machine-readable JSON with `--json-out`; it returns non-zero unless every required signed gate passes. A passing result reports `READY_FOR_SEPARATELY_AUTHORISED_BENCHMARK`, but the command never launches downloads, preprocessing, assembly, alignment, candidate discovery, or any M4–M15 stage. The result is not itself approval to execute; approval records must already exist and be independently signed.

Example:

```text
satellite-discovery m21-readiness validate \
  --manifest operator-manifest.json \
  --analysis-root ./inputs \
  --trust-store /custodian/reviewer-public-keys.json \
  --scan-root ./operator-workspace \
  --reference-manifest reference-panel.json \
  --reference-root ./reference-bytes \
  --forbidden-token <custodian-supplied-sensitive-term> \
  --json-out readiness.json
```

The fixtures and approval keys used by tests are generated temporarily and synthetically; no biological key or sample mapping is committed.

