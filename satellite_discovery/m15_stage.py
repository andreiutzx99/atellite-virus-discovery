"""Lossless M15 dossier stage for explicitly referenced upstream artifacts."""

import hashlib
import json
import os
import csv
from pathlib import Path, PurePosixPath
import tempfile

from . import artifact_contracts, m15_contracts


STAGE_KIND = "m15_evidence_dossier"
STAGE_VERSION = "1"
OUTPUT_CONTRACTS = m15_contracts.OUTPUT_CONTRACTS
CACHE_INPUT_SEMANTICS_VERSION = "m15-exact-references-and-lossless-axes-v1"
_M1_STATES = {
    "pending", "running", "complete", "skipped", "dependency_missing",
    "external_module_required", "failed", "interrupted",
}
_RAW_TEXT_TYPES = {
    "dvg_raw_output", "read_alignment_sam", "m8_raw_blast_output",
    "m9_protein_fasta", "m9_raw_blast_output",
}
_NON_JSON_SCHEMA_TYPES = _RAW_TEXT_TYPES | {
    "read_triage_table", "read_support_table", "m10_repeat_evidence",
    "m12_artifact_review_table",
}


def validate_config(config):
    if not isinstance(config, dict) or config:
        raise ValueError("M15 does not accept stage configuration")
    return {}


def artifact_input_name(index):
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("M15 artifact reference index is invalid")
    return f"artifact_{index:04d}"


