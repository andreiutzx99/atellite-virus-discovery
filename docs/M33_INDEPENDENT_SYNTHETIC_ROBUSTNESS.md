# M33 — Independent synthetic robustness and false-alarm stress testing

M33 reuses M29 read generation and real M6 assembly, M32's validated candidate
handoff and frozen M8 BLAST+ runtime, and M31 triage. It does not change
production defaults, support criteria, M8 settings, M31 thresholds, or governance.

## Design and execution

The runner preregisters three deterministic seed sets and case conditions before
calling M32. Each set exercises positive retrieval controls, a reference-absent
adversarial case, a reference-independent challenge, a target-absent no-contig
control, and a separate target-absent supported-background control. The known
reference panel is regenerated from the declared seed and case design; held-out
truth is not supplied to M8 or triage. M32's retrospective scoring runs only
after screening. Outputs preserve each M32 report and its per-contig provenance.

Run the full benchmark with verified BLAST+ 2.17.0+ executables:

```sh
PYTHONPATH=. python -m satellite_discovery.m33_independent_synthetic_robustness \
  --output /tmp/m33-run \
  --blastn /path/to/blastn \
  --makeblastdb /path/to/makeblastdb \
  --blastdbcmd /path/to/blastdbcmd \
  --replicates 3
```

The bounded CI run uses one independent replicate plus a fresh same-seed repeat
and retains its JSON, preregistration, M32 component reports, and raw M8
artifacts as a workflow artifact. Generated benchmark outputs should not be
committed as large run directories.

## Scoring

Target-absent synthetic false alarms are defined only by absence of target in
the generated synthetic truth (`positive_control=false`), never by an absent
reference-panel entry or an incomplete assembly. Target-positive adversarial
cases—including repetitive/reference-absent and reference-independent
challenges—are scored separately. Optional combined diagnostic stress
statistics are explicitly mixed-category measurements.

For every category, case-level and contig-level REVIEW_PRIORITY rates include
only cases with a read-supported contig and completed M8. No-contig and
incomplete-M8 cases are retained as unevaluable with reasons, not counted as
successful negative screens. Each category reports eligible denominators and
Wilson 95% intervals; intervals are descriptive and do not imply biological
specificity.

## Limits

The reused M25 read generator models substitution errors; it does not generate
insertions or deletions. The benchmark varies coverage, read length, and
substitution error but does not claim indel robustness. A same-seed repeat
compares normalized reconstruction, screening/triage, and alignment evidence
in a fresh output directory. Both run bundles are retained. Any mismatch is
identified by stage and case in the report and fails the benchmark command
after the report is written. Run-specific paths and timestamps are not compared.
The reported rates are synthetic triage outcomes only. Biological sensitivity, specificity,
false-discovery rate, and satellite-virus identification remain NOT_EVALUATED.

## Completed synthetic run

The checked-in machine-readable results are in
[`M33_INDEPENDENT_SYNTHETIC_ROBUSTNESS.json`](M33_INDEPENDENT_SYNTHETIC_ROBUSTNESS.json).
Using hash-verified NCBI BLAST+ 2.17.0+, the corrected run completed 21 cases
across three independent seeded runs and a fresh repeat. The repeat status is
`REPRODUCIBLE`; reconstruction, screening/triage, and normalized alignment
signatures match. A mismatch instead writes the reports and both component
bundles, records differing stages/cases as `REPRODUCIBILITY_MISMATCH`, and
fails the benchmark command.

| Truth category | Unit | REVIEW_PRIORITY | Eligible denominator | Rate | Wilson 95% interval |
|---|---|---:|---:|---:|---|
| Target absent | Case | 0 | 3 | 0% | 0–56.1% |
| Target absent | Contig | 0 | 3 | 0% | 0–56.1% |
| Target-positive adversarial | Case | 0 | 4 | 0% | 0–49.0% |
| Target-positive adversarial | Contig | 0 | 13 | 0% | 0–22.8% |
| Combined diagnostic stress | Case | 0 | 7 | 0% | 0–35.4% |
| Combined diagnostic stress | Contig | 0 | 16 | 0% | 0–19.4% |

The target-absent category includes three supported-background cases; the
separate target-absent no-contig control from each replicate is unevaluable.
Two target-positive adversarial cases are also unevaluable. They remain listed
in the JSON and are excluded from denominators. The reference-absent
adversarial cases are target-positive in synthetic truth and are not counted as
target-absent false alarms.

The earlier mixed subset is preserved for comparison: 0/5 eligible cases
(Wilson 95% upper bound 43.4%) and 0/14 contigs (upper bound 21.5%). It is not
a target-absent false-alarm estimate.

Positive-control technical recovery remains 7/15 exact and read-supported
(46.7%); 14/21 cases completed validated handoff and M8. Recovery was
condition-dependent: 6/7 exact-supported at coverage 80, read length 100, 0%
substitution error, and 1/1 at coverage 48, read length 100, 0% error. These
are synthetic technical results, not estimates of biological sensitivity.

Governance is unchanged:

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
