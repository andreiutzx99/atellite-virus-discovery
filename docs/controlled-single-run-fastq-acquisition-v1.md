# Controlled single-run FASTQ acquisition v1

This workflow joins the existing public-virus preflight to the existing
checksum-verified ENA downloader. It is opt-in and does not run QC, assembly,
classification, or satellite discovery.

## Dry run (default)

Install the project package, then supply the original intake, its source snapshot
directory, the human review decision, and a storage directory:

```sh
satellite-controlled-fastq \
  --intake runs/public-virus-SRR123456/public_accession.json \
  --raw-metadata runs/public-virus-SRR123456/raw_metadata \
  --decision review-decision.json \
  --storage /data/virus-pilot \
  --output /data/virus-pilot/SRR123456
```

Without `--execute`, the command only recomputes and prints the existing
preflight plan. It does not retrieve archive metadata or transfer FASTQ files.
The plan reports the run, virus, complete file manifest, expected compressed
bytes, required storage, and any blocking reasons.

## Explicit acquisition

After reviewing a ready dry-run, an operator may run the same command with
`--execute`. It recomputes the original preflight, then retrieves fresh NCBI SRA
and ENA metadata through `retrieve_accession()` in a newly created empty
temporary snapshot directory. The existing client therefore cannot reuse the
original intake's local cache. The workflow rejects incomplete archive
responses, changed run/experiment/sample/study relationships, changed virus
identity, unsuitable records, an invalid or changed complete FASTQ manifest,
policy mismatches, and budget or storage failures.

Only after those checks does the command print the exact run, virus, manifest
digest, compressed size, required headroom, and approved caps. The operator
must type the exact run accession and both exact approved resource caps. Any
missing or different value blocks transfer. Disk headroom is checked again
immediately before the existing ENA downloader is called. No SRA Toolkit
fallback or alternate run is attempted.

The downloader handles complete single/paired file sets, MD5 verification,
bounded transfer, and safe resume. An `acquisition.json` audit is written as
the transfer proceeds, with fresh archive metadata, the reviewed manifest,
operator confirmation, attempts, observed sizes/checksums, and final outcome.
Transfer failures and operator interrupts are recorded in the audit; an
interrupt is re-raised after the audit is safely updated. They do not authorize
a later automatic retry.

## Limits

Fresh retrieval timestamps and local snapshot hashes are audit information,
not proof of archive authenticity. The locally editable decision is not an
authenticated identity or authorization mechanism; this workflow requires an
interactive operator action each time. Network behavior, archive freshness,
and real-data performance are not exercised by the synthetic test suite. Do
not use this feature as evidence of biological identity or independence.

CI and tests use mocked archive responses and synthetic FASTQ bytes only. No
test or implementation command should download real sequencing reads.
