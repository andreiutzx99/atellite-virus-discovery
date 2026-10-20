"""Offline M21 benchmark governance checks. This module never downloads or runs stages."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import math
import os
import re
import secrets
import stat
import sqlite3
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # The project dependency is normally installed.
    InvalidSignature = Exception
    Ed25519PublicKey = None

SCHEMA_VERSION = "m21-benchmark-manifest-v1"
REFERENCE_SCHEMA_VERSION = "m21-reference-panel-manifest-v1"
SAMPLE_ID_RE = re.compile(r"BLD-[A-F0-9]{24}\Z")
DATASET_ID_RE = re.compile(r"DS-[A-Z0-9]{10}\Z")
OPAQUE_REF_RE = re.compile(r"(?:SRC|ACCREF)-[A-Z0-9]{10}\Z")
SHA256_RE = re.compile(r"[a-f0-9]{64}\Z")
APPROVAL_ID_RE = re.compile(r"APR-[A-Z0-9]{12}\Z")
REVIEWER_ID_RE = re.compile(r"REV-[A-Z0-9]{8}\Z")
KEY_ID_RE = re.compile(r"KEY-[A-Z0-9]{10}\Z")
SIGNATURE_RE = re.compile(r"[A-Za-z0-9+/]{86}==?\Z")
GATES = (
    "metadata_verification", "file_byte_verification", "data_use",
    "technical_qc", "reference_panel", "blinding", "ground_truth_review",
    "negative_control_review", "execution_authorization",
)
APPROVAL_STATUSES = {"APPROVED", "NOT_APPLICABLE", "PENDING", "REJECTED"}
LEAK_KEYS = re.compile(
    r"(?:truth_label|sample_name|biosample|run_accession|sample_accession|"
    r"expected_(?:target|sequence)|target_sequence|private_key)",
    re.IGNORECASE,
)
ACCESSION_RE = re.compile(r"\b(?:SRR|SRX|SAMN|PV)\d{5,}\b", re.IGNORECASE)
SAMPLE_LABEL_RE = re.compile(r"\b(?:Px15|PxBG2|Px31)\b", re.IGNORECASE)
BIO_PATH_LEAK_RE = re.compile(r"(?:px15|pxbg2|px31|truth[-_ ]?key|unblind(?:ed)?|positive[-_ ]?control|negative[-_ ]?control)", re.IGNORECASE)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
TEXT_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt", ".md", ".csv", ".tsv", ".xml"}


def generate_opaque_sample_id() -> str:
    """Generate an opaque, non-semantic identifier; never embeds a sample label."""
    return "BLD-" + secrets.token_hex(12).upper()


def validate_opaque_ids(ids: list[str]) -> list[str]:
    issues = []
    seen = set()
    for item in ids:
        if not isinstance(item, str) or not SAMPLE_ID_RE.fullmatch(item):
            issues.append("Malformed opaque sample identifier.")
        elif item in seen:
            issues.append("Duplicate opaque sample identifier.")
        else:
            seen.add(item)
    return issues


def write_sealed_truth_key(mapping: dict[str, str], key_path: str | Path,
                           analysis_root: str | Path,
                           operator_root: str | Path | None = None) -> None:
    """Write a custodian-only mapping outside analysis/operator trees, mode 0600, no overwrite."""
    if os.name == "nt":
        raise OSError("Production truth-key creation is disabled on Windows; secure ACLs are not verified.")
    target = Path(key_path).absolute()
    root = Path(analysis_root).resolve()
    operator_workspace = Path(operator_root or analysis_root).resolve()
    resolved_parent = target.parent.resolve(strict=True)
    resolved_target = resolved_parent / target.name
    if resolved_target == root or root in resolved_target.parents:
        raise ValueError("Truth key must be stored outside the analysis workspace.")
    if resolved_target == operator_workspace or operator_workspace in resolved_target.parents:
        raise ValueError("Truth key must be stored outside the operator workspace.")
    if target.exists() or target.is_symlink():
        raise FileExistsError("Truth-key destination already exists.")
    if not isinstance(mapping, dict) or not mapping or not all(
        isinstance(k, str) and k and isinstance(v, str) and SAMPLE_ID_RE.fullmatch(v)
        for k, v in mapping.items()
    ):
        raise ValueError("Truth-key mapping must contain labels and valid opaque IDs.")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("Truth-key opaque identifiers must be unique.")
    payload = json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode("utf-8")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def _approval_payload(dataset_id: str, sample_id: str, gate: str, record: dict[str, Any]) -> bytes:
    signed = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "sample_id": sample_id,
        "gate": gate,
        "status": record.get("status"),
        "approval_id": record.get("approval_id"),
        "reviewer_id": record.get("reviewer_id"),
        "approved_at": record.get("approved_at"),
        "expires_at": record.get("expires_at"),
        "evidence_sha256": record.get("evidence_sha256"),
        "manifest_sha256": record.get("manifest_sha256"),
        "key_id": record.get("key_id"),
    }
    return json.dumps(signed, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def _check_approval(dataset_id: str, sample_id: str, gate: str, record: Any,
                    trusted_reviewers: dict[str, str], now: datetime,
                    manifest_sha256: str | None = None) -> list[str]:
    prefix = f"gate {gate}"
    if not isinstance(record, dict):
        return [f"{prefix}: missing approval record."]
    allowed = {"status", "approval_id", "reviewer_id", "approved_at", "expires_at",
               "evidence_sha256", "manifest_sha256", "key_id", "signature_ed25519"}
    issues = [f"{prefix}: unknown approval fields."] if set(record) - allowed else []
    status = record.get("status")
    if not isinstance(status, str) or status not in APPROVAL_STATUSES:
        return issues + [f"{prefix}: invalid status."]
    if status != "APPROVED" and not (status == "NOT_APPLICABLE" and gate == "negative_control_review"):
        return issues + [f"{prefix}: approval is {status}."]
    for name, pattern in (
        ("approval_id", APPROVAL_ID_RE), ("reviewer_id", REVIEWER_ID_RE),
        ("evidence_sha256", SHA256_RE), ("manifest_sha256", SHA256_RE),
        ("key_id", KEY_ID_RE),
        ("signature_ed25519", SIGNATURE_RE),
    ):
        if not isinstance(record.get(name), str) or not pattern.fullmatch(record[name]):
            issues.append(f"{prefix}: missing or malformed {name}.")
    if manifest_sha256 is not None and record.get("manifest_sha256") != manifest_sha256:
        issues.append(f"{prefix}: approval is not bound to the current manifest content.")
    approved_at, expires_at = _parse_time(record.get("approved_at")), _parse_time(record.get("expires_at"))
    if not approved_at or not expires_at:
        issues.append(f"{prefix}: approval timestamps must be timezone-aware ISO-8601.")
    elif approved_at > now or expires_at <= now or expires_at <= approved_at:
        issues.append(f"{prefix}: approval is future-dated, expired, or has an invalid expiry.")
    reviewer = record.get("reviewer_id")
    reviewer_record = trusted_reviewers.get(reviewer) if isinstance(reviewer, str) else None
    if not isinstance(reviewer_record, dict):
        issues.append(f"{prefix}: reviewer is not in the external trust store.")
    elif record.get("key_id") != reviewer_record.get("key_id"):
        issues.append(f"{prefix}: approval uses a stale or rotated reviewer key.")
    elif reviewer_record.get("revoked") is not False:
        issues.append(f"{prefix}: reviewer key is revoked or has no explicit active status.")
    elif reviewer_record.get("role") != gate or gate not in reviewer_record.get("scopes", []):
        issues.append(f"{prefix}: reviewer role or permitted scope does not authorize this gate.")
    elif approved_at and (
        approved_at < _parse_time(reviewer_record["valid_from"])
        or approved_at >= _parse_time(reviewer_record["valid_until"])
    ):
        issues.append(f"{prefix}: approval was signed outside the reviewer key validity period.")
    elif not (_parse_time(reviewer_record.get("valid_from")) and _parse_time(reviewer_record.get("valid_until"))
              and _parse_time(reviewer_record["valid_from"]) <= now < _parse_time(reviewer_record["valid_until"])):
        issues.append(f"{prefix}: reviewer key is outside its validity period.")
    elif Ed25519PublicKey is None:
        issues.append(f"{prefix}: cryptography dependency unavailable; approval verification cannot run.")
    elif not issues:
        try:
            key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(reviewer_record["public_key_ed25519"], validate=True)
            )
            signature = base64.b64decode(record["signature_ed25519"], validate=True)
            key.verify(signature, _approval_payload(dataset_id, sample_id, gate, record))
        except (ValueError, InvalidSignature, TypeError):
            issues.append(f"{prefix}: signature verification failed.")
    return issues


def _load_trust_store(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"schema_version", "reviewers"} or data.get("schema_version") != "m21-reviewer-trust-store-v1" or not isinstance(data.get("reviewers"), list):
        raise ValueError("Malformed reviewer trust store.")
    reviewers = {}
    seen_keys = set()
    for item in data["reviewers"]:
        required = {"reviewer_id", "key_id", "public_key_ed25519", "role", "scopes",
                    "valid_from", "valid_until", "revoked"}
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("Malformed reviewer trust-store record.")
        if (not isinstance(item["reviewer_id"], str) or not REVIEWER_ID_RE.fullmatch(item["reviewer_id"])
                or not isinstance(item["key_id"], str) or not KEY_ID_RE.fullmatch(item["key_id"])
                or not isinstance(item["public_key_ed25519"], str)
                or not isinstance(item["role"], str) or not isinstance(item["scopes"], list)
                or any(scope not in GATES for scope in item["scopes"])
                or not isinstance(item["revoked"], bool)
                or not _parse_time(item["valid_from"]) or not _parse_time(item["valid_until"])
                or item["reviewer_id"] in reviewers):
            raise ValueError("Invalid or duplicate reviewer trust-store record.")
        try:
            raw = base64.b64decode(item["public_key_ed25519"], validate=True)
        except ValueError as exc:
            raise ValueError("Malformed reviewer public key.") from exc
        if len(raw) != 32:
            raise ValueError("Reviewer Ed25519 public keys must be 32 bytes.")
        fingerprint = hashlib.sha256(raw).hexdigest()
        if item["key_id"] in seen_keys or fingerprint in seen_keys:
            raise ValueError("Reviewer key IDs and public keys must be unique across independent roles.")
        seen_keys.add(item["key_id"])
        seen_keys.add(fingerprint)
        reviewers[item["reviewer_id"]] = item
    return reviewers


def _scan_leak_text(text: str, location: str) -> list[str]:
    issues = []
    if PRIVATE_KEY_RE.search(text) or re.search(r'"private_key"\s*:', text, re.I):
        issues.append(f"Private-key material detected in {location}.")
    if LEAK_KEYS.search(text):
        issues.append(f"Disallowed truth/identity field detected in {location}.")
    if ACCESSION_RE.search(text):
        issues.append(f"Biological accession-like identifier detected in {location}.")
    if SAMPLE_LABEL_RE.search(text):
        issues.append(f"Biological sample label detected in {location}.")
    return issues


def scan_operator_artifacts(root: str | Path, forbidden_tokens: list[str] | None = None) -> list[str]:
    root = Path(root)
    issues: list[str] = []
    tokens = [x.casefold() for x in (forbidden_tokens or []) if x]
    if root.is_symlink() or not root.is_dir():
        return ["Operator artifact directory is missing."]
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        issues.extend(_scan_leak_text(rel, rel))
        if BIO_PATH_LEAK_RE.search(rel):
            issues.append(f"Meaningful biological or truth-bearing label detected in path {rel}.")
        if path.is_symlink():
            issues.append(f"Symlink in operator artifact tree: {rel}.")
        elif path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeError, OSError):
                issues.append(f"Unreadable text artifact: {rel}.")
                continue
            issues.extend(_scan_leak_text(text, rel))
            if any(token in text.casefold() for token in tokens):
                issues.append(f"Configured disclosure token detected in {rel}.")
    return sorted(set(issues))


def operator_inventory_digest(root: str | Path) -> str:
    """Hash sorted paths and file bytes without loading artifacts into memory."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Operator artifact directory is missing.")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        if path.is_symlink():
            digest.update(b"SYMLINK")
        elif path.is_file():
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    return digest.hexdigest()


