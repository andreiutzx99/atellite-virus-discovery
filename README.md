# Satellite Discovery — phase 1/2 prototype

A modular starting point for a reproducible helper-associated element research pipeline. **Implemented: public SRA metadata search, parsing, suitability filtering, optional same-study context retrieval, ENA FASTQ availability lookup, and reports.** No raw read downloads, sequence analysis, DVG detection, biological candidate scoring, or biological validation have been performed.

## Run it

Requires Python 3.11 or newer. The current application uses only the Python standard library; no packages need installing. On Windows, double-click `Start.cmd` in this folder for prompts, or open a terminal here:

```console
python -m satellite_discovery --wizard
python -m satellite_discovery --helper influenza-a --limit 10 --include-controls --output runs/influenza-a
```

Open `report.html` in the output folder. `datasets.csv` opens in Excel. `datasets.json` retains structured attributes, exclusions and warnings.

Supported helper labels: `influenza-a`, `influenza-b`, `rhinovirus`, `adenovirus`, `human-coronavirus` (the four endemic human coronavirus search terms), and `sars-cov-2`. These are search categories, not established satellite/helper relationships. Add query aliases in `satellite_discovery/helpers.json` to extend metadata discovery.

`--limit` bounds **experiments**, which can contain several runs. Same-study context adds at most five experiments from each of up to three studies. It is a pilot sampling strategy, not an exhaustive control search. `--min-spots` defaults to 1,000,000 archive spots as an editable initial triage setting; this is not a scientifically validated sensitivity threshold or mapped coverage measurement. All nonexcluded samples remain `eligible_for_review`.

An optional `--query` accepts a custom Entrez metadata expression. Set `NCBI_EMAIL` if desired; `NCBI_API_KEY` is supported and never written to request provenance. Each process stays below three requests per second; do not run many searches concurrently behind the same IP without shared rate limiting.

## Resume or replay

Repeat the exact command to reuse successfully cached responses. A different parameter set requires a new directory. An output directory deliberately freezes its metadata snapshot. Use a new output directory for fresh archive results.

```console
python -m satellite_discovery --helper influenza-a --limit 10 --include-controls --output runs/influenza-a --offline
python -m unittest discover -s tests -v
```

Exit code 0 = complete metadata workflow, 1 = failed workflow, 2 = report produced with failed ENA enrichments. Missing FASTQ links are **unverified availability**, not proof that SRA reads are unavailable. Retrying reuses successful responses and retries failed requests. Do not run two writers into the same output directory.

## Scientific interpretation

Metadata mentions are not infection calls. Same-study samples are not automatically negative controls. Run counts are not independent biological sample counts. Source archive centre names are only provisional laboratory metadata. Library design, sample attributes and missingness must be reviewed before biological inference. AMPLICON libraries are explicitly excluded from unbiased discovery shortlists.

The future system will report computational candidates and associations, never confirmed new satellites. In particular, no-match results, folding predictions, or short terminal matches alone establish novelty or dependency. See [architecture](docs/ARCHITECTURE.md), [validation plan](docs/VALIDATION.md), and [development status](docs/STATUS.md).

## Reproducibility

Each run writes parameters, software/Python/OS versions, command, timestamps, accession list, raw API snapshots, request URLs without credentials, response SHA256 checksums, report checksums and a log. Live databases do not have an immutable release label; the saved response is the reproducible input. Current Python dependency: standard library only. Future sequence tools and reference snapshots need pinned versions and container digests before execution.

## Data sources

Search/retrieval uses [NCBI E-Utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/). Optional download-location metadata uses [ENA file reports](https://ena-docs.readthedocs.io/en/latest/retrieval/programmatic-access/file-reports.html). Client throttling follows [NCBI API guidance](https://www.ncbi.nlm.nih.gov/books/NBK25497/). No Replit app was supplied; the local Python project is portable to a development environment, while later read processing should use a Linux/WSL2 or HPC worker.
