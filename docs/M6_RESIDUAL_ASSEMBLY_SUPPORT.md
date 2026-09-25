# M6 — Residual-read assembly support

**Status: IMPLEMENTED.** M6 provides a reference-scoped technical partition,
optional assembly, and read-back support. It does not identify novel
satellites. See the [README](../README.md), [M6 workflow audit](M6_AUDIT.md),
and [roadmap](ROADMAP.md).

## 1. Purpose

Account for supplied reads against a declared reference FASTA, preserve
fragments not primarily mapped in that comparison, triage them for assembly
eligibility, and optionally test contigs by read-back alignment.

## 2. Why this milestone exists

Reads not accounted for by a bounded reference comparison may merit separate
technical handling. The stage preserves this run-scoped evidence without
converting it into a novelty or biological-identity claim.

## 3. Implemented functionality

M6 validates inputs and reference scope, requires complete primary SAM
accounting, assigns residual/eligible/retained-unassembled outcomes, optionally
runs registered assembly, and validates support alignments and contig evidence.

## 4. Inputs

Inputs include the declared clean FASTQ bytes and layout, matching QC
provenance, a declared reference FASTA and role table, bounded settings, and
the trusted minimap2 executable. Assembly is optional; optional DVG evidence
can be supplied without changing the M6 mapping definition.

## 5. Outputs

Outputs include residual FASTQ, assembly-eligible FASTQ, retained-unassembled
FASTQ, per-read triage/provenance, and—when enabled—assembly, read-back, and
contig-support evidence. These categories remain distinct.

## 6. External tools and dependencies

Minimap2 is required for the reference-screen and read-back stages.
SPAdes/Tadpole are optional registered assemblers. External executables and
databases are not bundled with the package.

## 7. Evidence produced

Tests and the artificial minimap2 runtime check support reference dictionary
validation, complete read accounting, paired behavior, input integrity,
triage rules, alignment validation, and configured technical support
criteria. They do not establish biological recovery performance.

## 8. Provenance and reuse

Evidence is bound to source-read and QC digests, reference FASTA/role digests,
tool identity, settings, and output digests. Source files are checked for
changes during triage; invalid or changed inputs cannot produce final
residual artifacts.

## 9. Failure and dependency semantics

Missing/duplicate/unknown primary records, incompatible reference dictionaries,
invalid coordinates, changed inputs, missing tools, invalid assemblies, and
failed support mappings remain explicit failures or unresolved states.
Incomplete comparison accounting cannot produce a valid zero-residual result.

## 10. Interpretation

**Residual** means no primary mapped record under the run's declared FASTA
and recorded minimap2 settings (`-a -x sr --secondary=no`). For paired reads,
a primary mapping for either mate excludes the whole fragment from the
residual set. This screen decision is not filtered by the later read-support
MAPQ, identity, or aligned-fraction criteria.

## 11. Limitations

Default residual triage uses a 50-base minimum read length, at most 5%
ambiguous bases, at least 1.2 bits entropy, and at least Phred 20. Support
defaults include MAPQ 20, at least 80% aligned query fraction, at least 95%
sequence identity, at least two distinct sequence hashes and fragments, at
least 80% coverage breadth, and mean depth 2. These are configurable
operational thresholds; they are not biologically calibrated. M6 has no
positive minimum contig-length threshold, although assembler behavior may
filter short contigs. For paired support, both mates must qualify on the same
supported contig.

## 12. What M6 does not establish

Residual does not mean novel, viral, satellite, unclassified, or absent from
all relevant genomes. `READ_SUPPORTED_ASSEMBLY` means configured technical
criteria passed. Read-back is a separate alignment using the same eligible
reads supplied to assembly, not an independent sample, held-out set, or
orthogonal assay.

## 13. Relevant tests and records

See [M6 workflow audit](M6_AUDIT.md), the
[M1–M6 scientific audit](M1_M6_SCIENTIFIC_AUDIT.md), the
[residual-read tests](../tests/test_residual_reads.py), the
[read-support tests](../tests/test_read_support.py), and the
[test suite](../tests/).

## 14. Relevant literature

The mapper is described by [Li (2018)](https://doi.org/10.1093/bioinformatics/bty191).
Biological context on satellite and subviral diversity is listed in the
[README references](../README.md#references). None of those sources calibrates
M6's defaults or validates this workflow's biological sensitivity or
specificity.

## 15. Relationship to other milestones

M6 consumes declared reads and references and may receive optional M5
caller-specific evidence. It is a technical evidence stage, not the planned
novelty, host, helper-dependence, ranking, or blinded-validation layers.
Those remain M7–M16 in the [roadmap](ROADMAP.md).