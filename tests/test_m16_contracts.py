import unittest

from satellite_discovery import m16_contracts


def target_ref():
    return {
        "schema": m16_contracts.TARGET_REF_SCHEMA,
        "producer_milestone": "M15",
        "producer_execution_ref": {
            "schema": "producer-execution-ref-v1",
            "producer_workflow_ref": {
                "path": "workflow.json",
                "sha256": "a" * 64,
                "workflow_id": "synthetic-m15-workflow",
            },
            "producer_stage_id": "m15-fixture",
            "producer_stage_kind": "m15_evidence_dossier",
            "producer_stage_manifest_sha256": "b" * 64,
        },
        "bundle_root_ref": "m15-output",
        "artifact_type": "m15_result_bundle",
        "contract_version": "1",
        "semantic_version": "2",
        "artifact_path": "m15-output/stage-runs/m15/result_bundle.json",
        "artifact_relative_path": "result_bundle.json",
        "artifact_sha256": "c" * 64,
        "implementation": {"source_sha256": "d" * 64},
        "contract_semantics": {"semantic_version": "2"},
        "configuration": {},
    }


def public_manifest(label_state="SEALED_SYNTHETIC_EXPECTATION"):
    return {
        "schema": m16_contracts.PUBLIC_MANIFEST_SCHEMA,
        "dataset_kind": "SYNTHETIC_FIXTURE",
        "fixture_set_id": "fixture-set-a",
        "sealed_key_commitment": "opaque-commitment-a",
        "target_ref": target_ref(),
        "adapter_id": "m15_dossier_state_projection",
        "adapter_version": "1",
        "items": [{
            "item_id": "item-a",
            "target_input_ref": {
                "path": "queries/item-a.json",
                "schema": m16_contracts.QUERY_SCHEMA,
                "sha256": "e" * 64,
            },
            "group_ids": ["family-a", "sample-a"],
            "split_role": "SYNTHETIC_HOLDOUT",
            "label_state": label_state,
            "fixture_provenance": {
                "schema": m16_contracts.FIXTURE_PROVENANCE_SCHEMA,
                "scope": "SOFTWARE_CONTRACT",
                "fixture_set_id": "fixture-set-a",
            },
        }],
    }


def custody_log():
    states = (
        ("SEALED", None, "a" * 64, None),
        ("PREDICTIONS_COMMITTED", "SEALED", "a" * 64, "b" * 64),
        ("BLINDED_CHECKED", "PREDICTIONS_COMMITTED", "a" * 64, "b" * 64),
        ("SCORED", "BLINDED_CHECKED", "a" * 64, "b" * 64),
    )
    events = []
    for sequence, (destination, source, target_digest, prediction_digest) in enumerate(
        states, start=1
    ):
        events.append({
            "sequence": sequence,
            "from_state": source,
            "to_state": destination,
            "actor": "m16-synthetic-benchmark",
            "tool_identity": "m16-stage-v1",
            "sealed_key_commitment": "opaque-custodian-commitment",
            "sealed_key_digest": "c" * 64 if destination == "SCORED" else None,
            "digests": {
                "target_binding_sha256": target_digest,
                "prediction_sha256": prediction_digest,
            },
            "reason": "synthetic custody fixture",
        })
    return {
        "schema": m16_contracts.CUSTODY_SCHEMA,
        "events": events,
        "terminal_state": "SCORED",
    }


