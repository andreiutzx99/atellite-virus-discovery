# Application capability audit — 2026-09-25

Audited source: main after PR #9 (`e1c4791567d8bcfa88ef9e89a59b60f7c7c60af3`). Validated baseline: 217 tests and five passing CI jobs. This change corrects documentation and records gaps; it implements none of the requested acquisition/reference/assembly/plugin extensions. No user QC was changed or rerun. No new biological analysis, runtime installation or licence audit was performed.

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
| External-tool interfaces | A/C for existing adapters; general plugin API D/E | Specific supplied-artifact adapters, dependency probes, bounded process utility | No dynamic caller registry, configurable arbitrary commands or drop-in ViReMa adapter API. |
| Reporting/UI | A; requested unified status UI D | Numbered review menu, linked HTML/CSV/JSON reports, preflight and report opening | Not every diagnostic is exposed in the menu; dependency errors do not have the requested dedicated workflow state. |
| Reproducibility | A with D limits | Artifact-workflow environment, code hashes, configuration, paths/digests, timestamps and available stage command records | Git revision may be unknown outside a checkout; not every installed runtime/library is fingerprinted; no independent reference-withholding proof. |

## Actual application map

These are separate implemented entry points, not one continuous discovery run:

```text
Metadata / selected public reads
  -> existing download, QC and integrity workflow
  -> verified retained files and QC reports

Independently supplied existing artifacts
  -> fixed allowlisted review workflow
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

`artifact_workflow.FIELDS` and `dispatch` are a hard-coded allowlist. Unknown kinds/configuration fields fail validation. No runtime plugin import, registry registration or arbitrary shell step exists. Acquisition/QC and arbitrary-input assembly are not registered stages. Historical module-contract documentation is not an executable extension API.

Artifact-workflow stages are recorded as `pending`, `running`, `complete`, `failed` or `interrupted`. Execution stops on failure; later steps remain pending. The requested `skipped`, `external_module_required` and `dependency_missing` workflow states are not implemented. Dependency failures can be visible as errors, but that is not equivalent to those distinct states. Unsupported kinds fail preflight rather than appearing as skipped stages.

Completed stages verify their saved artifacts on reuse. A rerun can reuse completed work and retry later work under unchanged identities, but individual adapters can require a fresh folder after failure; the SPAdes diagnostic deliberately does so. Forced termination can leave locks requiring operator verification. There is no general checkpoint-resume capability for every external tool.

The review menu provides implemented reviews and dependency checks, workflow preflight/run, report opening, snapshot comparison and supplied-digest evaluation. It does not provide a universal external-module installer, plug-in manager or arbitrary-input assembler launcher. No additional UI states or execution paths were added by this audit.

## Provenance assessment

The artifact-workflow bundle records software/Python/platform details, source hashes, Git revision when available, configuration, stage timestamps and input hashes. It collects supported stage manifests and command records, and preserves supplied reference metadata where that stage records it. This is evidence of what the software recorded, not independent certification of the supplied data or reference completeness.

An absent implementation, unassessed input, missing dependency or failed execution must not be described as a negative finding. No ViReMa-derived evidence or `confirmed_non_DVG` determination exists in the released application. The more specific proposed external-evidence status model has not been implemented or validated.

## Six requested answers

1. **Percentage/portion implemented:** no defensible percentage for the full requested application. Each of the 13 broad areas above has some supporting code, but counting that as 100% completion would be misleading. The repository has tested acquisition/QC and supplied-artifact review capabilities, plus isolated diagnostics; the requested end-to-end chain is incomplete. Tests count checks, not completed requirements.
2. **External modules still required:** existing optional operations require their documented external executables/libraries. The requested autonomous biological analysis capabilities are absent, not merely missing installations. Installing an assembler or ViReMa alone would not connect them to this application.
3. **Future ViReMa contract:** no detailed operational adapter contract is supplied in this context. The earlier broad provenance principles do not constitute a supported parser/execution schema or integration specification.
4. **Drop-in independently developed ViReMa adapter:** no. The current fixed dispatch engine does not expose such a plug-in API, and compatibility or scientific validity cannot be asserted for an unimplemented adapter.
5. **Other end-to-end gaps:** per-record reference provenance, registered production fallback, arbitrary-input assembly, independent withholding verification, unified dependency/skip states, general plug-in orchestration and broader dependency pinning remain absent. This audit does not implement them or represent them as complete.
6. **Engineering versus scientific gaps:** engineering includes missing registration, import/provenance features, UI/state handling and runtime packaging. Scientific gaps include curated truth/control sets, justified biological interpretation and independently assessed performance. Implementing engineering alone would not establish scientific validity. The requested discovery-enabling integrations remain outside the work provided here.

## Documentation corrections and validation

Corrected stale module-table claims that SPAdes had no runtime validation, that supplied-reference BLAST execution was unreleased, and that binary alignment decoding was only a gap. Clarified that historical placeholder statuses are not actual workflow states. Updated menu documentation for option 23 and process-cleanup limits. No detailed unsupported biological schemas were added.

Validation for this change consists of reading the cited code paths and checking documentation consistency. No new tests or repeated user analyses are warranted for a documentation-only update. The existing CI workflow still runs automatically for the PR; its results are recorded with the PR. The 217-test baseline is historical evidence, not a claim that the unimplemented capabilities were tested.
