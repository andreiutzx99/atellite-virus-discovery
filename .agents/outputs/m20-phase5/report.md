# M20 Phase 5 final acceptance review

- Decision: **SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED**
- Release-readiness classification: **SOFTWARE INTEGRATION VALIDATED; BIOLOGICAL DISCOVERY NOT VALIDATED**
- Recommendation: **Accept for synthetic software-integration scope only. This is not biological discovery or biological release validation.**
- Software integration: **VALIDATED**
- Biological discovery: **NOT VALIDATED**
- Cases audited: **10**
- Historical M12 INVALID findings classified: **5**
- Current M12 INVALID findings: **0**

| Case | Candidate availability | M12 verified/invalid | M15 accepted/invalid | Completeness |
|---|---|---:|---:|---|
| c001 | AVAILABLE | 8/0 | 30/0 | PARTIAL |
| c002 | UPSTREAM_UNAVAILABLE | 8/0 | 30/0 | PARTIAL |
| c003 | AVAILABLE | 8/0 | 30/0 | PARTIAL |
| c004 | AVAILABLE | 8/0 | 30/0 | PARTIAL |
| c005 | UPSTREAM_UNAVAILABLE | 8/0 | 30/0 | PARTIAL |
| c006 | UPSTREAM_UNAVAILABLE | 8/0 | 30/0 | PARTIAL |
| c007 | AVAILABLE | 8/0 | 30/0 | PARTIAL |
| c008 | AVAILABLE | 8/0 | 30/0 | PARTIAL |
| c009 | UPSTREAM_UNAVAILABLE | 8/0 | 30/0 | PARTIAL |
| c010 | UPSTREAM_UNAVAILABLE | 8/0 | 30/0 | PARTIAL |

## Historical M12 INVALID rows

- c002 `read_support_evidence`: VALIDATOR_DEFECT_CORRECTED_NO_BIOLOGICAL_OBSERVATION — The producer explicitly reported NOT_EVALUATED and emitted no query rows; requiring completed-query reconciliation mislabeled unavailable accounting as invalid evidence. The row is now VERIFIED for artifact identity with NOT_STARTED/UNKNOWN/NO_OBSERVATION axes.
- c005 `read_support_evidence`: VALIDATOR_DEFECT_CORRECTED_NO_BIOLOGICAL_OBSERVATION — The producer explicitly reported NOT_EVALUATED and emitted no query rows; requiring completed-query reconciliation mislabeled unavailable accounting as invalid evidence. The row is now VERIFIED for artifact identity with NOT_STARTED/UNKNOWN/NO_OBSERVATION axes.
- c006 `read_support_evidence`: VALIDATOR_DEFECT_CORRECTED_NO_BIOLOGICAL_OBSERVATION — The producer explicitly reported NOT_EVALUATED and emitted no query rows; requiring completed-query reconciliation mislabeled unavailable accounting as invalid evidence. The row is now VERIFIED for artifact identity with NOT_STARTED/UNKNOWN/NO_OBSERVATION axes.
- c009 `read_support_evidence`: VALIDATOR_DEFECT_CORRECTED_NO_BIOLOGICAL_OBSERVATION — The producer explicitly reported NOT_EVALUATED and emitted no query rows; requiring completed-query reconciliation mislabeled unavailable accounting as invalid evidence. The row is now VERIFIED for artifact identity with NOT_STARTED/UNKNOWN/NO_OBSERVATION axes.
- c010 `read_support_evidence`: VALIDATOR_DEFECT_CORRECTED_NO_BIOLOGICAL_OBSERVATION — The producer explicitly reported NOT_EVALUATED and emitted no query rows; requiring completed-query reconciliation mislabeled unavailable accounting as invalid evidence. The row is now VERIFIED for artifact identity with NOT_STARTED/UNKNOWN/NO_OBSERVATION axes.
## Full-workflow cache investigation

A fresh instrumented Phase 4 run completed in **89.335 seconds** under a 600-second bound. The identical generated M12 and M15 workflow specifications were then rerun at the same absolute output path. All **30/30 M12** and **10/10 M15** stages were `verified_reuse`; their cache keys, stage-manifest digests, input digests, and artifact digests are recorded per stage in `report.json`. The replay calls took **16.761 s** (M12) and **7.903 s** (M15).

| Call | Workflow | Stages | Executed | Verified reuse | Duration | Last completed |
|---:|---|---:|---:|---:|---:|---|
| 1 | Phase 4 base M4/M6 workflow | 20 | 20 | 0 | 25.316s | `m6_c010` |
| 2 | Phase 4 expanded M12 workflow | 30 | 10 | 20 | 13.392s | `m12_c010` |
| 3 | Phase 4 M15 dossier workflow | 10 | 10 | 0 | 14.592s | `m15_c010` |
| 4 | same-path M12 cache replay | 30 | 0 | 30 | 16.761s | `m12_c010` |
| 5 | same-path M15 cache replay | 10 | 0 | 10 | 7.903s | `m15_c010` |

All ten M6 residual-evidence stages found the optional `minimap2` 2.29 dependency available and executed on the fresh output. They verified reuse on the subsequent same-path workflow pass. No dependency-missing stage, deadlock, or timeout was observed. The earlier 300-second timeout was not reproduced; its cause remains unconfirmed.

The old Phase 4 seed contained M12 outputs with a different implementation source identity. Its ten M12 stages correctly recomputed; this is legitimate cache invalidation, not a same-input cache failure. The top-level Phase 4 runner requires an empty output directory; resume was therefore measured through its generated M12/M15 workflow specifications at their original paths.

## Reproducibility, fixtures, and CI

- Fresh full Phase 4 semantic-outcome digest: `1bf63dc52eee8d2d6f70a03a91923099e1a2588e43bc64643c17da7a18521656`; it matches the expected digest `1bf63dc52eee8d2d6f70a03a91923099e1a2588e43bc64643c17da7a18521656`.
- Frozen Phase 1 and Phase 2B fixture digests remain the values recorded in `report.json`; the Phase 4 run revalidated the frozen Phase 2B handoff. The 81 focused cache, identity, M12, M15, and M20 tests passed.
- The latest CI runs recorded at the reviewed PR head passed: four Linux/Windows × Python 3.11/3.12 matrix jobs (934 tests each; 33 Linux and 37 Windows skips), pinned-runtime and optional-tools jobs. A report-only commit will trigger fresh CI.
- Cache adversarial tests continue to reject tampered output bytes and changed producer/manifest identities; no validation rule was weakened.

## M20 results and limitations

- All data are synthetic. M13 and M14 were not supplied; M15 dossier completeness remains partial.
- M12 validates technical artifact identity and stated accounting only. M15 validates producer provenance separately from payload validity.
- Historical `NOT_EVALUATED`/empty-support rows remain classified as validator defects without biological observations; malformed or missing support evidence remains invalid.
- No biological satellite-virus discovery, novelty, function, helper dependence, or production-resource claim is validated.
