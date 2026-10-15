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
| Artificial junction | Generated concatenations of separated regions map to preconstructed artificial junction-transcript records. | Known-reference mapping only; not evidence of a viral junction in a sample. |
| sgRNA-like / DVG-like | Generated leader/body-like and deletion-like reads map to preconstructed synthetic sgRNA-like and DVG-like transcript references. | Not de novo junction discovery, not a measurement of junction-caller sensitivity, and not biological sgRNA/DVG classification, replication, satellite activity or helper dependence. |

The junction fixture test asks whether reads already generated from artificial junction sequences can map to matching, preconstructed artificial transcript references. It does **not** search for junctions de novo from reads aligned to an intact viral genome, and it does **not** estimate sensitivity, specificity, or detection limits for a junction caller. Those are distinct validation questions and remain untested here.

The focused offline command `PYTHONPATH=.:tests python -m unittest test_hcov229e_reference_panel test_hcov229e_technical_pilot` passed **5 tests** in the current PR revision. `python -m json.tool` validated the manifest and research registry. A full local `unittest discover` run exceeded the 300-second shell limit while running pre-existing slow/integration-style tests; its completion status is unknown. The full GitHub Actions result is required before treating CI as passing.
