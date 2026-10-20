# M21 Phase 2 — readiness report

**Snapshot:** 2026-10-20  
**Final decision:** `BLOCKED_FOR_BENCHMARK_EXECUTION`

## Summary

The three specified SRA run-to-sample mappings and their public paired-end Illumina run metadata were independently checked against NCBI SRA RunInfo, Experiment, and BioSample records. The direct metadata crosswalk agrees with the publication sample names:

| Sample | Experiment → BioSample → Run | Current evidence label | Qualification |
|---|---|---|---|
| Px15 | SRX28192996 → SAMN47635716 → SRR32918045 | Publication-supported satellite-positive for the assayed region | Identity and metadata pass; execution gates remain pending |
| PxBG2 | SRX28192998 → SAMN47635718 → SRR32918043 | Publication-supported satellite-positive for the assayed region | Identity and metadata pass; execution gates remain pending |
| Px31 | SRX28192997 → SAMN47635717 → SRR32918044 | Target-specific screen-negative within unknown detection limits | Identity and metadata pass; negative-control suitability remains pending |

The positive evidence is satellite-specific RT-PCR with Sanger-confirmed amplicon regions plus corresponding HTS evidence. PV541158/PV541159 are described as nearly complete; exact terminal recovery is not established by the reported partial amplicon. Px31's screen result is not proof of absolute absence because its assay detection limit is unreported. BRSV helper detection is separately reported in all three and does not establish helper dependence.

## Gate disposition

| Requirement | Status | Finding |
|---|---|---|
| Accession and sample identity | PASS | Direct Experiment/BioSample/Run crosswalk verified for the three specified samples. |
| Public metadata accessibility | PASS | NCBI returns public SRA run metadata and download-path fields. No payload access was attempted. |
| Layout and metadata completeness | PASS | RunInfo identifies paired Illumina NovaSeq 6000 libraries and reports spot/base counts. These metadata do not verify actual reads. |
| File integrity | NOT_EVALUATED | RunHash/ReadHash metadata exist, but no FASTQ export was retrieved, checksummed, or byte-validated. |
| Scientific positive labels | PASS, bounded | Publication supports Px15/PxBG2 positive labels for the assayed region; exact full-length termini are not verified. |
| Px31 negative-control suitability | PENDING | Target-specific non-detection is reported; assay detection limit and read adequacy are unknown. |
| Data-use permissions | PENDING | Article licence and public SRA status do not independently settle read-data reuse or redistribution terms. |
| Technical adequacy / pipeline compatibility | PENDING | No FASTQ quality, depth, conversion, or stage-assumption checks were performed. |
| Reference exclusion and blinding | PENDING | Plan documented; target-excluded references, opaque IDs, external key custody, and leakage checks have not been implemented. |
| General performance evidence | NOT_APPLICABLE to this set | Two positives and one screen-negative from one study cannot support broad sensitivity/specificity estimates. |

No aggregate `PASS` is assigned while file, permissions, technical, negative-sensitivity, and blinding gates remain unresolved.

## Phase 3 recommendation

Do not begin biological benchmark execution yet. A future Phase 3 proposal should require all of the following before any data acquisition or execution:

1. Review and document SRA/submitter reuse terms for the exact records; decide whether local retention and derived-output handling are permitted.
2. Separately authorize any file retrieval. If authorized, record exact exported-file sizes and cryptographic checksums, validate archive/read integrity, and assess read quality/depth without committing biological payloads.
3. Have an independent reviewer assess library adequacy and whether Px31's published negative screen is sufficiently sensitive for the frozen protocol. If not, keep Px31 unevaluable as a negative and source an independently verified helper-positive satellite-negative sample.
4. Approve target-exclusion rules, reference provenance, blind-key custody, group-aware partitioning, candidate matching, deduplication, and sample-level scoring before pipeline execution.
5. Obtain explicit approval for a later biological benchmark, separate from this metadata-only qualification.
6. Plan independent-study positives and helper-positive negatives before making any general performance estimate; keep the three-sample single-study set as feasibility-only.

The existing M1–M20 contracts and fixtures remain unchanged. No biological reads were downloaded or analyzed, and no biological discovery claim is made.

