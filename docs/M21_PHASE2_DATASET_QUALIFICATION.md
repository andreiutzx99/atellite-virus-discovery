# M21 Phase 2 — dataset qualification

**Decision:** `BLOCKED_FOR_BENCHMARK_EXECUTION`  
**Verification snapshot:** 2026-10-20  
**Scope:** metadata and publication review only. No biological FASTQ/FASTA payloads were downloaded, no biological reads were inspected or analyzed, and no M4–M15 workflow was run.

## Purpose and method

This report qualifies the three Phlox samples selected in the merged M21 Phase 1 design for possible future, separately approved blinded benchmark use. It does not authorize acquisition or execution. We checked the NCBI SRA RunInfo export for the three specified runs, the corresponding SRA Experiment records, BioSample records, and the cited publication and supplement. Accession crosswalks were compared directly; no identity was inferred from accession order.

The RunInfo endpoint reports public run metadata, spot/base counts, a `size_MB` value, paired layout, platform/model, and `RunHash`/`ReadHash` fields. These metadata fields are not a byte-level validation of any downloaded FASTQ export. We did not request the run download URLs or retrieve archive/read files. `avgLength` is reported as supplied and is not treated as a per-mate read length. The paper reports paired-end 150-nt sequencing; that published method is not an independent measurement of the delivered files.

### Run-level metadata observed

| Sample | Experiment | BioSample | Run | SRA spots / paired spots | Bases | SRA `size_MB` | Layout / platform / model | RunHash / ReadHash metadata |
|---|---|---|---|---:|---:|---:|---|---|
| Px15 | SRX28192996 | SAMN47635716 | SRR32918045 | 19,797,340 / 19,797,340 | 5,296,994,572 | 1,663 | PAIRED / ILLUMINA / Illumina NovaSeq 6000 | Present in RunInfo; see linked record |
| PxBG2 | SRX28192998 | SAMN47635718 | SRR32918043 | 25,111,795 / 25,111,795 | 6,998,822,040 | 2,193 | PAIRED / ILLUMINA / Illumina NovaSeq 6000 | Present in RunInfo; see linked record |
| Px31 | SRX28192997 | SAMN47635717 | SRR32918044 | 17,460,041 / 17,460,041 | 4,669,065,500 | 1,469 | PAIRED / ILLUMINA / Illumina NovaSeq 6000 | Present in RunInfo; see linked record |

The RunInfo rows report `avgLength` values of 267, 278, and 267, respectively. These are archive metadata values, not a claim that each mate has that length. The observed `size_MB` values describe the archive metadata representation, not the size of a future FASTQ conversion. Exact FASTQ file sizes, read lengths, quality, checksums, and successful conversion remain unverified.

## Scientific evidence and sample interpretation

The primary source is Motsar et al. (2025), which reports the Phlox samples and raw-read deposition under PRJNA1244124. Its satellite-specific evidence is distinct from the accession crosswalk:

- **Px15 / SRR32918045 — positive for the assayed region:** the paper reports satellite-associated HTS evidence and an expected-size 551-bp satellite RT-PCR product; bidirectional Sanger sequencing of the amplicon is reported as identical to the corresponding HTS region. GenBank PV541158 is described as nearly complete. The partial amplicon does not independently establish exact full-length termini.
- **PxBG2 / SRR32918043 — positive for the assayed region:** corresponding HTS, expected-size 551-bp satellite RT-PCR, and amplicon Sanger evidence are reported. GenBank PV541159 is described as nearly complete; exact termini are not independently established.
- **Px31 / SRR32918044 — target-specific screen-negative, detection-limited:** the paper reports no satellite-associated reads and no expected-size satellite RT-PCR product. No assay detection limit is reported. This is not proof of biological absence and requires review before this sample can enter a negative-control denominator.

The paper separately reports BRSV detection in all three samples by HTS and virus-specific RT-PCR, with Sanger evidence applying to detected amplicon regions. Co-detection supports a helper-positive candidate-control description; it does not demonstrate helper dependence.

The paper's reported assay outcomes are publication-supported findings. The SRA records independently verify the run/Experiment/BioSample metadata described above; archive metadata does not independently verify the biological assay labels.

## Qualification matrix summary

