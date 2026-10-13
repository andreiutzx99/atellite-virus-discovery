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
Explicit sample-level mixed/coinfection or modified/recombinant evidence is
`review_required`, a hold rather than a claim of confirmed coinfection. Typed
pathogen fields and explicit additional-pathogen fields are checked even when
the named pathogen is outside this two-virus profile. Study titles are broad
context: mentioning multiple viruses alone does not establish a mixed sample.
Incomplete archive metadata means screening cannot detect every possible
coinfection.

Typed pathogen fields are parsed conservatively across explicit list separators
and conjunctions. Ambiguous additional agents are held for review with the
original field and value recorded; recognized strain/isolate/lineage metadata
and an ordinary “infected with HCoV-229E” phrase are not themselves a second
pathogen. This bounded parser is not comprehensive pathogen recognition.

SRA run, experiment, sample, and study IDs are validated in their distinct
INSDC namespaces. BioSample (`SAMN`, `SAMEA`, `SAMD`) and BioProject
(`PRJNA`, `PRJEB`, `PRJDB`) IDs are validated when present, but remain optional
and are never substituted for SRA sample or study accessions.

Strain, isolate, stock/catalogue, passage, batch, experimental laboratory,
archive submission centre, and replicate values are retained separately when
supported and otherwise remain `UNKNOWN`. Archive `center_name` is not
evidence of the laboratory that prepared a biological sample.

Identity, library suitability, complete FASTQ availability/size, and overall
pilot readiness are separate decisions. For example, OC43 amplicon runs can
have archive-supported identity while being excluded as unsuitable for
unbiased discovery. Reasons attach to each failed gate; an identity hold does
not contaminate an otherwise passing technical assessment. The output does not
assign positive/negative biological labels, infer infection, or establish
independence between runs.

Curator evidence is recorded as pending and cannot promote an accession.
Metadata from edited `datasets.json`, CSV, or JSON is not accepted as input to
this route. Snapshot hashes detect changes relative to the local manifest;
they are not a cryptographic signature and do not resist an actor able to edit
both files. `verify_public_record()` is only a local consistency diagnostic: it
does not rederive normalized metadata or identity decisions from original
archive responses, authenticate those responses, or authorize acquisition. No
code in this profile treats successful verification as permission to download.
A later acquisition integration must rederive eligibility from bound archive
evidence or use a separately reviewed authenticated trust mechanism.

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
classification in this profile. Collecting multiple strains and isolates does
not establish independent biological recurrence.
