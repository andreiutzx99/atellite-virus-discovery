# M14 contract freeze: descriptive candidate/helper observations

**Contract status: FROZEN FOR THE DESCRIPTIVE SYNTHETIC/OFFLINE BASELINE.**
**Milestone status: PLANNED / NOT IMPLEMENTED.** This contract defines
observation identity, tested denominators, and descriptive counts. Inferential
association models and experimental dependence are not required baseline
behavior.

The [M14 final contract clarification](research/M14_CONTRACT_CLARIFICATION.md)
is normative for optional-source outcomes, frame/result precedence, and
canonical M14 identity. It does not authorize M14 implementation or real-data
use.

This freeze does not fulfill the roadmap's broader matched-observation
association question or establish helper dependence; those require
claim-appropriate data and evidence beyond this descriptive synthetic baseline.

## 1. Scope and non-goals

M14 validates supplied candidate/helper observations and summarizes co-detection
at an explicitly declared observational-unit level. It does not infer
independence from IDs, treat missing records as negatives, fit an association
model, or establish helper dependence.

The schema does not grant data-use permission. Any future real-data execution
requires a separately approved purpose/access/terms/privacy record; no such
approval or dataset is selected by this contract.

Out of scope:

- A universal biological unit or independence rule.
- Public/private cohort selection, metadata acquisition, or control matching.
- Statistical significance, abundance normalization, odds ratios, or
  population-level inference.
- Experimental intervention, rescue/complementation, or dependence claims.
- Taxonomic classification from sequence similarity or linked M5/M8/M9 output.

## 2. Runner and accepted upstream artifacts

The future allowlisted workflow stage is `m14_descriptive_observations`.
Invocation uses the existing workflow manifest runner:

```text
python -m satellite_discovery.artifact_workflow \
  --manifest <workflow.json> --output <output-directory>
```

There is no new M14 command or unrestricted file reader. A later implementation
requires an additive M4 registration and artifact validators; this contract
does not modify M4.

The M14 manifest may reference only these typed upstream artifacts:

| Producer | Accepted type | Permitted use |
| --- | --- | --- |
| M4 `catalogue_observations` | `sample_table`, `observation_table`, `occurrence_table`, `occurrence_summary` | Source rows and their declared sample/observation/provenance fields; do not infer omitted rows. |
| M4 `observations` | `occurrence_table`, `occurrence_summary` | Link outputs produced from explicitly supplied M4 `sample_table` and `observation_table`; do not infer omitted rows. |
| M7 `independent_recurrence` | `m7_observation_table`, `m7_exact_recurrence_table`, `m7_independence_summary`, `m7_validation_report`, `m7_provenance_manifest` | Link declared candidate/sample/run/study identities and M7 statuses. M7 independence remains unverified unless the M14 manifest carries a separate verification record. |

The primary M14 input is a caller-authored, versioned observation table
embedded in the manifest. M4 and M7 references are optional sources for those
rows. No additional M14 input artifact type is assumed. No M5/M8/M9 result,
sequence database, or raw read is a required input.

## 3. Input manifest and observational-unit model

The UTF-8 JSON manifest uses `schema = "m14-input-v1"`:

```json
{
  "schema": "m14-input-v1",
  "dataset_id": "stable non-sensitive identifier",
  "source_artifacts": [],
  "source_outcomes": [],
  "sampling_units": [],
  "evaluated_pairs": [],
  "observations": [],
  "analysis_profile": null
}
```