def _source_identity():
    sources = (
        Path(__file__).resolve(),
        Path(m15_contracts.__file__).resolve(),
        Path(artifact_contracts.__file__).resolve(),
        Path(__file__).with_name("artifact_workflow.py").resolve(),
    )
    digest = hashlib.sha256()
    for source in sorted(sources, key=lambda item: item.name):
        digest.update(source.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return {
        "schema": "m15-stage-implementation-v1",
        "semantic_version": m15_contracts.SEMANTIC_VERSION,
        "source_sha256": digest.hexdigest(),
        "output_schema_version": m15_contracts.OUTPUT_SCHEMA_VERSION,
    }


def register_stage(registry):
    input_types = sorted({
        "m15_input_manifest",
        *m15_contracts.ALL_INPUT_TYPES,
    })
    return registry.register(
        STAGE_KIND,
        None,
        run_stage,
        version=STAGE_VERSION,
        dynamic_inputs=True,
        config_validator=validate_config,
        input_contracts={"*": tuple(input_types)},
        output_contracts=OUTPUT_CONTRACTS,
        description=(
            "Preserves immutable M5-M14 producer references in a descriptive "
            "dossier without ranking, classification, or biological claims."
        ),
    )


def _regular_file(path):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError:
        return False
    return path.is_file() and not path.is_symlink() and info.st_size >= 0


def _producer_root(path, relative_path):
    path = Path(path)
    parts = PurePosixPath(relative_path).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("PATH_UNSAFE")
    root = path
    for _ in parts:
        root = root.parent
    root = root.resolve(strict=True)
    expected = root.joinpath(*parts)
    current = root
    for part in parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("PATH_UNSAFE")
    resolved = path.resolve(strict=True)
    if resolved != expected.resolve(strict=True):
        raise ValueError("PATH_UNSAFE")
    if not resolved.is_relative_to(root):
        raise ValueError("PATH_UNSAFE")
    return root, resolved


def _read_producer_manifest(root, ref):
    manifest = root / "manifest.json"
    if not _regular_file(manifest):
        raise FileNotFoundError("RUN_MANIFEST_UNAVAILABLE")
    if m15_contracts.sha256_file(manifest) != ref["producer_run_manifest_sha256"]:
        raise ValueError("RUN_MANIFEST_DIGEST_MISMATCH")
    try:
        value = m15_contracts.read_json(manifest)
    except (OSError, ValueError, UnicodeError) as error:
        raise ValueError("RUN_MANIFEST_INVALID") from error
    if m15_contracts.sha256_file(manifest) != ref["producer_run_manifest_sha256"]:
        raise ValueError("RUN_MANIFEST_DIGEST_MISMATCH")
    status = value.get("status")
    if status != ref["producer_status"]:
        raise ValueError("PRODUCER_STATUS_MISMATCH")
    output_hashes = value.get("output_sha256")
    if not isinstance(output_hashes, dict):
        raise ValueError("RUN_MANIFEST_INVALID")
    expected = output_hashes.get(ref["relative_path"])
    if expected != ref["sha256"]:
        raise ValueError("ARTIFACT_NOT_BOUND_BY_PRODUCER_MANIFEST")
    return value


def _payload_schema(path, artifact_type, descriptor):
    if artifact_type in _RAW_TEXT_TYPES:
        return "UNKNOWN", None
    try:
        value = m15_contracts.read_json_value(path)
    except ValueError as error:
        if artifact_type in _NON_JSON_SCHEMA_TYPES:
            return "UNKNOWN", None
        raise ValueError("ARTIFACT_SCHEMA_INVALID") from error
    schema = value.get("schema") if isinstance(value, dict) else None
    if isinstance(schema, str) and schema:
        return schema, value
    detail_schema = descriptor.get("schema") if isinstance(descriptor, dict) else None
    if isinstance(detail_schema, str) and detail_schema:
        return detail_schema, value
    return "UNKNOWN", value


def _evidence_id(ref, duplicate_index=None):
    identity = {
        "producer_milestone": ref["producer_milestone"],
        "producer_stage_id": ref["producer_stage_id"],
        "producer_run_manifest_sha256": ref["producer_run_manifest_sha256"],
        "artifact_sha256": ref["sha256"],
        "artifact_type": ref["artifact_type"],
        "relative_path": ref["relative_path"],
        "source_row_index": None,
    }
    if duplicate_index is not None:
        # Duplicate declarations are retained as invalid records. The occurrence
        # index only disambiguates those integrity-error records.
        identity["duplicate_reference_index"] = duplicate_index
    return hashlib.sha256(
        m15_contracts.canonical_json_bytes(identity)
    ).hexdigest()


def _record(ref, candidate_id, *, state, reason, schema="UNKNOWN",
            document=None, duplicate_index=None):
    artifact_validity = {
        "ACCEPTED": "VALID",
        "INVALID": "INVALID",
        "UNAVAILABLE": "UNKNOWN",
    }[state]
    axes = m15_contracts.map_explicit_axes(
        document,
        artifact_validity=artifact_validity,
    )
    status = ref["producer_status"]
    if status in _M1_STATES:
        axes["execution"] = status
    if (
        state == "ACCEPTED"
        and ref["producer_milestone"] == "M5"
        and ref["artifact_type"] in {"dvg_evidence", "dvg_evidence_summary"}
        and status == "complete"
        and isinstance(document, dict)
        and document.get("schema") in {"dvg-evidence-v1", "dvg-summary-v1"}
    ):
        result_status = document.get("status")
        event_count = (
            len(document.get("events", []))
            if ref["artifact_type"] == "dvg_evidence"
            and isinstance(document.get("events"), list)
            else document.get("event_count")
        )
        if result_status == "DVG_EVIDENCE_DETECTED" and isinstance(event_count, int) \
                and not isinstance(event_count, bool) and event_count > 0:
            axes["observation"] = "OBSERVED"
            axes["completeness"] = "COMPLETE"
        elif (result_status == "NO_DVG_EVIDENCE_DETECTED"
              and event_count == 0):
            axes["observation"] = "NOT_DETECTED_WITHIN_SCOPE"
            axes["completeness"] = "COMPLETE"
    if ref["producer_milestone"] == "M14" and state == "ACCEPTED":
        # Mainline has the frozen M14 interface but no M14 output validator.
        axes["artifact_validity"] = "UNKNOWN"
        axes.update({
            "applicability": "UNKNOWN",
            "completeness": "UNKNOWN",
            "observation": "UNKNOWN",
            "interpretation": "NOT_INTERPRETED",
        })
    if status not in _M1_STATES:
        axes.update({
            "applicability": "UNKNOWN",
            "execution": "UNKNOWN",
            "completeness": "UNKNOWN",
            "observation": "UNKNOWN",
            "interpretation": "NOT_INTERPRETED",
        })
    return {
        "evidence_id": _evidence_id(ref, duplicate_index),
        "candidate_id": candidate_id,
        "producer_ref": ref,
        "producer_status_raw": status,
        "producer_schema_raw": schema,
        "source_row_ref": None,
        "semantic_axes": axes,
        "dependency_edge_ids": [],
        "validation_state": state,
        "reason_code": reason,
    }


def _validate_ref(path, ref, input_type):
    if input_type != ref["artifact_type"]:
        raise ValueError("INPUT_ARTIFACT_TYPE_MISMATCH")
    if not m15_contracts.producer_type_allowed(ref):
        raise ValueError("PRODUCER_TYPE_MISMATCH")
    if ref["producer_status"] not in _M1_STATES:
        # Preserve unfamiliar producer states, but do not reject the reference.
        pass
    root, resolved = _producer_root(path, ref["relative_path"])
    producer_manifest = _read_producer_manifest(root, ref)
    details = artifact_contracts.validate_artifact(resolved, ref["artifact_type"])
    actual_sha = m15_contracts.sha256_file(resolved)
    if actual_sha != ref["sha256"]:
        raise ValueError("ARTIFACT_DIGEST_MISMATCH")
    contract_version = artifact_contracts.semantic_identity(
        ref["artifact_type"]
    )["contracts"][ref["artifact_type"]]
    if contract_version != ref["artifact_contract_version"]:
        raise ValueError("ARTIFACT_VERSION_MISMATCH")
    schema, document = _payload_schema(resolved, ref["artifact_type"], details)
    if m15_contracts.sha256_file(resolved) != ref["sha256"]:
        raise ValueError("ARTIFACT_DIGEST_MISMATCH")
    if ref["producer_milestone"] == "M14":
        return "UNKNOWN", schema, document, details, producer_manifest
    return "VALID", schema, document, details, producer_manifest


def _failure_record(ref, candidate_id, failure):
    if failure in {"UNAVAILABLE", "INPUT_UNAVAILABLE", "RUN_MANIFEST_UNAVAILABLE"}:
        return _record(
            ref, candidate_id, state="UNAVAILABLE",
            reason="INPUT_UNAVAILABLE",
        )
    reason = failure if isinstance(failure, str) and failure else "ARTIFACT_INVALID"
    return _record(ref, candidate_id, state="INVALID", reason=reason)


def _eligible_fragment_ids(path):
    eligible = set()
    with Path(path).open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if (row.get("outcome") == "ELIGIBLE_FOR_ASSEMBLY"
                    and str(row.get("residual", "")).strip().lower()
                    in {"true", "1"}):
                query_id = row.get("query_id")
                if isinstance(query_id, str) and query_id:
                    eligible.add(query_id)
    return eligible


def _m6_read_source_edges(records, provenance):
    triage_records = [
        record for record in records
        if record["validation_state"] == "ACCEPTED"
        and record["producer_ref"]["artifact_type"] == "read_triage_table"
    ]
    support_records = [
        record for record in records
        if record["validation_state"] == "ACCEPTED"
        and record["producer_ref"]["artifact_type"] == "read_support_evidence"
    ]
    edges = []
    for triage in triage_records:
        triage_ref = triage["producer_ref"]
        triage_ids = provenance.get(triage["evidence_id"], {}).get(
            "eligible_fragment_ids")
        if not isinstance(triage_ids, set) or not triage_ids:
            continue
        for support in support_records:
            support_ref = support["producer_ref"]
            if (
                support_ref["producer_milestone"] != triage_ref["producer_milestone"]
                or support_ref["producer_stage_id"] != triage_ref["producer_stage_id"]
                or support_ref["producer_run_manifest_sha256"]
                != triage_ref["producer_run_manifest_sha256"]
            ):
                continue
            support_ids = provenance.get(support["evidence_id"], {}).get(
                "support_input_fragment_ids")
            if not isinstance(support_ids, list) or not support_ids:
                continue
            if (any(not isinstance(item, str) or not item for item in support_ids)
                    or len(support_ids) != len(set(support_ids))
                    or set(support_ids) != triage_ids):
                continue
            ids_digest = hashlib.sha256(
                m15_contracts.canonical_json_bytes(sorted(triage_ids))
            ).hexdigest()
            source_ref = {
                "producer_run_manifest_sha256":
                    triage_ref["producer_run_manifest_sha256"],
                "triage_artifact_ref": triage_ref,
                "support_artifact_ref": support_ref,
                "eligible_fragment_ids_sha256": ids_digest,
            }
            edge_identity = {
                "source_evidence_id": triage["evidence_id"],
                "target_evidence_id": support["evidence_id"],
                "relation": "SAME_READ_SOURCE",
                "verification_state": "VERIFIED",
                "source_provenance_ref": source_ref,
            }
            edge_id = hashlib.sha256(
                m15_contracts.canonical_json_bytes(edge_identity)
            ).hexdigest()
            edges.append({"edge_id": edge_id, **edge_identity})
    edges.sort(key=lambda edge: (
        edge["source_evidence_id"], edge["relation"], edge["target_evidence_id"],
    ))
    return edges


def _m13_source_event_edges(records, provenance):
    m5_records = [
        record for record in records
        if record["validation_state"] == "ACCEPTED"
        and record["producer_ref"]["producer_milestone"] == "M5"
        and record["producer_ref"]["artifact_type"] == "dvg_evidence"
    ]
    m13_records = [
        record for record in records
        if record["validation_state"] == "ACCEPTED"
        and record["producer_ref"]["artifact_type"] == "m13_event_index"
    ]
    edges = []
    for m13 in m13_records:
        rows = provenance.get(m13["evidence_id"], {}).get("m13_event_rows")
        if not isinstance(rows, list):
            continue
        for row in rows:
            run_ref = row.get("m5_run_ref") if isinstance(row, dict) else None
            if not isinstance(run_ref, dict):
                continue
            index = row.get("source_row_index")
            if isinstance(index, bool) or not isinstance(index, int) or index < 0:
                continue
            for m5 in m5_records:
                m5_ref = m5["producer_ref"]
                if (
                    m5_ref["producer_stage_id"] != run_ref.get("producer_stage_id")
                    or m5_ref["producer_run_manifest_sha256"]
                    != run_ref.get("producer_run_manifest_sha256")
                    or m5_ref["sha256"] != run_ref.get("dvg_evidence_sha256")
                ):
                    continue
                events = provenance.get(m5["evidence_id"], {}).get("dvg_events")
                if (not isinstance(events, list) or index >= len(events)
                        or events[index] != row.get("source_event")):
                    continue
                source_event_id = row.get("source_event_id")
                if (source_event_id is not None
                        and events[index].get("evidence_id") != source_event_id):
                    continue
                source_ref = {
                    "m13_artifact_ref": m13["producer_ref"],
                    "m5_artifact_ref": m5_ref,
                    "m5_run_ref": run_ref,
                    "source_row_index": index,
                }
                if source_event_id is not None:
                    source_ref["source_event_id"] = source_event_id
                edge_identity = {
                    "source_evidence_id": m13["evidence_id"],
                    "target_evidence_id": m5["evidence_id"],
                    "relation": "DERIVED_FROM",
                    "verification_state": "VERIFIED",
                    "source_provenance_ref": source_ref,
                }
                edge_id = hashlib.sha256(
                    m15_contracts.canonical_json_bytes(edge_identity)
                ).hexdigest()
                edges.append({"edge_id": edge_id, **edge_identity})
    edges.sort(key=lambda edge: (
        edge["source_evidence_id"], edge["relation"], edge["target_evidence_id"],
        edge["source_provenance_ref"]["source_row_index"],
    ))
    return edges


def _resolve_records(inputs, manifest, input_failures):
    records = []
    warnings = []
    provenance = {}
    seen = {}
    for index, ref in enumerate(manifest["artifact_refs"]):
        key = (
            ref["producer_milestone"], ref["producer_stage_id"],
            ref["producer_run_manifest_sha256"], ref["artifact_type"],
            ref["relative_path"], ref["sha256"],
        )
        duplicate_index = seen.get(key)
        if duplicate_index is None:
            seen[key] = index
        input_name = artifact_input_name(index)
        failure = input_failures.get(input_name)
        path = inputs.get(input_name)
        if duplicate_index is not None:
            records.append(_record(
                ref, manifest["candidate_id"], state="INVALID",
                reason="DUPLICATE_REFERENCE", duplicate_index=index,
            ))
            warnings.append("DUPLICATE_REFERENCE")
            continue
        if failure is not None:
            records.append(_failure_record(
                ref, manifest["candidate_id"], failure))
            continue
        if path is None:
            records.append(_failure_record(
                ref, manifest["candidate_id"], "UNAVAILABLE"))
            continue
        try:
            validity, schema, document, details, producer_manifest = _validate_ref(
                path, ref, ref["artifact_type"])
            triage_ids = None
            if ref["artifact_type"] == "read_triage_table":
                triage_ids = _eligible_fragment_ids(path)
                if m15_contracts.sha256_file(path) != ref["sha256"]:
                    raise ValueError("ARTIFACT_DIGEST_MISMATCH")
            record = _record(
                ref, manifest["candidate_id"], state="ACCEPTED",
                reason=None, schema=schema, document=document,
            )
            if ref["artifact_type"] == "read_triage_table":
                provenance.setdefault(record["evidence_id"], {}).update({
                    "eligible_fragment_ids": triage_ids,
                })
            elif ref["artifact_type"] == "read_support_evidence":
                provenance.setdefault(record["evidence_id"], {}).update({
                    "support_input_fragment_ids": (
                        document.get("provenance", {}).get(
                            "support_input_fragment_ids")
                        if isinstance(document, dict)
                        and isinstance(document.get("provenance"), dict)
                        else None
                    ),
                })
            elif (ref["producer_milestone"] == "M5"
                  and ref["artifact_type"] == "dvg_evidence"
                  and isinstance(document, dict)):
                provenance.setdefault(record["evidence_id"], {}).update({
                    "dvg_events": document.get("events"),
                })
            elif (ref["producer_milestone"] == "M13"
                  and ref["artifact_type"] == "m13_event_index"
                  and isinstance(document, dict)):
                provenance.setdefault(record["evidence_id"], {}).update({
                    "m13_event_rows": document.get("events"),
                })
            if validity == "UNKNOWN":
                warnings.append("UPSTREAM_CONTRACT_VALIDATOR_UNAVAILABLE")
                record["semantic_axes"]["artifact_validity"] = "UNKNOWN"
            if ref["producer_status"] not in _M1_STATES:
                warnings.append("UNRECOGNIZED_PRODUCER_STATUS")
            if schema == "UNKNOWN" and ref["artifact_type"] not in _NON_JSON_SCHEMA_TYPES:
                warnings.append("UNRECOGNIZED_PRODUCER_SCHEMA")
                record["semantic_axes"].update({
                    "applicability": "UNKNOWN",
                    "execution": (
                        ref["producer_status"]
                        if ref["producer_status"] in _M1_STATES else "UNKNOWN"
                    ),
                    "completeness": "UNKNOWN",
                    "observation": "UNKNOWN",
                    "interpretation": "NOT_INTERPRETED",
                })
            records.append(record)
        except FileNotFoundError as error:
            records.append(_failure_record(
                ref, manifest["candidate_id"], str(error)))
        except (OSError, PermissionError):
            records.append(_failure_record(
                ref, manifest["candidate_id"], "UNAVAILABLE"))
        except (ValueError, KeyError, TypeError, UnicodeError, csv.Error) as error:
            reason = str(error)
            if reason not in {
                "INPUT_ARTIFACT_TYPE_MISMATCH", "PRODUCER_TYPE_MISMATCH",
                "PATH_UNSAFE", "RUN_MANIFEST_DIGEST_MISMATCH",
                "RUN_MANIFEST_INVALID", "PRODUCER_STATUS_MISMATCH",
                "ARTIFACT_NOT_BOUND_BY_PRODUCER_MANIFEST",
                "ARTIFACT_DIGEST_MISMATCH", "ARTIFACT_VERSION_MISMATCH",
            }:
                reason = "ARTIFACT_SCHEMA_INVALID"
            records.append(_failure_record(ref, manifest["candidate_id"], reason))
    records.sort(key=lambda row: row["evidence_id"])
    edges = (
        _m6_read_source_edges(records, provenance)
        + _m13_source_event_edges(records, provenance)
    )
    edges.sort(key=lambda edge: (
        edge["source_evidence_id"], edge["relation"],
        edge["target_evidence_id"],
        m15_contracts.canonical_json_bytes(edge["source_provenance_ref"]),
    ))
    edge_ids_by_evidence = {}
    for edge in edges:
        for evidence_id in (edge["source_evidence_id"], edge["target_evidence_id"]):
            edge_ids_by_evidence.setdefault(evidence_id, []).append(edge["edge_id"])
    for record in records:
        record["dependency_edge_ids"] = sorted(
            edge_ids_by_evidence.get(record["evidence_id"], []))
    return records, sorted(set(warnings)), edges


def _result_completeness(manifest, records, warnings):
    if not manifest["artifact_refs"]:
        return "NOT_EVALUATED"
    valid = sum(row["validation_state"] == "ACCEPTED" for row in records)
    invalid = sum(row["validation_state"] == "INVALID" for row in records)
    unavailable = sum(
        row["validation_state"] == "UNAVAILABLE" for row in records)
    if valid == 0 and invalid and not unavailable:
        return "INVALID"
    if invalid or unavailable:
        return "PARTIAL"
    if any(state not in {"PRESENT", "NOT_APPLICABLE"}
           for state in manifest["optional_stage_states"].values()):
        return "PARTIAL"
    if warnings:
        return "PARTIAL"
    if any(row["semantic_axes"]["artifact_validity"] == "UNKNOWN"
           for row in records):
        return "PARTIAL"
    return "COMPLETE_WITHIN_SUPPLIED_SCOPE"


def _summary(manifest, records, warnings, completeness):
    by_producer = {}
    for record in records:
        milestone = record["producer_ref"]["producer_milestone"]
        row = by_producer.setdefault(milestone, {
            "producer_milestone": milestone,
            "supplied_artifacts": 0,
            "accepted_records": 0,
            "invalid_records": 0,
            "unavailable_records": 0,
        })
        row["supplied_artifacts"] += 1
        if record["validation_state"] == "ACCEPTED":
            row["accepted_records"] += 1
        elif record["validation_state"] == "UNAVAILABLE":
            row["unavailable_records"] += 1
        else:
            row["invalid_records"] += 1
    by_producer = [by_producer[key] for key in sorted(by_producer)]
    absent = sorted(
        milestone for milestone, state
        in manifest["optional_stage_states"].items()
        if state not in {"PRESENT", "NOT_APPLICABLE"}
    )
    return {
        "schema": m15_contracts.SUMMARY_SCHEMA,
        "candidate_id": manifest["candidate_id"],
        "result_completeness": completeness,
        "optional_stage_states": manifest["optional_stage_states"],
        "counts": {
            "supplied_artifacts": len(manifest["artifact_refs"]),
            "accepted_records": sum(
                row["validation_state"] == "ACCEPTED" for row in records),
            "invalid_records": sum(
                row["validation_state"] == "INVALID" for row in records),
            "unavailable_records": sum(
                row["validation_state"] == "UNAVAILABLE" for row in records),
            "absent_optional_stages": absent,
            "unresolved_records": sum(
                row["semantic_axes"]["interpretation"] == "UNRESOLVED"
                for row in records),
            "compatibility_warnings": len(warnings),
        },
        "by_producer": by_producer,
    }


def _source_access_provenance(records):
    rows = []
    fields = (
        "source_terms_ref", "source_terms_refs", "attribution_ref",
        "attribution_refs", "access_class", "access_ref", "access_refs",
        "redistribution_limits",
    )
    for record in records:
        ref = record["producer_ref"]
        copied = {key: ref[key] for key in fields if key in ref}
        rows.append({
            "evidence_id": record["evidence_id"],
            "state": "DECLARED" if copied else "UNKNOWN",
            "references": copied,
        })
    return rows


def build_stage_context(input_paths, binding_plan, input_failures=None):
    input_failures = input_failures or {}
    manifest_path = input_paths.get("manifest")
    if manifest_path is None:
        raise ValueError("M15 requires its direct typed input manifest")
    manifest_path = Path(manifest_path)
    digest_before = m15_contracts.sha256_file(manifest_path)
    manifest = m15_contracts.validate_input_manifest(
        m15_contracts.read_json(manifest_path))
    manifest_digest = m15_contracts.sha256_file(manifest_path)
    if digest_before != manifest_digest:
        raise ValueError("M15 input manifest changed during validation")
    bindings = binding_plan.get("bindings", []) if isinstance(binding_plan, dict) else []
    by_index = {row["artifact_ref_index"]: row for row in bindings}
    resolved = []
    for index, ref in enumerate(manifest["artifact_refs"]):
        input_name = artifact_input_name(index)
        input_path = input_paths.get(input_name)
        actual_sha256 = None
        integrity_state = "UNAVAILABLE"
        if input_path is not None:
            input_path = Path(input_path)
            if not _regular_file(input_path):
                integrity_state = "INVALID"
            else:
                try:
                    actual_sha256 = m15_contracts.sha256_file(input_path)
                    integrity_state = "AVAILABLE"
                except OSError:
                    integrity_state = "UNAVAILABLE"
        input_descriptor = {
            "artifact_ref_index": index,
            "input_name": input_name,
            "artifact_type": ref["artifact_type"],
            "reference_sha256": ref["sha256"],
            "resolved_sha256": actual_sha256,
            "resolved_integrity_state": integrity_state,
            "producer_run_manifest_sha256": ref["producer_run_manifest_sha256"],
            "input_state": input_failures.get(input_name, integrity_state),
            "binding": by_index.get(index, {}),
        }
        resolved.append(input_descriptor)
    consumed_types = {"m15_input_manifest"}
    consumed_types.update(ref["artifact_type"] for ref in manifest["artifact_refs"])
    identity = {
        "schema": "m15-cache-context-v1",
        "input_schema": m15_contracts.INPUT_SCHEMA,
        "input_manifest_sha256": manifest_digest,
        "candidate_id": manifest["candidate_id"],
        "artifact_refs": manifest["artifact_refs"],
        "optional_stage_states": manifest["optional_stage_states"],
        "resolved_input_states": resolved,
        "contract_semantics": artifact_contracts.semantic_identity(consumed_types),
        "output_contract_semantics": artifact_contracts.semantic_identity(
            OUTPUT_CONTRACTS.values()),
        "implementation": _source_identity(),
        "output_schema_version": m15_contracts.OUTPUT_SCHEMA_VERSION,
        "cache_input_semantics_version": CACHE_INPUT_SEMANTICS_VERSION,
    }
    identity_sha = hashlib.sha256(
        m15_contracts.canonical_json_bytes(identity)
    ).hexdigest()
    return {
        "input_manifest": manifest,
        "input_manifest_sha256": manifest_digest,
        "binding_plan": binding_plan,
        "input_failures": dict(input_failures),
        "cache_identity": identity,
        "cache_identity_sha256": identity_sha,
    }


def _load_existing(output, cache_identity):
    output = Path(output)
    marker = output / "manifest.json"
    if not marker.is_file() or marker.is_symlink():
        return None
    try:
        value = m15_contracts.read_json(marker)
    except (OSError, ValueError):
        return None
    if value.get("identity") != cache_identity:
        return None
    hashes = value.get("output_sha256")
    if not isinstance(hashes, dict) or set(hashes) != set(OUTPUT_CONTRACTS):
        return None
    for name, artifact_type in OUTPUT_CONTRACTS.items():
        path = output / name
        if not _regular_file(path):
            return None
        if m15_contracts.sha256_file(path) != hashes.get(name):
            return None
        try:
            artifact_contracts.validate_artifact(path, artifact_type)
        except (OSError, ValueError):
            return None
    return value


def _write_outputs(output, context, inputs):
    manifest = context["input_manifest"]
    failures = context["input_failures"]
    records, warnings, edges = _resolve_records(inputs, manifest, failures)
    completeness = _result_completeness(manifest, records, warnings)
    envelope = {
        "schema": m15_contracts.ENVELOPE_SCHEMA,
        "candidate_id": manifest["candidate_id"],
        "records": records,
        "compatibility_warnings": warnings,
    }
    edge_document = {"schema": m15_contracts.EDGES_SCHEMA, "edges": edges}
    summary = _summary(manifest, records, warnings, completeness)
    contract_types = {"m15_input_manifest"}
    contract_types.update(ref["artifact_type"] for ref in manifest["artifact_refs"])
    temporary_parent = Path(output).parent
    temporary_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".m15-stage-", dir=temporary_parent) as folder:
        folder = Path(folder)
        paths = {
            "evidence_envelope.json": envelope,
            "dependency_edges.json": edge_document,
            "dossier_summary.json": summary,
        }
        output_digests = {}
        for name, value in paths.items():
            output_digests[name] = m15_contracts.write_json(folder / name, value)
        output_inventory = {
            artifact_type: {
                "relative_path": name,
                "artifact_type": artifact_type,
                "sha256": output_digests[name],
            }
            for name, artifact_type in OUTPUT_CONTRACTS.items()
            if name != "result_bundle.json"
        }
        bundle = {
            "schema": m15_contracts.RESULT_BUNDLE_SCHEMA,
            "input_schema": m15_contracts.INPUT_SCHEMA,
            "semantic_version": m15_contracts.SEMANTIC_VERSION,
            "candidate_id": manifest["candidate_id"],
            "result_completeness": completeness,
            "input_manifest_sha256": context["input_manifest_sha256"],
            "axis_mapping_semantic_version": CACHE_INPUT_SEMANTICS_VERSION,
            "optional_stage_states": manifest["optional_stage_states"],
            "producer_refs": sorted(
                manifest["artifact_refs"],
                key=lambda ref: (
                    ref["producer_milestone"], ref["producer_stage_id"],
                    ref["artifact_type"], ref["sha256"],
                    ref["producer_run_manifest_sha256"],
                ),
            ),
            "dependency_edges": edges,
            "contract_semantics": artifact_contracts.semantic_identity(
                contract_types),
            "implementation": _source_identity(),
            "outputs": output_inventory,
            "source_access_provenance": _source_access_provenance(records),
        }
        bundle_name = "result_bundle.json"
        output_digests[bundle_name] = m15_contracts.write_json(
            folder / bundle_name, bundle)
        for name, artifact_type in OUTPUT_CONTRACTS.items():
            artifact_contracts.validate_artifact(folder / name, artifact_type)
        stage_manifest = {
            "schema": "m15-stage-manifest-v1",
            "status": "complete",
            "stage": STAGE_KIND,
            "stage_version": STAGE_VERSION,
            "identity": context["cache_identity"],
            "output_sha256": output_digests,
        }
        m15_contracts.write_json(folder / "manifest.json", stage_manifest)
        output = Path(output)
        if output.is_symlink():
            raise ValueError("M15 stage output must not be a symbolic link")
        if output.exists():
            if any(output.iterdir()):
                raise ValueError("Existing M15 output directory is occupied or unverified")
            output.rmdir()
        os.replace(folder, output)
    return stage_manifest


