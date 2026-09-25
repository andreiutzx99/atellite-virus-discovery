# M7 — Independent recurrence and reproducibility

M7 adds an exact-recurrence evidence layer over declared M6 observations. It
compares candidate sequences only after M6 has assessed each reconstruction
individually. It does not pool reads, run an assembler, or decide what a
sequence is biologically.

## Purpose and evidence boundary

M6 reports technical reconstruction support from read-back against a contig.
M7 asks whether the exact sequence recurs among the observations supplied to
it, and at which declared sample, run, or study levels. Those are separate
evidence dimensions: repeated processing of one input is not converted into
multiple independent source datasets.

M7 does **not** establish satellite identity, novelty, helper dependence,
biological function, replication, pathogenicity, or complete-genome status.
“No recurrence detected” means only that no repeated supported sequence was
found in the observations that were evaluated. It does not mean the sequence
occurs nowhere else, is artifactual, or is not a satellite.

## Observation model and inputs

Each declared observation has a stable `observation_id`. Optional metadata
includes `candidate_id`, `sample_id`, `sequencing_run_id`, `study_id`,
`source_artifact_id`, `upstream_workflow_id`, and timezone-qualified
`observed_at`. `molecule_type` is `DNA`, `RNA`, or `unknown`.

An observation with available M6 output requires typed
`reconstruction_evidence` and `residual_read_manifest` artifacts. It may also
declare the M6 `canonical_contig_fasta` containing supported contigs. M7 checks
the M6 sample, QC and reference provenance; verifies the FASTA IDs and lengths
against per-contig M6 evidence; and requires both the top-level reconstruction
and the individual contig to have `READ_SUPPORTED_ASSEMBLY` status before a
sequence enters recurrence groups.

Unavailable or failed M6 observations are declared explicitly with
`m6_state`, `upstream_status`, and an optional `upstream_reason`. They do not
declare M6 evidence files. M7 keeps those records in its outputs rather than
representing them as negative sequence observations.

Missing IDs remain null and appear in `metadata_missing`. Common literal
placeholders such as `unknown`, `not provided`, `NA`, `none`, and `null` are
treated as missing. The original required M6 sample label is retained as
`m6_sample_id`; a placeholder is not used as a grouping key. M7 does not infer
sample, run, study, or timestamp metadata. If an M6 sidecar manifest is
available, its identity and checksum are recorded; otherwise the workflow
identity remains missing unless explicitly declared.

## Exact sequence recurrence

The default `orientation_policy` is `forward_only`. FASTA sequences are read
through the existing nucleotide parser, which removes formatting whitespace
and normalizes bases to uppercase. Exact groups are keyed by SHA256 of the
sequence content, and M7 also compares the actual canonical strings so a hash
collision cannot silently combine different sequences. Original sequence
hashes and IDs remain attached to each member.

Optional `reverse_complement_invariant` matching is limited to individually
supported nucleotide contigs and requires an explicit `DNA` or `RNA`
declaration for every supported sequence. M7 computes the reverse complement
using the corresponding IUPAC nucleotide alphabet and chooses the
lexicographically smaller of the forward and reverse-complement strings as
the matching key. Palindromic sequences retain a `palindromic` orientation
label. DNA and RNA alphabets are validated separately; the option does not
silently convert RNA `U` to DNA `T`.

M7 implements exact matching only. Approximate similarity, family clustering,
alignment thresholds, consensus sequences, and related-sequence recurrence
are not implemented. There are no comparison thresholds.

## Independence categories

Categories are explicit and may coexist:

| Category | M7 meaning |
| --- | --- |
| `SINGLE_OBSERVATION` | One distinct M6 source-read dataset supports the exact group. Multiple M6 processing records with the same source-read checksums still count as one dataset. |
| `REPEATED_SAME_SAMPLE` | At least two distinct source-read datasets have the same declared sample ID. |
| `RECURRENT_ACROSS_RUNS` | At least two distinct declared run IDs occur within the same declared sample. |
| `RECURRENT_ACROSS_SAMPLES` | At least two distinct declared sample IDs occur in the exact group. |
| `RECURRENT_ACROSS_STUDIES` | At least two distinct declared study/project IDs occur in the exact group. |
| `REPEATED_WITHIN_DECLARED_STUDY` | At least two distinct source-read datasets have the same declared study/project ID. |
| `RECURRENT_INDEPENDENCE_UNRESOLVED` | More than one distinct source-read dataset is present, but available metadata does not justify another category. |

The categories are computed from profiles keyed by the checksums of the M6
source FASTQ inputs. If repeated M6 processing of identical source-read bytes
contains conflicting sample, run, or study labels, the conflicting dimension
is excluded from the independence summary and reported. A distinct ID is a
declared metadata distinction, not external verification that samples or
studies were independently collected. The output retains every observation
and sequence member even when source datasets are deduplicated for
independence counts.

