"""Offline descriptive summaries of caller-authored candidate/helper observations.

M14 is deliberately limited to validating supplied observation frames and
reporting transparent counts.  It does not discover sequences, infer
independence, fit statistical models, or establish biological dependence.
"""

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil

from . import artifact_contracts
from .sequence_downloader import checksum


STAGE_KIND = "m14_descriptive_observations"
STAGE_VERSION = "1"
INPUT_SCHEMA = "m14-input-v1"
SEMANTIC_VERSION = "1"
SEMANTIC_SCHEMA = "m14-semantic-input-v1"
PROVENANCE_SCHEMA = "m14-provenance-v1"
CACHE_SCHEMA = "m14-cache-identity-v1"
OBSERVATION_SCHEMA = "m14-observation-table-v1"
SUMMARY_SCHEMA = "m14-descriptive-summary-v1"
RESULT_BUNDLE_SCHEMA = "m14-result-bundle-v1"
MAX_CONFIG_BYTES = 2_000_000
MAX_OUTPUT_BYTES = 32_000_000

OUTPUT_CONTRACTS = {
    "observations.json": "m14_observation_table",
    "descriptive_summary.json": "m14_descriptive_summary",
    "result_bundle.json": "m14_result_bundle",
}

SOURCE_SPECS = {
    "M4_CATALOGUE_OBSERVATIONS": {
        "milestone": "M4",
        "stage_kind": "catalogue_observations",
        "artifact_types": frozenset({
            "sample_table", "observation_table", "occurrence_table",
            "occurrence_summary",
        }),
    },
    "M4_OBSERVATIONS": {
        "milestone": "M4",
        "stage_kind": "observations",
        "artifact_types": frozenset({"occurrence_table", "occurrence_summary"}),
    },
    "M7_INDEPENDENT_RECURRENCE": {
        "milestone": "M7",
        "stage_kind": "independent_recurrence",
        "artifact_types": frozenset({
            "m7_observation_table", "m7_exact_recurrence_table",
            "m7_independence_summary", "m7_validation_report",
            "m7_provenance_manifest",
        }),
    },
}

SOURCE_STATES = frozenset({
    "NOT_SUPPLIED", "AVAILABLE", "UNAVAILABLE", "NOT_RUN", "FAILED",
    "INTERRUPTED", "INCOMPLETE", "INVALID",
})
RESULT_STATES = frozenset({
    "COMPLETED_DESCRIPTIVE", "NOT_EVALUATED",
    "INSUFFICIENT_MATCHED_EVIDENCE", "INVALID_INPUT", "INCOMPLETE",
})
UNIT_TYPES = frozenset({
    "SAMPLE", "SPECIMEN", "LIBRARY", "RUN", "EXPERIMENT", "STUDY",
    "OTHER_DECLARED",
})
OBSERVATION_STATES = frozenset({
    "PRESENT", "NOT_DETECTED_WITHIN_SCOPE", "UNKNOWN", "UNAVAILABLE",
    "NOT_APPLICABLE", "CONFLICTING",
})
INDEPENDENCE_STATES = frozenset({
    "UNVERIFIED", "VERIFIED_WITH_PROVENANCE", "UNKNOWN",
})
COMPLETENESS_STATES = frozenset({"COMPLETE", "PARTIAL", "UNKNOWN", "NOT_REPORTED"})
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_OUTCOME_KEYS = frozenset({
    "source_id", "source_kind", "source_state", "workflow_ref",
    "producer_stage", "artifact_refs", "artifact_attempts",
    "producer_result_status", "producer_completeness", "reason_code",
})
_ARTIFACT_REF_KEYS = frozenset({
    "artifact_id", "source_id", "producer_milestone", "producer_stage_kind",
    "producer_stage_id", "producer_workflow_id",
    "producer_run_manifest_sha256", "artifact_type", "contract_version",
    "relative_path", "content_sha256", "raw_producer_status",
})
_ARTIFACT_ATTEMPT_KEYS = frozenset({
    "artifact_type", "contract_version", "relative_path",
    "expected_content_sha256", "reason_code",
})
_MANIFEST_KEYS = frozenset({
    "schema", "dataset_id", "source_artifacts", "source_outcomes",
    "sampling_units", "evaluated_pairs", "observations", "analysis_profile",
})
_UNIT_KEYS = frozenset({
    "unit_id", "unit_type", "unit_type_label", "parent_unit_ids", "study_id",
    "independence_state", "independence_ref", "control_role", "source_refs",
})
_PAIR_KEYS = frozenset({"candidate_id", "helper_id", "unit_ids"})
_OBSERVATION_KEYS = frozenset({
    "observation_id", "candidate_id", "helper_id", "unit_id",
    "candidate_state", "helper_state", "candidate_state_reason",
    "helper_state_reason", "candidate_tested", "helper_tested",
    "candidate_method_ref", "helper_method_ref", "candidate_detection_limit",
    "helper_detection_limit", "source_refs",
})
_METHOD_KEYS = frozenset({
    "method_id", "method_version", "scope_id", "scope_description",
    "provenance_ref",
})
_DETECTION_LIMIT_KEYS = frozenset({"metric", "value", "unit", "basis"})


def _json_number(value):
    """Return a JSON-safe number with equivalent decimal tokens normalized."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("Detection-limit value must be a finite number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Detection-limit value must be a finite number") from None
    if not number.is_finite() or number < 0:
        raise ValueError("Detection-limit value must be finite and non-negative")
    normalized = number.normalize()
    if normalized == normalized.to_integral_value():
        return int(normalized)
    result = float(normalized)
    if not math.isfinite(result):
        raise ValueError("Detection-limit value is outside the supported range")
    return result


def _canonical_decimal(value):
    number = value if isinstance(value, Decimal) else Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Non-finite JSON number")
    if number == 0:
        return "0"
    text = format(number.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _canonical_json_text(value):
    """Encode JSON canonically, including exact finite decimal number tokens."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _canonical_decimal(value)
    if isinstance(value, list):
        return "[" + ",".join(_canonical_json_text(item) for item in value) + "]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Canonical JSON object keys must be strings")
        return "{" + ",".join(
            _canonical_json_text(key) + ":" + _canonical_json_text(value[key])
            for key in sorted(value)
        ) + "}"
    raise ValueError(f"Value is not JSON serializable: {type(value).__name__}")


def _canonical_json_bytes(value, *, trailing_newline=False):
    encoded = _canonical_json_text(value).encode("utf-8")
    return encoded + (b"\n" if trailing_newline else b"")


def _sha256_json(value):
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _json_safe(value):
    try:
        _canonical_json_bytes(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return True


def _object(value, expected, label, errors):
    if not isinstance(value, dict):
        errors.append(f"{label}_NOT_OBJECT")
        return False
    if set(value) != expected:
        errors.append(f"{label}_FIELDS_INVALID")
        return False
    return True


def _token(value):
    return isinstance(value, str) and bool(_TOKEN.fullmatch(value))


def _sorted_copy(rows, key):
    if not isinstance(rows, list):
        return rows
    decorated = []
    for index, row in enumerate(rows):
        try:
            sort_key = key(row)
        except (KeyError, TypeError, ValueError):
            sort_key = (2, _canonical_json_text(row) if _json_safe(row) else "", index)
        decorated.append((sort_key, index, row))
    decorated.sort(key=lambda item: (item[0], item[1]))
    return [row for _, _, row in decorated]


def _null_first(value):
    return (0, "") if value is None else (1, str(value))


def _normalize_rows(manifest):
    """Normalize only declared unordered arrays before the generic M1 key."""
    normalized = dict(manifest)
    if isinstance(normalized.get("sampling_units"), list):
        units = []
        for source in normalized["sampling_units"]:
            row = dict(source) if isinstance(source, dict) else source
            if isinstance(row, dict):
                if isinstance(row.get("parent_unit_ids"), list):
                    row["parent_unit_ids"] = sorted(row["parent_unit_ids"], key=str)
                if isinstance(row.get("source_refs"), list):
                    row["source_refs"] = sorted(row["source_refs"], key=str)
            units.append(row)
        normalized["sampling_units"] = _sorted_copy(
            units, lambda row: (str(row.get("unit_id", "")) if isinstance(row, dict) else "")
        )
    if isinstance(normalized.get("evaluated_pairs"), list):
        pairs = []
        for source in normalized["evaluated_pairs"]:
            row = dict(source) if isinstance(source, dict) else source
            if isinstance(row, dict) and isinstance(row.get("unit_ids"), list):
                row["unit_ids"] = sorted(row["unit_ids"], key=str)
            pairs.append(row)
        normalized["evaluated_pairs"] = _sorted_copy(
            pairs,
            lambda row: (
                str(row.get("candidate_id", "")), str(row.get("helper_id", ""))
            ) if isinstance(row, dict) else ("", ""),
        )
    if isinstance(normalized.get("observations"), list):
        observations = []
        for source in normalized["observations"]:
            row = dict(source) if isinstance(source, dict) else source
            if isinstance(row, dict):
                if isinstance(row.get("source_refs"), list):
                    row["source_refs"] = sorted(row["source_refs"], key=str)
                for key in ("candidate_detection_limit", "helper_detection_limit"):
                    limit = row.get(key)
                    if isinstance(limit, dict) and "value" in limit:
                        limit = dict(limit)
                        try:
                            limit["value"] = _json_number(limit["value"])
                        except ValueError:
                            pass
                        row[key] = limit
                for key in ("candidate_method_ref", "helper_method_ref"):
                    method = row.get(key)
                    if isinstance(method, dict) and isinstance(method.get("provenance_ref"), list):
                        method = dict(method)
                        method["provenance_ref"] = sorted(method["provenance_ref"], key=str)
                        row[key] = method
            observations.append(row)
        unit_index = {
            row.get("unit_id"): row
            for row in normalized.get("sampling_units", [])
            if isinstance(row, dict) and isinstance(row.get("unit_id"), str)
        }
        normalized["observations"] = _sorted_copy(
            observations,
            lambda row: (
                _null_first(
                    unit_index.get(row.get("unit_id"), {}).get("study_id")
                    if isinstance(row, dict) else None
                ),
                str(unit_index.get(row.get("unit_id"), {}).get("unit_type", ""))
                if isinstance(row, dict) else "",
                str(row.get("unit_id", "")) if isinstance(row, dict) else "",
                str(row.get("candidate_id", "")) if isinstance(row, dict) else "",
                str(row.get("helper_id", "")) if isinstance(row, dict) else "",
                str(row.get("observation_id", "")) if isinstance(row, dict) else "",
            ),
        )
    if isinstance(normalized.get("source_artifacts"), list):
        normalized["source_artifacts"] = _sorted_copy(
            normalized["source_artifacts"],
            lambda row: str(row.get("artifact_id", "")) if isinstance(row, dict) else "",
        )
    if isinstance(normalized.get("source_outcomes"), list):
        normalized["source_outcomes"] = _sorted_copy(
            normalized["source_outcomes"],
            lambda row: (
                str(row.get("source_kind", "")), str(row.get("source_id", ""))
            ) if isinstance(row, dict) else ("", ""),
        )
    return normalized


def validate_config(config):
    """Keep serializable semantic errors for a typed M14 INVALID_INPUT result."""
    if not isinstance(config, dict) or not _json_safe(config):
        raise ValueError("M14 configuration must be a JSON-safe object")
    if len(_canonical_json_bytes(config)) > MAX_CONFIG_BYTES:
        raise ValueError("M14 configuration exceeds the 2 MB contract limit")
    return _normalize_rows(config)


def _safe_relative_parts(raw, label):
    if (not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw
            or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw)):
        raise ValueError(f"{label}_PATH_UNSAFE")
    if any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ValueError(f"{label}_PATH_UNSAFE")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label}_PATH_UNSAFE")
    return path.parts


def _reject_symlink_components(path):
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            if current.is_symlink():
                raise ValueError("ARTIFACT_PATH_UNSAFE")
        except OSError as error:
            raise ValueError("ARTIFACT_PATH_UNSAFE") from error


def _path_without_symlinks(root, parts, *, must_exist=True):
    root = Path(root)
    _reject_symlink_components(root)
    current = root
    for part in parts:
        current = current / part
        try:
            if current.is_symlink():
                raise ValueError("ARTIFACT_PATH_UNSAFE")
            if must_exist and not current.exists():
                raise FileNotFoundError(str(current))
        except OSError as error:
            raise FileNotFoundError(str(current)) from error
    resolved_root = root.resolve(strict=True)
    resolved = current.resolve(strict=must_exist)
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("ARTIFACT_PATH_UNSAFE")
    return current


