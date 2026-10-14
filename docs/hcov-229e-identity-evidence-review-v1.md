# HCoV-229E identity and experimental-exposure evidence review v1

**Curation date:** 2026-10-14  
**Scope:** Public metadata and publication only. No sequencing reads were downloaded or inspected; no QC, assembly, alignment, or discovery was run.  
**Status:** Evidence review only. No policy change, run eligibility change, pilot selection, or acquisition authorization.

## Executive summary

All **15/15** run-to-experiment-to-BioSample-to-GEO sample relationships are supported by explicit accession fields from NCBI SRA RunInfo, NCBI BioSample records, GEO sample relations, and ENA's run file report. The three identifiers are not inferred from row order or naming similarity. No accession mapping remains unresolved.

The 12 runs labeled in GEO/BioSample as HCoV-229E infected for 6, 24, 48, or 72 hours have **supported study-reported exposure** when the exact sample mapping is followed to the publication. This is category B below, not archive-declared typed virus identity and not sequence-confirmed presence. The three 0-hour records are labeled **Untreated** in GEO and BioSample; the paper describes RNA extraction at 0 hours post-infection and compares the transcriptome with uninfected cells. The available sources do not establish whether those three cells were exposed to inoculum before collection. They remain unresolved baseline candidates, not mock controls and not supported virus-exposure samples.

All 15 archive records name *Homo sapiens* and give host/cell/treatment attributes, but none supplies a HCoV-229E value in an accepted `public-virus-v1` identity field. Thus the archive-declared identity status is **INSUFFICIENT for all 15**, and all 15 remain **HELD** under the unchanged policy. Sequence-confirmed presence is **NOT_ASSESSED for all 15**. The FASTQ manifests are listed with sizes and MD5s; all 15 complete runs fall below the existing 1,000,000,000-byte limit. That metadata does not authorize retrieval.

A separate `study_reported_experimental_exposure` evidence category is scientifically defensible for explicitly accession-mapped, source-cited, human-reviewed exploratory reporting, provided it is formally added to policy and never conflated with archive identity, sequence confirmation, biological findings, or acquisition eligibility. **Retain the current hold unless and until that formal policy review and independent validation are completed.**

## Current identity gate

The implementation is `satellite_discovery/public_virus.py::assess_identity`; its versioned terms and accepted keys are in `satellite_discovery/public_virus_policy.json`. For HCoV-229E, the accepted sample-level keys are exactly `virus`, `virus species`, `infecting virus`, `viral species`, and `pathogen`. A virus name in the sample-organism field can also support technical review. Matching evidence produces `accepted_for_technical_review`, not biological confirmation. No matching evidence produces `insufficient` with reason `sample_level_virus_identity_missing`. Conflicts, excluded pathogen terms, mixed/modified language, and ambiguous typed pathogen values have separate blocking outcomes.

| Evidence concept | What these records say | Current policy meaning |
|---|---|---|
| Host organism | SRA and each BioSample name *Homo sapiens*. | Host taxonomy is not viral identity. |
| Viral organism / isolate identity | No accepted virus-identity field on the reviewed BioSample records. The article names HCoV-229E VR740 as the study virus, but that is not an accepted archive sample-identity attribute. | Insufficient for the current identity gate. |
| Experimental exposure | The exact linked BioSample/GEO treatment for 12 samples says “Infected with HCoV-229E virus for [6/24/48/72] hours”; publication methods describe the same experimental design. | Study-reported exposure only; it does not satisfy the current archive identity gate. |
| Sequence-confirmed presence | Reads were not retrieved or examined in this review. | Not assessed; no sample is sequence-confirmed. |

GEO, paper descriptions, titles, treatment labels, and study-level assertions are relevant contextual evidence but cannot silently be reinterpreted as the accepted archive identity fields. The existing exact-run fixture `tests/fixtures/public_virus_metadata/SRR12424243.json` records human organism/host, no accepted virus identity attribute, and expected `insufficient` / `held_for_identity_review`. The policy file, keys, size threshold, preflight, and acquisition permissions are unchanged in this PR.

## Accession crosswalk and sample-level treatment

