import json
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m34_negative_control_indel_robustness import (
    ERROR_CONDITIONS,
    NEGATIVE_CATEGORIES,
    _metrics,
    _panel_content_signature,
    _validate_target_absence_truth,
    preregistered_design,
    render_markdown,
)


class M34DesignTests(unittest.TestCase):
    def test_design_registers_at_least_thirty_truth_absent_cases_blindly(self):
        design = preregistered_design(5)
        negatives = [case for case in design["cases"]
                     if case["case_id"] in design["category_by_id"]]
        self.assertEqual(len(negatives), 40)
        self.assertEqual(set(design["category_by_id"].values()),
                         set(NEGATIVE_CATEGORIES))
        self.assertEqual(len(set(design["seed_by_id"].values())),
                         len(design["seed_by_id"]))
        for case in negatives:
            self.assertFalse(case["positive"])
            self.assertNotIn(design["category_by_id"][case["case_id"]],
                             case["case_id"])
            self.assertTrue(case["analysis_id"].startswith("m34x"))

    def test_indel_matrix_covers_all_error_modes_and_multiple_depths_lengths(self):
        design = preregistered_design(1)
        self.assertEqual(len(design["indel_cases"]), len(ERROR_CONDITIONS))
        self.assertEqual(
            {case["error_rate"] for case in design["indel_cases"]}, {0, .01, .02, .05}
        )
        self.assertEqual(
            {case["insertion_rate"] for case in design["indel_cases"]}, {0, .005, .01, .03}
        )
        self.assertEqual(
            {case["deletion_rate"] for case in design["indel_cases"]}, {0, .005, .01, .03}
        )
        self.assertGreater(len({case["coverage"] for case in design["indel_cases"]}), 1)
        self.assertGreater(len({case["m25_read_length"] for case in design["indel_cases"]}), 1)

    def test_each_negative_background_spans_all_preregistered_error_conditions(self):
        design = preregistered_design(8)
        for category in NEGATIVE_CATEGORIES:
            case_ids = [cid for cid, value in design["category_by_id"].items()
                        if value == category]
            self.assertEqual(
                {design["negative_condition_by_id"][cid] for cid in case_ids},
                {row[0] for row in ERROR_CONDITIONS},
            )


class M34FalseAlarmTests(unittest.TestCase):
    def test_panel_comparison_uses_content_not_context_bound_snapshot_digest(self):
        full = {"panel_preregistration": {
            "schema": "m32-panel-v1", "seed": 10, "panel_fasta_sha256": "same",
            "records": [{"accession": "SYN001.1"}], "design_digest": "full",
            "snapshot_digest": "snapshot-full",
        }}
        repeat = {"panel_preregistration": {
            **full["panel_preregistration"], "design_digest": "repeat",
            "snapshot_digest": "snapshot-repeat",
        }}
        self.assertEqual(_panel_content_signature(full), _panel_content_signature(repeat))
        repeat["panel_preregistration"]["panel_fasta_sha256"] = "different"
        self.assertNotEqual(_panel_content_signature(full), _panel_content_signature(repeat))

    def test_target_absence_is_verified_from_registered_source_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            case = {"case_id": "held_out-m34-c0001", "positive": False}
            truth_path = Path(folder) / "reconstruction" / case["case_id"] / "heldout_truth.json"
            truth_path.parent.mkdir(parents=True)
            truth_path.write_text(json.dumps({"cases": [{"candidate_sequence": None}]}))
            result = _validate_target_absence_truth(folder, [case])
            self.assertEqual(result["status"], "VERIFIED")
            self.assertEqual(result["case_count"], 1)
            truth_path.write_text(json.dumps({"cases": [{"candidate_sequence": "ACGT"}]}))
            with self.assertRaisesRegex(RuntimeError, "source truth contains a target"):
                _validate_target_absence_truth(folder, [case])

    def test_only_truth_absent_supported_completed_m8_cases_are_eligible(self):
        cases = [
            {"case_id": "eligible", "m8_search_complete": True,
             "candidate_records": [
                 {"read_support_status": "READ_SUPPORTED_ASSEMBLY",
                  "triage_status": "INSUFFICIENT_EVIDENCE"},
                 {"read_support_status": "UNSUPPORTED_ASSEMBLY",
                  "triage_status": "REVIEW_PRIORITY"},
             ]},
            {"case_id": "no-support", "m8_search_complete": True,
             "candidate_records": []},
            {"case_id": "incomplete", "m8_search_complete": False,
             "candidate_records": [
                 {"read_support_status": "READ_SUPPORTED_ASSEMBLY",
                  "triage_status": "REVIEW_PRIORITY"},
             ]},
        ]
        result = _metrics(cases)
        self.assertEqual(result["case_level"]["eligible_denominator"], 1)
        self.assertEqual(result["contig_level"]["eligible_denominator"], 1)
        self.assertEqual(result["case_level"]["review_priority"], 0)
        self.assertEqual(len(result["unevaluable"]), 2)
        self.assertIsNotNone(result["case_level"]["wilson_95"])
        self.assertIsNone(result["contig_level"]["wilson_95"])

    def test_markdown_report_includes_both_truth_strata_and_recovery(self):
        rates = _metrics([])
        sample = {
            "target_absent_generated": 64,
            "target_absent_eligible": 0,
            "target_absent_false_alarm_rates": rates,
            "target_absent_by_category": {"mixed_background": {**rates, "generated_cases": 8}},
            "target_absent_by_error_condition": {"insertion_only": {**rates, "generated_cases": 8}},
            "positive_indel_recovery": {
                "generated_cases": 7, "exact_supported": 4, "partial_supported": 1,
                "exact_wilson_95": [.25, .8], "partial_wilson_95": [0, .4],
            },
            "indel_robustness_by_condition": {
                "combined_moderate": {
                    "exact_supported": True, "partial_supported": False,
                    "assembly_status": "COMPLETE", "m8_search_complete": True,
                    "triage_outcome": "INSUFFICIENT_EVIDENCE",
                },
            },
            "reproducibility": {"status": "REPRODUCIBLE"},
        }
        text = render_markdown(sample)
        self.assertIn("mixed_background", text)
        self.assertIn("insertion_only", text)
        self.assertIn("partial supported recovery", text)


if __name__ == "__main__":
    unittest.main()