def _read_json_file(path, *, limit=MAX_OUTPUT_BYTES):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("ARTIFACT_INTEGRITY_FAILED")
    if path.stat().st_size > limit:
        raise ValueError("ARTIFACT_SCHEMA_INVALID")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("ARTIFACT_SCHEMA_INVALID") from error


def _source_kind_state_errors(outcome):
    errors = []
    if not isinstance(outcome, dict) or set(outcome) != _SOURCE_OUTCOME_KEYS:
        return ["SOURCE_OUTCOME_INVALID"]
    source_id = outcome.get("source_id")
    source_kind = outcome.get("source_kind")
    state = outcome.get("source_state")
    if (not _token(source_id) or not isinstance(source_kind, str)
            or source_kind not in SOURCE_SPECS or not isinstance(state, str)
            or state not in SOURCE_STATES):
        errors.append("SOURCE_OUTCOME_INVALID")
    if not isinstance(outcome.get("artifact_refs"), list):
        errors.append("SOURCE_OUTCOME_INVALID")
    elif any(not _token(ref) for ref in outcome["artifact_refs"]):
        errors.append("SOURCE_OUTCOME_INVALID")
    elif len(outcome["artifact_refs"]) != len(set(outcome["artifact_refs"])):
        errors.append("SOURCE_OUTCOME_INVALID")
    if not isinstance(outcome.get("artifact_attempts"), list):
        errors.append("SOURCE_OUTCOME_INVALID")
    completeness = outcome.get("producer_completeness")
    if not isinstance(completeness, str) or completeness not in COMPLETENESS_STATES:
        errors.append("SOURCE_OUTCOME_INVALID")
    result = outcome.get("producer_result_status")
    if result is not None and (not isinstance(result, str) or not result):
        errors.append("SOURCE_OUTCOME_INVALID")
    reason = outcome.get("reason_code")
    if reason is not None and (not isinstance(reason, str) or not reason):
        errors.append("SOURCE_OUTCOME_INVALID")
    allowed_reasons = {
        "NOT_SUPPLIED": {"NOT_SUPPLIED"},
        "NOT_RUN": {"PRODUCER_NOT_RUN"},
        "UNAVAILABLE": {
            "WORKFLOW_UNAVAILABLE", "DEPENDENCY_UNAVAILABLE",
            "ARTIFACT_UNAVAILABLE",
        },
        "FAILED": {"PRODUCER_FAILED"},
        "INTERRUPTED": {"PRODUCER_INTERRUPTED"},
        "INCOMPLETE": {"PRODUCER_NONTERMINAL", "OUTPUT_INCOMPLETE"},
        "INVALID": {
            "PRODUCER_STAGE_NOT_FOUND", "PRODUCER_IDENTITY_MISMATCH",
            "UNSUPPORTED_PRODUCER_TYPE", "ARTIFACT_VERSION_MISMATCH",
            "ARTIFACT_DIGEST_MISMATCH", "ARTIFACT_SCHEMA_INVALID",
            "ARTIFACT_PATH_UNSAFE", "ARTIFACT_INTEGRITY_FAILED",
            "SOURCE_OUTCOME_INVALID",
        },
    }
    if state == "AVAILABLE":
        if reason is not None or outcome.get("artifact_attempts"):
            errors.append("SOURCE_OUTCOME_INVALID")
    elif (isinstance(state, str)
          and reason not in allowed_reasons.get(state, set())):
        errors.append("SOURCE_OUTCOME_INVALID")
    for attempt in outcome.get("artifact_attempts", []):
        if not isinstance(attempt, dict) or set(attempt) != _ARTIFACT_ATTEMPT_KEYS:
            errors.append("SOURCE_OUTCOME_INVALID")
            break
        if (attempt.get("artifact_type") is not None
                and (not isinstance(attempt["artifact_type"], str)
                     or not attempt["artifact_type"])
                or attempt.get("contract_version") is not None
                and (not isinstance(attempt["contract_version"], str)
                     or not attempt["contract_version"])
                or attempt.get("relative_path") is not None
                and not isinstance(attempt["relative_path"], str)
                or attempt.get("expected_content_sha256") is not None
                and (not isinstance(attempt["expected_content_sha256"], str)
                     or not _HASH.fullmatch(attempt["expected_content_sha256"]))
                or not isinstance(attempt.get("reason_code"), str)
                or not attempt["reason_code"]):
            errors.append("SOURCE_OUTCOME_INVALID")
            break
    workflow = outcome.get("workflow_ref")
    if workflow is not None:
        if (not isinstance(workflow, dict)
                or set(workflow) != {"relative_path", "workflow_id"}
                or not isinstance(workflow.get("relative_path"), str)
                or not workflow["relative_path"].endswith("workflow.json")
                or (workflow.get("workflow_id") is not None
                    and not _token(workflow["workflow_id"]))):
            errors.append("SOURCE_OUTCOME_INVALID")
    stage = outcome.get("producer_stage")
    if stage is not None:
        if (not isinstance(stage, dict)
                or set(stage) != {
                    "stage_id", "stage_kind", "raw_status", "manifest_sha256",
                }
                or not _token(stage.get("stage_id"))
                or not _token(stage.get("stage_kind"))
                or (stage.get("raw_status") is not None
                    and not isinstance(stage["raw_status"], str))
                or (stage.get("manifest_sha256") is not None
                    and (not isinstance(stage["manifest_sha256"], str)
                         or not _HASH.fullmatch(stage["manifest_sha256"])))):
            errors.append("SOURCE_OUTCOME_INVALID")
    if state == "AVAILABLE" and (workflow is None or stage is None):
        errors.append("SOURCE_OUTCOME_INVALID")
    if state == "NOT_SUPPLIED" and (workflow is not None or stage is not None):
        errors.append("SOURCE_OUTCOME_INVALID")
    if (state == "NOT_RUN" and workflow is None and stage is not None
            or state == "NOT_RUN" and workflow is not None and stage is None):
        errors.append("SOURCE_OUTCOME_INVALID")
    return errors


def _unverified_producer_stage(source):
    """Keep caller-declared stage identity, but never echo unverified claims."""
    stage = source.get("producer_stage") if isinstance(source, dict) else None
    if (not isinstance(stage, dict)
            or not _token(stage.get("stage_id"))
            or not _token(stage.get("stage_kind"))):
        return None
    return {
        "stage_id": stage["stage_id"],
        "stage_kind": stage["stage_kind"],
        "raw_status": None,
        "manifest_sha256": None,
    }


def _invalid_source_outcome(source):
    defaults = {
        "source_id": None,
        "source_kind": None,
        "source_state": "INVALID",
        "workflow_ref": None,
        "producer_stage": None,
        "artifact_refs": [],
        "artifact_attempts": [],
        "producer_result_status": None,
        "producer_completeness": "NOT_REPORTED",
        "reason_code": "SOURCE_OUTCOME_INVALID",
    }
    if isinstance(source, dict):
        defaults.update({
            key: value for key, value in source.items()
            if key in _SOURCE_OUTCOME_KEYS
        })
    defaults.update(
        source_state="INVALID",
        artifact_refs=[],
        artifact_attempts=[],
        producer_result_status=None,
        producer_completeness="NOT_REPORTED",
        reason_code="SOURCE_OUTCOME_INVALID",
    )
    defaults["producer_stage"] = _unverified_producer_stage(source)
    return defaults


def _normalize_invalid_source_outcome(source):
    if source.get("source_state") != "INVALID":
        return source
    result = _invalid_source_outcome(source)
    result["source_id"] = source.get("source_id") if _token(source.get("source_id")) else None
    source_kind = source.get("source_kind")
    result["source_kind"] = source_kind if (
        isinstance(source_kind, str) and source_kind in SOURCE_SPECS
    ) else None
    allowed_reasons = {
        "PRODUCER_STAGE_NOT_FOUND", "PRODUCER_IDENTITY_MISMATCH",
        "UNSUPPORTED_PRODUCER_TYPE", "ARTIFACT_VERSION_MISMATCH",
        "ARTIFACT_DIGEST_MISMATCH", "ARTIFACT_SCHEMA_INVALID",
        "ARTIFACT_PATH_UNSAFE", "ARTIFACT_INTEGRITY_FAILED",
        "SOURCE_OUTCOME_INVALID",
    }
    reason = source.get("reason_code")
    result["reason_code"] = (
        reason if isinstance(reason, str) and reason in allowed_reasons
        else "SOURCE_OUTCOME_INVALID"
    )
    workflow = source.get("workflow_ref")
    if (isinstance(workflow, dict)
            and set(workflow) == {"relative_path", "workflow_id"}
            and isinstance(workflow.get("relative_path"), str)
            and PurePosixPath(workflow["relative_path"]).name == "workflow.json"
            and (workflow.get("workflow_id") is None
                 or _token(workflow.get("workflow_id")))):
        result["workflow_ref"] = workflow
    stage = source.get("producer_stage")
    if (isinstance(stage, dict)
            and set(stage) == {
                "stage_id", "stage_kind", "raw_status", "manifest_sha256",
            }
            and _token(stage.get("stage_id"))
            and _token(stage.get("stage_kind"))
            and (stage.get("raw_status") is None
                 or isinstance(stage.get("raw_status"), str))
            and (stage.get("manifest_sha256") is None
                 or isinstance(stage.get("manifest_sha256"), str)
                 and _HASH.fullmatch(stage["manifest_sha256"]))):
        result["producer_stage"] = stage
    attempts = []
    attempt_rows = source.get("artifact_attempts")
    for attempt in attempt_rows if isinstance(attempt_rows, list) else []:
        if not isinstance(attempt, dict) or set(attempt) != _ARTIFACT_ATTEMPT_KEYS:
            continue
        reason = attempt.get("reason_code")
        if not isinstance(reason, str) or not reason:
            continue
        attempts.append({
            "artifact_type": (
                attempt.get("artifact_type")
                if isinstance(attempt.get("artifact_type"), str) else None
            ),
            "contract_version": (
                attempt.get("contract_version")
                if isinstance(attempt.get("contract_version"), str) else None
            ),
            "relative_path": (
                attempt.get("relative_path")
                if isinstance(attempt.get("relative_path"), str) else None
            ),
            "expected_content_sha256": (
                attempt.get("expected_content_sha256")
                if isinstance(attempt.get("expected_content_sha256"), str)
                and _HASH.fullmatch(attempt["expected_content_sha256"]) else None
            ),
            "reason_code": reason,
        })
    result["artifact_attempts"] = attempts
    return result


def _source_reason_for_raw(raw_status):
    return {
        "skipped": ("NOT_RUN", "PRODUCER_NOT_RUN"),
        "dependency_missing": ("UNAVAILABLE", "DEPENDENCY_UNAVAILABLE"),
        "external_module_required": ("UNAVAILABLE", "DEPENDENCY_UNAVAILABLE"),
        "pending": ("INCOMPLETE", "PRODUCER_NONTERMINAL"),
        "running": ("INCOMPLETE", "PRODUCER_NONTERMINAL"),
        "failed": ("FAILED", "PRODUCER_FAILED"),
        "interrupted": ("INTERRUPTED", "PRODUCER_INTERRUPTED"),
    }.get(raw_status)