def validate_reference_panel(document: Any, trusted_reviewers: dict[str, str],
                             now: datetime | None = None,
                             reference_root: str | Path | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    if not isinstance(document, dict):
        return ["Reference-panel manifest must be an object."]
    required = {"schema_version", "snapshot_id", "references", "target_exclusion_policy_id", "approval"}
    issues = [f"Reference-panel manifest missing {x}." for x in sorted(required - set(document))]
    if set(document) - required:
        issues.append("Reference-panel manifest contains unknown fields.")
    if document.get("schema_version") != REFERENCE_SCHEMA_VERSION:
        issues.append("Unsupported reference-panel schema version.")
    if not re.fullmatch(r"REF-[A-Z0-9]{10}", str(document.get("snapshot_id", ""))):
        issues.append("Malformed reference snapshot identifier.")
    if not re.fullmatch(r"POL-[A-Z0-9]{10}", str(document.get("target_exclusion_policy_id", ""))):
        issues.append("Missing or malformed target-exclusion policy identifier.")
    refs = document.get("references")
    if not isinstance(refs, list) or not refs:
        issues.append("Reference panel must list at least one provenance record.")
    else:
        for idx, ref in enumerate(refs):
            if not isinstance(ref, dict) or set(ref) != {"source", "accession_version", "path", "bytes", "sha256"}:
                issues.append(f"Reference record {idx} has missing or unknown provenance fields.")
            elif not all(isinstance(ref[k], str) and ref[k] for k in ("source", "accession_version", "path")) or not SHA256_RE.fullmatch(str(ref["sha256"])) or not isinstance(ref["bytes"], int) or isinstance(ref["bytes"], bool) or ref["bytes"] <= 0:
                issues.append(f"Reference record {idx} has invalid provenance or digest.")
            elif reference_root is None:
                issues.append("Reference-byte integrity root is required; metadata approval alone is insufficient.")
            else:
                root = Path(reference_root).resolve()
                path = root / ref["path"]
                try:
                    path.resolve(strict=True).relative_to(root)
                    if path.is_symlink() or not path.is_file():
                        raise ValueError("not a regular file")
                    digest = hashlib.sha256()
                    size = 0
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            size += len(chunk)
                            digest.update(chunk)
                    if size != ref["bytes"] or digest.hexdigest() != ref["sha256"]:
                        issues.append(f"Reference-byte integrity mismatch for record {idx}.")
                except (OSError, ValueError):
                    issues.append(f"Reference bytes are missing or unsafe for record {idx}.")
    approval = document.get("approval")
    if isinstance(approval, dict):
        status = approval.get("status")
        if status != "APPROVED":
            issues.append("Reference-panel independent review is not approved.")
        else:
            issues.extend(_check_approval(
                str(document.get("snapshot_id", "")), str(document.get("snapshot_id", "")),
                "reference_panel", approval, trusted_reviewers, now,
                _reference_panel_binding_digest(document),
            ))
    else:
        issues.append("Reference-panel independent approval record is missing.")
    return issues


def _reference_panel_binding_digest(document: dict[str, Any]) -> str:
    content = {key: value for key, value in document.items() if key != "approval"}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _manifest_binding_digest(document: dict[str, Any]) -> str:
    """Bind every non-approval field, including reads, provenance, truth review and reference panel."""
    content = {key: value for key, value in document.items() if key != "gates"}
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_manifest(document: Any, analysis_root: str | Path,
                      trusted_reviewers: dict[str, str] | None = None,
                      now: datetime | None = None, verify_files: bool = True,
                      scan_root: str | Path | None = None,
                      reference_manifest: Any = None,
                      reference_root: str | Path | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    trusted_reviewers = trusted_reviewers or {}
    issues: list[str] = []
    if not isinstance(document, dict):
        return {"decision": "BLOCKED", "issues": ["Manifest must be a JSON object."]}
    issues.extend(_scan_leak_text(json.dumps(document, sort_keys=True), "manifest"))
    top = {"schema_version", "dataset_id", "sample_id", "provenance", "read_input",
           "reference_panel_sha256",
           "ground_truth_review", "gates"}
    if set(document) != top:
        issues.append("Manifest fields are missing or unknown.")
    if document.get("schema_version") != SCHEMA_VERSION:
        issues.append("Unsupported manifest schema version.")
    dataset_id, sample_id = document.get("dataset_id"), document.get("sample_id")
    if not isinstance(dataset_id, str) or not DATASET_ID_RE.fullmatch(dataset_id):
        issues.append("Malformed dataset identifier.")
    if not isinstance(sample_id, str) or not SAMPLE_ID_RE.fullmatch(sample_id):
        issues.append("Malformed opaque sample identifier.")
    if not isinstance(document.get("reference_panel_sha256"), str) or not SHA256_RE.fullmatch(document.get("reference_panel_sha256", "")):
        issues.append("Missing or malformed reference-panel content digest.")
    reference_issues: list[str] = []
    if reference_manifest is None or reference_root is None:
        issues.append("Reference-panel metadata and independent byte-integrity evidence are required.")
    else:
        reference_issues = validate_reference_panel(reference_manifest, trusted_reviewers, now, reference_root)
        issues.extend(reference_issues)
        if isinstance(reference_manifest, dict):
            if _reference_panel_binding_digest(reference_manifest) != document.get("reference_panel_sha256"):
                issues.append("Reference-panel content does not match the manifest-bound digest.")

    provenance = document.get("provenance")
    if not isinstance(provenance, dict) or set(provenance) != {"source_catalog", "custodian_record_ref", "accession_refs"}:
        issues.append("Provenance must use source catalog and opaque custodian/accession references only.")
    else:
        if not isinstance(provenance["source_catalog"], str) or not provenance["source_catalog"]:
            issues.append("Missing provenance source catalog.")
        if not isinstance(provenance["custodian_record_ref"], str) or not OPAQUE_REF_RE.fullmatch(provenance["custodian_record_ref"]):
            issues.append("Malformed opaque custodian provenance reference.")
        refs = provenance["accession_refs"]
        if not isinstance(refs, list) or not refs or any(
            not isinstance(x, str) or not re.fullmatch(r"ACCREF-[A-Z0-9]{10}", x) for x in refs
        ) or len(set(refs)) != len(refs):
            issues.append("Accession references must be unique opaque references, not biological accessions.")

    root_path = Path(analysis_root).resolve()
    read_input = document.get("read_input")
    files: list[dict[str, Any]] = []
    if not isinstance(read_input, dict) or set(read_input) != {"layout", "format", "files"}:
        issues.append("Read-input record has missing or unknown fields.")
    else:
        layout, fmt = read_input["layout"], read_input["format"]
        if not isinstance(layout, str) or layout not in {"SINGLE", "PAIRED"} or not isinstance(fmt, str) or fmt not in {"FASTQ", "FASTQ_GZ"}:
            issues.append("Invalid read layout or expected input format.")
        files = read_input["files"] if isinstance(read_input["files"], list) else []
        expected_roles = {"R1"} if layout == "SINGLE" else {"R1", "R2"}
        roles = [f.get("role") for f in files if isinstance(f, dict)]
        if len(roles) != len(files) or any(not isinstance(role, str) for role in roles) or set(roles) != expected_roles or len(files) != len(expected_roles):
            issues.append("Read-file roles do not match declared layout.")
        for item in files:
            if not isinstance(item, dict) or set(item) != {"role", "path", "bytes", "sha256", "integrity_status"}:
                issues.append("Malformed read-file record.")
                continue
            status = item["integrity_status"]
            if not isinstance(status, str) or status not in {"METADATA_ONLY", "VERIFIED", "NOT_VERIFIED"}:
                issues.append("Invalid file integrity status.")
            path_valid = isinstance(item["path"], str) and not Path(item["path"]).is_absolute() and ".." not in Path(item["path"]).parts
            if not path_valid:
                issues.append("Read-file path must be relative and traversal-free.")
            elif BIO_PATH_LEAK_RE.search(item["path"]):
                issues.append("Read-file path contains a meaningful biological or truth-bearing label.")
            bytes_valid = isinstance(item["bytes"], int) and not isinstance(item["bytes"], bool) and item["bytes"] >= 0
            if not bytes_valid:
                issues.append("Invalid expected read-file byte count.")
            digest_valid = item["sha256"] is None or isinstance(item["sha256"], str) and bool(SHA256_RE.fullmatch(item["sha256"]))
            if not digest_valid:
                issues.append("Malformed read-file SHA-256.")
            if status == "VERIFIED" and (not item["sha256"] or not bytes_valid or item["bytes"] <= 0):
                issues.append("Verified file requires a positive byte count and SHA-256.")
            if status != "VERIFIED":
                issues.append(f"File-byte verification is not complete for {item['role']}.")
            if isinstance(item["path"], str) and isinstance(fmt, str):
                filename = Path(item["path"]).name.lower()
                suffixes = (".fastq", ".fq") if fmt == "FASTQ" else (".fastq.gz", ".fq.gz")
                if not filename.endswith(suffixes):
                    issues.append(f"File extension does not match declared input format for {item['role']}.")
            if verify_files and path_valid:
                relative = Path(item["path"])
                path = root_path / relative
                try:
                    path.resolve(strict=True).relative_to(root_path)
                except (OSError, ValueError):
                    issues.append(f"Read-file path escapes or is missing for {item['role']}.")
                    continue
                if path.is_symlink() or not path.is_file():
                    issues.append(f"Read-file bytes are unavailable for {item['role']}.")
                else:
                    digest = hashlib.sha256()
                    byte_count = 0
                    with path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            byte_count += len(chunk)
                            digest.update(chunk)
                    if bytes_valid and digest_valid and (byte_count != item["bytes"] or digest.hexdigest() != item["sha256"]):
                        issues.append(f"Read-file byte count or checksum mismatch for {item['role']}.")
                    if status != "VERIFIED":
                        issues.append(f"Read-file bytes exist but integrity status is not VERIFIED for {item['role']}.")

    gt = document.get("ground_truth_review")
    if not isinstance(gt, dict) or set(gt) != {"assayed_region_evidence", "full_length_reconstruction", "negative_control_assessment"}:
        issues.append("Ground-truth review must separate assayed-region, full-length, and negative-control assessment statuses.")
    else:
        enums = {
            "assayed_region_evidence": {"NOT_ASSESSED", "REVIEWED"},
            "full_length_reconstruction": {"NOT_ASSESSED", "REVIEWED"},
            "negative_control_assessment": {"NOT_CLAIMED", "PENDING", "REVIEWED"},
        }
        for key, allowed in enums.items():
            if not isinstance(gt[key], str) or gt[key] not in allowed:
                issues.append(f"Invalid ground-truth review status for {key}.")

    gates = document.get("gates")
    if not isinstance(gates, dict) or set(gates) != set(GATES):
        issues.append("Manifest must contain exactly the mandatory approval gates.")
    else:
        approval_ids, reviewer_ids = [], []
        for gate in GATES:
            record = gates[gate]
            if isinstance(record, dict):
                if record.get("approval_id"):
                    approval_ids.append(record["approval_id"])
                if record.get("reviewer_id"):
                    reviewer_ids.append(record["reviewer_id"])
            issues.extend(_check_approval(dataset_id or "", sample_id or "", gate, gates[gate],
                                          trusted_reviewers, now, _manifest_binding_digest(document)))
            if gate == "negative_control_review" and isinstance(gates[gate], dict) and gates[gate].get("status") == "NOT_APPLICABLE":
                if isinstance(gt, dict) and gt.get("negative_control_assessment") != "NOT_CLAIMED":
                    issues.append("Negative-control review cannot be N/A when the manifest records a control assessment.")
        # A positive/reconstruction claim cannot be inferred from a software-ready state.
        if isinstance(gt, dict) and gt.get("full_length_reconstruction") == "REVIEWED" and gates.get("ground_truth_review", {}).get("status") != "APPROVED":
            issues.append("Full-length reconstruction evidence lacks an approved independent review.")
        if len(approval_ids) != len(set(approval_ids)):
            issues.append("Approval identifier is reused across gates.")
        if len(reviewer_ids) != len(set(reviewer_ids)):
            issues.append("Independent approval roles must use distinct reviewers.")
        panel_approval = reference_manifest.get("approval") if isinstance(reference_manifest, dict) else None
        if isinstance(panel_approval, dict) and panel_approval.get("approval_id") in approval_ids:
            issues.append("Approval identifier is reused between the reference snapshot and dataset gates.")

    blinding_pass = False
    if scan_root is None:
        issues.append("Required operator-artifact disclosure scan root was not supplied.")
    else:
        scan_issues = scan_operator_artifacts(scan_root)
        issues.extend(scan_issues)
        try:
            inventory_digest = operator_inventory_digest(scan_root)
            blinding_approval = gates.get("blinding") if isinstance(gates, dict) else None
            if isinstance(blinding_approval, dict) and blinding_approval.get("evidence_sha256") != inventory_digest:
                issues.append("Blinding approval does not bind the current operator-artifact inventory.")
            blinding_pass = not scan_issues and isinstance(blinding_approval, dict) and blinding_approval.get("evidence_sha256") == inventory_digest
        except (OSError, ValueError):
            issues.append("Operator-artifact inventory could not be independently verified.")
    decision = "PREPARATION_COMPLETE_AWAITING_APPROVAL" if not issues else "BLOCKED"
    audit = []
    if isinstance(gates, dict):
        for gate in GATES:
            record = gates.get(gate)
            if isinstance(record, dict):
                audit.append({"gate": gate, **{key: record.get(key) for key in (
                    "approval_id", "reviewer_id", "key_id", "evidence_sha256", "manifest_sha256"
                )}})
    audit_digest = hashlib.sha256(json.dumps(audit, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    ref_ok = isinstance(reference_manifest, dict) and reference_root is not None and not reference_issues
    return {
        "schema_version": SCHEMA_VERSION, "decision": decision,
        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
        "dataset_id": dataset_id, "sample_id": sample_id,
        "readiness_categories": {
            "software_validation": "PASS" if not issues else "FAIL",
            "dataset_qualification": "PENDING_INDEPENDENT_REVIEW",
            "reference_integrity": "PASS" if ref_ok else "FAIL_OR_PENDING",
            "scientific_ground_truth_adequacy": "PENDING_INDEPENDENT_REVIEW",
            "data_use_permissions": "SIGNED_APPROVAL_REQUIRED",
            "blinding": "PASS" if blinding_pass else "FAIL",
            "independent_approvals": "PASS" if not issues else "FAIL",
            "biological_execution_authorisation": "NOT_GRANTED",
        },
        "audit_trail": audit, "audit_trail_sha256": audit_digest,
        "verification_timestamp": now.isoformat(), "issues": sorted(set(issues)),
    }


def validate_control_qualification(document: Any) -> list[str]:
    """Apply denominator and evidence-strength rules without inferring biological truth."""
    if not isinstance(document, dict):
        return ["Control qualification must be an object."]
    required = {"schema_version", "control_id", "control_class", "evidence_strength",
                "helper_status", "sequence_completeness", "study_group", "sensitivity_status",
                "specificity_status", "evaluation_status", "denominator_inclusion",
                "candidate_level_fp_reviewed", "sample_level_fp_reviewed"}
    issues = [f"Missing control qualification field: {key}." for key in sorted(required - set(document))]
    if set(document) - required:
        issues.append("Unknown control qualification field.")
    if document.get("schema_version") != "m21-control-qualification-v1":
        issues.append("Unsupported control qualification schema.")
    if not re.fullmatch(r"CTL-[A-Z0-9]{10}", str(document.get("control_id", ""))):
        issues.append("Malformed opaque control identifier.")
    allowed = {
        "control_class": {"POSITIVE", "SCREEN_NEGATIVE", "HELPER_COMPARATOR", "OTHER"},
        "evidence_strength": {"HIGH", "MODERATE", "LIMITED", "PENDING"},
        "helper_status": {"POSITIVE", "NEGATIVE", "UNKNOWN", "NOT_APPLICABLE"},
        "sequence_completeness": {"TERMINAL_VERIFIED", "NEAR_COMPLETE", "NOT_ASSESSED"},
        "sensitivity_status": {"ADEQUATE", "LIMITED", "UNKNOWN", "NOT_APPLICABLE"},
        "specificity_status": {"ADEQUATE", "LIMITED", "UNKNOWN", "NOT_ASSESSED"},
        "evaluation_status": {"EVALUABLE", "UNEVALUABLE", "PENDING"},
        "denominator_inclusion": {"INCLUDE", "EXCLUDE"},
    }
    for key, choices in allowed.items():
        if document.get(key) not in choices:
            issues.append(f"Invalid control qualification value for {key}.")
    if document.get("control_class") == "SCREEN_NEGATIVE" and (
        document.get("sensitivity_status") != "ADEQUATE"
        or document.get("evidence_strength") in {"LIMITED", "PENDING"}
    ):
        if document.get("evaluation_status") != "UNEVALUABLE" or document.get("denominator_inclusion") != "EXCLUDE":
            issues.append("Sensitivity-limited screen negatives must be unevaluable and excluded from denominators.")
    if document.get("evaluation_status") != "EVALUABLE" and document.get("denominator_inclusion") != "EXCLUDE":
        issues.append("Unevaluable or pending controls must be excluded from performance denominators.")
    if document.get("sequence_completeness") != "TERMINAL_VERIFIED" and document.get("control_class") == "POSITIVE":
        if document.get("evidence_strength") == "HIGH" and document.get("evaluation_status") == "EVALUABLE":
            issues.append("Near-complete or unassessed sequence ends cannot support a terminally verified claim.")
    if document.get("study_group") == "INDEPENDENT" and document.get("helper_status") == "UNKNOWN":
        issues.append("Independent-study helper status must be explicit or the control remains pending.")
    if document.get("study_group") not in {"WITHIN_STUDY", "INDEPENDENT"}:
        issues.append("Study group must distinguish within-study from independent-study validation.")
    if document.get("control_class") == "POSITIVE" and document.get("evaluation_status") == "EVALUABLE":
        if document.get("evidence_strength") not in {"HIGH", "MODERATE"}:
            issues.append("Performance-eligible positive controls require reviewed evidence.")
    if document.get("control_class") == "HELPER_COMPARATOR" and document.get("helper_status") not in {"POSITIVE", "NEGATIVE"}:
        issues.append("Helper comparison requires an explicit helper-positive or helper-negative status.")
    if not isinstance(document.get("candidate_level_fp_reviewed"), bool) or not isinstance(document.get("sample_level_fp_reviewed"), bool):
        issues.append("False-positive review must distinguish candidate-level and sample-level assessment.")
    return sorted(set(issues))


def _pair_id(header: str) -> tuple[str, str | None]:
    parts = header.split()
    token = parts[0]
    mate = None
    if token.endswith("/1") or token.endswith("/2"):
        mate, token = token[-1], token[:-2]
    elif len(parts) > 1 and re.match(r"[12]:", parts[1]):
        mate = parts[1][0]
    return token, mate


def validate_fastq(r1: str | Path, r2: str | Path | None = None,
                   thresholds: dict[str, float] | None = None,
                   max_records: int = 100_000_000,
                   limits: dict[str, float] | None = None) -> dict[str, Any]:
    """Stream FASTQ validation; runtime is checked cooperatively between records.

    This is not a hard wall-clock deadline: an individual read/decompression/database
    operation may run past the configured runtime before control returns to the check.
    """
    thresholds = thresholds or {}
    limits = limits or {}
    allowed_thresholds = {"min_reads", "min_length", "max_length", "min_mean_quality"}
    allowed_limits = {"max_records", "max_read_length", "max_decompressed_bytes", "max_runtime_seconds"}
    issues: list[str] = []
    if not isinstance(thresholds, dict):
        issues.append("QC thresholds must be an object.")
        thresholds = {}
    if not isinstance(limits, dict):
        issues.append("Validation limits must be an object.")
        limits = {}
    issues.extend(f"Unknown QC threshold: {x}." for x in set(thresholds) - allowed_thresholds)
    issues.extend(f"Unknown validation limit: {x}." for x in set(limits) - allowed_limits)

    def valid_number(value: Any, *, integer: bool = False) -> bool:
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (not integer or isinstance(value, int))
        )

    configured_limits = {
        "max_records": limits.get("max_records", max_records),
        "max_read_length": limits.get("max_read_length", 1_000_000),
        "max_decompressed_bytes": limits.get("max_decompressed_bytes", 100_000_000_000),
        "max_runtime_seconds": limits.get("max_runtime_seconds", 3600),
    }
    for name in ("max_records", "max_read_length", "max_decompressed_bytes"):
        value = configured_limits[name]
        if not valid_number(value, integer=True) or value <= 0:
            issues.append(f"Validation limit {name} must be a positive integer.")
    runtime_value = configured_limits["max_runtime_seconds"]
    if not valid_number(runtime_value) or runtime_value <= 0:
        issues.append("Validation limit max_runtime_seconds must be a positive finite number.")
    for name, value in thresholds.items():
        if name not in allowed_thresholds:
            continue
        if not valid_number(value):
            issues.append(f"QC threshold {name} must be a finite number.")
        elif name in {"min_reads", "min_length", "max_length"} and (
            value < (0 if name == "min_reads" else 1) or not float(value).is_integer()
        ):
            issues.append(f"QC threshold {name} must be a valid non-negative/positive integer.")
        elif name == "min_mean_quality" and not 0 <= value <= 93:
            issues.append("QC threshold min_mean_quality must be between 0 and 93.")
    if (
        valid_number(thresholds.get("min_length"))
        and valid_number(thresholds.get("max_length"))
        and thresholds["min_length"] > thresholds["max_length"]
    ):
        issues.append("QC threshold min_length cannot exceed max_length.")
    if issues:
        return {
            "status": "FAIL", "outcome": "INVALID_CONFIGURATION",
            "validation_mode": "INVALID_CONFIGURATION", "complete": False,
            "statistics": {
                "r1_records": 0, "r2_records": 0 if r2 is not None else None,
                "read_pairs": None, "min_read_length": None, "max_read_length": None,
                "read_length_histogram": {}, "mean_phred33_quality": None,
                "min_phred33_quality": None, "max_phred33_quality": None,
                "phred33_histogram": {}, "decompressed_bytes": {"R1": 0, "R2": 0},
                "duplicate_detection": "EXACT_DISK_BACKED_SQLITE",
            },
            "issues": sorted(set(issues)),
        }

    record_limit = configured_limits["max_records"]
    read_limit = configured_limits["max_read_length"]
    byte_limit = configured_limits["max_decompressed_bytes"]
    runtime_limit = float(runtime_value)
    started = time.monotonic()
    counters = {"R1": 0, "R2": 0}
    bytes_read = {"R1": 0, "R2": 0}
    lengths: dict[str, int] = {}
    qualities: dict[str, int] = {}
    quality_sum = quality_count = 0
    min_quality = max_quality = None
    min_length = max_length = None
    complete = True

    def records(path: Path, label: str, db: sqlite3.Connection):
        nonlocal min_length, max_length, min_quality, max_quality
        nonlocal quality_sum, quality_count
        opener = gzip.open if path.suffix.lower() == ".gz" else open
        try:
            with opener(path, "rt", encoding="ascii", newline="") as handle:
                while True:
                    if time.monotonic() - started > runtime_limit:
                        raise TimeoutError("FASTQ validation runtime limit exceeded.")
                    header = handle.readline(min(byte_limit + 1, 1_000_002))
                    if not header:
                        return
                    seq = handle.readline(min(read_limit + 2, byte_limit + 1))
                    plus = handle.readline(min(byte_limit + 1, 1_000_002))
                    quality = handle.readline(min(read_limit + 2, byte_limit + 1))
                    lines = (header, seq, plus, quality)
                    if any(len(line) > bound - 1 and not line.endswith(("\n", "\r")) for line, bound in (
                        (header, min(byte_limit + 1, 1_000_002)),
                        (seq, min(read_limit + 2, byte_limit + 1)),
                        (plus, min(byte_limit + 1, 1_000_002)),
                        (quality, min(read_limit + 2, byte_limit + 1)),
                    )):
                        raise ValueError("FASTQ line exceeds configured bounded-read limit.")
                    if any(line == "" for line in lines[1:]):
                        raise ValueError("Truncated FASTQ record.")
                    bytes_read[label] += sum(len(line.encode("ascii")) for line in lines)
                    if bytes_read[label] > byte_limit:
                        raise ValueError("FASTQ decompressed-byte limit exceeded.")
                    header, seq, plus, quality = (x.rstrip("\r\n") for x in lines)
                    if not header.startswith("@") or not header[1:].strip() or not seq or not plus.startswith("+") or len(seq) != len(quality):
                        raise ValueError("Malformed FASTQ record or sequence/quality length mismatch.")
                    if len(seq) > read_limit:
                        raise ValueError("FASTQ maximum read length exceeded.")
                    if any(ord(q) < 33 or ord(q) > 126 for q in quality):
                        raise ValueError("FASTQ quality character is outside the supported Phred+33 ASCII range.")
                    counters[label] += 1
                    if counters[label] > record_limit:
                        raise ValueError("FASTQ record limit exceeded; validation is incomplete.")
                    normalized, mate = _pair_id(header[1:])
                    try:
                        db.execute("INSERT INTO seen VALUES (?, ?)", (label, normalized))
                    except sqlite3.IntegrityError:
                        raise ValueError(f"Duplicate read identifier in {label} (exact disk-backed detection).")
                    length = len(seq)
                    lengths[str(length)] = lengths.get(str(length), 0) + 1
                    min_length = length if min_length is None else min(min_length, length)
                    max_length = length if max_length is None else max(max_length, length)
                    for char in quality:
                        q = ord(char) - 33
                        qualities[str(q)] = qualities.get(str(q), 0) + 1
                        quality_sum += q
                        quality_count += 1
                        min_quality = q if min_quality is None else min(min_quality, q)
                        max_quality = q if max_quality is None else max(max_quality, q)
                    yield normalized, mate
        except (OSError, UnicodeError, EOFError, gzip.BadGzipFile, TimeoutError, ValueError) as exc:
            raise ValueError(f"{label}: {type(exc).__name__}: {exc}") from exc

    try:
        with tempfile.TemporaryDirectory(prefix="m21-fastq-") as tmp:
            db = sqlite3.connect(Path(tmp) / "seen.sqlite")
            try:
                db.execute("CREATE TABLE seen (file TEXT NOT NULL, identifier TEXT NOT NULL, PRIMARY KEY(file, identifier))")
                left = records(Path(r1), "R1", db)
                right = records(Path(r2), "R2", db) if r2 is not None else None
                if right is None:
                    for _record in left:
                        pass
                else:
                    sentinel = object()
                    for pair in iter(lambda: (next(left, sentinel), next(right, sentinel)), (sentinel, sentinel)):
                        a, b = pair
                        if a is sentinel or b is sentinel:
                            issues.append("Paired FASTQ files have different record counts.")
                            complete = False
                            break
                        if a[0] != b[0] or a[1] == "2" or b[1] == "1":
                            issues.append("Paired FASTQ identifiers or mate suffixes are inconsistent.")
                            complete = False
                            break
            finally:
                db.close()
    except (ValueError, sqlite3.Error) as exc:
        issues.append(str(exc))
        complete = False
    r1_count, r2_count = counters["R1"], counters["R2"] if r2 is not None else None
    if "min_reads" in thresholds and r1_count < thresholds["min_reads"]:
        issues.append("Read count is below the configured minimum.")
    if min_length is not None and "min_length" in thresholds and min_length < thresholds["min_length"]:
        issues.append("Read length is below the configured minimum.")
    if max_length is not None and "max_length" in thresholds and max_length > thresholds["max_length"]:
        issues.append("Read length exceeds the configured maximum.")
    mean_quality = round(quality_sum / quality_count, 4) if quality_count else None
    if mean_quality is not None and "min_mean_quality" in thresholds and mean_quality < thresholds["min_mean_quality"]:
        issues.append("Mean quality is below the configured minimum.")
    stats = {
        "r1_records": r1_count, "r2_records": r2_count,
        "read_pairs": r1_count if r2 is not None and r1_count == r2_count else None,
        "min_read_length": min_length, "max_read_length": max_length,
        "read_length_histogram": dict(sorted(lengths.items(), key=lambda item: int(item[0]))),
        "mean_phred33_quality": mean_quality, "min_phred33_quality": min_quality,
        "max_phred33_quality": max_quality,
        "phred33_histogram": dict(sorted(qualities.items(), key=lambda item: int(item[0]))),
        "decompressed_bytes": bytes_read, "duplicate_detection": "EXACT_DISK_BACKED_SQLITE",
    }
    outcome = (
        "INCOMPLETE" if not complete else
        "COMPLETE_QUALITY_THRESHOLDS_FAILED" if issues else
        "COMPLETE_QUALITY_THRESHOLDS_PASSED"
    )
    return {"status": "PASS" if outcome == "COMPLETE_QUALITY_THRESHOLDS_PASSED" else "FAIL",
            "outcome": outcome,
            "validation_mode": "COMPLETE" if complete else "INCOMPLETE",
            "complete": complete, "statistics": stats, "issues": sorted(set(issues))}


def human_report(result: dict[str, Any]) -> str:
    lines = [f"Readiness decision: {result.get('decision', result.get('status', 'BLOCKED'))}"]
    if result.get("dataset_id"):
        lines.append(f"Dataset: {result['dataset_id']}")
    if result.get("sample_id"):
        lines.append(f"Opaque sample ID: {result['sample_id']}")
    lines.extend(f"- {item}" for item in result.get("issues", []))
    if not result.get("issues"):
        lines.append("All configured evidence and approval gates validated. This report does not launch or authorize execution on its own.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline M21 readiness checker; never downloads or runs discovery stages.")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="Validate a readiness manifest and local file digests.")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--trust-store")
    validate.add_argument("--analysis-root", required=True)
    validate.add_argument("--scan-root", required=True)
    validate.add_argument("--reference-manifest", required=True)
    validate.add_argument("--reference-root", required=True)
    validate.add_argument("--forbidden-token", action="append", default=[])
    validate.add_argument("--json-out")
    fastq = sub.add_parser("fastq-check", help="Check local FASTQ syntax and paired-read consistency.")
    fastq.add_argument("--r1", required=True)
    fastq.add_argument("--r2")
    fastq.add_argument("--thresholds-json")
    fastq.add_argument("--limits-json")
    fastq.add_argument("--json-out")
    ref = sub.add_parser("reference-check", help="Validate a reference-panel approval manifest.")
    ref.add_argument("--manifest", required=True)
    ref.add_argument("--trust-store")
    ref.add_argument("--reference-root", required=True)
    args = parser.parse_args(argv)
    try:
        trust = _load_trust_store(getattr(args, "trust_store", None))
        if args.command == "validate":
            document = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            reference_manifest = None
            if args.reference_manifest:
                reference_manifest = json.loads(Path(args.reference_manifest).read_text(encoding="utf-8"))
            result = validate_manifest(document, args.analysis_root, trust, scan_root=args.scan_root,
                                        reference_manifest=reference_manifest,
                                        reference_root=args.reference_root)
            if args.scan_root:
                result["issues"].extend(scan_operator_artifacts(args.scan_root, args.forbidden_token))
                result["issues"] = sorted(set(result["issues"]))
                if result["issues"]:
                    result["decision"] = "BLOCKED"
                    if result.get("readiness_categories"):
                        result["readiness_categories"]["blinding"] = "FAIL"
        elif args.command == "fastq-check":
            thresholds = json.loads(Path(args.thresholds_json).read_text()) if args.thresholds_json else {}
            limits = json.loads(Path(args.limits_json).read_text()) if args.limits_json else {}
            result = validate_fastq(args.r1, args.r2, thresholds, limits=limits)
        else:
            document = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            issues = validate_reference_panel(document, trust, reference_root=args.reference_root)
            result = {"decision": "APPROVED" if not issues else "BLOCKED", "issues": issues}
        print(human_report(result), end="")
        if getattr(args, "json_out", None):
            Path(args.json_out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if result.get("decision") in {"PREPARATION_COMPLETE_AWAITING_APPROVAL", "APPROVED"} or result.get("status") == "PASS" else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Readiness checker error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
