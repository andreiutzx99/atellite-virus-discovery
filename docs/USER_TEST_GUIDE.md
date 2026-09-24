# Current user instructions

Your completed SRR32283557 download/QC run does not need to be repeated. No additional user test is required for this update.

1. Open the current `satellite-discovery` repository folder (not the older `satellite-discovery-v0.2.0` installation).
2. Double-click **Run-reviews.cmd**.
3. Enter a menu number and press Enter. Paste each requested full file path. Choose a new output folder; use the same folder only when deliberately verifying reuse of unchanged inputs.
4. Open the exact `report.html` path printed after completion. If it fails, retain the error and output folder; do not delete completed QC.

| Menu | Purpose | Inputs |
|---|---|---|
| 1 | RNA/DNA library metadata review | Existing datasets.json |
| 2 | Study/control observation comparisons | Samples CSV and observations CSV |
| 3 | Sequence inventory and exact duplicate groups | Supplied nucleotide FASTA |
| 4 | Alignment-block coverage | Reference lengths, samples, aligned blocks CSVs |
| 5 | Reference-match and technical-control evidence | Feature lengths, matches, controls CSVs |
| 6 | Link existing sequence catalogues | Catalogue imports CSV |
| 7 | Existing report dashboard | Reports root folder and new HTML filename |
| 8 | Alignment coverage | Existing SAM or gzip-compressed SAM |
| 9 | Import existing nucleotide BLAST hits | Feature lengths CSV, reference provenance CSV, standard 12-column outfmt 6 table |
| 10 | Audit existing QC | Completed run folder or its qc folder; then checksum or full recount mode |
| 11 | Optional tool versions | New report folder; no read data, downloads or installation |
| 0 | Exit | None |

The exact CSV schemas, bounds and limitations are in [REVIEW_INFRASTRUCTURE.md](REVIEW_INFRASTRUCTURE.md), [observation instructions](OBSERVATION_REPORTS.md), and [sequence inventory](SEQUENCE_INVENTORY.md). If a referenced input is unavailable, the program does not synthesize evidence for it.

For menu 10, the existing run folder supplied during development is:

`C:\Users\ad6752\Documents\Codex\2026-09-19\a\outputs\satellite-discovery-v0.2.0\satellite-discovery\runs\20260920-142711`

The audit reads that folder and writes a separate report. Details: [QC_INTEGRITY_AUDIT.md](QC_INTEGRITY_AUDIT.md). The optional [Tadpole diagnostic](TADPOLE_RUNTIME_CHECK.md) requires its separately installed pinned runtime; it is not an assembly option for biological runs.

Version checks distinguish executable presence, successful version output and failed checks. They are not functional validation. Portable local tools can be detected even when absent from PATH. BAM/CRAM needs an additional supported decoder; changing a filename extension will not convert a file.

The later conditional-tools extension adds menu options 12–19 and expands menu 8 to optional BAM/CRAM. See [CONDITIONAL_TOOLS.md](CONDITIONAL_TOOLS.md) for exact schemas, dependency conditions and the artificial workflow example. The prior table describes the foundation options; it is not the complete current menu.
