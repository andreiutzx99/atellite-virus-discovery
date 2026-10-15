# Synthetic-only validation results

All sequence strings below are deterministically generated test fixtures; they are not downloaded reference sequences or reads.

| Scenario | Fixture/result | Interpretation boundary |
|---|---|---|
| Host and viral-reference mapping | Existing synthetic pilot maps independent host-like and virus-reference-like fixtures to their expected artificial records. | Mapping mechanics only; no biological presence claim. |
| Ambiguous mapping | Two identical generated references produce equal-score alignments / MAPQ 0 or secondary evidence. | Ambiguity is retained; no forced unique biological assignment. |
| Unmapped read | An unrelated generated read remains flagged unmapped in SAM. | Unmapped is not novel. |
| Mismatch | A generated read with one substituted base maps with a non-zero edit count. | Does not characterize real-stock divergence. |
| Quality filtering | Generated low-quality FASTQ is rejected; input, retained and rejected counts are checked. | No inference about archive read quality. |
| Coverage | Coverage is calculated from generated primary alignments and must be non-zero for the corresponding artificial target. | Not a real coverage estimate or genome completeness claim. |
| Contaminant-like read | Generated sequence maps to a clearly named synthetic contaminant-like reference. | Does not identify any laboratory contaminant. |
| Artificial junction | Generated concatenations of separated regions map to artificial junction-transcript records. | Not evidence of a viral junction in a sample. |
| sgRNA-like / DVG-like | Generated leader/body-like and deletion-like strings map only to artificial transcript records. | Not biological sgRNA/DVG classification, replication, satellite activity or helper dependence. |

The focused offline command `PYTHONPATH=.:tests python -m unittest test_hcov229e_reference_panel test_hcov229e_technical_pilot` passed **4 tests**. `python -m json.tool` validated the manifest and research registry. A full local `unittest discover` run exceeded the 300-second shell limit while running pre-existing slow/integration-style tests; its completion status is unknown. The full GitHub Actions result is required before treating CI as passing.
