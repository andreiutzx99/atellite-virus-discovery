# Public-virus provenance graph v1

`satellite_discovery.public_virus_provenance` is an offline data-contract layer.
It records archive entities, physical-material entities, typed relationships,
and source-bearing evidence. It does not retrieve reads, perform QC, make
biological classifications, or change M7.

## Schema

The canonical document schema is `public-virus-provenance-v1` (integer
`schema_version: 1`). Documents contain only `entities` and `relationships`.
Entity kinds distinguish SRA run, experiment, sample and study records,
BioSample, BioProject, biological material, viral isolate/stock, preparation,
infection, sequencing, and publication evidence.

Archive accessions belong on archive entities. They cannot serve as identifiers
for a `biological_material`. The graph does not infer a material entity from an
SRA or BioSample accession. A confirmed biological-material identity requires
an accepted curator identity-evidence record and a non-archive identifier.
Namespaced local identifiers can be used for physical materials; avoid
including identifying human-sample metadata.

Every relationship has a type, two entity references, and one or more evidence
items. Evidence records distinguish direct archive assertions, publication
assertions, curator decisions, and software-derived interpretations. Review
state (`accepted`, `proposed`, `rejected`, `conflicting`) and an uncertainty
statement are mandatory. Missing evidence is represented by no relationship;
uncertain or conflicting claims require an evidence-bearing relationship with
the corresponding review state. Contradictory assessments are surfaced as
`CONFLICTING`, not silently resolved.

Local SHA256 digests are labelled `local_integrity_only_not_source_authentication`.
Evidence IDs are stable hashes of canonical evidence content. Serialization
sorts entities, relationships, evidence, and object keys deterministically.
Unknown fields, malformed references, duplicate records, unbounded values, and
non-canonical documents are rejected with `ProvenanceValidationError`.

## Independence interface

`assess_independence(document, left, right, dimension)` returns one of:

* `INDEPENDENT`: direct accepted publication or curator evidence assesses the
  exact pair as different for the requested dimension.
* `NOT_INDEPENDENT`: direct accepted evidence assesses the exact pair as same.
* `CONFLICTING`: accepted direct evidence supports both conclusions.
* `UNKNOWN`: no qualifying direct evidence supports a conclusion.

Dimensions are sequencing, library preparation, biological sample,
experimental/infection, viral stock/lineage, and original viral isolate. An
assessment is pair- and dimension-specific. The function does not traverse
relationships, propagate uncertainty, or infer independence from differing
archive identifiers, studies, laboratories, strains, isolates, or sequencing
runs. A technical-replicate edge alone does not substitute for a reviewed
dimension-specific assessment.

## Example interpretation

Two runs linked to one SRA sample remain `UNKNOWN` for sequencing and biological
independence unless direct evidence establishes a dimension-specific
relationship. Separate infections linked to the same stock can be assessed as
independent experiments while remaining not independent viral origins. These
are contract examples only, not biological validation.