def _workflow_record(outcome):
    workflow_ref = outcome.get("workflow_ref")
    if not isinstance(workflow_ref, dict) or set(workflow_ref) != {
        "relative_path", "workflow_id",
    }:
        raise ValueError("SOURCE_OUTCOME_INVALID")
    parts = _safe_relative_parts(workflow_ref.get("relative_path"), "WORKFLOW")
    if PurePosixPath(workflow_ref["relative_path"]).name != "workflow.json":
        raise ValueError("SOURCE_OUTCOME_INVALID")
    root = Path.cwd().resolve()
    workflow_path = _path_without_symlinks(root, parts)
    if not workflow_path.is_file():
        raise FileNotFoundError(str(workflow_path))
    try:
        if workflow_path.stat().st_size > 1_000_000:
            raise ValueError("SOURCE_OUTCOME_INVALID")
        raw_workflow = workflow_path.read_bytes()
    except OSError as error:
        raise FileNotFoundError(str(workflow_path)) from error
    try:
        workflow = json.loads(raw_workflow.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("SOURCE_OUTCOME_INVALID") from error
    if not isinstance(workflow, dict) or workflow.get("schema") != "artifact-workflow-manifest-v2":
        raise ValueError("SOURCE_OUTCOME_INVALID")
    workflow_id = workflow.get("workflow_id")
    if (not isinstance(workflow_id, str) or not workflow_id
            or workflow_ref.get("workflow_id") != workflow_id):
        raise ValueError("PRODUCER_IDENTITY_MISMATCH")
    stages = workflow.get("stages")
    if not isinstance(stages, list):
        raise ValueError("SOURCE_OUTCOME_INVALID")
    stage_id = (outcome.get("producer_stage") or {}).get("stage_id")
    matching = [row for row in stages if isinstance(row, dict) and row.get("id") == stage_id]
    if len(matching) != 1:
        raise ValueError("PRODUCER_STAGE_NOT_FOUND")
    stage = matching[0]
    spec = SOURCE_SPECS.get(outcome.get("source_kind"))
    if spec is None:
        raise ValueError("UNSUPPORTED_PRODUCER_TYPE")
    if stage.get("kind") != spec["stage_kind"]:
        raise ValueError("PRODUCER_IDENTITY_MISMATCH")
    # The selected stage's raw M1 status is authoritative. Do not let missing
    # output storage for a failed, skipped, or nonterminal stage rewrite it.
    if stage.get("status") != "complete":
        return workflow, workflow_path, stage, None, None, None
    raw_output = workflow.get("output")
    if not isinstance(raw_output, str) or not raw_output:
        return workflow, workflow_path, stage, None, None, None
    output_root = Path(raw_output)
    if not output_root.is_absolute():
        output_root = root / output_root
    if output_root.is_symlink():
        raise ValueError("ARTIFACT_PATH_UNSAFE")
    if not isinstance(stage.get("output_path"), str):
        return workflow, workflow_path, stage, None, None, None
    try:
        stage_parts = _safe_relative_parts(stage["output_path"], "ARTIFACT")
        stage_output = _path_without_symlinks(output_root, stage_parts)
    except FileNotFoundError:
        return workflow, workflow_path, stage, None, None, None
    if not stage_output.is_dir():
        return workflow, workflow_path, stage, None, None, None
    manifest_path = stage_output / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("ARTIFACT_PATH_UNSAFE")
    if not manifest_path.is_file():
        return workflow, workflow_path, stage, stage_output, None, None
    try:
        if manifest_path.stat().st_size > 1_000_000:
            raise ValueError("SOURCE_OUTCOME_INVALID")
        raw_manifest = manifest_path.read_bytes()
    except OSError:
        return workflow, workflow_path, stage, stage_output, None, None
    try:
        stage_manifest = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("SOURCE_OUTCOME_INVALID") from error
    if not isinstance(stage_manifest, dict):
        raise ValueError("SOURCE_OUTCOME_INVALID")
    return (
        workflow, workflow_path, stage, stage_output, stage_manifest,
        hashlib.sha256(raw_manifest).hexdigest(),
    )


def _artifact_path(stage_output, relative_path):
    parts = _safe_relative_parts(relative_path, "ARTIFACT")
    path = _path_without_symlinks(stage_output, parts)
    if not path.is_file():
        raise ValueError("ARTIFACT_INTEGRITY_FAILED")
    return path


def _extract_producer_native(artifact_paths):
    result_status = None
    completeness = "NOT_REPORTED"
    for artifact_type, path in artifact_paths:
        if artifact_type not in {
            "m7_validation_report", "m7_independence_summary",
            "occurrence_summary",
        }:
            continue
        try:
            value = _read_json_file(path)
        except ValueError:
            continue
        if not isinstance(value, dict):
            continue
        if result_status is None:
            candidate = value.get("result_status", value.get("status"))
            if isinstance(candidate, str) and candidate:
                result_status = candidate
        native = value.get(
            "producer_completeness",
            value.get("completeness", value.get("analysis_completeness")),
        )
        if isinstance(native, str):
            normalized = native.upper()
            if normalized in {"COMPLETE", "PARTIAL", "UNKNOWN"}:
                completeness = normalized
    return result_status, completeness


def _attempt_from_ref(ref, reason):
    if not isinstance(ref, dict):
        return None
    return {
        "artifact_type": ref.get("artifact_type"),
        "contract_version": ref.get("contract_version"),
        "relative_path": ref.get("relative_path"),
        "expected_content_sha256": ref.get("content_sha256"),
        "reason_code": reason,
    }


def _resolve_source_outcomes(config):
    """Verify only explicit source references; never search the filesystem."""
    outcomes = config.get("source_outcomes")
    refs = config.get("source_artifacts")
    errors = []
    if not isinstance(outcomes, list) or not isinstance(refs, list):
        return [], [], {}, ["SOURCE_OUTCOME_INVALID"]
    outcome_by_id = {}
    duplicate_source_ids = set()
    for row in outcomes:
        if not isinstance(row, dict) or not _token(row.get("source_id")):
            errors.append("SOURCE_OUTCOME_INVALID")
            continue
        if row["source_id"] in outcome_by_id:
            errors.append("SOURCE_OUTCOME_INVALID")
            duplicate_source_ids.add(row["source_id"])
        outcome_by_id[row["source_id"]] = row
    refs_by_id = {}
    duplicate_artifact_ids = set()
    for ref in refs:
        if not isinstance(ref, dict) or not _token(ref.get("artifact_id")):
            errors.append("SOURCE_OUTCOME_INVALID")
            continue
        if ref["artifact_id"] in refs_by_id:
            errors.append("SOURCE_OUTCOME_INVALID")
            duplicate_artifact_ids.add(ref["artifact_id"])
        refs_by_id[ref["artifact_id"]] = ref

    resolved_outcomes = []
    verified_refs = []
    verified_paths = {}
    listed_ids = []
    source_kinds_without_runs = defaultdict(list)
    for source in outcomes:
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        source_kind = source.get("source_kind")
        claimed_state = source.get("source_state")
        if isinstance(source_kind, str) and source_kind in SOURCE_SPECS:
            source_kinds_without_runs[source_kind].append(source)
        row_errors = _source_kind_state_errors(source)
        if source_id in duplicate_source_ids:
            row_errors.append("SOURCE_OUTCOME_INVALID")
        artifact_ids = source.get("artifact_refs")
        if (isinstance(artifact_ids, list)
                and any(ref_id in duplicate_artifact_ids
                        for ref_id in artifact_ids if _token(ref_id))):
            row_errors.append("SOURCE_OUTCOME_INVALID")
        if row_errors:
            resolved_outcomes.append(_invalid_source_outcome(source))
            errors.append("SOURCE_OUTCOME_INVALID")
            continue

        current = dict(source)
        if isinstance(claimed_state, str) and claimed_state in {"NOT_SUPPLIED", "NOT_RUN"}:
            if (claimed_state == "NOT_SUPPLIED" and (
                    source.get("workflow_ref") is not None
                    or source.get("producer_stage") is not None
                    or source.get("artifact_refs") or source.get("artifact_attempts")
                    or source.get("producer_result_status") is not None
                    or source.get("producer_completeness") != "NOT_REPORTED"
                    or source.get("reason_code") != "NOT_SUPPLIED")):
                current.update(source_state="INVALID", reason_code="SOURCE_OUTCOME_INVALID")
            elif claimed_state == "NOT_RUN" and (
                    source.get("reason_code") != "PRODUCER_NOT_RUN"
                    or source.get("artifact_refs")
                    or source.get("artifact_attempts")
                    or source.get("producer_result_status") is not None
                    or source.get("producer_completeness") != "NOT_REPORTED"):
                current.update(source_state="INVALID", reason_code="SOURCE_OUTCOME_INVALID")
            else:
                if claimed_state == "NOT_SUPPLIED" or source.get("workflow_ref") is None:
                    resolved_outcomes.append(current)
                    continue
                # A declared NOT_RUN slot may retain an actual skipped M1 stage.
                try:
                    workflow, workflow_path, stage, stage_output, stage_manifest, manifest_hash = _workflow_record(source)
                except FileNotFoundError:
                    current.update(
                        source_state="UNAVAILABLE", reason_code="WORKFLOW_UNAVAILABLE",
                        artifact_refs=[], artifact_attempts=[],
                        producer_result_status=None, producer_completeness="NOT_REPORTED",
                        producer_stage=_unverified_producer_stage(source),
                    )
                    resolved_outcomes.append(current)
                    continue
                except ValueError:
                    current.update(
                        source_state="INVALID", reason_code="SOURCE_OUTCOME_INVALID",
                        artifact_refs=[], artifact_attempts=[],
                        producer_result_status=None, producer_completeness="NOT_REPORTED",
                        producer_stage=_unverified_producer_stage(source),
                    )
                    resolved_outcomes.append(current)
                    continue
                if stage.get("status") != "skipped":
                    current.update(
                        source_state="INVALID", reason_code="SOURCE_OUTCOME_INVALID",
                        artifact_refs=[], artifact_attempts=[],
                        producer_result_status=None, producer_completeness="NOT_REPORTED",
                    )
                else:
                    expected_stage = source.get("producer_stage")
                    if (not isinstance(expected_stage, dict)
                            or set(expected_stage) != {
                                "stage_id", "stage_kind", "raw_status", "manifest_sha256",
                            }
                            or expected_stage.get("stage_id") != stage.get("id")
                            or expected_stage.get("stage_kind") != stage.get("kind")
                            or expected_stage.get("raw_status") != "skipped"
                            or expected_stage.get("manifest_sha256") != manifest_hash):
                        current.update(
                            source_state="INVALID",
                            reason_code="SOURCE_OUTCOME_INVALID",
                            artifact_refs=[],
                        )
                        resolved_outcomes.append(current)
                        continue
                    current.update(
                        source_state="NOT_RUN", reason_code="PRODUCER_NOT_RUN",
                        artifact_refs=[], artifact_attempts=[],
                        producer_result_status=None, producer_completeness="NOT_REPORTED",
                        producer_stage={
                            "stage_id": stage.get("id"), "stage_kind": stage.get("kind"),
                            "raw_status": "skipped", "manifest_sha256": manifest_hash,
                        },
                    )
                resolved_outcomes.append(current)
                continue
        if current.get("source_state") == "INVALID":
            # Caller-declared INVALID and malformed NOT_SUPPLIED/NOT_RUN rows
            # have not passed producer verification.
            current["producer_stage"] = _unverified_producer_stage(source)
            resolved_outcomes.append(current)
            continue

        try:
            workflow, workflow_path, stage, stage_output, stage_manifest, manifest_hash = _workflow_record(source)
        except FileNotFoundError:
            current.update(
                source_state="UNAVAILABLE", artifact_refs=[],
                artifact_attempts=[
                    attempt for attempt in (
                        _attempt_from_ref(refs_by_id.get(ref_id), "ARTIFACT_UNAVAILABLE")
                        for ref_id in source.get("artifact_refs", [])
                    ) if attempt is not None
                ],
                producer_result_status=None, producer_completeness="NOT_REPORTED",
                reason_code="WORKFLOW_UNAVAILABLE",
                producer_stage=_unverified_producer_stage(source),
            )
            resolved_outcomes.append(current)
            continue
        except ValueError as error:
            reason = str(error)
            if reason not in {
                "PRODUCER_STAGE_NOT_FOUND", "PRODUCER_IDENTITY_MISMATCH",
                "UNSUPPORTED_PRODUCER_TYPE", "ARTIFACT_PATH_UNSAFE",
                "WORKFLOW_PATH_UNSAFE", "SOURCE_OUTCOME_INVALID",
                "WORKFLOW_UNAVAILABLE",
            }:
                reason = "SOURCE_OUTCOME_INVALID"
            state = "UNAVAILABLE" if reason == "WORKFLOW_UNAVAILABLE" else "INVALID"
            current.update(
                source_state=state, artifact_refs=[],
                artifact_attempts=[
                    attempt for attempt in (
                        _attempt_from_ref(refs_by_id.get(ref_id), reason)
                        for ref_id in source.get("artifact_refs", [])
                    ) if attempt is not None
                ],
                producer_result_status=None,
                producer_completeness="NOT_REPORTED",
                reason_code={
                    "WORKFLOW_UNAVAILABLE": "WORKFLOW_UNAVAILABLE",
                    "PRODUCER_STAGE_NOT_FOUND": "PRODUCER_STAGE_NOT_FOUND",
                    "PRODUCER_IDENTITY_MISMATCH": "PRODUCER_IDENTITY_MISMATCH",
                    "UNSUPPORTED_PRODUCER_TYPE": "UNSUPPORTED_PRODUCER_TYPE",
                    "ARTIFACT_PATH_UNSAFE": "ARTIFACT_PATH_UNSAFE",
                    "WORKFLOW_PATH_UNSAFE": "ARTIFACT_PATH_UNSAFE",
                }.get(reason, "SOURCE_OUTCOME_INVALID"),
                producer_stage=_unverified_producer_stage(source),
            )
            resolved_outcomes.append(current)
            continue

        expected_stage = source.get("producer_stage")
        if not isinstance(expected_stage, dict) or set(expected_stage) != {
            "stage_id", "stage_kind", "raw_status", "manifest_sha256",
        }:
            current.update(source_state="INVALID", artifact_refs=[],
                           reason_code="SOURCE_OUTCOME_INVALID")
            errors.append("SOURCE_OUTCOME_INVALID")
            resolved_outcomes.append(current)
            continue
        actual_raw_status = stage.get("status")
        actual_stage_id = stage.get("id")
        actual_stage_kind = stage.get("kind")
        if (expected_stage.get("stage_id") != actual_stage_id
                or expected_stage.get("stage_kind") != actual_stage_kind):
            current.update(source_state="INVALID", artifact_refs=[],
                           reason_code="PRODUCER_IDENTITY_MISMATCH",
                           producer_stage=_unverified_producer_stage(source))
            resolved_outcomes.append(current)
            continue
        if expected_stage.get("raw_status") != actual_raw_status:
            current.update(
                source_state="INVALID", artifact_refs=[],
                reason_code="SOURCE_OUTCOME_INVALID",
                producer_stage={
                    "stage_id": actual_stage_id, "stage_kind": actual_stage_kind,
                    "raw_status": actual_raw_status, "manifest_sha256": manifest_hash,
                },
            )
            resolved_outcomes.append(current)
            continue
        if expected_stage.get("manifest_sha256") != manifest_hash:
            current.update(
                source_state="INVALID", artifact_refs=[],
                reason_code="ARTIFACT_DIGEST_MISMATCH",
                producer_stage={
                    "stage_id": actual_stage_id, "stage_kind": actual_stage_kind,
                    "raw_status": actual_raw_status, "manifest_sha256": manifest_hash,
                },
            )
            resolved_outcomes.append(current)
            continue
        raw_status_mapping = (
            _source_reason_for_raw(actual_raw_status)
            if isinstance(actual_raw_status, str) else None
        )
        if raw_status_mapping:
            actual_state, reason = raw_status_mapping
            attempts = []
            for ref_id in source.get("artifact_refs", []):
                ref = refs_by_id.get(ref_id)
                attempt = _attempt_from_ref(ref, reason)
                if attempt:
                    attempts.append(attempt)
            current.update(
                source_state=actual_state, artifact_refs=[], artifact_attempts=attempts,
                producer_result_status=None, producer_completeness="NOT_REPORTED",
                producer_stage={
                    "stage_id": actual_stage_id, "stage_kind": actual_stage_kind,
                    "raw_status": actual_raw_status, "manifest_sha256": manifest_hash,
                },
                reason_code=reason,
            )
            resolved_outcomes.append(current)
            continue
        if actual_raw_status != "complete":
            current.update(source_state="INVALID", artifact_refs=[],
                           reason_code="SOURCE_OUTCOME_INVALID",
                           producer_stage={
                               "stage_id": actual_stage_id,
                               "stage_kind": actual_stage_kind,
                               "raw_status": actual_raw_status,
                               "manifest_sha256": manifest_hash,
                           })
            resolved_outcomes.append(current)
            continue
        if stage_manifest is None or stage_output is None or manifest_hash is None:
            current.update(
                source_state="INVALID", artifact_refs=[],
                artifact_attempts=[
                    attempt for attempt in (
                        _attempt_from_ref(refs_by_id.get(ref_id), "ARTIFACT_INTEGRITY_FAILED")
                        for ref_id in source.get("artifact_refs", [])
                    ) if attempt is not None
                ],
                producer_stage={
                    "stage_id": actual_stage_id, "stage_kind": actual_stage_kind,
                    "raw_status": actual_raw_status, "manifest_sha256": None,
                },
                producer_result_status=None,
                producer_completeness="NOT_REPORTED",
                reason_code="ARTIFACT_INTEGRITY_FAILED",
            )
            resolved_outcomes.append(current)
            continue
        if stage_manifest.get("status") != actual_raw_status:
            current.update(source_state="INVALID", artifact_refs=[],
                           reason_code="ARTIFACT_SCHEMA_INVALID")
            resolved_outcomes.append(current)
            continue
        inventory = stage_manifest.get("output_sha256")
        if not isinstance(inventory, dict):
            current.update(source_state="INVALID", artifact_refs=[],
                           reason_code="ARTIFACT_SCHEMA_INVALID")
            resolved_outcomes.append(current)
            continue

        selected_refs = []
        selected_pairs = []
        attempts = []
        state = "AVAILABLE"
        reason_code = None
        spec = SOURCE_SPECS[source_kind]
        for ref_id in source.get("artifact_refs", []):
            listed_ids.append(ref_id)
            ref = refs_by_id.get(ref_id)
            if ref is None or set(ref) != _ARTIFACT_REF_KEYS:
                state, reason_code = "INVALID", "SOURCE_OUTCOME_INVALID"
                continue
            allowed = spec["artifact_types"]
            if not isinstance(ref.get("artifact_type"), str):
                state, reason_code = "INVALID", "UNSUPPORTED_PRODUCER_TYPE"
                attempts.append(_attempt_from_ref(ref, reason_code))
                continue
            if (ref.get("producer_milestone") != spec["milestone"]
                    or ref.get("producer_stage_kind") != spec["stage_kind"]
                    or ref.get("artifact_type") not in allowed):
                state, reason_code = "INVALID", "UNSUPPORTED_PRODUCER_TYPE"
                attempt = _attempt_from_ref(ref, reason_code)
                if attempt:
                    attempts.append(attempt)
                continue
            if ref.get("contract_version") != artifact_contracts.CONTRACT_VERSION:
                state, reason_code = "INVALID", "ARTIFACT_VERSION_MISMATCH"
                attempts.append(_attempt_from_ref(ref, reason_code))
                continue
            if (ref.get("source_id") != source_id
                    or ref.get("producer_stage_id") != actual_stage_id
                    or ref.get("producer_stage_kind") != actual_stage_kind
                    or ref.get("producer_workflow_id") != workflow.get("workflow_id")
                    or ref.get("producer_run_manifest_sha256") != manifest_hash
                    or ref.get("raw_producer_status") != "complete"
                    or not isinstance(ref.get("content_sha256"), str)
                    or not _HASH.fullmatch(ref["content_sha256"])):
                state, reason_code = "INVALID", "PRODUCER_IDENTITY_MISMATCH"
                attempts.append(_attempt_from_ref(ref, reason_code))
                continue
            if not isinstance(ref.get("relative_path"), str):
                state, reason_code = "INVALID", "ARTIFACT_PATH_UNSAFE"
                attempts.append(_attempt_from_ref(ref, reason_code))
                continue
            if ref.get("relative_path") not in inventory:
                state, reason_code = "UNAVAILABLE", "ARTIFACT_UNAVAILABLE"
                attempts.append(_attempt_from_ref(ref, reason_code))
                continue
            try:
                artifact_path = _artifact_path(stage_output, ref.get("relative_path"))
            except FileNotFoundError:
                if ref.get("relative_path") not in inventory:
                    state, reason_code = "UNAVAILABLE", "ARTIFACT_UNAVAILABLE"
                else:
                    state, reason_code = "INVALID", "ARTIFACT_INTEGRITY_FAILED"
                attempts.append(_attempt_from_ref(ref, reason_code))
                continue
            except ValueError as error:
                state, reason_code = "INVALID", (
                    "ARTIFACT_PATH_UNSAFE" if str(error) == "ARTIFACT_PATH_UNSAFE"
                    else "ARTIFACT_INTEGRITY_FAILED"
                )
                attempts.append(_attempt_from_ref(ref, reason_code))
                continue
            declared_digest = inventory.get(ref["relative_path"])
            if (not isinstance(declared_digest, str)
                    or declared_digest != ref["content_sha256"]):
                state, reason_code = "INVALID", "ARTIFACT_DIGEST_MISMATCH"
                attempts.append(_attempt_from_ref(ref, reason_code))
                continue
            try:
                actual_digest = checksum(artifact_path)
                if actual_digest != ref["content_sha256"]:
                    state, reason_code = "INVALID", "ARTIFACT_DIGEST_MISMATCH"
                    attempts.append(_attempt_from_ref(ref, reason_code))
                    continue
                artifact_contracts.validate_artifact(artifact_path, ref["artifact_type"])
            except Exception:
                state, reason_code = "INVALID", "ARTIFACT_SCHEMA_INVALID"
                attempts.append(_attempt_from_ref(ref, reason_code))
                continue
            selected_refs.append(ref)
            selected_pairs.append((ref, ref["artifact_type"], artifact_path))

        if state == "AVAILABLE" and not selected_refs:
            state, reason_code = "UNAVAILABLE", "ARTIFACT_UNAVAILABLE"
        if state == "AVAILABLE" and attempts:
            state, reason_code = "INVALID", "SOURCE_OUTCOME_INVALID"
        if state != "AVAILABLE":
            for ref_id in source.get("artifact_refs", []):
                ref = refs_by_id.get(ref_id)
                if ref is not None and not any(
                    attempt.get("relative_path") == ref.get("relative_path")
                    for attempt in attempts
                ):
                    attempts.append(_attempt_from_ref(ref, reason_code))
            selected_refs = []
            selected_pairs = []
        else:
            selected_refs.sort(key=lambda row: row["artifact_id"])
            verified_refs.extend(selected_refs)
            for ref, _, path in selected_pairs:
                verified_paths[ref["artifact_id"]] = path
            if claimed_state != "AVAILABLE":
                state, reason_code = "INVALID", "SOURCE_OUTCOME_INVALID"
                verified_refs = [ref for ref in verified_refs if ref["source_id"] != source_id]
                selected_refs = []

        native_status, completeness = _extract_producer_native([
            (artifact_type, path) for _, artifact_type, path in selected_pairs
        ])
        current.update(
            source_state=state,
            producer_stage={
                "stage_id": actual_stage_id, "stage_kind": actual_stage_kind,
                "raw_status": actual_raw_status, "manifest_sha256": manifest_hash,
            },
            artifact_refs=[ref["artifact_id"] for ref in selected_refs],
            artifact_attempts=attempts if state != "AVAILABLE" else [],
            producer_result_status=native_status,
            producer_completeness=completeness,
            reason_code=reason_code,
        )
        resolved_outcomes.append(current)

    # Every supplied ArtifactRef must be owned by exactly one source outcome.
    referenced = []
    for source in outcomes:
        if isinstance(source, dict) and isinstance(source.get("artifact_refs"), list):
            referenced.extend(
                ref_id for ref_id in source["artifact_refs"] if _token(ref_id)
            )
    if (len(referenced) != len(set(referenced))
            or set(referenced) != set(refs_by_id)):
        errors.append("SOURCE_OUTCOME_INVALID")
    # Each source family must be explicit; one absence row is allowed only if
    # there are no declared runs of that family.
    if set(source_kinds_without_runs) != set(SOURCE_SPECS):
        errors.append("SOURCE_KIND_MISSING")
    for kind, rows in source_kinds_without_runs.items():
        states = [row.get("source_state") for row in rows if isinstance(row, dict)]
        if not rows or (
            len(rows) == 1 and isinstance(states[0], str)
            and states[0] in {"NOT_SUPPLIED", "NOT_RUN"}
        ):
            continue
        if any(
            isinstance(state, str) and state in {"NOT_SUPPLIED", "NOT_RUN"}
            for state in states
        ):
            errors.append("SOURCE_OUTCOME_INVALID")
    verified_refs.sort(key=lambda row: row.get("artifact_id", ""))
    resolved_outcomes = [
        _normalize_invalid_source_outcome(row) for row in resolved_outcomes
    ]
    return resolved_outcomes, verified_refs, verified_paths, errors


def inspect_dependency(config):
    """Return an always-available top-level dependency with per-source outcomes."""
    try:
        resolved, refs, _, errors = _resolve_source_outcomes(config)
        return {
            "status": "available",
            "m14_source_resolution": {
                "source_outcomes": [
                    {
                        "source_id": row.get("source_id"),
                        "source_kind": row.get("source_kind"),
                        "source_state": row.get("source_state"),
                        "reason_code": row.get("reason_code"),
                        "producer_workflow_id": (
                            row.get("workflow_ref", {}).get("workflow_id")
                            if isinstance(row.get("workflow_ref"), dict) else None
                        ),
                        "producer_stage_id": (
                            row.get("producer_stage", {}).get("stage_id")
                            if isinstance(row.get("producer_stage"), dict) else None
                        ),
                        "artifact_digests": sorted(
                            ref.get("content_sha256") for ref in refs
                            if ref.get("source_id") == row.get("source_id")
                        ),
                    }
                    for row in resolved
                ],
                "validation_errors": sorted(set(errors)),
                "contract_semantics": artifact_contracts.semantic_identity(sorted({
                    *(ref["artifact_type"] for ref in refs),
                    *OUTPUT_CONTRACTS.values(),
                })),
            },
        }
    except Exception as error:
        return {
            "status": "available",
            "m14_source_resolution": {
                "source_outcomes": [],
                "validation_errors": ["SOURCE_OUTCOME_INVALID"],
            },
        }


def _strip_ref(value):
    if isinstance(value, dict):
        return {
            key: _strip_ref(item) for key, item in value.items()
            if key not in {"source_refs", "independence_ref", "provenance_ref"}
        }
    if isinstance(value, list):
        return [_strip_ref(item) for item in value]
    return value


def _semantic_projection(config, source_outcomes, verified_refs):
    semantics = []
    refs_by_source = defaultdict(list)
    for ref in verified_refs:
        refs_by_source[ref["source_id"]].append(ref["artifact_type"])
    for source in source_outcomes:
        semantics.append({
            "source_kind": source.get("source_kind"),
            "source_state": source.get("source_state"),
            "verified_artifact_types": sorted(
                refs_by_source.get(source.get("source_id"), ())
            ) if source.get("source_state") == "AVAILABLE" else [],
        })
    semantics.sort(key=_canonical_json_bytes)
    units = config.get("sampling_units") if isinstance(config.get("sampling_units"), list) else []
    pairs = config.get("evaluated_pairs") if isinstance(config.get("evaluated_pairs"), list) else []
    observations = config.get("observations") if isinstance(config.get("observations"), list) else []
    return {
        "schema": SEMANTIC_SCHEMA,
        "dataset_id": config.get("dataset_id"),
        "input_schema": config.get("schema"),
        "semantic_version": SEMANTIC_VERSION,
        "sampling_units": [_strip_ref(row) for row in units],
        "evaluated_pairs": pairs,
        "observations": [_strip_ref(row) for row in observations],
        "source_semantics": semantics,
    }


def _provenance_projection(config, source_outcomes, verified_refs, findings):
    sources = []
    for row in source_outcomes:
        workflow = row.get("workflow_ref") if isinstance(row.get("workflow_ref"), dict) else {}
        stage = row.get("producer_stage") if isinstance(row.get("producer_stage"), dict) else {}
        sources.append({
            "source_id": row.get("source_id"),
            "source_kind": row.get("source_kind"),
            "source_state": row.get("source_state"),
            "workflow_id": workflow.get("workflow_id"),
            "stage_id": stage.get("stage_id"),
            "stage_kind": stage.get("stage_kind"),
            "raw_status": stage.get("raw_status"),
            "producer_result_status": row.get("producer_result_status"),
            "producer_completeness": row.get("producer_completeness"),
            "manifest_sha256": stage.get("manifest_sha256"),
            "reason_code": row.get("reason_code"),
            "artifact_attempts": [
                {
                    "artifact_type": attempt.get("artifact_type"),
                    "contract_version": attempt.get("contract_version"),
                    "expected_content_sha256": attempt.get("expected_content_sha256"),
                    "reason_code": attempt.get("reason_code"),
                }
                for attempt in row.get("artifact_attempts", [])
                if isinstance(attempt, dict)
            ],
        })
    sources.sort(key=lambda row: (str(row.get("source_kind")), str(row.get("source_id"))))
    artifacts = [{
        "artifact_id": ref.get("artifact_id"),
        "source_id": ref.get("source_id"),
        "producer_milestone": ref.get("producer_milestone"),
        "producer_stage_kind": ref.get("producer_stage_kind"),
        "producer_stage_id": ref.get("producer_stage_id"),
        "producer_workflow_id": ref.get("producer_workflow_id"),
        "producer_run_manifest_sha256": ref.get("producer_run_manifest_sha256"),
        "artifact_type": ref.get("artifact_type"),
        "contract_version": ref.get("contract_version"),
        "content_sha256": ref.get("content_sha256"),
        "raw_producer_status": ref.get("raw_producer_status"),
    } for ref in sorted(verified_refs, key=lambda row: row.get("artifact_id", ""))]
    return {
        "schema": PROVENANCE_SCHEMA,
        "sources": sources,
        "artifacts": artifacts,
        "row_provenance": {
            "sampling_units": [
                {
                    "unit_id": row.get("unit_id"),
                    "source_refs": row.get("source_refs", []),
                    "independence_ref": row.get("independence_ref"),
                    "control_role": row.get("control_role"),
                }
                for row in config.get("sampling_units", [])
                if isinstance(row, dict)
            ] if isinstance(config.get("sampling_units"), list) else [],
            "observations": [
                {
                    "observation_id": row.get("observation_id"),
                    "source_refs": row.get("source_refs", []),
                    "candidate_method_ref": row.get("candidate_method_ref"),
                    "helper_method_ref": row.get("helper_method_ref"),
                }
                for row in config.get("observations", [])
                if isinstance(row, dict)
            ] if isinstance(config.get("observations"), list) else [],
        },
        "validation_findings": sorted(set(findings)),
    }


def _registration_digest():
    # Delayed import avoids a module cycle during registry construction.
    from . import artifact_workflow

    definition = artifact_workflow.build_default_registry().get(STAGE_KIND)
    registration = artifact_workflow._stage_cache_registration_identity(definition)
    return _sha256_json(registration)


def _implementation_sha256():
    content = Path(__file__).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def _cache_identity(semantic_sha, provenance_sha, verified_refs):
    contract_types = sorted({
        *(ref["artifact_type"] for ref in verified_refs),
        *OUTPUT_CONTRACTS.values(),
    })
    return {
        "schema": CACHE_SCHEMA,
        "stage_id": STAGE_KIND,
        "stage_version": STAGE_VERSION,
        "stage_registration_sha256": _registration_digest(),
        "semantic_input_sha256": semantic_sha,
        "provenance_sha256": provenance_sha,
        "implementation_sha256": {
            "satellite_discovery/m14_descriptive_observations.py": _implementation_sha256(),
        },
        "contract_semantics": artifact_contracts.semantic_identity(contract_types),
    }


def _validate_provenance_refs(
    value, verified_ids, errors, label, *, required=False, declared_ids=None
):
    if isinstance(value, str):
        refs = [value]
    elif isinstance(value, list):
        refs = value
    else:
        errors.append(f"{label}_PROVENANCE_INVALID")
        return
    if required and not refs:
        errors.append(f"{label}_PROVENANCE_REQUIRED")
    if any(not _token(ref) for ref in refs) or refs != sorted(refs) or len(refs) != len(set(refs)):
        errors.append(f"{label}_PROVENANCE_INVALID")
        return
    declared_ids = declared_ids or set()
    if any(ref in declared_ids and ref not in verified_ids for ref in refs):
        errors.append(f"{label}_PROVENANCE_INVALID")


def _validate_method(method, tested, state, verified_ids, declared_ids, label, errors):
    if method is None:
        if state in {"PRESENT", "NOT_DETECTED_WITHIN_SCOPE"} or tested:
            errors.append(f"{label}_METHOD_REQUIRED")
        return
    if not _object(method, _METHOD_KEYS, f"{label}_METHOD", errors):
        return
    for key in ("method_id", "method_version", "scope_id", "scope_description"):
        if not isinstance(method.get(key), str) or not method[key].strip():
            errors.append(f"{label}_METHOD_INVALID")
    _validate_provenance_refs(
        method.get("provenance_ref"), verified_ids, errors, f"{label}_METHOD",
        required=True, declared_ids=declared_ids,
    )


def _validate_limit(value, label, errors):
    if value is None:
        return
    if not _object(value, _DETECTION_LIMIT_KEYS, f"{label}_LIMIT", errors):
        return
    if any(not isinstance(value.get(key), str) or not value[key].strip()
           for key in ("metric", "unit", "basis")):
        errors.append(f"{label}_LIMIT_INVALID")
    try:
        _json_number(value.get("value"))
    except ValueError:
        errors.append(f"{label}_LIMIT_INVALID")


def _validate_state(
    state, reason, tested, method, limit, label, verified_ids, declared_ids, errors
):
    if not isinstance(state, str) or state not in OBSERVATION_STATES:
        errors.append(f"{label}_STATE_INVALID")
        return
    if state in {"PRESENT", "NOT_DETECTED_WITHIN_SCOPE"}:
        if reason is not None:
            errors.append(f"{label}_REASON_INVALID")
        if tested is not True:
            errors.append(f"{label}_TESTED_REQUIRED")
    elif state in {"UNKNOWN", "UNAVAILABLE", "NOT_APPLICABLE", "CONFLICTING"}:
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"{label}_REASON_REQUIRED")
    if type(tested) is not bool:
        errors.append(f"{label}_TESTED_INVALID")
        return
    if state in {"UNAVAILABLE", "NOT_APPLICABLE", "CONFLICTING"} and tested:
        errors.append(f"{label}_TESTED_INVALID")
    if not tested and state in {"PRESENT", "NOT_DETECTED_WITHIN_SCOPE"}:
        errors.append(f"{label}_TESTED_INVALID")
    _validate_method(method, tested, state, verified_ids, declared_ids, label, errors)
    _validate_limit(limit, label, errors)
    if state == "NOT_DETECTED_WITHIN_SCOPE" and (
            not isinstance(method, dict)
            or not isinstance(method.get("scope_description"), str)
            or not method.get("scope_description", "").strip()):
        errors.append(f"{label}_DETECTION_SCOPE_REQUIRED")


