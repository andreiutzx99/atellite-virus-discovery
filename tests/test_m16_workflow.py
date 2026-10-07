import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from satellite_discovery import (
    artifact_contracts, m15_contracts, m16_contracts, m16_stage,
)
from satellite_discovery.artifact_workflow import (
    DEFAULT_STAGE_REGISTRY, inspect_configuration, run as run_workflow,
)


def _write(path, value, writer=m15_contracts.write_json):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    writer(path, value)
    return path


class M16WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="m16-workflow-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _authenticated_synthetic_producer_ref(self):
        producer_root = self.root / "synthetic-producer"
        stage_relative = "stage-runs/m14-fixture"
        stage_root = producer_root / stage_relative
        stage_root.mkdir(parents=True)
        artifact_name = "observations.json"
        artifact_path = stage_root / artifact_name
        # This authenticated software fixture intentionally has an invalid
        # M14 payload; M15 must retain that literal invalid state.
        _write(artifact_path, {
            "schema": "synthetic-fixture-not-an-m14-observation-table",
            "rows": [],
        })
        artifact_digest = m15_contracts.sha256_file(artifact_path)
        size_bytes = artifact_path.stat().st_size
        stage_identity = {
            "schema": "stage-identity-v1",
            "stage_id": "m14-fixture",
            "implementation_version": "m16-synthetic-producer-v1",
        }
        stage_manifest = {
            "schema": "synthetic-producer-stage-v1",
            "status": "complete",
            "identity": stage_identity,
            "output_sha256": {artifact_name: artifact_digest},
        }
        stage_manifest_path = _write(stage_root / "manifest.json", stage_manifest)
        stage_manifest_digest = m15_contracts.sha256_file(stage_manifest_path)
        workflow_id = "m16-synthetic-producer-workflow"
        descriptor = {
            "schema": "artifact-contract-v1",
            "artifact_type": "m14_observation_table",
            "contract_version": artifact_contracts.CONTRACT_VERSION,
            "producer_stage": "m14-fixture",
            "path": f"{stage_relative}/{artifact_name}",
            "sha256": artifact_digest,
            "size_bytes": size_bytes,
            "validation_state": "valid",
        }
        workflow = {
            "schema": "artifact-workflow-manifest-v2",
            "workflow_id": workflow_id,
            "status": "complete",
            "stages": [{
                "id": "m14-fixture",
                "kind": "m14_descriptive_observations",
                "status": "complete",
                "output_path": stage_relative,
                "stage_manifest_sha256": stage_manifest_digest,
                "stage_manifest_identity": stage_identity,
                "output_files": {
                    artifact_name: {
                        "sha256": artifact_digest,
                        "size_bytes": size_bytes,
                    },
                },
                "artifacts": {artifact_name: descriptor},
            }],
        }
        workflow_path = _write(producer_root / "workflow.json", workflow)
        workflow_digest = m15_contracts.sha256_file(workflow_path)
        reference = {
            "producer_milestone": "M14",
            "producer_stage_id": "m14-fixture",
            "producer_run_manifest_sha256": stage_manifest_digest,
            "producer_status": "complete",
            "artifact_type": "m14_observation_table",
            "artifact_contract_version": artifact_contracts.CONTRACT_VERSION,
            "relative_path": artifact_name,
            "sha256": artifact_digest,
            "provenance_mode": m15_contracts.AUTHENTICATED_PRODUCER_MODE,
            "producer_execution_ref": {
                "schema": "producer-execution-ref-v1",
                "producer_workflow_ref": {
                    "path": "workflow.json",
                    "sha256": workflow_digest,
                    "workflow_id": workflow_id,
                },
                "producer_stage_id": "m14-fixture",
                "producer_stage_kind": "m14_descriptive_observations",
                "producer_stage_manifest_sha256": stage_manifest_digest,
            },
            "producer_bundle_path": "synthetic-producer",
        }
        return reference, artifact_path

    def _run_actual_m15(self):
        reference, artifact_path = self._authenticated_synthetic_producer_ref()
        input_manifest = {
            "schema": m15_contracts.INPUT_SCHEMA,
            "candidate_id": "m16-synthetic-candidate",
            "artifact_refs": [reference],
            "optional_stage_states": {
                "M12": "NOT_SUPPLIED",
                "M13": "NOT_SUPPLIED",
                "M14": "PRESENT",
            },
        }
        _write(self.root / "m15-input.json", input_manifest)
        m15_spec = {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "m15-fixture",
                "kind": "m15_evidence_dossier",
                "inputs": {
                    "manifest": {
                        "path": "m15-input.json",
                        "artifact_type": "m15_input_manifest",
                    },
                    "artifact_0000": {
                        "path": artifact_path.relative_to(self.root).as_posix(),
                        "artifact_type": "m14_observation_table",
                    },
                },
            }],
        }
        _write(self.root / "m15-workflow.json", m15_spec)
        m15_output = self.root / "m15-output"
        run_workflow(self.root / "m15-workflow.json", m15_output)
        workflow = json.loads((m15_output / "workflow.json").read_text())
        stage = next(row for row in workflow["stages"] if row["id"] == "m15-fixture")
        self.assertEqual(stage["status"], "complete", stage.get("reason"))
        stage_output = m15_output / stage["output_path"]
        bundle_path = stage_output / "result_bundle.json"
        bundle = m15_contracts.read_json(bundle_path)
        envelope = m15_contracts.read_json(stage_output / "evidence_envelope.json")
        self.assertEqual(set(bundle["outputs"]), {
            "m15_evidence_envelope", "m15_dependency_edges", "m15_dossier_summary",
        })
        self.assertTrue(envelope["records"])
        return m15_output, workflow, stage, bundle, envelope, bundle_path

    def _make_m16_inputs(self, *, producer_workflow_crlf=False):
        m15_output, workflow, stage, bundle, envelope, bundle_path = (
            self._run_actual_m15()
        )
        if producer_workflow_crlf:
            producer_workflow_path = m15_output / "workflow.json"
            producer_workflow = producer_workflow_path.read_bytes()
            producer_workflow = producer_workflow.replace(b"\r\n", b"\n")
            producer_workflow_path.write_bytes(
                producer_workflow.replace(b"\n", b"\r\n")
            )
        descriptor = stage["artifacts"]["result_bundle.json"]
        execution_ref = {
            "schema": "producer-execution-ref-v1",
            "producer_workflow_ref": {
                "workflow_id": workflow["workflow_id"],
                "path": "workflow.json",
                "sha256": m15_contracts.sha256_file(m15_output / "workflow.json"),
            },
            "producer_stage_id": stage["id"],
            "producer_stage_kind": stage["kind"],
            "producer_stage_manifest_sha256": stage["stage_manifest_sha256"],
        }
        target_ref = {
            "schema": m16_contracts.TARGET_REF_SCHEMA,
            "producer_milestone": "M15",
            "producer_execution_ref": execution_ref,
            "bundle_root_ref": "m15-output",
            "artifact_type": "m15_result_bundle",
            "contract_version": descriptor["contract_version"],
            "semantic_version": bundle["semantic_version"],
            "artifact_path": descriptor["path"],
            "artifact_relative_path": "result_bundle.json",
            "artifact_sha256": descriptor["sha256"],
            "implementation": bundle["implementation"],
            "contract_semantics": bundle["contract_semantics"],
            "configuration": {},
        }
        evidence_id = envelope["records"][0]["evidence_id"]
        query = {
            "schema": m16_contracts.QUERY_SCHEMA,
            "evidence_ids": [evidence_id],
        }
        query_path = _write(
            self.root / "queries" / "item-a.json",
            query,
            writer=m16_contracts.write_json,
        )
        commitment = "custodian-supplied-fixture-commitment"
        public_manifest = {
            "schema": m16_contracts.PUBLIC_MANIFEST_SCHEMA,
            "dataset_kind": "SYNTHETIC_FIXTURE",
            "fixture_set_id": "m16-integration-fixture-set",
            "sealed_key_commitment": commitment,
            "target_ref": target_ref,
            "adapter_id": m16_stage.ADAPTER_ID,
            "adapter_version": m16_stage.ADAPTER_VERSION,
            "items": [{
                "item_id": "item-a",
                "target_input_ref": {
                    "path": query_path.relative_to(self.root).as_posix(),
                    "schema": m16_contracts.QUERY_SCHEMA,
                    "sha256": m16_contracts.semantic_sha256(
                        m16_contracts.validate_query(query)
                    ),
                },
                "group_ids": ["synthetic-group-a"],
                "split_role": "SYNTHETIC_HOLDOUT",
                "label_state": "SEALED_SYNTHETIC_EXPECTATION",
                "fixture_provenance": {
                    "schema": m16_contracts.FIXTURE_PROVENANCE_SCHEMA,
                    "scope": "SOFTWARE_CONTRACT",
                    "fixture_set_id": "m16-integration-fixture-set",
                },
            }],
        }
        public_path = _write(
            self.root / "m16-public.json",
            public_manifest,
            writer=m16_contracts.write_json,
        )
        query_context = m16_stage.build_stage_context({
            "public_manifest": public_path,
            "target_bundle": bundle_path,
        })
        self.assertEqual(
            query_context["target_status"],
            "AVAILABLE",
            query_context["target_error"],
        )
        expected = m16_stage._projection(
            query_context["target"], query["evidence_ids"]
        )
        key = {
            "schema": m16_contracts.SYNTHETIC_KEY_SCHEMA,
            "fixture_set_id": public_manifest["fixture_set_id"],
            "sealed_key_commitment": commitment,
            "items": [{
                "item_id": "item-a",
                "expected_software_outcome": expected,
                "label_scope": "SOFTWARE_CONTRACT",
            }],
        }
        key_path = _write(
            self.root / "sealed-key.json", key,
            writer=m16_contracts.write_json,
        )
        workflow_spec = {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "m16-fixture",
                "kind": m16_stage.STAGE_KIND,
                "inputs": {
                    "public_manifest": public_path.name,
                    "sealed_key": key_path.name,
                    "target_bundle": {
                        "path": bundle_path.relative_to(self.root).as_posix(),
                        "artifact_type": "m15_result_bundle",
                    },
                },
            }],
        }
        spec_path = _write(self.root / "m16-workflow.json", workflow_spec)
        return {
            "m15_output": m15_output,
            "m15_stage": stage,
            "bundle_path": bundle_path,
            "public_path": public_path,
            "key_path": key_path,
            "spec_path": spec_path,
            "public_manifest": public_manifest,
            "expected": expected,
        }

    def _run_m16(self, paths):
        output = self.root / "m16-output"
        run_workflow(paths["spec_path"], output)
        workflow = json.loads((output / "workflow.json").read_text())
        stage = next(row for row in workflow["stages"] if row["id"] == "m16-fixture")
        return output, workflow, stage

    @staticmethod
    def _tree_hashes(root):
        root = Path(root)
        return {
            path.relative_to(root).as_posix(): m15_contracts.sha256_file(path)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def test_actual_m15_output_and_all_companions_run_through_m16(self):
        paths = self._make_m16_inputs()
        preflight = inspect_configuration(paths["spec_path"])
        planned = preflight["stages"][0]
        self.assertEqual(planned["kind"], m16_stage.STAGE_KIND)
        self.assertEqual(planned["expected_action"], "execute")
        self.assertEqual(
            {
                name: value[0]
                for name, value in DEFAULT_STAGE_REGISTRY.get(
                    m16_stage.STAGE_KIND
                ).output_contracts.items()
            },
            m16_contracts.OUTPUT_CONTRACTS,
        )

        events = []
        original_read_regular_file = m16_contracts.read_regular_file
        original_commit_hook = m16_stage._after_prediction_commit

        def monitored_read(
            path, *, label="M16 input", maximum=m16_contracts.JSON_LIMIT
        ):
            if label == "M16 sealed synthetic key":
                events.append("key-opened")
            return original_read_regular_file(
                path, label=label, maximum=maximum
            )

        def committed(path):
            self.assertTrue(Path(path).is_file())
            events.append("predictions-committed")
            original_commit_hook(path)

        with (
            mock.patch.object(
                m16_contracts,
                "read_regular_file",
                side_effect=monitored_read,
            ),
            mock.patch.object(m16_stage, "_after_prediction_commit", side_effect=committed),
        ):
            output, workflow, stage = self._run_m16(paths)

        self.assertEqual(stage["status"], "complete", stage.get("reason"))
        self.assertEqual(events, ["predictions-committed", "key-opened"])
        stage_output = output / stage["output_path"]
        prediction = m16_contracts.read_json(stage_output / "predictions.json")
        leakage = m16_contracts.read_json(stage_output / "leakage_report.json")
        custody = m16_contracts.read_json(stage_output / "custody_log.json")
        metrics = m16_contracts.read_json(stage_output / "metric_summary.json")
        bundle = m16_contracts.read_json(stage_output / "result_bundle.json")
        self.assertEqual(prediction["rows"][0]["emitted_value"], paths["expected"])
        self.assertEqual(leakage["status"], "CLEAR")
        self.assertEqual(
            [event["to_state"] for event in custody["events"]],
            ["SEALED", "PREDICTIONS_COMMITTED", "BLINDED_CHECKED", "SCORED"],
        )
        self.assertEqual(metrics["n_exact_match"], 1)
        self.assertEqual(metrics["fixture_agreement_rate"], 1)
        self.assertEqual(bundle["target_identity"]["binding_sha256"],
                         prediction["target_provenance"]["binding_sha256"])
        self.assertEqual(set(bundle["outputs"]), set(m16_contracts.SIDE_CAR_CONTRACTS))
        self.assertNotIn("expected_software_outcome", json.dumps(prediction))
        for name, artifact_type in m16_contracts.OUTPUT_CONTRACTS.items():
            artifact_contracts.validate_artifact(stage_output / name, artifact_type)
        self.assertEqual(
            stage["inputs"]["sealed_key"]["validation_state"], "sealed_unread"
        )

    def test_windows_style_m15_workflow_newlines_are_accepted(self):
        paths = self._make_m16_inputs(producer_workflow_crlf=True)
        _output, _workflow, stage = self._run_m16(paths)
        self.assertEqual(stage["status"], "complete", stage.get("reason"))

    def test_commitment_mismatch_is_terminal_and_emits_no_metrics(self):
        paths = self._make_m16_inputs()
        key = m16_contracts.read_json(paths["key_path"])
        key["sealed_key_commitment"] = "different-opaque-commitment"
        m16_contracts.write_json(paths["key_path"], key)
        with self.assertRaises(m16_contracts.M16IntegrityError):
            self._run_m16(paths)
        output = self.root / "m16-output"
        workflow = json.loads((output / "workflow.json").read_text())
        stage = next(row for row in workflow["stages"] if row["id"] == "m16-fixture")
        self.assertEqual(stage["status"], "failed")
        stage_output = output / stage["output_path"]
        custody = m16_contracts.read_json(stage_output / "custody_log.json")
        self.assertEqual(custody["terminal_state"], "INTEGRITY_FAILED")
        self.assertFalse((stage_output / "metric_summary.json").exists())
        self.assertFalse((stage_output / "result_bundle.json").exists())
        self.assertEqual(
            [event["to_state"] for event in custody["events"]][-1],
            "INTEGRITY_FAILED",
        )

    def test_equivalent_json_formatting_reuses_the_same_m16_outputs(self):
        paths = self._make_m16_inputs()
        output, _workflow, first_stage = self._run_m16(paths)
        first_output = output / first_stage["output_path"]
        first_bytes = {
            name: (first_output / name).read_bytes()
            for name in m16_contracts.OUTPUT_CONTRACTS
        }
        m15_before = self._tree_hashes(paths["m15_output"])
        public = m16_contracts.read_json(paths["public_path"])
        query_path = (
            self.root / public["items"][0]["target_input_ref"]["path"]
        )
        query = m16_contracts.read_json(query_path)
        key = m16_contracts.read_json(paths["key_path"])
        for path, value in (
            (paths["public_path"], public),
            (query_path, query),
            (paths["key_path"], key),
        ):
            path.write_bytes(
                (json.dumps(value, indent=4, ensure_ascii=False) + "\n").encode(
                    "utf-8"
                )
            )
            self.assertNotIn(b"\r", path.read_bytes())

        output, _workflow, second_stage = self._run_m16(paths)
        second_output = output / second_stage["output_path"]
        self.assertEqual(second_stage["status"], "complete")
        self.assertEqual(second_stage["execution"], "verified_reuse")
        self.assertEqual(
            {
                name: (second_output / name).read_bytes()
                for name in m16_contracts.OUTPUT_CONTRACTS
            },
            first_bytes,
        )
        self.assertEqual(self._tree_hashes(paths["m15_output"]), m15_before)

    def test_scoring_identity_change_recomputes_m16_without_touching_m15(self):
        paths = self._make_m16_inputs()
        output, _workflow, first_stage = self._run_m16(paths)
        m15_before = self._tree_hashes(paths["m15_output"])
        original_cache_key = first_stage["cache_key"]
        key = m16_contracts.read_json(paths["key_path"])
        expected = key["items"][0]["expected_software_outcome"]
        expected["compatibility_warnings"].append(
            "synthetic scoring-identity probe"
        )
        m16_contracts.write_json(paths["key_path"], key)

        output, _workflow, second_stage = self._run_m16(paths)
        self.assertEqual(second_stage["status"], "complete")
        self.assertEqual(second_stage["cache_key"], original_cache_key)
        self.assertEqual(second_stage["execution"], "executed")
        stage_output = output / second_stage["output_path"]
        metrics = m16_contracts.read_json(stage_output / "metric_summary.json")
        self.assertEqual(metrics["n_exact_match"], 0)
        self.assertEqual(self._tree_hashes(paths["m15_output"]), m15_before)

    def test_tampered_cached_prediction_is_rejected_without_metrics(self):
        paths = self._make_m16_inputs()
        output, _workflow, first_stage = self._run_m16(paths)
        stage_output = output / first_stage["output_path"]
        with (stage_output / "predictions.json").open("ab") as stream:
            stream.write(b" ")
        with self.assertRaises(m16_contracts.M16IntegrityError):
            self._run_m16(paths)
        workflow = json.loads((output / "workflow.json").read_text())
        failed_stage = next(
            row for row in workflow["stages"] if row["id"] == "m16-fixture"
        )
        self.assertEqual(failed_stage["status"], "failed")
        stage_output = output / failed_stage["output_path"]
        self.assertFalse((stage_output / "metric_summary.json").exists())
        self.assertFalse((stage_output / "result_bundle.json").exists())
        custody = m16_contracts.read_json(stage_output / "custody_log.json")
        self.assertEqual(custody["terminal_state"], "INTEGRITY_FAILED")

    def test_coherently_rehashed_cache_is_replaced_by_fresh_predictions(self):
        paths = self._make_m16_inputs()
        output, _workflow, first_stage = self._run_m16(paths)
        stage_output = output / first_stage["output_path"]

        prediction_path = stage_output / "predictions.json"
        predictions = m16_contracts.read_json(prediction_path)
        predictions["rows"][0]["emitted_value"]["compatibility_warnings"].append(
            "coherently rehashed cache mutation"
        )
        m16_contracts.write_json(prediction_path, predictions)
        prediction_digest = m16_contracts.sha256_file(prediction_path)

        result_path = stage_output / "result_bundle.json"
        result_bundle = m16_contracts.read_json(result_path)
        result_bundle["prediction_sha256"] = prediction_digest
        result_bundle["scoring_identity"][
            "committed_prediction_sha256"
        ] = prediction_digest
        result_bundle["outputs"]["predictions.json"]["sha256"] = (
            prediction_digest
        )
        m16_contracts.write_json(result_path, result_bundle)

        manifest_path = stage_output / "manifest.json"
        manifest = m16_contracts.read_json(manifest_path)
        manifest["output_sha256"] = {
            name: m16_contracts.sha256_file(stage_output / name)
            for name in m16_contracts.OUTPUT_CONTRACTS
        }
        m16_contracts.write_json(manifest_path, manifest)
        self.assertTrue(m16_stage._existing_output_is_valid(stage_output))

        output, _workflow, second_stage = self._run_m16(paths)
        second_output = output / second_stage["output_path"]
        restored_predictions = m16_contracts.read_json(
            second_output / "predictions.json"
        )
        self.assertEqual(second_stage["status"], "complete")
        self.assertEqual(second_stage["execution"], "executed")
        self.assertEqual(
            restored_predictions["rows"][0]["emitted_value"], paths["expected"]
        )
        self.assertNotIn(
            "coherently rehashed cache mutation",
            restored_predictions["rows"][0]["emitted_value"][
                "compatibility_warnings"
            ],
        )
        metrics = m16_contracts.read_json(
            second_output / "metric_summary.json"
        )
        self.assertEqual(metrics["n_exact_match"], 1)

    def test_bundle_root_swap_after_validation_is_rejected_before_scoring(self):
        paths = self._make_m16_inputs()
        bundle_root = paths["m15_output"]
        backup_root = self.root / "m15-output-original"
        external_copy = self.root / "m15-output-external"
        shutil.copytree(bundle_root, external_copy)
        symlink_probe = self.root / ".m16-directory-link-probe"
        try:
            os.symlink(external_copy, symlink_probe, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(
                f"directory symlink/junction creation is unavailable: {error}"
            )
        else:
            symlink_probe.unlink()
        original_resolver = m16_contracts.resolve_relative_path
        swapped = False

        def validate_then_swap(root, value, label, **kwargs):
            nonlocal swapped
            result = original_resolver(root, value, label, **kwargs)
            if label == "M16 bundle_root_ref" and not swapped:
                os.replace(bundle_root, backup_root)
                try:
                    os.symlink(
                        external_copy, bundle_root, target_is_directory=True
                    )
                except (NotImplementedError, OSError) as error:
                    os.replace(backup_root, bundle_root)
                    raise unittest.SkipTest(
                        f"directory symlink/junction creation is unavailable: {error}"
                    ) from error
                swapped = True
            return result

        try:
            with mock.patch.object(
                m16_contracts,
                "resolve_relative_path",
                side_effect=validate_then_swap,
            ):
                with self.assertRaises(m16_contracts.M16IntegrityError):
                    self._run_m16(paths)
        finally:
            if bundle_root.is_symlink():
                bundle_root.unlink()
            if backup_root.exists():
                os.replace(backup_root, bundle_root)
            shutil.rmtree(external_copy, ignore_errors=True)

        self.assertTrue(swapped)
        self.assertEqual(
            list((self.root / "m16-output").rglob("metric_summary.json")), []
        )

    def test_query_path_swap_after_validation_never_loads_external_query(self):
        paths = self._make_m16_inputs()
        query_relative_path = paths["public_manifest"]["items"][0][
            "target_input_ref"
        ]["path"]
        query_path = self.root / query_relative_path
        backup_path = self.root / "validated-query-original.json"
        external_path = self.root / "external-query.json"
        m16_contracts.write_json(external_path, {
            "schema": m16_contracts.QUERY_SCHEMA,
            "evidence_ids": ["external-evidence"],
        })
        symlink_probe = self.root / ".m16-file-link-probe"
        try:
            os.symlink(external_path, symlink_probe)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"file symlink creation is unavailable: {error}")
        else:
            symlink_probe.unlink()
        original_resolver = m16_contracts.resolve_relative_path
        swapped = False

        def validate_then_swap(root, value, label, **kwargs):
            nonlocal swapped
            result = original_resolver(root, value, label, **kwargs)
            if label == "target input for item-a" and not swapped:
                os.replace(query_path, backup_path)
                try:
                    os.symlink(external_path, query_path)
                except (NotImplementedError, OSError) as error:
                    os.replace(backup_path, query_path)
                    raise unittest.SkipTest(
                        f"file symlink creation is unavailable: {error}"
                    ) from error
                swapped = True
            return result

        try:
            with mock.patch.object(
                m16_contracts,
                "resolve_relative_path",
                side_effect=validate_then_swap,
            ):
                context = m16_stage.build_stage_context({
                    "public_manifest": paths["public_path"],
                    "target_bundle": paths["bundle_path"],
                })
        finally:
            if query_path.is_symlink():
                query_path.unlink()
            if backup_path.exists():
                os.replace(backup_path, query_path)
            external_path.unlink(missing_ok=True)

        self.assertTrue(swapped)
        query_record = context["query_inputs"]["item-a"]
        self.assertEqual(query_record["status"], "INVALID_INPUT")
        self.assertEqual(query_record["reason_code"], "QUERY_PATH_UNSAFE")
        self.assertIsNone(query_record["query"])
        self.assertEqual(context["target_status"], "AVAILABLE")

    def test_sealed_key_path_swap_is_rejected_after_prediction_commit(self):
        paths = self._make_m16_inputs()
        key_path = paths["key_path"]
        backup_path = self.root / "sealed-key-original.json"
        external_path = self.root / "external-sealed-key.json"
        shutil.copyfile(key_path, external_path)
        symlink_probe = self.root / ".m16-key-link-probe"
        try:
            os.symlink(external_path, symlink_probe)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"file symlink creation is unavailable: {error}")
        else:
            symlink_probe.unlink()
        events = []
        key_swapped = False
        original_reader = m16_contracts.read_regular_file
        original_commit_hook = m16_stage._after_prediction_commit

        def committed(path):
            events.append("predictions-committed")
            original_commit_hook(path)

        def swap_then_read(path, *, label="M16 input", maximum=m16_contracts.JSON_LIMIT):
            nonlocal key_swapped
            if label == "M16 sealed synthetic key":
                events.append("sealed-key-open-attempt")
                os.replace(key_path, backup_path)
                try:
                    os.symlink(external_path, key_path)
                except (NotImplementedError, OSError) as error:
                    os.replace(backup_path, key_path)
                    raise unittest.SkipTest(
                        f"file symlink creation is unavailable: {error}"
                    ) from error
                key_swapped = True
            return original_reader(path, label=label, maximum=maximum)

        try:
            with (
                mock.patch.object(
                    m16_contracts,
                    "read_regular_file",
                    side_effect=swap_then_read,
                ),
                mock.patch.object(
                    m16_stage,
                    "_after_prediction_commit",
                    side_effect=committed,
                ),
                self.assertRaises(m16_contracts.M16IntegrityError),
            ):
                self._run_m16(paths)
        finally:
            if key_path.is_symlink():
                key_path.unlink()
            if backup_path.exists():
                os.replace(backup_path, key_path)
            external_path.unlink(missing_ok=True)

        self.assertEqual(
            events, ["predictions-committed", "sealed-key-open-attempt"]
        )
        self.assertTrue(key_swapped)
        output = self.root / "m16-output"
        workflow = json.loads((output / "workflow.json").read_text())
        failed_stage = next(
            row for row in workflow["stages"] if row["id"] == "m16-fixture"
        )
        stage_output = output / failed_stage["output_path"]
        custody = m16_contracts.read_json(stage_output / "custody_log.json")
        self.assertEqual(custody["terminal_state"], "INTEGRITY_FAILED")
        self.assertFalse((stage_output / "metric_summary.json").exists())
        self.assertFalse((stage_output / "result_bundle.json").exists())

    def test_windows_file_identity_fallback_rejects_substituted_handle(self):
        validated_path = self.root / "validated-input.json"
        external_path = self.root / "external-input.json"
        validated_path.write_bytes(b'{"source":"in-root"}')
        external_path.write_bytes(b'{"source":"outside"}')
        original_open = os.open

        def substitute_open(path, flags, *args, **kwargs):
            if Path(path) == validated_path:
                return original_open(external_path, flags, *args, **kwargs)
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(
            m16_contracts.os, "open", side_effect=substitute_open
        ):
            with self.assertRaises(m16_contracts.M16PathSecurityError):
                m16_contracts._open_windows_regular_file(
                    validated_path, "test input"
                )

    def test_interruption_after_prediction_commit_leaves_no_scored_artifact(self):
        paths = self._make_m16_inputs()
        output = self.root / "m16-output"
        with (
            mock.patch.object(
                m16_stage,
                "_after_prediction_commit",
                side_effect=KeyboardInterrupt,
            ),
            self.assertRaises(KeyboardInterrupt),
        ):
            self._run_m16(paths)

        workflow = json.loads((output / "workflow.json").read_text())
        stage = next(row for row in workflow["stages"] if row["id"] == "m16-fixture")
        self.assertEqual(stage["status"], "interrupted")
        self.assertEqual(list(output.rglob("predictions.json")), [])
        self.assertEqual(list(output.rglob("metric_summary.json")), [])
        self.assertEqual(list(output.rglob(".m16-stage-*")), [])

    def test_leaking_transitive_group_blocks_scoring(self):
        items = [
            {"item_id": "a", "group_ids": ["g1"], "split_role": "DEVELOPMENT"},
            {"item_id": "b", "group_ids": ["g1", "g2"], "split_role": "TUNING"},
            {"item_id": "c", "group_ids": ["g2"], "split_role": "TUNING"},
        ]
        report = m16_stage._leakage_report(items)
        self.assertEqual(report["status"], "LEAKAGE_DETECTED")
        self.assertTrue(report["scoring_blocked"])
        self.assertEqual(report["offending_item_ids"], ["a", "b", "c"])
        self.assertEqual(report["transitive_components"][0]["item_ids"], ["a", "b", "c"])
        m16_contracts.validate_leakage_report(report)


if __name__ == "__main__":
    unittest.main()
