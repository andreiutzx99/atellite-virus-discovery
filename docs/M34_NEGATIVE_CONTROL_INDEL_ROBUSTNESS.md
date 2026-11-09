# M34: expanded synthetic negative controls and indel robustness

M34 extends the registered M32 synthetic-only M6 → M8 → M31 evidence path. It
does not change M6, M8, M31, the production panel, or historical benchmark
settings. It uses only deterministic artificial sequences and the pinned M8
BLAST+ runtime.

## Run

The default design generates 64 target-absent cases: eight independent seeds
for each of eight backgrounds, spanning all seven preregistered error conditions
(the zero-error condition is repeated). Each category is stratified by error
condition. Seven target-positive cases exercise
substitution-only, insertion-only, deletion-only, combined-error, coverage,
and read-length conditions. Three existing M32 controls remain in each
bundle. The selected same-seed repeat is run separately and retained.

```sh
satellite-m34 \
  --output /tmp/m34-negative-control-indel-robustness \
  --blastn "$M8_BLASTN_EXECUTABLE" \
  --makeblastdb "$M8_MAKEBLASTDB_EXECUTABLE" \
  --negative-per-category 8
```

`M34_PREREGISTERED_DESIGN.json` is written before any M6 execution. It binds
the case IDs, independent seeds, target status, coverage, read length,
background category, and error rates. Analysis-stage IDs remain opaque; held-out
sequence truth is scored only after M8 and triage. `M34_READ_PROVENANCE_INDEX.json`
binds read-level provenance JSON, including source intervals and per-base
origins (`null` for inserted bases). Both the full and repeated M32 bundles are
kept under the output directory.
Target absence is verified after screening against each registered held-out
truth sidecar (`candidate_sequence` must be null), not inferred from panel
absence or assembly failure.

## Interpretation

Target-absent false alarms use only target-absent synthetic truth, never
reference-panel absence or assembly failure. Eligibility requires a read-
supported contig and a completed M8 search. The report gives case-, contig-,
and background-category rates with Wilson 95% intervals and lists
unevaluable cases. Contig counts and rates are descriptive; no contig-level
Wilson interval is calculated because contigs within one case are dependent.
Cases are the replication unit. Positive indel recovery and false alarms are separate
outcomes. Nonzero false alarms or reduced recovery are findings, not automatic
benchmark failures.

This declared error model is not a validated sequencing-platform error
distribution. Synthetic outcomes do not estimate biological sensitivity,
specificity, or false-discovery rate.

Governance remains fixed:

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
