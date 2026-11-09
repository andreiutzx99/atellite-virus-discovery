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

## Scientific review of the final-head CI artifact

The tracked [machine-readable summary](M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.json)
is derived from PR #101 head `5bfc11463389d226567277677344d7e58d14c142`
(workflow run `42609565425`). Raw reads, assemblies, BLAST output, and provenance
remain in the 14-day GitHub Actions artifact.

### Target-absent false alarms

The overall result is **5/35 eligible cases** (14.3%; case-level Wilson 95%
interval 6.3%–29.4%). All five are in the deliberately near-target-divergent
category: **5/5 eligible** (100%; Wilson 95% interval 56.6%–100%). That
category generated eight cases; three were unevaluable. Source-truth sidecars
confirm that each alarm has no target candidate. The cases were not relabeled
as target-positive and no M31 threshold was changed.

Each candidate had full read support, a completed M8 search, and high-coverage
matches to synthetic satellite-role references. The best full-length identity
to `SYN006.1` was 90.0%–90.268%; additional hits to `SYN003.1` were 87.333%–
87.973%. These are expected matches for a 900-base background constructed with
90 substitutions from a registered synthetic target reference. They show that
the frozen similarity-based prioritization has limited specificity for this
near-target negative category. They do **not** establish a biological
false-discovery rate.

| Case | Read condition | Candidate digest | Best synthetic panel match | Outcome |
|---|---|---|---|---|
| `development-m34-c0049` | zero error | `3c6ef127…684d81d` | SYN006.1, 90.268%, 894/900 bases, reverse | REVIEW_PRIORITY |
| `tuning-m34-c0050` | substitution only | `86092db2…e9847` | SYN006.1, 90.000%, 900/900 bases, forward | REVIEW_PRIORITY |
| `held_out-m34-c0051` | insertion only | `e970dbe7…f8428` | SYN006.1, 90.089%, 898/898 bases, forward | REVIEW_PRIORITY |
| `development-m34-c0052` | deletion only | `9cc29c0a…d8f9df` | SYN006.1, 90.000%, 900/900 bases, reverse | REVIEW_PRIORITY |
| `tuning-m34-c0056` | zero error | `67ee3992…54ac` | SYN006.1, 90.000%, 900/900 bases, reverse | REVIEW_PRIORITY |

Per-case truth-sidecar hashes, generated-background hashes, support depths,
secondary hits, and exact query/reference alignment coordinates are recorded in
the JSON summary.

### Positive indel root-cause review

The seven registered positive conditions yielded zero exact supported
reconstructions, three read-supported partial reconstructions, and four
SPAdes execution failures. Of the three cases where assembly completed, zero
were exact and all three were partial. The four execution failures are
**unevaluable**, not four additional measured reconstruction failures.

| Condition | Realized substitutions / insertions / deletions | M6 / SPAdes result | Contig and truth comparison | M8 / interpretation |
|---|---:|---|---|---|
| zero error | 0 / 0 / 0 | exit 0; read-supported | 899 bp; one missing truth prefix base. Generated target reads left that first base uncovered (depth 0). | Complete; INSUFFICIENT_EVIDENCE. Coverage-design limitation, not indel loss. |
| substitution only | 864 / 0 / 0 | SPAdes core return 21: invalid k-mer coverage histogram | No contig; read support not evaluated. | Not run. Not indel-specific because this condition has no indels. |
| insertion only | 0 / 438 / 0 | exit 0; read-supported | 901 bp; one insertion, one substitution, and terminal discrepancy; read coverage reached both ends. | Complete; INSUFFICIENT_EVIDENCE. The artifact does not isolate one insertion event as the cause. |
| deletion only | 0 / 0 / 430 | exit 0; read-supported | 898 bp; two missing truth suffix bases, both with zero generated-read coverage after deletions. | Complete; INSUFFICIENT_EVIDENCE. |
| combined low | 304 / 113 / 120 | SPAdes core return 21: invalid k-mer coverage histogram | No contig; read support not evaluated. | Not run; unevaluable. |
| combined moderate | 896 / 451 / 449 | SPAdes core return 21: invalid k-mer coverage histogram | No contig; read support not evaluated. | Not run; unevaluable. |
| combined higher | 3,968 / 2,132 / 2,233 | SPAdes core return 21: invalid k-mer coverage histogram | No contig; read support not evaluated; generated reads also had three uncovered truth positions. | Not run; unevaluable. |

All four failures have the same SPAdes-core histogram error (return value 21);
SPAdes stderr is empty and no contig or read-support result was produced. The
substitution-only failure shows that this behavior is not specific to indels.
The evidence points to a synthetic read-profile/assembler compatibility issue,
but does not prove a single causal mechanism. The zero-error and deletion-only
terminal findings correspond to read-coverage gaps in the registered synthetic
inputs. No production setting was changed and no held-out case was tuned.

The CI workflow validates this tracked summary against each newly generated
benchmark report before uploading the complete raw evidence bundle.
