# Development handoff

Prepared 2026-09-25 from main after PR #10 (`dbc85920e643376384029935da6642e9d1b0b539`). GitHub repository: [andreiutzx99/atellite-virus-discovery](https://github.com/andreiutzx99/atellite-virus-discovery). Distribution: `satellite-discovery`, version `0.3.0`, Python 3.11 or newer.

## Read this first

This is a working metadata/download/QC application with descriptive reviews of independently supplied artifacts, an allowlisted review workflow, and isolated artificial runtime diagnostics. It is **not** a complete or scientifically validated discovery application. Acquisition/QC, artifact review and artificial assembly diagnostics are separate entry points. Installing optional tools does not connect them into an end-to-end discovery chain.

This final pass adds a read-only Git handoff verifier and its regression tests, this consolidated report, README navigation, and clarification of historical architecture/resource-control documentation. It does **not** add the requested plugin registry, new workflow states, per-record reference importer, production alternative acquisition provider or arbitrary-input assembler. Those priorities remain unimplemented. No user QC was rerun or changed, and no exploratory biological analysis was performed.

The distinction between a source transfer and a complete application is essential: a GitHub handoff can be ready while the requested broader application remains incomplete. A test count is not a requirement-completion percentage.

## Released architecture and source map

| Component | Source files | Current behavior and limits |
|---|---|---|
| Package and entry points | `pyproject.toml`, `satellite_discovery/__init__.py`, `__main__.py`, `cli.py` | Standard-library base application; installed commands `satellite-discovery` and `satellite-reviews`. Python >=3.11. No bundled optional runtime or database. |
| Metadata | `database_query.py`, `metadata.py`, `metadata_filter.py`, `model_scope.py`, `workflow.py` | Bounded archive requests, cache/provenance, normalized run records, explicit metadata inclusion/exclusion/unknown handling, JSON/CSV/HTML reports. Metadata assertions do not establish scientific identity. |
| Read acquisition | `sequence_downloader.py`, `read_workflow.py` | Existing budgeted ENA FASTQ retrieval, verification, retained download/QC artifacts, failure diagnostics and reuse checks. Production automatic remote fallback is not configured. |
| Baseline QC | `quality_control.py` | Existing read checks/filtering and retained original/trimmed categories. This is the repository's baseline implementation, not integration of fastp, FastQC or MultiQC. |
| Read-only QC integrity | `qc_audit.py`, `audit_wizard.py` | Audits existing run artifacts without rerunning QC; reports integrity discrepancies. `Audit-existing-run.cmd` is the launcher. |
| Local archive conversion | `sra_conversion.py` | Explicit conversion of a supplied local archive using external SRA Toolkit, paired-output checks, command/version/provenance, bounded execution and verified reuse. Failed prior files are retained separately to avoid stale-mate acceptance. Not automatic remote retrieval. |
| Acquisition retry contract | `acquisition_fallback.py` | Trusted callables provided by application code; deterministic configured order, 0–2 retries, classified failures, caller-persisted history, timestamps and verification before acceptance. Prior success still requires verification. No production alternative registered; callbacks must enforce their own time/storage limits. |
| Library metadata review | `library_review.py` | Descriptive RNA/DNA/mixed/unknown labels and conflicts from supplied metadata; no automatic downstream tool selection. |
| Supplied observations | `observation_report.py`, `context_review.py` | Supplied sample/control observations, stratified context and paired quantitative reports with explicit missingness/denominators. Does not discover events in reads or infer causality. |
| Sequence inventory | `sequence_catalogue.py`, `sequence_quality.py` | Supplied FASTA parsing, length/composition/descriptors, exact duplicate groups, SQLite/CSV/FASTA/report outputs. This is not the requested provenance-rich per-record reference import, approximate clustering or functional interpretation. |
| Coverage and alignment decoding | `coverage_review.py`, `alignment_adapter.py` | Existing interval/SAM/gzip-SAM coverage review; optional pysam or samtools for BAM/CRAM. CRAM requires a supplied reference. No mapping or residual-read extraction stage. |
| Supplied similarity evidence | `blast_import.py`, `local_comparison.py` | Import existing nucleotide BLAST tables or run BLAST against independently supplied references; retain commands, versions, logs and outputs. External BLAST required for execution. No-hit does not establish novelty. |
| Supplied evidence/control review | `contamination_review.py` | Descriptive match coverage and technical-control evidence flags with uncertainty. No validated biological classifier or probability model. |
| Catalogue links | `catalogue_linker.py` | Link existing sequence inventories/occurrences by exact identity; no approximate family assignment. |
| Reference snapshots | `reference_snapshot.py` | Immutable supplied-file snapshots, hashes/sizes, supplied source/category/accession/version/provenance and snapshot comparison. One metadata record describes a file, not every sequence in it. No curated collection is included. |
| Supplied digest evaluator | `artifact_benchmark.py` | Exact supplied SHA256/control tables, produced/classified/unclassified counts and recurrence, including explicit zero-output completed datasets. Does not independently verify the underlying files or upstream withholding; not a biological recovery benchmark. |
| Stage lifecycle | `review_stage.py`, `stage_lock.py`, `portable_paths.py` | Shared output manifests/digests, lifecycle reports, portable names, exclusive locks with owner information and ownership-token cleanup. No automatic stale-lock deletion. |
| Bounded native processes | `bounded_process.py` | Argument-list execution, stage-local working directory, time/output monitoring, retained logs and process cleanup. POSIX groups and Windows PID-specific tree cleanup have documented limits; no hard CPU/RAM/filesystem quota or hostile-process sandbox. |
| Review orchestration | `artifact_workflow.py` | Fixed allowlist of 15 kinds; ordered execution and compatible earlier-stage artifact references, validation, failure/interruption reports, checksum-based reuse. No plugin registration API, arbitrary commands or dynamic imports from configuration. |
| Provenance | `reproducibility.py` | Workflow configuration, source hashes, Git when available, Python/OS, selected installed optional-package versions, input/output identities, stage state and available command records. Not a complete dependency lock or scientific certification. |
| User interface | `review_ui.py`, `report_generator.py`, launchers | Numbered terminal menu, HTML/CSV/JSON reports, existing-report dashboard, read-only workflow preview and report opening. No general plugin manager or unified discovery UI. |
| Environment checks/setup | `dependency_review.py`, `portable_setup.py` | Version/import/PATH diagnostics and existing pinned portable BLAST setup. Discovery/version success is not functional validation. Some probes refer to tools without implemented analysis adapters. |
| Artificial assembler diagnostics | `scripts/test_tadpole_runtime.py`, `scripts/check_tadpole_ci.py`, `artificial_spades.py`, `scripts/check_spades_ci.py` | Fixed generated artificial fixtures, single/paired execution and verified reuse. Tadpole validated on Windows/Linux; SPAdes on Linux. No arbitrary-input assembly or workflow assembly stage. |
| Release verification | `scripts/check_handoff.py`, `tests/test_handoff.py` | New read-only source publication check using Git and live origin/main, tested against disposable local repositories. Separate from application workflows and CI certification. |

