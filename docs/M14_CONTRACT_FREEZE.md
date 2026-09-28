# M14 contract freeze: descriptive candidate/helper observations

**Contract status: FROZEN FOR THE DESCRIPTIVE SYNTHETIC/OFFLINE BASELINE.**
**Milestone status: PLANNED / NOT IMPLEMENTED.** This contract defines
observation identity, tested denominators, and descriptive counts. Inferential
association models and experimental dependence are not required baseline
behavior.

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
  "sampling_units": [],
  "evaluated_pairs": [],
  "observations": [],
  "analysis_profile": null
}
```

`dataset_id` is required. `source_artifacts` contains immutable `ArtifactRef`
objects with producer milestone/stage, producer-run-manifest digest, exact
artifact type/version, relative path, content digest, and raw producer status.
The allowed producer/type pairs are listed in section 2. `sampling_units`,
`evaluated_pairs`, and `observations` are required arrays. They may all be
empty only when the result is `NOT_EVALUATED`; an empty table is not a zero
co-detection rate. `analysis_profile` must be null in this baseline; any
non-null inferential model is rejected as an unsupported optional branch.

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

The output state is `COMPLETED_DESCRIPTIVE`, `NOT_EVALUATED`,
`INSUFFICIENT_MATCHED_EVIDENCE`, `INVALID_INPUT`, `INCOMPLETE`, `FAILED`, or
`INTERRUPTED`.
There is no association estimate or dependence status in the baseline. A
schema-valid run with no eligible units completes as M1 `complete` and
`NOT_EVALUATED`/`INSUFFICIENT_MATCHED_EVIDENCE`. Invalid required input is
rejected by preflight or maps to M1 `failed`; runtime failure/interruption
uses the corresponding M1 lifecycle state. Missing optional sources remain
explicit states and do not block the descriptive result.

## 5. Validation, failures, and deterministic behavior

- Require exact schema, unique IDs, valid enum values, typed source refs, and
  all artifact digests. Reject an unrecognized producer/type pair.
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
- A malformed required manifest fails before execution. Invalid optional
  source rows are reported with validation errors; if no valid rows remain,
  the summary is `INVALID_INPUT`, not an empty successful negative.
- Inferential `analysis_profile` is rejected by this baseline. It does not
  fall back to a default statistical model.

Serialize JSON as UTF-8, no BOM, LF, one trailing newline, sorted object keys,
no NaN/Infinity. Sort rows by study ID (null first), unit type, unit ID,
candidate ID, helper ID, observation ID. Sort strata and cell reports
lexicographically by their key fields, with null before declared values. Do not
depend on input file order.

## 6. Provenance and cache identity

The result bundle records the manifest digest; dataset ID; every source
artifact’s producer stage/run digest, type/version, raw status, and content
digest; normalized observation-row digests; unit/relationship/independence
fields; method/detection limits; denominator rules; schema/semantic version;
consumed artifact-contract semantic identities; implementation/source digest;
and all output hashes.

The M14 cache identity includes every field above that affects row validity,
grouping, state, denominator, or output. Exclude generated timestamps and
absolute paths. A change in unit relationships, detection states, tested
denominators, source table bytes, or contract version invalidates M14 only;
it does not rewrite M7. Reuse requires identity match and output hash checks.

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
| Non-null inferential profile or unsupported source artifact | Validation error; no hidden default model or tool. |

## 8. Compatibility and claim boundary

M14 reads existing M4 table types and M7 outputs without changing their
contracts. It does not alter M7 recurrence or independently establish declared
sample/run/study relationships. Additive M4 registration and M14 artifact
validators are required for later workflow execution. M14 supports scoped
descriptive co-detection only; association requires a separately reviewed
profile, and helper dependence requires claim-appropriate experimental
evidence outside this contract.
