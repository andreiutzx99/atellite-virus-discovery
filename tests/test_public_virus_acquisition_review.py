import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from satellite_discovery import metadata_filter, public_virus
from satellite_discovery.public_virus_acquisition_review import (
    MAX_PACKET_BYTES,
    AcquisitionReviewError,
    build_review_packet as _build_review_packet,
    serialize_review_packet,
)
from satellite_discovery.public_virus_provenance import create_document
from satellite_discovery.sequence_downloader import files_for_run


_SNAPSHOT_TEMP = tempfile.TemporaryDirectory(prefix="public-virus-review-test-")
_SNAPSHOT_DIR = Path(_SNAPSHOT_TEMP.name)
_SNAPSHOT_NAME = "synthetic-sra-response.xml"
_SNAPSHOT_BYTES = b"<SRA>synthetic source response</SRA>\n"


def build_review_packet(document, provenance_document=None, *, raw_metadata_directory=_SNAPSHOT_DIR):
    return _build_review_packet(
        document, provenance_document,
        raw_metadata_directory=raw_metadata_directory,
    )


def make_intake(*, virus="hcov-229e", organism="Human coronavirus 229E",
                attributes=None, **overrides):
    snapshot_path = _SNAPSHOT_DIR / _SNAPSHOT_NAME
    snapshot_path.write_bytes(_SNAPSHOT_BYTES)
    record = {
        "run_accession": "SRR123456",
        "experiment_accession": "SRX123456",
        "sample_accession": "SRS123456",
        "biosample": "SAMN123456",
        "study_accession": "SRP123456",
        "bioproject": "PRJNA123456",
        "organism": organism,
        "attributes": attributes if attributes is not None else {"virus": "HCoV-229E"},
        "raw_sample_attributes": [
            {"key": key, "value": value}
            for key, value in (attributes if attributes is not None else
                               {"virus": "HCoV-229E"}).items()
        ],
        "platform": "ILLUMINA",
        "library_strategy": "RNA-Seq",
        "library_source": "TRANSCRIPTOMIC",
        "library_selection": "cDNA",
        "layout": "SINGLE",
        "total_spots": 24_000_000,
        "raw_read_availability": "ena_fastq_listed",
        "fastq_ftp": (
            "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/"
            "SRR123456/SRR123456.fastq.gz"
        ),
        "fastq_md5": "a" * 32,
        "fastq_bytes": "728420078",
    }
    record.update(overrides)
    record["public_virus"] = public_virus.assess_identity(record, virus)
    assessed = metadata_filter.assess(dict(record), min_spots=0)
    record["selection"] = assessed["selection"]
    record["exclusion_reasons"] = assessed["exclusion_reasons"]
    record["warnings"] = assessed["warnings"]
    library_reasons = assessed["exclusion_reasons"]
    record["technical_suitability"] = {
        "status": "eligible_for_review" if not library_reasons else "excluded",
        "reasons": library_reasons,
        "warnings": assessed["warnings"],
        "archive_errors": [],
    }
    try:
        fastqs = files_for_run(record)
        total = sum(item["bytes"] for item in fastqs)
        record["fastq_assessment"] = {
            "status": "complete_within_budget" if total <= 1_000_000_000
                      else "complete_over_budget",
            "complete": True, "total_bytes": total,
            "budget_bytes": 1_000_000_000, "fits_budget": total <= 1_000_000_000,
            "reasons": [] if total <= 1_000_000_000
                       else ["complete_fastq_exceeds_1gb_budget"],
        }
    except ValueError:
        record["fastq_assessment"] = {
            "status": "unverified_or_incomplete", "complete": False,
            "total_bytes": None, "budget_bytes": 1_000_000_000,
            "fits_budget": False, "reasons": ["ena_fastq_not_listed"],
        }
    record["pilot_readiness"] = {
        "status": "eligible_for_review" if (
            record["public_virus"]["status"] == "accepted_for_technical_review"
            and not library_reasons
            and record["fastq_assessment"]["fits_budget"]
        ) else "held_for_identity_review",
        "reasons": [],
    }
    record["curator_evidence"] = {
        "status": "pending_review", "may_authorize": False,
        "limitation": "No authenticated external trust anchor is implemented.",
    }
    manifest = {
        "schema": "public-virus-accession-manifest-v1",
        "profile": public_virus.POLICY["policy_version"],
        "policy_sha256": public_virus.POLICY_SHA256,
        "archive_source": "NCBI SRA / ENA",
        "retrieval_mode": "archive_client",
        "snapshot_index": [{
            "name": _SNAPSHOT_NAME,
            "sha256": hashlib.sha256(_SNAPSHOT_BYTES).hexdigest(),
        }],
        "archive_errors": [],
        "archive_snapshot_integrity": "digest_checked_against_local_manifest_only",
        "biological_confirmation": "not_performed",
        "read_download_enabled": False, "qc_enabled": False,
    }
    document = {"manifest": manifest, "record": record}
    manifest["record_sha256"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return document


def curator_evidence(state="accepted", statement="Synthetic curator assertion"):
    evidence = {
        "source": "curator_decision", "evidence_type": "synthetic",
        "review_state": state, "uncertainty": "Synthetic fixture only.",
        "statement": statement,
    }
    if state == "accepted":
        evidence["audit_reference"] = {
            "reviewer_id": "reviewer:test",
            "decision_id": "decision:test",
            "decision_rationale": "Synthetic test rationale.",
        }
    return evidence


def linked_provenance(*, conflict=False):
    state = "provisional" if conflict else "confirmed"
    identity = [curator_evidence("conflicting")] if conflict else [curator_evidence()]
    link = curator_evidence("conflicting" if conflict else "accepted", "Synthetic linkage")
    return create_document(
        [
            {"entity_id": "SRS123456", "entity_type": "sra_sample"},
            {"entity_id": "material-test", "entity_type": "biological_material",
             "identity_state": state, "identifiers": {"local_id": "MAT-test"},
             "identity_evidence": identity},
        ],
        [{
            "relationship_id": "sample-material",
            "relationship_type": "derived_from",
            "subject": "SRS123456", "object": "material-test",
            "evidence": [link],
        }],
    )


class PublicVirusAcquisitionReviewTests(unittest.TestCase):
    def test_eligible_review_is_not_download_authorization(self):
        document = make_intake()
        packet = build_review_packet(document)
        self.assertEqual(packet["outcome"], "eligible_for_curator_review")
        self.assertEqual(packet["run_accession"], "SRR123456")
        self.assertEqual(packet["fastq"]["file_count"], 1)
        self.assertEqual(packet["pilot_budget"]["status"], "within_budget")
        self.assertFalse(packet["may_download"])
        self.assertFalse(packet["download_enabled"])
        self.assertNotIn("download_authorized", json.dumps(packet))

    def test_missing_or_conflicting_sample_identity_is_not_eligible(self):
        missing = make_intake(organism="Homo sapiens", attributes={"host": "Homo sapiens"})
        self.assertEqual(build_review_packet(missing)["outcome"], "held_for_review")
        conflict = make_intake(organism="Human coronavirus 229E",
                               attributes={"virus": "HCoV-OC43"})
        packet = build_review_packet(conflict)
        self.assertEqual(packet["outcome"], "excluded")
        self.assertIn("virus_identity_excluded_or_conflicting",
                      {item["code"] for item in packet["reasons"]})

    def test_amplicon_is_excluded_even_with_matching_virus_identity(self):
        packet = build_review_packet(make_intake(library_strategy="AMPLICON"))
        self.assertEqual(packet["outcome"], "excluded")
        self.assertEqual(packet["library_suitability"]["status"], "excluded")

    def test_missing_files_and_inconsistent_manifest_are_held(self):
        missing = make_intake(raw_read_availability="not_listed",
                              fastq_ftp=None, fastq_md5=None, fastq_bytes=None)
        packet = build_review_packet(missing)
        self.assertEqual(packet["outcome"], "held_for_review")
        self.assertIn("fastq_metadata_missing_or_inconsistent",
                      {item["code"] for item in packet["reasons"]})
        corrupt = make_intake()
        corrupt["manifest"]["record_sha256"] = "0" * 64
        self.assertIn("intake_manifest_inconsistent",
                      {r["code"] for r in build_review_packet(corrupt)["reasons"]})

    def test_budget_is_decimal_one_gigabyte_and_over_budget_is_excluded(self):
        packet = build_review_packet(make_intake(fastq_bytes="1000000001"))
        self.assertEqual(packet["fastq"]["estimated_total_bytes"], 1_000_000_001)
        self.assertEqual(packet["pilot_budget"]["status"], "excluded")
        self.assertEqual(packet["outcome"], "excluded")

    def test_paired_fastq_requires_both_expected_files(self):
        first = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_1.fastq.gz"
        second = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_2.fastq.gz"
        complete = make_intake(
            layout="PAIRED", fastq_ftp=first + ";" + second,
            fastq_md5=("a" * 32) + ";" + ("b" * 32),
            fastq_bytes="400;500",
        )
        packet = build_review_packet(complete)
        self.assertEqual(packet["outcome"], "eligible_for_curator_review")
        self.assertEqual(packet["fastq"]["file_count"], 2)
        incomplete = make_intake(
            layout="PAIRED", fastq_ftp=first,
            fastq_md5="a" * 32, fastq_bytes="400",
        )
        held = build_review_packet(incomplete)
        self.assertEqual(held["outcome"], "held_for_review")
        self.assertIsNone(held["fastq"]["file_count"])

    def test_offline_snapshot_and_unverified_snapshot_files_are_held(self):
        offline = make_intake()
        offline["manifest"]["retrieval_mode"] = "offline_snapshot"
        packet = build_review_packet(offline)
        self.assertEqual(packet["outcome"], "held_for_review")
        self.assertIn("offline_or_unverified_metadata",
                      {item["code"] for item in packet["reasons"]})
        empty_index = make_intake()
        empty_index["manifest"]["snapshot_index"] = []
        empty_packet = build_review_packet(empty_index)
        self.assertEqual(empty_packet["outcome"], "held_for_review")
        self.assertIn("source_snapshots_missing", {
            item["code"] for item in empty_packet["reasons"]
        })
        no_directory = make_intake()
        self.assertIn("snapshot_directory_not_supplied", {
            item["code"] for item in build_review_packet(
                no_directory, raw_metadata_directory=None)["reasons"]
        })
        missing_file = make_intake()
        missing_file["manifest"]["snapshot_index"] = [
            {"name": "missing-response.xml", "sha256": "a" * 64}
        ]
        self.assertIn("snapshot_files_missing", {
            item["code"] for item in build_review_packet(missing_file)["reasons"]
        })
        wrong_hash = make_intake()
        wrong_hash["manifest"]["snapshot_index"][0]["sha256"] = "a" * 64
        self.assertIn("snapshot_hash_mismatch", {
            item["code"] for item in build_review_packet(wrong_hash)["reasons"]
        })
        duplicate = make_intake()
        entry = duplicate["manifest"]["snapshot_index"][0]
        duplicate["manifest"]["snapshot_index"] = [entry, dict(entry)]
        self.assertIn("snapshot_index_ambiguous", {
            item["code"] for item in build_review_packet(duplicate)["reasons"]
        })
        traversal = make_intake()
        traversal["manifest"]["snapshot_index"] = [
            {"name": "../outside.txt", "sha256": "a" * 64}
        ]
        self.assertIn("snapshot_index_malformed", {
            item["code"] for item in build_review_packet(traversal)["reasons"]
        })
        stale = make_intake()
        stale["manifest"]["profile"] = "old-policy"
        self.assertIn("stale_or_changed_policy", {
            item["code"] for item in build_review_packet(stale)["reasons"]
        })

    def test_missing_provenance_is_unknown_and_traceable_provenance_is_reported(self):
        absent = build_review_packet(make_intake())
        self.assertEqual(absent["identity_assessment"]["status"], "UNKNOWN")
        self.assertEqual(absent["biological_independence"]["status"], "UNKNOWN")
        self.assertFalse(absent["identity_assessment"]["provenance_supplied"])
        packet = build_review_packet(make_intake(), linked_provenance())
        self.assertEqual(packet["identity_assessment"]["status"],
                         "ESTABLISHED_BY_TRACEABLE_ASSERTIONS")
        self.assertTrue(packet["identity_assessment"]["provenance_valid"])
        self.assertEqual(packet["biological_independence"]["status"], "UNKNOWN")
        self.assertEqual(len(packet["references"]["provenance_entities"]), 2)

    def test_conflicting_provenance_is_never_independence(self):
        packet = build_review_packet(make_intake(), linked_provenance(conflict=True))
        self.assertEqual(packet["identity_assessment"]["status"], "CONFLICTING")
        self.assertEqual(packet["biological_independence"]["status"], "UNKNOWN")
        self.assertIn("provenance_identity_conflicting",
                      {r["code"] for r in packet["reasons"]})
        invalid = build_review_packet(make_intake(), {"schema": "invalid"})
        self.assertIn("provenance_invalid", {r["code"] for r in invalid["reasons"]})
        self.assertEqual(invalid["identity_assessment"]["status"], "UNKNOWN")

    def test_download_stays_disabled_for_every_review_outcome(self):
        unsupported = make_intake()
        unsupported["record"]["public_virus"]["virus"] = "not-supported"
        unsupported["manifest"]["record_sha256"] = hashlib.sha256(
            json.dumps(unsupported["record"], sort_keys=True,
                       separators=(",", ":")).encode()
        ).hexdigest()
        cases = [
            make_intake(),
            make_intake(organism="Homo sapiens", attributes={"host": "Homo sapiens"}),
            make_intake(organism="Human coronavirus 229E",
                        attributes={"virus": "HCoV-OC43"}),
            make_intake(library_strategy="AMPLICON"),
            make_intake(fastq_bytes="1000000001"),
            unsupported,
        ]
        for document in cases:
            with self.subTest(virus=document["record"].get("public_virus", {}).get("virus")):
                packet = build_review_packet(document)
                self.assertIn(packet["outcome"], {
                    "eligible_for_curator_review", "held_for_review", "excluded",
                })
                self.assertFalse(packet["may_download"])
                self.assertFalse(packet["download_enabled"])
        self.assertEqual(build_review_packet(cases[-1])["outcome"], "excluded")

    def test_malformed_and_oversized_inputs_fail_safely(self):
        malformed = build_review_packet({"manifest": [], "record": "bad"})
        self.assertEqual(malformed["outcome"], "held_for_review")
        self.assertIn("malformed_or_oversized_input",
                      {r["code"] for r in malformed["reasons"]})
        with self.assertRaises(AcquisitionReviewError):
            serialize_review_packet({"oversized": "x" * (MAX_PACKET_BYTES + 1)})

    def test_stored_identity_assessment_is_recomputed_not_trusted(self):
        document = make_intake()
        document["record"]["public_virus"]["status"] = "insufficient"
        document["manifest"]["record_sha256"] = hashlib.sha256(
            json.dumps(document["record"], sort_keys=True,
                       separators=(",", ":")).encode()
        ).hexdigest()
        packet = build_review_packet(document)
        self.assertIn("identity_assessment_inconsistent",
                      {r["code"] for r in packet["reasons"]})

    def test_packet_and_serialization_are_deterministic_and_bounded(self):
        first = build_review_packet(make_intake())
        second = build_review_packet(make_intake())
        self.assertEqual(first, second)
        self.assertEqual(serialize_review_packet(first), serialize_review_packet(second))
        self.assertLessEqual(len(serialize_review_packet(first).encode()), MAX_PACKET_BYTES)
        self.assertFalse(first["may_download"])
        self.assertFalse(first["download_enabled"])


if __name__ == "__main__":
    unittest.main()
