# M28 synthetic assembly failure diagnostics

## Scope and decision

Retrospective analysis of deterministic artificial A/C/G/T M25–M27 fixtures only. Synthetic truth is used only for diagnostics; it is not supplied to assembly or candidate ranking.

**Decision: retain existing production default.**
No experimental configuration is promoted. Existing M6 and assembly defaults remain unchanged.

## Frozen baseline

- Cases: 18 (9 positive; 9 target-absent controls).
- Exact recovery: 0/9.
- Partial recovery: 2/9.
- Negative-control cases with candidates: 0.
- M24 input-manifest digests reproduced: True.
- Baseline source commit: `5db8b9b79428054bd30b364836057e5e7e377322`.
- Candidate records / distinct sequence hashes: 64 / 41.
- Below-full-support records / distinct hashes: 32 / 12.

## Assembler failure diagnosis

Failure classes across all cases: `{"ASSEMBLER_COMPLETED_INCOMPLETE_SUPPORTED_CONTIGS": 5, "ASSEMBLER_PROCESS_FAILURE": 1, "NO_ASSEMBLY_ELIGIBLE_READS": 12}`.

The single process failure was `development-m25-01`: 107 assembly-eligible single-end reads were present. SPAdes 4.1.0 was found and version-checked; it exited with code 21 after `spades-core` reported an abnormal system call involving `K55/configs/config.info`. Immediately before that, SPAdes logged: `Invalid kmer coverage histogram, make sure that the coverage is indeed uniform`. The configuration file existed as a regular file; captured stderr was empty. The report records input identity, command, runtime settings, output inventory and log hashes. This is evidence of SPAdes' coverage-model failure on this input, not proof of the lower-level OS error's cause. This was an actual assembler process failure, not an upstream eligibility failure, and no contig FASTA was produced.

Twelve cases had zero assembly-eligible reads; these are not assembler failures. Five completed with read-supported but incomplete assemblies. Invalid-input, missing-dependency, and completed-empty-contig outcomes did not occur in the frozen replay. Configured timeout/output limits are cooperative, not hard operating-system resource quotas.

## Case-level assembly outcomes

| Case | Eligible reads | Assembly status | Failure classification | Exact | Partial |
|---|---:|---|---|---|---|
| development-m25-01 | 107 | EXECUTION_FAILED | ASSEMBLER_PROCESS_FAILURE | False | False |
| development-m25-02 | 432 | READ_SUPPORTED_ASSEMBLY | ASSEMBLER_COMPLETED_INCOMPLETE_SUPPORTED_CONTIGS | False | False |
| development-m25-03 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| development-m25-negative-1 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| development-m25-negative-2 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| development-m25-negative-3 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| tuning-m25-01 | 192 | READ_SUPPORTED_ASSEMBLY | ASSEMBLER_COMPLETED_INCOMPLETE_SUPPORTED_CONTIGS | False | True |
| tuning-m25-02 | 671 | READ_SUPPORTED_ASSEMBLY | ASSEMBLER_COMPLETED_INCOMPLETE_SUPPORTED_CONTIGS | False | False |
| tuning-m25-03 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| tuning-m25-negative-1 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| tuning-m25-negative-2 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| tuning-m25-negative-3 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| held_out-m25-01 | 107 | READ_SUPPORTED_ASSEMBLY | ASSEMBLER_COMPLETED_INCOMPLETE_SUPPORTED_CONTIGS | False | True |
| held_out-m25-02 | 427 | READ_SUPPORTED_ASSEMBLY | ASSEMBLER_COMPLETED_INCOMPLETE_SUPPORTED_CONTIGS | False | False |
| held_out-m25-03 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| held_out-m25-negative-1 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| held_out-m25-negative-2 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |
| held_out-m25-negative-3 | 0 | NO_SUPPORTED_ASSEMBLY | NO_ASSEMBLY_ELIGIBLE_READS | False | False |

## Graph evidence and limitations

Where SPAdes GFA files were retained, the JSON reports segment and link counts, terminal segments, branches, coverage tags, and file hashes. These graph summaries are descriptive and do not establish the unique correct path. Cases without GFA remain unavailable.

## Repeat and candidate evidence

Per-target entropy, exact k-mer uniqueness/multiplicity and spacing summaries use known synthetic truth only retrospectively. Candidate sequence hashes, lengths and support states are included in the JSON. Repeated candidate records are not independent reconstructions; no unsupported extension was filled from truth.

## Controlled experiments and promotion

Paired experiments used identical eligible reads within each frozen partition:

| Split | Default contigs | Experimental k=21,33 contigs | Default best breadth | Experimental best breadth | Exact recovery |
|---|---:|---:|---:|---:|---|
| development | 22 | 20 | 12.3% | 7.4% | False |
| tuning | 20 | 20 | 7.9% | 4.8% | False |
| held_out | 20 | 20 | 12.3% | 7.4% | False |

The unchanged default was not modified. Alternative runs are experimental; their standalone contigs were not passed through read-back support evaluation. These results do not justify promotion.

## M20 integration

M20 execution summary: `COMPLETE`. Per-phase schemas, statuses, decisions, and deterministic Phase 4 digest are recorded in the companion JSON. Phase 2B, 3 and 4 completed; Phase 4 replay digest was `5d3e04b5d6f8265210635ea434b079e2e399c0e94b4f6a6d528666e5dce4c996`. Phase 5 reported `SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED`. M13/M14 inputs were absent, leaving M15 dossier completeness partial. BLAST+ 2.16.0 did not satisfy the approved 2.17.0+ pin, so the nucleotide search remained unavailable rather than a completed no-hit result.

## Testing and CI

M28 focused: 3 passed; M25/M27 regressions: 9 passed; M20 Phase 2B–5 focused suite: 34 passed. Full repository discovery: 1,090 passed out of 1,111, 21 skipped, 0 failed. GitHub Actions was still running when this report snapshot was generated; the final-head result is linked from the draft PR.

The discovery run exercised tests with placeholder accession identifiers, but retrieved no complete FASTQ runs. All M28 analyses and assembly comparisons described here use artificial A/C/G/T fixtures.

## Governance

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
