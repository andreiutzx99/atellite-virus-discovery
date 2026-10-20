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

### Outcomes, metrics, and denominators

All metrics are calculated after one frozen, blinded scoring pass. The biological sample/library is the unit for sample-level metrics; reads, contigs, technical lanes, and repeated observations are not independent cases. Group technical duplicates and libraries from the same biological plant before counting independent cases. Report raw numerators and denominators for every metric, plus uncertainty intervals appropriate to the count (exact binomial intervals for sample-level proportions; Poisson intervals for event rates). With very small feasibility sets, show the intervals and state that they are too imprecise for general performance claims.

- **Binary sample-level decision:** before unblinding, define a qualifying satellite candidate using frozen identity, alignment coverage, sample attribution, and duplicate-collapse rules. A sample is pipeline-positive if it has at least one qualifying candidate; otherwise pipeline-negative. Each evaluable biological sample contributes at most one sample-level outcome, regardless of how many candidate contigs it yields.
- **Sample-level sensitivity:** TP/(TP+FN), where the denominator is independently verified, evaluable satellite-positive biological samples. A missed positive is an FN; unevaluable cases are excluded and enumerated separately.
- **Sample-level specificity:** TN/(TN+FP), calculated **only** among independently verified, evaluable satellite-negative biological samples under that predeclared binary decision rule. A negative sample with one or many qualifying satellite candidate calls contributes one sample-level FP, not multiple FPs. Report the number of distinct false candidate calls within each sample separately.
- **Candidate-level precision and recall:** freeze candidate deduplication and one-to-one candidate-to-target matching rules (identity/coverage thresholds, strand/termini policy, sample attribution, and treatment of fragmented/overlapping contigs) before analysis. Precision = matched reported candidate calls / all reported candidate calls. Recall = matched members of a predeclared truth-target set / all targets in that set. This recall is only for that finite, curated truth set; do not imply recall over an undefined universe of possible satellite sequences. Report matched/total counts and uncertainty clustered by biological sample; do not treat contigs as independent replicates.
- **False candidate-call burden:** report unmatched candidate calls separately as (a) total false candidate calls per independently verified negative biological sample and (b) false candidate calls per million input reads for single-end data or per million input read pairs for paired-end data. Give the false-call count and exact sample/read-pair denominator; cluster/count uncertainty by biological sample or study. Do not call FP/(FP+TN) a candidate-level false-positive rate: there is no defined candidate-negative universe. Keep one negative sample-level FP distinct from multiple false candidate calls within that sample.
- **Exact recovery:** count only when an independently established target sequence and its termini are defined. Require full-length 100% identity and coverage only across experimentally supported target boundaries; report near-full-length separately. Published near-complete records PV541158/PV541159 and 551-bp Sanger-confirmed RT-PCR amplicons do not establish exact terminal sequence. Exact terminal recovery for these records is therefore unevaluable unless separate evidence establishes both termini.
- **Specificity strata:** report independently verified clean negatives separately from DVG, ordinary-variation, and mixed-infection challenge samples. Do not combine challenge sets into the clean-negative denominator. Non-reporting, no assembly, or insufficient assay/read sensitivity is not a verified negative.
- **Unevaluable/unavailable:** failed or missing read retrieval/checksum, inadequate quality/depth, uncertain target status, unvalidated sample/run link, absent supported target boundary, or unavailable required dependency yields UNEVALUABLE with a prespecified reason. Publish counts by reason and keep these out of TP/FN/TN/FP denominators. Never recode as a biological negative.

### Single-study feasibility versus general performance

The Phlox set below is a single-study feasibility exercise, not an estimate of broad sensitivity or specificity. Even if Px15, PxBG2, and Px31 pass all gates, two positive plants and one screen-negative plant cannot support general performance claims. Count independent plants, group any technical replicates, and report only within-study descriptive outcomes with exact counts and wide uncertainty intervals. Leave-study-out evaluation and at least one independently curated study with orthogonally verified positives and helper-positive negatives are required before broader performance estimates. A proposed minimal feasibility set is the three named biological samples only, and only after the label/run evidence and read/provenance gates are confirmed; do not add the other six project records by proximity or presumed label.

### Label-strength hierarchy

**Verified positive:** target detected in the named biological sample by HTS and relevant orthogonal assay, with sample-linked sequence confirmation for the assayed region. State that region and assay; do not promote it to full-length/terminal validation without evidence. **Screen-negative (target-specific; detection-limited):** the named sample has no target-associated HTS reads and no expected-size result in a specified relevant assay; this means no detection within that assay/read sensitivity, not absolute biological absence. Report any assay detection limit as unknown if unpublished. **Proposed:** sample/run mapping, validation, or read/provenance gates remain unresolved. Helper status requires its own evidence row and is not inferred from co-detection alone. Keep DVG, ordinary viral variation, mixed infection, and clean satellite-negative classes separate.

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

