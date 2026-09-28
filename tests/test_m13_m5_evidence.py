import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import test_dvg_workflow as dvg_workflow_tests

from satellite_discovery import m13_contracts, m13_stage
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

    def _run_m13(self, runs, *, hypotheses=None):
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
        input_path = self.root / "m13-input.json"
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
                    "path": source_path.relative_to(self.root).as_posix(),
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
        spec_path = self.root / "m13-workflow.json"
        m13_contracts.write_json(spec_path, workflow_spec)
        output = self.root / "m13-output"
        run_workflow(spec_path, output)
        workflow = json.loads(
            (output / "workflow.json").read_text(encoding="utf-8")
        )
        stage = next(row for row in workflow["stages"] if row["id"] == "m13")
        self.assertEqual(stage["status"], "complete", stage.get("error"))
        output_root = output / stage["output_path"]
        return {
            "workflow": workflow,
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
        self.assertEqual(
            [event["source_row_index"] for event in events],
            list(range(len(source_events))),
        )
        event = events[0]
        self.assertEqual(
            event["m5_run_ref"]["producer_run_manifest_sha256"],
            result["summary"]["runs"][0]["producer_run_manifest_sha256"],
        )
        matrix = {
            row["hypothesis_id"]: row
            for row in result["hypothesis_matrix"]["hypotheses"]
        }
        self.assertEqual(matrix["structural"]["evidence_state"], "OBSERVED")
        self.assertEqual(matrix["function"]["evidence_state"], "UNRESOLVED")
        self.assertEqual(matrix["function"]["evidence_refs"], [])

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
                self.assertEqual(row["run_import_state"], import_state)
                self.assertEqual(row["outcome_code"], outcome_code)
                self.assertEqual(result["event_index"]["events"], [])

if __name__ == "__main__":
    unittest.main()