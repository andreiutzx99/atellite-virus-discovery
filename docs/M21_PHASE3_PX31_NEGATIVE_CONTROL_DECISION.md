# M21 Phase 3 — Px31 negative-control decision

**Decision:** `NEGATIVE_CONTROL_SUITABILITY_PENDING`

The Motsar et al. (2025) paper reports no satellite-associated reads and no expected-size product in the satellite-specific RT-PCR screen for Px31. The assay detection limit is not reported. This supports a **target-specific screen-negative** description only; it does not establish confirmed satellite absence.

The present record is insufficient to accept Px31 as an evaluable negative control. In particular, FASTQ bytes, read-level adequacy, and assay sensitivity have not been independently reviewed. It must not enter a specificity denominator unless an independent reviewer accepts evidence under a predeclared protocol.

### Minimum evidence for future acceptance

1. Verify sample/run identity and exact input-file checksums.
2. Assess read quality, usable depth, library suitability, and the workflow's ability to detect the target class at the intended sensitivity.
3. Review the orthogonal assay, controls, target-specific detection limit, and the basis for interpreting a negative result.
4. Obtain a signed, time-limited independent review scoped to this dataset and protocol.
5. Keep the label in custodian-only material; do not put it in operator manifests, paths, configuration, caches, or logs.

If these conditions remain unresolved, classify Px31 as unevaluable for sample-level specificity and exclude it from TN/FP denominators. Seek an independently verified satellite-negative sample with adequate technical evidence, preferably with its cognate helper detected, and keep it in a separate study-aware validation group. Co-detection does not establish helper dependence.

Sources: Motsar et al. 2025, *Plants* 14:1619, https://doi.org/10.3390/plants14111619 ; full text https://pmc.ncbi.nlm.nih.gov/articles/PMC12157320/ ; NCBI Experiment SRX28192997 https://www.ncbi.nlm.nih.gov/sra/SRX28192997 .

