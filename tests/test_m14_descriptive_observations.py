import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import artifact_contracts, artifact_workflow
from satellite_discovery import m14_descriptive_observations as m14


def _source_outcomes():
    return [
        {
            "source_id": source_id,
            "source_kind": source_kind,
            "source_state": "NOT_SUPPLIED",
            "workflow_ref": None,
            "producer_stage": None,
            "artifact_refs": [],
            "artifact_attempts": [],
            "producer_result_status": None,
            "producer_completeness": "NOT_REPORTED",
            "reason_code": "NOT_SUPPLIED",
        }
        for source_id, source_kind in (
            ("m4-catalogue-none", "M4_CATALOGUE_OBSERVATIONS"),
            ("m4-observations-none", "M4_OBSERVATIONS"),
            ("m7-recurrence-none", "M7_INDEPENDENT_RECURRENCE"),
        )
    ]


def _method(scope="synthetic-assay"):
    return {
        "method_id": "declared-method",
        "method_version": "1",
        "scope_id": scope,
        "scope_description": "Synthetic fixture scope only",
        "provenance_ref": "synthetic-method-record",
    }


def _observation(unit_id, observation_id, candidate_state="PRESENT",
                 helper_state="PRESENT", *, source_refs=None):
    return {
        "observation_id": observation_id,
        "candidate_id": "candidate-A",
        "helper_id": "helper-A",
        "unit_id": unit_id,
        "candidate_state": candidate_state,
        "helper_state": helper_state,
        "candidate_state_reason": None,
        "helper_state_reason": None,
        "candidate_tested": True,
        "helper_tested": True,
        "candidate_method_ref": _method(),
        "helper_method_ref": _method(),
        "candidate_detection_limit": {
            "metric": "reads", "value": 1.0, "unit": "count", "basis": "synthetic",
        },
        "helper_detection_limit": None,
        "source_refs": list(source_refs or []),
    }


def _manifest(unit_ids=("u1", "u2", "u3", "u4")):
    units = [
        {
            "unit_id": unit_id,
            "unit_type": "SAMPLE",
            "unit_type_label": None,
            "parent_unit_ids": [],
            "study_id": None,
            "independence_state": "UNVERIFIED",
            "independence_ref": None,
            "control_role": None,
            "source_refs": [],
        }
        for unit_id in unit_ids
    ]
    states = (
        ("PRESENT", "PRESENT"),
        ("PRESENT", "NOT_DETECTED_WITHIN_SCOPE"),
        ("NOT_DETECTED_WITHIN_SCOPE", "PRESENT"),
        ("NOT_DETECTED_WITHIN_SCOPE", "NOT_DETECTED_WITHIN_SCOPE"),
    )
    observations = [
        _observation(unit_id, f"obs-{index}", *states[index % len(states)])
        for index, unit_id in enumerate(unit_ids)
    ]
    return {
        "schema": "m14-input-v1",
        "dataset_id": "synthetic-m14-fixture",
        "source_artifacts": [],
        "source_outcomes": _source_outcomes(),
        "sampling_units": units,
        "evaluated_pairs": [{
            "candidate_id": "candidate-A",
            "helper_id": "helper-A",
            "unit_ids": sorted(unit_ids),
        }],
        "observations": observations,
        "analysis_profile": None,
    }


def _execute(config, output):
    return m14.run_stage({}, output, config)