## Actual pipeline map

```text
Metadata / selected reads
  -> existing acquisition, baseline QC and integrity checks
  -> retained files and QC reports

Independently supplied artifacts and references
  -> fixed allowlisted artifact-review workflow
  -> descriptive reports / catalogues / control summaries
  -> workflow status and reproducibility files

Fixed generated artificial fixtures
  -> standalone Tadpole or SPAdes diagnostic
  -> artificial runtime evidence

Source checkout
  -> new read-only Git handoff verification
  -> JSON publication status (CI checked separately)

Between acquisition/QC and autonomous downstream discovery:
  UNIMPLEMENTED / EXTERNAL SCIENTIFIC MODULES
  No executable bridge or detailed operational contracts are supplied.
```

Reports over supplied artifacts can be useful independently. Their existence does not establish a connected raw-data-to-candidate pipeline.

## Workflow architecture and state

The released schema is `artifact-workflow-v1`. It accepts 1–30 ordered stages. Each stage has an ID, an allowlisted kind and exactly the required input fields. File paths resolve relative to the specification. References to outputs of earlier stages are accepted only after checking their completed manifest and artifact digest. There is no automatic conversion between incompatible stage formats.

The 15 existing kinds are `sra_conversion`, `inventory`, `sequence_quality`, `library`, `observations`, `context`, `quantitative`, `alignment`, `cram`, `blast_import`, `blast_compare`, `contamination`, `catalogue_links`, `reference_snapshot`, and `artifact_benchmark`.

Actual state progression is `pending -> running -> complete`, or `running -> failed/interrupted`. Execution stops on failure; later stages remain pending. Completed-stage reuse verifies identities and saved artifacts. Changed input/configuration/implementation may require a fresh output folder. Some external diagnostics require a new folder after failure; there is no universal tool checkpoint/resume protocol.

