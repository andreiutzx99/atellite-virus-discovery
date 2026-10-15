import json
from pathlib import Path
import tempfile
import unittest

from satellite_discovery import artifact_contracts
from satellite_discovery.m17_workflow import (
    M10_BRANCHES, SCENARIOS, _m10_scope_result, generate_fixture_bundle, run,
)


class M17WorkflowTests(unittest.TestCase):
    def test_no_signal_state_requires_every_m10_branch_to_complete(self):
        branches = {
            branch: {
                "branch_status": "COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY",
                "evidence_status": "NO_EVIDENCE_REPORTED",
            }
            for branch in M10_BRANCHES
        }
        self.assertEqual(
            _m10_scope_result("syn-candidate-test", branches)["scope_state"],
            "NO_SIGNAL_WITHIN_TESTED_M10_SCOPE",
        )
        incomplete = dict(branches)
        incomplete.pop(M10_BRANCHES[-1])
        self.assertEqual(
            _m10_scope_result("syn-candidate-test", incomplete)["scope_state"],
            "INCOMPLETE_OR_UNRESOLVED",
        )

    def test_deterministic_synthetic_bundle_and_existing_typed_m9_m10_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = generate_fixture_bundle(root / "a")
            second = generate_fixture_bundle(root / "b")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            report = run(root / "run")
            self.assertTrue(report["synthetic_only"])
            self.assertEqual(report["candidate_count"], len(SCENARIOS))
            self.assertEqual(report["workflow_status"], "complete")
            self.assertEqual(
                [stage["status"] for stage in report["stages"]],
                ["complete", "complete"],
            )
            workflow = json.loads((root / "run" / "stages" / "workflow.json").read_text())
            self.assertEqual(workflow["stage_graph"], [{
                "from_stage": "m9_orfs", "artifact": "orf_results.json",
                "artifact_type": "m9_orf_results", "to_stage": "m10_architecture",
                "input": "m9_orf_results",
            }])
            by_id = {stage["id"]: stage for stage in workflow["stages"]}
            m9_output = root / "run" / "stages" / by_id["m9_orfs"]["output_path"]
            m10_output = root / "run" / "stages" / by_id["m10_architecture"]["output_path"]
            artifact_contracts.validate_artifact(
                m9_output / "orf_results.json", "m9_orf_results")
            artifact_contracts.validate_artifact(
                m10_output / "m10_bundle.json", "m10_result_bundle")
            self.assertEqual(
                workflow["output_artifacts"]["m9_orfs.orf_results.json"]["artifact_type"],
                "m9_orf_results",
            )
            self.assertTrue(
                workflow["output_artifacts"]["m9_orfs.orf_results.json"]["sha256"])
            self.assertEqual(
                workflow["output_artifacts"]["m10_architecture.m10_bundle.json"]["artifact_type"],
                "m10_result_bundle",
            )
            self.assertTrue(all(
                item["candidate_id"].startswith("syn-candidate-")
                for item in report["candidate_scope_results"]
            ))
            self.assertEqual(len(report["candidate_scope_results"]), len(SCENARIOS))
            truth = json.loads((root / "run" / "inputs" / "fixture_truth.json").read_text())
            self.assertTrue(all("scenario_label" in item for item in truth["scenarios"]))
            self.assertTrue(all(
                "scenario_label" not in item for item in
                json.loads((root / "run" / "inputs" / "candidate_sequence_set.json").read_text())["records"]
            ))
            output = root / "run" / "m17-report.json"
            self.assertTrue(output.is_file())
            self.assertTrue((root / "run" / "m17-report.html").is_file())
            run(root / "run")
            resumed = json.loads((root / "run" / "stages" / "workflow.json").read_text())
            self.assertEqual(
                [stage["execution"] for stage in resumed["stages"]],
                ["verified_reuse", "verified_reuse"],
            )

    def test_report_is_reproducible_and_truth_labels_are_not_inferred(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = run(root / "first")
            second = run(root / "second")
            self.assertEqual(
                (root / "first" / "m17-report.json").read_bytes(),
                (root / "second" / "m17-report.json").read_bytes(),
            )
            truth = json.loads(
                (root / "first" / "inputs" / "fixture_truth.json").read_text()
            )
            self.assertTrue(truth["synthetic_only"])
            self.assertIn("not pipeline inferences", truth["warning"])
            self.assertEqual(first["unimplemented_or_unavailable"],
                             second["unimplemented_or_unavailable"])
            self.assertTrue(first["input_sha256"])

    def test_fixture_regeneration_refuses_to_overwrite_modified_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "fixtures"
            candidate = generate_fixture_bundle(root)
            changed = b"user-modified fixture\n"
            candidate.write_bytes(changed)
            with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
                generate_fixture_bundle(root)
            self.assertEqual(candidate.read_bytes(), changed)


if __name__ == "__main__":
    unittest.main()
