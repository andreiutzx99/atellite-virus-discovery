"""Fail-closed validators for the M11 RNA MFE result bundle."""

import json
import math
from pathlib import Path
import re

from .m11_algorithms import (
    ACCOUNTING_SCHEMA,
    BUNDLE_SCHEMA,
    CONTRACT_VERSION,
    EVIDENCE_SCHEMA,
    FOLD_ACCOUNTING_SCHEMA,
    METHOD_ID,
    POLICY_IDS,
    PROFILE_ID,
    STAGE_VERSION,
    axes_for_branch,
    canonical_json,
    normalize_energy,
    sha256,
    stable_evidence_id,
    stable_request_id,
    validate_dot_bracket,
    validate_source,
)
from .sequence_downloader import checksum
from .m11_runtime import WHEEL_LOCK


_HASH = re.compile(r"^[0-9a-f]{64}$")
_BRANCH_STATUSES = {
    "PREDICTION_REPORTED", "INPUT_INVALID", "SEQUENCE_UNAVAILABLE",
    "INSUFFICIENT_INFORMATION", "NOT_APPLICABLE", "NOT_SELECTED",
    "DEPENDENCY_UNAVAILABLE", "EXECUTION_FAILED", "OUTPUT_INVALID",
    "INTERRUPTED", "TRUNCATED", "NOT_STARTED", "RUNNING",
}
_INPUT_STATUSES = {
    "INPUT_VALID", "INPUT_INVALID", "SEQUENCE_UNAVAILABLE",
    "COMPLETE_EMPTY_INPUT_SET",
}
_OUTPUT_TYPES = {
    "candidate_accounting.jsonl": "m11_candidate_accounting",
    "fold_accounting.jsonl": "m11_fold_accounting",
    "rna_structure_evidence.jsonl": "m11_rna_structure_evidence",
    "mfe_raw_results.jsonl": "m11_mfe_raw_results",
}


def _require_hash(value, label):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("M11 JSON artifact is unreadable") from error
    if not isinstance(value, dict):
        raise ValueError("M11 JSON artifact must contain an object")
    return value


def _read_jsonl(path, allow_empty=False):
    try:
        payload = Path(path).read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("M11 JSONL artifact is unreadable") from error
    if not payload:
        if allow_empty:
            return []
        raise ValueError("M11 JSONL artifact is empty")
    if b"\r" in payload or not payload.endswith(b"\n"):
        raise ValueError("M11 JSONL artifact must end with one LF")
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"M11 JSONL row {number} is malformed") from error
        if not isinstance(row, dict) or canonical_json(row) + "\n" != line + "\n":
            raise ValueError(f"M11 JSONL row {number} is not canonical JSON")
        rows.append(row)
    return rows


