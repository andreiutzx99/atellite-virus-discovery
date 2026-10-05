"""M13 M5-only, caller-scoped evidence matrix stage."""

import copy
import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile

from . import (
    artifact_contracts,
    dvg_evidence,
    execution_outcome,
    external_tool,
    m12_contracts,
    m13_contracts,
    stage_cache_identity,
    virema_adapter,
)
from .virema_adapter import CALLER_NAME, CALLER_VERSION


STAGE_KIND = "m13_m5_evidence_matrix"
STAGE_VERSION = "1"
OUTPUT_CONTRACTS = {
    "event_index.json": "m13_event_index",
    "hypothesis_matrix.json": "m13_hypothesis_matrix",
    "summary.json": "m13_summary",
    "result_bundle.json": "m13_result_bundle",
}
OUTPUT_SCHEMA_VERSION = "m13-output-schema-v1"
CACHE_INPUT_SEMANTICS_VERSION = "m13-input-and-execution-outcome-v1"
WORKFLOW_BINDING_SEMANTICS_VERSION = "m13-explicit-typed-m5-artifact-inputs-v1"

LIMITATIONS = [
    "M5 observations are caller-scoped and do not establish biological identity or absence.",
    "M13 does not infer DVG or satellite status, helper dependence, interference, or function.",
    "No cross-caller normalization, event merging, vote counting, or agreement is performed.",
]


def validate_config(config):
    if not isinstance(config, dict) or config:
        raise ValueError("M13 does not accept stage configuration")
    return {}


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_identity():
    source_sha256, line_profile = stage_cache_identity.stage_source_identity(
        STAGE_KIND,
        ("satellite_discovery.m13_stage",),
        {
            "m13_input_manifest",
            *m13_contracts.M5_ARTIFACT_TYPES,
            *OUTPUT_CONTRACTS.values(),
        },
        semantic_version=m13_contracts.SEMANTIC_VERSION,
        output_schema_version=OUTPUT_SCHEMA_VERSION,
    )
    source_sha256 = (
        stage_cache_identity.legacy_stage_source_identity(
            STAGE_KIND, source_sha256, line_profile
        )
        or source_sha256
    )
    return {
        "schema": "m13-stage-implementation-v1",
        "semantic_version": m13_contracts.SEMANTIC_VERSION,
        "source_sha256": source_sha256,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
    }


