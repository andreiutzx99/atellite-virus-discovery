import tempfile
import unittest
import json
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

    def test_m6_execution_failures_are_counted_as_diagnostics(self):
        metrics = phase8._metrics([{
            "positive": True,
            "status": "COMPLETE",
            "exact_recovered": False,
            "partial_candidate_count": 0,
            "candidate_count": 0,
            "false_positive_candidates": 0,
            "m6_reconstruction_status": "EXECUTION_FAILED",
            "m6_read_support_status": "NOT_EVALUATED",
        }, {
            "positive": False,
            "status": "COMPLETE",
            "exact_recovered": None,
            "partial_candidate_count": None,
            "candidate_count": 0,
            "false_positive_candidates": 0,
            "m6_reconstruction_status": "NO_SUPPORTED_ASSEMBLY",
            "m6_read_support_status": "NO_SUPPORTED_ASSEMBLY",
        }])
        self.assertEqual(1, metrics["reconstruction_execution_failures"])
        self.assertEqual(1, metrics["read_support_not_evaluated_cases"])

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
        failed = [dict(cases[0], m6_reconstruction_status="EXECUTION_FAILED")]
        self.assertNotEqual(first, phase8._signature(source, truth, failed))

    def test_failure_investigation_distinguishes_assembler_failure_and_false_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            stages = run / "stages"
            stages.mkdir()
            ids = ("s02", "s03", "s05")
            (stages / "workflow.json").write_text(json.dumps({
                "stages": [
                    {"id": f"m6_{sample}", "output_path": f"m6_{sample}"}
                    for sample in ids
                ]
            }))
            cases = []
            for sample, case_id in zip(ids, ("high_error", "low_coverage", "high_repeat")):
                directory = stages / f"m6_{sample}"
                directory.mkdir()
                failed = sample != "s05"
                for filename, payload in (
                    ("reconstruction_evidence.json", {
                        "status": "EXECUTION_FAILED" if failed else "NO_SUPPORTED_ASSEMBLY"
                    }),
                    ("read_support.json", {
                        "status": "NOT_EVALUATED" if failed else "NO_SUPPORTED_ASSEMBLY"
                    }),
                    ("candidate_sequence_set.json", {
                        "availability": {
                            "state": "UPSTREAM_UNAVAILABLE" if failed else "AVAILABLE"
                        }
                    }),
                    ("residual_manifest.json", {
                        "counts": {"residual_fragments": 480, "eligible_fragments": 480}
                    }),
                ):
                    (directory / filename).write_text(json.dumps(payload))
                (directory / "assembly" / "raw").mkdir(parents=True)
                if failed:
                    (directory / "assembly" / "raw" / "spades.log").write_text(
                        "0:00.000 ERROR   General Invalid kmer coverage histogram"
                    )
                cases.append({
                    "case_id": case_id,
                    "analysis_id": sample,
                    "candidate_count": 1 if sample == "s05" else 0,
                    "false_positive_candidates": 1 if sample == "s05" else 0,
                    "candidate_alignment_metrics": (
                        [{"identity": 0.7286, "truth_coverage": 0.08}]
                        if sample == "s05" else []
                    ),
                })
            findings = phase8._failure_investigation(run, cases)
            self.assertEqual("ASSEMBLER_EXECUTION_FAILURE", findings[0]["disposition"])
            self.assertIn("Invalid kmer coverage histogram", findings[0]["finding"])
            self.assertEqual(480, findings[1]["assembly_eligible_fragment_count"])
            self.assertEqual("UNSUPPORTED_FALSE_CANDIDATE", findings[2]["disposition"])
            self.assertIn("8.0% target coverage", findings[2]["finding"])

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
