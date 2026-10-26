import base64
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    Ed25519PrivateKey = None
    serialization = None

from satellite_discovery import m21_phase7_closure as closure
from satellite_discovery import m21_phase6_governance as phase6
from satellite_discovery import m21_phase7_evidence as phase7
from satellite_discovery import m21_phase7b_replay as replay
from tests.test_m21_phase6_governance import M21Phase6GovernanceTests
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
        artifact_id_by_kind = {}
        for index, kind in enumerate(kinds):
            artifact_id = f"fixture-{index:02d}"
            path = f"evidence/{artifact_id}.json"
            if kind == "trust_registry":
                content = json.dumps(bundle, sort_keys=True).encode()
            elif kind in {"checkpoint_history", "audit_chain"}:
                content = b"[]"
            elif kind == "reviewer_approvals":
                content = b'{"approvals":[],"closure_package":{}}'
            else:
                content = b"{}"
            contents[path] = content
            artifact_id_by_kind[kind] = artifact_id
            artifacts.append({
                "artifact_id": artifact_id, "path": path, "kind": kind,
                "sha256": replay.hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            })
        available_ids = [
            artifact_id_by_kind[kind] for kind in kinds if kind != "replay_inputs"
        ]
        stage_artifact_ids = {}
        for state in phase6.STATES[1:]:
            stage_artifact_ids[state] = {}
            for artifact_type in sorted(phase7.REQUIRED_TRANSITION_ARTIFACTS[state]):
                stage_artifact_ids[state][artifact_type] = available_ids.pop(0)
        replay_inputs = {
            "schema_version": replay.REPLAY_INPUT_SCHEMA,
            "transition_receipts": [],
            "stage_artifact_ids": stage_artifact_ids,
            "chain_id": "CHAIN-SYNTH-001",
            "local_checkpoints": [],
        }
        replay_input = next(item for item in artifacts if item["kind"] == "replay_inputs")
        contents[replay_input["path"]] = json.dumps(replay_inputs, sort_keys=True).encode()
        replay_input["size_bytes"] = len(contents[replay_input["path"]])
        replay_input["sha256"] = replay.hashlib.sha256(contents[replay_input["path"]]).hexdigest()
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
            with (
                patch.object(closure, "verify_ci_acceptance", return_value={"status": "PASS", "issues": []}),
                patch.object(phase7, "verify_artifact_backed_transitions",
                             return_value={"status": "PASS", "issues": [], "adapter_results": []}),
                patch.object(closure, "verify_checkpoint_retention",
                             return_value=closure._verified_evidence({"status": "PASS", "issues": []})),
                patch.object(closure, "verify_closure_package",
                             return_value={"decision": "INCOMPLETE", "issues": ["synthetic trust fixture"]}),
            ):
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


