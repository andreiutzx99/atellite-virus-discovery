"""Synthetic-only Phase 7 closure evidence verification.

This module verifies supplied evidence; it never retrieves biological data,
creates reviewer identities, or authorizes benchmark execution.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import m21_benchmark_readiness as readiness
from . import m21_phase6_governance as phase6
from . import m21_phase7_evidence as phase7

class _VerifiedClosureEvidence(dict[str, Any]):
    pass


_VERIFIED_TOKEN = object()


def _verified_evidence(value: dict[str, Any]) -> dict[str, Any]:
    result = _VerifiedClosureEvidence(value)
    result._verification_token = _VERIFIED_TOKEN
    return result


def _is_verified_evidence(value: Any) -> bool:
    return (
        type(value) is _VerifiedClosureEvidence
        and getattr(value, "_verification_token", None) is _VERIFIED_TOKEN
    )


SCHEMA_VERSION = "m21-phase7-closure-v1"
REPOSITORY = "andreiutzx99/atellite-virus-discovery"
WORKFLOW = ".github/workflows/tests.yml"
PREDICATE_TYPE = f"https://github.com/{REPOSITORY}/attestations/m21-phase7-ci-run/v1"
REVIEW_SCOPE = "phase7_closure_approval"
RETENTION_SCOPE = "phase7_checkpoint_retention"
CI_FIELDS = {
    "schema_version", "repository", "workflow", "workflow_ref", "run_id",
    "run_attempt", "run_sha", "tested_commit_sha", "event_name",
    "acceptance_tests_conclusion", "matrix_results_sha256",
}
PACKAGE_FIELDS = {
    "schema_version", "verification_policy", "software_revision", "reference_panel_evidence",
    "scientific_approval_evidence", "canonical_transition_evidence",
    "ci_acceptance", "checkpoint_retention", "expires_at", "limitations",
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _b64(value: Any) -> bytes:
    if not isinstance(value, str):
        raise ValueError("base64 value must be a string")
    return base64.b64decode(value, validate=True)


def _schema_errors(name: str, value: Any) -> list[str] | None:
    """Return schema errors, or None when the optional validator is unavailable."""
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return None
    schema_path = Path(__file__).with_name("m21_phase7_closure.schema.json")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors = Draft202012Validator(schema).iter_errors(value)
        return [f"{name} does not match its closure schema." for _ in errors]
    except (OSError, json.JSONDecodeError, ValueError):
        return [f"{name} schema could not be loaded."]


def _human_trust_store(value: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Validate closure trust records; identity class is an explicit trust input."""
    if not isinstance(value, dict) or not value:
        return {}, ["Closure trust store is missing."]
    errors: list[str] = []
    seen_keys: set[str] = set()
    for reviewer_id, record in value.items():
        required = {
            "reviewer_id", "key_id", "public_key_ed25519", "role", "scopes",
            "valid_from", "valid_until", "revoked", "identity_class",
        }
        if (not isinstance(record, dict) or set(record) != required
                or record.get("reviewer_id") != reviewer_id
                or record.get("identity_class") not in {"HUMAN", "SYNTHETIC"}
                or not isinstance(record.get("scopes"), list)
                or not isinstance(record.get("revoked"), bool)):
            errors.append("Closure reviewer trust record is malformed.")
            continue
        try:
            raw = _b64(record["public_key_ed25519"])
        except (KeyError, ValueError):
            errors.append("Closure reviewer public key is malformed.")
            continue
        fingerprint = hashlib.sha256(raw).hexdigest()
        if len(raw) != 32 or record.get("key_id") in seen_keys or fingerprint in seen_keys:
            errors.append("Closure reviewer keys must be valid and unique.")
        seen_keys.update({str(record.get("key_id")), fingerprint})
    return value, errors


