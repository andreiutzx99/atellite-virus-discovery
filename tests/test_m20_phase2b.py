import gzip
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from satellite_discovery import artifact_workflow, m20_phase1, m20_phase2b


class M20Phase2BBenchmarkTests(unittest.TestCase):
    def test_v2_matrix_is_deterministic_blind_and_separate_from_phase1(self):
        with tempfile.TemporaryDirectory() as temporary:
            first, second = Path(temporary) / "first", Path(temporary) / "second"
            result = m20_phase2b.generate_fixtures(first)
            self.assertEqual(result, m20_phase2b.generate_fixtures(second))
            self.assertEqual(10, result["case_count"])
            self.assertEqual(
                (first / "benchmark_manifest.json").read_bytes(),
                (second / "benchmark_manifest.json").read_bytes(),
            )
            manifest = json.loads((first / "benchmark_manifest.json").read_text())
            truth = json.loads((first / "heldout_truth.json").read_text())
            self.assertEqual("m20-phase2b-synthetic-benchmark-v2", manifest["schema"])
            self.assertEqual(
                {("random_start", 10), ("random_start", 30),
                 ("stratified_start", 10), ("stratified_start", 30)},
                {(row["sampling"], row["nominal_coverage"])
                 for row in manifest["recurrence_pairs"]},
            )
            self.assertEqual(4, len(manifest["recurrence_pairs"]))
            self.assertEqual(2, sum(row["role"] == "negative_control"
                                    for row in truth["cases"]))
            self.assertFalse((first / "inputs/heldout_truth.json").exists())
            self.assertFalse((first / "inputs/benchmark_manifest.json").exists())
            for row in manifest["cases"]:
                raw = gzip.decompress(
                    (first / "inputs" / row["sample_id"] / "reads.fastq.gz").read_bytes()
                ).decode()
                self.assertEqual(row["read_count"], len(raw.splitlines()) // 4)
                self.assertNotIn("positive", raw.lower())
                self.assertNotIn("negative", raw.lower())
            self.assertNotEqual(
                (first / "inputs/c001/reads.fastq.gz").read_bytes(),
                (first / "inputs/c002/reads.fastq.gz").read_bytes(),
            )
            baseline = m20_phase1.generate_fixtures(Path(temporary) / "phase1")
            self.assertEqual(
                result["schema"], "m20-phase2b-synthetic-benchmark-v2",
            )
            self.assertEqual(
                "24a4cdc9c0337f373d49ee49482f6c49eb91de03d8993cbe9ac2358925ccacac",
                baseline["manifest_sha256"],
            )
            self.assertEqual(
                "1d6e16d1c31975181dfa8cd86260297f2151d89914ff796d4ae23934936e2614",
                baseline["heldout_truth_sha256"],
            )

    def test_v2_verifier_rejects_rehashed_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m20_phase2b.generate_fixtures(root)
            target = root / "inputs/c001/reads.fastq.gz"
            target.write_bytes(target.read_bytes() + b"tamper")
            manifest_path = root / "benchmark_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["cases"][0]["files"]["c001/reads.fastq.gz"].update({
                "bytes": target.stat().st_size,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            })
            manifest_path.write_bytes(m20_phase2b._canonical(manifest))
            with self.assertRaisesRegex(ValueError, "deterministic generator"):
                m20_phase2b.verify_fixtures(root)

    def test_v2_analysis_spec_uses_only_opaque_typed_inputs(self):
        spec = m20_phase2b._workflow_spec()
        rows = artifact_workflow.validate(
            spec, artifact_workflow.build_default_registry(),
        )
        self.assertEqual(20, len(rows))
        encoded = json.dumps(spec, sort_keys=True).lower()
        for marker in ("heldout_truth", "candidate_sequence", "positive",
                       "negative_control", "random_start", "stratified_start"):
            self.assertNotIn(marker, encoded)
        matrix = json.loads(m20_phase2b._expected_files()[1])
        self.assertEqual(120, max(row["read_count"] for row in matrix["cases"]))
        m6_rows = [row for row in rows if row["kind"] == "residual_evidence"]
        self.assertTrue(all(row["config"]["threads"] == 1 for row in m6_rows))
        self.assertTrue(all(row["config"]["memory_mb"] == 2048 for row in m6_rows))


@unittest.skipUnless(
    shutil.which("spades.py") and shutil.which("minimap2"),
    "live v2 benchmark requires SPAdes and minimap2",
)
class M20Phase2BLiveTests(unittest.TestCase):
    def test_all_prespecified_cases_are_retained_and_diagnostics_are_well_typed(self):
        with tempfile.TemporaryDirectory(prefix="m20-phase2b-live-") as temporary:
            report = m20_phase2b.run(Path(temporary) / "run")
            self.assertEqual("COMPLETE", report["status"])
            self.assertTrue(report["fixtures"]["unchanged_after_execution"])
            self.assertTrue(report["fixtures"]["phase1_baseline"]["matches_frozen_digests"])
            self.assertEqual(10, len(report["cases"]))
            self.assertEqual(4, len(report["recurrence_pairs"]))
            self.assertTrue(all(row["assembler"]["version"] for row in report["cases"]))
            self.assertEqual(2, sum(
                row["negative_control_evaluation"] is not None for row in report["cases"]
            ))
            for row in report["cases"]:
                self.assertIn(row["qc_status"], {"COMPLETE", "INCOMPLETE", "UNAVAILABLE"})
                self.assertIn(row["m6_status"], {"COMPLETE", "INCOMPLETE", "UNAVAILABLE"})
                if (row["negative_control_evaluation"] and
                        row["negative_control_evaluation"]["state"] == "UNEVALUABLE"):
                    self.assertIsNone(row["negative_control_evaluation"]["prediction_count"])
                if row["alignment"] and row["alignment"].get("best"):
                    best = row["alignment"]["best"]
                    self.assertGreaterEqual(best["query_breadth"], 0)
                    self.assertLessEqual(best["query_breadth"], 1)
                    self.assertGreaterEqual(best["reference_breadth"], 0)
                    self.assertLessEqual(best["reference_breadth"], 1)
                    self.assertGreaterEqual(best["sequence_identity"], 0)
                    self.assertLessEqual(best["sequence_identity"], 1)
            for pair in report["recurrence_pairs"]:
                if pair["state"] == "UNEVALUABLE":
                    self.assertIsNone(pair["m7_exact_recurrence"])
            self.assertEqual("complete", report["workflow_status"]["m7"])


if __name__ == "__main__":
    unittest.main()
