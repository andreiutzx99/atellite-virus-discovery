import gzip
import random
import tempfile
import unittest
from pathlib import Path

from satellite_discovery import m19_benchmark as m19
from satellite_discovery.m25_read_coverage import (
    _make_fastq,
    _make_starts,
    _gzip_fastq,
    _stage_evaluation,
    _classification,
    _make_starts,
    _theory,
    coverage_summary,
)


class M25ReadCoverageTests(unittest.TestCase):
    def test_default_read_generation_is_byte_deterministic_and_provenanced(self):
        case = {
            "analysis_id": "m34test", "m25_read_length": 75, "coverage": 16,
            "read_start_mode": "uniform", "error_rate": 0.02,
        }
        payloads = []
        for _ in range(2):
            state = dict(case)
            payloads.append(_make_fastq(
                state, "ACGT" * 100, "TGCA" * 100,
                {"coverage": 16, "error_rate": 0.02},
            ))
            self.assertTrue(all(
                row["insertions"] == row["deletions"] == 0
                for row in state["_m25_layout"]["read_provenance"].values()
            ))
        self.assertEqual(payloads[0], payloads[1])
        legacy_rng = random.Random(m19.SEED + sum(case["analysis_id"].encode()))
        legacy_reads = []
        for bg_index, seq in enumerate(("TGCA" * 100,)):
            for i in range(8):
                start = round(i * (len(seq) - 75) / 7)
                legacy_reads.append(
                    (f"m34test-ref-{bg_index}-{i}", seq[start:start + 75], "I" * 75)
                )
        starts = _make_starts(400, 75, 16, "uniform", legacy_rng)
        for i, start in enumerate(starts):
            seq = list(("ACGT" * 100)[start:start + 75])
            quality = ["I"] * len(seq)
            for position in legacy_rng.sample(range(len(seq)), round(len(seq) * .02)):
                seq[position] = legacy_rng.choice("ACGT".replace(seq[position], ""))
                quality[position] = "5"
            legacy_reads.append((f"m34test-r{i:05d}", "".join(seq), "".join(quality)))
        self.assertEqual(payloads[0], _gzip_fastq(legacy_reads))
        lines = gzip.decompress(payloads[0]).decode("ascii").splitlines()
        self.assertEqual(len(lines) % 4, 0)
        for i in range(0, len(lines), 4):
            self.assertEqual(len(lines[i + 1]), len(lines[i + 3]))

    def test_indel_generation_is_deterministic_and_fastq_lengths_match(self):
        case = {
            "analysis_id": "m34indel", "m25_read_length": 75, "coverage": 48,
            "read_start_mode": "uniform", "error_rate": 0.02,
            "insertion_rate": 0.08, "deletion_rate": 0.10,
        }
        payloads, provenance = [], []
        for _ in range(2):
            state = dict(case)
            payload = _make_fastq(state, "ACGT" * 100, "TGCA" * 100,
                                  {"coverage": 48, "error_rate": 0.02})
            payloads.append(payload)
            provenance.append(state["_m25_layout"]["read_provenance"])
            lines = gzip.decompress(payload).decode("ascii").splitlines()
            self.assertEqual(len(lines) % 4, 0)
            for i in range(0, len(lines), 4):
                self.assertEqual(len(lines[i + 1]), len(lines[i + 3]))
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(provenance[0], provenance[1])
        self.assertTrue(any(row["insertions"] for row in provenance[0].values()))
        self.assertTrue(any(row["deletions"] for row in provenance[0].values()))

    def test_invalid_indel_rates_are_rejected(self):
        for rate in (-0.1, 1.1, float("nan")):
            case = {"analysis_id": "invalid", "m25_read_length": 75,
                    "read_start_mode": "uniform", "coverage": 1,
                    "insertion_rate": rate}
            with self.assertRaises(ValueError):
                _make_fastq(case, "A" * 100, "C" * 100,
                            {"coverage": 1, "error_rate": 0.0})

    def test_indel_and_substitution_errors_can_be_applied_to_negative_backgrounds(self):
        case = {
            "analysis_id": "m34negative", "m25_read_length": 75,
            "insertion_rate": 0.08, "deletion_rate": 0.10,
            "m25_apply_background_errors": True,
        }
        state = dict(case)
        payload = _make_fastq(
            state, None, "ACGT" * 100,
            {"coverage": 48, "error_rate": 0.02},
        )
        provenance = state["_m25_layout"]["read_provenance"]
        self.assertTrue(any(row["insertions"] for row in provenance.values()))
        self.assertTrue(any(row["deletions"] for row in provenance.values()))
        self.assertTrue(any(row["substitutions"] for row in provenance.values()))
        lines = gzip.decompress(payload).decode("ascii").splitlines()
        for i in range(0, len(lines), 4):
            self.assertEqual(len(lines[i + 1]), len(lines[i + 3]))
            self.assertEqual(len(lines[i + 1]), provenance[lines[i][1:]]["read_length"])

    def test_target_absent_background_reads_can_use_registered_coverage(self):
        case = {
            "analysis_id": "m34coveredbg", "m25_read_length": 75,
            "m25_background_read_coverage": True,
        }
        state = dict(case)
        payload = _make_fastq(
            state, None, "ACGT" * 75, {"coverage": 24, "error_rate": 0.0},
        )
        provenance = state["_m25_layout"]["read_provenance"]
        self.assertEqual(len(provenance), 96)
        self.assertTrue(all(row["source_role"] == "technical_reference"
                            for row in provenance.values()))
        self.assertTrue(all(row["source_record_sha256"] for row in provenance.values()))
        lines = gzip.decompress(payload).decode("ascii").splitlines()
        self.assertEqual(len(lines), 96 * 4)

    def test_substitution_insertion_deletion_and_combined_models_individually(self):
        models = (
            ("sub", .05, 0.0, 0.0, "substitutions"),
            ("ins", 0.0, .08, 0.0, "insertions"),
            ("del", 0.0, 0.0, .10, "deletions"),
            ("all", .05, .08, .10, None),
        )
        for name, sub, ins, dele, expected in models:
            case = {
                "analysis_id": f"m34model{name}", "m25_read_length": 75,
                "coverage": 48, "read_start_mode": "random",
                "insertion_rate": ins, "deletion_rate": dele,
            }
            state = dict(case)
            _make_fastq(state, "ACGT" * 100, "TGCA" * 100,
                        {"coverage": 48, "error_rate": sub})
            rows = [row for row in state["_m25_layout"]["read_provenance"].values()
                    if row["source_role"] == "target_truth"]
            totals = {key: sum(row[key] for row in rows)
                      for key in ("substitutions", "insertions", "deletions")}
            if expected:
                self.assertGreater(totals[expected], 0, name)
                for other in totals.keys() - {expected}:
                    self.assertEqual(totals[other], 0, name)
            else:
                self.assertTrue(all(value > 0 for value in totals.values()))
            lengths = [row["read_length"] for row in rows]
            if ins:
                self.assertGreater(max(lengths), 75)
            if dele:
                self.assertLess(min(lengths), 75)

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
