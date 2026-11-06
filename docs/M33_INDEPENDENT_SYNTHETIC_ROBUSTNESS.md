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

## Completed synthetic run

The checked-in machine-readable results are in
[`M33_INDEPENDENT_SYNTHETIC_ROBUSTNESS.json`](M33_INDEPENDENT_SYNTHETIC_ROBUSTNESS.json).
The run used the hash-verified NCBI BLAST+ 2.17.0+ runtime and completed 21
cases across three independent seeded runs, plus a fresh repeat of the first
seed set. Reconstruction, screening, and normalized alignment evidence matched
between the original and repeat runs.

| Measure | Result |
|---|---:|
| Positive controls | 7/15 exact, read-supported reconstructions (46.7%) |
| Validated M6-to-M8 handoffs | 14/21 |
| Completed M8 searches | 14/21 |
| Negative/decoy case REVIEW_PRIORITY | 0/5 eligible (Wilson 95%: 0–43.4%) |
| Negative/decoy contig REVIEW_PRIORITY | 0/14 eligible (Wilson 95%: 0–21.5%) |

Positive recovery varied by condition: 6/7 cases at coverage 80, read length
100, and 0% substitution error were exact-supported; 1/1 at coverage 48,
read length 100, and 0% error was exact-supported. No exact-supported
reconstructions occurred in the other tested positive conditions. These are
technical synthetic recovery results, not estimates of biological sensitivity.

By negative-control category, reference-absent adversarial cases had 0/2
eligible cases and 0/11 eligible contigs marked REVIEW_PRIORITY. Supported
target-absent background controls had 0/3 eligible cases and 0/3 eligible
contigs marked REVIEW_PRIORITY. Four negative/decoy cases were unevaluable
because they lacked a supported contig or had incomplete M8; they remain in
the JSON report and are excluded from the eligible denominators. The
target-absent no-contig controls likewise do not count as successful negative
screens.

Governance is unchanged:

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
