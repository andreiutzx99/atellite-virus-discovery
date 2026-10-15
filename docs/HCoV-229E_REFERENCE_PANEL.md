# HCoV-229E reference-panel rationale (v1)

**Scope:** GSE155986 / PRJNA656274 / SRP276927 / SRR12424250 only. This is a proposed metadata-level panel, not an acquired sequence bundle. No FASTA/FASTQ or large reference dataset was downloaded. Every sequence checksum is therefore unverified and represented as `null` in the manifest.

## Proposed composition

The essential host background is the RefSeq GRCh38.p14 assembly **GCF_000001405.40**, pinned with NCBI annotation release **GCF_000001405.40-RS_2025_08** when transcript annotations are required [S01–S03]. The assembly is a multi-record bundle, not one sequence. Its primary chromosome records and lengths are recorded individually in the manifest. GRCh38 is a general human reference, not the genotype of the MRC-5 culture or a sample-specific host assembly. The annotation release is similarly a versioned collection rather than a single transcript accession; package membership and checksum must be captured when a real panel is separately authorized.

The essential HCoV-229E comparison is RefSeq **NC_002645.1** (27,317 nt; clone `inf-1`) [S05–S06]. It is not evidence that the experimental stock exactly matches that clone. The paper reports ATCC VR740, but lot, passage, stock sequence and a direct link from that stock to the archive run remain unverified. The documented Haiti isolate **MF542265.1** (27,271 nt) is an optional diversity comparator [S09–S11], not a substitute helper reference. Any wider isolate panel should be selected and pinned after reviewing isolate provenance and the study stock.

The human mitochondrial record **NC_012920.1** is 16,569 nt and contains annotated 12S/16S rRNA features [S02, S04]. Nuclear and mitochondrial rRNA should be represented from the pinned host annotation/assembly, not by an unversioned hand-built consensus. The current manifest leaves stand-alone nuclear rRNA accessions unresolved rather than pinning stale or ambiguous records.

NCBI **UniVec Core** is an optional vector/linker/primer screen, not a complete contaminant database [S19]. The exact Illumina kit is unknown; the current `AGATCGGAAGAGC` QC adapter is only a software setting, not evidence that this kit was used [S20]. PhiX174 **NC_001422.1** (5,386 nt) is an optional technical-control comparator [S21, S23]; the manufacturer's PhiX product page does not establish that exact accession for a control lot [S21]. None of these optional references establishes contamination in this sample.

## Interpretation

Coronavirus discontinuous transcription naturally produces leader–body junctions [S12–S14]. The HCoV-229E review reports a CUAAAC transcription-regulatory core, but that species-level motif does not verify the exact sequence or junctions in the experimental stock. A junction can be compatible with normal subgenomic RNA, a noncanonical transcript, a DVG-like deletion, recombination, or an artifact [S15–S18]. ViReMa reports caller-scoped junction evidence; it does not classify a DVG, DI particle, satellite, or helper dependence.

No-hit is not evidence of novelty. Coverage, a split read, or a caller result is not biological validation. Candidate claims would require strain-matched references, controls, independent junction confirmation and, for function or helper dependence, suitable experiments. The reference panel is therefore **NO-GO for real-data interpretation** until the exact library/stock, reference artifacts, source terms, controls and authorized workflow are reviewed. This is a technical readiness decision only; public-virus status remains **HELD** and sequence confirmation **NOT_ASSESSED**.

## Source notes

The SRA record identifies SRR12424250 as GSM4718636, a single-end HiSeq 2500 run, and records cDNA selection and TruSeq RNA Library Preparation Kit v2; its submitted details conflict with the article's timepoint description [S07–S08]. Full citations and claim summaries are in `research/sources.json`. Research evidence pages are retained locally at the workspace root; large source texts and all sequence artifacts are intentionally absent from this PR.