def _validate_unit_rows(config, verified_ids, declared_ids, errors):
    units = config.get("sampling_units")
    if not isinstance(units, list):
        errors.append("SAMPLING_UNITS_INVALID")
        return {}, set()
    by_id = {}
    invalid_ids = set()
    for index, row in enumerate(units):
        row_errors = []
        if not _object(row, _UNIT_KEYS, f"UNIT_{index}", row_errors):
            errors.extend(row_errors)
            continue
        unit_id = row.get("unit_id")
        if not _token(unit_id) or unit_id in by_id:
            errors.append("UNIT_ID_DUPLICATE_OR_INVALID")
            if _token(unit_id):
                invalid_ids.add(unit_id)
            continue
        if (not isinstance(row.get("unit_type"), str)
                or row.get("unit_type") not in UNIT_TYPES):
            row_errors.append("UNIT_TYPE_INVALID")
        label = row.get("unit_type_label")
        if row.get("unit_type") == "OTHER_DECLARED":
            if not isinstance(label, str) or not label.strip():
                row_errors.append("UNIT_TYPE_LABEL_REQUIRED")
        elif label is not None:
            row_errors.append("UNIT_TYPE_LABEL_INVALID")
        parents = row.get("parent_unit_ids")
        if (not isinstance(parents, list) or any(not _token(item) for item in parents)
                or parents != sorted(parents) or len(parents) != len(set(parents))):
            row_errors.append("UNIT_PARENT_IDS_INVALID")
        if row.get("study_id") is not None and not _token(row["study_id"]):
            row_errors.append("UNIT_STUDY_ID_INVALID")
        independence_state = row.get("independence_state")
        if (not isinstance(independence_state, str)
                or independence_state not in INDEPENDENCE_STATES):
            row_errors.append("UNIT_INDEPENDENCE_INVALID")
        independence_ref = row.get("independence_ref")
        if row.get("independence_state") == "VERIFIED_WITH_PROVENANCE":
            if not isinstance(independence_ref, str) or independence_ref not in verified_ids:
                row_errors.append("INDEPENDENCE_PROVENANCE_INVALID")
        elif independence_ref is not None:
            row_errors.append("INDEPENDENCE_PROVENANCE_INVALID")
        control_role = row.get("control_role")
        if control_role is not None:
            if (not isinstance(control_role, dict)
                    or set(control_role) != {"label", "provenance_ref"}
                    or not isinstance(control_role.get("label"), str)
                    or not control_role["label"].strip()):
                row_errors.append("CONTROL_ROLE_INVALID")
            else:
                _validate_provenance_refs(
                    control_role["provenance_ref"], verified_ids, row_errors,
                    "CONTROL_ROLE", required=True, declared_ids=declared_ids,
                )
        source_refs = row.get("source_refs")
        if (not isinstance(source_refs, list)
                or any(not _token(item) for item in source_refs)
                or source_refs != sorted(source_refs)
                or len(source_refs) != len(set(source_refs))):
            row_errors.append("UNIT_SOURCE_REFS_INVALID")
        else:
            _validate_provenance_refs(
                source_refs, verified_ids, row_errors, "UNIT",
                declared_ids=declared_ids,
            )
        if row_errors:
            invalid_ids.add(unit_id)
            errors.extend(row_errors)
        by_id[unit_id] = row
    for unit_id, row in by_id.items():
        for parent in row.get("parent_unit_ids", []) if isinstance(row, dict) else []:
            if parent not in by_id:
                errors.append("UNIT_PARENT_FOREIGN_KEY_INVALID")
                invalid_ids.add(unit_id)
    return by_id, invalid_ids


