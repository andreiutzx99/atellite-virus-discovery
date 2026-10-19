import json
import tempfile
import unittest
from pathlib import Path

from satellite_discovery import m20_phase5


class M20Phase5ReleaseReadinessTests(unittest.TestCase):
    def test_not_evaluated_support_is_classified_as_unavailable_accounting(self):
        support = {
            "status": "NOT_EVALUATED",
            "read_support": [],
            "provenance": {"support_input_fragment_ids": [f"r{i}" for i in range(40)]},
        }
        self.assertTrue(m20_phase5._was_not_evaluated_artifact(
            support, "read_support_evidence",
        ))
        self.assertFalse(m20_phase5._was_not_evaluated_artifact(
            {**support, "status": "NO_SUPPORTED_ASSEMBLY"},
            "read_support_evidence",
        ))
        self.assertFalse(m20_phase5._was_not_evaluated_artifact(
            support, "read_support_table",
        ))

    def test_json_diff_reports_exact_paths_without_normalizing_content(self):
        before = {"qc_artifact": "/old/qc.json", "sha256": "a" * 64, "status": "ok"}
        after = {"qc_artifact": "/new/qc.json", "sha256": "b" * 64, "status": "failed"}
        differences = m20_phase5._leaf_differences(before, after)
        self.assertEqual(
            [item[0] for item in differences],
            ["/qc_artifact", "/sha256", "/status"],
        )
        self.assertEqual(differences[-1][1:], ("ok", "failed"))

    def test_replay_audit_accepts_only_path_bound_metadata_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old, new = root / "phase2b/stages/m4_m6", root / "phase4/m12_workflow"
            old_stage, new_stage = old / "m6_c001", new / "m6_c001"
            old_stage.mkdir(parents=True)
            new_stage.mkdir(parents=True)
            (old_stage / "alignment.sam").write_text(
                f"@PG\\tCL:tool -o {old_stage}/alignment.sam\\n"
                "q1\\t0\\tref\\t1\\t60\\t4M\\t*\\t0\\t0\\tACGT\\t!!!!\\n",
            )
            (new_stage / "alignment.sam").write_text(
                f"@PG\\tCL:tool -o {new_stage}/alignment.sam\\n"
                "q1\\t0\\tref\\t1\\t60\\t4M\\t*\\t0\\t0\\tACGT\\t!!!!\\n",
            )
            old_row = {"id": "m6_c001", "kind": "residual_evidence",
                       "output_path": "m6_c001", "artifacts": {
                           "alignment.sam": {"sha256": "a"},
                       }}
            new_row = {**old_row, "artifacts": {
                "alignment.sam": {"sha256": "b"},
            }}
            (old / "workflow.json").write_text(json.dumps({
                "stages": [old_row],
            }))
            (new / "workflow.json").write_text(json.dumps({
                "stages": [new_row],
            }))
            result = m20_phase5._replay_difference_audit(
                root / "phase2b", root / "phase4", "c001",
            )
            self.assertEqual(result["classification"], "EXPECTED_RUN_PATH_METADATA_WITH_DEPENDENT_DIGEST_CHANGES")
            self.assertEqual(result["unexplained_differences"], [])

    def test_replay_audit_does_not_hide_alignment_record_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            old, new = root / "phase2b/stages/m4_m6", root / "phase4/m12_workflow"
            old_stage, new_stage = old / "m6_c001", new / "m6_c001"
            old_stage.mkdir(parents=True)
            new_stage.mkdir(parents=True)
            header = "@PG\\tCL:tool -o {}\n"
            (old_stage / "alignment.sam").write_text(
                header.format(old_stage) + "q1\t0\tref\t1\t60\t4M\t*\t0\t0\tACGT\t!!!!\n",
            )
            (new_stage / "alignment.sam").write_text(
                header.format(new_stage) + "q1\t0\tref\t1\t60\t4M\t*\t0\t0\tTGCA\t!!!!\n",
            )
            old_row = {"id": "m6_c001", "kind": "residual_evidence",
                       "output_path": "m6_c001", "artifacts": {
                           "alignment.sam": {"sha256": "a"},
                       }}
            new_row = {**old_row, "artifacts": {
                "alignment.sam": {"sha256": "b"},
            }}
            (old / "workflow.json").write_text(json.dumps({"stages": [old_row]}))
            (new / "workflow.json").write_text(json.dumps({"stages": [new_row]}))
            result = m20_phase5._replay_difference_audit(
                root / "phase2b", root / "phase4", "c001",
            )
            self.assertEqual(result["classification"], "UNRESOLVED_CONTENT_DIFFERENCE")

    def test_report_writer_separates_software_from_biology(self):
        report = {
            "decision": "SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED",
            "software_integration_status": "VALIDATED",
            "biological_discovery_status": "NOT_VALIDATED",
            "cases": [],
            "m12_historical_invalid_findings": [],
            "m12_current_invalid_findings": [],
            "limitations": ["M13/M14 are absent."],
        }
        with tempfile.TemporaryDirectory() as temporary:
            m20_phase5.write_report(report, temporary)
            self.assertEqual(
                {p.name for p in Path(temporary).iterdir()},
                {"report.json", "report.md", "report.html"},
            )
            markdown = (Path(temporary) / "report.md").read_text()
            self.assertIn("Biological discovery: **NOT VALIDATED**", markdown)
            self.assertIn("M13/M14 are absent.", markdown)


if __name__ == "__main__":
    unittest.main()
