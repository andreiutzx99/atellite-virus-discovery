# M29 assembly root-cause recovery

Synthetic A/C/G/T data only. Historical M25–M28 results are not modified.

## Decision

**No production promotion.** The M19 production defaults and frozen support thresholds are unchanged.

## Historical root-cause evidence

M27 identifies low-complexity triage as the demonstrated reason three positive M25-03 cases had zero assembly-eligible reads. The nine target-absent controls are expected not to contain target reads; they are not failed positive recoveries.

The M28 SPAdes exit-21 record has no persisted stderr bytes and does not establish an operating-system cause. The five incomplete supported assemblies remain unexplained by the available evidence. Missing historical experimental FASTQ/SAM inputs prevent a read-level explanation for the 60 unsupported experimental contigs.

## M29 benchmark

- Cases: 17 (13 positive; 4 target-absent control).
- Demonstrated exact synthetic recoveries: 6; per-contig read-supported exact recoveries: 6.
- Held-out read-supported exact recoveries: 3.
- Confirmatory fresh-seed held-out B recoveries: 1.
- Target-absent raw contigs: 0; read-supported target-absent contigs: 0.
- Configuration B target-absent raw contigs: 1; read-supported background contigs: 1.
- Accepted false-positive satellite-virus candidates: NOT_EVALUATED; M29 did not run downstream discovery-specific candidate screening.
- False-positive discovery rates remain unknown; assembly and read support are not candidate acceptance.
- Historical checked-in benchmark findings are distinct from results freshly reproduced by this revision; see the JSON replay comparison.
- The prior PR-head summary and all 17 case-level historical run records are preserved separately in the JSON `historical_run_record` field.
- M29 success criterion met: False.
- Truth is read only after each registered M19 workflow run for retrospective scoring.
- The earlier exploratory B pilot is excluded from confirmation; the counted held-out validation uses a distinct deterministic seed.
- Reduced-coverage failures with an SPAdes invalid k-mer coverage histogram are attributed to the observed coverage-model failure only; no operating-system cause is inferred.

| Case | Split | Factor | Eligible reads | Raw contigs | Supported contigs | Exact | Supported exact | Partial | Candidate acceptance |
|---|---|---|---:|---:|---:|---|---|---|---|
| development-m29-positive_control | development | positive_control | 720 | 1 | 1 | True | True | False | NOT_EVALUATED |
| development-m29-repeat_challenge | development | repeat_challenge | 720 | 1 | 0 | False | False | False | NOT_EVALUATED |
| development-m29-target_absent_negative | development | target_absent_negative | 0 | 0 | 0 | False | False | False | NOT_EVALUATED |
| tuning-m29-reduced_coverage | tuning | reduced_coverage | 108 | 0 | 0 | False | False | False | NOT_EVALUATED |
| tuning-m29-short_reads | tuning | short_reads | 1440 | 1 | 1 | True | True | False | NOT_EVALUATED |
| tuning-m29-sequencing_errors | tuning | sequencing_errors | 720 | 1 | 1 | False | False | True | NOT_EVALUATED |
| tuning-m29-synthetic_background | tuning | synthetic_background | 720 | 1 | 1 | True | True | False | NOT_EVALUATED |
| tuning-m29-target_absent_negative | tuning | target_absent_negative | 0 | 0 | 0 | False | False | False | NOT_EVALUATED |
| held_out-m29-positive_control | held_out | positive_control | 720 | 1 | 1 | True | True | False | NOT_EVALUATED |
| held_out-m29-reduced_coverage | held_out | reduced_coverage | 108 | 0 | 0 | False | False | False | NOT_EVALUATED |
| held_out-m29-short_reads | held_out | short_reads | 1440 | 1 | 1 | True | True | False | NOT_EVALUATED |
| held_out-m29-repeat_challenge | held_out | repeat_challenge | 720 | 1 | 0 | False | False | False | NOT_EVALUATED |
| held_out-m29-sequencing_errors | held_out | sequencing_errors | 720 | 1 | 1 | False | False | True | NOT_EVALUATED |
| held_out-m29-synthetic_background | held_out | synthetic_background | 720 | 1 | 1 | True | True | False | NOT_EVALUATED |
| held_out-m29-low_coverage_validation | held_out | low_coverage_validation | 108 | 0 | 0 | False | False | False | NOT_EVALUATED |
| held_out-m29-low_coverage_target_absent_background | held_out | low_coverage_target_absent_background | 108 | 0 | 0 | False | False | False | NOT_EVALUATED |
| held_out-m29-target_absent_negative | held_out | target_absent_negative | 0 | 0 | 0 | False | False | False | NOT_EVALUATED |

## Matched configuration experiment

tuning: `tuning-m29-reduced_coverage`. Eligible-read input identity matched: `True`.

| Configuration | Status | Raw contigs | Read-supported contigs | Exact recovery | Supported exact | Accepted false-positive candidates |
|---|---|---:|---:|---|---|---|
| A: registered default | EXECUTION_FAILED | 0 | 0 | False | False | NOT_EVALUATED |
| B: SPAdes k=21 only | COMPLETED | 1 | 1 | True | True | NOT_EVALUATED |

held_out: `held_out-m29-low_coverage_validation`. Eligible-read input identity matched: `True`.

| Configuration | Status | Raw contigs | Read-supported contigs | Exact recovery | Supported exact | Accepted false-positive candidates |
|---|---|---:|---:|---|---|---|
| A: registered default | EXECUTION_FAILED | 0 | 0 | False | False | NOT_EVALUATED |
| B: SPAdes k=21 only | COMPLETED | 1 | 1 | True | True | NOT_EVALUATED |

negative_control: `held_out-m29-low_coverage_target_absent_background`. Eligible-read input identity matched: `True`.

| Configuration | Status | Raw contigs | Read-supported contigs | Exact recovery | Supported exact | Accepted false-positive candidates |
|---|---|---:|---:|---|---|---|
| A: registered default | EXECUTION_FAILED | 0 | 0 | False | False | NOT_EVALUATED |
| B: SPAdes k=21 only | COMPLETED | 1 | 1 | False | False | NOT_EVALUATED |

B is an isolated experiment on matched synthetic reads. It produced one read-supported background contig in the target-absent control; this is not an accepted satellite-virus candidate. Candidate screening was not evaluated, so specificity and the false-positive discovery rate remain unknown. B does not alter production parameters; the decision remains NO_PROMOTION.

## Verification and limitations

Fresh run status: `fresh_clean_execution`; full fixed matrix executed: `True`. Replay comparison: `MATCHED_STABLE_FIELDS`.
Compared 17 cases on fixed case identity, truth/input digests, parameters, and assembly-graph SHA-256. See JSON for per-case results.

Reproduce with `python -m satellite_discovery.m29_assembly_root_cause_recovery --output /tmp/m29-evidence --repository-root .`. The output directory must be new or empty; generated assembler work products stay outside Git.

The JSON companion contains per-stage read counts, support statuses, sequence digests, and historical evidence references. Assembly completion is not biological discovery. Results on synthetic controls do not establish performance on biological samples.

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