def validate_candidate_accounting(path):
    rows = _read_jsonl(path)
    header, candidates = rows[0], rows[1:]
    if (
        header.get("record_type") != "manifest"
        or header.get("schema") != ACCOUNTING_SCHEMA
        or header.get("stage_version") != STAGE_VERSION
        or header.get("contract_version") != CONTRACT_VERSION
        or header.get("input_status") not in _INPUT_STATUSES
        or header.get("aggregate_status") not in {"COMPLETE", "PARTIAL"}
    ):
        raise ValueError("M11 candidate-accounting header is invalid")
    if type(header.get("candidate_count")) is not int or header["candidate_count"] < 0:
        raise ValueError("M11 candidate count is invalid")
    for field in ("expected_fold_count", "accounted_fold_count"):
        if type(header.get(field)) is not int or header[field] < 0:
            raise ValueError(f"M11 candidate-accounting {field} is invalid")
    if len(candidates) != header["candidate_count"]:
        raise ValueError("M11 candidate count does not match its records")
    candidate_set = header.get("candidate_set")
    if not isinstance(candidate_set, dict) or (
        candidate_set.get("artifact_type") != "m8_candidate_sequence_set"
        or candidate_set.get("validation_state") != "valid"
        or not isinstance(candidate_set.get("artifact_id"), str)
        or type(candidate_set.get("size_bytes")) is not int
        or candidate_set["size_bytes"] <= 0
    ):
        raise ValueError("M11 candidate-set provenance is invalid")
    _require_hash(candidate_set.get("sha256"), "candidate_set.sha256")
    _require_hash(header.get("configuration_sha256"), "configuration_sha256")
    configuration = header.get("configuration")
    if not isinstance(configuration, dict) or (
        sha256(canonical_json(configuration).encode("utf-8"))
        != header["configuration_sha256"]
    ):
        raise ValueError("M11 configuration digest is inconsistent")
    if (
        configuration.get("contract_version") != CONTRACT_VERSION
        or configuration.get("method_id") != METHOD_ID
        or configuration.get("profile_id") != PROFILE_ID
        or configuration.get("policy_ids") != POLICY_IDS
        or configuration.get("resource_enforcement_policy") not in {
            "POSIX_RLIMIT_AS_AND_CHILD_PROCESS_TIMEOUT",
            "WINDOWS_JOB_OBJECT_PROCESS_MEMORY_AND_CHILD_PROCESS_TIMEOUT",
        }
    ):
        raise ValueError("M11 normalized configuration violates the frozen profile")
    _require_hash(header.get("run_identity"), "run_identity")
    implementation = header.get("implementation")
    if not isinstance(implementation, dict):
        raise ValueError("M11 implementation identity is missing")
    expected_run_identity = sha256(canonical_json({
        "stage": "m11_rna_mfe",
        "stage_version": STAGE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "candidate_sequence_set_sha256": candidate_set["sha256"],
        "configuration_sha256": header["configuration_sha256"],
        "implementation": implementation,
    }).encode("utf-8"))
    if expected_run_identity != header["run_identity"]:
        raise ValueError("M11 run identity is inconsistent with its inputs")
    identities = set()
    for candidate in candidates:
        if candidate.get("record_type") != "candidate":
            raise ValueError("M11 candidate accounting record type is invalid")
        candidate_id, sequence_id = candidate.get("candidate_id"), candidate.get("sequence_id")
        if (
            not isinstance(candidate_id, str) or not candidate_id
            or not isinstance(sequence_id, str) or not sequence_id
            or (candidate_id, sequence_id) in identities
        ):
            raise ValueError("M11 candidate identity is missing or duplicated")
        identities.add((candidate_id, sequence_id))
        if candidate.get("candidate_set_sha256") != candidate_set["sha256"]:
            raise ValueError("M11 candidate set hash does not match its header")
        if candidate.get("input_status") not in {
            "INPUT_VALID", "INPUT_INVALID", "SEQUENCE_UNAVAILABLE",
        }:
            raise ValueError("M11 candidate input status is invalid")
        if type(candidate.get("sequence_bytes_available")) is not bool:
            raise ValueError("M11 source-byte availability must be boolean")
        source = candidate.get("source_sequence")
        if candidate["sequence_bytes_available"]:
            if not isinstance(source, str) or not source:
                raise ValueError("M11 available source bytes are missing")
            state, _upper = validate_source(source)
            _require_hash(candidate.get("source_sha256"), "source_sha256")
            if (
                state != "INPUT_VALID"
                or sha256(source.encode("ascii")) != candidate["source_sha256"]
                or len(source) != candidate.get("source_length")
                or candidate["input_status"] not in {"INPUT_VALID", "INPUT_INVALID"}
            ):
                raise ValueError("M11 candidate source identity is inconsistent")
        elif source is not None or candidate["input_status"] not in {
            "SEQUENCE_UNAVAILABLE", "INPUT_INVALID",
        }:
            raise ValueError("M11 unavailable source is inconsistently recorded")
        elif candidate.get("source_sha256") is not None:
            _require_hash(candidate["source_sha256"], "source_sha256")
        source_artifact = candidate.get("source_artifact")
        if not isinstance(source_artifact, dict) or not source_artifact.get("artifact_id"):
            raise ValueError("M11 source-artifact identity is missing")
        _require_hash(source_artifact.get("sha256"), "source_artifact.sha256")
        source_ref = candidate_set.get("source_artifact")
        if isinstance(source_ref, dict) and (
            source_artifact.get("artifact_id") != source_ref.get("path")
            or source_artifact.get("sha256") != source_ref.get("sha256")
        ):
            raise ValueError("M11 candidate source-artifact identity changed")
    sort_keys = [
        (row["candidate_id"], row["sequence_id"], row["manifest_ordinal"])
        for row in candidates
    ]
    if sort_keys != sorted(sort_keys):
        raise ValueError("M11 candidate accounting records are not canonically ordered")
    ordinals = [row.get("manifest_ordinal") for row in candidates]
    if any(type(value) is not int for value in ordinals) or sorted(ordinals) != list(
        range(len(candidates))
    ):
        raise ValueError("M11 candidate manifest ordinals are missing or duplicated")
    return {
        "schema": ACCOUNTING_SCHEMA,
        "candidate_count": len(candidates),
        "input_status": header["input_status"],
        "aggregate_status": header["aggregate_status"],
        "expected_fold_count": header.get("expected_fold_count"),
        "accounted_fold_count": header.get("accounted_fold_count"),
    }


