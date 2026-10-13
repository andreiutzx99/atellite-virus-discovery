# Controlled public-virus acquisition preflight v1

`satellite_discovery.public_virus_acquisition_preflight.build_acquisition_preflight`
recomputes the current acquisition review gate from the original accession
document, its source-snapshot directory, and an optional provenance graph:

```python
plan = build_acquisition_preflight(
    accession_document,
    raw_metadata_directory,
    review_decision,
    provenance_document=optional_graph,
    storage_directory=pilot_storage,
)
```

It does not accept a previously saved review packet as evidence of eligibility.
Only a fresh `eligible_for_curator_review` outcome can produce a
`ready_for_operator_confirmation` plan. Held or excluded records remain
blocked. The plan contains the exact run and virus, current policy digest, all
validated FASTQ URLs/names/roles/sizes/MD5 values, complete compressed byte
total, 1,000,000,000-byte ceiling, and storage headroom required by the
existing downloader check (`3 × compressed bytes + 256 MiB`).

## Review decision record

Supply a JSON object with schema `public-virus-acquisition-review-decision-v1`
and the fields below:

- `reviewer_identifier`, `decision_identifier`, and nonempty
  `decision_rationale`
- Exact `approved_run_accession` and `selected_virus`
- Current `policy_version` and `policy_sha256` to bind the decision to the
  policy reviewed
- Nonempty `intended_pilot_purpose`
- `state`: `approved`, `rejected`, or `pending`
- `scope`: `max_runs` must be `1`; `max_compressed_bytes` must be a positive
  integer no greater than 1,000,000,000; `max_storage_bytes` must be a
  positive integer

Approval is blocked when the run, virus, expected compressed bytes, or required
storage headroom exceeds the supplied scope, or when the decision's policy
version/digest is stale. A missing, malformed, pending, or rejected decision
cannot produce a ready plan.

**This locally editable record is not authenticated authorization.** A decision
record, its local digest, or a ready plan never permits or triggers a download.
Every plan has `may_download: false` and `download_enabled: false`.

## Boundaries and future checks

The preflight makes no network requests and does not download reads, invoke SRA
Toolkit, run QC, assemble, cluster, or classify satellite candidates. It uses
the existing review gate, `files_for_run()`, and `check_disk()` validators.
Unknown file sizes, incomplete paired-end sets, policy or snapshot mismatches,
budget overflow, and insufficient storage block the plan.

Plans preserve biological independence as `UNKNOWN` when the supplied
provenance does not establish it. Technical eligibility does not mean
satellite-virus evidence. Local SHA256 checks detect changed or missing
snapshots only; they do not authenticate archive content or prove freshness.

Before a future controlled single-run downloader can execute, it must require a
separate explicit operator action and immediately repeat all checks listed in
`required_immediate_pre_download_checks`: fresh archive metadata and policy
validation, exact run/sample linkage, full FASTQ manifest comparison, byte
budget, current disk headroom, and exact approval-scope matching. Any difference
must stop the transfer.