For each row, NCBI RunInfo explicitly supplies `Run`, `Experiment`, `BioSample`, `SampleName` (the GSM), `BioProject`, and `SRAStudy`. The BioSample record independently lists its BioSample accession, SRA sample accession and GEO accession; GEO `!Sample_relation` independently points to that BioSample and the matching SRX; ENA independently supplies run, experiment, BioSample secondary/sample IDs, study and FASTQ manifest. The corresponding GEO matrix treatment field and BioSample `treatment` attribute are the reported condition evidence. The full run-level structured record and evidence field names are in the JSON companion.

| Run | Experiment | BioSample | GEO sample | GEO / BioSample treatment | Sample interpretation | FASTQ bytes |
|---|---|---|---|---|---|---:|
| SRR12424243 | SRX8920116 | SAMN15776103 | GSM4718629 | Untreated | 0 h; inoculation status unresolved | 728,420,078 |
| SRR12424244 | SRX8920117 | SAMN15776102 | GSM4718630 | Untreated | 0 h; inoculation status unresolved | 707,122,524 |
| SRR12424245 | SRX8920118 | SAMN15776101 | GSM4718631 | Untreated | 0 h; inoculation status unresolved | 738,657,482 |
| SRR12424246 | SRX8920119 | SAMN15776082 | GSM4718632 | Infected with HCoV-229E virus for 6 hours | Reported infected | 716,754,201 |
| SRR12424247 | SRX8920120 | SAMN15776081 | GSM4718633 | Infected with HCoV-229E virus for 6 hours | Reported infected | 812,687,023 |
| SRR12424248 | SRX8920121 | SAMN15776080 | GSM4718634 | Infected with HCoV-229E virus for 6 hours | Reported infected | 690,690,938 |
| SRR12424249 | SRX8920122 | SAMN15776100 | GSM4718635 | Infected with HCoV-229E virus for 24 hours | Reported infected | 719,954,581 |
| SRR12424250 | SRX8920123 | SAMN15776099 | GSM4718636 | Infected with HCoV-229E virus for 24 hours | Reported infected | 680,887,913 |
| SRR12424251 | SRX8920124 | SAMN15776083 | GSM4718637 | Infected with HCoV-229E virus for 24 hours | Reported infected | 688,743,343 |
| SRR12424252 | SRX8920125 | SAMN15776079 | GSM4718638 | Infected with HCoV-229E virus for 48 hours | Reported infected | 789,406,350 |
| SRR12424253 | SRX8920126 | SAMN15776078 | GSM4718639 | Infected with HCoV-229E virus for 48 hours | Reported infected | 662,991,065 |
| SRR12424254 | SRX8920127 | SAMN15776077 | GSM4718640 | Infected with HCoV-229E virus for 48 hours | Reported infected | 701,721,556 |
| SRR12424255 | SRX8920128 | SAMN15776076 | GSM4718641 | Infected with HCoV-229E virus for 72 hours | Reported infected | 665,176,079 |
| SRR12424256 | SRX8920129 | SAMN15776075 | GSM4718642 | Infected with HCoV-229E virus for 72 hours | Reported infected | 711,794,311 |
| SRR12424257 | SRX8920130 | SAMN15776074 | GSM4718643 | Infected with HCoV-229E virus for 72 hours | Reported infected | 751,000,032 |

The table shows **15 verified accession relationships**, **12 supported study-reported exposures**, **3 unresolved 0-hour samples**, **3 baseline candidates**, **0 confirmed mock controls**, and **0 sequence-confirmed samples**. All are single-end RNA-Seq, TRANSCRIPTOMIC, cDNA-selected runs in ENA, with listed FASTQ byte counts and MD5s. “cDNA” does not establish poly-A selection or rRNA depletion. The 0-hour labels are not assigned a mock condition: GEO/BioSample says “Untreated,” while the article's time-course methods say extraction at 0 hours post-infection. Clarification from the authors or a contemporaneous protocol is needed to resolve collection relative to inoculum.

## Publication evidence, replicates, and limitations

The paper's Methods report HCoV-229E VR740, MRC-5 cells and MOI 0.01; RNA extraction at 0, 6, 24, 48 and 72 hours post-infection; and “three biological repeats” at each time point. GEO titles use `MRC5_<time>_R1/R2/R3`. The paper also describes qPCR-based viral-titer estimates from infected cells and culture supernatants. This supports the study-level design and the 12 sample-linked 6–72-hour exposure labels, but it does not make those viral-titer measurements run-specific sequencing evidence.

