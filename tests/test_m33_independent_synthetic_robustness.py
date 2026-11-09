import unittest

from satellite_discovery.m33_independent_synthetic_robustness import (
    ReproducibilityMismatchError,
    _analysis_category,
    _reproducibility_signature,
    compare_reproducibility,
    false_alarm_metrics,
    preregistered_trials,
    validate_reproducibility,
    wilson_interval,
)


class M33RepeatabilityTests(unittest.TestCase):
    def test_alignment_repeatability_ignores_run_specific_match_metadata(self):
        def report(run_id):
            return {
                "reconstruction_and_handoffs": [{
                    "case_id": "case-1",
                    "read_input_sha256": "same-input",
                    "assembly_status": "ASSEMBLED",
                    "contig_count": 1,
                    "handoff": {"status": "COMPLETE"},
                    "assembly_graph": {
                        "status": "AVAILABLE", "sha256": "same-graph",
                        "segment_count": 1, "link_count": 0,
                    },
                }],
                "candidate_triage": [{
                    "case_id": "case-1",
                    "candidate_records": [{
                        "candidate_id": "candidate-1",
                        "query_sha256": "same-query",
                        "read_support_status": "READ_SUPPORTED_ASSEMBLY",
                        "m8_aggregate_status": "COMPLETE",
                        "reference_panel_entries": ["ref-1"],
                        "triage_status": "INSUFFICIENT_EVIDENCE",
                    }],
                    "matches": [{
                        "candidate_id": "candidate-1",
                        "reference": {"accession_version": "ref-1"},
                        "panel_role": "known_reference",
                        "masking_branch": "unmasked",
                        "alignment": {"identity": 99.0, "aligned_length": 100},
                        "run_metadata": run_id,
                    }],
                }],
            }

        self.assertEqual(
            _reproducibility_signature(report("first")),
            _reproducibility_signature(report("repeat")),
        )

    def test_changed_triage_result_is_a_validation_failure(self):
        reference = {
            "reconstruction": {"case-1": ("reads", "ASSEMBLED", 1, "COMPLETE")},
            "screening": {"case-1": (("candidate-1", "INSUFFICIENT_EVIDENCE"),)},
            "normalized_alignment_sha256": {"case-1": "same-alignment"},
        }
        repeat = {
            **reference,
            "screening": {"case-1": (("candidate-1", "REVIEW_PRIORITY"),)},
        }
        outcome = compare_reproducibility(reference, repeat)
        self.assertEqual(outcome["status"], "REPRODUCIBILITY_MISMATCH")
        self.assertEqual(outcome["differing_stages"], {"screening_triage": ["case-1"]})
        with self.assertRaises(ReproducibilityMismatchError):
            validate_reproducibility(outcome)

    def test_changed_normalized_alignment_is_a_validation_failure(self):
        reference = {
            "reconstruction": {"case-1": ("reads", "ASSEMBLED", 1, "COMPLETE")},
            "screening": {"case-1": (("candidate-1", "INSUFFICIENT_EVIDENCE"),)},
            "normalized_alignment_sha256": {"case-1": "alignment-a"},
        }
        repeat = {
            **reference,
            "normalized_alignment_sha256": {"case-1": "alignment-b"},
        }
        outcome = compare_reproducibility(reference, repeat)
        self.assertEqual(
            outcome["differing_stages"],
            {"normalized_alignment": ["case-1"]},
        )
        self.assertFalse(outcome["fully_reproducible"])
        with self.assertRaises(ReproducibilityMismatchError):
            validate_reproducibility(outcome)

    def test_changed_normalized_assembly_graph_is_detected(self):
        reference = {
            "reconstruction": {"case-1": {
                "assembly_graph": {"sha256": "graph-a"},
            }},
            "screening": {},
            "normalized_alignment_sha256": {},
        }
        repeat = {
            **reference,
            "reconstruction": {"case-1": {
                "assembly_graph": {"sha256": "graph-b"},
            }},
        }
        outcome = compare_reproducibility(reference, repeat)
        self.assertEqual(outcome["differing_stages"], {
            "reconstruction": ["case-1"],
        })
        with self.assertRaises(ReproducibilityMismatchError):
            validate_reproducibility(outcome)


