# M21 Phase 4 — operational readiness

**Overall state: `BLOCKED_FOR_BENCHMARK_EXECUTION`**

Phase 4 strengthens software/governance readiness only. It does not retrieve biological data, approve a biological benchmark, launch M4–M15, or change M1–M20 contracts.

## Implemented

- FASTQ/FASTQ.GZ validation is streamed one record at a time. Paired files are consumed in lockstep; counts, length/quality histograms and summary statistics are accumulated incrementally.
- Exact duplicate detection uses a temporary disk-backed SQLite primary key, avoiding an in-memory identifier set. Reports distinguish `INVALID_CONFIGURATION`, `INCOMPLETE`, `COMPLETE_QUALITY_THRESHOLDS_FAILED`, and `COMPLETE_QUALITY_THRESHOLDS_PASSED`; only the last outcome reports `status: PASS`. Invalid settings are rejected before opening the FASTQ. Any parser/limit interruption is `INCOMPLETE`, never a pass. Four-line FASTQ records are supported; multiline FASTQ is rejected as malformed. No biological QC suitability thresholds are inferred.
- The runtime limit is cooperative, not a hard deadline: elapsed time is checked between FASTQ records. A single blocking read/decompression/database operation may exceed the configured duration before the next check. Do not treat this setting as strict timeout enforcement.
- Reviewer trust stores define reviewer role, approval scope, key ID, validity interval and revocation state. Each gate requires its gate-specific role/scope; reviewers and approval IDs cannot be reused across dataset gates. Key rotation invalidates signatures using a stale key ID. Approval content and evidence digests enter a hash-identified audit record with a verification timestamp.
- Blinding approval binds a sorted operator-artifact inventory digest. The text scan covers supported configuration/text types and paths, rejects symlinks, and fails closed if inventory verification fails. Pattern scanning cannot detect every transformed or encrypted disclosure.
- Reference snapshot approvals bind source/version, policy identity and each local file path/byte count/SHA-256. The checker independently rehashes the actual local bytes and links the panel digest into the dataset manifest.
- Readiness output reports separate categories and always retains `BLOCKED_FOR_BENCHMARK_EXECUTION`; a successful software check is not execution authorization.

## Categories

| Category | Current software result |
|---|---|
| Software validation | Synthetic tests and validators only |
| Dataset qualification | Pending independent scientific/data review |
| Reference integrity | Local digest checks are available; no biological reference panel inspected |
| Scientific ground-truth adequacy | Pending |
| Data-use permissions | Pending |
| Blinding | Inventory-bound scan available; independent operational sign-off still required |
| Independent approvals | Synthetic trust records only |
| Biological execution authorization | Not granted |

Px31 remains `NEGATIVE_CONTROL_SUITABILITY_PENDING`. Do not infer absence from its target-specific screen-negative. See [control qualification rules](M21_PHASE4_CONTROL_QUALIFICATION.md).

## Phase 5 synthetic scoring additions

The separate Phase 5 modules provide synthetic reference-exclusion validation and deterministic scoring. See [reference exclusion](M21_PHASE5_REFERENCE_EXCLUSION.md), [control eligibility](M21_PHASE5_CONTROL_SCORING_ELIGIBILITY.md), [blinded handoff](M21_PHASE5_BLINDED_EVALUATION.md), and [scoring definitions](M21_PHASE5_SYNTHETIC_SCORING.md). These checks do not change the overall state or Phase 4/M1–M20 contracts.

## Limitations and custody

The SQLite identifier table is temporary and can require substantial disk space. Runtime, record, decompressed-byte and read-length limits are operator-configured safety limits, not biological QC thresholds; the runtime limit is cooperative and does not guarantee a hard wall-clock cutoff. Trust-store revocation/rotation is enforced against the supplied current store, but cross-run replay prevention still requires custodians to preserve and reconcile the tamper-evident audit digests in an external append-only custody system. No real reviewer credentials, approvals, mappings, FASTQ or reference sequences are included.