class M14DescriptiveObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m14-descriptive-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _run(self, config, label="run"):
        output = self.root / label
        _execute(config, output)
        summary = json.loads((output / "descriptive_summary.json").read_text())
        bundle = json.loads((output / "result_bundle.json").read_text())
        observations = json.loads((output / "observations.json").read_text())
        return output, summary, bundle, observations

    def _attach_source(self, config, source_kind, source_id, artifact_id,
                       artifact_type, artifact_document=None):
        spec = m14.SOURCE_SPECS[source_kind]
        producer = self.root / f"producer-{source_id}"
        output_root = producer / "output"
        stage_output = output_root / "stage"
        stage_output.mkdir(parents=True)
        relative_path = "summary.json"
        inventory = {}
        content_digest = "a" * 64
        if artifact_document is not None:
            artifact_bytes = m14._canonical_json_bytes(
                artifact_document, trailing_newline=True
            )
            (stage_output / relative_path).write_bytes(artifact_bytes)
            content_digest = hashlib.sha256(artifact_bytes).hexdigest()
            inventory[relative_path] = content_digest
        stage_manifest = {
            "schema": "producer-stage-manifest-v1",
            "status": "complete",
            "output_sha256": inventory,
        }
        manifest_bytes = m14._canonical_json_bytes(
            stage_manifest, trailing_newline=True
        )
        (stage_output / "manifest.json").write_bytes(manifest_bytes)
        stage_digest = hashlib.sha256(manifest_bytes).hexdigest()
        workflow_id = f"workflow-{source_id}"
        workflow = {
            "schema": "artifact-workflow-manifest-v2",
            "workflow_id": workflow_id,
            "output": str(output_root),
            "stages": [{
                "id": "producer-stage",
                "kind": spec["stage_kind"],
                "status": "complete",
                "output_path": "stage",
            }],
        }
        (producer / "workflow.json").write_text(
            json.dumps(workflow), encoding="utf-8"
        )
        ref = {
            "artifact_id": artifact_id,
            "source_id": source_id,
            "producer_milestone": spec["milestone"],
            "producer_stage_kind": spec["stage_kind"],
            "producer_stage_id": "producer-stage",
            "producer_workflow_id": workflow_id,
            "producer_run_manifest_sha256": stage_digest,
            "artifact_type": artifact_type,
            "contract_version": artifact_contracts.CONTRACT_VERSION,
            "relative_path": relative_path,
            "content_sha256": content_digest,
            "raw_producer_status": "complete",
        }
        outcome = {
            "source_id": source_id,
            "source_kind": source_kind,
            "source_state": "AVAILABLE",
            "workflow_ref": {
                "relative_path": f"producer-{source_id}/workflow.json",
                "workflow_id": workflow_id,
            },
            "producer_stage": {
                "stage_id": "producer-stage",
                "stage_kind": spec["stage_kind"],
                "raw_status": "complete",
                "manifest_sha256": stage_digest,
            },
            "artifact_refs": [artifact_id],
            "artifact_attempts": [],
            "producer_result_status": None,
            "producer_completeness": "NOT_REPORTED",
            "reason_code": None,
        }
        config["source_artifacts"].append(ref)
        outcome_index = next(
            index for index, row in enumerate(config["source_outcomes"])
            if row["source_kind"] == source_kind
        )
        config["source_outcomes"][outcome_index] = outcome
        return ref, outcome

    def test_four_synthetic_combinations_have_exact_cells(self):
        _, summary, bundle, _ = self._run(_manifest())

        self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
        self.assertEqual(summary["n_jointly_tested"], 4)
        self.assertEqual(summary["n_unique_units"], 4)
        self.assertEqual(summary["cells"], {
            "both_present": 1,
            "candidate_present_helper_not_detected": 1,
            "candidate_not_detected_helper_present": 1,
            "both_not_detected": 1,
        })
        self.assertFalse(bundle["claim_boundary"]["helper_dependence_assessed"])
        self.assertFalse(bundle["claim_boundary"]["independence_inferred"])

    def test_unscoped_negative_is_rejected_instead_of_counted(self):
        config = _manifest(("u1",))
        row = config["observations"][0]
        row["helper_state"] = "NOT_DETECTED_WITHIN_SCOPE"
        row["helper_tested"] = False
        row["helper_method_ref"] = None
        _, summary, bundle, output = self._run(config)

        self.assertEqual(bundle["result_state"], "INVALID_INPUT")
        self.assertEqual(summary["n_jointly_tested"], 0)
        self.assertEqual(output["observations"], [])
        self.assertTrue(output["rejected_observations"])

    def test_malformed_row_values_are_typed_input_errors_not_runtime_failures(self):
        config = _manifest(("u1",))
        config["observations"][0]["candidate_id"] = []
        config["observations"][0]["candidate_state"] = []

        _, _, bundle, output = self._run(config)

        self.assertEqual(bundle["result_state"], "INVALID_INPUT")
        self.assertFalse(output["observations"])
        self.assertTrue(output["rejected_observations"])

    def test_malformed_pair_identity_is_typed_input_error(self):
        config = _manifest(("u1",))
        config["evaluated_pairs"][0]["candidate_id"] = []

        _, _, bundle, _ = self._run(config)

        self.assertEqual(bundle["result_state"], "INVALID_INPUT")

    def test_missing_frame_row_is_incomplete_not_negative(self):
        config = _manifest(("u1", "u2"))
        config["observations"] = config["observations"][:1]
        _, summary, bundle, observations = self._run(config)

        self.assertEqual(bundle["result_state"], "INCOMPLETE")
        self.assertFalse(bundle["frame_complete"])
        self.assertEqual(summary["n_jointly_tested"], 1)
        self.assertEqual(observations["missing_pair_units"], [{
            "candidate_id": "candidate-A", "helper_id": "helper-A", "unit_id": "u2",
        }])

    def test_empty_scope_is_not_evaluated(self):
        config = _manifest(())
        _, summary, bundle, _ = self._run(config)

        self.assertEqual(bundle["result_state"], "NOT_EVALUATED")
        self.assertEqual(summary["n_jointly_tested"], 0)
        self.assertEqual(summary["denominator_scope"]["n_declared_pair_unit_rows"], 0)

    def test_complete_nonempty_frame_without_joint_evidence_is_insufficient(self):
        config = _manifest(("u1",))
        row = config["observations"][0]
        row["candidate_state"] = "UNKNOWN"
        row["candidate_state_reason"] = "synthetic state is unknown"
        row["candidate_tested"] = False
        row["candidate_method_ref"] = None
        _, summary, bundle, _ = self._run(config)

        self.assertEqual(bundle["result_state"], "INSUFFICIENT_MATCHED_EVIDENCE")
        self.assertEqual(summary["n_jointly_tested"], 0)
        self.assertEqual(summary["n_unknown_or_unavailable"], 1)

    def test_conflicting_evidence_is_retained_but_excluded(self):
        config = _manifest(("u1",))
        row = config["observations"][0]
        row["candidate_state"] = "CONFLICTING"
        row["candidate_state_reason"] = "two synthetic records disagree"
        row["candidate_tested"] = False
        row["candidate_method_ref"] = None
        row["source_refs"] = ["record-a", "record-b"]
        _, summary, bundle, output = self._run(config)

        self.assertEqual(bundle["result_state"], "INSUFFICIENT_MATCHED_EVIDENCE")
        self.assertEqual(summary["n_conflicting"], 1)
        self.assertEqual(summary["n_jointly_tested"], 0)
        self.assertEqual(output["observations"][0]["candidate_state"], "CONFLICTING")

    def test_input_permutations_and_equivalent_decimal_tokens_are_canonical(self):
        first = _manifest()
        second = copy.deepcopy(first)
        second["source_outcomes"].reverse()
        second["sampling_units"].reverse()
        second["evaluated_pairs"].reverse()
        second["observations"].reverse()
        second["observations"][0]["candidate_detection_limit"]["value"] = 1

        first_output, _, first_bundle, _ = self._run(first, "canonical-a")
        second_output, _, second_bundle, _ = self._run(second, "canonical-b")

        self.assertEqual(
            first_bundle["m14_semantic_input_sha256"],
            second_bundle["m14_semantic_input_sha256"],
        )
        for filename in (*m14.OUTPUT_CONTRACTS, "manifest.json"):
            self.assertEqual(
                (first_output / filename).read_bytes(),
                (second_output / filename).read_bytes(),
            )

    def test_optional_invalid_source_does_not_block_independent_rows(self):
        config = _manifest(("u1", "u2"))
        self._attach_source(
            config, "M4_CATALOGUE_OBSERVATIONS", "m4-catalogue-run",
            "unsupported-artifact", "unsupported_m4_type",
        )

        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            _, summary, bundle, _ = self._run(config, "optional-source-independent")
            config_with_bad_row_ref = copy.deepcopy(config)
            config_with_bad_row_ref["observations"][1]["source_refs"] = [
                "unsupported-artifact",
            ]
            _, partial_summary, partial_bundle, output = self._run(
                config_with_bad_row_ref, "optional-source-row-ref"
            )
        finally:
            os.chdir(original_cwd)

        self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
        self.assertEqual(summary["n_jointly_tested"], 2)
        self.assertEqual(bundle["source_outcomes"][0]["source_state"], "INVALID")
        self.assertEqual(
            bundle["source_outcomes"][0]["reason_code"], "UNSUPPORTED_PRODUCER_TYPE"
        )
        self.assertEqual(partial_bundle["result_state"], "INCOMPLETE")
        self.assertEqual(partial_summary["n_jointly_tested"], 1)
        self.assertEqual(len(output["rejected_observations"]), 1)

    def test_valid_m4_and_m7_sources_preserve_native_status_and_completeness(self):
        config = _manifest(("u1",))
        self._attach_source(
            config,
            "M4_CATALOGUE_OBSERVATIONS",
            "synthetic-m4-run",
            "m4-occurrence-summary",
            "occurrence_summary",
            {
                "schema": "synthetic-occurrence-summary-v1",
                "status": "NO_OCCURRENCES_DETECTED",
                "producer_completeness": "PARTIAL",
            },
        )
        self._attach_source(
            config,
            "M7_INDEPENDENT_RECURRENCE",
            "synthetic-m7-run",
            "m7-independence-summary",
            "m7_independence_summary",
            {
                "schema": "m7-independence-summary-v1",
                "analysis_completeness": "PARTIAL",
                "result_status": "UPSTREAM_UNAVAILABLE_OR_FAILED",
                "observation_count": 1,
                "supported_sequence_observation_count": 0,
                "exact_group_count": 0,
                "recurrent_group_count": 0,
                "limitations": ["Synthetic partial-accounting fixture"],
                "m6_evidence_class_counts": {},
            },
        )
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            _, summary, bundle, _ = self._run(config)
        finally:
            os.chdir(original_cwd)

        sources = {row["source_kind"]: row for row in bundle["source_outcomes"]}
        self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
        self.assertEqual(summary["n_jointly_tested"], 1)
        self.assertEqual(
            sources["M4_CATALOGUE_OBSERVATIONS"]["producer_result_status"],
            "NO_OCCURRENCES_DETECTED",
        )
        self.assertEqual(
            sources["M4_CATALOGUE_OBSERVATIONS"]["producer_completeness"],
            "PARTIAL",
        )
        self.assertEqual(
            sources["M7_INDEPENDENT_RECURRENCE"]["producer_result_status"],
            "UPSTREAM_UNAVAILABLE_OR_FAILED",
        )
        self.assertEqual(
            sources["M7_INDEPENDENT_RECURRENCE"]["producer_completeness"],
            "PARTIAL",
        )

    def test_missing_workflow_is_unavailable_not_a_caller_frame_failure(self):
        config = _manifest(("u1",))
        _, outcome = self._attach_source(
            config, "M4_CATALOGUE_OBSERVATIONS", "m4-missing-workflow",
            "missing-workflow-artifact", "occurrence_summary",
            {"schema": "synthetic-occurrence-summary-v1"},
        )
        (self.root / "producer-m4-missing-workflow" / "workflow.json").unlink()
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            _, summary, bundle, _ = self._run(config)
        finally:
            os.chdir(original_cwd)

        resolved = next(
            row for row in bundle["source_outcomes"]
            if row["source_id"] == outcome["source_id"]
        )
        self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
        self.assertEqual(summary["n_jointly_tested"], 1)
        self.assertEqual(resolved["source_state"], "UNAVAILABLE")
        self.assertEqual(resolved["reason_code"], "WORKFLOW_UNAVAILABLE")

    def test_mismatched_expected_raw_status_invalidates_only_that_source(self):
        config = _manifest(("u1",))
        _, outcome = self._attach_source(
            config, "M4_CATALOGUE_OBSERVATIONS", "m4-status-mismatch",
            "status-mismatch-artifact", "occurrence_summary",
            {"schema": "synthetic-occurrence-summary-v1"},
        )
        outcome["producer_stage"]["raw_status"] = "failed"
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            _, summary, bundle, _ = self._run(config)
        finally:
            os.chdir(original_cwd)

        resolved = next(
            row for row in bundle["source_outcomes"]
            if row["source_id"] == outcome["source_id"]
        )
        self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
        self.assertEqual(summary["n_jointly_tested"], 1)
        self.assertEqual(resolved["source_state"], "INVALID")
        self.assertEqual(resolved["reason_code"], "SOURCE_OUTCOME_INVALID")

    def test_missing_completed_stage_manifest_is_integrity_failure(self):
        config = _manifest(("u1",))
        ref, outcome = self._attach_source(
            config, "M4_CATALOGUE_OBSERVATIONS", "m4-missing-stage-manifest",
            "missing-stage-manifest-artifact", "occurrence_summary",
            {"schema": "synthetic-occurrence-summary-v1"},
        )
        (self.root / "producer-m4-missing-stage-manifest" / "output" / "stage"
         / "manifest.json").unlink()
        outcome["producer_stage"]["manifest_sha256"] = None
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            _, summary, bundle, _ = self._run(config)
        finally:
            os.chdir(original_cwd)

        resolved = next(
            row for row in bundle["source_outcomes"]
            if row["source_id"] == outcome["source_id"]
        )
        self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
        self.assertEqual(summary["n_jointly_tested"], 1)
        self.assertEqual(resolved["source_state"], "INVALID")
        self.assertEqual(resolved["reason_code"], "ARTIFACT_INTEGRITY_FAILED")
        self.assertEqual(ref["artifact_id"], "missing-stage-manifest-artifact")

    def test_missing_artifact_inventory_is_invalid_but_absent_entry_is_unavailable(self):
        config = _manifest(("u1",))
        ref, outcome = self._attach_source(
            config, "M4_CATALOGUE_OBSERVATIONS", "m4-inventory-missing",
            "inventory-missing-artifact", "occurrence_summary",
            {"schema": "synthetic-occurrence-summary-v1"},
        )
        stage_dir = (
            self.root / "producer-m4-inventory-missing" / "output" / "stage"
        )
        manifest_path = stage_dir / "manifest.json"
        raw = m14._canonical_json_bytes(
            {"schema": "producer-stage-manifest-v1", "status": "complete"},
            trailing_newline=True,
        )
        manifest_path.write_bytes(raw)
        stage_digest = hashlib.sha256(raw).hexdigest()
        outcome["producer_stage"]["manifest_sha256"] = stage_digest
        ref["producer_run_manifest_sha256"] = stage_digest
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            _, _, bundle, _ = self._run(config, "inventory-absent")
        finally:
            os.chdir(original_cwd)
        resolved = next(
            row for row in bundle["source_outcomes"]
            if row["source_id"] == outcome["source_id"]
        )
        self.assertEqual(resolved["source_state"], "INVALID")
        self.assertEqual(resolved["reason_code"], "ARTIFACT_SCHEMA_INVALID")

        config = _manifest(("u1",))
        ref, outcome = self._attach_source(
            config, "M4_CATALOGUE_OBSERVATIONS", "m4-inventory-entry-absent",
            "inventory-entry-absent-artifact", "occurrence_summary",
            {"schema": "synthetic-occurrence-summary-v1"},
        )
        stage_dir = (
            self.root / "producer-m4-inventory-entry-absent" / "output" / "stage"
        )
        manifest_path = stage_dir / "manifest.json"
        raw = m14._canonical_json_bytes(
            {
                "schema": "producer-stage-manifest-v1",
                "status": "complete",
                "output_sha256": {},
            },
            trailing_newline=True,
        )
        manifest_path.write_bytes(raw)
        stage_digest = hashlib.sha256(raw).hexdigest()
        outcome["producer_stage"]["manifest_sha256"] = stage_digest
        ref["producer_run_manifest_sha256"] = stage_digest
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            _, _, bundle, _ = self._run(config, "inventory-item-absent")
        finally:
            os.chdir(original_cwd)
        resolved = next(
            row for row in bundle["source_outcomes"]
            if row["source_id"] == outcome["source_id"]
        )
        self.assertEqual(resolved["source_state"], "UNAVAILABLE")
        self.assertEqual(resolved["reason_code"], "ARTIFACT_UNAVAILABLE")

    def test_malformed_optional_artifact_path_isolated_from_valid_rows(self):
        config = _manifest(("u1",))
        ref, outcome = self._attach_source(
            config, "M4_CATALOGUE_OBSERVATIONS", "m4-bad-artifact-path",
            "bad-artifact-path", "occurrence_summary",
            {"schema": "synthetic-occurrence-summary-v1"},
        )
        ref["relative_path"] = ["not", "a", "path"]
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            _, summary, bundle, _ = self._run(config)
        finally:
            os.chdir(original_cwd)

        resolved = next(
            row for row in bundle["source_outcomes"]
            if row["source_id"] == outcome["source_id"]
        )
        self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
        self.assertEqual(summary["n_jointly_tested"], 1)
        self.assertEqual(resolved["source_state"], "INVALID")
        self.assertEqual(resolved["reason_code"], "ARTIFACT_PATH_UNSAFE")

    def test_declared_skipped_m1_stage_is_retained_as_not_run(self):
        config = _manifest(("u1",))
        producer = self.root / "producer"
        producer.mkdir()
        workflow = {
            "schema": "artifact-workflow-manifest-v2",
            "workflow_id": "synthetic-skipped-run",
            "output": str(producer / "missing-output"),
            "stages": [{
                "id": "catalogue-stage",
                "kind": "catalogue_observations",
                "status": "skipped",
            }],
        }
        (producer / "workflow.json").write_text(json.dumps(workflow), encoding="utf-8")
        config["source_outcomes"][0].update(
            source_id="m4-catalogue-skipped",
            source_state="NOT_RUN",
            workflow_ref={
                "relative_path": "producer/workflow.json",
                "workflow_id": "synthetic-skipped-run",
            },
            producer_stage={
                "stage_id": "catalogue-stage",
                "stage_kind": "catalogue_observations",
                "raw_status": "skipped",
                "manifest_sha256": None,
            },
            reason_code="PRODUCER_NOT_RUN",
        )
        original_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            _, _, bundle, _ = self._run(config)
        finally:
            os.chdir(original_cwd)

        self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
        self.assertEqual(bundle["source_outcomes"][0]["source_state"], "NOT_RUN")
        self.assertEqual(bundle["source_outcomes"][0]["producer_stage"]["raw_status"], "skipped")

    def test_missing_required_source_family_invalidates_manifest(self):
        config = _manifest(("u1",))
        config["source_outcomes"] = config["source_outcomes"][:-1]

        _, _, bundle, _ = self._run(config)

        self.assertEqual(bundle["result_state"], "INVALID_INPUT")

    def test_m14_implementation_identity_is_scoped_to_its_stage(self):
        registry = artifact_workflow.build_default_registry()
        m14_definition = registry.get(m14.STAGE_KIND)
        m13_definition = registry.get("m13_m5_evidence_matrix")
        runtime = {"source_sha256": "unchanged-package-baseline"}
        dependency = {"status": "available"}
        with patch.object(m14, "_implementation_sha256", side_effect=["1" * 64, "2" * 64]):
            m14_first = artifact_workflow._stage_cache_key(
                {"id": "describe", "kind": m14.STAGE_KIND}, m14_definition,
                {}, {}, runtime, dependency,
            )
            m14_second = artifact_workflow._stage_cache_key(
                {"id": "describe", "kind": m14.STAGE_KIND}, m14_definition,
                {}, {}, runtime, dependency,
            )
        m13_first = artifact_workflow._stage_cache_key(
            {"id": "m13", "kind": "m13_m5_evidence_matrix"}, m13_definition,
            {}, {}, runtime, None,
        )
        m13_second = artifact_workflow._stage_cache_key(
            {"id": "m13", "kind": "m13_m5_evidence_matrix"}, m13_definition,
            {}, {}, runtime, None,
        )

        self.assertNotEqual(m14_first, m14_second)
        self.assertEqual(m13_first, m13_second)

    def test_m14_source_hash_normalizes_crlf(self):
        source = Path(m14.__file__).read_bytes()
        crlf_source = source.replace(b"\n", b"\r\n")
        expected = hashlib.sha256(source.replace(b"\r\n", b"\n")).hexdigest()
        with patch.object(Path, "read_bytes", return_value=crlf_source):
            self.assertEqual(m14._implementation_sha256(), expected)

    def test_m14_stage_is_registered_and_runs_through_m1(self):
        config = _manifest(("u1",))
        specification = {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "describe",
                "kind": m14.STAGE_KIND,
                "inputs": {},
                "config": config,
            }],
        }
        spec_path = self.root / "m14-workflow.json"
        spec_path.write_text(json.dumps(specification), encoding="utf-8")
        registry = artifact_workflow.build_default_registry()
        definition = registry.get(m14.STAGE_KIND)

        self.assertIsNotNone(definition)
        self.assertTrue(definition.dynamic_inputs)
        artifact_workflow.run(spec_path, self.root / "workflow-output", registry)
        workflow = json.loads(
            (self.root / "workflow-output" / "workflow.json").read_text()
        )
        self.assertEqual(workflow["status"], "complete")
        stage = next(row for row in workflow["stages"] if row["id"] == "describe")
        self.assertEqual(stage["status"], "complete")
        stage_dir = self.root / "workflow-output" / stage["output_path"]
        self.assertTrue((stage_dir / "result_bundle.json").is_file())
        for filename, artifact_type in m14.OUTPUT_CONTRACTS.items():
            artifact_contracts.validate_artifact(stage_dir / filename, artifact_type)


if __name__ == "__main__":
    unittest.main()