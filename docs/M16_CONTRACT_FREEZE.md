# M16 contract freeze: synthetic benchmark and leakage harness

**Contract status: FROZEN FOR GENERIC SYNTHETIC MECHANICS ONLY.** M16 is
**PLANNED / NOT IMPLEMENTED**. This contract defines a generated-fixture
manifest, split/group validation, label isolation, deterministic outcome
accounting, and custody state transitions. It does not select or execute an
empirical benchmark.

These mechanics are not the roadmap's final independent-holdout benchmark or
claim-appropriate biological validation. Those remain outside this frozen
synthetic contract and require separately approved criteria, data, and assays.

## 1. Scope and non-goals

M16 validates synthetic fixture manifests and may compare a frozen target
output with a synthetic expected software outcome after the prediction output
is committed. It exercises grouping/leakage rules, custody/blinding mechanics,
execution-state accounting, denominators, coverage, abstention, and stable
reporting.

This contract does not:

- Select biological benchmark items, datasets, truth labels, or actual
  development/validation/holdout membership.
- Define biological truth tiers, performance thresholds, stop rules, or
  claim-generalization criteria.
- Retrieve sequences/read payloads or run external callers.
- Treat synthetic expected behavior as empirical truth or report biological
  sensitivity, specificity, accuracy, calibration, or function.
- Change M12–M15 outputs or feed benchmark results back into those stages.

Any input with `dataset_kind = "EMPIRICAL"` is rejected by this contract as
`OUT_OF_SCOPE`; a future empirical benchmark requires a separately approved
contract version and decisions recorded outside this freeze.

## 2. Runner and accepted target artifacts

The future allowlisted stage is `m16_synthetic_benchmark`. It uses the existing
artifact-workflow manifest runner and its preflight mode. No new top-level CLI,
dynamic module, arbitrary command, or biological-data loader is defined. An
additive M4 stage registration and M16 artifact validators will be needed
before workflow execution.

The only target artifacts accepted in this baseline are frozen outputs from:

| Producer | Accepted type |
| --- | --- |
| M12 artifact-bounded review | `m12_result_bundle` |
| M13 M5-only dossier | `m13_result_bundle` |
| M14 descriptive observations | `m14_result_bundle` |
| M15 lossless dossier | `m15_result_bundle` |

Each target ref contains producer milestone/stage ID, run-manifest SHA-256,
artifact type, artifact semantic version, relative path, output SHA-256, and
the exact target implementation/configuration identity. The target must be
frozen before fixture predictions are generated. A synthetic test adapter may
be registered for mechanics-only tests; it cannot supply biological labels.

## 3. Input manifests and hidden-label boundary

M16 consumes two separately hashed UTF-8 JSON inputs:

1. **Public manifest** (`schema = "m16-public-manifest-v1"`), visible to the
   target execution path:

```json
{
  "schema": "m16-public-manifest-v1",
  "dataset_kind": "SYNTHETIC_FIXTURE",
  "fixture_set_id": "stable synthetic identifier",
  "target_ref": {},
  "adapter_id": "registered adapter identifier",
  "adapter_version": "immutable version",
  "items": []
}
```

2. **Sealed fixture key** (`schema = "m16-synthetic-key-v1"`), readable only
   by the scoring step after the prediction artifact is finalized:

```json
{
  "schema": "m16-synthetic-key-v1",
  "fixture_set_id": "same synthetic identifier",
  "items": []
}
```

Every public item contains:

| Field | Requirement |
| --- | --- |
| `item_id` | Unique stable synthetic ID. |
| `target_input_ref` | Hash-bound synthetic input/fixture reference; no empirical payload. |
| `group_ids` | Sorted IDs for synthetic duplicate/family/sample/run/study/lab grouping cases. |
| `split_role` | `DEVELOPMENT`, `TUNING`, `SYNTHETIC_HOLDOUT`, or `UNASSIGNED`; used only to test generic split validation. |
| `label_state` | `SEALED_SYNTHETIC_EXPECTATION`, `UNKNOWN`, or `NOT_APPLICABLE`. |
| `fixture_provenance` | Required declaration that the item is generated for software-contract testing, not empirical truth. |

