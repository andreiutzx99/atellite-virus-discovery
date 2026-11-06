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

Negative/decoy case-level and contig-level REVIEW_PRIORITY rates include only
cases that produce a read-supported contig and complete M8. No-contig and
incomplete-M8 cases are listed as unevaluable, never counted as successful
negative screens. Wilson 95% intervals are descriptive and do not imply
biological specificity.

## Limits

The reused M25 read generator models substitution errors; it does not generate
insertions or deletions. The benchmark varies coverage, read length, and
substitution error but does not claim indel robustness. A same-seed repeat
compares read, assembly, handoff, screening, and triage signatures in a fresh
output directory. The reported rates are
synthetic triage false alarms only. Biological sensitivity, specificity,
false-discovery rate, and satellite-virus identification remain NOT_EVALUATED.

Governance is unchanged:

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
