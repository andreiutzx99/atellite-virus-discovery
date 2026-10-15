# HCoV-229E technical pilot readiness

## Decision

**NO-GO for real-read analysis at this time.** This is a technical readiness assessment, not an approval or change to the existing scientific decision. Status remains **HELD**; sequence confirmation remains **NOT_ASSESSED**. No FASTQ was downloaded or processed. The archive record reports a 24.9M-spot single-end run and describes cDNA selection/TruSeq v2, but that metadata does not establish an enrichment method or resolve a paper-to-archive timepoint discrepancy [S07–S08].

| Area | Current assessment | Evidence needed before real analysis |
|---|---|---|
| Reference provenance | Candidate human/229E records are pinned by accession and version; exact stock match is unknown. | Separately authorized retrieval, artifact SHA-256, source terms, panel lock and exact transcript package inventory. |
| Input/output integrity | Existing workflow fingerprints local inputs and writes technical reports. | Validate acquired FASTQ against separately approved manifest; preserve raw inputs and outputs immutably. |
| Resource use | Synthetic demonstration measures its own small fixture. | Benchmark on representative synthetic sizes; no inference from demo timings to the 24.9M-spot archive run. |
| Negative controls | No run-specific blank/control evidence was established here. | Confirm extraction/library blanks, positive controls, run controls, index design and their outcomes. |
| Sample independence | Archive labels and replicate names do not prove independent biological material. | Review experimental design and sample provenance; do not count technical splits as biological replicates. |
| Mapping bias | A single reference can miss divergent or structured viral reads; host transcript annotations are versioned bundles. | Freeze a justified panel, compare mapping configurations, retain ambiguous/unmapped reads, and report sensitivity to reference choice. |
| Candidate false positives | sgRNA, DVG-like junctions, contaminants and library artifacts can share split-read patterns. | Use controls, independent aligners/callers where justified, read-level inspection and orthogonal validation. |
| Reproducibility | Synthetic fixture has deterministic inputs and software/tool reporting. | Record reference checksums, exact executable versions, parameters, environment and all output digests for any authorized run. |
| QC vs discovery | Existing baseline QC is separate from biological interpretation. | Keep QC gates, mapping evidence, candidate screening and biological conclusions as distinct states and reports. |

## Interpretation boundaries

The synthetic tests exercise software mechanics only. Correct mapping to an artificial reference does not show viral presence; a synthetic junction is not a DVG; an artificial subgenomic-like sequence does not validate coronavirus transcription; a contaminant-like fixture does not identify a contaminant source. Coronavirus sgRNA and DVG biology motivate these fixture patterns, but cannot be inferred from them [S12–S18]. DVG callers produce scoped computational observations and do not establish replication, interference or helper dependence. A negative search does not establish novelty.

## Outstanding decisions

- Confirm experimental virus stock/lot/passage and exact host-cell provenance from primary records.
- Resolve the study's library kit, enrichment/depletion method, adapters, control design and whether samples are biologically independent. A `cDNA` selection label alone does not establish poly-A enrichment or rRNA depletion.
- Approve the exact host-transcript and rRNA bundle, variant comparison set, contaminant sources and reuse terms before acquiring them.
- Define the negative-control and independent-validation plan before any candidate review.
- Keep acquisition disabled and create no scientific approval or operator authorization in this PR.

## Next development milestone

After independent review of source terms and the reference manifest, design a separately gated, one-run technical execution plan with control requirements, exact pinned reference artifacts, explicit unmapped/ambiguous-read retention, resource limits, provenance checks and a no-candidate interpretation path. Do not activate it from this synthetic validation PR.
