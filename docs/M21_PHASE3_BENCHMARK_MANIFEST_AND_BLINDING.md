# M21 Phase 3 — manifest, approval and blinding specification

**Scope:** offline governance software and synthetic tests only. This does not authorize sequencing-data retrieval, biological pipeline execution, or discovery.

## Manifest

The versioned schema is `satellite_discovery/m21_benchmark_manifest.schema.json`; the offline checker is `satellite-discovery m21-readiness validate` (or `python -m satellite_discovery.m21_benchmark_readiness validate`). The operator manifest contains only opaque dataset/sample IDs, a source-catalog name, and opaque custodian/accession references. It rejects biological accession patterns, sample-name/truth-label fields, expected sequence fields, and unknown properties.

Metadata verification and byte verification are separate signed gates. A metadata record, archive hash field, declared byte count, or `METADATA_ONLY` status cannot satisfy byte verification. To pass the byte gate, the local file must exist under the supplied analysis root, match the declared size and SHA-256, and be marked `VERIFIED`. Paired layouts require exactly R1 and R2.

The mandatory signed gates are metadata verification, file-byte verification, data-use approval, technical-QC approval, reference-panel approval, blinding approval, ground-truth review, negative-control review, and execution authorization. A gate is accepted only when its record is structurally valid, unexpired, signed with Ed25519, and signed by a reviewer in a separately supplied public-key trust store. The signature binds the gate, opaque dataset/sample IDs, status, approval ID, reviewer, timestamps, and evidence digest. The checker verifies the signature and digest syntax; the reviewer remains responsible for examining the referenced evidence before signing. Private signing keys must never be placed in the repository or operator workspace.

Ground-truth review uses separate, non-label-bearing statuses for assayed-region evidence, full-length reconstruction evidence, and negative-control assessment. A reviewed assayed region is not proof of full-length reconstruction. A negative-control claim cannot be represented by a truth label in the operator manifest; the independent signed negative-control review must attest to adequate orthogonal evidence and stated detection limits. `NOT_APPLICABLE` is allowed only for a signed-off decision that no negative-control claim is being made.

## Blinding and truth-key custody

- Generate random `BLD-` identifiers with `generate_opaque_sample_id`; validation rejects malformed and duplicate IDs.
- `write_sealed_truth_key` refuses a path inside the declared analysis workspace, creates the key exclusively, and restricts permissions to owner read/write. Custodian-controlled storage, backup, access logging, and deletion remain operational responsibilities.
- The operator-artifact scan checks filenames and text artifacts for sample/truth fields, public accession patterns, private-key blocks, and optional custodian-provided disclosure tokens. The custodian must supply sensitive terms from outside the operator workspace; no real sample names or mapping are embedded in this code or its tests.
- The scan is a safeguard, not a proof against deliberate or transformed leakage. Review filenames, metadata, configuration, caches, logs, and derived artifacts before unblinding.

## Reference-panel approval

The reference-panel schema requires source and accession/version provenance, a snapshot ID, SHA-256 digest for each reference, target-exclusion policy ID, and a signed independent approval with expiry. The validator rejects missing provenance, malformed digests, and unresolved review. It validates metadata only; no reference sequence is downloaded, inspected, or searched in this phase.

## Command behavior

The checker defaults to `BLOCKED`. It emits a human-readable summary and can write machine-readable JSON with `--json-out`; it returns non-zero unless every required signed gate passes. A passing result reports `READY_FOR_SEPARATELY_AUTHORISED_BENCHMARK`, but the command never launches downloads, preprocessing, assembly, alignment, candidate discovery, or any M4–M15 stage. The result is not itself approval to execute; approval records must already exist and be independently signed.

Example:

```text
satellite-discovery m21-readiness validate \
  --manifest operator-manifest.json \
  --analysis-root ./inputs \
  --trust-store /custodian/reviewer-public-keys.json \
  --scan-root ./operator-workspace \
  --forbidden-token <custodian-supplied-sensitive-term> \
  --json-out readiness.json
```

The fixtures and approval keys used by tests are generated temporarily and synthetically; no biological key or sample mapping is committed.

