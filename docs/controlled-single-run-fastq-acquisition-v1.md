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

## Live acquisition disabled

`--execute` is not an authorization mechanism. The controlled acquisition API
and its transfer boundary fail closed before invoking archive, confirmation, or
download callbacks. A locally editable decision, digest, environment variable,
CLI option, or callback cannot authenticate an operator. This is intentional:
no independent trust anchor is currently implemented.

The prior implementation's temporary fresh archive response directory was
deleted after checks. It did not safely retain exact source response bytes.
Destination filesystem binding, safe output-path handling, concurrency locks,
and redirect destination validation are also not complete. These limitations
must be resolved and independently tested before any future implementation can
enable live acquisition. In particular, the downloader follows HTTP redirects;
the controlled acquisition workflow remains disabled rather than relying on
the initial ENA URL check as redirect protection.

The legacy downloader remains unchanged for existing callers. Its availability
does not authorize or enable the controlled acquisition workflow.

## Requirements for a future trusted authorization

Before live acquisition can be enabled, a separate trusted service or
equivalent security-reviewed mechanism must independently verify operator
identity and issue a short-lived, single-use authorization bound to the exact
run, virus, reviewed FASTQ manifest digest, policy version, resource caps, and
permitted action. It must provide expiry and replay protection. No such
mechanism is supplied by this project, and a local signature or hash alone is
not an adequate substitute.

After authorization exists, the implementation still needs bounded atomic
retention and digest verification of fresh source snapshots, secure
destination-scoped storage checks, collision-safe exclusive locking, atomic
audit updates, verified-only resume, and strict redirect-host validation.
Network behavior, archive authenticity, and real-data performance are not
established by synthetic tests. Do not use this feature as evidence of
biological identity or independence.

CI and tests use mocked archive responses and synthetic FASTQ bytes only. No
test or implementation command should download real sequencing reads.