def _validate_pairs(config, unit_by_id, errors):
    pairs = config.get("evaluated_pairs")
    if not isinstance(pairs, list):
        errors.append("EVALUATED_PAIRS_INVALID")
        return [], set()
    frame = set()
    seen_pairs = set()
    normalized = []
    for index, pair in enumerate(pairs):
        if not _object(pair, _PAIR_KEYS, f"PAIR_{index}", errors):
            continue
        candidate, helper = pair.get("candidate_id"), pair.get("helper_id")
        if not _token(candidate) or not _token(helper):
            errors.append("EVALUATED_PAIR_ID_INVALID")
            continue
        pair_key = (candidate, helper)
        if pair_key in seen_pairs:
            errors.append("EVALUATED_PAIR_ID_INVALID")
            continue
        seen_pairs.add(pair_key)
        unit_ids = pair.get("unit_ids")
        if (not isinstance(unit_ids, list)
                or any(not _token(item) for item in unit_ids)
                or unit_ids != sorted(unit_ids)
                or len(unit_ids) != len(set(unit_ids))):
            errors.append("PAIR_UNIT_IDS_INVALID")
            continue
        for unit_id in unit_ids:
            if unit_id not in unit_by_id:
                errors.append("PAIR_UNIT_FOREIGN_KEY_INVALID")
            frame.add((candidate, helper, unit_id))
        normalized.append(pair)
    return normalized, frame


