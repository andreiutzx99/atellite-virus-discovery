# Conditional tools and artifact workflow

This extension consumes existing artifacts. It does not perform the original autonomous satellite-discovery workflow or change its category-4 interfaces.

## Quick start without optional tools

Double-click `Run-artifact-workflow.cmd`, supply the full path to `examples/artifact-workflow/workflow.json`, then choose a new output folder. It inventories an artificial FASTA and passes its verified normalized FASTA into descriptive sequence-quality reporting. Rerun with the same specification/output to verify reuse. A failed later step can resume while completed steps are integrity-checked. Changes to inputs, code or settings require a new output folder. A lock left by an abruptly terminated process must only be removed after confirming that process has stopped.

Equivalent command from the repository root:

```console
python -m satellite_discovery.artifact_workflow --manifest examples/artifact-workflow/workflow.json --output runs/artifact-demo
```

Each step has `id`, `kind` and `inputs`. Input values are paths relative to the workflow JSON, or `{"stage":"earlier_id","artifact":"filename.ext"}`. Only earlier, completed, hash-verified artifacts can be referenced. No arbitrary commands, plugins, forward references, discovery steps or shell scripts are accepted. The `FIELDS` registry in `artifact_workflow.py` is the exact list of supported inputs. The workflow reports linked results and records failures; it does not treat a blocked dependency as success.

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

## BAM/CRAM

The adapter automatically uses importable `pysam`, otherwise `samtools` on PATH. It does not require an alignment index because it streams the complete file. CRAM requires an explicit local reference FASTA; the reference is copied into the owned output folder before native decoding so source files are not indexed or edited. Native decoding runs in a child process with a 180-second time limit and bounded output. The existing strict SAM parser then computes coverage. Input, decoded SAM and supplied reference are each limited to 256 MB for this review tool.

On a compatible Linux/macOS Python environment, install the optional dependency with `python -m pip install -e ".[alignment]"`. Native Windows Python on this machine still has no compatible wheel for the pinned `pysam==0.24.1`; no unverified third-party binary is bundled. A supported samtools installation on PATH is an alternative. Windows without either decoder continues to accept SAM/gzip-SAM. The Linux optional CI job installs pysam and samtools and exercises real BAM and CRAM decoding through both backends using artificial data.

Pair columns count flags on accepted primary records. They are not deduplicated molecules, verified mate pairs or proof of assembly support.

Sources: [pysam installation](https://pysam.readthedocs.io/en/stable/installation.html), [pysam alignment API](https://pysam.readthedocs.io/en/stable/api.html), [published pysam distributions](https://pypi.org/project/pysam/0.24.1/).

## Local BLAST and reference snapshots

BLAST+ discovery checks PATH, then one unambiguous portable installation under `.tools`. Every reference FASTA ID must have exactly one CSV row with `reference_id,reference_role,reference_source,reference_version`. Roles follow the existing contamination-review vocabulary. Each run builds a local nucleotide database from those supplied references, records commands and executable hashes/versions, runs standard nucleotide BLAST defaults with one thread, and exports `features.csv`, `matches.csv` and `hit_status.csv`. No hit is not evidence of novelty. BLAST database and log artifacts are retained and checked on reuse.

A workflow can pass BLAST `features.csv` and `matches.csv` into the existing `contamination` stage together with a separately supplied controls table. No automatic rejection or biological classification is added.

Menu 18 installs only the pinned NCBI Windows BLAST+ 2.17.0 archive. SHA256 verification, path/type checks, extraction limits, a lock and existing-file verification prevent silent replacement of changed tools. It uses no admin access. Other platforms can supply their package-manager BLAST installation on PATH. Runtime availability is distinct from scientific reference coverage. [NCBI command-line documentation](https://www.ncbi.nlm.nih.gov/sites/books/NBK569856/).

Reference snapshot JSON has a `files` list. Every entry requires `name`, `sha256`, `bytes`, `source`, `version`, `role`, and exactly one of `path` (relative to the specification) or `url` (credential-free HTTPS). Up to 100 files and 100 MB total are supported. Files are copied/downloaded and verified, never silently updated; a new snapshot needs a new specification/output folder. This manages explicit references, not automatic taxonomic selection or comprehensive database curation.

## Context, quantitative data and sequence descriptors

Context CSV fields: `sample_id,study_id,laboratory,country,lane,control_status,control_source,library_molecule,strand`. Use explicit `unknown` values for missing context. Control status is `negative`, `positive`, `technical` or `unknown`; asserted controls need a source. Assay is `RNA`, `DNA`, `mixed` or `unknown`; strand is `forward`, `reverse`, `unstranded` or `unknown`. The observations CSV retains `sample_id,feature_id,detection`. Reports retain every stratum; neither shared laboratory nor geography proves independence or contamination.

Quantitative CSV fields: `sample_id,feature_id,study_id,assay,x_unit,y_unit,x,y`. Values are finite numbers or `unknown`. Pearson r is calculated only within identical feature/study/assay/unit strata, with at least three complete pairs and nonconstant values. No normalization, p-value, causal interpretation or confidence score is inferred. Optional `python -m pip install -e ".[plots]"` adds matplotlib scatter exports: at most 12 strata and 2,000 displayed pairs per stratum, explicitly scaled axes. The numeric table uses all supplied rows.

Sequence-quality reports add longest identical-symbol run and called-dinucleotide diversity/concentration. These measurements do not reject sequences or diagnose technical artefacts.

## SRA conversion boundary

Menu 19 activates if a compatible NCBI `fasterq-dump` is on PATH. It converts an existing local archive (pilot cap 100 MB), checks plain output layout, writes deterministic gzip copies, validates FASTQ syntax and counts, and checks mate-count agreement. It requires 2 GB free disk space and limits native execution to 300 seconds/1 GB of intermediate output. Full mate-ID checks remain in QC. This adapter is unit-tested with a process fixture; a real SRA Toolkit conversion has not been runtime-validated here. It is not yet an automatic remote-archive fallback in the acquisition wizard.

## Not added

Approximate viral-family clustering, ORF/functional discovery analysis and novel-element reconstruction remain the existing category-4 interfaces. SPAdes can be version-detected if installed, but its biological assembly stage is not activated. No Replit connector is available; these standard Python entry points can be used in an independently configured Python environment without assuming a provider-specific plugin.
