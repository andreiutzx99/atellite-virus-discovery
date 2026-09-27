"""Deterministic, optional M11 ViennaRNA MFE stage over the validated M6 handoff."""

import json
import math
from pathlib import Path
import tempfile

from . import artifact_contracts, m11_contracts
from .m11_algorithms import (
    ACCOUNTING_SCHEMA,
    BUNDLE_SCHEMA,
    CONTRACT_VERSION,
    ENGINE_RELEASE,
    EVIDENCE_SCHEMA,
    FOLD_ACCOUNTING_SCHEMA,
    METHOD_ID,
    POLICY_IDS,
    PROFILE_ID,
    STAGE_VERSION,
    axes_for_branch,
    canonical_json,
    normalize_energy,
    resolve_applicability,
    sha256,
    source_digest,
    stable_evidence_id,
    stable_request_id,
    validate_dot_bracket,
    validate_source,
)
from .m11_engine import ResourceEnforcementError, fold_single
from .m11_runtime import runtime_identity
from .m8_candidate_handoff import validate_candidate_sequence_set
from .sequence_downloader import checksum


STAGE_KIND = "m11_rna_mfe"
_OUTPUT_TYPES = {
    "candidate_accounting.jsonl": "m11_candidate_accounting",
    "fold_accounting.jsonl": "m11_fold_accounting",
    "rna_structure_evidence.jsonl": "m11_rna_structure_evidence",
    "mfe_raw_results.jsonl": "m11_mfe_raw_results",
    "m11_bundle.json": "m11_result_bundle",
}


def _positive_int(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _check_resource_support(memory_bytes):
    import os
    if os.name == "posix":
        try:
            import resource
        except ImportError as error:
            raise ValueError("M11 cannot enforce a per-fold memory limit") from error
        if not hasattr(resource, "RLIMIT_AS"):
            raise ValueError("M11 cannot enforce a per-fold memory limit")
    elif os.name == "nt":
        import ctypes
        if not hasattr(ctypes, "WinDLL"):
            raise ValueError("M11 cannot enforce a per-fold memory limit")
        try:
            ctypes.WinDLL("kernel32", use_last_error=True)
        except OSError as error:
            raise ValueError("M11 cannot enforce a per-fold memory limit") from error
    else:
        raise ValueError("M11 resource caps are unsupported on this operating system")
    _positive_int(memory_bytes, "memory_bytes_per_fold")


def _normalized_region_requests(value):
    if not isinstance(value, list):
        raise ValueError("region_requests must be an array")
    rows = []
    keys = set()
    for ordinal, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {
            "candidate_id", "sequence_id", "start", "end",
        }:
            raise ValueError(
                "Each M11 region request requires candidate_id, sequence_id, start and end"
            )
        candidate_id, sequence_id = raw["candidate_id"], raw["sequence_id"]
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError("region request candidate_id must be non-empty text")
        if not isinstance(sequence_id, str) or not sequence_id:
            raise ValueError("region request sequence_id must be non-empty text")
        if type(raw["start"]) is not int or type(raw["end"]) is not int:
            raise ValueError("region coordinates must be integers")
        key = (candidate_id, sequence_id, raw["start"], raw["end"])
        if key in keys:
            raise ValueError("Duplicate M11 candidate/region request")
        keys.add(key)
        rows.append({
            "candidate_id": candidate_id,
            "sequence_id": sequence_id,
            "start": raw["start"],
            "end": raw["end"],
            "request_ordinal": ordinal,
        })
    return rows


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("M11 configuration must be an object")
    allowed = {
        "max_fold_symbols", "max_folds_per_run", "timeout_seconds_per_fold",
        "memory_bytes_per_fold", "region_requests", "runtime_identity",
    }
    if set(config) - allowed:
        raise ValueError("M11 configuration contains an unknown option")
    values = {
        "max_fold_symbols": 100_000,
        "max_folds_per_run": 1_000,
        "timeout_seconds_per_fold": 60.0,
        "memory_bytes_per_fold": 2_147_483_648,
    }
    for name in ("max_fold_symbols", "max_folds_per_run"):
        if name in config:
            values[name] = _positive_int(config[name], name)
    if "memory_bytes_per_fold" in config:
        values["memory_bytes_per_fold"] = _positive_int(
            config["memory_bytes_per_fold"], "memory_bytes_per_fold")
    timeout = config.get(
        "timeout_seconds_per_fold", values["timeout_seconds_per_fold"])
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or timeout <= 0):
        raise ValueError("timeout_seconds_per_fold must be finite and positive")
    values["timeout_seconds_per_fold"] = float(timeout)
    _check_resource_support(values["memory_bytes_per_fold"])
    regions = _normalized_region_requests(config.get("region_requests", []))
    current_runtime = runtime_identity()
    supplied_runtime = config.get("runtime_identity")
    if supplied_runtime is not None and supplied_runtime != current_runtime:
        raise ValueError("M11 runtime identity changed after workflow preflight")
    return {
        **values,
        "region_requests": regions,
        "runtime_identity": current_runtime,
        "resource_enforcement_policy": (
            "POSIX_RLIMIT_AS_AND_CHILD_PROCESS_TIMEOUT"
            if __import__("os").name == "posix"
            else "WINDOWS_JOB_OBJECT_PROCESS_MEMORY_AND_CHILD_PROCESS_TIMEOUT"
        ),
        "policy_ids": POLICY_IDS,
        "method_id": METHOD_ID,
        "profile_id": PROFILE_ID,
        "contract_version": CONTRACT_VERSION,
    }