def _validate_observations(
    config, frame, unit_by_id, invalid_units, verified_ids, declared_ids, errors
):
    observations = config.get("observations")
    if not isinstance(observations, list):
        errors.append("OBSERVATIONS_INVALID")
        return [], [], set(), False
    accepted = []
    rejected = []
    seen_ids = set()
    seen_rows = set()
    observed_frame = set()
    structural_duplicate = False
    for index, row in enumerate(observations):
        row_errors = []
        if not _object(row, _OBSERVATION_KEYS, f"OBSERVATION_{index}", row_errors):
            rejected.append({
                "observation_id": row.get("observation_id") if isinstance(row, dict) else None,
                "reason_codes": sorted(set(row_errors)),
            })
            continue
        observation_id = row.get("observation_id")
        if not _token(observation_id) or observation_id in seen_ids:
            errors.append("OBSERVATION_ID_DUPLICATE_OR_INVALID")
            structural_duplicate = True
            row_errors.append("OBSERVATION_ID_DUPLICATE_OR_INVALID")
        if _token(observation_id):
            seen_ids.add(observation_id)
        candidate, helper, unit_id = (
            row.get("candidate_id"), row.get("helper_id"), row.get("unit_id")
        )
        if not _token(candidate) or not _token(helper) or not _token(unit_id):
            row_errors.append("OBSERVATION_IDENTITY_INVALID")
        pair_unit = (candidate, helper, unit_id) if all(
            _token(item) for item in (candidate, helper, unit_id)
        ) else None
        if pair_unit is not None:
            if pair_unit in seen_rows:
                errors.append("PAIR_UNIT_DUPLICATE")
                structural_duplicate = True
                row_errors.append("PAIR_UNIT_DUPLICATE")
            seen_rows.add(pair_unit)
            observed_frame.add(pair_unit)
            if pair_unit not in frame:
                row_errors.append("OBSERVATION_OUTSIDE_FRAME")
        if (not _token(unit_id) or unit_id not in unit_by_id
                or (isinstance(unit_id, str) and unit_id in invalid_units)):
            row_errors.append("OBSERVATION_UNIT_INVALID")
        source_refs = row.get("source_refs")
        if (not isinstance(source_refs, list)
                or any(not _token(item) for item in source_refs)
                or source_refs != sorted(source_refs)
                or len(source_refs) != len(set(source_refs))):
            row_errors.append("OBSERVATION_SOURCE_REFS_INVALID")
        else:
            _validate_provenance_refs(
                source_refs, verified_ids, row_errors, "OBSERVATION",
                declared_ids=declared_ids,
            )
        for prefix in ("candidate", "helper"):
            _validate_state(
                row.get(f"{prefix}_state"),
                row.get(f"{prefix}_state_reason"),
                row.get(f"{prefix}_tested"),
                row.get(f"{prefix}_method_ref"),
                row.get(f"{prefix}_detection_limit"),
                prefix.upper(),
                verified_ids,
                declared_ids,
                row_errors,
            )
            if row.get(f"{prefix}_state") == "CONFLICTING":
                method = row.get(f"{prefix}_method_ref")
                provenance = set(source_refs or [])
                if isinstance(method, dict):
                    method_refs = method.get("provenance_ref")
                    if isinstance(method_refs, str):
                        provenance.add(method_refs)
                    elif isinstance(method_refs, list):
                        provenance.update(method_refs)
                if len(provenance) < 2:
                    row_errors.append(f"{prefix.upper()}_CONFLICT_PROVENANCE_REQUIRED")
        if row_errors:
            rejected.append({
                "observation_id": observation_id,
                "reason_codes": sorted(set(row_errors)),
            })
        else:
            accepted.append(row)
    return accepted, rejected, observed_frame, structural_duplicate


def _stratum_key(row, unit, dataset_id):
    candidate_method = row.get("candidate_method_ref")
    helper_method = row.get("helper_method_ref")
    return (
        dataset_id,
        row["candidate_id"],
        row["helper_id"],
        unit["unit_type"],
        _canonical_json_text(unit.get("control_role")),
        unit.get("study_id"),
        candidate_method.get("scope_id") if isinstance(candidate_method, dict) else None,
        helper_method.get("scope_id") if isinstance(helper_method, dict) else None,
    )


def _summary(accepted, units, dataset_id, frame_complete, result_state, frame):
    groups = defaultdict(list)
    all_cells = Counter()
    excluded_reasons = Counter()
    for row in accepted:
        unit = units[row["unit_id"]]
        groups[_stratum_key(row, unit, dataset_id)].append(row)
        if not _jointly_evaluable(row):
            for state in {
                row.get("candidate_state"), row.get("helper_state"),
            }:
                if state in {"UNKNOWN", "UNAVAILABLE", "NOT_APPLICABLE", "CONFLICTING"}:
                    excluded_reasons[state] += 1
            if row.get("candidate_tested") is not True or row.get("helper_tested") is not True:
                excluded_reasons["NOT_JOINTLY_TESTED"] += 1
            if (row.get("candidate_state") == "NOT_DETECTED_WITHIN_SCOPE"
                    or row.get("helper_state") == "NOT_DETECTED_WITHIN_SCOPE"):
                excluded_reasons["SCOPED_NONDETECTION_METHOD_OR_SCOPE_INVALID"] += 1

    strata = []
    totals = Counter()
    def stratum_sort_key(key):
        return (
            key[0], key[1], key[2], key[3], _null_first(key[4]),
            _null_first(key[5]), _null_first(key[6]), _null_first(key[7]),
        )

    for key, rows in sorted(groups.items(), key=lambda item: stratum_sort_key(item[0])):
        cells = Counter()
        counts = Counter()
        units_in_stratum = set()
        for row in rows:
            units_in_stratum.add(row["unit_id"])
            counts["n_rows"] += 1
            counts["n_candidate_tested"] += row.get("candidate_tested") is True
            counts["n_helper_tested"] += row.get("helper_tested") is True
            states = (row.get("candidate_state"), row.get("helper_state"))
            if any(state in {"UNKNOWN", "UNAVAILABLE"} for state in states):
                counts["n_unknown_or_unavailable"] += 1
            if "NOT_APPLICABLE" in states:
                counts["n_not_applicable"] += 1
            if "CONFLICTING" in states:
                counts["n_conflicting"] += 1
            if _jointly_evaluable(row):
                counts["n_jointly_tested"] += 1
                cell = _cell_name(*states)
                cells[cell] += 1
                all_cells[cell] += 1
            else:
                counts["n_excluded_from_joint_testing"] += 1
        counts["n_unique_units"] = len(units_in_stratum)
        for name in (
            "n_rows", "n_unique_units", "n_candidate_tested", "n_helper_tested",
            "n_jointly_tested", "n_unknown_or_unavailable", "n_not_applicable",
            "n_conflicting", "n_excluded_from_joint_testing",
        ):
            totals[name] += counts[name]
        strata.append({
            "dataset_id": key[0],
            "candidate_id": key[1],
            "helper_id": key[2],
            "unit_type": key[3],
            "control_role": json.loads(key[4]),
            "study_id": key[5],
            "candidate_method_scope_id": key[6],
            "helper_method_scope_id": key[7],
            **{name: counts[name] for name in (
                "n_rows", "n_unique_units", "n_candidate_tested",
                "n_helper_tested", "n_jointly_tested",
                "n_unknown_or_unavailable", "n_not_applicable",
                "n_conflicting", "n_excluded_from_joint_testing",
            )},
            "cells": {
                name: cells[name] for name in (
                    "both_present",
                    "candidate_present_helper_not_detected",
                    "candidate_not_detected_helper_present",
                    "both_not_detected",
                )
            },
        })
    totals["n_unique_units"] = len({row["unit_id"] for row in accepted})
    return {
        "schema": SUMMARY_SCHEMA,
        "dataset_id": dataset_id,
        "result_state": result_state,
        "frame_complete": frame_complete,
        "denominator_scope": {
            "n_declared_pair_unit_rows": len(frame),
            "n_accepted_observation_rows": len(accepted),
            "n_jointly_tested": totals["n_jointly_tested"],
            "is_complete_denominator": frame_complete,
        },
        **{name: totals[name] for name in (
            "n_rows", "n_unique_units", "n_candidate_tested", "n_helper_tested",
            "n_jointly_tested", "n_unknown_or_unavailable", "n_not_applicable",
            "n_conflicting", "n_excluded_from_joint_testing",
        )},
        "cells": {
            name: all_cells[name] for name in (
                "both_present",
                "candidate_present_helper_not_detected",
                "candidate_not_detected_helper_present",
                "both_not_detected",
            )
        },
        "excluded_reasons": dict(sorted(excluded_reasons.items())),
        "strata": strata,
    }


def _jointly_evaluable(row):
    return (
        row.get("candidate_tested") is True
        and row.get("helper_tested") is True
        and row.get("candidate_state") in {"PRESENT", "NOT_DETECTED_WITHIN_SCOPE"}
        and row.get("helper_state") in {"PRESENT", "NOT_DETECTED_WITHIN_SCOPE"}
        and isinstance(row.get("candidate_method_ref"), dict)
        and isinstance(row.get("helper_method_ref"), dict)
    )


def _cell_name(candidate_state, helper_state):
    return {
        ("PRESENT", "PRESENT"): "both_present",
        ("PRESENT", "NOT_DETECTED_WITHIN_SCOPE"): "candidate_present_helper_not_detected",
        ("NOT_DETECTED_WITHIN_SCOPE", "PRESENT"): "candidate_not_detected_helper_present",
        ("NOT_DETECTED_WITHIN_SCOPE", "NOT_DETECTED_WITHIN_SCOPE"): "both_not_detected",
    }[(candidate_state, helper_state)]