“Biological repeats” and `R1`–`R3` are reported labels, not proof that the samples came from independently prepared infections or independent biological units. These are cultured MRC-5 cells, not independent human donors. The available source set does not document separate culture preparations, infection batches, cell passages, or the experimental randomization needed to establish independence. Independence therefore remains **UNKNOWN** for all groups.

No run has a missing or contradictory accession link in the reviewed sources. The main unresolved sample interpretation is the 0-hour exposure status; replicate independence is also unresolved. Archive metadata may change or be withdrawn after this dated review. Local SHA-256 values are recorded to detect later byte differences only; they do not authenticate the origin or truth of source content.

## Evidence classification

Statuses use `SUPPORTED`, `INSUFFICIENT`, `CONFLICTED`, and `NOT_ASSESSED`; they are evidence labels, not numeric confidence scores.

| Category | Question | Findings |
|---|---|---|
| A. `ARCHIVE_DECLARED_VIRUS_IDENTITY` | Does the exact archive sample record identify HCoV-229E in a current accepted field? | `INSUFFICIENT` for 15/15. Host organism is human; treatment and cell line attributes do not use a current accepted virus identity key. |
| B. `STUDY_REPORTED_VIRUS_EXPOSURE` | Does an accession-linked study record report experimental exposure? | `SUPPORTED` for 12/15 samples at 6–72 h. `INSUFFICIENT` for the three conflicting/ambiguous-in-time 0-hour untreated records. |
| C. `SEQUENCE_CONFIRMED_VIRUS_PRESENCE` | Has sequence from this exact sample been assessed for virus? | `NOT_ASSESSED` for 15/15. No reads were acquired or analyzed. |

Category B can be strong as an account of what the study says while remaining insufficient for A and unknown for C. The separate categories prevent study-report evidence from being misrepresented as archive identity or detected infection.

## Current policy versus a possible separately reviewed exposure category

| Decision point | Current `public-virus-v1` | Possible future `study_reported_experimental_exposure` |
|---|---|---|
| Evidence allowed | Virus named in sample organism or exact accepted typed identity attributes. | Exact accession mapping plus sample-specific GEO/BioSample condition and a traceable primary protocol/publication. |
| GEO/paper treatment labels | Context only; do not satisfy identity gate. | Can support category B, clearly labelled as reported exposure. |
| Human host taxonomy | Not viral identity. | Still not viral identity. |
| Sequence presence | Not implied by metadata. | Still separate; only sequence analysis could assess it. |
| Controls | No automatic control designation from a study label. | Untreated, mock, and infected conditions separate; unclear 0-hour samples remain unresolved. |
| Review | Existing profile validation and human review safeguards. | Formal policy amendment; two independent reviewers; resolve discrepancies; retain source/version/date and evidence fields; changes trigger reassessment. |
| Downstream use | A current hold blocks pilot readiness. | Exploratory summaries only, with uncertainty visible; not confirmation or acquisition eligibility by itself. |

The extension is scientifically defensible **only as an evidence vocabulary and explicitly human-reviewed exploratory class**. Applying it to an intake or allowing it to change a gate requires a formal policy change. A policy should specify exact sources/fields, accession-by-accession reconciliation, source change/withdrawal handling, dual-review decisions, run duplication, control semantics, and downstream labels. No such policy is implemented here.

## Negative and adversarial cases

| Case | Required evidence outcome |
|---|---|
| GEO says infected but links to a different SRA sample | `CONFLICTED`; do not transfer the exposure annotation to the run. |
| Study says HCoV-229E but no sample-level accession mapping exists | Category B `INSUFFICIENT`; study-level statement alone cannot label a run. |
| BioSample organism is *Homo sapiens* | Host only; category A remains `INSUFFICIENT`. |
| Exact mapped sample is explicitly mock infected | Record mock as a reported condition, not infected exposure or sequence evidence. |
| 0-hour baseline | Here GEO/BioSample say “Untreated” while the paper uses “0 hours post-infection”; role stays unresolved, not mock and not supported exposure. |
| Conflicting treatment annotations | `CONFLICTED`, preserve both original statements, require human resolution. |
| No detectable virus in a future assay | Record that assay result and detection limits; do not reinterpret the study treatment as proof of presence. |
| Two runs from the same sample | Preserve both run accessions but one biological-unit identity; do not count them as independent replicates. |
| Archive annotation changed or withdrawn | Preserve dated evidence snapshot and source URL/hash; mark stale/conflicted and re-review, never silently retain a previous status. |

