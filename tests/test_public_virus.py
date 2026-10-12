import json
import subprocess
import sys
import tempfile
import copy
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery.public_virus import (
    assess_identity, retrieve_accession, verify_public_record, verify_snapshot_index,
    _validate_accession_relationships,
)
from satellite_discovery.cli import main as cli_main
from test_metadata import XML


def _public_xml():
    return (XML.replace("SRPTEST", "SRP123")
            .replace("SRXTEST", "SRX123")
            .replace("SRSTEST", "SRS123")
            .replace("PRJNATEST", "PRJNA123")
            .replace("SAMNTEST", "SAMN123"))


class PublicVirusTests(unittest.TestCase):
    def test_sample_organism_supports_229e_without_catalog_and_keeps_unknowns(self):
        row = {"organism": "Human coronavirus 229E",
               "attributes": {"host": "Homo sapiens"}}
        result = assess_identity(row, "hcov-229e")
        self.assertEqual(result["status"], "accepted_for_technical_review")
        self.assertEqual(result["strain"], "UNKNOWN")
        self.assertEqual(result["isolate"], "UNKNOWN")
        self.assertEqual(result["laboratory_stock_catalogue"], "UNKNOWN")

    def test_host_and_title_mentions_do_not_establish_virus_identity(self):
        row = {"organism": "Homo sapiens", "sample_title": "229E infected cells",
               "study_title": "Human coronavirus 229E infection",
               "attributes": {"host": "Homo sapiens"}}
        self.assertEqual(assess_identity(row, "hcov-229e")["status"], "insufficient")

    def test_virus_specific_attribute_supports_oc43_with_unknown_strain(self):
        row = {"organism": "Homo sapiens",
               "attributes": {"host": "Homo sapiens", "infecting virus": "HCoV-OC43"}}
        result = assess_identity(row, "hcov-oc43")
        self.assertEqual(result["status"], "accepted_for_technical_review")
        self.assertEqual(result["strain"], "UNKNOWN")

    def test_conflicting_and_excluded_identities_are_held(self):
        conflict = {"organism": "HCoV-229E",
                    "attributes": {"virus": "HCoV-OC43"}}
        self.assertEqual(assess_identity(conflict, "hcov-229e")["status"], "conflicting")
        excluded = {"organism": "HCoV-229E", "study_title": "SARS-CoV-2 comparison"}
        self.assertEqual(assess_identity(excluded, "hcov-229e")["status"], "excluded")

    def test_mixed_modified_and_unconfigured_second_pathogen_are_held(self):
        target = {"organism": "Human coronavirus 229E",
                  "attributes": {"infection type": "coinfection"}}
        self.assertEqual(assess_identity(target, "hcov-229e")["status"], "review_required")
        second = {"organism": "Human coronavirus 229E",
                  "attributes": {"pathogen": "HCoV-229E and influenza A"}}
        decision = assess_identity(second, "hcov-229e")
        self.assertEqual(decision["status"], "review_required")
        self.assertTrue(decision["review_evidence"])
        modified = {"organism": "Human coronavirus 229E",
                    "sample_title": "recombinant engineered virus"}
        self.assertEqual(assess_identity(modified, "hcov-229e")["status"], "review_required")

    def test_study_context_and_independent_strains_are_not_overcalled(self):
        row = {"organism": "Human coronavirus 229E",
               "study_title": "Comparison of 229E and influenza A in cell culture",
               "attributes": {"strain": "clinical isolate X"}}
        self.assertEqual(assess_identity(row, "hcov-229e")["status"],
                         "accepted_for_technical_review")

    def test_table_driven_adversarial_identity_matrix(self):
        cases = [
            ("single virus, no catalogue", {"organism": "Human coronavirus 229E"}, "accepted_for_technical_review"),
            ("known strain", {"organism": "HCoV-229E", "attributes": {"strain": "clinical isolate"}}, "accepted_for_technical_review"),
            ("unknown strain", {"organism": "HCoV-229E"}, "accepted_for_technical_review"),
            ("conflicting supported virus", {"organism": "HCoV-229E", "attributes": {"virus": "HCoV-OC43"}}, "conflicting"),
            ("host only", {"organism": "Homo sapiens", "attributes": {"host": "HCoV-229E"}}, "insufficient"),
            ("title only", {"organism": "Homo sapiens", "sample_title": "229E infected cells"}, "insufficient"),
            ("untyped claim", {"organism": "Homo sapiens", "attributes": {"comment": "infected with HCoV-229E"}}, "insufficient"),
            ("plus separator and unsupported second agent", {"organism": "HCoV-229E", "attributes": {"pathogen": "HCoV-229E + Dengue virus"}}, "review_required"),
            ("semicolon list", {"organism": "HCoV-229E", "attributes": {"virus": "HCoV-229E; influenza A"}}, "review_required"),
            ("comma list", {"organism": "HCoV-229E", "attributes": {"pathogen": "HCoV-229E, influenza A"}}, "review_required"),
            ("slash list", {"organism": "HCoV-229E", "attributes": {"virus species": "HCoV-229E / dengue virus"}}, "review_required"),
            ("conjunction list and alternate key format", {"organism": "Homo sapiens", "attributes": {"virus_species": "HCoV-229E and influenza A"}}, "review_required"),
            ("same-virus strain labels", {"organism": "HCoV-229E", "attributes": {"pathogen": "HCoV-229E strain A / HCoV-229E strain B"}}, "accepted_for_technical_review"),
            ("same-virus strain suffix shorthand", {"organism": "HCoV-229E", "attributes": {"pathogen": "HCoV-229E strain A/B"}}, "accepted_for_technical_review"),
            ("different supported viruses in one typed field", {"organism": "HCoV-229E", "attributes": {"virus": "HCoV-229E and HCoV-OC43"}}, "review_required"),
            ("repeated typed values with unsupported second pathogen", {"organism": "HCoV-229E", "attributes": {"pathogen": "HCoV-229E"}, "public_virus_attribute_entries": [{"key": "pathogen", "value": "HCoV-229E"}, {"key": "pathogen", "value": "Dengue virus"}]}, "review_required"),
            ("alternate mixed flag", {"organism": "HCoV-229E", "attributes": {"mixed_infection_status": "TRUE"}}, "review_required"),
            ("explicit additional pathogen", {"organism": "HCoV-229E", "attributes": {"secondary pathogen": "influenza A"}}, "review_required"),
            ("recombinant sample", {"organism": "HCoV-229E", "sample_title": "recombinant virus"}, "review_required"),
            ("modified sample", {"organism": "HCoV-229E", "sample_title": "mouse-adapted mutant"}, "review_required"),
            ("excluded pathogen takes precedence", {"organism": "HCoV-229E", "attributes": {"pathogen": "HCoV-229E + SARS-CoV-2"}}, "excluded"),
            ("broad study title is not sample-level mixture", {"organism": "HCoV-229E", "study_title": "229E and influenza comparison"}, "accepted_for_technical_review"),
            ("misleading title wording does not establish identity", {"organism": "Homo sapiens", "sample_title": "HCoV-229E mutant-cell comparison"}, "review_required"),
        ]
        for name, row, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(assess_identity(row, "hcov-229e")["status"], expected)

    def test_malformed_attributes_and_unsupported_virus_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "dictionary"):
            assess_identity({"organism": "HCoV-229E", "attributes": []}, "hcov-229e")
        with self.assertRaisesRegex(ValueError, "key/value"):
            assess_identity({"attributes": {}, "public_virus_attribute_entries": ["broken"]}, "hcov-229e")
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            assess_identity({"organism": "HCoV-229E"}, "hcov-229e-something-else")

    def test_repeated_raw_typed_attributes_are_preserved_for_identity_review(self):
        xml = _public_xml().replace("Homo sapiens", "Human coronavirus 229E")
        xml = xml.replace(
            "</SAMPLE_ATTRIBUTES>",
            '<SAMPLE_ATTRIBUTE><TAG>pathogen</TAG><VALUE>HCoV-229E</VALUE></SAMPLE_ATTRIBUTE>'
            '<SAMPLE_ATTRIBUTE><TAG>pathogen</TAG><VALUE>Dengue virus</VALUE></SAMPLE_ATTRIBUTE>'
            "</SAMPLE_ATTRIBUTES>",
        ).replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
        with tempfile.TemporaryDirectory() as tmp, \
             patch("satellite_discovery.public_virus.Client.search", return_value={"ids": ["uid"]}), \
             patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
             patch("satellite_discovery.public_virus.enrich_ena"):
            doc = retrieve_accession("SRR123", "hcov-229e", tmp)
        identity = doc["record"]["public_virus"]
        self.assertEqual(identity["status"], "review_required")
        self.assertTrue(any(
            evidence["field"] == "attribute:pathogen"
            and evidence["reason"] == "conflicting_repeated_typed_pathogen_values"
            for evidence in identity["review_evidence"]
        ))

    def test_stock_laboratory_and_archive_centre_are_distinct(self):
        result = assess_identity({
            "organism": "Human coronavirus OC43", "laboratory": "GEO",
            "attributes": {"strain designation": "OC43 clinical isolate"},
        }, "hcov-oc43")
        self.assertEqual(result["archive_center_name"], "GEO")
        self.assertEqual(result["experimental_laboratory"], "UNKNOWN")
        self.assertEqual(result["laboratory_stock_catalogue"], "UNKNOWN")
        self.assertEqual(result["strain"], "OC43 clinical isolate")
        self.assertNotIn("laboratory", result)

    def test_sanitized_archive_metadata_fixtures_are_reproducible(self):
        fixture_dir = Path(__file__).parent / "fixtures" / "public_virus_metadata"
        for accession, virus in (("SRR12424243", "hcov-229e"),
                                 ("SRR3198409", "hcov-oc43")):
            fixture = json.loads((fixture_dir / (accession + ".json")).read_text())
            row = copy.deepcopy(fixture["record"])
            with tempfile.TemporaryDirectory() as tmp, \
                 patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["archive-id"]}), \
                 patch("satellite_discovery.public_virus.Client.fetch",
                       return_value="<metadata-fixture/>"), \
                 patch("satellite_discovery.public_virus.parse_packages",
                       return_value=[row]), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession(accession, virus, tmp)
            record, expected = doc["record"], fixture["expected"]
            self.assertRegex(record["sample_accession"], r"^SRS[0-9]+$")
            self.assertRegex(record["biosample"], r"^SAMN[0-9]+$")
            self.assertRegex(record["study_accession"], r"^SRP[0-9]+$")
            self.assertRegex(record["bioproject"], r"^PRJNA[0-9]+$")
            self.assertNotEqual(record["sample_accession"], record["biosample"])
            self.assertNotEqual(record["study_accession"], record["bioproject"])
            self.assertEqual(record["public_virus"]["status"], expected["identity"])
            self.assertEqual(record["technical_suitability"]["status"], expected["library"])
            self.assertEqual(record["fastq_assessment"]["status"], expected["fastq"])
            self.assertEqual(record["pilot_readiness"]["status"], expected["pilot"])
            if accession == "SRR12424243":
                self.assertEqual(record["technical_suitability"]["reasons"], [])
                self.assertEqual(record["pilot_readiness"]["reasons"],
                                 ["sample_level_virus_identity_missing"])
            else:
                self.assertIn("library_strategy_unsuitable_for_unbiased_discovery",
                              record["technical_suitability"]["reasons"])
                self.assertNotIn("archive_sample_level_virus_identity",
                                 record["pilot_readiness"]["reasons"])

    def test_accession_syntax_and_relationship_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "accession"):
                retrieve_accession("../SRR123", "hcov-229e", tmp, offline=True)
            xml = _public_xml().replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                with self.assertRaisesRegex(ValueError, "exactly one matching run"):
                    retrieve_accession("SRR999", "hcov-229e", tmp)

    def test_missing_sample_relationship_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = _public_xml().replace('SAMPLE accession="SRS123"', 'SAMPLE accession=""')
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml):
                with self.assertRaisesRegex(ValueError, "linkage is incomplete"):
                    retrieve_accession("SRR123", "hcov-229e", tmp)

    def test_metadata_only_intake_and_edit_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = _public_xml().replace("Homo sapiens", "Human coronavirus 229E")
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession("SRR123", "hcov-229e", tmp)
            self.assertEqual(doc["record"]["public_virus"]["status"], "accepted_for_technical_review")
            self.assertEqual(doc["record"]["archive_center_name"], "Example centre")
            self.assertNotIn("laboratory", doc["record"])
            self.assertEqual(doc["record"]["public_virus"]["experimental_laboratory"], "UNKNOWN")
            self.assertFalse(doc["manifest"]["read_download_enabled"])
            self.assertFalse(doc["manifest"]["qc_enabled"])
            self.assertTrue(verify_public_record(doc, Path(tmp) / "raw_metadata"))
            doc["record"]["organism"] = "Homo sapiens"
            with self.assertRaisesRegex(ValueError, "record changed"):
                verify_public_record(doc, Path(tmp) / "raw_metadata")

    def test_local_digest_verification_is_not_acquisition_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = _public_xml().replace("Homo sapiens", "Human coronavirus 229E")
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"]}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession("SRR123", "hcov-229e", tmp)
            doc["record"]["organism"] = "Homo sapiens"
            doc["manifest"]["record_sha256"] = __import__("hashlib").sha256(
                json.dumps(doc["record"], sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            self.assertTrue(verify_public_record(doc, Path(tmp) / "raw_metadata"))
            self.assertFalse(doc["manifest"]["read_download_enabled"])
            self.assertFalse(doc["manifest"]["qc_enabled"])
            self.assertFalse(doc["record"]["curator_evidence"]["may_authorize"])

    def test_snapshot_and_policy_digest_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "response.txt"
            path.write_text("archive response")
            import hashlib
            entries = [{"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
            self.assertTrue(verify_snapshot_index(tmp, entries))
            path.write_text("changed response")
            with self.assertRaisesRegex(ValueError, "snapshot missing or changed"):
                verify_snapshot_index(tmp, entries)
        with tempfile.TemporaryDirectory() as tmp:
            xml = _public_xml().replace("Homo sapiens", "Human coronavirus 229E")
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession("SRR123", "hcov-229e", tmp)
            doc["manifest"]["policy_sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "policy version or digest changed"):
                verify_public_record(doc, Path(tmp) / "raw_metadata")

    def test_offline_cache_does_not_promote_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = _public_xml().replace("Homo sapiens", "Human coronavirus 229E")
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession("SRR123", "hcov-229e", tmp, offline=True)
            self.assertEqual(doc["record"]["public_virus"]["status"], "unresolved")
            self.assertEqual(doc["record"]["technical_suitability"]["status"], "eligible_for_review")
            self.assertEqual(doc["record"]["technical_suitability"]["reasons"], [])
            self.assertEqual(doc["record"]["pilot_readiness"]["status"], "held_for_identity_review")
            self.assertEqual(doc["record"]["pilot_readiness"]["reasons"],
                             ["offline_archive_snapshot_not_independently_authenticated",
                              "ena_fastq_not_listed"])

    def test_amplicon_identity_does_not_make_library_suitable(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = _public_xml().replace("RNA-Seq", "AMPLICON").replace("Homo sapiens", "Human coronavirus OC43")
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession("SRR123", "hcov-oc43", tmp)
            self.assertEqual(doc["record"]["public_virus"]["status"],
                             "accepted_for_technical_review")
            self.assertEqual(doc["record"]["technical_suitability"]["status"], "excluded")
            self.assertIn("library_strategy_unsuitable_for_unbiased_discovery",
                          doc["record"]["technical_suitability"]["reasons"])

    def test_public_profile_cannot_start_qc(self):
        argv = ["satellite-discovery", "--public-virus", "hcov-229e",
                "--public-virus-accession", "SRR123", "--stage", "qc"]
        with patch.object(sys, "argv", argv), \
             patch("satellite_discovery.cli.retrieve_accession") as intake:
            with self.assertRaises(SystemExit) as raised:
                cli_main()
            self.assertEqual(raised.exception.code, 2)
            intake.assert_not_called()

    def test_accession_namespace_mismatches_are_rejected(self):
        row = {
            "run_accession": "SRR123", "experiment_accession": "SRX123",
            "sample_accession": "SRS123", "study_accession": "SRP123",
            "biosample": "SAMN123", "bioproject": "PRJNA123",
        }
        _validate_accession_relationships(row)
        for field, wrong in (
            ("sample_accession", "SAMN123"),
            ("study_accession", "PRJNA123"),
            ("biosample", "SRS123"),
            ("bioproject", "SRP123"),
            ("experiment_accession", "SRS123"),
            ("run_accession", "SAMN123"),
        ):
            broken = {**row, field: wrong}
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    _validate_accession_relationships(broken)

    def test_multiple_readiness_failures_remain_separate(self):
        row = {
            "run_accession": "SRR123", "experiment_accession": "SRX123",
            "sample_accession": "SRS123", "study_accession": "SRP123",
            "organism": "Homo sapiens", "attributes": {},
            "library_strategy": "AMPLICON", "library_source": "VIRAL RNA",
            "library_selection": "PCR", "platform": "ILLUMINA",
            "layout": "SINGLE", "total_spots": 2_000_000,
            "raw_read_availability": "unverified",
        }
        with tempfile.TemporaryDirectory() as tmp, \
             patch("satellite_discovery.public_virus.Client.search", return_value={"ids": ["uid"]}), \
             patch("satellite_discovery.public_virus.Client.fetch", return_value="<metadata-fixture/>"), \
             patch("satellite_discovery.public_virus.parse_packages", return_value=[row]), \
             patch("satellite_discovery.public_virus.enrich_ena"):
            doc = retrieve_accession("SRR123", "hcov-229e", tmp)
        record = doc["record"]
        self.assertEqual(record["public_virus"]["status"], "insufficient")
        self.assertEqual(record["technical_suitability"]["status"], "excluded")
        self.assertIn("library_strategy_unsuitable_for_unbiased_discovery",
                      record["technical_suitability"]["reasons"])
        self.assertEqual(record["fastq_assessment"]["status"], "unverified_or_incomplete")
        self.assertIn("ena_fastq_not_listed", record["fastq_assessment"]["reasons"])
        self.assertEqual(record["pilot_readiness"]["status"], "held_for_identity_review")
        self.assertIn("sample_level_virus_identity_missing", record["pilot_readiness"]["reasons"])
        self.assertIn("library_strategy_unsuitable_for_unbiased_discovery",
                      record["pilot_readiness"]["reasons"])
        self.assertIn("ena_fastq_not_listed", record["pilot_readiness"]["reasons"])

    def test_documented_python_module_entry_point(self):
        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "satellite_discovery", "--help"],
            cwd=repo, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--public-virus-accession", result.stdout)


if __name__ == "__main__":
    unittest.main()