@unittest.skipIf(Ed25519PrivateKey is None, "cryptography required for synthetic Ed25519 fixtures")
class CanonicalReplayMappingTests(unittest.TestCase):
    def test_content_addressed_stage_map_invokes_all_canonical_phase7_adapters(self):
        fixture = M21Phase6GovernanceTests()
        fixture.setUp()
        try:
            receipts, stage_paths, artifact_root = fixture.phase7_complete_synthetic_transition()
            descriptors = []
            files = {}
            id_by_path = {}
            for index, path in enumerate(sorted(p for p in artifact_root.rglob("*") if p.is_file())):
                relative = path.relative_to(artifact_root).as_posix()
                artifact_id = f"stage-{index:04d}"
                content = path.read_bytes()
                files[relative] = content
                id_by_path[relative] = artifact_id
                descriptors.append({"artifact_id": artifact_id, "path": relative})
            inputs = {
                "schema_version": replay.REPLAY_INPUT_SCHEMA,
                "transition_receipts": receipts,
                "chain_id": "CHAIN-SYNTH-001",
                "local_checkpoints": [],
                "stage_artifact_ids": {
                    state: {kind: id_by_path[path] for kind, path in artifacts.items()}
                    for state, artifacts in stage_paths.items()
                },
            }
            registry = {
                reviewer_id: {
                    "roles": ["reviewer"], "key_id": record["key_id"],
                    "public_key_ed25519": record["public_key_ed25519"],
                    "scopes": record["scopes"], "valid_from": record["valid_from"],
                    "valid_until": record["valid_until"], "revoked": record["revoked"],
                }
                for reviewer_id, record in fixture.trust.items()
            }
            result = replay._replay_canonical_transitions(
                json.dumps(inputs, sort_keys=True).encode(),
                {"artifacts": descriptors},
                {item["artifact_id"]: files[item["path"]] for item in descriptors},
                files, registry,
            )
            self.assertEqual(result["status"], "PASS", result["issues"])
            self.assertEqual(len(result["adapter_results"]), 5)
            self.assertFalse(result["biological_execution_authorized"])
        finally:
            fixture.tearDown()

    def test_synthetic_zip_runs_real_canonical_transition_replay(self):
        fixture = M21Phase6GovernanceTests()
        fixture.setUp()
        try:
            receipts, stage_paths, artifact_root = fixture.phase7_complete_synthetic_transition()
            root_key = Ed25519PrivateKey.generate()
            root_public = root_key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
            anchor = {
                "schema_version": replay.trust.ANCHOR_SCHEMA,
                "anchor_id": "ANCHOR-ZIP-SYNTH",
                "key_id": "ROOT-ZIP-SYNTH",
                "public_key_ed25519": base64.b64encode(root_public).decode(),
                "key_fingerprint_sha256": replay.trust.sha256(root_public),
                "authority": "synthetic package test",
            }
            identities = []
            for reviewer_id, source in fixture.trust.items():
                public_key = base64.b64decode(source["public_key_ed25519"])
                identities.append({
                    "identity_id": reviewer_id,
                    "display_name": reviewer_id,
                    "organization": "synthetic-test",
                    "key_id": source["key_id"],
                    "public_key_ed25519": source["public_key_ed25519"],
                    "key_fingerprint_sha256": replay.trust.sha256(public_key),
                    "identity_class": "SYNTHETIC",
                    "roles": ["reviewer"],
                    "scopes": list(source["scopes"]),
                    "valid_from": "2020-01-01T00:00:00Z",
                    "valid_until": "2099-01-01T00:00:00Z",
                    "revoked": False,
                    "identity_verification": {
                        "method": "synthetic test fixture",
                        "evidence_sha256": replay.hashlib.sha256(reviewer_id.encode()).hexdigest(),
                        "authority": "test only",
                    },
                    "enrollment_approvals": [],
                    "rotation": None,
                })
            registry = {
                "schema_version": replay.trust.REGISTRY_SCHEMA,
                "registry_id": "REG-ZIP-SYNTH",
                "generation": 1,
                "previous_checkpoint_sha256": None,
                "issued_at": "2026-10-20T00:00:00Z",
                "expires_at": "2099-01-01T00:00:00Z",
                "identities": identities,
            }
            checkpoint_body = {
                "schema_version": replay.trust.CHECKPOINT_SCHEMA,
                "registry_id": registry["registry_id"],
                "generation": 1,
                "registry_sha256": replay.trust.digest(registry),
                "previous_checkpoint_sha256": None,
                "issued_at": "2026-10-20T00:00:00Z",
            }
            bundle = {
                "registry": registry,
                "state_checkpoint": {
                    **checkpoint_body,
                    "signature_ed25519": base64.b64encode(
                        root_key.sign(replay.trust.canonical_bytes(checkpoint_body)),
                    ).decode(),
                },
                "anchor_signature": base64.b64encode(
                    root_key.sign(replay.trust.canonical_bytes(registry)),
                ).decode(),
            }
            artifact_contents = {}
            artifact_descriptors = []
            artifact_id_by_path = {}
            def add_artifact(path, kind, content):
                artifact_id = f"zip-{len(artifact_descriptors):04d}"
                artifact_contents[path] = content
                artifact_id_by_path[path] = artifact_id
                artifact_descriptors.append({
                    "artifact_id": artifact_id, "path": path, "kind": kind,
                    "sha256": replay.hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                })
            for index, source_path in enumerate(sorted(
                path for path in artifact_root.rglob("*") if path.is_file()
            )):
                rel = source_path.relative_to(artifact_root).as_posix()
                add_artifact(rel, "transition_artifact", source_path.read_bytes())
            stage_ids = {
                state: {
                    artifact_type: artifact_id_by_path[rel]
                    for artifact_type, rel in entries.items()
                }
                for state, entries in stage_paths.items()
            }
            kinds = sorted(replay.REQUIRED_KINDS)
            kind_paths = {}
            for kind in kinds:
                path = f"package/{kind}.json"
                kind_paths[kind] = path
                if kind == "trust_registry":
                    content = json.dumps(bundle, sort_keys=True).encode()
                elif kind in {"checkpoint_history", "audit_chain"}:
                    content = b"[]"
                elif kind == "custody_receipt":
                    content = b"{}"
                elif kind == "reviewer_approvals":
                    content = b'{"approvals":[],"closure_package":{}}'
                elif kind == "ci_statement":
                    content = b"{}"
                elif kind == "replay_inputs":
                    content = b""
                else:
                    content = b"{}"
                add_artifact(path, kind, content)
            replay_input = {
                "schema_version": replay.REPLAY_INPUT_SCHEMA,
                "transition_receipts": receipts,
                "stage_artifact_ids": stage_ids,
                "chain_id": "SYNTHETIC-ZIP-CHAIN",
                "local_checkpoints": [],
            }
            replay_descriptor = next(a for a in artifact_descriptors if a["kind"] == "replay_inputs")
            replay_contents = json.dumps(replay_input, sort_keys=True).encode()
            artifact_contents[replay_descriptor["path"]] = replay_contents
            replay_descriptor["sha256"] = replay.hashlib.sha256(replay_contents).hexdigest()
            replay_descriptor["size_bytes"] = len(replay_contents)
            with tempfile.TemporaryDirectory() as temp:
                temp_path = Path(temp)
                anchor_path = temp_path / "anchor.json"
                anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
                manifest = {
                    "schema_version": replay.SCHEMA_VERSION,
                    "software_revision": "8b83cbc14b0210c92acd9d021f4a5225c3245e7a",
                    "snapshot_id": "DS-SYNTH00001",
                    "policy_version": "synthetic-package-test-v1",
                    "artifacts": artifact_descriptors,
                    "limitations": ["synthetic fixture only"],
                }
                package = temp_path / "synthetic-evidence.zip"
                with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
                    for path, content in artifact_contents.items():
                        archive.writestr(path, content)
                with (
                    patch.object(closure, "verify_ci_acceptance",
                                 return_value={"status": "PASS", "issues": []}),
                    patch.object(closure, "verify_checkpoint_retention",
                                 return_value=closure._verified_evidence({"status": "PASS", "issues": []})),
                    patch.object(closure, "verify_closure_package",
                                 return_value={"decision": "PASS", "issues": []}),
                ):
                    result = replay.verify_package(
                        package, trust_anchor_path=anchor_path,
                        trust_anchor_fingerprint=anchor["key_fingerprint_sha256"],
                        trust_state_checkpoint_sha256=replay.trust.digest(checkpoint_body),
                    )
                    repeated = replay.verify_package(
                        package, trust_anchor_path=anchor_path,
                        trust_anchor_fingerprint=anchor["key_fingerprint_sha256"],
                        trust_state_checkpoint_sha256=replay.trust.digest(checkpoint_body),
                    )
            self.assertEqual(result["decision"], "INCOMPLETE", result["issues"])
            self.assertEqual(result["canonical_transition_status"], "PASS")
            self.assertEqual(result["canonical_stage_count"], 5)
            self.assertEqual(result["closure_decision"], "PASS")
            self.assertIn("Synthetic evidence replay cannot establish operational readiness.",
                          result["issues"])
            self.assertEqual(
                json.dumps(result, sort_keys=True),
                json.dumps(repeated, sort_keys=True),
            )
            self.assertEqual(result["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
            self.assertFalse(result["biological_execution_authorized"])
        finally:
            fixture.tearDown()


if __name__ == "__main__":
    unittest.main()