def register_stage(registry):
    input_types = sorted({
        "m13_input_manifest",
        *m13_contracts.M5_ARTIFACT_TYPES,
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
            "Imports explicitly referenced, validated M5 ViReMa artifacts and "
            "emits caller-scoped observations without classification."
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
    root = path
    for _part in parts:
        root = root.parent
    resolved_path = path.resolve(strict=True)
    resolved_root = root.resolve(strict=True)
    expected = resolved_root.joinpath(*parts).resolve(strict=True)
    if not resolved_path.is_relative_to(resolved_root) or resolved_path != expected:
        raise ValueError("M13 artifact path does not match its producer-relative reference")
    return resolved_root


def _check_no_symlink_between(root, path):
    root = Path(root).resolve(strict=True)
    path = Path(path)
    if path.is_symlink():
        raise ValueError("M13 source artifact must not be a symbolic link")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("M13 source artifact escapes its producer output")
    current = root
    relative = resolved.relative_to(root)
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("M13 source artifact path contains a symbolic link")
    return resolved


def _read_stage_manifest(stage_root, expected_digest, producer_stage_id, producer_status):
    marker = Path(stage_root) / "manifest.json"
    if not _regular_file(marker):
        raise OSError("M5 producer stage manifest is unavailable")
    marker_digest = _sha256_file(marker)
    if marker_digest != expected_digest:
        raise ValueError("M5 producer stage-manifest digest does not match")
    value = m13_contracts.read_json(marker)
    if value.get("schema") != "external-tool-stage-v1":
        raise ValueError("M5 producer manifest schema is not an external-tool stage")
    if producer_status == "complete" and value.get("status") != "complete":
        raise ValueError("Completed M5 run has a noncompleted producer manifest")
    identity = value.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("M5 producer manifest identity is missing")
    declared_stage_id = identity.get("stage_id")
    if declared_stage_id is not None and declared_stage_id != producer_stage_id:
        raise ValueError("M5 producer stage ID does not match")
    adapter = identity.get("adapter")
    if not isinstance(adapter, dict) or adapter.get("name") != "virema-dvg-adapter":
        raise ValueError("M5 producer manifest is not the registered ViReMa adapter")
    if not isinstance(value.get("output_sha256"), dict):
        raise ValueError("M5 producer manifest has no output inventory")
    return value, marker_digest


def _workflow_stage(workflow, stage_id):
    stages = workflow.get("stages")
    if not isinstance(stages, list):
        raise ValueError("Referenced workflow has no stage records")
    matches = [
        stage for stage in stages
        if isinstance(stage, dict) and stage.get("id") == stage_id
    ]
    if len(matches) != 1:
        raise ValueError("Referenced workflow stage is absent or duplicated")
    stage = matches[0]
    if (stage.get("evidence_family") != "dvg"
            or stage.get("caller") != CALLER_NAME
            or stage.get("caller_version") != CALLER_VERSION):
        raise ValueError("Referenced workflow stage is not the registered ViReMa M5 producer")
    return stage


def _verify_execution_refs(input_manifest_path, run):
    try:
        verified = execution_outcome.verify_execution_outcome_refs(
            input_manifest_path,
            run["producer_workflow_ref"],
            run["execution_record_ref"],
            expected_stage_id=run["producer_stage_id"],
        )
        workflow = verified["workflow"]
        record = verified["record"]
        stage = _workflow_stage(workflow, run["producer_stage_id"])
        if stage.get("status") != run["producer_status"]:
            raise execution_outcome.ExecutionOutcomeInvalidError(
                "M13 declared M1 stage status does not match the verified workflow"
            )
        if record["producer_execution_status_raw"] != run["producer_status"]:
            raise execution_outcome.ExecutionOutcomeInvalidError(
                "M13 declared M1 stage status does not match the execution record"
            )
        if record["producer_status_raw"] not in m13_contracts.M5_EVIDENCE_STATUSES:
            raise execution_outcome.ExecutionOutcomeInvalidError(
                "Verified M5 evidence status is unsupported"
            )
        return {
            "verification_state": "VERIFIED",
            "workflow": workflow,
            "record": record,
            "stage": stage,
            "workflow_sha256": verified["workflow_sha256"],
            "execution_record_sha256": verified["execution_record_sha256"],
            "error_code": None,
        }
    except execution_outcome.ExecutionOutcomeIncompleteError as error:
        workflow = error.workflow
        if not isinstance(workflow, dict):
            return {
                "verification_state": "INCOMPLETE",
                "workflow": None,
                "record": None,
                "stage": None,
                "workflow_sha256": run["producer_workflow_ref"]["sha256"],
                "execution_record_sha256": run["execution_record_ref"]["sha256"],
                "error_code": "WORKFLOW_NONTERMINAL",
            }
        try:
            stage = _workflow_stage(workflow, run["producer_stage_id"])
            if stage.get("status") != run["producer_status"]:
                raise ValueError("M13 declared state does not match the workflow")
            return {
                "verification_state": "INCOMPLETE",
                "workflow": workflow,
                "record": None,
                "stage": stage,
                "workflow_sha256": run["producer_workflow_ref"]["sha256"],
                "execution_record_sha256": run["execution_record_ref"]["sha256"],
                "error_code": "WORKFLOW_NONTERMINAL",
            }
        except (ValueError, KeyError, TypeError):
            return {
                "verification_state": "INVALID",
                "workflow": workflow,
                "record": None,
                "stage": None,
                "workflow_sha256": run["producer_workflow_ref"]["sha256"],
                "execution_record_sha256": run["execution_record_ref"]["sha256"],
                "error_code": "WORKFLOW_STAGE_IDENTITY_INVALID",
            }
    except execution_outcome.ExecutionOutcomeUnavailableError:
        return {
            "verification_state": "UNAVAILABLE",
            "workflow": None,
            "record": None,
            "stage": None,
            "workflow_sha256": run["producer_workflow_ref"]["sha256"],
            "execution_record_sha256": run["execution_record_ref"]["sha256"],
            "error_code": "EXECUTION_RECORD_UNAVAILABLE",
        }
    except (execution_outcome.ExecutionOutcomeInvalidError, ValueError, KeyError, TypeError):
        return {
            "verification_state": "INVALID",
            "workflow": None,
            "record": None,
            "stage": None,
            "workflow_sha256": run["producer_workflow_ref"]["sha256"],
            "execution_record_sha256": run["execution_record_ref"]["sha256"],
            "error_code": "EXECUTION_RECORD_INVALID",
        }


def _stage_output_root_from_workflow(input_manifest_path, run, execution):
    workflow = execution.get("workflow")
    if not isinstance(workflow, dict):
        return None
    stage = execution.get("stage") or _workflow_stage(
        workflow, run["producer_stage_id"]
    )
    output_path = stage.get("output_path")
    if not isinstance(output_path, str):
        return None
    relative = PurePosixPath(output_path)
    if (not output_path or relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or "\\" in output_path):
        raise ValueError("Referenced M5 output path is unsafe")
    workflow_path = (
        Path(input_manifest_path).parent
        / PurePosixPath(run["producer_workflow_ref"]["path"])
    )
    root = workflow_path.parent.resolve(strict=True)
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Referenced M5 stage output contains a symbolic link")
    return candidate.resolve(strict=False)


def _resolve_artifact_inputs(run_index, run, input_paths, input_failures):
    refs = []
    roots = set()
    error_state = None
    for ref in run["artifacts"]:
        input_name = m13_contracts.artifact_input_name(
            run_index, ref["artifact_type"]
        )
        failure = input_failures.get(input_name)
        path = input_paths.get(input_name)
        row = {
            "input_name": input_name,
            "artifact_ref": ref,
            "path": None,
            "sha256": None,
            "contract_version": None,
            "stage_root": None,
            "verification_state": "UNAVAILABLE",
            "error_code": "ARTIFACT_INPUT_UNAVAILABLE",
        }
        if failure is not None:
            row["verification_state"] = failure
            row["error_code"] = (
                "ARTIFACT_INPUT_INVALID" if failure == "INVALID"
                else "ARTIFACT_INPUT_UNAVAILABLE"
            )
            if failure == "INVALID":
                error_state = "INVALID"
            elif error_state is None:
                error_state = "UNAVAILABLE"
            refs.append(row)
            continue
        if path is None:
            if error_state is None:
                error_state = "UNAVAILABLE"
            refs.append(row)
            continue
        try:
            path = Path(path)
            if not _regular_file(path):
                raise OSError("M5 artifact input is unavailable")
            root = _producer_root(path, ref["relative_path"])
            resolved_path = _check_no_symlink_between(root, path)
            artifact_contracts.validate_artifact(resolved_path, ref["artifact_type"])
            actual_sha = _sha256_file(resolved_path)
            if actual_sha != ref["sha256"]:
                raise ValueError("M5 artifact digest does not match its reference")
            current_version = artifact_contracts.semantic_identity(
                ref["artifact_type"]
            )["contracts"][ref["artifact_type"]]
            if current_version != ref["artifact_contract_version"]:
                raise ValueError("M5 artifact contract version does not match")
            if ref["producer_status"] != run["producer_status"]:
                raise ValueError("M5 artifact producer status does not match its run")
            row.update(
                path=str(resolved_path),
                sha256=actual_sha,
                contract_version=current_version,
                stage_root=str(root),
                verification_state="AVAILABLE",
                error_code=None,
            )
            roots.add(str(root))
        except OSError:
            row["verification_state"] = "UNAVAILABLE"
            row["error_code"] = "ARTIFACT_INPUT_UNAVAILABLE"
            if error_state is None:
                error_state = "UNAVAILABLE"
        except (ValueError, KeyError, TypeError, UnicodeError):
            row["verification_state"] = "INVALID"
            row["error_code"] = "ARTIFACT_INPUT_INVALID"
            error_state = "INVALID"
        refs.append(row)
    if len(roots) > 1:
        error_state = "INVALID"
        for row in refs:
            if row["verification_state"] == "AVAILABLE":
                row["verification_state"] = "INVALID"
                row["error_code"] = "ARTIFACTS_DO_NOT_SHARE_PRODUCER_ROOT"
    return refs, (next(iter(roots)) if len(roots) == 1 else None), error_state


def _verify_producer_manifest(run, artifact_rows, artifact_root, execution, manifest_path):
    digest = run["producer_run_manifest_sha256"]
    if digest is None:
        return {
            "verification_state": "NOT_REQUIRED",
            "manifest": None,
            "stage_root": artifact_root,
            "sha256": None,
            "error_code": None,
        }
    stage_root = artifact_root
    if stage_root is None and run["producer_status"] != "complete":
        try:
            stage_root = _stage_output_root_from_workflow(
                manifest_path, run, execution
            )
        except OSError:
            stage_root = None
    if stage_root is None:
        return {
            "verification_state": "UNAVAILABLE",
            "manifest": None,
            "stage_root": None,
            "sha256": None,
            "error_code": "PRODUCER_MANIFEST_UNAVAILABLE",
        }
    try:
        value, actual = _read_stage_manifest(
            stage_root,
            digest,
            run["producer_stage_id"],
            run["producer_status"],
        )
        for row in artifact_rows:
            if row["verification_state"] != "AVAILABLE":
                continue
            ref = row["artifact_ref"]
            if value["output_sha256"].get(ref["relative_path"]) != ref["sha256"]:
                raise ValueError("M5 output inventory digest does not match its artifact")
        return {
            "verification_state": "VERIFIED",
            "manifest": value,
            "stage_root": str(Path(stage_root).resolve(strict=True)),
            "sha256": actual,
            "error_code": None,
        }
    except OSError:
        return {
            "verification_state": "UNAVAILABLE",
            "manifest": None,
            "stage_root": str(stage_root),
            "sha256": None,
            "error_code": "PRODUCER_MANIFEST_UNAVAILABLE",
        }
    except (ValueError, KeyError, TypeError):
        return {
            "verification_state": "INVALID",
            "manifest": None,
            "stage_root": str(stage_root),
            "sha256": None,
            "error_code": "PRODUCER_MANIFEST_INVALID",
        }


def _parse_completed_payloads(run, artifact_rows, producer_manifest):
    by_type = {
        row["artifact_ref"]["artifact_type"]: row
        for row in artifact_rows
    }
    required = m13_contracts.REQUIRED_COMPLETED_TYPES
    if not required <= set(by_type):
        raise ValueError("Completed M5 artifact set is incomplete")
    if producer_manifest.get("status") != "complete":
        raise ValueError("Completed M5 run manifest is not complete")

    payloads = {}
    for artifact_type in required:
        path = by_type[artifact_type]["path"]
        if path is None:
            raise OSError("Required M5 artifact is unavailable")
        payloads[artifact_type] = m13_contracts.read_json(path)
    evidence = payloads["dvg_evidence"]
    summary = payloads["dvg_evidence_summary"]
    parameters = payloads["dvg_parameters"]
    dvg_evidence.validate_evidence_document(evidence)
    dvg_evidence.validate_summary(summary)
    events = evidence.get("events")
    if not isinstance(events, list):
        raise ValueError("Validated M5 evidence has no events array")
    if (summary.get("status") != evidence.get("status")
            or summary.get("event_count") != len(events)
            or summary.get("caller") != evidence.get("caller")):
        raise ValueError("M5 summary and evidence accounting disagree")
    if (parameters.get("schema") != "dvg-parameters-v1"
            or parameters.get("caller") != CALLER_NAME
            or parameters.get("caller_version") != CALLER_VERSION
            or evidence.get("caller") != CALLER_NAME):
        raise ValueError("M5 run is not the validated ViReMa producer")
    if evidence.get("caller_version") not in (None, CALLER_VERSION):
        raise ValueError("M5 event document caller version does not match ViReMa")
    if summary.get("caller_version") not in (None, CALLER_VERSION):
        raise ValueError("M5 summary caller version does not match ViReMa")
    if (summary.get("status") not in {
            "DVG_EVIDENCE_DETECTED", "NO_DVG_EVIDENCE_DETECTED"}):
        raise ValueError("Completed M5 run has a noncompleted evidence status")
    input_sha = parameters.get("input_sha256")
    if not isinstance(input_sha, dict):
        raise ValueError("M5 parameters have no input identity")
    reference_sha = input_sha.get("reference")
    if not isinstance(reference_sha, str) or not m13_contracts._HASH_RE.fullmatch(reference_sha):
        raise ValueError("M5 parameters have no valid reference digest")
    if summary["status"] == "DVG_EVIDENCE_DETECTED" and not events:
        raise ValueError("M5 detected-event status has an empty event array")
    if summary["status"] == "NO_DVG_EVIDENCE_DETECTED" and events:
        raise ValueError("M5 completed-zero status has nonempty events")
    return {
        "caller": CALLER_NAME,
        "caller_version": CALLER_VERSION,
        "reference_sha256": reference_sha,
        "status": summary["status"],
        "events": events,
        "event_count": len(events),
        "evidence": evidence,
        "summary": summary,
        "parameters": parameters,
    }


def _execution_state(run, execution):
    if execution["verification_state"] != "VERIFIED":
        if execution["verification_state"] == "INCOMPLETE":
            stage = execution.get("stage")
            return {
                "run_import_state": "INCOMPLETE",
                "producer_execution_status_raw": (
                    stage.get("status") if isinstance(stage, dict) else None
                ),
                "producer_status_raw": (
                    _workflow_m5_status(stage) if isinstance(stage, dict) else None
                ),
                "outcome_code": None,
                "failure_code": None,
                "reason_code": execution["error_code"],
            }
        return {
            "run_import_state": execution["verification_state"],
            "producer_execution_status_raw": None,
            "producer_status_raw": None,
            "outcome_code": None,
            "failure_code": None,
            "reason_code": execution["error_code"],
        }
    record = execution["record"]
    if record["producer_execution_status_raw"] != run["producer_status"]:
        return {
            "run_import_state": "INVALID",
            "producer_execution_status_raw": record["producer_execution_status_raw"],
            "producer_status_raw": record["producer_status_raw"],
            "outcome_code": record["outcome_code"],
            "failure_code": record.get("failure_code"),
            "reason_code": "EXECUTION_STATUS_MISMATCH",
        }
    outcome = record["outcome_code"]
    failure = record.get("failure_code")
    if outcome == "NOT_STARTED":
        state = "NOT_SUPPLIED"
        reason = "PRODUCER_NOT_STARTED"
    elif outcome == "UNAVAILABLE":
        state = "UNAVAILABLE"
        reason = "PRODUCER_UNAVAILABLE"
    elif outcome == "FAILED":
        state = "IMPORTED_NONCOMPLETED"
        reason = "PRODUCER_RUNTIME_FAILURE"
    elif outcome == "INTERRUPTED":
        state = "INTERRUPTED"
        reason = "PRODUCER_INTERRUPTED"
    elif outcome == "INCOMPLETE_OUTPUT":
        state = "INCOMPLETE"
        reason = "PRODUCER_OUTPUT_INCOMPLETE"
    elif outcome == "INVALID_OUTPUT":
        incomplete_failures = {
            "TRUNCATED_OUTPUT",
            "INCOMPLETE_ACCOUNTING",
        }
        if failure in incomplete_failures:
            state = "INCOMPLETE"
            reason = "PRODUCER_OUTPUT_INCOMPLETE"
        else:
            state = "INVALID"
            reason = "PRODUCER_OUTPUT_INVALID"
    else:
        state = "INVALID"
        reason = "UNEXPECTED_NONCOMPLETED_OUTCOME"
    return {
        "run_import_state": state,
        "producer_execution_status_raw": record["producer_execution_status_raw"],
        "producer_status_raw": record["producer_status_raw"],
        "outcome_code": outcome,
        "failure_code": failure,
        "reason_code": reason,
    }


def _known_execution_statuses(execution):
    record = execution.get("record")
    if isinstance(record, dict):
        return (
            record.get("producer_execution_status_raw"),
            record.get("producer_status_raw"),
        )
    stage = execution.get("stage")
    if isinstance(stage, dict):
        return stage.get("status"), _workflow_m5_status(stage)
    return None, None


def _workflow_m5_status(stage):
    value = stage.get("dvg_evidence")
    if isinstance(value, dict) and isinstance(value.get("status"), str):
        return value["status"]
    state = stage.get("status")
    if state in {"pending", "running", "skipped"}:
        return dvg_evidence.NOT_EVALUATED
    if state in {"dependency_missing", "external_module_required"}:
        return dvg_evidence.ANALYSIS_UNAVAILABLE
    if state in {"failed", "interrupted"}:
        if stage.get("error_type") == "InvalidDVGResultError":
            return dvg_evidence.INVALID_RESULT
        return dvg_evidence.ANALYSIS_FAILED
    if state == "complete":
        return dvg_evidence.INVALID_RESULT
    return None


def _resolved_run(run_index, run, input_paths, input_failures, input_manifest_path):
    execution = None
    if run["producer_status"] != "complete":
        execution = _verify_execution_refs(input_manifest_path, run)

    artifact_rows, artifact_root, artifact_error = _resolve_artifact_inputs(
        run_index, run, input_paths, input_failures
    )
    producer_manifest = _verify_producer_manifest(
        run,
        artifact_rows,
        artifact_root,
        execution,
        input_manifest_path,
    )
    if execution is None:
        execution = {
            "verification_state": "NOT_REQUIRED",
            "workflow": None,
            "record": None,
            "stage": None,
            "workflow_sha256": None,
            "execution_record_sha256": None,
            "error_code": None,
        }

    artifact_states = [row["verification_state"] for row in artifact_rows]
    if "INVALID" in artifact_states or artifact_error == "INVALID":
        import_state = "INVALID"
        raw_m1, raw_m5 = _known_execution_statuses(execution)
        status_data = {
            "producer_execution_status_raw": raw_m1,
            "producer_status_raw": raw_m5,
            "outcome_code": None,
            "failure_code": None,
            "reason_code": "M5_ARTIFACT_INVALID",
        }
    elif "UNAVAILABLE" in artifact_states or artifact_error == "UNAVAILABLE":
        import_state = "UNAVAILABLE"
        raw_m1, raw_m5 = _known_execution_statuses(execution)
        status_data = {
            "producer_execution_status_raw": raw_m1,
            "producer_status_raw": raw_m5,
            "outcome_code": None,
            "failure_code": None,
            "reason_code": "M5_ARTIFACT_UNAVAILABLE",
        }
    elif producer_manifest["verification_state"] == "INVALID":
        import_state = "INVALID"
        raw_m1, raw_m5 = _known_execution_statuses(execution)
        status_data = {
            "producer_execution_status_raw": raw_m1,
            "producer_status_raw": raw_m5,
            "outcome_code": None,
            "failure_code": None,
            "reason_code": producer_manifest["error_code"],
        }
    elif producer_manifest["verification_state"] == "UNAVAILABLE":
        import_state = "UNAVAILABLE"
        raw_m1, raw_m5 = _known_execution_statuses(execution)
        status_data = {
            "producer_execution_status_raw": raw_m1,
            "producer_status_raw": raw_m5,
            "outcome_code": None,
            "failure_code": None,
            "reason_code": producer_manifest["error_code"],
        }
    elif run["producer_status"] == "complete":
        try:
            payloads = _parse_completed_payloads(
                run, artifact_rows, producer_manifest["manifest"]
            )
            status = payloads["status"]
            import_state = (
                "IMPORTED_WITH_EVENTS" if payloads["event_count"]
                else "IMPORTED_COMPLETED_ZERO"
            )
            if ((status == "DVG_EVIDENCE_DETECTED")
                    != (import_state == "IMPORTED_WITH_EVENTS")):
                raise ValueError("M5 completion status and validated events disagree")
            status_data = {
                "producer_execution_status_raw": "complete",
                "producer_status_raw": status,
                "outcome_code": (
                    "COMPLETED_EVENTS" if payloads["event_count"] else "COMPLETED_ZERO"
                ),
                "failure_code": None,
                "reason_code": (
                    "VALIDATED_M5_EVENTS" if payloads["event_count"]
                    else "VALIDATED_M5_COMPLETED_ZERO"
                ),
            }
            event_payloads = payloads
        except OSError:
            import_state = "UNAVAILABLE"
            event_payloads = None
            status_data = {
                "producer_execution_status_raw": "complete",
                "producer_status_raw": None,
                "outcome_code": None,
                "failure_code": None,
                "reason_code": "M5_REQUIRED_ARTIFACT_UNAVAILABLE",
            }
        except (ValueError, KeyError, TypeError, UnicodeError):
            import_state = "INVALID"
            event_payloads = None
            status_data = {
                "producer_execution_status_raw": "complete",
                "producer_status_raw": None,
                "outcome_code": None,
                "failure_code": None,
                "reason_code": "M5_ACCOUNTING_OR_CONTRACT_INVALID",
            }
    else:
        status_data = _execution_state(run, execution)
        import_state = status_data["run_import_state"]
        event_payloads = None

    if run["producer_status"] == "complete" and "event_payloads" not in locals():
        event_payloads = None
    resolved = {
        "producer_stage_id": run["producer_stage_id"],
        "producer_run_manifest_sha256": run["producer_run_manifest_sha256"],
        "producer_status": run["producer_status"],
        "producer_workflow_ref": run.get("producer_workflow_ref"),
        "execution_record_ref": run.get("execution_record_ref"),
        "artifact_states": run["artifact_states"],
        "artifact_refs": run["artifacts"],
        "artifact_inputs": artifact_rows,
        "artifact_error_state": artifact_error,
        "artifact_root": artifact_root,
        "producer_manifest": producer_manifest,
        "execution": execution,
        "run_import_state": import_state,
        "producer_execution_status_raw": status_data["producer_execution_status_raw"],
        "producer_status_raw": status_data["producer_status_raw"],
        "outcome_code": status_data["outcome_code"],
        "failure_code": status_data["failure_code"],
        "reason_code": status_data["reason_code"],
        "event_payloads": event_payloads,
        "event_count": (
            event_payloads["event_count"] if event_payloads is not None else None
        ),
        "caller": event_payloads["caller"] if event_payloads is not None else None,
        "caller_version": (
            event_payloads["caller_version"] if event_payloads is not None else None
        ),
        "reference_sha256": (
            event_payloads["reference_sha256"] if event_payloads is not None else None
        ),
    }
    resolved["cache_record"] = _cache_record(resolved)
    return resolved


def _cache_record(run):
    return {
        "producer_stage_id": run["producer_stage_id"],
        "producer_run_manifest_sha256": run["producer_run_manifest_sha256"],
        "producer_status": run["producer_status"],
        "producer_workflow_ref": run["producer_workflow_ref"],
        "execution_record_ref": run["execution_record_ref"],
        "artifact_states": dict(sorted(run["artifact_states"].items())),
        "artifact_refs": [
            {
                "producer_stage_id": item["producer_stage_id"],
                "producer_run_manifest_sha256": item["producer_run_manifest_sha256"],
                "producer_status": item["producer_status"],
                "artifact_type": item["artifact_type"],
                "relative_path": item["relative_path"],
                "sha256": item["sha256"],
                "artifact_contract_version": item["artifact_contract_version"],
            }
            for item in sorted(run["artifact_refs"], key=lambda ref: ref["artifact_type"])
        ],
        "resolved_artifacts": [
            {
                "artifact_type": row["artifact_ref"]["artifact_type"],
                "verification_state": row["verification_state"],
                "error_code": row["error_code"],
                "sha256": row["sha256"],
                "contract_version": row["contract_version"],
            }
            for row in sorted(
                run["artifact_inputs"],
                key=lambda item: item["artifact_ref"]["artifact_type"],
            )
        ],
        "producer_manifest": {
            "verification_state": run["producer_manifest"]["verification_state"],
            "sha256": run["producer_manifest"]["sha256"],
            "error_code": run["producer_manifest"]["error_code"],
        },
        "execution_outcome": {
            "verification_state": run["execution"]["verification_state"],
            "workflow_sha256": run["execution"]["workflow_sha256"],
            "execution_record_sha256": run["execution"]["execution_record_sha256"],
            "outcome_code": (
                run["execution"]["record"].get("outcome_code")
                if run["execution"]["record"] else None
            ),
            "producer_execution_status_raw": (
                run["execution"]["record"].get("producer_execution_status_raw")
                if run["execution"]["record"]
                else (
                    run["execution"]["stage"].get("status")
                    if run["execution"]["stage"] else None
                )
            ),
            "producer_status_raw": (
                run["execution"]["record"].get("producer_status_raw")
                if run["execution"]["record"]
                else (
                    _workflow_m5_status(run["execution"]["stage"])
                    if run["execution"]["stage"] else None
                )
            ),
            "failure_code": (
                run["execution"]["record"].get("failure_code")
                if run["execution"]["record"] else None
            ),
            "error_code": run["execution"]["error_code"],
        },
        "run_import_state": run["run_import_state"],
        "reason_code": run["reason_code"],
    }


def _stage_context(input_paths, binding_plan, input_failures=None):
    input_failures = input_failures or {}
    manifest_path = input_paths.get("manifest")
    if manifest_path is None:
        raise ValueError("M13 requires its explicit input manifest")
    manifest_path = Path(manifest_path)
    manifest = m13_contracts.load_input_manifest(manifest_path)
    manifest_sha = _sha256_file(manifest_path)
    if artifact_contracts.semantic_identity("m13_input_manifest")["contracts"][
            "m13_input_manifest"] != m13_contracts.OUTPUT_CONTRACT_VERSION:
        raise ValueError("M13 input contract semantic identity is inconsistent")

    runs = [
        _resolved_run(
            index,
            run,
            input_paths,
            input_failures,
            manifest_path,
        )
        for index, run in enumerate(manifest["m5_runs"])
    ]
    contract_types = {"m13_input_manifest"}
    contract_types.update(
        ref["artifact_type"]
        for run in manifest["m5_runs"]
        for ref in run["artifacts"]
    )
    contract_semantics = artifact_contracts.semantic_identity(contract_types)
    output_contract_semantics = artifact_contracts.semantic_identity(
        OUTPUT_CONTRACTS.values()
    )
    implementation = _source_identity()
    cache_identity = {
        "schema": "m13-stage-cache-context-v1",
        "input_schema": m13_contracts.INPUT_SCHEMA,
        "semantic_version": m13_contracts.SEMANTIC_VERSION,
        "candidate_id": manifest["candidate_id"],
        "input_manifest_sha256": manifest_sha,
        "resolved_runs": [run["cache_record"] for run in sorted(
            runs,
            key=lambda item: (
                item["producer_stage_id"],
                item["producer_run_manifest_sha256"] or "",
                item["execution_record_ref"]["sha256"]
                if item["execution_record_ref"] else "",
            ),
        )],
        "workflow_binding_semantics_version": WORKFLOW_BINDING_SEMANTICS_VERSION,
        "contract_semantics": contract_semantics,
        "output_contract_semantics": output_contract_semantics,
        "implementation": implementation,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
    }
    cache_sha = hashlib.sha256(
        m13_contracts.canonical_json_bytes(cache_identity)
    ).hexdigest()
    return {
        "input_manifest": manifest,
        "input_manifest_sha256": manifest_sha,
        "runs": runs,
        "cache_identity": cache_identity,
        "cache_identity_sha256": cache_sha,
        "implementation": implementation,
        "binding_plan": binding_plan,
        "input_failures": dict(input_failures),
    }


def build_stage_context(input_paths, binding_plan, input_failures=None):
    return _stage_context(input_paths, binding_plan, input_failures)


def _event_reference(run, evidence_sha, row_index):
    return {
        "producer_stage_id": run["producer_stage_id"],
        "producer_run_manifest_sha256": run["producer_run_manifest_sha256"],
        "dvg_evidence_sha256": evidence_sha,
        "source_row_index": row_index,
    }


def _build_event_index(context):
    candidate_id = context["input_manifest"]["candidate_id"]
    rows = []
    for run in context["runs"]:
        payload = run["event_payloads"]
        if payload is None or run["run_import_state"] != "IMPORTED_WITH_EVENTS":
            continue
        evidence_ref = next(
            ref for ref in run["artifact_refs"]
            if ref["artifact_type"] == "dvg_evidence"
        )
        run_ref = {
            "producer_stage_id": run["producer_stage_id"],
            "producer_run_manifest_sha256": run["producer_run_manifest_sha256"],
            "dvg_evidence_sha256": evidence_ref["sha256"],
        }
        for index, event in enumerate(payload["events"]):
            row = {
                "candidate_id": candidate_id,
                "m5_run_ref": run_ref,
                "caller": payload["caller"],
                "caller_version": payload["caller_version"],
                "reference_sha256": payload["reference_sha256"],
                "source_row_index": index,
                "source_event": copy.deepcopy(event),
            }
            if "evidence_id" in event:
                row["source_event_id"] = event["evidence_id"]
            rows.append(row)
    rows.sort(key=lambda row: (
        row["m5_run_ref"]["producer_stage_id"],
        row["m5_run_ref"]["producer_run_manifest_sha256"],
        row["source_row_index"],
    ))
    return {
        "schema": m13_contracts.EVENT_INDEX_SCHEMA,
        "candidate_id": candidate_id,
        "events": rows,
    }


def _event_refs(event_index):
    refs = []
    for row in event_index["events"]:
        refs.append({
            "producer_stage_id": row["m5_run_ref"]["producer_stage_id"],
            "producer_run_manifest_sha256": (
                row["m5_run_ref"]["producer_run_manifest_sha256"]
            ),
            "dvg_evidence_sha256": row["m5_run_ref"]["dvg_evidence_sha256"],
            "source_row_index": row["source_row_index"],
        })
    return refs


def _build_hypothesis_matrix(context, event_index):
    hypotheses = context["input_manifest"]["hypotheses"]
    event_refs = _event_refs(event_index)
    has_assessed_m5 = any(
        run["run_import_state"] in {
            "IMPORTED_WITH_EVENTS",
            "IMPORTED_COMPLETED_ZERO",
        }
        for run in context["runs"]
    )
    rows = []
    for hypothesis in sorted(hypotheses, key=lambda item: item["hypothesis_id"]):
        if not has_assessed_m5:
            state = "NOT_ASSESSED"
            reason = (
                "No completed, validated M5 run was available for this supplied question."
            )
        elif (hypothesis["scope"] == "STRUCTURAL_OBSERVATION" and event_refs):
            state = "OBSERVED"
            reason = (
                "A cited M5 run contains caller-reported event rows for this supplied "
                "structural question; this is not a biological identity or function call."
            )
        else:
            state = "UNRESOLVED"
            reason = (
                "The supplied M5 evidence does not resolve this question; a caller "
                "zero or missing event is not evidence of biological absence."
            )
        rows.append({
            "hypothesis_id": hypothesis["hypothesis_id"],
            "label": hypothesis["label"],
            "scope": hypothesis["scope"],
            "provenance_ref": hypothesis["provenance_ref"],
            "evidence_refs": event_refs if state == "OBSERVED" else [],
            "evidence_state": state,
            "reason": reason,
        })
    return {
        "schema": m13_contracts.HYPOTHESIS_MATRIX_SCHEMA,
        "candidate_id": context["input_manifest"]["candidate_id"],
        "hypotheses": rows,
    }


def _run_summary(run):
    return {
        "producer_stage_id": run["producer_stage_id"],
        "producer_run_manifest_sha256": run["producer_run_manifest_sha256"],
        "producer_workflow_ref": run["producer_workflow_ref"],
        "execution_record_ref": run["execution_record_ref"],
        "producer_status_raw": run["producer_status_raw"],
        "producer_execution_status_raw": run["producer_execution_status_raw"],
        "declared_producer_execution_status": run["producer_status"],
        "outcome_code": run["outcome_code"],
        "failure_code": run["failure_code"],
        "run_import_state": run["run_import_state"],
        "artifact_states": dict(run["artifact_states"]),
        "artifact_refs": sorted(
            run["artifact_refs"],
            key=lambda ref: ref["artifact_type"],
        ),
        "caller": run["caller"],
        "caller_version": run["caller_version"],
        "reference_sha256": run["reference_sha256"],
        "event_count": run["event_count"],
        "reason_code": run["reason_code"],
    }


def _build_summary(context):
    runs = sorted(
        context["runs"],
        key=lambda item: (
            item["producer_stage_id"],
            item["producer_run_manifest_sha256"] or "",
            item["execution_record_ref"]["sha256"]
            if item["execution_record_ref"] else "",
        ),
    )
    summaries = [_run_summary(run) for run in runs]
    count = sum(row["event_count"] or 0 for row in summaries)
    complete_states = {
        "IMPORTED_WITH_EVENTS",
        "IMPORTED_COMPLETED_ZERO",
    }
    completeness = (
        "COMPLETE"
        if all(row["run_import_state"] in complete_states for row in summaries)
        else "PARTIAL"
    )
    return {
        "schema": m13_contracts.SUMMARY_SCHEMA,
        "candidate_id": context["input_manifest"]["candidate_id"],
        "summary_completeness": completeness,
        "run_count": len(summaries),
        "event_count": count,
        "runs": summaries,
        "limitations": list(LIMITATIONS),
    }


def _bundle_run(run):
    return {
        "producer_stage_id": run["producer_stage_id"],
        "producer_run_manifest_sha256": run["producer_run_manifest_sha256"],
        "producer_status_raw": run["producer_status_raw"],
        "producer_execution_status_raw": run["producer_execution_status_raw"],
        "outcome_code": run["outcome_code"],
        "failure_code": run["failure_code"],
        "run_import_state": run["run_import_state"],
        "artifact_refs": sorted(
            run["artifact_refs"],
            key=lambda ref: ref["artifact_type"],
        ),
        "producer_workflow_ref": run["producer_workflow_ref"],
        "execution_record_ref": run["execution_record_ref"],
    }


def _output_identity(output, cache_identity):
    output = Path(output)
    marker = output / "manifest.json"
    if not _regular_file(marker):
        return None
    stage_manifest = m13_contracts.read_json(marker)
    if (stage_manifest.get("schema") != "m13-stage-manifest-v1"
            or stage_manifest.get("status") != "complete"
            or stage_manifest.get("identity") != cache_identity):
        raise ValueError("Existing M13 stage output has a different or invalid identity")
    digests = stage_manifest.get("output_sha256")
    if not isinstance(digests, dict) or set(digests) != set(OUTPUT_CONTRACTS):
        raise ValueError("Existing M13 stage output inventory is incomplete")
    for name, artifact_type in OUTPUT_CONTRACTS.items():
        path = output / name
        if not _regular_file(path):
            raise ValueError("Existing M13 output is missing or unsafe")
        if _sha256_file(path) != digests[name]:
            raise ValueError("Existing M13 output digest does not match its manifest")
        artifact_contracts.validate_artifact(path, artifact_type)
    _validate_output_set(output, cache_identity)
    return stage_manifest


def _validate_output_set(output, cache_identity):
    output = Path(output)
    event_index = m13_contracts.read_json(output / "event_index.json")
    hypothesis_matrix = m13_contracts.read_json(output / "hypothesis_matrix.json")
    summary = m13_contracts.read_json(output / "summary.json")
    bundle = m13_contracts.read_json(output / "result_bundle.json")
    m13_contracts.validate_event_index(event_index)
    m13_contracts.validate_hypothesis_matrix(hypothesis_matrix)
    m13_contracts.validate_summary(summary)
    m13_contracts.validate_result_bundle(bundle)
    candidate_id = summary["candidate_id"]
    if (event_index["candidate_id"] != candidate_id
            or hypothesis_matrix["candidate_id"] != candidate_id
            or bundle["candidate_id"] != candidate_id):
        raise ValueError("M13 output candidate identities do not match")
    if len(event_index["events"]) != summary["event_count"]:
        raise ValueError("M13 event index count does not match its summary")

    run_rows = {
        (row["producer_stage_id"], row["producer_run_manifest_sha256"]): row
        for row in summary["runs"]
    }
    event_refs = set()
    for row in event_index["events"]:
        run_ref = row["m5_run_ref"]
        identity = (
            run_ref["producer_stage_id"],
            run_ref["producer_run_manifest_sha256"],
        )
        producer = run_rows.get(identity)
        if (producer is None
                or producer["run_import_state"] != "IMPORTED_WITH_EVENTS"
                or producer["caller"] != row["caller"]
                or producer["caller_version"] != row["caller_version"]
                or producer["reference_sha256"] != row["reference_sha256"]):
            raise ValueError("M13 event-index row has no matching imported M5 run")
        evidence_refs = [
            ref for ref in producer["artifact_refs"]
            if ref["artifact_type"] == "dvg_evidence"
        ]
        if (len(evidence_refs) != 1
                or evidence_refs[0]["sha256"] != run_ref["dvg_evidence_sha256"]):
            raise ValueError("M13 event-index row is not bound to its evidence artifact")
        event_refs.add((
            run_ref["producer_stage_id"],
            run_ref["producer_run_manifest_sha256"],
            run_ref["dvg_evidence_sha256"],
            row["source_row_index"],
        ))

    for hypothesis in hypothesis_matrix["hypotheses"]:
        for ref in hypothesis["evidence_refs"]:
            identity = (
                ref["producer_stage_id"],
                ref["producer_run_manifest_sha256"],
                ref["dvg_evidence_sha256"],
                ref["source_row_index"],
            )
            if identity not in event_refs:
                raise ValueError("M13 hypothesis evidence link is absent from the event index")

    if len(bundle["producer_runs"]) != len(summary["runs"]):
        raise ValueError("M13 result bundle producer count does not match its summary")
    for producer, summary_row in zip(bundle["producer_runs"], summary["runs"]):
        for field in (
            "producer_stage_id",
            "producer_run_manifest_sha256",
            "producer_status_raw",
            "producer_execution_status_raw",
            "outcome_code",
            "failure_code",
            "run_import_state",
            "artifact_refs",
            "producer_workflow_ref",
            "execution_record_ref",
        ):
            if producer[field] != summary_row[field]:
                raise ValueError("M13 result bundle producer does not match its summary")
    expected_cache_sha = hashlib.sha256(
        m13_contracts.canonical_json_bytes(cache_identity)
    ).hexdigest()
    if bundle["stage_cache_context_sha256"] != expected_cache_sha:
        raise ValueError("M13 result bundle cache identity does not match")
    if bundle["input_manifest_sha256"] != cache_identity["input_manifest_sha256"]:
        raise ValueError("M13 result bundle input manifest digest does not match")
    if bundle["implementation"]["source_sha256"] != cache_identity[
            "implementation"]["source_sha256"]:
        raise ValueError("M13 result bundle implementation digest does not match")
    for artifact_type, filename in (
        ("m13_event_index", "event_index.json"),
        ("m13_hypothesis_matrix", "hypothesis_matrix.json"),
        ("m13_summary", "summary.json"),
    ):
        output_ref = bundle["outputs"][artifact_type]
        if output_ref["sha256"] != _sha256_file(output / filename):
            raise ValueError("M13 result bundle output digest does not match")


def _write_outputs(output, context):
    event_index = _build_event_index(context)
    hypothesis_matrix = _build_hypothesis_matrix(context, event_index)
    summary = _build_summary(context)
    temp_parent = Path(output).parent
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".m13-stage-", dir=temp_parent) as folder:
        folder = Path(folder)
        event_path = folder / "event_index.json"
        matrix_path = folder / "hypothesis_matrix.json"
        summary_path = folder / "summary.json"
        bundle_path = folder / "result_bundle.json"
        m13_contracts.write_json(event_path, event_index)
        m13_contracts.write_json(matrix_path, hypothesis_matrix)
        m13_contracts.write_json(summary_path, summary)
        output_hashes = {
            "event_index.json": _sha256_file(event_path),
            "hypothesis_matrix.json": _sha256_file(matrix_path),
            "summary.json": _sha256_file(summary_path),
        }
        producer_runs = [
            _bundle_run(run)
            for run in sorted(
                context["runs"],
                key=lambda item: (
                    item["producer_stage_id"],
                    item["producer_run_manifest_sha256"] or "",
                    item["execution_record_ref"]["sha256"]
                    if item["execution_record_ref"] else "",
                ),
            )
        ]
        bundle = {
            "schema": m13_contracts.RESULT_BUNDLE_SCHEMA,
            "input_schema": m13_contracts.INPUT_SCHEMA,
            "semantic_version": m13_contracts.SEMANTIC_VERSION,
            "candidate_id": context["input_manifest"]["candidate_id"],
            "input_manifest_sha256": context["input_manifest_sha256"],
            "stage_cache_context_sha256": context["cache_identity_sha256"],
            "implementation": {
                "semantic_version": m13_contracts.SEMANTIC_VERSION,
                "source_sha256": context["implementation"]["source_sha256"],
            },
            "producer_runs": producer_runs,
            "outputs": {
                "m13_event_index": {
                    "artifact_type": "m13_event_index",
                    "artifact_contract_version": m13_contracts.OUTPUT_CONTRACT_VERSION,
                    "sha256": output_hashes["event_index.json"],
                },
                "m13_hypothesis_matrix": {
                    "artifact_type": "m13_hypothesis_matrix",
                    "artifact_contract_version": m13_contracts.OUTPUT_CONTRACT_VERSION,
                    "sha256": output_hashes["hypothesis_matrix.json"],
                },
                "m13_summary": {
                    "artifact_type": "m13_summary",
                    "artifact_contract_version": m13_contracts.OUTPUT_CONTRACT_VERSION,
                    "sha256": output_hashes["summary.json"],
                },
            },
            "limitations": list(LIMITATIONS),
        }
        m13_contracts.write_json(bundle_path, bundle)
        stage_digests = {
            name: _sha256_file(folder / name)
            for name in sorted(OUTPUT_CONTRACTS)
        }
        for name, artifact_type in OUTPUT_CONTRACTS.items():
            artifact_contracts.validate_artifact(folder / name, artifact_type)
        stage_manifest = {
            "schema": "m13-stage-manifest-v1",
            "status": "complete",
            "identity": context["cache_identity"],
            "output_sha256": stage_digests,
        }
        m13_contracts.write_json(folder / "manifest.json", stage_manifest)
        for name in set(OUTPUT_CONTRACTS) | {"manifest.json"}:
            if not _regular_file(folder / name):
                raise ValueError("M13 failed to create a regular output artifact")
        _validate_output_set(folder, context["cache_identity"])
        output = Path(output)
        if output.exists():
            if output.is_symlink() or any(output.iterdir()):
                raise ValueError("Existing M13 output directory is occupied or unverified")
            output.rmdir()
        os.replace(folder, output)
    return stage_manifest


def run_stage(inputs, output, config, *, workflow_context=None):
    validate_config(config)
    if not isinstance(workflow_context, dict):
        raise ValueError("M13 requires its explicit typed input and producer context")
    plan = workflow_context.get("binding_plan")
    failures = workflow_context.get("input_failures", {})
    fresh = _stage_context(inputs, plan, failures)
    expected_identity = workflow_context.get("cache_identity")
    if fresh["cache_identity"] != expected_identity:
        raise ValueError("M13 inputs changed after cache identity was calculated")
    if _sha256_file(inputs["manifest"]) != fresh["input_manifest_sha256"]:
        raise ValueError("M13 input manifest changed during stage execution")

    existing = _output_identity(Path(output), fresh["cache_identity"])
    if existing is not None:
        return existing
    output = Path(output)
    if output.is_symlink():
        raise ValueError("M13 stage output must not be a symbolic link")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Existing M13 stage output is partial, changed, or unverified")
    return _write_outputs(output, fresh)


run_stage.cache_implementation_identity = _source_identity
run_stage.cache_input_contract_semantics = True
run_stage.cache_input_contract_semantics_version = CACHE_INPUT_SEMANTICS_VERSION