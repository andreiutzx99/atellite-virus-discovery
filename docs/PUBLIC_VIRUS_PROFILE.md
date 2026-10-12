# Public-virus metadata profile v1

`public-virus-v1` is an opt-in, metadata-only intake profile for HCoV-229E and
HCoV-OC43. It is separate from the named laboratory-model profile and does not
change its policy or acceptance rules.

Run one archive accession at a time:

```sh
python -m satellite_discovery.cli \
  --public-virus-accession SRR12424243 \
  --public-virus hcov-229e \
  --output runs/public-virus-SRR12424243
```

The command resolves the run through NCBI SRA, checks that the fetched package
contains the exact run and its experiment, sample, and study identifiers, then
queries ENA for read-file availability and compressed sizes. Original archive
responses are kept in `raw_metadata/`; their response hashes and retrieval
metadata are listed in `public_accession.json`. Offline mode uses only those
cached responses and fails if a required snapshot is absent or fails its
recorded digest check.

Only the archive's sample organism field and recognized virus-specific sample
attributes may support virus identity. Host organism, study title, experiment
title, and an untyped free-text claim do not establish it. A matching identity
is reported as `accepted_for_technical_review`, never as biological
confirmation. Missing identity is `insufficient`; contradictory virus identity
is `conflicting`; configured excluded-pathogen mentions are `excluded`.
Strain, isolate, catalogue, passage, batch, laboratory, and replicate values
are retained separately when present and otherwise remain `UNKNOWN`.

Library suitability is a separate decision. For example, OC43 amplicon runs
can have archive-supported OC43 identity while being excluded as unsuitable for
unbiased discovery. The output does not assign positive/negative biological
labels, infer infection, or establish independence between runs.

Curator evidence is recorded as pending and cannot promote an accession.
Metadata from edited `datasets.json`, CSV, or JSON is not accepted as input to
this route. Snapshot hashes detect changes relative to the local manifest;
they are not a cryptographic signature and do not resist an actor able to edit
both files. No claim of archive signature verification is made.

This profile intentionally does not enable downloads, read QC, or downstream
analysis. Those require a later reviewed integration that revalidates the
profile, normalized archive record, evidence state, and policy digest at every
entry point.

## Future cross-strain comparison design

Keep comparison downstream of sample-level identity and source review. Group
records using verified study, BioProject, sample/BioSample, experiment, lab,
preparation, passage, batch, and explicit biological/technical replicate
metadata. Missing grouping data stays `UNKNOWN`; separate run IDs or strain
labels alone never imply independent origins. A future comparison stage should
consume versioned, provenance-bound sample groups and frozen references, split
at study/family level before analysis, and report recurrence separately from
helper dependence or biological confirmation. Preserve existing M7 recurrence
behavior; do not add cross-strain matching, clustering, ranking, or
classification in this profile.
