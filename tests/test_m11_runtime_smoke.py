import os
import platform
import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import artifact_contracts, m11_runtime, m11_stage
from satellite_discovery.m11_engine import fold_single
from satellite_discovery.m11_runtime import WHEEL_LOCK, runtime_identity
from tests.test_m11_stage import _make_handoff


class M11PinnedRuntimeSmokeTests(unittest.TestCase):
    def test_pinned_wheel_receipt_and_synthetic_golden_fold(self):
        identity = runtime_identity()
        if identity["status"] != "available":
            message = (
                "Pinned M11 runtime is not available: "
                f"{identity.get('reason_code')}"
            )
            if os.environ.get("M11_REQUIRE_RUNTIME") == "1":
                self.fail(message)
            self.skipTest(message)

        target = (platform.system(), f"{sys.version_info.major}.{sys.version_info.minor}")
        self.assertIn(target, WHEEL_LOCK)
        filename, wheel_hash = WHEEL_LOCK[target]
        self.assertEqual(identity["wheel_filename"], filename)
        self.assertEqual(identity["wheel_sha256"], wheel_hash)
        self.assertEqual(identity["version"], "2.7.2")
        self.assertRegex(identity["native_library_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(identity["installed_files_sha256"], r"^[0-9a-f]{64}$")

        status, result, reason = fold_single(
            "GCGAAACGC",
            timeout_seconds=30,
            memory_bytes=1_610_612_736,
        )
        self.assertEqual((status, reason), ("COMPLETED", None))
        self.assertEqual(result["dot_bracket"], "(((...)))")
        self.assertEqual(result["energy_hex"], "-0x1.99999a0000000p-2")
        details = result["effective_model_details"]
        self.assertEqual(details["temperature"], 37.0)
        self.assertEqual(details["dangles"], 2)
        self.assertEqual(details["parameter_set"], "TURNER_2004_BUILTIN")
        self.assertEqual(details["noGU"], 0)
        self.assertEqual(details["noLP"], 0)
        self.assertEqual(details["min_loop_size"], 3)

    def test_receipt_detects_runtime_file_changes(self):
        identity = runtime_identity()
        if identity["status"] != "available":
            self.skipTest(
                "Pinned M11 runtime is not available: "
                f"{identity.get('reason_code')}"
            )
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "receipt.json"
            receipt.write_text(
                m11_runtime._receipt_path().read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            with patch.object(m11_runtime, "_receipt_path", return_value=receipt):
                self.assertEqual(runtime_identity()["status"], "available")
                value = json.loads(receipt.read_text(encoding="utf-8"))
                value["installed_files_sha256"] = "0" * 64
                receipt.write_text(json.dumps(value), encoding="utf-8")
                changed = runtime_identity()
            self.assertEqual(changed["status"], "unavailable")
            self.assertEqual(changed["reason_code"], "PINNED_RUNTIME_CONTENT_MISMATCH")

    def test_pinned_runtime_completes_a_validated_m11_bundle(self):
        identity = runtime_identity()
        if identity["status"] != "available":
            self.skipTest(
                "Pinned M11 runtime is not available: "
                f"{identity.get('reason_code')}"
            )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            handoff = _make_handoff(root)
            output = root / "m11-output"
            m11_stage.run_stage(
                {"candidate_sequence_set": str(handoff)}, output, {})
            bundle = artifact_contracts.validate_artifact(
                output / "m11_bundle.json", "m11_result_bundle")
            self.assertEqual(bundle["aggregate_status"], "COMPLETE")
            self.assertEqual(bundle["candidate_count"], 2)
            self.assertEqual(bundle["fold_count"], 2)
            self.assertEqual(bundle["evidence_count"], 2)
            evidence_path = output / "rna_structure_evidence.jsonl"
            evidence = [
                json.loads(line)
                for line in evidence_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(evidence[0]["mfe_structure_dot_bracket"], "(((...)))")
            self.assertEqual(evidence[1]["view_sequence"], "AUGCAAA")
            self.assertEqual(evidence[0]["runtime_identity"]["wheel_sha256"],
                             identity["wheel_sha256"])


if __name__ == "__main__":
    unittest.main()