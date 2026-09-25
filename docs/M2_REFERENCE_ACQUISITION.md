# M2 — Reference records and acquisition

**Status: IMPLEMENTED.** M2 adds provenance-bearing reference handling and
registered acquisition paths. It does not certify the biological meaning or
completeness of the data. See the [README](../README.md) and
[roadmap](ROADMAP.md) for current project status.

## 1. Purpose

Acquire declared public read data and preserve reference records/snapshots with
enough provenance to identify what was supplied to later analysis.

## 2. Why this milestone exists

Read files and reference collections need traceable origins, integrity checks,
and explicit transfer limits before they can be used in a reproducible
workflow.

## 3. Implemented functionality

M2 provides registered ENA acquisition, a conditional NCBI SRA Toolkit path,
per-record reference imports, immutable reference snapshots, checksums, and
verified reuse of recorded inputs.

## 4. Inputs

Inputs include declared accessions/search scope and transfer budgets, supplied
reference records/files with source and role metadata, and validated workflow
configuration. Provider use is restricted to registered paths.

## 5. Outputs

Outputs include downloaded read files and transfer/QC records, imported
reference records, and local snapshots with source, role, size, and digest
metadata.

## 6. External tools and dependencies

ENA acquisition uses its public services. The NCBI Toolkit path is conditional
on the external SRA Toolkit being available and eligible under the workflow
policy. Tool/database installation is not bundled with a source checkout.

## 7. Evidence produced

Tests support the declared transfer, checksum, reference-record, snapshot,
and reuse contracts. They do not prove that an accession has the expected
biological identity or that a reference collection is complete.

## 8. Provenance and reuse

The workflow records declared sources and content digests. A changed source
file or snapshot is distinguishable from previously verified content; reuse
does not silently certify an updated or differently curated reference.

## 9. Failure and dependency semantics

Unavailable services, ineligible accessions, missing external tools, budget
limits, and integrity failures remain explicit. A failed or incomplete
transfer is not treated as a valid empty dataset.

## 10. Interpretation

M2 can support the claim that particular bytes were obtained or imported and
matched a recorded digest. Metadata and source assertions remain supplied
information, not independent biological verification.

## 11. Limitations

Acquisition does not automatically curate, taxonomically classify, or certify
reference suitability. Provider coverage, network availability, and optional
tool availability are environment-dependent.

## 12. What M2 does not establish

It does not establish sample identity, infection status, biological safety,
reference-panel completeness, absence of an organism, or sequence novelty.

## 13. Relevant tests and records

See the [test suite](../tests/), [conditional-tool guide](CONDITIONAL_TOOLS.md),
[deployment and recovery notes](DEPLOYMENT.md), and the current
[capability audit](APPLICATION_CAPABILITY_AUDIT.md).

## 14. Relevant literature

The [Sequence Read Archive description](https://doi.org/10.1093/nar/gkq1019)
provides resource context. See also the official
[ENA browser documentation](https://www.ebi.ac.uk/ena/browser/about). These
resources do not certify the content or completeness of any local snapshot.

## 15. Relationship to other milestones

M2 supplies traceable inputs and reference records to later workflows. M3
assembles supplied reads; M4 connects typed artifacts; M6 screens only against
its explicitly declared reference FASTA. Later evidence and biological
validation remain planned; see the [roadmap](ROADMAP.md).