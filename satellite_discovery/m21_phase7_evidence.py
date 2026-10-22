"""Synthetic-only multi-artifact integrity and independently retained custody.

This module verifies bytes supplied by the caller; it performs no retrieval and
does not authorize biological execution.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import m21_benchmark_readiness as readiness
from . import m21_phase6_governance as phase6
from . import m21_reference_exclusion as exclusion

LIMIT_FIELDS = {"max_artifacts", "max_total_bytes", "max_total_bases",
                "max_references", "max_alignment_cells"}


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
    return report


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
    return {
        "status": "FAIL" if issues else "PASS", "issues": sorted(set(issues)),
        "snapshot_id": manifest["snapshot_id"],
        "reference_inventory_sha256": panel["artifact_inventory_sha256"],
        "exclusion_policy_sha256": policy_sha,
        "aggregate_exclusion_evidence_sha256": panel["aggregate_exclusion_evidence_sha256"],
        "scientific_review_sha256": review_sha,
        "reference_policy_approval_set_sha256": phase6._approval_set_digest(policy_approvals),
        "scientific_review_approval_set_sha256": phase6._approval_set_digest(scientific_approvals),
        "panel": panel,
    }


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
    return {
        "status": "FAIL" if issues else "PASS",
        "anchor_status": "INDEPENDENTLY_ANCHORED" if latest and not issues else "UNANCHORED",
        "checkpoint_count": len(verified), "last_verified_checkpoint": latest,
        "local_checkpoint_count": len(local_checkpoints), "issues": sorted(set(issues)),
        "limitation": "This verifier checks supplied retained bytes and signatures only; the caller must establish their independent source, retention policy, and custody.",
    }


REQUIRED_TRANSITION_ARTIFACTS = {
    "QUALIFIED": {"control_qualification", "qualification_evidence"},
    "REFERENCE_APPROVED": {"reference_panel_manifest", "exclusion_policy",
                           "aggregate_exclusion", "scientific_review"},
    "BLINDED_ANALYSIS_VERIFIED": {"blinded_analysis"},
    "UNBLINDING_AUTHORISED": {"unblinding_authorization"},
    "SYNTHETIC_SCORING_COMPLETE": {"synthetic_scoring_result"},
}


def verify_artifact_backed_transitions(
    receipts: Any, artifact_paths: Any, artifact_root: str | Path,
    trusted_reviewers: dict[str, Any], stage_verifiers: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Reopen signed artifacts; caller callbacks are explicitly non-authoritative.

    The canonical Phase 4–6 adapter registry is not yet shipped. Therefore this
    function can establish byte integrity but must return INCOMPLETE, never PASS,
    until built-in semantic adapters are added.
    """
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
    if Path(artifact_root).is_symlink() or not Path(artifact_root).is_dir():
        return {"status": "FAIL", "state": authenticated["state"],
                "issues": ["Stage artifact root is missing or unsafe."],
                "biological_execution_authorized": False}
    root = Path(artifact_root).resolve()
    checked = []
    critical_paths: list[tuple[Path, str]] = []
    total_bytes = 0
    for envelope in receipts:
        receipt = envelope["receipt"]
        state = receipt["requested_state"]
        expected = REQUIRED_TRANSITION_ARTIFACTS[state]
        supplied = artifact_paths.get(state)
        digests = receipt["verified_artifact_digests"]
        if not isinstance(supplied, dict) or set(supplied) != set(digests) or not expected.issubset(supplied):
            issues.append(f"Required or typed artifacts are missing for {state}.")
            break
        stage_items = []
        for artifact_type, rel in sorted(supplied.items()):
            if not isinstance(rel, str) or not rel:
                issues.append(f"Artifact path is invalid for {state}:{artifact_type}.")
                break
            path = root / rel
            try:
                path.resolve(strict=True).relative_to(root)
                if path.is_symlink() or not path.is_file():
                    raise ValueError("not a regular file")
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
                if artifact_type in expected:
                    data = path.read_bytes()
                    if artifact_type != "qualification_evidence":
                        json.loads(data.decode("utf-8"))
                    if _file_sha(path) != (actual, size):
                        raise ValueError("artifact changed while it was parsed")
                critical_paths.append((path, actual))
                stage_items.append({"type": artifact_type, "sha256": actual, "bytes": size})
            except (OSError, UnicodeError, ValueError, OverflowError, json.JSONDecodeError) as exc:
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
    return {
        "status": "FAIL" if issues else "INCOMPLETE", "state": authenticated["state"],
        "issues": sorted(set(issues)), "verified_stages": checked,
        "semantic_adapter_status": "INCOMPLETE",
        "custom_callbacks_authoritative": False,
        "limitation": "Only signed artifact bytes were checked; no built-in canonical Phase 4–6 adapter registry is available.",
        "transition_sha256": authenticated["transition_sha256"],
        "biological_execution_authorized": False,
        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
    }


def phase7_readiness_report(
    panel: dict[str, Any] | None, scientific: dict[str, Any] | None,
    custody: dict[str, Any] | None, transitions: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build deterministic JSON and plain-text status without granting execution."""
    panel = panel or {}
    scientific = scientific or {}
    custody = custody or {}
    transitions = transitions or {}
    valid = {"PASS", "FAIL", "INCOMPLETE", "PENDING"}
    def status(value: Any) -> str:
        return value if isinstance(value, str) and value in valid else "PENDING"
    report = {
        "schema_version": "m21-phase7-readiness-v1",
        "reference_snapshot_id": panel.get("snapshot_id"),
        "reference_artifacts_verified": panel.get("artifact_count", 0),
        "aggregate_limits": panel.get("aggregate_limits"),
        "per_artifact_status": [
            {"path": item.get("path"), "status": status(item.get("status"))}
            for item in panel.get("artifacts", []) if isinstance(item, dict)
        ],
        "aggregate_exclusion_status": status(panel.get("status")),
        "scientific_approval_status": status(scientific.get("status")),
        "audit_chain_status": status(custody.get("status")),
        "independent_custody_anchor_status": custody.get("anchor_status", "UNANCHORED"),
        "custody_policy_status": (
            "PASS" if custody.get("status") == "PASS"
            and custody.get("anchor_status") == "INDEPENDENTLY_ANCHORED" else
            "FAIL" if custody.get("status") == "FAIL" else "INCOMPLETE"
        ),
        "last_verified_checkpoint": custody.get("last_verified_checkpoint"),
        "governance_transition_status": status(transitions.get("status")),
        # These are implementation facts, not caller-provided status strings.
        # Both remain incomplete until the built-in verifier registry and the
        # named adversarial matrix are shipped and independently exercised.
        "canonical_stage_adapters_status": "INCOMPLETE",
        "adversarial_matrix_status": "INCOMPLETE",
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