`skipped`, `dependency_missing` and `external_module_required` are **not operational workflow states**. Missing dependencies are currently failures/errors. Unknown kinds fail validation. No missing implementation or unassessed sample should be interpreted as a successful negative analytical result. Historical placeholder status names in other documents are not implemented APIs.

Each started artifact workflow normally writes `workflow.json`, `report.html` and `reproducibility.json`, including recorded failure/interruption. Validation or inaccessible-output failures can occur before those files can be created. Reports link to actual stage outputs. A forcibly killed process may leave a lock; independently verify the owner has stopped before removing it. Existing user run directories must be preserved.

## Plugin architecture: current answer

There is no operational general plugin registry or stable external-adapter SDK. `FIELDS` and `dispatch` in `artifact_workflow.py` remain fixed application code. Installing an independent package does not register it. User configuration cannot specify arbitrary shell commands or Python imports. No example external adapter, new execution manifest format or detailed future biological-adapter contract was added in this pass.

Consequently, another developer cannot use a documented drop-in registration API today. Existing dedicated adapters and the shared bounded runner should not be described as such an API. Any future interface would require its own design, review, compatibility tests and scope assessment. This handoff records the absence; it does not give an operational implementation plan for the unimplemented scientific chain.

## Launchers and reports

Windows: `Start.cmd` or `Run-reviews.cmd`. Linux: `sh Run-reviews.sh`. Installed command: `satellite-reviews`. Base review operations need no optional scientific runtime.

| Menu | Existing function |
|---|---|
| 1–6 | Library metadata; observations; FASTA inventory; interval coverage; supplied evidence/control review; linked catalogues |
| 7–11 | Existing-report dashboard; alignment coverage; BLAST-table import; QC integrity audit; optional dependency diagnostics |
| 12–16 | Artifact workflow; supplied-reference BLAST; context; paired quantitative reports; sequence descriptors |
| 17–19 | File-level reference snapshot; portable BLAST setup; explicit local archive conversion |
| 20–23 | Read-only workflow preview; open existing HTML report; snapshot comparison; supplied-digest/control evaluation |

Not all standalone diagnostic modules are exposed in the menu. The dashboard reads reported states and does not independently verify every linked artifact. WSL and HPC usage guidance exists, but no real WSL/HPC deployment has been demonstrated; Ubuntu CI does not establish that.

## Dependencies and packaging

| Dependency | Required for | Evidence / qualification |
|---|---|---|
| Python >=3.11 | Base application and tests | CI matrix is Python 3.11/3.12 on Windows/Ubuntu; not a claim of all OS/Python combinations. |
| Git | New handoff verifier and its fixture tests | Full history, main and origin/main required for the checker. Not required for most installed review functions. |
| pysam 0.24.1 or samtools | Conditional binary alignment decoding | Real artificial BAM/CRAM Linux tests; pure text alternatives remain available. |
| NCBI BLAST+ | Existing supplied-reference comparison | Real artificial Linux tests and prior Windows evidence. |
| matplotlib | Optional figure export | Optional extra accepts >=3.8,<4; CI installs 3.10.1. |
| SRA Toolkit | Explicit archive conversion | Prior tiny benign yeast Windows validation with 3.4.1; not a production automatic fallback service. |
| Java and BBTools | Fixed artificial Tadpole diagnostic | Prior Java 17 / BBTools 40.01 evidence; pinned archive verified by diagnostic setup. |
| Compatible SPAdes | Fixed artificial SPAdes diagnostic | Linux 3.15.5 evidence; no native Windows SPAdes support claim. |

Optional native tools/databases, `.tools`, virtual environments and user data are not bundled. CI uses Ubuntu apt packages for several tools; the dependency closure and runner images are not fully pinned. A wrapper executable hash does not fingerprint all libraries or core executables. Read-only version/import probes deliberately do not claim capability validation.

No ViReMa installation, adapter, junction parser, container execution or scientific test exists here. A prior upstream licence inspection is documented in `SPADES_AND_LICENSE_REPORT.md`; it is not integration or validation evidence and does not cover all dependency redistribution questions.

## Tests and clean installation

From a full checkout, use a dedicated Python virtual environment. Install the base package and run:

```console
python -m pip install .
satellite-reviews --help
python -I scripts/check_installed.py
python -m unittest discover -s tests -v
```