def run_stage(inputs, output, config, *, workflow_context=None):
    validate_config(config)
    if workflow_context is None:
        workflow_context = build_stage_context(inputs, {"bindings": []})
    if not isinstance(workflow_context, dict):
        raise ValueError("M15 workflow context is malformed")
    fresh = build_stage_context(
        inputs,
        workflow_context.get("binding_plan"),
        workflow_context.get("input_failures", {}),
    )
    if fresh["cache_identity"] != workflow_context.get("cache_identity"):
        raise ValueError("M15 inputs changed after cache identity was calculated")
    if m15_contracts.sha256_file(inputs["manifest"]) \
            != fresh["input_manifest_sha256"]:
        raise ValueError("M15 input manifest changed during stage execution")
    existing = _load_existing(output, fresh["cache_identity"])
    if existing is not None:
        return existing
    output = Path(output)
    if output.is_symlink():
        raise ValueError("M15 stage output must not be a symbolic link")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Existing M15 output directory is partial, changed, or unverified")
    result = _write_outputs(output, fresh, inputs)
    if m15_contracts.sha256_file(inputs["manifest"]) \
            != fresh["input_manifest_sha256"]:
        raise ValueError("M15 input manifest changed during stage execution")
    return result


run_stage.cache_implementation_identity = _source_identity
run_stage.cache_input_contract_semantics = True
run_stage.cache_input_contract_semantics_version = CACHE_INPUT_SEMANTICS_VERSION