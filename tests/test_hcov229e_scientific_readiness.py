import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs" / "hcov229e-scientific-readiness-v1.json"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "hcov229e_sources" / "real_reduced"


class ScientificReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decision = json.loads(DECISION_PATH.read_text(encoding="utf-8"))

    def test_exact_scope_and_non_authorizing_status(self):
        record = self.decision
        self.assertEqual(record["schema"], "hcov229e-scientific-readiness-v1")
        self.assertEqual(
            record["review_scope"]["scope"],
            {
                "virus": "HCoV-229E",
                "geo_series": "GSE155986",
                "geo_sample": "GSM4718636",
                "bioproject": "PRJNA656274",
                "sra_study": "SRP276927",
                "biosample": "SAMN15776099",
                "sra_experiment": "SRX8920123",
                "sra_run": "SRR12424250",
                "publication_doi": "10.1371/journal.pone.0247128",
            },
        )
        decision = record["decision"]
        self.assertEqual(decision["scientific_status"], "HELD")
        self.assertEqual(decision["sequence_confirmation"], "NOT_ASSESSED")
        self.assertEqual(decision["technical_readiness"], "NO_GO_FOR_REAL_READ_ANALYSIS")
        self.assertFalse(decision["acquisition_enabled"])
        self.assertFalse(decision["acquisition_authorized"])
        self.assertFalse(decision["authorizing"])
        self.assertFalse(decision["prior_conditional_go_is_approval"])
        self.assertEqual(decision["reference_panel_status"], "NOT_ACTIVATED")

    def test_no_reads_or_reference_sequences_were_acquired(self):
        scope = self.decision["review_scope"]
        self.assertTrue(scope["metadata_only"])
        self.assertFalse(scope["reads_downloaded_or_inspected"])
        self.assertFalse(scope["biological_reference_sequences_downloaded"])
        self.assertFalse(scope["analysis_performed"])
        panel = self.decision["reference_panel"]
        self.assertFalse(panel["artifact_sequences_downloaded"])
        self.assertTrue(panel["all_unacquired_artifact_checksums_are_null"])
        for artifact in panel["artifacts"]:
            self.assertIsNone(artifact["artifact_sha256"], artifact["role"])

    def test_accession_chain_and_evidence_classes_stay_separate(self):
        crosswalk = self.decision["accession_crosswalk"]
        self.assertEqual(crosswalk["status"], "SUPPORTED")
        self.assertEqual(crosswalk["relationships_verified_in_study_set"], 15)
        self.assertEqual(crosswalk["unresolved_accession_mappings"], 0)
        self.assertEqual(crosswalk["pilot_run"]["run"], "SRR12424250")
        findings = {item["id"]: item for item in self.decision["evidence_findings"]}
        self.assertEqual(findings["archive_identity"]["status"], "INSUFFICIENT")
        self.assertEqual(findings["reported_exposure"]["status"], "SUPPORTED")
        self.assertEqual(findings["sequence_presence"]["status"], "NOT_ASSESSED")
        self.assertEqual(findings["zero_hour_control_semantics"]["status"], "UNRESOLVED")
        self.assertEqual(findings["biological_independence"]["status"], "UNKNOWN")

    def test_96_hour_conflict_is_explicit_and_unresolved(self):
        item = next(x for x in self.decision["discrepancies"] if x["id"] == "96_hour_timepoint")
        self.assertEqual(item["status"], "UNRESOLVED")
        text = " ".join(x["statement"] for x in item["observations"])
        self.assertIn("72", text)
        self.assertIn("96", text)
        self.assertIn("No 96-hour GSM/SRX/SRR", item["finding"])
        self.assertIn("Do not infer", item["resolution"])
        sample_text = (FIXTURE_ROOT / "geo_sample.soft").read_text(encoding="utf-8")
        series_text = (FIXTURE_ROOT / "geo_series.soft").read_text(encoding="utf-8")
        self.assertIn("0, 6, 24, 48, 72 and 96 hours", sample_text)
        self.assertIn("0, 6, 24, 48 and 72", series_text)
        self.assertEqual(series_text.count("!Series_sample_id ="), 15)

    def test_sources_are_dated_and_capture_hashes_are_well_formed(self):
        self.assertTrue(self.decision["sources"])
        for source in self.decision["sources"]:
            self.assertTrue(source["id"])
            self.assertTrue(source["url"])
            self.assertTrue(source["retrieved_at"])
            digest = source.get("response_sha256")
            if digest:
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
        for artifact in self.decision["reference_panel"]["artifacts"]:
            self.assertTrue(artifact["source_urls"], artifact["role"])
            self.assertTrue(all(url.startswith("https://") for url in artifact["source_urls"]))

    def test_interpretation_does_not_upgrade_predictions_to_function(self):
        limits = self.decision["interpretation_boundaries"]
        self.assertTrue(limits["canonical_subgenomic_junction_is_not_automatically_a_dvg"])
        self.assertTrue(limits["dvg_caller_output_does_not_establish_function"])
        self.assertTrue(limits["no_hit_does_not_establish_novelty"])
        self.assertTrue(limits["co_detection_does_not_establish_helper_dependence"])
        self.assertTrue(limits["structure_prediction_does_not_establish_function"])


if __name__ == "__main__":
    unittest.main()
