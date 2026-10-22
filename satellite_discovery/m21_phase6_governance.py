"""Authenticated, synthetic-only M21 Phase 6 governance primitives.

This module never retrieves data, creates production credentials, or authorizes
biological execution. Signatures authenticate approvals; they do not establish
scientific validity.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import m21_benchmark_readiness as readiness
from . import m21_reference_exclusion as exclusion
from . import m21_scientific_scoring as scoring

PHASE6_SCOPES = {
    "control_qualification", "reference_exclusion_policy",
    "scientific_review", "unblinding", "custody_checkpoint",
    "governance_transition",
}
STATES = (
    "PREPARED", "QUALIFIED", "REFERENCE_APPROVED",
    "BLINDED_ANALYSIS_VERIFIED", "UNBLINDING_AUTHORISED",
    "SYNTHETIC_SCORING_COMPLETE",
)
AGGREGATE_SAMPLE = "BLD-000000000000000000000000"
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_phase6_trust_store(path: str | Path) -> dict[str, dict[str, Any]]:
    """Reuse Phase 4 Ed25519 verification while allowing Phase 6-specific scopes."""
    return readiness._load_trust_store(path, extra_scopes=PHASE6_SCOPES)


def _approval_set(
    *, dataset_id: str, sample_id: str, scope: str, binding_digest: str,
    evidence_digest: str, approvals: Any, trusted_reviewers: dict[str, dict[str, Any]],
    now: datetime, minimum: int = 2,
) -> dict[str, Any]:
    issues: list[str] = []
    if scope not in PHASE6_SCOPES and scope not in readiness.GATES:
        issues.append("Approval scope is not recognized.")
    if not SHA_RE.fullmatch(str(binding_digest)) or not SHA_RE.fullmatch(str(evidence_digest)):
        issues.append("Approval binding and evidence digests must be SHA-256 values.")
    if not isinstance(approvals, list) or len(approvals) < minimum:
        return {"status": "FAIL", "issues": ["Required independent signed approvals are missing."]}
    reviewers: list[str] = []
    approval_ids: list[str] = []
    for approval in approvals:
        if isinstance(approval, dict):
            reviewers.append(str(approval.get("reviewer_id", "")))
            approval_ids.append(str(approval.get("approval_id", "")))
            if approval.get("evidence_sha256") != evidence_digest:
                issues.append("Approval evidence digest does not match the approved artifact.")
            if approval.get("manifest_sha256") != binding_digest:
                issues.append("Approval is bound to different content.")
            issues.extend(readiness._check_approval(
                dataset_id, sample_id, scope, approval, trusted_reviewers, now, binding_digest,
            ))
        else:
            issues.append("Malformed approval record.")
    if len(set(reviewers)) != len(reviewers):
        issues.append("One reviewer cannot satisfy multiple independent approval requirements.")
    if len(set(approval_ids)) != len(approval_ids):
        issues.append("Duplicate approval identifier.")
    return {"status": "FAIL" if issues else "PASS", "issues": sorted(set(issues)),
            "reviewer_ids": sorted(reviewers), "approval_ids": sorted(approval_ids),
            "binding_sha256": binding_digest, "evidence_sha256": evidence_digest}


def _approval_set_digest(approvals: list[dict[str, Any]]) -> str:
    """Hash the exact authenticated approvals independent of input list order."""
    return digest(sorted(approvals, key=lambda item: item["approval_id"]))


def _phase5_record(content: dict[str, Any], reviewer_ids: list[str]) -> dict[str, Any]:
    source = content["phase4_qualification"]
    control_class = content["control_class"]
    return {
        "control_id": content["control_id"], "sample_ids": content["sample_ids"],
        "control_class": control_class, "evaluation_status": content["evaluation_status"],
        "independently_reviewed": True, "scoring_eligibility": content["scoring_eligibility"],
        "exclusion_reason": content["exclusion_reason"], "study_id": content["study_id"],
        "replicate_group": content["replicate_group"],
        "evidence_strength": source["evidence_strength"],
        "sensitivity_status": source["sensitivity_status"],
        "review_evidence_sha256": content["evidence_sha256"],
        "reviewer_ids": reviewer_ids,
    }


def verify_signed_control_qualification(
    document: Any, evidence_bytes: bytes, trusted_reviewers: dict[str, dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Authenticate Phase 4 qualifications and derive—not trust—Phase 5 review fields."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(document, dict) or set(document) != {"content", "approvals"}:
        return {"status": "FAIL", "issues": ["Signed qualification envelope is malformed."]}
    content, approvals = document["content"], document["approvals"]
    required = {"phase4_qualification", "control_id", "sample_ids", "control_class",
                "evaluation_status", "scoring_eligibility", "exclusion_reason", "study_id",
                "replicate_group", "evidence_sha256"}
    if not isinstance(content, dict) or set(content) != required:
        return {"status": "FAIL", "issues": ["Qualification content has missing or unknown fields."]}
    issues = readiness.validate_control_qualification(content["phase4_qualification"])
    q4 = content["phase4_qualification"]
    if not isinstance(q4, dict):
        return {"status": "FAIL", "issues": sorted(set(issues + ["Phase 4 qualification must be an object."]))}
    if (content["control_id"] != q4.get("control_id")
            or not isinstance(content["sample_ids"], list) or not content["sample_ids"]
            or not all(isinstance(x, str) and scoring.OPAQUE_SAMPLE.fullmatch(x) for x in content["sample_ids"])
            or not isinstance(content["study_id"], str) or not content["study_id"]
            or not isinstance(content["replicate_group"], str) or not content["replicate_group"]):
        issues.append("Qualification content is not bound to its Phase 4 control, samples, study, and group.")
    expected_class = {
        "POSITIVE": "POSITIVE", "SCREEN_NEGATIVE": "NEGATIVE",
        "HELPER_COMPARATOR": ("HELPER_POSITIVE" if q4.get("helper_status") == "POSITIVE"
                             else "HELPER_NEGATIVE" if q4.get("helper_status") == "NEGATIVE" else None),
        "OTHER": None,
    }.get(q4.get("control_class"))
    if content["control_class"] != expected_class:
        issues.append("Phase 5 control class conflicts with the signed Phase 4 qualification.")
    eligible = (
        q4.get("control_class") in {"POSITIVE", "SCREEN_NEGATIVE"}
        and q4.get("evaluation_status") == "EVALUABLE"
        and q4.get("denominator_inclusion") == "INCLUDE"
    )
    if content["scoring_eligibility"] is not eligible:
        issues.append("Scoring eligibility conflicts with signed Phase 4 denominator qualification.")
    if content["evaluation_status"] != q4.get("evaluation_status"):
        issues.append("Evaluation status conflicts with signed Phase 4 qualification.")
    eligible = content["scoring_eligibility"] is True
    if eligible and q4.get("control_class") == "POSITIVE" and q4.get("evidence_strength") not in {"HIGH", "MODERATE"}:
        issues.append("Eligible positive controls require independently reviewed HIGH or MODERATE evidence.")
    if eligible and q4.get("control_class") == "SCREEN_NEGATIVE" and q4.get("sensitivity_status") != "ADEQUATE":
        issues.append("Eligible negative controls require ADEQUATE screening sensitivity.")
    evidence_sha = hashlib.sha256(evidence_bytes).hexdigest() if isinstance(evidence_bytes, bytes) else ""
    if content.get("evidence_sha256") != evidence_sha:
        issues.append("Qualification evidence bytes do not match the declared digest.")
    if issues:
        return {"status": "FAIL", "issues": sorted(set(issues))}
    binding = digest(content)
    approval_result = _approval_set(
        dataset_id="DS-SYNTH00001", sample_id=content["sample_ids"][0],
        scope="control_qualification", binding_digest=binding, evidence_digest=evidence_sha,
        approvals=approvals, trusted_reviewers=trusted_reviewers, now=now,
    )
    if approval_result["status"] != "PASS":
        return {"status": "FAIL", "issues": approval_result["issues"]}
    normalized = _phase5_record(content, approval_result["reviewer_ids"])
    normalized["qualification_sha256"] = scoring.qualification_digest(normalized)
    issues = scoring.validate_qualification(normalized)
    if issues:
        return {"status": "FAIL", "issues": issues}
    return {"status": "PASS", "scoring_qualification": normalized,
            "qualification_content_sha256": binding,
            "approval_ids": approval_result["approval_ids"],
            "reviewer_ids": approval_result["reviewer_ids"]}


SCIENTIFIC_REVIEW_FIELDS = {
    "policy_version", "min_identity", "min_query_coverage", "alignment_model",
    "sequence_completeness_assumptions", "reference_panel_exclusion_scope",
    "known_false_exclusion_risks", "known_missed_exclusion_risks",
    "reviewer_evidence_sha256", "decision", "limitations", "expires_at",
    "policy_sha256", "reference_sha256",
}


def verify_reference_governance(
    policy: Any, reference_manifest: Any, reference_root: str | Path,
    exclusion_result: Any, scientific_review: Any, policy_approvals: Any,
    scientific_approvals: Any, scientific_evidence_bytes: bytes,
    trusted_reviewers: dict[str, dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Bind panel, policy, verification output, and independent scientific review."""
    now = now or datetime.now(timezone.utc)
    issues: list[str] = []
    if not isinstance(policy, dict):
        return {"status": "FAIL", "issues": ["Reference-exclusion policy is malformed."]}
    policy_sha = exclusion.exclusion_policy_digest(policy)
    if not isinstance(exclusion_result, dict) or exclusion_result.get("status") != "PASS":
        issues.append("Reference-exclusion verification is not complete and passing.")
        exclusion_result = {}
    if not SHA_RE.fullmatch(str(exclusion_result.get("evidence_sha256", ""))) or not SHA_RE.fullmatch(str(exclusion_result.get("reference_sha256", ""))):
        issues.append("Reference-exclusion result is missing valid policy-bound evidence digests.")
    panel_issues = readiness.validate_reference_panel(reference_manifest, trusted_reviewers, now, reference_root)
    issues.extend(panel_issues)
    if not isinstance(reference_manifest, dict):
        reference_manifest = {}
    references = reference_manifest.get("references", [])
    ref_sha = exclusion_result.get("reference_sha256")
    if not any(isinstance(item, dict) and item.get("sha256") == ref_sha for item in references):
        issues.append("Exclusion result is not bound to a signed reference-panel byte digest.")
    # Recompute the Phase 5 exclusion result from the signed local panel bytes;
    # never accept a caller-supplied PASS label or fabricated result rows.
    if isinstance(references, list) and len(references) == 1 and not panel_issues:
        reference = references[0]
        try:
            recomputed = exclusion.validate_reference_exclusions(
                Path(reference_root) / reference["path"], policy,
                expected_policy_sha256=policy_sha,
                expected_reference_sha256=reference["sha256"],
            )
            if recomputed != exclusion_result:
                issues.append("Supplied exclusion result does not match recomputation from approved bytes.")
        except (KeyError, TypeError, OSError, ValueError):
            issues.append("Reference-exclusion result could not be recomputed from approved bytes.")
    elif len(references) != 1:
        issues.append("Phase 6 currently requires one signed FASTA artifact per exclusion result.")
    if not isinstance(scientific_review, dict) or set(scientific_review) != SCIENTIFIC_REVIEW_FIELDS:
        issues.append("Scientific-review record is incomplete or contains unknown fields.")
        scientific_review = {}
    else:
        if (scientific_review["policy_version"] != policy.get("schema_version")
                or scientific_review["min_identity"] != policy.get("min_identity")
                or scientific_review["min_query_coverage"] != policy.get("min_query_coverage")
                or scientific_review["policy_sha256"] != policy_sha
                or scientific_review["reference_sha256"] != ref_sha
                or scientific_review["decision"] != "APPROVED"):
            issues.append("Scientific review does not approve the exact policy and panel used.")
        expiry = readiness._parse_time(scientific_review["expires_at"])
        if not expiry or expiry <= now:
            issues.append("Scientific review is expired or has invalid expiry.")
        if not SHA_RE.fullmatch(str(scientific_review["reviewer_evidence_sha256"])):
            issues.append("Scientific-review evidence digest is malformed.")
        if (not isinstance(scientific_evidence_bytes, bytes)
                or hashlib.sha256(scientific_evidence_bytes).hexdigest() != scientific_review["reviewer_evidence_sha256"]):
            issues.append("Scientific-review evidence bytes do not match their digest.")
    if issues:
        return {"status": "FAIL", "issues": sorted(set(issues))}
    panel_sha = readiness._reference_panel_binding_digest(reference_manifest)
    binding = digest({"policy_sha256": policy_sha, "reference_panel_manifest_sha256": panel_sha,
                      "reference_sha256": ref_sha,
                      "exclusion_evidence_sha256": exclusion_result["evidence_sha256"]})
    p = _approval_set(dataset_id=reference_manifest["snapshot_id"],
                      sample_id=reference_manifest["snapshot_id"], scope="reference_exclusion_policy",
                      binding_digest=binding, evidence_digest=policy_sha, approvals=policy_approvals,
                      trusted_reviewers=trusted_reviewers, now=now)
    scientific_binding = digest(scientific_review)
    s = _approval_set(dataset_id=reference_manifest["snapshot_id"],
                      sample_id=reference_manifest["snapshot_id"], scope="scientific_review",
                      binding_digest=scientific_binding,
                      evidence_digest=scientific_review["reviewer_evidence_sha256"],
                      approvals=scientific_approvals, trusted_reviewers=trusted_reviewers, now=now)
    if p["status"] != "PASS" or s["status"] != "PASS":
        return {"status": "FAIL", "issues": sorted(set(p["issues"] + s["issues"]))}
    ids = [reference_manifest["approval"]["approval_id"], *p["approval_ids"], *s["approval_ids"]]
    reviewers = [reference_manifest["approval"]["reviewer_id"], *p["reviewer_ids"], *s["reviewer_ids"]]
    if len(ids) != len(set(ids)):
        return {"status": "FAIL", "issues": ["Approval identifier is reused across reference governance."]}
    if len(reviewers) != len(set(reviewers)):
        return {"status": "FAIL", "issues": ["One reviewer cannot satisfy independent reference approval requirements."]}
    return {"status": "PASS", "policy_sha256": policy_sha, "reference_sha256": ref_sha,
            "reference_manifest_sha256": panel_sha, "evidence_sha256": exclusion_result["evidence_sha256"],
            "binding_sha256": binding, "approval_ids": ids, "reviewer_ids": sorted(set(reviewers)),
            "scientific_review_sha256": scientific_binding,
            "reference_policy_approval_set_sha256": _approval_set_digest(policy_approvals),
            "scientific_review_approval_set_sha256": _approval_set_digest(scientific_approvals)}


