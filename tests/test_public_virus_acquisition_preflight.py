import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import metadata_filter, public_virus
from satellite_discovery.public_virus_acquisition_preflight import (
    DECISION_SCHEMA,
    MAX_COMPRESSED_BYTES,
    STORAGE_HEADROOM_FIXED_BYTES,
    build_acquisition_preflight,
)
from satellite_discovery.sequence_downloader import files_for_run


def make_intake(raw_directory, *, attributes=None, organism="Human coronavirus 229E",
                layout="SINGLE", fastq_bytes="728420078", fastq_ftp=None,
                fastq_md5=None, library_strategy="RNA-Seq"):
    fastq_ftp = fastq_ftp or (
        "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/"
        "SRR123456/SRR123456.fastq.gz"
    )
    fastq_md5 = fastq_md5 or "a" * 32
    sample_attributes = attributes if attributes is not None else {"virus": "HCoV-229E"}
    record = {
        "run_accession": "SRR123456", "experiment_accession": "SRX123456",
        "sample_accession": "SRS123456", "biosample": "SAMN123456",
        "study_accession": "SRP123456", "bioproject": "PRJNA123456",
        "organism": organism, "attributes": sample_attributes,
        "raw_sample_attributes": [
            {"key": key, "value": value} for key, value in sample_attributes.items()
        ],
        "platform": "ILLUMINA", "library_strategy": library_strategy,
        "library_source": "TRANSCRIPTOMIC", "library_selection": "cDNA",
        "layout": layout, "total_spots": 24_000_000,
        "raw_read_availability": "ena_fastq_listed",
        "fastq_ftp": fastq_ftp, "fastq_md5": fastq_md5,
        "fastq_bytes": fastq_bytes,
    }
    record["public_virus"] = public_virus.assess_identity(record, "hcov-229e")
    assessment = metadata_filter.assess(dict(record), min_spots=0)
    record["selection"] = assessment["selection"]
    record["exclusion_reasons"] = assessment["exclusion_reasons"]
    record["warnings"] = assessment["warnings"]
    record["technical_suitability"] = {
        "status": "eligible_for_review" if not assessment["exclusion_reasons"] else "excluded",
        "reasons": assessment["exclusion_reasons"],
        "warnings": assessment["warnings"], "archive_errors": [],
    }
    try:
        fastqs = files_for_run(record)
        total = sum(item["bytes"] for item in fastqs)
        within_budget = total <= MAX_COMPRESSED_BYTES
        record["fastq_assessment"] = {
            "status": "complete_within_budget" if within_budget else "complete_over_budget",
            "complete": True, "total_bytes": total,
            "budget_bytes": MAX_COMPRESSED_BYTES, "fits_budget": within_budget,
            "reasons": [] if within_budget else ["complete_fastq_exceeds_1gb_budget"],
        }
    except (KeyError, TypeError, ValueError):
        record["fastq_assessment"] = {
            "status": "unverified_or_incomplete", "complete": False,
            "total_bytes": None, "budget_bytes": MAX_COMPRESSED_BYTES,
            "fits_budget": False, "reasons": ["ena_fastq_not_listed"],
        }
    record["curator_evidence"] = {
        "status": "pending_review", "may_authorize": False,
        "limitation": "No authenticated external trust anchor is implemented.",
    }
    snapshot = b'{"source":"synthetic archive response"}\n'
    snapshot_name = "sra-response.json"
    (Path(raw_directory) / snapshot_name).write_bytes(snapshot)
    manifest = {
        "schema": "public-virus-accession-manifest-v1",
        "profile": public_virus.POLICY["policy_version"],
        "policy_sha256": public_virus.POLICY_SHA256,
        "archive_source": "NCBI SRA / ENA", "retrieval_mode": "archive_client",
        "snapshot_index": [{
            "name": snapshot_name, "sha256": hashlib.sha256(snapshot).hexdigest(),
        }],
        "archive_errors": [],
        "archive_snapshot_integrity": "digest_checked_against_local_manifest_only",
        "biological_confirmation": "not_performed",
        "read_download_enabled": False, "qc_enabled": False,
    }
    manifest["record_sha256"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {"manifest": manifest, "record": record}


def make_decision(*, run="SRR123456", virus="hcov-229e", state="approved",
                  max_compressed_bytes=MAX_COMPRESSED_BYTES,
                  max_storage_bytes=10_000_000_000):
    return {
        "schema": DECISION_SCHEMA,
        "reviewer_identifier": "reviewer:test",
        "decision_identifier": "decision:test",
        "decision_rationale": "Synthetic test approval for offline preflight.",
        "approved_run_accession": run, "selected_virus": virus,
        "policy_version": public_virus.POLICY["policy_version"],
        "policy_sha256": public_virus.POLICY_SHA256,
        "intended_pilot_purpose": "Synthetic compatibility test.",
        "scope": {
            "max_runs": 1,
            "max_compressed_bytes": max_compressed_bytes,
            "max_storage_bytes": max_storage_bytes,
        },
        "state": state,
    }


class PublicVirusAcquisitionPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="public-virus-preflight-")
        self.raw = Path(self.temp.name) / "raw"
        self.storage = Path(self.temp.name) / "storage"
        self.raw.mkdir()
        self.storage.mkdir()
        self.document = make_intake(self.raw)

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, decision=None, document=None, **kwargs):
        with patch(
            "satellite_discovery.sequence_downloader.check_disk", return_value=None,
        ):
            return build_acquisition_preflight(
                document or self.document, self.raw, decision,
                storage_directory=self.storage, **kwargs,
            )

    def test_eligible_single_run_plan_is_explicitly_non_executable(self):
        plan = self.plan(make_decision())
        self.assertEqual(plan["status"], "ready_for_operator_confirmation")
        self.assertEqual(plan["run_accession"], "SRR123456")
        self.assertEqual(plan["selected_virus"], "hcov-229e")
        self.assertEqual(plan["review_gate_outcome"], "eligible_for_curator_review")
        self.assertEqual(len(plan["fastq_files"]), 1)
        self.assertEqual(plan["fastq_files"][0]["expected_md5"], "a" * 32)
        self.assertEqual(plan["expected_compressed_bytes"], 728_420_078)
        self.assertEqual(
            plan["required_storage_headroom_bytes"],
            3 * 728_420_078 + STORAGE_HEADROOM_FIXED_BYTES,
        )
        self.assertFalse(plan["may_download"])
        self.assertFalse(plan["download_enabled"])
        self.assertTrue(plan["required_immediate_pre_download_checks"])

    def test_held_and_excluded_runs_remain_blocked(self):
        held = make_intake(
            self.raw, organism="Homo sapiens", attributes={"host": "Homo sapiens"},
        )
        held_plan = self.plan(make_decision(), held)
        self.assertEqual(held_plan["status"], "blocked")
        self.assertIn("review_gate_not_eligible", {x["code"] for x in held_plan["reasons"]})
        excluded = make_intake(self.raw, library_strategy="AMPLICON")
        excluded_plan = self.plan(make_decision(), excluded)
        self.assertEqual(excluded_plan["status"], "blocked")
        self.assertEqual(excluded_plan["review_gate_outcome"], "excluded")

    def test_missing_and_rejected_human_review_block(self):
        missing = self.plan()
        self.assertIn("human_review_missing", {x["code"] for x in missing["reasons"]})
        rejected = self.plan(make_decision(state="rejected"))
        self.assertIn("human_review_not_approved", {x["code"] for x in rejected["reasons"]})

    def test_approved_review_with_mismatched_accession_blocks(self):
        plan = self.plan(make_decision(run="SRR999999"))
        self.assertIn("human_review_run_mismatch", {x["code"] for x in plan["reasons"]})

    def test_approved_review_with_mismatched_virus_blocks(self):
        plan = self.plan(make_decision(virus="hcov-oc43"))
        self.assertIn("human_review_virus_mismatch", {x["code"] for x in plan["reasons"]})

    def test_complete_paired_end_set_is_kept_whole(self):
        first = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_1.fastq.gz"
        second = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_2.fastq.gz"
        paired = make_intake(
            self.raw, layout="PAIRED", fastq_ftp=first + ";" + second,
            fastq_md5="a" * 32 + ";" + "b" * 32, fastq_bytes="300;400",
        )
        plan = self.plan(make_decision(), paired)
        self.assertEqual(plan["status"], "ready_for_operator_confirmation")
        self.assertEqual({item["role"] for item in plan["fastq_files"]}, {"R1", "R2"})
        self.assertEqual(plan["expected_compressed_bytes"], 700)

    def test_incomplete_paired_end_file_set_blocks(self):
        incomplete = make_intake(
            self.raw, layout="PAIRED",
            fastq_ftp="ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_1.fastq.gz",
            fastq_md5="a" * 32, fastq_bytes="300",
        )
        plan = self.plan(make_decision(), incomplete)
        self.assertIn(
            "review_gate_fastq_metadata_missing_or_inconsistent",
            {x["code"] for x in plan["reasons"]},
        )
        self.assertEqual(plan["status"], "blocked")

    def test_unknown_file_size_blocks(self):
        unknown = make_intake(self.raw, fastq_bytes="unknown")
        plan = self.plan(make_decision(), unknown)
        self.assertIn(
            "review_gate_fastq_metadata_missing_or_inconsistent",
            {x["code"] for x in plan["reasons"]},
        )

    def test_exact_budget_is_allowed_and_above_budget_is_blocked(self):
        exact = make_intake(self.raw, fastq_bytes=str(MAX_COMPRESSED_BYTES))
        exact_plan = self.plan(make_decision(), exact)
        self.assertEqual(exact_plan["status"], "ready_for_operator_confirmation")
        self.assertEqual(exact_plan["expected_compressed_bytes"], MAX_COMPRESSED_BYTES)
        above = make_intake(self.raw, fastq_bytes=str(MAX_COMPRESSED_BYTES + 1))
        above_plan = self.plan(make_decision(), above)
        self.assertEqual(above_plan["status"], "blocked")
        self.assertIn(
            "review_gate_fastq_over_pilot_budget",
            {x["code"] for x in above_plan["reasons"]},
        )

    def test_inadequate_disk_space_is_reported(self):
        with patch(
            "satellite_discovery.sequence_downloader.check_disk",
            side_effect=RuntimeError("Insufficient disk space: test"),
        ):
            plan = build_acquisition_preflight(
                self.document, self.raw, make_decision(),
                storage_directory=self.storage,
            )
        self.assertIn("insufficient_disk_space", {x["code"] for x in plan["reasons"]})
        self.assertEqual(plan["status"], "blocked")

    def test_missing_or_changed_source_snapshot_blocks(self):
        changed = self.raw / "sra-response.json"
        changed.unlink()
        missing = self.plan(make_decision())
        self.assertIn("review_gate_snapshot_files_missing",
                      {x["code"] for x in missing["reasons"]})
        changed.write_text('{"changed":true}\n', encoding="utf-8")
        changed_plan = self.plan(make_decision())
        self.assertIn("review_gate_snapshot_hash_mismatch",
                      {x["code"] for x in changed_plan["reasons"]})

    def test_policy_mismatch_blocks(self):
        stale = make_intake(self.raw)
        stale["manifest"]["profile"] = "old-policy"
        plan = self.plan(make_decision(), stale)
        self.assertIn("policy_mismatch", {x["code"] for x in plan["reasons"]})

    def test_malformed_approval_record_blocks(self):
        malformed = make_decision()
        malformed["scope"]["max_runs"] = True
        plan = self.plan(malformed)
        self.assertIn("human_review_scope_invalid", {x["code"] for x in plan["reasons"]})
        malformed["state"] = ["approved"]
        plan = self.plan(malformed)
        self.assertIn("human_review_malformed", {x["code"] for x in plan["reasons"]})

    def test_review_scope_and_policy_must_cover_the_plan(self):
        small_byte_scope = self.plan(make_decision(max_compressed_bytes=1000))
        self.assertIn("human_review_compressed_limit_exceeded",
                      {x["code"] for x in small_byte_scope["reasons"]})
        small_storage_scope = self.plan(make_decision(max_storage_bytes=1))
        self.assertIn("human_review_storage_limit_exceeded",
                      {x["code"] for x in small_storage_scope["reasons"]})
        stale_decision = make_decision()
        stale_decision["policy_sha256"] = "0" * 64
        stale_policy = self.plan(stale_decision)
        self.assertIn("human_review_policy_mismatch",
                      {x["code"] for x in stale_policy["reasons"]})

    def test_missing_provenance_preserves_unknown_independence(self):
        plan = self.plan(make_decision())
        self.assertEqual(plan["biological_independence"]["status"], "UNKNOWN")
        self.assertTrue(any("UNKNOWN" in item for item in plan["limitations"]))

    def test_equivalent_inputs_produce_deterministic_output(self):
        decision = make_decision()
        self.assertEqual(self.plan(decision), self.plan(decision))

    def test_download_flags_are_false_for_all_outcomes(self):
        cases = [
            self.plan(make_decision()),
            self.plan(),
            self.plan(make_decision(state="rejected")),
            self.plan(make_decision(run="SRR999999")),
            self.plan(make_decision(), make_intake(self.raw, library_strategy="AMPLICON")),
        ]
        for plan in cases:
            with self.subTest(status=plan["status"]):
                self.assertFalse(plan["may_download"])
                self.assertFalse(plan["download_enabled"])


if __name__ == "__main__":
    unittest.main()
