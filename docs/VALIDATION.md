# Validation plan — biological gate not yet passed

The current tests validate software metadata behavior only. No sensitivity, false-positive rate, ranking performance or satellite rediscovery has been measured. No novel sequence screen has started.

## Smallest biological proof-of-concept (future phases 3–10)

Choose a published known satellite/helper system with public raw reads, independent confirmation, sufficient library coverage and interpretable controls. A plant satellite RNA system such as cucumber mosaic virus satellite RNA is a potential initial benchmark family; accession selection and suitability review remain to be done. A nucleotide reference alone does not establish a usable raw-read benchmark. Add other independently validated systems only after auditing the linked publications, raw libraries, sample identity and control annotations. Do not assume the requested respiratory helpers have suitable known satellite-positive datasets.

1. Create a frozen manifest of independently labelled samples, archive accessions, publications, library characteristics and expected detectable positives. Use several studies/systems for a meaningful generalization test.
2. Separate development/tuning studies from held-out evaluation studies. Keep label files outside classifier inputs.
3. Withhold positive reference sequences and close homologues from **all** nucleotide, protein, profile/domain and contamination resources that could leak the labels. Record exclusions; measure separate exact-withhold and family-withhold tasks.
4. Start from raw reads through the exact future workflow, including QC, host/helper handling, assembly, classification and scoring. Capture retention of expected positive reads at each gate to localize failures.
5. Evaluate raw known-positive data plus independently justified negatives. Natural samples in which no satellite is expected are not guaranteed true negatives; distinguish apparent candidate burden from a measured false-positive rate.
6. Use shuffled/decoy sequences and synthetic read mixtures for software/artefact stress tests. Those controls cannot establish biological specificity or substitute for natural-data validation.
7. Freeze thresholds on development data before opening held-out labels. Missing prerequisites produce a failed/incomplete gate, not an automatic pass.

## Metrics and denominators

- Sensitivity: recovered known-positive samples / eligible known-positive samples, with confidence intervals and per-system/depth/library strata. Define recovery by predeclared sequence identity and covered fraction suitable to that benchmark; do not tune on held-out outputs.
- False-positive rate: false-positive evaluable negative units / all evaluable true-negative units. State the unit (sample or candidate); do not divide contig counts by samples. Uncertain biological negatives get a separate apparent-positive-rate label.
- Ranking: reciprocal rank, recall@K and rank of each withheld positive, reporting the number of candidates and ties. Missing positives have rank infinity and reciprocal rank zero.
- DVG discrimination: confusion matrix on independently supported DVG versus satellite examples, plus an unresolved class. A DVG annotation cannot be its own ground truth.
- Filter attrition: positive retention after every gate, specifically short/low-abundance/noncoding cases.
- Reproducibility: exact metadata snapshot replay; repeated sequence jobs with fixed software/references/seeds; deterministic versus tool-dependent outputs documented.

## Acceptance and gate artifact

Before implementation evaluation, record numeric acceptance criteria justified by benchmark size and the intended screening burden. Do not invent a universal acceptable sensitivity/FPR from this prototype. The planned gate artifact includes benchmark manifest hash, software commit, reference hashes, predeclared criteria, measured metrics/intervals, exclusions, held-out status and pass/fail. Changes to software, references or major thresholds invalidate the applicable pass until re-evaluation. Until this exists and passes, only metadata exploration and benchmark development are enabled.

## Supplied-artifact validation follow-up

See [ARTIFACT_VALIDATION_REPORT.md](ARTIFACT_VALIDATION_REPORT.md) for implementation, test evidence and explicit remaining limitations. This adds bounded fallback retries/history, file-level reference metadata, digest/control evaluation (menu23 and workflow stage), and a paired artificial Tadpole diagnostic. It does not deliver a biological discovery chain.
