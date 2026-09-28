# M15 contract freeze: lossless cross-stage evidence dossier

**Contract status: FROZEN FOR A DESCRIPTIVE, LOSSLESS DOSSIER.** M15 is
**PLANNED / NOT IMPLEMENTED**.
This contract preserves original producer records and adds only semantic
normalizations that are provably lossless. There is no ranking, score,
classifier, or biological winner.

## 1. Scope and non-goals

M15 validates immutable references to upstream evidence, preserves raw
producer-specific schemas/statuses, describes evidence dependencies, and
renders a dossier that can contain complete or partial input sets. It does
not rerun upstream analysis, deduplicate by biological similarity, convert
correlated evidence into independent votes, or assign a candidate class.

M11 is deliberately not part of this frozen contract. Although the current
roadmap marks M11 implemented as an optional RNA-fold prediction stage, M15
does not consume M11 artifacts; adding them requires a separately reviewed
contract version. Missing M11 or any optional M12–M14 branch is explicitly
absent, not negative.

## 2. Runner and accepted artifact types

The future stage is `m15_evidence_dossier`, invoked through the existing
allowlisted artifact-workflow manifest runner. No dedicated command,
arbitrary import, or per-milestone executable is added. An additive M4
registration and artifact validators will be required for implementation.

M15 accepts references to these producer types only:

| Producer identity | Accepted artifact types |
| --- | --- |
| M5 ViReMa producer; exact stage ID and run-manifest digest copied from its validated producer manifest | `dvg_raw_output`, `dvg_evidence`, `dvg_evidence_summary`, `dvg_parameters` |
| M6 residual/support producer; exact stage ID and run-manifest digest copied from its validated producer manifest | `residual_read_manifest`, `read_triage_table`, `read_alignment_sam`, `read_support_evidence`, `read_support_table`, `reconstruction_evidence`, `m8_candidate_sequence_set` |
| M7 registered stage `independent_recurrence` | `m7_observation_table`, `m7_exact_recurrence_table`, `m7_independence_summary`, `m7_validation_report`, `m7_provenance_manifest` |
| M8 registered stage `m8_homology` | `m8_raw_blast_output`, `m8_query_status`, `m8_match_evidence`, `m8_summary`, `m8_search_commands` |
| Caller-supplied M8 immutable reference snapshot, identified by its own snapshot manifest | `m8_reference_snapshot_manifest` (snapshot provenance only; payload is not an M15 input) |
| M9 registered stage `m9_orf_translation` | `m9_orf_results`, `m9_protein_fasta`, `m9_orf_bundle` |
| Caller-supplied M9 immutable protein snapshot, identified by its own snapshot manifest | `m9_protein_reference_manifest` (snapshot provenance only; payload is not an M15 input) |
| M9 registered stage `m9_blastp` | `m9_protein_search_status`, `m9_protein_match_evidence`, `m9_protein_summary`, `m9_search_commands`, `m9_output_bundle`, `m9_raw_blast_output` |
| M10 registered stage `m10_exact_first` | `m10_candidate_accounting`, `m10_repeat_evidence`, `m10_result_bundle` |
| M12 registered stage `m12_artifact_review` | `m12_artifact_review_table`, `m12_summary`, `m12_result_bundle` |
| M13 registered stage `m13_m5_evidence_matrix` | `m13_event_index`, `m13_hypothesis_matrix`, `m13_summary`, `m13_result_bundle` |
| M14 registered stage `m14_descriptive_observations` | `m14_observation_table`, `m14_descriptive_summary`, `m14_result_bundle` |

Every reference must identify the exact producer milestone/stage, immutable
producer-run manifest digest, artifact type and semantic version, relative
path, SHA-256, and raw producer status. M15 does not accept arbitrary report
text as evidence. M1–M4 workflow/run manifests may be linked for provenance,
but their untyped contents are not interpreted as evidence rows. No M15 output
or M16 benchmark result can be an M15 input.

When an upstream reference snapshot carries source terms, attribution, access
class, or redistribution limits, copy those exact provenance references into
the dossier (or mark them `UNKNOWN`). M15 does not grant permission, infer
redistribution rights, or include reference payloads as evidence inputs.

