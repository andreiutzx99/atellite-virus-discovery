import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery.controlled_fastq_acquisition import acquire_single_run
from satellite_discovery.public_virus_acquisition_preflight import fastq_manifest_sha256
from satellite_discovery.sequence_downloader import files_for_run
from test_public_virus_acquisition_preflight import make_decision, make_intake


class ControlledFastqAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="controlled-fastq-test-")
        self.root = Path(self.temp.name)
        self.raw = self.root / "original" / "raw_metadata"
        self.raw.mkdir(parents=True)
        self.storage = self.root / "storage"
        self.storage.mkdir()
        self.output = self.root / "reads"
        self.payload = b"synthetic-fastq"
        self.size = str(len(self.payload))
        self.md5 = hashlib.md5(self.payload).hexdigest()
        self.document = make_intake(
            self.raw, fastq_bytes=self.size, fastq_md5=self.md5,
        )
        self.files = files_for_run(self.document["record"])
        self.decision = make_decision(
            manifest_digest=fastq_manifest_sha256(self.files),
        )

    def tearDown(self):
        self.temp.cleanup()

    def retriever(self, *, url=None, bytes_value=None, md5=None, layout="SINGLE"):
        def retrieve(run, virus, output, offline=False):
            self.assertEqual(run, "SRR123456")
            self.assertEqual(virus, "hcov-229e")
            self.assertFalse(offline)
            raw = Path(output) / "raw_metadata"
            raw.mkdir(parents=True, exist_ok=True)
            self.assertTrue(raw.is_dir())
            self.assertEqual(list(raw.iterdir()), [], "fresh archive directory must start empty")
            return make_intake(
                raw, fastq_bytes=bytes_value or self.size,
                fastq_md5=md5 or self.md5, fastq_ftp=url, layout=layout,
            )
        return retrieve

    def confirmation(self, request):
        return {
            "run_accession": request["run_accession"],
            "max_compressed_bytes": request["approved_max_compressed_bytes"],
            "max_storage_bytes": request["approved_max_storage_bytes"],
        }

    def execute(self, **kwargs):
        def download(spec, directory):
            path = Path(directory) / spec["name"]
            path.write_bytes(self.payload)
            return path
        with (
            patch("satellite_discovery.sequence_downloader.check_disk", return_value=None),
            patch.dict(os.environ, {"CI": ""}),
        ):
            return acquire_single_run(
                self.document, self.raw, self.decision, self.output, self.storage,
                kwargs.pop("confirmation_callback", self.confirmation),
                retriever=kwargs.pop("retriever", self.retriever()),
                downloader=kwargs.pop("downloader", download),
                **kwargs,
            )

    def test_fresh_revalidation_and_exact_operator_confirmation_download_one_run(self):
        result = self.execute()
        self.assertEqual(result["status"], "complete")
        audit = json.loads(Path(result["audit_path"]).read_text(encoding="utf-8"))
        self.assertEqual(audit["run_accession"], "SRR123456")
        self.assertEqual(audit["status"], "complete")
        self.assertEqual(audit["fresh_retrieval_mode"], "isolated_empty_snapshot_directory")
        self.assertEqual(len(audit["files"]), 1)
        self.assertEqual(audit["files"][0]["observed_md5"], self.md5)
        self.assertFalse(audit.get("qc_enabled", False))

    def test_complete_paired_run_downloads_both_mates(self):
        r1, r2 = b"synthetic-r1", b"synthetic-r2"
        url1 = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_1.fastq.gz"
        url2 = "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_2.fastq.gz"
        metadata = {
            "layout": "PAIRED", "fastq_ftp": url1 + ";" + url2,
            "fastq_md5": hashlib.md5(r1).hexdigest() + ";" + hashlib.md5(r2).hexdigest(),
            "fastq_bytes": f"{len(r1)};{len(r2)}",
        }
        paired = make_intake(self.raw, **metadata)
        decision = make_decision(
            manifest_digest=fastq_manifest_sha256(files_for_run(paired["record"])),
        )

        def retrieve(run, virus, output, offline=False):
            raw = Path(output) / "raw_metadata"
            raw.mkdir(parents=True, exist_ok=True)
            return make_intake(raw, **metadata)

        payloads = {"R1": r1, "R2": r2}
        def download(spec, directory):
            path = Path(directory) / spec["name"]
            path.write_bytes(payloads[spec["role"]])
            return path

        with (
            patch("satellite_discovery.sequence_downloader.check_disk", return_value=None),
            patch.dict(os.environ, {"CI": ""}),
        ):
            result = acquire_single_run(
                paired, self.raw, decision, self.output, self.storage,
                self.confirmation, retriever=retrieve, downloader=download,
            )
        self.assertEqual(result["status"], "complete")
        self.assertEqual({item["role"] for item in result["files"]}, {"R1", "R2"})

    def test_missing_confirmation_blocks_after_fresh_revalidation(self):
        events = []
        retrieve = self.retriever()
        def tracked_retrieve(*args, **kwargs):
            events.append("fresh")
            return retrieve(*args, **kwargs)
        result = self.execute(
            retriever=tracked_retrieve,
            confirmation_callback=lambda request: events.append("confirm"),
        )
        self.assertEqual(events, ["fresh", "confirm"])
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], "operator_confirmation_missing_or_mismatched")
        self.assertFalse(self.output.exists())

    def test_changed_fresh_fastq_metadata_blocks(self):
        changed_url = (
            "ftp.ebi.ac.uk/vol1/fastq/SRR123/456/"
            "SRR123456/SRR123456.fastq.gz"
        )
        result = self.execute(retriever=self.retriever(url=changed_url))
        self.assertEqual(result["status"], "blocked")
        self.assertIn(
            "fresh_preflight_blocked",
            {item["code"] for item in result["reasons"]},
        )
        self.assertFalse(self.output.exists())

    def test_changed_fresh_md5_or_size_blocks(self):
        cases = (
            self.retriever(md5="b" * 32),
            self.retriever(bytes_value=str(len(self.payload) + 1)),
        )
        for retrieve in cases:
            with self.subTest(retriever=retrieve):
                result = self.execute(retriever=retrieve)
                self.assertEqual(result["status"], "blocked")
                self.assertFalse(self.output.exists())

    def test_fresh_archive_failure_fails_closed(self):
        def unavailable(*args, **kwargs):
            raise RuntimeError("synthetic network failure")
        result = self.execute(retriever=unavailable)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], "fresh_archive_retrieval_failed")

    def test_ci_environment_blocks_network_and_transfer_callbacks(self):
        def unexpected(*args, **kwargs):
            self.fail("CI must block before invoking external acquisition callbacks")
        with patch.dict(os.environ, {"CI": "true"}):
            result = acquire_single_run(
                self.document, self.raw, self.decision, self.output, self.storage,
                unexpected, retriever=unexpected, downloader=unexpected,
            )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], "acquisition_disabled_in_ci")

    def test_confirmation_must_match_exact_scope(self):
        wrong = {
            "run_accession": "SRR123456",
            "max_compressed_bytes": 999,
            "max_storage_bytes": self.decision["scope"]["max_storage_bytes"],
        }
        result = self.execute(confirmation_callback=lambda request: wrong)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], "operator_confirmation_missing_or_mismatched")

    def test_post_download_checksum_failure_is_audited(self):
        def corrupted(spec, directory):
            path = Path(directory) / spec["name"]
            path.write_bytes(b"corrupted")
            return path
        result = self.execute(downloader=corrupted)
        self.assertEqual(result["status"], "failed")
        audit = json.loads(Path(result["audit_path"]).read_text(encoding="utf-8"))
        self.assertEqual(audit["status"], "failed")
        self.assertEqual(audit["files"], [])

    def test_immediate_disk_check_failure_blocks_transfer(self):
        def no_space(directory, compressed_bytes):
            raise RuntimeError("Insufficient disk space: synthetic")
        result = self.execute(disk_checker=no_space)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], "insufficient_or_unavailable_storage")
        self.assertFalse(self.output.exists())

    def test_rejected_review_and_over_budget_run_never_reach_fresh_retrieval(self):
        rejected = dict(self.decision, state="rejected")
        def unexpected(*args, **kwargs):
            self.fail("fresh retrieval must not occur for rejected approval")
        with patch("satellite_discovery.sequence_downloader.check_disk", return_value=None):
            result = acquire_single_run(
                self.document, self.raw, rejected, self.output, self.storage,
                self.confirmation, retriever=unexpected,
            )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(self.output.exists())

        oversized_raw = self.root / "oversized" / "raw_metadata"
        oversized_raw.mkdir(parents=True)
        oversized = make_intake(oversized_raw, fastq_bytes="1000000001")
        oversized_files = files_for_run(oversized["record"])
        oversized_decision = make_decision(
            manifest_digest=fastq_manifest_sha256(oversized_files),
        )
        with patch("satellite_discovery.sequence_downloader.check_disk", return_value=None):
            result = acquire_single_run(
                oversized, oversized_raw, oversized_decision,
                self.output, self.storage, self.confirmation,
                retriever=unexpected,
            )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
