# M26: SAM Validation and Candidate Evidence Quality

## Executive summary

M26 starts from merged M25 commit
`e36ccc3b0adf6f91a1c3c709f11068028fd8cccd`. All tests and replays use
deterministic synthetic A/C/G/T fixtures. No biological reads or external
biological references were accessed.

The M25 SAM failures were caused by valid supplementary alignments whose
hard-clipped `SEQ` contained only the unclipped part of the original read.
M6 previously required every SAM record to repeat the entire source read. The
validator now checks the complete source read against CIGAR clipping and the
SAM-strand sequence, without accepting an unknown read or reconstructing
missing bases.

The corrected 18-case M25 replay reproduces all input-manifest digests. All 18
M6 stages complete; the two former SAM-validation failures are resolved.
Exact recoveries remain 0/9, partial recoveries remain 2/9, and one actual
assembler execution failure remains. Three low-complexity cases do not produce
assembly-eligible reads. Running more cases is not evidence of improved
scientific performance.

For the nine-positive-case synthetic pilot, Wilson 95% intervals are 0–29.9%
for exact recovery (0/9) and 6.3–54.7% for partial recovery (2/9). These wide
intervals reflect the small pilot; no recovery improvement is claimed.

The 32 candidates previously grouped as below full read support comprise 31
`UNSUPPORTED_ASSEMBLY` and one `LOW_SUPPORT_ASSEMBLY` record. Thirty 56-nt
repeat fragments are only ten distinct sequences, repeated once in each of the
three splits; none has a qualifying read-back row. No candidate threshold,
filter, or default scoring behavior was changed.

## M25 baseline reproduction

The frozen M25 compact report and the M26 replay contain the same input
manifest SHA-256 for each of the 18 cases. The three pinned M24 baseline
manifest digests also reproduce. The historical M25 report is not rewritten.

| Metric | Historical M25 | Corrected replay |
|---|---:|---:|
| Cases / positive / target-absent controls | 18 / 9 / 9 | 18 / 9 / 9 |
| Positive targets with complete generated input coverage | 6/9 | 6/9 |
| Exact recoveries | 0/9 | 0/9 |
| Partial recoveries | 2/9 | 2/9 |
| M6 SAM-validation failures | 2 | 0 |
| Actual assembler execution failures | 1 | 1 |
| Cases with no assembly-eligible reads | 1 | 3 |
| Candidate records below full read support | 32 | 32 |

All nine target-absent controls produce zero candidate sequences in both
reports.

The two former M6 failures now complete reference screening, but their read
retention differs substantially. The development target has 745 of 747 reads
mapped to the synthetic `m19-reference-m2503`; only two target reads remain,
with 21.4% target coverage. The held-out target has 74 of 747 reads mapped to
that reference; 673 remain, with 99.6% target coverage. The tuning target has
2 of 267 reads mapped; 265 remain, with complete target coverage. All three
cases then have zero assembly-eligible reads under the unchanged low-complexity
triage configuration. These are observed screen outcomes, not SAM-validation
failures; the replay does not change screening defaults or assert that the
screen should retain those mapped reads.

| M25-03 split | Target reads in | Mapped to synthetic reference | Target reads residual | Post-screen coverage | Eligible target reads |
|---|---:|---:|---:|---:|---:|
| Development | 747 | 745 | 2 | 21.4% | 0 |
| Tuning | 267 | 2 | 265 | 100.0% | 0 |
| Held-out | 747 | 74 | 673 | 99.6% | 0 |

The development and held-out mappings have low MAPQ (median 1 in both
partitions); the tuning mappings have MAPQ 4 and 5. This is a synthetic
reference-screen result, not proof of biological contamination or homology.
The existing M6 decision treats these alignments according to its unchanged
screening contract. M26 does not change that contract or reinterpret low-MAPQ
alignments as confirmed reference matches.

## SAM validation root cause and correction