def verify_ci_acceptance(
    results_bytes: bytes, statement: Any, bundle_bytes: bytes, *,
    expected_revision: str, now: datetime | None = None,
    gh_binary: str = "gh", timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Verify result bytes, run predicate, Sigstore bundle, and GitHub workflow identity."""
    now = now or datetime.now(timezone.utc)
    issues: list[str] = []
    if not isinstance(statement, dict) or set(statement) != CI_FIELDS:
        return {"status": "FAIL", "issues": ["CI run statement is malformed."]}
    try:
        cases = json.loads(results_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {"status": "FAIL", "issues": ["Acceptance-results bytes are not valid UTF-8 JSON."]}
    if (not isinstance(cases, list)
            or tuple(item.get("case_id") for item in cases if isinstance(item, dict))
            != phase7.PHASE7_ACCEPTANCE_CASES
            or len(cases) != len(phase7.PHASE7_ACCEPTANCE_CASES)
            or any(not isinstance(item, dict)
                   or set(item) != {"case_id", "test_name", "expected", "observed"}
                   or item.get("test_name") != "test_" + str(item.get("case_id"))
                   or item.get("expected") != "FAIL" or item.get("observed") != "FAIL"
                   for item in cases)
            or results_bytes != phase6.canonical_bytes(cases)):
        issues.append("Acceptance results are partial, noncanonical, reordered, or not all passing.")
    if (statement.get("schema_version") != "m21-phase7-ci-run-statement-v1"
            or statement.get("repository") != REPOSITORY
            or statement.get("workflow") != WORKFLOW
            or statement.get("acceptance_tests_conclusion") != "success"
            or statement.get("tested_commit_sha") != expected_revision
            or statement.get("event_name") not in {"push", "pull_request"}
            or not isinstance(statement.get("workflow_ref"), str)
            or not re.fullmatch(
                rf"{re.escape(REPOSITORY)}/{re.escape(WORKFLOW)}@refs/(?:heads/m21/phase7-governance-closure|pull/[0-9]+/merge)",
                statement["workflow_ref"],
            )
            or not str(statement.get("run_id", "")).isdigit()
            or not isinstance(statement.get("run_attempt"), int)
            or isinstance(statement.get("run_attempt"), bool)
            or statement["run_attempt"] < 1
            or any(not isinstance(statement.get(key), str)
                   or len(statement[key]) != 40
                   or any(c not in "0123456789abcdef" for c in statement[key])
                   for key in ("run_sha", "tested_commit_sha"))
            or statement.get("matrix_results_sha256") != phase6.digest(cases)):
        issues.append("CI run identity or matrix digest does not bind the supplied revision and results.")
    bundle_sha = sha256_bytes(bundle_bytes)
    try:
        bundle = json.loads(bundle_bytes.decode("utf-8"))
        envelope = bundle["dsseEnvelope"]
        payload = json.loads(_b64(envelope["payload"]).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return {"status": "FAIL", "issues": ["GitHub attestation bundle is malformed."]}
    subjects = payload.get("subject") if isinstance(payload, dict) else None
    predicate = payload.get("predicate") if isinstance(payload, dict) else None
    if (payload.get("predicateType") != PREDICATE_TYPE
            or not isinstance(subjects, list) or len(subjects) != 1
            or not isinstance(subjects[0], dict)
            or subjects[0].get("name") != "m21_phase7_acceptance_matrix_results.json"
            or subjects[0].get("digest") != {"sha256": sha256_bytes(results_bytes)}
            or predicate != statement):
        issues.append("Attestation subject or predicate does not match the exact CI evidence.")
    if issues:
        return {"status": "FAIL", "issues": sorted(set(issues))}
    if shutil.which(gh_binary) is None:
        return {"status": "INCOMPLETE", "issues": ["GitHub CLI is unavailable for authoritative attestation verification."]}
    try:
        with tempfile.TemporaryDirectory(prefix="m21-phase7-closure-") as temp:
            root = Path(temp)
            result_path = root / "m21_phase7_acceptance_matrix_results.json"
            bundle_path = root / "attestation.jsonl"
            result_path.write_bytes(results_bytes)
            bundle_path.write_bytes(bundle_bytes)
            workflow_identity = f"{REPOSITORY}/{WORKFLOW}"
            completed = subprocess.run(
                [gh_binary, "attestation", "verify", str(result_path),
                 "--bundle", str(bundle_path), "--repo", REPOSITORY,
                 "--signer-workflow", workflow_identity,
                 "--predicate-type", PREDICATE_TYPE],
                capture_output=True, text=True, timeout=timeout_seconds, check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "INCOMPLETE", "issues": ["GitHub attestation verification could not be performed."]}
    if completed.returncode != 0:
        unavailable = any(term in completed.stderr.lower() for term in (
            "401", "403", "rate limit", "network", "not authenticated", "timeout",
        ))
        if unavailable:
            return {"status": "INCOMPLETE", "issues": ["GitHub attestation verification was unavailable."]}
        return {"status": "FAIL", "issues": ["GitHub CLI rejected the attestation bundle or signer identity."]}
    run_path = f"repos/{REPOSITORY}/actions/runs/{statement['run_id']}/attempts/{statement['run_attempt']}"
    jobs_path = f"{run_path}/jobs?per_page=100"
    try:
        run_check = subprocess.run(
            [gh_binary, "api", run_path], capture_output=True, text=True,
            timeout=timeout_seconds, check=False,
        )
        jobs_check = subprocess.run(
            [gh_binary, "api", jobs_path], capture_output=True, text=True,
            timeout=timeout_seconds, check=False,
        )
        run_data = json.loads(run_check.stdout) if run_check.returncode == 0 else {}
        jobs_data = json.loads(jobs_check.stdout) if jobs_check.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {"status": "INCOMPLETE", "issues": ["GitHub run and job metadata could not be independently retrieved."]}
    if run_check.returncode != 0 or jobs_check.returncode != 0:
        return {"status": "INCOMPLETE", "issues": ["GitHub run and job metadata could not be independently retrieved."]}
    matching_jobs = [
        job for job in jobs_data.get("jobs", [])
        if isinstance(job, dict) and job.get("name") == "phase7-acceptance-evidence"
    ] if isinstance(jobs_data, dict) else []
    expected_head = statement["tested_commit_sha"]
    run_head_valid = (
        run_data.get("head_sha") == expected_head
        if statement["event_name"] == "pull_request"
        else run_data.get("head_sha") == statement["run_sha"] == expected_head
    )
    if (run_check.returncode != 0 or jobs_check.returncode != 0
            or run_data.get("status") != "completed"
            or run_data.get("conclusion") != "success"
            or run_data.get("run_attempt") != statement["run_attempt"]
            or run_data.get("event") != statement["event_name"]
            or run_data.get("path") != WORKFLOW
            or not run_head_valid or len(matching_jobs) != 1
            or matching_jobs[0].get("status") != "completed"
            or matching_jobs[0].get("conclusion") != "success"):
        return {"status": "FAIL", "issues": ["GitHub run or acceptance-job metadata does not match the signed CI statement."]}
    return _verified_evidence({
        "status": "PASS", "issues": [], "run_id": statement["run_id"],
        "run_attempt": statement["run_attempt"], "tested_commit_sha": expected_revision,
        "workflow_ref": statement["workflow_ref"],
        "results_sha256": sha256_bytes(results_bytes), "bundle_sha256": bundle_sha,
        "predicate_type": PREDICATE_TYPE,
        "subject_name": "m21_phase7_acceptance_matrix_results.json",
        "verification_method": "gh attestation verify --bundle",
        "verified_at": now.isoformat(), "evidence_class": "GITHUB_ATTESTATION",
        "workflow_run_conclusion": run_data["conclusion"],
        "acceptance_job_conclusion": matching_jobs[0]["conclusion"],
    })


def verify_checkpoint_retention(
    package: Any, trust_store: Any, *, local_events: Any,
    local_checkpoints: Any, expected_snapshot: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Verify signed externally retained checkpoints; do not infer custody from a local file."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(package, dict) or set(package) != {
        "schema_version", "benchmark_snapshot_id", "dataset_id", "chain_id",
        "retained_checkpoints", "retention_receipt",
    }:
        return {"status": "FAIL", "issues": ["Retained checkpoint package is malformed."]}
    schema_issues = _schema_errors("Retained checkpoint package", package)
    if schema_issues:
        return {"status": "FAIL", "issues": schema_issues}
    reviewers, issues = _human_trust_store(trust_store)
    receipt = package.get("retention_receipt")
    if (package.get("schema_version") != "m21-phase7-retained-checkpoints-v1"
            or package.get("benchmark_snapshot_id") != expected_snapshot
            or package.get("dataset_id") != expected_snapshot
            or not isinstance(receipt, dict)
            or set(receipt) != {"source_uri", "retrieved_at", "retrieved_by", "custodian_id",
                                "key_id", "signature_ed25519", "package_sha256"}):
        issues.append("Retention receipt does not bind the expected synthetic snapshot.")
        return {"status": "FAIL", "issues": issues}
    source = urlparse(str(receipt["source_uri"]))
    custodian = reviewers.get(receipt["custodian_id"])
    content = {k: v for k, v in receipt.items() if k != "signature_ed25519"}
    package_digest = phase6.digest({
        "benchmark_snapshot_id": package["benchmark_snapshot_id"],
        "dataset_id": package["dataset_id"], "chain_id": package["chain_id"],
        "retained_checkpoints": package["retained_checkpoints"],
    })
    timestamp = readiness._parse_time(receipt["retrieved_at"])
    if (source.scheme != "https" or not source.netloc or source.username
            or source.password or source.query or source.fragment
            or not isinstance(receipt["retrieved_by"], str) or not receipt["retrieved_by"]
            or receipt["retrieved_by"] == receipt["custodian_id"]
            or receipt["package_sha256"] != package_digest
            or not timestamp or timestamp > now or not custodian
            or custodian.get("role") != RETENTION_SCOPE
            or RETENTION_SCOPE not in custodian.get("scopes", [])
            or custodian.get("identity_class") not in {"HUMAN", "SYNTHETIC"}
            or custodian.get("revoked") is not False
            or custodian.get("key_id") != receipt["key_id"]
            or not readiness._parse_time(custodian.get("valid_from"))
            or not readiness._parse_time(custodian.get("valid_until"))
            or not (readiness._parse_time(custodian["valid_from"]) <= timestamp
                    < readiness._parse_time(custodian["valid_until"]))):
        issues.append("Retention source, custodian, identity, or package digest is invalid or non-independent.")
    else:
        try:
            Ed25519PublicKey.from_public_bytes(_b64(custodian["public_key_ed25519"])).verify(
                _b64(receipt["signature_ed25519"]), canonical_bytes(content),
            )
        except (ValueError, InvalidSignature, TypeError):
            issues.append("External retention receipt signature verification failed.")
    if issues:
        return {"status": "FAIL", "issues": sorted(set(issues))}
    retained = package["retained_checkpoints"]
    custody = phase7.verify_independent_custody(
        local_events, local_checkpoints, retained, reviewers,
        dataset_id=package["dataset_id"], chain_id=package["chain_id"],
        trust_store_identity=phase6.digest(reviewers), now=now,
        require_local_checkpoints=True,
    )
    if custody.get("status") != "PASS" or custody.get("anchor_status") != "INDEPENDENTLY_ANCHORED":
        return {"status": "FAIL", "issues": custody.get("issues", ["Checkpoint continuity failed."])}
    return _verified_evidence({
        "status": "PASS", "issues": [], "checkpoint_count": custody["checkpoint_count"],
        "package_sha256": package_digest, "source_uri": receipt["source_uri"],
        "retrieval_identity": receipt["retrieved_by"], "custodian_id": receipt["custodian_id"],
        "verified_at": now.isoformat(), "continuity": custody,
        "evidence_class": custodian["identity_class"],
        "limitation": "Custody is only as trustworthy as the independently provisioned custodian key and retention source.",
    })


def verify_closure_package(
    package: Any, approvals: Any, trust_store: Any, *,
    verified_components: dict[str, Any], ci_verification: Any,
    checkpoint_verification: Any, now: datetime | None = None,
) -> dict[str, Any]:
    """Recompute a content-addressed closure decision; never accept caller PASS fields."""
    now = now or datetime.now(timezone.utc)
    if not isinstance(package, dict) or set(package) != PACKAGE_FIELDS:
        return {"decision": "FAIL", "issues": ["Closure package is malformed."]}
    schema_issues = _schema_errors("Closure package", package)
    if schema_issues:
        return {"decision": "FAIL", "issues": schema_issues}
    if (package.get("schema_version") != SCHEMA_VERSION
            or package.get("verification_policy") != SCHEMA_VERSION):
        return {"decision": "FAIL", "issues": ["Unsupported closure package schema version."]}
    if (not isinstance(package.get("software_revision"), str)
            or len(package["software_revision"]) != 40
            or any(c not in "0123456789abcdef" for c in package["software_revision"])):
        return {"decision": "FAIL", "issues": ["Software revision is malformed."]}
    expires = readiness._parse_time(package.get("expires_at"))
    if not expires or expires <= now:
        return {"decision": "FAIL", "issues": ["Closure package is expired or has invalid expiry."]}
    reviewers, issues = _human_trust_store(trust_store)
    required_components = {
        "reference_panel_evidence", "scientific_approval_evidence",
        "canonical_transition_evidence",
    }
    if not isinstance(verified_components, dict) or set(verified_components) != required_components:
        issues.append("All canonical Phase 7 component verifications are required.")
    else:
        for name, result in verified_components.items():
            if (not phase7._is_verified_result(result) or result.get("status") != "PASS"
                    or package.get(name) != phase6.digest(result)):
                issues.append(f"{name} was not recomputed by a canonical Phase 7 verifier.")
    if (not _is_verified_evidence(ci_verification)
            or ci_verification.get("status") != "PASS"
            or ci_verification.get("tested_commit_sha") != package["software_revision"]
            or package.get("ci_acceptance") != phase6.digest(ci_verification)):
        issues.append(
            "CI acceptance is unverified or is bound to different revision/evidence."
            if _is_verified_evidence(ci_verification) else
            "Authoritatively verified CI acceptance is required."
        )
    if (not _is_verified_evidence(checkpoint_verification)
            or checkpoint_verification.get("status") != "PASS"
            or package.get("checkpoint_retention") != phase6.digest(checkpoint_verification)):
        issues.append("Independently authenticated checkpoint retention is required.")
    package_sha = phase6.digest(package)
    evidence_sha = phase6.digest({
        "package_sha256": package_sha,
        "ci_verification": ci_verification,
        "checkpoint_verification": checkpoint_verification,
        "verification_policy": SCHEMA_VERSION,
    })
    approval_errors = []
    if not isinstance(approvals, list) or len(approvals) < 2:
        approval_errors.append("At least two independent reviewer approvals are required.")
    reviewer_ids: list[str] = []
    approval_ids: list[str] = []
    if isinstance(approvals, list):
        for approval in approvals:
            if isinstance(approval, dict):
                reviewer_ids.append(str(approval.get("reviewer_id", "")))
                approval_ids.append(str(approval.get("approval_id", "")))
                if approval.get("evidence_sha256") != evidence_sha:
                    approval_errors.append("Reviewer approval does not cover the complete verification evidence.")
            approval_errors.extend(readiness._check_approval(
                package["software_revision"], package_sha, REVIEW_SCOPE,
                approval, reviewers, now, package_sha,
            ))
    if len(reviewer_ids) != len(set(reviewer_ids)):
        approval_errors.append("Reviewer identities must be distinct.")
    if len(approval_ids) != len(set(approval_ids)):
        approval_errors.append("Reviewer approval identifiers must be unique.")
    issues.extend(approval_errors)
    if issues:
        hard_failure = (
            (isinstance(ci_verification, dict) and ci_verification.get("status") == "FAIL")
            or (isinstance(checkpoint_verification, dict) and checkpoint_verification.get("status") == "FAIL")
            or any(any(word in issue.lower() for word in
                       ("malformed", "invalid", "expired", "failed", "mismatch", "altered",
                        "revoked", "different", "distinct", "unique", "validity",
                        "outside", "stale", "rotated", "scope"))
                   for issue in issues)
        )
        return {
            "decision": "FAIL" if hard_failure else "INCOMPLETE",
            "issues": sorted(set(issues)), "package_sha256": package_sha,
            "evidence_sha256": evidence_sha, "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
            "biological_execution_authorized": False,
        }
    synthetic = (
        any(reviewers[r].get("identity_class") != "HUMAN" for r in reviewer_ids if r in reviewers)
        or ci_verification.get("evidence_class") != "GITHUB_ATTESTATION"
        or checkpoint_verification.get("evidence_class") != "HUMAN"
    )
    decision = "INCOMPLETE" if synthetic else "PASS"
    return {
        "decision": decision, "issues": [],
        "package_sha256": package_sha, "evidence_sha256": evidence_sha,
        "reviewer_ids": sorted(reviewer_ids), "verification_policy": SCHEMA_VERSION,
        "verified_at": now.isoformat(),
        "limitations": list(package["limitations"]),
        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
        "biological_execution_authorized": False,
    }
