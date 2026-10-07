"""Synthetic M16 benchmark stage with post-commit scoring and M15 projection."""

from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from . import (
    artifact_contracts, m15_contracts, m16_contracts, stage_cache_identity,
)
from .external_tool import DependencyMissingError
from .producer_provenance import (
    ProducerProvenanceIncompleteError,
    ProducerProvenanceInvalidError,
    ProducerProvenanceUnavailableError,
    verify_producer_artifact,
)

M16IntegrityError = m16_contracts.M16IntegrityError


STAGE_KIND = "m16_synthetic_benchmark"
STAGE_VERSION = "1"
ADAPTER_ID = "m15_dossier_state_projection"
ADAPTER_VERSION = "1"
SCORER_VERSION = "1"
CACHE_PROJECTION_VERSION = "m16-workflow-cache-input-projection-v1"
_M15_COMPANIONS = {
    "evidence_envelope.json": (
        "m15_evidence_envelope", "m15-evidence-envelope-v2",
    ),
    "dependency_edges.json": (
        "m15_dependency_edges", "m15-dependency-edges-v2",
    ),
    "dossier_summary.json": (
        "m15_dossier_summary", "m15-dossier-summary-v2",
    ),
}
_TARGET_CONTRACT_TYPES = {
    "m12_result_bundle", "m13_result_bundle", "m14_result_bundle",
    "m15_result_bundle", "m15_evidence_envelope", "m15_dependency_edges",
    "m15_dossier_summary",
}
OUTPUT_CONTRACTS = m16_contracts.OUTPUT_CONTRACTS


def validate_config(config):
    if not isinstance(config, dict) or config:
        raise ValueError("M16 does not accept stage configuration")
    return {}


def _source_identity():
    source_sha256, _line_profile = stage_cache_identity.stage_source_identity(
        STAGE_KIND,
        (
            "satellite_discovery.m16_stage",
            "satellite_discovery.m16_contracts",
            "satellite_discovery.m15_contracts",
            "satellite_discovery.producer_provenance",
        ),
        {
            *_TARGET_CONTRACT_TYPES,
            *OUTPUT_CONTRACTS.values(),
        },
        semantic_version=m16_contracts.SEMANTIC_VERSION,
        output_schema_version=m16_contracts.OUTPUT_SCHEMA_VERSION,
    )
    return {
        "schema": "m16-stage-implementation-v1",
        "semantic_version": m16_contracts.SEMANTIC_VERSION,
        "source_sha256": source_sha256,
        "output_schema_version": m16_contracts.OUTPUT_SCHEMA_VERSION,
        "workflow_cache_projection_version": CACHE_PROJECTION_VERSION,
    }


def register_stage(registry):
    return registry.register(
        STAGE_KIND,
        ("public_manifest", "sealed_key", "target_bundle"),
        run_stage,
        version=STAGE_VERSION,
        config_validator=validate_config,
        input_contracts={
            "target_bundle": (
                "m12_result_bundle", "m13_result_bundle",
                "m14_result_bundle", "m15_result_bundle",
            ),
        },
        output_contracts=OUTPUT_CONTRACTS,
        description=(
            "Runs a generated-fixture benchmark and custody harness against "
            "frozen M12-M15 bundles; M16 v1 enables only the lossless M15 "
            "state-projection adapter."
        ),
    )


def _input_path(inputs, name):
    value = inputs.get(name)
    if value is None:
        return None
    if isinstance(value, (str, os.PathLike)):
        return Path(value)
    if isinstance(value, dict):
        path = value.get("path")
        if isinstance(path, str) and value.get("status", "available") == "available":
            return Path(path)
    return None


