import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import test_dvg_workflow as dvg_workflow_tests

from satellite_discovery import (
    dvg_evidence,
    execution_outcome,
    m13_contracts,
    m13_stage,
    reproducibility,
)
from satellite_discovery import artifact_workflow
from satellite_discovery.artifact_workflow import run as run_workflow


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class M13M5EvidenceTests(unittest.TestCase):
    def setUp(self):
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="m13-m5-evidence-"
        )
        self.root = Path(self._temporary_directory.name)

    def tearDown(self):
        self._temporary_directory.cleanup()

    def _produce_m5(self, name, behavior="positive", *, skip=False):
        fixture_root = self.root / name
        fixture_root.mkdir()
        dvg_workflow_tests._fixture(fixture_root)
        if behavior == "multi":
            reference = fixture_root / "reference.fasta"
            reference.write_text(
                reference.read_text(encoding="utf-8") + ">REF2\nGATTACA\n",
                encoding="utf-8",
            )
        registry, _adapter = dvg_workflow_tests._registry(behavior)
        output = fixture_root / "m5-output"
        spec = dvg_workflow_tests._spec(
            fixture_root, skip=skip, include_report=False
        )
        try:
            run_workflow(spec, output, registry=registry)
        except Exception:
            # Failed synthetic callers write their terminal workflow and
            # execution outcome before surfacing the failure to their caller.
            pass
        workflow_path = output / "workflow.json"
        self.assertTrue(workflow_path.is_file())
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        stage = next(row for row in workflow["stages"] if row["id"] == "dvg")
        if behavior in {"positive", "multi", "negative"} and not skip:
            self.assertEqual(stage["status"], "complete", stage.get("error_type"))
        return {
            "fixture_root": fixture_root,
            "output": output,
            "workflow_path": workflow_path,
            "workflow": workflow,
            "stage": stage,
        }

    def _m5_run_ref(self, m5, *, workflow_path=None, outcome_path=None):
        stage = m5["stage"]
        status = stage["status"]
        marker_path = None
        run_digest = None
        refs = []
        states = {
            artifact_type: "NOT_PRODUCED"
            for artifact_type in m13_contracts.ARTIFACT_STATE_KEYS
        }
        if status == "complete":
            marker_path = m5["output"] / stage["output_path"] / "manifest.json"
            run_digest = _sha256(marker_path)
            for descriptor in stage.get("artifacts", {}).values():
                artifact_type = descriptor.get("artifact_type")
                if artifact_type not in m13_contracts.M5_ARTIFACT_TYPES:
                    continue
                relative_path = Path(descriptor["path"]).relative_to(
                    Path(stage["output_path"])
                ).as_posix()
                states[artifact_type] = "PRESENT"
                refs.append({
                    "producer_milestone": "M5",
                    "producer_stage_id": stage["id"],
                    "producer_status": "complete",
                    "producer_run_manifest_sha256": run_digest,
                    "artifact_type": artifact_type,
                    "relative_path": relative_path,
                    "sha256": descriptor["sha256"],
                    "artifact_contract_version": descriptor["contract_version"],
                })

        result = {
            "producer_stage_id": stage["id"],
            "producer_run_manifest_sha256": run_digest,
            "producer_status": status,
            "artifacts": refs,
            "artifact_states": states,
            "_source_artifact_root": (
                str(m5["output"] / stage["output_path"])
                if status == "complete" else None
            ),
        }
        if status != "complete":
            if workflow_path is None:
                workflow_path = m5["workflow_path"]
            if outcome_path is None:
                outcome_path = m5["output"] / "execution-outcomes" / "dvg.json"
            workflow_ref_path = Path(workflow_path)
            outcome_ref_path = Path(outcome_path)
            workflow_ref_path = workflow_ref_path.relative_to(self.root).as_posix()
            outcome_ref_path = outcome_ref_path.relative_to(self.root).as_posix()
            result["producer_workflow_ref"] = {
                "path": workflow_ref_path,
                "sha256": _sha256(self.root / workflow_ref_path),
                "workflow_id": m5["workflow"]["workflow_id"],
            }
            if Path(outcome_path).is_file():
                outcome_record = json.loads(
                    Path(outcome_path).read_text(encoding="utf-8")
                )
                outcome_sha256 = _sha256(outcome_path)
                outcome_schema = outcome_record["schema"]
            else:
                outcome_sha256 = "0" * 64
                outcome_schema = "m5-execution-outcome-v1"
            result["execution_record_ref"] = {
                "path": outcome_ref_path,
                "sha256": outcome_sha256,
                "schema": outcome_schema,
            }
        return result

    def _configure_noncompleted_m5(
        self, m5, *, stage_status, m5_status, failure_code=None
    ):
        workflow = m5["workflow"]
        workflow["status"] = (
            "failed" if stage_status in {"failed", "interrupted"} else "partial"
        )
        stage = m5["stage"]
        stage["status"] = stage_status
        stage["dvg_evidence"] = {"status": m5_status}
        m13_contracts.write_json(m5["workflow_path"], workflow)
        failure_codes = (
            {"dvg": failure_code} if failure_code is not None else None
        )
        execution_outcome.write_final_outcomes(
            m5["output"], failure_codes=failure_codes
        )
        return self._m5_run_ref(m5)

    def _run_m13(
        self, runs, *, hypotheses=None, root=None, input_path_overrides=None
    ):
        root = Path(root) if root is not None else self.root
        input_path_overrides = input_path_overrides or {}
        input_manifest = {
            "schema": m13_contracts.INPUT_SCHEMA,
            "candidate_id": "synthetic-candidate",
            "m5_runs": [
                {key: value for key, value in run.items()
                 if not key.startswith("_")}
                for run in runs
            ],
            "hypotheses": hypotheses or [],
        }
        input_path = root / "m13-input.json"
        m13_contracts.write_json(input_path, input_manifest)
        inputs = {
            "manifest": {
                "path": input_path.name,
                "artifact_type": "m13_input_manifest",
            }
        }
        for run_index, run in enumerate(runs):
            for ref in run["artifacts"]:
                source_path = (
                    Path(run["_source_artifact_root"]) / ref["relative_path"]
                )
                input_name = m13_contracts.artifact_input_name(
                    run_index, ref["artifact_type"]
                )
                inputs[input_name] = {
                    "path": input_path_overrides.get(
                        input_name,
                        source_path.relative_to(root).as_posix(),
                    ),
                    "artifact_type": ref["artifact_type"],
                }

        workflow_spec = {
            "schema": "artifact-workflow-v1",
            "stages": [{
                "id": "m13",
                "kind": "m13_m5_evidence_matrix",
                "inputs": inputs,
            }],
        }
        spec_path = root / "m13-workflow.json"
        m13_contracts.write_json(spec_path, workflow_spec)
        output = root / "m13-output"
        run_workflow(spec_path, output)
        workflow_path = output / "workflow.json"
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        stage = next(row for row in workflow["stages"] if row["id"] == "m13")
        self.assertEqual(stage["status"], "complete", stage.get("error"))
        output_root = output / stage["output_path"]
        return {
            "workflow": workflow,
            "workflow_path": workflow_path,
            "output_root": output,
            "input_manifest_path": input_path,
            "workflow_spec_path": spec_path,
            "stage": stage,
            "output": output_root,
            "event_index": json.loads(
                (output_root / "event_index.json").read_text(encoding="utf-8")
            ),
            "hypothesis_matrix": json.loads(
                (output_root / "hypothesis_matrix.json").read_text(encoding="utf-8")
            ),
            "summary": json.loads(
                (output_root / "summary.json").read_text(encoding="utf-8")
            ),
            "bundle": json.loads(
                (output_root / "result_bundle.json").read_text(encoding="utf-8")
            ),
        }

    def test_completed_events_preserve_m5_provenance_and_limit_hypothesis_claims(self):
        m5 = self._produce_m5("m5-events", "multi")
        result = self._run_m13(
            [self._m5_run_ref(m5)],
            hypotheses=[
                {
                    "hypothesis_id": "structural",
                    "scope": "STRUCTURAL_OBSERVATION",
                    "label": "A caller-reported structural event exists",
                    "provenance_ref": "synthetic:test",
                },
                {
                    "hypothesis_id": "function",
                    "scope": "FUNCTION_OR_INTERFERENCE",
                    "label": "The candidate has helper-dependent function",
                    "provenance_ref": "synthetic:test",
                },
            ],
        )

        source_events = json.loads(
            (m5["output"] / m5["stage"]["output_path"] / "evidence.json")
            .read_text(encoding="utf-8")
        )["events"]
        events = result["event_index"]["events"]
        self.assertEqual(
            [event["source_event"] for event in events],
            source_events,
        )
        self.assertEqual(len(events), len(source_events))
        self.assertEqual(
            [event["source_row_index"] for event in events],
            list(range(len(source_events))),
        )
        self.assertEqual(
            result["summary"]["summary_completeness"],
            "COMPLETE",
        )
        imported_run = result["summary"]["runs"][0]
        self.assertEqual(imported_run["run_import_state"], "IMPORTED_WITH_EVENTS")
        self.assertEqual(imported_run["event_count"], len(source_events))
        self.assertEqual(
            imported_run["producer_status_raw"],
            dvg_evidence.DVG_EVIDENCE_DETECTED,
        )
        event = events[0]
        self.assertEqual(
            event["m5_run_ref"]["producer_run_manifest_sha256"],
            imported_run["producer_run_manifest_sha256"],
        )
        self.assertEqual(
            event["caller"],
            imported_run["caller"],
        )
        self.assertEqual(
            event["caller_version"],
            imported_run["caller_version"],
        )
        self.assertEqual(
            event["reference_sha256"],
            imported_run["reference_sha256"],
        )
        matrix = {
            row["hypothesis_id"]: row
            for row in result["hypothesis_matrix"]["hypotheses"]
        }
        self.assertEqual(matrix["structural"]["evidence_state"], "OBSERVED")
        self.assertEqual(matrix["function"]["evidence_state"], "UNRESOLVED")
        self.assertEqual(matrix["function"]["evidence_refs"], [])
        serialized = json.dumps({
            "summary": result["summary"],
            "hypothesis_matrix": result["hypothesis_matrix"],
        })
        for forbidden_claim in (
            "DVG_CONFIRMED",
            "NOT_DVG",
            "SATELLITE",
            "NOT_SATELLITE",
            "BIOLOGICALLY_AUTHENTIC",
            "NOVEL",
            "HELPER_DEPENDENT",
            "FUNCTION_PROVEN",
        ):
            self.assertNotIn(forbidden_claim, serialized)

    def test_completed_zero_is_not_an_absence_or_function_claim(self):
        m5 = self._produce_m5("m5-zero", "negative")
        result = self._run_m13(
            [self._m5_run_ref(m5)],
            hypotheses=[
                {
                    "hypothesis_id": "structural",
                    "scope": "STRUCTURAL_OBSERVATION",
                    "label": "A structural event was reported",
                    "provenance_ref": "synthetic:test",
                },
                {
                    "hypothesis_id": "identity",
                    "scope": "BIOLOGICAL_IDENTITY",
                    "label": "The candidate has a confirmed identity",
                    "provenance_ref": "synthetic:test",
                },
            ],
        )

        self.assertEqual(result["event_index"]["events"], [])
        self.assertEqual(result["summary"]["event_count"], 0)
        self.assertEqual(
            result["summary"]["runs"][0]["run_import_state"],
            "IMPORTED_COMPLETED_ZERO",
        )
        self.assertEqual(
            result["summary"]["runs"][0]["producer_execution_status_raw"],
            "complete",
        )
        self.assertEqual(
            result["summary"]["runs"][0]["producer_status_raw"],
            dvg_evidence.NO_DVG_EVIDENCE_DETECTED,
        )
        self.assertTrue(all(
            row["evidence_state"] == "UNRESOLVED"
            for row in result["hypothesis_matrix"]["hypotheses"]
        ))

    def test_invalid_run_does_not_erase_an_independent_valid_run(self):
        good = self._produce_m5("m5-good", "positive")
        bad = self._produce_m5("m5-bad", "positive")
        good_ref = self._m5_run_ref(good)
        bad_ref = self._m5_run_ref(bad)
        bad_evidence = (
            bad["output"] / bad["stage"]["output_path"] / "evidence.json"
        )
        bad_evidence.write_text("{not valid JSON", encoding="utf-8")

        result = self._run_m13([good_ref, bad_ref])
        states = {
            row["producer_run_manifest_sha256"]: row["run_import_state"]
            for row in result["summary"]["runs"]
        }
        self.assertEqual(states[good_ref["producer_run_manifest_sha256"]],
                         "IMPORTED_WITH_EVENTS")
        self.assertEqual(states[bad_ref["producer_run_manifest_sha256"]], "INVALID")
        self.assertEqual(len(result["event_index"]["events"]), 1)
        self.assertEqual(result["summary"]["summary_completeness"], "PARTIAL")

    def test_skipped_and_nonterminal_runs_retain_m1_and_m5_states(self):
        skipped = self._produce_m5("m5-skipped", "positive", skip=True)
        skipped_result = self._run_m13([self._m5_run_ref(skipped)])
        skipped_row = skipped_result["summary"]["runs"][0]
        self.assertEqual(skipped_row["producer_execution_status_raw"], "skipped")
        self.assertEqual(skipped_row["producer_status_raw"], "NOT_EVALUATED")
        self.assertEqual(skipped_row["run_import_state"], "NOT_SUPPLIED")

        running = self._produce_m5("m5-running", "positive", skip=True)
        workflow_path = running["workflow_path"]
        workflow = running["workflow"]
        workflow["status"] = "running"
        stage = next(row for row in workflow["stages"] if row["id"] == "dvg")
        stage["status"] = "running"
        m13_contracts.write_json(workflow_path, workflow)
        unfinished = self._m5_run_ref(
            running,
            workflow_path=workflow_path,
            outcome_path=running["output"] / "not-written-yet.json",
        )
        running_result = self._run_m13([unfinished])
        running_row = running_result["summary"]["runs"][0]
        self.assertEqual(running_row["producer_execution_status_raw"], "running")
        self.assertEqual(running_row["producer_status_raw"], "NOT_EVALUATED")
        self.assertEqual(running_row["run_import_state"], "INCOMPLETE")
        self.assertIsNone(running_row["outcome_code"])

    def test_terminal_failure_outcomes_are_not_mapped_to_zero_events(self):
        expected = {
            "nonzero": ("ANALYSIS_FAILED", "IMPORTED_NONCOMPLETED", "FAILED"),
            "partial": ("INVALID_RESULT", "INCOMPLETE", "INCOMPLETE_OUTPUT"),
            "malformed": ("INVALID_RESULT", "INVALID", "INVALID_OUTPUT"),
        }
        for behavior, (raw_status, import_state, outcome_code) in expected.items():
            with self.subTest(behavior=behavior):
                m5 = self._produce_m5(f"m5-{behavior}", behavior)
                result = self._run_m13([self._m5_run_ref(m5)])
                row = result["summary"]["runs"][0]
                self.assertEqual(row["producer_status_raw"], raw_status)
                self.assertEqual(row["producer_execution_status_raw"], "failed")
                self.assertEqual(row["run_import_state"], import_state)
                self.assertEqual(row["outcome_code"], outcome_code)
                self.assertNotEqual(row["outcome_code"], "COMPLETED_ZERO")
                self.assertEqual(result["event_index"]["events"], [])

    def test_structured_incomplete_reasons_remain_incomplete(self):
        for failure_code in (
            dvg_evidence.TRUNCATED_OUTPUT,
            dvg_evidence.INCOMPLETE_ACCOUNTING,
        ):
            with self.subTest(failure_code=failure_code):
                m5 = self._produce_m5(
                    f"m5-{failure_code.lower()}",
                    "positive",
                )
                run = self._configure_noncompleted_m5(
                    m5,
                    stage_status="failed",
                    m5_status=dvg_evidence.INVALID_RESULT,
                    failure_code=failure_code,
                )
                result = self._run_m13([run])
                row = result["summary"]["runs"][0]
                self.assertEqual(row["producer_execution_status_raw"], "failed")
                self.assertEqual(
                    row["producer_status_raw"], dvg_evidence.INVALID_RESULT
                )
                self.assertEqual(row["failure_code"], failure_code)
                self.assertEqual(row["outcome_code"], "INCOMPLETE_OUTPUT")
                self.assertEqual(row["run_import_state"], "INCOMPLETE")
                self.assertEqual(row["reason_code"], "PRODUCER_OUTPUT_INCOMPLETE")
                self.assertNotEqual(row["run_import_state"], "IMPORTED_COMPLETED_ZERO")
                self.assertEqual(result["summary"]["summary_completeness"], "PARTIAL")
                self.assertEqual(result["event_index"]["events"], [])

    def test_pending_interrupted_and_unavailable_outcomes_keep_typed_states(self):
        cases = (
            (
                "pending",
                "pending",
                dvg_evidence.NOT_EVALUATED,
                None,
                "NOT_SUPPLIED",
                "NOT_STARTED",
            ),
            (
                "interrupted",
                "interrupted",
                dvg_evidence.ANALYSIS_FAILED,
                None,
                "INTERRUPTED",
                "INTERRUPTED",
            ),
            (
                "dependency-missing",
                "dependency_missing",
                dvg_evidence.ANALYSIS_UNAVAILABLE,
                None,
                "UNAVAILABLE",
                "UNAVAILABLE",
            ),
            (
                "external-module-required",
                "external_module_required",
                dvg_evidence.ANALYSIS_UNAVAILABLE,
                None,
                "UNAVAILABLE",
                "UNAVAILABLE",
            ),
        )
        for name, stage_status, raw_m5_status, failure, expected_state, expected_outcome in cases:
            with self.subTest(stage_status=stage_status):
                m5 = self._produce_m5(f"m5-{name}", "positive")
                run = self._configure_noncompleted_m5(
                    m5,
                    stage_status=stage_status,
                    m5_status=raw_m5_status,
                    failure_code=failure,
                )
                result = self._run_m13([run])
                row = result["summary"]["runs"][0]
                self.assertEqual(row["producer_execution_status_raw"], stage_status)
                self.assertEqual(row["producer_status_raw"], raw_m5_status)
                self.assertEqual(row["outcome_code"], expected_outcome)
                self.assertEqual(row["run_import_state"], expected_state)
                self.assertNotEqual(row["outcome_code"], "COMPLETED_ZERO")
                self.assertEqual(result["event_index"]["events"], [])

    def test_valid_run_survives_incomplete_and_unavailable_bundle_members(self):
        valid = self._produce_m5("m5-valid-partial", "positive")
        valid_ref = self._m5_run_ref(valid)
        running = self._produce_m5("m5-running-partial", "positive", skip=True)
        running["workflow"]["status"] = "running"
        running["stage"]["status"] = "running"
        m13_contracts.write_json(running["workflow_path"], running["workflow"])
        running_ref = self._m5_run_ref(
            running,
            outcome_path=running["output"] / "not-written-yet.json",
        )

        incomplete_result = self._run_m13(
            [valid_ref, running_ref],
            hypotheses=[{
                "hypothesis_id": "structural",
                "scope": "STRUCTURAL_OBSERVATION",
                "label": "A structural event was reported",
                "provenance_ref": "synthetic:test",
            }],
        )
        rows_by_status = {
            row["producer_execution_status_raw"]: row
            for row in incomplete_result["summary"]["runs"]
        }
        self.assertEqual(
            rows_by_status["complete"]["run_import_state"],
            "IMPORTED_WITH_EVENTS",
        )
        self.assertEqual(rows_by_status["running"]["run_import_state"], "INCOMPLETE")
        self.assertGreater(incomplete_result["summary"]["event_count"], 0)
        self.assertEqual(
            incomplete_result["summary"]["summary_completeness"], "PARTIAL"
        )
        self.assertEqual(
            incomplete_result["hypothesis_matrix"]["hypotheses"][0]["evidence_state"],
            "OBSERVED",
        )

        unavailable = self._produce_m5("m5-unavailable-partial", "positive")
        unavailable_ref = self._configure_noncompleted_m5(
            unavailable,
            stage_status="dependency_missing",
            m5_status=dvg_evidence.ANALYSIS_UNAVAILABLE,
        )
        unavailable_result = self._run_m13([valid_ref, unavailable_ref])
        rows_by_status = {
            row["producer_execution_status_raw"]: row
            for row in unavailable_result["summary"]["runs"]
        }
        self.assertEqual(
            rows_by_status["complete"]["run_import_state"],
            "IMPORTED_WITH_EVENTS",
        )
        self.assertEqual(
            rows_by_status["dependency_missing"]["run_import_state"],
            "UNAVAILABLE",
        )
        self.assertGreater(unavailable_result["summary"]["event_count"], 0)
        self.assertEqual(
            unavailable_result["summary"]["summary_completeness"], "PARTIAL"
        )

    def test_execution_reference_integrity_failures_are_typed_by_m13(self):
        cases = (
            "digest",
            "schema",
            "workflow-id",
            "stage-id",
            "missing",
            "corrupt",
        )
        for case in cases:
            with self.subTest(case=case):
                m5 = self._produce_m5(f"m5-integrity-{case}", "positive")
                run = self._configure_noncompleted_m5(
                    m5,
                    stage_status="dependency_missing",
                    m5_status=dvg_evidence.ANALYSIS_UNAVAILABLE,
                )
                record_path = self.root / run["execution_record_ref"]["path"]
                if case == "digest":
                    run["producer_workflow_ref"]["sha256"] = "0" * 64
                    expected_state = "INVALID"
                elif case == "schema":
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                    record["schema"] = "m5-execution-outcome-v0"
                    m13_contracts.write_json(record_path, record)
                    run["execution_record_ref"]["sha256"] = _sha256(record_path)
                    expected_state = "INVALID"
                elif case == "workflow-id":
                    run["producer_workflow_ref"]["workflow_id"] = "wrong-workflow"
                    expected_state = "INVALID"
                elif case == "stage-id":
                    run["producer_stage_id"] = "wrong-stage"
                    expected_state = "INVALID"
                elif case == "missing":
                    record_path.unlink()
                    expected_state = "UNAVAILABLE"
                else:
                    record_path.write_text("{malformed sidecar", encoding="utf-8")
                    expected_state = "INVALID"

                result = self._run_m13([run])
                row = result["summary"]["runs"][0]
                self.assertEqual(row["run_import_state"], expected_state)
                self.assertNotEqual(row["run_import_state"], "IMPORTED_COMPLETED_ZERO")
                self.assertEqual(result["event_index"]["events"], [])

    def test_artifact_digest_version_and_root_containment_failures_are_typed(self):
        for case in ("digest", "version"):
            with self.subTest(case=case):
                m5 = self._produce_m5(f"m5-artifact-{case}", "positive")
                run = self._m5_run_ref(m5)
                evidence_ref = next(
                    ref for ref in run["artifacts"]
                    if ref["artifact_type"] == "dvg_evidence"
                )
                if case == "digest":
                    evidence_ref["sha256"] = "0" * 64
                else:
                    evidence_ref["artifact_contract_version"] = "m5-evidence-v0"
                result = self._run_m13([run])
                self.assertEqual(
                    result["summary"]["runs"][0]["run_import_state"], "INVALID"
                )
                self.assertEqual(result["event_index"]["events"], [])

        m5 = self._produce_m5("m5-artifact-root", "positive")
        run = self._m5_run_ref(m5)
        outside = self.root.parent / f"{self.root.name}-outside-evidence.json"
        evidence_path = (
            Path(run["_source_artifact_root"])
            / next(
                ref["relative_path"] for ref in run["artifacts"]
                if ref["artifact_type"] == "dvg_evidence"
            )
        )
        outside.write_bytes(evidence_path.read_bytes())
        link = self.root / "outside-evidence-link.json"
        link.symlink_to(outside)
        evidence_input = m13_contracts.artifact_input_name(0, "dvg_evidence")
        result = self._run_m13(
            [run],
            input_path_overrides={evidence_input: link.name},
        )
        self.assertEqual(
            result["summary"]["runs"][0]["run_import_state"], "INVALID"
        )
        self.assertEqual(result["event_index"]["events"], [])

    def test_two_same_shaped_runs_keep_distinct_identity_and_provenance(self):
        first = self._produce_m5("m5-same-shape-a", "positive")
        second = self._produce_m5("m5-same-shape-b", "positive")
        first_ref = self._m5_run_ref(first)
        second_ref = self._m5_run_ref(second)
        first_events = json.loads(
            (
                first["output"] / first["stage"]["output_path"] / "evidence.json"
            ).read_text(encoding="utf-8")
        )["events"]
        second_events = json.loads(
            (
                second["output"] / second["stage"]["output_path"] / "evidence.json"
            ).read_text(encoding="utf-8")
        )["events"]
        self.assertEqual(first_events, second_events)

        result = self._run_m13([first_ref, second_ref])
        runs = result["summary"]["runs"]
        self.assertEqual(len(runs), 2)
        self.assertTrue(all(
            row["run_import_state"] == "IMPORTED_WITH_EVENTS" for row in runs
        ))
        run_identities = {
            row["producer_run_manifest_sha256"] for row in runs
        }
        event_identities = {
            (
                event["m5_run_ref"]["producer_run_manifest_sha256"],
                event["m5_run_ref"]["dvg_evidence_sha256"],
                event["source_row_index"],
            )
            for event in result["event_index"]["events"]
        }
        self.assertEqual(len(run_identities), 2)
        self.assertEqual(len(result["event_index"]["events"]), 2)
        self.assertEqual(len(event_identities), 2)
        self.assertEqual(
            {event["m5_run_ref"]["producer_run_manifest_sha256"]
             for event in result["event_index"]["events"]},
            run_identities,
        )

    def test_absent_optional_raw_output_does_not_invalidate_events(self):
        m5 = self._produce_m5("m5-optional-raw", "positive")
        run = self._m5_run_ref(m5)
        raw_type = "dvg_raw_output"
        run["artifacts"] = [
            ref for ref in run["artifacts"]
            if ref["artifact_type"] != raw_type
        ]
        if raw_type in run["artifact_states"]:
            run["artifact_states"][raw_type] = "NOT_PRODUCED"

        result = self._run_m13([run])
        row = result["summary"]["runs"][0]
        self.assertEqual(row["run_import_state"], "IMPORTED_WITH_EVENTS")
        self.assertGreater(row["event_count"], 0)
        self.assertEqual(row["artifact_states"][raw_type], "NOT_PRODUCED")

    def test_m13_cache_is_scoped_and_validated(self):
        m5 = self._produce_m5("m5-cache-scope", "positive")
        run = self._m5_run_ref(m5)
        source_root = Path(run["_source_artifact_root"])
        m5_before = {
            path.relative_to(source_root).as_posix(): _sha256(path)
            for path in source_root.rglob("*")
            if path.is_file()
        }
        m5_workflow_sha_before = _sha256(m5["workflow_path"])
        m5_cache_key = m5["stage"]["cache_key"]
        hypotheses_a = [{
            "hypothesis_id": "structural",
            "scope": "STRUCTURAL_OBSERVATION",
            "label": "Structural observation",
            "provenance_ref": "synthetic:test",
        }]
        first = self._run_m13([run], hypotheses=hypotheses_a)
        original_event_bytes = (first["output"] / "event_index.json").read_bytes()

        unrelated = self.root / "unrelated-nondependency.txt"
        unrelated.write_text("not an M13 input", encoding="utf-8")
        same_inputs = self._run_m13([run], hypotheses=hypotheses_a)
        self.assertEqual(same_inputs["stage"]["cache_key"], first["stage"]["cache_key"])

        hypotheses_b = [{
            "hypothesis_id": "function",
            "scope": "FUNCTION_OR_INTERFERENCE",
            "label": "Function remains unresolved",
            "provenance_ref": "synthetic:test",
        }]
        changed_m13_only = self._run_m13([run], hypotheses=hypotheses_b)
        self.assertNotEqual(
            changed_m13_only["stage"]["cache_key"],
            first["stage"]["cache_key"],
        )
        self.assertNotEqual(
            changed_m13_only["hypothesis_matrix"]["hypotheses"],
            first["hypothesis_matrix"]["hypotheses"],
        )
        m5_workflow_after = json.loads(
            m5["workflow_path"].read_text(encoding="utf-8")
        )
        m5_stage_after = next(
            row for row in m5_workflow_after["stages"] if row["id"] == "dvg"
        )
        self.assertEqual(m5_stage_after["cache_key"], m5_cache_key)
        self.assertEqual(_sha256(m5["workflow_path"]), m5_workflow_sha_before)
        m5_after = {
            path.relative_to(source_root).as_posix(): _sha256(path)
            for path in source_root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(m5_after, m5_before)

        other_m5 = self._produce_m5("m5-cache-upstream-change", "multi")
        changed_upstream = self._run_m13(
            [self._m5_run_ref(other_m5)],
            hypotheses=hypotheses_a,
        )
        self.assertNotEqual(
            changed_upstream["stage"]["cache_key"],
            first["stage"]["cache_key"],
        )

        runtime = reproducibility.environment()
        compatibility_file = Path(artifact_workflow.__file__).with_name(
            "m12_legacy_cache_compatibility.txt"
        )
        compatibility = dict(
            line.split("=", 1)
            for line in compatibility_file.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        identity_compatibility_file = Path(artifact_workflow.__file__).with_name(
            "stage_cache_identity_compatibility.txt"
        )
        identity_compatibility = dict(
            line.split("=", 1)
            for line in identity_compatibility_file.read_text(
                encoding="utf-8"
            ).splitlines()
            if "=" in line
        )
        self.assertEqual(
            m13_stage._source_identity()["source_sha256"],
            identity_compatibility[
                "source.m13_m5_evidence_matrix.legacy_sha256_lf"
            ],
        )
        registry = artifact_workflow.build_default_registry()
        for suffix in ("", "_crlf"):
            package_runtime = {
                **runtime,
                "source_sha256": compatibility[
                    f"accepted_source_sha256{suffix}"
                ],
            }
            legacy_runtime = {
                **runtime,
                "source_sha256": compatibility[
                    f"legacy_source_sha256{suffix}"
                ],
            }
            for kind, definition in registry._stages.items():
                if kind == m13_stage.STAGE_KIND:
                    continue
                stage = {"id": f"cache-isolation-{kind}", "kind": kind}
                before = artifact_workflow._stage_cache_key(
                    stage, definition, {}, {}, legacy_runtime, None
                )
                after = artifact_workflow._stage_cache_key(
                    stage, definition, {}, {}, package_runtime, None
                )
                self.assertEqual(
                    before,
                    after,
                    f"{kind} cache identity changed for source digest {suffix!r}",
                )

        relocated_root = self.root / "relocated"
        relocated_root.mkdir()
        relocated_fixture = relocated_root / "m5-cache-scope"
        shutil.copytree(m5["fixture_root"], relocated_fixture)
        relocated_run = dict(run)
        relocated_run["_source_artifact_root"] = str(
            relocated_fixture / "m5-output" / m5["stage"]["output_path"]
        )
        relocated = self._run_m13(
            [relocated_run],
            hypotheses=hypotheses_a,
            root=relocated_root,
        )
        self.assertEqual(relocated["stage"]["cache_key"], first["stage"]["cache_key"])
        self.assertEqual(
            relocated["bundle"]["stage_cache_context_sha256"],
            first["bundle"]["stage_cache_context_sha256"],
        )

        (first["output"] / "event_index.json").write_text(
            '{"tampered":true}\n',
            encoding="utf-8",
        )
        repaired = self._run_m13([run], hypotheses=hypotheses_a)
        self.assertEqual(repaired["stage"]["cache_key"], first["stage"]["cache_key"])
        self.assertEqual(
            (repaired["output"] / "event_index.json").read_bytes(),
            original_event_bytes,
        )

    def test_m13_source_identity_is_deterministic_and_normalized(self):
        first = m13_stage._source_identity()
        second = m13_stage._source_identity()
        self.assertEqual(first, second)
        self.assertRegex(first["source_sha256"], r"^[0-9a-f]{64}$")

if __name__ == "__main__":
    unittest.main()