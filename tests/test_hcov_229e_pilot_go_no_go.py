import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
REPORT = ROOT / "docs" / "hcov-229e-pilot-go-no-go-v1.json"
PR63 = ROOT / "docs" / "hcov-229e-identity-evidence-review-v1.json"


class HCoV229EPilotDecisionTests(unittest.TestCase):
    def test_refreshed_snapshot_matches_prior_curated_identity_and_manifest(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        prior = json.loads(PR63.read_text(encoding="utf-8"))
        prior_runs = {row["run"]: row for row in prior["runs"]}
        current = report["records"]
        self.assertEqual(len(current), 15)
        self.assertEqual(set(row["run"] for row in current), set(prior_runs))
        for row in current:
            old = prior_runs[row["run"]]
            with self.subTest(run=row["run"]):
                self.assertEqual(row["experiment"], old["experiment"])
                self.assertEqual(row["biosample"], old["biosample"])
                self.assertEqual(row["geo_sample"], old["geo_sample"])
                self.assertEqual(row["fastq_bytes"], old["fastq_bytes"])
                self.assertEqual(row["fastq_md5"], old["fastq_md5"])
                self.assertEqual(row["fastq_bytes"], int(row["fastq_bytes"]))

    def test_decision_keeps_policy_and_acquisition_separate(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["recommendation"]["scientific_decision"], "CONDITIONAL GO")
        self.assertEqual(report["recommendation"]["policy_approval"], "PENDING")
        self.assertFalse(report["recommendation"]["acquisition_authorized"])
        self.assertEqual(report["recommendation"]["current_eligibility"], "HELD")
        self.assertTrue(report["current_policy"]["unchanged"])
        self.assertEqual(report["current_policy"]["max_compressed_bytes_per_run"], 1_000_000_000)

    def test_exposure_counts_controls_and_baselines_are_conservative(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        rows = report["records"]
        infected = [r for r in rows if r["exposure_assessment"] == "SUPPORTED_STUDY_REPORTED"]
        baselines = [r for r in rows if r["exposure_assessment"] == "INSUFFICIENT_UNRESOLVED_BASELINE"]
        self.assertEqual(len(infected), 12)
        self.assertEqual(len(baselines), 3)
        self.assertEqual(report["findings"]["confirmed_mock_controls"], 0)
        self.assertEqual(report["findings"]["sequence_confirmed_presence"], "NOT_ASSESSED")
        self.assertEqual(report["findings"]["biological_independence"], "UNKNOWN")
        self.assertTrue(all(r["fastq_bytes"] < 1_000_000_000 for r in rows))
        self.assertTrue(all(r["timepoint_hours"] == 0 for r in baselines))

    def test_provisional_run_manifest_is_exactly_one_complete_single_end_file(self):
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        pilot = report["provisional_pilot"]
        self.assertEqual(pilot["nomination_status"], "PROVISIONAL_NOT_APPROVED")
        self.assertEqual(pilot["run"], "SRR12424250")
        self.assertEqual(pilot["experiment"], "SRX8920123")
        self.assertEqual(pilot["biosample"], "SAMN15776099")
        self.assertEqual(pilot["geo_sample"], "GSM4718636")
        self.assertEqual(pilot["layout"], "SINGLE")
        self.assertEqual(len(pilot["fastq_manifest"]), 1)
        self.assertEqual(pilot["fastq_manifest"][0]["compressed_bytes"], 680_887_913)
        self.assertEqual(pilot["fastq_manifest"][0]["md5"], "9ac379cab68b8b5e2862ec167e95d3c9")
        self.assertFalse(pilot["acquisition_authorized"])


if __name__ == "__main__":
    unittest.main()