def _load_m15_target(public_manifest_path, target_bundle_path, target_ref):
    root = m16_contracts.resolve_relative_path(
        public_manifest_path.parent,
        target_ref["bundle_root_ref"],
        "M16 bundle_root_ref",
    )
    bundle_root = root.resolve(strict=True)
    if not bundle_root.is_dir():
        raise ValueError("M16 bundle_root_ref must name a directory")
    bundle_path = m16_contracts.resolve_relative_path(
        bundle_root, target_ref["artifact_path"], "M16 artifact_path",
        require_file=True,
    ).resolve(strict=True)
    supplied_path = Path(target_bundle_path).resolve(strict=True)
    if supplied_path != bundle_path:
        raise M16IntegrityError(
            "INTEGRITY_FAILED: target_bundle input does not match target_ref.artifact_path"
        )

    execution_ref = target_ref["producer_execution_ref"]
    workflow_ref = execution_ref["producer_workflow_ref"]
    workflow_path = m16_contracts.resolve_relative_path(
        bundle_root, workflow_ref["path"], "M16 producer workflow path",
        require_file=True,
    )
    workflow_raw = workflow_path.read_bytes()
    if hashlib.sha256(workflow_raw).hexdigest() != workflow_ref["sha256"]:
        raise M16IntegrityError(
            "INTEGRITY_FAILED: producer workflow digest mismatch"
        )
    # M15's shared workflow writer uses platform text-mode newlines. Bind the
    # exact producer bytes above, then normalize CRLF only for strict parsing.
    workflow = m16_contracts.parse_json_bytes(
        workflow_raw.replace(b"\r\n", b"\n"),
        label="M15 producer workflow manifest",
    )
    stages = workflow.get("stages")
    if not isinstance(stages, list):
        raise M16IntegrityError("INTEGRITY_FAILED: producer workflow stages are invalid")
    selected = [
        stage for stage in stages
        if isinstance(stage, dict)
        and stage.get("id") == execution_ref["producer_stage_id"]
    ]
    if len(selected) != 1:
        raise M16IntegrityError(
            "INTEGRITY_FAILED: selected M15 producer stage is missing or ambiguous"
        )
    stage = selected[0]
    if stage.get("kind") != "m15_evidence_dossier":
        raise M16IntegrityError(
            "INTEGRITY_FAILED: selected producer stage kind is not M15"
        )
    if stage.get("status") != "complete":
        try:
            verify_producer_artifact(
                bundle_root=bundle_root,
                producer_execution_ref=execution_ref,
                artifact_path=target_ref["artifact_path"],
                artifact_relative_path=target_ref["artifact_relative_path"],
                artifact_type=target_ref["artifact_type"],
                contract_version=target_ref["contract_version"],
                expected_sha256=target_ref["artifact_sha256"],
            )
        except ProducerProvenanceIncompleteError as error:
            raise M16IntegrityError(f"{error.code}: {error}") from error
        except ProducerProvenanceInvalidError as error:
            raise M16IntegrityError(
                f"INTEGRITY_FAILED: {error.code}: {error}"
            ) from error
        raise M16IntegrityError(
            "PRODUCER_STAGE_INCOMPLETE: selected M15 producer stage is not complete"
        )
    stage_output = stage.get("output_path")
    if not isinstance(stage_output, str):
        raise M16IntegrityError("INTEGRITY_FAILED: M15 stage output path is missing")
    m16_contracts.safe_relative_path(stage_output, "M15 workflow stage output_path")
    expected_artifact_path = (
        PurePosixPath(stage_output) / target_ref["artifact_relative_path"]
    ).as_posix()
    if expected_artifact_path != target_ref["artifact_path"]:
        raise M16IntegrityError(
            "INTEGRITY_FAILED: target artifact_path differs from the workflow row"
        )
    descriptors = stage.get("artifacts")
    if not isinstance(descriptors, dict):
        raise M16IntegrityError("INTEGRITY_FAILED: M15 workflow artifact descriptors are missing")
    bundle_descriptor = descriptors.get("result_bundle.json")
    if (
        not isinstance(bundle_descriptor, dict)
        or bundle_descriptor.get("path") != target_ref["artifact_path"]
        or bundle_descriptor.get("artifact_type") != "m15_result_bundle"
        or bundle_descriptor.get("contract_version") != "1"
        or bundle_descriptor.get("sha256") != target_ref["artifact_sha256"]
    ):
        raise M16IntegrityError(
            "INTEGRITY_FAILED: M15 workflow result-bundle descriptor mismatch"
        )

    try:
        verified_bundle = verify_producer_artifact(
            bundle_root=bundle_root,
            producer_execution_ref=execution_ref,
            artifact_path=target_ref["artifact_path"],
            artifact_relative_path=target_ref["artifact_relative_path"],
            artifact_type=target_ref["artifact_type"],
            contract_version=target_ref["contract_version"],
            expected_sha256=target_ref["artifact_sha256"],
        )
    except ProducerProvenanceUnavailableError:
        raise
    except (ProducerProvenanceIncompleteError, ProducerProvenanceInvalidError) as error:
        raise M16IntegrityError(
            f"INTEGRITY_FAILED: {error.code}: {error}"
        ) from error

    stage_manifest_path = bundle_root / stage_output / "manifest.json"
    stage_manifest = m16_contracts.read_json(
        stage_manifest_path, label="M15 stage manifest"
    )
    if (
        stage_manifest.get("status") != "complete"
        or stage_manifest.get("stage") != "m15_evidence_dossier"
        or stage_manifest.get("stage_version") != "2"
        or stage_manifest.get("schema") != "m15-stage-manifest-v1"
        or hashlib.sha256(stage_manifest_path.read_bytes()).hexdigest()
            != execution_ref["producer_stage_manifest_sha256"]
    ):
        raise M16IntegrityError("INTEGRITY_FAILED: M15 stage manifest identity mismatch")

    bundle = m16_contracts.read_json(bundle_path, label="M15 result bundle")
    try:
        m15_contracts.validate_result_bundle(bundle)
        artifact_contracts.validate_artifact(bundle_path, "m15_result_bundle")
    except (ValueError, KeyError, TypeError) as error:
        raise M16IntegrityError(
            f"INTEGRITY_FAILED: M15 result bundle is invalid: {error}"
        ) from error
    if (
        bundle.get("schema") != "m15-result-bundle-v2"
        or bundle.get("semantic_version") != "2"
        or bundle.get("input_schema") not in {"m15-input-v1", "m15-input-v2"}
        or bundle.get("implementation") != target_ref["implementation"]
        or bundle.get("contract_semantics") != target_ref["contract_semantics"]
        or stage_manifest.get("identity", {}).get("implementation")
            != bundle.get("implementation")
        or target_ref["configuration"] != {}
    ):
        raise M16IntegrityError("INTEGRITY_FAILED: M15 implementation/configuration binding mismatch")
    if stage.get("stage_manifest_sha256") != execution_ref["producer_stage_manifest_sha256"]:
        raise M16IntegrityError("INTEGRITY_FAILED: M15 workflow stage-manifest digest mismatch")

    output_hashes = stage_manifest.get("output_sha256")
    if not isinstance(output_hashes, dict):
        raise M16IntegrityError("INTEGRITY_FAILED: M15 output inventory is missing")
    companion_documents = {}
    companion_identities = {}
    stage_dir = (bundle_root / stage_output).resolve(strict=True)
    for filename, (artifact_type, expected_schema) in _M15_COMPANIONS.items():
        inventory = bundle["outputs"].get(artifact_type)
        if (
            not isinstance(inventory, dict)
            or inventory.get("relative_path") != filename
            or inventory.get("artifact_type") != artifact_type
        ):
            raise M16IntegrityError(
                f"INTEGRITY_FAILED: M15 companion inventory mismatch: {filename}"
            )
        companion_path = stage_dir / filename
        digest = inventory["sha256"]
        if (
            output_hashes.get(filename) != digest
            or m16_contracts.sha256_file(companion_path) != digest
        ):
            raise M16IntegrityError(
                f"INTEGRITY_FAILED: M15 companion digest mismatch: {filename}"
            )
        companion_artifact_path = (
            PurePosixPath(stage_output) / filename
        ).as_posix()
        companion_descriptor = descriptors.get(filename)
        if (
            not isinstance(companion_descriptor, dict)
            or companion_descriptor.get("path") != companion_artifact_path
            or companion_descriptor.get("artifact_type") != artifact_type
            or companion_descriptor.get("contract_version") != "1"
            or companion_descriptor.get("sha256") != digest
        ):
            raise M16IntegrityError(
                f"INTEGRITY_FAILED: M15 workflow companion descriptor mismatch: {filename}"
            )
        try:
            verified_companion = verify_producer_artifact(
                bundle_root=bundle_root,
                producer_execution_ref=execution_ref,
                artifact_path=companion_artifact_path,
                artifact_relative_path=filename,
                artifact_type=artifact_type,
                contract_version="1",
                expected_sha256=digest,
            )
            artifact_contracts.validate_artifact(companion_path, artifact_type)
            document = m16_contracts.read_json(
                companion_path, label=f"M15 companion {filename}"
            )
        except ProducerProvenanceUnavailableError:
            raise
        except (
            ProducerProvenanceIncompleteError, ProducerProvenanceInvalidError,
            ValueError, OSError, KeyError, TypeError,
        ) as error:
            code = getattr(error, "code", "COMPANION_INVALID")
            raise M16IntegrityError(
                f"INTEGRITY_FAILED: M15 companion verification failed: {filename}: {code}"
            ) from error
        if document.get("schema") != expected_schema:
            raise M16IntegrityError(
                f"INTEGRITY_FAILED: M15 companion schema mismatch: {filename}"
            )
        companion_documents[filename] = document
        companion_identities[filename] = {
            "artifact_type": artifact_type,
            "contract_version": "1",
            "schema": expected_schema,
            "sha256": digest,
            "binding_sha256": verified_companion.binding_sha256,
        }

    if bundle_descriptor.get("metadata", {}).get("schema") != "m15-result-bundle-v2":
        raise M16IntegrityError("INTEGRITY_FAILED: M15 result descriptor semantic identity mismatch")
    target_identity = {
        "schema": "m16-m15-target-identity-v1",
        "binding_sha256": verified_bundle.binding_sha256,
        "workflow_id": verified_bundle.workflow_id,
        "producer_workflow_sha256": verified_bundle.workflow_sha256,
        "producer_workflow_status_raw": verified_bundle.workflow_status_raw,
        "producer_stage_id": verified_bundle.stage_id,
        "producer_stage_kind": verified_bundle.stage_kind,
        "producer_stage_status_raw": verified_bundle.stage_status_raw,
        "producer_stage_manifest_sha256": verified_bundle.stage_manifest_sha256,
        "artifact_relative_path": verified_bundle.artifact_relative_path,
        "artifact_type": verified_bundle.artifact_type,
        "contract_version": verified_bundle.contract_version,
        "semantic_version": bundle["semantic_version"],
        "input_schema": bundle["input_schema"],
        "artifact_sha256": verified_bundle.artifact_sha256,
        "bundle_schema": bundle["schema"],
        "producer_stage_version": stage_manifest["stage_version"],
        "producer_stage_manifest_schema": stage_manifest["schema"],
        "implementation": bundle["implementation"],
        "configuration": {},
        "contract_semantics": bundle["contract_semantics"],
        "companions": companion_identities,
    }
    provenance = {
        "producer_milestone": "M15",
        "producer_workflow_sha256": verified_bundle.workflow_sha256,
        "producer_stage_manifest_sha256": verified_bundle.stage_manifest_sha256,
        "producer_stage_id": verified_bundle.stage_id,
        "producer_stage_kind": verified_bundle.stage_kind,
        "artifact_type": verified_bundle.artifact_type,
        "contract_version": verified_bundle.contract_version,
        "semantic_version": bundle["semantic_version"],
        "artifact_sha256": verified_bundle.artifact_sha256,
        "binding_sha256": verified_bundle.binding_sha256,
    }
    return {
        "bundle": bundle,
        "envelope": companion_documents["evidence_envelope.json"],
        "edges": companion_documents["dependency_edges.json"],
        "summary": companion_documents["dossier_summary.json"],
        "identity": target_identity,
        "provenance": provenance,
        "binding_sha256": verified_bundle.binding_sha256,
    }


