# Module contracts and incomplete stages

These boundaries preserve modularity. They are not implementations of the original discovery methods. Every external adapter must receive a schema version, input paths and SHA256 hashes, method/version and parameters. It must return `complete`, `failed`, `blocked_dependency`, or `not_implemented`, plus output hashes and logs. Unimplemented stages emit **no findings** and block dependent execution. Missing evidence is never a negative observation. No arbitrary score is a calibrated probability.

| Interface | Expected input | Expected output | Released implementation / remaining boundary |
|---|---|---|---|
| Acquisition/QC/integrity | Archive metadata or existing QC folder | Verified FASTQ, metrics, source/output digests | Implemented; SRA Toolkit conversion unavailable |
| Library review | datasets.json | RNA/DNA/mixed/unknown and conflict CSV/JSON/HTML | Implemented; does not select tools automatically |
| Mapping | Verified read manifest plus independently supplied versioned reference manifest | SAM/BAM, command/version/log and conservation counts | Historical local prototype not released; automated helper-discovery mapping unsupported here |
| Read partition | Existing alignments plus source-read IDs | Mapped/unmapped/partial partitions and exhaustive count manifest | Not released; no discovery read extraction is performed |
| Assembly | Verified read manifest, external assembler method/version/parameters | FASTA, logs, graph if available and hashes | SPAdes runtime unavailable; Tadpole artificial-fixture diagnostic only; no automatic novel-element reconstruction |
| BAM/CRAM decoder | Existing BAM/CRAM and reference manifest where required | Validated alignment-block stream with coordinate convention and exclusions | Dependency gap; SAM/gzip-SAM/interval alternative implemented |
| Database search | Supplied sequences and independently curated reference manifest | Standard nucleotide BLAST table, database versions, command and logs | Execution adapter not released; no auto-curated biological panel |
| BLAST evidence import | Existing 12-column nucleotide outfmt 6 and feature/reference manifests | Normalized matches, orientation, reported-hit status, provenance | Implemented; no inference from no-hit status |
| Contamination review | Feature lengths, supplied matches and explicit technical-control calls | Per-role union coverage, evidence flags and uncertainty | Implemented; no validated automatic rejection or contamination probabilities |
| Sequence inventory | Supplied nucleotide FASTA | Length, GC, ambiguity, single-symbol entropy, exact duplicates, SQLite/FASTA | Implemented; no biological low-complexity rejection threshold |
| Coverage | Existing interval CSV or SAM/gzip-SAM | Alignment counts, covered bases, depth/breadth and exclusions | Implemented; does not establish unique molecule support or reliable assembly |
| DVG / recombination assessment | External independently validated assessment with cited source | External category, provenance, uncertainty and assessed sequence ID | No automatic reconstruction, terminal/packaging analysis or functional inference |
| ORF/domain/motif/structure assessment | External annotated records with method/reference provenance | Descriptive annotation table linked by sequence ID | Not implemented in this discovery context; no functional predictions generated |
| Observations and studies | Explicit unique samples/observations and known/unknown status | Stratified recurrence/control counts and denominators, HTML/CSV/SQLite | Implemented; no read-level detection or causal dependency inference |
| Catalogue and exact groups | Verified sequence snapshots with sample/study metadata | Stable exact-sequence IDs, linked occurrences, SQLite and CSV adapters | Implemented; no approximate-family discovery, consensus or phylogeny |
| Approximate clustering | Independently supplied validated cluster membership | Cluster ID, sequence IDs, external method/threshold/provenance | Placeholder only; exact groups must not be substituted for similarity clusters |
| External reference curation | Curated source/accession/version and role manifest | Verified snapshot manifest with update history | No comprehensive automatic reference curation or biological suitability claims |
| Scientific validation | Independent truth labels and blinded benchmark protocol | Explicit denominators, sensitivity/false-positive/rank results and uncertainty | No biological benchmark or fabricated metrics; software fixtures remain separate |
| UI/reporting/provenance | Implemented-stage artifacts | Linked reports, exports, status and dependency diagnostics | Implemented for supplied artifacts; no autonomous RUN DISCOVERY |

For all placeholder interfaces, absence of an implementation is a hard stop, not an empty successful result. Future independent implementations require record-conservation, invalid-input, interruption, resource-limit, provenance and validation tests before any integration. The released launcher never calls these placeholders. The original biological methods are not prescribed by these interface declarations.

## Conditional implementation update (2026-09-24)

The table above retains the original boundaries. These specific generic adapters are now implemented: `alignment_adapter` (optional pysam/samtools to the existing coverage contract), `local_comparison` (supplied query/reference FASTA and roles to BLAST database/hits and provenance), `reference_snapshot` (explicit source/hash specification to immutable local files), `sra_conversion` (local archive to verified gzip FASTQ when fasterq-dump is available), `context_review` (supplied context/quantitative tables to descriptive reports), and `artifact_workflow` (allowlisted stage specification to verified resumable outputs). See [exact current contracts and limits](CONDITIONAL_TOOLS.md). No mapping, extraction, novel-element assembly, functional annotation or approximate-family discovery interface is activated by these additions.
