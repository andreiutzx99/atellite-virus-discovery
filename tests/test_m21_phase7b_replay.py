import base64
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
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
from satellite_discovery import m21_benchmark_readiness as readiness
from tests import test_m21_phase7_closure as closure_fixtures
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

    def test_fully_signed_synthetic_zip_runs_all_internal_validators(self):
        fixture = M21Phase6GovernanceTests()
        fixture.setUp()
        now = closure_fixtures.NOW
        try:
            receipts, stage_paths, artifact_root = fixture.phase7_complete_synthetic_transition()
            reviewer_ids = list(fixture.trust)
            closure_reviewers = reviewer_ids[:2]
            checkpoint_reviewer = reviewer_ids[2]
            custodian = reviewer_ids[3]
            trust_admins = reviewer_ids[4:7]
            self.assertEqual(len(trust_admins), 3)
            extra_scopes = {
                closure_reviewers[0]: [closure.REVIEW_SCOPE],
                closure_reviewers[1]: [closure.REVIEW_SCOPE],
                checkpoint_reviewer: ["custody_checkpoint"],
                custodian: [closure.RETENTION_SCOPE],
                **{reviewer_id: ["trust_registry_enrollment"] for reviewer_id in trust_admins},
            }
            root_key = Ed25519PrivateKey.generate()
            root_raw = root_key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
            anchor = {
                "schema_version": replay.trust.ANCHOR_SCHEMA,
                "anchor_id": "ANCHOR-INTEGRATED-SYNTH",
                "key_id": "ROOT-INTEGRATED-SYNTH",
                "public_key_ed25519": base64.b64encode(root_raw).decode(),
                "key_fingerprint_sha256": replay.trust.sha256(root_raw),
                "authority": "synthetic integrated test only",
            }

            def make_registry(generation, previous_pin=None, enroll=False):
                identities = []
                for reviewer_id, source in fixture.trust.items():
                    scopes = sorted(set(source["scopes"] + extra_scopes.get(reviewer_id, [])))
                    roles = ["reviewer"]
                    if reviewer_id in trust_admins:
                        roles.append("trust_admin")
                    if reviewer_id == custodian:
                        roles.append("custodian")
                    raw_key = base64.b64decode(source["public_key_ed25519"])
                    identities.append({
                        "identity_id": reviewer_id,
                        "display_name": reviewer_id,
                        "organization": "synthetic-integrated-fixture",
                        "key_id": source["key_id"],
                        "public_key_ed25519": source["public_key_ed25519"],
                        "key_fingerprint_sha256": replay.trust.sha256(raw_key),
                        "identity_class": "SYNTHETIC", "roles": roles, "scopes": scopes,
                        "valid_from": "2026-01-01T00:00:00Z",
                        "valid_until": "2027-01-01T00:00:00Z",
                        "revoked": False,
                        "identity_verification": {
                            "method": "synthetic integrated fixture",
                            "evidence_sha256": replay.hashlib.sha256(reviewer_id.encode()).hexdigest(),
                            "authority": "test only",
                        },
                        "enrollment_approvals": [], "rotation": None,
                    })
                if enroll:
                    for index, identity in enumerate(identities):
                        approval_body = {key: identity[key] for key in (
                            "identity_id", "key_id", "key_fingerprint_sha256", "roles",
                            "scopes", "valid_from", "valid_until", "identity_verification",
                        )}
                        for admin_id in trust_admins:
                            if admin_id == identity["identity_id"]:
                                continue
                            admin = next(x for x in identities if x["identity_id"] == admin_id)
                            identity["enrollment_approvals"].append({
                                "identity_id": admin_id, "key_id": admin["key_id"],
                                "signature_ed25519": base64.b64encode(
                                    fixture.private[admin_id].sign(
                                        replay.trust.canonical_bytes(approval_body),
                                    ),
                                ).decode(),
                            })
                registry = {
                    "schema_version": replay.trust.REGISTRY_SCHEMA,
                    "registry_id": "REG-INTEGRATED-SYNTH",
                    "generation": generation,
                    "previous_checkpoint_sha256": previous_pin,
                    "issued_at": "2026-10-20T00:00:00Z" if generation == 1 else "2026-10-21T00:00:00Z",
                    "expires_at": "2027-01-01T00:00:00Z",
                    "identities": identities,
                }
                checkpoint_body = {
                    "schema_version": replay.trust.CHECKPOINT_SCHEMA,
                    "registry_id": registry["registry_id"], "generation": generation,
                    "registry_sha256": replay.trust.digest(registry),
                    "previous_checkpoint_sha256": previous_pin,
                    "issued_at": registry["issued_at"],
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
                return bundle, replay.trust.digest(checkpoint_body)

            historical_bundle, historical_pin = make_registry(1)
            current_bundle, current_pin = make_registry(2, historical_pin, enroll=True)
            verified_root = replay.trust.verify_registry(
                current_bundle, anchor,
                expected_anchor_fingerprint=anchor["key_fingerprint_sha256"],
                expected_state_checkpoint_sha256=current_pin,
                expected_previous_checkpoint_sha256=historical_pin,
                historical_registry_bundles=[historical_bundle], now=now,
            )
            self.assertEqual(verified_root["status"], "PASS", verified_root)
            trust_store = {}
            for identity_id, record in verified_root["identity_registry"].items():
                trust_store[identity_id] = {
                    "reviewer_id": identity_id, "key_id": record["key_id"],
                    "public_key_ed25519": record["public_key_ed25519"],
                    "role": list(record["scopes"]), "scopes": list(record["scopes"]),
                    "valid_from": record["valid_from"], "valid_until": record["valid_until"],
                    "revoked": record["revoked"], "identity_class": record["identity_class"],
                }
            canonical_reviewers = {
                identity_id: {
                    **trust_store[identity_id],
                    "role": list(verified_root["identity_registry"][identity_id]["scopes"]),
                }
                for identity_id in verified_root["identity_registry"]
                if "reviewer" in verified_root["identity_registry"][identity_id]["roles"]
            }
            transition_inputs = {
                "schema_version": replay.REPLAY_INPUT_SCHEMA,
                "transition_receipts": receipts, "chain_id": "CHAIN-INTEGRATED-SYNTH",
                "local_checkpoints": [],
                "stage_artifact_ids": {},
            }
            transition_result = phase7.verify_artifact_backed_transitions(
                receipts, stage_paths, artifact_root, canonical_reviewers, now=now,
            )
            self.assertEqual(transition_result["status"], "PASS", transition_result["issues"])

            ci_results, ci_statement, ci_bundle = closure_fixtures.ci_fixture()
            ci_statement = dict(ci_statement, workflow_ref=(
                f"{closure.REPOSITORY}/{closure.WORKFLOW}@refs/pull/87/merge"
            ))
            ci_cases = json.loads(ci_results)
            ci_statement["matrix_results_sha256"] = phase6.digest(ci_cases)
            payload = {
                "_type": "https://in-toto.io/Statement/v1",
                "subject": [{
                    "name": "m21_phase7_acceptance_matrix_results.json",
                    "digest": {"sha256": closure.sha256_bytes(ci_results)},
                }],
                "predicateType": closure.PREDICATE_TYPE, "predicate": ci_statement,
            }
            ci_bundle = json.dumps({
                "dsseEnvelope": {"payload": base64.b64encode(json.dumps(
                    payload, sort_keys=True, separators=(",", ":"),
                ).encode()).decode()},
            }, sort_keys=True, separators=(",", ":")).encode()
            run_data = {
                "head_sha": ci_statement["tested_commit_sha"], "status": "completed",
                "conclusion": "success", "run_attempt": ci_statement["run_attempt"],
                "event": ci_statement["event_name"], "path": closure.WORKFLOW,
            }
            jobs_data = {"jobs": [{
                "name": "phase7-acceptance-evidence",
                "status": "completed", "conclusion": "success",
            }]}
            def gh_boundary(args, **kwargs):
                if args[1:3] == ["attestation", "verify"]:
                    return SimpleNamespace(returncode=0, stdout="", stderr="")
                response = jobs_data if "jobs?" in args[-1] else run_data
                return SimpleNamespace(returncode=0, stdout=json.dumps(response), stderr="")
            with (
                patch.object(closure.shutil, "which", return_value="/test-only/gh"),
                patch.object(closure.subprocess, "run", side_effect=gh_boundary),
            ):
                ci_verified = closure.verify_ci_acceptance(
                    ci_results, ci_statement, ci_bundle,
                    expected_revision=closure_fixtures.REVISION, now=now,
                )
            self.assertEqual(ci_verified["status"], "PASS", ci_verified)

            chain_id = "CHAIN-INTEGRATED-CUSTODY"
            event = phase6.make_audit_event(
                "EVT-INTEGRATED-0001", "SYNTHETIC_ZIP", "2026-10-20T10:00:00Z",
                {"fixture": replay.hashlib.sha256(b"retained synthetic event").hexdigest()},
                "synthetic-test", "PASS", None,
            )
            checkpoint_content = {
                "dataset_id": "DS-SYNTH00001", "chain_id": chain_id,
                "event_count": 1, "event_sha256": event["event_sha256"], "sequence": 1,
                "created_at": "2026-10-20T11:00:00Z", "previous_checkpoint_sha256": None,
                "trust_store_identity": phase6.digest(trust_store),
            }
            checkpoint_approval = {
                "status": "APPROVED", "approval_id": "APR-000000000001",
                "reviewer_id": checkpoint_reviewer,
                "key_id": fixture.trust[checkpoint_reviewer]["key_id"],
                "approved_at": "2026-10-20T11:00:00Z",
                "expires_at": "2027-01-01T00:00:00Z",
                "evidence_sha256": event["event_sha256"],
                "manifest_sha256": phase6.digest(checkpoint_content),
            }
            checkpoint_approval["signature_ed25519"] = base64.b64encode(
                fixture.private[checkpoint_reviewer].sign(readiness._approval_payload(
                    "DS-SYNTH00001", chain_id, "custody_checkpoint", checkpoint_approval,
                )),
            ).decode()
            checkpoint = {**checkpoint_content, "approval": checkpoint_approval}
            custody_core = {
                "benchmark_snapshot_id": "DS-SYNTH00001", "dataset_id": "DS-SYNTH00001",
                "chain_id": chain_id, "retained_checkpoints": [checkpoint],
            }
            retention_receipt = {
                "source_uri": "https://synthetic-custody.example/archive",
                "retrieved_at": "2026-10-20T12:00:00Z",
                "retrieved_by": "independent-synthetic-retriever",
                "custodian_id": custodian,
                "key_id": fixture.trust[custodian]["key_id"],
                "package_sha256": phase6.digest(custody_core),
            }
            retention_receipt["signature_ed25519"] = base64.b64encode(
                fixture.private[custodian].sign(closure.canonical_bytes(retention_receipt)),
            ).decode()
            custody_package = {
                "schema_version": "m21-phase7-retained-checkpoints-v1",
                **custody_core, "retention_receipt": retention_receipt,
            }
            checkpoint_verified = closure.verify_checkpoint_retention(
                custody_package, trust_store, local_events=[event],
                local_checkpoints=[checkpoint], expected_snapshot="DS-SYNTH00001", now=now,
            )
            self.assertEqual(checkpoint_verified["status"], "PASS", checkpoint_verified)

            closure_components = {
                "reference_panel_evidence": transition_result["reference_panel_result"],
                "scientific_approval_evidence": transition_result["scientific_approval_result"],
                "canonical_transition_evidence": transition_result,
            }
            closure_package = {
                "schema_version": closure.SCHEMA_VERSION,
                "verification_policy": closure.SCHEMA_VERSION,
                "software_revision": closure_fixtures.REVISION,
                **{name: phase6.digest(value) for name, value in closure_components.items()},
                "ci_acceptance": phase6.digest(ci_verified),
                "checkpoint_retention": phase6.digest(checkpoint_verified),
                "expires_at": "2027-01-01T00:00:00Z",
                "limitations": ["Synthetic test evidence only."],
            }
            closure_package_sha = phase6.digest(closure_package)
            closure_evidence_sha = phase6.digest({
                "package_sha256": closure_package_sha, "ci_verification": ci_verified,
                "checkpoint_verification": checkpoint_verified,
                "verification_policy": closure.SCHEMA_VERSION,
            })
            closure_approvals = []
            for index, reviewer_id in enumerate(closure_reviewers):
                approval = {
                    "status": "APPROVED", "approval_id": f"APR-00000000000{index + 2}",
                    "reviewer_id": reviewer_id,
                    "key_id": fixture.trust[reviewer_id]["key_id"],
                    "approved_at": "2026-10-20T13:00:00Z",
                    "expires_at": "2027-01-01T00:00:00Z",
                    "evidence_sha256": closure_evidence_sha,
                    "manifest_sha256": closure_package_sha,
                }
                approval["signature_ed25519"] = base64.b64encode(
                    fixture.private[reviewer_id].sign(readiness._approval_payload(
                        closure_fixtures.REVISION, closure_package_sha,
                        closure.REVIEW_SCOPE, approval,
                    )),
                ).decode()
                closure_approvals.append(approval)

            artifact_bytes = {}
            descriptors = []
            id_by_path = {}
            def add_artifact(path, kind, content):
                artifact_id = f"integrated-{len(descriptors):04d}"
                artifact_bytes[path] = content
                id_by_path[path] = artifact_id
                descriptors.append({
                    "artifact_id": artifact_id, "path": path, "kind": kind,
                    "sha256": replay.hashlib.sha256(content).hexdigest(),
                    "size_bytes": len(content),
                })
            stage_kind = {
                ("REFERENCE_APPROVED", "reference_panel_manifest"): "reference_panel",
                ("REFERENCE_APPROVED", "aggregate_exclusion"): "scientific_approval",
                ("REFERENCE_APPROVED", "scientific_review"): "scientific_evidence",
                ("QUALIFIED", "control_qualification"): "control_qualification",
            }
            for state, artifacts in stage_paths.items():
                for artifact_type, relative in artifacts.items():
                    source_path = artifact_root / relative
                    add_artifact(
                        relative, stage_kind.get((state, artifact_type), "transition_artifact"),
                        source_path.read_bytes(),
                    )
            add_artifact("refs/panel.fa", "reference_file", (artifact_root / "refs/panel.fa").read_bytes())
            stage_ids = {
                state: {kind: id_by_path[path] for kind, path in entries.items()}
                for state, entries in stage_paths.items()
            }
            required_data = {
                "transition_evidence": phase6.canonical_bytes(receipts),
                "ci_results": ci_results,
                "ci_statement": phase6.canonical_bytes(ci_statement),
                "ci_attestation": ci_bundle,
                "reviewer_approvals": phase6.canonical_bytes({
                    "closure_package": closure_package, "approvals": closure_approvals,
                }),
                "trust_registry": phase6.canonical_bytes(current_bundle),
                "trust_registry_history": phase6.canonical_bytes([historical_bundle]),
                "checkpoint_history": phase6.canonical_bytes([checkpoint]),
                "custody_receipt": phase6.canonical_bytes(retention_receipt),
                "audit_chain": phase6.canonical_bytes([event]),
            }
            for kind, content in required_data.items():
                add_artifact(f"package/{kind}.json", kind, content)
            transition_inputs = {
                **transition_inputs,
                "stage_artifact_ids": stage_ids,
                "chain_id": chain_id,
                "local_checkpoints": [checkpoint],
            }
            add_artifact("package/replay_inputs.json", "replay_inputs",
                         phase6.canonical_bytes(transition_inputs))
            manifest = {
                "schema_version": replay.SCHEMA_VERSION,
                "software_revision": closure_fixtures.REVISION,
                "snapshot_id": "DS-SYNTH00001", "policy_version": "integrated-synthetic-v1",
                "artifacts": descriptors, "limitations": ["Synthetic fixture only."],
            }
            with tempfile.TemporaryDirectory() as temp:
                temp_root = Path(temp)
                anchor_path = temp_root / "anchor.json"
                anchor_path.write_text(json.dumps(anchor), encoding="utf-8")
                package_path = temp_root / "fully-signed-synthetic.zip"
                with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.writestr("manifest.json", phase6.canonical_bytes(manifest))
                    for path, content in artifact_bytes.items():
                        archive.writestr(path, content)
                with (
                    patch.object(closure.shutil, "which", return_value="/test-only/gh"),
                    patch.object(closure.subprocess, "run", side_effect=gh_boundary),
                ):
                    result = replay.verify_package(
                        package_path, trust_anchor_path=anchor_path,
                        trust_anchor_fingerprint=anchor["key_fingerprint_sha256"],
                        trust_state_checkpoint_sha256=current_pin,
                        previous_trust_state_checkpoint_sha256=historical_pin, now=now,
                    )
                    repeated = replay.verify_package(
                        package_path, trust_anchor_path=anchor_path,
                        trust_anchor_fingerprint=anchor["key_fingerprint_sha256"],
                        trust_state_checkpoint_sha256=current_pin,
                        previous_trust_state_checkpoint_sha256=historical_pin, now=now,
                    )
            self.assertEqual(
                json.dumps(result, sort_keys=True),
                json.dumps(repeated, sort_keys=True),
            )
            mutations = {
                "invalid scientific approval": (
                    "scientific_approval", lambda _: b"{}",
                ),
                "incorrect reference identity": (
                    "reference_file", lambda _: b">altered-reference\nNNNN\n",
                ),
                "control-qualification substitution": (
                    "control_qualification", lambda _: b"{}",
                ),
                "altered transition receipt": (
                    "replay_inputs",
                    lambda raw: phase6.canonical_bytes({
                        **json.loads(raw),
                        "transition_receipts": [
                            {
                                **json.loads(raw)["transition_receipts"][0],
                                "receipt": {
                                    **json.loads(raw)["transition_receipts"][0]["receipt"],
                                    "verification_result": "FAIL",
                                },
                            },
                            *json.loads(raw)["transition_receipts"][1:],
                        ],
                    }),
                ),
                "missing custody checkpoint": (
                    "checkpoint_history", lambda _: b"[]",
                ),
                "modified custody checkpoint": (
                    "checkpoint_history",
                    lambda raw: phase6.canonical_bytes([
                        {**json.loads(raw)[0], "sequence": 2},
                    ]),
                ),
                "invalid reviewer signature": (
                    "reviewer_approvals",
                    lambda raw: phase6.canonical_bytes({
                        **json.loads(raw),
                        "approvals": [
                            {**approval, "signature_ed25519": "A" * 88}
                            for approval in json.loads(raw)["approvals"]
                        ],
                    }),
                ),
                "wrong CI run attempt": (
                    "ci_statement",
                    lambda raw: phase6.canonical_bytes({
                        **json.loads(raw),
                        "run_attempt": json.loads(raw)["run_attempt"] + 1,
                    }),
                ),
            }
            with tempfile.TemporaryDirectory() as mutation_temp:
                mutation_root = Path(mutation_temp)
                mutation_anchor = mutation_root / "anchor.json"
                mutation_anchor.write_text(json.dumps(anchor), encoding="utf-8")
                for index, (label, (kind, mutate)) in enumerate(mutations.items()):
                    with self.subTest(mutation=label):
                        mutated_contents = dict(artifact_bytes)
                        mutated_descriptors = json.loads(json.dumps(descriptors))
                        mutated_manifest = json.loads(json.dumps(manifest))
                        descriptor = next(item for item in mutated_descriptors if item["kind"] == kind)
                        path = descriptor["path"]
                        mutated_contents[path] = mutate(mutated_contents[path])
                        descriptor["size_bytes"] = len(mutated_contents[path])
                        descriptor["sha256"] = replay.hashlib.sha256(
                            mutated_contents[path],
                        ).hexdigest()
                        if label == "cross-snapshot evidence substitution":
                            mutated_manifest["snapshot_id"] = "DS-OTHER00001"
                        mutated_manifest["artifacts"] = mutated_descriptors
                        mutated_path = mutation_root / f"mutation-{index}.zip"
                        with zipfile.ZipFile(
                            mutated_path, "w", compression=zipfile.ZIP_DEFLATED,
                        ) as archive:
                            archive.writestr(
                                "manifest.json", phase6.canonical_bytes(mutated_manifest),
                            )
                            for member, content in mutated_contents.items():
                                archive.writestr(member, content)
                        with (
                            patch.object(closure.shutil, "which", return_value="/test-only/gh"),
                            patch.object(closure.subprocess, "run", side_effect=gh_boundary),
                        ):
                            rejected = replay.verify_package(
                                mutated_path, trust_anchor_path=mutation_anchor,
                                trust_anchor_fingerprint=anchor["key_fingerprint_sha256"],
                                trust_state_checkpoint_sha256=current_pin,
                                previous_trust_state_checkpoint_sha256=historical_pin,
                                now=now,
                            )
                        self.assertEqual(rejected["decision"], "FAIL", rejected)
                with self.subTest(mutation="cross-snapshot evidence substitution"):
                    mutated_contents = dict(artifact_bytes)
                    mutated_descriptors = json.loads(json.dumps(descriptors))
                    mutated_manifest = json.loads(json.dumps(manifest))
                    mutated_manifest["snapshot_id"] = "DS-OTHER00001"
                    mutated_manifest["artifacts"] = mutated_descriptors
                    mutated_path = mutation_root / "cross-snapshot.zip"
                    with zipfile.ZipFile(
                        mutated_path, "w", compression=zipfile.ZIP_DEFLATED,
                    ) as archive:
                        archive.writestr(
                            "manifest.json", phase6.canonical_bytes(mutated_manifest),
                        )
                        for member, content in mutated_contents.items():
                            archive.writestr(member, content)
                    with (
                        patch.object(closure.shutil, "which", return_value="/test-only/gh"),
                        patch.object(closure.subprocess, "run", side_effect=gh_boundary),
                    ):
                        rejected = replay.verify_package(
                            mutated_path, trust_anchor_path=mutation_anchor,
                            trust_anchor_fingerprint=anchor["key_fingerprint_sha256"],
                            trust_state_checkpoint_sha256=current_pin,
                            previous_trust_state_checkpoint_sha256=historical_pin,
                            now=now,
                        )
                    self.assertEqual(rejected["decision"], "FAIL", rejected)
            self.assertEqual(result["decision"], "INCOMPLETE", result["issues"])
            self.assertEqual(result["canonical_transition_status"], "PASS")
            self.assertEqual(result["checkpoint_retention_status"], "PASS")
            self.assertEqual(result["ci_attestation_status"], "PASS")
            self.assertEqual(result["closure_decision"], "INCOMPLETE")
            self.assertEqual(result["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
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