def _query_semantics(manifest_path, manifest):
    root = manifest_path.parent
    resolved = {}
    semantic_rows = {}
    for item in manifest["items"]:
        item_id = item["item_id"]
        ref = item["target_input_ref"]
        record = {
            "status": "AVAILABLE",
            "reason_code": None,
            "query": None,
            "semantic_sha256": None,
        }
        try:
            query_path = m16_contracts.resolve_relative_path(
                root, ref["path"], f"target input for {item_id}",
            )
            if query_path.is_symlink():
                raise ValueError("QUERY_PATH_UNSAFE")
            if not query_path.is_file():
                record.update(
                    status="DEPENDENCY_UNAVAILABLE",
                    reason_code="QUERY_INPUT_UNAVAILABLE",
                )
            else:
                query_value = m16_contracts.validate_query(
                    m16_contracts.read_json(query_path, label=f"M16 query {item_id}")
                )
                digest = m16_contracts.semantic_sha256(query_value)
                if digest != ref["sha256"]:
                    record.update(
                        status="INVALID_INPUT",
                        reason_code="QUERY_DIGEST_MISMATCH",
                    )
                else:
                    record["query"] = query_value
                    record["semantic_sha256"] = digest
        except FileNotFoundError:
            record.update(
                status="DEPENDENCY_UNAVAILABLE",
                reason_code="QUERY_INPUT_UNAVAILABLE",
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            record.update(
                status="INVALID_INPUT",
                reason_code=(
                    "QUERY_PATH_UNSAFE"
                    if "unsafe" in str(error).lower() or "link" in str(error).lower()
                    else "QUERY_INVALID"
                ),
            )
        resolved[item_id] = record
        semantic_rows[item_id] = {
            "semantic_sha256": record["semantic_sha256"],
            "status": record["status"],
            "declared_sha256": ref["sha256"],
        }
    return resolved, semantic_rows


def _path_free_target_identity(identity):
    return identity


def build_stage_context(inputs, *, workflow_root=None):
    """Resolve only public manifest/query data and authenticated target files.

    The sealed-key path is retained by the trusted stage handler, but this
    function never opens it and no target adapter receives it.
    """
    public_manifest_path = _input_path(inputs, "public_manifest")
    target_bundle_path = _input_path(inputs, "target_bundle")
    if public_manifest_path is None:
        return {
            "public_status": "UNAVAILABLE",
            "target_status": "UNAVAILABLE",
            "cache_identity": None,
            "target": None,
            "query_inputs": {},
        }
    public_manifest_path = public_manifest_path.resolve(strict=True)
    public_raw = public_manifest_path.read_bytes()
    public_value = m16_contracts.validate_public_manifest(
        m16_contracts.parse_json_bytes(public_raw, label="M16 public manifest")
    )
    if (
        public_value["adapter_id"] != ADAPTER_ID
        or public_value["adapter_version"] != ADAPTER_VERSION
    ):
        raise ValueError("M16 adapter is not registered or its version is unsupported")
    query_inputs, query_semantics = _query_semantics(
        public_manifest_path, public_value
    )
    target = None
    target_status = "AVAILABLE"
    target_error = None
    try:
        if target_bundle_path is None:
            raise ProducerProvenanceUnavailableError(
                "M16 target bundle input is unavailable",
                code="REFERENCED_FILE_UNAVAILABLE",
            )
        target_ref = public_value["target_ref"]
        target = _load_m15_target(
            public_manifest_path, target_bundle_path, target_ref
        )
    except ProducerProvenanceUnavailableError as error:
        target_status = "DEPENDENCY_UNAVAILABLE"
        target_error = error.code
    except FileNotFoundError:
        target_status = "DEPENDENCY_UNAVAILABLE"
        target_error = "REFERENCED_FILE_UNAVAILABLE"
    except M16IntegrityError as error:
        target_status = "INTEGRITY_FAILED"
        target_error = str(error)
    except (OSError, ValueError, KeyError, TypeError) as error:
        target_status = "INTEGRITY_FAILED"
        target_error = f"INTEGRITY_FAILED: {error}"

    target_identity = target["identity"] if target is not None else None
    public_projection = m16_contracts.semantic_public_projection(
        public_value, query_semantics
    )
    public_semantic_sha256 = m16_contracts.semantic_sha256(public_projection)
    item_projection = [{
        "item_id": item["item_id"],
        "group_ids": item["group_ids"],
        "split_role": item["split_role"],
        "label_state": item["label_state"],
        "fixture_provenance": item["fixture_provenance"],
        "target_input_semantic_sha256": query_semantics[item["item_id"]][
            "semantic_sha256"
        ],
        "target_input_status": query_semantics[item["item_id"]]["status"],
    } for item in public_value["items"]]
    target_artifact_identity = (
        _path_free_target_identity(target_identity)
        if target_identity is not None
        else {
            "schema": "m16-unavailable-target-v1",
            "status": target_status,
        }
    )
    cache_identity = {
        "schema": "m16-target-execution-cache-v1",
        "cache_projection_version": CACHE_PROJECTION_VERSION,
        "public_manifest_semantic_sha256": public_semantic_sha256,
        "fixture_set_id": public_value["fixture_set_id"],
        "items": item_projection,
        "target_identity": target_artifact_identity,
        "adapter_id": public_value["adapter_id"],
        "adapter_version": public_value["adapter_version"],
        "outcome_schema_version": m16_contracts.OUTCOME_SCHEMA_VERSION,
        "sealed_key_commitment": public_value["sealed_key_commitment"],
    }
    execution_identity_sha256 = m16_contracts.semantic_sha256(cache_identity)
    return {
        "public_status": "AVAILABLE",
        "manifest_path": str(public_manifest_path),
        "manifest_file_sha256": hashlib.sha256(public_raw).hexdigest(),
        "public_manifest": public_value,
        "public_manifest_semantic_sha256": public_semantic_sha256,
        "query_inputs": query_inputs,
        "query_semantics": query_semantics,
        "target": target,
        "target_status": target_status,
        "target_error": target_error,
        "cache_identity": cache_identity,
        "execution_identity_sha256": execution_identity_sha256,
        "target_identity": target_identity,
        "target_provenance": target["provenance"] if target is not None else None,
    }


def _projection(target, evidence_ids):
    records = target["envelope"].get("records")
    if not isinstance(records, list):
        raise ValueError("M15 evidence envelope records are invalid")
    by_id = {}
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("evidence_id"), str):
            by_id.setdefault(record["evidence_id"], []).append(record)
    selected = []
    fields = (
        "evidence_id", "validation_state", "reason_code",
        "producer_status_raw", "producer_schema_raw",
        "producer_provenance_state", "producer_provenance_error_code",
        "producer_binding_sha256", "producer_execution_state",
        "semantic_axes", "dependency_edge_ids",
    )
    for evidence_id in evidence_ids:
        rows = by_id.get(evidence_id, [])
        if len(rows) != 1:
            raise ValueError("QUERY_EVIDENCE_ID_UNRESOLVED")
        record = rows[0]
        if not set(fields) <= set(record):
            raise ValueError("M15 selected evidence record is missing projection fields")
        selected.append({field: record[field] for field in fields})
    selected.sort(key=lambda row: row["evidence_id"])
    value = {
        "schema": m16_contracts.PROJECTION_SCHEMA,
        "input_schema": target["bundle"]["input_schema"],
        "semantic_version": target["bundle"]["semantic_version"],
        "candidate_id": target["bundle"]["candidate_id"],
        "result_completeness": target["bundle"]["result_completeness"],
        "optional_stage_states": target["bundle"]["optional_stage_states"],
        "compatibility_warnings": target["envelope"]["compatibility_warnings"],
        "records": selected,
    }
    return m16_contracts.validate_projection(value)


