# Observational comparison stage

This stage imports existing observation tables. It does not infer detections from reads or produce candidate rankings. The bundled example is fictional and is not a finding from a public dataset.

## Run the example

From the project folder:

```console
python -m satellite_discovery.observation_report --samples examples/observations/samples.csv --observations examples/observations/observations.csv --output runs/observation-example
```

Open `runs/observation-example/report.html`. Repeat exactly the same command to verify and reuse the completed outputs. The second execution checks every output hash; it does not rebuild the database or overwrite the report.

For other input tables, double-click `Compare-observations.cmd`. Enter the full path to each input CSV and a new output folder when prompted. No downloads or existing QC runs are changed.

## Inputs

`samples.csv` requires:

| Column | Meaning |
|---|---|
| sample_id | Unique biological sample or technical-control ID, not a sequencing-run ID |
| study_id | Study identifier or the explicit value `unknown` |
| condition | Supplied condition label: `positive`, `negative`, or `unknown` |
| sample_type | `biological`, `technical_control`, or `unknown` |
| library_molecule | `RNA`, `DNA`, `mixed`, or `unknown`, based on assay metadata |

`observations.csv` requires `sample_id`, `feature_id`, and `detection`. A feature is a supplied unclassified-sequence/feature identifier; no sequences are needed. Detection must be `present`, `absent`, or `unknown`. Missing rows become unknown, never absent. An absent call should come from an explicit assessment with a documented detection method; the software cannot verify that assessment.

Repeated sequencing runs from one biological sample must be reconciled upstream using a documented policy. Duplicate sample IDs or duplicate sample/feature calls are rejected rather than silently summed. Different sample IDs are assumed to identify different samples; the program cannot discover mislabeled duplicates.

RNA, DNA, mixed and unknown assays are kept separate in comparisons. A DNA virus can occur in an RNA assay, and an RNA-derived library can be sequenced as cDNA. Organism genome type does not establish assay molecule type. Missing or conflicting assay metadata should remain unknown until reviewed.

## Outputs

- `recurrence.csv`: biological present/absent/unknown sample counts and distinct study identifiers with detections.
- `comparisons.csv`: within-study, assay, sample-type and condition counts; observed fractions use only explicitly assessed samples.
- `summary.json`: machine-readable counts and interpretation limits.
- `observations.sqlite`: normalized sample and observation tables with unique keys and foreign-key checks.
- `report.html`: escaped HTML tables and simple sample-count bars, usable offline.
- `manifest.json`: timestamps, input hashes, output hashes, command, Python version, engine hash and status.

Observed fractions are descriptive ratios, not calibrated probabilities. No score, significance test, causal inference, helper-dependency inference, or sequence ranking is produced. Distinct study IDs do not guarantee independent laboratories or biological replication. Technical controls are displayed separately from biological negative samples. This stage cannot rule out index hopping or contamination.

The matrix is limited to 100,000 sample/feature cells. The SQLite database is an export for this cohort, not a global sequence-search database.

## Recovery and integrity

Changed inputs or changed engine code require a new output folder. Completed outputs with mismatched hashes are rejected without overwriting them. Ordinary failed attempts can be rerun with unchanged inputs; the database is rebuilt as an atomic replacement, avoiding duplicate imports. An exclusive lock prevents simultaneous writers.

After a forced process termination, a lock may remain. Confirm no report process is running before removing only `.observations.lock` in that report folder. Rerun the same command. Keep the original input files and previous evidence. This small stage recomputes its report after an interrupted attempt; it never reruns download, QC, mapping or assembly.

## Unimplemented component contract

The observational stage accepts pre-existing validated observation tables. It does not create them from the unfinished sequence-analysis modules. See [module interfaces](MODULE_INTERFACES.md) for explicit status and boundaries. A missing stage must be reported as `not_implemented`, not as an empty successful result.
