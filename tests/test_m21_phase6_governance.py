import base64
import copy
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    serialization = None
    Ed25519PrivateKey = None

from satellite_discovery import m21_benchmark_readiness as readiness
from satellite_discovery import m21_phase6_governance as gov
from satellite_discovery import m21_reference_exclusion as exclusion
from satellite_discovery import m21_scientific_scoring as scoring


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
DS = "DS-SYNTH00001"
SAMPLE = "BLD-0123456789ABCDEF01234567"


@unittest.skipIf(Ed25519PrivateKey is None, "cryptography is required for synthetic Ed25519 tests")
class M21Phase6GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = {}
        self.trust = {}
        self.people = {}
        scopes = sorted(gov.PHASE6_SCOPES | {"reference_panel"})
        counter = 1
        for scope in scopes:
            self.people[scope] = []
            for _ in range(2):
                reviewer = f"REV-{counter:08d}"
                key_id = f"KEY-{counter:010d}"
                key = Ed25519PrivateKey.generate()
                public = key.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
                self.private[reviewer] = key
                self.trust[reviewer] = {
                    "reviewer_id": reviewer, "key_id": key_id,
                    "public_key_ed25519": base64.b64encode(public).decode(),
                    "role": scope, "scopes": [scope],
                    "valid_from": "2026-01-01T00:00:00Z",
                    "valid_until": "2027-01-01T00:00:00Z", "revoked": False,
                }
                self.people[scope].append(reviewer)
                counter += 1
        self.approval_counter = 1

    def tearDown(self):
        self.temp.cleanup()

    def approval(self, scope, binding, evidence, person=0, *, expires="2027-01-01T00:00:00Z",
                 approval_id=None, dataset=DS, sample=SAMPLE):
        reviewer = self.people[scope][person]
        trust_record = self.trust[reviewer]
        record = {
            "status": "APPROVED",
            "approval_id": approval_id or f"APR-{self.approval_counter:012d}",
            "reviewer_id": reviewer, "key_id": trust_record["key_id"],
            "approved_at": "2026-10-01T00:00:00Z", "expires_at": expires,
            "evidence_sha256": evidence, "manifest_sha256": binding,
        }
        self.approval_counter += 1
        record["signature_ed25519"] = base64.b64encode(
            self.private[reviewer].sign(readiness._approval_payload(dataset, sample, scope, record))
        ).decode()
        return record

    def control(self, *, control_class="POSITIVE", eval_status="EVALUABLE",
                inclusion="INCLUDE", sample=SAMPLE):
        evidence = b"synthetic qualification evidence"
        p4 = {
            "schema_version": "m21-control-qualification-v1",
            "control_id": "CTL-SYNTH00001", "control_class": "POSITIVE",
            "evidence_strength": "HIGH", "helper_status": "NOT_APPLICABLE",
            "sequence_completeness": "TERMINAL_VERIFIED", "study_group": "WITHIN_STUDY",
            "sensitivity_status": "ADEQUATE", "specificity_status": "ADEQUATE",
            "evaluation_status": eval_status, "denominator_inclusion": inclusion,
            "candidate_level_fp_reviewed": True, "sample_level_fp_reviewed": True,
        }
        content = {
            "phase4_qualification": p4, "control_id": p4["control_id"],
            "sample_ids": [sample], "control_class": control_class,
            "evaluation_status": eval_status,
            "scoring_eligibility": eval_status == "EVALUABLE" and inclusion == "INCLUDE",
            "exclusion_reason": None if inclusion == "INCLUDE" and eval_status == "EVALUABLE" else "PENDING_EVIDENCE",
            "study_id": "STUDY-SYNTH-01", "replicate_group": "BIO-SYNTH-01",
            "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        }
        binding = gov.digest(content)
        approvals = [self.approval("control_qualification", binding, content["evidence_sha256"], i)
                     for i in range(2)]
        return {"content": content, "approvals": approvals}, evidence

    def test_signed_control_qualification_derives_review_and_pending_stays_excluded(self):
        document, evidence = self.control()
        result = gov.verify_signed_control_qualification(document, evidence, self.trust, NOW)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["scoring_qualification"]["independently_reviewed"])
        self.assertEqual(len(result["reviewer_ids"]), 2)
        pending, pending_evidence = self.control(eval_status="PENDING", inclusion="EXCLUDE")
        result = gov.verify_signed_control_qualification(pending, pending_evidence, self.trust, NOW)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["scoring_qualification"]["scoring_eligibility"])
        unevaluable, unevaluable_evidence = self.control(eval_status="UNEVALUABLE", inclusion="EXCLUDE")
        result = gov.verify_signed_control_qualification(unevaluable, unevaluable_evidence, self.trust, NOW)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["scoring_qualification"]["scoring_eligibility"])

    def test_control_signature_attacks_fail_closed(self):
        doc, evidence = self.control()
        variants = []
        variants.append(("unsigned", {**doc, "approvals": []}, evidence, None))
        changed = json.loads(json.dumps(doc))
        changed["content"]["study_id"] = "STUDY-ALTERED"
        variants.append(("content tamper", changed, evidence, None))
        wrong_role = json.loads(json.dumps(doc))
        reviewer = wrong_role["approvals"][0]["reviewer_id"]
        role_trust = copy.deepcopy(self.trust)
        role_trust[reviewer]["role"] = "scientific_review"
        variants.append(("wrong role", wrong_role, evidence, role_trust))
        wrong_scope = json.loads(json.dumps(doc))
        scope_trust = copy.deepcopy(self.trust)
        scope_trust[reviewer]["scopes"] = ["scientific_review"]
        variants.append(("wrong scope", wrong_scope, evidence, scope_trust))
        expired = json.loads(json.dumps(doc))
        expired["approvals"] = [self.approval("control_qualification",
            gov.digest(expired["content"]), expired["content"]["evidence_sha256"], 0,
            expires="2026-10-20T00:00:00Z"),
            self.approval("control_qualification", gov.digest(expired["content"]),
            expired["content"]["evidence_sha256"], 1)]
        variants.append(("expired", expired, evidence, None))
        revoked = json.loads(json.dumps(doc))
        revoked_trust = copy.deepcopy(self.trust)
        revoked_trust[revoked["approvals"][0]["reviewer_id"]]["revoked"] = True
        variants.append(("revoked", revoked, evidence, revoked_trust))
        duplicate_reviewer = json.loads(json.dumps(doc))
        duplicate_reviewer["approvals"][1] = self.approval(
            "control_qualification", gov.digest(doc["content"]),
            doc["content"]["evidence_sha256"], 0,
        )
        variants.append(("duplicate reviewer", duplicate_reviewer, evidence, None))
        duplicate_id = json.loads(json.dumps(doc))
        duplicate_id["approvals"][1] = self.approval(
            "control_qualification", gov.digest(doc["content"]),
            doc["content"]["evidence_sha256"], 1,
            approval_id=duplicate_id["approvals"][0]["approval_id"],
        )
        variants.append(("duplicate approval id", duplicate_id, evidence, None))
        for label, envelope, proof, trust in variants:
            with self.subTest(label=label):
                self.assertEqual(gov.verify_signed_control_qualification(envelope, proof, trust or self.trust, NOW)["status"], "FAIL")
        self.assertEqual(gov.verify_signed_control_qualification(doc, b"altered evidence", self.trust, NOW)["status"], "FAIL")

    def reference_approval_bundle(self):
        ref_root = self.root / "refs"
        ref_root.mkdir(exist_ok=True)
        ref_bytes = b">SYNTHREF-00000001\nCCCCCCCC\n"
        (ref_root / "panel.fa").write_bytes(ref_bytes)
        ref_sha = hashlib.sha256(ref_bytes).hexdigest()
        base = {
            "schema_version": readiness.REFERENCE_SCHEMA_VERSION,
            "snapshot_id": "REF-SYNTH00001",
            "references": [{"source": "synthetic", "accession_version": "SYNTH.1",
                            "path": "panel.fa", "bytes": len(ref_bytes), "sha256": ref_sha}],
            "target_exclusion_policy_id": "POL-SYNTH00001",
        }
        panel_binding = readiness._reference_panel_binding_digest(base)
        panel_approval = self.approval("reference_panel", panel_binding,
                                      hashlib.sha256(b"panel-review").hexdigest(),
                                      0, dataset=base["snapshot_id"], sample=base["snapshot_id"])
        manifest = {**base, "approval": panel_approval}
        policy = {
            "schema_version": exclusion.POLICY_VERSION, "policy_id": "EXCL-SYNTH00001",
            "min_query_coverage": 0.5, "min_identity": 0.8,
            "max_sequence_length": 1000, "max_total_bases": 1000,
            "max_panel_bytes": 10000, "max_references": 10,
            "max_alignment_cells": 10000,
            "excluded_sequences": [{"sequence_id": "SYNTH-00000001", "sequence": "AAAA",
                                    "sha256": hashlib.sha256(b"AAAA").hexdigest()}],
        }
        policy_sha = exclusion.exclusion_policy_digest(policy)
        result = exclusion.validate_reference_exclusions(
            ref_root / "panel.fa", policy, expected_policy_sha256=policy_sha,
            expected_reference_sha256=ref_sha,
        )
        review_bytes = b"synthetic scientific threshold assessment"
        review = {
            "policy_version": policy["schema_version"],
            "min_identity": policy["min_identity"], "min_query_coverage": policy["min_query_coverage"],
            "alignment_model": "bounded semiglobal substring DP; substitutions and gaps",
            "sequence_completeness_assumptions": "Synthetic fixture bytes are complete.",
            "reference_panel_exclusion_scope": "Local panel FASTA only.",
            "known_false_exclusion_risks": ["Conserved short motifs can over-exclude."],
            "known_missed_exclusion_risks": ["Thresholds do not establish relatedness."],
            "reviewer_evidence_sha256": hashlib.sha256(review_bytes).hexdigest(),
            "decision": "APPROVED", "limitations": ["Synthetic evidence only."],
            "expires_at": "2027-01-01T00:00:00Z",
            "policy_sha256": policy_sha, "reference_sha256": ref_sha,
        }
        panel_digest = readiness._reference_panel_binding_digest(manifest)
        policy_binding = gov.digest({
            "policy_sha256": policy_sha, "reference_panel_manifest_sha256": panel_digest,
            "reference_sha256": ref_sha, "exclusion_evidence_sha256": result["evidence_sha256"],
        })
        policy_approvals = [self.approval(
            "reference_exclusion_policy", policy_binding, policy_sha, i,
            dataset=manifest["snapshot_id"], sample=manifest["snapshot_id"],
        ) for i in range(2)]
        science_binding = gov.digest(review)
        science_approvals = [self.approval(
            "scientific_review", science_binding, review["reviewer_evidence_sha256"], i,
            dataset=manifest["snapshot_id"], sample=manifest["snapshot_id"],
        ) for i in range(2)]
        return policy, manifest, ref_root, result, review, policy_approvals, science_approvals, review_bytes

    def reference_input(self):
        args = self.reference_approval_bundle()
        names = ("policy", "reference_manifest", "reference_root", "exclusion_result",
                 "scientific_review", "policy_approvals", "scientific_approvals",
                 "scientific_evidence_bytes")
        evidence = dict(zip(names, args))
        verified = gov.verify_reference_governance(*args, self.trust, NOW)
        self.assertEqual(verified["status"], "PASS", verified.get("issues"))
        return evidence, verified

    def test_reference_policy_panel_and_science_approvals_bind_exact_inputs(self):
        args = self.reference_approval_bundle()
        result = gov.verify_reference_governance(*args[:7], args[7], self.trust, NOW)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["policy_sha256"], exclusion.exclusion_policy_digest(args[0]))
        fabricated = list(args)
        fabricated[3] = dict(args[3], results=[dict(args[3]["results"][0], decision="REJECT")])
        self.assertEqual(gov.verify_reference_governance(
            *fabricated[:7], fabricated[7], self.trust, NOW)["status"], "FAIL")
        changed_policy = dict(args[0], min_identity=0.99)
        self.assertEqual(gov.verify_reference_governance(
            changed_policy, args[1], *args[2:7], args[7], self.trust, NOW)["status"], "FAIL")
        args[2].joinpath("panel.fa").write_bytes(b">SYNTHREF-00000001\nGGGGGGGG\n")
        self.assertEqual(gov.verify_reference_governance(*args[:7], args[7], self.trust, NOW)["status"], "FAIL")

    def test_phase6_trust_scopes_extend_phase4_only_for_phase6_loader(self):
        trust_path = self.root / "trust.json"
        trust_path.write_text(json.dumps({
            "schema_version": "m21-reviewer-trust-store-v1",
            "reviewers": [next(iter(self.trust.values()))],
        }))
        with self.assertRaises(ValueError):
            readiness._load_trust_store(trust_path)
        self.assertEqual(len(gov.load_phase6_trust_store(trust_path)), 1)

    def test_reference_incomplete_scientific_evidence_and_expiry_fail(self):
        args = self.reference_approval_bundle()
        args[3]["status"] = "INCOMPLETE"
        self.assertEqual(gov.verify_reference_governance(*args[:7], args[7], self.trust, NOW)["status"], "FAIL")
        args = self.reference_approval_bundle()
        self.assertEqual(gov.verify_reference_governance(*args[:7], b"changed", self.trust, NOW)["status"], "FAIL")
        args = list(self.reference_approval_bundle())
        args[4] = dict(args[4], expires_at="2026-10-20T00:00:00Z")
        self.assertEqual(gov.verify_reference_governance(*args[:7], args[7], self.trust, NOW)["status"], "FAIL")

    def analysis_truth(self):
        sample_rows = [{"sample_id": SAMPLE, "candidates": [{"candidate_id": "cand-A"}],
                        "read_count": 10, "read_unit": "READS"}]
        analysis = {"samples": sample_rows, "analysis_sha256": scoring.canonical_sha256(sample_rows)}
        truth = {"analysis_sha256": analysis["analysis_sha256"],
                 "truth_records": [{"sample_id": SAMPLE, "label": "POSITIVE",
                                    "truth_candidate_ids": ["cand-A"]}]}
        analysis_path = self.root / "analysis.json"
        truth_path = self.root / "truth.json"
        analysis_path.write_text(json.dumps(analysis, separators=(",", ":")))
        truth_bytes = json.dumps(truth, separators=(",", ":")).encode()
        truth_path.write_bytes(truth_bytes)
        return analysis, truth, analysis_path, truth_path, hashlib.sha256(truth_bytes).hexdigest()

    def signed_unblinding(self, analysis, truth_digest, reference_digest, qualifications, *, policy_sha=None):
        policy_sha = policy_sha or scoring.scoring_policy_digest()
        context = gov.unblinding_context(
            analysis["analysis_sha256"], truth_digest, policy_sha, reference_digest,
            [item["qualification_sha256"] for item in qualifications],
        )
        binding = gov.digest(context)
        return [self.approval("unblinding", binding, truth_digest, i, sample=gov.AGGREGATE_SAMPLE)
                for i in range(2)]

    def test_unblinding_entry_point_authenticates_before_truth_and_scores_synthetic_only(self):
        analysis, truth, ap, tp, truth_digest = self.analysis_truth()
        qual, evidence = self.control()
        verified = gov.verify_signed_control_qualification(qual, evidence, self.trust, NOW)
        qualifications = [verified["scoring_qualification"]]
        reference, reference_verified = self.reference_input()
        approvals = self.signed_unblinding(analysis, truth_digest, reference_verified["evidence_sha256"], qualifications)
        result = gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], reference, approvals,
                                               self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
        self.assertEqual(result["governance"]["unblinding_authorization"], "PASS")
        self.assertEqual(result["sample_level"]["confusion_matrix"]["TP"], 1)
        self.assertEqual(result["candidate_level"]["true_positives"], 1)
        self.assertEqual(result["candidate_level"]["precision"]["value"], 1.0)
        self.assertEqual(result["candidate_level"]["recall"]["value"], 1.0)

        denied = gov.evaluate_synthetic_bundle(ap, self.root / "truth-does-not-exist.json",
                                               [(qual, evidence)], reference, [],
                                               self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)
        self.assertEqual(denied["status"], "FAIL")
        self.assertTrue(any("approval" in issue.lower() for issue in denied["issues"]))

    def test_unblinding_requires_independent_binding_to_analysis_truth_and_policy(self):
        analysis, _, ap, tp, truth_digest = self.analysis_truth()
        qual, evidence = self.control()
        record = gov.verify_signed_control_qualification(qual, evidence, self.trust, NOW)["scoring_qualification"]
        reference, ref = self.reference_input()
        valid = self.signed_unblinding(analysis, truth_digest, ref["evidence_sha256"], [record])
        single = gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], reference, valid[:1],
                                               self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)
        self.assertEqual(single["status"], "FAIL")
        stale_policy = self.signed_unblinding(analysis, truth_digest, ref["evidence_sha256"], [record], policy_sha="0" * 64)
        self.assertEqual(gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], reference, stale_policy,
                                                       self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)["status"], "FAIL")
        expired = [self.approval("unblinding", gov.digest(gov.unblinding_context(
            analysis["analysis_sha256"], truth_digest, scoring.scoring_policy_digest(),
            ref["evidence_sha256"], [record["qualification_sha256"]],
        )), truth_digest, 0, expires="2026-10-20T00:00:00Z", sample=gov.AGGREGATE_SAMPLE), valid[1]]
        self.assertEqual(gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], reference, expired,
                                                       self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)["status"], "FAIL")
        revoked_trust = copy.deepcopy(self.trust)
        revoked_trust[valid[0]["reviewer_id"]]["revoked"] = True
        self.assertEqual(gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], reference, valid,
                                                       revoked_trust, expected_truth_bundle_sha256=truth_digest, now=NOW)["status"], "FAIL")
        tp.write_text("{}")
        self.assertEqual(gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], reference, valid,
                                                       self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)["status"], "FAIL")
        analysis["samples"][0]["read_count"] = 999
        ap.write_text(json.dumps(analysis))
        self.assertEqual(gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], reference, valid,
                                                       self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)["status"], "FAIL")

    def test_audit_chain_detects_alteration_removal_reordering_and_duplicate_ids(self):
        one = gov.make_audit_event("EVT-1", "QUALIFIED", "2026-10-21T10:00:00Z",
                                   {"qualification": "a" * 64}, "synthetic-operator", "PASS", None)
        two = gov.make_audit_event("EVT-2", "REFERENCE_APPROVED", "2026-10-21T10:01:00Z",
                                   {"reference": "b" * 64}, "synthetic-reviewer", "PASS", one["event_sha256"])
        chain = [one, two]
        self.assertEqual(gov.verify_audit_chain(chain)["status"], "PASS")
        self.assertEqual(gov.verify_audit_chain(chain)["anchor_status"], "UNANCHORED")
        self.assertEqual(gov.verify_audit_chain([two, one])["status"], "FAIL")
        self.assertEqual(gov.verify_audit_chain([two])["status"], "FAIL")
        tampered = [dict(one), dict(two)]
        tampered[0]["identity"] = "changed"
        self.assertEqual(gov.verify_audit_chain(tampered)["status"], "FAIL")
        self.assertEqual(gov.verify_audit_chain([one, dict(one)])["status"], "FAIL")
        appended = gov.append_audit_event(chain, "EVT-3", "ANALYSIS_VERIFIED",
                                          "2026-10-21T10:02:00Z", {"analysis": "c" * 64},
                                          None, "PASS")
        self.assertEqual(len(appended), 3)

    def test_signed_checkpoint_and_state_machine_fail_closed(self):
        event = gov.make_audit_event("EVT-1", "QUALIFIED", "2026-10-21T10:00:00Z",
                                     {"qualification": "a" * 64}, None, "PASS", None)
        head = event["event_sha256"]
        binding = gov.digest({"event_count": 1, "event_sha256": head})
        approval = self.approval("custody_checkpoint", binding, head, 0,
                                 sample=gov.AGGREGATE_SAMPLE)
        checkpoint = {"event_count": 1, "event_sha256": head, "approval": approval}
        result = gov.verify_audit_chain([event], checkpoint, self.trust, NOW)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["anchor_status"], "VERIFIED")
        stale = {**checkpoint, "event_count": 2}
        self.assertEqual(gov.verify_audit_chain([event], stale, self.trust, NOW)["status"], "FAIL")
        self.assertEqual(gov.advance_governance_state("PREPARED", "REFERENCE_APPROVED", "PASS")["status"], "FAIL")
        self.assertEqual(gov.advance_governance_state("PREPARED", "QUALIFIED", "PENDING")["status"], "FAIL")
        state = "PREPARED"
        for next_state in gov.STATES[1:]:
            outcome = gov.advance_governance_state(state, next_state, "PASS")
            self.assertEqual(outcome["status"], "PASS")
            self.assertFalse(outcome["biological_execution_authorized"])
            state = outcome["state"]
        blocked = gov.governance_readiness({}, result)
        self.assertEqual(blocked["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
        self.assertFalse(blocked["biological_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
