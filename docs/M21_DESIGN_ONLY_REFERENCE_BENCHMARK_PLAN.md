# M21 — design-only reference and benchmark plan

**Status:** DESIGN ONLY. No biological reads were downloaded or analyzed. Catalogue labels are review metadata and must never enter M1–M20 pipeline inputs.

## Baseline and scope

Reviewed `main` at `2f66cdb09c183373ddf1ea628479c4e25d1d8731` on 2026-10-19. M20 PR #78 (head `e1ea9ac`) is closed and merged at that SHA; the M20 Phase 5 report says synthetic software integration validated, biological discovery not validated. This proposal is separate and does not alter PR #78. M1–M20 contracts, fixtures, validation rules, and analysis inputs are out of scope.

M21 deliverables are this plan, a literature/archive catalogue, and a capability-gap assessment only. It proposes a future review-gated benchmark, not implementation or a biological-performance claim. No biological reads, pipeline runs, wet-lab material, or code/contract changes are authorized.

## Research question and benchmark unit

Can the existing registered workflow produce traceable candidate evidence for independently characterized satellite RNAs in public plant-virus sequencing data while distinguishing ordinary viral variation, mixed infections, and defective viral genomes (DVGs)? A benchmark unit is one independently collected biological sample/library and its complete read set, not a read, contig, or technical lane. Related samples from one plant or experiment remain in one partition.

M20 demonstrated typed synthetic handoffs only; its report explicitly says M13/M14 are absent and M15 completeness is partial. Neither M20 nor this catalogue establishes biological capability.

## Proposed evaluation design (not authorized to execute)

1. **Qualify data first.** Verify archive status, run-to-sample mapping, layout, file availability/checksums, publication ground truth, sample-level target status, permissions, and sample relationships. Independently review labels. Mark a case proposed or unavailable if required evidence is missing.
2. **Partition before unblinding.** A custodian keeps an immutable truth key mapping opaque IDs to expected satellite, helper, host, DVG/variation confounder, and evidence strength. Group by study, plant/host individual, isolate, and experiment before splitting; related samples and technical replicates cannot cross partitions. Freeze/hash the read inputs and reference panel. Operators see opaque IDs and permitted reads/reference inputs only—not truth labels, expected satellite sequences, PCR results, or positive/negative status. Exclude held-out targets and close homologs from the supplied search panel; record the snapshot and exclusions. Do not put labels in filenames, paths, metadata, stage configuration, or logs.
3. **Use unchanged registered stages only after separate authorization.** Use a new isolated output root and existing input contracts. Keep truth and scoring outside pipeline execution. No M1–M20 changes are implied.
4. **Score once after freezing outputs.** An independent scorer joins candidate IDs to the sealed key after output identities and hashes are frozen. Preserve no-candidate, dependency-unavailable, invalid, and incomplete states. Any rerun after disclosure is exploratory, not blinded.

### Outcomes and denominators

- **Exact recovery (primary):** for each independently verified positive, require the top-level recovered consensus to match the frozen curated target at 100% identity and full-length coverage, including exact termini where experimentally established. Report near-full-length separately; pre-register any tolerance. A partial assembly is not exact recovery.
- **Candidate-level detection:** one-to-one match reported candidate to truth using a predeclared identity/coverage rule and correct sample attribution. Report sample-level TP/FN/FP/TN, precision, recall/sensitivity, F1, and specificity with counts and confidence intervals. Cluster duplicate contigs using a frozen rule. Reads and repeated observations are not independent cases.
- **Specificity/false positives:** calculate specificity only over evaluable independently verified satellite-absent controls. Report false candidates per sample and per million input read pairs (or reads for single-end libraries), candidate-level FPR = FP/(FP+TN), and specificity = TN/(TN+FP). Publish every false-positive candidate sequence/evidence. Stratify clean negatives, DVG challenges, and ordinary-variation challenges; they are not interchangeable.
- **Unevaluable/unavailable:** missing reads, failed retrieval, inadequate depth/quality, uncertain target status, missing validated target sequence, absent comparator/control, or required tool unavailable yields `UNEVALUABLE` with a reason. Keep outside sensitivity/specificity denominators; publish counts. Never recode as TN, FN, or biological absence.
- **Secondary descriptive metrics:** candidate-level precision/recall by study/library type/abundance stratum; contig completeness and fragmentation; false-positive sequence class; and processing failure rate. Prespecify abundance thresholds; no post hoc threshold selection.

### Label-strength hierarchy

