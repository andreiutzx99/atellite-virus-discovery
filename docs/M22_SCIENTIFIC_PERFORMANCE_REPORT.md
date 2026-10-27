# M22 Scientific Performance Report

## Scope and safety

All fixtures in this report are generated artificial A/C/G/T sequences. No
biological read datasets, authentic pathogen-associated sequences, or external
reference sequences were accessed. M21 governance remains unchanged:
`decision=INCOMPLETE`, `overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`, and
`biological_execution_authorized=false`.

## Reproduced M21/M19 baseline

The original six-case M19 benchmark was run twice with its original inputs,
scoring, and default M6 configuration. Both runs produced the same per-case
outcome vector and the same generated-input manifest SHA-256:
`fb6d9003164d858534b9f33416f0f9d11dd6aba139eb7e22352b2d7089c3f625`.

| Baseline outcome | Result |
|---|---:|
| Positive cases | 5 |
| Exact recoveries | 2/5 |
| Threshold-qualified partial recoveries | 0/5 |
| SPAdes execution failures | 2 |
| Unsupported repeat-derived candidates | 1 |
| Negative controls with a candidate | 0/1 |

The two failures retain `EXECUTION_FAILED` in M6 reconstruction evidence. Both
SPAdes 4.1.0 logs identify the K55 invalid k-mer coverage-histogram error. The
high-repeat 65-nt contig was retained in the candidate artifact but marked
`UNSUPPORTED_ASSEMBLY`; read-back support did not qualify it.

## Expanded blinded synthetic suite

The suite contains 24 case instances: six positives and two target-absent
controls in each of development, tuning, and held-out splits, each generated
from an independent fixed seed. Each case was evaluated with both
configurations, for 48 M6 runs. It varies target length (500–1,200 nt),
nominal depth (16–60×), read error (0–5%), reference divergence (25–45%),
randomized read starts, repetitive and low-complexity sequence, target GC
composition, and synthetic background composition. Candidate and background sequences are
generated independently. Opaque analysis IDs are used in workflow inputs;
scenario labels and truth remain in post-run sidecars.

The same per-split input-manifest digest was verified for both predeclared
configurations:

1. The unchanged M21 SPAdes default.
2. A separate experiment adding only `-k 21,33`.

Partial recovery is a descriptive synthetic metric requiring at least 95%
local identity and 50% target coverage. Exact recovery remains strict
case-insensitive full-sequence identity. Partial candidates therefore remain
non-exact predictions in candidate precision and false-positive counts.

### Results across all three splits

| Configuration | Exact | Partial | Candidates | Exact candidate precision | False-positive candidates | Read-supported false positives | Unsupported candidates | Execution failures | Negative controls without candidates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M21 default | 0/18 | 5/18 | 9 | 0/9 | 9 | 6 | 3 | 6/24 | 6/6 |
| Experimental `-k 21,33` | 0/18 | 10/18 | 14 | 0/14 | 14 | 11 | 3 | 1/24 | 6/6 |

The held-out split alone produced 0/6 exact recoveries with either
configuration. The default produced 2/6 partial recoveries, 3 candidates,
three non-exact predictions, and 2/8 execution failures. The experimental
configuration produced 3/6 partial recoveries, 4 candidates, four non-exact
predictions, and 1/8 execution failures. Both configurations had no candidates
in either held-out negative control.

The report includes two-sided 95% Wilson intervals for exact recovery: 0–17.6%
for 0/18 across each full configuration evaluation and 0–39.0% for 0/6 in the
held-out split. These wide intervals reflect the small synthetic sample sizes.

The experimental k-mer list reduced execution failures and increased partial
recovery, but did not improve exact recovery and increased the number of
non-exact candidates on held-out data. It is therefore **not adopted**. The
existing M21 configuration remains the default.

Recorded mean assembly runtime was 2.255 seconds for the M21 default and 1.777
seconds for the experimental configuration across available assembly manifests.
The maximum SPAdes log-reported allocator value was 601 MiB; the configured
memory ceiling was 2,048 MiB. The log value is not OS peak RSS, so these results
do not claim a measured process peak.

## Candidate discrimination

In the expanded suite, each split/configuration contained one repeat-derived
candidate marked `UNSUPPORTED_ASSEMBLY`; filtering only on the existing M6
read-support status would remove that candidate. It would not remove the
remaining read-supported non-exact predictions. Read-back support is evidence
about agreement with the same synthetic reads, not proof of held-out truth.
For the held-out repeat case, the best default candidate had 72.86% local
identity and 7.11% target coverage; the experimental candidate had 72.34%
identity and 4.78% coverage. Both remained unsupported by M6 read-back.

The existing M6→M8 handoff preserves support status rather than silently
discarding assembled sequence evidence. The benchmark now reports all-emitted
and read-supported candidate counts separately. No new discovery-confidence
rule was adopted: the held-out results do not support treating read-back
support alone as sufficient to establish candidate correctness. Unsupported
candidates remain explicitly distinguished from supported candidates and
assembly execution failures.

## Integration and validation

The registered M20 synthetic integration completed with the unchanged M21
default: all ten cases completed through the Phase 5 report, and the Phase 5
result was `SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED`.
Phase 4 primary and replay reports had the same deterministic semantic
outcomes digest, `660a022931c4f9d5f2cdaec597cac61c841b53c752cc2be4c851488bcf50e396`.
The report accepted M6, M7, M8, M9, M10, and M12 handoffs; contract-unavailable
M5/M13/M14 inputs and the excluded M10 JSONL accounting payload were not
changed. No M1–M20 contract was modified.

The Phase 8 validation command exits nonzero because the existing M21 decision
remains `INCOMPLETE` and `BLOCKED_FOR_BENCHMARK_EXECUTION`; that governance
state is preserved and is not evidence of an M20 integration failure.

Focused M22 generator/metrics tests: 4 passed. Focused M19 benchmark tests: 10
passed, one optional-tool test skipped in that run. The complete local
repository suite passed 1,091 tests with 21 skipped. GitHub Actions results are
pending publication of the M22 branch.

## Limitations

The deliberately low-complexity target was excluded by configured M6 read
triage and produced no candidate. This is a synthetic miss, not an assembly
execution failure. These are small artificial software tests, not biological
sensitivity, specificity, novelty, helper-dependence, or functional validation. Each split
uses the same scenario design with an independent seed; it does not cover the
full space of sequence and read-generation conditions. Confidence intervals
are descriptive of these finite synthetic cases only. SPAdes allocator-log
values are not operating-system RSS measurements. No change to the M21
assembly default or candidate confidence contracts is justified by this
evidence.
