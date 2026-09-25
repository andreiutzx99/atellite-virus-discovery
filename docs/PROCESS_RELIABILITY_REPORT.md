# Process reliability follow-up after PR #7

Historical PR #7 report. Its assembly statements describe that change only; the later generic SPAdes/Tadpole stage is documented in the current [assembly guide](ASSEMBLY.md).

M5 ViReMa integration and M6 residual-read support were added after this
report's baseline. See the [current roadmap](ROADMAP.md) and
[M1–M6 scientific audit](M1_M6_SCIENTIFIC_AUDIT.md); the status statements
below remain historical.

This pass implements independent subprocess and lock reliability fixes from the requested follow-up. It is a partial delivery of that request. ViReMa/DVG integration and extensions to the viral/helper-dependent reconstruction or blinded-discovery chain are not implemented. Existing user QC and exploratory virus screens were not run.

| Component | Implementation | Tested | Scientific validation | Dependency | Remaining limitation |
|---|---|---|---|---|---|
| Process cleanup | POSIX new session/process-group termination; Windows PID-specific taskkill tree termination followed by direct-child cleanup | Real Python parent/worker timeout and interruption fixtures; POSIX normal-parent-exit fixture in Linux CI | Not applicable | POSIX signals or Windows taskkill | Windows tree cleanup requires a live parent; no Windows Job Object containment. Descendants that escape the POSIX group are outside this guarantee. |
| Timeout/output limits | Deadline includes launch; final elapsed-time and byte checks; cleanup wait bounded; exit code in failure message | Timeout, fast oversized output, nonzero exit, existing budget tests | Not applicable | Standard library | Polling can overshoot; no CPU/RAM quota or hostile-process sandbox. Process creation and filesystem scans are not forcibly interruptible. |
| Output scanning | Reject symlinks, reparse points and special files; tolerate scratch files deleted during traversal; propagate traversal errors | Symlink/special-file fixtures on supported platforms; normal output scans | Not applicable | Filesystem support | Hard links and concurrent hostile filesystem changes are not contained. Tools requiring stage-local symlinks now fail explicitly. |
| Cleanup failure reporting | Keep the original failure and add cleanup detail to exception notes and retained log | Injected cleanup failure preserves timeout and warning | Not applicable | None | Does not certify that every descendant stopped when tree cleanup failed. |
| Review/workflow locks | PID, hostname, timestamp and ownership token; replacement-lock preservation; explicit stale-lock diagnostics | Ownership, exclusivity, legacy/malformed locks, disappearance/replacement; existing interruption/resume tests | Not applicable | None | No automatic stale-lock deletion. Operator must independently verify the owning process has stopped; PID/age alone is insufficient. |
| Temporary files/reuse | Retain failed-run logs and scratch evidence; existing checksum/identity-based reuse preserved | Existing lifecycle tests and installed smoke | Not applicable | Existing stages | No blanket cleanup of caller directories. Implementation identity changes require a new output folder; old results remain preserved. |
| Acquisition provider integration | Existing primary path and retry contract unchanged | Baseline regression suite | Not assessed | External providers | Production alternative remains unregistered. |
| SPAdes diagnostic | Existing dependency probe unchanged | No new runtime validation | No | Compatible external runtime | A dedicated artificial-only SPAdes diagnostic is not delivered in this pass. |
| Per-record references | Existing file-level snapshots unchanged | Baseline regression suite | No | Supplied files/metadata | Per-record importer not delivered. |
| Independent withholding | Existing digest evaluator unchanged | Baseline regression suite | No | Independent benchmark design | Upstream withholding is still not independently proven. |
| ViReMa/common DVG schema/second caller | Not implemented in this context | No | No | Not installed, bundled or redistributed by this change | No executable adapter, DVG parser, evidence schema or multi-caller aggregator is claimed. |

## Answers to the requested questions

1. **Production acquisition fallback operational?** No automatic alternative is registered; the existing primary route and generic retry contract remain available.
2. **SPAdes actually runtime validated?** No. Prior Tadpole artificial validation does not validate SPAdes.
3. **Process/resource controls improved?** Yes, as detailed above. This applies to calls through `bounded_process.run`; other standalone subprocess call sites, including the binary alignment decoder, retain their previous controls.
4. **Per-record reference import operational?** No; file-level reference snapshots remain the implemented scope.
5. **Benchmark withholding independently verifiable?** No. The existing evaluator correctly reports this as not verified.
6. **ViReMa integrated/executable or merely conditional?** Neither integration nor its adapter is implemented. Installing ViReMa alone would not add that capability to this application.
7. **Common DVG evidence representation available?** No new DVG schema or parser was added.
8. **No evidence distinguished from confirmed non-DVG?** No DVG result is generated at all. The software must not be presented as proving either label; this behavior has not been implemented/tested as a DVG reporting feature.
9. **Second caller addable without redesign?** Not established: no DVG adapter contract is supplied by this pass.
10. **Permitted technical work still remaining?** Yes: Windows Job Object containment, consistent cleanup across other subprocess sites, stronger OS-level quotas, an independent artificial SPAdes diagnostic, and additional general-purpose acquisition/import facilities. This report does not claim all technically feasible work is complete.
11. **Before scientific candidate-detection validation?** The analytical chain remains incomplete, with no biological recovery benchmark or scientific performance evidence. The requested viral/helper-dependent discovery, DVG-discrimination and blinded-discovery integrations remain outside the supported work performed here.

## Integration audit

A = implemented/software-tested; B = implementation without scientific validation; C = external dependency; D = missing technical work; E = outside supported scope in this context.

| Chain component | Status | Extent |
|---|---|---|
| Acquisition/QC | A/B/C; fallback D | Existing acquisition/QC unchanged; no QC rerun |
| Generic process reliability | A with D limitations | New process-group/tree cleanup and lock diagnostics; no hard containment guarantee |
| Assembly capability | Tadpole A/C; SPAdes C/D | Prior fixed artificial Tadpole fixture; no new assembly pipeline |
| Reference comparison/catalogues | A/B/C | Existing supplied-artifact reviews |
| DVG/recombination integration | E | Not added |
| Recurrence/control accounting | A/B | Existing supplied-observation/digest reports |
| Benchmark evaluation | A/B; withholding D/E | Existing digest evaluation; requested integrated blinded-discovery extension not added |
| Reports | A | Reliability status and explicit missing functionality documented |

## Operational notes and validation

Logs and failed outputs are retained. A timeout or cleanup failure is an execution failure, never a negative biological result. Legacy empty locks remain blocking; new locks identify their recorded owner. Before manually removing a stale lock, verify that no corresponding writer is running on the recorded host and preserve the stage artifacts. Age alone is not evidence of staleness. The ownership-token check reduces accidental deletion of replaced locks but is not a security boundary against concurrent hostile modification.

Local Windows suite: 208 tests passed with six skips (optional tools and unsupported platform/symlink fixtures). CI runs the same suite on Windows/Ubuntu Python 3.11/3.12 and the optional Linux tools job. POSIX-only cleanup and special-file tests run on Linux. Installed-package smoke validation is part of all four offline jobs.

The implementation uses Python's documented [new-session subprocess option](https://docs.python.org/3/library/subprocess.html) and [process-group signals](https://docs.python.org/3.12/library/os.html#os.killpg). Windows uses Microsoft's documented [taskkill tree option](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/taskkill), targeting only the launched PID, without a shell or image-name kill.
