# Verify an existing QC run

## Windows launcher

1. Double-click `Audit-existing-run.cmd` in the project folder.
2. Paste the full run-folder path (the folder containing `report.html`) and press Enter.
3. If the folder contains multiple QC runs, enter the listed run number.
4. Enter `1` for checksums and recorded accounting, or `2` to also recount reads and check paired identifiers. Press Enter.
5. On success, the browser opens a report headed **QC integrity audit**, with status **passed**. New reports are saved in the project folder under `audits/<timestamp>/`; existing run files stay unchanged.

If an error appears, copy the line beginning `Audit failed:`. You do not need to repeat the download or QC to use this tool.

The read-only audit accepts completed portable QC results, including version 0.2.0. It checks all recorded output SHA256 hashes and reconciles the saved input, retained, rejected, paired, orphan and single-read counts. It does not download files, rerun filtering, change source files or perform biological analysis.

Run from the project directory, replacing both example paths:

```console
python -m satellite_discovery.qc_audit --qc-dir "C:\your-run\phase3\SRR123\qc" --output "C:\audits\SRR123.json"
```

Success prints `QC integrity audit passed` and exits with code 0. Failure exits with code 1 and does not write a success report. Choose a new output filename outside the source QC directory each time.

The default verifies compressed file hashes and recorded accounting; it does not recount FASTQ records. Add `--full` to parse every output record, reconcile observed counts and check retained paired-read identifiers and mate labels. This can take substantially longer for large runs.

Add `--html` to also save a readable HTML report beside the JSON. Both output names must be new; existing reports are not overwritten. For example, `--output audit.json --full --html` produces `audit.json` and `audit.html` after a successful full audit.

Hashes establish consistency with the saved QC record, not independent authenticity of that record. A successful audit does not establish sample identity, biological suitability, infection or candidate detection.

Development status: current synthetic mapping fixtures pass; biological classification remains unvalidated. See [mapping status](SYNTHETIC_MAPPING_STATUS.md). The mapping shortcut is a synthetic diagnostic, not a completed next-stage biological workflow.
