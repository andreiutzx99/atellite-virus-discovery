import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery.public_virus import (
    assess_identity, retrieve_accession, verify_public_record, verify_snapshot_index,
)
from satellite_discovery.cli import main as cli_main
from test_metadata import XML


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

    def test_accession_syntax_and_relationship_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "accession"):
                retrieve_accession("../SRR123", "hcov-229e", tmp, offline=True)
            xml = XML.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                with self.assertRaisesRegex(ValueError, "exactly one matching run"):
                    retrieve_accession("SRR999", "hcov-229e", tmp)

    def test_missing_sample_relationship_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = XML.replace('SAMPLE accession="SRSTEST"', 'SAMPLE accession=""')
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml):
                with self.assertRaisesRegex(ValueError, "linkage is incomplete"):
                    retrieve_accession("SRR123", "hcov-229e", tmp)

    def test_metadata_only_intake_and_edit_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = XML.replace("Homo sapiens", "Human coronavirus 229E")
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession("SRR123", "hcov-229e", tmp)
            self.assertEqual(doc["record"]["public_virus"]["status"], "accepted_for_technical_review")
            self.assertFalse(doc["manifest"]["read_download_enabled"])
            self.assertFalse(doc["manifest"]["qc_enabled"])
            self.assertTrue(verify_public_record(doc, Path(tmp) / "raw_metadata"))
            doc["record"]["organism"] = "Homo sapiens"
            with self.assertRaisesRegex(ValueError, "record changed"):
                verify_public_record(doc, Path(tmp) / "raw_metadata")

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
            xml = XML.replace("Homo sapiens", "Human coronavirus 229E")
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
            xml = XML.replace("Homo sapiens", "Human coronavirus 229E")
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession("SRR123", "hcov-229e", tmp, offline=True)
            self.assertEqual(doc["record"]["public_virus"]["status"], "unresolved")
            self.assertEqual(doc["record"]["technical_suitability"]["status"], "excluded")

    def test_amplicon_identity_does_not_make_library_suitable(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = XML.replace("RNA-Seq", "AMPLICON").replace("Homo sapiens", "Human coronavirus OC43")
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


if __name__ == "__main__":
    unittest.main()