The applicable SAM format specification is
[SAMv1](https://github.com/samtools/hts-specs/blob/master/SAMv1.tex). It states
that hard-clipped bases are absent from `SEQ`, and reverse-strand sequence is
reverse-complemented and recorded consistently with CIGAR.

The previous validator hashed the complete original read and compared that
digest with each record’s `SEQ`. This incorrectly rejected supplementary
records such as `88M62H` and `22H90M38H`, although the clipped `SEQ` segments
matched their corresponding source-read slices.

The corrected validation:

- Keeps strict QNAME, mate, primary-record accounting, reference-dictionary,
  and declared-input checks.
- Parses CIGAR operations and rejects malformed or internal clipping.
- Requires `SEQ` length to equal query-consuming CIGAR length and full-read
  length to equal `SEQ` length plus terminal hard clips.
- Reverse-complements the source sequence when flag `0x10` is set, then
  compares `SEQ` exactly with the source slice remaining after hard clips.
- Preserves soft-clipped bases in `SEQ`; verifies sequence and quality lengths,
  supported bases, reference bounds, and missing `SEQ` rejection.
- Applies identity checks to primary, secondary, and supplementary records;
  supplementary records cannot replace or redefine the source read.

Regression cases cover primary/full reads, soft clipping, left/right/both-end
hard clipping, reverse-strand clipping, supplementary records, malformed
clipping, inconsistent lengths, invalid bases, and mismatched source sequence.
No validation assertion was weakened.

## Missing-output reporting

M25 stage coverage now carries an explicit evaluation state. A present empty
FASTQ is a measured zero (`COMPLETE`); a failed producer is `FAILED`; a
missing artifact from a completed producer is `OUTPUT_MISSING`; and a stage
that did not run is `NOT_EVALUATED`. Unavailable coverage is represented as
`null`, never as zero. The assembly-failure aggregate is set only when
reconstruction evidence explicitly reports `EXECUTION_FAILED`.

## Controlled replay and case outcomes

The original read generator, case seeds, inputs, reference sequences,
reference-screen settings, triage thresholds, assembler settings, and support
thresholds were unchanged. M25 and corrected M26 per-case results are in
[`M26_SAM_VALIDATION_CANDIDATE_EVIDENCE.json`](M26_SAM_VALIDATION_CANDIDATE_EVIDENCE.json).

| Corrected outcome | Cases |
|---|---|
| Actual assembler execution failure | development-m25-01 |
| No eligible reads after triage | development-m25-03, tuning-m25-03, held_out-m25-03 |
| Partial, non-exact candidate | tuning-m25-01, held_out-m25-01 |
| Non-exact candidate set, with unsupported fragments | development-m25-02, tuning-m25-02, held_out-m25-02 |

All target reads were still represented after completed reference screening
in the two formerly blocked cases. The retained reads were excluded before
assembly by the existing low-complexity eligibility criteria. Negative
controls continued to produce zero candidates.

## Candidate redundancy and evidence quality

All below-full-support records originate from SPAdes `assembly/contigs.fasta`.
The 30 unsupported 56-nt sequences have ten distinct sequence hashes; each
distinct sequence occurs in all three split-specific assemblies. All 30 are
exact substrings of their synthetic target. The twelve distinct
below-full-support sequences produce 66 pairwise local alignments with 98.18%
to 100% identity (median 100%), consistent with repeat-associated overlap
rather than 32 independent predictions.

All 32 candidates have 100% candidate coverage, but only 4.0–12.33% target
coverage. The 56-nt fragments have no qualifying read-back rows. The
unsupported 62-nt fragment covers 6.89% of its target and has no support rows.
The 111-nt low-support fragment covers 12.33%; it has 16 read-support rows, of
which one qualifies, below the existing two-distinct-fragment support
requirement. These are incomplete fragments, not near-complete candidates.

Truth comparisons are retrospective and excluded from discovery-stage
classification. No new score, length cutoff, or filtering rule was introduced;
therefore no scoring method is being promoted on these results. The repeated
sequence hashes and support evidence show why raw candidate count must not be
interpreted as independent reconstruction count.

## Independent synthetic validation

The original development, tuning, and held-out M25 partitions were preserved
and replayed with identical manifests. Regression fixtures independently
exercise the validator’s CIGAR, clipping, orientation, sequence, and read-name
checks. No new evidence-quality classifier was trained or tuned on held-out
truth, and no biological-performance claim follows from validator acceptance.

## M20 integration

The registered M20 Phase 2B–5 chain and a separate deterministic Phase 4 replay
were rerun from synthetic handoffs; each phase reports `COMPLETE`. The Phase 4
and replay semantic digest is identical:
`4bd95efee25842356c5c0261b9e4b2ea315964ccf00d965b99a2d40555d77778`. Phase 5
reports `SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED`,
with zero current or historical invalid M12 findings. M8 reports `PARTIAL`
for all ten cases where approved BLAST+ execution is unavailable; these are
not biological no-hit results. Dependency pins and producer bindings were not
changed.

## Verification

- Focused M26/M25/M19–M24 tests: 63 run, 62 passed, one optional live-tool test
  skipped.
- Full repository discovery: 1,104 tests run, 1,083 passed, 21 skipped, no
  failures.
- Corrected M25 replay: all 18 cases completed; all input-manifest digests
  matched; governance fields remained unchanged.
- GitHub Actions is running for the draft PR; its final status will be checked
  and recorded before handoff.

## Limitations and governance

This work evaluates synthetic software behavior only. It does not validate
biological discovery, authorize biological execution, or establish the
biological meaning of any sequence. The M25 pilot remains the regression
benchmark; the replay improves execution accounting, not recovery accuracy.

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
