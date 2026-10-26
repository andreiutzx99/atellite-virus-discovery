"""Synthetic-only multi-artifact integrity and independently retained custody.

This module verifies bytes supplied by the caller; it performs no retrieval and
does not authorize biological execution.
"""
from __future__ import annotations

import hashlib
import json
import base64
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import m21_benchmark_readiness as readiness
from . import m21_phase6_governance as phase6
from . import m21_reference_exclusion as exclusion

LIMIT_FIELDS = {"max_artifacts", "max_total_bytes", "max_total_bases",
                "max_references", "max_alignment_cells"}


class _VerifiedPhase7Result(dict):
    """In-process marker for results returned by canonical Phase 7 verifiers."""

    def __init__(self, value: dict[str, Any], token: object | None = None):
        super().__init__(value)
        self._verification_token = token


_VERIFIED_RESULT_TOKEN = object()


def _is_verified_result(value: Any) -> bool:
    return (
        type(value) is _VerifiedPhase7Result
        and value._verification_token is _VERIFIED_RESULT_TOKEN
    )


def _verified_result(value: dict[str, Any]) -> dict[str, Any]:
    return _VerifiedPhase7Result(value, _VERIFIED_RESULT_TOKEN) if value.get("status") == "PASS" else value


PHASE7_ACCEPTANCE_CASES = (
    "missing_qualification_document", "altered_qualification_evidence",
    "missing_reference_manifest", "reference_snapshot_substitution",
    "duplicate_reference_artifact", "excluded_sequence_policy_change",
    "aggregate_budget_exhaustion", "scientific_review_rejection",
    "altered_policy_approval",
    "missing_blinded_analysis", "analysis_digest_substitution",
    "truth_leakage_in_analysis", "qualification_binding_substitution",
    "missing_unblinding_authorization",
    "unblinding_snapshot_substitution", "altered_unblinding_signature",
    "missing_truth_bundle", "scoring_result_tamper",
    "wrong_artifact_type", "artifact_changed_during_verification",
    "receipt_replay", "invalid_intermediate_transition",
    "expired_transition_signer", "revoked_transition_signer",
    "checkpoint_rollback", "checkpoint_missing_local_history",
    "checkpoint_rotation_reordered",
)

CI_RUN_EVIDENCE_FIELDS = {
    "repository", "workflow", "workflow_ref", "run_id", "run_attempt",
    "run_sha", "tested_commit_sha", "event_name", "conclusion",
    "matrix_results_sha256", "attestation_bundle_sha256",
}
GIT_COMMIT_SHA_RE = re.compile(r"[a-f0-9]{40}\Z")