def _execute_public(public_manifest, target, query_inputs, adapter_id, adapter_version):
    """Public boundary: no sealed-key path, bytes, or expected outcomes enter."""
    if adapter_id != ADAPTER_ID or adapter_version != ADAPTER_VERSION:
        raise ValueError("M16 public adapter selection is not registered")
    rows = []
    for item in public_manifest["items"]:
        item_id = item["item_id"]
        query_record = query_inputs[item_id]
        execution_state = "COMPLETED"
        outcome_state = "EMITTED"
        emitted_value = None
        reason_code = None
        if query_record["status"] == "DEPENDENCY_UNAVAILABLE":
            execution_state = "DEPENDENCY_UNAVAILABLE"
            outcome_state = "UNKNOWN"
            reason_code = query_record["reason_code"]
        elif query_record["status"] != "AVAILABLE":
            execution_state = "INVALID_INPUT"
            outcome_state = "UNKNOWN"
            reason_code = query_record["reason_code"]
        else:
            try:
                emitted_value = _projection(
                    target, query_record["query"]["evidence_ids"]
                )
            except (ValueError, KeyError, TypeError):
                execution_state = "INVALID_INPUT"
                outcome_state = "UNKNOWN"
                emitted_value = None
                reason_code = "QUERY_EVIDENCE_ID_UNRESOLVED"
        rows.append({
            "item_id": item_id,
            "execution_state": execution_state,
            "outcome_state": outcome_state,
            "emitted_value": emitted_value,
            "reason_code": reason_code,
        })
    rows.sort(key=lambda row: row["item_id"])
    return rows


