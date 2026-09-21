# Implemented milestones and remaining work

This roadmap supplements the historical architecture. Implementation, runtime testing and scientific validation are separate statuses. Existing acquisition/QC stages and local development work are preserved.

## Merged foundation (PR #1)

1. **Observational reports:** supplied tables, explicit missing observations, sample/control and RNA/DNA stratification, recurrence counts, SQLite and HTML/CSV, verified reuse and failed-attempt recovery. Complete for the documented table contract.
2. **Library metadata review:** existing metadata snapshots, assay-source evidence, conflict/missingness flags and reports. Complete for the documented read-only review contract. It does not choose downstream tools or alter archive-selection filters.
3. **Supplied sequence inventory:** validated FASTA import, basic composition, exact duplicate groups, SQLite and FASTA/CSV/HTML exports, integrity checking and failed-attempt recovery. Complete for a single import. No similarity clustering or reconstruction is performed.

## Separate local development components

The QC audit, generic mapping adapter, SPAdes adapter, BLAST adapter and runtime diagnostics remain in the working directory. Not all of that earlier work is part of these focused publication commits. Mapping/BLAST tests used artificial fixtures; SPAdes lacks a validated local runtime and Tadpole remains a standalone runtime diagnostic. Published reporting milestones must not be described as completing those stages.

## Implemented infrastructure follow-up

4. **Unified review interface:** `Run-reviews.cmd` dispatches the existing tools and the new reviews. A bounded, read-only dashboard links existing reports and labels statuses as reported, not integrity-verified.
5. **Supplied-alignment coverage:** interval-table and bounded plain-text SAM imports, explicit coordinate/CIGAR conventions, gap-aware breadth/depth and exclusion counts. Validated with artificial overlaps, gaps, clipping, invalid inputs and empty assessed panels.
6. **Descriptive contamination evidence:** externally supplied reference matches, required provenance fields and explicit technical-control calls. Union coverage and review flags preserve uncertainty; no automatic rejection or probability inference.
7. **Cross-import catalogue linking:** verified existing snapshots, exact-sequence links, consistent sample metadata, per-sample presence deduplication, SQLite provenance and CSV adapters compatible with the completed observational stage.
8. **Resource/recovery tests:** shared review lifecycle, exclusive locks, failed-write recovery, changed-input detection, output integrity checks, row limits and interrupted SQLite/report recovery without duplicate imports.

These complete the five concrete items previously listed under remaining permitted engineering work. Each remains limited to its documented artifact contract; completion does not mean the historical biological discovery design is implemented.

## Unsupported broader components

BAM/CRAM and compressed-SAM input, automatic contamination reference searches, approximate sequence clustering, ORF reporting and the combined discovery workflow remain outside these implemented contracts. Functional compatibility and biological identity are not inferred. The earlier local assembly/mapping prototypes remain separate from this published infrastructure. See [review interfaces and exact limits](REVIEW_INFRASTRUCTURE.md) and [module contracts](MODULE_INTERFACES.md).

## Verification

The observational milestone added nine tests; the library-review milestone added seven; the inventory milestone added eight. Their examples use fictional metadata or artificial sequences. Run `python -m unittest discover -s tests -q` to test the checkout you have; totals differ between the focused published branch and the broader local development checkout.

The infrastructure follow-up adds 19 targeted tests, including adapter round trips into the existing observation module. It does not repeat completed public-data QC.
