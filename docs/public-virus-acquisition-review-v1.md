# Public-virus acquisition review gate v1

`satellite_discovery.public_virus_acquisition_review` builds a bounded,
deterministic review packet from an existing `public_accession.json` document.
Call `build_review_packet(document, provenance_document=None,
raw_metadata_directory=None)`; use `serialize_review_packet(packet)` for
canonical compact JSON. Inputs and output are size-bounded.

The gate recomputes the selected-virus identity assessment with the current
public-virus policy, checks the policy version and digest, verifies the local
record digest and (when supplied) snapshot files through the existing intake
verifier, re-evaluates library suitability, and parses the complete ENA FASTQ
metadata through the existing `files_for_run` validator. Incomplete,
inconsistent, offline-only, or unverifiable metadata is held. The gate does
not treat `pilot_readiness` or another single stored status as sufficient.

Possible outcomes are `eligible_for_curator_review`, `held_for_review`, and
`excluded`. Eligibility means only that the record meets this gate's technical
screen for a human review. It is not biological validation, authenticated
archive evidence, a recurrence count, or permission to acquire data. Every
packet sets `download_enabled` and `may_download` to `false`.

The technical pilot subset is deliberately conservative: Illumina RNA-Seq or
WGS, supported by accepted sample-level virus metadata, a complete validated
FASTQ file set, and a total size no greater than 1,000,000,000 bytes. Amplicon
and other intake-excluded strategies remain excluded; unrecognized or biased
library details are held for review. Missing provenance does not prevent
technical consideration, but biological identity and independence remain
`UNKNOWN`. Independence is never inferred from run, sample, strain, laboratory,
or study differences.

If a canonical provenance graph is supplied, it is validated using the PR #58
contract. Only directly matched archive entities and directly linked biological
materials are summarized. A confirmed biological identity is reported as
traceable only when the material's accepted curator identity evidence and its
direct archive-to-material relationship both carry structured audit
references. These references improve traceability but do not authenticate
curators or establish biological truth. Unresolved direct identity conflicts
are surfaced as `CONFLICTING`.

The intake manifest's local SHA256 values detect local inconsistency only; they
do not authenticate NCBI/ENA metadata or confer download authority. When the
manifest lists raw snapshot files, provide their directory using
`raw_metadata_directory` for local verification; without it, the packet is
held. The current accession format has no independently authenticated
retrieval timestamp, so metadata age cannot be certified.

A later PR must add a separately reviewed, explicit acquisition-authorization
step. It must define the approver and scope, revalidate current archive
metadata and file manifests immediately before use, apply storage/network and
budget controls, and keep acquisition disabled absent that authorization.
Nothing in this module invokes a downloader, SRA Toolkit, QC, assembly, or
candidate-ranking code.