def implementation_identity():
    source_paths = (
        Path(__file__),
        Path(__file__).with_name("m11_algorithms.py"),
        Path(__file__).with_name("m11_engine.py"),
        Path(__file__).with_name("m11_runtime.py"),
        Path(__file__).with_name("m11_contracts.py"),
        Path(__file__).with_name("m8_candidate_handoff.py"),
    )
    return {
        "schema": "m11-rna-mfe-stage-identity-v1",
        "stage_version": STAGE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "source_sha256": {
            path.name: checksum(path) for path in source_paths
        },
        "artifact_contract_semantics": artifact_contracts.semantic_identity({
            "m8_candidate_sequence_set",
            *_OUTPUT_TYPES.values(),
        }),
        "policy_ids": POLICY_IDS,
        "method_id": METHOD_ID,
        "profile_id": PROFILE_ID,
    }


def _canonical_hash(value):
    return sha256(canonical_json(value).encode("utf-8"))


def _index_fasta(path):
    index = {}
    current_id = None
    start = None
    with Path(path).open("rb") as source:
        while True:
            position = source.tell()
            line = source.readline()
            if not line:
                if current_id is not None:
                    index[current_id] = (start, position)
                break
            if line.startswith(b">"):
                if current_id is not None:
                    index[current_id] = (start, position)
                fields = line[1:].strip().split(None, 1)
                if not fields:
                    raise ValueError("Candidate FASTA contains an empty identifier")
                current_id = fields[0].decode("ascii")
                if current_id in index:
                    raise ValueError("Candidate FASTA has duplicate record identifiers")
                start = source.tell()
    return index


def _read_fasta_sequence(path, span):
    start, end = span
    with Path(path).open("rb") as source:
        source.seek(start)
        payload = source.read(end - start)
    return b"".join(payload.splitlines()).decode("ascii")