The sealed key contains one entry per labelled item with `item_id`,
`expected_software_outcome`, and `label_scope = "SOFTWARE_CONTRACT"`.
`expected_software_outcome` is a string/object defined by the registered
synthetic adapter schema, not a biological class. Unknown/not-applicable items
have no expected outcome. The public manifest must not contain an expected
outcome or label-key path that the target can read. The public runner receives
only the public manifest, target artifact, and input fixtures; the scorer
receives predictions plus the sealed key after prediction commitment.

There is no empirical `positive`, `negative`, `disputed truth`, or biological
label enum in this contract.

## 4. Outputs, states, and metric mechanics

Proposed future output artifact types:

- `m16_prediction_table` — item IDs and target outcomes/abstentions with target
  provenance, written before scoring.
- `m16_leakage_report` — group/split checks with offending IDs for synthetic
  fixtures.
- `m16_custody_log` — append-only state transitions and actor/tool identity.
- `m16_metric_summary` — deterministic synthetic outcome/denominator counts.
- `m16_result_bundle` — input, target, prediction, scoring-key commitment, and
  output digests.

Prediction `execution_state` is one of `COMPLETED`, `NOT_EVALUATED`,
`DEPENDENCY_UNAVAILABLE`, `FAILED`, `INTERRUPTED`, `INCOMPLETE`, `TRUNCATED`,
or `INVALID_INPUT`. `outcome_state` is `EMITTED`, `ABSTAINED`,
`NOT_APPLICABLE`, or `UNKNOWN`. These describe software execution, not truth.
The workflow lifecycle itself remains the existing M1 state set.

For metric accounting, define two non-overlapping accounting axes:

- Item/prediction axis: `n_items` is the public item count. Every item is
  counted exactly once as `PREDICTION_EMITTED`, `ABSTAINED`,
  `OUTCOME_UNKNOWN`, `NOT_EVALUATED`, `DEPENDENCY_UNAVAILABLE`, `FAILED`,
  `INTERRUPTED`, `INCOMPLETE`, `TRUNCATED`, `INVALID_INPUT`, or
  `PREDICTION_NOT_APPLICABLE`. These counts sum to `n_items`. A completed
  item’s category follows `outcome_state`; a non-completed item’s category
  follows `execution_state` and its outcome is null/unknown.
- Label axis: `n_labelled` is the number of items with a matching sealed
  `SEALED_SYNTHETIC_EXPECTATION`; `n_unknown_label` and
  `n_not_applicable_label` are reported separately and are not included in
  `n_labelled`. These three label-state counts sum to `n_items` and are
  independent of the prediction-state counts.
- `n_emitted` is the number of labelled items with
  `execution_state = COMPLETED` and `outcome_state = EMITTED`.
- `n_exact_match` is the number of emitted outcomes exactly equal to the
  sealed synthetic expected outcome.
- `coverage = n_emitted / n_labelled`.
- `fixture_agreement_rate = n_exact_match / n_emitted`.
- `fixture_match_over_labelled = n_exact_match / n_labelled`.

Rates are null when their denominator is zero and otherwise serialized as
decimal numbers at a fixed declared precision. These are software-fixture
mechanics only, not biological performance estimates. No threshold is applied.

## 5. Group/leakage and custody rules

For this harness, all items sharing any identical non-empty `group_id` must
have the same `split_role`; otherwise the leakage report is `LEAKAGE_DETECTED`
and scoring is blocked. Duplicate `item_id`, a group ID with malformed type,
or an item whose `dataset_kind`/fixture provenance is not synthetic is invalid.
The synthetic manifest can exercise development/tuning/holdout separation,
but this contract assigns no real items to those partitions.

The custody state machine is:

```text
SEALED -> PREDICTIONS_COMMITTED -> BLINDED_CHECKED -> SCORED
   \             \                    \
    +-------------+--------------------+-> INTEGRITY_FAILED
```

- `SEALED`: key digest recorded; key content unavailable to target execution.
- `PREDICTIONS_COMMITTED`: prediction bytes and target identity hashed and
  immutable.
- `BLINDED_CHECKED`: execution record confirms that the public runner was not
  given the key content and leakage checks passed.
