# Software progress report

The project is an operational public-data preparation and descriptive artifact-review toolkit. It is not a completed or biologically validated satellite-discovery system.

## Working software

- SRA/ENA metadata retrieval, constrained dataset selection, verified downloads, baseline QC, resumability and read-only QC integrity audits.
- RNA/DNA metadata review; FASTA catalogue, exact duplicate groups and export; SQLite catalogues; study/control observations and recurrence.
- Coverage from supplied intervals/SAM/gzip-SAM, plus optional BAM/CRAM decoding and descriptive pair-flag counts.
- Existing BLAST-table import and executable local BLAST+ comparison against supplied, documented references.
- Supplied laboratory/country/lane/control/strand context, quantitative association tables, repeat/ambiguity descriptors, HTML/CSV/JSON reports and optional scatter plots.
- Checksum-pinned reference snapshots, portable Windows BLAST setup, dependency/version checks and a resumable workflow connecting permitted artifact stages.

## Still conditional or requiring work

- Native Windows pysam is unavailable here. BAM/CRAM activates with pysam or samtools in a compatible environment; real decoder tests are included in Linux CI.
- Local SRA conversion activates with fasterq-dump, but has only process-fixture validation here. Automatic remote-SRA conversion fallback is not integrated into acquisition.
- SPAdes is absent; Tadpole retains its tested artificial-fixture diagnostic. Neither is activated for the category-4 biological reconstruction workflow.
- Replit is not configured. Standard Python entry points can be used on another independently configured machine, but no connector execution is claimed.
- Scientific rejection rules, reliable-assembly decisions, contamination-source attribution and comprehensive reference curation still need external evidence and validation. Descriptive statistics do not replace these.
- Approximate viral-family clustering, ORF/functional discovery analysis and the other existing category-4 interfaces remain unchanged.

All 22 previously partial/dependency-limited entries have individual [A/B/C decisions](PARTIAL_FEATURE_FOLLOWUP.md). “Addressed” means reviewed and the feasible generic portion implemented; it does not mean the original scientific requirement is fully solved.

## What you need to do

No rerun of completed QC is needed. To try the new dependency-free workflow, double-click `Run-artifact-workflow.cmd`, select `examples/artifact-workflow/workflow.json`, and choose a new output folder. The included data are artificial. Exact optional-tool and input instructions are in [CONDITIONAL_TOOLS.md](CONDITIONAL_TOOLS.md).
