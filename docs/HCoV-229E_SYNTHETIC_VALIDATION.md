# Synthetic-only validation results

All sequence strings and reads in this report are deterministic generated fixtures. No real reference sequence or FASTQ was downloaded or analyzed. The study scope remains GSE155986 / PRJNA656274 / SRP276927 / SRR12424250 only.

## De novo synthetic junction-caller check

The pinned ViReMa 0.25 caller (source commit `481defd7c340bb52fa80748a89d478be9c265f64`) was run through the existing adapter against **one intact 1,500-nt artificial genome**. No junction-transcript reference was supplied. Ground-truth breakpoints are held by the validation harness and are not passed in caller inputs or configuration.

| Fixture | Read length | Read support | Quality | Expected breakpoints | Result |
|---|---:|---:|---:|---|---|
| Leader–body-like artificial junction | 80 nt | 8 | Q40 | 139 → 500 | Detected; exact breakpoints |
| Internal-deletion-like artificial junction | 120 nt | 4 | Q40 | 259 → 750 | Detected; exact breakpoints |
| Alternative-order rearrangement-like artificial junction | 80 nt | 2 | Q40 | 939 → 300 | Detected; exact breakpoints |
| Leader–body-like quality replicate | 80 nt | 8 | Q20 | 139 → 500 | Detected; exact breakpoints |
| Leader–body-like quality replicate | 80 nt | 8 | Q0 | 139 → 500 | Detected; exact breakpoints |

Five positive fixture trials were recovered with exact breakpoints. This exercises three support counts (2, 4, 8), two read lengths (80, 120 nt), and three quality encodings (Q0, Q20, Q40). Quality was varied only for one junction pattern at fixed length/support; this is not a broad quality-response curve.

The combined negative set contained **56 reads**, eight each of continuous genomic reads, single-substitution reads, repetitive/ambiguous reads, low-complexity reads, adapter-like reads, short continuous alignments, and low-quality continuous reads. ViReMa emitted no junction calls for the negative set.

| Metric | Result on these artificial fixtures |
|---|---:|
| True-positive fixture trials | 5 |
| False-positive calls | 0 |
| False-negative fixture trials | 0 |
| Sensitivity | 1.00 (5/5 fixture trials) |
| Precision | 1.00 (5/5 calls) |
| Exact breakpoint matches | 5/5 |

These values describe only these generated sequences, settings, and cases. They are not estimates of biological sensitivity/specificity, do not establish real sample junctions, and do not show that unusual junctions are DVGs or sgRNAs. The caller’s generic `DVG_EVIDENCE_DETECTED` status remains caller-reported junction evidence, not a biological classification.

## Existing synthetic mapping tests

Separate mapping fixtures still map generated reads to preconstructed artificial transcript references. Those tests validate known-reference mapping mechanics only; they do not constitute de novo discovery or caller sensitivity evidence. The ViReMa exercise above is distinct because its caller receives the intact artificial genome.

| Scenario | Fixture/result | Interpretation boundary |
|---|---|---|
| Host and viral-reference mapping | Synthetic host-like and virus-reference-like fixtures map to artificial records. | Mapping mechanics only; no biological presence claim. |
| Ambiguous mapping | Identical generated references produce equal-score alignments / MAPQ 0 or secondary evidence. | Ambiguity is retained; no forced unique biological assignment. |
| Unmapped read | An unrelated generated read remains flagged unmapped in SAM. | Unmapped is not novel. |
| Mismatch | A generated read with one substituted base maps with a non-zero edit count. | Does not characterize real-stock divergence. |
| Quality filtering | Generated low-quality FASTQ is rejected; input, retained and rejected counts are checked. | No inference about archive read quality. |
| Coverage | Coverage is calculated from generated primary alignments. | Not a real coverage estimate or genome-completeness claim. |
| Contaminant-like read | Generated sequence maps to a synthetic contaminant-like reference. | Does not identify any laboratory contaminant. |

## Reproduction and limitations

- Generate fixture tests: `PYTHONPATH=.:tests python -m unittest test_synthetic_junction_validation test_hcov229e_reference_panel test_hcov229e_technical_pilot`
- Run pinned ViReMa/Bowtie diagnostic: `python scripts/check_virema_ci.py`
- The diagnostic writes a machine-readable report under `.tools/virema-diagnostic-*/report.json`; its temporary tool checkout, binaries, reads, and outputs are not project deliverables.
- The current cases do not test inserted bases at junctions, reverse-strand junctions, broad breakpoint distributions, or sensitivity across independent random genomes. Positive quality replicates vary only quality for a single pattern; the negative set tests several artifact classes but only one generated genome.
- A detected pattern compatible with artificial sgRNA-like transcription or a DVG-like rearrangement does not establish satellite-virus identity, replication, interference, or helper dependence. No biological inference is made.

The scientific status remains **HELD**, sequence confirmation remains **NOT_ASSESSED**, and the technical decision remains **NO-GO for real-read analysis**.
