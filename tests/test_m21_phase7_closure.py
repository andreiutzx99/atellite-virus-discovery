import base64
import copy
import json
import unittest
from datetime import datetime, timezone
from subprocess import CompletedProcess
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from satellite_discovery import m21_benchmark_readiness as readiness
from satellite_discovery import m21_phase6_governance as gov
from satellite_discovery import m21_phase7_closure as closure
from satellite_discovery import m21_phase7_evidence as phase7


NOW = datetime(2026, 10, 26, 16, 0, tzinfo=timezone.utc)
REVISION = "a" * 40


def ci_fixture():
    cases = [
        {"case_id": case, "test_name": "test_" + case, "expected": "FAIL", "observed": "FAIL"}
        for case in phase7.PHASE7_ACCEPTANCE_CASES
    ]
    results = gov.canonical_bytes(cases)
    statement = {
        "schema_version": "m21-phase7-ci-run-statement-v1",
        "repository": closure.REPOSITORY,
        "workflow": closure.WORKFLOW,
        "workflow_ref": f"{closure.REPOSITORY}/{closure.WORKFLOW}@refs/heads/m21/phase7-governance-closure",
        "run_id": "40342500597", "run_attempt": 1,
        "run_sha": REVISION, "tested_commit_sha": REVISION,
        "event_name": "push", "acceptance_tests_conclusion": "success",
        "matrix_results_sha256": gov.digest(cases),
    }
    payload = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [{
            "name": "m21_phase7_acceptance_matrix_results.json",
            "digest": {"sha256": closure.sha256_bytes(results)},
        }],
        "predicateType": closure.PREDICATE_TYPE,
        "predicate": statement,
    }
    bundle = json.dumps({
        "dsseEnvelope": {"payload": base64.b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).decode()}
    }, sort_keys=True, separators=(",", ":")).encode()
    return results, statement, bundle


