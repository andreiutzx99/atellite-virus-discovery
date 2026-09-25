# Application capability audit — 2026-09-25, Milestone 1

Audited source: Milestone 1 development branch based on verified main commit `c5b5eb15d737601b48009a090faef7717c92d54a`. The prior main baseline had 229 passing tests. This milestone adds registry/adapter/state infrastructure only; it does not add acquisition, reference-import, assembly or biological analysis functionality. No user QC/results were changed.

A = implemented and software-tested within its stated scope; B = scientific interpretation/performance remains unvalidated; C = external runtime/data dependency; D = missing engineering; E = unsupported/external scientific functionality. A component can have several labels; a passing software test does not remove B or C.

| Area | Status | Implemented extent | Remaining limitation |
|---|---|---|---|
| SRA/ENA acquisition | A/C; fallback D | Metadata retrieval and budgeted ENA FASTQ download with existing checks/reuse | Retry callback infrastructure is not a registered production alternative. `read_workflow` imports failure diagnostics, not the fallback executor. |
| FASTQ conversion | A/C | Explicit local SRA conversion with fasterq-dump, syntax/pair checks, provenance and reuse | External Toolkit required; not an automatic remote fallback. Prior benign paired runtime evidence exists. |
| QC | A/B | Baseline read checks/filtering and retained read categories | Not equivalent to other QC packages; does not establish biological suitability. Separate read workflow. |
| Integrity | A | Input/output hashes, completed-stage verification, identity checks and existing QC audit | Not a proof of scientific correctness or source truth. Implementation changes can require a fresh output folder. |
| Alignment-file handling | A/B/C | Existing SAM/gzip-SAM coverage; optional BAM/CRAM decoding, reference required for CRAM | No read mapping or extraction stage; external native decoder required for binary formats. |
| Reference management | A/B/C; per-record D | Pinned file-level snapshots, supplied provenance and comparison between snapshots | Sequence inventory has per-sequence records, but it is not the requested provenance-rich per-record reference importer. No complete curated reference collection. |
| Generic comparison | A/B/C | Supplied query/reference BLAST execution and existing-hit import | External BLAST and independently supplied references; no-hit does not establish novelty. |
| Assembly infrastructure | A/C for diagnostics; arbitrary-input adapter D/E | Fixed artificial Tadpole and SPAdes execution/reuse tested | No arbitrary-read assembler adapter and no assembly stage in the artifact workflow. |
| Artifact/sequence catalogues | A/B | Supplied FASTA inventory, exact duplicates/groups, SQLite/CSV/FASTA and linked occurrences | Exact identity is not a biological family assignment or approximate clustering. |
| Recurrence/control analysis | A/B | Supplied observation/control tables, strata, denominators and exact-digest recurrence | Does not detect events in reads, validate control labels or establish causal dependence. |
| External-tool interfaces | A/C; scientific adapter D/E | Deterministic trusted stage registry, generic bounded adapter contract, dependency/version/hash inspection, separate logs, provenance, output inventory and verified reuse | Only a harmless text fixture is added. No ViReMa or other scientific adapter; process runner is not a hostile-code sandbox. |
| Reporting/UI | A with explicit workflow states | Numbered review menu, linked HTML/CSV/JSON reports, preflight, report opening and readable states/reasons | Not every diagnostic is exposed in the menu; there is no universal plugin installer or arbitrary-input assembler launcher. |
| Reproducibility | A with D limits | Artifact-workflow environment, code hashes, configuration, paths/digests, timestamps and available stage command records | Git revision may be unknown outside a checkout; not every installed runtime/library is fingerprinted; no independent reference-withholding proof. |

## Actual application map

These are separate implemented entry points, not one continuous discovery run:

```text
Metadata / selected public reads
  -> existing download, QC and integrity workflow
  -> verified retained files and QC reports

Independently supplied existing artifacts
  -> trusted registry-based review workflow
  -> comparison / catalogue / control reports (where the supplied inputs fit)
  -> reproducibility bundle

Fixed generated artificial fixtures
  -> standalone assembler diagnostics
  -> diagnostic evidence only

Autonomous scientific discovery chain
  -> NOT IMPLEMENTED / UNSUPPORTED MODULES
     (no executable bridge is supplied between the entry points above)
```

The diagram does not imply that existing review stages consume every preceding output automatically. Each stage has its own input schema; only already compatible earlier-stage artifacts can be handed off.

## Workflow, status and UI findings

`WorkflowStageRegistry` replaces hard-coded branching as the workflow's dispatch mechanism while retaining the existing built-in kinds. Trusted application code registers stage handlers and external adapters. Workflow JSON can choose only registered stage/module identifiers and validated data; it cannot supply executable commands, Python imports or expressions. The generic placeholder records an unavailable module instead of importing it dynamically.

The eight stage states are `pending`, `running`, `complete`, `skipped`, `dependency_missing`, `external_module_required`, `failed` and `interrupted`. Valid transitions are defined centrally. Missing executables and missing trusted modules have distinct infrastructure states and stop the workflow without changing completed earlier outputs. Explicitly skipped stages are not complete. Ordinary failures still stop execution, leaving later stages pending.

Completed stages verify their saved artifacts on reuse. External adapter reuse checks inputs, configuration, adapter source/version, executable identity, relevant environment and every inventoried output hash. A failed or changed external stage requires a fresh stage output folder. Forced termination can leave locks requiring operator verification. There is no general checkpoint-resume capability for every external tool.

The review menu provides implemented reviews and dependency checks, workflow preflight/run, report opening, snapshot comparison and supplied-digest evaluation. It does not provide a universal external-module installer, plugin manager or arbitrary-input assembler launcher.

## Provenance assessment

The artifact-workflow bundle records software/Python/platform details, source hashes, Git revision when available, configuration, the registry snapshot, stage timestamps and input hashes. External tool manifests additionally capture adapter/tool identities, executable paths/hashes/version output, safe argv, stdout/stderr, exit status and checksummed outputs. This records what the software ran; it does not independently certify supplied data or scientific conclusions.

An absent implementation, unassessed input, missing dependency or failed execution must not be described as a negative finding. No ViReMa-derived evidence or `confirmed_non_DVG` determination exists in the released application. The more specific proposed external-evidence status model has not been implemented or validated.

## Milestone 1 answers

1. **Registry operational?** Yes. Built-ins and trusted adapters are registered deterministically; duplicate and unknown names fail safely.
2. **Can workflow config execute arbitrary shell/Python?** No. Config selects registered identifiers and validated data only.
3. **Are all eight workflow states operational?** Yes, with centralized transitions and report labels.
4. **Do missing module/dependency states work?** Yes. Both are distinct infrastructure states and neither represents an analytical negative.
5. **Is external execution tested and provenance recorded?** Yes. The artificial text adapter executes at runtime; logs, tool/adapter/input/configuration/environment details, output checksums and reuse are covered by tests.
6. **Is a biological adapter included?** No. ViReMa, DVG analysis, satellite-virus discovery, ranking and interpretation remain unimplemented and were not started.

## Documentation corrections and validation

Updated the current capability summary for the trusted registry, adapter contract, external-module placeholder and workflow states. The adapter-specific implementation contract is in `EXTERNAL_TOOL_ADAPTERS.md`. Historical architecture documents remain proposals and are not evidence of installed or validated scientific modules.

The local full suite collected 246 tests: 243 passed, 0 failed and 3 optional-tool tests skipped because optional tools are not installed in this environment. PR #12's pull-request and push runs, plus the post-merge main run, passed all five GitHub CI jobs including optional tools; the handoff links to the run records. No existing user QC/results were rerun or modified.
