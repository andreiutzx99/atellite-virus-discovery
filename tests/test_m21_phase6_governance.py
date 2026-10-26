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
from satellite_discovery import m21_phase7_evidence as phase7
from satellite_discovery import m21_reference_exclusion as exclusion
from satellite_discovery import m21_scientific_scoring as scoring


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
DS = "DS-SYNTH00001"
SAMPLE = "BLD-0123456789ABCDEF01234567"


def synthetic_ci_run(cases, run_id="39966979127"):
    return {
        "repository": "andreiutzx99/atellite-virus-discovery",
        "workflow": ".github/workflows/tests.yml",
        "workflow_ref": "andreiutzx99/atellite-virus-discovery/.github/workflows/tests.yml@refs/pull/85/merge",
        "run_id": run_id, "run_attempt": 1,
        "run_sha": "a" * 40, "tested_commit_sha": "b" * 40,
        "event_name": "pull_request", "conclusion": "success",
        "matrix_results_sha256": gov.digest(cases),
        "attestation_bundle_sha256": "c" * 64,
    }


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

    def test_signed_scope_projection_authorizes_canonical_gate_role(self):
        scope = "control_qualification"
        reviewer = self.people[scope][0]
        record = dict(self.trust[reviewer], role=[scope])
        approval = self.approval(
            scope, gov.digest({"fixture": "binding"}),
            gov.digest({"fixture": "evidence"}),
        )
        issues = readiness._check_approval(
            DS, SAMPLE, scope, approval, {reviewer: record}, NOW,
        )
        self.assertEqual(issues, [])

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
                inclusion="INCLUDE", sample=SAMPLE, control_id="CTL-SYNTH00001",
                sample_ids=None, study_id="STUDY-SYNTH-01",
                replicate_group="BIO-SYNTH-01"):
        evidence = f"synthetic qualification evidence {control_id}".encode()
        sample_ids = sample_ids or [sample]
        phase4_class = "SCREEN_NEGATIVE" if control_class == "NEGATIVE" else "POSITIVE"
        p4 = {
            "schema_version": "m21-control-qualification-v1",
            "control_id": control_id, "control_class": phase4_class,
            "evidence_strength": "HIGH", "helper_status": "NOT_APPLICABLE",
            "sequence_completeness": "TERMINAL_VERIFIED", "study_group": "WITHIN_STUDY",
            "sensitivity_status": "ADEQUATE", "specificity_status": "ADEQUATE",
            "evaluation_status": eval_status, "denominator_inclusion": inclusion,
            "candidate_level_fp_reviewed": True, "sample_level_fp_reviewed": True,
        }
        content = {
            "phase4_qualification": p4, "control_id": p4["control_id"],
            "sample_ids": sample_ids, "control_class": control_class,
            "evaluation_status": eval_status,
            "scoring_eligibility": eval_status == "EVALUABLE" and inclusion == "INCLUDE",
            "exclusion_reason": None if inclusion == "INCLUDE" and eval_status == "EVALUABLE" else "PENDING_EVIDENCE",
            "study_id": study_id, "replicate_group": replicate_group,
            "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
        }
        binding = gov.digest(content)
        approvals = [self.approval(
            "control_qualification", binding, content["evidence_sha256"], i,
            sample=sample_ids[0],
        )
                     for i in range(2)]
        return {"content": content, "approvals": approvals}, evidence

    def resign_control(self, document):
        content = document["content"]
        binding = gov.digest(content)
        evidence_sha = content["evidence_sha256"]
        document["approvals"] = [
            self.approval("control_qualification", binding, evidence_sha, i,
                          sample=content["sample_ids"][0])
            for i in range(2)
        ]

    def test_phase6_rejects_ineligible_scientific_evidence_and_class_conflicts(self):
        positive, evidence = self.control()
        positive["content"]["phase4_qualification"]["evidence_strength"] = "LIMITED"
        self.resign_control(positive)
        result = gov.verify_signed_control_qualification(positive, evidence, self.trust, NOW)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("HIGH or MODERATE" in issue for issue in result["issues"]))

        negative, evidence = self.control()
        negative["content"]["phase4_qualification"].update(
            control_class="SCREEN_NEGATIVE", sensitivity_status="UNKNOWN"
        )
        negative["content"]["control_class"] = "NEGATIVE"
        self.resign_control(negative)
        result = gov.verify_signed_control_qualification(negative, evidence, self.trust, NOW)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("ADEQUATE screening sensitivity" in issue for issue in result["issues"]))

        conflicting, evidence = self.control()
        conflicting["content"]["control_class"] = "NEGATIVE"
        self.resign_control(conflicting)
        result = gov.verify_signed_control_qualification(conflicting, evidence, self.trust, NOW)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("conflicts with the signed Phase 4" in issue for issue in result["issues"]))

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

    def signed_unblinding(self, analysis, truth_digest, reference_governance, qualifications, *, policy_sha=None):
        policy_sha = policy_sha or scoring.scoring_policy_digest()
        context = gov.unblinding_context(
            analysis["analysis_sha256"], truth_digest, policy_sha, reference_governance,
            [item["qualification_sha256"] for item in qualifications],
        )
        binding = gov.digest(context)
        return [self.approval("unblinding", binding, truth_digest, i, sample=gov.AGGREGATE_SAMPLE)
                for i in range(2)]

    def signed_transition_receipt(self, current, requested, category, artifacts, previous):
        receipt = {
            "current_state": current,
            "requested_state": requested,
            "evidence_category": category,
            "verified_artifact_digests": artifacts,
            "verification_result": "PASS",
            "previous_transition_sha256": previous,
        }
        binding = gov.digest(receipt)
        evidence = gov.digest(artifacts)
        approvals = [
            self.approval("governance_transition", binding, evidence, i,
                          sample=gov.AGGREGATE_SAMPLE)
            for i in range(2)
        ]
        return {"receipt": receipt, "approvals": approvals}

    def test_unblinding_entry_point_authenticates_before_truth_and_scores_synthetic_only(self):
        analysis, truth, ap, tp, truth_digest = self.analysis_truth()
        qual, evidence = self.control()
        verified = gov.verify_signed_control_qualification(qual, evidence, self.trust, NOW)
        qualifications = [verified["scoring_qualification"]]
        reference, reference_verified = self.reference_input()
        approvals = self.signed_unblinding(analysis, truth_digest, reference_verified, qualifications)
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
        valid = self.signed_unblinding(analysis, truth_digest, ref, [record])
        single = gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], reference, valid[:1],
                                               self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)
        self.assertEqual(single["status"], "FAIL")
        stale_policy = self.signed_unblinding(analysis, truth_digest, ref, [record], policy_sha="0" * 64)
        self.assertEqual(gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], reference, stale_policy,
                                                       self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)["status"], "FAIL")
        expired = [self.approval("unblinding", gov.digest(gov.unblinding_context(
            analysis["analysis_sha256"], truth_digest, scoring.scoring_policy_digest(),
            ref, [record["qualification_sha256"]],
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

    def test_unblinding_binds_exact_scientific_and_reference_approval_sets(self):
        analysis, _, ap, tp, truth_digest = self.analysis_truth()
        qual, evidence = self.control()
        record = gov.verify_signed_control_qualification(qual, evidence, self.trust, NOW)["scoring_qualification"]
        reference, verified = self.reference_input()
        authorization = self.signed_unblinding(analysis, truth_digest, verified, [record])

        mutated = copy.deepcopy(reference)
        mutated["scientific_approvals"][0]["expires_at"] = "2026-12-01T00:00:00Z"
        result = gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], mutated, authorization,
                                               self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)
        self.assertEqual(result["status"], "FAIL")

        replacement = copy.deepcopy(reference)
        review = replacement["scientific_review"]
        binding = gov.digest(review)
        replacement["scientific_approvals"] = [
            self.approval(
                "scientific_review", binding, review["reviewer_evidence_sha256"], i,
                dataset=replacement["reference_manifest"]["snapshot_id"],
                sample=replacement["reference_manifest"]["snapshot_id"],
            )
            for i in range(2)
        ]
        result = gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], replacement, authorization,
                                               self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)
        self.assertEqual(result["status"], "FAIL")

        replacement = copy.deepcopy(reference)
        replacement["policy_approvals"] = [
            self.approval(
                "reference_exclusion_policy", verified["binding_sha256"],
                verified["policy_sha256"], i,
                dataset=replacement["reference_manifest"]["snapshot_id"],
                sample=replacement["reference_manifest"]["snapshot_id"],
            )
            for i in range(2)
        ]
        result = gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], replacement, authorization,
                                               self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)
        self.assertEqual(result["status"], "FAIL")

        expired = copy.deepcopy(reference)
        expired["scientific_approvals"] = [
            self.approval(
                "scientific_review", binding, review["reviewer_evidence_sha256"], i,
                expires="2026-10-20T00:00:00Z",
                dataset=expired["reference_manifest"]["snapshot_id"],
                sample=expired["reference_manifest"]["snapshot_id"],
            )
            for i in range(2)
        ]
        result = gov.evaluate_synthetic_bundle(ap, tp, [(qual, evidence)], expired, authorization,
                                               self.trust, expected_truth_bundle_sha256=truth_digest, now=NOW)
        self.assertEqual(result["status"], "FAIL")

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
        self.assertEqual(gov.advance_governance_state("PREPARED", "QUALIFIED", "PASS")["status"],
                         "NON_AUTHORITATIVE")

        chain = []
        verified = gov.verify_governance_transitions(chain, self.trust, NOW)
        for current, requested in zip(gov.STATES, gov.STATES[1:]):
            category = gov.TRANSITION_EVIDENCE_CATEGORIES[requested]
            chain.append(self.signed_transition_receipt(
                current, requested, category, {"stage_evidence": gov.digest(requested)},
                verified["transition_sha256"],
            ))
            verified = gov.verify_governance_transitions(chain, self.trust, NOW)
            self.assertEqual(verified["status"], "PASS", verified["issues"])
            self.assertFalse(verified["biological_execution_authorized"])
        self.assertEqual(verified["state"], "SYNTHETIC_SCORING_COMPLETE")

        wrong_category = self.signed_transition_receipt(
            "PREPARED", "QUALIFIED", "REFERENCE_GOVERNANCE",
            {"qualification": "a" * 64}, None,
        )
        self.assertEqual(gov.verify_governance_transitions([wrong_category], self.trust, NOW)["status"], "FAIL")
        altered = copy.deepcopy(chain)
        altered[0]["receipt"]["verified_artifact_digests"]["stage_evidence"] = "f" * 64
        self.assertEqual(gov.verify_governance_transitions(altered, self.trust, NOW)["status"], "FAIL")
        self.assertEqual(gov.verify_governance_transitions([chain[1], chain[0]], self.trust, NOW)["status"], "FAIL")
        self.assertEqual(gov.verify_governance_transitions([chain[0], chain[0]], self.trust, NOW)["status"], "FAIL")
        blocked = gov.governance_readiness({}, result)
        self.assertEqual(blocked["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
        self.assertFalse(blocked["biological_execution_authorized"])

    def test_phase7_multi_artifact_panel_is_complete_aggregate_and_snapshot_bound(self):
        policy, manifest, root, _, _, _, _, _ = self.reference_approval_bundle()
        second_bytes = b">SYNTHREF-00000002\nGGGGGGGG\n"
        (root / "panel2.fa").write_bytes(second_bytes)
        base = {key: value for key, value in manifest.items() if key != "approval"}
        base["references"] = [*base["references"], {
            "source": "synthetic", "accession_version": "SYNTH.2", "path": "panel2.fa",
            "bytes": len(second_bytes), "sha256": hashlib.sha256(second_bytes).hexdigest(),
        }]
        binding = readiness._reference_panel_binding_digest(base)
        base["approval"] = self.approval(
            "reference_panel", binding, hashlib.sha256(b"panel-review").hexdigest(),
            dataset=base["snapshot_id"], sample=base["snapshot_id"],
        )
        limits = {"max_artifacts": 2, "max_total_bytes": 10000,
                  "max_total_bases": 1000, "max_references": 10,
                  "max_alignment_cells": 10000}
        result = phase7.verify_multi_artifact_reference_panel(
            base, policy, root, self.trust, limits, NOW,
        )
        self.assertEqual(result["status"], "PASS", result["issues"])
        self.assertEqual(result["artifact_count"], 2)
        self.assertEqual(result["reference_count"], 2)
        self.assertEqual(result["overall_exclusion_status"], "PASS")

        (root / "unapproved.fa").write_text(">SYNTHREF-00000003\nCCCCCCCC\n")
        self.assertEqual(phase7.verify_multi_artifact_reference_panel(
            base, policy, root, self.trust, limits, NOW,
        )["status"], "FAIL")
        (root / "unapproved.fa").unlink()
        (root / "panel2.fa").write_bytes(b">SYNTHREF-00000001\nGGGGGGGG\n")
        rejected = phase7.verify_multi_artifact_reference_panel(
            base, policy, root, self.trust, limits, NOW,
        )
        self.assertEqual(rejected["status"], "FAIL")
        self.assertTrue(any("Conflicting reference identifiers" in x for x in rejected["issues"]))
        (root / "panel2.fa").write_bytes(second_bytes)
        (root / "panel2.fa").unlink()
        self.assertEqual(phase7.verify_multi_artifact_reference_panel(
            base, policy, root, self.trust, limits, NOW,
        )["status"], "FAIL")
        (root / "panel2.fa").write_bytes(b">SYNTHREF-00000002\nTTTTTTTT\n")
        self.assertEqual(phase7.verify_multi_artifact_reference_panel(
            base, policy, root, self.trust, limits, NOW,
        )["status"], "FAIL")
        (root / "panel2.fa").write_bytes(second_bytes)
        constrained = {**limits, "max_total_bytes": 1}
        self.assertEqual(phase7.verify_multi_artifact_reference_panel(
            base, policy, root, self.trust, constrained, NOW,
        )["status"], "FAIL")
        constrained = {**limits, "max_alignment_cells": 1}
        self.assertEqual(phase7.verify_multi_artifact_reference_panel(
            base, policy, root, self.trust, constrained, NOW,
        )["status"], "FAIL")

    def test_phase7_independent_checkpoint_detects_rollback_and_replacement(self):
        chain_id = "CHAIN-SYNTH-01"
        trust_identity = gov.digest(self.trust)
        event = gov.make_audit_event("EVT-1", "QUALIFIED", "2026-10-21T10:00:00Z",
                                     {"qualification": "a" * 64}, None, "PASS", None)
        content = {
            "dataset_id": DS, "chain_id": chain_id, "event_count": 1,
            "event_sha256": event["event_sha256"], "sequence": 1,
            "created_at": "2026-10-21T11:00:00Z",
            "previous_checkpoint_sha256": None, "trust_store_identity": trust_identity,
        }
        approval = self.approval(
            "custody_checkpoint", gov.digest(content), event["event_sha256"], 0,
            dataset=DS, sample=chain_id,
        )
        checkpoint = {**content, "approval": approval}
        valid = phase7.verify_independent_custody(
            [event], [checkpoint], [checkpoint], self.trust, dataset_id=DS,
            chain_id=chain_id, trust_store_identity=trust_identity, now=NOW,
        )
        self.assertEqual(valid["status"], "PASS", valid["issues"])
        self.assertEqual(valid["anchor_status"], "INDEPENDENTLY_ANCHORED")
        self.assertEqual(phase7.verify_independent_custody(
            [event], [checkpoint], [], self.trust, dataset_id=DS,
            chain_id=chain_id, trust_store_identity=trust_identity, now=NOW,
        )["anchor_status"], "UNANCHORED")
        self.assertEqual(phase7.verify_independent_custody(
            [], [checkpoint], [checkpoint], self.trust, dataset_id=DS,
            chain_id=chain_id, trust_store_identity=trust_identity, now=NOW,
        )["status"], "FAIL")
        replacement = gov.make_audit_event("EVT-X", "QUALIFIED", "2026-10-21T10:00:00Z",
                                           {"qualification": "b" * 64}, None, "PASS", None)
        self.assertEqual(phase7.verify_independent_custody(
            [replacement], [checkpoint], [checkpoint], self.trust, dataset_id=DS,
            chain_id=chain_id, trust_store_identity=trust_identity, now=NOW,
        )["status"], "FAIL")

    def test_phase7_custody_allows_valid_suffix_and_rejects_missing_local_history(self):
        chain_id = "CHAIN-SYNTH-02"
        trust_identity = gov.digest(self.trust)
        first = gov.make_audit_event(
            "EVT-A", "QUALIFIED", "2026-10-21T10:00:00Z",
            {"qualification": "a" * 64}, None, "PASS", None,
        )
        content = {
            "dataset_id": DS, "chain_id": chain_id, "event_count": 1,
            "event_sha256": first["event_sha256"], "sequence": 1,
            "created_at": "2026-10-21T11:00:00Z",
            "previous_checkpoint_sha256": None, "trust_store_identity": trust_identity,
        }
        checkpoint = {**content, "approval": self.approval(
            "custody_checkpoint", gov.digest(content), first["event_sha256"], 0,
            dataset=DS, sample=chain_id,
        )}
        suffix = gov.make_audit_event(
            "EVT-B", "REFERENCE_APPROVED", "2026-10-21T12:00:00Z",
            {"reference": "b" * 64}, None, "PASS", first["event_sha256"],
        )
        accepted = phase7.verify_independent_custody(
            [first, suffix], [checkpoint], [checkpoint], self.trust,
            dataset_id=DS, chain_id=chain_id, trust_store_identity=trust_identity, now=NOW,
        )
        self.assertEqual(accepted["status"], "PASS", accepted["issues"])
        self.assertEqual(accepted["last_verified_checkpoint"]["event_count"], 1)
        second_content = {
            "dataset_id": DS, "chain_id": chain_id, "event_count": 2,
            "event_sha256": suffix["event_sha256"], "sequence": 2,
            "created_at": "2026-10-21T13:00:00Z",
            "previous_checkpoint_sha256": gov.digest({
                **content, "approval_set_sha256": gov._approval_set_digest([checkpoint["approval"]])
            }),
            "trust_store_identity": trust_identity,
        }
        second_checkpoint = {**second_content, "approval": self.approval(
            "custody_checkpoint", gov.digest(second_content), suffix["event_sha256"], 1,
            dataset=DS, sample=chain_id,
        )}
        rotated = phase7.verify_independent_custody(
            [first, suffix], [checkpoint, second_checkpoint],
            [checkpoint, second_checkpoint], self.trust, dataset_id=DS,
            chain_id=chain_id, trust_store_identity=trust_identity, now=NOW,
        )
        self.assertEqual(rotated["status"], "PASS", rotated["issues"])
        self.assertEqual(rotated["checkpoint_count"], 2)
        reordered = phase7.verify_independent_custody(
            [first, suffix], [second_checkpoint, checkpoint],
            [second_checkpoint, checkpoint], self.trust, dataset_id=DS,
            chain_id=chain_id, trust_store_identity=trust_identity, now=NOW,
        )
        self.assertEqual(reordered["status"], "FAIL")
        revoked = copy.deepcopy(self.trust)
        revoked[checkpoint["approval"]["reviewer_id"]]["revoked"] = True
        revoked_result = phase7.verify_independent_custody(
            [first, suffix], [checkpoint, second_checkpoint],
            [checkpoint, second_checkpoint], revoked, dataset_id=DS,
            chain_id=chain_id, trust_store_identity=gov.digest(revoked), now=NOW,
        )
        self.assertEqual(revoked_result["status"], "FAIL")
        missing_local = phase7.verify_independent_custody(
            [first], [], [checkpoint], self.trust, dataset_id=DS, chain_id=chain_id,
            trust_store_identity=trust_identity, now=NOW,
        )
        self.assertEqual(missing_local["status"], "FAIL")
        policy_allows_missing = phase7.verify_independent_custody(
            [first], [], [checkpoint], self.trust, dataset_id=DS, chain_id=chain_id,
            trust_store_identity=trust_identity, require_local_checkpoints=False, now=NOW,
        )
        self.assertEqual(policy_allows_missing["status"], "PASS", policy_allows_missing["issues"])
        fabricated = dict(checkpoint, event_sha256="f" * 64)
        self.assertEqual(phase7.verify_independent_custody(
            [first], [fabricated], [fabricated], self.trust, dataset_id=DS,
            chain_id=chain_id, trust_store_identity=trust_identity, now=NOW,
        )["status"], "FAIL")

    def test_phase7_panel_scientific_review_authenticates_inventory_and_limits(self):
        policy, manifest, root, _, _, _, _, _ = self.reference_approval_bundle()
        limits = {"max_artifacts": 1, "max_total_bytes": 10000,
                  "max_total_bases": 1000, "max_references": 10,
                  "max_alignment_cells": 10000}
        panel = phase7.verify_multi_artifact_reference_panel(
            manifest, policy, root, self.trust, limits, NOW,
        )
        self.assertEqual(panel["status"], "PASS", panel["issues"])
        evidence = b"synthetic full-panel review"
        review = {
            "snapshot_id": manifest["snapshot_id"],
            "reference_inventory_sha256": panel["artifact_inventory_sha256"],
            "exclusion_policy_sha256": exclusion.exclusion_policy_digest(policy),
            "aggregate_exclusion_evidence_sha256": panel["aggregate_exclusion_evidence_sha256"],
            "reviewer_evidence_sha256": hashlib.sha256(evidence).hexdigest(),
            "decision": "APPROVED", "expires_at": "2027-01-01T00:00:00Z",
            "limitations": ["Synthetic fixtures only."],
        }
        binding = gov.digest({
            "snapshot_id": manifest["snapshot_id"],
            "reference_inventory_sha256": review["reference_inventory_sha256"],
            "exclusion_policy_sha256": review["exclusion_policy_sha256"],
            "aggregate_exclusion_evidence_sha256": review["aggregate_exclusion_evidence_sha256"],
        })
        policy_approvals = [self.approval(
            "reference_exclusion_policy", binding, review["exclusion_policy_sha256"], i,
            dataset=manifest["snapshot_id"], sample=manifest["snapshot_id"],
        ) for i in range(2)]
        review_sha = gov.digest(review)
        science_approvals = [self.approval(
            "scientific_review", review_sha, review["reviewer_evidence_sha256"], i,
            dataset=manifest["snapshot_id"], sample=manifest["snapshot_id"],
        ) for i in range(2)]
        result = phase7.verify_multi_artifact_scientific_approval(
            manifest, policy, root, limits, review, evidence, policy_approvals,
            science_approvals, self.trust, NOW,
        )
        self.assertEqual(result["status"], "PASS", result["issues"])
        altered = dict(review, reference_inventory_sha256="0" * 64)
        self.assertEqual(phase7.verify_multi_artifact_scientific_approval(
            manifest, policy, root, limits, altered, evidence, policy_approvals,
            science_approvals, self.trust, NOW,
        )["status"], "FAIL")

    def test_phase7_transition_receipts_reopen_each_stage_artifact(self):
        root = self.root / "stage-artifacts"
        root.mkdir()
        receipts, paths = [], {}
        verified = gov.verify_governance_transitions([], self.trust, NOW)
        for current, requested in zip(gov.STATES, gov.STATES[1:]):
            artifacts, stage_paths = {}, {}
            for artifact_type in sorted(phase7.REQUIRED_TRANSITION_ARTIFACTS[requested]):
                content = (b"synthetic evidence bytes" if artifact_type == "qualification_evidence"
                           else json.dumps({"synthetic": True}).encode())
                rel = f"{requested}/{artifact_type}.dat"
                destination = root / rel
                destination.parent.mkdir(exist_ok=True)
                destination.write_bytes(content)
                artifacts[artifact_type] = hashlib.sha256(content).hexdigest()
                stage_paths[artifact_type] = rel
            receipts.append(self.signed_transition_receipt(
                current, requested, gov.TRANSITION_EVIDENCE_CATEGORIES[requested],
                artifacts, verified["transition_sha256"],
            ))
            verified = gov.verify_governance_transitions(receipts, self.trust, NOW)
            paths[requested] = stage_paths
        called = []
        stage_verifiers = {
            category: (lambda *_args: called.append("untrusted PASS") or {"status": "PASS"})
            for category in gov.TRANSITION_EVIDENCE_CATEGORIES.values()
        }
        result = phase7.verify_artifact_backed_transitions(
            receipts, paths, root, self.trust, stage_verifiers, NOW,
        )
        self.assertEqual(result["status"], "FAIL", result["issues"])
        self.assertFalse(called, "Untrusted custom callbacks must not run as authoritative verifiers.")
        self.assertFalse(result["custom_callbacks_authoritative"])
        self.assertEqual(len(result["verified_stages"]), 5)
        self.assertEqual(result["semantic_adapter_status"], "FAIL")
        self.assertTrue(result["issues"])
        (root / paths["QUALIFIED"]["control_qualification"]).write_text("{}")
        changed = phase7.verify_artifact_backed_transitions(
            receipts, paths, root, self.trust, stage_verifiers, NOW,
        )
        self.assertEqual(changed["status"], "FAIL")

    def phase7_complete_synthetic_transition(self):
        root = self.root / "phase7-complete"
        root.mkdir()
        panel_root = root / "refs"
        panel_root.mkdir()
        policy, manifest, source_root, _, _, _, _, _ = self.reference_approval_bundle()
        (panel_root / "panel.fa").write_bytes((source_root / "panel.fa").read_bytes())
        limits = {
            "max_artifacts": 1, "max_total_bytes": 10000, "max_total_bases": 1000,
            "max_references": 1, "max_alignment_cells": 10000,
        }
        panel = phase7.verify_multi_artifact_reference_panel(
            manifest, policy, panel_root, self.trust, limits, NOW,
        )
        self.assertEqual(panel["status"], "PASS", panel["issues"])
        self._phase7_panel_result = panel
        review_bytes = b"synthetic panel-wide scientific review"
        review = {
            "snapshot_id": manifest["snapshot_id"],
            "reference_inventory_sha256": panel["artifact_inventory_sha256"],
            "exclusion_policy_sha256": exclusion.exclusion_policy_digest(policy),
            "aggregate_exclusion_evidence_sha256": panel["aggregate_exclusion_evidence_sha256"],
            "reviewer_evidence_sha256": hashlib.sha256(review_bytes).hexdigest(),
            "decision": "APPROVED", "expires_at": "2027-01-01T00:00:00Z",
            "limitations": ["Synthetic reference fixtures only."],
        }
        policy_binding = gov.digest({
            "snapshot_id": manifest["snapshot_id"],
            "reference_inventory_sha256": panel["artifact_inventory_sha256"],
            "exclusion_policy_sha256": exclusion.exclusion_policy_digest(policy),
            "aggregate_exclusion_evidence_sha256": panel["aggregate_exclusion_evidence_sha256"],
        })
        policy_approvals = [
            self.approval("reference_exclusion_policy", policy_binding,
                          exclusion.exclusion_policy_digest(policy), i,
                          dataset=manifest["snapshot_id"], sample=manifest["snapshot_id"])
            for i in range(2)
        ]
        science_approvals = [
            self.approval("scientific_review", gov.digest(review),
                          review["reviewer_evidence_sha256"], i,
                          dataset=manifest["snapshot_id"], sample=manifest["snapshot_id"])
            for i in range(2)
        ]
        reference_result = phase7.verify_multi_artifact_scientific_approval(
            manifest, policy, panel_root, limits, review, review_bytes,
            policy_approvals, science_approvals, self.trust, NOW,
        )
        self.assertEqual(reference_result["status"], "PASS", reference_result["issues"])
        self._phase7_scientific_result = reference_result

        control, qualification_evidence = self.control()
        qualification_result = gov.verify_signed_control_qualification(
            control, qualification_evidence, self.trust, NOW,
        )
        analysis, truth, _, _, _ = self.analysis_truth()
        truth_artifact = {"benchmark_snapshot_id": DS, "truth_bundle": truth}
        truth_artifact_bytes = json.dumps(
            truth_artifact, sort_keys=True, separators=(",", ":"),
        ).encode()
        truth_digest = hashlib.sha256(truth_artifact_bytes).hexdigest()
        ref_context = {
            **reference_result,
            "evidence_sha256": reference_result["aggregate_exclusion_evidence_sha256"],
            "reference_manifest_sha256": reference_result["reference_inventory_sha256"],
            "policy_sha256": reference_result["exclusion_policy_sha256"],
        }
        context = gov.unblinding_context(
            analysis["analysis_sha256"], truth_digest, scoring.scoring_policy_digest(),
            ref_context, [qualification_result["scoring_qualification"]["qualification_sha256"]],
        )
        unblinding_approvals = [
            self.approval("unblinding", gov.digest(context), truth_digest, i,
                          sample=gov.AGGREGATE_SAMPLE)
            for i in range(2)
        ]
        authorization = gov.verify_unblinding_authorization(
            context, unblinding_approvals, self.trust, NOW,
        )
        self.assertEqual(authorization["status"], "PASS", authorization["issues"])
        exclusion_result = {
            "status": "PASS",
            "evidence_sha256": reference_result["aggregate_exclusion_evidence_sha256"],
            "results": [{"decision": "ACCEPT"}], "issues": [],
        }
        expected_result = scoring.score_synthetic_bundle(
            analysis, truth, [qualification_result["scoring_qualification"]],
            unblinding_authorization={
                "approved": True, "reviewer_ids": authorization["reviewer_ids"],
                "truth_bundle_sha256": scoring.canonical_sha256(truth["truth_records"]),
            },
            expected_policy_sha256=scoring.scoring_policy_digest(),
            reference_exclusion_result=exclusion_result,
            expected_reference_evidence_sha256=exclusion_result["evidence_sha256"],
        )
        qualification_digest = control["content"]["evidence_sha256"]
        qualification_evidence_bundle = json.dumps({
            "items": [{
                "evidence_sha256": qualification_digest,
                "evidence_bytes_base64": base64.b64encode(qualification_evidence).decode(),
            }],
        }, sort_keys=True, separators=(",", ":")).encode()
        payloads = {
            "QUALIFIED": {
                "control_qualification": {
                    "benchmark_snapshot_id": DS,
                    "qualifications": [{
                        "document": control, "evidence_sha256": qualification_digest,
                    }],
                },
                "qualification_evidence": qualification_evidence_bundle,
            },
            "REFERENCE_APPROVED": {
                "reference_panel_manifest": {
                    "benchmark_snapshot_id": DS, "reference_manifest": manifest,
                    "reference_root": "refs",
                },
                "exclusion_policy": policy,
                "aggregate_exclusion": {
                    "aggregate_limits": limits, "policy_approvals": policy_approvals,
                    "scientific_approvals": science_approvals,
                },
                "scientific_review": {
                    "review": review, "evidence_bytes_base64": base64.b64encode(review_bytes).decode(),
                },
            },
            "BLINDED_ANALYSIS_VERIFIED": {
                "blinded_analysis": {
                    "benchmark_snapshot_id": DS,
                    "reference_snapshot_id": manifest["snapshot_id"],
                    "qualification_sha256s": [
                        qualification_result["scoring_qualification"]["qualification_sha256"]
                    ],
                    "analysis": analysis,
                },
            },
            "UNBLINDING_AUTHORISED": {
                "unblinding_authorization": {
                    "benchmark_snapshot_id": DS, "truth_bundle_sha256": truth_digest,
                    "approvals": unblinding_approvals,
                },
            },
            "SYNTHETIC_SCORING_COMPLETE": {
                "synthetic_scoring_result": {"benchmark_snapshot_id": DS, "result": expected_result},
                "truth_bundle": truth_artifact,
            },
        }
        receipts, paths, previous = [], {}, None
        for current, requested in zip(gov.STATES, gov.STATES[1:]):
            paths[requested] = {}
            digests = {}
            for artifact_type, payload in payloads[requested].items():
                if isinstance(payload, bytes):
                    data = payload
                else:
                    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                rel = f"{requested}/{artifact_type}.json"
                destination = root / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                paths[requested][artifact_type] = rel
                digests[artifact_type] = hashlib.sha256(data).hexdigest()
            receipt = self.signed_transition_receipt(
                current, requested, gov.TRANSITION_EVIDENCE_CATEGORIES[requested],
                digests, previous,
            )
            receipts.append(receipt)
            verified = gov.verify_governance_transitions(receipts, self.trust, NOW)
            self.assertEqual(verified["status"], "PASS", verified["issues"])
            previous = verified["transition_sha256"]
        return receipts, paths, root

    def test_phase7_all_canonical_adapters_verify_synthetic_progression(self):
        receipts, paths, root = self.phase7_complete_synthetic_transition()
        result = phase7.verify_artifact_backed_transitions(
            receipts, paths, root, self.trust, now=NOW,
        )
        self.assertEqual(result["status"], "PASS", result["issues"])
        self.assertEqual(result["semantic_adapter_status"], "PASS")
        self.assertEqual(len(result["adapter_results"]), 5)
        self.assertFalse(result["biological_execution_authorized"])
        self.assertEqual(result["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")

    def test_phase7_scoring_handles_multiple_qualified_controls_and_excluded_samples(self):
        positive_samples = [SAMPLE, "BLD-1123456789ABCDEF01234567"]
        negative_sample = "BLD-2123456789ABCDEF01234567"
        excluded_sample = "BLD-3123456789ABCDEF01234567"
        controls = [
            self.control(sample_ids=positive_samples, control_id="CTL-SYNTH00001",
                         replicate_group="BIO-POS-01"),
            self.control(control_class="NEGATIVE", sample=negative_sample,
                         control_id="CTL-SYNTH00002", replicate_group="BIO-NEG-01"),
            self.control(control_class="POSITIVE", eval_status="UNEVALUABLE",
                         inclusion="EXCLUDE", sample=excluded_sample,
                         control_id="CTL-SYNTH00003", replicate_group="BIO-EXC-01"),
        ]
        qualifications = []
        for document, evidence in controls:
            verified = gov.verify_signed_control_qualification(document, evidence, self.trust, NOW)
            self.assertEqual(verified["status"], "PASS", verified.get("issues"))
            qualifications.append(verified["scoring_qualification"])

        rows = [
            {"sample_id": positive_samples[0], "candidates": [], "read_count": 10, "read_unit": "READS"},
            {"sample_id": positive_samples[1], "candidates": [{"candidate_id": "cand-A"}],
             "read_count": 12, "read_unit": "READS"},
            {"sample_id": negative_sample, "candidates": [{"candidate_id": "cand-X"}],
             "read_count": 200, "read_unit": "READS"},
            {"sample_id": excluded_sample, "candidates": [{"candidate_id": "cand-Z"}],
             "read_count": 900, "read_unit": "READS"},
        ]
        analysis = {"samples": rows, "analysis_sha256": scoring.canonical_sha256(rows)}
        truth_records = [
            {"sample_id": positive_samples[0], "label": "POSITIVE", "truth_candidate_ids": ["cand-A"]},
            {"sample_id": positive_samples[1], "label": "POSITIVE", "truth_candidate_ids": ["cand-A"]},
            {"sample_id": negative_sample, "label": "NEGATIVE", "truth_candidate_ids": []},
        ]
        truth = {"analysis_sha256": analysis["analysis_sha256"], "truth_records": truth_records}
        self.assertEqual(scoring.validate_blinded_analysis(analysis), [])
        self.assertNotIn("truth_records", analysis)
        truth_bytes = json.dumps(truth, sort_keys=True, separators=(",", ":")).encode()
        truth_sha = hashlib.sha256(truth_bytes).hexdigest()
        reference_evidence, reference_verified = self.reference_input()
        approvals = self.signed_unblinding(
            analysis, truth_sha, reference_verified, qualifications,
        )
        context = gov.unblinding_context(
            analysis["analysis_sha256"], truth_sha, scoring.scoring_policy_digest(),
            reference_verified, [item["qualification_sha256"] for item in qualifications],
        )
        authorization = gov.verify_unblinding_authorization(
            context, approvals, self.trust, NOW,
        )
        self.assertEqual(authorization["status"], "PASS", authorization["issues"])
        result = scoring.score_synthetic_bundle(
            analysis, truth, qualifications,
            unblinding_authorization={
                "approved": True, "reviewer_ids": authorization["reviewer_ids"],
                "truth_bundle_sha256": scoring.canonical_sha256(truth_records),
            },
            expected_policy_sha256=scoring.scoring_policy_digest(),
            reference_exclusion_result=reference_evidence["exclusion_result"],
            expected_reference_evidence_sha256=reference_evidence["exclusion_result"]["evidence_sha256"],
        )
        self.assertEqual(result["status"], "PASS", result["issues"])
        self.assertEqual(result["sample_level"]["confusion_matrix"], {"TP": 1, "FP": 1, "TN": 0, "FN": 0})
        self.assertEqual(result["candidate_level"]["false_candidate_burden_per_million_reads_or_pairs"]["denominator"], 200)
        self.assertEqual(result["candidate_level"]["false_candidate_burden_per_million_reads_or_pairs"]["value"], 5000)
        self.assertEqual(len(result["excluded_controls"]), 1)
        self.assertEqual(result["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")

    def test_phase7_matrix_attestation_requires_exact_signed_27_case_results(self):
        cases = [{
            "case_id": case, "test_name": "test_" + case,
            "expected": "FAIL", "observed": "FAIL",
        } for case in phase7.PHASE7_ACCEPTANCE_CASES]
        matrix = {
            "schema_version": "m21-phase7-acceptance-matrix-v2",
            "cases": cases, "ci_run": synthetic_ci_run(cases),
        }
        binding = gov.digest(matrix)
        approvals = [
            self.approval("governance_transition", binding,
                          gov.digest({"cases": cases, "ci_run": matrix["ci_run"]}), i,
                          sample=gov.AGGREGATE_SAMPLE)
            for i in range(2)
        ]
        verified = phase7.verify_adversarial_matrix(matrix, approvals, self.trust, NOW)
        self.assertEqual(verified["status"], "PASS", verified.get("issues"))
        self.assertEqual(verified["case_count"], 27)
        self.assertEqual(
            phase7.phase7_readiness_report(None, None, None, None, verified)["adversarial_matrix_status"],
            "PASS",
        )
        forged = dict(verified, status="PASS")
        self.assertEqual(
            phase7.phase7_readiness_report(None, None, None, None, forged)["adversarial_matrix_status"],
            "INCOMPLETE",
        )
        cloned = type(verified)(verified)
        self.assertEqual(
            phase7.phase7_readiness_report(None, None, None, None, cloned)["adversarial_matrix_status"],
            "INCOMPLETE",
        )
        altered = copy.deepcopy(matrix)
        altered["ci_run"]["run_id"] = "39966979128"
        rejected = phase7.verify_adversarial_matrix(altered, approvals, self.trust, NOW)
        self.assertEqual(rejected["status"], "FAIL")

    def test_phase7_readiness_pass_requires_all_canonical_verified_results(self):
        receipts, paths, root = self.phase7_complete_synthetic_transition()
        transitions = phase7.verify_artifact_backed_transitions(
            receipts, paths, root, self.trust, now=NOW,
        )
        self.assertEqual(transitions["status"], "PASS", transitions["issues"])
        for index in range(2):
            reviewer = f"REV-{10000000 + index:08d}"
            key_id = f"KEY-{1000000000 + index:010d}"
            key = Ed25519PrivateKey.generate()
            public = key.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
            self.private[reviewer] = key
            self.trust[reviewer] = {
                "reviewer_id": reviewer, "key_id": key_id,
                "public_key_ed25519": base64.b64encode(public).decode(),
                "role": "governance_transition", "scopes": ["governance_transition"],
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_until": "2027-01-01T00:00:00Z", "revoked": False,
            }
            self.people["governance_transition"].append(reviewer)
        events = [gov.make_audit_event(
            "EVT-READINESS", "SYNTHETIC_SCORING_COMPLETE", "2026-10-21T10:00:00Z",
            {"transition": transitions["transition_sha256"]}, None, "PASS", None,
        )]
        trust_identity = gov.digest(self.trust)
        checkpoint_content = {
            "dataset_id": DS, "chain_id": "CHAIN-READINESS-01", "event_count": 1,
            "event_sha256": events[0]["event_sha256"], "sequence": 1,
            "created_at": "2026-10-21T11:00:00Z", "previous_checkpoint_sha256": None,
            "trust_store_identity": trust_identity,
        }
        checkpoint = {**checkpoint_content, "approval": self.approval(
            "custody_checkpoint", gov.digest(checkpoint_content),
            events[0]["event_sha256"], 0, dataset=DS, sample="CHAIN-READINESS-01",
        )}
        custody = phase7.verify_independent_custody(
            events, [checkpoint], [checkpoint], self.trust, dataset_id=DS,
            chain_id="CHAIN-READINESS-01", trust_store_identity=trust_identity, now=NOW,
        )
        self.assertEqual(custody["status"], "PASS", custody["issues"])
        cases = [{
            "case_id": case, "test_name": "test_" + case,
            "expected": "FAIL", "observed": "FAIL",
        } for case in phase7.PHASE7_ACCEPTANCE_CASES]
        matrix = {
            "schema_version": "m21-phase7-acceptance-matrix-v2",
            "cases": cases, "ci_run": synthetic_ci_run(cases, "39966973178"),
        }
        binding = gov.digest(matrix)
        matrix_approvals = [
            self.approval(
                "governance_transition", binding,
                gov.digest({"cases": cases, "ci_run": matrix["ci_run"]}), index + 2,
                          sample=gov.AGGREGATE_SAMPLE)
            for index in range(2)
        ]
        matrix_result = phase7.verify_adversarial_matrix(
            matrix, matrix_approvals, self.trust, NOW,
        )
        self.assertEqual(matrix_result["status"], "PASS", matrix_result.get("issues"))
        report = phase7.phase7_readiness_report(
            self._phase7_panel_result, self._phase7_scientific_result,
            custody, transitions, matrix_result,
        )
        self.assertEqual(report["decision"], "PASS", report["evidence_mismatches"])
        self.assertFalse(report["biological_execution_authorized"])
        self.assertEqual(report["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")

    def test_phase7_readiness_report_is_deterministic_and_never_authorizes_execution(self):
        report = phase7.phase7_readiness_report(None, None, None, None)
        self.assertEqual(report["decision"], "INCOMPLETE")
        self.assertEqual(report["overall_state"], "BLOCKED_FOR_BENCHMARK_EXECUTION")
        self.assertFalse(report["biological_execution_authorized"])
        apparently_qualifying = phase7.phase7_readiness_report(
            {"status": "PASS"}, {"status": "PASS"},
            {"status": "PASS", "anchor_status": "INDEPENDENTLY_ANCHORED"},
            {"status": "PASS"},
        )
        self.assertEqual(apparently_qualifying["decision"], "INCOMPLETE")
        self.assertEqual(apparently_qualifying["canonical_stage_adapters_status"], "INCOMPLETE")
        self.assertEqual(apparently_qualifying["adversarial_matrix_status"], "INCOMPLETE")
        no_anchor = phase7.phase7_readiness_report(
            {"status": "PASS"}, {"status": "PASS"},
            {"status": "PASS", "anchor_status": "UNANCHORED"},
            {"status": "PASS"},
        )
        self.assertEqual(no_anchor["decision"], "INCOMPLETE")
        missing_matrix = phase7.phase7_readiness_report(
            {"status": "PASS"}, {"status": "PASS"},
            {"status": "PASS", "anchor_status": "INDEPENDENTLY_ANCHORED"},
            {"status": "PASS"},
        )
        self.assertEqual(missing_matrix["decision"], "INCOMPLETE")
        self.assertEqual(
            report["human_readable"],
            phase7.phase7_readiness_report(None, None, None, None)["human_readable"],
        )


if __name__ == "__main__":
    unittest.main()
