# Conditional tools and artifact workflow

This extension consumes existing artifacts. It does not perform the original autonomous satellite-discovery workflow or change its category-4 interfaces.

## Quick start without optional tools

Double-click `Run-artifact-workflow.cmd`, supply the full path to `examples/artifact-workflow/workflow.json`, then choose a new output folder. It inventories an artificial FASTA and passes its verified normalized FASTA into descriptive sequence-quality reporting. Rerun with the same specification/output to verify reuse. A failed later step can resume while completed steps are integrity-checked. Changes to inputs, code or settings require a new output folder. A lock left by an abruptly terminated process must only be removed after confirming that process has stopped.

Equivalent command from the repository root:

```console
python -m satellite_discovery.artifact_workflow --manifest examples/artifact-workflow/workflow.json --output runs/artifact-demo
```

Use a read-only configuration/dependency/cache preview before execution:

```console
python -m satellite_discovery.artifact_workflow --manifest examples/artifact-workflow/workflow.json --output runs/artifact-demo --preflight
```

`--preflight` validates declared inputs and artifact contracts, checks dependencies, and reports planned, reusable, blocked, or missing-input stages. It does not execute workflow stages. `--output` is optional for preflight and required for execution.

On Linux, WSL2, or a compatible HPC login environment, install into a user-owned Python 3.11+ virtual environment with `python -m pip install .`, then start the numbered menu with `satellite-reviews`. The same entry point is installed on Windows. Optional executables must be available on that environment's PATH (including scheduler jobs); a Windows installation does not supply Linux executables to WSL. No administrator access is needed for the base Python package. HPC scheduler submission and site-specific module configuration are not provided or validated.

The workflow writes `report.html`, `workflow.json`, and `reproducibility.json` while running and on failure. The manifest records workflow/configuration identity, Git/runtime information, stage order and graph, input/output artifact descriptors, dependency reports, reference-record snapshot IDs, execution/reuse status, warnings, failures, and final report paths. Artifact descriptors include contract version, checksum, size, producer, validation state, and provenance. Each stage records pending/running/complete/failed/interrupted/dependency-missing/external-module-required status, timestamps, and any exception type/message. A missing input is attributed to its stage; later stages stay pending. Completed-stage links are relative so the HTML remains usable when the whole output folder is copied. A graceful interrupt releases the workflow lock; forced process termination still requires the manual lock check above. Resume reuses completed outputs only after stage manifests, contracts, and hashes are verified. New lifecycle/engine versions intentionally require a new output folder; historical QC is not rerun or modified.

Stage IDs and snapshot filenames must be portable: case-only duplicates and Windows device names such as `CON`, `NUL`, and `COM1` are rejected on every platform before work starts. Snapshot names cannot collide with report/manifest names, including by case.

Each step has `id`, `kind` and `inputs`. Input values can be paths relative to the workflow JSON, explicitly typed files such as `{"path":"reads.fastq.gz","artifact_type":"validated_fastq"}`, or `{"stage":"earlier_id","artifact":"filename.ext"}`. Stage handoffs are checked against registered input/output contracts before execution; only earlier, completed, hash-verified artifacts can be referenced. No arbitrary commands, plugins, forward references, discovery steps or shell scripts are accepted. The trusted stage registry is the source of supported fields and contracts. The workflow reports linked results and records failures; it does not treat a blocked dependency as success.

## Integrated typed workflow (Milestone 4)

The generic `artifact-workflow-v1` runner can connect already-supported components without taking ownership of their data:

```text
declared FASTQ (or converted / explicitly validated FASTQ)
  -> FASTQ validation -> registered SPAdes or Tadpole assembly
  -> canonical contig FASTA -> exact sequence catalogue
  -> declared immutable reference snapshot -> per-record import -> declared roles
  -> local BLAST comparison -> descriptive occurrence/control handoff
  -> workflow report
```

The flow is assembled from registered stage IDs and exact artifact names. FASTQ can enter through `fastq_validate`, an existing SRA conversion result, or an explicitly typed QC FASTQ; QC is not rerun. Catalogue observations link exact sequence hashes to declared sample/control metadata and preserve their source catalogue checksums. Reference roles come only from supplied snapshot metadata. No automatic reference curation or biological interpretation is performed.

