# HCoV-229E source fixtures

- `real_reduced/` contains reduced, redacted copies derived from actual public API
  responses retrieved on 2026-10-14.
- `real_reduced/capture_manifest.json` records the exact original response-body
  SHA256, URL, HTTP status, content type, byte count, retrieval header date, and
  source accession. Hashes identify the originals; they do not validate the reduced
  fixture bytes.
- GEO/BioSample submitter contact and personal-name fields are omitted. PubMed XML
  was reduced to citation fields and a short excerpt; the full abstract and reference
  list are not included.
- Synthetic adversarial fixtures, if added, belong in a sibling `synthetic/` folder
  and must be labeled synthetic. Never treat one as a live source response.
- The API response bodies and selected headers were captured temporarily for
  inspection. No FASTQ or other sequencing reads were requested or downloaded.
