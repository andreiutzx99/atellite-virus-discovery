# M21 Phase 8 — Synthetic Scientific Validation

## Executive summary

The registered M20 synthetic workflow completed 10 seeded cases through
M4→M6, M7, M8/M9/M10, M12/M15 and the final Phase 5 report. Repeating Phase 4
produced the same semantic digest. Phase 5 validated software integration but
explicitly left biological discovery `NOT_VALIDATED`.

The six-case M19 matrix ran twice with matching recovery, candidate and M6
diagnostic outcomes. Two cases hit actual SPAdes reconstruction errors, so their
zero-candidate results are execution failures, not evidence that the targets
are unrecoverable. All results remain synthetic software evidence.

**M21 Phase 8: TECHNICAL IMPLEMENTATION COMPLETE.** This is a software and
synthetic-evidence completion status only; biological discovery is not validated.
Governance remains `decision=INCOMPLETE` and
`overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`; biological execution remains
unauthorized.

## Pipeline status

M19 reuses the existing M4 QC and M6 residual-evidence workflow. Held-out labels
and target sequences stay outside the analysis graph and are used only for
post-run scoring. M1–M20 implementation behavior was not changed.

Separately, the registered M20 Phase 2B→3→4→5 workflow passed on artificial
fixtures. It exercised M4/M6 and M7, followed by M8/M9/M10, M12/M15, and the
final integration report. The M20 Phase 5 result is
`SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED`. No biological
identity, function, novelty, or helper dependence is inferred.

M20 ran 10 cases with 10 distinct read seeds (8 positives, 2 target-absent
controls). Every case had 30 accepted M15 producer bindings from M6/M7/M8/M9/
M10/M12. M13/M14 were absent. The Phase 4 semantic digest matched across its
primary and replay runs; current M12 invalid findings: 0.
Digest: `0265d7b54c599ce9edc9b472b81b14d131d38678632a6f12ee90a8c91fc9c267`.

### M20 per-case read-to-report trace

Each seed identifies the synthetic read realization. The final 30-record M15
binding set for each case spans producer milestones M6/M7/M8/M9/M10/M12; the
SHA-256 below is computed over its producer, artifact and digest bindings.

| Case | Role | Read seed | M4/M6 | M7 | M8/M9 ORF/M9 BLASTP/M10 | M12/M15 | Bindings | M15 trace SHA-256 |
|---|---|---:|---|---|---|---|---:|---|
| c001 | positive | 20262117 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `7a8d64c0dab977ebfe7cf8922f01bb1b8ff6d1d4b600e650ec2022403034e404` |
| c002 | positive | 20262118 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `ba5b46a8d0188c6eef1f0bd5391222b2e86abaf1c4526b2fa2e215f071da2204` |
| c003 | positive | 20262119 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `cf0b2d9f5d047d1e681ec335ed2dce9cb457f1e32bb2b7d62240b4e285d58810` |
| c004 | positive | 20262120 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `04d795e1de961dac7e518b51cfe1f25028c1216cc39384d47e95bd12a353749b` |
| c005 | positive | 20262121 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `26549373a6a1d82a00f259aaf2f41285b0741887d063678d7547303bee39b12c` |
| c006 | positive | 20262122 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `4738c77d2bc68fbdac573721448cf27e621feff261d71bb948ed7cc2af7a7b7c` |
| c007 | positive | 20262123 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `5181ade7a3f26e867a99f0de786c9947f798d30593d2493cd59f4b0385a122b4` |
| c008 | positive | 20262124 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `0cb211f3596bc73f0a7b7feeef90f8b1f2ea9fe98fc48dcbb1651334fcfd9994` |
| c009 | negative control | 20262125 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `65d32e92c304056376decc8ad0df47e9cabd278467b462c2d7c0202eda1bd306` |
| c010 | negative control | 20262126 | complete/complete | complete | complete/complete/complete/complete | complete/complete | 30 | `ce4349458bf1c71ce81a42a8dcacbb360cd738ec42477e27fcf666ce74c3ff5a` |

## Synthetic benchmark results

The benchmark contains five positive cases and one negative control. Each
condition has one fixed-seed realization. All sequences are artificial A/C/G/T
strings; no biological sequencing data or authentic pathogen-associated
sequence was used.