The row-level evidence and statuses are in [`M21_PHASE2_QUALIFICATION_MATRIX.csv`](M21_PHASE2_QUALIFICATION_MATRIX.csv). `PASS` applies only to the narrow criterion and evidence stated; it is not a dataset-wide approval. FASTQ-byte checks are `NOT_EVALUATED`; unresolved reviews are `PENDING`.

| Sample | Identity | Access / metadata | Scientific status | Control suitability | Overall |
|---|---|---|---|---|---|
| Px15 | PASS — direct Experiment/BioSample/Run crosswalk | PASS — public SRA record and paired Illumina run metadata; byte checks not evaluated | PASS for published satellite-positive assayed region; terminal completeness unresolved | PENDING — technical adequacy, file integrity, terms, and blinding still open | Not qualified for execution |
| PxBG2 | PASS — direct Experiment/BioSample/Run crosswalk | PASS — public SRA record and paired Illumina run metadata; byte checks not evaluated | PASS for published satellite-positive assayed region; terminal completeness unresolved | PENDING — technical adequacy, file integrity, terms, and blinding still open | Not qualified for execution |
| Px31 | PASS — direct Experiment/BioSample/Run crosswalk | PASS — public SRA record and paired Illumina run metadata; byte checks not evaluated | PENDING — screen-negative evidence has unknown detection limit | PENDING — negative-control adequacy, technical adequacy, terms, and blinding still open | Not qualified for execution |

## Outstanding qualification gates

1. **FASTQ and integrity:** current FASTQ availability, exported file sizes, file checksums, successful conversion, and read-level properties have not been checked. RunInfo `RunHash`/`ReadHash` are recorded as archive metadata, not substitutes for checksums of the exact benchmark input files.
2. **Reuse terms:** public access and the article's CC BY 4.0 licence do not establish the archive reads' reuse or redistribution terms. A curator must review applicable SRA/submitter terms and record the result before acquisition or reuse.
3. **Technical adequacy:** depth, read quality, contamination, library suitability, and compatibility with registered stage assumptions cannot be concluded from these metadata alone.
4. **Negative sensitivity:** Px31's target-specific screen result is documented, but the publication does not state an assay limit of detection. Independent review must decide whether it is an adequate evaluable negative for the intended protocol.
5. **Blinding and target exclusion:** a reference-panel exclusion list, truth custodian, opaque-ID mapping, and separation checks are proposed in the accompanying plan but have not been created or operationally tested.
6. **Independent validation:** three samples from one study (two positives, one screen-negative) support, at most, a within-study feasibility question. They cannot support general sensitivity or specificity estimates.

## Limits and non-actions

No biological data files or sequence payloads were downloaded or committed. No assembly, alignment, candidate search, homology search, or biological pipeline execution was performed. No sample identity, novelty, function, pathogenicity, transmission, or helper-dependence claim is made. Existing M1–M20 contracts, fixtures, schemas, and validation rules were not changed.

## Evidence sources

All archive metadata below was retrieved on 2026-10-20:

- NCBI SRA RunInfo export for the three named runs: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra&id=SRR32918045,SRR32918043,SRR32918044&rettype=runinfo&retmode=text
- Px15 Experiment: https://www.ncbi.nlm.nih.gov/sra/SRX28192996 ; BioSample: https://www.ncbi.nlm.nih.gov/biosample/SAMN47635716
- PxBG2 Experiment: https://www.ncbi.nlm.nih.gov/sra/SRX28192998 ; BioSample: https://www.ncbi.nlm.nih.gov/biosample/SAMN47635718
- Px31 Experiment: https://www.ncbi.nlm.nih.gov/sra/SRX28192997 ; BioSample: https://www.ncbi.nlm.nih.gov/biosample/SAMN47635717
- Motsar et al. 2025, *Plants* 14:1619, DOI 10.3390/plants14111619: https://doi.org/10.3390/plants14111619 ; full text: https://pmc.ncbi.nlm.nih.gov/articles/PMC12157320/ ; supplementary Tables S1–S2: https://pmc.ncbi.nlm.nih.gov/articles/instance/12157320/bin/plants-14-01619-s001.zip
- NCBI SRA overview and access guidance: https://www.ncbi.nlm.nih.gov/sra/about/
- NCBI data-use policies: https://www.ncbi.nlm.nih.gov/home/about/policies/