`check_installed.py` tests installed package resources/entry points and fixed artificial review/reuse/provenance operations. It does not use completed user QC runs. The source suite before this pass contained 217 tests. This pass adds 12 handoff-verifier tests, yielding 229 collected tests. Dependency-free runs intentionally skip the three optional-runtime tests; the Linux optional-tools job is the source of the no-skip full-suite count. Runtime outcomes must be read from the actual final CI, not inferred from this count.

The new tests use temporary local Git repositories and a local bare remote: clean matching source, merged and unmerged branches, untracked/modified files, unpublished main, live-remote disagreement despite stale tracking refs, stash detection, missing committed handoff files, expected-commit mismatch, detached HEAD, remote failure, timeout/malformed commit, and shallow-clone rejection. They perform no biological operations or internet access. Git absence skips these fixture tests, so a no-Git local result is not full verification.

Existing `.github/workflows/tests.yml` has five jobs:

1. Windows Python 3.11 offline/package checks.
2. Windows Python 3.12 offline/package checks.
3. Ubuntu Python 3.11 offline/package/shell-launcher checks.
4. Ubuntu Python 3.12 offline/package/shell-launcher checks.
5. Ubuntu Python 3.12 optional tools: pinned Python optional packages, apt native tools, actual fixed artificial Tadpole/SPAdes diagnostics, then the full suite with `RUN_OPTIONAL_TOOL_TESTS=1`.

The last job uploads artificial SPAdes output folders as `artificial-spades-evidence`, with 14-day retention. Persistent structured summaries are tracked under `docs/validation/`; expiring Actions artifacts are not a permanent data archive. CI also runs on pushes, allowing the final merged main commit to be tested directly. Offline fixture tests are software validation, not scientific sensitivity/specificity tests.

## New handoff checker

Run from a clean full-history checkout of main:

```console
python scripts/check_handoff.py
python scripts/check_handoff.py --expected-commit FULL_COMMIT_SHA
```

It prints JSON and exits 0 only when its **source** checks pass; otherwise it exits 1. It checks the current branch, HEAD/local main/tracking main/live origin main commit equality, tracked source tree, non-ignored working changes, unmerged local branches, stashes and committed handoff files. Git requests have a 30-second per-command timeout and interactive credential prompts are disabled. It does not fetch, switch branches, stage, commit, push, merge or delete anything. Use an ordinary Git fetch yourself before checking stale local refs.

`source_status: READY` is deliberately separate from `ci_status: not_checked` and `application_completeness: not_assessed`. Inspect GitHub CI before declaring the full GitHub transfer READY. An unreachable remote, shallow clone, detached HEAD or Git error fails closed. The check is a point-in-time snapshot, not a repository lock.

Ignored run data, installed tools, virtual environments, other clones and server-only branches are outside its certification. Inspect them separately if needed. Do not force-add private or generated data to make a source handoff appear complete. This pass separately checks fetched remote branches and local stashes before reporting readiness.

## Overall delivery history

The following are merged milestones; counts are historical suite sizes, not additional independent tests to sum.

| Milestone | Delivered |
|---|---|
| Early project / PRs #1–#3 | Metadata/download/QC foundations and descriptive supplied-observation, sequence, coverage/evidence/catalogue reviews; scope documentation and user-facing review tools. |
| PR #4, `c3188f9` | Conditional binary alignment/BLAST tooling and allowlisted artifact orchestration; 144-test milestone and optional-tool CI. |
| PR #5, `cb36446` | Portable paths, stage failure/interruption diagnostics, limits and recovery; 161 tests. |
| PR #6, `99e997c` | Reproducibility bundle, preflight/report opening/Linux launcher, snapshot comparison, trusted fallback API, installed smoke/reuse checks, tiny benign paired archive-conversion evidence; 182 tests. |
| PR #7, `b614d4f` | Retry/history improvements, supplied-file reference metadata, digest/control evaluator and paired artificial Tadpole validation; 196 tests. |
| PR #8, `40804a6` | Process tree cleanup and output scanning, owner-aware locks and diagnostics; 208 tests. |
| PR #9, `e1c4791` | Fixed artificial SPAdes diagnostic, real Linux single/paired/reuse evidence, scratch-directory race fix and historical licence audit; 217 tests. |
| PR #10, `dbc8592` | Documentation-only capability audit and correction of stale runtime/API claims; no new functionality. |
| Current handoff pass | Read-only source publication verifier, 12 regression tests, consolidated handoff and documentation navigation/clarification. No new scientific or workflow/plugin integration. |

## Remaining engineering and scientific gaps

