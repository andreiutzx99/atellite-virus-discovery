# HCoV-229E pilot source-evidence capture (2026-10-14)

This is a metadata-only review of the exact pilot run. No sequencing reads were fetched.
The reduced, redacted source fixtures are in
`tests/fixtures/hcov229e_sources/real_reduced/`; `capture_manifest.json` records each
exact response-body SHA256, retrieval time, HTTP status, content type, byte count,
URL, accession and selected response headers. Digests refer to the original response
bytes, not the reduced fixtures.

## Current source findings

All nine API responses used for the review returned HTTP 200. The accession chain is
supported by structured fields in independent records:

| Source | Observed structured evidence |
|---|---|
| GEO GSM4718636 | `!Sample_geo_accession=GSM4718636`; `!Sample_series_id=GSE155986`; explicit BioSample `SAMN15776099` and SRA experiment `SRX8920123` relations; title `MRC5_24_R2`; cell line `MRC-5`; treatment `Infected with HCoV-229E virus for 24 hours`; library strategy `RNA-Seq`. Its sample-level extraction protocol lists 0/6/24/48/72/**96** hours. |
| GEO GSE155986 | Includes GSM4718636 in `!Series_sample_id`; links to BioProject PRJNA656274 and SRA study SRP276927; the overall design describes HCoV-229E exposure and 0/6/24/48/72-hour sampling. |
| BioSample SAMN15776099 | Public record; structured identifiers include SRS7176671 and GSM4718636; links to PRJNA656274; attributes independently report MRC-5 and the same 24-hour HCoV-229E treatment. |
| SRA package | One package links run SRR12424250, experiment SRX8920123, sample SRS7176671, study SRP276927, BioSample SAMN15776099, GEO sample GSM4718636, GSE155986 and PRJNA656274. Library strategy is RNA-Seq, source transcriptomic, selection cDNA, layout single-end. |
| ENA run report | One row agrees on run, experiment, BioSample, study and BioProject. It lists one FASTQ with 680,887,913 bytes and MD5 `9ac379cab68b8b5e2862ec167e95d3c9`. This is archive metadata; the file bytes were not downloaded or verified. |
| PubMed record | PMID 33630927 identifies DOI 10.1371/journal.pone.0247128 and the PLOS ONE 2021 article “Transcriptomic profiling and genomic mutational analysis of Human coronavirus (HCoV)-229E -infected human cells.” This supports study-level context only, not run-level infection or viral-read presence. |

The GEO and BioSample records were last updated in October 2022; SRA/ENA currently return
the same accession relationships and manifest. These observations establish a current
cross-source match at retrieval time, not continuous immutability. The sequence-confirmed
viral-presence state remains `NOT_ASSESSED`; the strict public-virus identity remains
`INSUFFICIENT` and eligibility remains `HELD`.

The source texts also expose an unresolved 96-hour discrepancy. The GEO sample extraction
protocol and the article's Methods mention 96 hours, while the GEO series overall design
lists 0/6/24/48/72 hours and the 15 deposited GSM records represent three samples at each
of those five timepoints. No 96-hour GSM/SRX/SRR was identified in the reviewed series.
The available records do not establish whether 96-hour material was used for another
assay, not deposited, or described by a broad protocol statement. Do not infer a
96-hour sequencing run or treat the discrepancy as an archive error.

## Fixture handling

The source responses are public, but the GEO and BioSample responses include submitter
contact/name fields, while PubMed XML includes the full abstract and reference list.
Those full bodies were inspected from temporary files and are not committed. Checked-in
fixtures are reduced copies: personal contact fields, author/contact details and the
full publication abstract/reference list are omitted. The publication fixture retains
only bibliographic metadata and a short identifying excerpt. The fixture manifest
preserves exact original response digests and retrieval metadata so the reductions can
be distinguished from exact raw captures.

These records support the reviewed sample-treatment statement. They do not alter the
PR #65 recommendation (CONDITIONAL GO), constitute human approval, change public-virus-v1,
or authorize acquisition.
