# M35 — Synthetic Candidate Specificity and Assembly Failure Root-Cause Analysis

**Status: INCOMPLETE.** This document records the verified M34 baseline and the
M35 preregistration scaffold. It does not report completed M35 experiments.

## Governance and frozen settings

The required governance state remains:

- `decision=INCOMPLETE`
- `overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`
- `biological_execution_authorized=false`

No biological data or external biological reference data were used. M6 and M8
settings and M31 thresholds remain unchanged. No production promotion is
proposed.

## Preregistered specificity design

The planned synthetic similarity levels are 100%, 98%, 95%, 92%, 90%, 85%,
80%, and 70%, with three independent sequence-family seeds. The 100% condition
is an exact positive control; target-absent decoys use the remaining levels.
Truth is assigned independently of similarity, and held-out truth must remain
outside screening and prioritisation inputs.

The planned frozen panel SHA-256 is
`ced54090aadd76a48642cce73ee72bb749b198f5a2be90ab921ad489744140df`.
The development, tuning, and held-out assignment is by independent family.
The current code adds validation for the design matrix and held-out truth
separation, but the M35 similarity-gradient benchmark has **not** been run.

## M34 false-alarm baseline

The M34 Actions artifact reports 5 `REVIEW_PRIORITY` outcomes among 35
eligible target-absent cases. All five eligible near-target-divergence cases
were prioritised (5/5); three of eight generated cases in that category were
unevaluable. The five case IDs are:

| Case | M34 observation |
|---|---|
| `development-m34-c0049` | 90.268% identity to `SYN006.1`, 99.3% query coverage |
| `tuning-m34-c0050` | 90.000% identity to `SYN006.1`, full query coverage |
| `held_out-m34-c0051` | 90.089% identity to `SYN006.1`, full query coverage |
| `development-m34-c0052` | 90.000% identity to `SYN006.1`, full query coverage |
| `tuning-m34-c0056` | 90.000% identity to `SYN006.1`, full query coverage |

Their registered source truth is target-absent. These observations describe
synthetic specificity only and are not a biological false-discovery rate.
M35 has not yet independently reproduced the five cases from the frozen
pipeline.

## M34 assembler-failure baseline

The M34 artifact records four SPAdes exit-code-21 failures, all with the
`invalid kmer coverage histogram` error. The substitution-only failure is
included, so indels alone cannot explain the observed failures.

| Condition | Read length | Nominal coverage | Realised substitutions / insertions / deletions |
|---|---:|---:|---:|
| `substitution_only` | 100 | 48 | 864 / 0 / 0 |
| `combined_low` | 75 | 24 | 304 / 113 / 120 |
| `combined_moderate` | 100 | 48 | 896 / 451 / 449 |
| `combined_higher` | 150 | 80 | 3,968 / 2,132 / 2,233 |

These are assembler execution failures, not measured reconstruction losses.
M35 has not yet performed the one-factor-at-a-time coverage, read-length,
error-rate, terminal-coverage, read-sampling, and background-composition
experiments required to identify a root cause.

## M35 work not yet completed

- Independently reproduce the M34 alarms and four SPAdes failures.
- Run the registered similarity gradient through assembly, measured read
  support, frozen M8 screening, and frozen M31 triage.
- Compare the registered evidence features without changing triage behavior.
- Run controlled SPAdes diagnostics and separately namespaced alternatives.
- Repeat cases in fresh output directories and compare normalized evidence.
- Add complete provenance, leakage, failure-classification, and summary-drift
  checks; run M29–M34 regressions and final-head GitHub Actions.

Until those experiments and validations complete, the M35 results are
**NOT_RUN**, and no scientific success claim is made.