class M16ContractTests(unittest.TestCase):
    def test_public_m15_profile_and_sealed_key_coverage(self):
        public = m16_contracts.validate_public_manifest(public_manifest())
        key = {
            "schema": m16_contracts.SYNTHETIC_KEY_SCHEMA,
            "fixture_set_id": "fixture-set-a",
            "sealed_key_commitment": "opaque-commitment-a",
            "items": [{
                "item_id": "item-a",
                "expected_software_outcome": {"result": "opaque-fixture-value"},
                "label_scope": "SOFTWARE_CONTRACT",
            }],
        }
        normalized = m16_contracts.validate_synthetic_key(key, public)
        self.assertEqual(normalized["items"][0]["item_id"], "item-a")
        self.assertEqual(
            m16_contracts.validate_query({
                "schema": m16_contracts.QUERY_SCHEMA,
                "evidence_ids": ["b" * 64, "a" * 64],
            })["evidence_ids"],
            ["a" * 64, "b" * 64],
        )

    def test_unknown_empirical_and_unsafe_inputs_are_rejected(self):
        empirical = public_manifest()
        empirical["dataset_kind"] = "EMPIRICAL"
        with self.assertRaises(m16_contracts.M16OutOfScopeError):
            m16_contracts.validate_public_manifest(empirical)

        unknown_field = public_manifest()
        unknown_field["biological_truth"] = "positive"
        with self.assertRaises(ValueError):
            m16_contracts.validate_public_manifest(unknown_field)

        unsafe_path = public_manifest()
        unsafe_path["items"][0]["target_input_ref"]["path"] = "../query.json"
        with self.assertRaises(ValueError):
            m16_contracts.validate_public_manifest(unsafe_path)

        wrong_target = public_manifest()
        wrong_target["target_ref"]["artifact_type"] = "m14_result_bundle"
        with self.assertRaises(ValueError):
            m16_contracts.validate_public_manifest(wrong_target)

    def test_public_key_commitment_and_item_coverage_must_match(self):
        public = m16_contracts.validate_public_manifest(public_manifest())
        key = {
            "schema": m16_contracts.SYNTHETIC_KEY_SCHEMA,
            "fixture_set_id": "fixture-set-a",
            "sealed_key_commitment": "wrong-commitment",
            "items": [{
                "item_id": "item-a",
                "expected_software_outcome": "opaque",
                "label_scope": "SOFTWARE_CONTRACT",
            }],
        }
        with self.assertRaises(m16_contracts.M16IntegrityError):
            m16_contracts.validate_synthetic_key(key, public)
        key["sealed_key_commitment"] = public["sealed_key_commitment"]
        key["items"] = []
        with self.assertRaises(ValueError):
            m16_contracts.validate_synthetic_key(key, public)

        unlabelled = m16_contracts.validate_public_manifest(
            public_manifest("UNKNOWN")
        )
        key["items"] = []
        self.assertEqual(
            m16_contracts.validate_synthetic_key(key, unlabelled)["items"], []
        )

    def test_custody_log_requires_commitment_and_canonical_digest_separately(self):
        value = custody_log()
        self.assertEqual(
            m16_contracts.validate_custody_log(value),
            {"event_count": 4, "terminal_state": "SCORED"},
        )

        missing_commitment = custody_log()
        del missing_commitment["events"][0]["sealed_key_commitment"]
        with self.assertRaises(ValueError):
            m16_contracts.validate_custody_log(missing_commitment)

        inconsistent_commitment = custody_log()
        inconsistent_commitment["events"][2][
            "sealed_key_commitment"
        ] = "another-opaque-commitment"
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            m16_contracts.validate_custody_log(inconsistent_commitment)

        missing_scored_digest = custody_log()
        missing_scored_digest["events"][-1]["sealed_key_digest"] = None
        with self.assertRaises(ValueError):
            m16_contracts.validate_custody_log(missing_scored_digest)

        opaque_value_in_digest = custody_log()
        opaque_value_in_digest["events"][-1]["sealed_key_digest"] = (
            "opaque-custodian-commitment"
        )
        with self.assertRaises(ValueError):
            m16_contracts.validate_custody_log(opaque_value_in_digest)

        digest_cannot_replace_commitment = custody_log()
        digest_cannot_replace_commitment["events"][0][
            "sealed_key_commitment"
        ] = None
        with self.assertRaises(ValueError):
            m16_contracts.validate_custody_log(digest_cannot_replace_commitment)

    def test_custody_log_forbids_key_digest_before_permitted_scorer_access(self):
        for event_index, state in enumerate(
            ("SEALED", "PREDICTIONS_COMMITTED", "BLINDED_CHECKED")
        ):
            with self.subTest(state=state):
                value = custody_log()
                value["events"][event_index]["sealed_key_digest"] = "c" * 64
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    m16_contracts.validate_custody_log(value)

    def test_custody_log_preserves_committed_identities_and_transition_order(self):
        changed_target = custody_log()
        changed_target["events"][2]["digests"][
            "target_binding_sha256"
        ] = "d" * 64
        with self.assertRaisesRegex(ValueError, "target identity changed"):
            m16_contracts.validate_custody_log(changed_target)

        changed_prediction = custody_log()
        changed_prediction["events"][3]["digests"][
            "prediction_sha256"
        ] = "e" * 64
        with self.assertRaisesRegex(ValueError, "prediction identity changed"):
            m16_contracts.validate_custody_log(changed_prediction)

        wrong_order = custody_log()
        wrong_order["events"][2]["to_state"] = "SCORED"
        with self.assertRaisesRegex(ValueError, "transition"):
            m16_contracts.validate_custody_log(wrong_order)

    def test_duplicate_queries_and_unsorted_or_duplicate_groups_are_rejected(self):
        with self.assertRaises(ValueError):
            m16_contracts.validate_query({
                "schema": m16_contracts.QUERY_SCHEMA,
                "evidence_ids": ["a" * 64, "a" * 64],
            })
        malformed = public_manifest()
        malformed["items"][0]["group_ids"] = ["sample-a", "family-a"]
        with self.assertRaises(ValueError):
            m16_contracts.validate_public_manifest(malformed)
        malformed = public_manifest()
        malformed["items"][0]["group_ids"] = ["family-a", "family-a"]
        with self.assertRaises(ValueError):
            m16_contracts.validate_public_manifest(malformed)


if __name__ == "__main__":
    unittest.main()