## 3. Input manifest

The UTF-8 JSON manifest uses `schema = "m15-input-v1"`:

```json
{
  "schema": "m15-input-v1",
  "candidate_id": "stable opaque identifier",
  "artifact_refs": [],
  "optional_stage_states": {
    "M12": "NOT_SUPPLIED",
    "M13": "NOT_SUPPLIED",
    "M14": "NOT_SUPPLIED"
  }
}
```

`candidate_id` is required. `artifact_refs` contains zero or more immutable
references from section 2; zero refs is valid and yields `NOT_EVALUATED`.
`optional_stage_states` has exactly M12, M13, and M14 keys, each `PRESENT`,
`NOT_SUPPLIED`, `NOT_AUTHORIZED`, `UNAVAILABLE`, `NOT_APPLICABLE`, `UNKNOWN`,
`FAILED`, `INTERRUPTED`, `INCOMPLETE`, or `INVALID`. `PRESENT` requires at
least one matching valid artifact reference. `FAILED`, `INTERRUPTED`,
`INCOMPLETE`, and `INVALID` may coexist with references to valid partial
artifacts; their raw producer statuses remain attached to those refs. For
M5–M10, presence is established by `artifact_refs`; do not synthesize empty
producer records for omitted stages.

## 4. Evidence envelope and outputs

Proposed future output artifact types:

- `m15_evidence_envelope` — one record per accepted upstream artifact/row.
- `m15_dependency_edges` — explicit provenance/dependency relationships.
- `m15_dossier_summary` — counts of supplied, absent, invalid, and unresolved
  records, without a score or class call.
- `m15_result_bundle` — exact input/output references and integrity manifest.

Each envelope record contains:

```json
{
  "evidence_id": "sha256-derived stable ID",
  "candidate_id": "same input candidate",
  "producer_ref": {},
  "producer_status_raw": "exact producer value",
  "producer_schema_raw": "exact producer schema/version",
  "source_row_ref": null,
  "semantic_axes": {},
  "dependency_edge_ids": []
}
```

`evidence_id` is derived from producer-run-manifest digest, artifact digest,
and source row index where applicable. `source_row_ref` is null only for a
whole-artifact record. The original source object remains retrievable unchanged
by `producer_ref`; M15 never overwrites its status or schema.

The semantic axes are:

| Axis | Values | Lossless normalization rule |
| --- | --- | --- |
| `artifact_validity` | `VALID`, `INVALID`, `UNKNOWN` | M15 may set valid/invalid only from its own hash/schema checks; otherwise unknown. |
| `applicability` | `APPLICABLE`, `NOT_APPLICABLE`, `UNKNOWN` | Copy only an explicit producer value; never infer not-applicable from absence. |
| `execution` | Existing M1 stage lifecycle value or `UNKNOWN` | Copy only the exact producer lifecycle state; do not infer stage completion from an evidence result code. |
| `completeness` | `COMPLETE`, `INCOMPLETE`, `TRUNCATED`, `UNKNOWN` | Copy only explicit accounting/completeness from producer contract; else unknown. |
| `observation` | `OBSERVED`, `NOT_DETECTED_WITHIN_SCOPE`, `NO_OBSERVATION`, `UNKNOWN` | Map only when producer contract explicitly means that exact scoped result and its accounting is valid. |
| `interpretation` | `SUPPORTS`, `CONFLICTS`, `UNRESOLVED`, `NOT_INTERPRETED` | Map only an explicit hypothesis-linked producer interpretation; otherwise `NOT_INTERPRETED`. |

All axes are present in every envelope; unknown is explicit. Raw status/schema
remain authoritative if an axis cannot be mapped losslessly. A completed
scoped no-signal cannot be created from `UNKNOWN`, `UNAVAILABLE`, failure,
incomplete accounting, or a missing optional artifact.

