# Artificial artifact-workflow fixture

The integration tests generate this small dataset from a fixed pseudorandom
seed. It contains no user or biological discovery data:

- one synthetic nucleotide sequence used as the supplied reference and as an
  exact sample/control sequence;
- an `N`-only FASTQ/FASTA record that must yield no BLAST alignment;
- distinct sample and control catalogues so occurrence linkage is testable;
- deterministic single-end and paired-end short reads for optional real
  assembler runs.

Expected behavior is software-level only: exact fixture records are retained,
the supplied exact reference produces comparison evidence, the ambiguous
no-hit record produces no comparison rows, and the shared checksum is visible
in both declared sample and control observations. A no-hit is not evidence of
novelty or biological absence.