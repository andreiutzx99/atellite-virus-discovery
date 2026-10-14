import hashlib
import json
import tempfile
import threading
import unittest
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request
from unittest.mock import patch

from satellite_discovery.controlled_fastq_acquisition import (
    LIVE_ACQUISITION_BLOCK_CODE,
    _check_destination_space,
    _controlled_ena_opener,
    _create_acquisition_lock,
    _ENARedirectHandler,
    _retain_archive_snapshots,
    _safe_output_path,
    _validate_ena_redirect_target,
    acquire_single_run,
    plan_single_run,
)
from controlled_acquisition_harness import run_synthetic_acquisition as _orchestrate_synthetic_acquisition
from satellite_discovery.public_virus_acquisition_preflight import fastq_manifest_sha256
from satellite_discovery.sequence_downloader import files_for_run
from test_public_virus_acquisition_preflight import make_decision, make_intake


class ControlledFastqAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="controlled-fastq-test-")
        self.root = Path(self.temp.name)
        self.raw = self.root / "original" / "raw_metadata"
        self.raw.mkdir(parents=True)
        self.storage = self.root
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
        evidence = self.root / "reads.archive-evidence"
        self.assertTrue((evidence / "snapshot_manifest.json").is_file())
        self.assertGreater(audit["fresh_archive_manifest"]["retained_archive_evidence"]["total_bytes"], 0)

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
        self.assertFalse((self.root / ".interrupted.acquisition.lock").exists())

    def test_destination_scope_links_locks_and_collisions_fail_closed(self):
        outside = self.root / "outside"
        outside.mkdir()
        with self.assertRaisesRegex(ValueError, "scope|cannot be resolved"):
            _safe_output_path(outside / "reads", self.root / "other-scope")
        link = self.root / "linked-output"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlinks unavailable on this platform")
        with self.assertRaisesRegex(ValueError, "link"):
            _safe_output_path(link / "reads", self.root)
        first = _create_acquisition_lock(self.root / "locked-run")
        try:
            with self.assertRaisesRegex(RuntimeError, "already locked"):
                _create_acquisition_lock(self.root / "locked-run")
        finally:
            first.unlink()

        collision = self.root / "existing-run"
        collision.mkdir()
        result = _orchestrate_synthetic_acquisition(
            self.document, self.raw, self.decision, collision, self.storage,
            self.confirmation, retriever=self.retriever(),
            downloader=lambda *args: self.fail("existing destination must not be written"),
            disk_checker=lambda directory, size: None,
        )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reasons"][0]["code"], "acquisition_destination_collision")

    def test_storage_headroom_uses_destination_volume_and_approved_cap(self):
        required = 3 * 100 + 256 * 1024 * 1024
        with patch(
            "satellite_discovery.controlled_fastq_acquisition.shutil.disk_usage",
            return_value=SimpleNamespace(free=required + 1),
        ) as usage:
            result = _check_destination_space(
                self.root / "reads", 100, required,
            )
        self.assertEqual(result["required_bytes"], required)
        usage.assert_called_once_with(self.root)
        with self.assertRaisesRegex(RuntimeError, "exceeds approved"):
            _check_destination_space(self.root / "reads", 100, required - 1)
        with patch(
            "satellite_discovery.controlled_fastq_acquisition.shutil.disk_usage",
            return_value=SimpleNamespace(free=0),
        ):
            with self.assertRaisesRegex(RuntimeError, "Insufficient"):
                _check_destination_space(self.root / "reads", 100, required)

    def test_controlled_redirect_policy_accepts_only_https_ena_hosts(self):
        allowed = "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR123456.fastq.gz"
        self.assertEqual(_validate_ena_redirect_target(allowed), allowed)
        for target in (
            "http://ftp.sra.ebi.ac.uk/reads.fastq.gz",
            "https://example.invalid/reads.fastq.gz",
            "https://ftp.ebi.ac.uk:8443/reads.fastq.gz",
        ):
            with self.subTest(target=target), self.assertRaises(ValueError):
                _validate_ena_redirect_target(target)

        handler = _ENARedirectHandler()
        request = Request("https://ftp.sra.ebi.ac.uk/start")
        headers = Message()
        response = BytesIO()
        with self.assertRaises(HTTPError):
            handler.redirect_request(
                request, response, 302, "Found", headers,
                "https://redirector.example.invalid/reads.fastq.gz",
            )
        redirected = handler.redirect_request(
            request, response, 302, "Found", headers,
            "https://ftp.ebi.ac.uk/reads.fastq.gz",
        )
        self.assertEqual(redirected.full_url, "https://ftp.ebi.ac.uk/reads.fastq.gz")
        opener = _controlled_ena_opener()
        self.assertTrue(any(isinstance(handler, _ENARedirectHandler) for handler in opener.handlers))

    def test_two_threads_cannot_own_the_same_acquisition_lock(self):
        barrier = threading.Barrier(2)
        results = []
        def attempt():
            try:
                lock = _create_acquisition_lock(self.root / "threaded")
                results.append("owned")
                barrier.wait(timeout=2)
                lock.unlink()
            except RuntimeError:
                results.append("rejected")
                barrier.wait(timeout=2)
        workers = [threading.Thread(target=attempt) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=5)
        self.assertEqual(sorted(results), ["owned", "rejected"])

    def test_synthetic_audit_write_failure_prevents_transfer(self):
        def should_not_download(*args, **kwargs):
            self.fail("transfer must not start if audit initialization fails")
        with patch(
            "controlled_acquisition_harness._atomic_audit_write",
            side_effect=OSError("synthetic audit failure"),
        ):
            with self.assertRaisesRegex(OSError, "synthetic audit failure"):
                self.execute(downloader=should_not_download)

    def test_archive_evidence_retention_rejects_corrupt_duplicate_oversized_and_unsafe(self):
        source = self.root / "fresh-snapshots"
        source.mkdir()
        payload = b"exact archive response bytes"
        (source / "sra-response.json").write_bytes(payload)
        index = [{"name": "sra-response.json", "sha256": hashlib.sha256(payload).hexdigest()}]
        retained = _retain_archive_snapshots(source, self.root / "kept-evidence", index)
        self.assertEqual((self.root / "kept-evidence" / "sra-response.json").read_bytes(), payload)
        self.assertEqual(retained["snapshots"][0]["sha256"], index[0]["sha256"])
        with self.assertRaises(FileExistsError):
            _retain_archive_snapshots(source, self.root / "kept-evidence", index)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            _retain_archive_snapshots(source, self.root / "duplicate", index + index)
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            _retain_archive_snapshots(
                source, self.root / "corrupt",
                [{"name": index[0]["name"], "sha256": "0" * 64}],
            )
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            _retain_archive_snapshots(
                source, self.root / "unsafe",
                [{"name": "../secret", "sha256": "0" * 64}],
            )
        large = self.root / "large"
        large.mkdir()
        (large / "oversized.json").touch()
        (large / "oversized.json").write_bytes(b"")
        with (large / "oversized.json").open("r+b") as handle:
            handle.truncate(50 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "byte limit"):
            _retain_archive_snapshots(
                large, self.root / "too-large",
                [{"name": "oversized.json", "sha256": "0" * 64}],
            )

    def test_archive_evidence_retention_rejects_symlink_and_missing_snapshot(self):
        source = self.root / "fresh-links"
        source.mkdir()
        target = self.root / "outside.json"
        target.write_text("{}")
        link = source / "response.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this platform")
        index = [{"name": "response.json", "sha256": hashlib.sha256(b"{}").hexdigest()}]
        with self.assertRaisesRegex(ValueError, "missing, duplicated or unindexed|regular file"):
            _retain_archive_snapshots(source, self.root / "linked-evidence", index)
        link.unlink()
        with self.assertRaisesRegex(ValueError, "missing, duplicated or unindexed"):
            _retain_archive_snapshots(source, self.root / "missing-evidence", index)

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
