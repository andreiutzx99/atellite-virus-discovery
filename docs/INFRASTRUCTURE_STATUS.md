# Infrastructure status, 2026-09-24

Baseline: main `c3188f9`. Local validation: Windows, Python 3.12.5, 161 tests, three optional-tool tests skipped. The PR CI checks provide fresh Windows/Ubuntu and optional-tool results. Fixtures are artificial; tests do not establish scientific discovery performance.

| Component | Status | Tested | Dependency | Remaining limitation |
|---|---|---|---|---|
| Dependency inventory | Complete | Missing tools, versions, failures, timeout and fasterq-dump fixture | Python; optional executables on PATH | Version success is not functional validation |
| Portable output names | Complete | Case collisions, device names, reserved reports, validation before writes | Python | External input paths still follow the host filesystem |
| Windows/Linux launcher and packaging | Complete | Isolated installed-distribution smoke; CI 3.11/3.12 matrix | Python 3.11+, installer | Virtual environment must be configured |
| WSL2/HPC deployment | Conditional dependency/environment | Portable Python contracts; no live WSL/HPC deployment | Linux Python and site tools | Scheduler, modules and site policies need local setup |
| Existing local SRA adapter | Requires external validation | Existing mocked process/conversion/reuse tests | fasterq-dump, disk allowance | No real Toolkit conversion verified in this session |
| Remote automatic SRA fallback | Unsupported/outside current scope | Existing ENA failure/skip/partial-state tests | SRA transport/runtime would be needed | Not integrated; no added autonomous acquisition route |
| Existing acquisition diagnostics | Complete | Mocked downloads, corruption, interruption, resume, no suitable data | Network for fresh retrieval | External archive availability cannot be guaranteed |
| Supplied reference snapshots | Complete | Hash/reuse/corruption, naming, pre-copy sizes, accession/version/date export | Local files or HTTPS | Declared provenance is user-supplied; updates require new manifest/output |
| Scientific reference curation/update policy | Requires external validation | No scientific validation claimed | Independently curated evidence | No automatic database completeness or suitability decision |
| Existing supplied-reference BLAST | Conditional dependency/environment | Existing artificial real-tool test in optional CI; mocked missing/mismatch paths | BLAST+ | No fresh local BLAST runtime installed by this follow-up |
| Existing BAM/CRAM decoding | Conditional dependency/environment | Existing Linux backend equivalence test; final log-limit regression | pysam or samtools; CRAM reference | Native Windows optional decoder availability remains conditional |
| Artifact orchestration and diagnostics | Complete | Named failures, missing inputs, interrupt/resume, preserved stages, report hashes | Python plus each stage's requirements | Forced termination may leave a lock; code/input changes require new output |
| Process resource controls | Complete | Invalid budgets, existing over-budget outputs, timeout, exit failures, cwd with spaces | OS subprocess support | Polling is not a hard quota; detached grandchildren are not supervised |
| HTML/CSV/JSON summaries | Complete | Escaping, pending/failed/interrupted stages, portable relative links | Python | Top-level workflow summary describes the latest attempt |
| CI and clean installation | Complete | Offline suite and isolated packaged registries/entry-point checks | GitHub Actions; optional Linux packages | CI results are tied to the tested commit, not every possible platform |
| SPAdes/Tadpole discovery activation and category-4 analysis | Unsupported/outside current scope | Existing diagnostics only | Tools plus separate supported scientific design | Original boundaries remain unchanged |
| Replit connector | Conditional dependency/environment | No configured connector | External environment integration | No connector runtime result claimed |

These statuses apply to the stated contracts, not an assertion that all possible future infrastructure improvements are exhausted. Remaining broader features retain their original IDs and boundaries in PERMITTED_ROADMAP.md and PARTIAL_FEATURE_FOLLOWUP.md.