`workflow_report` produces machine-readable `report.json` and human-readable `report.html` from declared JSON summaries. The root `report.html` also shows stage execution/reuse, runtime and dependency details, verified structured summaries, checksummed inputs/outputs, warnings, failures, and links to stage/final reports. It distinguishes completed comparisons, no configured-reference match, missing dependencies, failed stages, and stages not executed; a missing BLAST dependency is never represented as zero matches. The BLAST stage retains executable identities and command parameters in `commands.json`, raw and restored hit tables, logs, and database files. It records an empty `configured_thresholds` object because no additional identity/coverage filter is applied; BLAST executable defaults remain in effect. Short deterministic internal identifiers accommodate BLAST's local-ID length limit; reported matches map back to the immutable record IDs.

The deterministic test fixture is artificial: a seeded synthetic sequence, an exact supplied-reference match, distinct sample/control catalogues, and an ambiguous no-hit record. Test it with `python -m unittest discover -s tests -p 'test_artifact_workflow_m4.py' -v`. The real single-/paired-end SPAdes and Tadpole workflows are conditional integration tests; run them with `RUN_OPTIONAL_TOOL_TESTS=1` when those dependencies are installed. Tool execution and artificial fixtures validate software handoffs only, not sensitivity, specificity, or biological discovery.

## New menu options

| Menu | Function | Required inputs |
|---|---|---|
| 8 | SAM/gzip-SAM/BAM/CRAM coverage and pair-flag counts | Existing alignment; explicit local reference for CRAM |
| 12 | Resumable artifact workflow | Workflow JSON and output folder |
| 13 | Executable local BLAST comparison | Query FASTA, reference FASTA, reference roles/provenance CSV |
| 14 | Supplied sample context | Context samples CSV and observations CSV |
| 15 | Supplied quantitative associations | Measurements CSV |
| 16 | Sequence quality descriptors | Existing FASTA |
| 17 | Pinned reference snapshot | JSON specification with exact file hashes/sizes |
| 18 | Portable Windows BLAST setup | Uses the project .tools folder; may download the pinned official archive |
| 19 | Conditional local SRA conversion | Local .sra archive; fasterq-dump on PATH |
| 20 | Read-only workflow configuration preview | Workflow JSON; reports missing paths without executing |
| 21 | Open existing report | Local HTML file; prints path on headless systems |
| 22 | Reference snapshot comparison | Two completed snapshots and a new comparison output folder |
| 23 | Supplied artifact-digest/control evaluation | Dataset status, expected digest and observed artifact CSVs |

See [deployment and reproducibility instructions](DEPLOYMENT.md) and the [assembly stage guide](ASSEMBLY.md). Unknown workflow/stage configuration fields are rejected rather than ignored. Dependency reports include prefetch, vdb-validate, Tadpole and isolated pysam/matplotlib checks. The generic assembly stage is registered separately from the fixed artificial diagnostics; version checks and software execution do not establish biological assembly quality.

## BAM/CRAM

The adapter automatically uses importable `pysam`, otherwise `samtools` on PATH. It does not require an alignment index because it streams the complete file. CRAM requires an explicit local reference FASTA; the reference is copied into the owned output folder before native decoding so source files are not indexed or edited. Native decoding runs in a child process with a 180-second time limit and bounded output. The existing strict SAM parser then computes coverage. Input, decoded SAM and supplied reference are each limited to 256 MB for this review tool.

On a compatible Linux/macOS Python environment, install the optional dependency with `python -m pip install -e ".[alignment]"`. Native Windows Python on this machine still has no compatible wheel for the pinned `pysam==0.24.1`; no unverified third-party binary is bundled. A supported samtools installation on PATH is an alternative. Windows without either decoder continues to accept SAM/gzip-SAM. The Linux optional CI job installs pysam and samtools and exercises real BAM and CRAM decoding through both backends using artificial data.

Pair columns count flags on accepted primary records. They are not deduplicated molecules, verified mate pairs or proof of assembly support.

