import json
import sys
import tempfile
import copy
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery.public_virus import (
    assess_identity, retrieve_accession, verify_public_record, verify_snapshot_index,
    _validate_archive_accessions,
)
from satellite_discovery.cli import main as cli_main
from satellite_discovery.metadata import parse_packages
from test_metadata import XML


def public_xml():
    return (XML.replace("SRPTEST", "SRP123456")
            .replace("SRXTEST", "SRX123456")
            .replace("SRSTEST", "SRS123456")
            .replace("PRJNATEST", "PRJNA123456")
            .replace("SAMNTEST", "SAMN123456"))


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

    def test_bounded_adversarial_identity_matrix_blocks_mixed_pilot_readiness(self):
        cases = [
            ("known single", {"pathogen": "HCoV-229E"}, "accepted_for_technical_review",
             "archive_sample_level_virus_identity"),
            ("known second", {"pathogen": "HCoV-229E + HCoV-OC43"}, "review_required",
             "multiple_or_ambiguous_pathogen_metadata_requires_review"),
            ("unknown second", {"pathogen": "HCoV-229E with Dengue virus"}, "review_required",
             "multiple_or_ambiguous_pathogen_metadata_requires_review"),
            ("repeated typed pathogen fields",
             {"pathogen": "HCoV-229E", "virus species": "Dengue virus"},
             "review_required", "multiple_or_ambiguous_pathogen_metadata_requires_review"),
            ("explicit flag", {"infection type": "coinfection"}, "review_required",
             "multiple_or_ambiguous_pathogen_metadata_requires_review"),
            ("contradictory", {"virus": "HCoV-OC43"}, "conflicting",
             "multiple_public_virus_identities"),
            ("excluded", {"pathogen": "HCoV-229E and SARS-CoV-2"}, "excluded",
             "excluded_pathogen_mentioned_in_metadata"),
            ("same-virus isolates and strains",
             {"pathogen": "HCoV-229E isolate VR-740 and HCoV-229E strain VR-740"},
             "accepted_for_technical_review", "archive_sample_level_virus_identity"),
            ("ambiguous", {"pathogen": "HCoV-229E / possibly dengue"}, "review_required",
             "multiple_or_ambiguous_pathogen_metadata_requires_review"),
            ("study context", {}, "accepted_for_technical_review",
             "archive_sample_level_virus_identity"),
            ("empty", {"pathogen": ""}, "accepted_for_technical_review",
             "archive_sample_level_virus_identity"),
            ("malformed", {"pathogen": "???"}, "review_required",
             "multiple_or_ambiguous_pathogen_metadata_requires_review"),
            ("infected with one virus", {"pathogen": "infected with HCoV-229E"},
             "accepted_for_technical_review", "archive_sample_level_virus_identity"),
            ("strain designation", {"pathogen": "HCoV-229E with strain designation VR-740"},
             "accepted_for_technical_review", "archive_sample_level_virus_identity"),
            ("punctuated isolate identifier",
             {"pathogen": "HCoV-229E with isolate VR-740/1"},
             "accepted_for_technical_review", "archive_sample_level_virus_identity"),
        ]
        for connector in ("and", "with", "alongside", "together with", "plus",
                          ";", ",", "/", "&"):
            cases.append((f"separator {connector}",
                          {"pathogen": f"HCoV-229E {connector} Dengue virus"},
                          "review_required",
                          "multiple_or_ambiguous_pathogen_metadata_requires_review"))

        for label, attrs, expected, reason in cases:
            with self.subTest(case=label):
                study = ("Comparison of 229E and Dengue viruses"
                         if label == "study context" else "")
                row = {"organism": "Human coronavirus 229E", "study_title": study,
                       "attributes": attrs}
                identity = assess_identity(row, "hcov-229e")
                self.assertEqual(identity["status"], expected)
                self.assertEqual(identity["reason"], reason)
                if expected == "review_required":
                    self.assertTrue(identity["review_evidence"])
                    self.assertTrue(all("field" in item and "value" in item
                                        for item in identity["review_evidence"]))
                    record = parse_packages(public_xml(), None)[0]
                    record.update({"run_accession": "SRR123456",
                                   "organism": "Human coronavirus 229E",
                                   "attributes": attrs,
                                   "raw_read_availability": "ena_fastq_listed",
                                   "fastq_ftp": "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/x.fastq.gz",
                                   "fastq_md5": "0" * 32, "fastq_bytes": "100"})
                    with tempfile.TemporaryDirectory() as tmp, \
                         patch("satellite_discovery.public_virus.Client.search",
                               return_value={"ids": ["uid"]}), \
                         patch("satellite_discovery.public_virus.Client.fetch",
                               return_value="<metadata/>"), \
                         patch("satellite_discovery.public_virus.parse_packages",
                               return_value=[record]), \
                          patch("satellite_discovery.public_virus._sample_attribute_entries",
                                return_value=[{"key": key, "value": value}
                                              for key, value in attrs.items()]), \
                         patch("satellite_discovery.public_virus.enrich_ena"), \
                         patch("satellite_discovery.public_virus.files_for_run",
                               return_value=[{"bytes": 100}]):
                        doc = retrieve_accession("SRR123456", "hcov-229e", tmp)
                    self.assertEqual(doc["record"]["technical_suitability"]["status"],
                                     "eligible_for_review")
                    self.assertNotEqual(doc["record"]["pilot_readiness"]["status"],
                                        "eligible_for_review")

    def test_INSDC_accession_namespaces_and_optional_links(self):
        for run, experiment, sample, study in (
            ("SRR1", "SRX2", "SRS3", "SRP4"),
            ("ERR1", "ERX2", "ERS3", "ERP4"),
            ("DRR1", "DRX2", "DRS3", "DRP4"),
        ):
            row = {"run_accession": run, "experiment_accession": experiment,
                   "sample_accession": sample, "study_accession": study}
            _validate_archive_accessions(row)
            for value in ("SAMN1", "SAMEA1", "SAMD1"):
                row["biosample"] = value
                _validate_archive_accessions(row)
            for value in ("PRJNA1", "PRJEB1", "PRJDB1"):
                row["bioproject"] = value
                _validate_archive_accessions(row)
            row.pop("biosample")
            row.pop("bioproject")
            _validate_archive_accessions(row)
        base = {"run_accession": "ERR1", "experiment_accession": "ERX2",
                "sample_accession": "ERS3", "study_accession": "ERP4"}
        for field, bad in (("sample_accession", "SAMN1"), ("study_accession", "PRJNA1"),
                           ("biosample", "SRR1"), ("biosample", "SAMEAX"),
                           ("bioproject", "SRP1"), ("bioproject", "PRJXX1"),
                           ("experiment_accession", "ERS3")):
            with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                _validate_archive_accessions({**base, field: bad})

    def test_stock_laboratory_and_archive_centre_are_distinct(self):
        result = assess_identity({
            "organism": "Human coronavirus OC43", "laboratory": "GEO",
            "attributes": {"strain designation": "OC43 clinical isolate"},
        }, "hcov-oc43")
        self.assertEqual(result["archive_center_name"], "GEO")
        self.assertEqual(result["experimental_laboratory"], "UNKNOWN")
        self.assertEqual(result["laboratory_stock_catalogue"], "UNKNOWN")
        self.assertEqual(result["strain"], "OC43 clinical isolate")

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
                  patch("satellite_discovery.public_virus._sample_attribute_entries",
                        return_value=[{"key": key, "value": value}
                                      for key, value in row["attributes"].items()]), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession(accession, virus, tmp)
            record, expected = doc["record"], fixture["expected"]
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

    def test_repeated_raw_pathogen_attributes_survive_both_orders(self):
        attrs_xml = (
            '<SAMPLE_ATTRIBUTES><SAMPLE_ATTRIBUTE><TAG>pathogen</TAG><VALUE>{}</VALUE>'
            '</SAMPLE_ATTRIBUTE><SAMPLE_ATTRIBUTE><TAG>pathogen</TAG><VALUE>{}</VALUE>'
            '</SAMPLE_ATTRIBUTE></SAMPLE_ATTRIBUTES>'
        )
        original = (
            '<SAMPLE_ATTRIBUTES><SAMPLE_ATTRIBUTE><TAG>host</TAG>'
            '<VALUE>Homo sapiens</VALUE></SAMPLE_ATTRIBUTE></SAMPLE_ATTRIBUTES>'
        )
        cases = [
            (("Dengue virus", "HCoV-229E"), "review_required"),
            (("HCoV-229E", "Dengue virus"), "review_required"),
            (("HCoV-229E", "HCoV-229E"), "accepted_for_technical_review"),
        ]

        def enrich(_client, row):
            row.update({"raw_read_availability": "ena_fastq_listed",
                        "fastq_ftp": "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/x.fastq.gz",
                        "fastq_md5": "0" * 32, "fastq_bytes": "100"})

        for values, expected in cases:
            xml = (public_xml().replace(
                       "<SCIENTIFIC_NAME>Homo sapiens</SCIENTIFIC_NAME>",
                       "<SCIENTIFIC_NAME>Human coronavirus 229E</SCIENTIFIC_NAME>")
                   .replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
                   .replace(original, attrs_xml.format(*values)))
            with self.subTest(values=values), tempfile.TemporaryDirectory() as tmp, \
                 patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"]}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena", side_effect=enrich), \
                 patch("satellite_discovery.public_virus.files_for_run",
                       return_value=[{"bytes": 100}]):
                document = retrieve_accession("SRR123", "hcov-229e", tmp)
            record = document["record"]
            self.assertEqual(record["public_virus"]["status"], expected)
            self.assertEqual([item["value"] for item in record["raw_sample_attributes"]],
                             list(values))
            if expected == "review_required":
                self.assertEqual(
                    record["public_virus"]["reason"],
                    "multiple_or_ambiguous_pathogen_metadata_requires_review",
                )
                self.assertTrue(any(
                    item["field"] == "attribute:pathogen" and item["value"] == "Dengue virus"
                    for item in record["public_virus"]["review_evidence"]
                ))
                self.assertEqual(record["pilot_readiness"]["status"],
                                 "held_for_identity_review")
                self.assertNotEqual(record["pilot_readiness"]["status"],
                                    "eligible_for_review")
            else:
                self.assertEqual(record["pilot_readiness"]["status"],
                                 "eligible_for_review")

    def test_accession_syntax_and_relationship_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "accession"):
                retrieve_accession("../SRR123", "hcov-229e", tmp, offline=True)
            xml = public_xml().replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                with self.assertRaisesRegex(ValueError, "exactly one matching run"):
                    retrieve_accession("SRR999", "hcov-229e", tmp)

    def test_missing_sample_relationship_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = public_xml().replace('SAMPLE accession="SRS123456"', 'SAMPLE accession=""')
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml):
                with self.assertRaisesRegex(ValueError, "linkage is incomplete"):
                    retrieve_accession("SRR123", "hcov-229e", tmp)

    def test_metadata_only_intake_and_edit_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = public_xml().replace("Homo sapiens", "Human coronavirus 229E")
            xml = xml.replace("SRRTEST1", "SRR123").replace("SRRTEST2", "SRR1234")
            with patch("satellite_discovery.public_virus.Client.search",
                       return_value={"ids": ["uid"], "count": 1}), \
                 patch("satellite_discovery.public_virus.Client.fetch", return_value=xml), \
                 patch("satellite_discovery.public_virus.enrich_ena"):
                doc = retrieve_accession("SRR123", "hcov-229e", tmp)
            self.assertEqual(doc["record"]["public_virus"]["status"], "accepted_for_technical_review")
            self.assertFalse(doc["manifest"]["read_download_enabled"])
            self.assertFalse(doc["manifest"]["qc_enabled"])
            self.assertEqual(doc["record"]["archive_center_name"], "Example centre")
            self.assertNotIn("laboratory", doc["record"])
            self.assertEqual(doc["record"]["public_virus"]["experimental_laboratory"],
                             "UNKNOWN")
            self.assertTrue(verify_public_record(doc, Path(tmp) / "raw_metadata"))
            doc["record"]["organism"] = "Homo sapiens"
            with self.assertRaisesRegex(ValueError, "record changed"):
                verify_public_record(doc, Path(tmp) / "raw_metadata")

    def test_local_digest_verification_is_not_acquisition_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml = public_xml().replace("Homo sapiens", "Human coronavirus 229E")
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
            xml = public_xml().replace("Homo sapiens", "Human coronavirus 229E")
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
            xml = public_xml().replace("Homo sapiens", "Human coronavirus 229E")
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
            xml = public_xml().replace("RNA-Seq", "AMPLICON").replace("Homo sapiens", "Human coronavirus OC43")
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

    def test_documented_module_command_shows_public_intake_help(self):
        project_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "satellite_discovery", "--help"],
            cwd=project_root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--public-virus-accession", result.stdout)
        self.assertIn("--public-virus", result.stdout)


if __name__ == "__main__":
    unittest.main()
