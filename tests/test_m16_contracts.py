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
