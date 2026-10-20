"""Offline M21 benchmark governance checks. This module never downloads or runs stages."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import secrets
import stat
import sys
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
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
TEXT_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".txt", ".md", ".csv"}


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
                           analysis_root: str | Path) -> None:
    """Write a custodian-only mapping outside the analysis tree, mode 0600, no overwrite."""
    target = Path(key_path).absolute()
    root = Path(analysis_root).resolve()
    resolved_parent = target.parent.resolve(strict=True)
    resolved_target = resolved_parent / target.name
    if resolved_target == root or root in resolved_target.parents:
        raise ValueError("Truth key must be stored outside the analysis workspace.")
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
                    trusted_reviewers: dict[str, str], now: datetime) -> list[str]:
    prefix = f"gate {gate}"
    if not isinstance(record, dict):
        return [f"{prefix}: missing approval record."]
    allowed = {"status", "approval_id", "reviewer_id", "approved_at", "expires_at",
               "evidence_sha256", "signature_ed25519"}
    issues = [f"{prefix}: unknown approval fields."] if set(record) - allowed else []
    status = record.get("status")
    if not isinstance(status, str) or status not in APPROVAL_STATUSES:
        return issues + [f"{prefix}: invalid status."]
    if status != "APPROVED" and not (status == "NOT_APPLICABLE" and gate == "negative_control_review"):
        return issues + [f"{prefix}: approval is {status}."]
    for name, pattern in (
        ("approval_id", APPROVAL_ID_RE), ("reviewer_id", REVIEWER_ID_RE),
        ("evidence_sha256", SHA256_RE), ("signature_ed25519", SIGNATURE_RE),
    ):
        if not isinstance(record.get(name), str) or not pattern.fullmatch(record[name]):
            issues.append(f"{prefix}: missing or malformed {name}.")
    approved_at, expires_at = _parse_time(record.get("approved_at")), _parse_time(record.get("expires_at"))
    if not approved_at or not expires_at:
        issues.append(f"{prefix}: approval timestamps must be timezone-aware ISO-8601.")
    elif approved_at > now or expires_at <= now or expires_at <= approved_at:
        issues.append(f"{prefix}: approval is future-dated, expired, or has an invalid expiry.")
    reviewer = record.get("reviewer_id")
    key_text = trusted_reviewers.get(reviewer) if isinstance(reviewer, str) else None
    if key_text is None:
        issues.append(f"{prefix}: reviewer is not in the external trust store.")
    elif not issues:
        try:
            key = Ed25519PublicKey.from_public_bytes(base64.b64decode(key_text, validate=True))
            signature = base64.b64decode(record["signature_ed25519"], validate=True)
            key.verify(signature, _approval_payload(dataset_id, sample_id, gate, record))
        except (ValueError, InvalidSignature, TypeError):
            issues.append(f"{prefix}: signature verification failed.")
    return issues


def _load_trust_store(path: str | Path | None) -> dict[str, str]:
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(
        not REVIEWER_ID_RE.fullmatch(str(k)) or not isinstance(v, str) for k, v in data.items()
    ):
        raise ValueError("Malformed reviewer trust store.")
    return data


def _scan_leak_text(text: str, location: str) -> list[str]:
    issues = []
    if PRIVATE_KEY_RE.search(text) or re.search(r'"private_key"\s*:', text, re.I):
        issues.append(f"Private-key material detected in {location}.")
    if LEAK_KEYS.search(text):
        issues.append(f"Disallowed truth/identity field detected in {location}.")
    if ACCESSION_RE.search(text):
        issues.append(f"Biological accession-like identifier detected in {location}.")
    return issues


def scan_operator_artifacts(root: str | Path, forbidden_tokens: list[str] | None = None) -> list[str]:
    root = Path(root)
    issues: list[str] = []
    tokens = [x.casefold() for x in (forbidden_tokens or []) if x]
    if not root.is_dir():
        return ["Operator artifact directory is missing."]
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        issues.extend(_scan_leak_text(rel, rel))
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


def validate_reference_panel(document: Any, trusted_reviewers: dict[str, str],
                             now: datetime | None = None) -> list[str]:
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
            if not isinstance(ref, dict) or set(ref) != {"source", "accession_version", "sha256"}:
                issues.append(f"Reference record {idx} has missing or unknown provenance fields.")
            elif not all(isinstance(ref[k], str) and ref[k] for k in ("source", "accession_version")) or not SHA256_RE.fullmatch(str(ref["sha256"])):
                issues.append(f"Reference record {idx} has invalid provenance or digest.")
    approval = document.get("approval")
    if isinstance(approval, dict):
        status = approval.get("status")
        if status != "APPROVED":
            issues.append("Reference-panel independent review is not approved.")
        else:
            issues.extend(_check_approval(
                str(document.get("snapshot_id", "")), str(document.get("snapshot_id", "")),
                "reference_panel", approval, trusted_reviewers, now,
            ))
    else:
        issues.append("Reference-panel independent approval record is missing.")
    return issues


def validate_manifest(document: Any, analysis_root: str | Path,
                      trusted_reviewers: dict[str, str] | None = None,
                      now: datetime | None = None, verify_files: bool = True) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    trusted_reviewers = trusted_reviewers or {}
    issues: list[str] = []
    if not isinstance(document, dict):
        return {"decision": "BLOCKED", "issues": ["Manifest must be a JSON object."]}
    issues.extend(_scan_leak_text(json.dumps(document, sort_keys=True), "manifest"))
    top = {"schema_version", "dataset_id", "sample_id", "provenance", "read_input",
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
        for gate in GATES:
            issues.extend(_check_approval(dataset_id or "", sample_id or "", gate, gates[gate], trusted_reviewers, now))
            if gate == "negative_control_review" and isinstance(gates[gate], dict) and gates[gate].get("status") == "NOT_APPLICABLE":
                if isinstance(gt, dict) and gt.get("negative_control_assessment") != "NOT_CLAIMED":
                    issues.append("Negative-control review cannot be N/A when the manifest records a control assessment.")
        # A positive/reconstruction claim cannot be inferred from a software-ready state.
        if isinstance(gt, dict) and gt.get("full_length_reconstruction") == "REVIEWED" and gates.get("ground_truth_review", {}).get("status") != "APPROVED":
            issues.append("Full-length reconstruction evidence lacks an approved independent review.")

    decision = "READY_FOR_SEPARATELY_AUTHORISED_BENCHMARK" if not issues else "BLOCKED"
    return {"schema_version": SCHEMA_VERSION, "decision": decision, "dataset_id": dataset_id,
            "sample_id": sample_id, "issues": sorted(set(issues))}


def _read_fastq(path: Path, max_records: int) -> tuple[list[tuple[str, str, str]], list[str]]:
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    records, issues = [], []
    try:
        with opener(path, "rt", encoding="ascii", newline=None) as handle:
            while True:
                header = handle.readline()
                if not header:
                    break
                seq, plus, quality = handle.readline(), handle.readline(), handle.readline()
                if not seq or not plus or not quality:
                    issues.append("Truncated FASTQ record.")
                    break
                header, seq, plus, quality = (x.rstrip("\r\n") for x in (header, seq, plus, quality))
                if not header.startswith("@") or not header[1:].strip() or not seq or not plus.startswith("+") or len(seq) != len(quality):
                    issues.append("Malformed FASTQ record or sequence/quality length mismatch.")
                    break
                if any(ord(q) < 33 or ord(q) > 126 for q in quality):
                    issues.append("FASTQ quality character is outside the supported Phred+33 ASCII range.")
                    break
                records.append((header[1:], seq, quality))
                if len(records) > max_records:
                    issues.append("FASTQ record safety limit exceeded.")
                    break
    except (OSError, UnicodeError, EOFError) as exc:
        issues.append(f"FASTQ read failed: {type(exc).__name__}.")
    return records, issues


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
                   max_records: int = 100_000) -> dict[str, Any]:
    """Inspect local FASTQ only; thresholds are optional and never inferred."""
    thresholds = thresholds or {}
    allowed_thresholds = {"min_reads", "min_length", "max_length", "min_mean_quality"}
    issues = [f"Unknown QC threshold: {x}." for x in set(thresholds) - allowed_thresholds]
    first, errors = _read_fastq(Path(r1), max_records)
    issues.extend(errors)
    second = None
    if r2 is not None:
        second, errors = _read_fastq(Path(r2), max_records)
        issues.extend(errors)
        if len(first) != len(second):
            issues.append("Paired FASTQ files have different record counts.")
        ids1, ids2 = [_pair_id(r[0]) for r in first], [_pair_id(r[0]) for r in second]
        if any(x[0] == "" for x in ids1 + ids2) or [x[0] for x in ids1] != [x[0] for x in ids2]:
            issues.append("Paired FASTQ identifiers are missing or inconsistent.")
        if any(x[1] == "2" for x in ids1) or any(x[1] == "1" for x in ids2):
            issues.append("Paired FASTQ mate suffixes are reversed.")
    for label, records in (("R1", first), ("R2", second or [])):
        seen = set()
        for header, _, _ in records:
            normalized, _mate = _pair_id(header)
            if normalized in seen:
                issues.append(f"Duplicate read identifier in {label}.")
                break
            seen.add(normalized)
    lengths = [len(record[1]) for record in first + (second or [])]
    length_histogram: dict[str, int] = {}
    for length in lengths:
        key = str(length)
        length_histogram[key] = length_histogram.get(key, 0) + 1
    qualities = [ord(q) - 33 for record in first + (second or []) for q in record[2]]
    histogram: dict[str, int] = {}
    for quality in qualities:
        label = str(quality)
        histogram[label] = histogram.get(label, 0) + 1
    stats = {
        "r1_records": len(first), "r2_records": len(second) if second is not None else None,
        "read_pairs": len(first) if second is not None and len(first) == len(second) else None,
        "min_read_length": min(lengths) if lengths else None,
        "max_read_length": max(lengths) if lengths else None,
        "read_length_histogram": dict(sorted(length_histogram.items(), key=lambda pair: int(pair[0]))),
        "mean_phred33_quality": round(sum(qualities) / len(qualities), 4) if qualities else None,
        "min_phred33_quality": min(qualities) if qualities else None,
        "max_phred33_quality": max(qualities) if qualities else None,
        "phred33_histogram": dict(sorted(histogram.items(), key=lambda pair: int(pair[0]))),
    }
    if "min_reads" in thresholds and len(first) < thresholds["min_reads"]:
        issues.append("Read count is below the configured minimum.")
    if lengths and "min_length" in thresholds and min(lengths) < thresholds["min_length"]:
        issues.append("Read length is below the configured minimum.")
    if lengths and "max_length" in thresholds and max(lengths) > thresholds["max_length"]:
        issues.append("Read length exceeds the configured maximum.")
    if qualities and "min_mean_quality" in thresholds and stats["mean_phred33_quality"] < thresholds["min_mean_quality"]:
        issues.append("Mean quality is below the configured minimum.")
    return {"status": "PASS" if not issues else "FAIL", "statistics": stats, "issues": sorted(set(issues))}


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
    validate.add_argument("--scan-root")
    validate.add_argument("--forbidden-token", action="append", default=[])
    validate.add_argument("--json-out")
    fastq = sub.add_parser("fastq-check", help="Check local FASTQ syntax and paired-read consistency.")
    fastq.add_argument("--r1", required=True)
    fastq.add_argument("--r2")
    fastq.add_argument("--thresholds-json")
    ref = sub.add_parser("reference-check", help="Validate a reference-panel approval manifest.")
    ref.add_argument("--manifest", required=True)
    ref.add_argument("--trust-store")
    args = parser.parse_args(argv)
    try:
        trust = _load_trust_store(getattr(args, "trust_store", None))
        if args.command == "validate":
            document = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            result = validate_manifest(document, args.analysis_root, trust)
            if args.scan_root:
                result["issues"].extend(scan_operator_artifacts(args.scan_root, args.forbidden_token))
                result["issues"] = sorted(set(result["issues"]))
                if result["issues"]:
                    result["decision"] = "BLOCKED"
        elif args.command == "fastq-check":
            thresholds = json.loads(Path(args.thresholds_json).read_text()) if args.thresholds_json else {}
            result = validate_fastq(args.r1, args.r2, thresholds)
        else:
            document = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
            issues = validate_reference_panel(document, trust)
            result = {"decision": "APPROVED" if not issues else "BLOCKED", "issues": issues}
        print(human_report(result), end="")
        if getattr(args, "json_out", None):
            Path(args.json_out).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if result.get("decision") in {"READY_FOR_SEPARATELY_AUTHORISED_BENCHMARK", "APPROVED"} or result.get("status") == "PASS" else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Readiness checker error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