Each dependency edge contains `edge_id`, `source_evidence_id`,
`target_evidence_id`, `relation`, `verification_state`, and
`source_provenance_ref`. `relation` is one of `DERIVED_FROM`, `SAME_INPUT`,
`SAME_READ_SOURCE`, `SHARED_REFERENCE`, `SAME_DECLARED_UNIT`,
`POTENTIAL_OVERLAP`, or `UNKNOWN`; `verification_state` is `VERIFIED`,
`DECLARED_UNVERIFIED`, or `UNKNOWN`. M15 may create an edge only when an
upstream manifest or the input explicitly supports it. An edge is not an
independence assertion. M15 does not output a count of “independent votes.”

## 5. Lifecycle, partial input, and failures

The M15 stage uses existing M1 lifecycle values. Its result completeness is
`COMPLETE_WITHIN_SUPPLIED_SCOPE`, `PARTIAL`, `NOT_EVALUATED`, or `INVALID`.
`PARTIAL` means a dossier was produced but one or more referenced/optional
branches were missing, unavailable, invalid, incomplete, or failed. Every
record retains the more specific state and reason.

- Optional stage absent: keep its explicit manifest state and emit no
  synthetic negative row.
- Valid partial set: preserve each valid envelope record even if another
  artifact is invalid or unavailable.
- Invalid referenced artifact: emit an integrity-error record with the
  reference and reason; do not ingest its payload.
- Unrecognized producer schema/status: preserve raw value, set unmappable
  axes to `UNKNOWN`, and mark compatibility warning. If the artifact type or
  bytes are invalid, mark invalid instead.
- Malformed required M15 manifest fails preflight/input validation.
- No conflict resolution or ranking; conflicting evidence remains multiple
  linked records and summary count.

## 6. Provenance, cache identity, and deterministic output

The identity binds candidate ID; exact input-manifest digest; each consumed
artifact’s producer milestone/stage, producer-run-manifest digest, type,
semantic version, content digest and raw status; optional-stage states;
source-row identity; supplied source-access/terms references; dependency-edge source and relation; M15 axis-mapping
semantic version; the semantic identity of only the artifact contracts
consumed; implementation/source digest; and all output digests.

The identity excludes generated timestamps, absolute paths, display formatting,
and evidence not referenced by the input. Changing an upstream artifact
invalidates M15 through its digest; an M15-only change does not invalidate its
producers. Reuse requires exact identity and verified output hashes.

Serialize as canonical UTF-8 JSON, no BOM, LF, one final newline, sorted object
keys, no non-finite numbers. Sort envelope rows by evidence ID; edges by
source ID, relation, target ID; summaries by producer and state. Keep raw
source payload bytes unchanged and refer to them by digest. Same inputs and
implementation produce byte-identical semantic outputs.

## 7. Synthetic acceptance fixtures

| Fixture | Required result |
| --- | --- |
| Mixed M5–M14 records with all status classes | Preserve raw schema/status and map only explicitly supported axes. |
| M5 completed caller zero | Method-scoped observation only; no candidate-negative interpretation. |
| M8 no-hit plus failed/incomplete branch | Preserve exact per-branch producer records; never map failure to scoped no-match. |
| Missing M12/M13/M14 branches | Explicit `NOT_SUPPLIED`; no negative record. |
| M6 assembly and read-back from the same eligible reads | A `SAME_READ_SOURCE` edge when producer provenance establishes it; no independent-vote count. |
| Two records with shared reference or source event | Preserve both and emit supported dependency edge; do not collapse records or inflate independence. |
| Unknown producer status | Preserve raw status; affected normalized axes are `UNKNOWN`/`NOT_INTERPRETED`. |
| Corrupt artifact, duplicate reference, or mismatched digest | Invalid record; valid records remain in a `PARTIAL` dossier. |
| Empty artifact list | `NOT_EVALUATED`, no synthetic evidence or ranking. |

## 8. Compatibility and claim boundary

Existing M5–M10 type names are defined in
[`artifact_contracts.py`](../satellite_discovery/artifact_contracts.py);
M12–M14 types are defined by their respective freeze contracts. M15 is
downstream-only and does not alter producer schemas, statuses, or cache
identity. Additive M4 registration is needed to run it as a workflow stage.
The dossier is descriptive integration, not a biological classification,
functional conclusion, or priority score.
