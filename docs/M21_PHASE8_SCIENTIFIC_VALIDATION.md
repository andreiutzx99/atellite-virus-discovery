# M21 Phase 8 — Synthetic Scientific Validation

## Executive summary

The existing M4 quality-control → M6 residual-evidence and assembly path completed
the six-case fixed-seed M19 synthetic matrix twice, with identical semantic
results. It recovered 2 of 5 planted artificial targets exactly (40%) and
produced no candidates meeting the declared partial-recovery threshold. One
non-exact, short repeat-derived candidate was produced. This is evidence about
the bounded software path only; it is not a biological performance estimate.

**Phase 8 status: INCOMPLETE.** The full discovery workflow through candidate
classification and final evidence/report integration was not demonstrated, and
the wider M20/M21 recommendation backlog was not fully reviewed. Governance
remains `decision=INCOMPLETE` and
`overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`; biological execution remains
unauthorized.

## Pipeline status

The benchmark reuses M19’s existing M4 QC and M6 residual-evidence workflow,
including reference screening, assembly, candidate extraction, and read support.
Held-out labels and target sequences remain outside the analysis graph and are
used only for post-run scoring. M1–M20 implementation behavior was not changed.

This is not the complete M1–M20 pipeline requested for Phase 8: downstream
candidate classification and final evidence integration are absent from the
M19 benchmark graph. No biological identity, function, novelty, or helper
dependence is inferred from a candidate.

Separately, the existing M20 Phase 2 live integration test passed through its
registered M4→M6→M7 recurrence handoff on synthetic fixtures. That test is
additional software integration evidence, but it does not establish biological
candidate classification and is not folded into the M19 recovery rates above.

## Synthetic benchmark results

The benchmark contains five positive cases and one negative control. Each
condition has one fixed-seed realization. All sequences are artificial A/C/G/T
strings; no biological sequencing data or authentic pathogen-associated
sequence was used.

| Case | Expected target | M4/M6 state | Exact recovery | Partial candidates | Candidates | False candidates |
|---|---:|---|---:|---:|---:|---:|
| Baseline | Yes | Complete | Yes | 0 | 1 | 0 |
| High error (5%) | Yes | Complete | No | 0 | 0 | 0 |
| Low nominal coverage (16×) | Yes | Complete | No | 0 | 0 | 0 |
| High reference divergence (45%) | Yes | Complete | Yes | 0 | 1 | 0 |
| High repeat complexity | Yes | Complete | No | 0 | 1 | 1 |
| Negative control | No | Complete | N/A | N/A | 0 | 0 |

### Aggregate metrics

- **Synthetic target detection:** 2/5 (40%); only exact recoveries count as detections here.
- **Exact full-sequence recovery:** 2/5 (40%).
- **Partial recovery:** 0/5 cases. A partial candidate must be non-exact, at least
  95% local identity, and cover at least 50% of the held-out target.
- **Candidate-level exact precision:** 2/3 (66.7%).
- **Negative-control specificity:** 1/1 (100%) in this single negative control.
- **False positives:** one non-exact candidate in the high-repeat positive case;
  none in the single negative control.

The recovered baseline and high-divergence candidates each had 100% identity and
100% target coverage. The high-repeat candidate was 65 nt, with 72.86% best
local identity over 8% target coverage; it is not a partial recovery under the
declared threshold. The high-error and low-coverage cases produced no
candidate. These single observations do not establish why those cases failed.

The numeric rates are descriptive software metrics only. One negative control
is insufficient to validate specificity; no confidence intervals, runtime, or
memory measurements are claimed. These results should not be generalized to
biological samples or other sequence families.

## Reproducibility

Two independent executions produced identical semantic signatures for the
fixed-seed source manifest, held-out truth, per-case status and recovery,
candidate sequence digests, alignment metrics, and false-positive counts:

`b8db3e053f27a45845ecc753fbadfb3b2faa1504dc2ee501bfb5b61d093eda4c`

Run-specific timestamps and filesystem paths are excluded from that comparison.
The signature verifies equality for these two synthetic runs; it is not
independent scientific validation.

## Improvements implemented

- Added a Phase 8 command that runs the existing M19 path twice and writes
  machine-readable JSON and Markdown reports.
- Added local-alignment identity and truth-coverage reporting so exact and
  partial recovery are separated.
- Added semantic reproducibility checks including candidate sequence digests.
- Added tests for partial alignment metrics, exact scoring, negative-control
  metrics, incomplete-evidence handling, and artifact path containment.

## Recommendation disposition

- **Reused:** fixed-seed synthetic positives/negative, M4→M6 stages, and strict
  exact truth scoring from M19.
- **Implemented:** separate exact and thresholded partial recovery reporting,
  candidate identity/coverage, and repeat-run semantic comparison.
- **Deferred:** connect the current M4→M6 benchmark to all downstream candidate
  classification and evidence-report stages.
- **Not reviewed:** the complete M20/M21 recommendation backlog. This report
  does not claim that every prior recommendation has been dispositioned.

## Tests and CI

The Phase 8 validation tests (7) and M19 benchmark tests (10 passed, 1
optional live-test skipped) passed locally. Full repository discovery passed
with 1,084 tests and 21 skips; the live M20 Phase 2 M4→M6→M7 test passed.
GitHub Actions for the current PR commit remain the release check; consult
PR #88 for their commit-specific status.

## Readiness assessment

| Dimension | Assessment |
|---|---|
| Software implementation | Existing M4→M6 path works for this synthetic matrix; full requested end-to-end path is not demonstrated |
| Synthetic benchmark | Completed; 6 cases, 5 positive and 1 negative |
| Reproducibility | Two-run semantic equality demonstrated |
| Scientific validity | Not established; one synthetic realization per condition and one negative control |
| M21 governance | `INCOMPLETE`; benchmark execution remains `BLOCKED_FOR_BENCHMARK_EXECUTION` |
| Operational authorization | Biological execution is not authorized |

Phase 8 does not meet its technical acceptance criteria and is reported as
`INCOMPLETE`. Passing software tests or synthetic benchmarks do not change
operational authorization.
