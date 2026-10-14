# Controlled single-run FASTQ acquisition v1

This documents a proposed workflow joining the existing public-virus preflight
to the checksum-verified ENA downloader. Production acquisition is disabled;
the CLI supports dry-run planning only. It does not run QC, assembly,
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

`--execute` is not an authorization mechanism. The production
`acquire_single_run()` API fails before invoking archive, confirmation, or
download callbacks. A locally editable decision, digest, environment variable,
CLI option, or callback cannot authenticate an operator. This is intentional:
no independent trust anchor is currently implemented.

Synthetic end-to-end orchestration lives only in the `tests/` tree and is not
part of the application package. It uses injected test doubles and cannot be
selected from the production API or CLI.

The synthetic orchestration harness now copies the exact fresh response bytes
to a separate, bounded evidence directory before its temporary retrieval
directory is removed. It records each file's SHA256 and size, rejects unsafe,
missing, duplicated, changed, oversized, or pre-existing evidence paths, and
writes a local manifest. These hashes establish local consistency only, not
archive authenticity. The production entry point remains disabled and does not
invoke this harness.

The test harness also checks destination-scope containment, link-free output
paths, destination-volume headroom, exclusive locks, no-overwrite collisions,
and atomic audit writes. A controlled HTTPS redirect handler restricts ENA
redirect hosts; the legacy downloader's default behavior remains unchanged.
These checks have only been exercised with synthetic files and mocked
responses, not live HTTP or real filesystems on every target platform. The
production workflow remains disabled.

The legacy downloader remains unchanged for existing callers. The redirect
handler is tested separately and is not attached to a live transfer path;
production acquisition remains disabled.

## Requirements for a future trusted authorization

Before live acquisition can be enabled, a separate trusted service or
equivalent security-reviewed mechanism must independently verify operator
identity and issue a short-lived, single-use authorization bound to the exact
run, virus, reviewed FASTQ manifest digest, policy version, resource caps, and
permitted action. It must provide expiry and replay protection. No such
mechanism is supplied by this project, and a local signature or hash alone is
not an adequate substitute.

No authenticated production transfer path exists. If one is proposed later,
it must explicitly use the tested snapshot, destination, lock, audit, and
redirect safeguards; resume/reuse remains disabled in the test harness.
Network behavior, archive authenticity, and real-data performance are not
established by synthetic tests. Do not use this feature as evidence of
biological identity or independence.

CI and tests use mocked archive responses and synthetic FASTQ bytes only. No
test or implementation command should download real sequencing reads.