Sources: [pysam installation](https://pysam.readthedocs.io/en/stable/installation.html), [pysam alignment API](https://pysam.readthedocs.io/en/stable/api.html), [published pysam distributions](https://pypi.org/project/pysam/0.24.1/).

## Local BLAST and reference snapshots

BLAST+ discovery checks PATH, then one unambiguous portable installation under `.tools`. Every reference FASTA ID must have exactly one CSV row with `reference_id,reference_role,reference_source,reference_version`. Roles follow the existing contamination-review vocabulary. Each run builds a local nucleotide database from those supplied references, records commands and executable hashes/versions, runs standard nucleotide BLAST defaults with one thread, and exports descriptive hit/evidence tables and a structured summary. Short internal query/reference IDs are mapped back to the original declared IDs before reporting. No hit means only “no match found under the configured comparison”; it is not evidence of novelty or confirmed absence. BLAST database, raw/restored hit tables, ID mapping, and log artifacts are retained and checked on reuse.

A workflow can pass BLAST `features.csv` and `matches.csv` into the existing `contamination` stage together with a separately supplied controls table. No automatic rejection or biological classification is added.

Menu 18 installs only the pinned NCBI Windows BLAST+ 2.17.0 archive. SHA256 verification, path/type checks, extraction limits, a lock and existing-file verification prevent silent replacement of changed tools. It uses no admin access. Other platforms can supply their package-manager BLAST installation on PATH. Runtime availability is distinct from scientific reference coverage. [NCBI command-line documentation](https://www.ncbi.nlm.nih.gov/sites/books/NBK569856/).

Reference snapshot JSON has a `files` list. Every entry requires `name`, `sha256`, `bytes`, `source`, `version`, `role`, and exactly one of `path` (relative to the specification) or `url` (credential-free HTTPS). Up to 100 files and 100 MB total are supported. Files are copied/downloaded and verified, never silently updated; a new snapshot needs a new specification/output folder. This manages explicit references, not automatic taxonomic selection or comprehensive database curation.

Optional `accession` and `database_version` fields preserve supplied provenance. Omitted fields are reported as `unknown`. The references table also records `retrieved_utc`, meaning when this local snapshot was populated, not the source publication date. Verified reuse retains that timestamp. Local file sizes are checked against the declaration before copying. Version output in menu 11 now includes `fasterq-dump`; this is an availability diagnostic, not a functional conversion test.

The common external-process runner rejects invalid time/byte budgets before launch, runs in its owned stage directory, and checks retained files against its stage byte budget. The runner uses POSIX process-group cleanup or Windows PID-specific tree cleanup and preserves logs. These are polling limits, not OS quotas: tools can overshoot between checks. Windows cleanup requires a live parent and POSIX descendants that leave their group are not contained. See PROCESS_RELIABILITY_REPORT.md for the precise limits. Existing over-budget intermediates are preserved and reported rather than silently removed.

## Context, quantitative data and sequence descriptors

Context CSV fields: `sample_id,study_id,laboratory,country,lane,control_status,control_source,library_molecule,strand`. Use explicit `unknown` values for missing context. Control status is `negative`, `positive`, `technical` or `unknown`; asserted controls need a source. Assay is `RNA`, `DNA`, `mixed` or `unknown`; strand is `forward`, `reverse`, `unstranded` or `unknown`. The observations CSV retains `sample_id,feature_id,detection`. Reports retain every stratum; neither shared laboratory nor geography proves independence or contamination.

Quantitative CSV fields: `sample_id,feature_id,study_id,assay,x_unit,y_unit,x,y`. Values are finite numbers or `unknown`. Pearson r is calculated only within identical feature/study/assay/unit strata, with at least three complete pairs and nonconstant values. No normalization, p-value, causal interpretation or confidence score is inferred. Optional `python -m pip install -e ".[plots]"` adds matplotlib scatter exports: at most 12 strata and 2,000 displayed pairs per stratum, explicitly scaled axes. The numeric table uses all supplied rows.

Sequence-quality reports add longest identical-symbol run and called-dinucleotide diversity/concentration. These measurements do not reject sequences or diagnose technical artefacts.

## SRA conversion boundary

Menu 19 activates if a compatible NCBI `fasterq-dump` is on PATH. It converts an existing local archive (pilot cap 100 MB), checks plain output layout, writes deterministic gzip copies, validates FASTQ syntax/counts and paired identifiers/orientation. It requires 2 GB free disk space and limits native execution to 300 seconds/1 GB of intermediate output. Empty conversion outputs fail explicitly. Successful scratch is cleaned; failed outputs are preserved on retry so stale mates cannot be accepted. A real Windows Toolkit 3.4.1 paired yeast conversion and verified reuse passed: [evidence and exact validation limits](validation/SRA_VALIDATION.md). It is not an automatic remote-archive fallback in the acquisition wizard.

Menu 22 verifies every recorded artifact in both snapshots before reporting added/removed/changed/unchanged files. Content hashes, versions and supplied provenance changes are detected; retrieval time alone is not treated as a reference change. The snapshot manifest SHA256 is its recorded identity. No existing snapshot is updated in place, and cached comparisons reject modified source artifacts.

## Not added

Approximate viral-family clustering, ORF/functional discovery analysis and novel-element reconstruction remain outside the supported workflow. The registered SPAdes/Tadpole assembly stage handles supplied FASTQ as a generic file-processing step; it does not perform candidate discovery or biological interpretation. See [the assembly stage guide](ASSEMBLY.md).