None of these cases can automatically become sequence-confirmed infection.

## Recommendation and answers

1. **Can each run be mapped to a GEO sample?** Yes, 15/15 supported by independently matching explicit accession relationships. No mappings remain unresolved.
2. **Which samples have supported reported HCoV-229E exposure?** GSM4718632–GSM4718643 (12 samples; runs SRR12424246–SRR12424257) at 6, 24, 48, or 72 hours. This is reported exposure, not archive-declared identity or sequence confirmation.
3. **Which are baseline/control samples?** GSM4718629–GSM4718631 are 0-hour samples labelled “Untreated”; they are baseline candidates. No sample is established as a mock-infected control. The possible immediate post-inoculation interpretation of 0 h remains unresolved.
4. **What is missing?** Accepted archive sample-level virus identity; sequence inspection; exact meaning of the 0-hour collection relative to inoculation; evidence that replicate labels represent independent preparations; and an independent second-curator review.
5. **Is a distinct study-reported-exposure category defensible?** Yes, as an explicitly separate, source-linked, human-reviewed exploratory evidence category. It must not claim archive identity, sequence-confirmed presence, or biological confirmation.
6. **Would adoption require a formal policy change?** Yes. This review does not implement one.
7. **Should GSE155986 remain HELD under current policy?** Yes; all 15 remain held and no eligibility changes are made.
8. **What review before considering a pilot?** Independent verification of every source relation and condition; resolution of 0-hour semantics; replicate-unit audit; formal policy approval; and then re-run the existing technical and acquisition preflight without bypassing its unchanged identity checks.

No pilot, control, backup, or acquisition authorization is selected. Acquisition remains disabled.

## Reproducibility and sources

Machine-readable companion: [`hcov-229e-identity-evidence-review-v1.json`](hcov-229e-identity-evidence-review-v1.json). It contains 15 run records, accession links, evidence fields, normalized exposure categories, FASTQ manifest metadata, policy outcomes, source URLs, and bounded source-response SHA-256 values. Hashes are not signatures or authenticity proof. The JSON is a dated curation record, not an archive snapshot with authority over live records.

- GEO GSE155986 series and sample records: <https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE155986>
- GEO series matrix: <https://ftp.ncbi.nlm.nih.gov/geo/series/GSE155nnn/GSE155986/matrix/GSE155986_series_matrix.txt.gz>
- NCBI SRA study SRP276927 and RunInfo: <https://www.ncbi.nlm.nih.gov/sra?term=SRP276927> and <https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo?acc=SRP276927>
- NCBI BioProject PRJNA656274: <https://www.ncbi.nlm.nih.gov/bioproject/PRJNA656274>
- NCBI BioSample records SAMN15776103, SAMN15776102, SAMN15776101, SAMN15776082, SAMN15776081, SAMN15776080, SAMN15776100, SAMN15776099, SAMN15776083, SAMN15776079, SAMN15776078, SAMN15776077, SAMN15776076, SAMN15776075, SAMN15776074; e.g. <https://www.ncbi.nlm.nih.gov/biosample/SAMN15776103>
- ENA read-run report, including per-run file path, bytes and MD5: <https://www.ebi.ac.uk/ena/portal/api/filereport?accession=PRJNA656274&result=read_run&fields=run_accession,experiment_accession,sample_accession,study_accession,secondary_sample_accession,scientific_name,library_strategy,library_source,library_selection,library_layout,fastq_ftp,fastq_bytes,fastq_md5&format=tsv>
- Friedman N. et al. (2021), “Transcriptomic profiling and genomic mutational analysis of Human coronavirus (HCoV)-229E-infected human cells,” PLOS ONE 16(2):e0247128, <https://doi.org/10.1371/journal.pone.0247128>; open full text: <https://pmc.ncbi.nlm.nih.gov/articles/PMC7906355/>

---

**HCOV-229E IDENTITY EVIDENCE REVIEW: READY FOR INDEPENDENT SCIENTIFIC REVIEW**
