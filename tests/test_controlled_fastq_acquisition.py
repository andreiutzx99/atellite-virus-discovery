import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery.controlled_fastq_acquisition import (
    LIVE_ACQUISITION_BLOCK_CODE,
    _orchestrate_synthetic_acquisition,
    acquire_single_run,
    plan_single_run,
)
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
        document = make_intake(
            self.raw, fastq_bytes=str(len(self.payload)),
            fastq_md5=hashlib.md5(self.payload).hexdigest(),
        )
        files = files_for_run(document["record"])
        self.document = document
        self.decision = make_decision(
            manifest_digest=fastq_manifest_sha256(files),
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
            return make_intake(
                raw, fastq_bytes=bytes_value or str(len(self.payload)),
                fastq_md5=md5 or hashlib.md5(self.payload).hexdigest(),
                fastq_ftp=url, layout=layout,
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
        return _orchestrate_synthetic_acquisition(
            self.document, self.raw, self.decision, self.output, self.storage,
            kwargs.pop("confirmation_callback", self.confirmation),
            retriever=kwargs.pop("retriever", self.retriever()),
            downloader=kwargs.pop("downloader", download),
            disk_checker=kwargs.pop("disk_checker", lambda directory, size: None),
            **kwargs,
        )

    def test_dry_run_remains_available_without_creating_output(self):
        result = plan_single_run(
            self.document, self.raw, self.decision,
            storage_directory=self.storage,
        )
        self.assertEqual(result["status"], "ready_for_operator_confirmation")
        self.assertFalse(self.output.exists())

    def test_live_acquisition_denied_before_retrieval_confirmation_or_transfer(self):
        def unexpected(*args, **kwargs):
            self.fail("disabled acquisition must not invoke caller callbacks")

        result = acquire_single_run(
            self.document, self.raw, self.decision, self.output, self.storage,
            unexpected, retriever=unexpected, downloader=unexpected,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], LIVE_ACQUISITION_BLOCK_CODE)
        self.assertIn("independently trusted", result["reasons"][0]["detail"])
        self.assertFalse(self.output.exists())

    def test_synthetic_single_end_acquisition_and_audit(self):
        result = self.execute()
        self.assertEqual(result["status"], "complete")
        audit = json.loads(Path(result["audit_path"]).read_text(encoding="utf-8"))
        self.assertEqual(audit["status"], "complete")
        self.assertEqual(len(audit["files"]), 1)
        self.assertFalse(audit.get("qc_enabled", False))

    def test_synthetic_paired_end_acquisition_requires_both_verified_mates(self):
        r1, r2 = b"synthetic-r1", b"synthetic-r2"
        metadata = {
            "layout": "PAIRED",
            "fastq_ftp": (
                "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_1.fastq.gz;"
                "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_2.fastq.gz"
            ),
            "fastq_md5": hashlib.md5(r1).hexdigest() + ";" + hashlib.md5(r2).hexdigest(),
            "fastq_bytes": f"{len(r1)};{len(r2)}",
        }
        fresh = make_intake(self.raw, **metadata)
        decision = make_decision(manifest_digest=fastq_manifest_sha256(files_for_run(fresh["record"])))
        payloads = {"R1": r1, "R2": r2}

        def download(spec, directory):
            path = Path(directory) / spec["name"]
            path.write_bytes(payloads[spec["role"]])
            return path

        def retrieve(run, virus, output, offline=False):
            raw = Path(output) / "raw_metadata"
            raw.mkdir(parents=True)
            return make_intake(raw, **metadata)

        result = _orchestrate_synthetic_acquisition(
            fresh, self.raw, decision, self.output, self.storage, self.confirmation,
            retriever=retrieve, downloader=download,
            disk_checker=lambda directory, size: None,
        )
        self.assertEqual(result["status"], "complete")
        self.assertEqual({item["role"] for item in result["files"]}, {"R1", "R2"})

    def test_synthetic_missing_mate_cannot_complete_pair(self):
        r1, r2 = b"synthetic-r1", b"synthetic-r2"
        metadata = {
            "layout": "PAIRED",
            "fastq_ftp": (
                "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_1.fastq.gz;"
                "ftp.sra.ebi.ac.uk/vol1/fastq/SRR123/456/SRR123456/SRR123456_2.fastq.gz"
            ),
            "fastq_md5": hashlib.md5(r1).hexdigest() + ";" + hashlib.md5(r2).hexdigest(),
            "fastq_bytes": f"{len(r1)};{len(r2)}",
        }
        fresh = make_intake(self.raw, **metadata)
        decision = make_decision(manifest_digest=fastq_manifest_sha256(files_for_run(fresh["record"])))
        def retrieve(run, virus, output, offline=False):
            raw = Path(output) / "raw_metadata"
            raw.mkdir(parents=True)
            return make_intake(raw, **metadata)
        def only_r1(spec, directory):
            path = Path(directory) / spec["name"]
            path.write_bytes(r1)
            return path
        result = _orchestrate_synthetic_acquisition(
            fresh, self.raw, decision, self.output, self.storage, self.confirmation,
            retriever=retrieve, downloader=only_r1,
            disk_checker=lambda directory, size: None,
        )
        self.assertEqual(result["status"], "failed")
        audit = json.loads(Path(result["audit_path"]).read_text())
        self.assertNotEqual(audit["status"], "complete")

    def test_synthetic_changed_metadata_and_manifest_block(self):
        result = self.execute(retriever=self.retriever(bytes_value=str(len(self.payload) + 1)))
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(self.output.exists())

    def test_synthetic_incorrect_confirmation_blocks(self):
        result = self.execute(confirmation_callback=lambda request: {"run_accession": "SRR000000"})
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], "operator_confirmation_missing_or_mismatched")

    def test_synthetic_rejected_approval_and_disk_failure_block(self):
        rejected = dict(self.decision, state="rejected")
        result = _orchestrate_synthetic_acquisition(
            self.document, self.raw, rejected, self.output, self.storage, self.confirmation,
            retriever=self.retriever(), downloader=lambda *args: self.fail("must not download"),
            disk_checker=lambda *args: None,
        )
        self.assertEqual(result["status"], "blocked")
        result = self.execute(disk_checker=lambda *args: (_ for _ in ()).throw(RuntimeError("no space")))
        self.assertEqual(result["status"], "blocked")

    def test_synthetic_checksum_failure_and_interruption_are_audited(self):
        def corrupted(spec, directory):
            path = Path(directory) / spec["name"]
            path.write_bytes(b"corrupt")
            return path
        failed = self.execute(downloader=corrupted)
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(json.loads(Path(failed["audit_path"]).read_text())["status"], "failed")

        self.output = self.root / "interrupted"
        def interrupt(*args):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.execute(downloader=interrupt)
        audit = json.loads((self.output / "acquisition.json").read_text())
        self.assertEqual(audit["status"], "interrupted")

    def test_synthetic_audit_write_failure_prevents_transfer(self):
        def should_not_download(*args, **kwargs):
            self.fail("transfer must not start if audit initialization fails")
        with patch(
            "satellite_discovery.sequence_downloader.write_json",
            side_effect=OSError("synthetic audit failure"),
        ):
            with self.assertRaisesRegex(OSError, "synthetic audit failure"):
                self.execute(downloader=should_not_download)

    def test_ci_variable_and_confirmation_callback_cannot_authorize_acquisition(self):
        def unexpected(*args, **kwargs):
            self.fail("CI or an auto-confirming callback is not authorization")

        with patch.dict("os.environ", {"CI": ""}):
            result = acquire_single_run(
                self.document, self.raw, self.decision, self.output, self.storage,
                lambda request: {
                    "run_accession": request["run_accession"],
                    "max_compressed_bytes": request["approved_max_compressed_bytes"],
                    "max_storage_bytes": request["approved_max_storage_bytes"],
                },
                retriever=unexpected, downloader=unexpected,
            )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], LIVE_ACQUISITION_BLOCK_CODE)

    def test_controlled_transfer_boundary_fails_closed(self):
        def unexpected(*args, **kwargs):
            self.fail("controlled transfer must fail before calling downloader")

        result = acquire_single_run(
            self.document, self.raw, self.decision, self.output, self.storage,
            unexpected, retriever=unexpected, downloader=unexpected,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], LIVE_ACQUISITION_BLOCK_CODE)


if __name__ == "__main__":
    unittest.main()
