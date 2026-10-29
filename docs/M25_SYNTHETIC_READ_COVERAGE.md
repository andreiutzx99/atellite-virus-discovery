# M25: Synthetic Read Coverage and Reconstruction Limits

## Scope and governance

This report covers deterministic synthetic A/C/G/T fixtures only. Generated
read coordinates and held-out target truth were used for retrospective scoring;
neither was supplied to the registered workflow. No biological sequence or
biological validation was used.

Governance remains unchanged:

```text
decision=INCOMPLETE
overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION
biological_execution_authorized=false
```

## M24 baseline reproduction

The unchanged M24 default path completed all 24 baseline cases (8 per split).
For development, tuning, and held-out, the input-manifest SHA-256 values match
the values pinned by M24. All three runs used the same configuration digest,
`9afbf25ca9ea5125762ee1fb39c9a50130c4df6eda9a28592c0206eb529a1a6a`.
M24 recorded zero exact recoveries in each split.

## M25 controlled pilot

The run completed 18 cases: 9 positive synthetic targets and 9 negative
controls, distributed across development, tuning, and held-out splits. Positive
cases varied read-start mode, read length (75/100/150 bases), nominal depth
(16/48/80×), and simulated error rate. The three read-start modes were
independent realizations, not paired read sets.

| Measure | Result |
|---|---:|
| Exact reconstructions | 0/9 |
| Partial reconstructions | 2/9 |
| Positive targets with no uncovered bases | 6/9 |
| Positive targets meeting the three-independent-reads-per-end threshold | 5/9 |
| Mean measured positive-target coverage | 99.45% |
| M6 assembler execution failures (original aggregate) | 3/9 |
| Actual assembler execution failures (retrospective) | 1/9 |
| Upstream M6 SAM-validation failures | 2/9 |
| Cases with no assembly-eligible reads | 1/9 |
| Candidates below full read support (legacy combined count) | 32 |
| Negative controls with any candidate | 0/9 |
| Negative-control false-positive candidates | 0 |

For 0 exact recoveries in 9 positive cases, the two-sided 95% Wilson interval
is approximately 0–29.9%. These counts are descriptive only. The small number
of independent cases, and the fact that the start modes were not paired, do not
support a strong causal comparison between read-start modes or coverage
conditions. Some cases also failed within the assembler, so workflow completion
must not be treated as successful reconstruction.

The original aggregate counted any incomplete M6 workflow as an assembler
failure. Retrospective stage inspection shows one actual assembler execution
failure, two upstream M6 reference-screen SAM-validation failures, and one
case where triage left no assembly-eligible reads. All nine cases had zero
read loss in QC. In the two SAM-validation failures, the stage emitted no
residual FASTQ, so the original report's zero post-screen coverage was not a
measurement: it resulted from treating a missing artifact as an empty file.
The validator rejected supplementary SAM records whose hard-clipped `SEQ`
fields contain only part of the full input read. This does not demonstrate
target-read loss by the reference-screen algorithm.

The legacy count of 32 combines 31 `UNSUPPORTED_ASSEMBLY` contigs and one
`LOW_SUPPORT_ASSEMBLY` contig. Of the 31, thirty 56-nt contigs are exact
target-derived repeat fragments: ten distinct sequence hashes recur once in
each development, tuning, and held-out run. They have no qualifying read-back
rows. The remaining 62-nt unsupported contig also has no read-back rows; the
111-nt low-support contig has one qualifying read-back row. None is a complete
reconstruction. Per-case stage classifications and candidate sequences are
preserved in
[`M25_FOLLOWUP_DIAGNOSTICS.json`](M25_FOLLOWUP_DIAGNOSTICS.json); this is
additive and does not rewrite the compact pilot results.

“Coverage complete” refers only to retrospective coverage of the synthetic
target. It does not guarantee assembly, exact reconstruction, read support, or
biological validity. The terminal-evidence threshold is an operational
classification used for this experiment, not a validated biological threshold.

## M20 integration availability

The registered synthetic M20 chain was regenerated and run through Phase 5.
Phase 2B completed all 10 cases and confirmed the frozen Phase 1 baseline and
fixtures were unchanged. Phase 3 and Phase 4 completed; all 10 M12 and all 10
M15 Phase 4 outcomes were complete. A second Phase 4 replay produced the same
semantic digest,
`a1d46e2c44f493a9d820720dc1664c6365e47edd4eed5a9882f65e1b9920956e`.
Phase 5 reported
`SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED`, with zero
current and historical M12 invalid findings.

Phase completion does not mean every optional analysis dependency was
available. M8 results were `PARTIAL` because the installed BLAST+ executables
did not match the approved 2.17.0+ hashes (the local package was 2.16.0).
Those results are dependency-unavailable, not biological no-hit findings.
All 10 M8 results were partial; M9 ORF and BLASTP each had five complete and
five partial outcomes, and all 10 M10 outcomes were complete. Phase 2B also
recorded five upstream-unavailable candidate outputs; these remained
explicitly unavailable rather than being fabricated. The Phase 2B report
completed all 10 M6 cases.

## Verification

- M25 focused unit tests: 4 passed.
- Python compilation of the M25 runner and modified M19 generator: passed.
- M20 Phase 1–5 focused test modules: 38 tests run, 34 passed and 4 optional
  live-tool tests skipped.
- Fresh M24 baseline reproduction and M25 18-case run: completed.
- All three M24 input-manifest digests matched their pinned values.
- All 18 M25 cases and the three M24 input-manifest digests reproduced.
- The clean offline CI suite ran 1,101 tests: 1,068 passed and 33 were skipped
  in 96.947 seconds. The optional-tools CI suite ran 1,101 tests: 948 passed
  and 153 were skipped in 215.847 seconds. All 11 jobs in GitHub Actions run
  `40741114487` passed.
- M20 Phase 2B–5 execution, including a deterministic Phase 4 replay, completed
  as described above.
- Local full discovery remains environment-limited: normal discovery exceeded
  its five-minute command limit; the restricted-PATH attempt had two
  environment-related errors. Successful CI is the clean full-suite result.

The detailed compact per-case data are in
[`M25_SYNTHETIC_READ_COVERAGE_CASES.json`](M25_SYNTHETIC_READ_COVERAGE_CASES.json).
Retrospective stage attribution, read counts, SAM-validation evidence, and the
replayed candidate sequences are in
[`M25_FOLLOWUP_DIAGNOSTICS.json`](M25_FOLLOWUP_DIAGNOSTICS.json). Original
workflow outputs remain outside the repository.
