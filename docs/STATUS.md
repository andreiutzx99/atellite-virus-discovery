# Development status

## Verification on 19 September 2026

- 15 offline unit/integration tests passed on Python 3.12.5, Windows.
- Live influenza metadata search plus bounded study context: seven runs, all excluded (amplicon libraries).
- Live RNA-Seq influenza metadata query: three runs, all eligible for review; infection status remains unknown.
- Both runs replayed with the network function forced to fail if called. JSON, CSV and HTML SHA256 hashes were unchanged.
- See `smoke-results.json` for tested accession lists. Full response snapshots and reports are retained locally under `runs/` and excluded from Git.
- Initial test failures came from restrictive permissions on Python-created Windows temporary directories. The test fixture now creates unique scratch directories with inherited permissions; production output directories were unaffected.


| Phase | Status |
|---|---|
| 1 architecture/repository | Implemented: modular Python package, design, CLI, CI definition |
| 2 SRA metadata | Implemented: bounded querying, full package parsing, per-run normalization, explicit filtering, ENA location metadata, bounded same-study context, reports and snapshot replay |
| 3 downloads/QC | Planned; no FASTQ downloaded |
| 4 helper mapping | Planned |
| 5 DVG discrimination | Planned |
| 6 assembly/contaminant analysis | Planned |
| 7 features | Planned |
| 8 candidate scores | Design only; no calibrated model or candidate scores |
| 9 known positives | Validation design only; no raw-data rediscovery performed |
| 10 negative controls | Validation design only |
| 11 exploratory sequence screen | Not started; requires validation |
| 12 catalogue/cross-dataset sequence search | Architecture only |

Current limitations: simple lexical metadata query, newest-first experiment sampling, incomplete sample metadata, provisional archive-centre laboratory field, bounded/nonexhaustive study context, no read-confirmed helper/control status, no automatic BioSample supplementary fetch, no GUI beyond the beginner wizard and static HTML. Output size is bounded by experiments rather than runs. Standard library Python 3.12 was used locally; CI definition is present but CI execution must be checked separately.

The metadata shortlist is reviewable, not an automatically validated analysis cohort. Missing links, host fields and controls remain explicit. No clinical or experimental claims are made by the software.
