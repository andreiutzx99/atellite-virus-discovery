import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m29_assembly_root_cause_recovery import (
    _summarize_case,
    _case_seed,
    _controlled_improvement,
    case_matrix,
    historical_findings,
)


class M29AssemblyRootCauseRecoveryTests(unittest.TestCase):
    def test_case_matrix_is_fixed_partitioned_and_covers_required_challenges(self):
        cases = case_matrix()
        self.assertEqual(len({case["case_id"] for case in cases}), len(cases))
        self.assertEqual({case["case_id"].split("-")[0] for case in cases},
                         {"development", "tuning", "held_out"})
        factors = {case["m29_factor"] for case in cases}
        self.assertEqual(sum(not case["positive"] for case in cases), 4)
        self.assertTrue({
            "reduced_coverage", "short_reads", "repeat_challenge",
            "sequencing_errors", "synthetic_background", "target_absent_negative",
            "low_coverage_validation", "low_coverage_target_absent_background",
        }.issubset(factors))
        self.assertTrue(any(
            case["case_id"].startswith("held_out-") and case["positive"]
            and case["m29_factor"] == "positive_control" for case in cases
        ))
        self.assertTrue(all("candidate_sequence" not in case for case in cases))
        held_out_validation = next(
            case for case in cases if case["m29_factor"] == "low_coverage_validation"
        )
        held_out_baseline = next(
            case for case in cases
            if case["case_id"] == "held_out-m29-positive_control"
        )
        self.assertNotEqual(_case_seed(held_out_validation), _case_seed(held_out_baseline))

    def test_configuration_comparison_requires_matching_eligible_input_digest(self):
        rows = [
            {
                "split": "tuning", "factor": "reduced_coverage",
                "case_id": "tuning-m29-reduced_coverage",
                "assembly_eligible_input_sha256": "tuning-digest",
                "assembler_status": "EXECUTION_FAILED", "exact_recovery": False,
                "read_support_statuses": [], "false_positive_candidates": None,
                "experimental_configuration_B": {
                    "input_sha256": "tuning-digest", "status": "COMPLETED",
                    "exact_recovery": True, "read_support_status": "READ_SUPPORTED_ASSEMBLY",
                },
            },
            {
                "split": "held_out", "factor": "low_coverage_validation",
                "case_id": "held_out-m29-low_coverage_validation",
                "assembly_eligible_input_sha256": "heldout-digest",
                "assembler_status": "EXECUTION_FAILED", "exact_recovery": False,
                "read_support_statuses": [], "false_positive_candidates": None,
                "experimental_configuration_B": {
                    "input_sha256": "heldout-digest", "status": "COMPLETED",
                    "exact_recovery": True, "read_support_status": "READ_SUPPORTED_ASSEMBLY",
                },
            },
            {
                "split": "held_out", "factor": "low_coverage_target_absent_background",
                "case_id": "held_out-m29-low_coverage_target_absent_background",
                "assembly_eligible_input_sha256": "negative-digest",
                "assembler_status": "READ_SUPPORTED_ASSEMBLY", "exact_recovery": False,
                "read_support_statuses": [], "false_positive_candidates": 0,
                "experimental_configuration_B": {
                    "input_sha256": "negative-digest", "status": "COMPLETED",
                    "false_positive_candidates": 0,
                },
            },
        ]
        comparisons = _controlled_improvement(rows)
        self.assertTrue(comparisons["tuning"]["input_identity_matched"])
        self.assertTrue(comparisons["held_out"]["input_identity_matched"])
        self.assertTrue(comparisons["negative_control"]["input_identity_matched"])
        self.assertEqual(
            comparisons["negative_control"]["configuration_B"]["false_positive_candidates"],
            0,
        )

    def test_historical_findings_separate_demonstrated_and_unresolved_causes(self):
        root = Path(__file__).parents[1]
        result = historical_findings(root)
        demonstrated = result["demonstrated"]
        self.assertEqual(demonstrated["positive_cases_with_zero_eligible_reads"], 3)
        self.assertEqual(len(demonstrated["m27_low_complexity_focus_cases"]), 3)
        self.assertEqual(len(demonstrated["incomplete_supported_cases"]), 5)
        self.assertEqual(demonstrated["spades_exit_21_cases"][0]["return_code"], 21)
        self.assertTrue(any("operating-system cause" in item for item in result["unresolved"]))

    def test_summary_scores_truth_only_after_read_supported_candidate_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            case = {
                "analysis_id": "m29t01", "case_id": "held_out-m29-positive_control",
                "positive": True, "m29_factor": "positive_control",
                "target_length": 120, "coverage": 80, "m25_read_length": 100,
                "error_rate": 0.0, "repeat_complexity": "low",
                "background_gc_fraction": None,
            }
            truth = "ACGTTGCA" * 15
            truth_path = root / "heldout_truth.json"
            truth_path.write_text(json.dumps({"cases": [{
                "case_id": case["case_id"], "positive": True,
                "candidate_sequence": truth,
                "candidate_sha256": hashlib.sha256(truth.encode()).hexdigest(),
            }]}))
            reads = [("r1", truth[:100], "I" * 100), ("r2", truth[20:120], "I" * 100)]
            raw_path = root / "inputs/datasets/m29t01/reads.fastq.gz"
            raw_path.parent.mkdir(parents=True)
            raw_path.write_bytes(__import__(
                "satellite_discovery.m25_read_coverage", fromlist=["_gzip_fastq"]
            )._gzip_fastq(reads))
            qc = root / "stages/qc_m29t01"
            stage = root / "stages/m6_m29t01"
            qc.mkdir(parents=True)
            stage.mkdir(parents=True)
            (qc / "clean_single.fastq.gz").write_bytes(raw_path.read_bytes())
            (stage / "residual_read1.fastq.gz").write_bytes(raw_path.read_bytes())
            (stage / "residual_manifest.json").write_text(json.dumps({
                "counts": {"eligible_fragments": 2}
            }))
            reverse = truth.translate(str.maketrans("ACGT", "TGCA"))[::-1]
            (stage / "candidate_sequences.fasta").write_text(f">candidate\n{reverse}\n")
            (stage / "reconstruction_evidence.json").write_text(json.dumps({
                "status": "READ_SUPPORTED_ASSEMBLY",
                "contigs": [{"status": "READ_SUPPORTED_ASSEMBLY"}],
            }))
            (root / "inputs/source_manifest.json").write_text("{}\n")
            row = _summarize_case(case, root, {})
            self.assertTrue(row["exact_recovery"])
            self.assertTrue(row["best_truth_match"]["strand_exact_match"])
            self.assertEqual(row["assembler_status"], "READ_SUPPORTED_ASSEMBLY")
            self.assertEqual(row["stage_read_counts"]["assembly_eligible"], 2)
            self.assertIsNone(row["false_positive_candidates"])


if __name__ == "__main__":
    unittest.main()