def _leakage_report(items):
    group_items = {}
    for item in items:
        for group_id in item["group_ids"]:
            group_items.setdefault(group_id, []).append(item)
    group_checks = []
    offending_groups = set()
    offending_items = set()
    for group_id, members in sorted(group_items.items()):
        roles = sorted({item["split_role"] for item in members})
        item_ids = sorted({item["item_id"] for item in members})
        leaking = len(roles) > 1
        group_checks.append({
            "group_id": group_id,
            "item_ids": item_ids,
            "split_roles": roles,
            "leaking": leaking,
        })
        if leaking:
            offending_groups.add(group_id)
            offending_items.update(item_ids)

    parent = {item["item_id"]: item["item_id"] for item in items}

    def find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for members in group_items.values():
        item_ids = sorted({item["item_id"] for item in members})
        for item_id in item_ids[1:]:
            union(item_ids[0], item_id)
    components = {}
    item_by_id = {item["item_id"]: item for item in items}
    for item_id in sorted(parent):
        components.setdefault(find(item_id), []).append(item_id)
    component_rows = []
    for item_ids in sorted(components.values(), key=lambda ids: tuple(ids)):
        group_ids = sorted({
            group_id
            for item_id in item_ids
            for group_id in item_by_id[item_id]["group_ids"]
        })
        roles = sorted({item_by_id[item_id]["split_role"] for item_id in item_ids})
        leaking = len(roles) > 1
        component_rows.append({
            "item_ids": sorted(item_ids),
            "group_ids": group_ids,
            "split_roles": roles,
            "leaking": leaking,
        })
        if leaking:
            offending_groups.update(group_ids)
            offending_items.update(item_ids)
    detected = bool(offending_groups or offending_items)
    report = {
        "schema": m16_contracts.LEAKAGE_SCHEMA,
        "status": "LEAKAGE_DETECTED" if detected else "CLEAR",
        "group_checks": group_checks,
        "transitive_components": component_rows,
        "offending_group_ids": sorted(offending_groups),
        "offending_item_ids": sorted(offending_items),
        "scoring_blocked": detected,
        "blocking_reason": (
            "SYNTHETIC_GROUP_CROSSES_SPLIT_ROLES" if detected else None
        ),
    }
    m16_contracts.validate_leakage_report(report)
    return report


def _prediction_category(row):
    if row["execution_state"] != "COMPLETED":
        return row["execution_state"]
    return {
        "EMITTED": "PREDICTION_EMITTED",
        "ABSTAINED": "ABSTAINED",
        "UNKNOWN": "OUTCOME_UNKNOWN",
        "NOT_APPLICABLE": "PREDICTION_NOT_APPLICABLE",
    }[row["outcome_state"]]


