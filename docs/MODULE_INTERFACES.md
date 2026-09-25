# Module contracts and incomplete stages

This document records modular boundaries and historical requirements; it is not the current complete capability register. M1–M6 capabilities are summarized in the [README](../README.md) and [roadmap](ROADMAP.md). The placeholder contracts below are not all implemented plug-in stages. Missing evidence is never a negative observation, and no arbitrary score is a calibrated probability.

| Interface | Expected input | Expected output | Released implementation / remaining boundary |
|---|---|---|---|
| Acquisition/QC/integrity | Archive metadata or existing QC folder | Verified FASTQ, metrics, source/output digests | Implemented; local SRA conversion conditional on fasterq-dump, with real paired yeast validation |
| Library review | datasets.json | RNA/DNA/mixed/unknown and conflict CSV/JSON/HTML | Implemented; does not select tools automatically |
| Mapping | Verified read manifest plus independently supplied versioned reference manifest | SAM/BAM, command/version/log and conservation counts | General automated helper-discovery mapping is not implemented. M6 separately performs primary mapping against a declared reference FASTA for residual accounting; it is not a general discovery mapper. |
| Read partition | Existing alignments plus source-read IDs | Mapped/unmapped/partial partitions and exhaustive count manifest | M6 implements a declared-reference residual partition with complete primary-record accounting. The broader arbitrary-alignment extraction interface described here is not implemented. |
| Assembly | One or two structurally validated FASTQ files with an explicit layout; registered assembler parameters | Preserved raw output, catalogue-compatible canonical FASTA, logs, manifest and hashes | Registered arbitrary-input SPAdes/Tadpole stage is software-tested, including real single/paired runs in the current environment. No biological assembly-quality claim or automatic novel-element reconstruction |
| BAM/CRAM decoder | Existing BAM/CRAM and reference manifest where required | Validated alignment-block stream with coordinate convention and exclusions | Implemented conditional decoder using pysam or samtools; real artificial BAM/CRAM tests in Linux CI. SAM/gzip-SAM/interval handling remains available without those dependencies |
| Database search | Supplied sequences and independently curated reference manifest | Standard nucleotide BLAST table, database versions, command and logs | Supplied-reference BLAST execution adapter implemented and runtime-tested; external BLAST required, no auto-curated biological panel |
| BLAST evidence import | Existing 12-column nucleotide outfmt 6 and feature/reference manifests | Normalized matches, orientation, reported-hit status, provenance | Implemented; no inference from no-hit status |
| Contamination review | Feature lengths, supplied matches and explicit technical-control calls | Per-role union coverage, evidence flags and uncertainty | Implemented; no validated automatic rejection or contamination probabilities |
| Sequence inventory | Supplied nucleotide FASTA | Length, GC, ambiguity, single-symbol entropy, exact duplicates, SQLite/FASTA | Implemented; no biological low-complexity rejection threshold |
| Coverage | Existing interval CSV or SAM/gzip-SAM | Alignment counts, covered bases, depth/breadth and exclusions | Implemented; does not establish unique molecule support or reliable assembly |
| DVG / recombination assessment | External independently validated assessment with cited source | External category, provenance, uncertainty and assessed sequence ID | M5 implements optional ViReMa caller-specific junction evidence. Multi-caller assessment, terminal/packaging analysis, and functional inference remain unimplemented. |
| ORF/domain/motif/structure assessment | External annotated records with method/reference provenance | Descriptive annotation table linked by sequence ID | Not implemented in this discovery context; no functional predictions generated |
| Observations and studies | Explicit unique samples/observations and known/unknown status | Stratified recurrence/control counts and denominators, HTML/CSV/SQLite | Implemented; no read-level detection or causal dependency inference |
| Catalogue and exact groups | Verified sequence snapshots with sample/study metadata | Stable exact-sequence IDs, linked occurrences, SQLite and CSV adapters | Implemented; no approximate-family discovery, consensus or phylogeny |
| Approximate clustering | Independently supplied validated cluster membership | Cluster ID, sequence IDs, external method/threshold/provenance | Placeholder only; exact groups must not be substituted for similarity clusters |
| External reference curation | Curated source/accession/version and role manifest | Verified snapshot manifest with update history | No comprehensive automatic reference curation or biological suitability claims |
| Scientific validation | Independent truth labels and blinded benchmark protocol | Explicit denominators, sensitivity/false-positive/rank results and uncertainty | No biological benchmark or fabricated metrics; software fixtures remain separate |
| UI/reporting/provenance | Implemented-stage artifacts | Linked reports, exports, status and dependency diagnostics | Implemented for supplied artifacts; no autonomous RUN DISCOVERY |

For all placeholder interfaces, absence of an implementation is a hard stop, not an empty successful result. Future independent implementations require record-conservation, invalid-input, interruption, resource-limit, provenance and validation tests before any integration. The released launcher never calls these placeholders. The original biological methods are not prescribed by these interface declarations.

## Conditional implementation update (2026-09-24)

The table above retains the original boundaries. These specific generic adapters are implemented: `alignment_adapter` (optional pysam/samtools to the existing coverage contract), `local_comparison` (supplied query/reference FASTA and roles to BLAST database/hits and provenance), `reference_snapshot` (explicit source/hash specification to immutable local files), `sra_conversion` (local archive to verified gzip FASTQ when fasterq-dump is available), `context_review` (supplied context/quantitative tables to descriptive reports), and `artifact_workflow` (allowlisted stage specification to verified resumable outputs). See [exact current contracts and limits](CONDITIONAL_TOOLS.md). Separately, M5 implements optional caller-specific ViReMa evidence and M6 implements declared-reference residual screening with optional residual assembly/read-back. Neither activates autonomous biological discovery, general-purpose helper mapping, functional annotation, or approximate-family discovery.

## Supplied-artifact validation follow-up

See [ARTIFACT_VALIDATION_REPORT.md](ARTIFACT_VALIDATION_REPORT.md) for implementation, test evidence and explicit remaining limitations. This adds bounded fallback retries/history, file-level reference metadata, digest/control evaluation (menu23 and workflow stage), and a paired artificial Tadpole diagnostic. It does not deliver a biological discovery chain.

## Current implementation audit

[APPLICATION_CAPABILITY_AUDIT.md](APPLICATION_CAPABILITY_AUDIT.md) distinguishes current runtime behavior from historical contracts. The workflow has a fixed allowlist; the placeholder statuses above are not implemented workflow status values or evidence of a callable external-module registry.
