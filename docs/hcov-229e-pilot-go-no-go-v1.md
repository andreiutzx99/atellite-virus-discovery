# HCoV-229E exploratory pilot: scientific go/no-go

**Evidence snapshot:** 2026-10-14  
**Dataset:** GSE155986 / PRJNA656274 / SRP276927  
**Decision:** **SCIENTIFIC DECISION: CONDITIONAL GO**

This is an evidence-based recommendation, not completed human approval. It supports consideration of **one limited technical pipeline pilot**, not biological discovery, infection validation, or acquisition. All 15 runs remain **HELD** under unchanged `public-virus-v1`; acquisition remains disabled.

## Executive decision

A narrowly scoped amendment is scientifically defensible for exploratory technical intake of the 12 runs with explicit 6-, 24-, 48-, or 72-hour HCoV-229E treatment annotations. Current GEO, BioSample, SRA RunInfo, ENA, and primary-publication records form consistent accession chains for all 15 deposited runs. ENA currently reports one single-end FASTQ manifest for each run, and each individual file is under the existing 1,000,000,000-byte cap.

The recommendation is conditional because the current strict identity policy still holds all runs; metadata does not establish sequence-confirmed viral presence; the actual library selection chemistry is unspecified; and no run-level read quality or viral content has been inspected. The three 0-hour samples remain ambiguous, there is no confirmed mock control, and independent preparation of the reported biological repeats is not described sufficiently.

Separate decisions:

| Decision | Result |
|---|---|
| Scientific case for a one-run technical pilot | **CONDITIONAL GO** |
| Policy change | **Not approved; human review required** |
| Acquisition authorization | **NO; not authorized** |
| Controlled biological discovery study | **NO** |

## Independent source refresh

Public metadata were fetched on **2026-10-14** from:

- [GEO series GSE155986](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE155986&targ=self&form=text&view=full), plus all 15 current GSM sample records.
- All 15 linked [NCBI BioSample](https://www.ncbi.nlm.nih.gov/biosample/SAMN15776103) records.
- [NCBI SRA RunInfo for SRP276927](https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo?acc=SRP276927).
- [ENA run/file report for SRP276927](https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRP276927&result=read_run&fields=study_accession,run_accession,experiment_accession,sample_accession,secondary_sample_accession,library_name,library_layout,library_source,library_selection,instrument_platform,instrument_model,fastq_ftp,fastq_bytes,fastq_md5&format=tsv).
- The [original PLOS ONE paper](https://doi.org/10.1371/journal.pone.0247128), published 2021-02-25.

All 15 Run → Experiment → BioSample → GEO sample chains match across the refreshed records. GEO samples report a last-update date of 2022-10-25; ENA run rows report `last_updated=2021-03-04`. No changed run mapping, file size, or FASTQ MD5 was found compared with the prior review. These source dates do not establish continuous immutability.

The deposited series contains 15 runs from 0 through 72 hours. The paper methods mention RNA collection through 96 hours, but no 96-hour run is present in the current GSE/SRP run set; the pilot scope does not include one.

### Sample evidence and the 0-hour ambiguity

The 12 samples at 6, 24, 48, and 72 hours have GEO and BioSample treatment fields explicitly stating infection with HCoV-229E for the stated time. The paper describes MRC-5 cells infected with HCoV-229E at MOI 0.01 and uses the same time course.

The three 0-hour records are titled `MRC5_0_R1/R2/R3` and annotated `Untreated`. Their GEO treatment protocol is generic infection wording, while the series design and paper describe samples at 0 hours post-infection and compare transcriptomic results with uninfected cells. These statements do **not** resolve whether the deposited 0-hour material was collected before inoculation, immediately after inoculation, or under another baseline definition. Do not classify these runs as mock, infected, or uninfected.

The paper says “three biological repeats” were tested at each time point. It does not provide sufficient detail about separate culture preparation or independent infection events to establish biological independence for this pilot review. Replicate labels and separate accession records alone do not prove independence.

## Library suitability

Current GEO/SRA/ENA metadata report `RNA-Seq`, transcriptomic source, `cDNA` selection, single-end layout, and Illumina HiSeq 2500. The paper reports total RNA with RIN >8, preparation using Illumina TruSeq RNA Library Preparation Kit v2, and HiSeq 2500 sequencing. It does not explicitly establish whether these libraries used poly-A selection, rRNA depletion, or another enrichment step. The archive’s controlled value `cDNA` does not resolve that.

This is reasonably suitable for a **pipeline-processing** pilot: the material is host-cell transcriptomic RNA-seq from a study reporting HCoV-229E infection, with a public single-end run manifest. The original paper reports intracellular viral propagation peaking at 24 hours by qPCR, but that is not a measurement of viral reads in the nominated run. Unknown enrichment chemistry, single-end reads, and the absence of read-level analysis limit any expectation of viral-read recovery. The pilot could test file handling, QC, reference mapping, and pipeline behavior; it cannot establish infection, viral presence, or a biological finding.

## Policy decision matrix

| Question | Answer | Justification |
|---|---|---|
| Accession mapping sufficiently supported? | **YES** | 15/15 current Run/Experiment/BioSample/GEO chains agree. |
| Exposure sufficiently documented? | **CONDITIONAL** | Explicit for the 12 samples at 6–72 hours; unresolved for the 0-hour samples. |
| Archive-declared identity sufficient under current policy? | **NO** | Host material is reported as human MRC-5; the existing virus identity gate remains insufficient and HELD. |
| Narrow exposure-based amendment defensible? | **YES, narrowly** | It can support a reviewed technical-intake exception for exact GSE155986 run scope, but not viral identity or sequence confirmation. |
| Library suitable for technical pilot? | **CONDITIONAL** | RNA-seq is usable for pipeline exercise; selection chemistry and viral-read recovery are unknown. |
| Nominated run under 1 GB? | **YES, by current metadata** | ENA lists one 680,887,913-byte file; a future preflight must recheck it. |
| Appropriate biological controls established? | **NO** | No confirmed mock run; 0-hour samples are ambiguous. |
| Biological independence established? | **NO / UNKNOWN** | The paper labels biological repeats but does not describe preparation well enough to establish independence. |
| Single-run technical pilot justifiable? | **CONDITIONAL** | It needs a reviewed policy change and separate acquisition authorization; it cannot make discovery claims. |
| Controlled biological discovery study justifiable now? | **NO** | Controls and established independent biological replication are lacking. |
| Acquisition currently authorized? | **NO** | No eligibility policy change or operator authorization has been approved. |
| What approval remains? | **PENDING** | Owner decision and independent scientific review of the narrow rule, then separate operator approval and fresh acquisition preflight. |

## Provisional run nomination

**SRR12424250** is the provisional choice, not an approval to download:

| Field | Current record |
|---|---|
| SRR | `SRR12424250` |
| SRX | `SRX8920123` |
| BioSample | `SAMN15776099` |
| GEO sample | `GSM4718636` |
| Reported condition | HCoV-229E infection, 24 hours |
| Layout | Single-end |
| FASTQ | [SRR12424250.fastq.gz](https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR124/050/SRR12424250/SRR12424250.fastq.gz) |
| Compressed bytes | `680887913` |
| ENA MD5 | `9ac379cab68b8b5e2862ec167e95d3c9` |

The 24-hour timepoint is useful because the paper reports peak intracellular viral propagation at 24 hours by qPCR. Among the three 24-hour entries, this run has the smallest current manifest. Neither observation predicts the viral-read yield of this specific run. The size and MD5 are archive metadata only; the bytes and digest have not been verified by downloading the file.

## Minimum PR #66

If the owner and independent scientific reviewer accept this recommendation, PR #66 should implement one small, versioned, opt-in rule for explicitly approved GSE155986 runs only:

1. Require a recorded human scientific approval decision before activating the exact run scope.
2. Keep exposure evidence distinct from archive identity and sequence-confirmed presence.
3. Bind approval to exact GEO/SRA/BioSample/ENA mappings and sample-level exposure evidence.
4. Retain the current 1 GB per-run limit, full manifest, checksum, provenance, storage, and preflight safeguards.
5. Leave every other dataset on strict `public-virus-v1`.
6. Keep acquisition disabled until a separate operator confirmation and fresh acquisition preflight.

Do not build a general policy framework or expand the permitted virus/study scope.

## Approval and safety status

- No reviewer identities or approvals are claimed; any human review remains pending.
- No policy amendment has been activated.
- All current GSE155986 runs remain **HELD**.
- Acquisition is disabled and has not been authorized.
- No FASTQ or other sequencing reads were downloaded or inspected; no QC, assembly, alignment, or discovery analysis was run.
- Sequence-confirmed viral presence remains **NOT ASSESSED**.

Machine-readable source snapshot and all 15 run manifests: [`hcov-229e-pilot-go-no-go-v1.json`](hcov-229e-pilot-go-no-go-v1.json).
