"""Offline planning and human-review checks for one public-virus run.

This module never authorizes or performs data acquisition. A preflight plan is
not an execution capability; a future downloader must repeat live checks and
require a separate operator action.
"""
import hashlib
import json
import re

from . import public_virus, sequence_downloader
from .public_virus_acquisition_review import (
    PILOT_BUDGET_BYTES, build_review_packet,
)


SCHEMA = "public-virus-acquisition-preflight-v1"
DECISION_SCHEMA = "public-virus-acquisition-review-decision-v1"
FASTQ_MANIFEST_SCHEMA = "public-virus-fastq-manifest-v1"
MAX_COMPRESSED_BYTES = PILOT_BUDGET_BYTES
STORAGE_HEADROOM_FIXED_BYTES = 256 * 1024 * 1024


def _reason(code, detail):
    return {"code": code, "detail": detail}


def _is_nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def _valid_uint(value, *, positive=False):
    return (isinstance(value, int) and not isinstance(value, bool)
            and value >= (1 if positive else 0))


def canonical_fastq_manifest_json(files):
    """Return the canonical UTF-8 JSON text for validated FASTQ file metadata."""
    if not isinstance(files, (list, tuple)) or not files:
        raise ValueError("A nonempty validated FASTQ file list is required")
    entries = []
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("FASTQ manifest entries must be objects")
        url, name, role = item.get("url"), item.get("name"), item.get("role")
        byte_count, md5 = item.get("bytes"), item.get("md5")
        if (not all(isinstance(value, str) and value for value in (url, name, role))
                or not _valid_uint(byte_count, positive=True)
                or not isinstance(md5, str)
                or not re.fullmatch(r"[0-9a-f]{32}", md5)):
            raise ValueError("FASTQ manifest entry is missing validated fields")
        entries.append({
            "expected_bytes": byte_count,
            "expected_md5": md5,
            "name": name,
            "role": role,
            "url": url,
        })
    entries.sort(key=lambda entry: (entry["role"], entry["name"], entry["url"]))
    return json.dumps(
        {"files": entries, "schema": FASTQ_MANIFEST_SCHEMA},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    )


def fastq_manifest_sha256(files):
    """Hash the canonical manifest over UTF-8 bytes."""
    return hashlib.sha256(canonical_fastq_manifest_json(files).encode("utf-8")).hexdigest()


def _validate_decision(
    decision, run_accession, virus, expected_bytes, expected_manifest_sha256,
    policy_version, policy_sha256,
):
    reasons = []
    if decision is None:
        return [_reason("human_review_missing", "A structured human-review decision is required.")]
    if not isinstance(decision, dict):
        return [_reason("human_review_malformed", "The review decision must be a JSON object.")]

    required_strings = (
        "reviewer_identifier", "decision_identifier", "decision_rationale",
        "approved_run_accession", "selected_virus", "intended_pilot_purpose",
        "policy_version", "policy_sha256",
    )
    state = decision.get("state")
    if (decision.get("schema") != DECISION_SCHEMA
            or any(not _is_nonempty_string(decision.get(key)) for key in required_strings)
            or not isinstance(state, str)
            or state not in {"approved", "rejected", "pending"}):
        return [_reason("human_review_malformed",
                        "The review decision is missing required fields or has invalid values.")]

    if state != "approved":
        reasons.append(_reason(
            "human_review_not_approved",
            "Only an explicitly approved review decision can complete preflight.",
        ))
    if decision["approved_run_accession"] != run_accession:
        reasons.append(_reason(
            "human_review_run_mismatch",
            "The approved run accession does not match the intake run.",
        ))
    if decision["selected_virus"] != virus:
        reasons.append(_reason(
            "human_review_virus_mismatch",
            "The approved virus does not match the intake virus.",
        ))
    if (decision["policy_version"] != policy_version
            or decision["policy_sha256"] != policy_sha256):
        reasons.append(_reason(
            "human_review_policy_mismatch",
            "The review decision is not bound to the current policy version and digest.",
        ))
    approved_manifest_sha256 = decision.get("fastq_manifest_sha256")
    if approved_manifest_sha256 is None or approved_manifest_sha256 == "":
        reasons.append(_reason(
            "human_review_fastq_manifest_missing",
            "The review decision must include the exact FASTQ manifest SHA256.",
        ))
    elif (not isinstance(approved_manifest_sha256, str)
          or not re.fullmatch(r"[0-9a-f]{64}", approved_manifest_sha256)):
        reasons.append(_reason(
            "human_review_fastq_manifest_malformed",
            "The approved FASTQ manifest digest must be 64 lowercase hexadecimal characters.",
        ))
    elif expected_manifest_sha256 is None:
        reasons.append(_reason(
            "fastq_manifest_unavailable",
            "The current complete FASTQ manifest could not be recomputed.",
        ))
    elif approved_manifest_sha256 != expected_manifest_sha256:
        reasons.append(_reason(
            "human_review_fastq_manifest_mismatch",
            "The current complete FASTQ manifest differs from the reviewed manifest.",
        ))

    scope = decision.get("scope")
    expected_scope_keys = {
        "max_runs", "max_compressed_bytes", "max_storage_bytes",
    }
    if (not isinstance(scope, dict) or set(scope) != expected_scope_keys
            or not isinstance(scope.get("max_runs"), int)
            or isinstance(scope.get("max_runs"), bool)
            or scope.get("max_runs") != 1
            or not _valid_uint(scope.get("max_compressed_bytes"), positive=True)
            or scope.get("max_compressed_bytes", MAX_COMPRESSED_BYTES) > MAX_COMPRESSED_BYTES
            or not _valid_uint(scope.get("max_storage_bytes"), positive=True)):
        reasons.append(_reason(
            "human_review_scope_invalid",
            "Review scope must limit approval to one run and explicit positive compressed-byte and storage caps.",
        ))
        return reasons
    if expected_bytes is not None and expected_bytes > scope["max_compressed_bytes"]:
        reasons.append(_reason(
            "human_review_compressed_limit_exceeded",
            "Expected FASTQ bytes exceed the reviewer-approved compressed-byte limit.",
        ))
    return reasons


