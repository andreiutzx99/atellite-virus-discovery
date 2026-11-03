# M28 synthetic assembly failure diagnostics

## Scope and decision

Retrospective analysis of deterministic artificial A/C/G/T M25–M27 fixtures only. Synthetic truth is used only for diagnostics; it is not supplied to assembly or candidate ranking.

**Decision: retain existing production default.**
No experimental configuration is promoted. Existing M6 and assembly defaults remain unchanged.

## Evidence status

- Original experimental results: documented historical results; all three k=21,33 assemblies completed, producing 20 contigs each. All 60 contigs were recorded as unsupported under frozen M6 thresholds, with no exact recovery.
- Current follow-up verification: report metadata and code/tests only. The experiments were not rerun, and no production threshold or default changed.
- Unavailable evidence: original experimental eligible-read FASTQ and SAM files. Mapped/unmapped counts, alignment rejection counts and per-contig alignment detail are not supplied.

The original experimental FASTQ and SAM evidence was unavailable for this follow-up analysis. Consequently, mapped/unmapped read counts and the relative contributions of absent alignments versus rejected low-confidence alignments could not be independently determined. Unsupported classifications reflect the previously recorded frozen M6 support criteria and must not be interpreted as proof that no reads aligned.

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

Failure attribution is derived from persisted M6 stage manifests and reconstruction evidence. A missing output is not treated as proof of assembler failure; upstream failure and zero eligible reads remain separate categories. Prior M25–M27 reports contain historical incident descriptions, but their original run outputs are unavailable here and those details are not independently reverified by this report.

Configured timeout/output limits are cooperative, not hard operating-system resource quotas.

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

| Split | Default contigs | Experimental k=21,33 contigs | Default best breadth | Experimental best breadth | Exact recovery | Support (supported / low / unsupported) |
|---|---:|---:|---:|---:|---|---|
| development | 22 | 20 | 12.3% | 7.4% | False | 0 / 0 / 20 |
| tuning | 20 | 20 | 7.9% | 4.8% | False | 0 / 0 / 20 |
| held_out | 20 | 20 | 12.3% | 7.4% | False | 0 / 0 / 20 |

The unchanged default was not modified. Experimental contigs were evaluated against matching frozen M6 read-support thresholds. This synthetic comparison does not justify promotion.

### Read accounting from original experimental evidence

The per-run input counts below are preserved from the original mapper execution records. Primary mapped/unmapped counts, rejection counts, and per-contig qualifying-read counts are not supplied because the original FASTQ and SAM evidence is unavailable.

| Split | Historically recorded input reads | Primary mapped | Primary unmapped | Rejected by MAPQ | Rejected by alignment fraction | Rejected by identity | Rejected by other support criteria | Per-contig qualifying support counts |
|---|---:|---|---|---|---|---|---|---|
| development | 432 | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED |
| tuning | 671 | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED |
| held_out | 427 | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED |

SPAdes `-m 2` is 2 GB (2,048 MB). The experimental command used `-m 2`; the execution metadata now reports the value in both units.

## M20 integration

M20 execution summary: `NOT_SUPPLIED`. Available per-phase evidence is recorded in the companion JSON; missing artifacts remain unavailable and are not inferred.

## Testing and CI

Test and CI outcomes are not embedded in this scientific report. Use current test output and final-head GitHub Actions checks on the draft PR; historical test counts are not presented as current verification.

All M28 analyses and assembly comparisons described here use artificial A/C/G/T fixtures.

## Governance

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
