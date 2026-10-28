# M23 Assembly Accuracy and Candidate Evidence Validation

This is a synthetic-only retrospective analysis. It does not modify M6 or authorize biological execution.

## M22 default baseline reproduction

Reproduced 24 cases (18 positive, 6 negative). 
M22 reported exact/threshold-qualified partial recoveries: 0/5; M23 strand-normalized exact/partial candidates: 0/6; 
assembly execution failures: 6; candidate predictions: 9.
Literal M22 exact recoveries: 0; strand-normalized exact recoveries: 0.

| Split | Input manifest SHA-256 | Default workflow configuration SHA-256 |
|---|---|---|
| development | `6aa757fad5a443dbbf709ccdacd4b60045e8f2b9c24cbd20eebd52e25063a066` | `9afbf25ca9ea5125762ee1fb39c9a50130c4df6eda9a28592c0206eb529a1a6a` |
| tuning | `ba1ad7dc54b9be99ccafd674aac5d51ccc21696d478d260ecb0dd8d4c4cdd812` | `9afbf25ca9ea5125762ee1fb39c9a50130c4df6eda9a28592c0206eb529a1a6a` |
| held_out | `b9b9964aac89a6d6a20a3b4f87b79370096e2f0717bfad7aa0ead6af3e5f2107` | `9afbf25ca9ea5125762ee1fb39c9a50130c4df6eda9a28592c0206eb529a1a6a` |

## Aggregate error and controlled experiment results

Across 9 positive candidates, mean full-length identity was 0.688; global alignment counted 0 substitutions, 0 insertions, 2522 deletions, and 14 internal gap runs. Terminal missing/extra bases were 2522/0.

Read-supported terminal trimming changed exact recoveries 0→0 and high-quality partial candidates 6→6. It was not promoted.

## Candidate sequence-error diagnostics

| Split / case | Class | Length | Full identity | Local identity | Target coverage | Candidate coverage | Subs / ins / del | Missing target ends | Extra candidate ends | M6 support | Independent-read breadth |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| development/development-case-01 | high_quality_partial | 499 | 0.998 | 1.000 | 0.998 | 1.000 | 0 / 0 / 1 | 1 | 0 | READ_SUPPORTED_ASSEMBLY | 0.998 |
| development/development-case-03 | high_quality_partial | 1195 | 0.996 | 1.000 | 0.996 | 1.000 | 0 / 0 / 5 | 5 | 0 | READ_SUPPORTED_ASSEMBLY | 0.996 |
| development/development-case-05 | unsupported | 65 | 0.072 | 1.000 | 0.072 | 1.000 | 0 / 0 / 835 | 835 | 0 | UNSUPPORTED_ASSEMBLY | 1.000 |
| tuning/tuning-case-01 | high_quality_partial | 496 | 0.992 | 1.000 | 0.992 | 1.000 | 0 / 0 / 4 | 4 | 0 | READ_SUPPORTED_ASSEMBLY | 1.000 |
| tuning/tuning-case-03 | high_quality_partial | 1199 | 0.999 | 1.000 | 0.999 | 1.000 | 0 / 0 / 1 | 1 | 0 | READ_SUPPORTED_ASSEMBLY | 0.997 |
| tuning/tuning-case-05 | unsupported | 65 | 0.072 | 1.000 | 0.072 | 1.000 | 0 / 0 / 835 | 835 | 0 | UNSUPPORTED_ASSEMBLY | 1.000 |
| held_out/held_out-case-01 | high_quality_partial | 498 | 0.996 | 1.000 | 0.996 | 1.000 | 0 / 0 / 2 | 2 | 0 | READ_SUPPORTED_ASSEMBLY | 0.998 |
| held_out/held_out-case-03 | high_quality_partial | 1196 | 0.997 | 1.000 | 0.997 | 1.000 | 0 / 0 / 4 | 4 | 0 | READ_SUPPORTED_ASSEMBLY | 0.997 |
| held_out/held_out-case-05 | unsupported | 65 | 0.072 | 1.000 | 0.072 | 1.000 | 0 / 0 / 835 | 835 | 0 | UNSUPPORTED_ASSEMBLY | 1.000 |

## Stage attribution and independent evidence

Per-case M4/M6 evidence, read-triage reason counts, assembly manifests, candidate extraction, and read-support artifacts are recorded in the JSON report. Missing evidence is left unavailable rather than attributed to an unobserved stage.

The independent confidence experiment uses 17-mer matches to a separately generated synthetic read replicate. It is retrospective only; the held-out replicate is not passed to the discovery workflow. Candidate-end trimming based on that read set is also scored as an isolated experiment and never writes to production candidates.

Candidate confidence AUC for high-quality partial versus other positive candidates: 0.08333333333333333. Exact-reconstruction association: not estimable: no exact candidates in the reproduced M22 baseline. No confidence rule or pipeline correction was promoted.

## End-to-end and test verification

M20 Phase 1 through Phase 5 integration suites: 38 tests passed. Full repository unittest discovery was attempted but exceeded the 300-second local command limit; completion is not claimed. GitHub Actions results are tracked by the draft PR.

## Limitations and governance

Alignment uses linear gap penalties and one optimal traceback; repeat-rich sequences can have equivalent placements. A potential contig join is a hypothesis only. The benchmark is small and synthetic, exact reconstruction is absent, and independent-read k-mer evidence is error-sensitive and can be ambiguous in repeats. No biological sensitivity, specificity, novelty, or helper dependence is established.

`decision=INCOMPLETE`; `overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`; `biological_execution_authorized=false`.