`dataset_id` is required. `source_artifacts` contains only verified immutable
`ArtifactRef` objects; `source_outcomes` is required typed metadata for each
optional M4/M7 source family and run, including an explicit `NOT_SUPPLIED`
record when the source was not provided or `NOT_RUN` when a declared source
slot was not executed. Neither state has a placeholder scientific artifact.
`NOT_SUPPLIED` has no artifact, workflow reference, path, or digest; `NOT_RUN`
may retain a real M1 workflow/stage reference only when M1 records the producer
as skipped. The allowed
producer/type pairs and exact outcome rules are defined in the
[contract clarification](research/M14_CONTRACT_CLARIFICATION.md#1-input-boundary-and-optional-source-records).
For supplied artifacts, the reference binds the producer workflow/stage,
completed stage-manifest digest, exact artifact type/version, relative path,
content digest, and raw producer status. Resolve only explicit
workspace-relative references; do not search the filesystem.

`sampling_units`, `evaluated_pairs`, and `observations` are required arrays.
An all-empty or explicit zero-unit scope is `NOT_EVALUATED`. A nonempty
declared frame with missing or rejected pair/unit rows is `INCOMPLETE`; a
structurally invalid required manifest is `INVALID_INPUT`. A complete
nonempty frame with no jointly tested/evaluable rows is
`INSUFFICIENT_MATCHED_EVIDENCE`. Exact precedence is normative in the
[clarification, §2](research/M14_CONTRACT_CLARIFICATION.md#2-frame-evidence-and-result-precedence).
`analysis_profile` must be null in this baseline; any non-null inferential
model is rejected as an unsupported optional branch.

Each `sampling_units` row has exactly these fields:

| Field | Contract |
| --- | --- |
| `unit_id` | Stable unique opaque ID within the sampling frame. |
| `unit_type` | `SAMPLE`, `SPECIMEN`, `LIBRARY`, `RUN`, `EXPERIMENT`, `STUDY`, or `OTHER_DECLARED`; the last requires `unit_type_label`. |
| `unit_type_label` | Null for a standard type; required non-empty source-declared label for `OTHER_DECLARED`. |
| `parent_unit_ids` | Sorted unique list of declared related units; empty if none are supplied. |
| `study_id` | Opaque declared study ID or null; null is unknown, not a new study. |
| `independence_state` | `UNVERIFIED`, `VERIFIED_WITH_PROVENANCE`, or `UNKNOWN`; no inferred independence. |
| `independence_ref` | Immutable verification evidence reference; required only for `VERIFIED_WITH_PROVENANCE`, otherwise null. |
| `control_role` | Null or an object containing the exact source-declared role label and provenance ref; M14 does not normalize, match, or assess adequacy. |
| `source_refs` | Sorted provenance references for the unit; may be empty only for synthetic fixtures. |

Each `evaluated_pairs` row defines one candidate/helper pair and its complete
sampling frame for this run: `candidate_id`, `helper_id`, and a sorted,
duplicate-free `unit_ids` array. Every listed unit must exist in
`sampling_units`. Every pair/unit combination must have exactly one matching
observation row. This makes the declared denominator frame explicit; a
missing row is an invalid/incomplete input, never an implicit negative.

Each observation row has exactly these required fields:

| Field | Contract |
| --- | --- |
| `observation_id` | Stable unique row ID within `dataset_id`. |
| `candidate_id`, `helper_id` | Opaque IDs; labels are not verified taxonomy. |
| `unit_id` | Foreign key to one sampling-unit row. |
| `candidate_state`, `helper_state` | Each is `PRESENT`, `NOT_DETECTED_WITHIN_SCOPE`, `UNKNOWN`, `UNAVAILABLE`, `NOT_APPLICABLE`, or `CONFLICTING`. |
| `candidate_state_reason`, `helper_state_reason` | Null for `PRESENT`/`NOT_DETECTED_WITHIN_SCOPE`; non-empty source-grounded reason for `UNKNOWN`, `UNAVAILABLE`, `NOT_APPLICABLE`, or `CONFLICTING`. |
| `candidate_tested`, `helper_tested` | Boolean indicator that the row's designated method was evaluated; false cannot pair with `PRESENT` or `NOT_DETECTED_WITHIN_SCOPE`. |
| `candidate_method_ref`, `helper_method_ref` | `MethodRef` object when the matching tested flag is true; otherwise null or the declared unavailable method reference. |
| `candidate_detection_limit`, `helper_detection_limit` | `DetectionLimit` object or null when not supplied; do not convert to an assumed sensitivity. |
| `source_refs` | Sorted provenance references for the observation; may be empty only for synthetic fixtures. |

`MethodRef` contains non-empty `method_id`, `method_version`, `scope_id`, and
`scope_description`, plus a provenance reference to the method/run record.
`DetectionLimit` contains `metric`, numeric non-negative `value`, `unit`, and
`basis`; null means no detection limit was supplied. The `scope_description`
states what was actually evaluated (for example, a named assay and its
declared specimen scope), not an inferred biological sampling frame.

No inference is made from the identifier names or relationship graph.
`VERIFIED_WITH_PROVENANCE` means the supplied verification record exists and
passes integrity checks; it does not mean M14 has independently audited the
underlying biology.

`PRESENT` and `NOT_DETECTED_WITHIN_SCOPE` require the relevant `*_tested` to be
true and a method reference. `NOT_DETECTED_WITHIN_SCOPE` also requires a
declared detection scope. `CONFLICTING` requires at least two distinct
provenance references supporting incompatible observations; it is excluded
from the 2×2 cells and has `*_tested = false` because no single designated
method result is being summarized. `UNAVAILABLE` and `NOT_APPLICABLE` require
`*_tested = false`; `UNKNOWN` may be tested or untested, but a true tested flag
requires its method reference. Each state reason identifies the supplied
source-grounded explanation without asserting a biological cause. The unit
must be listed under the pair’s `unit_ids`.
`UNKNOWN` means state cannot be inferred from supplied data. `UNAVAILABLE`
means an attempted/required measurement or source dependency could not be
obtained or run. `NOT_APPLICABLE` must be explicitly declared; it is not a
synonym for missing or untested.

## 4. Outputs and exact counting rules

Proposed future output artifact types:

- `m14_observation_table` — normalized rows plus exact source-row references.
- `m14_descriptive_summary` — counts and denominators only.
- `m14_result_bundle` — manifest binding inputs, outputs, and provenance.

Each stratum is keyed by `dataset_id`, candidate ID, helper ID, `unit_type`,
declared `control_role`, optional `study_id`, and the candidate/helper method
scope-ID pair. Null values remain explicit categories and are not merged with
declared values. It reports:

- `n_rows`, `n_unique_units`, `n_candidate_tested`, `n_helper_tested`,
  `n_jointly_tested`, and `n_unknown_or_unavailable`.
- `n_candidate_tested` and `n_helper_tested` count pair/unit rows with the
  respective tested flag true, regardless of the other member’s state.
  `n_jointly_tested` counts rows where both tested flags are true and both
  states are evaluable as `PRESENT` or `NOT_DETECTED_WITHIN_SCOPE`.
  `n_unique_units` is the number of distinct unit IDs in that stratum.
- `n_rows` counts accepted pair/unit rows. `n_unknown_or_unavailable` counts
  rows with either member in `UNKNOWN` or `UNAVAILABLE`; `NOT_APPLICABLE` and
  `CONFLICTING` have separate counts.
- The exact declared control-role labels represented in each stratum; control
  adequacy and matching are not computed.
- Four 2×2 cells only over unique units where both candidate and helper were
  tested under declared methods and each state is present or scoped-not-detected:
  both present; candidate present/helper not-detected; candidate
  not-detected/helper present; both not-detected.
- Separate counts for `UNKNOWN`, `UNAVAILABLE`, `NOT_APPLICABLE`, `CONFLICTING`,
  and rows excluded from joint testing, with reasons.

The jointly tested/evaluable denominator is the number of pair/unit rows for
which both tested flags are true and both states are either `PRESENT` or valid
`NOT_DETECTED_WITHIN_SCOPE`. The denominator scope is the exact `unit_ids` list
on the matching `evaluated_pairs` row; a separate untested or unobserved unit
cannot silently join it. Duplicate pair/unit rows are invalid. Conflicting
source records are represented in that row as `CONFLICTING` with their distinct
provenance refs and excluded from the four cells; they are never resolved by
row order.

The M14 computation result state is `COMPLETED_DESCRIPTIVE`,
`NOT_EVALUATED`, `INSUFFICIENT_MATCHED_EVIDENCE`, `INVALID_INPUT`, or
`INCOMPLETE`. `FAILED` and `INTERRUPTED` are M1 execution lifecycle states,
not M14 computation results; a handler failure/interruption does not publish
an M14 result bundle.
There is no association estimate or dependence status in the baseline. A
schema-valid run with no eligible units completes as M1 `complete` and
`NOT_EVALUATED` only for a zero-unit scope, or
`INSUFFICIENT_MATCHED_EVIDENCE` for a complete nonempty frame with no eligible
rows. Semantic input errors produce the typed `INVALID_INPUT` result when the
M14 handler can serialize the supplied manifest. A handler runtime failure or
interruption remains M1 `failed` or `interrupted` and does not publish a
reusable M14 result. Optional-source outcomes never override the caller-frame
result; preserve partial valid rows and exclude only rows whose required
provenance fails verification. See the
[normative precedence table](research/M14_CONTRACT_CLARIFICATION.md#2-frame-evidence-and-result-precedence).

## 5. Validation, failures, and deterministic behavior

- Require exact schema, unique IDs, valid enum values, typed source refs, and
  all artifact digests. Mark an unrecognized optional producer/type pair as
  that source's `INVALID` outcome; do not discard independent valid sources.
  If a required observation row depends on that reference, reject that row and
  apply the frame/result precedence in §2.
- Reject `NOT_DETECTED_WITHIN_SCOPE` without a positive tested flag, method
  reference, declared detection scope, and denominator membership. Reject
  `UNAVAILABLE`/`NOT_APPLICABLE` with a true tested flag or without a reason;
  reject any missing state reason required by the field table.
- Reject `VERIFIED_WITH_PROVENANCE` without an integrity-verifiable
  `independence_ref`; never upgrade `UNVERIFIED` automatically.
- Reject duplicate observation IDs and duplicate pair/unit rows. Distinct
  conflicting source records must be represented in one `CONFLICTING` row with
  their provenance refs. Do not silently deduplicate, assume independence, or
  count mates, technical replicates, lanes, or runs as biological units.
- Missing observation rows do not become `NOT_DETECTED`. Missing metadata
  yields `UNKNOWN`; an unavailable method remains `UNAVAILABLE`.
- Source-outcome rows must obey the exact state/reference combinations in the
  [contract clarification](research/M14_CONTRACT_CLARIFICATION.md#11-verification-and-source-state-rules).
  Optional failures remain per-source outcomes and cannot become negative
  observations. Reject malformed required rows and invalid required
  provenance; retain independent valid rows. If every nonempty supplied
  observation row is rejected, report `INVALID_INPUT`; if valid rows remain
  but the declared frame has a hole, report `INCOMPLETE`.
- Inferential `analysis_profile` is rejected by this baseline. It does not
  fall back to a default statistical model.

Serialize JSON as UTF-8, no BOM, LF, one trailing newline, sorted object keys,
no NaN/Infinity. Sort rows by study ID (null first), unit type, unit ID,
candidate ID, helper ID, observation ID. Sort strata and cell reports
lexicographically by their key fields, with null before declared values. Do not
depend on input file order. Canonical source/frame ordering, semantic identity,
and the distinction between scientific identity and raw-byte provenance are
specified in the
[contract clarification, §3](research/M14_CONTRACT_CLARIFICATION.md#3-canonical-m14-identity-reuse-and-serialization).

## 6. Provenance and cache identity

The result bundle records the canonical semantic input digest,
`m14_provenance_sha256`, `m14_cache_identity_sha256`, dataset ID; all
source-outcome states; each available artifact’s producer stage/run digest,
type/version, raw status, and content digest; normalized
observation-row digests; unit/relationship/independence fields;
method/detection limits; denominator rules; schema/semantic version; consumed
M4/M7 artifact-contract semantic identities; M14-scoped implementation
identity; and all output hashes. Do not bind unreferenced files, absolute
paths, timestamps, host identity, or unrelated workflow-stage metadata into
the semantic digest. The semantic digest excludes raw run IDs and byte
digests; the separate provenance digest binds those exact verified sources.

The semantic, provenance, and composite M14 cache identities are defined in
[contract clarification, §3](research/M14_CONTRACT_CLARIFICATION.md#3-canonical-m14-identity-reuse-and-serialization).
The existing M1 stage cache key additionally partitions by stage identity and
uses the normalized M14 configuration and per-source dependency report.
Workspace-root relocation with unchanged relative references does not change
identity. Changes to observation semantics, denominator, source state,
verified producer run/artifact, M14 rules, or consumed contract semantics
invalidate M14 only; they do not rewrite M4/M7 or alter M1–M13 cache
identities. Raw artifact digests remain exact integrity/provenance values;
line-ending-only text changes may change provenance/cache identity while
leaving the scientific semantic digest and counts unchanged. To preserve
unscoped earlier-stage keys across M14-only source changes, update the
accepted LF/CRLF source digests in
`satellite_discovery/m12_legacy_cache_compatibility.txt` while preserving its
legacy baseline. Reuse requires matching composite identity and full
output-hash/contract checks.

## 7. Synthetic acceptance fixtures

| Fixture | Required result |
| --- | --- |
| Four valid combinations across four unique sample units | Exact hand-counted 2×2 cells and `n_jointly_tested = 4`. |
| Candidate/helper `NOT_DETECTED_WITHIN_SCOPE` without a test/method/denominator | Reject row; it cannot enter a negative cell. |
| Same sample with multiple runs/libraries | Preserve parent relationships; denominator counts only the declared analysis unit and never silently treats runs as independent samples. |
| Missing row, `UNKNOWN`, `UNAVAILABLE`, `NOT_APPLICABLE` | Separate counts; none enters a not-detected cell. |
| One pair/unit row with conflicting source refs | Preserve the conflicting provenance and exclude that unit from the 2×2 cells pending curation. |
| M7 declared recurrence with `independence_state = UNVERIFIED` | Link metadata; no verified-independence summary. |
| Empty observation list | `NOT_EVALUATED`, zero evaluated denominator, no negative association. |
| Non-null inferential profile | Validation error; no hidden default model or tool. |
| Unsupported optional source artifact | Per-source `INVALID`; no incompatible artifact is consumed and independent rows remain eligible. |
| One `NOT_SUPPLIED` or `NOT_RUN` outcome for each source family with no supplied run | No path or artifact is fabricated; a complete caller frame still computes normally. A real M1 `skipped` stage may be retained with `NOT_RUN`. |
| Supplied, valid M4/M7 source with producer-native no-signal status | Preserve `AVAILABLE` plus the exact scoped producer result; do not convert it into an M14 negative or no-association result. |
| Optional source unavailable, not run, failed, or interrupted | Preserve distinct source outcome and raw M1 status; consume no uncommitted artifact and do not block independent caller rows. |
| Optional source nonterminal or positively marked incomplete/truncated | Preserve `INCOMPLETE`; do not consume the unfinished artifact. A malformed/truncated byte stream without a valid incomplete marker is `INVALID`. |
| Optional source incompatible, corrupt, or digest-mismatched | Preserve `INVALID` and the attempted-reference reason; do not interpret it as absence or no signal. |
| Complete zero-unit declared scope | `NOT_EVALUATED`, zero denominator, no negative claim. |
| Complete nonempty frame with no jointly evaluable rows | `INSUFFICIENT_MATCHED_EVIDENCE`; no 2×2 negative inference. |
| Partial valid rows with another optional source failed/invalid | Keep independently valid rows and source outcomes; `INCOMPLETE` if the declared frame has holes, otherwise result follows the complete frame. |
| Two verified, incompatible source records for one pair/unit | Preserve one `CONFLICTING` observation with distinct provenance; exclude it from all 2×2 cells, not `INVALID`. |
| Nonterminal selected producer stage | Source `INCOMPLETE`; uncommitted artifacts are not consumed; no required M14 row is inferred from it. |
| M7 valid partial accounting caused by M6 gaps | Source `AVAILABLE`, `producer_completeness=PARTIAL`; preserve M7's statuses without converting them into M14 absence. |
| Permuted order of semantically unordered inputs | Same canonical semantic identity, normalized output order, output bytes, and hashes. |
| Equivalent numeric detection-limit tokens (`1`, `1.0`, `1e0`) | Same normalized semantic identity and canonical JSON number in output. |
| Workspace moved with unchanged relative layout | Same M14 semantic identity and cache dependency; no absolute path is serialized. |
| LF/CRLF-only manifest or implementation-source variation | Same M14 scientific semantic identity and counts; raw source artifact digest remains an exact provenance value. |
| M14 configuration/rule change or relevant upstream artifact change | M14-only invalidation; M1–M13 producer outputs and identities remain unchanged. |
| Irrelevant timestamp, host path, unrelated workflow-stage metadata, or unreferenced artifact change | No change to M14 semantic identity. |
| Stale or tampered M14 output | Reject reuse when any stage/output/result-bundle hash or contract check fails. |

## 8. Compatibility and claim boundary

M14 reads existing M4 table types and M7 outputs without changing their
contracts. It does not alter M7 recurrence or independently establish declared
sample/run/study relationships. Additive M4 registration and M14 artifact
validators are required for later workflow execution. M14 supports scoped
descriptive co-detection only; association requires a separately reviewed
profile, and helper dependence requires claim-appropriate experimental
evidence outside this contract. M13 is not a prerequisite: no M13 producer or
artifact type is in the M14 source allowlist.
