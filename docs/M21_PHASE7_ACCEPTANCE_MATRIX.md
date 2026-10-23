# M21 Phase 7 adversarial acceptance matrix

All cases below use fixed synthetic fixtures and independently named `unittest`
methods in `tests/test_m21_phase7_acceptance_matrix.py`. Each adversarial case
expects `FAIL` and asserts it; the untrusted fixture never authorizes execution.
Checkpoint rotation acceptance and the valid uncheckpointed suffix are positive
controls in `test_phase7_custody_allows_valid_suffix_and_rejects_missing_local_history`.

| Case | Test function | Expected | Observed locally |
|---|---|---:|---:|
| Missing qualification document | `test_missing_qualification_document` | FAIL | FAIL |
| Altered qualification evidence | `test_altered_qualification_evidence` | FAIL | FAIL |
| Missing reference manifest | `test_missing_reference_manifest` | FAIL | FAIL |
| Reference snapshot substitution | `test_reference_snapshot_substitution` | FAIL | FAIL |
| Duplicate reference artifact | `test_duplicate_reference_artifact` | FAIL | FAIL |
| Excluded-sequence policy changed | `test_excluded_sequence_policy_change` | FAIL | FAIL |
| Aggregate budget exhausted | `test_aggregate_budget_exhaustion` | FAIL | FAIL |
| Scientific review rejects panel | `test_scientific_review_rejection` | FAIL | FAIL |
| Altered policy approval | `test_altered_policy_approval` | FAIL | FAIL |
| Missing blinded analysis | `test_missing_blinded_analysis` | FAIL | FAIL |
| Analysis digest substitution | `test_analysis_digest_substitution` | FAIL | FAIL |
| Truth fields leak into blinded analysis | `test_truth_leakage_in_analysis` | FAIL | FAIL |
| Qualification binding substituted | `test_qualification_binding_substitution` | FAIL | FAIL |
| Missing unblinding authorization | `test_missing_unblinding_authorization` | FAIL | FAIL |
| Unblinding snapshot substituted | `test_unblinding_snapshot_substitution` | FAIL | FAIL |
| Altered unblinding signature | `test_altered_unblinding_signature` | FAIL | FAIL |
| Missing truth bundle | `test_missing_truth_bundle` | FAIL | FAIL |
| Signed scoring result changed | `test_scoring_result_tamper` | FAIL | FAIL |
| Wrong artifact type/path | `test_wrong_artifact_type` | FAIL | FAIL |
| Artifact changes during verification | `test_artifact_changed_during_verification` | FAIL | FAIL |
| Receipt replay | `test_receipt_replay` | FAIL | FAIL |
| Invalid intermediate transition | `test_invalid_intermediate_transition` | FAIL | FAIL |
| Expired transition signer | `test_expired_transition_signer` | FAIL | FAIL |
| Revoked transition signer | `test_revoked_transition_signer` | FAIL | FAIL |
| Checkpoint rollback | `test_checkpoint_rollback` | FAIL | FAIL |
| Required local checkpoint history missing | `test_checkpoint_missing_local_history` | FAIL | FAIL |
| Checkpoint history reordered | `test_checkpoint_rotation_reordered` | FAIL | FAIL |

The signed matrix-attestation validator accepts only these 27 ordered case IDs,
the exact associated test-function names, and matching `expected`/`observed`
outcomes. Two distinct trusted governance reviewers must sign the canonical
matrix digest before readiness can consume its result.
