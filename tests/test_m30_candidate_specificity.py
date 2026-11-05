import json
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m30_candidate_specificity import (
    GOVERNANCE,
    _fixture_rows,
    _metrics,
    audit_runtime,
    build,
)


class M30CandidateSpecificityTests(unittest.TestCase):
    def test_candidate_generation_is_blind_to_scenario_truth(self):
        inputs, truth = _fixture_rows()
        self.assertEqual(len(inputs), len(truth))
        self.assertEqual({row["split"] for row in inputs},
                         {"development", "tuning", "held_out"})
        self.assertEqual(
            {row["candidate_id"] for row in inputs},
            {row["candidate_id"] for row in truth},
        )
        self.assertTrue(all("scenario" not in row and "target_present" not in row
                            for row in inputs))
        self.assertTrue(all("sequence" not in row for row in truth))
        hashes = [row["sequence_sha256"] for row in inputs if row["sequence_sha256"]]
        self.assertLess(len(set(hashes)), len(hashes))  # repeated target is intentional

    def test_unavailable_pipeline_does_not_turn_candidates_into_negatives(self):
        _, truth = _fixture_rows()
        rows = [{
            "candidate_id": item["candidate_id"],
            "screening_status": "NOT_EVALUATED",
            "final_acceptance_status": "NOT_EVALUATED",
        } for item in truth]
        metrics = _metrics(rows, {item["candidate_id"]: item for item in truth})
        self.assertEqual(metrics["status"], "NOT_EVALUATED")
        self.assertEqual(metrics["denominator"], 0)
        for key in ("true_positives", "false_positives", "true_negatives",
                    "false_negatives", "sensitivity", "specificity", "precision"):
            self.assertEqual(metrics[key], "NOT_EVALUATED")

    def test_benchmark_covers_required_synthetic_scenarios(self):
        inputs, truth = _fixture_rows()
        scenarios = {row["scenario"] for row in truth}
        self.assertTrue({
            "target_like_supported", "background_supported", "near_target_decoy",
            "repeat_challenge", "truncated_target", "unsupported_exact_target",
            "target_absent", "ambiguous_insufficient_evidence",
        }.issubset(scenarios))
        by_id = {row["candidate_id"]: row for row in inputs}
        exact_supported = next(
            row for row in truth if row["scenario"] == "target_like_supported"
        )
        exact_unsupported = next(
            row for row in truth if row["scenario"] == "unsupported_exact_target"
        )
        self.assertEqual(by_id[exact_supported["candidate_id"]]["m6_support_status"],
                         "READ_SUPPORTED_ASSEMBLY")
        self.assertEqual(by_id[exact_unsupported["candidate_id"]]["m6_support_status"],
                         "UNSUPPORTED_ASSEMBLY")
        truth_by_id = {row["candidate_id"]: row for row in truth}
        self.assertTrue(truth_by_id[exact_unsupported["candidate_id"]]["target_present"])

    def test_report_preserves_truth_separation_and_governance(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build(tmp)
            inputs = json.loads(
                (Path(tmp) / "M30_SYNTHETIC_CANDIDATE_INPUTS.json").read_text()
            )
            truth = json.loads(
                (Path(tmp) / "M30_SYNTHETIC_CANDIDATE_TRUTH.json").read_text()
            )
            self.assertEqual(len(inputs["candidates"]), 11)
            self.assertEqual(len(truth["cases"]), 11)
            self.assertEqual(result["governance"], GOVERNANCE)
            self.assertFalse(result["biological_data_used"])
            self.assertFalse(result["external_biological_queries"])
            self.assertEqual(result["conclusion"]["status"], "NOT_VALIDATED")
            self.assertTrue(all(
                row["final_acceptance_status"] == "NOT_EVALUATED"
                for row in result["screening"]
            ))

    def test_current_m8_runtime_assessment_is_explicit(self):
        audit = audit_runtime()
        self.assertIn(audit["m8"]["status"],
                      {"DEPENDENCY_UNAVAILABLE", "NOT_EVALUATED"})
        self.assertIn("does not accept or reject", audit["m8"]["role"])
        self.assertIn("classifier", audit["m9_m15"]["reason"])


if __name__ == "__main__":
    unittest.main()
