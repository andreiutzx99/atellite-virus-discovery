# HCoV-229E scientific readiness and evidence review

**Review date:** 2026-10-15  
**Evidence scope:** metadata and publication records already captured on 2026-10-14; no new archive retrieval was needed for this review.  
**Scope:** GSE155986 / GSM4718636 / PRJNA656274 / SRP276927 / SAMN15776099 / SRX8920123 / SRR12424250 / DOI 10.1371/journal.pone.0247128.

## Executive assessment

The exact accession chain for the proposed 24-hour run is well supported: NCBI SRA RunInfo, GEO, BioSample, and ENA identify SRR12424250 / SRX8920123 / SAMN15776099 / GSM4718636 within SRP276927 / PRJNA656274 / GSE155986. GEO and BioSample report HCoV-229E treatment for 24 hours; the publication reports an HCoV-229E MRC-5 infection experiment. These are archive-declared relationships and study-reported exposure, not evidence that viral sequence is present in this run.

The highest-priority interpretation blockers are: (1) the unresolved 0-hour status and absence of a confirmed infection-matched mock in the deposited series; (2) unresolved meaning and coverage of a 96-hour timepoint described in the GEO sample protocol and article but absent from the 15-sample series; (3) no evidence that the “three biological repeats” were separate infection/culture units; (4) no exact ATCC VR-740 stock lot, passage, or sequence link; and (5) unspecified library enrichment beyond the `cDNA` selection field and kit name. The first three restrict control-based, time-course, or replicated biological conclusions, but do not by themselves prevent a limited single-run technical feasibility test.

The prior **CONDITIONAL GO** in `hcov-229e-pilot-go-no-go-v1.md` is a scientific recommendation for consideration of a limited technical pilot, not a completed approval, policy change, eligibility decision, or acquisition authorization. The current identity policy still yields **HELD**. The separate technical readiness decision remains **NO-GO for real-read analysis**. Sequence confirmation remains **NOT_ASSESSED**; no reference is activated; acquisition is disabled.

## Evidence categories and confidence boundaries

| Claim | Evidence class | Assessment | What it establishes |
|---|---|---|---|
| SRR12424250 maps to SRX8920123, SAMN15776099, GSM4718636, GSE155986, SRP276927 and PRJNA656274 | Explicit archive metadata relationships | **SUPPORTED** | The records identify the same deposited run/sample at retrieval time. |
| GSM4718636 / SAMN15776099 reports HCoV-229E treatment for 24 hours | Sample-level archive annotation | **SUPPORTED as reported exposure** | What GEO/BioSample say about the sample; not sequence-confirmed infection. |
| Study used HCoV-229E VR-740 in MRC-5 cells at MOI 0.01 | Publication-reported experimental information | **SUPPORTED at study level** | The paper’s described protocol; not proof of the exact run’s stock, lot, passage, or viral content. |
| HCoV-229E sequence is present in SRR12424250 | Sequence-confirmed information | **NOT_ASSESSED** | Reads were not downloaded or analyzed. |
| 0-hour samples are suitable mock controls | Conflicting/incomplete records | **UNRESOLVED** | GEO/BioSample label them “Untreated”; series and paper describe a 0-hour post-infection point. Do not relabel them mock, infected, or uninfected. |
| 96-hour sample group is represented in GSE155986/SRP276927 | Conflicting series and protocol descriptions | **UNRESOLVED; no deposited 96-hour sample identified** | GEO sample extraction protocol and the article mention 96 hours, while GEO series design lists 0/6/24/48/72 and its 15 accessions comprise three samples at those five times. |
| Three reported repeats are independent biological infections | Study wording and replicate labels only | **UNKNOWN** | “Three biological repeats” and R1/R2/R3 do not identify separate infection events or culture preparations. |
| `cDNA` means poly-A selection or rRNA depletion | Archive field and kit name | **NOT_ESTABLISHED** | Neither the field nor “TruSeq RNA Library Preparation Kit v2” documents the actual enrichment/depletion choice. |

No repeated statement derived from the same GEO record or study is counted as independent biological corroboration. Agreement between GEO, BioSample, SRA and ENA strengthens the accession crosswalk, not sequence confirmation.

## Exact sample and archive evidence

The run-level evidence captured 2026-10-14 identifies:

| Entity | Accession | Evidence |
|---|---|---|
| GEO series | GSE155986 | Includes GSM4718636; links to PRJNA656274 and SRP276927. |
| GEO sample | GSM4718636 | Title `MRC5_24_R2`; cell line MRC-5; treatment “Infected with HCoV-229E virus for 24 hours”; links to SAMN15776099 and SRX8920123. |
| BioProject / SRA study | PRJNA656274 / SRP276927 | Series and run context. |
| SRA experiment | SRX8920123 | Links the run and sample. |
| BioSample / SRA sample | SAMN15776099 / SRS7176671 | Names *Homo sapiens*, MRC-5 and 24-hour HCoV-229E treatment; links to GSM4718636 and PRJNA656274. |
| SRA run | SRR12424250 | RunInfo `SampleName=GSM4718636`; 24,902,615 spots; archive statistics report average read length 51 bases. |
| ENA run record | SRR12424250 | Agrees on experiment, BioSample and study; one single-end FASTQ manifest, 680,887,913 compressed bytes, MD5 `9ac379cab68b8b5e2862ec167e95d3c9`. |

These bytes and MD5 are archive metadata only; the FASTQ has not been downloaded or verified. Its reported size is below the existing 1,000,000,000-byte per-run threshold, but that is not a fresh preflight, eligibility, or permission to acquire.

The current `public-virus-v1` identity rule accepts exact sample-organism or specified typed virus-identity attributes. The reviewed BioSample names the host as human; HCoV-229E appears in the treatment field, not an accepted identity field. Therefore the exact run remains **HELD** under the unchanged policy. The distinct study-reported exposure assessment does not override that gate.

## Experimental provenance and unresolved discrepancies

### 0-hour samples and controls

The three GEO/BioSample records GSM4718629–GSM4718631 are titled `MRC5_0_R1/R2/R3` and annotated `Untreated`. The GEO series design and publication describe RNA collection at 0 hours post-infection and comparison with uninfected cells. The available records do not establish whether inoculum had been added before collection, what “Untreated” means operationally, or whether any deposited sample was a mock-inoculated control. Treat these as unresolved baseline candidates, not negative controls.

### 96-hour discrepancy

The captured GEO series record’s `!Series_overall_design` lists RNA extraction at 0, 6, 24, 48 and 72 hours; the series contains 15 samples, three at each of those five times. The GEO sample-level `!Sample_extract_protocol_ch1` for GSM4718636 lists 0, 6, 24, 48, 72 **and 96** hours. The article’s Methods likewise states extraction at 0, 6, 24, 48, 72 and 96 hours; its Results mention reduced MRC-5 cell counts at 96 HPI and transcriptomic changes through 48–72 HPI. No 96-hour GSM/SRX/SRR appears in the deposited series reviewed here.

The records do not explain whether the 96-hour material was collected but not deposited, used for another assay, or retained in a protocol template. Do not infer that a missing run is an archive error or that 96-hour RNA-seq exists. Resolve against the authors’ sample manifest or contemporaneous laboratory records before making a time-course comparison.

### Cells, stock, and replicates

GEO/BioSample report MRC-5, a human diploid lung fibroblast cell line. The paper reports HCoV-229E VR-740, MRC-5, MOI 0.01 and three “biological repeats” per timepoint. No reviewed source links a specific ATCC VR-740 lot/passage or stock sequence to SRR12424250. No source establishes cell passage, authentication, mycoplasma status, separate culture preparations, independent infection events, or randomization for the R1/R2/R3 labels. These remain unknown; the repeats are not treated as independent biological units for inference.

### Library and read characteristics

Archive fields describe RNA-Seq, transcriptomic source, `cDNA` selection, single-end layout and Illumina HiSeq 2500. The sample protocol and article report total RNA with RIN >8 and Illumina TruSeq RNA Library Preparation Kit v2. They do not say whether poly-A selection, rRNA depletion, or another enrichment was used. The SRA average read length of 51 bases is a metadata statistic, not a read-level quality assessment. No read content, adapter contamination, viral fraction, host mapping, or run QC has been measured.

## Reference-panel readiness

The existing manifest is a **proposed metadata-only panel**, marked `NOT_ACTIVATED`; it contains no downloaded sequence artifacts. Do not fill any null SHA-256 value from accession metadata. “Checksum null” means the exact artifact was not retrieved and hashed.