def validate_fold_accounting(path):
    rows = _read_jsonl(path, allow_empty=True)
    identities = set()
    allowed_axes = set(_BRANCH_STATUSES)
    for row in rows:
        if row.get("record_type") != "fold_request" or row.get("schema") != FOLD_ACCOUNTING_SCHEMA:
            raise ValueError("M11 fold-accounting record type or schema is invalid")
        request_id = row.get("request_id")
        _require_hash(request_id, "request_id")
        if request_id in identities:
            raise ValueError("M11 fold request identities must be unique")
        identities.add(request_id)
        for name in ("candidate_id", "sequence_id"):
            if not isinstance(row.get(name), str) or not row[name]:
                raise ValueError(f"M11 fold request {name} is missing")
        if row.get("branch_status") not in allowed_axes:
            raise ValueError("M11 fold branch status is invalid")
        expected_axes = axes_for_branch(row["branch_status"])
        for name, expected in expected_axes.items():
            if row.get(name) != expected:
                raise ValueError(f"M11 {name} conflicts with branch status")
        if row.get("method_id") != METHOD_ID or row.get("profile_id") != PROFILE_ID:
            raise ValueError("M11 fold method/profile identity is invalid")
        if row.get("orientation") != "AS_SUPPLIED" or row.get(
                "coordinate_system") != "ZERO_BASED_HALF_OPEN_SOURCE":
            raise ValueError("M11 fold orientation or coordinate system is invalid")
        _require_hash(row.get("run_identity"), "run_identity")
        if row.get("policy_ids") != POLICY_IDS:
            raise ValueError("M11 fold policy identity is invalid")
        if type(row.get("candidate_ordinal")) is not int or row["candidate_ordinal"] < 0:
            raise ValueError("M11 candidate ordinal is invalid")
        if type(row.get("request_ordinal")) is not int:
            raise ValueError("M11 request ordinal is invalid")
        region = row.get("source_region")
        if region is not None and (
            not isinstance(region, dict)
            or type(region.get("start")) is not int
            or type(region.get("end")) is not int
        ):
            raise ValueError("M11 fold region is malformed")
        if stable_request_id(
            row["candidate_id"], row["sequence_id"], row.get("source_sha256"),
            region.get("start") if region else None,
            region.get("end") if region else None,
        ) != request_id:
            raise ValueError("M11 request identity is inconsistent")
        limits = row.get("effective_limits")
        if not isinstance(limits, dict):
            raise ValueError("M11 fold request limits are missing")
        for name in ("max_fold_symbols", "max_folds_per_run", "memory_bytes_per_fold"):
            if type(limits.get(name)) is not int or limits[name] <= 0:
                raise ValueError("M11 fold request has invalid finite limits")
        timeout = limits.get("timeout_seconds_per_fold")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("M11 timeout limit is invalid")
        if row["branch_status"] == "PREDICTION_REPORTED":
            _require_hash(row.get("evidence_id"), "evidence_id")
            _require_hash(row.get("raw_engine_result_sha256"), "raw_engine_result_sha256")
            if type(row.get("raw_result_row")) is not int or row["raw_result_row"] < 1:
                raise ValueError("M11 raw result row reference is invalid")
        elif row.get("evidence_id") is not None or row.get("raw_engine_result_sha256") is not None:
            raise ValueError("M11 non-prediction branch must not link fabricated evidence")
    return {"schema": FOLD_ACCOUNTING_SCHEMA, "request_count": len(rows)}


