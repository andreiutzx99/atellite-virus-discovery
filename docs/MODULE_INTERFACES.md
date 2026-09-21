# Module contracts and incomplete stages

This document defines artifact boundaries, not implementations or validated biological methods. Existing source modules remain in place. Listing a stage does not establish its readiness for real-data execution.

All stages should accept an input manifest with schema version, artifact paths, SHA256 hashes, method identifier and parameters. Results must declare one of `complete`, `failed`, `blocked_dependency`, or `not_implemented`. Unimplemented stages return no observations and must stop dependent execution. Missing evidence must never be converted to a negative finding.

| Stage | Input artifact | Output artifact | Current limitation |
|---|---|---|---|
| Acquisition/QC/audit | Archived dataset metadata and verified files | QC files, metrics and integrity manifests | Existing implemented components preserved |
| Library metadata review | Existing dataset metadata snapshot | RNA/DNA source evidence and conflict report | Implemented read-only; no automatic tool selection |
| Read mapping/extraction | Verified reads and reference manifest | Alignment artifacts and partition manifests | Existing adapter; synthetic testing does not establish biological suitability |
| Assembly | Verified input manifest | Contig file, runtime log and checksum manifest | Existing SPAdes adapter lacks local runtime validation; Tadpole is a standalone synthetic diagnostic |
| Database comparison | Supplied sequences and versioned reference manifest | Descriptive matches and method provenance | Existing BLAST adapter; no validated comprehensive reference panel |
| Contamination/artefact assessment | Descriptive matches and technical-control observations | Evidence flags and reasons, with unknown status permitted | Supplied-match/control evidence review implemented; automatic searches and biological validation pending |
| Coverage/composition/ORF summary | Supplied sequence/alignment artifacts | Descriptive measurements with units and missing-data status | Basic composition and supplied interval/SAM coverage implemented; ORF reporting pending |
| Recurrence/study comparisons | Unique sample table and explicit observation table | Stratified counts, SQLite export and HTML/CSV report | Implemented in observation_report; no read-level detection |
| Clustering/catalogue/FASTA export | Independently supplied sequence records | Exact-sequence groups, SQLite and normalized FASTA export | Exact grouping/import/export and cross-import links implemented; approximate clustering pending |
| Functional compatibility and biological identity | Independent external assessment, if available | Cited external conclusion and provenance | No implementation or automatic inference in this application |

No reserved field named probability should be populated from an arbitrary score. Reports should distinguish method-generated measurements, user-supplied observations and external interpretations. The observation importer does not consume a functional-compatibility result.

Future adapters need separate tests for input validation, record conservation, resource failures, stale outputs and reproducibility before being connected to the user interface. This document does not authorize or validate downstream biological methods.