def _metrics(public_manifest, predictions, key):
    expected_by_id = {
        row["item_id"]: row["expected_software_outcome"]
        for row in key["items"]
    }
    public_by_id = {item["item_id"]: item for item in public_manifest["items"]}
    counts = {category: 0 for category in m16_contracts.PREDICTION_CATEGORIES}
    n_labelled = 0
    n_unknown = 0
    n_not_applicable = 0
    n_emitted = 0
    n_exact = 0
    outcome_rows = {}
    for row in predictions:
        counts[_prediction_category(row)] += 1
        item = public_by_id[row["item_id"]]
        label_state = item["label_state"]
        if label_state == "UNKNOWN":
            n_unknown += 1
            continue
        if label_state == "NOT_APPLICABLE":
            n_not_applicable += 1
            continue
        n_labelled += 1
        expected = expected_by_id[row["item_id"]]
        outcome_id = m16_contracts.semantic_sha256(expected)
        aggregate = outcome_rows.setdefault(
            outcome_id,
            {"outcome_id": outcome_id, "n_labelled": 0,
             "n_emitted": 0, "n_exact_match": 0},
        )
        aggregate["n_labelled"] += 1
        if (
            row["execution_state"] == "COMPLETED"
            and row["outcome_state"] == "EMITTED"
        ):
            n_emitted += 1
            aggregate["n_emitted"] += 1
            if m16_contracts.canonical_json_bytes(
                row["emitted_value"]
            ) == m16_contracts.canonical_json_bytes(expected):
                n_exact += 1
                aggregate["n_exact_match"] += 1
    def rate(numerator, denominator):
        if denominator == 0:
            return None
        value = (
            Decimal(numerator) / Decimal(denominator)
        ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        return m16_contracts.FixedRate(value)

    result = {
        "schema": m16_contracts.METRIC_SCHEMA,
        "scope": "SOFTWARE_CONTRACT",
        "rate_precision": m16_contracts.RATE_PRECISION,
        "n_items": len(public_manifest["items"]),
        "prediction_counts": counts,
        "n_labelled": n_labelled,
        "n_unknown_label": n_unknown,
        "n_not_applicable_label": n_not_applicable,
        "n_emitted": n_emitted,
        "n_exact_match": n_exact,
        "coverage": rate(n_emitted, n_labelled),
        "fixture_agreement_rate": rate(n_exact, n_emitted),
        "fixture_match_over_labelled": rate(n_exact, n_labelled),
        "outcome_rows": [outcome_rows[key] for key in sorted(outcome_rows)],
    }
    return result


def _custody_event(events, destination, reason, *, target_digest=None,
                   prediction_digest=None, key_digest=None):
    current = events[-1]["to_state"] if events else None
    events.append({
        "sequence": len(events) + 1,
        "from_state": current,
        "to_state": destination,
        "actor": "m16-synthetic-benchmark",
        "tool_identity": "m16-stage-v1",
        "digests": {
            "target_binding_sha256": target_digest,
            "prediction_sha256": prediction_digest,
            "canonical_sealed_key_sha256": key_digest,
        },
        "reason": reason,
    })


def _custody_document(events):
    terminal = events[-1]["to_state"]
    return {
        "schema": m16_contracts.CUSTODY_SCHEMA,
        "events": events,
        "terminal_state": terminal,
    }


def _scorer_identity():
    return {
        "schema": "m16-scorer-identity-v1",
        "implementation": _source_identity(),
        "scoring_version": SCORER_VERSION,
    }


def _write_document(folder, filename, value):
    path = Path(folder) / filename
    digest = m16_contracts.write_json(path, value)
    return path, digest


def _load_existing(output, cache_identity):
    output = Path(output)
    marker = output / "manifest.json"
    if marker.is_symlink() or not marker.is_file():
        return None
    try:
        manifest = m16_contracts.read_json(marker, label="M16 stage manifest")
        if (
            manifest.get("schema") != "m16-stage-manifest-v1"
            or manifest.get("status") != "complete"
            or manifest.get("stage") != STAGE_KIND
            or manifest.get("stage_version") != STAGE_VERSION
            or manifest.get("identity") != cache_identity
            or set(manifest.get("output_sha256", {})) != set(OUTPUT_CONTRACTS)
        ):
            return None
        for name, artifact_type in OUTPUT_CONTRACTS.items():
            path = output / name
            if (
                path.is_symlink()
                or not path.is_file()
                or m16_contracts.sha256_file(path)
                    != manifest["output_sha256"].get(name)
            ):
                return None
            artifact_contracts.validate_artifact(path, artifact_type)
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _existing_output_is_valid(output):
    output = Path(output)
    marker = output / "manifest.json"
    try:
        manifest = m16_contracts.read_json(
            marker, label="Existing M16 stage manifest"
        )
        if (
            manifest.get("schema") != "m16-stage-manifest-v1"
            or manifest.get("status") != "complete"
            or manifest.get("stage") != STAGE_KIND
            or manifest.get("stage_version") != STAGE_VERSION
            or set(manifest.get("output_sha256", {})) != set(OUTPUT_CONTRACTS)
        ):
            return False
        for name, artifact_type in OUTPUT_CONTRACTS.items():
            path = output / name
            if (
                path.is_symlink()
                or not path.is_file()
                or m16_contracts.sha256_file(path)
                != manifest["output_sha256"].get(name)
            ):
                return False
            artifact_contracts.validate_artifact(path, artifact_type)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _managed_output_state(output):
    output = Path(output)
    if not output.exists():
        return "EMPTY"
    if output.is_symlink() or not output.is_dir():
        return "UNSAFE"
    names = {path.name for path in output.iterdir()}
    if not names:
        return "EMPTY"
    marker = output / "manifest.json"
    if marker.is_file() and not marker.is_symlink():
        try:
            value = m16_contracts.read_json(marker, label="Existing M16 stage manifest")
        except (OSError, ValueError):
            return "UNVERIFIED"
        if value.get("schema") == "m16-stage-manifest-v1":
            return "MANAGED"
    allowed_partial = {
        "predictions.json", "leakage_report.json", "custody_log.json",
    }
    return "PARTIAL" if names <= allowed_partial else "UNVERIFIED"


def _publish_directory(temporary, output):
    temporary = Path(temporary)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    state = _managed_output_state(output)
    if state == "UNSAFE" or state == "UNVERIFIED":
        raise M16IntegrityError(
            "INTEGRITY_FAILED: existing M16 output is unsafe or unverified"
        )
    if state == "EMPTY":
        if output.exists():
            output.rmdir()
        os.replace(temporary, output)
        return
    backup_parent = Path(tempfile.mkdtemp(
        prefix=".m16-replace-", dir=output.parent
    ))
    backup = backup_parent / "previous"
    try:
        os.replace(output, backup)
        os.replace(temporary, output)
        shutil.rmtree(backup)
    except Exception:
        if not output.exists() and backup.exists():
            os.replace(backup, output)
        raise
    finally:
        if backup_parent.exists():
            shutil.rmtree(backup_parent, ignore_errors=True)


def _verify_prediction_commit(path, expected_sha256):
    if m16_contracts.sha256_file(path) != expected_sha256:
        raise M16IntegrityError(
            "INTEGRITY_FAILED: committed prediction bytes changed before scoring"
        )


def _after_prediction_commit(_prediction_path):
    """Explicit hook for the post-commit integrity boundary and its tests."""


def _terminal_failure(output, temporary, events, message, *, target_digest=None,
                      prediction_digest=None, key_digest=None):
    if not events or events[-1]["to_state"] != "INTEGRITY_FAILED":
        _custody_event(
            events, "INTEGRITY_FAILED", message,
            target_digest=target_digest,
            prediction_digest=prediction_digest,
            key_digest=key_digest,
        )
    _write_document(temporary, "custody_log.json", _custody_document(events))
    _publish_directory(temporary, output)
    shutil.rmtree(temporary.parent, ignore_errors=True)
    raise M16IntegrityError(f"INTEGRITY_FAILED: {message}")


def run_stage(inputs, output, config, *, workflow_context=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".m16-stage-", dir=output.parent
    ) as temporary_root:
        return _run_stage_impl(
            inputs,
            output,
            config,
            workflow_context=workflow_context,
            temp_root=Path(temporary_root),
        )


def _run_stage_impl(inputs, output, config, *, workflow_context=None, temp_root):
    validate_config(config)
    if not isinstance(workflow_context, dict):
        workflow_context = build_stage_context(inputs)
    fresh = build_stage_context(inputs)
    if fresh.get("cache_identity") != workflow_context.get("cache_identity"):
        raise M16IntegrityError(
            "INTEGRITY_FAILED: M16 public inputs or target changed after cache projection"
        )
    public_manifest = fresh.get("public_manifest")
    if public_manifest is None:
        raise DependencyMissingError(
            "M16 public manifest is unavailable",
            {"status": "unavailable", "dependency": "m16_public_manifest"},
        )
    output = Path(output)
    temp_root = Path(temp_root)
    temporary = temp_root / "stage"
    temporary.mkdir()
    events = []
    target_digest = (
        fresh.get("target", {}).get("binding_sha256")
        if fresh.get("target") else None
    )
    _custody_event(
        events, "SEALED",
        "Opaque custodian commitment recorded; key content and path are unavailable to public execution.",
        target_digest=target_digest,
    )
    existing_output_state = _managed_output_state(output)
    if existing_output_state == "MANAGED" and not _existing_output_is_valid(output):
        _terminal_failure(
            output, temporary, events,
            "EXISTING_M16_OUTPUT_TAMPERED_OR_INVALID",
            target_digest=target_digest,
        )
    if existing_output_state in {"UNSAFE", "UNVERIFIED"}:
        raise M16IntegrityError(
            "INTEGRITY_FAILED: existing M16 output is unsafe or unverified"
        )
    if fresh.get("target_status") == "DEPENDENCY_UNAVAILABLE":
        shutil.rmtree(temp_root, ignore_errors=True)
        raise DependencyMissingError(
            "M16 target producer dependency is unavailable",
            {"status": "unavailable", "reason_code": fresh.get("target_error")},
        )
    if fresh.get("target_status") != "AVAILABLE" or fresh.get("target") is None:
        _terminal_failure(
            output, temporary, events,
            fresh.get("target_error") or "M16 target identity verification failed",
            target_digest=target_digest,
        )

    prediction_provenance = fresh["target_provenance"]
    predictions = {
        "schema": m16_contracts.PREDICTION_SCHEMA,
        "fixture_set_id": public_manifest["fixture_set_id"],
        "adapter_id": public_manifest["adapter_id"],
        "adapter_version": public_manifest["adapter_version"],
        "target_provenance": prediction_provenance,
        "rows": _execute_public(
            public_manifest,
            fresh["target"],
            fresh["query_inputs"],
            public_manifest["adapter_id"],
            public_manifest["adapter_version"],
        ),
    }
    m16_contracts.validate_prediction_table(predictions)
    prediction_path, prediction_digest = _write_document(
        temporary, "predictions.json", predictions
    )
    leakage = _leakage_report(public_manifest["items"])
    _write_document(temporary, "leakage_report.json", leakage)
    _custody_event(
        events, "PREDICTIONS_COMMITTED",
        "Canonical prediction artifact was written and its bytes were hashed before key access.",
        target_digest=target_digest,
        prediction_digest=prediction_digest,
    )
    _write_document(temporary, "custody_log.json", _custody_document(events))
    try:
        _after_prediction_commit(prediction_path)
    except BaseException:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    try:
        _verify_prediction_commit(prediction_path, prediction_digest)
    except M16IntegrityError as error:
        _terminal_failure(
            output, temporary, events, str(error),
            target_digest=target_digest,
            prediction_digest=prediction_digest,
        )
    if leakage["scoring_blocked"]:
        _terminal_failure(
            output, temporary, events,
            "SYNTHETIC_GROUP_CROSSES_SPLIT_ROLES",
            target_digest=target_digest,
            prediction_digest=prediction_digest,
        )

    _custody_event(
        events, "BLINDED_CHECKED",
        "Public executor received only the public manifest, verified target artifacts, and query fixtures; no key path, key content, or expected outcomes were passed.",
        target_digest=target_digest,
        prediction_digest=prediction_digest,
    )
    _write_document(temporary, "custody_log.json", _custody_document(events))

    key_path = _input_path(inputs, "sealed_key")
    if key_path is None or key_path.is_symlink() or not key_path.is_file():
        _terminal_failure(
            output, temporary, events,
            "SEALED_KEY_UNAVAILABLE_OR_UNSAFE",
            target_digest=target_digest,
            prediction_digest=prediction_digest,
        )
    try:
        key_value = m16_contracts.read_json(
            key_path, label="M16 sealed synthetic key"
        )
        key = m16_contracts.validate_synthetic_key(key_value, public_manifest)
        for row in key["items"]:
            m16_contracts.validate_projection(row["expected_software_outcome"])
        canonical_key_digest = m16_contracts.semantic_sha256(key)
    except (OSError, ValueError, KeyError, TypeError) as error:
        _terminal_failure(
            output, temporary, events,
            f"SEALED_KEY_INVALID: {error}",
            target_digest=target_digest,
            prediction_digest=prediction_digest,
        )
    try:
        _verify_prediction_commit(prediction_path, prediction_digest)
    except M16IntegrityError as error:
        _terminal_failure(
            output, temporary, events, str(error),
            target_digest=target_digest,
            prediction_digest=prediction_digest,
            key_digest=canonical_key_digest,
        )

    metrics = _metrics(public_manifest, predictions["rows"], key)
    try:
        m16_contracts.validate_metric_summary(
            json.loads(
                (m16_contracts.canonical_json_bytes(metrics)).decode("utf-8"),
                parse_float=Decimal,
            )
        )
    except (ValueError, TypeError) as error:
        _terminal_failure(
            output, temporary, events,
            f"METRIC_INTEGRITY_FAILED: {error}",
            target_digest=target_digest,
            prediction_digest=prediction_digest,
            key_digest=canonical_key_digest,
        )
    _write_document(temporary, "metric_summary.json", metrics)
    _custody_event(
        events, "SCORED",
        "Scorer opened the sealed key only after prediction commitment and blinding checks.",
        target_digest=target_digest,
        prediction_digest=prediction_digest,
        key_digest=canonical_key_digest,
    )
    _write_document(temporary, "custody_log.json", _custody_document(events))
    try:
        _verify_prediction_commit(prediction_path, prediction_digest)
    except M16IntegrityError as error:
        (temporary / "metric_summary.json").unlink(missing_ok=True)
        _terminal_failure(
            output, temporary, events, str(error),
            target_digest=target_digest,
            prediction_digest=prediction_digest,
            key_digest=canonical_key_digest,
        )

    sidecar_hashes = {
        name: m16_contracts.sha256_file(temporary / name)
        for name in m16_contracts.SIDE_CAR_CONTRACTS
    }
    scoring_identity = {
        "schema": "m16-scoring-identity-v1",
        "execution_identity_sha256": fresh["execution_identity_sha256"],
        "canonical_sealed_key_sha256": canonical_key_digest,
        "committed_prediction_sha256": prediction_digest,
        "scorer_identity": _scorer_identity(),
        "scoring_version": SCORER_VERSION,
        "sidecar_sha256": sidecar_hashes,
    }
    stage_cache_identity = {
        "schema": "m16-stage-cache-key-v1",
        "execution_identity_sha256": fresh["execution_identity_sha256"],
        "canonical_sealed_key_sha256": canonical_key_digest,
        "scorer_identity": _scorer_identity(),
        "scoring_version": SCORER_VERSION,
    }
    outputs = {}
    for name, artifact_type in m16_contracts.SIDE_CAR_CONTRACTS.items():
        sidecar = m16_contracts.read_json(
            temporary / name, label=f"M16 sidecar {name}"
        )
        outputs[name] = {
            "artifact_type": artifact_type,
            "contract_version": artifact_contracts.CONTRACT_VERSION,
            "schema": sidecar["schema"],
            "sha256": sidecar_hashes[name],
        }
    result_bundle = {
        "schema": m16_contracts.RESULT_BUNDLE_SCHEMA,
        "scope": "SOFTWARE_CONTRACT",
        "fixture_set_id": public_manifest["fixture_set_id"],
        "public_manifest_semantic_sha256":
            fresh["public_manifest_semantic_sha256"],
        "sealed_key_commitment": public_manifest["sealed_key_commitment"],
        "canonical_sealed_key_sha256": canonical_key_digest,
        "target_identity": fresh["target_identity"],
        "adapter_id": public_manifest["adapter_id"],
        "adapter_version": public_manifest["adapter_version"],
        "outcome_schema_version": m16_contracts.OUTCOME_SCHEMA_VERSION,
        "prediction_sha256": prediction_digest,
        "execution_identity_sha256": fresh["execution_identity_sha256"],
        "scoring_identity": scoring_identity,
        "stage_cache_identity": stage_cache_identity,
        "outputs": outputs,
    }
    _write_document(temporary, "result_bundle.json", result_bundle)
    output_hashes = {
        name: m16_contracts.sha256_file(temporary / name)
        for name in OUTPUT_CONTRACTS
    }
    for name, artifact_type in OUTPUT_CONTRACTS.items():
        artifact_contracts.validate_artifact(temporary / name, artifact_type)
    stage_manifest = {
        "schema": "m16-stage-manifest-v1",
        "status": "complete",
        "stage": STAGE_KIND,
        "stage_version": STAGE_VERSION,
        "identity": stage_cache_identity,
        "output_sha256": output_hashes,
    }
    m16_contracts.write_json(temporary / "manifest.json", stage_manifest)
    existing = _load_existing(output, stage_cache_identity)
    if existing is not None:
        shutil.rmtree(temp_root, ignore_errors=True)
        return existing
    try:
        _publish_directory(temporary, output)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise
    shutil.rmtree(temp_root, ignore_errors=True)
    return stage_manifest


run_stage.cache_implementation_identity = _source_identity