def validate_structure_evidence(path):
    rows = _read_jsonl(path, allow_empty=True)
    identifiers = set()
    requests = set()
    for row in rows:
        if row.get("record_type") != "RNA_STRUCTURE_EVIDENCE" or row.get("schema") != EVIDENCE_SCHEMA:
            raise ValueError("M11 structure evidence schema is invalid")
        evidence_id, request_id = row.get("evidence_id"), row.get("request_id")
        _require_hash(evidence_id, "evidence_id")
        _require_hash(request_id, "request_id")
        if evidence_id in identifiers or request_id in requests:
            raise ValueError("M11 structure evidence identities are duplicated")
        identifiers.add(evidence_id)
        requests.add(request_id)
        _require_hash(row.get("source_sha256"), "source_sha256")
        _require_hash(row.get("candidate_set_sha256"), "candidate_set_sha256")
        _require_hash(row.get("view_sha256"), "view_sha256")
        _require_hash(row.get("raw_engine_result_sha256"), "raw_engine_result_sha256")
        source = row.get("source_sequence")
        source_state, _ = validate_source(source)
        if (
            source_state != "INPUT_VALID"
            or sha256(source.encode("ascii")) != row["source_sha256"]
            or len(source) != row.get("source_sequence_length")
        ):
            raise ValueError("M11 evidence source identity is invalid")
        region = row.get("source_region")
        if not isinstance(region, dict):
            raise ValueError("M11 evidence source region is missing")
        start, end = region.get("start"), region.get("end")
        if type(start) is not int or type(end) is not int or not (0 <= start < end <= len(source)):
            raise ValueError("M11 evidence region coordinates are invalid")
        molecule = row.get("molecule_type")
        if not isinstance(molecule, str) or molecule.upper() not in {"DNA", "RNA"}:
            raise ValueError("M11 evidence molecule declaration is invalid")
        selected = source[start:end].upper()
        view = selected.replace("T", "U") if molecule.upper() == "DNA" else selected
        if (
            row.get("view_sequence") != view
            or sha256(b"M11-RNA-VIEW-v1\0" + view.encode("ascii")) != row["view_sha256"]
            or len(view) != row.get("view_length")
        ):
            raise ValueError("M11 RNA view does not match source and transformation")
        canonical = set("ACGU" if molecule.upper() == "RNA" else "ACGT")
        if (
            (molecule.upper() == "RNA" and "T" in source.upper())
            or (molecule.upper() == "DNA" and "U" in source.upper())
            or any(symbol not in canonical for symbol in selected)
        ):
            raise ValueError("M11 evidence violates molecule or fold-alphabet policy")
        expected_transformation = (
            "ASCII_UPPERCASE_AND_DNA_T_TO_RNA_U"
            if molecule.upper() == "DNA" else "ASCII_UPPERCASE"
        )
        if (
            row.get("transformation") != expected_transformation
            or row.get("view_policy") != POLICY_IDS["rna_view"]
            or row.get("coordinate_system") != "ZERO_BASED_HALF_OPEN_SOURCE"
            or row.get("coordinate_map") != {
                "kind": "IDENTITY_OFFSET",
                "view_start": 0,
                "view_end": len(view),
                "source_start": start,
                "source_end": end,
                "one_to_one": True,
            }
        ):
            raise ValueError("M11 coordinate map or RNA-view policy is inconsistent")
        expected_request = stable_request_id(
            row["candidate_id"], row["sequence_id"], row["source_sha256"], start, end)
        if expected_request != request_id:
            raise ValueError("M11 request identity does not match its source region")
        if row.get("method_id") != METHOD_ID or row.get("profile_id") != PROFILE_ID:
            raise ValueError("M11 evidence method/profile is invalid")
        if row.get("viennarna_version") != "2.7.2" or row.get("orientation") != "AS_SUPPLIED":
            raise ValueError("M11 evidence engine or orientation is invalid")
        if row.get("branch_status") != "PREDICTION_REPORTED" or row.get(
                "evidence_status") != "EVIDENCE_FOUND":
            raise ValueError("M11 evidence status is invalid")
        if not validate_dot_bracket(row.get("mfe_structure_dot_bracket"), len(view)):
            raise ValueError("M11 dot-bracket structure is malformed")
        if row.get("mfe_energy_hex") != float.fromhex(
                row["mfe_energy_hex"]).hex() or row.get(
                    "mfe_energy_kcal_mol") != normalize_energy(
                        float.fromhex(row["mfe_energy_hex"])):
            raise ValueError("M11 normalized energy does not match raw energy")
        model = row.get("effective_model_details")
        if (
            not isinstance(model, dict)
            or model.get("temperature") != 37.0
            or model.get("dangles") != 2
            or model.get("parameter_set") != "TURNER_2004_BUILTIN"
        ):
            raise ValueError("M11 effective model details do not match the frozen profile")
        source_artifact = row.get("source_artifact")
        if not isinstance(source_artifact, dict) or not source_artifact.get("artifact_id"):
            raise ValueError("M11 evidence source-artifact identity is missing")
        _require_hash(source_artifact.get("sha256"), "source_artifact.sha256")
        limits = row.get("effective_limits")
        if not isinstance(limits, dict) or any(
            type(limits.get(name)) is not int or limits[name] <= 0
            for name in (
                "max_fold_symbols", "max_folds_per_run", "memory_bytes_per_fold",
            )
        ):
            raise ValueError("M11 evidence resource limits are invalid")
        timeout = limits.get("timeout_seconds_per_fold")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
            or row.get("resource_enforcement_policy") not in {
                "POSIX_RLIMIT_AS_AND_CHILD_PROCESS_TIMEOUT",
                "WINDOWS_JOB_OBJECT_PROCESS_MEMORY_AND_CHILD_PROCESS_TIMEOUT",
            }
        ):
            raise ValueError("M11 evidence timeout or enforcement policy is invalid")
        _require_hash(row.get("run_identity"), "run_identity")
        runtime = row.get("runtime_identity")
        if not isinstance(runtime, dict) or runtime.get("status") != "available":
            raise ValueError("M11 evidence lacks an available pinned runtime identity")
        if (
            runtime.get("engine") != "ViennaRNA"
            or runtime.get("version") != "2.7.2"
            or not isinstance(runtime.get("native_library_sha256"), str)
            or not _HASH.fullmatch(runtime["native_library_sha256"])
            or not isinstance(runtime.get("installed_files_sha256"), str)
            or not _HASH.fullmatch(runtime["installed_files_sha256"])
            or not any(
                runtime.get("wheel_filename") == filename
                and runtime.get("wheel_sha256") == digest
                for filename, digest in WHEEL_LOCK.values()
            )
        ):
            raise ValueError("M11 evidence runtime identity is not one of the pinned builds")
        evidence_hash = row.get("evidence_sha256")
        _require_hash(evidence_hash, "evidence_sha256")
        identity_payload = dict(row)
        del identity_payload["evidence_sha256"]
        if sha256(canonical_json(identity_payload).encode("utf-8")) != evidence_hash:
            raise ValueError("M11 normalized evidence digest is inconsistent")
        if evidence_id != stable_evidence_id(
            row.get("run_identity"), request_id
        ):
            raise ValueError("M11 evidence identity is not derived from its run")
    return {"schema": EVIDENCE_SCHEMA, "evidence_count": len(rows)}