| Case | Expected target | M4/M6 state | Exact recovery | Partial candidates | Candidates | False candidates |
|---|---:|---|---:|---:|---:|---:|
| Baseline | Yes | Complete | Yes | 0 | 1 | 0 |
| High error (5%) | Yes | Workflow complete; reconstruction failed | No | 0 | 0 | 0 |
| Low nominal coverage (16×) | Yes | Workflow complete; reconstruction failed | No | 0 | 0 | 0 |
| High reference divergence (45%) | Yes | Complete | Yes | 0 | 1 | 0 |
| High repeat complexity | Yes | Complete | No | 0 | 1 | 1 |
| Negative control | No | Complete | N/A | N/A | 0 | 0 |

### Aggregate metrics

- **Synthetic target detection:** 2/5 (40%); this counts observed candidates, while two other positives hit SPAdes execution failures.
- **Exact full-sequence recovery:** 2/5 (40%).
- **Partial recovery:** 0/5 cases. A partial candidate must be non-exact, at least
  95% local identity, and cover at least 50% of the held-out target.
- **Candidate-level exact precision:** 2/3 (66.7%).
- **Negative-control specificity:** 1/1 (100%) in this single negative control.
- **False positives:** one non-exact candidate in the high-repeat positive case;
  none in the single negative control.

The recovered baseline and high-divergence candidates each had 100% identity and
100% target coverage. The high-repeat case emitted a 65-nt candidate with
72.86% identity over 8% target coverage. M6 read-back reported
`NO_SUPPORTED_ASSEMBLY`; the candidate is a false positive against held-out
synthetic truth and is not a partial recovery.

High-error and low-coverage M6 reconstruction both reported
`EXECUTION_FAILED`, while read support was `NOT_EVALUATED`. SPAdes logged
`Invalid kmer coverage histogram, make sure that the coverage is indeed uniform`
and exited with return value 21. The high-error case had 480 assembly-eligible
residual fragments; low coverage had 128. These are assembler execution
failures, not evidence that target sequences were absent or unrecoverable.

### SPAdes root-cause investigation

Both failures used the same available SPAdes 4.1.0 runtime and M6 invocation:
single-end `--only-assembler`, one thread, a 2-GiB tool memory limit, and
automatic k selection from 100-nt reads. The generated M19 reads were
deterministically and evenly spaced rather than randomly sampled: 480
assembly-eligible 100-nt reads (60× nominal target coverage) in high-error,
and 128 reads (16×) in low-coverage. The error was raised in the K55 stage at
SPAdes' `EC Threshold Finding`; K21 and K33 had already run. The process exited
quickly with code 21, not a timeout or memory-limit error.

An isolated, separately labelled full M19 experiment held the generated inputs,
SPAdes 4.1.0, memory, thread count, and registered M4/M6 read-back path fixed,
changing only the k-mer list from automatic 21/33/55 to 21/33. Both former
execution failures then completed assembly. This isolates the failure to the
K55 coverage-histogram stage for these synthetic inputs, rather than missing
tools, malformed FASTQ, or general SPAdes/runtime incompatibility. It does not
establish a general SPAdes defect or prove which property of the synthetic
k-mer spectrum triggers the upstream histogram guard.

| Experimental case | SPAdes/M6 result | Truth comparison | Disposition |
|---|---|---|---|
| High error | Assembly completed; read-back supported | 794-nt contig; 99.87% local identity and 99.25% target coverage | One threshold-qualified partial candidate; not exact |
| Low coverage | Assembly completed; read-back supported | 800-nt contig; 52.51% local identity and 99.0% target coverage | Unsupported candidate; below the fixed 95% identity threshold |

Across the six-case experiment, exact recovery remained 2/5, partial recovery
increased from 0/5 to 1/5, execution failures fell from two to zero, and
non-exact candidates increased from one to three. The low-coverage candidate
was supported by the same reads used to assemble it, but did not match held-out
truth sufficiently to qualify as a partial recovery. Two candidates failed the
fixed partial-recovery thresholds. The negative control remained candidate-free.

No production k-mer change was adopted: the experimental setting trades the
two assembler errors for more unsupported predictions and does not improve
exact recovery. The original six-case M19 baseline and M1–M20 assembler
configuration remain unchanged. The failures are adequately characterized for
Phase 8 technical completion, but remain limitations of the baseline result.

