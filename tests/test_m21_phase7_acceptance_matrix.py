"""Individually reported fail-closed attacks against a complete synthetic chain."""
import copy
import json
import unittest
from pathlib import Path
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    Ed25519PrivateKey = None

from satellite_discovery import m21_phase6_governance as gov
from satellite_discovery import m21_phase7_evidence as phase7

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


def _edit(case, state, artifact, update):
    def mutate(fixture, receipts, paths, root):
        path = root / paths[state][artifact]
        value = json.loads(path.read_text(encoding="utf-8"))
        update(value)
        path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    return mutate


def _remove(state, artifact):
    def mutate(fixture, receipts, paths, root):
        (root / paths[state][artifact]).unlink()
    return mutate


def _alter_raw(state, artifact):
    def mutate(fixture, receipts, paths, root):
        path = root / paths[state][artifact]
        path.write_bytes(path.read_bytes() + b"altered")
    return mutate


def _replay(fixture, receipts, paths, root):
    receipts.append(copy.deepcopy(receipts[0]))


def _invalid_transition(fixture, receipts, paths, root):
    receipts[2]["receipt"]["requested_state"] = "UNBLINDING_AUTHORISED"


def _expired_signer(fixture, receipts, paths, root):
    reviewer = receipts[0]["approvals"][0]["reviewer_id"]
    fixture.trust[reviewer]["valid_until"] = "2026-10-20T00:00:00Z"


def _revoked_signer(fixture, receipts, paths, root):
    reviewer = receipts[0]["approvals"][0]["reviewer_id"]
    fixture.trust[reviewer]["revoked"] = True


def _wrong_artifact_type(fixture, receipts, paths, root):
    paths["QUALIFIED"]["control_qualification"] = paths["QUALIFIED"]["qualification_evidence"]


def _changed_after_verification(fixture, receipts, paths, root):
    original = phase7._file_sha
    mutation = {"calls": 0, "changed": False}

    def race(path):
        result = original(path)
        mutation["calls"] += 1
        if mutation["calls"] == 1:
            # Mutate the first artifact only after its initial digest has been
            # computed. Append mode avoids replace/rename semantics that vary
            # across Windows and POSIX filesystems.
            with Path(path).open("ab") as stream:
                stream.write(b" ")
                stream.flush()
            mutation["changed"] = True
        return result

    fixture._phase7_file_hash_patch = race
    fixture._phase7_file_hash_mutation = mutation


def _checkpoint_fixture(fixture, chain_id, event_id, event_time, checkpoint_time,
                        sequence, event_digest, previous_checkpoint=None):
    content = {
        "dataset_id": gov.DATASET_ID if hasattr(gov, "DATASET_ID") else "DS-SYNTH00001",
        "chain_id": chain_id, "event_count": sequence,
        "event_sha256": event_digest, "sequence": sequence,
        "created_at": checkpoint_time,
        "previous_checkpoint_sha256": previous_checkpoint,
        "trust_store_identity": gov.digest(fixture.trust),
    }
    approval = fixture.approval(
        "custody_checkpoint", gov.digest(content), event_digest, sequence % 2,
        dataset=content["dataset_id"], sample=chain_id,
    )
    return {**content, "approval": approval}


def _checkpoint_rollback(fixture, receipts, paths, root):
    event = gov.make_audit_event("EVT-MATRIX-1", "QUALIFIED", "2026-10-21T10:00:00Z",
                                 {"qualification": "a" * 64}, None, "PASS", None)
    checkpoint = _checkpoint_fixture(fixture, "CHAIN-MATRIX-01", event["event_id"],
                                     "2026-10-21T10:00:00Z", "2026-10-21T11:00:00Z",
                                     1, event["event_sha256"])
    result = phase7.verify_independent_custody(
        [], [checkpoint], [checkpoint], fixture.trust, dataset_id="DS-SYNTH00001",
        chain_id="CHAIN-MATRIX-01", trust_store_identity=gov.digest(fixture.trust), now=NOW,
    )
    fixture._phase7_direct_result = result


