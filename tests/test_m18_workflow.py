import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import m18_workflow


class M18FixtureTests(unittest.TestCase):
    @staticmethod
    def _mock_m4_failure(spec_path, output_path, _registry, *, missing_m6_artifacts=False,
                         missing_artifact_stage_ids=(), raise_after_manifest=False):
        spec = json.loads(Path(spec_path).read_text())
        output_path = Path(output_path)
        missing_artifact_stage_ids = set(missing_artifact_stage_ids)
        stages = []
        for stage in spec["stages"]:
            row = {"id": stage["id"]}
            if stage["id"] in missing_artifact_stage_ids:
                row.update(status="complete", output_path=f"simulated/{stage['id']}")
            elif stage["kind"] == "fastq_qc":
                row.update(status="complete", output_path=f"simulated/{stage['id']}")
                qc_dir = output_path / row["output_path"]
                qc_dir.mkdir(parents=True, exist_ok=True)
                (qc_dir / "qc.json").write_text(json.dumps({
                    "before": {"reads": 3}, "after": {"reads": 3},
                    "counts": {"rejected_reads": 0},
                }))
            elif stage["kind"] == "residual_evidence":
                if missing_m6_artifacts:
                    row.update(status="complete", output_path=f"simulated/{stage['id']}")
                else:
                    row.update(
                        status="dependency_missing",
                        error={"code": "DEPENDENCY_MISSING", "message": "SPAdes is unavailable"},
                        reason="Required optional assembler was not found.",
                    )
            else:
                row.update(status="blocked", reason="Blocked by unavailable M6 output.")
            stages.append(row)
        manifest = {
            "schema": "artifact-workflow-v1",
            "status": "incomplete" if missing_m6_artifacts else "dependency_missing",
            "stages": stages,
        }
        output_path.mkdir(parents=True, exist_ok=True)
        (output_path / "workflow.json").write_text(json.dumps(manifest))
        if raise_after_manifest:
            raise RuntimeError("simulated interruption after M4 manifest write")

    def test_dependency_failure_preserves_m4_errors_and_does_not_invent_findings(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "m18"
            with patch.object(
                m18_workflow.artifact_workflow, "run",
                side_effect=lambda spec, out, registry: self._mock_m4_failure(
                    spec, out, registry, raise_after_manifest=True
                ),
            ):
                report = m18_workflow.run(output)
            self.assertEqual("dependency_missing", report["workflow_status"])
            self.assertEqual("INCOMPLETE", report["integration_status"])
            self.assertEqual("RuntimeError", report["execution_error"]["type"])
            cli_output = Path(folder) / "cli-run"
            with patch.object(
                m18_workflow.artifact_workflow, "run",
                side_effect=lambda spec, out, registry: self._mock_m4_failure(
                    spec, out, registry, raise_after_manifest=True
                ),
            ):
                self.assertEqual(2, m18_workflow.main(["--output", str(cli_output)]))
            saved = json.loads((cli_output / "m18-report.json").read_text())
            self.assertEqual("dependency_missing", saved["workflow_status"])
            self.assertEqual("INCOMPLETE", saved["integration_status"])
            self.assertEqual("RuntimeError", saved["execution_error"]["type"])
            for case in saved["cases"]:
                self.assertEqual("dependency_missing", case["m4_stage_statuses"]["m6"])
                diagnostic = case["stage_diagnostics"]["m6"]
                self.assertEqual("DEPENDENCY_MISSING", diagnostic["error"]["code"])
                self.assertEqual("Required optional assembler was not found.", diagnostic["reason"])
                self.assertEqual("UNAVAILABLE", case["assembly_and_read_back"]["candidate_availability"])
                self.assertIsNone(case["assembly_and_read_back"]["candidate_count"])
                self.assertIsNone(case["reference_screening"]["residual_fragments"])
                self.assertEqual("BLOCKED", case["m9_orf_evidence"]["aggregate_status"])
                self.assertIsNone(case["m9_orf_evidence"]["observed_orf_count"])
                self.assertEqual("BLOCKED", case["m10_architecture_evidence"]["aggregate_status"])
                self.assertIsNone(case["m10_architecture_evidence"]["candidate_count"])
                self.assertIsNone(case["m10_architecture_evidence"]["branch_statuses"])
            self.assertTrue((output / "m18-report.html").is_file())
            self.assertIn("INCOMPLETE", (output / "m18-report.html").read_text())

    def test_complete_m4_stage_with_missing_required_artifacts_is_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "m18"
            with patch.object(
                m18_workflow.artifact_workflow, "run",
                side_effect=lambda spec, out, registry: self._mock_m4_failure(
                    spec, out, registry, missing_m6_artifacts=True
                ),
            ):
                report = m18_workflow.run(output)
            case = next(row for row in report["cases"] if row["case_id"] == "rna_supported")
            self.assertEqual("complete", case["m4_stage_statuses"]["m6"])
            diagnostic = case["stage_diagnostics"]["m6"]
            self.assertEqual("INCOMPLETE", diagnostic["report_status"])
            self.assertIn("candidate_sequence_set.json", diagnostic["missing_artifacts"])
            self.assertIsNone(case["assembly_and_read_back"]["candidate_count"])
            self.assertIsNone(case["m9_orf_evidence"]["candidate_count"])
            self.assertIsNone(case["m10_architecture_evidence"]["candidate_count"])

    def test_missing_qc_m9_and_m10_artifacts_are_not_read_as_empty_results(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "m18"
            missing = {
                "qc_rna_supported", "m9_rna_supported", "m10_rna_supported",
            }
            with patch.object(
                m18_workflow.artifact_workflow, "run",
                side_effect=lambda spec, out, registry: self._mock_m4_failure(
                    spec, out, registry, missing_artifact_stage_ids=missing
                ),
            ):
                report = m18_workflow.run(output)
            case = next(row for row in report["cases"] if row["case_id"] == "rna_supported")
            self.assertEqual("INCOMPLETE", case["stage_diagnostics"]["qc"]["report_status"])
            self.assertIsNone(case["qc"]["input_reads"])
            self.assertEqual("INCOMPLETE", case["stage_diagnostics"]["m9"]["report_status"])
            self.assertIsNone(case["m9_orf_evidence"]["observed_orf_count"])
            self.assertEqual("INCOMPLETE", case["stage_diagnostics"]["m10"]["report_status"])
            self.assertIsNone(case["m10_architecture_evidence"]["candidate_count"])

    def test_stale_m4_manifest_is_ignored_after_runner_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "m18"
            stages_root = output / "stages"
            stages_root.mkdir(parents=True)
            stale_manifest = {"status": "complete", "stages": [{
                "id": "m6_rna_supported", "status": "complete",
                "output_path": "stale-success",
            }]}
            (stages_root / "workflow.json").write_text(json.dumps(stale_manifest))
            with patch.object(
                m18_workflow.artifact_workflow, "run",
                side_effect=RuntimeError("failed before replacing prior manifest"),
            ):
                report = m18_workflow.run(output)
            self.assertEqual("execution_error", report["workflow_status"])
            self.assertTrue(report["execution_error"]["stale_manifest_ignored"])
            case = next(row for row in report["cases"] if row["case_id"] == "rna_supported")
            self.assertEqual("UNAVAILABLE", case["m4_stage_statuses"]["m6"])
            self.assertIsNone(case["assembly_and_read_back"]["candidate_count"])

    def test_fixture_generation_is_deterministic_and_guarded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "first", root / "second"
            m18_workflow.generate_fixture_bundle(first)
            m18_workflow.generate_fixture_bundle(second)
            paths = sorted(path.relative_to(first) for path in first.rglob("*") if path.is_file())
            self.assertEqual(
                {str(path): (first / path).read_bytes() for path in paths},
                {str(path): (second / path).read_bytes() for path in paths},
            )
            source = m18_workflow.validate_fixture_bundle(first)
            self.assertTrue(source["synthetic_only"])
            self.assertEqual(12, len(source["files"]))
            truth = json.loads((first / "fixture_truth.json").read_text())
            self.assertEqual({"RNA", "DNA"}, {case["pathway"] for case in truth["cases"]})
            self.assertEqual(4, len(truth["cases"]))
            self.assertFalse((first / "fixture_truth.json").resolve().is_relative_to(
                (first / "datasets").resolve()
            ))

    def test_provenance_manifest_cannot_self_attest_altered_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m18_workflow.generate_fixture_bundle(root)
            read_path = root / "datasets/rna_supported/reads.fastq.gz"
            read_path.write_bytes(b"not the deterministic fixture")
            with self.assertRaisesRegex(ValueError, "altered fixture bytes"):
                m18_workflow.validate_fixture_bundle(root)

    def test_workflow_graph_uses_registered_stages_and_excludes_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m18_workflow._build_workflow(root)
            specification = json.loads((root / "m18-workflow.json").read_text())
            self.assertEqual(16, len(specification["stages"]))
            kinds = [stage["kind"] for stage in specification["stages"]]
            self.assertEqual(4, kinds.count("fastq_qc"))
            self.assertEqual(4, kinds.count("residual_evidence"))
            self.assertEqual(4, kinds.count("m9_orf_translation"))
            self.assertEqual(4, kinds.count("m10_exact_first"))
            encoded = json.dumps(specification)
            self.assertNotIn("fixture_truth", encoded)
            self.assertNotIn("scenario_label", encoded)
            for stage in specification["stages"]:
                if stage["kind"] == "residual_evidence":
                    self.assertEqual("fastq_qc", next(
                        row["kind"] for row in specification["stages"]
                        if row["id"] == stage["inputs"]["read1"]["stage"]
                    ))
                    self.assertEqual("candidate_sequence_set.json",
                                     next(row for row in specification["stages"]
                                          if row["id"] == f"m9_{stage['config']['sample_id']}")
                                     ["inputs"]["candidate_sequence_set"]["artifact"])


@unittest.skipUnless(os.environ.get("RUN_OPTIONAL_TOOL_TESTS") == "1",
                     "Optional live minimap2/SPAdes integration job")
class M18LiveWorkflowTests(unittest.TestCase):
    def test_real_registered_qc_m6_m9_m10_graph(self):
        if not shutil.which("minimap2") or not (shutil.which("spades.py") or shutil.which("spades")):
            self.skipTest("minimap2 or SPAdes is unavailable")
        with tempfile.TemporaryDirectory(prefix="m18-live-") as folder:
            report = m18_workflow.run(Path(folder) / "m18")
            self.assertEqual("complete", report["workflow_status"])
            self.assertEqual("COMPLETE", report["integration_status"])
            cases = {case["case_id"]: case for case in report["cases"]}
            for case_id in ("rna_supported", "dna_supported"):
                row = cases[case_id]
                self.assertNotIn("stage_diagnostics", row)
                self.assertEqual("AVAILABLE", row["assembly_and_read_back"]["candidate_availability"])
                self.assertEqual(["READ_SUPPORTED_ASSEMBLY"],
                                 row["assembly_and_read_back"]["candidate_support_statuses"])
                self.assertEqual("COMPLETE", row["m9_orf_evidence"]["aggregate_status"])
                self.assertEqual(1, row["m10_architecture_evidence"]["candidate_count"])
            self.assertEqual("UPSTREAM_UNAVAILABLE",
                             cases["rna_reference_only"]["assembly_and_read_back"]["candidate_availability"])
            low_support = cases["dna_insufficient_support"]["assembly_and_read_back"]
            self.assertEqual("AVAILABLE", low_support["candidate_availability"])
            self.assertEqual(["LOW_SUPPORT_ASSEMBLY"], low_support["candidate_support_statuses"])
            self.assertEqual(1000, low_support["support_thresholds"]["min_distinct_fragments"])
            self.assertGreaterEqual(cases["rna_supported"]["qc"]["rejected_reads"], 2)
            self.assertNotIn("execution_error", report)


if __name__ == "__main__":
    unittest.main()