def validate_raw_results(path):
    rows = _read_jsonl(path, allow_empty=True)
    requests = set()
    for row in rows:
        if row.get("record_type") != "raw_engine_result":
            raise ValueError("M11 raw-result record type is invalid")
        request_id = row.get("request_id")
        _require_hash(request_id, "request_id")
        if request_id in requests:
            raise ValueError("M11 raw result request identity is duplicated")
        requests.add(request_id)
        envelope = row.get("raw_engine_result")
        if not isinstance(envelope, dict) or set(envelope) != {"dot_bracket", "energy_hex"}:
            raise ValueError("M11 raw API result envelope is malformed")
        try:
            energy = float.fromhex(envelope["energy_hex"])
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("M11 raw energy representation is invalid") from error
        if not math.isfinite(energy) or energy.hex() != envelope["energy_hex"]:
            raise ValueError("M11 raw energy representation is invalid")
        if not isinstance(envelope["dot_bracket"], str):
            raise ValueError("M11 raw dot-bracket result is invalid")
        _require_hash(row.get("raw_engine_result_sha256"), "raw_engine_result_sha256")
        if sha256(canonical_json(envelope).encode("utf-8")) != row["raw_engine_result_sha256"]:
            raise ValueError("M11 raw API result digest is inconsistent")
    return {"schema": "m11-mfe-raw-results-v1", "raw_result_count": len(rows)}


