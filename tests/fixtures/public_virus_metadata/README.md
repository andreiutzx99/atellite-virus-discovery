# Public-virus metadata fixtures

These are narrowly derived, sanitized metadata-only snapshots for deterministic
acceptance tests. They contain no FASTQ or sequence content.

Source accessions: `SRR12424243` and `SRR3198409`. The fixture fields record the
run, experiment, SRA sample/study, BioSample and BioProject identifiers; sample organism; library
metadata; ENA FASTQ listing, MD5 and compressed size. The first record was
cross-checked against NCBI SRA RunInfo; the second uses ENA archive sample
taxonomy and run-file metadata.

Sources accessed 2026-10-12:

- NCBI SRA RunInfo:
  `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra&id=11593703&rettype=runinfo&retmode=text`
- ENA read-run report (replace `ACCESSION` with either run accession):
  `https://www.ebi.ac.uk/ena/portal/api/filereport?accession=ACCESSION&result=read_run&fields=run_accession,experiment_accession,sample_accession,study_accession,scientific_name,library_strategy,library_source,library_selection,library_layout,instrument_platform,fastq_ftp,fastq_md5,fastq_bytes&format=tsv`

SRA sample/study identifiers (`SRS`/`SRP`) are stored separately from BioSample
and BioProject identifiers (`SAMN`/`PRJNA`); none is inferred from another.
Only reported metadata is represented. Missing sample fields are not inferred.
The expected results preserve the distinction between archive identity,
library suitability, FASTQ engineering metadata and pilot readiness.
