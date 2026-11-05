# M29 assembly root-cause recovery

Synthetic A/C/G/T data only. Historical M25–M28 results are not modified.

## Decision

**No production promotion.** The M19 production defaults and frozen support thresholds are unchanged.

## Historical root-cause evidence

M27 identifies low-complexity triage as the demonstrated reason three positive M25-03 cases had zero assembly-eligible reads. The nine target-absent controls are expected not to contain target reads; they are not failed positive recoveries.

The M28 SPAdes exit-21 record has no persisted stderr bytes and does not establish an operating-system cause. The five incomplete supported assemblies remain unexplained by the available evidence. Missing historical experimental FASTQ/SAM inputs prevent a read-level explanation for the 60 unsupported experimental contigs.

## M29 benchmark

- Cases: 17 (13 positive; 4 target-absent control).
- Exact recoveries: 6; independently read-supported exact recoveries: 6.
- Held-out read-supported exact recoveries: 3.
- Confirmatory fresh-seed held-out B recoveries: 1.
- False-positive candidates in target-absent controls: 0.
- Configuration B false-positive candidates in its held-out target-absent control: 1.
- M29 success criterion met: False.
- Truth is read only after each registered M19 workflow run for retrospective scoring.
- The earlier exploratory B pilot is excluded from confirmation; the counted held-out validation uses a distinct deterministic seed.
- Reduced-coverage failures with an SPAdes invalid k-mer coverage histogram are attributed to the observed coverage-model failure only; no operating-system cause is inferred.

| Case | Split | Factor | Eligible | Contigs | Assembly | Exact | Partial | Identity | Breadth | Candidates |
|---|---|---|---:|---:|---|---|---|---:|---:|---:|
| development-m29-positive_control | development | positive_control | 720 | 1 | READ_SUPPORTED_ASSEMBLY | True | False | 1.0 | 1.0 | 1 |
| development-m29-repeat_challenge | development | repeat_challenge | 720 | 1 | NO_SUPPORTED_ASSEMBLY | False | False | 1.0 | 0.07222222222222222 | 1 |
| development-m29-target_absent_negative | development | target_absent_negative | 0 | 0 | NO_SUPPORTED_ASSEMBLY | False | False | None | None | 0 |
| tuning-m29-reduced_coverage | tuning | reduced_coverage | 108 | 0 | EXECUTION_FAILED | False | False | None | None | 0 |
| tuning-m29-short_reads | tuning | short_reads | 1440 | 1 | READ_SUPPORTED_ASSEMBLY | True | False | 1.0 | 1.0 | 1 |
| tuning-m29-sequencing_errors | tuning | sequencing_errors | 720 | 1 | READ_SUPPORTED_ASSEMBLY | False | True | 0.9988851727982163 | 0.9966666666666667 | 1 |
| tuning-m29-synthetic_background | tuning | synthetic_background | 720 | 1 | READ_SUPPORTED_ASSEMBLY | True | False | 1.0 | 1.0 | 1 |
| tuning-m29-target_absent_negative | tuning | target_absent_negative | 0 | 0 | NO_SUPPORTED_ASSEMBLY | False | False | None | None | 0 |
| held_out-m29-positive_control | held_out | positive_control | 720 | 1 | READ_SUPPORTED_ASSEMBLY | True | False | 1.0 | 1.0 | 1 |
| held_out-m29-reduced_coverage | held_out | reduced_coverage | 108 | 0 | EXECUTION_FAILED | False | False | None | None | 0 |
| held_out-m29-short_reads | held_out | short_reads | 1440 | 1 | READ_SUPPORTED_ASSEMBLY | True | False | 1.0 | 1.0 | 1 |
| held_out-m29-repeat_challenge | held_out | repeat_challenge | 720 | 1 | NO_SUPPORTED_ASSEMBLY | False | False | 1.0 | 0.07222222222222222 | 1 |
| held_out-m29-sequencing_errors | held_out | sequencing_errors | 720 | 1 | READ_SUPPORTED_ASSEMBLY | False | True | 0.9988876529477196 | 0.9988888888888889 | 1 |
| held_out-m29-synthetic_background | held_out | synthetic_background | 720 | 1 | READ_SUPPORTED_ASSEMBLY | True | False | 1.0 | 1.0 | 1 |
| held_out-m29-low_coverage_validation | held_out | low_coverage_validation | 108 | 0 | EXECUTION_FAILED | False | False | None | None | 0 |
| held_out-m29-low_coverage_target_absent_background | held_out | low_coverage_target_absent_background | 108 | 0 | EXECUTION_FAILED | False | False | None | None | 0 |
| held_out-m29-target_absent_negative | held_out | target_absent_negative | 0 | 0 | NO_SUPPORTED_ASSEMBLY | False | False | None | None | 0 |

## Matched configuration experiment

tuning: `tuning-m29-reduced_coverage`. Eligible-read input identity matched: `True`.

| Configuration | Assembly status | Exact recovery | Read support | False-positive candidates |
|---|---|---|---|---:|
| A: registered default | EXECUTION_FAILED | False | [] | None |
| B: SPAdes k=21 only | COMPLETED | True | READ_SUPPORTED_ASSEMBLY | None |

held_out: `held_out-m29-low_coverage_validation`. Eligible-read input identity matched: `True`.

| Configuration | Assembly status | Exact recovery | Read support | False-positive candidates |
|---|---|---|---|---:|
| A: registered default | EXECUTION_FAILED | False | [] | None |
| B: SPAdes k=21 only | COMPLETED | True | READ_SUPPORTED_ASSEMBLY | None |

negative_control: `held_out-m29-low_coverage_target_absent_background`. Eligible-read input identity matched: `True`.

| Configuration | Assembly status | Exact recovery | Read support | False-positive candidates |
|---|---|---|---|---:|
| A: registered default | EXECUTION_FAILED | False | [] | 0 |
| B: SPAdes k=21 only | COMPLETED | False | READ_SUPPORTED_ASSEMBLY | 1 |

B is an isolated experiment on matched synthetic reads. It does not alter production parameters. Promotion requires replicated held-out performance.

## Verification and limitations

Reproduce with `python -m satellite_discovery.m29_assembly_root_cause_recovery --output /tmp/m29-evidence --repository-root .`. The output directory must be new or empty; generated assembler work products stay outside Git.

The JSON companion contains per-stage read counts, support statuses, sequence digests, and historical evidence references. Assembly completion is not biological discovery. Results on synthetic controls do not establish performance on biological samples.

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
