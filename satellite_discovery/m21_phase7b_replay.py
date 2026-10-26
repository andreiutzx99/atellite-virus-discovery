"""Safe, deterministic verification of Phase 7B evidence-package archives."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import m21_phase7_closure as closure
from . import m21_phase7b_trust as trust

SCHEMA_VERSION = "m21-phase7b-evidence-package-v1"
MAX_FILES = 100
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
SCHEMA_VALIDATOR_UNAVAILABLE = "Required JSON Schema validation is unavailable."
REQUIRED_KINDS = {
    "reference_panel", "scientific_approval", "control_qualification",
    "transition_evidence", "ci_results", "ci_statement", "ci_attestation",
    "reviewer_approvals", "trust_registry", "checkpoint_history",
    "custody_receipt", "audit_chain", "replay_inputs", "scientific_evidence",
}


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))


def _schema_valid(name: str, value: Any) -> list[str] | None:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return None
    try:
        errors = Draft202012Validator(_load_schema(name)).iter_errors(value)
    except (OSError, ValueError, json.JSONDecodeError):
        return [f"Schema {name} could not be loaded."]
    return [f"{name}: {error.message}" for error in errors]


def _safe_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return (not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)
            and path.as_posix() == value)


def _read_archive(path: Path) -> tuple[dict[str, Any], dict[str, bytes], list[str]]:
    issues: list[str] = []
    if path.is_symlink() or not path.is_file():
        return {}, {}, ["Evidence package is not a regular file."]
    if path.stat().st_size > MAX_PACKAGE_BYTES:
        return {}, {}, ["Compressed evidence archive exceeds its size limit."]
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                return {}, {}, ["Evidence package exceeds the file-count limit."]
            names: set[str] = set()
            for info in infos:
                mode = info.external_attr >> 16
                if (not _safe_path(info.filename) or info.filename in names
                        or stat.S_ISLNK(mode) or info.is_dir()):
                    issues.append("Archive contains an unsafe, duplicate, or non-regular path.")
                    break
                names.add(info.filename)
                if (info.file_size > MAX_ARTIFACT_BYTES
                        or (info.compress_size == 0 and info.file_size > 0)
                        or (info.compress_size > 0
                            and info.file_size > info.compress_size * MAX_COMPRESSION_RATIO)):
                    issues.append("Archive member exceeds per-artifact or compression-ratio limits.")
                    break
            if issues:
                return {}, {}, issues
            if sum(info.file_size for info in infos) > MAX_PACKAGE_BYTES:
                return {}, {}, ["Evidence package exceeds the aggregate uncompressed-size limit."]
            if "manifest.json" not in names:
                return {}, {}, ["Evidence package manifest is missing."]
            manifest_bytes = archive.read("manifest.json")
            if len(manifest_bytes) > 1024 * 1024:
                return {}, {}, ["Evidence package manifest exceeds its size limit."]
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            files = {name: archive.read(name) for name in names if name != "manifest.json"}
            return manifest, files, []
    except (OSError, zipfile.BadZipFile, UnicodeError, json.JSONDecodeError):
        return {}, {}, ["Evidence package archive is unreadable or malformed."]


def _validate_manifest(manifest: Any, files: dict[str, bytes]) -> tuple[dict[str, bytes], list[str]]:
    issues = _schema_valid("m21_phase7b_evidence_package.schema.json", manifest)
    if issues is None:
        return {}, [SCHEMA_VALIDATOR_UNAVAILABLE]
    if not isinstance(manifest, dict):
        return {}, issues or ["Evidence manifest is malformed."]
    if manifest.get("schema_version") != SCHEMA_VERSION:
        issues.append("Unsupported evidence-package schema version.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) > MAX_FILES - 1:
        return {}, issues + ["Artifact inventory is malformed or too large."]
    by_id: dict[str, bytes] = {}
    paths: set[str] = set()
    kinds: set[str] = set()
    seen_kinds: set[str] = set()
    listed: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            issues.append("Artifact descriptor is malformed.")
            continue
        artifact_id, path, kind = item.get("artifact_id"), item.get("path"), item.get("kind")
        if (not _safe_path(path) or path == "manifest.json" or path not in files
                or artifact_id in by_id or path in paths):
            issues.append("Artifact is missing, unsafe, duplicated, or substituted.")
            continue
        if kind in REQUIRED_KINDS and kind in seen_kinds:
            issues.append(f"Required artifact kind is duplicated: {kind}.")
            continue
        content = files[path]
        if (len(content) != item.get("size_bytes")
                or hashlib.sha256(content).hexdigest() != item.get("sha256")):
            issues.append(f"Artifact integrity check failed: {artifact_id}.")
            continue
        by_id[artifact_id] = content
        paths.add(path)
        kinds.add(kind)
        seen_kinds.add(kind)
        listed.add(path)
    if kinds - REQUIRED_KINDS - {"reference_file", "transition_artifact"}:
        issues.append("Evidence package contains an unexpected artifact kind.")
    if REQUIRED_KINDS - kinds:
        issues.append("Evidence package is missing required artifact kinds.")
    if listed != set(files):
        issues.append("Evidence archive contains unlisted files.")
    return by_id, sorted(set(issues))


def verify_package(
    package_path: str | Path, *, trust_anchor_path: str | Path,
    trust_anchor_fingerprint: str, trust_state_checkpoint_sha256: str,
    previous_trust_state_checkpoint_sha256: str | None = None,
    gh_binary: str = "gh",
) -> dict[str, Any]:
    """Check archive integrity and authenticated roots; never trust package PASS fields."""
    raw_package_path = Path(package_path)
    raw_anchor_path = Path(trust_anchor_path)
    if raw_package_path.is_symlink() or raw_anchor_path.is_symlink():
        return {"decision": "FAIL", "issues": ["Package and trust anchor must not be symlinks."]}
    package_path = raw_package_path.resolve()
    anchor_path = raw_anchor_path.resolve()
    repository_root = Path(__file__).resolve().parents[1]
    if anchor_path == package_path or anchor_path.is_relative_to(repository_root):
        return {"decision": "FAIL", "issues": ["Trust anchor must be provisioned outside the repository and package."]}
    try:
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"decision": "INCOMPLETE", "issues": ["Independently provisioned trust anchor is unavailable."]}
    manifest, files, issues = _read_archive(package_path)
    if issues:
        return {"decision": "FAIL", "issues": issues}
    artifacts, issues = _validate_manifest(manifest, files)
    if issues:
        decision = "INCOMPLETE" if SCHEMA_VALIDATOR_UNAVAILABLE in issues else "FAIL"
        return {"decision": decision, "issues": issues}
    artifact_by_kind = {
        item["kind"]: artifacts[item["artifact_id"]]
        for item in manifest["artifacts"]
    }
    registry_data = json.loads(artifact_by_kind["trust_registry"].decode("utf-8"))
    root_check = trust.verify_registry(
        registry_data, anchor,
        expected_anchor_fingerprint=trust_anchor_fingerprint,
        expected_state_checkpoint_sha256=trust_state_checkpoint_sha256,
        expected_previous_checkpoint_sha256=previous_trust_state_checkpoint_sha256,
    )
    if root_check.get("status") != "PASS":
        return {"decision": root_check.get("status", "FAIL"), "issues": root_check.get("issues", [])}
    statement = json.loads(artifact_by_kind["ci_statement"].decode("utf-8"))
    ci_check = closure.verify_ci_acceptance(
        artifact_by_kind["ci_results"], statement, artifact_by_kind["ci_attestation"],
        expected_revision=manifest["software_revision"], gh_binary=gh_binary,
    )
    if ci_check.get("status") != "PASS":
        return {"decision": ci_check.get("status", "INCOMPLETE"), "issues": ci_check.get("issues", [])}
    # Component evidence remains raw and content-addressed in the package.
    # Until all Phase 7 scientific and transition inputs are replayed through
    # their canonical verifiers, the package cannot report closure PASS.
    return {
        "decision": "INCOMPLETE",
        "issues": [
            "Reference-panel, scientific-approval, control-qualification, transition, custody and reviewer-approval inputs require canonical replay before closure.",
        ],
        "package_sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
        "manifest_sha256": trust.digest(manifest),
        "artifact_count": len(artifacts),
        "trust_registry_sha256": root_check["registry_sha256"],
        "ci_attestation_status": ci_check["status"],
        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
        "biological_execution_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay M21 Phase 7B evidence packages.")
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Verify a content-addressed evidence archive.")
    verify.add_argument("evidence_package")
    verify.add_argument("--trust-anchor", required=True)
    verify.add_argument("--trust-anchor-fingerprint", required=True)
    verify.add_argument("--trust-state-checkpoint-sha256", required=True)
    verify.add_argument("--previous-trust-state-checkpoint-sha256")
    verify.add_argument("--gh-binary", default="gh")
    args = parser.parse_args(argv)
    result = verify_package(
        args.evidence_package, trust_anchor_path=args.trust_anchor,
        trust_anchor_fingerprint=args.trust_anchor_fingerprint,
        trust_state_checkpoint_sha256=args.trust_state_checkpoint_sha256,
        previous_trust_state_checkpoint_sha256=args.previous_trust_state_checkpoint_sha256,
        gh_binary=args.gh_binary,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result.get("decision") in {"PASS", "INCOMPLETE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
