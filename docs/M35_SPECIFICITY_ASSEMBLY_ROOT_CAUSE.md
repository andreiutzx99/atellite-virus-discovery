# M35 — Synthetic Candidate Specificity and Assembly Failure Root-Cause Analysis

**Status: INCOMPLETE — pending independent review.** M34 was independently
reproduced, and the registered synthetic M35 similarity gradient and SPAdes
one-factor comparisons were run. Results remain diagnostic, not biological
claims.

## Governance and frozen settings

The required governance state remains:

- `decision=INCOMPLETE`
- `overall_state=INCOMPLETE_PENDING_INDEPENDENT_REVIEW`
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
The M35 design was executed with three registered sequence-family seeds. Its
design SHA-256 is
`ce1e5ebbc112416023cec48735977ee676012172974523d7109e3f19ca0ba54a`.

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
M35 independently reproduced all five cases (5/5; Wilson 95% interval
0.566–1.000). This is a small synthetic benchmark, not a biological
false-discovery-rate estimate.

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
M35 independently reproduced all four (4/4; Wilson 95% interval 0.510–1.000).

## M35 similarity gradient

The Actions artifact reports 21 target-absent decoys and three exact positive
controls. Every decoy case was evaluable. All three decoys at 98%, 95%, 92%,
and 90% similarity were `REVIEW_PRIORITY`; none of the three at 85%, 80%, or
70% was. Wilson 95% intervals use independent seed-family cases as the unit:

| Similarity | Truth stratum | Eligible / generated | Unevaluable | `REVIEW_PRIORITY` | Wilson 95% |
|---:|---|---:|---:|---:|---:|
| 100% | exact positive control | 0 / 3 | 3 | 0 | not estimable |
| 98% | target-absent decoy | 3 / 3 | 0 | 3 | 0.439–1.000 |
| 95% | target-absent decoy | 3 / 3 | 0 | 3 | 0.439–1.000 |
| 92% | target-absent decoy | 3 / 3 | 0 | 3 | 0.439–1.000 |
| 90% | target-absent decoy | 3 / 3 | 0 | 3 | 0.439–1.000 |
| 85% | target-absent decoy | 3 / 3 | 0 | 0 | 0.000–0.561 |
| 80% | target-absent decoy | 3 / 3 | 0 | 0 | 0.000–0.561 |
| 70% | target-absent decoy | 3 / 3 | 0 | 0 | 0.000–0.561 |

The three exact positive controls had no supported assembly, so they are
unevaluable rather than negative results. The feature diagnostics show
qualifying target-role alignments in all three decoys at 98–90%, and none at
85–70%; the frozen M31 triage behavior and thresholds were unchanged.

Fresh-directory repeatability was `REPRODUCIBLE` for all eight held-out
conditions: 8/8 had identical read-provenance hashes and 8/8 had matching
pipeline outcomes.

## Controlled SPAdes comparisons

The registered matrix contains 14 settings including the baseline, with two
technical repeats each (28 executions total):

| Factor | Level | SPAdes execution failures | Read-supported assemblies |
|---|---:|---:|---:|
| baseline (`combined_moderate`) | — | 2/2 | 0/2 |
| coverage | 24 | 2/2 | 0/2 |
| coverage | 80 | 2/2 | 0/2 |
| read length | 75 | 2/2 | 0/2 |
| read length | 150 | 2/2 | 0/2 |
| substitutions | 0.0 | 0/2 | 2/2 |
| substitutions | 0.01 | 2/2 | 0/2 |
| substitutions | 0.05 | 2/2 | 0/2 |
| insertions | 0.0 | 2/2 | 0/2 |
| insertions | 0.005 | 2/2 | 0/2 |
| insertions | 0.03 | 2/2 | 0/2 |
| deletions | 0.0 | 2/2 | 0/2 |
| deletions | 0.005 | 2/2 | 0/2 |
| deletions | 0.03 | 2/2 | 0/2 |

The 26 failures reported
`Invalid kmer coverage histogram; SPAdes advises checking coverage
uniformity.` No OAT replicate was `NOT_RUN`. The 13 comparisons against
baseline are descriptive only and do not establish a causal assembler
mechanism.

Separately namespaced alternative assembler configurations are **NOT_RUN**:
none was registered in the M35 design, so executing one would require a new
registered design. Do not infer an alternative-assembler result from the
SPAdes comparisons.

## Evidence provenance

The M35 evidence is from Actions run `42815490595`, commit
`41962cc3a5bef690b8715feb7e35b74381860f40`, artifact
`13765202624` (`m35-synthetic-investigation`). The artifact ZIP SHA-256 is
`3abf0833ec7f21b879748024072c73fc9170987548a3fa9adc61cab341a8cf49`.

The raw M32 report SHA-256 is
`d219ab29546495a9040b3952a2b5b2864f9841a0ad1afd83295ee738bb154a01`;
the read-provenance index SHA-256 is
`03706b62bf133df69d0e3629af86d2a075095b51ce2abda086245b583c924bcc`;
and the target-absence validation SHA-256 is
`330c26876d3acee9b42b5d73c22085a5672bdc6f5300c71a13660b22beb2727e`.
The frozen panel SHA remains
`ced54090aadd76a48642cce73ee72bb749b198f5a2be90ab921ad489744140df`.

M6 and M8 settings and M31 thresholds remain unchanged. The artifact contains
case-level evidence, denominators, uncertainty intervals, failure statuses,
and provenance hashes. Full CI passed on implementation head
`41962cc3a5bef690b8715feb7e35b74381860f40` (run `42815487458`); GitHub Actions
is rerun after this tracked-report update. Independent review remains pending;
no causal assembler mechanism or biological specificity claim is made.