def unblinding_context(analysis_sha256: str, truth_bundle_sha256: str,
                       scoring_policy_sha256: str, reference_governance: dict[str, Any],
                       qualification_sha256s: list[str]) -> dict[str, Any]:
    return {"analysis_sha256": analysis_sha256, "truth_bundle_sha256": truth_bundle_sha256,
            "scoring_policy_sha256": scoring_policy_sha256,
            "reference_evidence_sha256": reference_governance["evidence_sha256"],
            "reference_panel_manifest_sha256": reference_governance["reference_manifest_sha256"],
            "reference_exclusion_policy_sha256": reference_governance["policy_sha256"],
            "recomputed_exclusion_evidence_sha256": reference_governance["evidence_sha256"],
            "signed_scientific_review_sha256": reference_governance["scientific_review_sha256"],
            "scientific_review_approval_set_sha256": reference_governance["scientific_review_approval_set_sha256"],
            "reference_policy_approval_set_sha256": reference_governance["reference_policy_approval_set_sha256"],
            "qualification_sha256s": sorted(qualification_sha256s)}


def verify_unblinding_authorization(
    context: dict[str, Any], approvals: Any, trusted_reviewers: dict[str, dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    binding = digest(context)
    return _approval_set(dataset_id="DS-SYNTH00001", sample_id=AGGREGATE_SAMPLE,
                         scope="unblinding", binding_digest=binding,
                         evidence_digest=context.get("truth_bundle_sha256", ""),
                         approvals=approvals, trusted_reviewers=trusted_reviewers, now=now)


def evaluate_synthetic_bundle(
    analysis_path: str | Path, truth_bundle_path: str | Path,
    signed_qualifications: list[tuple[dict[str, Any], bytes]],
    reference_evidence: dict[str, Any], unblinding_approvals: Any,
    trusted_reviewers: dict[str, dict[str, Any]], *,
    expected_truth_bundle_sha256: str, now: datetime | None = None,
) -> dict[str, Any]:
    """Verify all gates before opening truth bytes, then invoke Phase 5 scoring."""
    now = now or datetime.now(timezone.utc)
    try:
        analysis = json.loads(Path(analysis_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "FAIL", "issues": ["Blinded analysis artifact cannot be read."]}
    if not isinstance(analysis, dict) or set(analysis) != {"analysis_sha256", "samples"}:
        return {"status": "FAIL", "issues": ["Blinded analysis artifact has invalid structure."]}
    if analysis.get("analysis_sha256") != scoring.canonical_sha256(analysis.get("samples")):
        return {"status": "FAIL", "issues": ["Blinded analysis digest mismatch."]}
    reference_fields = {
        "policy", "reference_manifest", "reference_root", "exclusion_result",
        "scientific_review", "policy_approvals", "scientific_approvals",
        "scientific_evidence_bytes",
    }
    if not isinstance(reference_evidence, dict) or set(reference_evidence) != reference_fields:
        return {"status": "FAIL", "issues": ["Complete reference-governance evidence is required."]}
    reference_governance = verify_reference_governance(
        reference_evidence["policy"], reference_evidence["reference_manifest"],
        reference_evidence["reference_root"], reference_evidence["exclusion_result"],
        reference_evidence["scientific_review"], reference_evidence["policy_approvals"],
        reference_evidence["scientific_approvals"], reference_evidence["scientific_evidence_bytes"],
        trusted_reviewers, now,
    )
    if reference_governance["status"] != "PASS":
        return {"status": "FAIL", "issues": reference_governance["issues"]}
    verified_controls = []
    seen_approval_ids: set[str] = set()
    for envelope, evidence in signed_qualifications:
        result = verify_signed_control_qualification(envelope, evidence, trusted_reviewers, now)
        if result["status"] != "PASS":
            return {"status": "FAIL", "issues": result["issues"]}
        if seen_approval_ids.intersection(result["approval_ids"]):
            return {"status": "FAIL", "issues": ["Approval identifier is reused across control qualifications."]}
        seen_approval_ids.update(result["approval_ids"])
        verified_controls.append(result["scoring_qualification"])
    expected_policy = scoring.scoring_policy_digest()
    qualification_hashes = sorted(item["qualification_sha256"] for item in verified_controls)
    context = unblinding_context(
        analysis["analysis_sha256"], expected_truth_bundle_sha256, expected_policy,
        reference_governance, qualification_hashes,
    )
    auth = verify_unblinding_authorization(context, unblinding_approvals, trusted_reviewers, now)
    if auth["status"] != "PASS":
        return {"status": "FAIL", "issues": auth["issues"]}
    all_reviewers = [*reference_governance["reviewer_ids"]]
    all_approval_ids = [*reference_governance["approval_ids"]]
    for result in verified_controls:
        all_reviewers.extend(result["reviewer_ids"])
    all_approval_ids.extend(auth["approval_ids"])
    if len(all_reviewers) != len(set(all_reviewers)):
        return {"status": "FAIL", "issues": ["Reviewer identity is reused across independent governance decisions."]}
    if len(all_approval_ids) != len(set(all_approval_ids)):
        return {"status": "FAIL", "issues": ["Approval identifier is reused across governance decisions."]}
    # Deliberately open truth only after all approval checks above have passed.
    try:
        truth_bytes = Path(truth_bundle_path).read_bytes()
    except OSError:
        return {"status": "FAIL", "issues": ["Authorized truth bundle is unavailable."]}
    if hashlib.sha256(truth_bytes).hexdigest() != expected_truth_bundle_sha256:
        return {"status": "FAIL", "issues": ["Sealed truth bundle digest mismatch."]}
    try:
        truth = json.loads(truth_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {"status": "FAIL", "issues": ["Authorized truth bundle is malformed."]}
    phase5_auth = {"approved": True, "reviewer_ids": auth["reviewer_ids"],
                   "truth_bundle_sha256": scoring.canonical_sha256(truth.get("truth_records"))}
    result = scoring.score_synthetic_bundle(
        analysis, truth, verified_controls, unblinding_authorization=phase5_auth,
        expected_policy_sha256=expected_policy, reference_exclusion_result={
            "status": "PASS", "evidence_sha256": reference_governance["evidence_sha256"],
            "results": [{"decision": "ACCEPT"}], "issues": [],
        }, expected_reference_evidence_sha256=reference_governance["evidence_sha256"],
    )
    result["governance"] = {"cryptographic_approvals": "PASS",
                            "control_qualification": "PASS",
                            "reference_exclusion_integrity": "PASS",
                            "scientific_review": "PASS",
                            "blinding_integrity": "PASS",
                            "unblinding_authorization": "PASS",
                            "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION"}
    return result


def make_audit_event(event_id: str, event_type: str, timestamp: str,
                     artifact_digests: dict[str, str], identity: str | None,
                     verification_result: str, previous_event_sha256: str | None) -> dict[str, Any]:
    event = {"event_id": event_id, "event_type": event_type, "timestamp": timestamp,
             "artifact_digests": artifact_digests, "identity": identity,
             "previous_event_sha256": previous_event_sha256,
             "verification_result": verification_result}
    event["event_sha256"] = digest(event)
    return event


def verify_audit_chain(events: Any, checkpoint: Any = None,
                       trusted_reviewers: dict[str, dict[str, Any]] | None = None,
                       now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if not isinstance(events, list):
        return {"status": "FAIL", "issues": ["Audit events must be an array."]}
    issues, ids = [], set()
    previous = None
    last_time = None
    for event in events:
        if not isinstance(event, dict) or set(event) != {
            "event_id", "event_type", "timestamp", "artifact_digests", "identity",
            "previous_event_sha256", "verification_result", "event_sha256",
        }:
            issues.append("Malformed audit event.")
            continue
        if (not isinstance(event["event_id"], str) or not event["event_id"]
                or not isinstance(event["event_type"], str) or not event["event_type"]
                or (event["identity"] is not None and not isinstance(event["identity"], str))
                or not isinstance(event["verification_result"], str)):
            issues.append("Audit event identity, type, or verification state is malformed.")
            continue
        if event["event_id"] in ids:
            issues.append("Duplicate audit event identifier.")
        ids.add(event["event_id"])
        timestamp = readiness._parse_time(event["timestamp"])
        if not timestamp or (last_time is not None and timestamp < last_time):
            issues.append("Audit event timestamps are invalid or reordered.")
        last_time = timestamp
        if event["previous_event_sha256"] != previous:
            issues.append("Audit chain is reordered or an intermediate event was removed.")
        expected = digest({key: value for key, value in event.items() if key != "event_sha256"})
        if event["event_sha256"] != expected:
            issues.append("Audit event content was altered.")
        if not isinstance(event["artifact_digests"], dict) or any(
            not SHA_RE.fullmatch(str(value)) for value in event["artifact_digests"].values()
        ):
            issues.append("Audit event contains malformed artifact digests.")
        previous = event["event_sha256"]
    anchor_status = "UNANCHORED"
    if checkpoint is not None:
        if (not events or not isinstance(checkpoint, dict)
                or set(checkpoint) != {"event_count", "event_sha256", "approval"}):
            issues.append("Checkpoint does not identify a valid non-empty chain.")
        else:
            expected_chain_digest = previous
            checkpoint_binding = digest({"event_count": len(events), "event_sha256": expected_chain_digest})
            if checkpoint.get("event_count") != len(events) or checkpoint.get("event_sha256") != expected_chain_digest:
                issues.append("Custody checkpoint is stale or mismatched.")
            else:
                signed = _approval_set(
                    dataset_id="DS-SYNTH00001", sample_id=AGGREGATE_SAMPLE,
                    scope="custody_checkpoint", binding_digest=checkpoint_binding,
                    evidence_digest=expected_chain_digest,
                    approvals=[checkpoint.get("approval")],
                    trusted_reviewers=trusted_reviewers or {}, now=now, minimum=1,
                )
                issues.extend(signed["issues"])
                if signed["status"] == "PASS":
                    anchor_status = "VERIFIED"
    return {"status": "FAIL" if issues else "PASS", "issues": sorted(set(issues)),
            "event_count": len(events), "chain_head_sha256": previous,
            "anchor_status": anchor_status,
            "custody_limitation": "A local hash chain cannot prevent whole-log deletion, rollback, or replacement without an independently retained anchor."}


TRANSITION_EVIDENCE_CATEGORIES = {
    "QUALIFIED": "CONTROL_QUALIFICATION",
    "REFERENCE_APPROVED": "REFERENCE_GOVERNANCE",
    "BLINDED_ANALYSIS_VERIFIED": "BLINDED_ANALYSIS",
    "UNBLINDING_AUTHORISED": "UNBLINDING_AUTHORIZATION",
    "SYNTHETIC_SCORING_COMPLETE": "SYNTHETIC_SCORING",
}
TRANSITION_RECEIPT_FIELDS = {
    "current_state", "requested_state", "evidence_category",
    "verified_artifact_digests", "verification_result",
    "previous_transition_sha256",
}


def verify_governance_transitions(
    receipts: Any, trusted_reviewers: dict[str, dict[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify a complete signed receipt chain from PREPARED; never trust caller PASS."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(receipts, list):
        return {"status": "FAIL", "state": "PREPARED", "issues": ["Transition receipts must be an array."]}
    state = "PREPARED"
    previous_digest = None
    approval_ids: set[str] = set()
    transitions = []
    issues: list[str] = []
    for envelope in receipts:
        if (not isinstance(envelope, dict) or set(envelope) != {"receipt", "approvals"}
                or not isinstance(envelope.get("receipt"), dict)
                or set(envelope["receipt"]) != TRANSITION_RECEIPT_FIELDS):
            issues.append("Transition receipt envelope is malformed.")
            break
        receipt = envelope["receipt"]
        requested = receipt["requested_state"]
        expected_category = (
            TRANSITION_EVIDENCE_CATEGORIES.get(requested)
            if isinstance(requested, str) else None
        )
        artifacts = receipt["verified_artifact_digests"]
        if (receipt["current_state"] != state or requested not in STATES
                or STATES.index(requested) != STATES.index(state) + 1):
            issues.append("Transition receipt is replayed, reordered, or skips a required stage.")
        if not expected_category or receipt["evidence_category"] != expected_category:
            issues.append("Evidence category cannot authorize the requested state.")
        if receipt["verification_result"] != "PASS":
            issues.append("Transition evidence receipt is not passing.")
        if (not isinstance(artifacts, dict) or not artifacts
                or any(not isinstance(key, str) or not key
                       or not isinstance(value, str) or not SHA_RE.fullmatch(value)
                       for key, value in artifacts.items())):
            issues.append("Transition receipt must bind verified SHA-256 artifact digests.")
        if receipt["previous_transition_sha256"] != previous_digest:
            issues.append("Transition receipt does not extend the verified previous transition.")
        if issues:
            break
        binding = digest(receipt)
        authenticated = _approval_set(
            dataset_id="DS-SYNTH00001", sample_id=AGGREGATE_SAMPLE,
            scope="governance_transition", binding_digest=binding,
            evidence_digest=digest(artifacts), approvals=envelope["approvals"],
            trusted_reviewers=trusted_reviewers, now=now,
        )
        if authenticated["status"] != "PASS":
            issues.extend(authenticated["issues"])
            break
        if approval_ids.intersection(authenticated["approval_ids"]):
            issues.append("Transition approval was replayed in the receipt chain.")
            break
        approval_ids.update(authenticated["approval_ids"])
        transition_digest = digest({
            "receipt": receipt,
            "approval_set_sha256": _approval_set_digest(envelope["approvals"]),
        })
        transitions.append(transition_digest)
        state = requested
        previous_digest = transition_digest
    return {
        "status": "FAIL" if issues else "PASS",
        "state": state,
        "issues": sorted(set(issues)),
        "transition_count": len(transitions),
        "transition_sha256": previous_digest,
        "biological_execution_authorized": False,
    }


def advance_governance_state(current: str, requested: str, evidence_state: str) -> dict[str, Any]:
    """Non-authoritative sequence helper; use verify_governance_transitions for authorization."""
    if current not in STATES or requested not in STATES:
        return {"status": "FAIL", "state": current, "issues": ["Unknown governance state."]}
    index = STATES.index(current)
    if index + 1 >= len(STATES) or STATES[index + 1] != requested:
        return {"status": "FAIL", "state": current, "issues": ["Governance transition skips or reverses a required stage."]}
    if evidence_state != "PASS":
        return {"status": "FAIL", "state": current, "issues": ["Required evidence for the next state is not passing."]}
    return {"status": "NON_AUTHORITATIVE", "state": requested,
            "issues": ["A plain PASS string is not an authenticated evidence receipt."],
            "biological_execution_authorized": False}


def append_audit_event(events: list[dict[str, Any]], event_id: str, event_type: str,
                       timestamp: str, artifact_digests: dict[str, str],
                       identity: str | None, verification_result: str) -> list[dict[str, Any]]:
    """Return a new sequence; refuse append when the existing prefix is invalid."""
    existing = verify_audit_chain(events)
    if existing["status"] != "PASS":
        raise ValueError("Cannot append to an invalid audit chain.")
    if event_id in {event.get("event_id") for event in events}:
        raise ValueError("Audit event identifier already exists.")
    prefix = [dict(event) for event in events]
    prefix.append(make_audit_event(event_id, event_type, timestamp, artifact_digests,
                                   identity, verification_result, existing["chain_head_sha256"]))
    if verify_audit_chain(prefix)["status"] != "PASS":
        raise ValueError("New audit event is malformed or invalid.")
    return prefix


def governance_readiness(categories: dict[str, str], audit: dict[str, Any]) -> dict[str, Any]:
    required = {"cryptographic_approval_verification", "control_qualification",
                "reference_exclusion_integrity", "scientific_review_evidence",
                "blinding_integrity", "unblinding_authorization", "audit_chain_verification",
                "synthetic_scoring_eligibility"}
    valid = {"PASS", "FAIL", "INCOMPLETE", "PENDING"}
    categories = categories if isinstance(categories, dict) else {}
    audit = audit if isinstance(audit, dict) else {}
    result = {key: categories.get(key, "PENDING") for key in sorted(required)}
    result = {key: value if value in valid else "PENDING" for key, value in result.items()}
    result["audit_anchor"] = audit.get("anchor_status", "UNANCHORED")
    return {"categories": result, "software_correctness": result["synthetic_scoring_eligibility"],
            "evidence_integrity": result["reference_exclusion_integrity"],
            "reviewer_authentication": result["cryptographic_approval_verification"],
            "scientific_appropriateness": result["scientific_review_evidence"],
            "dataset_qualification": result["control_qualification"],
            "biological_benchmark_authorization": "BLOCKED",
            "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
            "biological_execution_authorized": False}