## Recommended minimal feasibility set and readiness

**Dataset verdict: BLOCKED_FOR_BENCHMARK_EXECUTION; sample/run mapping is resolved.** Primary SRA Experiment metadata directly names the three 2025 paper samples and links each Experiment to a BioSample and Run; no run label is inferred from ordering. The publication supplies satellite-specific RT-PCR/amplicon Sanger evidence for Px15 and PxBG2 and target non-detection for Px31. However, read files have not been fetched or checksummed, source data reuse terms have not been confirmed, library adequacy has not been independently assessed, and the Px31 assay's detection limit is not reported. These gates preclude calling the dataset execution-ready.

After those gates are reviewed, the smallest single-study feasibility set is **SRR32918045 (Px15; target-positive), SRR32918043 (PxBG2; target-positive), and SRR32918044 (Px31; target-specific screen-negative with BRSV helper detected)**. These are three distinct biological plant samples in one study, each with one public paired-end NovaSeq 6000 run. SRA experiment titles, BioSample links, and the paper sample names agree. Keep the uninfected RT-PCR control out of read-based denominators because no SRA library is identified for it. Do not add the six other project runs without independently establishing their sample labels and target evidence.

For this set, evaluate blinded candidate detection under the frozen matching rule and report sample-level counts, candidate counts, and per-million-pair false-call burden. Treat terminal exact recovery as unevaluable: PV541158 and PV541159 are described as nearly complete, while the documented bidirectional Sanger confirmation is for a 551-bp satellite RT-PCR product, not the complete sequence termini. Px31's result is target-specific non-detection within unknown assay/read limits, not proof of absolute absence. Its helper-positive status is separately supported by BRSV HTS and expected-size RT-PCR/Sanger evidence reported for the sample. This feasibility set cannot estimate broad sensitivity/specificity. Require leave-study-out and independent-study validation before any general performance estimate.

No biological FASTQ was downloaded, no biological pipeline execution was performed, and no M1–M20 contract was changed.

## Sources consulted (2026-10-19)

- Motsar et al. 2025, “Molecular Characterization of Tobacco Streak Virus, Beet Ringspot Virus, and Beet Ringspot Virus Satellite RNA from a New Natural Host, *Phlox paniculata*,” *Plants* 14:1619. DOI https://doi.org/10.3390/plants14111619 ; full text https://pmc.ncbi.nlm.nih.gov/articles/PMC12157320/ ; BioProject PRJNA1244124: https://www.ncbi.nlm.nih.gov/bioproject/PRJNA1244124 ; SRA project search: https://www.ncbi.nlm.nih.gov/sra/?term=PRJNA1244124 ; exact records: Px15 SRX28192996 / SAMN47635716 / SRR32918045 (https://www.ncbi.nlm.nih.gov/sra/SRX28192996), Px31 SRX28192997 / SAMN47635717 / SRR32918044 (https://www.ncbi.nlm.nih.gov/sra/SRX28192997), PxBG2 SRX28192998 / SAMN47635718 / SRR32918043 (https://www.ncbi.nlm.nih.gov/sra/SRX28192998). Supplemental Tables S1–S2: https://pmc.ncbi.nlm.nih.gov/articles/instance/12157320/bin/plants-14-01619-s001.zip .
- Miljanić et al. 2022, “Small RNA Sequencing and Multiplex RT-PCR for Diagnostics of Grapevine Viruses and Virus-like Organisms,” *Viruses* 14:921. DOI https://doi.org/10.3390/v14050921 ; full text https://pmc.ncbi.nlm.nih.gov/articles/PMC9145883/ ; BioProject PRJNA667593.
- Bosma et al. 2019, “Identification and quantification of defective virus genomes in high throughput sequencing data using DVG-profiler,” *PLOS ONE* 14:e0216944. DOI https://doi.org/10.1371/journal.pone.0216944 ; full text https://pmc.ncbi.nlm.nih.gov/articles/PMC6524942/ ; BioProject PRJNA525871.
- Olmo-Uceda et al. 2022, “DVGfinder: A Metasearch Tool for Identifying Defective Viral Genomes in RNA-Seq Data,” *Viruses* 14:1114. DOI https://doi.org/10.3390/v14051114 ; full text https://pmc.ncbi.nlm.nih.gov/articles/PMC9144107/ .
- NCBI SRA: https://www.ncbi.nlm.nih.gov/sra/about/ .
