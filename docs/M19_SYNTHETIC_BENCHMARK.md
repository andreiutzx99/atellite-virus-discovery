# M19 synthetic quantitative benchmark

M19 is an opt-in, software-only evaluation of the registered M4 QC → M6
residual-evidence path. It generates a fixed, bounded matrix of synthetic
datasets varying read-substitution error, nominal coverage, candidate/reference
sequence divergence, and repeat complexity, plus a no-candidate negative
control.

## Run

Install the project and make minimap2 and SPAdes available on `PATH`, then run:

```sh
satellite-m19 --output generated-artifacts/m19
```

The output contains deterministic FASTQ/reference inputs, an M4 workflow
manifest, a `heldout_truth.json` sidecar, and JSON/HTML summaries. The workflow
graph receives only reads, technical reference sequences, and reference-role
metadata. Held-out candidate sequences and positive/negative labels are kept
outside the analysis graph and used for scoring only after M6 completes.

If a stage is blocked, unavailable, incomplete, or not evaluated, its metrics
remain `null`; the report does not convert missing evidence into zero recovery
or zero false positives. The CLI exits nonzero unless every M6 case completed
with its required output artifacts.

## Metrics

- **Recovery:** an expected synthetic candidate is recovered only when a
  predicted M6 candidate sequence exactly matches the held-out sequence,
  case-insensitively. `recovery_rate` is therefore a strict software metric
  over one synthetic target per positive case.
- **False positives:** every predicted sequence not exactly matching the
  held-out positive target is counted, including every prediction in the
  negative control. `false_discovery_fraction` is false positives divided by
  predicted candidates; it is `null` when no candidates were predicted.
- **Execution state:** each case retains its M4 M6 stage status and reports
  `COMPLETE`, `BLOCKED`, `UNAVAILABLE`, `INCOMPLETE`, or `NOT_EVALUATED`.
  Metrics are not scored when required M6 outputs are absent or invalid.

The current six-case design is an initial engineering matrix, not a calibrated
benchmark: it has one deterministic realization per factor setting, one
negative control, no biological truth, and no claim-generalization threshold.
Coverage is nominal read-base coverage before QC; realized reads and quality
filtering are recorded by the upstream stages. Exact matching intentionally
does not credit near matches or partial contigs.

All sequences are artificial A/C/G/T strings generated from fixed seeds. The
held-out sidecar is independent of the workflow input manifest and is never
passed to an analysis stage. This benchmark does not use, retrieve, or activate
biological datasets; does not change M1–M18 contracts; and does not identify
satellites or establish biological sensitivity, specificity, function,
novelty, helper dependence, or independent validation.