def verify_adversarial_matrix(
    matrix: Any, approvals: Any, trusted_reviewers: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Authenticate exact 27-case synthetic matrix outcomes; reject self-reported PASS."""
    now = now or datetime.now(timezone.utc)
    if (not isinstance(matrix, dict) or set(matrix) != {"schema_version", "cases", "ci_run"}
            or matrix.get("schema_version") != "m21-phase7-acceptance-matrix-v2"
            or not isinstance(matrix.get("cases"), list)):
        return {"status": "FAIL", "issues": ["Adversarial matrix evidence is malformed."]}
    cases = matrix["cases"]
    ci_run = matrix["ci_run"]
    names = []
    issues = []
    for item in cases:
        if (not isinstance(item, dict) or set(item) != {"case_id", "test_name", "expected", "observed"}
                or item.get("expected") != "FAIL" or item.get("observed") != "FAIL"
                or not isinstance(item.get("case_id"), str)
                or item.get("test_name") != "test_" + str(item.get("case_id"))):
            issues.append("Adversarial matrix case is malformed or did not observe its expected rejection.")
            continue
        names.append(item["case_id"])
    if tuple(names) != PHASE7_ACCEPTANCE_CASES:
        issues.append("Adversarial matrix does not contain the exact 27 ordered acceptance cases.")
    if (not isinstance(ci_run, dict) or set(ci_run) != CI_RUN_EVIDENCE_FIELDS
            or ci_run.get("repository") != "andreiutzx99/atellite-virus-discovery"
            or ci_run.get("workflow") != ".github/workflows/tests.yml"
            or not isinstance(ci_run.get("workflow_ref"), str)
            or not ci_run["workflow_ref"].startswith(
                "andreiutzx99/atellite-virus-discovery/.github/workflows/tests.yml@"
            )
            or ci_run["workflow_ref"].split("@", 1)[-1] not in {
                "refs/heads/m21/phase7-evidence-integrity", "refs/pull/85/merge",
            }
            or not isinstance(ci_run.get("run_id"), str)
            or not ci_run["run_id"].isdigit()
            or not isinstance(ci_run.get("run_attempt"), int)
            or isinstance(ci_run.get("run_attempt"), bool) or ci_run["run_attempt"] < 1
            or ci_run.get("event_name") not in {"push", "pull_request"}
            or ci_run.get("conclusion") != "success"
            or any(not isinstance(ci_run.get(key), str) or not GIT_COMMIT_SHA_RE.fullmatch(ci_run[key])
                   for key in ("run_sha", "tested_commit_sha"))
            or any(not isinstance(ci_run.get(key), str) or not phase6.SHA_RE.fullmatch(ci_run[key])
                   for key in ("matrix_results_sha256", "attestation_bundle_sha256"))
            or ci_run.get("matrix_results_sha256") != phase6.digest(cases)):
        issues.append("CI run evidence is incomplete, unsuccessful, mismatched, or unattested.")
    if issues:
        return {"status": "FAIL", "issues": sorted(set(issues))}
    binding = phase6.digest(matrix)
    signed = phase6._approval_set(
        dataset_id=BENCHMARK_SNAPSHOT_ID, sample_id=phase6.AGGREGATE_SAMPLE,
        scope="governance_transition", binding_digest=binding,
        evidence_digest=phase6.digest({"cases": cases, "ci_run": ci_run}), approvals=approvals,
        trusted_reviewers=trusted_reviewers, now=now,
    )
    if signed["status"] != "PASS":
        return {"status": "FAIL", "issues": signed["issues"]}
    return _verified_result({
        "status": "PASS", "issues": [], "case_count": len(cases),
        "matrix_sha256": binding, "approval_ids": signed["approval_ids"],
        "reviewer_ids": signed["reviewer_ids"], "ci_run_sha256": phase6.digest(ci_run),
        "workflow_identity": ci_run["workflow_ref"], "tested_commit_sha": ci_run["tested_commit_sha"],
        "ci_run_id": ci_run["run_id"],
    })


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _file_sha(path: Path) -> tuple[str, int]:
    h, size = hashlib.sha256(), 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            h.update(block)
    return h.hexdigest(), size


def verify_multi_artifact_reference_panel(
    manifest: Any, policy: Any, reference_root: str | Path,
    trusted_reviewers: dict[str, Any], aggregate_limits: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify every signed panel artifact under aggregate resource limits.

    Inventory order is canonicalized by safe relative path. Per-file exclusion
    validation remains Phase 5's implementation, with one shared alignment budget.
    """
    now = now or datetime.now(timezone.utc)
    issues: list[str] = []
    if not isinstance(aggregate_limits, dict) or set(aggregate_limits) != LIMIT_FIELDS:
        return {"status": "FAIL", "issues": ["Aggregate limit profile is malformed."]}
    if any(not isinstance(v, int) or isinstance(v, bool) or v <= 0
           for v in aggregate_limits.values()):
        return {"status": "FAIL", "issues": ["Aggregate limits must be positive integers."]}
    if not isinstance(manifest, dict) or not isinstance(manifest.get("references"), list):
        return {"status": "FAIL", "issues": ["Signed reference inventory is malformed."]}
    if not isinstance(policy, dict):
        return {"status": "FAIL", "issues": ["Exclusion policy is malformed."]}
    policy_limits = {
        "max_total_bytes": policy.get("max_panel_bytes"),
        "max_total_bases": policy.get("max_total_bases"),
        "max_references": policy.get("max_references"),
        "max_alignment_cells": policy.get("max_alignment_cells"),
    }
    if (any(not isinstance(v, int) or isinstance(v, bool) or v <= 0
            for v in policy_limits.values())
            or any(aggregate_limits[k] > policy_limits[k] for k in policy_limits)
            or aggregate_limits["max_artifacts"] > policy_limits["max_references"]
            or aggregate_limits["max_artifacts"] > 100):
        return {"status": "FAIL", "issues": ["Aggregate limits exceed the approved policy ceilings."]}
    refs = manifest["references"]
    if not refs or len(refs) > aggregate_limits["max_artifacts"]:
        return {"status": "INCOMPLETE", "issues": ["Panel artifact-count limit exceeded or inventory empty."]}
    issues.extend(readiness.validate_reference_panel(manifest, trusted_reviewers, now, reference_root))
    if Path(reference_root).is_symlink() or not Path(reference_root).is_dir():
        return {"status": "FAIL", "issues": ["Reference root is missing or unsafe."]}
    root = Path(reference_root).resolve()
    paths: set[str] = set()
    declared_hashes: set[str] = set()
    reference_ids: set[str] = set()
    inventory = []
    total_bytes = total_bases = total_refs = 0
    budget = {"used": 0, "limit": aggregate_limits["max_alignment_cells"]}
    per_artifact = []
    for item in sorted((x for x in refs if isinstance(x, dict)), key=lambda x: str(x.get("path", ""))):
        rel = item.get("path")
        if not isinstance(rel, str) or not rel or rel in paths:
            issues.append("Reference inventory contains a missing or duplicate path.")
            continue
        paths.add(rel)
        if item.get("sha256") in declared_hashes:
            issues.append("Reference inventory contains a duplicate artifact digest.")
        declared_hashes.add(item.get("sha256"))
        path = root / rel
        try:
            path.resolve(strict=True).relative_to(root)
            if path.is_symlink() or not path.is_file():
                raise ValueError("unsafe artifact")
            before_sha, before_bytes = _file_sha(path)
            total_bytes += before_bytes
            parsed = exclusion._fasta(path, policy["max_sequence_length"], aggregate_limits["max_total_bases"])
            ids = {identifier for identifier, _ in parsed}
            if reference_ids.intersection(ids):
                issues.append(f"Conflicting reference identifiers across artifacts: {rel}.")
            reference_ids.update(ids)
            total_bases += sum(len(seq) for _, seq in parsed)
            total_refs += len(parsed)
            if (total_bytes > aggregate_limits["max_total_bytes"]
                    or total_bases > aggregate_limits["max_total_bases"]
                    or total_refs > aggregate_limits["max_references"]):
                issues.append("Aggregate byte, base, or reference limit exceeded.")
                break
            if before_sha != item.get("sha256") or before_bytes != item.get("bytes"):
                issues.append(f"Reference artifact differs from approved snapshot: {rel}.")
            result = exclusion.validate_reference_exclusions(
                path, policy,
                expected_policy_sha256=exclusion.exclusion_policy_digest(policy),
                expected_reference_sha256=item.get("sha256"),
                alignment_budget=budget,
            )
            after_sha, after_bytes = _file_sha(path)
            if (before_sha, before_bytes) != (after_sha, after_bytes):
                issues.append(f"Reference artifact changed during verification: {rel}.")
            if result.get("status") != "PASS":
                issues.append(f"Reference exclusion is not passing for {rel}.")
            per_artifact.append({"path": rel, "sha256": before_sha, "bytes": before_bytes,
                                 "status": result.get("status"), "result": result})
            inventory.append({"path": rel, "sha256": before_sha, "bytes": before_bytes})
        except (OSError, UnicodeError, ValueError, KeyError, OverflowError) as exc:
            issues.append(f"Reference artifact is missing, unsafe, or incomplete: {rel} ({exc}).")
    if total_bytes > aggregate_limits["max_total_bytes"]:
        issues.append("Aggregate panel byte limit exceeded.")
    if total_bases > aggregate_limits["max_total_bases"]:
        issues.append("Aggregate panel base limit exceeded.")
    if total_refs > aggregate_limits["max_references"]:
        issues.append("Aggregate reference-count limit exceeded.")
    if budget["used"] > budget["limit"]:
        issues.append("Aggregate alignment-work limit exceeded.")
    if len(paths) != len(refs):
        issues.append("One or more manifest artifacts were not verified.")
    try:
        actual_files = set()
        for path in root.rglob("*"):
            if path.is_symlink():
                issues.append(f"Symlink in reference artifact directory: {path.relative_to(root).as_posix()}.")
            elif path.is_file():
                actual_files.add(path.relative_to(root).as_posix())
        if actual_files != paths:
            issues.append("Reference artifact directory contains missing or unapproved artifacts.")
    except OSError:
        issues.append("Reference artifact inventory could not be enumerated.")
    artifact_inventory_sha = _sha(_canonical({
        "snapshot_id": manifest.get("snapshot_id"),
        "reference_panel_manifest_sha256": readiness._reference_panel_binding_digest(manifest),
        "artifacts": inventory,
    }))
    aggregate_evidence_sha = _sha(_canonical({
        "inventory_sha256": artifact_inventory_sha,
        "policy_sha256": exclusion.exclusion_policy_digest(policy),
        "aggregate_limits": aggregate_limits,
        "per_artifact_evidence": [
            {"path": x["path"], "result": x["result"]} for x in per_artifact
        ],
    }))
    report = {
        "status": "FAIL" if issues else "PASS", "snapshot_id": manifest.get("snapshot_id"),
        "artifact_count": len(per_artifact), "total_bytes": total_bytes,
        "total_bases": total_bases, "reference_count": total_refs,
        "aggregate_limits": dict(aggregate_limits),
        "alignment_cells_used": budget["used"], "artifact_inventory_sha256": artifact_inventory_sha,
        "aggregate_exclusion_evidence_sha256": aggregate_evidence_sha,
        "artifacts": per_artifact, "issues": sorted(set(issues)),
    }
    report["overall_exclusion_status"] = report["status"]
    return _verified_result(report)


PANEL_REVIEW_FIELDS = {
    "snapshot_id", "reference_inventory_sha256", "exclusion_policy_sha256",
    "aggregate_exclusion_evidence_sha256", "reviewer_evidence_sha256",
    "decision", "expires_at", "limitations",
}


def verify_multi_artifact_scientific_approval(
    manifest: Any, policy: Any, reference_root: str | Path,
    aggregate_limits: Any, scientific_review: Any, scientific_evidence: bytes,
    policy_approvals: Any, scientific_approvals: Any,
    trusted_reviewers: dict[str, Any], now: datetime | None = None,
) -> dict[str, Any]:
    """Recompute the full panel result, then authenticate approvals over that snapshot."""
    now = now or datetime.now(timezone.utc)
    panel = verify_multi_artifact_reference_panel(
        manifest, policy, reference_root, trusted_reviewers, aggregate_limits, now,
    )
    issues = list(panel["issues"])
    if panel["status"] != "PASS":
        return {"status": "FAIL", "issues": issues, "panel": panel}
    if not isinstance(scientific_review, dict) or set(scientific_review) != PANEL_REVIEW_FIELDS:
        return {"status": "FAIL", "issues": ["Panel scientific-review record is malformed."],
                "panel": panel}
    review = scientific_review
    policy_sha = exclusion.exclusion_policy_digest(policy)
    if (review["snapshot_id"] != manifest["snapshot_id"]
            or review["reference_inventory_sha256"] != panel["artifact_inventory_sha256"]
            or review["exclusion_policy_sha256"] != policy_sha
            or review["aggregate_exclusion_evidence_sha256"] != panel["aggregate_exclusion_evidence_sha256"]
            or review["decision"] != "APPROVED"
            or not isinstance(review["limitations"], list) or not review["limitations"]):
        issues.append("Scientific review does not cover the exact approved panel and aggregate result.")
    expiry = readiness._parse_time(review["expires_at"])
    if not expiry or expiry <= now:
        issues.append("Panel scientific review is expired or has invalid expiry.")
    review_evidence_sha = _sha(scientific_evidence) if isinstance(scientific_evidence, bytes) else ""
    if review.get("reviewer_evidence_sha256") != review_evidence_sha:
        issues.append("Panel scientific-review evidence bytes do not match their digest.")
    if issues:
        return {"status": "FAIL", "issues": sorted(set(issues)), "panel": panel}
    policy_binding = phase6.digest({
        "snapshot_id": manifest["snapshot_id"],
        "reference_inventory_sha256": panel["artifact_inventory_sha256"],
        "exclusion_policy_sha256": policy_sha,
        "aggregate_exclusion_evidence_sha256": panel["aggregate_exclusion_evidence_sha256"],
    })
    p = phase6._approval_set(
        dataset_id=manifest["snapshot_id"], sample_id=manifest["snapshot_id"],
        scope="reference_exclusion_policy", binding_digest=policy_binding,
        evidence_digest=policy_sha, approvals=policy_approvals,
        trusted_reviewers=trusted_reviewers, now=now,
    )
    review_sha = phase6.digest(review)
    s = phase6._approval_set(
        dataset_id=manifest["snapshot_id"], sample_id=manifest["snapshot_id"],
        scope="scientific_review", binding_digest=review_sha,
        evidence_digest=review_evidence_sha, approvals=scientific_approvals,
        trusted_reviewers=trusted_reviewers, now=now,
    )
    all_reviewers = [*p.get("reviewer_ids", []), *s.get("reviewer_ids", [])]
    all_ids = [*p.get("approval_ids", []), *s.get("approval_ids", [])]
    if len(all_reviewers) != len(set(all_reviewers)):
        issues.append("A reviewer cannot approve both panel policy and scientific review.")
    if len(all_ids) != len(set(all_ids)):
        issues.append("Approval identifier is reused across panel governance decisions.")
    panel_approval = manifest.get("approval", {})
    if (isinstance(panel_approval, dict)
            and panel_approval.get("reviewer_id") in set(all_reviewers)):
        issues.append("Panel reviewer is reused for policy or scientific approval.")
    if (isinstance(panel_approval, dict)
            and panel_approval.get("approval_id") in set(all_ids)):
        issues.append("Panel approval identifier is reused in later governance decisions.")
    if p["status"] != "PASS" or s["status"] != "PASS":
        issues.extend(p["issues"] + s["issues"])
    if issues:
        return {"status": "FAIL", "issues": sorted(set(issues)), "panel": panel}
    return _verified_result({
        "status": "FAIL" if issues else "PASS", "issues": sorted(set(issues)),
        "snapshot_id": manifest["snapshot_id"],
        "reference_inventory_sha256": panel["artifact_inventory_sha256"],
        "exclusion_policy_sha256": policy_sha,
        "aggregate_exclusion_evidence_sha256": panel["aggregate_exclusion_evidence_sha256"],
        "scientific_review_sha256": review_sha,
        "reference_policy_approval_set_sha256": phase6._approval_set_digest(policy_approvals),
        "scientific_review_approval_set_sha256": phase6._approval_set_digest(scientific_approvals),
        "panel": panel,
    })


CHECKPOINT_FIELDS = {
    "dataset_id", "chain_id", "event_count", "event_sha256", "sequence",
    "created_at", "previous_checkpoint_sha256", "trust_store_identity", "approval",
}


def _checkpoint_content(checkpoint: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in checkpoint.items() if k != "approval"}


def verify_independent_custody(
    events: Any, local_checkpoints: Any, retained_checkpoints: Any,
    trusted_reviewers: dict[str, Any], *, dataset_id: str, chain_id: str,
    trust_store_identity: str, now: datetime | None = None,
    require_local_checkpoints: bool = True,
) -> dict[str, Any]:
    """Compare a local chain with a separately supplied retained checkpoint history.

    `retained_checkpoints` must be obtained out-of-band by the caller. A signature
    or local copy alone is never interpreted as independent retention.
    """
    now = now or datetime.now(timezone.utc)
    if not isinstance(trusted_reviewers, dict) or not isinstance(require_local_checkpoints, bool):
        return {"status": "FAIL", "anchor_status": "UNANCHORED",
                "issues": ["Trusted reviewer store is malformed."]}
    if not isinstance(events, list):
        return {"status": "FAIL", "anchor_status": "UNANCHORED",
                "issues": ["Audit events must be an array."]}
    try:
        actual_trust_identity = phase6.digest(trusted_reviewers)
    except (TypeError, ValueError):
        return {"status": "FAIL", "anchor_status": "UNANCHORED",
                "issues": ["Trusted reviewer store is malformed."]}
    if trust_store_identity != actual_trust_identity:
        return {"status": "FAIL", "anchor_status": "UNANCHORED",
                "issues": ["Trust-store identity does not match the supplied reviewer store."]}
    local_chain = phase6.verify_audit_chain(events, now=now)
    issues = list(local_chain["issues"])
    if not isinstance(local_checkpoints, list) or not isinstance(retained_checkpoints, list):
        return {"status": "FAIL", "anchor_status": "UNANCHORED",
                "issues": ["Checkpoint histories must be arrays."]}
    if not retained_checkpoints:
        if require_local_checkpoints and local_checkpoints:
            issues.append("Local checkpoints cannot establish independent retention without a retained history.")
        return {"status": "FAIL" if issues else "PASS", "anchor_status": "UNANCHORED",
                "local_checkpoint_count": len(local_checkpoints), "last_verified_checkpoint": None,
                "issues": sorted(set(issues)),
                "limitation": "No independently retained checkpoint was supplied; local signatures are not an external anchor."}
    if require_local_checkpoints and not local_checkpoints:
        issues.append("Required local checkpoint history is missing.")
    previous_sha = None
    previous_time = None
    previous_count = 0
    verified = []
    reviewer_ids: list[str] = []
    for checkpoint in retained_checkpoints:
        if not isinstance(checkpoint, dict) or set(checkpoint) != CHECKPOINT_FIELDS:
            issues.append("Malformed retained checkpoint.")
            break
        seq = checkpoint["sequence"]
        created = readiness._parse_time(checkpoint["created_at"])
        content = _checkpoint_content(checkpoint)
        event_count = checkpoint["event_count"]
        if (not isinstance(event_count, int) or isinstance(event_count, bool)
                or event_count <= previous_count or event_count > len(events)
                or not isinstance(checkpoint["event_sha256"], str)
                or not phase6.SHA_RE.fullmatch(checkpoint["event_sha256"])
                or not isinstance(checkpoint["trust_store_identity"], str)):
            issues.append("Checkpoint count, event digest, or trust identity is malformed, stale, or outside the local history.")
            break
        local_event_digest = events[event_count - 1].get("event_sha256") if isinstance(events[event_count - 1], dict) else None
        binding = phase6.digest(content)
        approval = phase6._approval_set(
            dataset_id=dataset_id, sample_id=chain_id, scope="custody_checkpoint",
            binding_digest=binding, evidence_digest=checkpoint["event_sha256"],
            approvals=[checkpoint["approval"]], trusted_reviewers=trusted_reviewers,
            now=now, minimum=1,
        )
        if (checkpoint["dataset_id"] != dataset_id or checkpoint["chain_id"] != chain_id
                or checkpoint["trust_store_identity"] != trust_store_identity
                or not isinstance(seq, int) or isinstance(seq, bool) or seq != len(verified) + 1
                or checkpoint["previous_checkpoint_sha256"] != previous_sha
                or checkpoint["event_sha256"] != local_event_digest
                or not created or (previous_time and created <= previous_time)
                or approval["status"] != "PASS"):
            issues.append("Retained checkpoint history is invalid, reordered, conflicting, expired, revoked, or untrusted.")
            issues.extend(approval["issues"])
            break
        verified.append({**content, "checkpoint_sha256": phase6.digest({
            **content, "approval_set_sha256": phase6._approval_set_digest([checkpoint["approval"]])
        })})
        reviewer_ids.extend(approval["reviewer_id"] for approval in [checkpoint["approval"]])
        previous_sha = verified[-1]["checkpoint_sha256"]
        previous_time = created
        previous_count = event_count
    latest = verified[-1] if verified else None
    if len(verified) != len(retained_checkpoints):
        issues.append("One or more retained checkpoints could not be verified.")
    if latest and local_chain.get("status") == "PASS":
        # A suffix after the latest retained event is legitimate; it must remain
        # part of the locally verified hash chain.
        if local_chain.get("event_count", 0) < latest["event_count"]:
            issues.append("Local audit chain rolled back behind the retained checkpoint.")
    if len(local_checkpoints) != len(verified):
        if require_local_checkpoints or local_checkpoints:
            issues.append("Local checkpoint history is missing, extra, or differs from retained history.")
    else:
        for local, retained in zip(local_checkpoints, retained_checkpoints):
            if not isinstance(local, dict) or set(local) != CHECKPOINT_FIELDS:
                issues.append("Malformed local checkpoint history.")
                break
            if not isinstance(retained, dict) or phase6.digest(local) != phase6.digest(retained):
                issues.append("Local checkpoint history was substituted, reordered, or conflicts with retention.")
                break
    return _verified_result({
        "status": "FAIL" if issues else "PASS",
        "anchor_status": "INDEPENDENTLY_ANCHORED" if latest and not issues else "UNANCHORED",
        "checkpoint_count": len(verified), "last_verified_checkpoint": latest,
        "local_checkpoint_count": len(local_checkpoints), "reviewer_ids": sorted(set(reviewer_ids)),
        "issues": sorted(set(issues)),
        "limitation": "This verifier checks supplied retained bytes and signatures only; the caller must establish their independent source, retention policy, and custody.",
    })


REQUIRED_TRANSITION_ARTIFACTS = {
    "QUALIFIED": {"control_qualification", "qualification_evidence"},
    "REFERENCE_APPROVED": {"reference_panel_manifest", "exclusion_policy",
                           "aggregate_exclusion", "scientific_review"},
    "BLINDED_ANALYSIS_VERIFIED": {"blinded_analysis"},
    "UNBLINDING_AUTHORISED": {"unblinding_authorization"},
    "SYNTHETIC_SCORING_COMPLETE": {"synthetic_scoring_result", "truth_bundle"},
}

BENCHMARK_SNAPSHOT_ID = "DS-SYNTH00001"


def _stage_document(cache: dict[str, dict[str, Any]], state: str, kind: str) -> Any:
    return cache[state].get(kind)


def _safe_stage_directory(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("stage directory must be a non-empty relative path")
    path = root / value
    path.resolve(strict=True).relative_to(root)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("stage directory is missing or unsafe")
    return path


def _safe_stage_file(root: Path, value: Any) -> Path:
    if (not isinstance(value, str) or not value or "\\" in value
            or Path(value).is_absolute() or any(part in {"", ".", ".."} for part in Path(value).parts)):
        raise ValueError("artifact path must be a normalized relative path")
    path = root / value
    path.resolve(strict=True).relative_to(root)
    cursor = root
    for part in Path(value).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError("artifact path contains a symlink")
    if not path.is_file():
        raise ValueError("artifact path is not a regular file")
    return path


def _adapt_qualified(cache: dict[str, dict[str, Any]], context: dict[str, Any],
                     trusted_reviewers: dict[str, Any], now: datetime) -> dict[str, Any]:
    package = _stage_document(cache, "QUALIFIED", "control_qualification")
    evidence_bytes = context["raw"]["QUALIFIED"]["qualification_evidence"]
    try:
        evidence_bundle = json.loads(evidence_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {"status": "FAIL", "issues": ["Qualification evidence bundle is not valid JSON."]}
    if (not isinstance(package, dict) or set(package) != {"benchmark_snapshot_id", "qualifications"}
            or package["benchmark_snapshot_id"] != BENCHMARK_SNAPSHOT_ID):
        return {"status": "FAIL", "issues": ["Qualification package has a missing or conflicting benchmark snapshot."]}
    items = evidence_bundle.get("items") if isinstance(evidence_bundle, dict) else None
    qualifications = package["qualifications"]
    if (not isinstance(items, list) or not items or not isinstance(qualifications, list)
            or not qualifications):
        return {"status": "FAIL", "issues": ["Qualification and evidence bundles must be non-empty arrays."]}
    evidence_by_digest = {}
    issues = []
    for item in items:
        if (not isinstance(item, dict) or set(item) != {"evidence_sha256", "evidence_bytes_base64"}
                or not isinstance(item["evidence_sha256"], str)
                or not phase6.SHA_RE.fullmatch(item["evidence_sha256"])
                or item["evidence_sha256"] in evidence_by_digest):
            issues.append("Qualification evidence bundle contains malformed or duplicate entries.")
            continue
        try:
            evidence_by_digest[item["evidence_sha256"]] = base64.b64decode(
                item["evidence_bytes_base64"], validate=True,
            )
        except (TypeError, ValueError):
            issues.append("Qualification evidence bytes are not valid base64.")
    verified = []
    normalized = []
    control_ids = set()
    approval_ids = set()
    sample_ids = set()
    for item in qualifications:
        if not isinstance(item, dict) or set(item) != {"document", "evidence_sha256"}:
            issues.append("Qualification bundle entry has missing or unknown fields.")
            continue
        evidence = evidence_by_digest.get(item["evidence_sha256"])
        if evidence is None or not isinstance(item["document"], dict):
            issues.append("Qualification evidence is missing for a signed control record.")
            continue
        control_id = item["document"].get("content", {}).get("control_id")
        result = phase6.verify_signed_control_qualification(
            item["document"], evidence, trusted_reviewers, now,
        )
        if result.get("status") != "PASS":
            issues.extend(result.get("issues", ["Signed Phase 4 qualification failed."]))
            continue
        record = result["scoring_qualification"]
        if control_id in control_ids or sample_ids.intersection(record["sample_ids"]):
            issues.append("Qualification bundle reuses a control or sample identifier.")
        control_ids.add(control_id)
        sample_ids.update(record["sample_ids"])
        if approval_ids.intersection(result["approval_ids"]):
            issues.append("Qualification bundle reuses an approval identifier.")
        approval_ids.update(result["approval_ids"])
        verified.append((item["document"], evidence))
        normalized.append(record)
    if set(evidence_by_digest) != {item.get("evidence_sha256") for item in qualifications if isinstance(item, dict)}:
        issues.append("Qualification evidence bundle contains unreferenced evidence.")
    if issues or len(normalized) != len(qualifications):
        return {"status": "FAIL", "issues": sorted(set(issues))}
    context["qualification_documents"] = verified
    context["qualifications"] = normalized
    context["qualification_result"] = {
        "status": "PASS", "approval_ids": sorted(approval_ids),
        "reviewer_ids": sorted({r for record in normalized for r in record["reviewer_ids"]}),
    }
    context["benchmark_snapshot_id"] = package["benchmark_snapshot_id"]
    return {"status": "PASS", "issues": [], "qualification_count": len(normalized),
            "approval_ids": sorted(approval_ids),
            "reviewer_ids": context["qualification_result"]["reviewer_ids"]}


def _adapt_reference_approved(cache: dict[str, dict[str, Any]], context: dict[str, Any],
                              root: Path, trusted_reviewers: dict[str, Any],
                              now: datetime) -> dict[str, Any]:
    package = _stage_document(cache, "REFERENCE_APPROVED", "reference_panel_manifest")
    aggregate = _stage_document(cache, "REFERENCE_APPROVED", "aggregate_exclusion")
    review_package = _stage_document(cache, "REFERENCE_APPROVED", "scientific_review")
    policy = _stage_document(cache, "REFERENCE_APPROVED", "exclusion_policy")
    if (not isinstance(package, dict)
            or set(package) != {"benchmark_snapshot_id", "reference_manifest", "reference_root"}
            or package.get("benchmark_snapshot_id") != context.get("benchmark_snapshot_id")
            or not isinstance(aggregate, dict)
            or set(aggregate) != {"aggregate_limits", "policy_approvals", "scientific_approvals"}
            or not isinstance(review_package, dict)
            or set(review_package) != {"review", "evidence_bytes_base64"}):
        return {"status": "FAIL", "issues": ["Reference-governance typed evidence is incomplete or snapshot-mismatched."]}
    try:
        reference_root = _safe_stage_directory(root, package["reference_root"])
        review_bytes = base64.b64decode(review_package["evidence_bytes_base64"], validate=True)
    except (TypeError, ValueError, OSError) as exc:
        return {"status": "FAIL", "issues": [f"Reference-governance evidence could not be decoded safely ({exc})."]}
    result = verify_multi_artifact_scientific_approval(
        package["reference_manifest"], policy, reference_root,
        aggregate["aggregate_limits"], review_package["review"], review_bytes,
        aggregate["policy_approvals"], aggregate["scientific_approvals"],
        trusted_reviewers, now,
    )
    if result.get("status") == "PASS":
        context["reference_result"] = result
        context["reference_evidence"] = {
            "manifest": package["reference_manifest"], "policy": policy,
            "reference_root": reference_root, "aggregate_limits": aggregate["aggregate_limits"],
            "review": review_package["review"], "review_bytes": review_bytes,
            "policy_approvals": aggregate["policy_approvals"],
            "scientific_approvals": aggregate["scientific_approvals"],
        }
        context["reference_snapshot_id"] = package["reference_manifest"]["snapshot_id"]
    return result


def _analysis_issues(analysis: Any) -> list[str]:
    return phase6.scoring.validate_blinded_analysis(analysis)


def _adapt_blinded_analysis(cache: dict[str, dict[str, Any]], context: dict[str, Any],
                            now: datetime) -> dict[str, Any]:
    package = _stage_document(cache, "BLINDED_ANALYSIS_VERIFIED", "blinded_analysis")
    required = {"benchmark_snapshot_id", "reference_snapshot_id",
                "qualification_sha256s", "analysis"}
    if (not isinstance(package, dict) or set(package) != required
            or package.get("benchmark_snapshot_id") != context.get("benchmark_snapshot_id")
            or package.get("reference_snapshot_id") != context.get("reference_snapshot_id")
            or package.get("qualification_sha256s") != sorted(
                x["qualification_sha256"] for x in context.get("qualifications", []))):
        return {"status": "FAIL", "issues": ["Blinded analysis is not bound to the verified benchmark, reference panel, and qualifications."]}
    issues = _analysis_issues(package["analysis"])
    qualified_samples = {
        sample_id for item in context.get("qualifications", [])
        for sample_id in item["sample_ids"]
    }
    if {row.get("sample_id") for row in package["analysis"].get("samples", []) if isinstance(row, dict)} - qualified_samples:
        issues.append("Blinded analysis contains samples without an authenticated qualification.")
    if issues:
        return {"status": "FAIL", "issues": issues}
    context["analysis"] = package["analysis"]
    context["analysis_sha256"] = package["analysis"]["analysis_sha256"]
    return {"status": "PASS", "issues": [], "analysis_sha256": context["analysis_sha256"]}


def _adapt_unblinding(cache: dict[str, dict[str, Any]], context: dict[str, Any],
                      trusted_reviewers: dict[str, Any], now: datetime) -> dict[str, Any]:
    package = _stage_document(cache, "UNBLINDING_AUTHORISED", "unblinding_authorization")
    if (not isinstance(package, dict)
            or set(package) != {"benchmark_snapshot_id", "truth_bundle_sha256", "approvals"}
            or package.get("benchmark_snapshot_id") != context.get("benchmark_snapshot_id")
            or not isinstance(package.get("truth_bundle_sha256"), str)
            or not phase6.SHA_RE.fullmatch(package["truth_bundle_sha256"])):
        return {"status": "FAIL", "issues": ["Unblinding authorization is malformed or snapshot-mismatched."]}
    reference = context.get("reference_result", {})
    ref_context = {
        **reference,
        "evidence_sha256": reference.get("aggregate_exclusion_evidence_sha256"),
        "reference_manifest_sha256": reference.get("reference_inventory_sha256"),
        "policy_sha256": reference.get("exclusion_policy_sha256"),
    }
    unblind_context = phase6.unblinding_context(
        context["analysis_sha256"], package["truth_bundle_sha256"],
        phase6.scoring.scoring_policy_digest(), ref_context,
        [item["qualification_sha256"] for item in context["qualifications"]],
    )
    result = phase6.verify_unblinding_authorization(
        unblind_context, package["approvals"], trusted_reviewers, now,
    )
    if result.get("status") == "PASS":
        context["unblinding_context"] = unblind_context
        context["unblinding_approvals"] = package["approvals"]
        context["truth_bundle_sha256"] = package["truth_bundle_sha256"]
        context["unblinding_result"] = result
    return result


def _adapt_synthetic_scoring(cache: dict[str, dict[str, Any]], context: dict[str, Any],
                             now: datetime) -> dict[str, Any]:
    scoring_package = _stage_document(cache, "SYNTHETIC_SCORING_COMPLETE", "synthetic_scoring_result")
    truth_package = _stage_document(cache, "SYNTHETIC_SCORING_COMPLETE", "truth_bundle")
    if (not isinstance(scoring_package, dict)
            or set(scoring_package) != {"benchmark_snapshot_id", "result"}
            or scoring_package.get("benchmark_snapshot_id") != context.get("benchmark_snapshot_id")
            or not isinstance(truth_package, dict)
            or set(truth_package) != {"benchmark_snapshot_id", "truth_bundle"}
            or truth_package.get("benchmark_snapshot_id") != context.get("benchmark_snapshot_id")):
        return {"status": "FAIL", "issues": ["Scoring result or truth bundle is malformed or snapshot-mismatched."]}
    truth = truth_package["truth_bundle"]
    if hashlib.sha256(context["raw"]["SYNTHETIC_SCORING_COMPLETE"]["truth_bundle"]).hexdigest() != context.get("truth_bundle_sha256"):
        return {"status": "FAIL", "issues": ["Truth bundle bytes do not match the approved unblinding digest."]}
    if truth.get("analysis_sha256") != context.get("analysis_sha256"):
        return {"status": "FAIL", "issues": ["Truth bundle is not bound to the verified blinded analysis."]}
    exclusion_result = {
        "status": "PASS",
        "evidence_sha256": context["reference_result"]["aggregate_exclusion_evidence_sha256"],
        "results": [{"decision": "ACCEPT"}],
        "issues": [],
    }
    authorization = context["unblinding_result"]
    actual = phase6.scoring.score_synthetic_bundle(
        context["analysis"], truth, context["qualifications"],
        unblinding_authorization={
            "approved": True, "reviewer_ids": authorization["reviewer_ids"],
            "truth_bundle_sha256": phase6.scoring.canonical_sha256(truth.get("truth_records")),
        },
        expected_policy_sha256=phase6.scoring.scoring_policy_digest(),
        reference_exclusion_result=exclusion_result,
        expected_reference_evidence_sha256=exclusion_result["evidence_sha256"],
    )
    expected = {"benchmark_snapshot_id": BENCHMARK_SNAPSHOT_ID, "result": actual}
    if phase6.canonical_bytes(scoring_package) != phase6.canonical_bytes(expected):
        return {"status": "FAIL", "issues": ["Signed scoring result differs from the canonical Phase 5 recomputation."],
                "recomputed_result": actual}
    reviewer_ids = [
        *context["reference_result"].get("reviewer_ids", []),
        *[reviewer for item in context["qualifications"] for reviewer in item["reviewer_ids"]],
        *authorization.get("reviewer_ids", []),
    ]
    if len(reviewer_ids) != len(set(reviewer_ids)):
        return {"status": "FAIL", "issues": ["Reviewer identity is reused across independent governance stages."]}
    approval_ids = [
        *context["qualification_result"].get("approval_ids", []),
        *context["reference_result"].get("approval_ids", []),
        *authorization.get("approval_ids", []),
    ]
    if len(approval_ids) != len(set(approval_ids)):
        return {"status": "FAIL", "issues": ["Approval identifier is reused across independent governance stages."]}
    return {"status": actual.get("status"), "issues": actual.get("issues", []),
            "scoring_result_sha256": _sha(phase6.canonical_bytes(actual)),
            "recomputed_result": actual,
            "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION"}


CANONICAL_STAGE_ADAPTERS = {
    "QUALIFIED": _adapt_qualified,
    "REFERENCE_APPROVED": _adapt_reference_approved,
    "BLINDED_ANALYSIS_VERIFIED": _adapt_blinded_analysis,
    "UNBLINDING_AUTHORISED": _adapt_unblinding,
    "SYNTHETIC_SCORING_COMPLETE": _adapt_synthetic_scoring,
}


def verify_artifact_backed_transitions(
    receipts: Any, artifact_paths: Any, artifact_root: str | Path,
    trusted_reviewers: dict[str, Any], stage_verifiers: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify receipt signatures, immutable bytes, then all five built-in adapters."""
    now = now or datetime.now(timezone.utc)
    authenticated = phase6.verify_governance_transitions(receipts, trusted_reviewers, now)
    issues = list(authenticated["issues"])
    if authenticated["status"] != "PASS":
        return {"status": "FAIL", "state": authenticated["state"], "issues": issues,
                "biological_execution_authorized": False}
    if (authenticated["state"] != "SYNTHETIC_SCORING_COMPLETE"
            or authenticated["transition_count"] != len(phase6.STATES) - 1):
        return {"status": "FAIL", "state": authenticated["state"],
                "issues": ["A complete authenticated transition chain is required."],
                "biological_execution_authorized": False}
    if not isinstance(artifact_paths, dict):
        return {"status": "FAIL", "state": authenticated["state"],
                "issues": ["Stage artifact path inventory is malformed."],
                "biological_execution_authorized": False}
    expected_states = set(phase6.STATES[1:])
    if set(artifact_paths) != expected_states:
        return {"status": "FAIL", "state": authenticated["state"],
                "issues": ["Stage artifact state inventory is incomplete or contains unknown states."],
                "biological_execution_authorized": False}
    if Path(artifact_root).is_symlink() or not Path(artifact_root).is_dir():
        return {"status": "FAIL", "state": authenticated["state"],
                "issues": ["Stage artifact root is missing or unsafe."],
                "biological_execution_authorized": False}
    root = Path(artifact_root).resolve()
    checked = []
    critical_paths: list[tuple[Path, str]] = []
    cache: dict[str, dict[str, Any]] = {}
    raw: dict[str, dict[str, bytes]] = {}
    total_bytes = 0
    seen_paths: set[str] = set()
    for envelope in receipts:
        receipt = envelope["receipt"]
        state = receipt["requested_state"]
        expected = REQUIRED_TRANSITION_ARTIFACTS[state]
        supplied = artifact_paths.get(state)
        digests = receipt["verified_artifact_digests"]
        if (not isinstance(supplied, dict) or set(supplied) != set(digests)
                or set(supplied) != expected):
            issues.append(f"Required or typed artifacts are missing for {state}.")
            break
        stage_items = []
        for artifact_type, rel in sorted(supplied.items()):
            try:
                path = _safe_stage_file(root, rel)
                if rel in seen_paths:
                    raise ValueError("artifact path is reused by multiple evidence types")
                seen_paths.add(rel)
                if path.stat().st_size > 16 * 1024 * 1024:
                    raise OverflowError("stage artifact exceeds the per-file verification limit")
                actual, size = _file_sha(path)
                total_bytes += size
                if total_bytes > 64 * 1024 * 1024:
                    raise OverflowError("stage artifacts exceed the aggregate verification limit")
                if actual != digests.get(artifact_type):
                    raise ValueError("receipt digest mismatch")
                if size == 0:
                    raise ValueError("empty evidence artifact")
                data = path.read_bytes()
                if len(data) != size:
                    raise ValueError("artifact size changed while being read")
                if artifact_type in expected:
                    raw.setdefault(state, {})[artifact_type] = data
                    if artifact_type == "qualification_evidence":
                        pass
                    else:
                        parsed = json.loads(data.decode("utf-8"))
                        cache.setdefault(state, {})[artifact_type] = parsed
                    if _file_sha(path) != (actual, size):
                        raise ValueError("artifact changed while it was parsed")
                critical_paths.append((path, actual))
                stage_items.append({"type": artifact_type, "sha256": actual, "bytes": size})
            except (OSError, UnicodeError, TypeError, ValueError, OverflowError, json.JSONDecodeError) as exc:
                issues.append(f"Artifact verification failed for {state}:{artifact_type} ({exc}).")
                break
        if issues:
            break
        checked.append({"state": state, "artifacts": stage_items})
    if not issues:
        for path, expected_sha in critical_paths:
            try:
                if _file_sha(path)[0] != expected_sha:
                    issues.append("Stage evidence changed before final verification.")
                    break
            except OSError:
                issues.append("Stage evidence disappeared before final verification.")
                break
    adapter_results = []
    context: dict[str, Any] = {"raw": raw}
    if not issues:
        adapter_args = {
            "QUALIFIED": (trusted_reviewers, now),
            "REFERENCE_APPROVED": (root, trusted_reviewers, now),
            "BLINDED_ANALYSIS_VERIFIED": (now,),
            "UNBLINDING_AUTHORISED": (trusted_reviewers, now),
            "SYNTHETIC_SCORING_COMPLETE": (now,),
        }
        for state, adapter in CANONICAL_STAGE_ADAPTERS.items():
            try:
                result = adapter(cache, context, *adapter_args[state])
            except (KeyError, TypeError, ValueError, OSError, UnicodeError) as exc:
                result = {"status": "FAIL", "issues": [f"Canonical {state} adapter rejected malformed evidence ({exc})."]}
            adapter_results.append({"state": state, **result})
            if result.get("status") != "PASS":
                issues.extend(result.get("issues", [f"Canonical {state} adapter did not pass."]))
                break
    return _verified_result({
        "status": "FAIL" if issues else "PASS", "state": authenticated["state"],
        "issues": sorted(set(issues)), "verified_stages": checked,
        "semantic_adapter_status": "FAIL" if issues else "PASS",
        "adapter_results": adapter_results,
        "custom_callbacks_authoritative": False,
        "limitation": "PASS means synthetic Phase 7 evidence integrity only; independent retention and biological authorization remain separate.",
        "transition_sha256": authenticated["transition_sha256"],
        "biological_execution_authorized": False,
        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
    })


def phase7_readiness_report(
    panel: dict[str, Any] | None, scientific: dict[str, Any] | None,
    custody: dict[str, Any] | None, transitions: dict[str, Any] | None,
    adversarial_matrix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build deterministic JSON and plain-text status without granting execution."""
    panel = panel or {}
    scientific = scientific or {}
    custody = custody or {}
    transitions = transitions or {}
    valid = {"PASS", "FAIL", "INCOMPLETE", "PENDING"}
    def status(value: Any) -> str:
        return value if isinstance(value, str) and value in valid else "PENDING"
    trusted_panel = _is_verified_result(panel)
    trusted_scientific = _is_verified_result(scientific)
    trusted_custody = _is_verified_result(custody)
    trusted_transitions = _is_verified_result(transitions)
    trusted_matrix = _is_verified_result(adversarial_matrix)
    expected_adapter_states = list(CANONICAL_STAGE_ADAPTERS)
    adapter_results = transitions.get("adapter_results", []) if trusted_transitions else []
    adapters_pass = (
        transitions.get("semantic_adapter_status") == "PASS"
        and [item.get("state") for item in adapter_results] == expected_adapter_states
        and all(item.get("status") == "PASS" for item in adapter_results)
        and transitions.get("custom_callbacks_authoritative") is False
    )
    matrix_pass = (
        trusted_matrix and adversarial_matrix.get("status") == "PASS"
        and adversarial_matrix.get("case_count") == len(PHASE7_ACCEPTANCE_CASES)
        and isinstance(adversarial_matrix.get("matrix_sha256"), str)
        and bool(phase6.SHA_RE.fullmatch(adversarial_matrix["matrix_sha256"]))
    )
    report = {
        "schema_version": "m21-phase7-readiness-v1",
        "reference_snapshot_id": panel.get("snapshot_id"),
        "reference_artifacts_verified": panel.get("artifact_count", 0),
        "aggregate_limits": panel.get("aggregate_limits"),
        "per_artifact_status": [
            {"path": item.get("path"), "status": status(item.get("status"))}
            for item in panel.get("artifacts", []) if isinstance(item, dict)
        ],
        "aggregate_exclusion_status": status(panel.get("status")) if trusted_panel else "INCOMPLETE",
        "scientific_approval_status": status(scientific.get("status")) if trusted_scientific else "INCOMPLETE",
        "audit_chain_status": status(custody.get("status")) if trusted_custody else "INCOMPLETE",
        "independent_custody_anchor_status": (
            custody.get("anchor_status", "UNANCHORED") if trusted_custody else "UNANCHORED"
        ),
        "custody_policy_status": (
            "PASS" if trusted_custody and custody.get("status") == "PASS"
            and custody.get("anchor_status") == "INDEPENDENTLY_ANCHORED" else
            "FAIL" if trusted_custody and custody.get("status") == "FAIL" else "INCOMPLETE"
        ),
        "last_verified_checkpoint": custody.get("last_verified_checkpoint") if trusted_custody else None,
        "governance_transition_status": (
            status(transitions.get("status")) if trusted_transitions else "INCOMPLETE"
        ),
        "canonical_stage_adapters_status": "PASS" if trusted_transitions and adapters_pass else "INCOMPLETE",
        "adversarial_matrix_status": "PASS" if matrix_pass else "INCOMPLETE",
        "evidence_mismatches": sorted(set(
            [*panel.get("issues", []), *scientific.get("issues", []),
             *custody.get("issues", []), *transitions.get("issues", [])]
        )),
        "limitations": [
            "Independent retention is supplied and established out-of-band by the caller.",
            "Filesystem checks do not provide atomic or tamper-proof storage.",
            "Biological execution remains blocked.",
        ],
        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
        "biological_execution_authorized": False,
    }
    if trusted_transitions and trusted_matrix and trusted_custody:
        stage_reviewers = [
            reviewer for item in adapter_results if isinstance(item, dict)
            for reviewer in item.get("reviewer_ids", [])
        ]
        all_reviewer_ids = [
            *stage_reviewers, *adversarial_matrix.get("reviewer_ids", []),
            *custody.get("reviewer_ids", []),
        ]
        if len(all_reviewer_ids) != len(set(all_reviewer_ids)):
            report["evidence_mismatches"] = sorted(set(
                [*report["evidence_mismatches"], "Reviewer identity is reused across Phase 7 evidence groups."]
            ))
    component_statuses = (
        "aggregate_exclusion_status", "scientific_approval_status",
        "custody_policy_status", "governance_transition_status",
        "canonical_stage_adapters_status", "adversarial_matrix_status",
    )
    report["decision"] = "FAIL" if (
        report["evidence_mismatches"] or any(report[key] == "FAIL" for key in component_statuses)
    ) else (
        "PASS" if all(report[key] == "PASS" for key in component_statuses) and
        report["independent_custody_anchor_status"] == "INDEPENDENTLY_ANCHORED" else
        "INCOMPLETE"
    )
    human = [
        "M21 Phase 7 readiness: " + report["decision"],
        f"Reference snapshot: {report['reference_snapshot_id'] or 'PENDING'}",
        f"Reference artifacts verified: {report['reference_artifacts_verified']}",
        f"Aggregate exclusion: {report['aggregate_exclusion_status']}",
        f"Scientific approval: {report['scientific_approval_status']}",
        f"Audit chain: {report['audit_chain_status']}",
        f"Independent custody: {report['independent_custody_anchor_status']}",
        f"Custody policy: {report['custody_policy_status']}",
        f"Governance transitions: {report['governance_transition_status']}",
        f"Canonical stage adapters: {report['canonical_stage_adapters_status']}",
        f"Adversarial acceptance matrix: {report['adversarial_matrix_status']}",
        "Overall state: BLOCKED_FOR_BENCHMARK_EXECUTION",
    ]
    report["human_readable"] = "\n".join(human)
    return report