def _checkpoint_missing_local_history(fixture, receipts, paths, root):
    event = gov.make_audit_event("EVT-MATRIX-2", "QUALIFIED", "2026-10-21T10:00:00Z",
                                 {"qualification": "b" * 64}, None, "PASS", None)
    checkpoint = _checkpoint_fixture(fixture, "CHAIN-MATRIX-02", event["event_id"],
                                     "2026-10-21T10:00:00Z", "2026-10-21T11:00:00Z",
                                     1, event["event_sha256"])
    result = phase7.verify_independent_custody(
        [event], [], [checkpoint], fixture.trust, dataset_id="DS-SYNTH00001",
        chain_id="CHAIN-MATRIX-02", trust_store_identity=gov.digest(fixture.trust), now=NOW,
    )
    fixture._phase7_direct_result = result


def _checkpoint_rotation_reordered(fixture, receipts, paths, root):
    chain_id = "CHAIN-MATRIX-03"
    first = gov.make_audit_event("EVT-MATRIX-3", "QUALIFIED", "2026-10-21T10:00:00Z",
                                 {"qualification": "c" * 64}, None, "PASS", None)
    first_checkpoint = _checkpoint_fixture(
        fixture, chain_id, first["event_id"], "2026-10-21T10:00:00Z",
        "2026-10-21T11:00:00Z", 1, first["event_sha256"],
    )
    suffix = gov.make_audit_event("EVT-MATRIX-4", "REFERENCE_APPROVED", "2026-10-21T12:00:00Z",
                                  {"reference": "d" * 64}, None, "PASS", first["event_sha256"])
    previous = gov.digest({
        **{key: value for key, value in first_checkpoint.items() if key != "approval"},
        "approval_set_sha256": gov._approval_set_digest([first_checkpoint["approval"]]),
    })
    second_checkpoint = _checkpoint_fixture(
        fixture, chain_id, suffix["event_id"], "2026-10-21T12:00:00Z",
        "2026-10-21T13:00:00Z", 2, suffix["event_sha256"], previous,
    )
    result = phase7.verify_independent_custody(
        [first, suffix], [second_checkpoint, first_checkpoint],
        [second_checkpoint, first_checkpoint], fixture.trust,
        dataset_id="DS-SYNTH00001", chain_id=chain_id,
        trust_store_identity=gov.digest(fixture.trust), now=NOW,
    )
    fixture._phase7_direct_result = result


_CASES = [
    ("missing_qualification_document", _remove("QUALIFIED", "control_qualification")),
    ("altered_qualification_evidence", _alter_raw("QUALIFIED", "qualification_evidence")),
    ("missing_reference_manifest", _remove("REFERENCE_APPROVED", "reference_panel_manifest")),
    ("reference_snapshot_substitution", _edit("x", "REFERENCE_APPROVED", "reference_panel_manifest", lambda x: x.update(benchmark_snapshot_id="DS-SYNTH99999"))),
    ("duplicate_reference_artifact", _edit("x", "REFERENCE_APPROVED", "reference_panel_manifest", lambda x: x["reference_manifest"]["references"].append(copy.deepcopy(x["reference_manifest"]["references"][0])))),
    ("excluded_sequence_policy_change", _edit("x", "REFERENCE_APPROVED", "exclusion_policy", lambda x: x["excluded_sequences"].append({"sequence_id": "SYNTH-X", "sequence": "CCCC", "sha256": "0" * 64}))),
    ("aggregate_budget_exhaustion", _edit("x", "REFERENCE_APPROVED", "aggregate_exclusion", lambda x: x["aggregate_limits"].update(max_total_bytes=1))),
    ("scientific_review_rejection", _edit("x", "REFERENCE_APPROVED", "scientific_review", lambda x: x["review"].update(decision="REJECT"))),
    ("altered_policy_approval", _edit("x", "REFERENCE_APPROVED", "aggregate_exclusion", lambda x: x["policy_approvals"][0].update(signature_ed25519="invalid"))),
    ("missing_blinded_analysis", _remove("BLINDED_ANALYSIS_VERIFIED", "blinded_analysis")),
    ("analysis_digest_substitution", _edit("x", "BLINDED_ANALYSIS_VERIFIED", "blinded_analysis", lambda x: x["analysis"].update(analysis_sha256="0" * 64))),
    ("truth_leakage_in_analysis", _edit("x", "BLINDED_ANALYSIS_VERIFIED", "blinded_analysis", lambda x: x["analysis"]["samples"][0].update(label="POSITIVE"))),
    ("qualification_binding_substitution", _edit("x", "BLINDED_ANALYSIS_VERIFIED", "blinded_analysis", lambda x: x.update(qualification_sha256s=["0" * 64]))),
    ("missing_unblinding_authorization", _remove("UNBLINDING_AUTHORISED", "unblinding_authorization")),
    ("unblinding_snapshot_substitution", _edit("x", "UNBLINDING_AUTHORISED", "unblinding_authorization", lambda x: x.update(benchmark_snapshot_id="DS-SYNTH99999"))),
    ("altered_unblinding_signature", _edit("x", "UNBLINDING_AUTHORISED", "unblinding_authorization", lambda x: x["approvals"][0].update(signature_ed25519="invalid"))),
    ("missing_truth_bundle", _remove("SYNTHETIC_SCORING_COMPLETE", "truth_bundle")),
    ("scoring_result_tamper", _edit("x", "SYNTHETIC_SCORING_COMPLETE", "synthetic_scoring_result", lambda x: x["result"].update(status="FAIL"))),
    ("wrong_artifact_type", _wrong_artifact_type),
    ("artifact_changed_during_verification", _changed_after_verification),
    ("receipt_replay", _replay),
    ("invalid_intermediate_transition", _invalid_transition),
    ("expired_transition_signer", _expired_signer),
    ("revoked_transition_signer", _revoked_signer),
    ("checkpoint_rollback", _checkpoint_rollback),
    ("checkpoint_missing_local_history", _checkpoint_missing_local_history),
    ("checkpoint_rotation_reordered", _checkpoint_rotation_reordered),
]