class Phase7ClosureTests(unittest.TestCase):
    def test_ci_attestation_requires_authoritative_gh_verification(self):
        results, statement, bundle = ci_fixture()
        responses = [
            CompletedProcess([], 0, "", ""),
            CompletedProcess([], 0, json.dumps({
                "status": "completed", "conclusion": "success", "run_attempt": 1,
                "event": "push", "path": closure.WORKFLOW, "head_sha": REVISION,
            }), ""),
            CompletedProcess([], 0, json.dumps({
                "jobs": [{"name": "phase7-acceptance-evidence",
                          "status": "completed", "conclusion": "success"}],
            }), ""),
        ]
        with patch.object(closure.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(closure.subprocess, "run", side_effect=responses):
            result = closure.verify_ci_acceptance(
                results, statement, bundle, expected_revision=REVISION, now=NOW,
            )
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(closure._is_verified_evidence(result))

    def test_ci_attestation_missing_verifier_stays_incomplete(self):
        results, statement, bundle = ci_fixture()
        with patch.object(closure.shutil, "which", return_value=None):
            result = closure.verify_ci_acceptance(
                results, statement, bundle, expected_revision=REVISION, now=NOW,
            )
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_ci_attestation_rejects_wrong_run_attempt_or_failed_acceptance_job(self):
        results, statement, bundle = ci_fixture()
        for run_data, jobs_data in (
            (
                {"status": "completed", "conclusion": "success", "run_attempt": 2,
                 "event": "push", "path": closure.WORKFLOW, "head_sha": REVISION},
                {"jobs": [{"name": "phase7-acceptance-evidence",
                           "status": "completed", "conclusion": "success"}]},
            ),
            (
                {"status": "completed", "conclusion": "success", "run_attempt": 1,
                 "event": "push", "path": closure.WORKFLOW, "head_sha": REVISION},
                {"jobs": [{"name": "phase7-acceptance-evidence",
                           "status": "completed", "conclusion": "failure"}]},
            ),
        ):
            responses = [
                CompletedProcess([], 0, "", ""),
                CompletedProcess([], 0, json.dumps(run_data), ""),
                CompletedProcess([], 0, json.dumps(jobs_data), ""),
            ]
            with patch.object(closure.shutil, "which", return_value="/usr/bin/gh"), \
                 patch.object(closure.subprocess, "run", side_effect=responses):
                result = closure.verify_ci_acceptance(
                    results, statement, bundle, expected_revision=REVISION, now=NOW,
                )
            self.assertEqual(result["status"], "FAIL")

    def test_ci_attestation_rejects_tampered_subject_digest(self):
        results, statement, bundle = ci_fixture()
        payload = json.loads(base64.b64decode(
            json.loads(bundle)["dsseEnvelope"]["payload"]
        ))
        payload["subject"][0]["digest"]["sha256"] = "0" * 64
        bundle = json.dumps({"dsseEnvelope": {"payload": base64.b64encode(
            json.dumps(payload).encode()
        ).decode()}}).encode()
        with patch.object(closure.shutil, "which", return_value="/usr/bin/gh"):
            result = closure.verify_ci_acceptance(
                results, statement, bundle, expected_revision=REVISION, now=NOW,
            )
        self.assertEqual(result["status"], "FAIL")

    def test_ci_attestation_rejects_partial_matrix_and_wrong_workflow(self):
        results, statement, bundle = ci_fixture()
        partial = gov.canonical_bytes(json.loads(results)[:-1])
        with patch.object(closure.shutil, "which", return_value=None):
            result = closure.verify_ci_acceptance(
                partial, statement, bundle, expected_revision=REVISION, now=NOW,
            )
        self.assertEqual(result["status"], "FAIL")
        wrong = dict(statement, workflow_ref="owner/repo/.github/workflows/other.yml@refs/heads/main")
        result = closure.verify_ci_acceptance(
            results, wrong, bundle, expected_revision=REVISION, now=NOW,
        )
        self.assertEqual(result["status"], "FAIL")

    def _signed_synthetic_package(self):
        private = []
        trust = {}
        for index in range(2):
            reviewer_id = f"REV-{index + 1:08d}"
            key_id = f"KEY-{index + 1:010d}"
            key = Ed25519PrivateKey.generate()
            private.append(key)
            trust[reviewer_id] = {
                "reviewer_id": reviewer_id,
                "key_id": key_id,
                "public_key_ed25519": base64.b64encode(key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )).decode(),
                "role": closure.REVIEW_SCOPE, "scopes": [closure.REVIEW_SCOPE],
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z",
                "revoked": False, "identity_class": "SYNTHETIC",
            }
        component_results = {
            name: phase7._verified_result({"status": "PASS", "issues": []})
            for name in (
                "reference_panel_evidence", "scientific_approval_evidence",
                "canonical_transition_evidence",
            )
        }
        ci = closure._verified_evidence({
            "status": "PASS", "tested_commit_sha": REVISION,
            "evidence_class": "GITHUB_ATTESTATION",
        })
        checkpoints = closure._verified_evidence({
            "status": "PASS", "evidence_class": "SYNTHETIC",
        })
        package = {
            "schema_version": closure.SCHEMA_VERSION,
            "verification_policy": closure.SCHEMA_VERSION,
            "software_revision": REVISION,
            **{name: gov.digest(result) for name, result in component_results.items()},
            "ci_acceptance": gov.digest(ci),
            "checkpoint_retention": gov.digest(checkpoints),
            "expires_at": "2027-01-01T00:00:00Z",
            "limitations": ["Synthetic test evidence only."],
        }
        package_sha = gov.digest(package)
        evidence_sha = gov.digest({
            "package_sha256": package_sha, "ci_verification": ci,
            "checkpoint_verification": checkpoints,
            "verification_policy": closure.SCHEMA_VERSION,
        })
        approvals = []
        for index, (reviewer_id, key) in enumerate(zip(trust, private)):
            record = {
                "status": "APPROVED", "approval_id": f"APR-{index + 1:012d}",
                "reviewer_id": reviewer_id, "key_id": trust[reviewer_id]["key_id"],
                "approved_at": "2026-10-26T15:00:00Z",
                "expires_at": "2027-01-01T00:00:00Z",
                "evidence_sha256": evidence_sha, "manifest_sha256": package_sha,
            }
            record["signature_ed25519"] = base64.b64encode(key.sign(
                readiness._approval_payload(REVISION, package_sha, closure.REVIEW_SCOPE, record)
            )).decode()
            approvals.append(record)
        return package, approvals, trust, component_results, ci, checkpoints

    def test_synthetic_closure_package_never_reports_operational_pass(self):
        package, approvals, trust, components, ci, checkpoints = self._signed_synthetic_package()
        result = closure.verify_closure_package(
            package, approvals, trust, verified_components=components,
            ci_verification=ci, checkpoint_verification=checkpoints, now=NOW,
        )
        self.assertEqual(result["decision"], "INCOMPLETE")
        self.assertEqual(result["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
        self.assertFalse(result["biological_execution_authorized"])

    def test_closure_rejects_caller_supplied_pass_fields_and_changed_revision(self):
        package, approvals, trust, components, ci, checkpoints = self._signed_synthetic_package()
        caller_pass = {name: {"status": "PASS"} for name in components}
        result = closure.verify_closure_package(
            package, approvals, trust, verified_components=caller_pass,
            ci_verification={"status": "PASS", "tested_commit_sha": REVISION},
            checkpoint_verification={"status": "PASS"}, now=NOW,
        )
        self.assertEqual(result["decision"], "INCOMPLETE")
        changed = dict(package, software_revision="b" * 40)
        result = closure.verify_closure_package(
            changed, approvals, trust, verified_components=components,
            ci_verification=ci, checkpoint_verification=checkpoints, now=NOW,
        )
        self.assertEqual(result["decision"], "FAIL")

    def _checkpoint_fixture(self, suffix=False):
        checkpoint_key = Ed25519PrivateKey.generate()
        custodian_key = Ed25519PrivateKey.generate()
        reviewers = {
            "REV-00000001": self._trust_record(
                "REV-00000001", "KEY-0000000001", checkpoint_key,
                "custody_checkpoint", "SYNTHETIC",
            ),
            "REV-00000002": self._trust_record(
                "REV-00000002", "KEY-0000000002", custodian_key,
                closure.RETENTION_SCOPE, "SYNTHETIC",
            ),
        }
        chain_id = "CHAIN-SYNTH-01"
        event1 = gov.make_audit_event(
            "EVT-SYNTH-0001", "FIXTURE", "2026-10-20T10:00:00Z",
            {"fixture": "a" * 64}, "synthetic-test", "PASS", None,
        )
        events = [event1]
        if suffix:
            event2 = gov.make_audit_event(
                "EVT-SYNTH-0002", "FIXTURE", "2026-10-20T11:00:00Z",
                {"fixture": "b" * 64}, "synthetic-test", "PASS",
                event1["event_sha256"],
            )
            events.append(event2)
        content = {
            "dataset_id": "DS-SYNTH00001", "chain_id": chain_id,
            "event_count": 1, "event_sha256": event1["event_sha256"],
            "sequence": 1, "created_at": "2026-10-20T12:00:00Z",
            "previous_checkpoint_sha256": None,
            "trust_store_identity": gov.digest(reviewers),
        }
        approval = {
            "status": "APPROVED", "approval_id": "APR-000000000001",
            "reviewer_id": "REV-00000001", "key_id": "KEY-0000000001",
            "approved_at": "2026-10-20T12:00:00Z",
            "expires_at": "2027-01-01T00:00:00Z",
            "evidence_sha256": event1["event_sha256"],
            "manifest_sha256": gov.digest(content),
        }
        approval["signature_ed25519"] = base64.b64encode(checkpoint_key.sign(
            readiness._approval_payload(
                "DS-SYNTH00001", chain_id, "custody_checkpoint", approval,
            )
        )).decode()
        checkpoint = {**content, "approval": approval}
        core = {
            "benchmark_snapshot_id": "DS-SYNTH00001",
            "dataset_id": "DS-SYNTH00001", "chain_id": chain_id,
            "retained_checkpoints": [checkpoint],
        }
        receipt = {
            "source_uri": "https://custody.example/synthetic",
            "retrieved_at": "2026-10-26T15:30:00Z",
            "retrieved_by": "synthetic-test-retriever",
            "custodian_id": "REV-00000002",
            "key_id": "KEY-0000000002", "package_sha256": gov.digest(core),
        }
        receipt["signature_ed25519"] = base64.b64encode(custodian_key.sign(
            closure.canonical_bytes(receipt),
        )).decode()
        package = {
            "schema_version": "m21-phase7-retained-checkpoints-v1",
            **core, "retention_receipt": receipt,
        }
        return package, reviewers, events, [checkpoint]

    @staticmethod
    def _trust_record(reviewer_id, key_id, key, role, identity_class):
        return {
            "reviewer_id": reviewer_id, "key_id": key_id,
            "public_key_ed25519": base64.b64encode(key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )).decode(),
            "role": role, "scopes": [role],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_until": "2027-01-01T00:00:00Z",
            "revoked": False, "identity_class": identity_class,
        }

    def test_external_checkpoint_retention_verifies_signed_chain_and_suffix(self):
        package, trust, events, checkpoints = self._checkpoint_fixture(suffix=True)
        result = closure.verify_checkpoint_retention(
            package, trust, local_events=events, local_checkpoints=checkpoints,
            expected_snapshot="DS-SYNTH00001", now=NOW,
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["evidence_class"], "SYNTHETIC")

    def test_checkpoint_rollback_substitution_missing_and_unauthenticated_source_fail(self):
        package, trust, events, checkpoints = self._checkpoint_fixture()
        result = closure.verify_checkpoint_retention(
            package, trust, local_events=[], local_checkpoints=checkpoints,
            expected_snapshot="DS-SYNTH00001", now=NOW,
        )
        self.assertEqual(result["status"], "FAIL")
        substituted = json.loads(json.dumps(package))
        substituted["retained_checkpoints"][0]["event_sha256"] = "0" * 64
        result = closure.verify_checkpoint_retention(
            substituted, trust, local_events=events, local_checkpoints=checkpoints,
            expected_snapshot="DS-SYNTH00001", now=NOW,
        )
        self.assertEqual(result["status"], "FAIL")
        missing = json.loads(json.dumps(package))
        missing["retained_checkpoints"] = []
        result = closure.verify_checkpoint_retention(
            missing, trust, local_events=events, local_checkpoints=checkpoints,
            expected_snapshot="DS-SYNTH00001", now=NOW,
        )
        self.assertEqual(result["status"], "FAIL")
        unauthenticated = json.loads(json.dumps(package))
        unauthenticated["retention_receipt"]["source_uri"] = "file:///tmp/checkpoints"
        result = closure.verify_checkpoint_retention(
            unauthenticated, trust, local_events=events, local_checkpoints=checkpoints,
            expected_snapshot="DS-SYNTH00001", now=NOW,
        )
        self.assertEqual(result["status"], "FAIL")

    def test_reviewer_approval_missing_duplicate_expired_or_revoked_is_rejected(self):
        package, approvals, trust, components, ci, checkpoints = self._signed_synthetic_package()
        result = closure.verify_closure_package(
            package, [], trust, verified_components=components,
            ci_verification=ci, checkpoint_verification=checkpoints, now=NOW,
        )
        self.assertEqual(result["decision"], "INCOMPLETE")
        result = closure.verify_closure_package(
            package, [approvals[0], copy.deepcopy(approvals[0])], trust,
            verified_components=components, ci_verification=ci,
            checkpoint_verification=checkpoints, now=NOW,
        )
        self.assertEqual(result["decision"], "FAIL")
        revoked = copy.deepcopy(trust)
        revoked[approvals[0]["reviewer_id"]]["revoked"] = True
        result = closure.verify_closure_package(
            package, approvals, revoked, verified_components=components,
            ci_verification=ci, checkpoint_verification=checkpoints, now=NOW,
        )
        self.assertEqual(result["decision"], "FAIL")
        expired = copy.deepcopy(trust)
        expired[approvals[0]["reviewer_id"]]["valid_until"] = "2026-10-25T00:00:00Z"
        result = closure.verify_closure_package(
            package, approvals, expired, verified_components=components,
            ci_verification=ci, checkpoint_verification=checkpoints, now=NOW,
        )
        self.assertEqual(result["decision"], "FAIL")


if __name__ == "__main__":
    unittest.main()
