# Engineering foundation audit, 2026-09-24

Baseline: PR #5, `cb36446`, 161 tests and five successful CI jobs. Source, tests, CI, README, progress/feature tables, conditional-tool documentation and TODO/FIXME/reserved-interface searches were reviewed. No completed user QC was reopened or rerun. New public-data use was limited to a tiny brewing-yeast software benchmark, separate from biological acquisition.

## Audit decisions

- **A: feasible missing infrastructure.** Workflow-wide provenance, configuration preview, report opening, Linux launcher, snapshot comparison, broader optional-tool diagnostics, fallback extension API and installed workflow smoke. Implemented here.
- **B: incomplete testing.** SRA layouts/failures/retry isolation/cleanup, inaccessible output, broken imports, snapshot comparison integrity. Added regression fixtures and a real paired SRA benchmark.
- **C: external dependency/environment.** Optional executable availability, WSL/HPC configuration and provider-specific connectors. Readiness is reported explicitly.
- **D: scientific validation.** Reference completeness, contamination causality, assembly reliability and discovery performance need independent evidence.
- **E: unsupported scope.** Existing category-4 biological interfaces, production remote-SRA routing, scheduler-specific submission and universal tool installers remain unimplemented. No placeholder is presented as operational.

## Component table

| Component | Implementation | Validation | Dependency | Remaining gap |
|---|---|---|---|---|
| Local SRA conversion | Syntax/count/mate checks, retained failures, scratch cleanup, verified resume | Real Windows Toolkit 3.4.1 paired yeast run; single/failure/disk/timeout fixtures | fasterq-dump; 2 GB free disk | No live single-end, large-archive or Linux Toolkit benchmark |
| Accession retrieval benchmark | Bounded prefetch invocation recorded separately | SRR12086795: 80,055-byte archive; 2 records per mate; reuse passed | Toolkit/network | Not an automatic production backend |
| Acquisition fallback contract | Failure classes; ordered registered-callable API with mandatory verification and attempt provenance | Transient fallback, unknown provider, integrity refusal and interruption fixtures | Application-registered providers | Remote SRA provider/routing unregistered; not an installation-only gap |
| Dependency diagnostics | PATH/native portable names, hashes, versions, isolated imports; capability status explicit | Missing/broken/timeout/native-name fixtures | Optional tools/packages | Version/import success is not functional proof |
| BLAST+ | Existing supplied-reference comparison preserved | Real artificial-data Linux CI matching/unrelated/reuse test | BLAST+ | No reference completeness claim |
| pysam/samtools | Existing conditional decoding preserved | Real Linux BAM/CRAM equivalence CI, log-bound checks | Either decoder; CRAM reference | Native Windows availability varies |
| matplotlib | Optional plotting plus import/version readiness | Real Linux scatter export CI | matplotlib | Numerical outputs work without plotting |
| Tadpole/SPAdes | Diagnostic/readiness boundary retained | Tadpole earlier artificial runtime evidence is historical; SPAdes readiness only | BBTools/Java or SPAdes | No assembly activation or fresh SPAdes capability test |
| Windows/Linux launcher | Start.cmd/Run-reviews.cmd numbered UI; shell launcher uses checkout/.venv | Installed command smoke, Linux shell CI, report-opening fixtures | Python 3.11+ | Initial Python/environment setup required |
| WSL/HPC readiness | Paths, environment, scratch, batch command and recovery documented | Ubuntu CI; local WSL probe lacked usable distribution | Configured platform/site modules | No live WSL/HPC deployment or scheduler adapter |
| Configuration/UI | Read-only preview, unknown-field rejection, run/resume/report/snapshot actions | No-write preview, missing paths, headless report fixtures | Browser optional | No GUI installer |
| Reference snapshots | Accession/version/source/role/hash/size/date metadata, immutable reuse | Existing checksum/reuse tests and comparison regressions | Local files/HTTPS | Source assertions are not scientifically certified |
| Reference update detection | Verified comparison; manifest SHA256 identity | Changed/added/removed/unchanged and corrupt/cached-source tests | Two completed snapshots | No automatic curation or in-place update |
| Reproducibility | Per-workflow configuration, source/Git/OS/Python/package metadata, commands, paths/hashes, references/status/output locations | Success/failure/reuse fixtures; isolated installed example | Git optional | Latest-attempt bundle; no input sequences or arbitrary environment capture |
| Failure/recovery | Stage-specific diagnostics, verified reuse, atomic HTML replacement, manifest shape checks | Missing files, permissions, interruption, malformed input, integrity/resume tests | Writable output | Cannot write into an inaccessible folder; forced termination can leave locks |
| Resource limits | Existing size/time bounds plus conversion failure tests | Disk/budget/timeout/process fixtures | OS/filesystem | Polling is not hard quotas or detached-grandchild supervision |
| Clean installation/CI | Install -> dependencies -> example workflow -> report/provenance -> resume, isolated from source imports | Windows/Ubuntu Python 3.11/3.12; optional Linux tool job | Actions/package availability | CI is commit/platform-specific, not a universal guarantee |
| Replit/provider integration | Standard CLI interfaces only | No configured connector | External integration | No connector execution claim |
| Scientific discovery/category-4 | Reserved interfaces unchanged | No scientific validation claimed | Independent evidence and supported scientific scope | Outside implemented engineering scope |

The follow-up suite contains 182 tests. Dependency-free jobs skip three existing real optional-tool tests; the optional Linux job executes them. The live SRA benchmark is separate from CI: [evidence and limits](validation/SRA_VALIDATION.md). [Deployment/reproducibility contracts](DEPLOYMENT.md) define supported behavior. CI outcomes belong to the corresponding PR commit, not this document's configuration claims.

## Final audit answers

1. The audited A items for the supported contracts are implemented. Further generic engineering remains possible: remote-SRA provider/routing, scheduler adapters, process-tree supervision, universal installers and broader deployment support are extensions, not completed features. This is not a claim that every possible enhancement is exhausted.
2. New implemented paths have software tests. Fixture evidence is distinguished from live evidence. Fresh SPAdes/Tadpole capability, live single-end/large SRA, WSL/HPC and Replit were not validated here.
3. Implemented conditional paths elsewhere require compatible tools, PATH/environment, adequate disk and an explicit CRAM reference. WSL/HPC requires platform/site setup. Production remote fallback needs implementation and policy, not just installation.
4. Biological identity/dependence, reference completeness, contamination causality, reliability and discovery sensitivity/specificity need external scientific evidence and truth-labelled validation.
5. Category-4 analysis, automatic production remote-SRA routing, scheduler-specific adapters and provider-specific connectors remain outside implemented scope. Engineering success does not complete the scientific discovery system.
