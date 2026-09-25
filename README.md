# Satellite Discovery 0.3.0

Public sequencing metadata retrieval, verified downloads, baseline QC and descriptive review tools. The original end-to-end satellite-discovery design is **not implemented or biologically validated**. The complete feature audit is in [PERMITTED_ROADMAP.md](docs/PERMITTED_ROADMAP.md).

## Start here

For transfer to another development environment, read [DEVELOPMENT_HANDOFF.md](docs/DEVELOPMENT_HANDOFF.md). It inventories the released application, explains tests and dependencies, and explicitly lists unimplemented functionality. `python scripts/check_handoff.py` checks source publication against live `origin/main`; CI and application completeness are separate checks.

Use Python 3.11 or newer. On Windows, double-click **Start.cmd** (or **Run-reviews.cmd**) and select the numbered review. On Linux, use **Run-reviews.sh**. The menu asks for existing files and an output folder, then prints the report path. No optional bioinformatics executable is required for the pure-Python review tools. See [Windows/Linux/WSL/HPC setup and recovery](docs/DEPLOYMENT.md).

For an installed command on Windows or Linux, run `python -m pip install .` in a Python virtual environment, then use `satellite-reviews` to open the same numbered menu. See [portability and recovery instructions](docs/CONDITIONAL_TOOLS.md).

Menu 20 previews configuration, 12 runs or resumes an artifact workflow, 21 opens reports, and 22 compares verified reference snapshots. Every started artifact workflow writes a compact `reproducibility.json`, including on failure.

Available reviews include RNA/DNA metadata, sample/control observations, FASTA inventory, alignment coverage (interval CSV or SAM/gzip-SAM), reference-match evidence, linked catalogues, existing report dashboards, imported nucleotide BLAST tables, existing QC integrity, and optional dependency versions. See [precise input instructions](docs/USER_TEST_GUIDE.md) and [file contracts](docs/REVIEW_INFRASTRUCTURE.md).

`Audit-existing-run.cmd` audits completed QC without repeating it. `Test-Tadpole.cmd` is a separate artificial-fixture diagnostic for a pinned local BBTools installation; it does not process biological runs. Optional executables, databases and `.tools` are not bundled or installed by a source checkout.

## Acquisition and scope

The existing SRA/ENA acquisition and QC components are preserved. New metadata searches use the eight requested exact model keys and conservative metadata gates, documented in [REVISED_SCOPE.md](docs/REVISED_SCOPE.md). Missing stock evidence remains unknown/held. Metadata labels are not proof of sample identity, infection or biological safety. Broad legacy helper labels cannot start new acquisition runs.

Existing version 0.2.0 installations and completed run directories remain untouched. `Test-download-QC.cmd` explains its retired broad-helper shortcut. Historical instructions are retained separately and are not current commands.

## Tests and limits

```console
python -m unittest discover -s tests -q
```

The public test suite uses artificial fixtures and mocked archive services. It verifies software contracts, not discovery sensitivity. Reports never turn arbitrary scores into probabilities or missing observations into absence. Supplied BLAST hits do not establish novelty; exact duplicate groups are not inferred viral families.

See [module interfaces](docs/MODULE_INTERFACES.md) for unsupported/unavailable stages and the [registered assembly guide](docs/ASSEMBLY.md) for arbitrary-input SPAdes/Tadpole use. Assembly processes supplied FASTQ but does not perform biological discovery or interpretation. Local historical mapping/assembly/BLAST prototypes are preserved in the developer working directory but are not part of the released source or user interface. Public source status is defined by the feature audit, not by untracked local files.

## Conditional tools and workflow extension

The 22 partial/dependency-limited audit entries have now been reconsidered individually: [A/B/C decisions](docs/PARTIAL_FEATURE_FOLLOWUP.md). See the [quick progress report](docs/PROGRESS_REPORT.md) and [conditional-tool instructions](docs/CONDITIONAL_TOOLS.md). `Run-artifact-workflow.cmd` connects permitted existing-artifact stages with verified resume. It does not activate category-4 biological discovery functions.

See [the artifact validation report](docs/ARTIFACT_VALIDATION_REPORT.md) for the post-PR6 changes, tested capabilities and remaining work. Menu23 evaluates supplied file-digest/control tables. An executable example is in `examples/artifact-benchmark/workflow.json`.