| Reference / role | Version and provenance | Artifact identity, terms, and status |
|---|---|---|
| Human host assembly | GRCh38.p14, GCF_000001405.40; NCBI assembly report records chromosome accession.version and lengths. | Multi-record bundle; not an MRC-5 genotype. No exact FASTA artifact hash; review terms for the exact bundle before any separately authorized use. |
| Human annotation / transcripts | GCF_000001405.40-RS_2025_08 | Versioned collection, not one accession. Exact membership and artifact hashes unavailable until approved retrieval. |
| Mitochondrial comparator | NC_012920.1, 16,569 nt | Reference record, not sample-specific mitochondrial sequence. SHA-256 null; artifact and reuse terms unreviewed. |
| Human rRNA | Intended from pinned assembly annotation | Standalone nuclear rRNA accession/version set unresolved. Do not claim complete coverage or substitute an unpinned record. |
| HCoV-229E comparison | NC_002645.1, clone inf-1, 27,317 nt | Valid comparison reference only; **not verified as the experimental stock**. SHA-256 null; exact-artifact terms need review. |
| Optional HCoV-229E diversity comparator | MF542265.1, 229E/Haiti-1/2016, 27,271 nt | Optional comparator only, not the helper stock. SHA-256 null; terms need review. |
| Technical/vector screening | UniVec Core; Illumina adapter-core sequence; optional PhiX174 NC_001422.1 | UniVec build is unpinned and not comprehensive; adapter sequence is not kit-confirmed; PhiX reference does not establish use or lot identity. None is activated; exact build/lot/hash and reuse review are pending. |

Source record identifiers, exact URLs, review retrieval dates, statuses, and reference details are in `hcov229e-scientific-readiness-v1.json`. No reference FASTA, transcript package, adapter database, or FASTQ was retrieved in this review.

## Readiness decision matrix

In this matrix, **technical pilot** means a limited feasibility test of the selected SRR12424250 run, considered only after separate scientific, policy, operator, and acquisition authorization. A `false` technical-pilot blocker does not grant that authorization or permit real-read analysis now. The overall decision remains **NO-GO for real-read analysis**. Biological-interpretation blockers identify conclusions that remain unsupported even if a technical feasibility test is separately authorized.

| Issue | Available evidence / strength | Unknown and consequence | Blocks technical pilot? | Blocks biological interpretation? | Next action and responsible reviewer |
|---|---|---|---|---|---|
| Accession chain | Explicit matching SRA, GEO, BioSample and ENA fields; strong for record linkage. | Records can change; linkage does not prove sample contents. | No current mismatch; fresh metadata check required before any future action. | No; mapping alone does not establish biological identity or viral presence. | Recheck exact relationships; archive curator or data custodian. |
| Exposure vs identity | GEO/BioSample report 24-h HCoV-229E treatment; paper reports study infection. | No accepted archive virus-identity field; no sequence confirmation. | Current public-virus policy holds this run. | Yes, for claims of infection in the actual sequenced material. | Preserve separate evidence categories; policy owner and independent scientist. |
| 0-hour control role | “Untreated” labels and 0-h post-infection descriptions conflict in meaning. | Inoculation/collection ordering and mock status unknown. | No, not for a limited single-run feasibility test; still blocks assigning the samples as matched negative controls. | Yes, for infection-versus-control contrasts and claims treating 0-hour samples as confirmed mock/uninfected controls. | Obtain sample sheet/protocol clarification; study author or archive curator. |
| 96-hour coverage | Sample protocol/article mention 96 h; GEO series design and deposited sample set omit it. | Whether 96-h material was sequenced/deposited and why it is absent. | No, not for a limited feasibility test on the selected 24-hour run. | Yes, for claims of a complete 0–96 h sequencing time course or 96-hour results. | Reconcile sample manifest with authors and archive curator. |
| Biological replication | Paper says three biological repeats; GEO uses R1/R2/R3. | Separate culture/infection unit, passage and batch independence. | No, not for a limited single-run feasibility test. | Yes, for replicated biological inference using R1/R2/R3 as independent units. | Review lab design records with study author and independent scientist. |
| Cell and virus stock provenance | MRC-5 and VR-740 reported by study. | Cell passage/authentication and exact stock lot, passage, sequence. | Blocks stock-matched reference choice and biological run interpretation. | Yes. | Request contemporaneous cell and virus stock records; laboratory scientist. |
| Library enrichment | RNA-Seq, cDNA, TruSeq v2, single-end; RIN >8 reported. | Poly-A vs rRNA depletion vs other selection; run-level adapter/read quality. | Blocks confident expected viral-RNA recovery and final reference/QC configuration. | Yes, for absence or abundance claims. | Obtain library worksheet or core-facility protocol; study author or sequencing center. |
| Reference artifacts | Proposed accession/version panel; all sequence hashes null. | Exact file contents, terms, transcript membership, rRNA/UniVec build. | Yes, before real mapping. | Yes, for reference-dependent identity or no-hit claims. | Obtain separate artifact/reuse approval, record hashes, review panel; reference curator. |
| Controls and technical pipeline | Synthetic checks and policy/runbook exist; no run-specific blank/control outcomes. | Extraction/library blanks, positive control, index design, mapping and independent-caller validation. | Yes, before pilot execution. | Yes, especially for chimeras, DVG candidates and low-abundance calls. | Finalize control inventory and preregistered thresholds; technical lead and independent reviewer. |
| Authorization | Inactive review pathway and unsigned templates; current acquisition disabled. | No genuine scientific approvals or operator authorization. | **Yes.** | Not itself biological evidence. | Separate future policy/approval and operator review; do not create them here. |

