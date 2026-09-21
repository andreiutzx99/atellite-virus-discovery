# Implemented milestones and remaining work

This roadmap supplements the historical architecture. Implementation, runtime testing and scientific validation are separate statuses. Existing acquisition/QC stages and local development work are preserved.

## Published development branch

1. **Observational reports:** supplied tables, explicit missing observations, sample/control and RNA/DNA stratification, recurrence counts, SQLite and HTML/CSV, verified reuse and failed-attempt recovery. Complete for the documented table contract.
2. **Library metadata review:** existing metadata snapshots, assay-source evidence, conflict/missingness flags and reports. Complete for the documented read-only review contract. It does not choose downstream tools or alter archive-selection filters.
3. **Supplied sequence inventory:** validated FASTA import, basic composition, exact duplicate groups, SQLite and FASTA/CSV/HTML exports, integrity checking and failed-attempt recovery. Complete for a single import. No similarity clustering or reconstruction is performed.

## Separate local development components

The QC audit, generic mapping adapter, SPAdes adapter, BLAST adapter and runtime diagnostics remain in the working directory. Not all of that earlier work is part of these focused publication commits. Mapping/BLAST tests used artificial fixtures; SPAdes lacks a validated local runtime and Tadpole remains a standalone runtime diagnostic. Published reporting milestones must not be described as completing those stages.

## Remaining permitted engineering work

- A unified interface showing stage readiness and linking existing artifacts.
- Generic supplied-alignment coverage summaries with explicit coordinate conventions and separate validation fixtures.
- Descriptive contamination evidence from independently supplied reference matches and technical controls, preserving uncertainty.
- Cross-import catalogue linking and reviewed observation-table adapters, with sample identity/provenance checks.
- Additional resource-failure and interrupted-job integration tests when those stages are implemented.

Approximate sequence clustering, ORF reporting and the combined discovery workflow remain unimplemented here. External biological interpretations use provenance-bearing interfaces rather than empty successful results. See [module contracts](MODULE_INTERFACES.md). No milestone in this branch establishes helper dependency or biological novelty.

## Verification

The observational milestone added nine tests; the library-review milestone added seven; the inventory milestone added eight. Their examples use fictional metadata or artificial sequences. Run `python -m unittest discover -s tests -q` to test the checkout you have; totals differ between the focused published branch and the broader local development checkout.
