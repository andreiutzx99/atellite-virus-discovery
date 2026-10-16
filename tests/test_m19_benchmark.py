import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import m19_benchmark


class M19BenchmarkTests(unittest.TestCase):
    @staticmethod
    def _blocked_runner(spec_path, output_path, _registry, status="blocked"):
        spec = json.loads(Path(spec_path).read_text())
        stages = []
        for stage in spec["stages"]:
            row = {"id": stage["id"], "status": "complete" if stage["kind"] == "fastq_qc" else status}
            if stage["kind"] != "fastq_qc":
                row.update(reason="Simulated M6 dependency is unavailable.")
            stages.append(row)
        root = Path(output_path)
        root.mkdir(parents=True, exist_ok=True)
        (root / "workflow.json").write_text(json.dumps({
            "status": "dependency_missing" if status == "dependency_missing" else "incomplete",
            "stages": stages,
        }))

    def test_controlled_matrix_and_truth_are_deterministic_and_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = Path(folder) / "a", Path(folder) / "b"
            source1, truth1 = m19_benchmark.generate_inputs(first)
            source2, truth2 = m19_benchmark.generate_inputs(second)
            self.assertEqual(source1, source2)
            self.assertEqual(truth1, truth2)
            self.assertEqual(6, len(truth1["cases"]))
            ids = {row["case_id"] for row in truth1["cases"]}
            self.assertEqual(ids, {row["case_id"] for row in m19_benchmark.CASES})
            self.assertIn("high_error", ids)
            self.assertIn("low_coverage", ids)
            self.assertIn("high_divergence", ids)
            self.assertIn("high_repeat", ids)
            spec = m19_benchmark._workflow_spec()
            self.assertNotIn("candidate_sequence", json.dumps(spec))
            self.assertNotIn("heldout_truth", json.dumps(spec))
            self.assertFalse((first / "heldout_truth.json").exists())

    def test_exact_scoring_reports_recovery_and_false_positives(self):
        truth = "ACGT" * 20
        metrics = m19_benchmark.score_sequences(truth, [truth.lower(), "N" * len(truth)])
        self.assertEqual(1, metrics["recovered_true_candidates"])
        self.assertEqual(1, metrics["false_positive_candidates"])
        self.assertEqual(0.5, metrics["false_discovery_fraction"])
        negative = m19_benchmark.score_sequences(None, ["ACGT"])
        self.assertIsNone(negative["recovery_rate"])
        self.assertEqual(1, negative["false_positive_candidates"])

    def test_blocked_m6_writes_reports_and_keeps_metrics_unevaluated(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "m19"
            report = m19_benchmark.run(output, runner=self._blocked_runner)
            self.assertEqual("INCOMPLETE", report["benchmark_status"])
            self.assertEqual(6, len(report["cases"]))
            for case in report["cases"]:
                self.assertEqual("BLOCKED", case["status"])
                self.assertEqual("blocked", case["m4_stage_status"])
                self.assertIsNone(case["recovered_true_candidates"])
                self.assertIsNone(case["false_positive_candidates"])
                self.assertIn("Simulated M6 dependency", case["m4_error"])
            self.assertTrue((output / "m19-report.json").is_file())
            self.assertIn("INCOMPLETE", (output / "m19-report.html").read_text())

    def test_cli_nonzero_for_unavailable_m6(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "m19"
            with patch.object(
                m19_benchmark.artifact_workflow, "run",
                side_effect=lambda spec, out, reg: self._blocked_runner(
                    spec, out, reg, status="dependency_missing"
                ),
            ):
                self.assertEqual(2, m19_benchmark.main(["--output", str(output)]))

    def test_exception_before_manifest_refresh_ignores_stale_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "m19"
            stages = output / "stages"
            stages.mkdir(parents=True)
            (stages / "workflow.json").write_text(json.dumps({
                "status": "complete",
                "stages": [{"id": "m6_baseline", "status": "complete", "output_path": "old-run"}],
            }))
            def fail_before_refresh(_spec, _output, _registry):
                raise RuntimeError("simulated failure before a fresh manifest")
            report = m19_benchmark.run(output, runner=fail_before_refresh)
            self.assertEqual("execution_error", report["workflow_status"])
            self.assertTrue(report["execution_error"]["stale_manifest_ignored"])
            self.assertTrue(all(row["status"] == "UNAVAILABLE" for row in report["cases"]))
            self.assertTrue(all(row["recovered_true_candidates"] is None for row in report["cases"]))

    def test_changed_synthetic_input_is_not_silently_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m19_benchmark.generate_inputs(root)
            target = root / "datasets/baseline/reads.fastq.gz"
            target.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "overwrite changed M19 input"):
                m19_benchmark.generate_inputs(root)


@unittest.skipUnless(os.environ.get("RUN_OPTIONAL_TOOL_TESTS") == "1",
                     "Optional minimap2/SPAdes benchmark integration")
class M19LiveBenchmarkTests(unittest.TestCase):
    def test_registered_m6_benchmark_runs_with_optional_tools(self):
        if not shutil.which("minimap2") or not (shutil.which("spades.py") or shutil.which("spades")):
            self.skipTest("minimap2 or SPAdes is unavailable")
        with tempfile.TemporaryDirectory(prefix="m19-live-") as folder:
            report = m19_benchmark.run(Path(folder) / "m19")
            self.assertEqual("COMPLETE", report["benchmark_status"])
            self.assertEqual(6, len(report["cases"]))
            self.assertTrue(all(row["status"] == "COMPLETE" for row in report["cases"]))
            for row in report["cases"]:
                self.assertIsInstance(row["predicted_candidate_count"], int)
                self.assertIsInstance(row["false_positive_candidates"], int)
            rows = {row["case_id"]: row for row in report["cases"]}
            self.assertEqual(1, rows["baseline"]["recovered_true_candidates"])
            self.assertIsNone(rows["negative_control"]["recovery_rate"])
            self.assertTrue((Path(folder) / "m19/m19-report.json").is_file())
