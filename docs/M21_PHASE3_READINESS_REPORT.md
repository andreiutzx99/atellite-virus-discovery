# M21 Phase 3 — software readiness report

**Decision:** `BLOCKED_FOR_BENCHMARK_EXECUTION`

## Software readiness

Phase 3 adds an offline manifest and approval-gate checker, Ed25519 signature/expiry validation against an external reviewer public-key trust store, local SHA-256/byte-count checks, a reference-panel metadata validator, opaque-ID generation/validation, an out-of-analysis-tree sealed-key writer, operator-artifact leakage scanning, and bounded local FASTQ syntax/QC checks.

The checker has a fail-closed default and requires every mandatory gate. Metadata verification cannot substitute for file-byte verification. Ground-truth review keeps assayed-region evidence distinct from full-length reconstruction; negative-control suitability is separately reviewed. A successful report never launches a download or a discovery stage. Readiness requires explicit, valid signed execution authorization and does not arise from passing software tests.

The tests use generated synthetic FASTQ, temporary Ed25519 keys, temporary approval records, and temporary truth-key data. No biological read, reference, sample mapping, or real reviewer key is present in the test fixtures.

Verification completed locally: all 17 focused M21 governance tests pass; the new Python module compiles; both JSON schemas and `pyproject.toml` parse; `git diff --check` passes. The full existing `unittest` suite did not finish within the 300-second local limit, so its result is **incomplete**, not a pass or a test failure. CI results will be reported separately after the draft PR is opened.

## Dataset qualification

Phase 2 verified public metadata crosswalks for Px15, PxBG2, and Px31, but did not retrieve or checksum FASTQ bytes. The current software does not change those qualification results.

## Ground-truth adequacy

Px15 and PxBG2 have publication-supported satellite-specific evidence for the assayed region, not verified exact termini. Px31 remains `NEGATIVE_CONTROL_SUITABILITY_PENDING`: its target-specific screen-negative is detection-limited, and the assay limit is unknown. It must not be counted as a confirmed negative or placed in a specificity denominator without independent approval.

## Data-use permissions

Public SRA access and the article's CC BY 4.0 licence do not settle read-file processing, retention, redistribution, or derived-output terms. The data-use gate remains pending until a reviewer resolves the exact terms and any institutional requirements.

## Biological execution authorization

No biological benchmark is approved. No FASTQ or FASTA was downloaded or inspected, no biological reference database or homology search was made, and no M4–M15 workflow ran. The recommended current state is `BLOCKED_FOR_BENCHMARK_EXECUTION`; a later software-only preparation state may be `PREPARATION_COMPLETE_AWAITING_APPROVAL`. `READY_FOR_SEPARATELY_AUTHORISED_BENCHMARK` is only reportable after all evidence and authorization gates are explicitly signed and independently reviewed.

## Phase 4 recommendation

After review of this draft PR, Phase 4 should focus on operational trust-store provisioning and approval-evidence custody, a scalable streaming FASTQ validator stress-tested on synthetic data, and independent review of the reference-exclusion and blinding protocol. Biological reads, reference acquisition, and benchmark execution require separate explicit authorization and remain out of this phase.

