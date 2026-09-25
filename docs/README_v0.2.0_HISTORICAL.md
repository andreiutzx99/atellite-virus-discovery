> Historical version 0.2.0 documentation. Commands and scope below describe
> that earlier release, not current capabilities. See the [current README](../README.md),
> [M1–M6 roadmap](ROADMAP.md), and [M6 scientific audit](M6_AUDIT.md).

# Satellite Discovery — version 0.2.0

Reproducible public sequencing **metadata discovery, bounded FASTQ download and baseline QC**. Implements phases 1–3 in version 0.2.0. Statements below that helper mapping, assembly, or DVG analysis were not implemented apply to that historical version only.

## Start here

**[Step-by-step test guide](USER_TEST_GUIDE_v0.2.0_HISTORICAL.md)**: exact files to open, responses to enter, expected output and troubleshooting.

Requires Python 3.11 or newer. Uses the Python standard library; no extra package installation is needed.

- Double-click **Test-download-QC.cmd** for a repeatable public-data test (~170 MB download).
- Double-click **Start.cmd** for helper selection, metadata search and optional bounded download/QC. The report opens automatically.

From a terminal inside this repository:

```console
python -m satellite_discovery --wizard
python -m satellite_discovery --helper influenza-a --limit 10 --stage qc --max-runs 1 --max-download-mb 1000 --output runs/influenza-pilot
```

`report.html` distinguishes metadata-only execution, completed QC and failed/skipped stages. `datasets.csv` includes exclusion reasons; `datasets.json` preserves structured metadata. No manually supplied reads are required.

## Dataset search

The old default often returned only recent amplicon libraries. New defaults target RNA-Seq/metagenomic WGS for RNA helpers and RNA-Seq/WGS for adenovirus, restrict to supported Illumina libraries, exclude explicitly PCR-selected libraries, and search records published at least 90 days ago. At most two experiments are retrieved before searching other studies; each experiment may still contain multiple runs. Incomplete mirrors, insufficient depth and budget exclusions remain possible and are reported explicitly.

`--limit` is the experiment search budget, not a guaranteed suitable-run count. `--include-controls` adds bounded same-study context (up to five experiments from each of three studies); those samples are not confirmed negatives. `--query` overrides the default date/library restrictions. The resolved query/cutoff is frozen in each run's parameters and reused on resume.

Helper labels: `influenza-a`, `influenza-b`, `rhinovirus`, `adenovirus`, `human-coronavirus`, `sars-cov-2`. These are metadata search categories, not established satellite/helper relationships. Extend aliases in `satellite_discovery/helpers.json`.

## Download and QC

`--stage metadata` is the CLI default. `--stage qc` selects complete supported FASTQ runs with ENA file sizes/MD5 checksums, preferring study diversity then smaller inputs within the run/byte budgets. The MB budget covers **compressed input size**, not total network traffic (retries may retransmit bytes). It never truncates a dataset to fit the budget. Raw inputs remain compressed; QC streams gzip files.

Downloads are verified against byte count and MD5; manifests record local SHA256 checksums. Interrupted downloads use HTTP Range where supported. A server ignoring Range triggers a clean restart. Corrupt files are never marked complete. Supported layouts: single-end, paired R1/R2, and paired plus separate unpaired reads. Missing ENA files or unsupported formats are skipped; **SRA Toolkit fallback is not implemented**.

The portable QC baseline validates FASTQ/Phred+33, sequence lengths and paired identifiers, trims exact adapter matches and low-quality ends, and filters length/mean-quality/N fraction. Defaults: common Illumina core `AGATCGGAAGAGC`, 12-base minimum terminal adapter overlap, end Phred 20, mean Phred 20, minimum length 30, maximum N fraction 0.05. These are engineering defaults, **not validated discovery thresholds**. `--adapter` replaces the adapter list and can be repeated; `--min-length` changes the length cutoff. Remaining thresholds are explicit in `QCConfig` and saved in every QC report.

This is not fastp. It does not provide overlap-based adapter detection, mismatch-tolerant trimming, duplicate inference or low-complexity removal. Original, rejected and surviving orphan reads are retained. Zero surviving reads trigger a visible warning. Advanced processing and tool comparisons remain future work.

## Outputs and resume

```text
runs/<id>/
  parameters.json, manifest.json, run.log
  raw_metadata/                  timestamped, checksummed API snapshots
  datasets.json, datasets.csv
  report.html                    stage-aware summary
  phase3/
    parameters.json, download_plan.json, manifest.json, run.log
    <run-accession>/
      raw/*.fastq.gz             original verified archive inputs
      qc/qc.json                metrics, parameters and hashes
      qc/clean_*.fastq.gz        retained reads; pairs stay together
      qc/orphan_*.fastq.gz       surviving unpaired mates
      qc/rejected.fastq.gz       original rejected records
```

Repeat the **same command and output folder** to reuse verified downloads and QC. Changed settings require a new folder. `--offline` forbids network use. Existing 0.1.0 results remain intact; use a new folder for this version. Do not run concurrent writers into one run directory. Phase 3 uses a lock; see the guide for abrupt-shutdown recovery.

Exit code 0: requested stages completed; 1: fatal error; 2: partial result or no suitable downloads; 130: user interruption. Errors are retained in stage manifests. Completed QC does not establish biological suitability.

## Reproducibility and interpretation

Stages record software/Python versions, commands, parameters, timestamps, accession identifiers, input/output hashes and errors. Archive snapshots have retrieval times and response hashes rather than invented release versions. Raw reads and run directories are excluded from GitHub.

Metadata mentions are not infection calls. Same-study samples are not automatically controls, and runs are not independent biological samples. Missing evidence remains unknown. Shortlisted datasets are **eligible for review**. Spots are archive units, not mapped coverage. Candidate discovery requires the planned blinded validation gate in [VALIDATION.md](VALIDATION.md). See the current [architecture overview](../README.md#pipeline-architecture) and [release status](STATUS.md).

## Tests and sources

```console
python -m unittest discover -s tests -v
```

Tests cover metadata parsing/filtering, report escaping, checksum and resume failures, paired-read handling, QC metrics, resource limits and stage replay. GitHub Actions runs the offline suite.

Sources: [NCBI E-Utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/), [ENA file reports](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/file-reports.html), and [ENA archive-generated files](https://ena-docs.readthedocs.io/en/latest/retrieval/file-download/archive-generated-files.html). Later adapter-method comparisons should use documented [fastp](https://github.com/OpenGene/fastp) behavior. Optional `NCBI_EMAIL`/`NCBI_API_KEY` variables are supported without saving credentials in request URLs. Metadata throttling is per process; shared throttling across multiple processes is not implemented.