**Verified positive:** independently characterized target linked to the exact sample/library with orthogonal evidence (e.g. PCR/sequence confirmation) and stable target sequence. **Probable positive:** publication reports sequence-level identification but orthogonal sample-level confirmation is not established. **Proposed:** literature/archive lead with sample/run mapping or validation missing. **Verified negative:** named target-absent sample tested with a relevant orthogonal assay, preferably despite confirmed helper infection. Non-reporting, failed assembly, or low depth is not negative. Keep DVG, ordinary viral variation, mixed infection, and clean satellite-negative as separate truth classes.

## Provenance, licensing, and biosafety gates

- Curator manifest records accession, BioSample, SRA Experiment/Run, publication, exact source URL, access date, archive status, eventual file/checksum, declared/observed layout, and inclusion/exclusion rationale. Pin reference bytes and source records by digest. Authenticate read-to-run and run-to-sample links; do not infer from filenames.
- Keep the sealed label key outside pipeline workspace, artifacts, caches, and routine logs. Do not encode answers in read names. Freeze outputs before scoring. Review data access and retention before acquisition.
- Public SRA availability is not itself a clear reuse licence. Record paper licence separately from read-data terms; check archive/submitter terms before redistribution or mirroring. Do not commit reads or derived biological sequences to this repository.
- Plant pathogen reads are not wet-lab permission. No acquisition, culture, synthesis, or material distribution. Human-pathogen DVG datasets (e.g. mumps) are excluded from the first benchmark; later computational use requires institutional biosafety/privacy review.
- Do not infer helper dependence from co-detection or claim function, novelty, pathogenicity, or transmission from sequence similarity or pipeline output.

## Review gates before any implementation/data use

1. Resolve sample/run/target label map and confirm primary-source negative, variation, and DVG strata.
2. Confirm reuse terms and that files remain public and checksum-addressable.
3. Approve target-excluded reference construction, group-aware partitions, and blind-key custody.
4. Review gaps in `M21_CAPABILITY_GAP_ASSESSMENT.md`; no M1–M20 changes are authorized here.
5. Obtain separate explicit review approval before any biological-data benchmark. Until then: no downloads and no biological execution.

## Suggested small initial benchmark for review

**Provisional candidate: one BRSV satellite-RNA *Phlox* study (BioProject PRJNA1244124), conditional on exact sample/run mapping.** The 2025 paper reports two BRSV satRNAs and says one sample, Px31, had neither satellite-associated reads nor expected-size PCR product; it also reports BRSV/helper and other viruses. NCBI SRA lists nine public paired-end Illumina FASTQ runs. This could offer a positive plus a within-study negative/confounder comparison. However, the evidence reviewed does not securely map the PCR-confirmed positive and Px31 negative labels to exact SRA runs. It is **not ready to run**. First resolve the mapping from supplements and SRA metadata and assess read length, depth, and sample relationships. If the link cannot be established, do not substitute an assumed positive/negative.

Defer grapevine small-RNA and mumps DVG data to capability/challenge work: Ion Torrent size-selected small RNAs are not a clean end-to-end benchmark for the general FASTQ-to-assembly path; mumps DVG reads are neither satellite positives nor clean negatives.

## Sources consulted (2026-10-19)

- Motsar et al. 2025, “Molecular Characterization of Tobacco Streak Virus, Beet Ringspot Virus, and Beet Ringspot Virus Satellite RNA from a New Natural Host, *Phlox paniculata*,” *Plants* 14:1619. DOI https://doi.org/10.3390/plants14111619 ; full text https://pmc.ncbi.nlm.nih.gov/articles/PMC12157320/ ; BioProject PRJNA1244124: https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1244124 ; SRA: https://www.ncbi.nlm.nih.gov/sra/?term=PRJNA1244124 .
- Miljanić et al. 2022, “Small RNA Sequencing and Multiplex RT-PCR for Diagnostics of Grapevine Viruses and Virus-like Organisms,” *Viruses* 14:921. DOI https://doi.org/10.3390/v14050921 ; full text https://pmc.ncbi.nlm.nih.gov/articles/PMC9145883/ ; BioProject PRJNA667593.
- Bosma et al. 2019, “Identification and quantification of defective virus genomes in high throughput sequencing data using DVG-profiler,” *PLOS ONE* 14:e0216944. DOI https://doi.org/10.1371/journal.pone.0216944 ; full text https://pmc.ncbi.nlm.nih.gov/articles/PMC6524942/ ; BioProject PRJNA525871.
- Olmo-Uceda et al. 2022, “DVGfinder: A Metasearch Tool for Identifying Defective Viral Genomes in RNA-Seq Data,” *Viruses* 14:1114. DOI https://doi.org/10.3390/v14051114 ; full text https://pmc.ncbi.nlm.nih.gov/articles/PMC9144107/ .
- NCBI SRA: https://www.ncbi.nlm.nih.gov/sra/about/ .
