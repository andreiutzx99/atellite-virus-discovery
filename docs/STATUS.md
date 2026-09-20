# Development status

## Version 0.2.0 verification

- 47 offline unit/integration tests passed on Python 3.12.5, Windows.
- Full live public-data test: `SRR3157747`, 169,330,557 compressed bytes, matched ENA MD5.
- QC processed 5,124,569 reads; 5,123,414 survived the explicit baseline filters. Original and rejected reads were retained. This was a software integration test, not biological satellite validation.
- The live download/QC run took approximately 19 minutes on the development machine. The user guide allows 20–30 minutes for this baseline engine.
- The updated default metadata search returned 12 eligible runs across five studies. The mirrored complete files in that small shortlist exceeded the 1,000 MB default input budget; the report now gives exact size requirements and skipped reasons. The guided test uses a known affordable public run.
- See `phase3-smoke-results.json` for measured QC metrics, hashes and offline replay evidence. Full inputs and reports stay under the local `runs/phase3-live-proof` folder and are excluded from Git.


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
| 3 downloads/QC | Implemented in 0.2.0: complete ENA FASTQ downloads, byte/MD5 checks, Range resume, budgets, baseline streaming QC, retained rejected/orphan reads and stage reports. SRA Toolkit/fastp integrations remain unimplemented |
| 4 helper mapping | Planned |
| 5 DVG discrimination | Planned |
| 6 assembly/contaminant analysis | Planned |
| 7 features | Planned |
| 8 candidate scores | Design only; no calibrated model or candidate scores |
| 9 known positives | Validation design only; no raw-data rediscovery performed |
| 10 negative controls | Validation design only |
| 11 exploratory sequence screen | Not started; requires validation |
| 12 catalogue/cross-dataset sequence search | Architecture only |

Current limitations: lexical metadata queries, bounded/nonrepresentative study sampling, incomplete sample metadata, provisional archive-centre laboratory field, bounded/nonexhaustive study context, no read-confirmed helper/control status, no automatic BioSample supplementary fetch, no GUI beyond the beginner wizard and static HTML. Metadata is bounded by experiment count; downloads are additionally bounded by run count and compressed input size. Baseline QC uses exact adapter matching, has no overlap-based detection and has not been biologically calibrated. Standard library Python 3.12 is used locally.

The metadata shortlist is reviewable, not an automatically validated analysis cohort. Missing links, host fields and controls remain explicit. No clinical or experimental claims are made by the software.
