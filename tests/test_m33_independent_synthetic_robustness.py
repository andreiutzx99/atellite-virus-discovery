import unittest

from satellite_discovery.m33_independent_synthetic_robustness import (
    _reproducibility_signature,
    false_alarm_metrics,
    preregistered_trials,
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
    def test_only_supported_contigs_with_completed_m8_enter_denominators(self):
        cases = [
            {
                "case_id": "eligible", "negative_or_decoy": True,
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
                "case_id": "no-contig", "negative_or_decoy": True,
                "m8_search_complete": False, "candidate_records": [],
            },
            {
                "case_id": "incomplete", "negative_or_decoy": True,
                "m8_search_complete": False,
                "candidate_records": [
                    {"read_support_status": "READ_SUPPORTED_ASSEMBLY",
                     "triage_status": "REVIEW_PRIORITY"},
                ],
            },
            {
                "case_id": "positive", "negative_or_decoy": False,
                "m8_search_complete": True,
                "candidate_records": [
                    {"read_support_status": "READ_SUPPORTED_ASSEMBLY",
                     "triage_status": "REVIEW_PRIORITY"},
                ],
            },
        ]
        result = false_alarm_metrics(cases)
        self.assertEqual(result["case_level"]["eligible_denominator"], 1)
        self.assertEqual(result["case_level"]["review_priority"], 1)
        self.assertEqual(result["contig_level"]["eligible_denominator"], 1)
        self.assertEqual(result["contig_level"]["review_priority"], 1)
        self.assertEqual(len(result["unevaluable"]), 2)
        category = result["by_experiment_type"]["target_absent_supported_background"]
        self.assertEqual(category["case_level"]["eligible_denominator"], 1)

    def test_empty_denominator_is_not_reported_as_zero_rate(self):
        result = false_alarm_metrics([{
            "case_id": "no-contig", "negative_or_decoy": True,
            "m8_search_complete": False, "candidate_records": [],
        }])
        self.assertIsNone(result["case_level"]["rate"])
        self.assertIsNone(result["case_level"]["wilson_95"])

    def test_wilson_interval_bounds_and_zero_denominator(self):
        interval = wilson_interval(1, 10)
        self.assertLess(interval[0], 0.1)
        self.assertGreater(interval[1], 0.1)
        self.assertIsNone(wilson_interval(0, 0))


if __name__ == "__main__":
    unittest.main()