@unittest.skipIf(
    Ed25519PrivateKey is None,
    "cryptography is required for signed synthetic Phase 7 acceptance fixtures",
)
class M21Phase7AdversarialAcceptanceMatrix(unittest.TestCase):
    def test_named_matrix_functions_match_the_trusted_case_registry(self):
        self.assertEqual(
            tuple(case for case, _ in _CASES),
            phase7.PHASE7_ACCEPTANCE_CASES,
        )

    def setUp(self):
        from tests import test_m21_phase6_governance
        M21Phase6GovernanceTests = test_m21_phase6_governance.M21Phase6GovernanceTests
        self.fixture = M21Phase6GovernanceTests(methodName="runTest")
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def run_case(self, case_name, mutate):
        receipts, paths, root = self.fixture.phase7_complete_synthetic_transition()
        mutate(self.fixture, receipts, paths, root)
        direct = getattr(self.fixture, "_phase7_direct_result", None)
        if direct is not None:
            self.assertEqual(direct["status"], "FAIL", f"{case_name} was accepted")
            del self.fixture._phase7_direct_result
            return
        if getattr(self.fixture, "_phase7_file_hash_patch", None):
            from unittest.mock import patch
            with patch.object(phase7, "_file_sha", side_effect=self.fixture._phase7_file_hash_patch):
                result = phase7.verify_artifact_backed_transitions(
                    receipts, paths, root, self.fixture.trust, now=NOW,
                )
            self.assertTrue(
                self.fixture._phase7_file_hash_mutation["changed"],
                "the deterministic mutation hook must alter an artifact after its initial digest",
            )
        else:
            result = phase7.verify_artifact_backed_transitions(
                receipts, paths, root, self.fixture.trust, now=NOW,
            )
        self.assertEqual(result["status"], "FAIL", f"{case_name} was accepted")
        self.assertFalse(result.get("biological_execution_authorized", False))


def _matrix_test(case_name, mutate):
    def test(self):
        self.run_case(case_name, mutate)
    test.__name__ = f"test_{case_name}"
    test.__doc__ = f"Reject synthetic adversarial case: {case_name}."
    return test


for _case_name, _mutator in _CASES:
    setattr(M21Phase7AdversarialAcceptanceMatrix, f"test_{_case_name}", _matrix_test(_case_name, _mutator))