def _frame_result(manifest, accepted, rejected, frame, observed_frame, structural_errors):
    structural_invalid = bool(structural_errors)
    if structural_invalid:
        return "INVALID_INPUT", False
    if not frame and not manifest.get("observations"):
        return "NOT_EVALUATED", True
    incomplete = bool(frame - observed_frame) or bool(rejected) or len(accepted) != len(frame)
    if not frame and manifest.get("observations"):
        incomplete = True
    if incomplete:
        if manifest.get("observations") and not accepted:
            return "INVALID_INPUT", False
        return "INCOMPLETE", False
    jointly = sum(1 for row in accepted if _jointly_evaluable(row))
    if jointly == 0:
        return "INSUFFICIENT_MATCHED_EVIDENCE", True
    return "COMPLETED_DESCRIPTIVE", True


def _result_error_rows(errors):
    return [{"reason_code": code} for code in sorted(set(errors))]


def _read_output_doc(path, expected_schema, exact_keys):
    value = _read_json_file(path)
    if not isinstance(value, dict) or value.get("schema") != expected_schema:
        raise ValueError("M14 output has an invalid schema")
    if set(value) != exact_keys:
        raise ValueError("M14 output has invalid fields")
    return value


_OBSERVATION_OUTPUT_KEYS = frozenset({
    "schema", "dataset_id", "semantic_version", "result_state",
    "frame_complete", "observations", "rejected_observations",
    "missing_pair_units", "source_outcomes", "validation_findings",
})
_SUMMARY_OUTPUT_KEYS = frozenset({
    "schema", "dataset_id", "result_state", "frame_complete",
    "denominator_scope", "n_rows", "n_unique_units", "n_candidate_tested",
    "n_helper_tested", "n_jointly_tested", "n_unknown_or_unavailable",
    "n_not_applicable", "n_conflicting", "n_excluded_from_joint_testing",
    "cells", "excluded_reasons", "strata",
})
_BUNDLE_OUTPUT_KEYS = frozenset({
    "schema", "dataset_id", "input_schema", "semantic_version",
    "result_state", "frame_complete", "source_outcomes", "source_artifacts",
    "validation_findings", "m14_semantic_input_sha256",
    "m14_provenance_sha256", "m14_cache_identity_sha256",
    "stage_registration_sha256", "implementation_sha256",
    "contract_semantics", "outputs", "denominator_rules", "claim_boundary",
})


def _denominator_rules():
    return {
        "scope": "evaluated_pairs[].unit_ids",
        "jointly_tested": (
            "Both members tested under declared methods and each state is "
            "PRESENT or NOT_DETECTED_WITHIN_SCOPE."
        ),
        "missing_rows_are_not_negative": True,
        "association_estimate": None,
    }


def _claim_boundary():
    return {
        "summary": "Descriptive co-detection only; association and dependence were not assessed.",
        "independence_inferred": False,
        "helper_dependence_assessed": False,
    }


def _validate_output_source_outcomes(rows):
    if not isinstance(rows, list):
        raise ValueError("M14 source outcomes must be an array")
    invalid_reasons = {
        "PRODUCER_STAGE_NOT_FOUND", "PRODUCER_IDENTITY_MISMATCH",
        "UNSUPPORTED_PRODUCER_TYPE", "ARTIFACT_VERSION_MISMATCH",
        "ARTIFACT_DIGEST_MISMATCH", "ARTIFACT_SCHEMA_INVALID",
        "ARTIFACT_PATH_UNSAFE", "ARTIFACT_INTEGRITY_FAILED",
        "SOURCE_OUTCOME_INVALID",
    }
    valid_ids = set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != _SOURCE_OUTCOME_KEYS
                or not _json_safe(row)):
            raise ValueError("M14 source outcome row is malformed")
        state = row.get("source_state")
        if not isinstance(state, str) or state not in SOURCE_STATES:
            raise ValueError("M14 source outcome state is invalid")
        if state == "INVALID":
            if (row.get("reason_code") not in invalid_reasons
                    or row.get("artifact_refs") != []
                    or not isinstance(row.get("artifact_attempts"), list)):
                raise ValueError("M14 invalid source outcome is malformed")
            continue
        if _source_kind_state_errors(row):
            raise ValueError("M14 resolved source outcome is malformed")
        source_id = row.get("source_id")
        if source_id in valid_ids:
            raise ValueError("M14 resolved source IDs are not unique")
        valid_ids.add(source_id)


def _validate_output_artifact_refs(refs, source_outcomes):
    if not isinstance(refs, list):
        raise ValueError("M14 source artifact references must be an array")
    if any(
        not isinstance(ref, dict) or set(ref) != _ARTIFACT_REF_KEYS
        or not _token(ref.get("artifact_id"))
        or not _token(ref.get("source_id"))
        or not _token(ref.get("producer_stage_id"))
        or not _token(ref.get("producer_stage_kind"))
        or not _token(ref.get("producer_workflow_id"))
        or not isinstance(ref.get("producer_milestone"), str)
        or not isinstance(ref.get("artifact_type"), str)
        or ref.get("contract_version") != artifact_contracts.CONTRACT_VERSION
        or not isinstance(ref.get("relative_path"), str)
        or not isinstance(ref.get("producer_run_manifest_sha256"), str)
        or not _HASH.fullmatch(ref["producer_run_manifest_sha256"])
        or not isinstance(ref.get("content_sha256"), str)
        or not _HASH.fullmatch(ref["content_sha256"])
        or ref.get("raw_producer_status") != "complete"
        for ref in refs
    ):
        raise ValueError("M14 source artifact reference is malformed")
    artifact_ids = [ref["artifact_id"] for ref in refs]
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("M14 source artifact IDs are not unique")
    if artifact_ids != sorted(artifact_ids):
        raise ValueError("M14 source artifact references are not canonical")
    outcomes_by_id = {
        row["source_id"]: row
        for row in source_outcomes
        if row.get("source_state") == "AVAILABLE" and _token(row.get("source_id"))
    }
    expected_ids = set()
    for ref in refs:
        try:
            _safe_relative_parts(ref["relative_path"], "ARTIFACT")
        except ValueError as error:
            raise ValueError("M14 source artifact path is unsafe") from error
        if not any(
            ref["producer_milestone"] == spec["milestone"]
            and ref["producer_stage_kind"] == spec["stage_kind"]
            and ref["artifact_type"] in spec["artifact_types"]
            for spec in SOURCE_SPECS.values()
        ):
            raise ValueError("M14 source artifact producer/type is unsupported")
        outcome = outcomes_by_id.get(ref["source_id"])
        if outcome is None:
            raise ValueError("M14 source artifact has no available source outcome")
        stage = outcome.get("producer_stage")
        workflow = outcome.get("workflow_ref")
        if (not isinstance(stage, dict) or not isinstance(workflow, dict)
                or ref["artifact_id"] not in outcome.get("artifact_refs", [])
                or ref["producer_stage_id"] != stage.get("stage_id")
                or ref["producer_stage_kind"] != stage.get("stage_kind")
                or ref["producer_workflow_id"] != workflow.get("workflow_id")
                or ref["producer_run_manifest_sha256"] != stage.get("manifest_sha256")
                or ref["raw_producer_status"] != stage.get("raw_status")):
            raise ValueError("M14 source artifact does not match its producer outcome")
        expected_ids.add(ref["artifact_id"])
    outcome_ids = {
        ref_id
        for row in source_outcomes
        if row.get("source_state") == "AVAILABLE"
        for ref_id in row.get("artifact_refs", [])
    }
    if expected_ids != outcome_ids:
        raise ValueError("M14 source artifact references do not match their outcomes")


def validate_output_file(path, artifact_type):
    """Strict validators for the three public M14 output contracts."""
    if artifact_type == "m14_observation_table":
        doc = _read_output_doc(path, OBSERVATION_SCHEMA, _OBSERVATION_OUTPUT_KEYS)
        if not isinstance(doc["observations"], list) or not isinstance(doc["rejected_observations"], list):
            raise ValueError("M14 observation output rows must be arrays")
        if (not isinstance(doc["result_state"], str)
                or doc["result_state"] not in RESULT_STATES
                or type(doc["frame_complete"]) is not bool
                or doc["semantic_version"] != SEMANTIC_VERSION):
            raise ValueError("M14 observation output state is invalid")
        _validate_output_source_outcomes(doc["source_outcomes"])
        if any(
            not isinstance(row, dict) or set(row) != _OBSERVATION_KEYS
            or not _json_safe(row) or not _token(row.get("observation_id"))
            for row in doc["observations"]
        ):
            raise ValueError("M14 accepted observation row is malformed")
        if any(
            not isinstance(row, dict)
            or set(row) != {"observation_id", "reason_codes"}
            or (row.get("observation_id") is not None
                and not _token(row.get("observation_id")))
            or not isinstance(row.get("reason_codes"), list)
            or any(not isinstance(reason, str) or not reason for reason in row["reason_codes"])
            for row in doc["rejected_observations"]
        ):
            raise ValueError("M14 rejected observation row is malformed")
        if not isinstance(doc["missing_pair_units"], list) or any(
            not isinstance(row, dict)
            or set(row) != {"candidate_id", "helper_id", "unit_id"}
            or any(not _token(row.get(key)) for key in ("candidate_id", "helper_id", "unit_id"))
            for row in doc["missing_pair_units"]
        ):
            raise ValueError("M14 missing-frame row is malformed")
        return {"schema": OBSERVATION_SCHEMA, "record_count": len(doc["observations"])}
    if artifact_type == "m14_descriptive_summary":
        doc = _read_output_doc(path, SUMMARY_SCHEMA, _SUMMARY_OUTPUT_KEYS)
        if (not isinstance(doc["result_state"], str)
                or doc["result_state"] not in RESULT_STATES
                or type(doc["frame_complete"]) is not bool):
            raise ValueError("M14 summary state is invalid")
        for key in (
            "n_rows", "n_unique_units", "n_candidate_tested", "n_helper_tested",
            "n_jointly_tested", "n_unknown_or_unavailable", "n_not_applicable",
            "n_conflicting", "n_excluded_from_joint_testing",
        ):
            if type(doc[key]) is not int or doc[key] < 0:
                raise ValueError("M14 summary count is invalid")
        if not isinstance(doc["strata"], list) or not isinstance(doc["cells"], dict):
            raise ValueError("M14 summary structure is invalid")
        if set(doc["cells"]) != {
            "both_present", "candidate_present_helper_not_detected",
            "candidate_not_detected_helper_present", "both_not_detected",
        } or any(type(value) is not int or value < 0 for value in doc["cells"].values()):
            raise ValueError("M14 summary cells are invalid")
        scope = doc["denominator_scope"]
        if (not isinstance(scope, dict)
                or set(scope) != {
                    "n_declared_pair_unit_rows", "n_accepted_observation_rows",
                    "n_jointly_tested", "is_complete_denominator",
                }
                or any(type(scope.get(key)) is not int or scope[key] < 0 for key in (
                    "n_declared_pair_unit_rows", "n_accepted_observation_rows",
                    "n_jointly_tested",
                ))
                or type(scope.get("is_complete_denominator")) is not bool
                or scope["n_accepted_observation_rows"] != doc["n_rows"]
                or scope["n_jointly_tested"] != doc["n_jointly_tested"]
                or scope["is_complete_denominator"] != doc["frame_complete"]):
            raise ValueError("M14 denominator scope is invalid")
        return {"schema": SUMMARY_SCHEMA, "record_count": len(doc["strata"])}
    if artifact_type == "m14_result_bundle":
        doc = _read_output_doc(path, RESULT_BUNDLE_SCHEMA, _BUNDLE_OUTPUT_KEYS)
        if (not isinstance(doc["result_state"], str)
                or doc["result_state"] not in RESULT_STATES
                or type(doc["frame_complete"]) is not bool):
            raise ValueError("M14 result bundle state is invalid")
        for key in (
            "m14_semantic_input_sha256", "m14_provenance_sha256",
            "m14_cache_identity_sha256", "stage_registration_sha256",
        ):
            if not isinstance(doc[key], str) or not _HASH.fullmatch(doc[key]):
                raise ValueError("M14 result identity digest is invalid")
        outputs = doc["outputs"]
        expected = {
            "m14_observation_table": "observations.json",
            "m14_descriptive_summary": "descriptive_summary.json",
        }
        if not isinstance(outputs, dict) or set(outputs) != set(expected):
            raise ValueError("M14 result bundle output inventory is invalid")
        for contract_type, filename in expected.items():
            record = outputs[contract_type]
            if not isinstance(record, dict) or set(record) != {"file", "sha256"}:
                raise ValueError("M14 result bundle output record is invalid")
            if record["file"] != filename or not isinstance(record["sha256"], str) or not _HASH.fullmatch(record["sha256"]):
                raise ValueError("M14 result bundle output hash is invalid")
            sibling = Path(path).parent / filename
            if sibling.is_symlink() or not sibling.is_file() or checksum(sibling) != record["sha256"]:
                raise ValueError("M14 result bundle does not bind its sibling output")
            sibling_type = artifact_type_for_output(filename)
            validate_output_file(sibling, sibling_type)
        observation_doc = _read_output_doc(
            Path(path).parent / "observations.json",
            OBSERVATION_SCHEMA, _OBSERVATION_OUTPUT_KEYS,
        )
        summary_doc = _read_output_doc(
            Path(path).parent / "descriptive_summary.json",
            SUMMARY_SCHEMA, _SUMMARY_OUTPUT_KEYS,
        )
        if (observation_doc["dataset_id"] != doc["dataset_id"]
                or summary_doc["dataset_id"] != doc["dataset_id"]
                or observation_doc["result_state"] != doc["result_state"]
                or summary_doc["result_state"] != doc["result_state"]
                or observation_doc["frame_complete"] != doc["frame_complete"]
                or summary_doc["frame_complete"] != doc["frame_complete"]
                or observation_doc["source_outcomes"] != doc["source_outcomes"]
                or doc["denominator_rules"] != _denominator_rules()
                or doc["claim_boundary"] != _claim_boundary()):
            raise ValueError("M14 result bundle contradicts its outputs or claim boundary")
        _validate_output_source_outcomes(doc["source_outcomes"])
        refs = doc["source_artifacts"]
        _validate_output_artifact_refs(refs, doc["source_outcomes"])
        expected_identity = _cache_identity(
            doc["m14_semantic_input_sha256"],
            doc["m14_provenance_sha256"],
            refs,
        )
        if (doc["stage_registration_sha256"]
                != expected_identity["stage_registration_sha256"]
                or doc["implementation_sha256"]
                != expected_identity["implementation_sha256"]
                or doc["contract_semantics"]
                != expected_identity["contract_semantics"]
                or doc["m14_cache_identity_sha256"]
                != _sha256_json(expected_identity)):
            raise ValueError("M14 result bundle cache identity is inconsistent")
        stage_manifest_path = Path(path).parent / "manifest.json"
        stage_manifest = _read_json_file(stage_manifest_path)
        if (not isinstance(stage_manifest, dict)
                or set(stage_manifest) != {"schema", "status", "identity", "output_sha256"}
                or stage_manifest.get("schema") != "m14-stage-manifest-v1"
                or stage_manifest.get("status") != "complete"):
            raise ValueError("M14 stage manifest is invalid")
        stage_identity = stage_manifest.get("identity")
        if (not isinstance(stage_identity, dict)
                or set(stage_identity) != {
                    "schema", "m14_cache_identity_sha256",
                    "m14_semantic_input_sha256", "m14_provenance_sha256",
                }
                or stage_identity.get("schema") != "m14-stage-identity-v1"
                or stage_identity.get("m14_cache_identity_sha256")
                != doc["m14_cache_identity_sha256"]
                or stage_identity.get("m14_semantic_input_sha256")
                != doc["m14_semantic_input_sha256"]
                or stage_identity.get("m14_provenance_sha256")
                != doc["m14_provenance_sha256"]):
            raise ValueError("M14 stage manifest identity does not match its result bundle")
        inventory = stage_manifest.get("output_sha256")
        if not isinstance(inventory, dict) or set(inventory) != set(OUTPUT_CONTRACTS):
            raise ValueError("M14 stage output inventory is invalid")
        for filename in OUTPUT_CONTRACTS:
            output_path = Path(path).parent / filename
            if (not isinstance(inventory.get(filename), str)
                    or not _HASH.fullmatch(inventory[filename])
                    or output_path.is_symlink() or not output_path.is_file()
                    or checksum(output_path) != inventory[filename]):
                raise ValueError("M14 stage output inventory digest is invalid")
        return {"schema": RESULT_BUNDLE_SCHEMA, "result_state": doc["result_state"]}
    raise ValueError(f"Unknown M14 output contract: {artifact_type!r}")


