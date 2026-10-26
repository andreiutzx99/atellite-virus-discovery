import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    Ed25519PrivateKey = None

from satellite_discovery import m21_phase7_closure as closure
from satellite_discovery import m21_phase7b_replay as replay
from tests.test_m21_phase7b_trust import TrustRootTests


@unittest.skipIf(Ed25519PrivateKey is None, "cryptography required for synthetic Ed25519 fixtures")
class EvidencePackageTests(unittest.TestCase):
    def _package(self, root: Path):
        bundle, anchor, fingerprint, state_pin, _ = TrustRootTests()._bundle()
        anchor_path = root / "external-anchor.json"
        anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
        kinds = sorted(replay.REQUIRED_KINDS)
        artifacts = []
        contents = {}
        for index, kind in enumerate(kinds):
            artifact_id = f"fixture-{index:02d}"
            path = f"evidence/{artifact_id}.json"
            content = json.dumps(bundle, sort_keys=True).encode() if kind == "trust_registry" else b"{}"
            contents[path] = content
            artifacts.append({
                "artifact_id": artifact_id, "path": path, "kind": kind,
                "sha256": replay.hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            })
        manifest = {
            "schema_version": replay.SCHEMA_VERSION,
            "software_revision": "8b83cbc14b0210c92acd9d021f4a5225c3245e7a",
            "snapshot_id": "DS-SYNTH00001", "policy_version": "fixture-policy-v1",
            "artifacts": artifacts, "limitations": ["synthetic fixture only"],
        }
        package_path = root / "fixture.zip"
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
            for name, content in contents.items():
                archive.writestr(name, content)
        return package_path, anchor_path, fingerprint, state_pin

    def test_valid_package_integrity_never_claims_operational_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            package, anchor, fingerprint, pin = self._package(Path(temp))
            with patch.object(closure, "verify_ci_acceptance", return_value={"status": "PASS", "issues": []}):
                result = replay.verify_package(
                    package, trust_anchor_path=anchor,
                    trust_anchor_fingerprint=fingerprint,
                    trust_state_checkpoint_sha256=pin,
                )
        self.assertEqual(result["decision"], "INCOMPLETE")
        self.assertEqual(result["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
        self.assertFalse(result["biological_execution_authorized"])

    def test_tampered_artifact_and_unsafe_archive_path_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            package, anchor, fingerprint, pin = self._package(Path(temp))
            with zipfile.ZipFile(package, "a") as archive:
                archive.writestr("evidence/fixture-00.json", b"tampered")
            with patch.object(closure, "verify_ci_acceptance", return_value={"status": "PASS", "issues": []}):
                result = replay.verify_package(
                    package, trust_anchor_path=anchor,
                    trust_anchor_fingerprint=fingerprint,
                    trust_state_checkpoint_sha256=pin,
                )
            self.assertEqual(result["decision"], "FAIL")
            unsafe = Path(temp) / "unsafe.zip"
            with zipfile.ZipFile(unsafe, "w") as archive:
                archive.writestr("../escape", b"x")
            result = replay.verify_package(
                unsafe, trust_anchor_path=anchor,
                trust_anchor_fingerprint=fingerprint,
                trust_state_checkpoint_sha256=pin,
            )
            self.assertEqual(result["decision"], "FAIL")

    def test_manifest_must_account_for_every_archive_member(self):
        with tempfile.TemporaryDirectory() as temp:
            package, anchor, fingerprint, pin = self._package(Path(temp))
            with zipfile.ZipFile(package, "a") as archive:
                archive.writestr("unlisted.json", b"{}")
            with patch.object(replay, "_schema_valid", return_value=None):
                result = replay.verify_package(
                    package, trust_anchor_path=anchor,
                    trust_anchor_fingerprint=fingerprint,
                    trust_state_checkpoint_sha256=pin,
                )
        self.assertEqual(result["decision"], "FAIL")

    def test_missing_schema_validator_does_not_mask_bad_artifact_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            package, anchor, fingerprint, pin = self._package(Path(temp))
            with zipfile.ZipFile(package, "r") as source:
                members = {name: source.read(name) for name in source.namelist()}
            manifest = json.loads(members["manifest.json"])
            manifest["artifacts"][0]["sha256"] = "0" * 64
            members["manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
            with zipfile.ZipFile(package, "w") as target:
                for name, content in members.items():
                    target.writestr(name, content)
            with patch.object(replay, "_schema_valid", return_value=None):
                result = replay.verify_package(
                    package, trust_anchor_path=anchor,
                    trust_anchor_fingerprint=fingerprint,
                    trust_state_checkpoint_sha256=pin,
                )
        self.assertEqual(result["decision"], "FAIL")

    def test_invalid_archive_is_checked_before_unavailable_anchor(self):
        with tempfile.TemporaryDirectory() as temp:
            package, anchor, fingerprint, pin = self._package(Path(temp))
            with zipfile.ZipFile(package, "a") as archive:
                archive.writestr("unlisted.json", b"{}")
            missing_anchor = Path(temp) / "not-provisioned.json"
            result = replay.verify_package(
                package, trust_anchor_path=missing_anchor,
                trust_anchor_fingerprint=fingerprint,
                trust_state_checkpoint_sha256=pin,
            )
        self.assertEqual(result["decision"], "FAIL")


if __name__ == "__main__":
    unittest.main()