The numeric rates are descriptive software metrics only. One negative control
is insufficient to validate specificity; no confidence intervals, runtime, or
memory measurements are claimed. These results should not be generalized to
biological samples or other sequence families.

## Reproducibility

Two independent executions produced identical semantic signatures including
fixed-seed inputs, held-out truth, per-case M6 reconstruction/read-support
states, recovery, candidate sequence digests, alignment metrics, and false
positive counts:

`e3791869aba2fb708bcb18182a41bc8a26acf82620f4822e2c5febebdef45bcd`

Run-specific timestamps and filesystem paths are excluded from that comparison.
The signature verifies equality for these two synthetic runs; it is not
independent scientific validation.

## Improvements implemented

- Added a Phase 8 command that runs the existing M19 path twice and writes
  machine-readable JSON and Markdown reports.
- Added local-alignment identity and truth-coverage reporting so exact and
  partial recovery are separated.
- Added semantic reproducibility checks including M6 reconstruction and read-support states.
- Ran the registered M20 synthetic pipeline through the final Phase 5 report and replayed Phase 4.
- Recorded SPAdes failure diagnostics and residual counts for the two M19 assembly failures.
- Added tests for partial alignment metrics, exact scoring, negative-control
  metrics, incomplete-evidence handling, and artifact path containment.

## Recommendation disposition

| Status | Recommendation and evidence |
|---|---|
| Reused | Fixed-seed synthetic controls and M19 held-out truth scoring; two baseline runs matched including M6 failure states. |
| Implemented | Exact/partial recovery, identity/coverage, M6 reconstruction/read-support states, and failure diagnostics. |
| Implemented | Registered M20 synthetic M4→M15 and Phase 5 report; Phase 4 semantic replay matched. |
| Evaluated; not adopted | Isolated SPAdes `-k 21,33` experiment completed the two failing assemblies but increased unsupported predictions without improving exact recovery. |
| Deferred | M5, M13, M14, and M10 JSONL handoffs; current producer contracts do not supply or accept them, and were not changed. |
| Satisfied | M21 Phase 4 synthetic streaming validator and bounded checks remain in place; they do not establish biological suitability. |
| Future research | Evaluate randomized read starts, multiple seeds, coverage/error ranges, and more negative controls before generalizing M19 recovery or SPAdes k-mer behavior. |
| Deferred pending authorization | Biological reads, data-use permission, library adequacy, independent truth labels, and reference-exclusion review. |
| Deferred pending authorization | Production reviewer trust, blind-key custody, authenticated approvals, and independently retained audit checkpoints. |
| Satisfied | M21 remains `INCOMPLETE` and `BLOCKED_FOR_BENCHMARK_EXECUTION`; biological execution remains unauthorized. |

No scoped TODO/FIXME markers were found in M20/M21 documentation, milestone
modules, or related tests. The sole repository-wide match is an unrelated
infrastructure-status note.

## Tests and CI

The 9 focused Phase 8 tests pass locally, including M6 execution-failure
diagnostics. Full repository discovery passed: 1,087 tests, 21 skipped. On
implementation commit `5a022bb18e3127bf9b744bf1764b6e01dce51b5c`, both GitHub
Actions runs completed successfully with 11/11 jobs each. PR #88 remains open
and draft for human review.

## Readiness assessment

| Dimension | Assessment |
|---|---|
| Software implementation | Complete: M20 registered pipeline completed 10 synthetic cases through M15 and Phase 5; M19 baseline failures were reproduced and characterized, and unsupported candidates remain explicitly classified |
| Synthetic benchmark | M19: 6 cases, 5 positive and 1 negative; M20: 10 cases, 8 positive and 2 target-absent |
| Reproducibility | M19 semantic equality includes M6 execution states; M20 Phase 4 replay digest matched |
| Scientific validity | Not established; one synthetic realization per condition and one negative control |
| M21 governance | `INCOMPLETE`; benchmark execution remains `BLOCKED_FOR_BENCHMARK_EXECUTION` |
| Operational authorization | Biological execution is not authorized |

M21 Phase 8 technical implementation is **COMPLETE**. The original M19
baseline remains intact, and the experimental k-mer setting was not promoted.
This conclusion does not imply biological validation: M21 governance remains
`decision=INCOMPLETE`, `overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`, and
`biological_execution_authorized=false`.
