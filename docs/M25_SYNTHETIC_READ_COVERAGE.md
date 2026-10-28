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
| M6 assembler execution failures | 3/9 |
| Unsupported candidate sequences | 32 |
| Negative controls with any candidate | 0/9 |
| Negative-control false-positive candidates | 0 |

For 0 exact recoveries in 9 positive cases, the two-sided 95% Wilson interval
is approximately 0–29.9%. These counts are descriptive only. The small number
of independent cases, and the fact that the start modes were not paired, do not
support a strong causal comparison between read-start modes or coverage
conditions. Some cases also failed within the assembler, so workflow completion
must not be treated as successful reconstruction.

“Coverage complete” refers only to retrospective coverage of the synthetic
target. It does not guarantee assembly, exact reconstruction, read support, or
biological validity. The terminal-evidence threshold is an operational
classification used for this experiment, not a validated biological threshold.

## M20 integration availability

The registered M20 Phase 5 integration was not run. Its frozen Phase 2B, Phase
3, and Phase 4 handoff directories are absent from the available workspace. The
available Phase 5 report alone cannot serve as those inputs or establish their
identity. No M20 integration result is claimed.

## Verification

- M25 focused unit tests: 4 passed.
- Python compilation of the M25 runner and modified M19 generator: passed.
- M20 Phase 1–5 focused test modules: 38 tests run, 34 passed and 4 optional
  live-tool tests skipped.
- Fresh M24 baseline reproduction and M25 18-case run: completed.
- All three M24 input-manifest digests matched their pinned values.
- Full repository discovery with the normal environment exceeded the
  five-minute command limit while entering live M20 Phase 2. A second run with
  external tools hidden completed 1,101 tests but had 2 environment-related
  failures because that restricted `PATH` also hid `pip` and the NCBI toolkit;
  1,099 tests passed and 45 were skipped. Neither run establishes a clean full
  suite.
- The registered M20 Phase 5 integration remains unavailable because its
  frozen Phase 2B, Phase 3, and Phase 4 handoff directories are absent.
- Remote CI remains to be verified on the draft PR.

The detailed compact per-case data are in
[`M25_SYNTHETIC_READ_COVERAGE_CASES.json`](M25_SYNTHETIC_READ_COVERAGE_CASES.json).
Full workflow outputs were kept outside the repository.
