"""Safe, deterministic verification of Phase 7B evidence-package archives."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import m21_phase7_closure as closure
from . import m21_phase6_governance as phase6
from . import m21_phase7_evidence as phase7
from . import m21_phase7b_trust as trust

SCHEMA_VERSION = "m21-phase7b-evidence-package-v1"
MAX_FILES = 100
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
SCHEMA_VALIDATOR_UNAVAILABLE = "Required JSON Schema validation is unavailable."
OPTIONAL_KINDS = {"reference_file", "transition_artifact", "trust_registry_history"}
REQUIRED_KINDS = {
    "reference_panel", "scientific_approval", "control_qualification",
    "transition_evidence", "ci_results", "ci_statement", "ci_attestation",
    "reviewer_approvals", "trust_registry", "checkpoint_history",
    "custody_receipt", "audit_chain", "replay_inputs", "scientific_evidence",
}
SINGLETON_KINDS = REQUIRED_KINDS | {"trust_registry_history"}
REPLAY_INPUT_SCHEMA = "m21-phase7b-replay-inputs-v1"


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
    # Check all content-addressed archive facts before consulting the optional
    # schema validator. Missing validation tooling must not hide known tampering.
    issues: list[str] = []
    if not isinstance(manifest, dict):
        return {}, ["Evidence manifest is malformed."]
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
        if (not isinstance(artifact_id, str) or not artifact_id
                or not _safe_path(path) or path == "manifest.json" or path not in files
                or artifact_id in by_id or path in paths):
            issues.append("Artifact is missing, unsafe, duplicated, or substituted.")
            continue
        if kind in SINGLETON_KINDS and kind in seen_kinds:
            issues.append(f"Required artifact kind is duplicated: {kind}.")
            continue
        content = files[path]
        expected_size = item.get("size_bytes")
        expected_sha = item.get("sha256")
        if (not isinstance(expected_size, int) or isinstance(expected_size, bool)
                or not isinstance(expected_sha, str)
                or len(content) != expected_size
                or hashlib.sha256(content).hexdigest() != expected_sha):
            issues.append(f"Artifact integrity check failed: {artifact_id}.")
            continue
        by_id[artifact_id] = content
        paths.add(path)
        kinds.add(kind)
        seen_kinds.add(kind)
        listed.add(path)
    if kinds - REQUIRED_KINDS - OPTIONAL_KINDS:
        issues.append("Evidence package contains an unexpected artifact kind.")
    if REQUIRED_KINDS - kinds:
        issues.append("Evidence package is missing required artifact kinds.")
    if listed != set(files):
        issues.append("Evidence archive contains unlisted files.")
    schema_issues = _schema_valid("m21_phase7b_evidence_package.schema.json", manifest)
    if schema_issues is None:
        issues.append(SCHEMA_VALIDATOR_UNAVAILABLE)
    else:
        issues.extend(schema_issues)
    return by_id, sorted(set(issues))


def _replay_canonical_transitions(
    replay_inputs_bytes: bytes, manifest: dict[str, Any],
    artifacts: dict[str, bytes], files: dict[str, bytes],
    identity_registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Replay transition receipts and their content-addressed stage artifacts."""
    try:
        inputs = json.loads(replay_inputs_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return {"status": "FAIL", "issues": ["Canonical replay input is not valid JSON."]}
    if (not isinstance(inputs, dict)
            or set(inputs) != {
                "schema_version", "transition_receipts", "stage_artifact_ids",
                "chain_id", "local_checkpoints",
            }
            or inputs.get("schema_version") != REPLAY_INPUT_SCHEMA
            or not isinstance(inputs.get("transition_receipts"), list)
            or not isinstance(inputs.get("stage_artifact_ids"), dict)
            or not isinstance(inputs.get("chain_id"), str) or not inputs["chain_id"]
            or not isinstance(inputs.get("local_checkpoints"), list)):
        return {"status": "FAIL", "issues": ["Canonical replay input mapping is malformed."]}

    states = set(phase6.STATES[1:])
    mapping = inputs["stage_artifact_ids"]
    if set(mapping) != states:
        return {"status": "FAIL", "issues": ["Canonical replay is missing one or more transition stages."]}
    path_by_id = {
        item["artifact_id"]: item["path"]
        for item in manifest["artifacts"]
    }
    stage_paths: dict[str, dict[str, str]] = {}
    used_ids: set[str] = set()
    for state in phase6.STATES[1:]:
        entries = mapping.get(state)
        required = phase7.REQUIRED_TRANSITION_ARTIFACTS[state]
        if not isinstance(entries, dict) or set(entries) != required:
            return {"status": "FAIL", "issues": [f"Canonical replay artifact map is incomplete for {state}."]}
        stage_paths[state] = {}
        for artifact_type, artifact_id in entries.items():
            if (not isinstance(artifact_id, str) or artifact_id not in path_by_id
                    or artifact_id in used_ids or artifact_id not in artifacts):
                return {"status": "FAIL", "issues": ["Canonical replay references a missing or reused artifact ID."]}
            used_ids.add(artifact_id)
            stage_paths[state][artifact_type] = path_by_id[artifact_id]

    reviewers: dict[str, dict[str, Any]] = {}
    for identity_id, record in identity_registry.items():
        if "reviewer" not in record.get("roles", []):
            continue
        scopes = record.get("scopes", [])
        reviewers[identity_id] = {
            "reviewer_id": identity_id,
            "key_id": record["key_id"],
            "public_key_ed25519": record["public_key_ed25519"],
            "role": list(scopes),
            "scopes": list(scopes),
            "valid_from": record["valid_from"],
            "valid_until": record["valid_until"],
            "revoked": record["revoked"],
        }
    if not reviewers:
        return {"status": "FAIL", "issues": ["Authenticated trust registry has no canonical reviewers."]}

    try:
        with tempfile.TemporaryDirectory(prefix="m21-phase7b-replay-") as temporary:
            root = Path(temporary)
            for relative, content in files.items():
                destination = root.joinpath(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            result = phase7.verify_artifact_backed_transitions(
                inputs["transition_receipts"], stage_paths, root, reviewers,
            )
    except (OSError, ValueError, TypeError) as exc:
        return {"status": "FAIL", "issues": [f"Canonical Phase 7 replay could not run ({exc})."]}
    return result


def _blocked_result(decision: str, issues: list[str], **fields: Any) -> dict[str, Any]:
    return {
        "decision": decision,
        "issues": issues,
        **fields,
        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
        "biological_execution_authorized": False,
    }


def verify_package(
    package_path: str | Path, *, trust_anchor_path: str | Path,
    trust_anchor_fingerprint: str, trust_state_checkpoint_sha256: str,
    previous_trust_state_checkpoint_sha256: str | None = None,
    gh_binary: str = "gh",
) -> dict[str, Any]:
    """Check archive integrity and authenticated roots; never trust package PASS fields."""
    raw_package_path = Path(package_path)
    raw_anchor_path = Path(trust_anchor_path)
    if raw_package_path.is_symlink():
        return _blocked_result("FAIL", ["Evidence package must not be a symlink."])
    package_path = raw_package_path.resolve()
    manifest, files, issues = _read_archive(package_path)
    if issues:
        return _blocked_result("FAIL", issues)
    artifacts, issues = _validate_manifest(manifest, files)
    if issues:
        decision = (
            "INCOMPLETE"
            if issues == [SCHEMA_VALIDATOR_UNAVAILABLE]
            else "FAIL"
        )
        return _blocked_result(decision, issues)
    if raw_anchor_path.is_symlink():
        return _blocked_result("FAIL", ["Trust anchor must not be a symlink."])
    anchor_path = raw_anchor_path.resolve()
    repository_root = Path(__file__).resolve().parents[1]
    if anchor_path == package_path or anchor_path.is_relative_to(repository_root):
        return {"decision": "FAIL", "issues": ["Trust anchor must be provisioned outside the repository and package."]}
    try:
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _blocked_result("INCOMPLETE", ["Independently provisioned trust anchor is unavailable."])
    artifact_by_kind = {
        item["kind"]: artifacts[item["artifact_id"]]
        for item in manifest["artifacts"]
    }
    try:
        registry_data = json.loads(artifact_by_kind["trust_registry"].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _blocked_result("FAIL", ["Trust registry artifact is malformed JSON."])
    history_bytes = next(
        (artifacts[item["artifact_id"]] for item in manifest["artifacts"]
         if item["kind"] == "trust_registry_history"),
        None,
    )
    try:
        history = json.loads(history_bytes.decode("utf-8")) if history_bytes is not None else None
    except (UnicodeError, json.JSONDecodeError):
        return _blocked_result("FAIL", ["Trust-registry history is malformed JSON."])
    if history is not None and not isinstance(history, list):
        return _blocked_result("FAIL", ["Trust-registry history must be an array of signed registry bundles."])
    root_check = trust.verify_registry(
        registry_data, anchor,
        expected_anchor_fingerprint=trust_anchor_fingerprint,
        expected_state_checkpoint_sha256=trust_state_checkpoint_sha256,
        expected_previous_checkpoint_sha256=previous_trust_state_checkpoint_sha256,
        historical_registry_bundles=history,
    )
    if root_check.get("status") != "PASS":
        return _blocked_result(root_check.get("status", "FAIL"), root_check.get("issues", []))
    try:
        statement = json.loads(artifact_by_kind["ci_statement"].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _blocked_result("FAIL", ["CI statement artifact is malformed JSON."])
    ci_check = closure.verify_ci_acceptance(
        artifact_by_kind["ci_results"], statement, artifact_by_kind["ci_attestation"],
        expected_revision=manifest["software_revision"], gh_binary=gh_binary,
    )
    if ci_check.get("status") != "PASS":
        return _blocked_result(ci_check.get("status", "INCOMPLETE"), ci_check.get("issues", []))
    transition_check = _replay_canonical_transitions(
        artifact_by_kind["replay_inputs"], manifest, artifacts, files,
        root_check["identity_registry"],
    )
    if transition_check.get("status") != "PASS":
        return _blocked_result(
            transition_check.get("status", "FAIL"),
            transition_check.get("issues", ["Canonical Phase 7 replay failed."]),
        )
    try:
        replay_inputs = json.loads(artifact_by_kind["replay_inputs"].decode("utf-8"))
        reviewer_bundle = json.loads(artifact_by_kind["reviewer_approvals"].decode("utf-8"))
        retained_checkpoints = json.loads(artifact_by_kind["checkpoint_history"].decode("utf-8"))
        local_events = json.loads(artifact_by_kind["audit_chain"].decode("utf-8"))
        retention_receipt = json.loads(artifact_by_kind["custody_receipt"].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _blocked_result("FAIL", ["Custody or reviewer evidence is malformed JSON."])
    if (not isinstance(replay_inputs, dict)
            or not isinstance(replay_inputs.get("chain_id"), str)
            or not replay_inputs["chain_id"]
            or not isinstance(replay_inputs.get("local_checkpoints"), list)
            or not isinstance(retained_checkpoints, list)
            or not isinstance(local_events, list)
            or not isinstance(retention_receipt, dict)
            or not isinstance(reviewer_bundle, dict)
            or set(reviewer_bundle) != {"closure_package", "approvals"}
            or not isinstance(reviewer_bundle["approvals"], list)):
        return _blocked_result("FAIL", ["Custody or reviewer evidence package is incomplete."])
    closure_trust = {
        identity_id: {
            "reviewer_id": identity_id,
            "key_id": record["key_id"],
            "public_key_ed25519": record["public_key_ed25519"],
            "role": list(record["scopes"]),
            "scopes": list(record["scopes"]),
            "valid_from": record["valid_from"],
            "valid_until": record["valid_until"],
            "revoked": record["revoked"],
            "identity_class": record["identity_class"],
        }
        for identity_id, record in root_check["identity_registry"].items()
    }
    checkpoint_package = {
        "schema_version": "m21-phase7-retained-checkpoints-v1",
        "benchmark_snapshot_id": manifest["snapshot_id"],
        "dataset_id": manifest["snapshot_id"],
        "chain_id": replay_inputs["chain_id"],
        "retained_checkpoints": retained_checkpoints,
        "retention_receipt": retention_receipt,
    }
    checkpoint_check = closure.verify_checkpoint_retention(
        checkpoint_package, closure_trust, local_events=local_events,
        local_checkpoints=replay_inputs["local_checkpoints"],
        expected_snapshot=manifest["snapshot_id"],
    )
    if checkpoint_check.get("status") != "PASS":
        return _blocked_result(
            checkpoint_check.get("status", "FAIL"),
            checkpoint_check.get("issues", ["Independent custody verification failed."]),
        )
    components = {
        "reference_panel_evidence": transition_check.get("reference_panel_result"),
        "scientific_approval_evidence": transition_check.get("scientific_approval_result"),
        "canonical_transition_evidence": transition_check,
    }
    closure_check = closure.verify_closure_package(
        reviewer_bundle["closure_package"], reviewer_bundle["approvals"],
        closure_trust, verified_components=components,
        ci_verification=ci_check, checkpoint_verification=checkpoint_check,
    )
    decision = closure_check.get("decision", "INCOMPLETE")
    report_issues = list(closure_check.get("issues", []))
    if decision == "PASS":
        decision = "INCOMPLETE"
        report_issues.append("Synthetic evidence replay cannot establish operational readiness.")
    return _blocked_result(
        decision,
        report_issues,
        package_sha256=hashlib.sha256(package_path.read_bytes()).hexdigest(),
        manifest_sha256=trust.digest(manifest),
        artifact_count=len(artifacts),
        trust_registry_sha256=root_check["registry_sha256"],
        ci_attestation_status=ci_check["status"],
        canonical_transition_status=transition_check["status"],
        canonical_stage_count=len(transition_check.get("adapter_results", [])),
        checkpoint_retention_status=checkpoint_check["status"],
        closure_decision=closure_check.get("decision", "INCOMPLETE"),
    )


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
