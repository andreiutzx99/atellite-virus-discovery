import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import (
    artifact_contracts, artifact_workflow, m15_contracts, m15_stage,
)
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
            (
                index for index, row in enumerate(config["source_outcomes"])
                if row["source_kind"] == source_kind
                and row["source_state"] == "NOT_SUPPLIED"
            ),
            None,
        )
        if outcome_index is None:
            config["source_outcomes"].append(outcome)
        else:
            config["source_outcomes"][outcome_index] = outcome
        return ref, outcome

    def _declare_stage_source(self, config, source_kind, source_id, raw_status):
        spec = m14.SOURCE_SPECS[source_kind]
        producer = self.root / f"producer-{source_id}"
        producer.mkdir(parents=True)
        workflow_id = f"workflow-{source_id}"
        workflow_path = producer / "workflow.json"
        workflow_path.write_text(json.dumps({
            "schema": "artifact-workflow-manifest-v2",
            "workflow_id": workflow_id,
            "output": str(producer / "output"),
            "stages": [{
                "id": "producer-stage",
                "kind": spec["stage_kind"],
                "status": raw_status,
            }],
        }), encoding="utf-8")
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
                "raw_status": raw_status,
                "manifest_sha256": None,
            },
            "artifact_refs": [],
            "artifact_attempts": [],
            "producer_result_status": None,
            "producer_completeness": "NOT_REPORTED",
            "reason_code": None,
        }
        slot = next(
            (
                index for index, row in enumerate(config["source_outcomes"])
                if row["source_kind"] == source_kind
                and row["source_state"] == "NOT_SUPPLIED"
            ),
            None,
        )
        if slot is None:
            config["source_outcomes"].append(outcome)
        else:
            config["source_outcomes"][slot] = outcome
        return outcome, workflow_path

    def _run_from(self, root, config, label="run"):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        previous_root = self.root
        previous_cwd = Path.cwd()
        self.root = root
        try:
            os.chdir(root)
            return self._run(config, label)
        finally:
            os.chdir(previous_cwd)
            self.root = previous_root

    def _refresh_producer_manifest(self, ref, outcome, inventory_updates=None):
        stage_output = (
            self.root / f"producer-{outcome['source_id']}" / "output" / "stage"
        )
        manifest_path = stage_output / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["output_sha256"].update(inventory_updates or {})
        raw_manifest = m14._canonical_json_bytes(
            manifest, trailing_newline=True,
        )
        manifest_path.write_bytes(raw_manifest)
        manifest_digest = hashlib.sha256(raw_manifest).hexdigest()
        outcome["producer_stage"]["manifest_sha256"] = manifest_digest
        ref["producer_run_manifest_sha256"] = manifest_digest
        return stage_output

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
            _, summary, bundle, observations = self._run(config)
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
        self.assertEqual(resolved["producer_stage"], {
            "stage_id": "producer-stage",
            "stage_kind": "catalogue_observations",
            "raw_status": None,
            "manifest_sha256": None,
        })
        self.assertIsNone(resolved["producer_result_status"])
        self.assertEqual(resolved["producer_completeness"], "NOT_REPORTED")
        self.assertEqual(resolved["artifact_refs"], [])
        self.assertEqual(
            [row["artifact_id"] for row in bundle["source_artifacts"]],
            [],
        )
        self.assertEqual(len(bundle["source_outcomes"]), 3)
        self.assertEqual(observations["observations"][0]["candidate_state"], "PRESENT")
        self.assertEqual(observations["observations"][0]["helper_state"], "PRESENT")
        self.assertEqual(len(observations["observations"]), 1)
        self.assertTrue(bundle["frame_complete"])
        self.assertEqual(
            bundle["claim_boundary"]["summary"],
            "Descriptive co-detection only; association and dependence were not assessed.",
        )
        self.assertFalse(bundle["claim_boundary"]["helper_dependence_assessed"])
        self.assertFalse(bundle["claim_boundary"]["independence_inferred"])

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
        runtime = {"source_sha256": "unchanged-package-baseline"}
        dependency = {"status": "available"}
        other_stage_keys_before = {
            kind: artifact_workflow._stage_cache_key(
                {"id": f"scope-check-{kind}", "kind": kind},
                definition, {}, {}, runtime, None,
            )
            for kind, definition in registry._stages.items()
            if kind != m14.STAGE_KIND
        }
        with patch.object(m14, "_implementation_sha256", side_effect=["1" * 64, "2" * 64]):
            m14_first = artifact_workflow._stage_cache_key(
                {"id": "describe", "kind": m14.STAGE_KIND}, m14_definition,
                {}, {}, runtime, dependency,
            )
            m14_second = artifact_workflow._stage_cache_key(
                {"id": "describe", "kind": m14.STAGE_KIND}, m14_definition,
                {}, {}, runtime, dependency,
            )
            other_stage_keys_during = {
                kind: artifact_workflow._stage_cache_key(
                    {"id": f"scope-check-{kind}", "kind": kind},
                    definition, {}, {}, runtime, None,
                )
                for kind, definition in registry._stages.items()
                if kind != m14.STAGE_KIND
            }

        self.assertNotEqual(m14_first, m14_second)
        self.assertEqual(other_stage_keys_before, other_stage_keys_during)
        self.assertEqual(len(other_stage_keys_before), len(registry._stages) - 1)

    def test_m14_source_hash_normalizes_crlf(self):
        source = Path(m14.__file__).read_bytes()
        lf_source = source.replace(b"\r\n", b"\n")
        crlf_source = lf_source.replace(b"\n", b"\r\n")
        expected = hashlib.sha256(lf_source).hexdigest()
        with patch.object(Path, "read_bytes", return_value=crlf_source):
            self.assertEqual(m14._implementation_sha256(), expected)

    def test_m14_only_source_changes_preserve_legacy_upstream_cache_identity(self):
        runtime = artifact_workflow.reproducibility.environment()
        legacy_identity = artifact_workflow._legacy_package_cache_digest(runtime)

        m14_only_change = copy.deepcopy(runtime)
        m14_only_change["source_files"]["m14_descriptive_observations.py"] = (
            "f" * 64
        )
        m14_only_change["source_sha256"] = hashlib.sha256(
            json.dumps(
                m14_only_change["source_files"], sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            legacy_identity,
            artifact_workflow._legacy_package_cache_digest(m14_only_change),
        )

        crlf_runtime = copy.deepcopy(runtime)
        package = Path(artifact_workflow.reproducibility.__file__).resolve().parent
        crlf_hashes = {}
        for source in sorted(package.iterdir()):
            if source.suffix not in {".py", ".json"} or not source.is_file():
                continue
            content = source.read_bytes()
            content = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            crlf_hashes[source.name] = hashlib.sha256(content).hexdigest()
        crlf_runtime["source_files"] = crlf_hashes
        crlf_runtime["source_sha256"] = hashlib.sha256(
            json.dumps(crlf_hashes, sort_keys=True).encode("utf-8")
        ).hexdigest()
        compatibility = dict(
            line.split("=", 1)
            for line in (
                package / "m12_legacy_cache_compatibility.txt"
            ).read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        self.assertEqual(
            compatibility["legacy_source_sha256_crlf"],
            artifact_workflow._legacy_package_cache_digest(crlf_runtime),
        )

        shared_change = copy.deepcopy(m14_only_change)
        shared_change["source_files"]["artifact_workflow.py"] = "e" * 64
        shared_change["source_sha256"] = hashlib.sha256(
            json.dumps(
                shared_change["source_files"], sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        self.assertEqual(
            shared_change["source_sha256"],
            artifact_workflow._legacy_package_cache_digest(shared_change),
        )

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

    def test_nonterminal_and_failed_sources_leave_independent_evidence_unchanged(self):
        statuses = (
            ("pending", "INCOMPLETE", "PRODUCER_NONTERMINAL"),
            ("running", "INCOMPLETE", "PRODUCER_NONTERMINAL"),
            ("failed", "FAILED", "PRODUCER_FAILED"),
            ("interrupted", "INTERRUPTED", "PRODUCER_INTERRUPTED"),
            ("dependency_missing", "UNAVAILABLE", "DEPENDENCY_UNAVAILABLE"),
            ("external_module_required", "UNAVAILABLE", "DEPENDENCY_UNAVAILABLE"),
        )
        for raw_status, expected_state, expected_reason in statuses:
            with self.subTest(raw_status=raw_status):
                config = _manifest(("u1",))
                outcome, _ = self._declare_stage_source(
                    config, "M4_CATALOGUE_OBSERVATIONS",
                    f"m4-{raw_status}", raw_status,
                )
                independent_source_id = f"m7-independent-{raw_status}"
                self._attach_source(
                    config, "M7_INDEPENDENT_RECURRENCE",
                    independent_source_id,
                    f"{independent_source_id}-artifact",
                    "m7_independence_summary",
                    {
                        "schema": "m7-independence-summary-v1",
                        "analysis_completeness": "PARTIAL",
                        "result_status": "UPSTREAM_UNAVAILABLE_OR_FAILED",
                        "observation_count": 1,
                        "supported_sequence_observation_count": 0,
                        "exact_group_count": 0,
                        "recurrent_group_count": 0,
                        "limitations": ["Synthetic independent source"],
                        "m6_evidence_class_counts": {},
                    },
                )
                _, summary, bundle, table = self._run_from(
                    self.root, config, f"nonterminal-{raw_status}",
                )

                resolved = next(
                    row for row in bundle["source_outcomes"]
                    if row["source_id"] == outcome["source_id"]
                )
                independent = next(
                    row for row in bundle["source_outcomes"]
                    if row["source_id"] == independent_source_id
                )
                self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
                self.assertEqual(bundle["frame_complete"], True)
                self.assertEqual(resolved["source_state"], expected_state)
                self.assertEqual(resolved["reason_code"], expected_reason)
                self.assertEqual(resolved["producer_stage"]["raw_status"], raw_status)
                self.assertIsNone(resolved["producer_stage"]["manifest_sha256"])
                self.assertEqual(independent["source_state"], "AVAILABLE")
                self.assertEqual(len(bundle["source_artifacts"]), 1)
                self.assertEqual(summary["n_jointly_tested"], 1)
                self.assertEqual(
                    (table["observations"][0]["candidate_state"],
                     table["observations"][0]["helper_state"]),
                    ("PRESENT", "PRESENT"),
                )

    def test_all_unavailable_source_families_keep_caller_frame_and_declared_attempts(self):
        config = _manifest(("u1",))
        cases = (
            (
                "M4_CATALOGUE_OBSERVATIONS", "m4-catalogue-missing",
                "occurrence_summary",
            ),
            ("M4_OBSERVATIONS", "m4-observations-missing", "occurrence_summary"),
            (
                "M7_INDEPENDENT_RECURRENCE", "m7-recurrence-missing",
                "m7_independence_summary",
            ),
        )
        outcomes = []
        for source_kind, source_id, artifact_type in cases:
            ref, outcome = self._attach_source(
                config, source_kind, source_id, f"{source_id}-artifact",
                artifact_type, None,
            )
            outcomes.append((ref, outcome))
            (self.root / outcome["workflow_ref"]["relative_path"]).unlink()

        _, summary, bundle, table = self._run_from(
            self.root, config, "all-sources-unavailable",
        )

        self.assertEqual(bundle["result_state"], "COMPLETED_DESCRIPTIVE")
        self.assertTrue(bundle["frame_complete"])
        self.assertEqual(summary["n_jointly_tested"], 1)
        self.assertEqual(bundle["source_artifacts"], [])
        self.assertEqual(
            {(row["source_kind"], row["source_state"])
             for row in bundle["source_outcomes"]},
            {
                ("M4_CATALOGUE_OBSERVATIONS", "UNAVAILABLE"),
                ("M4_OBSERVATIONS", "UNAVAILABLE"),
                ("M7_INDEPENDENT_RECURRENCE", "UNAVAILABLE"),
            },
        )
        resolved = {row["source_id"]: row for row in bundle["source_outcomes"]}
        for ref, outcome in outcomes:
            row = resolved[outcome["source_id"]]
            self.assertEqual(row["reason_code"], "WORKFLOW_UNAVAILABLE")
            self.assertEqual(row["producer_stage"]["raw_status"], None)
            self.assertEqual(row["producer_stage"]["manifest_sha256"], None)
            self.assertEqual(row["artifact_refs"], [])
            self.assertEqual(
                row["artifact_attempts"][0]["relative_path"], ref["relative_path"],
            )
        self.assertEqual(len(table["observations"]), 1)
        self.assertEqual(table["observations"][0]["candidate_state"], "PRESENT")
        self.assertEqual(table["observations"][0]["helper_state"], "PRESENT")

    def test_multiple_valid_runs_are_order_independent_and_keep_run_provenance(self):
        configs = []
        for source_id, artifact_id in (
            ("m4-run-a", "m4-artifact-a"),
            ("m4-run-b", "m4-artifact-b"),
        ):
            config = _manifest(("u1",))
            self._attach_source(
                config, "M4_CATALOGUE_OBSERVATIONS", source_id, artifact_id,
                "occurrence_summary",
                {
                    "schema": "synthetic-occurrence-summary-v1",
                    "status": "NO_OCCURRENCES_DETECTED",
                    "producer_completeness": "PARTIAL",
                },
            )
            configs.append(config)

        _, _, first, _ = self._run_from(self.root, configs[0], "run-a")
        _, _, second, _ = self._run_from(self.root, configs[1], "run-b")
        self.assertEqual(
            first["m14_semantic_input_sha256"],
            second["m14_semantic_input_sha256"],
        )
        self.assertNotEqual(
            first["m14_provenance_sha256"], second["m14_provenance_sha256"],
        )
        self.assertNotEqual(
            first["m14_cache_identity_sha256"],
            second["m14_cache_identity_sha256"],
        )

        combined = _manifest(("u1",))
        combined["source_outcomes"] = [
            row for row in combined["source_outcomes"]
            if row["source_kind"] != "M4_CATALOGUE_OBSERVATIONS"
        ]
        combined["source_outcomes"].extend(
            copy.deepcopy(
                next(
                    row for row in config["source_outcomes"]
                    if row["source_kind"] == "M4_CATALOGUE_OBSERVATIONS"
                )
            )
            for config in configs
        )
        combined["source_artifacts"] = [
            copy.deepcopy(config["source_artifacts"][0]) for config in configs
        ]
        _, _, ordered, _ = self._run_from(self.root, combined, "multiple-runs")
        permuted = copy.deepcopy(combined)
        permuted["source_outcomes"].reverse()
        permuted["source_artifacts"].reverse()
        _, _, reversed_bundle, _ = self._run_from(
            self.root, permuted, "multiple-runs-reversed",
        )
        self.assertEqual(
            ordered["m14_cache_identity_sha256"],
            reversed_bundle["m14_cache_identity_sha256"],
        )
        self.assertEqual(
            [ref["artifact_id"] for ref in ordered["source_artifacts"]],
            ["m4-artifact-a", "m4-artifact-b"],
        )

    def test_unreadable_workflow_and_stage_mismatches_do_not_echo_claimed_status_or_digest(self):
        cases = (
            ("workflow-id", "PRODUCER_IDENTITY_MISMATCH"),
            ("stage-id", "PRODUCER_STAGE_NOT_FOUND"),
            ("stage-kind", "PRODUCER_IDENTITY_MISMATCH"),
        )
        original_root = self.root
        try:
            for case, expected_reason in cases:
                with self.subTest(case=case):
                    self.root = original_root / case
                    self.root.mkdir()
                    config = _manifest(("u1",))
                    _, outcome = self._attach_source(
                        config, "M4_CATALOGUE_OBSERVATIONS", f"source-{case}",
                        f"artifact-{case}", "occurrence_summary",
                        {"schema": "synthetic-occurrence-summary-v1"},
                    )
                    expected_stage_id = outcome["producer_stage"]["stage_id"]
                    expected_stage_kind = outcome["producer_stage"]["stage_kind"]
                    if case == "workflow-id":
                        path = self.root / outcome["workflow_ref"]["relative_path"]
                        workflow = json.loads(path.read_text(encoding="utf-8"))
                        workflow["workflow_id"] = "different-workflow"
                        path.write_text(json.dumps(workflow), encoding="utf-8")
                    elif case == "stage-id":
                        expected_stage_id = "declared-stage-not-present"
                        outcome["producer_stage"]["stage_id"] = expected_stage_id
                    else:
                        expected_stage_kind = "declared-stage-kind"
                        outcome["producer_stage"]["stage_kind"] = expected_stage_kind
                    _, _, bundle, _ = self._run_from(
                        self.root, config, f"mismatch-{case}",
                    )
                    resolved = next(
                        row for row in bundle["source_outcomes"]
                        if row["source_id"] == outcome["source_id"]
                    )
                    self.assertEqual(resolved["source_state"], "INVALID")
                    self.assertEqual(resolved["reason_code"], expected_reason)
                    self.assertEqual(resolved["producer_stage"], {
                        "stage_id": expected_stage_id,
                        "stage_kind": expected_stage_kind,
                        "raw_status": None,
                        "manifest_sha256": None,
                    })
                    self.assertEqual(bundle["source_artifacts"], [])
        finally:
            self.root = original_root

    def test_caller_declared_invalid_stage_metadata_is_sanitized(self):
        config = _manifest(("u1",))
        outcome = config["source_outcomes"][0]
        outcome.update(
            source_id="caller-invalid-source",
            source_state="INVALID",
            workflow_ref={
                "relative_path": "missing-producer/workflow.json",
                "workflow_id": "caller-workflow-id",
            },
            producer_stage={
                "stage_id": "caller-stage-id",
                "stage_kind": "catalogue_observations",
                "raw_status": "complete",
                "manifest_sha256": "f" * 64,
            },
            reason_code="SOURCE_OUTCOME_INVALID",
        )
        _, _, bundle, _ = self._run(config)
        resolved = next(
            row for row in bundle["source_outcomes"]
            if row["source_id"] == "caller-invalid-source"
        )
        self.assertEqual(resolved["source_state"], "INVALID")
        self.assertEqual(resolved["producer_stage"], {
            "stage_id": "caller-stage-id",
            "stage_kind": "catalogue_observations",
            "raw_status": None,
            "manifest_sha256": None,
        })

    def test_symlink_artifact_path_is_rejected_after_stage_provenance_is_verified(self):
        config = _manifest(("u1",))
        ref, outcome = self._attach_source(
            config, "M4_CATALOGUE_OBSERVATIONS", "m4-symlink-artifact",
            "symlink-artifact", "occurrence_summary",
            {"schema": "synthetic-occurrence-summary-v1"},
        )
        stage_output = (
            self.root / "producer-m4-symlink-artifact" / "output" / "stage"
        )
        original = (stage_output / "summary.json").read_bytes()
        outside = self.root / "outside-summary.json"
        outside.write_bytes(original)
        link = stage_output / "linked-summary.json"
        link.symlink_to(outside)
        digest = hashlib.sha256(original).hexdigest()
        ref["relative_path"] = "linked-summary.json"
        ref["content_sha256"] = digest
        self._refresh_producer_manifest(
            ref, outcome, {"linked-summary.json": digest},
        )

        _, summary, bundle, table = self._run_from(
            self.root, config, "symlink-artifact",
        )

        resolved = next(
            row for row in bundle["source_outcomes"]
            if row["source_id"] == outcome["source_id"]
        )
        self.assertEqual(resolved["source_state"], "INVALID")
        self.assertEqual(resolved["reason_code"], "ARTIFACT_PATH_UNSAFE")
        self.assertEqual(resolved["producer_stage"]["raw_status"], "complete")
        self.assertEqual(
            resolved["producer_stage"]["manifest_sha256"],
            ref["producer_run_manifest_sha256"],
        )
        self.assertEqual(resolved["artifact_refs"], [])
        self.assertEqual(bundle["source_artifacts"], [])
        self.assertEqual(summary["n_jointly_tested"], 1)
        self.assertEqual(table["observations"][0]["candidate_state"], "PRESENT")
        self.assertEqual(table["observations"][0]["helper_state"], "PRESENT")

    def test_cache_identity_ignores_locations_and_unrelated_workflow_metadata(self):
        original_root = self.root
        root_a = original_root / "location-a"
        root_b = original_root / "location-b"
        try:
            self.root = root_a
            root_a.mkdir()
            config = _manifest(("u1",))
            self._attach_source(
                config, "M4_CATALOGUE_OBSERVATIONS", "relocated-source",
                "relocated-artifact", "occurrence_summary",
                {
                    "schema": "synthetic-occurrence-summary-v1",
                    "status": "NO_OCCURRENCES_DETECTED",
                    "producer_completeness": "PARTIAL",
                },
            )
            _, _, initial, _ = self._run_from(root_a, config, "initial")

            workflow_path_a = root_a / "producer-relocated-source" / "workflow.json"
            workflow_a = json.loads(workflow_path_a.read_text(encoding="utf-8"))
            workflow_a["generated_at"] = "synthetic-time-a"
            workflow_a["host"] = "synthetic-host-a"
            workflow_a["stages"].append({
                "id": "unrelated-stage",
                "kind": "unrelated-synthetic-kind",
                "status": "failed",
            })
            workflow_path_a.write_text(json.dumps(workflow_a), encoding="utf-8")
            _, _, metadata_only, _ = self._run_from(
                root_a, config, "metadata-only",
            )

            root_b.mkdir()
            producer_b = root_b / "producer-relocated-source"
            shutil.copytree(
                root_a / "producer-relocated-source", producer_b,
            )
            workflow_path_b = producer_b / "workflow.json"
            workflow_b = json.loads(workflow_path_b.read_text(encoding="utf-8"))
            workflow_b["output"] = str(producer_b / "output")
            workflow_b["generated_at"] = "synthetic-time-b"
            workflow_b["host"] = "synthetic-host-b"
            workflow_path_b.write_text(json.dumps(workflow_b), encoding="utf-8")
            _, _, relocated, _ = self._run_from(root_b, config, "relocated")

            identity_fields = (
                "m14_semantic_input_sha256",
                "m14_provenance_sha256",
                "m14_cache_identity_sha256",
            )
            for field in identity_fields:
                self.assertEqual(initial[field], metadata_only[field], field)
                self.assertEqual(initial[field], relocated[field], field)
            serialized = json.dumps(relocated, sort_keys=True)
            self.assertNotIn(str(root_a), serialized)
            self.assertNotIn(str(root_b), serialized)
        finally:
            self.root = original_root

    def test_semantic_input_and_contract_changes_invalidate_the_right_identities(self):
        config = _manifest(("u1",))
        _, _, baseline, _ = self._run(config, "identity-baseline")

        changed_observation = copy.deepcopy(config)
        changed_observation["observations"][0]["candidate_state"] = (
            "NOT_DETECTED_WITHIN_SCOPE"
        )
        _, _, changed_semantics, _ = self._run(
            changed_observation, "identity-semantic-change",
        )
        self.assertNotEqual(
            baseline["m14_semantic_input_sha256"],
            changed_semantics["m14_semantic_input_sha256"],
        )
        self.assertNotEqual(
            baseline["m14_cache_identity_sha256"],
            changed_semantics["m14_cache_identity_sha256"],
        )

        with patch.dict(
            artifact_contracts._CONTRACT_SEMANTIC_VERSIONS,
            {"m14_observation_table": "next-contract-semantics"},
        ):
            _, _, changed_contract, _ = self._run(config, "identity-contract-change")
        self.assertEqual(
            baseline["m14_semantic_input_sha256"],
            changed_contract["m14_semantic_input_sha256"],
        )
        self.assertNotEqual(
            baseline["m14_cache_identity_sha256"],
            changed_contract["m14_cache_identity_sha256"],
        )

    def test_tampered_m14_output_is_rejected_instead_of_reused_by_m1(self):
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
        spec_path = self.root / "tampered-m14-workflow.json"
        output = self.root / "tampered-m14-output"
        spec_path.write_text(json.dumps(specification), encoding="utf-8")
        registry = artifact_workflow.build_default_registry()
        artifact_workflow.run(spec_path, output, registry)
        workflow = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
        prior = next(row for row in workflow["stages"] if row["id"] == "describe")
        stage_output = output / prior["output_path"]
        stage = specification["stages"][0]
        definition = registry.get(m14.STAGE_KIND)

        (stage_output / "descriptive_summary.json").write_text(
            '{"tampered":true}\n', encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            m14.validate_output_file(
                stage_output / "result_bundle.json", "m14_result_bundle",
            )
        self.assertIsNone(artifact_workflow._verified_previous_stage(
            output.resolve(), stage, definition, prior,
        ))

        with self.assertRaises(Exception):
            artifact_workflow.run(spec_path, output, registry)
        after = json.loads((output / "workflow.json").read_text(encoding="utf-8"))
        self.assertNotEqual(after["status"], "complete")
        after_stage = next(row for row in after["stages"] if row["id"] == "describe")
        self.assertNotEqual(after_stage["status"], "complete")


class M14M15AuthenticatedWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m14-m15-integration-")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_real_m14_workflow_artifact_is_verified_by_m15(self):
        m14_spec_path = self.root / "m14-workflow.json"
        m14_output = self.root / "m14-output"
        m14_spec = {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "describe",
                "kind": m14.STAGE_KIND,
                "inputs": {},
                "config": _manifest(("unit-A",)),
            }],
        }
        m15_contracts.write_json(m14_spec_path, m14_spec)
        registry = artifact_workflow.build_default_registry()
        artifact_workflow.run(m14_spec_path, m14_output, registry)
        m14_workflow = json.loads(
            (m14_output / "workflow.json").read_text(encoding="utf-8")
        )
        m14_row = next(
            row for row in m14_workflow["stages"] if row["id"] == "describe"
        )
        self.assertEqual(m14_row["status"], "complete", m14_row.get("error"))
        stage_output = m14_output / m14_row["output_path"]
        relative_path = "observations.json"
        artifact_path = stage_output / relative_path
        stage_manifest_sha256 = m15_contracts.sha256_file(
            stage_output / "manifest.json"
        )
        workflow_sha256 = m15_contracts.sha256_file(
            m14_output / "workflow.json"
        )
        contract_version = artifact_contracts.CONTRACT_VERSION
        ref = {
            "producer_milestone": "M14",
            "producer_stage_id": "describe",
            "producer_run_manifest_sha256": stage_manifest_sha256,
            "producer_status": "complete",
            "artifact_type": "m14_observation_table",
            "artifact_contract_version": contract_version,
            "relative_path": relative_path,
            "sha256": m15_contracts.sha256_file(artifact_path),
            "provenance_mode": (
                m15_contracts.AUTHENTICATED_PRODUCER_MODE
            ),
            "producer_execution_ref": {
                "schema": "producer-execution-ref-v1",
                "producer_workflow_ref": {
                    "path": "workflow.json",
                    "sha256": workflow_sha256,
                    "workflow_id": m14_workflow["workflow_id"],
                },
                "producer_stage_id": "describe",
                "producer_stage_kind": m14.STAGE_KIND,
                "producer_stage_manifest_sha256": stage_manifest_sha256,
            },
            "producer_bundle_path": "m14-output",
        }
        m15_input_path = self.root / "m15-input.json"
        m15_contracts.write_json(m15_input_path, {
            "schema": m15_contracts.INPUT_SCHEMA,
            "candidate_id": "candidate-A",
            "artifact_refs": [ref],
            "optional_stage_states": {
                "M12": "NOT_SUPPLIED",
                "M13": "NOT_SUPPLIED",
                "M14": "PRESENT",
            },
        })
        m15_spec_path = self.root / "m15-workflow.json"
        m15_contracts.write_json(m15_spec_path, {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "m15",
                "kind": m15_stage.STAGE_KIND,
                "inputs": {
                    "manifest": {
                        "path": m15_input_path.name,
                        "artifact_type": "m15_input_manifest",
                    },
                    "artifact_0000": {
                        "path": (
                            f"m14-output/{m14_row['output_path']}/"
                            f"{relative_path}"
                        ),
                        "artifact_type": "m14_observation_table",
                    },
                },
            }],
        })
        m15_output = self.root / "m15-output"
        artifact_workflow.run(m15_spec_path, m15_output, registry)
        m15_workflow = json.loads(
            (m15_output / "workflow.json").read_text(encoding="utf-8")
        )
        m15_row = next(
            row for row in m15_workflow["stages"] if row["id"] == "m15"
        )
        self.assertEqual(m15_row["status"], "complete", m15_row.get("error"))
        m15_stage_output = m15_output / m15_row["output_path"]
        envelope = json.loads(
            (m15_stage_output / "evidence_envelope.json").read_text(
                encoding="utf-8"
            )
        )
        record = envelope["records"][0]
        self.assertEqual(record["validation_state"], "ACCEPTED")
        self.assertEqual(record["producer_provenance_state"], "VERIFIED")
        self.assertTrue(record["producer_binding_sha256"])
        self.assertEqual(record["semantic_axes"]["artifact_validity"], "VALID")
        self.assertEqual(
            record["producer_schema_raw"],
            "m14-observation-table-v1",
        )


if __name__ == "__main__":
    unittest.main()