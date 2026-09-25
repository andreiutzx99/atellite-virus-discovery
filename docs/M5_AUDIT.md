# Milestone 5 — 30-point local acceptance audit

> Historical local acceptance record. M5 is present in the current source
> baseline. This table records the checks and publication-gate state at the
> time of the M5 audit; see the [current M5 description](M5_DVG_EVIDENCE.md),
> [current roadmap](ROADMAP.md), and [M1–M6 scientific audit](M1_M6_SCIENTIFIC_AUDIT.md).

This is a software and integration audit, not a biological validation. The
audited baseline is `58a02e054dde75fb9943d0b076ba74863cc76f39` on `main`;
the implementation branch is `feature/milestone-5-dvg-evidence`. The checks
below were completed locally before publication. **Remote GitHub checks,
review, merge, and local-main synchronization are separate gates** and must
not be inferred from this local audit.

| # | Check | Result and evidence |
| ---: | --- | --- |
| 1 | M1–M4 remain available | **PASS.** Existing commands, contracts, and tests remain; the complete installed-project suite passed (340 tests, 8 optional-tool skips). |
| 2 | No untrusted executable selected by a workflow file | **PASS.** Only the trusted registry registers `dvg_virema`; the workflow names a kind and typed inputs, not a command or shell string. |
| 3 | DVG is an optional stage | **PASS.** Existing workflows need no ViReMa installation; synthetic workflow tests keep M4 stages complete when the DVG dependency is absent. |
| 4 | Input contracts prevent accidental handoffs | **PASS.** The adapter requires a validated FASTQ and an explicitly declared FASTA reference; the optional catalogue has its own record-table contract. |
| 5 | Configuration is bounded | **PASS.** Only safe `sample_id`, seed, mismatches, and thread count are accepted; adapter tests reject extra and invalid options. |
| 6 | FASTQ is checked before execution | **PASS.** The adapter reads the entire declared single-end FASTQ, rejects malformed or empty input, and records a read checksum. |
| 7 | Reference identity is explicit | **PASS.** FASTA identifiers, lengths, sequence hashes, and the supplied reference artifact hash are recorded. |
| 8 | ViReMa cannot build indexes beside the supplied reference | **PASS.** The adapter verifies a stage-local reference copy; real runs create indexes only within the stage output. |
| 9 | ViReMa's two read-path expectations are satisfied | **PASS.** Hash-checked reads are staged in the working directory and `raw/`; the redundant root copy is removed from successful output. |
| 10 | Catalogue mapping requires exact identity | **PASS.** Event linkage resolves only on a unique record ID **and** sequence SHA256 match; otherwise it is unresolved. |
| 11 | Upstream source is actually pinned | **PASS.** Three source files must match hashes at `Routh-Lab/ViReMaDocker` commit `481defd7c340bb52fa80748a89d478be9c265f64`. |
| 12 | Bowtie executable identity is verified | **PASS.** All three audited Linux x86_64 Bowtie 0.12.9 binary hashes and versions are checked; other builds/platforms are unavailable. |
| 13 | Missing or altered dependencies cannot become negative evidence | **PASS.** Dependency inspection returns `ANALYSIS_UNAVAILABLE`, never `NO_DVG_EVIDENCE_DETECTED`. |
| 14 | Execution is bounded and shell-free | **PASS.** The adapter constructs its own fixed argv; timeout, output byte limit, safe IDs, and stage-local paths are enforced. |
| 15 | Only the documented native result family is interpreted | **PASS.** Strict parsing reads compiled virus-virus recombination text; SAM and other ViReMa result families remain raw. |
| 16 | Native file grammar is fail-closed | **PASS.** Parser tests cover complete sections, terminal tabs, duplicate/unknown libraries, malformed tokens, missing files, and truncated endings. |
| 17 | Breakpoints, strands, and support are checked | **PASS.** Events carry one-based bounded coordinates, donor/acceptor orientation, and positive support checked against references and caller counts. |
| 18 | Analysed reads must match the input | **PASS.** Both execution and reuse compare ViReMa's stdout read count with the staged FASTQ record count, including the zero-event case. |
| 19 | A completed caller run must be observed | **PASS.** Exactly one final `Time to complete in seconds:  N` stdout marker is required; truncated or duplicate markers are invalid. |
| 20 | Empty native output has a narrow meaning | **PASS.** It means zero *reported* viral recombination events only if the successful stdout count is zero; a nonempty or partial native result is never silently zero. |
| 21 | Real artificial positive is reproducible | **PASS.** Pinned Linux ViReMa/Bowtie reported `259_to_750_#_8`; normalized evidence has one event, support 8, and `DVG_EVIDENCE_DETECTED`. |
| 22 | Real artificial negative stays scoped | **PASS.** Contiguous synthetic reads yielded empty native output and `NO_DVG_EVIDENCE_DETECTED`, explicitly not a non-DVG biological classification. |
| 23 | Evidence provenance is recoverable | **PASS.** Each event has caller/version, sample, input hashes, reference sequence hashes, raw file/line/hash/token, and null values for unavailable caller fields. |
| 24 | Structured outputs are validated | **PASS.** Evidence, summary, parameters, native text, and HTML have typed contracts, bounded validation, input/source hashes, and status/count consistency checks. |
| 25 | Saved output reuse cannot hide tampering | **PASS.** Reuse checks the full output inventory and reparses native results; tests cover changed normalized JSON, diagnostics, and an inventoried-file symlink. |
| 26 | All six outcomes stay distinct | **PASS.** Synthetic tests distinguish detected, no detected evidence, not evaluated, unavailable, failed/interrupted, and invalid results. No failed state becomes a negative. |
| 27 | Reports expose useful but bounded evidence | **PASS.** Stage, root, and consolidated reports show caller/version, status, event count, raw location, limited event references, and interpretation limits. |
| 28 | Cache identity follows evidence, not presentation | **PASS.** Caller/parser/executable/input changes invalidate reuse; identical verified bytes rematerialized at a new path reuse safely without rerunning ViReMa. |
| 29 | Linux optional runtime CI is configured | **PASS locally.** The Ubuntu job fetches the exact upstream commit into temporary storage, checks binary hashes, and runs both synthetic cases; `python scripts/check_virema_ci.py` passed locally. **Remote job result is pending publication.** |
| 30 | Redistribution and scope boundaries are explicit | **PASS.** The ViReMa MIT terms, Bowtie Artistic terms, NumPy metadata, no-vendoring policy, and synthetic-only scientific limits are documented in [DVG evidence](DVG_EVIDENCE.md). |

The full local suite ran with `python -m unittest discover -s tests`:
**340 tests passed, 8 skipped**. The independent real-runtime script passed
both generated cases and verified reuse. `git diff --check` and package
compilation also passed. These checks do not establish biological sensitivity,
specificity, clinical validity, or a merged GitHub state.