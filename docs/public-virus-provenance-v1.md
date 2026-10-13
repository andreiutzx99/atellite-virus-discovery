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
items. The validator checks endpoint types for archive run/experiment/sample
links, publication reports, stock preparation, replicate links, and aliquots.
`derived_from` remains general-purpose and is never traversed to infer lineage
or independence. `reported_in_publication` accepts any non-publication subject.
Technical replicates must connect matching entity types among runs, sequencing
events, or preparation events; biological replicates must connect matching
biological-material or infection-event types. `aliquot_of` connects biological
material or viral stock entities.

Evidence records distinguish direct archive assertions, publication
assertions, curator decisions, and software-derived interpretations. Review
state (`accepted`, `proposed`, `rejected`, `conflicting`) and an uncertainty
statement are mandatory. Missing evidence is represented by no relationship;
uncertain or conflicting claims require an evidence-bearing relationship with
the corresponding review state. Contradictory accepted assessments are
surfaced as `CONFLICTING`, not silently resolved. Unresolved conflicting
identity evidence prevents a biological-material entity from being marked
`confirmed`; rejected evidence is retained but is not itself an unresolved
conflict.

Accepted independence evidence includes a structured `audit_reference`.
Publication assertions require `publication_ref` and `source_locator`.
Curator decisions require a pseudonymous or stable `reviewer_id`, `decision_id`,
and `decision_rationale`. Proposed, rejected, and conflicting evidence can be
recorded without an audit reference, but an independence relationship always
requires a valid dimension and assessment. These references improve
traceability; they do not verify a publication, authenticate an identity, or
establish biological truth.

Local SHA256 digests are labelled `local_integrity_only_not_source_authentication`.
Evidence IDs are stable hashes of canonical evidence content. Serialization
sorts entities, relationships, evidence, and object keys deterministically.
Unknown fields, malformed references, duplicate records, unbounded values, and
non-canonical documents are rejected with `ProvenanceValidationError`.

## Independence interface

`assess_independence(document, left, right, dimension)` returns one of:

* `INDEPENDENT`: direct accepted publication or curator evidence assesses the
  exact pair as different for the requested dimension. This means “supported
  by accepted assertions in this supplied provenance document,” not
  independently authenticated or biologically validated independence.
* `NOT_INDEPENDENT`: direct accepted evidence assesses the exact pair as same.
* `CONFLICTING`: accepted direct evidence supports both conclusions.
* `UNKNOWN`: no qualifying direct evidence supports a conclusion.

Dimensions are sequencing, library preparation, biological sample,
experimental/infection, viral stock/lineage, and original viral isolate. An
assessment is pair- and dimension-specific. The function does not traverse
relationships, propagate uncertainty, or infer independence from differing
archive identifiers, studies, laboratories, strains, isolates, or sequencing
runs. A technical-replicate edge alone does not substitute for a reviewed
dimension-specific assessment. `INDEPENDENT` is an interpretation of assertions
marked accepted in the supplied document; it is not a verification service,
authentication result, biological classification, or acquisition
authorization.

## Example interpretation

Two runs linked to one SRA sample remain `UNKNOWN` for sequencing and biological
independence unless direct evidence establishes a dimension-specific
relationship. Separate infections linked to the same stock can be assessed as
independent experiments while remaining not independent viral origins. These
are contract examples only, not biological validation.
