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

## Verification

The optional Linux job successfully installed the documented dependencies and passed real pysam/samtools BAM/CRAM equivalence, BLAST and matplotlib-export tests on artificial data. Windows and Ubuntu offline jobs also passed. [First complete optional-tool CI run](https://github.com/andreiutzx99/atellite-virus-discovery/actions/runs/36013987940).

The preceding milestone contained 144 tests. Dependency-free jobs intentionally skip the three real-tool tests; the optional-tools job executes them. Windows BLAST comparison/reuse and pinned portable-installation verification passed in that milestone. SRA conversion remains process-fixture tested, not live-runtime validated.

## Infrastructure reliability follow-up

Inspected baseline `c3188f9` and reproduced its 144-test result on Windows/Python 3.12.5 (three optional runtime tests skipped). The follow-up suite has 161 tests, passing locally with the same three skips. It adds portable-name regression tests, stage-specific failure/interruption reports, recovery checks, snapshot provenance and pre-copy size checks, subprocess working-directory/budget tests, and a fast-decoder log-limit regression. CI now covers Python 3.11 and 3.12 on Windows and Ubuntu, installed-package checks, and the existing Linux optional-tool job. CI outcomes must be read from the corresponding PR checks; configuration alone is not a runtime result.

No completed user QC dataset was opened or rerun. Changes to lifecycle identities intentionally require new review output folders; old artifacts remain untouched. The [current component status table](INFRASTRUCTURE_STATUS.md) separates completed software contracts from dependency, external-validation, and scope limits.
