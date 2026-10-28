import hashlib
import json
import gzip
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import m19_benchmark, m22_synthetic_benchmark


class M22SyntheticBenchmarkTests(unittest.TestCase):
    def test_design_has_blinded_independent_splits_and_requested_diversity(self):
        all_ids = set()
        for split in m22_synthetic_benchmark.SPLITS:
            cases = m22_synthetic_benchmark._cases(split)
            self.assertEqual(8, len(cases))
            self.assertEqual(6, sum(row["positive"] for row in cases))
            self.assertEqual(2, sum(not row["positive"] for row in cases))
            ids = {row["analysis_id"] for row in cases}
            self.assertEqual(8, len(ids))
            all_ids.update(f"{split}:{item}" for item in ids)
            self.assertTrue(all(row["read_start_mode"] == "random" for row in cases))
        self.assertEqual(24, len(all_ids))
        self.assertEqual({500, 650, 700, 750, 800, 900, 1100, 1200},
                         {row["target_length"] for row in m22_synthetic_benchmark._cases("development")})
        self.assertEqual({0.0, 0.02, 0.05},
                         {row["error_rate"] for row in m22_synthetic_benchmark._cases("development")})
        self.assertEqual({0.2, 0.25, 0.5, 0.75},
                         {row["gc_fraction"] for row in m22_synthetic_benchmark._cases("development")})

    def test_generator_is_deterministic_and_keeps_truth_and_labels_out_of_workflow(self):
        cases = m22_synthetic_benchmark._cases("held_out")
        with tempfile.TemporaryDirectory() as folder:
            roots = [Path(folder) / "a", Path(folder) / "b"]
            results = []
            for root in roots:
                with patch.object(m19_benchmark, "CASES", cases), \
                     patch.object(m19_benchmark, "SEED", 220301):
                    results.append(m19_benchmark.generate_inputs(root))
                    workflow = json.dumps(m19_benchmark._workflow_spec())
                self.assertNotIn("held_out-case", workflow)
                self.assertNotIn("candidate_sequence", workflow)
                self.assertNotIn("positive", workflow)
                self.assertNotIn("background_gc_fraction", workflow)
            self.assertEqual(results[0], results[1])
            source, truth = results[0]
            self.assertEqual(8, len(truth["cases"]))
            self.assertNotIn("held_out-case", json.dumps(source))
            reads = gzip.decompress(
                (roots[0] / "datasets/x01/reads.fastq.gz").read_bytes()
            ).decode("ascii")
            headers = [line for line in reads.splitlines() if line.startswith("@")]
            self.assertTrue(headers)
            self.assertTrue(all("-read-" in row for row in headers))
            self.assertFalse(any(
                token in row.lower()
                for row in headers
                for token in ("positive", "negative", "candidate", "reference", "repeat")
            ))

    def test_support_gate_metrics_are_separate_from_exact_and_partial_truth_scoring(self):
        cases = [
            {"positive": True, "candidate_count": 2, "exact_candidate_count": 1,
             "false_positive_candidates": 1,
             "read_supported_candidate_count": 1, "read_supported_exact_candidate_count": 1,
             "read_supported_false_positive_candidates": 0, "exact_recovery": True,
             "partial_recovery": False, "assembler_state": "COMPLETE",
             "assembly_runtime_seconds": 3.0, "configured_memory_mb": 2048,
             "spades_log_reported_memory_mb": 25},
            {"positive": False, "candidate_count": 1, "exact_candidate_count": 0,
             "false_positive_candidates": 1,
             "read_supported_candidate_count": 0, "read_supported_exact_candidate_count": 0,
             "read_supported_false_positive_candidates": 0, "exact_recovery": False,
             "partial_recovery": False, "assembler_state": "COMPLETE",
             "assembly_runtime_seconds": 2.0, "configured_memory_mb": 2048,
             "spades_log_reported_memory_mb": 19},
        ]
        result = m22_synthetic_benchmark.summarize(cases)
        self.assertEqual(2, result["false_positive_candidates"])
        self.assertEqual(0, result["read_supported_false_positive_candidates"])
        self.assertAlmostEqual(1 / 3, result["exact_candidate_precision"])
        self.assertEqual(1.0, result["read_supported_exact_candidate_precision"])
        self.assertFalse(result["spades_log_memory_is_os_rss"])
        self.assertEqual(0.0, m22_synthetic_benchmark._wilson(0, 6)[0])

    def test_original_m19_baseline_input_manifest_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m19_benchmark.generate_inputs(root)
            actual = hashlib.sha256((root / "source_manifest.json").read_bytes()).hexdigest()
        self.assertEqual(
            "fb6d9003164d858534b9f33416f0f9d11dd6aba139eb7e22352b2d7089c3f625",
            actual,
        )


if __name__ == "__main__":
    unittest.main()
