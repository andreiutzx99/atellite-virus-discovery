import random
import tempfile
import unittest
from pathlib import Path

from satellite_discovery.m25_read_coverage import (
    _stage_evaluation,
    _classification,
    _make_starts,
    _theory,
    coverage_summary,
)


class M25ReadCoverageTests(unittest.TestCase):
    def test_missing_stage_output_is_not_measured_as_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "residual.fastq.gz"
            self.assertEqual(_stage_evaluation(output, "failed"), "FAILED")
            self.assertEqual(_stage_evaluation(output, "complete"), "OUTPUT_MISSING")
            self.assertEqual(_stage_evaluation(output), "NOT_EVALUATED")
            output.write_bytes(b"")
            self.assertEqual(_stage_evaluation(output, "complete"), "COMPLETE")

    def test_uniform_start_model_has_correct_edge_probabilities(self):
        model = _theory(10, 4, 1)
        self.assertAlmostEqual(model["first_base_covered_probability"], 1 / 7)
        self.assertAlmostEqual(model["last_base_covered_probability"], 1 / 7)
        self.assertAlmostEqual(model["both_ends_covered_probability"], 0)
        self.assertAlmostEqual(model["expected_target_coverage"], 4 / 10)
        self.assertAlmostEqual(model["maximum_single_base_coverage_probability"], 4 / 7)

    def test_coverage_summary_distinguishes_depth_from_completeness(self):
        summary = coverage_summary("A" * 12, [0, 4], 4, [0, 1])
        self.assertEqual(summary["nominal_depth"], 8 / 12)
        self.assertEqual(summary["first_base_depth"], 1)
        self.assertEqual(summary["last_base_depth"], 0)
        self.assertEqual(summary["coverage_gaps"], 4)
        self.assertEqual(summary["read_error_bases"], 1)
        self.assertEqual(_classification(summary), "COVERAGE_INSUFFICIENT")

    def test_terminal_enrichment_covers_both_ends_by_design(self):
        starts = _make_starts(500, 100, 16, "terminal_enriched", random.Random(4))
        metrics = coverage_summary("A" * 500, starts, 100)
        self.assertIn(0, starts)
        self.assertIn(400, starts)
        self.assertGreaterEqual(metrics["terminal_5_independent_reads"], 1)
        self.assertGreaterEqual(metrics["terminal_3_independent_reads"], 1)

    def test_uniform_sampling_is_deterministic_and_bounded(self):
        a = _make_starts(900, 100, 48, "uniform", random.Random(1))
        b = _make_starts(900, 100, 48, "uniform", random.Random(9))
        self.assertEqual(a, b)
        self.assertEqual(a[0], 0)
        self.assertEqual(a[-1], 800)


if __name__ == "__main__":
    unittest.main()
