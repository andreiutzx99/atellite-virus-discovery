# Research Notes: HCoV-229E Reference Panel and Synthetic Pilot

**Status:** source review complete; panel metadata proposed; no sequence artifacts acquired.  
**Retrieved:** 2026-10-15.  
**Scope:** GSE155986 / PRJNA656274 / SRP276927 / SRR12424250 only.

## Findings

- GRCh38.p14 is RefSeq assembly GCF_000001405.40. Its assembly report provides exact accession.version and lengths for 24 chromosomes and the mitochondrial sequence. The primary assembly is not a sample-specific genotype. NCBI's current annotation release is GCF_000001405.40-RS_2025_08 (dated 2025-08-01); transcripts and rRNA are a versioned collection, not one accession.
- NC_002645.1 is a 27,317-nt complete HCoV-229E RefSeq record, clone `inf-1`. MF542265.1 is a 27,271-nt complete genome for strain 229E/Haiti-1/2016. They are comparison references only; neither establishes the exact stock used in GSE155986.
- SRA identifies SRR12424250 as GSM4718636, MRC5_24_R2, single-end Illumina HiSeq 2500, 24.9M spots; its submitted record reports cDNA selection and TruSeq RNA Library Preparation Kit v2. The paper describes infected MRC-5 cells, 0.01 MOI and several harvest times/replicates. Archive and paper descriptions contain a timepoint discrepancy. The exact stock, lot, passage, sample-to-stock sequence, library enrichment, and control outcomes remain unresolved.
- Coronavirus leader-body junctions and DVG-compatible rearrangements are biologically plausible but not specific. A junction is evidence for a computational pattern only. Caller output cannot identify a DVG, satellite, replication, interference, or helper dependence without appropriate independent evidence.
- UniVec and published adapter/technical-control resources can inform optional screens, but no exact kit-specific adapter or run-specific contaminant/control identity is established. The manifest does not include downloaded data or checksums.

## Open items

- Resolve the human standalone nuclear rRNA accession/version set or keep it represented only by the pinned genome annotation package.
- Confirm stock/passages, cell provenance, library preparation, control design and biological independence from primary study records.
- Review artifact-specific reuse terms and capture checksums only when reference retrieval is separately authorized.

See `sources.json` for the source registry and `../docs/HCoV-229E_REFERENCE_PANEL.md` for rationale and interpretation limits. Full research fetches are in the workspace's root `research/sources/` folder; large source texts are intentionally not copied into this PR.
