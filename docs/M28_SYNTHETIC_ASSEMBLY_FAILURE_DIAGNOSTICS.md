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
