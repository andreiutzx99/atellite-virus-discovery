# Development handoff

Prepared 2026-09-25 from the verified main baseline `77b47c7c855ccda794956b348bfa728dde20e469`. GitHub repository: [andreiutzx99/atellite-virus-discovery](https://github.com/andreiutzx99/atellite-virus-discovery). Distribution: `satellite-discovery`, version `0.3.0`, Python 3.11 or newer. Milestone 1 is merged as PR #12. Milestone 2 was developed on `feature/milestone-2-reference-acquisition` from the stated baseline; its implementation and limits are documented below.

## Read this first

This is a working metadata/download/QC application with descriptive reviews of independently supplied artifacts, an allowlisted review workflow, and isolated artificial runtime diagnostics. Milestone 2 adds provenance-rich per-record reference imports and a registered ENA/NCBI acquisition path. It is **not** a complete or scientifically validated discovery application. Read acquisition/QC, artifact review and artificial assembly diagnostics remain separate capabilities; installing optional tools does not create an end-to-end discovery chain.

Milestone 1 added a trusted stage registry, a generic bounded external-tool adapter contract, eight explicit stage states, an external-module placeholder and one harmless text adapter. Milestone 2 adds immutable per-record reference snapshots and comparisons, plus a trusted provider registry with ENA primary acquisition and a conditional NCBI SRA Toolkit fallback. Existing QC/results and earlier workflow stages remain intact. No ViReMa, DVG analysis, candidate discovery, biological ranking or interpretation is implemented.

The distinction between a source transfer and a complete application is essential: a GitHub handoff can be ready while the requested broader application remains incomplete. A test count is not a requirement-completion percentage.

## Released architecture and source map

| Component | Source files | Current behavior and limits |
|---|---|---|
| Package and entry points | `pyproject.toml`, `satellite_discovery/__init__.py`, `__main__.py`, `cli.py` | Standard-library base application; installed commands `satellite-discovery` and `satellite-reviews`. Python >=3.11. No bundled optional runtime or database. |
| Metadata | `database_query.py`, `metadata.py`, `metadata_filter.py`, `model_scope.py`, `workflow.py` | Bounded archive requests, cache/provenance, normalized run records, explicit metadata inclusion/exclusion/unknown handling, JSON/CSV/HTML reports. Metadata assertions do not establish scientific identity. |
| Read acquisition | `sequence_downloader.py`, `read_workflow.py`, `acquisition_providers.py` | Budgeted ENA FASTQ is primary; eligible SRR runs may use the registered NCBI SRA Toolkit fallback under explicit workflow policy. Provider/transfer attempts, checksums, provenance, QC artifacts and reuse verification are recorded. The real external fallback remains conditionally unvalidated; see below. |
| Baseline QC | `quality_control.py` | Existing read checks/filtering and retained original/trimmed categories. This is the repository's baseline implementation, not integration of fastp, FastQC or MultiQC. |
| Read-only QC integrity | `qc_audit.py`, `audit_wizard.py` | Audits existing run artifacts without rerunning QC; reports integrity discrepancies. `Audit-existing-run.cmd` is the launcher. |
| Local archive conversion | `sra_conversion.py` | Explicit conversion of a supplied local archive using external SRA Toolkit, paired-output checks, command/version/provenance, bounded execution and verified reuse. Failed prior files are retained separately to avoid stale-mate acceptance. Not automatic remote retrieval. |
| Acquisition retry contract | `acquisition_fallback.py` | Trusted callables provided by application code; deterministic provider order, classified failures, caller-persisted attempt history, timestamps and verification before acceptance. The read workflow supplies an explicit failure-class fallback policy; each provider applies its own time/storage limits. |
| Library metadata review | `library_review.py` | Descriptive RNA/DNA/mixed/unknown labels and conflicts from supplied metadata; no automatic downstream tool selection. |
| Supplied observations | `observation_report.py`, `context_review.py` | Supplied sample/control observations, stratified context and paired quantitative reports with explicit missingness/denominators. Does not discover events in reads or infer causality. |
| Sequence inventory | `sequence_catalogue.py`, `sequence_quality.py` | Supplied FASTA parsing, length/composition/descriptors, exact duplicate groups, SQLite/CSV/FASTA/report outputs. This remains separate from the provenance-rich reference-record importer and does not perform approximate clustering or functional interpretation. |
| Coverage and alignment decoding | `coverage_review.py`, `alignment_adapter.py` | Existing interval/SAM/gzip-SAM coverage review; optional pysam or samtools for BAM/CRAM. CRAM requires a supplied reference. No mapping or residual-read extraction stage. |
| Supplied similarity evidence | `blast_import.py`, `local_comparison.py` | Import existing nucleotide BLAST tables or run BLAST against independently supplied references; retain commands, versions, logs and outputs. External BLAST required for execution. No-hit does not establish novelty. |
| Supplied evidence/control review | `contamination_review.py` | Descriptive match coverage and technical-control evidence flags with uncertainty. No validated biological classifier or probability model. |
| Catalogue links | `catalogue_linker.py` | Link existing sequence inventories/occurrences by exact identity; no approximate family assignment. |
| Reference snapshots | `reference_snapshot.py`, `reference_record_import.py` | Verified file-level snapshots can be expanded into immutable per-record snapshots with stable internal IDs, normalized sequence hashes, provenance, conflict reports, SQLite/CSV/FASTA outputs, indexed lookups and read-only comparisons. No curated collection is included. |
| Supplied digest evaluator | `artifact_benchmark.py` | Exact supplied SHA256/control tables, produced/classified/unclassified counts and recurrence, including explicit zero-output completed datasets. Does not independently verify the underlying files or upstream withholding; not a biological recovery benchmark. |
| Stage lifecycle | `review_stage.py`, `stage_lock.py`, `portable_paths.py`, `workflow_states.py` | Shared output manifests/digests, owner-aware locks and explicit state-transition rules for pending, running, complete, skipped, dependency-missing, external-module-required, failed and interrupted stages. No automatic stale-lock deletion. |
| Bounded native processes | `bounded_process.py` | Argument-list execution, separate stdout/stderr capture for external adapters, stage-local working directory, time/output monitoring, retained logs and process cleanup. POSIX groups and Windows PID-specific tree cleanup have documented limits; no hard CPU/RAM/filesystem quota or hostile-process sandbox. |
| Stage registry and review orchestration | `artifact_workflow.py`, `stage_registry.py` | Deterministic trusted-code registry keeps the earlier built-ins and registers the reference-record import stage, harmless external adapter and declarative external-module placeholder. Workflow JSON cannot import modules or provide commands. Ordered execution and verified earlier-stage artifacts remain supported. |
| External-tool adapter | `external_tool.py`, `example_transform_adapter.py`, `example_transform_tool.py` | Required/optional input declarations, executable/version/hash checks, safe argv execution, timeout and output limits, separate logs, checksummed output inventory, provenance, failure states and verified reuse. The example performs only an artificial text transform. |
| Provenance | `reproducibility.py` | Workflow configuration, registry snapshot, source hashes, Git when available, Python/OS, selected optional-package versions, input/output identities, stage states and external-tool manifests. Not a complete dependency lock or scientific certification. |
| User interface | `review_ui.py`, `report_generator.py`, launchers | Numbered terminal menu, HTML/CSV/JSON reports, existing-report dashboard, read-only workflow preview and report opening. No general plugin manager or unified discovery UI. |
| Environment checks/setup | `dependency_review.py`, `portable_setup.py` | Version/import/PATH diagnostics and existing pinned portable BLAST setup. Discovery/version success is not functional validation. Some probes refer to tools without implemented analysis adapters. |
| Artificial assembler diagnostics | `scripts/test_tadpole_runtime.py`, `scripts/check_tadpole_ci.py`, `artificial_spades.py`, `scripts/check_spades_ci.py` | Fixed generated artificial fixtures, single/paired execution and verified reuse. Tadpole validated on Windows/Linux; SPAdes on Linux. No arbitrary-input assembly or workflow assembly stage. |
| Release verification | `scripts/check_handoff.py`, `tests/test_handoff.py` | New read-only source publication check using Git and live origin/main, tested against disposable local repositories. Separate from application workflows and CI certification. |

## Actual pipeline map

```text
Metadata / selected reads
  -> ENA-primary acquisition, conditional NCBI SRA fallback, baseline QC and integrity checks
  -> retained files and QC reports

Independently supplied artifacts and references
  -> trusted registry of built-in and external-tool review stages
  -> descriptive reports / catalogues / control summaries
  -> explicit workflow states and reproducibility files

Verified file-level reference snapshot
  -> per-record import, immutable catalogue and comparison

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

The schema remains `artifact-workflow-v1` and accepts 1–30 ordered stages. Existing files without new `config` or `skip` fields remain valid. Stages select a registered kind and supply its required inputs; trusted adapters may also declare optional inputs. File paths resolve relative to the specification. References to earlier-stage outputs are accepted only after checking a completed manifest and artifact digest.

All earlier built-in kinds remain registered: `sra_conversion`, `inventory`, `sequence_quality`, `library`, `observations`, `context`, `quantitative`, `alignment`, `cram`, `blast_import`, `blast_compare`, `contamination`, `catalogue_links`, `reference_snapshot`, and `artifact_benchmark`. The registry adds `reference_record_import` and also contains `example_text_transform` and the generic `external_module` requirement stage.

The eight stage states are `pending`, `running`, `complete`, `skipped`, `dependency_missing`, `external_module_required`, `failed` and `interrupted`. Valid transitions are defined centrally. A stage can be explicitly skipped with `"skip": true`; skipped work is not complete. Missing executables and unregistered modules are distinct infrastructure statuses, not analytical outcomes. Ordinary failures still stop execution and leave later stages pending. A mixture of complete and skipped stages is summarized as `partial`.

The `external_module` stage uses a safe module identifier and supplied input/configuration data. It resolves only through trusted code registrations; it never imports a module named in JSON. If unavailable, the workflow records `external_module_required` and what is missing without changing earlier outputs. If an external executable is absent, it records `dependency_missing` before invoking the adapter. Neither infrastructure status, nor `skipped`, is a successful analysis, zero observations or absence of evidence. Unknown stage kinds and fields fail validation.

Each started artifact workflow writes `workflow.json`, `report.html` and `reproducibility.json`, including failure, interruption and infrastructure states. Reports show readable state labels and reasons. External stage manifests capture adapter/tool identity, executable hashes/version output, input hashes, configuration, safe argv, environment, timestamps, duration, exit status, logs and output hashes. Reuse requires matching identities and a verified complete output inventory, never folder existence alone. Changed/failed external stages require a new stage output folder. A forcibly killed process may leave a lock; verify its owner before manual recovery. Existing user run directories must be preserved.

## Plugin architecture: current answer

The operational `WorkflowStageRegistry` is populated only by trusted application code. Existing built-ins and the example adapter use the same registry. New trusted adapters can register a stable stage kind, module name, input contract, configuration validator and handler without adding another branch to the workflow dispatcher. The registry is deterministic and inspectable.

Workflow files are data-only: they cannot provide shell commands, Python expressions, imports or executable paths. The adapter contract and harmless reference implementation are documented in [EXTERNAL_TOOL_ADAPTERS.md](EXTERNAL_TOOL_ADAPTERS.md). Adapters are trusted code; process limits are not a sandbox for hostile programs. No scientific external adapter is included, and engineering support does not validate domain interpretation.

## Launchers and reports

Windows: `Start.cmd` or `Run-reviews.cmd`. Linux: `sh Run-reviews.sh`. Installed command: `satellite-reviews`. Base review operations need no optional scientific runtime.

| Menu | Existing function |
|---|---|
| 1–6 | Library metadata; observations; FASTA inventory; interval coverage; supplied evidence/control review; linked catalogues |
| 7–11 | Existing-report dashboard; alignment coverage; BLAST-table import; QC integrity audit; optional dependency diagnostics |
| 12–16 | Artifact workflow; supplied-reference BLAST; context; paired quantitative reports; sequence descriptors |
| 17–19 | File-level reference snapshot; portable BLAST setup; explicit local archive conversion |
| 20–23 | Read-only workflow preview; open existing HTML report; snapshot comparison; supplied-digest/control evaluation |

Not all standalone diagnostic modules are exposed in the menu. Reference-record import is available as a registered workflow stage, not a new numbered menu action. The dashboard reads reported states and does not independently verify every linked artifact. The workflow HTML report distinguishes complete, running, skipped, dependency missing, external module required, failed and interrupted stages. WSL and HPC usage guidance exists, but no real WSL/HPC deployment has been demonstrated; Ubuntu CI does not establish that.

## Dependencies and packaging

| Dependency | Required for | Evidence / qualification |
|---|---|---|
| Python >=3.11 | Base application and tests | CI matrix is Python 3.11/3.12 on Windows/Ubuntu; not a claim of all OS/Python combinations. |
| Git | New handoff verifier and its fixture tests | Full history, main and origin/main required for the checker. Not required for most installed review functions. |
| pysam 0.24.1 or samtools | Conditional binary alignment decoding | Real artificial BAM/CRAM Linux tests; pure text alternatives remain available. |
| NCBI BLAST+ | Existing supplied-reference comparison | Real artificial Linux tests and prior Windows evidence. |
| matplotlib | Optional figure export | Optional extra accepts >=3.8,<4; CI installs 3.10.1. |
| SRA Toolkit | Explicit local archive conversion; conditional remote NCBI fallback | Prior tiny benign yeast Windows validation with 3.4.1 covers the separate local conversion feature. The automatic NCBI fallback requires `prefetch`, `vdb-validate` and `fasterq-dump`; the current Replit environment and declared optional-tools CI job do not install them. |
| Java and BBTools | Fixed artificial Tadpole diagnostic | Prior Java 17 / BBTools 40.01 evidence; pinned archive verified by diagnostic setup. They are not required for the new text-transform adapter. |
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

`check_installed.py` tests installed package resources/entry points and fixed artificial review/reuse/provenance operations. It does not use completed user QC runs. The Milestone 1 baseline was 246 collected tests. Milestone 2 adds per-record import, provenance, conflict, lookup/comparison and provider/fallback coverage; the current suite has 259 collected tests. The local dependency-free run passed 256 and skipped the three existing optional-runtime tests. Fake executable tests exercise the NCBI command wrapper, bounds, output checks and failure handling; they do not prove a real SRA Toolkit run. The optional-tools CI job does not install SRA Toolkit.

**NCBI runtime status:** conditional external dependency — implementation tested with controlled fixtures; real SRA Toolkit execution still requires runtime validation.

The existing handoff-checker tests use temporary local Git repositories and a local bare remote: clean matching source, merged and unmerged branches, untracked/modified files, unpublished main, live-remote disagreement despite stale tracking refs, stash detection, missing committed handoff files, expected-commit mismatch, detached HEAD, remote failure, timeout/malformed commit, and shallow-clone rejection. They perform no biological operations or internet access. Git absence skips these fixture tests, so a no-Git local result is not full verification.

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
| Prior handoff pass | Read-only source publication verifier and 12 regression tests; brought the baseline to 229 tests. No scientific integration. |
| Milestone 1 / PR #12 | Trusted stage registry, generic external-tool adapter, eight stage states, module requirement placeholder, harmless runtime-tested text adapter, adapter documentation and 17 regression tests. Local result: 243 passed, 0 failed, 3 optional-tool skips. PR and branch-push CI each passed all five jobs; [PR #12](https://github.com/andreiutzx99/atellite-virus-discovery/pull/12) merged as `96b6d057d5dcda7c7f1862a3696ef3cae1eb024c`. The [post-merge main run](https://github.com/andreiutzx99/atellite-virus-discovery/actions/runs/36137959715) also passed all five jobs. No biological adapter or Milestone 2 work. |

## Milestone 2: reference records and acquisition

### Per-record reference imports

`reference_record_import` is a trusted `artifact-workflow-v1` stage. It accepts only `references.csv` from a completed, verified file-level reference snapshot, verifies each FASTA member against its declared byte count and SHA256, and writes a separate immutable record snapshot. It does not change the parent snapshot or any existing QC/results.

The record snapshot contains `records.csv`, `records.fasta`, indexed `catalogue.sqlite`, `snapshot.json`, `conflicts.json`, `validation.json`, and `report.html`. The workflow manifest records the input identity and output hashes; lookups and comparisons first verify the completed snapshot and all seven outputs. A changed parent, importer identity or output requires a new output folder rather than silently reusing stale results.

Each FASTA record remains distinct, including records with duplicate identifiers across different reference files or identical sequences. Stable internal record IDs are derived from the supplied reference ID and FASTA ID. Sequences are uppercased and whitespace is removed before length, SHA256 and exact-sequence grouping are calculated. Supplied source, category, version, database version, parent snapshot/file identity, original header and provenance are retained. Explicit accession-shaped tokens may be parsed with a version; no accession is inferred from sequence.

Duplicate identifiers within one FASTA are invalid. Reused FASTA IDs across files, accession/version changes and conflicting sequences are reported; conflicts set `review_required` and are never resolved or merged automatically. Invalid FASTA creates a failed stage with `validation.json`, not a completed record catalogue. Inputs are capped at 100 MB per file, 10,000 records and 20 million bases. Exact lookups support internal record ID, FASTA ID, accession with optional version, or sequence SHA256. Snapshot comparisons report added, removed, changed and unchanged records without modifying either source snapshot. This is not a taxonomy, completeness, biological suitability or reference-curation assessment.

### Provider order, fallback and verification

The trusted provider registry orders `ena_fastq` first and `ncbi_sra_toolkit` second; workflow configuration selects registered names and cannot import provider code or supply commands. The read planner limits automatic NCBI fallback candidates to non-excluded Illumina RNA-seq/WGS SRR runs with known spot counts and SINGLE or PAIRED layout. An unavailable ENA file-size estimate reserves the full configured acquisition budget for that run rather than pretending the size is known.

Fallback is explicitly enabled only for `timeout`, `remote_unavailable`, `metadata_unavailable`, `record_unavailable`, `file_unavailable` and `integrity_failure`. Dependency-missing, unsupported-layout, budget, conversion and unclassified execution failures are reported rather than treated as permission to switch providers. Completed acquisitions pass their provider-specific verifier before QC accepts them.

ENA uses the Portal file report and HTTPS FASTQ endpoint; each file is checked against declared byte count and provider MD5, with local SHA256 also recorded. Up to three transfer attempts can resume a partial HTTP transfer; running, retrying, failed and complete transfer states are retained in the phase 3 manifest. NCBI accepts SRR run accessions, runs `prefetch`, `vdb-validate` and `fasterq-dump --split-3`, records tool paths/versions/hashes, commands and logs, validates FASTQ syntax and paired identifiers/mate orientation, and records local archive and FASTQ SHA256. NCBI does not provide a FASTQ checksum in this path. Completed NCBI attempts are reusable only after engine identity, manifest metadata, archive and FASTQ outputs are verified; incomplete attempts are retained as diagnostic evidence, not accepted as complete.

The per-run byte budget also limits the converted compressed FASTQ output. NCBI prefetch and conversion have a 60-minute process timeout, `vdb-validate` has a five-minute timeout, and the conversion workspace is capped at 20 GiB with a 64 MiB allowance. Missing `prefetch`, `vdb-validate` or `fasterq-dump` is reported as `dependency_missing`. The application and current optional-tools CI job do not install SRA Toolkit. Fake executables exercise wrapper behavior and controlled fixtures; they do not establish compatibility with a real toolkit version or successful live NCBI retrieval.

## Remaining engineering and scientific gaps

Engineering gaps still present include arbitrary-input assembly integration, a unified acquisition-to-review workflow, full dependency pinning/fingerprinting, stronger OS resource containment, broader platform deployment validation and permanent comprehensive runtime-evidence retention. The registry foundation does not supply any biological adapter. These gaps are not promised as part of Milestone 1 or 2.

Ordinary maintenance can continue independently: preserve backward compatibility, fix reproducible defects in existing supported reviews, improve install/packaging diagnostics, and validate release integrity. User QC/results must remain untouched unless a separately authorized task requires otherwise.

External/unimplemented scientific functions include autonomous residual/unknown-sequence recovery, DVG/recombination analysis including ViReMa, functional sequence characterization, biological candidate evaluation/ranking, and independently validated blinded recovery. They are listed only to identify absence. This document supplies no execution/parser schemas or detailed integration contracts for them.

Scientific-validation gaps are separate: appropriate independently curated truth/control data, justified interpretations and calibrated performance, provenance/label accuracy, reference completeness and independent withholding verification. Completing software interfaces would not resolve these. Missing evidence is unknown, not a negative result; passing artificial reconstruction is not evidence of biological discovery capability.

## Milestone 1 acceptance status

1. **Is the registry operational?** Yes. It deterministically registers existing built-ins and trusted adapters and rejects duplicate/unknown names.
2. **Can trusted adapters be added without redesigning the dispatcher?** Yes. Registration and the adapter contract are documented in [EXTERNAL_TOOL_ADAPTERS.md](EXTERNAL_TOOL_ADAPTERS.md).
3. **Can workflow JSON execute arbitrary shell/Python code?** No. It can select registered identifiers and provide validated data only.
4. **Are all eight stage states operational?** Yes. States and transitions are centralized and reported separately.
5. **Does `external_module_required` work?** Yes. An unregistered module requirement is recorded without dynamic import or modification of completed earlier outputs.
6. **Does `dependency_missing` work?** Yes. A missing executable is reported before adapter execution.
7. **Is the example adapter runtime tested?** Yes. It runs a harmless text transform through the bounded process runner.
8. **Is external provenance and verified reuse recorded?** Yes. Adapter/tool identity, executable, inputs, configuration, argv, environment, duration, status, logs and output hashes are captured; changed identities or output hashes prevent reuse.
9. **What remains before another milestone?** Review this implementation and decide separately whether to authorize further work. Milestone 2 adds infrastructure only; no biological analysis or interpretation is included.

## Repository state and authoritative receipt

Verified development baseline before Milestone 1: `c5b5eb15d737601b48009a090faef7717c92d54a`; baseline reproduction was 229 passing tests with no skips. Milestone 1 PR #12 merged as `96b6d057d5dcda7c7f1862a3696ef3cae1eb024c`; the main-branch run `36137959715` passed all five jobs. The completion receipt reports the current main commit after the handoff-documentation follow-up.

The implementation merge SHA and its passing main-branch run are recorded above. Resolve the exact current imported version with `git rev-parse HEAD` and its source tree with `git rev-parse HEAD^{tree}`. Verify the Replit checkout against GitHub main after merge. The [Actions tests history](https://github.com/andreiutzx99/atellite-virus-discovery/actions/workflows/tests.yml) provides commit-specific run status. A green older run must not be substituted for the imported commit.

Authoritative source is GitHub main, including this document, adapter documentation, source, tests and workflow configuration. Local environments, ignored data/tools, expiring Actions artifacts and historical prototypes are not part of the released source. The registry is an infrastructure extension point only; it does not establish end-to-end scientific functionality.

## Transfer brief for another platform

> Import `andreiutzx99/atellite-virus-discovery` from GitHub main at the exact commit in the final handoff receipt. Read `docs/DEVELOPMENT_HANDOFF.md`, `docs/EXTERNAL_TOOL_ADAPTERS.md` and `docs/APPLICATION_CAPABILITY_AUDIT.md`. The application is Python >=3.11, package 0.3.0, with metadata/download/baseline QC and descriptive supplied-artifact reviews. Milestone 1 adds a trusted stage registry, a safe external-tool adapter contract, explicit workflow states and a harmless text fixture adapter. Milestone 2 adds per-record reference snapshots and an ENA-primary, conditionally available NCBI SRA acquisition fallback. Workflow configuration cannot supply commands or imports. No biological adapter, DVG analysis, candidate discovery, ranking or interpretation is implemented. Preserve existing user data and completed QC. Distinguish software behavior, dependencies, missing engineering and scientific validation; do not interpret skipped or unavailable work as negative evidence. Do not start further milestones before review.
