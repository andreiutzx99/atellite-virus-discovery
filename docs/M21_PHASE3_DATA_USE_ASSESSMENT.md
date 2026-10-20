# M21 Phase 3 — data-use and governance assessment

**Decision:** `PENDING`; this record is not a permission grant.

## Source-supported observations

- NCBI SRA RunInfo and Experiment records list the selected records as public and provide archive metadata/download-path fields. The RunInfo consent field is `public`.
- NCBI's molecular-data policy says NCBI itself places no restrictions on use or distribution and does not accept data when submitters request reuse/redistribution restrictions. The same policy cautions that original submitters or countries of origin may assert patent, copyright, or other intellectual-property rights, which NCBI does not assess or transfer.
- Motsar et al. (2025) is published under CC BY 4.0. That article licence applies to the article; it is not evidence that deposited read files carry the same licence or that redistribution is permitted.
- The run metadata reviewed did not identify a specific submitter restriction or separate licence for the SRA files. This is not a complete legal clearance and does not establish permission for a particular processing, retention, redistribution, or derived-result use.

## Decisions still required

Before any separately authorized acquisition, a designated governance reviewer must record whether the exact SRA/submitter terms permit:

1. Local processing and temporary copies.
2. Retention period, storage location, backup, and deletion.
3. Redistribution or mirroring of raw files (do not assume this is allowed).
4. Publication of derived results, aggregate statistics, and any sequence-level output.
5. Required attribution and citation.
6. Institutional biosafety, privacy, or data-governance review.

Any ambiguity leaves the data-use gate pending. The readiness checker will not create or infer an approval; it requires an unexpired, signed approval record from a reviewer in an externally managed trust store. Public accessibility is not treated as unrestricted reuse permission.

Sources consulted 2026-10-20: NCBI SRA overview https://www.ncbi.nlm.nih.gov/sra/about/ ; NCBI molecular-data usage policy https://www.ncbi.nlm.nih.gov/home/about/policies/ ; NCBI RunInfo export and sample records cited in `M21_PHASE2_DATASET_QUALIFICATION.md` ; Motsar et al. 2025 https://doi.org/10.3390/plants14111619 .

