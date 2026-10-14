import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery.controlled_fastq_acquisition import (
    LIVE_ACQUISITION_BLOCK_CODE,
    TrustedAuthorizationUnavailable,
    _controlled_transfer,
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
        payload = b"synthetic-fastq"
        document = make_intake(
            self.raw, fastq_bytes=str(len(payload)),
            fastq_md5=hashlib.md5(payload).hexdigest(),
        )
        files = files_for_run(document["record"])
        self.document = document
        self.decision = make_decision(
            manifest_digest=fastq_manifest_sha256(files),
        )

    def tearDown(self):
        self.temp.cleanup()

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

        with self.assertRaises(TrustedAuthorizationUnavailable):
            _controlled_transfer({"name": "synthetic.fastq.gz"}, self.output, unexpected)


if __name__ == "__main__":
    unittest.main()
