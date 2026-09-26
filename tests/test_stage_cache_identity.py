import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from satellite_discovery import artifact_contracts
from satellite_discovery import artifact_workflow
from satellite_discovery.artifact_workflow import (
    _stage_cache_key,
    _stage_output_directory,
    build_default_registry,
)
from satellite_discovery.independent_recurrence import run_stage as run_m7_stage


class StageCacheIdentityTests(unittest.TestCase):
    def setUp(self):
        self.registry = build_default_registry()

    @staticmethod
    def _key(definition, stage_id, runtime=None, dependency=None, inputs=None):
        return _stage_cache_key(
            {"id": stage_id, "kind": definition.kind},
            definition,
            {},
            inputs or {},
            runtime or {},
            dependency,
        )

    @staticmethod
    def _registry_with_m9_probe(implementation_version):
        registry = build_default_registry()

        def run_probe(inputs, output, config):
            return []

        run_probe.cache_implementation_identity = lambda: {
            "stage": "m9-identity-probe",
            "implementation_version": implementation_version,
        }
        registry.register("m9_identity_probe", (), run_probe, version="1")
        return registry

    def test_a_b_c_m9_registration_and_source_changes_leave_m6_m7_m8_keys_stable(self):
        registry_before = build_default_registry()
        registry_after = self._registry_with_m9_probe("changed-m9-source")
        keys_before = {}
        keys_after = {}
        for kind in ("residual_evidence", "independent_recurrence", "m8_homology"):
            keys_before[kind] = self._key(
                registry_before.get(kind), kind,
                {"source_sha256": "package-before-m9"},
            )
            keys_after[kind] = self._key(
                registry_after.get(kind), kind,
                {"source_sha256": "package-with-m9"},
            )
        self.assertEqual(keys_before, keys_after)

        m6 = registry_before.get("residual_evidence").handler
        environment_before = {
            "software_version": "same",
            "git_revision": "revision-before-m9",
            "source_sha256": "package-before-m9",
            "python": "same-python",
            "platform": "same-platform",
        }
        environment_after = {
            **environment_before,
            "software_version": "with-m9",
            "git_revision": "revision-with-m9",
            "source_sha256": "package-with-m9",
        }
        identity_before = m6._identity(
            {"assembly": "none"}, {}, {"dependencies": []}, [],
            environment_before, {})
        identity_after = m6._identity(
            {"assembly": "none"}, {}, {"dependencies": []}, [],
            environment_after, {})
        self.assertEqual(identity_before, identity_after)
        self.assertEqual(
            identity_before["environment"],
            {"python": "same-python", "platform": "same-platform"},
        )

        first_m9 = self._registry_with_m9_probe("m9-source-v1")
        second_m9 = self._registry_with_m9_probe("m9-source-v2")
        self.assertNotEqual(
            self._key(first_m9.get("m9_identity_probe"), "m9_identity_probe"),
            self._key(second_m9.get("m9_identity_probe"), "m9_identity_probe"),
        )

    def test_d_unchanged_upstream_keys_select_the_previous_outputs(self):
        registry_before = build_default_registry()
        registry_after = self._registry_with_m9_probe("m9-source-v2")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            for kind in ("residual_evidence", "independent_recurrence", "m8_homology"):
                cached = output / (kind + "-cached")
                cached.mkdir()
                old_key = self._key(
                    registry_before.get(kind), kind,
                    {"source_sha256": "package-before-m9"},
                )
                current_key = self._key(
                    registry_after.get(kind), kind,
                    {"source_sha256": "package-with-m9"},
                )
                selected = _stage_output_directory(
                    output,
                    kind,
                    current_key,
                    {kind: {"cache_key": old_key, "output_path": cached.name}},
                )
                self.assertEqual(selected, cached.resolve())

    def test_e_m8_contract_semantic_change_invalidates_m8_only(self):
        definition = self.registry.get("m8_homology")
        before = self._key(definition, "m8_homology")
        with patch.dict(
            artifact_contracts._CONTRACT_SEMANTIC_VERSIONS,
            {"m8_summary": "2"},
        ):
            after = self._key(definition, "m8_homology")
        self.assertNotEqual(before, after)

    def test_f_reference_payload_and_search_profile_changes_invalidate_m8(self):
        definition = self.registry.get("m8_homology")
        payload_a = {
            "reference_payload_demo": {
                "sha256": "a" * 64,
                "artifact_type": "m8_reference_payload",
            },
        }
        payload_b = {
            "reference_payload_demo": {
                "sha256": "b" * 64,
                "artifact_type": "m8_reference_payload",
            },
        }
        common = {"source_sha256": "same-package"}
        first = self._key(
            definition, "m8_homology", common,
            {"search_profile_sha256": "profile-a"}, payload_a,
        )
        self.assertNotEqual(
            first,
            self._key(
                definition, "m8_homology", common,
                {"search_profile_sha256": "profile-a"}, payload_b,
            ),
        )
        self.assertNotEqual(
            first,
            self._key(
                definition, "m8_homology", common,
                {"search_profile_sha256": "profile-b"}, payload_a,
            ),
        )

    def test_g_shared_artifact_validator_change_invalidates_m6_m7_m8(self):
        kinds = ("residual_evidence", "independent_recurrence", "m8_homology")
        before = {
            kind: self._key(
                self.registry.get(kind), kind,
                {"source_sha256": "same-package"},
            )
            for kind in kinds
        }
        with patch.object(artifact_contracts, "VALIDATOR_SEMANTIC_VERSION", "2"):
            after = {
                kind: self._key(
                    self.registry.get(kind), kind,
                    {"source_sha256": "same-package"},
                )
                for kind in kinds
            }
        for kind in kinds:
            with self.subTest(stage=kind):
                self.assertNotEqual(before[kind], after[kind])

        with patch.object(artifact_workflow, "WORKFLOW_CACHE_SEMANTICS_VERSION", "2"):
            runner_semantics_changed = {
                kind: self._key(
                    self.registry.get(kind), kind,
                    {"source_sha256": "same-package"},
                )
                for kind in kinds
            }
        for kind in kinds:
            with self.subTest(runner_stage=kind):
                self.assertNotEqual(before[kind], runner_semantics_changed[kind])

    def test_h_scoped_stage_keys_are_deterministic(self):
        for kind in ("residual_evidence", "independent_recurrence", "m8_homology"):
            definition = self.registry.get(kind)
            first = self._key(
                definition, kind,
                {"source_sha256": "same-package"},
                {"tool_version": "fixed"},
                {"input": {"sha256": "c" * 64, "artifact_type": "raw_fasta"}},
            )
            second = self._key(
                definition, kind,
                {"source_sha256": "same-package"},
                {"tool_version": "fixed"},
                {"input": {"sha256": "c" * 64, "artifact_type": "raw_fasta"}},
            )
            self.assertEqual(first, second, kind)

    def test_i_incompatible_m7_identity_manifest_is_rejected_without_rewriting_outputs(self):
        config = {
            "observations": [{
                "observation_id": "obs-failed",
                "m6_state": "failed",
                "upstream_status": "execution_failed",
                "upstream_reason": "M6 did not complete",
                "sample_id": "unknown",
                "study_id": None,
            }],
        }
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "m7"
            run_m7_stage({}, output, config)
            marker = output / "manifest.json"
            prior = json.loads(marker.read_text(encoding="utf-8"))
            prior["identity"]["schema"] = "m7-stage-identity-v1"
            marker.write_text(json.dumps(prior), encoding="utf-8")
            manifest_before = marker.read_bytes()
            outputs_before = {
                path.name: path.read_bytes()
                for path in output.iterdir()
                if path.is_file() and path.name != marker.name
            }

            with self.assertRaisesRegex(ValueError, "implementation changed"):
                run_m7_stage({}, output, config)

            self.assertEqual(marker.read_bytes(), manifest_before)
            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in output.iterdir()
                    if path.is_file() and path.name != marker.name
                },
                outputs_before,
            )

    def test_j_adding_an_unrelated_contract_does_not_change_existing_semantic_identity(self):
        types = {"m8_candidate_sequence_set", "m8_summary"}
        before = artifact_contracts.semantic_identity(types)
        with patch.dict(artifact_contracts._CONTRACTS, {"m9_probe_contract": "test"}):
            after = artifact_contracts.semantic_identity(types)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()