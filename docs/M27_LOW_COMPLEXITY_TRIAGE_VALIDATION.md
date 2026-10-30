# M27 synthetic low-complexity triage validation

## Scope and decision

This is a synthetic-only diagnostic of the unchanged M25 read-coverage
benchmark at merged M26 commit
`a2c654e59eeca4e6b35c3e34ead937cd98e3889b`. No biological sequencing data or
external biological references were used. M1–M26 behavior and governance were
not changed.

**Decision: retain the existing M6 triage default.** Lowering its Shannon
entropy cutoff did not produce exact or partial target reconstruction in any
of the nine paired runs. Two lower-threshold held-out runs emitted candidates,
including unsupported and low-support candidates. Development and tuning
assembler executions failed for both experimental settings. These results do
not establish that low-complexity reads are invalid or that any candidate is
biological.

## Baseline reproduction

The fixed-seed M25 run completed all 18 cases: 9 positives and 9 target-absent
controls. All three M24 input-manifest digests matched. The baseline reproduced
0 exact recoveries, 2 partial recoveries, 0 SAM validation failures, 1
assembler execution failure, and 0 negative-control candidates. The existing
governance state remains incomplete and blocks biological benchmark execution.

## M25-03 read-flow audit

The audit classified target reads only by the exact generated ID pattern
`m2503-r` followed by five digits. Reference-read identifiers were excluded
from target counts. Target placement against held-out synthetic truth was
performed retrospectively for diagnostics only; truth was not supplied to the
workflow.

| Split | Target reads generated | Target reads after QC | Target reads after screen | Default assembly-eligible target reads | Truth coverage after QC → after screen |
|---|---:|---:|---:|---:|---:|
| Development | 747 | 747 | 2 | 0 | 11.0% → 10.8% |
| Tuning | 267 | 267 | 265 | 0 | 30.8% → 30.8% |
| Held out | 747 | 747 | 673 | 0 | 11.0% → 11.0% |

The remaining target reads in each split were excluded by low sequence
complexity under the default rule. QC rejected no reads in these three cases.
The resulting assembly eligibility was zero in all three. These are synthetic
read-flow observations, not evidence about real sequencing quality.

## Paired triage experiments

Only `min_entropy_bits` changed: A retained the existing value (1.2), B used
0.95, and C used 0 as a diagnostic lower bound. Screening, read identity,
support thresholds, and other triage criteria were unchanged. Every
experimental input manifest matched its baseline counterpart.

| Split | Setting | Eligible reads | Assembler status | Exact / partial reconstruction | Candidates (unsupported; low-support) |
|---|---|---:|---|---|---:|
| Development | A: default 1.2 | 0 | No supported assembly | No / No | 0 (0; 0) |
| Development | B: 0.95 | 1 | Execution failed | No / No | 0 (0; 0) |
| Development | C: 0 | 2 | Execution failed | No / No | 0 (0; 0) |
| Tuning | A: default 1.2 | 0 | No supported assembly | No / No | 0 (0; 0) |
| Tuning | B: 0.95 | 175 | Execution failed | No / No | 0 (0; 0) |
| Tuning | C: 0 | 265 | Execution failed | No / No | 0 (0; 0) |
| Held out | A: default 1.2 | 0 | No supported assembly | No / No | 0 (0; 0) |
| Held out | B: 0.95 | 504 | Read-supported assembly | No / No | 6 (1; 2) |
| Held out | C: 0 | 673 | Read-supported assembly | No / No | 7 (1; 2) |

The increase in eligible reads is expected from lowering the threshold; it is
not itself an improvement. The held-out candidates did not recover the target
exactly or partially, and candidate support labels remain distinct from
assembly execution and target recovery. The small, fixed synthetic design does
not justify changing the production default.

## Limits and artifacts

Entropy, k-mer diversity, periodicity, homopolymer length, and retrospective
truth placement are diagnostics, not stand-alone validity criteria. The
experiment is not a biological sensitivity/specificity estimate, and does not
authorize biological execution or change governance.

The compact machine-readable summary is
[`M27_LOW_COMPLEXITY_TRIAGE_VALIDATION.json`](M27_LOW_COMPLEXITY_TRIAGE_VALIDATION.json).
The full per-read diagnostic output was generated outside the repository during
the run and is not part of the committed source tree.

## M20 and test cross-checks

The synthetic M20 Phase 2B runner completed all 10 prespecified cases: five
produced read-supported assemblies, five assembler executions failed, and none
recovered the full target exactly. Phase 3 completed its 10-case handoff. The
M8 nucleotide search remained unavailable because the installed BLAST+ 2.16.0
binary did not match the stage's approved 2.17.0+ executable pin; this is not a
completed no-hit result. M9 BLASTP ran, and M10 reported partial aggregate
results. All M20 inputs and reference panels were artificial.

The focused M27 tests passed (3 tests). The focused M20 Phase 1/2B/3 set passed
(18 tests, including its live synthetic integrations). A broad test discovery
run exceeded the five-minute command limit and was terminated before producing
a suite summary, so the full repository suite is not reported as passing.
