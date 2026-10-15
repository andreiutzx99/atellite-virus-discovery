# ViReMa synthetic junction stress validation

## Scope and method

This benchmark evaluates the pinned ViReMa 0.25 adapter on generated data only. It used source commit `481defd7c340bb52fa80748a89d478be9c265f64` and the adapter's audited Bowtie 0.12.9 binaries. No real FASTQ or biological reference sequence was downloaded or analyzed.

Each caller execution received an intact, single-record 6,000-nt artificial genome and a separate FASTQ. The harness retained expected breakpoint truth outside the caller's reference, reads, and configuration. Junction-transcript references were not used. Calls were compared in event coordinates; ±5 nt and ±10 nt tolerances are reported separately from exact recovery.

The bounded design comprised 13 positive case runs across three independently seeded genomes and seven separate negative-control runs on a fourth seeded genome with an intentionally duplicated sequence block. Positive factors covered read lengths 50, 75, 100, and 150 nt; supporting-read counts 1, 2, 5, 10, and 20; substitution rates 0%, 1%, 2%, and 5%; and leader–body-like, internal-deletion-like, and reverse-order-like arrangements. Quality strings encoded Q40 for unchanged bases and Q0 at simulated substitutions. ViReMa was run with `--Seed 25`, `--N 1`, and one thread.

The 13 case runs are separate datasets, but not 13 independent genome draws: conditions reuse the three reference genomes to keep the matrix bounded. Read support is the number of reads within one case, not the number of independent trials. Negative conditions were evaluated independently rather than pooled.

## Results

| Measure | Result |
|---|---:|
| Positive case runs | 13 |
| Recovered exactly | 10/13 |
| Recovered within 5 nt | 12/13 |
| Recovered within 10 nt | 12/13 |
| False-negative events at ±10 nt | 1 |
| False-positive events in the seven negative datasets | 0 |
| Sensitivity at ±10 nt | 12/13 (92.3%) |
| Precision at ±10 nt | 12/(12+0) (100% on this fixture set) |
| ViReMa execution errors | 0 |
| Summed per-case runtime | 43.0 s |
| Peak child-process RSS | 97,604 kB |
| Total generated caller-output bytes | 169,119,672 |

The resource figures are from one Linux x86_64 run. Runtime is summed over the 20 caller executions and excludes the one-time pinned-tool fetch/setup. Peak RSS is a runner-level child-process high-water mark, not a per-case measurement. Output bytes include temporary alignment and index files.

### Results by factor

| Factor | Within ±10 nt | Exact | Interpretation |
|---|---:|---:|---|
| 50 nt | 1/1 | 1/1 | Recovered in this condition |
| 75 nt | 1/1 | 1/1 | Recovered in this condition |
| 100 nt | 9/10 | 7/10 | Includes support and error-sweep cases; not a replicated length-only estimate |
| 150 nt | 1/1 | 1/1 | Recovered in this condition |
| 1 supporting read | 1/1 | 1/1 | One deliberately constructed case; not a general minimum-support claim |
| 2 supporting reads | 1/1 | 1/1 | One deliberately constructed case |
| 5 supporting reads | 1/1 | 1/1 | One deliberately constructed case |
| 10 supporting reads | 8/9 | 6/9 | One 5% error case missed; two other calls were offset by one base |
| 20 supporting reads | 1/1 | 1/1 | One deliberately constructed case |
| 0% substitutions | 10/10 | 9/10 | Two calls were one base off at both junctions |
| 1% substitutions | 1/1 | 1/1 | Recovered in this condition |
| 2% substitutions | 1/1 | 0/1 | Recovered within tolerance; 7/10 reads supported it and both coordinates were +1 nt |
| 5% substitutions | 0/1 | 0/1 | Missed; see failure case below |

Strata have small and unequal sample sizes. They are descriptive observations, not robust estimates or guarantees for other genomes, breakpoints, qualities, or read-generation processes.

### Negative datasets

Each row is its own 20-read caller execution; all produced zero junction calls.

| Negative dataset | Calls |
|---|---:|
| Continuous genomic reads | 0 |
| Substitution-only reads | 0 |
| Repetitive / ambiguous sequence | 0 |
| Low-complexity reads | 0 |
| Adapter-chimera reads | 0 |
| Low-quality continuous reads | 0 |
| Short continuous reads | 0 |

Zero calls in these seven synthetic datasets do not establish zero false-positive risk in biological data.

## Failure and breakpoint analysis

- **5% substitution case, 100 nt, 10 supporting reads:** the expected breakpoints were 2500 → 4451; no junction event was reported. Each read had five simulated substitutions, marked Q0 at those bases. The harness found each full flank and each ViReMa 25-mer seed flank unique in the artificial reference. ViReMa's log reported zero straightforward recombination events, ten unknown/ambiguous recombination events, and zero completely unmapped reads. This is a genuine caller miss under this constructed condition; it is not explained by repeated flanks in the reference. The mismatch/quality interaction is a plausible contributor, but this single condition does not establish the cause.
- **2% substitution case, 100 nt, 10 reads:** ViReMa reported breakpoints 3201 → 1152 rather than 3200 → 1151 and support of 7 rather than 10. The call is within 5 nt, but not exact. Its log classified seven as straightforward recombination events and three as unknown/ambiguous.
- **One zero-error baseline:** the output was 401 → 2052 instead of 400 → 2051, also a one-base offset. Both expected flanks and their 25-mer seed fragments were unique. Other constructed cases were exact. These offsets were retained as tolerance-level recoveries, not silently counted as exact.

The machine-readable report retains every case's expected breakpoints, observed normalized events, native caller output, stdout/stderr excerpts, reference-seed ambiguity counts, quality/error settings, per-case runtime, and output size. The report's failure explanations are explicitly hypotheses where causality is not established.

## Reproduction and standard CI

- Fast fixture tests: `PYTHONPATH=.:tests python -m unittest test_virema_stress_design test_synthetic_junction_validation`
- Existing pinned smoke test: `python scripts/check_virema_ci.py`
- Extended benchmark: `python scripts/check_virema_ci.py --extended-stress`
- The extended report is written under `.tools/virema-diagnostic-*/report.json`. Temporary generated references, reads, and tool outputs remain under `.tools/` and are not source deliverables.

The extended benchmark is optional and is not part of the standard CI job; standard CI continues to run the pinned smoke diagnostic and deterministic offline tests. The optional run completed all 20 caller executions without infrastructure errors. Detection misses and breakpoint offsets are benchmark findings, not reasons to fail the runner.

## Interpretation and next milestone

These results validate synthetic software behavior only. They do not establish biological sensitivity or specificity, identify biological sgRNAs or DVGs, or support satellite-virus, replication, interference, or helper-dependence claims. Scientific status remains **HELD**, sequence confirmation remains **NOT_ASSESSED**, and the technical decision remains **NO-GO for real-read analysis**. The exact SRR12424250 pilot scope is unchanged.

Next, repeat the 2–5% error conditions across more independently generated genomes and breakpoints, and compare explicitly permitted mismatch settings while retaining unknown/ambiguous read counts. Keep those runs synthetic and report each condition separately.
