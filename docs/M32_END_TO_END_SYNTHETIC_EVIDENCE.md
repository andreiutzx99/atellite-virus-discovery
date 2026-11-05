# M32 — End-to-end synthetic evidence integration

M32 connects fresh deterministic synthetic reads to the registered M6
reconstruction/read-back implementation, the typed M6-to-M8 sequence contract,
the frozen M8 BLAST+ profile, and M31's panel-relative triage. It does not alter
production assembly or acceptance thresholds.

## Reproduction

Install the repository's normal optional tools (`spades.py`, `minimap2`, and
`blastdbcmd`), then provision NCBI BLAST+ 2.17.0+ using the archive, executable
hashes, and runtime checks in `satellite_discovery/m8_blastn_profile.py` and
`.github/workflows/tests.yml`. Run:

```sh
PYTHONPATH=. python -m satellite_discovery.m32_end_to_end_synthetic_evidence \
  --output /tmp/m32-run \
  --blastn /path/to/blastn \
  --makeblastdb /path/to/makeblastdb \
  --blastdbcmd /path/to/blastdbcmd
```

Outputs retain each M19/M6 run, assembly graph and manifest, contig FASTA,
read-support evidence, support alignments, M6-to-M8 handoff, M8 commands,
normalized matches, and raw BLAST branches. The report stores hashes for the
handoff, M6 evidence, reference snapshot, and raw search outputs. The generated
truth sidecar is retrospective and is not an M8 or triage input.

## Evaluation scope and limitations

The fixed case set includes development, tuning, and held-out synthetic cases
plus a held-out target-absent control. M6 read-back support is technical
evidence from the specified reads; it is not independent biological
confirmation. M8 similarity and M31 triage are relative to a synthetic panel.
Neither establishes biological identity, satellite-virus status, novelty, or
candidate acceptance. Biological sensitivity, specificity, and false-discovery
rate remain `NOT_EVALUATED`.

## Observed run

The completed local run used the frozen BLAST+ 2.17.0+ runtime with verified
`blastn` and `makeblastdb` executable hashes. Results were:

| Measure | Result |
|---|---:|
| Cases | 5 |
| Positive synthetic assembly exact recoveries | 3 / 4 |
| Positive exact recoveries with qualifying M6 read support | 3 / 4 |
| Validated M6-to-M8 handoffs | 4 / 5 |
| Completed M8 searches | 4 / 4 contig-bearing cases |
| Held-out positive exact, supported, handed off, screened, and triaged | Yes |
| Held-out target-absent controls | 1; no contig, no M8 query, insufficient evidence |

The held-out positive was an exact reconstructed contig with measured M6
support, passed the integrity-checked M6-to-M8 handoff, completed both M8
masking branches, and received `REVIEW_PRIORITY` triage. A development repeat
challenge produced an unsupported short contig and was assigned
`INSUFFICIENT_EVIDENCE`. M8 raw outputs, commands, normalized matches, reference
provenance, assembly graphs, support records, and digests are retained in the
generated run directory. The report JSON records per-case denominators and
hashes.

This is a small synthetic integration benchmark, not evidence of biological
performance. The checked-in JSON is the concise frozen result summary; the
reproduction command writes the full artifact bundle.

Missing contigs, failed reconstruction, absent support, invalid provenance, or
incomplete M8 branches must remain explicit and cannot be treated as a
successful end-to-end result.

Governance remains:

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```