def validate_bundle(path):
    bundle_path = Path(path)
    bundle = _read_json(bundle_path)
    if (
        bundle.get("schema") != BUNDLE_SCHEMA
        or bundle.get("stage") != "m11_rna_mfe"
        or bundle.get("stage_version") != STAGE_VERSION
        or bundle.get("contract_version") != CONTRACT_VERSION
        or bundle.get("input_status") not in _INPUT_STATUSES
        or bundle.get("aggregate_status") not in {"COMPLETE", "PARTIAL"}
    ):
        raise ValueError("M11 result bundle header is invalid")
    source_inputs = bundle.get("source_inputs")
    source = (
        source_inputs.get("candidate_sequence_set")
        if isinstance(source_inputs, dict) else None
    )
    if not isinstance(source, dict) or source.get("validation_state") != "valid" or (
        source.get("artifact_type") != "m8_candidate_sequence_set"
        or not isinstance(source.get("artifact_id"), str)
        or type(source.get("size_bytes")) is not int
        or source["size_bytes"] <= 0
    ):
        raise ValueError("M11 result bundle lacks validated candidate provenance")
    _require_hash(source.get("sha256"), "candidate_sequence_set.sha256")
    _require_hash(bundle.get("run_identity"), "run_identity")
    outputs = bundle.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != set(_OUTPUT_TYPES):
        raise ValueError("M11 result bundle output list is incomplete")
    details = {}
    for name, artifact_type in _OUTPUT_TYPES.items():
        descriptor = outputs[name]
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("artifact_type") != artifact_type
            or descriptor.get("path") != name
            or descriptor.get("role") != artifact_type
        ):
            raise ValueError(f"M11 output descriptor {name} is invalid")
        _require_hash(descriptor.get("sha256"), f"{name}.sha256")
        if type(descriptor.get("size_bytes")) is not int or descriptor["size_bytes"] < 0:
            raise ValueError(f"M11 output descriptor {name} has an invalid size")
        target = bundle_path.parent / name
        if target.is_symlink() or not target.is_file():
            raise ValueError(f"M11 bundle child artifact {name} is missing")
        if target.stat().st_size != descriptor["size_bytes"] or checksum(target) != descriptor["sha256"]:
            raise ValueError(f"M11 bundle child artifact {name} failed integrity validation")
        from .artifact_contracts import validate_artifact
        details[name] = validate_artifact(target, artifact_type)
    fold_rows = _read_jsonl(bundle_path.parent / "fold_accounting.jsonl", allow_empty=True)
    evidence_rows = _read_jsonl(bundle_path.parent / "rna_structure_evidence.jsonl", allow_empty=True)
    raw_rows = _read_jsonl(bundle_path.parent / "mfe_raw_results.jsonl", allow_empty=True)
    candidate_rows = _read_jsonl(bundle_path.parent / "candidate_accounting.jsonl")
    header = candidate_rows[0]
    if (
        header.get("candidate_set", {}).get("sha256") != source["sha256"]
        or header.get("aggregate_status") != bundle["aggregate_status"]
        or header.get("input_status") != bundle["input_status"]
        or header.get("run_identity") != bundle.get("run_identity")
    ):
        raise ValueError("M11 bundle and candidate-accounting identities disagree")
    candidate_ref = header.get("candidate_set")
    if not isinstance(candidate_ref, dict) or (
        any(
            source.get(field) != candidate_ref.get(field)
            for field in ("artifact_id", "artifact_type", "sha256", "size_bytes")
        )
        or bundle.get("configuration") != header.get("configuration")
        or bundle.get("configuration_sha256")
        != header.get("configuration_sha256")
        or bundle.get("implementation") != header.get("implementation")
        or bundle.get("policy_ids") != POLICY_IDS
        or bundle.get("method_id") != METHOD_ID
        or bundle.get("profile_id") != PROFILE_ID
    ):
        raise ValueError("M11 bundle provenance or effective configuration is inconsistent")
    expected_requests = {}
    candidate_records = candidate_rows[1:]
    explicit = {}
    for region in header.get("configuration", {}).get("region_requests", []):
        key = (region["candidate_id"], region["sequence_id"])
        explicit.setdefault(key, []).append(region)
    for candidate in candidate_records:
        key = (candidate["candidate_id"], candidate["sequence_id"])
        regions = explicit.pop(key, None)
        if not regions:
            known_length = candidate["source_length"]
            regions = [{
                "start": 0 if type(known_length) is int else None,
                "end": known_length if type(known_length) is int else None,
                "request_ordinal": -1,
            }]
        source_digest = candidate["source_sha256"]
        for region in regions:
            request_id = stable_request_id(
                candidate["candidate_id"], candidate["sequence_id"],
                source_digest, region["start"], region["end"],
            )
            expected_requests[request_id] = (
                candidate["candidate_id"], candidate["sequence_id"],
                source_digest, region["start"], region["end"],
                candidate["manifest_ordinal"], region["request_ordinal"],
            )
    for (candidate_id, sequence_id), regions in explicit.items():
        for region in regions:
            request_id = stable_request_id(
                candidate_id, sequence_id, None, region["start"], region["end"])
            expected_requests[request_id] = (
                candidate_id, sequence_id, None, region["start"], region["end"],
                len(candidate_records), region["request_ordinal"],
            )
    observed_requests = {}
    for row in fold_rows:
        region = row.get("source_region")
        observed_requests[row["request_id"]] = (
            row["candidate_id"], row["sequence_id"], row.get("source_sha256"),
            region.get("start") if region else None,
            region.get("end") if region else None,
            row["candidate_ordinal"], row["request_ordinal"],
        )
    if observed_requests != expected_requests:
        raise ValueError("M11 fold accounting does not cover each requested candidate/region")
    expected_limits = {
        key: header["configuration"][key]
        for key in (
            "max_fold_symbols",
            "max_folds_per_run",
            "timeout_seconds_per_fold",
            "memory_bytes_per_fold",
        )
    }
    expected_enforcement = header["configuration"]["resource_enforcement_policy"]
    if any(
        row.get("effective_limits") != expected_limits
        or row.get("resource_enforcement_policy") != expected_enforcement
        for row in fold_rows
    ):
        raise ValueError(
            "M11 fold accounting limits disagree with normalized configuration"
        )
    fold_sort_keys = [
        (
            row["candidate_id"],
            row["sequence_id"],
            (row.get("source_region") or {}).get("start", -1),
            (row.get("source_region") or {}).get("end", -1),
            row["candidate_ordinal"],
            row["request_ordinal"],
        )
        for row in fold_rows
    ]
    if fold_sort_keys != sorted(fold_sort_keys):
        raise ValueError("M11 fold requests are not in canonical order")
    if any(row.get("run_identity") != bundle["run_identity"] for row in fold_rows):
        raise ValueError("M11 fold request run identities disagree with the bundle")
    if (
        any(
            type(bundle.get(field)) is not int
            for field in (
                "candidate_count", "expected_fold_count", "accounted_fold_count",
            )
        )
        or bundle["expected_fold_count"] != len(fold_rows)
        or bundle.get("accounted_fold_count") != len(fold_rows)
        or header.get("expected_fold_count") != len(fold_rows)
        or header.get("accounted_fold_count") != len(fold_rows)
        or bundle["candidate_count"] != len(candidate_rows) - 1
    ):
        raise ValueError("M11 bundle count accounting is inconsistent")
    evidence_by_request = {row["request_id"]: row for row in evidence_rows}
    raw_by_request = {row["request_id"]: row for row in raw_rows}
    candidate_by_key = {
        (row["candidate_id"], row["sequence_id"]): row
        for row in candidate_records
    }
    effective_limits = expected_limits
    predictions = {
        row["request_id"] for row in fold_rows
        if row["branch_status"] == "PREDICTION_REPORTED"
    }
    if predictions != set(evidence_by_request) or predictions != set(raw_by_request):
        raise ValueError("M11 prediction, evidence, and raw-result records disagree")
    for row in fold_rows:
        if row["branch_status"] == "PREDICTION_REPORTED":
            evidence = evidence_by_request[row["request_id"]]
            raw = raw_by_request[row["request_id"]]
            candidate = candidate_by_key.get(
                (row["candidate_id"], row["sequence_id"])
            )
            region = row.get("source_region")
            if (
                candidate is None
                or evidence["evidence_id"] != row.get("evidence_id")
                or evidence.get("run_identity") != bundle["run_identity"]
                or evidence.get("candidate_set_sha256") != source["sha256"]
                or evidence.get("source_sha256") != row.get("source_sha256")
                or evidence.get("source_sequence") != candidate.get("source_sequence")
                or evidence.get("source_sequence_length")
                != candidate.get("source_length")
                or evidence.get("source_artifact") != candidate.get("source_artifact")
                or evidence.get("molecule_type") != candidate.get("molecule_type")
                or evidence.get("completeness_state")
                != candidate.get("completeness_state")
                or evidence.get("source_region") != region
                or evidence.get("effective_limits") != effective_limits
                or evidence.get("resource_enforcement_policy")
                != header["configuration"].get("resource_enforcement_policy")
                or evidence["raw_engine_result_sha256"] != row.get(
                    "raw_engine_result_sha256")
                or raw["raw_engine_result_sha256"] != row.get(
                    "raw_engine_result_sha256")
                or evidence.get("raw_result_artifact") != {
                    "path": "mfe_raw_results.jsonl",
                    "row": row.get("raw_result_row"),
                }
                or row.get("raw_result_row") != next(
                    i for i, item in enumerate(raw_rows, 1)
                    if item["request_id"] == row["request_id"])
                or evidence["candidate_id"] != row["candidate_id"]
                or evidence["sequence_id"] != row["sequence_id"]
                or raw["raw_engine_result"].get("dot_bracket")
                != evidence["mfe_structure_dot_bracket"]
                or raw["raw_engine_result"].get("energy_hex")
                != evidence["mfe_energy_hex"]
            ):
                raise ValueError("M11 fold record is not bound to its evidence")
    empty_ok = (
        bundle["aggregate_status"] == "COMPLETE"
        and bundle["input_status"] == "COMPLETE_EMPTY_INPUT_SET"
        and bundle["candidate_count"] == 0
        and not fold_rows
    )
    all_predictions = bool(fold_rows) and predictions == {
        row["request_id"] for row in fold_rows
    }
    if bundle["aggregate_status"] == "COMPLETE" and not (empty_ok or all_predictions):
        raise ValueError("M11 complete aggregate contains an incomplete request")
    if bundle["aggregate_status"] == "PARTIAL" and all_predictions:
        raise ValueError("M11 partial aggregate has only complete predictions")
    return {
        "schema": BUNDLE_SCHEMA,
        "candidate_count": bundle["candidate_count"],
        "fold_count": len(fold_rows),
        "evidence_count": len(evidence_rows),
        "aggregate_status": bundle["aggregate_status"],
        "input_status": bundle["input_status"],
    }