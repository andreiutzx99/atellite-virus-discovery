# RNA/DNA library metadata review

The library review stage reads an existing `datasets.json` and produces a separate report. It does not repeat database queries, download reads, change QC output, or select an assembler/alignment mode.

Double-click `Review-library-metadata.cmd` and enter the existing datasets file path and a new output folder. Alternatively:

```console
python -m satellite_discovery.library_review --datasets PATH_TO_DATASETS_JSON --output NEW_REVIEW_FOLDER
```

Open `report.html` in the new folder. `library_review.json` preserves the supporting metadata evidence. The CSV provides one row per run. `manifest.json` records source/engine hashes and output checksums. Repeat the exact command to verify and reuse completed outputs. Changed inputs/code or an incomplete attempt require a new review folder. Source data is never rewritten.

## Interpretation

The module labels the **assay source**, not the organism's genome type or the physical material read by the sequencer. RNA assays often sequence cDNA. The organism/helper name is never used as evidence of library molecule type. Strand orientation remains unknown; paired-end layout does not establish strandedness.

Rules use archive library-source and strategy fields. Transcriptomic, metatranscriptomic and viral-RNA sources provide RNA-origin evidence; genomic and synthetic sources provide DNA evidence. RNA sequencing strategies provide RNA-origin evidence. WGS, amplicon and metagenomic labels alone do not resolve molecule type. Contradictory DNA-source/RNA-strategy evidence becomes `unknown` with `conflicting` status, not an invented mixed library. Explicit mixed assays currently remain unresolved rather than being inferred from contradictory annotations.

Targeted selection, single-cell/barcode requirements and unresolved read layouts are flagged for review. These flags do not by themselves certify or reject an analysis cohort. No automatic biological interpretation, tool selection or change to the existing inclusion criteria is made.

Primary definitions: [ENA permitted library source and strategy values](https://ena-docs.readthedocs.io/en/latest/submit/reads/webin-cli.html#permitted-values-for-library-source). The separation of sample, experiment and run follows the [NCBI SRA metadata model](https://www.ncbi.nlm.nih.gov/sra/docs/submitmeta/). These are descriptive metadata rules, not a validated classifier of experimental protocols.
