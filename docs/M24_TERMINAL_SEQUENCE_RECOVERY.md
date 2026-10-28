# M24 Terminal Sequence Recovery and Assembly Boundary Validation

## Executive summary

This synthetic-only evaluation reproduced the unchanged M22 `m21_default`
baseline from M23 merge `3b65bdab129fab2a3be0addf4cad5b60fb969aab`. Across 24
cases (18 positive, 6 target-absent), there were 0 exact recoveries, 6
strand-aware high-quality partial candidates, 3 unsupported repeat-derived
fragments, and 6 assembly execution failures.

The six near-complete candidates were missing 17 terminal bases in total:
9 at the 5′ end and 8 at the 3′ end. Retrospective inspection found no
synthetic input read covering any of those missing terminal bases, so no
missing-end evidence could pass QC, reference screening, read triage, or reach
SPAdes. A bounded read-overhang experiment therefore accepted no extensions.
Exact recovery stayed 0; partial candidates stayed 6; there were no incorrect
extensions. The default pipeline was not changed.

M20's registered synthetic integration completed its technical phases and
deterministic replay. Phase 5 reported
`SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED`. M21 Phase 8
remains `INCOMPLETE`, with
`decision=INCOMPLETE`,
`overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`, and
`biological_execution_authorized=false`.

## M23 baseline reproduction

The M22 default configuration and input manifests reproduced their recorded
SHA-256 digests:

| Split | Input manifest SHA-256 | Workflow configuration SHA-256 |
|---|---|---|
| development | `6aa757fad5a443dbbf709ccdacd4b60045e8f2b9c24cbd20eebd52e25063a066` | `9afbf25ca9ea5125762ee1fb39c9a50130c4df6eda9a28592c0206eb529a1a6a` |
| tuning | `ba1ad7dc54b9be99ccafd674aac5d51ccc21696d478d260ecb0dd8d4c4cdd812` | `9afbf25ca9ea5125762ee1fb39c9a50130c4df6eda9a28592c0206eb529a1a6a` |
| held-out | `b9b9964aac89a6d6a20a3b4f87b79370096e2f0717bfad7aa0ead6af3e5f2107` | `9afbf25ca9ea5125762ee1fb39c9a50130c4df6eda9a28592c0206eb529a1a6a` |

M22's literal exact/partial result remains 0/5. Strand-normalized M23 scoring
found 0 exact and 6 high-quality partial candidates; one candidate is
reverse-complement oriented. This is not a change to the M22 baseline metric.

## Terminal-loss diagnostics

| Split / case | Original candidate length | Missing 5′ bases | Missing 3′ bases | Input reads touching missing end | Post-QC / triage evidence |
|---|---:|---:|---:|---:|---|
| development / case 01 | 499 | 0 | 1 | 0 | None |
| development / case 03 | 1,195 | 2 | 3 | 0 | None |
| tuning / case 01 | 496 | 3 | 1 | 0 | None |
| tuning / case 03 | 1,199 | 1 | 0 | 0 | None |
| held-out / case 01 | 498 | 1 | 1 | 0 | None |
| held-out / case 03 | 1,196 | 2 | 2 | 0 | None |
| **Total** | — | **9** | **8** | **0** | — |

All original synthetic reads were retained by QC (208 or 256 reads in these
cases), but their randomly sampled starts did not cover the omitted terminal
positions. Thus none of the terminal bases were available to survive the
subsequent stages. Read triage had no terminal-supporting read to retain or
reject, and the reference-screen SAM contained only the technical-reference
matches among its mapped reads. The remaining reads were unmapped to that
reference, not evidence of missing terminal sequence.

For supported candidates, SPAdes emitted one contig and graph/path files were
available. The inspected graph represented the emitted contig path in both
orientations; it did not provide missing nucleotide evidence. The single-end
benchmark has no read-pair boundary evidence. The observed limitation is
upstream read coverage at the extreme target ends, not demonstrated truncation
by candidate extraction. No evidence shows that SPAdes reconstructed missing
bases which a later stage then removed.

## Boundary evidence and experimental recovery

The experiment considers only the original M22 FASTQ reads and M22 candidate
sequences while constructing a proposed correction. A proposal requires an
exact read overlap of at least 30 bases, a unique overlap context in the
candidate, no more than 20 added bases, and the same overhang in at least two
distinct read identifiers. Conflicting or repeat-ambiguous overhangs are
rejected. Held-out truth is opened only after all proposals have been
constructed, for retrospective scoring.

No candidate had qualifying terminal overhang evidence. Accordingly, all
candidate sequences remained byte-for-byte unchanged:

| Measure | M22 default | M24 experimental |
|---|---:|---:|
| Exact recoveries | 0 | 0 |
| Strand-aware partial candidates | 6 | 6 |
| Correctly recovered terminal bases | — | 0 |
| Incorrect terminal extensions | — | 0 |
| Unsupported candidates | 3 | 3 |
| Assembly execution failures | 6 | 6 |

The complete original and experimental sequence strings, lengths, per-candidate
boundary votes, and alignments are in [`m24-terminal-recovery.json`](m24-terminal-recovery.json).
Because no extension was evidence-supported, it is rejected as a production
change. This is not evidence that future extensions are impossible; it shows
that the present reads do not support one safely.

The three 65-base repeat-derived fragments remain unsupported regression
cases. They received no experimental extension. Their complete short-fragment
k-mer breadth is not treated as reconstruction accuracy: M23 measured only
7.2% target coverage despite full fragment breadth. No arbitrary length
threshold was added.

## M20 end-to-end integration

The registered M20 run completed both recorded M4/M6 executions. M20 Phase 2B,
Phase 3, Phase 4 primary, and Phase 4 replay reports were `COMPLETE`. Primary
and replay produced the same deterministic semantic-outcomes digest:
`94821b9d7a940b4d6541d6e844a2757a3eebab634229315df6f4fe26fb5fd927`.
Phase 5 reported software integration validated and biological discovery not
validated. M12/M15 producer-binding checks remained within the registered
synthetic contracts; unavailable M5/M13/M14 handoffs and the excluded M10
JSONL payload were not modified.

The enclosing Phase 8 command exits nonzero because the unchanged M21
governance result is `INCOMPLETE` and blocked for benchmark execution. That
governance result is preserved and is not interpreted as a failure of the M20
technical integration.

## Tests and CI

M24 and M23 focused tests: 6 passed. The M20 Phase 1–5, M22, M23, and M24
focused regression set passed 48 tests. Full repository unittest discovery
completed locally: 1,097 passed, 21 skipped, 0 failed.

GitHub Actions status will be recorded after the draft PR has run its checks.

## Limitations

All sequences and reads in this work are deterministic artificial A/C/G/T
fixtures. The sample is small, single-end, and not a biological benchmark.
Random read starts left no reads over the missing terminal bases in the six
evaluated candidates. The exact-overlap experiment intentionally rejects
noisy, conflicting, or repeat-ambiguous evidence and therefore may fail to
extend boundaries when useful but imperfect reads exist. Graph artifacts are
reported as available, but the M22 candidate handoff does not include a
validated graph-boundary evidence contract. No biological sensitivity,
specificity, novelty, helper dependence, or function is established.

`decision=INCOMPLETE`;
`overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`;
`biological_execution_authorized=false`.