def build_acquisition_preflight(
    accession_document,
    raw_metadata_directory,
    review_decision=None,
    *,
    provenance_document=None,
    storage_directory=None,
):
    """Recompute technical eligibility and prepare a non-executable single-run plan."""
    record = accession_document.get("record", {}) if isinstance(accession_document, dict) else {}
    manifest = accession_document.get("manifest", {}) if isinstance(accession_document, dict) else {}
    run_value = record.get("run_accession") if isinstance(record, dict) else None
    run_accession = run_value if isinstance(run_value, str) else None
    identity = record.get("public_virus") if isinstance(record, dict) else None
    virus = identity.get("virus") if isinstance(identity, dict) else None
    if not isinstance(manifest, dict):
        manifest = {}
    review_packet = build_review_packet(
        accession_document, provenance_document,
        raw_metadata_directory=raw_metadata_directory,
    )
    reasons = []
    files = []
    expected_bytes = None
    current_manifest_sha256 = None
    required_storage_bytes = None
    review_eligible = review_packet.get("outcome") == "eligible_for_curator_review"

    if not review_eligible:
        gate_outcome = review_packet.get("outcome", "held_for_review")
        reasons.append(_reason(
            "review_gate_not_eligible",
            f"The current review gate returned {gate_outcome}; held or excluded runs cannot be planned.",
        ))
        for gate_reason in review_packet.get("reasons", []):
            reasons.append(_reason(
                f"review_gate_{gate_reason.get('code', 'unknown')}",
                gate_reason.get("detail", "Review-gate requirement was not satisfied."),
            ))

    if isinstance(record, dict):
        try:
            validated_files = sequence_downloader.files_for_run(record)
            if len({item["name"] for item in validated_files}) != len(validated_files):
                raise ValueError("Duplicate FASTQ filenames")
            current_manifest_sha256 = fastq_manifest_sha256(validated_files)
            if review_eligible:
                files = validated_files
                expected_bytes = sum(item["bytes"] for item in files)
                required_storage_bytes = (
                    3 * expected_bytes + STORAGE_HEADROOM_FIXED_BYTES
                )
        except (KeyError, TypeError, ValueError):
            files = []
            expected_bytes = None
            current_manifest_sha256 = None
            if review_eligible:
                reasons.append(_reason(
                    "fastq_file_set_invalid",
                    "The complete single/paired FASTQ file set, checksums, or sizes are invalid.",
                ))

    reasons.extend(_validate_decision(
        review_decision, run_accession, virus, expected_bytes,
        current_manifest_sha256,
        public_virus.POLICY["policy_version"], public_virus.POLICY_SHA256,
    ))

    if expected_bytes is not None and expected_bytes > MAX_COMPRESSED_BYTES:
        reasons.append(_reason(
            "fastq_over_pilot_budget",
            "The complete FASTQ set exceeds the 1,000,000,000-byte compressed pilot limit.",
        ))

    if (manifest.get("profile") != public_virus.POLICY["policy_version"]
            or manifest.get("policy_sha256") != public_virus.POLICY_SHA256):
        reasons.append(_reason(
            "policy_mismatch",
            "The intake policy version or digest differs from the current supported-virus policy.",
        ))

    scope = review_decision.get("scope") if isinstance(review_decision, dict) else {}
    storage_cap = scope.get("max_storage_bytes") if isinstance(scope, dict) else None
    compressed_cap = scope.get("max_compressed_bytes") if isinstance(scope, dict) else None
    if (required_storage_bytes is not None and _valid_uint(storage_cap, positive=True)
            and required_storage_bytes > storage_cap):
        reasons.append(_reason(
            "human_review_storage_limit_exceeded",
            "Required storage headroom exceeds the reviewer-approved storage limit.",
        ))
    if storage_directory is None:
        reasons.append(_reason(
            "storage_directory_missing",
            "A storage directory is required for a disk-headroom check.",
        ))
    elif required_storage_bytes is not None:
        try:
            sequence_downloader.check_disk(storage_directory, expected_bytes)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            code = ("insufficient_disk_space"
                    if isinstance(exc, RuntimeError) and "Insufficient disk space" in str(exc)
                    else "storage_check_failed")
            reasons.append(_reason(
                code,
                "Available storage does not meet the downloader's required headroom."
                if code == "insufficient_disk_space"
                else "The supplied storage location could not be checked.",
            ))

    unique_reasons = {reason["code"]: reason for reason in reasons}
    ordered_reasons = [unique_reasons[key] for key in sorted(unique_reasons)]
    ready = not ordered_reasons and review_eligible
    return {
        "schema": SCHEMA,
        "status": "ready_for_operator_confirmation" if ready else "blocked",
        "run_accession": run_accession,
        "selected_virus": virus,
        "policy": {
            "version": public_virus.POLICY["policy_version"],
            "sha256": public_virus.POLICY_SHA256,
        },
        "review_gate_outcome": review_packet.get("outcome"),
        "biological_independence": review_packet.get(
            "biological_independence",
            {"status": "UNKNOWN", "reason": "not assessed"},
        ),
        "fastq_files": [
            {
                "name": item["name"], "url": item["url"], "role": item["role"],
                "expected_bytes": item["bytes"], "expected_md5": item["md5"],
            }
            for item in files
        ],
        "fastq_manifest_sha256": current_manifest_sha256,
        "expected_compressed_bytes": expected_bytes,
        "maximum_allowed_compressed_bytes": MAX_COMPRESSED_BYTES,
        "required_storage_headroom_bytes": required_storage_bytes,
        "review_decision": {
            "state": (review_decision.get("state")
                      if isinstance(review_decision, dict)
                      and isinstance(review_decision.get("state"), str)
                      and review_decision.get("state") in {"approved", "rejected", "pending"}
                      else None),
            "decision_identifier": (
                review_decision.get("decision_identifier")
                if isinstance(review_decision, dict)
                and isinstance(review_decision.get("decision_identifier"), str) else None
            ),
            "reviewer_identifier": (
                review_decision.get("reviewer_identifier")
                if isinstance(review_decision, dict)
                and isinstance(review_decision.get("reviewer_identifier"), str) else None
            ),
            "decision_rationale": (
                review_decision.get("decision_rationale")
                if isinstance(review_decision, dict)
                and isinstance(review_decision.get("decision_rationale"), str) else None
            ),
            "approved_run_accession": (
                review_decision.get("approved_run_accession")
                if isinstance(review_decision, dict)
                and isinstance(review_decision.get("approved_run_accession"), str) else None
            ),
            "selected_virus": (
                review_decision.get("selected_virus")
                if isinstance(review_decision, dict)
                and isinstance(review_decision.get("selected_virus"), str) else None
            ),
            "policy_version": (
                review_decision.get("policy_version")
                if isinstance(review_decision, dict)
                and isinstance(review_decision.get("policy_version"), str) else None
            ),
            "policy_sha256": (
                review_decision.get("policy_sha256")
                if isinstance(review_decision, dict)
                and isinstance(review_decision.get("policy_sha256"), str) else None
            ),
            "intended_pilot_purpose": (
                review_decision.get("intended_pilot_purpose")
                if isinstance(review_decision, dict)
                and isinstance(review_decision.get("intended_pilot_purpose"), str) else None
            ),
            "scope": {
                "max_runs": (
                    scope.get("max_runs") if _valid_uint(scope.get("max_runs"))
                    else None
                ),
                "max_compressed_bytes": (
                    compressed_cap if _valid_uint(compressed_cap) else None
                ),
                "max_storage_bytes": (
                    storage_cap if _valid_uint(storage_cap) else None
                ),
            },
        },
        "reasons": ordered_reasons,
        "limitations": [
            "Technical eligibility and human-entered approval are not biological validation or authenticated authorization.",
            "Local snapshot SHA256 checks establish local consistency only, not independent archive authentication or freshness.",
            "Biological independence remains UNKNOWN unless separately established with traceable evidence.",
            "This plan does not classify the run as satellite-virus evidence.",
            "Plans are not execution capabilities; no reads are downloaded and no QC or analysis is run.",
        ],
        "required_immediate_pre_download_checks": [
            "Require a separate explicit operator action; this review record alone never enables acquisition.",
            "Perform a fresh archive lookup and revalidate run, sample, experiment, study, virus identity, and current policy.",
            "Compare the complete live FASTQ URL, filename, paired-end role, compressed size, and MD5 set with the approved plan.",
            "Recompute the complete-run byte budget and check current storage headroom immediately before transfer.",
            "Stop on any changed accession, file set, policy, approval scope, checksum, size, or resource limit.",
        ],
        "may_download": False,
        "download_enabled": False,
    }
