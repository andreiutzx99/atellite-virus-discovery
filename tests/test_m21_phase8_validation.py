import tempfile
import unittest
from pathlib import Path

from satellite_discovery import m21_phase8_validation as phase8


class Phase8ValidationTests(unittest.TestCase):
    def test_local_alignment_reports_exact_and_partial_sequence_metrics(self):
        exact = phase8._best_local_alignment("ACGTACGT", "ACGTACGT")
        self.assertEqual(1.0, exact["identity"])
        self.assertEqual(1.0, exact["truth_coverage"])

        partial = phase8._best_local_alignment("ACGTACGT", "ACGT")
        self.assertEqual(1.0, partial["identity"])
        self.assertEqual(0.5, partial["truth_coverage"])
        self.assertGreater(partial["aligned_columns"], 0)

    def test_nonmatching_sequence_has_no_reported_identity_without_alignment(self):
        metrics = phase8._best_local_alignment("AAAAAAAA", "TTTTTTTT")
        self.assertEqual(0.0, metrics["identity"])
        self.assertEqual(0.0, metrics["truth_coverage"])
        self.assertEqual(0, metrics["aligned_columns"])

    def test_metrics_separate_exact_recovery_partial_and_negative_controls(self):
        rows = [
            {
                "positive": True,
                "status": "COMPLETE",
                "exact_recovered": True,
                "partial_candidate_count": 0,
                "candidate_count": 1,
                "false_positive_candidates": 0,
            },
            {
                "positive": True,
                "status": "COMPLETE",
                "exact_recovered": False,
                "partial_candidate_count": 1,
                "candidate_count": 1,
                "false_positive_candidates": 1,
            },
            {
                "positive": False,
                "status": "COMPLETE",
                "exact_recovered": None,
                "partial_candidate_count": None,
                "candidate_count": 0,
                "false_positive_candidates": 0,
            },
        ]
        metrics = phase8._metrics(rows)
        self.assertEqual(2, metrics["detected_positive_cases"])
        self.assertEqual(1.0, metrics["synthetic_detection_rate"])
        self.assertEqual(0.5, metrics["exact_recovery_rate"])
        self.assertEqual(1, metrics["partial_recovery_cases"])
        self.assertEqual(0.5, metrics["candidate_precision"])
        self.assertEqual(1.0, metrics["negative_control_specificity"])
        self.assertEqual(0, metrics["false_positive_negative_controls"])
        self.assertEqual("DESCRIPTIVE_SYNTHETIC_ONLY", metrics["performance_claim_status"])

    def test_incomplete_negative_control_keeps_metrics_unevaluated(self):
        rows = [
            {
                "positive": True,
                "status": "COMPLETE",
                "exact_recovered": True,
                "partial_candidate_count": 0,
                "candidate_count": 1,
                "false_positive_candidates": 0,
            },
            {
                "positive": False,
                "status": "UNAVAILABLE",
                "exact_recovered": None,
                "partial_candidate_count": None,
                "candidate_count": None,
                "false_positive_candidates": None,
            },
        ]
        metrics = phase8._metrics(rows)
        self.assertIsNone(metrics["negative_control_specificity"])
        self.assertEqual("NOT_VALIDATED", metrics["performance_claim_status"])

    def test_semantic_signature_changes_when_predictions_change(self):
        source = {"seed": 1}
        truth = {"cases": [{"candidate_sequence": "ACGT"}]}
        cases = [{
            "case_id": "synthetic-1",
            "status": "COMPLETE",
            "exact_recovered": True,
            "partial_candidate_count": 0,
            "candidate_count": 1,
            "candidate_alignment_metrics": [{"identity": 1.0, "truth_coverage": 1.0}],
            "candidate_sequence_sha256": ["known-digest"],
            "false_positive_candidates": 0,
        }]
        first = phase8._signature(source, truth, cases)
        changed = [dict(cases[0], candidate_sequence_sha256=["different-digest"])]
        self.assertNotEqual(first, phase8._signature(source, truth, changed))

    def test_safe_artifact_resolution_rejects_parent_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "run"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "escapes"):
                phase8._safe_child(root, "../outside")

    def test_markdown_report_names_scope_and_fail_closed_status(self):
        report = {
            "phase8_status": "INCOMPLETE",
            "executive_summary": "Synthetic result summary.",
            "existing_pipeline": "M4 QC -> M6 evidence",
            "software_pipeline_status": "M4_M6_COMPLETE",
            "cases": [],
            "metrics": {"performance_claim_status": "DESCRIPTIVE_SYNTHETIC_ONLY"},
            "reproducibility": {"verified": True, "signature": "abc123"},
            "improvements_implemented": ["Partial sequence metrics."],
            "recommendation_dispositions": [
                {"status": "DEFERRED", "recommendation": "Candidate classification."}
            ],
            "acceptance": {"ci_passed": None},
            "limitations": ["One synthetic negative control."],
        }
        markdown = phase8._markdown(report)
        self.assertIn("## Executive summary", markdown)
        self.assertIn("## Pipeline status", markdown)
        self.assertIn("## Recommendation disposition", markdown)
        self.assertIn("Phase 8 technical acceptance is not claimed", markdown)


if __name__ == "__main__":
    unittest.main()
