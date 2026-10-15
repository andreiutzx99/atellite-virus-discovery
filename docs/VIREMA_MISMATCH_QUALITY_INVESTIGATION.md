# ViReMa mismatch and FASTQ quality investigation

## Scope

This is a controlled synthetic-only follow-up to PR #72, using the same pinned ViReMa 0.25 adapter, upstream source commit, and Bowtie binaries. It ran on intact artificial references; no junction-transcript reference or breakpoint truth was passed to the caller. No real FASTQ or biological reference sequence was downloaded or analyzed.

The optional investigation contains 39 caller executions:

- Three generated genomes and fixed 100-nt, 10-read junction fixtures.
- Exact, unmutated reads at Q0, Q20, and Q40 to isolate FASTQ quality.
- 2% and 5% substitutions with Q40 throughout, compared with the exact same substituted sequences carrying Q0 only at changed positions.
- A mismatch sweep (0, 1, 2, 3) on selected 5% inputs, including both quality profiles.
- Four junction-free continuous-read controls, one for each mismatch setting.
- An exact recreation of the PR #72 5% false-negative reads, including its genome seed, breakpoint, independent per-read mutation seeds, and mutation positions. That anchor was tested at all four mismatch settings with both Q40 and the original Q0-at-substitution qualities.

Each controlled contrast holds the reference, junction positions, and input support constant. The JSON report stores each condition's read sequence(s), quality string(s), hashes, mutation positions, configuration, normalized events, native output, caller logs, unknown/ambiguous counts, runtime, and output bytes. Expected coordinates use one-based base positions: the donor is the last base of the first segment and the acceptor is the first base of the second. The adapter preserves the integer coordinates reported by native ViReMa output.

## Results

### FASTQ quality

For each of three exact-read fixtures, Q0, Q20, and Q40 produced the same event and support (10/10). Two fixtures reported coordinates one base above the generated split; the third was exact. This gives **no measurable quality-score effect on these exact-read conditions**.

For each tested substituted sequence, Q40 and Q0-at-substitution comparisons also had the same normalized event/no-event result, support, coordinates, and unknown/ambiguous count. The recreated PR #72 anchor behaved identically at every mismatch setting under Q40 and Q0-at-substitution qualities. These observations do not establish that FASTQ quality can never affect ViReMa; they show no effect for the controlled inputs tested.

### Substitutions and mismatch settings

At the default `--N 1`, results varied by generated genome and breakpoint context:

| Substitution condition | Outcome at `--N 1` |
|---|---|
| 2%, seed 1729 | 10/10 supporting reads; both coordinates +1 nt |
| 2%, seed 2718 | No normalized call; 10 unknown/ambiguous events |
| 2%, seed 31415 | 10/10 supporting reads; exact coordinates |
| 5%, seed 1729, shared altered sequence across reads | 10/10 supporting reads; both coordinates −1 nt |
| 5%, seed 2718 | No normalized call; 10 unknown/ambiguous events |
| 5%, seed 31415 | No normalized call; 10 unknown/ambiguous events |

For the **exact PR #72 missed-read fixture**, `--N 0` and `--N 1` produced no call with either quality profile. `--N 2` and `--N 3` each emitted one event supported by only 3 of 10 reads; the remaining 7 were logged as unknown/ambiguous. Both settings reported 2502 → 4453 versus generated positions 2500 → 4451 (a +2/+2 offset). The call is within 5 nt but is not exact, and most input support remains unresolved.

On a separate 5% fixture where the same mutated read was repeated 10 times, `--N 0` missed the event, while `--N 1`, `--N 2`, and `--N 3` each recovered all 10 reads, with coordinates −1/−1. Thus, greater mismatch tolerance improved recovery for some constructed inputs but did not resolve the exact PR #72 anchor fully. The two fixture designs differ in per-read mutation realization and breakpoint context; their difference does not isolate either factor as the cause.

The four continuous, junction-free controls produced zero calls at mismatch values 0–3. This small control set cannot establish that more permissive mismatch settings are safe or have low false-call rates generally.

### Breakpoint interpretation

With error-free reads and fixed settings, two of the three generated breakpoints were reported +1/+1 and one was exact. In the error-bearing cases, offsets included −1/−1 and +2/+2, while other calls remained exact. These mixed offsets are inconsistent with one universal one-base coordinate conversion explaining every observation. The +2/+2 result on the recreated PR #72 input occurred only when mismatch tolerance was raised to 2 or 3 and only 3 reads supported the event. Treat these as context- and setting-associated observations, not proof of a mapping or coordinate bug.

## Interpretation and recommendation

Within this bounded synthetic experiment, changing FASTQ quality did not change outcomes. Substitution effects varied across genomes and junction contexts. Mismatch tolerance 2–3 recovered a partial event from the exact PR #72 failure fixture, but not all reads, and shifted both reported coordinates by two bases. A separate repeated-mutant fixture showed full support at settings 1–3; mismatch 0 missed it. More permissive settings therefore have a condition-dependent sensitivity effect, while the available false-call check is too small to quantify the tradeoff.

**Do not change the default mismatch setting based on these results.** The next synthetic milestone should repeat the exact anchor over more independently generated junction positions and per-read mutation realizations, with matched junction-free and artifact controls at each mismatch setting. Report full-support, partial-support, coordinate-tolerance, unknown/ambiguous, and extra-call outcomes separately.

Scientific status remains **HELD**, sequence confirmation **NOT_ASSESSED**, and technical status **NO-GO for real-read analysis**. The SRR12424250 scope and M1–M16/M7 contracts are unchanged.

## Reproduction

- Focused offline tests: `PYTHONPATH=.:tests python -m unittest test_virema_mismatch_quality_design test_virema_stress_design test_virema_adapter`
- Existing pinned smoke plus this investigation: `python scripts/check_virema_ci.py --mismatch-quality-investigation`
- The investigation is optional. The machine-readable per-condition results are retained in `.tools/virema-diagnostic-*/report.json`; generated inputs and caller outputs are not committed.