def _candidate_inputs(inputs):
    if set(inputs) != {"candidate_sequence_set"}:
        raise ValueError("M11 accepts exactly one candidate_sequence_set input")
    path = Path(inputs["candidate_sequence_set"]).resolve(strict=True)
    validation = validate_candidate_sequence_set(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    availability = document["availability"]
    fasta_path = (
        path.parent / availability["fasta_artifact"]["path"]
        if availability.get("fasta_artifact") else None
    )
    records = document.get("records", [])
    fasta_index = _index_fasta(fasta_path) if fasta_path else {}
    expected_fasta = {
        row["fasta_record_id"]: row for row in records
        if row.get("sequence_bytes_available") is True
    }
    if set(fasta_index) != set(expected_fasta):
        raise ValueError("M11 FASTA index disagrees with the validated handoff")
    sequences = {}
    for fasta_id, span in fasta_index.items():
        sequence = _read_fasta_sequence(fasta_path, span)
        record = expected_fasta[fasta_id]
        if (
            len(sequence) != record["sequence_length"]
            or source_digest(sequence) != record["sequence_sha256"]
        ):
            raise ValueError("M11 source sequence bytes disagree with the handoff")
        sequences[fasta_id] = sequence
    descriptor = {
        "artifact_type": "m8_candidate_sequence_set",
        "artifact_id": path.name,
        "sha256": checksum(path),
        "size_bytes": path.stat().st_size,
        "validation_state": "valid",
        "validation_metadata": validation,
        "schema": document.get("schema"),
        "producer": document.get("producer"),
        "availability": availability,
        "source_artifact": document.get("source_artifact"),
        "assembly_manifest": document.get("assembly_manifest"),
        "m6_evidence": document.get("m6_evidence"),
    }
    inputs_fingerprint = {
        str(path): checksum(path),
    }
    if fasta_path:
        inputs_fingerprint[str(fasta_path.resolve())] = checksum(fasta_path)
    for ref in (
        document.get("source_artifact"),
        document.get("assembly_manifest"),
        document.get("m6_evidence", {}).get("artifact"),
    ):
        if ref:
            ref_path = (path.parent / ref["path"]).resolve(strict=True)
            inputs_fingerprint[str(ref_path)] = checksum(ref_path)
    return path, document, records, sequences, descriptor, inputs_fingerprint


def _request_plan(records, sequences, config):
    by_identity = {}
    for ordinal, record in enumerate(records):
        by_identity[(record["candidate_id"], record["sequence_id"])] = (
            ordinal, record)
    explicit = {}
    for row in config["region_requests"]:
        key = (row["candidate_id"], row["sequence_id"])
        explicit.setdefault(key, []).append(row)

    requests = []
    for key, (candidate_ordinal, record) in by_identity.items():
        sequence = (
            sequences.get(record.get("fasta_record_id"))
            if record.get("sequence_bytes_available") is True else None
        )
        selected = explicit.pop(key, None)
        if selected:
            regions = selected
        else:
            regions = [{
                "start": 0 if sequence is not None else None,
                "end": len(sequence) if sequence is not None else None,
                "request_ordinal": -1,
            }]
        for region in regions:
            start, end = region["start"], region["end"]
            requests.append({
                "candidate_id": record["candidate_id"],
                "sequence_id": record["sequence_id"],
                "candidate_ordinal": candidate_ordinal,
                "request_ordinal": region["request_ordinal"],
                "record": record,
                "sequence": sequence,
                "start": start,
                "end": end,
                "source_sha256": (
                    record.get("sequence_sha256") if sequence is not None else None
                ),
                "known_candidate": True,
            })
    for (candidate_id, sequence_id), rows in explicit.items():
        for row in rows:
            requests.append({
                "candidate_id": candidate_id,
                "sequence_id": sequence_id,
                "candidate_ordinal": len(records),
                "request_ordinal": row["request_ordinal"],
                "record": None,
                "sequence": None,
                "start": row["start"],
                "end": row["end"],
                "source_sha256": None,
                "known_candidate": False,
            })
    requests.sort(key=lambda row: (
        row["candidate_id"], row["sequence_id"],
        row["start"] if type(row["start"]) is int else -1,
        row["end"] if type(row["end"]) is int else -1,
        row["candidate_ordinal"], row["request_ordinal"],
    ))
    return requests


def _branch_record(request, request_id, run_identity, config, runtime, status,
                   reason=None, view=None):
    axes = axes_for_branch(status)
    record = {
        "record_type": "fold_request",
        "schema": FOLD_ACCOUNTING_SCHEMA,
        "request_id": request_id,
        "candidate_id": request["candidate_id"],
        "sequence_id": request["sequence_id"],
        "candidate_ordinal": request["candidate_ordinal"],
        "request_ordinal": request["request_ordinal"],
        "source_sha256": request["source_sha256"],
        "source_length": len(request["sequence"]) if request["sequence"] is not None else None,
        "source_region": (
            {"start": request["start"], "end": request["end"]}
            if request["start"] is not None and request["end"] is not None
            else None
        ),
        "coordinate_system": "ZERO_BASED_HALF_OPEN_SOURCE",
        "orientation": "AS_SUPPLIED",
        "method_id": METHOD_ID,
        "profile_id": PROFILE_ID,
        "policy_ids": POLICY_IDS,
        "effective_limits": {
            "max_fold_symbols": config["max_fold_symbols"],
            "max_folds_per_run": config["max_folds_per_run"],
            "timeout_seconds_per_fold": config["timeout_seconds_per_fold"],
            "memory_bytes_per_fold": config["memory_bytes_per_fold"],
        },
        "runtime_identity": runtime,
        "run_identity": run_identity,
        "view": view,
        "reason_code": reason,
        "evidence_id": None,
        "raw_engine_result_sha256": None,
        "raw_result_row": None,
        **axes,
    }
    return record


def _write_jsonl(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="\n") as target:
        for row in rows:
            target.write(canonical_json(row) + "\n")


def run_stage(inputs, output, config):
    config = validate_config(config)
    candidate_path, document, records, sequences, candidate_descriptor, fingerprint = (
        _candidate_inputs(inputs)
    )
    implementation = implementation_identity()
    config_sha = _canonical_hash(config)
    input_identity = {
        "stage": STAGE_KIND,
        "stage_version": STAGE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "candidate_sequence_set_sha256": candidate_descriptor["sha256"],
        "configuration_sha256": config_sha,
        "implementation": implementation,
    }
    run_identity = _canonical_hash(input_identity)
    request_plan = _request_plan(records, sequences, config)
    availability_state = document["availability"]["state"]
    input_status = {
        "AVAILABLE": "INPUT_VALID",
        "PARTIALLY_AVAILABLE": "INPUT_VALID",
        "UPSTREAM_UNAVAILABLE": "SEQUENCE_UNAVAILABLE",
        "INVALID_OUTPUT": "INPUT_INVALID",
        "COMPLETE_EMPTY": "COMPLETE_EMPTY_INPUT_SET",
    }[availability_state]

    candidate_rows = []
    for ordinal, record in enumerate(records):
        sequence = (
            sequences.get(record.get("fasta_record_id"))
            if record.get("sequence_bytes_available") is True else None
        )
        candidate_rows.append({
            "record_type": "candidate",
            "candidate_id": record["candidate_id"],
            "sequence_id": record["sequence_id"],
            "manifest_ordinal": ordinal,
            "fasta_record_id": record.get("fasta_record_id"),
            "sequence_bytes_available": sequence is not None,
            "source_sequence": sequence,
            "source_sha256": (
                source_digest(sequence) if sequence is not None
                else record.get("sequence_sha256")
            ),
            "source_length": (
                len(sequence) if sequence is not None
                else record.get("sequence_length")
            ),
            "source_artifact": {
                "artifact_id": record["source_artifact_id"],
                "sha256": record.get("source_artifact_sha256"),
            },
            "candidate_set_sha256": candidate_descriptor["sha256"],
            "molecule_type": record.get("molecule_type"),
            "completeness_state": record.get("completeness_state"),
            "m6_support_status": record.get("m6_support_status"),
            "input_status": (
                "INPUT_INVALID" if availability_state == "INVALID_OUTPUT"
                else "INPUT_VALID" if sequence is not None
                else "SEQUENCE_UNAVAILABLE"
            ),
            "limitations": [
                "Source sequence and provenance are unchanged; MFE is a prediction for the supplied orientation only."
            ],
        })
    candidate_rows.sort(key=lambda row: (
        row["candidate_id"], row["sequence_id"], row["manifest_ordinal"],
    ))

    runtime = config["runtime_identity"]
    preclassified = []
    for request in request_plan:
        request_id = stable_request_id(
            request["candidate_id"], request["sequence_id"],
            request["source_sha256"], request["start"], request["end"],
        )
        request["request_id"] = request_id
        record = request["record"]
        sequence = request["sequence"]
        if not request["known_candidate"] or availability_state == "INVALID_OUTPUT":
            preclassified.append((request, request_id, "INPUT_INVALID", "INVALID_CANDIDATE_IDENTITY"))
            continue
        if sequence is None:
            preclassified.append((request, request_id, "SEQUENCE_UNAVAILABLE", "SOURCE_BYTES_UNAVAILABLE"))
            continue
        input_state, upper = validate_source(sequence)
        if input_state != "INPUT_VALID":
            preclassified.append((request, request_id, "INPUT_INVALID", "SOURCE_SEQUENCE_INVALID"))
            continue
        input_state, applicability, view = resolve_applicability(
            upper, record.get("molecule_type"), request["start"], request["end"])
        if input_state == "INPUT_INVALID":
            preclassified.append((request, request_id, "INPUT_INVALID", "INVALID_REGION"))
            continue
        if applicability == "INSUFFICIENT_INFORMATION":
            preclassified.append((request, request_id, "INSUFFICIENT_INFORMATION", "MOLECULE_TYPE_UNKNOWN_OR_INCONSISTENT"))
            continue
        if applicability == "NOT_APPLICABLE":
            preclassified.append((request, request_id, "NOT_APPLICABLE", "VALID_AMBIGUITY_OUTSIDE_MFE_ALPHABET"))
            continue
        preclassified.append((request, request_id, "READY", None, view))

    eligible = [row for row in preclassified if row[2] == "READY"]
    permitted = {
        row[1] for row in eligible[:config["max_folds_per_run"]]
    }
    fold_rows = []
    evidence_rows = []
    raw_rows = []
    for item in preclassified:
        request, request_id, status, reason, *optional_view = item
        record = request["record"]
        item_result = None
        view = optional_view[0] if optional_view else None
        if status == "READY":
            if request_id not in permitted:
                status, reason = "TRUNCATED", "MAX_FOLDS_PER_RUN"
            elif view["view_length"] > config["max_fold_symbols"]:
                status, reason = "TRUNCATED", "MAX_FOLD_SYMBOLS"
            elif runtime["status"] != "available":
                status, reason = "DEPENDENCY_UNAVAILABLE", runtime["reason_code"]
            else:
                status, result, reason = fold_single(
                    view["view_sequence"],
                    config["timeout_seconds_per_fold"],
                    config["memory_bytes_per_fold"],
                )
                if status == "COMPLETED":
                    if not isinstance(result, dict):
                        status, reason = "OUTPUT_INVALID", "MALFORMED_ENGINE_RESULT"
                        structure = None
                        model_details = None
                    else:
                        structure = result.get("dot_bracket")
                        model_details = result.get("effective_model_details")
                if status == "COMPLETED":
                    try:
                        energy = float.fromhex(result.get("energy_hex", ""))
                        normalized_energy = normalize_energy(energy)
                    except (TypeError, ValueError, OverflowError):
                        status, reason = "OUTPUT_INVALID", "INVALID_MFE_ENERGY"
                    else:
                        if not validate_dot_bracket(structure, view["view_length"]):
                            status, reason = "OUTPUT_INVALID", "INVALID_DOT_BRACKET"
                        elif (
                            not isinstance(model_details, dict)
                            or model_details.get("temperature") != 37.0
                            or model_details.get("dangles") != 2
                            or model_details.get("parameter_set") != "TURNER_2004_BUILTIN"
                        ):
                            status, reason = "OUTPUT_INVALID", "MODEL_PROFILE_MISMATCH"
                        else:
                            raw_envelope = {
                                "dot_bracket": structure,
                                "energy_hex": energy.hex(),
                            }
                            raw_digest = _canonical_hash(raw_envelope)
                            evidence_id = stable_evidence_id(
                                run_identity, request_id)
                            raw_rows.append({
                                "record_type": "raw_engine_result",
                                "request_id": request_id,
                                "raw_engine_result": raw_envelope,
                                "raw_engine_result_sha256": raw_digest,
                            })
                            raw_row_number = len(raw_rows)
                            evidence = {
                                "record_type": "RNA_STRUCTURE_EVIDENCE",
                                "schema": EVIDENCE_SCHEMA,
                                "evidence_id": evidence_id,
                                "request_id": request_id,
                                "candidate_id": request["candidate_id"],
                                "sequence_id": request["sequence_id"],
                                "candidate_set_sha256": candidate_descriptor["sha256"],
                                "source_sha256": request["source_sha256"],
                                "source_sequence_length": len(request["sequence"]),
                                "source_sequence": request["sequence"],
                                "molecule_type": record["molecule_type"],
                                "completeness_state": record["completeness_state"],
                                "source_region": view["source_region"],
                                "coordinate_system": "ZERO_BASED_HALF_OPEN_SOURCE",
                                "orientation": "AS_SUPPLIED",
                                "coordinate_map": view["coordinate_map"],
                                "view_sequence": view["view_sequence"],
                                "view_sha256": view["view_sha256"],
                                "view_length": view["view_length"],
                                "view_policy": POLICY_IDS["rna_view"],
                                "transformation": view["transformation"],
                                "method_id": METHOD_ID,
                                "profile_id": PROFILE_ID,
                                "viennarna_version": ENGINE_RELEASE,
                                "runtime_identity": runtime,
                                "effective_model_details": model_details,
                                "effective_limits": {
                                    "max_fold_symbols": config["max_fold_symbols"],
                                    "max_folds_per_run": config["max_folds_per_run"],
                                    "timeout_seconds_per_fold": config["timeout_seconds_per_fold"],
                                    "memory_bytes_per_fold": config["memory_bytes_per_fold"],
                                },
                                "mfe_structure_dot_bracket": structure,
                                "mfe_energy_kcal_mol": normalized_energy,
                                "mfe_energy_hex": energy.hex(),
                                "raw_engine_result_sha256": raw_digest,
                                "raw_result_artifact": {
                                    "path": "mfe_raw_results.jsonl",
                                    "row": raw_row_number,
                                },
                                "limitations": [
                                    "Predicted model-dependent secondary structure; not observed structure, expression, activity, or function.",
                                    "MFE energy is an optimum under the named model, not a probability, confidence score, or significance statistic.",
                                    "A partial supplied fragment is a prediction for that fragment only.",
                                    "Synthetic acceptance fixtures validate software behavior, not biological performance.",
                                ],
                                "branch_status": "PREDICTION_REPORTED",
                                "evidence_status": "EVIDENCE_FOUND",
                                "run_identity": run_identity,
                            }
                            evidence["evidence_sha256"] = _canonical_hash(evidence)
                            evidence_rows.append(evidence)
                            status, reason = "PREDICTION_REPORTED", None
                            item_result = {
                                "evidence_id": evidence_id,
                                "raw_engine_result_sha256": raw_digest,
                                "raw_result_row": raw_row_number,
                            }
        row = _branch_record(
            request, request_id, run_identity, config, runtime,
            status, reason, view,
        )
        if status == "PREDICTION_REPORTED":
            row.update(item_result)
        fold_rows.append(row)

    if not records and availability_state == "COMPLETE_EMPTY":
        aggregate_status = "COMPLETE"
        input_status = "COMPLETE_EMPTY_INPUT_SET"
    else:
        aggregate_status = (
            "COMPLETE" if fold_rows and all(
                row["branch_status"] == "PREDICTION_REPORTED"
                for row in fold_rows
            ) else "PARTIAL"
        )
    accounted_count = len(fold_rows)
    if accounted_count != len(request_plan):
        raise ValueError("M11 internal fold accounting is incomplete")

    accounting_header = {
        "record_type": "manifest",
        "schema": ACCOUNTING_SCHEMA,
        "stage": STAGE_KIND,
        "stage_version": STAGE_VERSION,
        "contract_version": CONTRACT_VERSION,
        "run_identity": run_identity,
        "candidate_count": len(candidate_rows),
        "input_status": input_status,
        "aggregate_status": aggregate_status,
        "expected_fold_count": len(request_plan),
        "accounted_fold_count": accounted_count,
        "candidate_set": candidate_descriptor,
        "configuration": config,
        "configuration_sha256": config_sha,
        "implementation": implementation,
        "policy_ids": POLICY_IDS,
        "method_id": METHOD_ID,
        "profile_id": PROFILE_ID,
        "limitations": [
            "No biological database retrieval, sequence search, or empirical performance evaluation was performed."
        ],
    }
    out_dir = Path(output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".m11-stage-", dir=out_dir) as tmp:
        tmp = Path(tmp)
        _write_jsonl(
            tmp / "candidate_accounting.jsonl",
            [accounting_header, *candidate_rows],
        )
        _write_jsonl(tmp / "fold_accounting.jsonl", fold_rows)
        _write_jsonl(tmp / "rna_structure_evidence.jsonl", evidence_rows)
        _write_jsonl(tmp / "mfe_raw_results.jsonl", raw_rows)
        descriptors = {}
        for filename, artifact_type in _OUTPUT_TYPES.items():
            if filename == "m11_bundle.json":
                continue
            path = tmp / filename
            descriptors[filename] = {
                "path": filename,
                "role": artifact_type,
                "artifact_type": artifact_type,
                "sha256": checksum(path),
                "size_bytes": path.stat().st_size,
            }
        bundle = {
            "schema": BUNDLE_SCHEMA,
            "stage": STAGE_KIND,
            "stage_version": STAGE_VERSION,
            "contract_version": CONTRACT_VERSION,
            "run_identity": run_identity,
            "input_status": input_status,
            "aggregate_status": aggregate_status,
            "candidate_count": len(candidate_rows),
            "expected_fold_count": len(request_plan),
            "accounted_fold_count": accounted_count,
            "source_inputs": {"candidate_sequence_set": candidate_descriptor},
            "configuration": config,
            "configuration_sha256": config_sha,
            "implementation": implementation,
            "policy_ids": POLICY_IDS,
            "method_id": METHOD_ID,
            "profile_id": PROFILE_ID,
            "outputs": descriptors,
            "limitations": [
                "Predicted RNA secondary structure is not experimental structure or biological function.",
                "No biological searches or biological performance claims are part of this software baseline.",
            ],
        }
        (tmp / "m11_bundle.json").write_text(
            canonical_json(bundle) + "\n", encoding="utf-8")

        final_validation = validate_candidate_sequence_set(candidate_path)
        if final_validation != candidate_descriptor["validation_metadata"]:
            raise ValueError("M11 candidate handoff changed during analysis")
        for path, expected in fingerprint.items():
            if checksum(path) != expected:
                raise ValueError("M11 source input changed during analysis")
        for filename in _OUTPUT_TYPES:
            (tmp / filename).replace(out_dir / filename)

    manifest = {
        "status": "complete",
        "stage": STAGE_KIND,
        "stage_version": STAGE_VERSION,
        "output_sha256": {
            name: checksum(out_dir / name) for name in _OUTPUT_TYPES
        },
    }
    (out_dir / "manifest.json").write_text(
        canonical_json(manifest) + "\n", encoding="utf-8")
    m11_contracts.validate_bundle(out_dir / "m11_bundle.json")
    return list(_OUTPUT_TYPES)


run_stage.cache_implementation_identity = implementation_identity
run_stage.cache_input_contract_semantics = True
run_stage.cache_input_contract_semantics_version = "m11-input-contract-semantics-v1"