## M6 states and negative-result semantics

M7 preserves these evidence classes:

- `TECHNICALLY_SUPPORTED_RECONSTRUCTION` — M6 marks the contig as
  `READ_SUPPORTED_ASSEMBLY`; only this class can contribute a sequence to an
  exact group.
- `UNSUPPORTED_RECONSTRUCTION` — M6 completed but did not support the
  reconstruction. Such contigs are retained in the observation record and
  excluded from recurrence.
- `UNRESOLVED_UNASSEMBLED_RESIDUAL_EVIDENCE` — M6 did not attempt assembly;
  this is not a negative sequence observation.
- `UPSTREAM_UNAVAILABLE` and `UPSTREAM_FAILED` — M6 did not supply usable
  reconstruction evidence.

If all observations lack supported sequences because upstream evidence is
unavailable or failed, the result is `UPSTREAM_UNAVAILABLE_OR_FAILED`. Other
runs with no eligible supported sequence report
`NO_ELIGIBLE_SUPPORTED_SEQUENCES`. An evaluated exact group with more than one
source-read dataset reports
`RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS`; otherwise the status is
`NO_RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS`. Upstream gaps make the
analysis `PARTIAL` and are counted in the validation report.

## Outputs and provenance

| Output | Contract | Contents |
| --- | --- | --- |
| `observations.json` | `m7_observation_table` | Declared observations, M6 state, provenance, missing metadata, residual counts, and per-contig support status. |
| `exact_recurrence.json` | `m7_exact_recurrence_table` | Exact groups and the original observation/sequence members, orientation, and independence summaries. |
| `recurrence_summary.json` | `m7_independence_summary` | Result status, completeness, counts, method, and limitations. |
| `validation_report.json` | `m7_validation_report` | Available, unavailable, failed, unsupported, unresolved, and supported-sequence counts plus warnings. |
| `recurrence_provenance.json` | `m7_provenance_manifest` | Configuration and input hashes, implementation identity, source-data fingerprints, and output hashes. |
| `report.html` | `report` | Human-readable summary that retains the same evidence boundaries. |

The artifact-workflow stage also writes its standard `manifest.json` with
execution state and verified output checksums. Reuse is bound to normalized
configuration, typed input checksums, and the implementation identity. A
changed sequence or M6 artifact changes the workflow cache identity; changed
independence metadata or comparison configuration also forces new evidence.
Attempting to reuse a completed M7 output directory with changed inputs or
configuration fails closed.

## Tests

`tests/test_independent_recurrence.py` uses deterministic artificial M6
artifacts to cover a single observation; same-sample, cross-run, cross-sample,
and cross-study recurrence; reverse-complement matching; similar and unrelated
sequences; missing metadata; corrupted artifacts; changed-input and
changed-metadata reuse; unavailable and failed M6 states; unsupported contigs;
duplicate source-read datasets; deterministic output ordering; portable
input/output paths; typed workflow roles; and the absence of raw-read inputs.

## Limitations and scientific language

The sample, run, study, and molecule-type values are declared metadata; M7
does not verify their truth. Source-read checksums identify repeated input
bytes, not independent laboratory preparation. Exact sequence recurrence is
not a related-sequence search. M7 has no calibrated sensitivity, specificity,
or universal denominator and does not replace negative controls or
experimental validation.

“Independent observation,” “recurrence,” “supported reconstruction,”
“unresolved,” and “candidate” describe the software evidence. Do not report
M7 recurrence as “novel satellite discovered,” “confirmed satellite,”
“validated virus,” or evidence of biological function.

## Literature

The following works support general principles, not M7's specific schemas,
thresholds, metadata categories, or scientific conclusions:

- Lazic, S. E. (2010). The problem of pseudoreplication in neuroscientific
  studies: is it affecting your analysis? *BMC Neuroscience*, 11, 5.
  https://doi.org/10.1186/1471-2202-11-5
  — relevant to distinguishing repeated observations from independent
  experimental units.
- Sandve, G. K., Nekrutenko, A., Taylor, J., & Hovig, E. (2013). Ten Simple
  Rules for Reproducible Computational Research. *PLoS Computational Biology*,
  9(10), e1003285. https://doi.org/10.1371/journal.pcbi.1003285
  — general computational reproducibility practices.
- Wilkinson, M. D., et al. (2016). The FAIR Guiding Principles for scientific
  data management and stewardship. *Scientific Data*, 3, 160018.
  https://doi.org/10.1038/sdata.2016.18
  — general guidance for reusable, well-described research data.

The exact-sequence rule, source-read checksum deduplication, status mappings,
and category definitions above are project-specific engineering rules. They
are not validated biological criteria.