class M33DesignTests(unittest.TestCase):
    def test_design_has_independent_reproducible_trial_seeds(self):
        first = preregistered_trials()
        second = preregistered_trials()
        self.assertEqual([row["seed"] for row in first], [row["seed"] for row in second])
        self.assertEqual(len({row["seed"] for row in first}), len(first))
        for trial in first:
            self.assertEqual(len(trial["cases"]), 17)
            self.assertEqual(len(set(trial["seed_map"].values())), len(trial["seed_map"]))

    def test_design_varies_coverage_read_length_and_substitution_errors(self):
        trials = preregistered_trials()
        held_out = [trial["cases"][8] for trial in trials]
        self.assertEqual({row["coverage"] for row in held_out}, {24, 48, 80})
        self.assertEqual({row["m25_read_length"] for row in held_out}, {50, 75, 100})
        self.assertEqual({row["error_rate"] for row in held_out}, {0.0, 0.02, 0.05})


class M33FalseAlarmTests(unittest.TestCase):
    def test_truth_categories_keep_positive_adversarial_out_of_false_alarm_rate(self):
        self.assertEqual(
            _analysis_category(True, "reference_absent_adversarial"),
            "target_positive_adversarial",
        )
        self.assertEqual(
            _analysis_category(True, "reference_independent_challenge"),
            "target_positive_adversarial",
        )
        self.assertEqual(_analysis_category(False, "target_absent_no_contig"),
                         "target_absent")
        cases = [
            {
                "case_id": "target-absent", "analysis_category": "target_absent",
                "target_present_in_synthetic_truth": False,
                "experiment_type": "target_absent_supported_background",
                "m8_search_complete": True,
                "candidate_records": [
                    {"read_support_status": "READ_SUPPORTED_ASSEMBLY",
                     "triage_status": "REVIEW_PRIORITY"},
                    {"read_support_status": "UNSUPPORTED_ASSEMBLY",
                     "triage_status": "REVIEW_PRIORITY"},
                ],
            },
            {
                "case_id": "positive-adversarial",
                "analysis_category": "target_positive_adversarial",
                "target_present_in_synthetic_truth": True,
                "experiment_type": "reference_absent_adversarial",
                "m8_search_complete": True,
                "candidate_records": [
                    {"read_support_status": "READ_SUPPORTED_ASSEMBLY",
                     "triage_status": "REVIEW_PRIORITY"},
                ],
            },
            {
                "case_id": "no-contig", "analysis_category": "target_absent",
                "target_present_in_synthetic_truth": False,
                "experiment_type": "target_absent_no_contig",
                "m8_search_complete": False, "candidate_records": [],
            },
            {
                "case_id": "incomplete", "analysis_category": "target_absent",
                "target_present_in_synthetic_truth": False,
                "experiment_type": "target_absent_supported_background",
                "m8_search_complete": False,
                "candidate_records": [
                    {"read_support_status": "READ_SUPPORTED_ASSEMBLY",
                     "triage_status": "REVIEW_PRIORITY"},
                ],
            },
            {
                "case_id": "positive", "analysis_category": "positive_retrieval_control",
                "target_present_in_synthetic_truth": True,
                "experiment_type": "known_reference_positive",
                "m8_search_complete": True,
                "candidate_records": [
                    {"read_support_status": "READ_SUPPORTED_ASSEMBLY",
                     "triage_status": "REVIEW_PRIORITY"},
                ],
            },
        ]
        result = false_alarm_metrics(cases)
        absent = result["target_absent_synthetic_false_alarms"]
        adversarial = result["target_positive_adversarial_triage"]
        self.assertEqual(absent["case_level"]["eligible_denominator"], 1)
        self.assertEqual(absent["case_level"]["review_priority"], 1)
        self.assertEqual(absent["contig_level"]["eligible_denominator"], 1)
        self.assertEqual(len(absent["unevaluable"]), 2)
        self.assertEqual(adversarial["case_level"]["eligible_denominator"], 1)
        self.assertEqual(adversarial["case_level"]["review_priority"], 1)
        self.assertEqual(adversarial["contig_level"]["eligible_denominator"], 1)
        self.assertEqual(
            result["historical_mixed_category_comparison"]["case_level"]["eligible_denominator"],
            2,
        )

    def test_empty_denominator_is_not_reported_as_zero_rate(self):
        result = false_alarm_metrics([{
            "case_id": "no-contig", "analysis_category": "target_absent",
            "target_present_in_synthetic_truth": False,
            "m8_search_complete": False, "candidate_records": [],
        }])
        absent = result["target_absent_synthetic_false_alarms"]
        self.assertIsNone(absent["case_level"]["rate"])
        self.assertIsNone(absent["case_level"]["wilson_95"])

    def test_wilson_interval_bounds_and_zero_denominator(self):
        interval = wilson_interval(1, 10)
        self.assertLess(interval[0], 0.1)
        self.assertGreater(interval[1], 0.1)
        self.assertIsNone(wilson_interval(0, 0))


if __name__ == "__main__":
    unittest.main()