def artifact_type_for_output(filename):
    for name, artifact_type in OUTPUT_CONTRACTS.items():
        if name == filename:
            return artifact_type
    raise ValueError("Unknown M14 output filename")


def _normalize_manifest_for_result(config):
    normalized = dict(config)
    for key in ("source_artifacts", "source_outcomes", "sampling_units", "evaluated_pairs", "observations"):
        if not isinstance(normalized.get(key), list):
            normalized[key] = []
    return normalized


def _analyze(config, *, verified_outcomes=None, verified_refs=None, source_errors=None):
    manifest = _normalize_manifest_for_result(config)
    source_outcomes = verified_outcomes or []
    verified_refs = verified_refs or []
    source_errors = list(source_errors or [])
    structural_errors = []
    if set(config) != _MANIFEST_KEYS:
        structural_errors.append("INPUT_FIELDS_INVALID")
    if config.get("schema") != INPUT_SCHEMA:
        structural_errors.append("INPUT_SCHEMA_INVALID")
    if not _token(config.get("dataset_id")):
        structural_errors.append("DATASET_ID_INVALID")
    if config.get("analysis_profile") is not None:
        structural_errors.append("ANALYSIS_PROFILE_UNSUPPORTED")
    for key in ("source_artifacts", "source_outcomes", "sampling_units", "evaluated_pairs", "observations"):
        if not isinstance(config.get(key), list):
            structural_errors.append(f"{key.upper()}_INVALID")
    verified_ids = {ref["artifact_id"] for ref in verified_refs}
    declared_ids = {
        row.get("artifact_id") for row in manifest.get("source_artifacts", [])
        if isinstance(row, dict) and isinstance(row.get("artifact_id"), str)
    }
    # Optional-source metadata errors are findings, not caller-frame failures.
    # The only source-list error that invalidates the required manifest is an
    # omitted source family; malformed source rows stay isolated as INVALID.
    fatal_source_errors = [
        code for code in source_errors if code == "SOURCE_KIND_MISSING"
    ]
    structural_errors.extend(fatal_source_errors)
    units, invalid_units = _validate_unit_rows(
        manifest, verified_ids, declared_ids, structural_errors
    )
    for unit_id, row in units.items():
        for parent in row.get("parent_unit_ids", []) if isinstance(row, dict) else []:
            if parent == unit_id:
                structural_errors.append("UNIT_PARENT_CYCLE")
    _, frame = _validate_pairs(manifest, units, structural_errors)
    accepted, rejected, observed_frame, duplicate_rows = _validate_observations(
        manifest, frame, units, invalid_units, verified_ids, declared_ids,
        structural_errors
    )
    if duplicate_rows:
        structural_errors.append("DUPLICATE_OBSERVATION_IDENTITY")
    # Keep source-specific problems from invalidating an otherwise independent
    # caller frame. Row references to a rejected artifact are checked above.
    state, frame_complete = _frame_result(
        manifest, accepted, rejected, frame, observed_frame, structural_errors
    )
    findings = sorted(set(source_errors + structural_errors))
    normalized_rows = sorted(
        accepted,
        key=lambda row: (
            _null_first(units[row["unit_id"]].get("study_id")),
            units[row["unit_id"]].get("unit_type", ""),
            row["unit_id"], row["candidate_id"], row["helper_id"], row["observation_id"],
        ),
    )
    missing = sorted(frame - observed_frame)
    observation_table = {
        "schema": OBSERVATION_SCHEMA,
        "dataset_id": config.get("dataset_id"),
        "semantic_version": SEMANTIC_VERSION,
        "result_state": state,
        "frame_complete": frame_complete,
        "observations": normalized_rows,
        "rejected_observations": sorted(
            rejected,
            key=lambda row: (
                row.get("observation_id") is not None,
                str(row.get("observation_id") or ""),
                tuple(row.get("reason_codes", [])),
            ),
        ),
        "missing_pair_units": [
            {"candidate_id": candidate, "helper_id": helper, "unit_id": unit_id}
            for candidate, helper, unit_id in missing
        ],
        "source_outcomes": source_outcomes,
        "validation_findings": _result_error_rows(findings),
    }
    summary = _summary(
        normalized_rows, units, config.get("dataset_id"), frame_complete, state, frame
    )
    return state, frame_complete, observation_table, summary, findings, units, accepted, rejected


def _write_json(path, value):
    Path(path).write_bytes(_canonical_json_bytes(value, trailing_newline=True))


def _build_result_bundle(
    config, state, frame_complete, source_outcomes, verified_refs, findings,
    observation_path, summary_path,
):
    normalized = _normalize_manifest_for_result(config)
    semantic_projection = _semantic_projection(normalized, source_outcomes, verified_refs)
    provenance_projection = _provenance_projection(
        normalized, source_outcomes, verified_refs, findings
    )
    semantic_sha = _sha256_json(semantic_projection)
    provenance_sha = _sha256_json(provenance_projection)
    identity = _cache_identity(semantic_sha, provenance_sha, verified_refs)
    cache_sha = _sha256_json(identity)
    contract_semantics = identity["contract_semantics"]
    return {
        "schema": RESULT_BUNDLE_SCHEMA,
        "dataset_id": config.get("dataset_id"),
        "input_schema": config.get("schema"),
        "semantic_version": SEMANTIC_VERSION,
        "result_state": state,
        "frame_complete": frame_complete,
        "source_outcomes": source_outcomes,
        "source_artifacts": verified_refs,
        "validation_findings": _result_error_rows(findings),
        "m14_semantic_input_sha256": semantic_sha,
        "m14_provenance_sha256": provenance_sha,
        "m14_cache_identity_sha256": cache_sha,
        "stage_registration_sha256": identity["stage_registration_sha256"],
        "implementation_sha256": identity["implementation_sha256"],
        "contract_semantics": contract_semantics,
        "outputs": {
            "m14_observation_table": {
                "file": "observations.json", "sha256": checksum(observation_path),
            },
            "m14_descriptive_summary": {
                "file": "descriptive_summary.json", "sha256": checksum(summary_path),
            },
        },
        "denominator_rules": _denominator_rules(),
        "claim_boundary": _claim_boundary(),
    }, semantic_sha, provenance_sha, cache_sha


def run_stage(inputs, output, config):
    """Execute M14 offline and write the three checksum-bound artifacts."""
    if inputs:
        raise ValueError("M14 does not accept generic workflow input artifacts")
    config = validate_config(config)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("M14 output directory must be empty before execution")

    source_outcomes, verified_refs, verified_paths, source_errors = _resolve_source_outcomes(config)
    state, frame_complete, observation_table, summary, findings, _, _, _ = _analyze(
        config,
        verified_outcomes=source_outcomes,
        verified_refs=verified_refs,
        source_errors=source_errors,
    )
    observation_path = output / "observations.json"
    summary_path = output / "descriptive_summary.json"
    bundle_path = output / "result_bundle.json"
    stage_manifest_path = output / "manifest.json"
    try:
        _write_json(observation_path, observation_table)
        _write_json(summary_path, summary)
        bundle, _, _, cache_sha = _build_result_bundle(
            config, state, frame_complete, source_outcomes, verified_refs,
            findings, observation_path, summary_path,
        )
        _write_json(bundle_path, bundle)
        output_hashes = {
            filename: checksum(output / filename)
            for filename in sorted(OUTPUT_CONTRACTS)
        }
        stage_manifest = {
            "schema": "m14-stage-manifest-v1",
            "status": "complete",
            "identity": {
                "schema": "m14-stage-identity-v1",
                "m14_cache_identity_sha256": cache_sha,
                "m14_semantic_input_sha256": bundle["m14_semantic_input_sha256"],
                "m14_provenance_sha256": bundle["m14_provenance_sha256"],
            },
            "output_sha256": output_hashes,
        }
        _write_json(stage_manifest_path, stage_manifest)
        for filename, artifact_type in OUTPUT_CONTRACTS.items():
            artifact_contracts.validate_artifact(output / filename, artifact_type)
        return stage_manifest
    except BaseException:
        # Never leave a result bundle that could be mistaken for a committed run.
        for path in (bundle_path, stage_manifest_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


def _cache_implementation_identity():
    return {
        "identity_schema": "m14-cache-implementation-v1",
        "stage": STAGE_KIND,
        "stage_version": STAGE_VERSION,
        "implementation_sha256": _implementation_sha256(),
        "contract_types": sorted(OUTPUT_CONTRACTS.values()),
        "contract_semantics": artifact_contracts.semantic_identity(
            sorted(OUTPUT_CONTRACTS.values())
        ),
    }


run_stage.cache_implementation_identity = _cache_implementation_identity