Technical feasibility, scientific evidence, eligibility, and authorization are separate decisions. This PR creates none of the missing approvals and does not change any existing gate.

## Overall decision and next milestone

**Scientific status: HELD. Sequence confirmation: NOT_ASSESSED. Technical decision: NO-GO for real-read analysis. Acquisition: disabled. Reference panel: not activated.**

The next meaningful milestone is a metadata-only resolution package from the study team or archive curator: the exact 96-hour sample/deposition inventory, 0-hour inoculation timing and control labels, independently prepared infection/culture units, MRC-5 provenance, ATCC VR-740 lot/passage/stock sequence, and the actual library enrichment protocol and control outcomes. An independent scientist should review that package and the proposed reference-panel terms before any affected biological conclusions are drawn. A limited single-run technical feasibility test may be considered only after its own technical gates and separate scientific, policy, operator, and acquisition approvals are satisfied; this review does not provide them. Such a test would still not establish infection by itself, biological replication, DVG function, or helper dependence.

## Sources and retrieval record

The source snapshot was captured 2026-10-14 (UTC timestamps and body hashes in `tests/fixtures/hcov229e_sources/real_reduced/capture_manifest.json`). The review also reuses the 2026-10-14, metadata-only 15-run evidence review and its source snapshot hashes. Retrieval hashes identify captured response bytes; they are not source authentication or proof that archive content is immutable.

- GEO sample GSM4718636: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4718636&targ=self&form=text&view=full — retrieved 2026-10-14 21:56:41 UTC.
- GEO series GSE155986: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE155986&targ=self&form=text&view=full — retrieved 2026-10-14 21:56:41 UTC.
- BioSample SAMN15776099: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=biosample&id=15776099&retmode=xml — retrieved 2026-10-14 21:56:42 UTC.
- SRA SRR12424250 record: https://www.ncbi.nlm.nih.gov/sra/SRR12424250; captured record: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra&id=11593710&retmode=xml — retrieved 2026-10-14 21:56:42 UTC.
- ENA SRR12424250 file report: https://www.ebi.ac.uk/ena/portal/api/filereport?accession=SRR12424250&result=read_run&format=tsv&fields=run_accession,experiment_accession,sample_accession,study_accession,secondary_study_accession,fastq_ftp,fastq_md5,fastq_bytes — retrieved 2026-10-14 21:56:42 UTC.
- Primary study: https://doi.org/10.1371/journal.pone.0247128; PubMed record PMID 33630927 and Europe PMC full text PMC7906355 — captured 2026-10-14. Article Methods and Results are study-level evidence, not run-level sequence evidence.
- Existing source registry and reference panel: `research/sources.json` and `docs/hcov229e-reference-panel-v1.json`, metadata snapshot dated 2026-10-15.

The source registry was not modified: this review reuses the existing primary evidence and adds no new primary source.