- `SCORED`: scorer opened the synthetic key after all prior checks.
- `INTEGRITY_FAILED`: terminal; no score may be produced.

The log records transition, timestamp-independent event sequence number,
actor/tool identity, relevant artifact digests, and reason. No synthetic result
may claim blinded empirical evaluation.

## 6. Validation, failure propagation, and deterministic output

- Validate exact schema, target type/identity, adapter registration/version,
  unique item IDs, synthetic-only provenance, matching public/key fixture-set
  IDs, key coverage, and SHA-256 values.
- Require exactly one prediction record per public item. A completed prediction
  has exactly one of `EMITTED`, `ABSTAINED`, `NOT_APPLICABLE`, or `UNKNOWN`;
  non-completed predictions have no emitted value and an unknown outcome.
  Prediction-state and label-state partitions are validated independently.
- Public target execution must finish and the prediction digest must be
  committed before scorer access. If label-key content is available to target
  execution, fail the blinding check and do not score.
- Run grouping checks before scoring. Leakage, target identity mismatch,
  hidden-label access, corrupted key, or changed prediction digest yields
  M16 result `INTEGRITY_FAILED`; the M1 stage lifecycle is `failed` and no
  metrics are emitted.
- A target item may be unavailable, failed, interrupted, incomplete, or
  abstained while other items remain in the result. Preserve each state and
  denominator; do not silently drop rows.
- Invalid manifest is rejected before execution. A missing target dependency
  maps to M1 `dependency_missing` or `external_module_required`; unknown labels
  are not negative labels.

Serialize UTF-8 JSON, no BOM, LF, one trailing newline, sorted object keys,
and no NaN/Infinity. Sort items and predictions by `item_id`, group checks by
`group_id` and split, custody events by sequence number, and metric rows by
adapter-defined outcome. The same fixture, target, adapter, and key must yield
byte-identical semantic outputs.

## 7. Provenance and cache identity

Bind the public-manifest digest, fixture-set identity, target producer/run and
output digest, target implementation/configuration identity, adapter ID and
version, group graph, split roles, label-state summary, sealed-key commitment,
prediction digest, scoring implementation/version, contract semantic version,
and all output hashes.

The target-execution identity excludes the sealed key content and expected
outcomes; it includes only the public-manifest digest and sealed-key
commitment supplied by the custodian. The scoring identity additionally binds
the sealed-key digest and prediction digest. A target/config/adapter/fixture
change invalidates M16 only; it does not rewrite M12–M15 outputs. Reuse requires
all identities and output hashes to match.

## 8. Synthetic acceptance fixtures

| Fixture | Required result |
| --- | --- |
| Fully synthetic expected outcomes and matching predictions | Exact counts/rates from the formulas above; all output marked `SOFTWARE_CONTRACT`. |
| Hidden key supplied to the target runner | Blinding check fails; no score. |
| Same synthetic group appears in development and synthetic holdout | `LEAKAGE_DETECTED`; score blocked. |
| Unknown or not-applicable item | Counted separately; never added to `n_labelled` or a negative denominator. |
| Completed item with unknown outcome | Count as `OUTCOME_UNKNOWN`; exclude from `n_emitted` and `n_exact_match`. |
| Abstained/unavailable/failed/incomplete prediction | Retain row; report exact state and denominator effect. |
| Zero labelled or zero emitted items | Rates are null for zero denominators; no divide-by-zero or implicit zero score. |
| Corrupt key, target digest, or post-commit prediction bytes | `INTEGRITY_FAILED`; no metrics. |
| Manifest claims empirical source or biological label | Reject `OUT_OF_SCOPE`; do not retrieve or evaluate the payload. |

## 9. Compatibility and claim boundary

M16 consumes only frozen M12–M15 result bundles and generated fixtures. It
does not change upstream artifacts, tool identities, or biological
interpretations. An additive M4 stage registration is required if the harness
is exposed through the existing workflow runner; test-only adapter mechanics
may be exercised by synthetic tests without a production stage. This contract
does not define empirical truth tiers, holdout membership, final metrics,
thresholds, or stop rules.
