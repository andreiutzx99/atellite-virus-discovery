# M21 Phase 3 — FASTQ technical-readiness specification

The local-only `fastq-check` command performs format/integrity checks without network access or workflow invocation:

```text
satellite-discovery m21-readiness fastq-check --r1 synthetic_R1.fastq --r2 synthetic_R2.fastq
```

It supports plain FASTQ and gzip-compressed FASTQ, checks four-line records, nonempty sequence, `+` separator, sequence/quality length equality, supported Phred+33 character range, truncation/decompression errors, duplicate identifiers, mate count and normalized identifier consistency. It reports read and pair counts, length range, mean/min/max quality, and a quality-score histogram. Configurable `min_reads`, `min_length`, `max_length`, and `min_mean_quality` thresholds can be supplied as JSON; the tool does not set universal biological QC cutoffs. Pair identifier conventions supported are `/1` and `/2`, or matching IDs with standard `1:` / `2:` mate markers.

The parser caps each input at 100,000 records to bound memory. This phase tests only small synthetic fixtures; it does not establish full-scale throughput or suitability for the selected biological libraries. Future approved use needs a separately reviewed scalable implementation and thresholds appropriate to the assay and workflow.

The checklist for any separately authorized future files includes file existence and expected format, paired-mate consistency, cryptographic digest, read counts, length and quality distributions, truncation/corruption, duplicate or malformed identifiers, and depth/suitability review. Depth adequacy and contamination are curator/scientific judgments not decided by this parser. Do not interpret passing syntax checks as evidence of biological adequacy.

