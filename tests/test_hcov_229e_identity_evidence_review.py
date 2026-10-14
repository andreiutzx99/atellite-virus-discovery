import json
from pathlib import Path
import unittest

from satellite_discovery.public_virus import POLICY, assess_identity


ROOT = Path(__file__).parents[1]
RECORD = ROOT / "docs" / "hcov-229e-identity-evidence-review-v1.json"
VALID_STATUSES = {"SUPPORTED", "INSUFFICIENT", "CONFLICTED", "NOT_ASSESSED"}


def mapping_issues(runs):
    issues = []
    for field in ("run", "experiment", "biosample", "geo_sample"):
        values = [record[field] for record in runs]
        if len(values) != len(set(values)):
            issues.append("duplicate_" + field)
    for record in runs:
        if not all(record.get(field) for field in
                   ("run", "experiment", "biosample", "geo_sample", "project", "study")):
            issues.append("incomplete_accession_mapping")
    return issues


class HCoV229EIdentityEvidenceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(RECORD.read_text(encoding="utf-8"))
        cls.runs = cls.document["runs"]

    def test_versioned_record_has_exactly_one_record_per_expected_run(self):
        self.assertEqual(self.document["schema"], "hcov-229e-identity-evidence-review-v1")
        self.assertEqual(self.document["schema_version"], 1)
        accessions = [run["run"] for run in self.runs]
        self.assertEqual(len(accessions), 15)
        self.assertEqual(len(set(accessions)), 15)
        self.assertEqual(set(accessions), {f"SRR{n}" for n in range(12424243, 12424258)})

    def test_relationships_and_source_field_evidence_are_present_for_each_run(self):
        self.assertEqual(mapping_issues(self.runs), [])
        for run in self.runs:
            with self.subTest(run=run["run"]):
                self.assertRegex(run["experiment"], r"^SRX\d+$")
                self.assertRegex(run["biosample"], r"^SAMN\d+$")
                self.assertRegex(run["geo_sample"], r"^GSM\d+$")
                self.assertEqual(run["project"], "PRJNA656274")
                self.assertEqual(run["study"], "SRP276927")
                for category in ("mapping", "condition", "archive_identity"):
                    self.assertTrue(run["evidence"][category])
                self.assertTrue(run["evidence"]["mapping"][0].startswith("sra.Run"))

    def test_duplicate_or_conflicting_mapping_is_flagged(self):
        duplicate_run = [dict(run) for run in self.runs]
        duplicate_run[1]["run"] = duplicate_run[0]["run"]
        self.assertIn("duplicate_run", mapping_issues(duplicate_run))

        conflicting_experiment = [dict(run) for run in self.runs]
        conflicting_experiment[1]["experiment"] = conflicting_experiment[0]["experiment"]
        self.assertIn("duplicate_experiment", mapping_issues(conflicting_experiment))

        incomplete = [dict(run) for run in self.runs]
        incomplete[0]["biosample"] = ""
        self.assertIn("incomplete_accession_mapping", mapping_issues(incomplete))

    def test_status_vocab_and_evidence_categories_do_not_collapse(self):
        for run in self.runs:
            for key in ("archive_identity", "reported_exposure", "sequence_presence"):
                self.assertIn(run[key], VALID_STATUSES)
            self.assertEqual(run["archive_identity"], "INSUFFICIENT")
            self.assertEqual(run["sequence_presence"], "NOT_ASSESSED")
            if run["reported_exposure"] == "SUPPORTED":
                self.assertNotEqual(run["sequence_presence"], "SUPPORTED")

    def test_zero_hour_baselines_are_not_called_mock_or_supported_exposure(self):
        baseline = [run for run in self.runs if run["timepoint_hours"] == 0]
        self.assertEqual(len(baseline), 3)
        self.assertTrue(all(run["treatment"] == "Untreated" for run in baseline))
        self.assertTrue(all(run["reported_exposure"] == "INSUFFICIENT" for run in baseline))
        self.assertTrue(all(run["sample_role"] == "UNRESOLVED_UNTREATED_ZERO_HOUR_BASELINE"
                            for run in baseline))
        self.assertEqual(self.document["counts"]["confirmed_mock_controls"], 0)

    def test_exposure_supported_only_for_the_twelve_linked_six_to_seventy_two_hour_runs(self):
        supported = [run for run in self.runs if run["reported_exposure"] == "SUPPORTED"]
        self.assertEqual(len(supported), 12)
        self.assertEqual({run["timepoint_hours"] for run in supported}, {6, 24, 48, 72})

    def test_archive_identity_gate_and_acquisition_policy_are_unchanged(self):
        self.assertEqual(POLICY["policy_version"], "public-virus-v1")
        self.assertEqual(
            POLICY["viruses"]["hcov-229e"]["identity_attribute_keys"],
            ["virus", "virus species", "infecting virus", "viral species", "pathogen"],
        )
        for run in self.runs:
            result = assess_identity(
                {"organism": "Homo sapiens", "attributes": {"host": "Homo sapiens"}},
                "hcov-229e",
            )
            self.assertEqual(result["status"], "insufficient")
            self.assertEqual(run["current_policy"], "HELD")
        self.assertFalse(self.document["acquisition_enabled"])
        self.assertFalse(self.document["authorizing"])

    def test_fastq_manifest_metadata_is_complete_and_within_cap_without_retrieval(self):
        for run in self.runs:
            self.assertGreater(run["fastq_bytes"], 0)
            self.assertLessEqual(run["fastq_bytes"], 1_000_000_000)
            self.assertRegex(run["fastq_md5"], r"^[0-9a-f]{32}$")
        self.assertFalse(self.document["retrieval"]["reads_downloaded_or_inspected"])

    def test_counts_match_run_level_records_and_snapshot_hashes_are_not_authenticators(self):
        counts = self.document["counts"]
        self.assertEqual(counts["accession_relationships_verified"], len(self.runs))
        self.assertEqual(counts["study_reported_exposure_supported"],
                         sum(run["reported_exposure"] == "SUPPORTED" for run in self.runs))
        self.assertEqual(counts["unresolved_accession_mappings"], 0)
        self.assertFalse(self.document["retrieval"]["snapshot_hashes_are_authenticators"])


if __name__ == "__main__":
    unittest.main()