Engineering gaps still present include a general plugin registry/adapter interface, richer workflow states and policies, a provenance-rich per-record reference importer, a registered production acquisition alternative, arbitrary-input assembly integration, a unified acquisition-to-review workflow, full dependency pinning/fingerprinting, stronger OS resource containment, broader platform deployment validation and permanent comprehensive runtime-evidence retention. These are not promised or implemented by this handoff. Some would extend the unsupported discovery chain in this project; labeling them generic does not make them delivered or independently in scope.

Ordinary maintenance can continue independently: preserve backward compatibility, fix reproducible defects in existing supported reviews, improve install/packaging diagnostics, and validate release integrity. User QC/results must remain untouched unless a separately authorized task requires otherwise.

External/unimplemented scientific functions include autonomous residual/unknown-sequence recovery, DVG/recombination analysis including ViReMa, functional sequence characterization, biological candidate evaluation/ranking, and independently validated blinded recovery. They are listed only to identify absence. This document supplies no execution/parser schemas or detailed integration contracts for them.

Scientific-validation gaps are separate: appropriate independently curated truth/control data, justified interpretations and calibrated performance, provenance/label accuracy, reference completeness and independent withholding verification. Completing software interfaces would not resolve these. Missing evidence is unknown, not a negative result; passing artificial reconstruction is not evidence of biological discovery capability.

## Eight requested answers

1. **Generic plugin registry operational?** No; fixed allowlist remains.
2. **Drop-in independent external adapter without engine changes?** No supported API exists; current dedicated adapters are not a registry.
3. **New workflow states operational?** No; only pending/running/complete/failed/interrupted are implemented.
4. **Per-record reference import operational?** No; file snapshots and sequence inventories are distinct existing features.
5. **Acquisition fallback infrastructure operational?** Partially: tested trusted-callable retries/history/verification exist. Production automatic fallback and forcibly bounded provider orchestration do not.
6. **Arbitrary-input generic assembly operational?** No; fixed artificial diagnostics only.
7. **Engineering remaining?** The gaps listed above remain. This pass adds source-transfer verification, not the proposed infrastructure integrations.
8. **Ready for another environment?** Ready to import the published source once final CI/merge/source-equality checks pass. Not ready as a complete end-to-end application. Use the final PR's receipt for the concrete source/CI handoff status.

## Repository state and authoritative receipt

Baseline before this pass: `dbc85920e643376384029935da6642e9d1b0b539`; [baseline passing CI](https://github.com/andreiutzx99/atellite-virus-discovery/actions/runs/36112904158). That run had five passing jobs and 217 tests in the optional-tools job. It is historical evidence, not the final run for this pass.

The final merge SHA cannot be embedded literally in the file contained by that same commit: changing the file changes its commit identity. Resolve the exact imported version with `git rev-parse HEAD` and its source tree with `git rev-parse HEAD^{tree}`. The final handoff PR's merged commit and passing **main push** CI URL are recorded in the PR receipt and final response after merge. The [Actions tests history](https://github.com/andreiutzx99/atellite-virus-discovery/actions/workflows/tests.yml) provides commit-specific run status. A green older run must not be substituted for the imported commit.

Authoritative source is GitHub main, including this document, source, tests and workflow configuration. Local environments, ignored data/tools, expiring Actions artifacts and historical prototypes are not part of the released source. No general plugin infrastructure is present; the existing workflow and new release checker are the latest implemented infrastructure. Do not claim otherwise.

## Transfer brief for another platform

> Import `andreiutzx99/atellite-virus-discovery` from GitHub main, using the exact commit in the final handoff receipt. Read `docs/DEVELOPMENT_HANDOFF.md` and `docs/APPLICATION_CAPABILITY_AUDIT.md` before changing code. Historical architecture documents describe unimplemented aspirations, not release capabilities. The application is Python >=3.11, package 0.3.0, with metadata/download/baseline QC, descriptive supplied-artifact reviews, an allowlisted resumable artifact workflow and fixed artificial runtime diagnostics. The final pass adds only a read-only Git source-handoff verifier and its tests plus documentation. There is no general plugin registry, new unavailable/skip workflow-state model, per-record reference importer, production automatic acquisition fallback or arbitrary-input assembly. Verify the exact source, run the software tests and inspect optional-tool CI. Preserve existing user data and completed QC. Distinguish software behavior, dependencies, missing engineering and scientific validation in all reports; do not treat missing modules as negative results. Continue only independently scoped, supported software maintenance. No unsupported scientific integration is authorized or specified by this handoff.
