"""Frozen M13 synthetic/offline input and artifact contracts.

M13 preserves caller-scoped M5 observations. It does not classify candidates,
combine callers, or infer biological absence or function.
"""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from . import m12_contracts


INPUT_SCHEMA = "m13-input-v1"
EVENT_INDEX_SCHEMA = "m13-event-index-v1"
HYPOTHESIS_MATRIX_SCHEMA = "m13-hypothesis-matrix-v1"
SUMMARY_SCHEMA = "m13-summary-v1"
RESULT_BUNDLE_SCHEMA = "m13-result-bundle-v1"
SEMANTIC_VERSION = "1"
OUTPUT_CONTRACT_VERSION = "2"

M5_ARTIFACT_TYPES = frozenset({
    "dvg_parameters",
    "dvg_evidence_summary",
    "dvg_evidence",
    "dvg_raw_output",
})
REQUIRED_COMPLETED_TYPES = frozenset({
    "dvg_parameters",
    "dvg_evidence_summary",
    "dvg_evidence",
})
ARTIFACT_STATE_KEYS = tuple(sorted(M5_ARTIFACT_TYPES))
ARTIFACT_STATES = frozenset({
    "PRESENT",
    "NOT_PRODUCED",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
    "UNKNOWN",
})
RUN_IMPORT_STATES = frozenset({
    "IMPORTED_WITH_EVENTS",
    "IMPORTED_COMPLETED_ZERO",
    "IMPORTED_NONCOMPLETED",
    "NOT_SUPPLIED",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
    "INVALID",
    "INCOMPLETE",
    "INTERRUPTED",
})
EVIDENCE_STATES = frozenset({
    "OBSERVED",
    "CONFLICTING",
    "UNRESOLVED",
    "NOT_ASSESSED",
})
HYPOTHESIS_SCOPES = frozenset({
    "STRUCTURAL_OBSERVATION",
    "BIOLOGICAL_IDENTITY",
    "FUNCTION_OR_INTERFERENCE",
    "SOURCE_ORIGIN",
    "OTHER",
})
M1_STAGE_STATES = frozenset({
    "pending",
    "running",
    "complete",
    "skipped",
    "dependency_missing",
    "external_module_required",
    "failed",
    "interrupted",
})
M5_EVIDENCE_STATUSES = frozenset({
    "DVG_EVIDENCE_DETECTED",
    "NO_DVG_EVIDENCE_DETECTED",
    "NOT_EVALUATED",
    "ANALYSIS_UNAVAILABLE",
    "ANALYSIS_FAILED",
    "INVALID_RESULT",
})
EXECUTION_OUTCOME_CODES = frozenset({
    "COMPLETED_EVENTS",
    "COMPLETED_ZERO",
    "NOT_STARTED",
    "UNAVAILABLE",
    "FAILED",
    "INTERRUPTED",
    "INCOMPLETE_OUTPUT",
    "INVALID_OUTPUT",
})

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_TEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]+$")
_RUN_REQUIRED_FIELDS = frozenset({
    "producer_stage_id",
    "producer_run_manifest_sha256",
    "producer_status",
    "artifacts",
    "artifact_states",
})
_RUN_OPTIONAL_FIELDS = frozenset({
    "producer_workflow_ref",
    "execution_record_ref",
})
_WORKFLOW_REF_FIELDS = frozenset({"path", "sha256", "workflow_id"})
_EXECUTION_REF_FIELDS = frozenset({"path", "sha256", "schema"})
_HYPOTHESIS_FIELDS = frozenset({
    "hypothesis_id",
    "label",
    "scope",
    "provenance_ref",
})


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON value is not allowed: {value}")


def read_json(path, *, max_bytes=32_000_000):
    path = Path(path)
    info = path.lstat()
    if path.is_symlink() or not path.is_file():
        raise ValueError("M13 JSON must be a regular non-symlink file")
    if info.st_size > max_bytes:
        raise ValueError("M13 JSON exceeds the 32 MB contract limit")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("M13 JSON must not contain a UTF-8 BOM")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("M13 JSON is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError("M13 JSON document must be an object")
    return value


def canonical_json_bytes(value):
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("M13 output is not finite JSON data") from error
    return (text + "\n").encode("utf-8")


def write_json(path, value):
    payload = canonical_json_bytes(value)
    Path(path).write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _exact_fields(value, required, optional=(), label="object"):
    required = set(required)
    optional = set(optional)
    if (not isinstance(value, dict)
            or not required <= set(value)
            or set(value) - required - optional):
        raise ValueError(f"{label} must contain exactly its declared fields")


def _text(value, label, *, maximum=512):
    if (not isinstance(value, str) or not value or len(value) > maximum
            or not _TEXT_RE.fullmatch(value)):
        raise ValueError(f"{label} must be non-empty bounded text")
    return value


def _hash(value, label, *, optional=False):
    if optional and value is None:
        return None
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _relative_path(value, label):
    if (not isinstance(value, str) or not value or "\\" in value
            or value.startswith("/") or re.match(r"^[A-Za-z]:", value)):
        raise ValueError(f"{label} must be a normalized relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} must not contain path traversal")
    if PurePosixPath(value).as_posix() != value:
        raise ValueError(f"{label} must be normalized")
    return value


def artifact_input_name(run_index, artifact_type):
    """Stable dynamic-input key for one declared M5 ArtifactRef."""
    if (not isinstance(run_index, int) or isinstance(run_index, bool)
            or run_index < 0 or artifact_type not in M5_ARTIFACT_TYPES):
        raise ValueError("M13 artifact input identity is invalid")
    return f"m5_{run_index:04d}_{artifact_type}"


def validate_workflow_ref(value):
    _exact_fields(value, _WORKFLOW_REF_FIELDS, label="producer_workflow_ref")
    _relative_path(value["path"], "producer_workflow_ref.path")
    _hash(value["sha256"], "producer_workflow_ref.sha256")
    _text(value["workflow_id"], "producer_workflow_ref.workflow_id", maximum=256)
    return value


def validate_execution_record_ref(value):
    _exact_fields(value, _EXECUTION_REF_FIELDS, label="execution_record_ref")
    _relative_path(value["path"], "execution_record_ref.path")
    _hash(value["sha256"], "execution_record_ref.sha256")
    if value["schema"] != "m5-execution-outcome-v1":
        raise ValueError("execution_record_ref schema is unsupported")
    return value


def validate_hypothesis(value):
    _exact_fields(value, _HYPOTHESIS_FIELDS, label="M13 hypothesis")
    _text(value["hypothesis_id"], "hypothesis_id", maximum=128)
    _text(value["label"], "hypothesis label", maximum=512)
    if value["scope"] not in HYPOTHESIS_SCOPES:
        raise ValueError("M13 hypothesis scope is unsupported")
    _text(value["provenance_ref"], "hypothesis provenance_ref", maximum=2048)
    return value


def validate_m5_run_ref(value):
    _exact_fields(
        value,
        _RUN_REQUIRED_FIELDS,
        _RUN_OPTIONAL_FIELDS,
        "M5RunRef",
    )
    _text(value["producer_stage_id"], "producer_stage_id", maximum=128)
    if not m12_contracts.STAGE_ID_RE.fullmatch(value["producer_stage_id"]):
        raise ValueError("producer_stage_id is not a safe stage identifier")
    producer_status = value["producer_status"]
    if producer_status not in M1_STAGE_STATES:
        raise ValueError("producer_status is not an M1 stage lifecycle state")
    run_digest = _hash(
        value["producer_run_manifest_sha256"],
        "producer_run_manifest_sha256",
        optional=producer_status != "complete",
    )

    artifacts = value["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) > len(M5_ARTIFACT_TYPES):
        raise ValueError("M5RunRef.artifacts must be a bounded array")
    states = value["artifact_states"]
    _exact_fields(states, ARTIFACT_STATE_KEYS, label="M5RunRef.artifact_states")
    if any(state not in ARTIFACT_STATES for state in states.values()):
        raise ValueError("M5RunRef contains an unsupported artifact state")

    seen_types = set()
    seen_ref_identities = set()
    for ref in artifacts:
        m12_contracts.validate_artifact_ref(ref)
        artifact_type = ref["artifact_type"]
        if artifact_type not in M5_ARTIFACT_TYPES:
            raise ValueError("M13 accepts only the frozen M5 ViReMa artifact types")
        if artifact_type in seen_types:
            raise ValueError("M5RunRef contains a duplicate artifact type")
        seen_types.add(artifact_type)
        if ref["producer_milestone"] != "M5":
            raise ValueError("M13 ArtifactRef producer must be M5")
        if (ref["producer_stage_id"] != value["producer_stage_id"]
                or ref["producer_status"] != producer_status):
            raise ValueError("M13 ArtifactRef producer identity does not match its run")
        if run_digest is None or ref["producer_run_manifest_sha256"] != run_digest:
            raise ValueError("M13 ArtifactRef run-manifest digest does not match its run")
        identity = (
            ref["producer_run_manifest_sha256"],
            ref["artifact_type"],
            ref["sha256"],
        )
        if identity in seen_ref_identities:
            raise ValueError("M5RunRef contains a duplicate ArtifactRef identity")
        seen_ref_identities.add(identity)
        if states[artifact_type] != "PRESENT":
            raise ValueError("ArtifactRef requires a PRESENT artifact state")

    for artifact_type in M5_ARTIFACT_TYPES:
        count = sum(ref["artifact_type"] == artifact_type for ref in artifacts)
        if (states[artifact_type] == "PRESENT") != (count == 1):
            raise ValueError("Artifact state and ArtifactRef declaration disagree")

    if producer_status == "complete":
        if run_digest is None:
            raise ValueError("Completed M5 runs require an exact run-manifest digest")
        if not REQUIRED_COMPLETED_TYPES <= seen_types:
            raise ValueError("Completed M5 runs require parameters, summary, and evidence")
    else:
        if "producer_workflow_ref" not in value or "execution_record_ref" not in value:
            raise ValueError(
                "Noncompleted M5 runs require explicit workflow and execution-record references"
            )
        validate_workflow_ref(value["producer_workflow_ref"])
        validate_execution_record_ref(value["execution_record_ref"])
        if artifacts and run_digest is None:
            raise ValueError("M5 artifacts require an exact producer run-manifest digest")
    if producer_status == "complete" and (
            "producer_workflow_ref" in value or "execution_record_ref" in value):
        raise ValueError(
            "Completed M5 runs use verified typed artifacts, not execution-outcome references"
        )

    if producer_status == "running" and not (
            "producer_workflow_ref" in value and "execution_record_ref" in value):
        raise ValueError("A nonterminal M5 run requires explicit workflow references")
    return value


def validate_input_manifest(value):
    _exact_fields(
        value,
        {"schema", "candidate_id", "m5_runs", "hypotheses"},
        label="M13 input manifest",
    )
    if value["schema"] != INPUT_SCHEMA:
        raise ValueError("M13 input schema is unsupported")
    _text(value["candidate_id"], "candidate_id", maximum=256)
    runs = value["m5_runs"]
    if not isinstance(runs, list) or not runs or len(runs) > 10_000:
        raise ValueError("m5_runs must contain at least one bounded M5RunRef")
    run_identities = set()
    artifact_identities = set()
    for run in runs:
        validate_m5_run_ref(run)
        digest = run["producer_run_manifest_sha256"]
        identity = (
            run["producer_stage_id"],
            digest if digest is not None else run["execution_record_ref"]["sha256"],
        )
        if identity in run_identities:
            raise ValueError("M13 input contains a duplicate producer run identity")
        run_identities.add(identity)
        for ref in run["artifacts"]:
            ref_identity = (
                ref["producer_run_manifest_sha256"],
                ref["artifact_type"],
                ref["sha256"],
            )
            if ref_identity in artifact_identities:
                raise ValueError("M13 input contains a duplicate ArtifactRef identity")
            artifact_identities.add(ref_identity)

    hypotheses = value["hypotheses"]
    if not isinstance(hypotheses, list) or len(hypotheses) > 10_000:
        raise ValueError("hypotheses must be a bounded array")
    hypothesis_ids = set()
    for hypothesis in hypotheses:
        validate_hypothesis(hypothesis)
        if hypothesis["hypothesis_id"] in hypothesis_ids:
            raise ValueError("M13 input contains a duplicate hypothesis_id")
        hypothesis_ids.add(hypothesis["hypothesis_id"])
    return value


def load_input_manifest(path):
    return validate_input_manifest(read_json(path))


def validate_input_manifest_file(path):
    value = load_input_manifest(path)
    return {
        "schema": value["schema"],
        "run_count": len(value["m5_runs"]),
        "hypothesis_count": len(value["hypotheses"]),
    }


def _validate_m5_run_identity(value, *, allow_none=False):
    _exact_fields(
        value,
        {"producer_stage_id", "producer_run_manifest_sha256", "dvg_evidence_sha256"},
        label="M13 event run reference",
    )
    _text(value["producer_stage_id"], "producer_stage_id", maximum=128)
    _hash(
        value["producer_run_manifest_sha256"],
        "producer_run_manifest_sha256",
        optional=allow_none,
    )
    _hash(value["dvg_evidence_sha256"], "dvg_evidence_sha256")


def _validate_event_reference(value):
    _exact_fields(
        value,
        {
            "producer_stage_id",
            "producer_run_manifest_sha256",
            "dvg_evidence_sha256",
            "source_row_index",
        },
        label="M13 event reference",
    )
    _text(value["producer_stage_id"], "producer_stage_id", maximum=128)
    _hash(value["producer_run_manifest_sha256"], "producer_run_manifest_sha256")
    _hash(value["dvg_evidence_sha256"], "dvg_evidence_sha256")
    index = value["source_row_index"]
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise ValueError("source_row_index must be a non-negative integer")


def validate_event_index(value):
    _exact_fields(
        value,
        {"schema", "candidate_id", "events"},
        label="M13 event index",
    )
    if value["schema"] != EVENT_INDEX_SCHEMA:
        raise ValueError("M13 event-index schema is unsupported")
    _text(value["candidate_id"], "candidate_id", maximum=256)
    rows = value["events"]
    if not isinstance(rows, list):
        raise ValueError("M13 event index events must be an array")
    identities = set()
    for row in rows:
        _exact_fields(
            row,
            {
                "candidate_id",
                "m5_run_ref",
                "caller",
                "caller_version",
                "reference_sha256",
                "source_row_index",
                "source_event",
            },
            {"source_event_id"},
            "M13 event-index row",
        )
        if row["candidate_id"] != value["candidate_id"]:
            raise ValueError("M13 event row candidate_id does not match its index")
        _validate_m5_run_identity(row["m5_run_ref"])
        _text(row["caller"], "caller", maximum=128)
        _text(row["caller_version"], "caller_version", maximum=128)
        _hash(row["reference_sha256"], "reference_sha256")
        index = row["source_row_index"]
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError("source_row_index must be a non-negative integer")
        if not isinstance(row["source_event"], dict):
            raise ValueError("source_event must preserve the source M5 event object")
        if "source_event_id" in row and (
                not isinstance(row["source_event_id"], str)
                or not row["source_event_id"]):
            raise ValueError("source_event_id must be non-empty text when supplied")
        identity = (
            row["m5_run_ref"]["producer_run_manifest_sha256"],
            row["m5_run_ref"]["dvg_evidence_sha256"],
            index,
        )
        if identity in identities:
            raise ValueError("M13 event index contains a duplicate source-row identity")
        identities.add(identity)


def validate_hypothesis_matrix(value):
    _exact_fields(
        value,
        {"schema", "candidate_id", "hypotheses"},
        label="M13 hypothesis matrix",
    )
    if value["schema"] != HYPOTHESIS_MATRIX_SCHEMA:
        raise ValueError("M13 hypothesis-matrix schema is unsupported")
    _text(value["candidate_id"], "candidate_id", maximum=256)
    rows = value["hypotheses"]
    if not isinstance(rows, list):
        raise ValueError("M13 hypothesis matrix hypotheses must be an array")
    seen = set()
    for row in rows:
        _exact_fields(
            row,
            {
                "hypothesis_id",
                "label",
                "scope",
                "provenance_ref",
                "evidence_refs",
                "evidence_state",
                "reason",
            },
            label="M13 hypothesis-matrix row",
        )
        validate_hypothesis({
            key: row[key]
            for key in ("hypothesis_id", "label", "scope", "provenance_ref")
        })
        if row["hypothesis_id"] in seen:
            raise ValueError("M13 hypothesis matrix contains a duplicate hypothesis")
        seen.add(row["hypothesis_id"])
        refs = row["evidence_refs"]
        if not isinstance(refs, list):
            raise ValueError("evidence_refs must be an array")
        ref_keys = set()
        for ref in refs:
            _validate_event_reference(ref)
            key = (
                ref["producer_run_manifest_sha256"],
                ref["dvg_evidence_sha256"],
                ref["source_row_index"],
            )
            if key in ref_keys:
                raise ValueError("M13 hypothesis matrix contains a duplicate evidence reference")
            ref_keys.add(key)
        if row["evidence_state"] not in EVIDENCE_STATES:
            raise ValueError("M13 hypothesis evidence_state is unsupported")
        _text(row["reason"], "hypothesis reason", maximum=1024)
        if row["evidence_state"] == "OBSERVED":
            if row["scope"] != "STRUCTURAL_OBSERVATION" or not refs:
                raise ValueError(
                    "OBSERVED requires cited M5 events for a structural observation"
                )
        elif refs:
            raise ValueError(
                "Only directly supported structural observations may cite M5 events"
            )


def validate_summary(value):
    _exact_fields(
        value,
        {
            "schema",
            "candidate_id",
            "summary_completeness",
            "run_count",
            "event_count",
            "runs",
            "limitations",
        },
        label="M13 summary",
    )
    if value["schema"] != SUMMARY_SCHEMA:
        raise ValueError("M13 summary schema is unsupported")
    _text(value["candidate_id"], "candidate_id", maximum=256)
    if value["summary_completeness"] not in {"COMPLETE", "PARTIAL"}:
        raise ValueError("M13 summary completeness is unsupported")
    runs = value["runs"]
    if not isinstance(runs, list) or len(runs) != value["run_count"]:
        raise ValueError("M13 summary run_count does not match runs")
    if not isinstance(value["run_count"], int) or isinstance(value["run_count"], bool):
        raise ValueError("M13 summary run_count must be an integer")
    if (not isinstance(value["event_count"], int)
            or isinstance(value["event_count"], bool) or value["event_count"] < 0):
        raise ValueError("M13 summary event_count must be a non-negative integer")
    if not isinstance(value["limitations"], list) or not value["limitations"]:
        raise ValueError("M13 summary must retain its scientific limitations")
    for limitation in value["limitations"]:
        _text(limitation, "M13 limitation", maximum=1024)
    identities = set()
    total_events = 0
    complete_states = {"IMPORTED_WITH_EVENTS", "IMPORTED_COMPLETED_ZERO"}
    for row in runs:
        _exact_fields(
            row,
            {
                "producer_stage_id",
                "producer_run_manifest_sha256",
                "producer_workflow_ref",
                "execution_record_ref",
                "producer_status_raw",
                "producer_execution_status_raw",
                "declared_producer_execution_status",
                "outcome_code",
                "failure_code",
                "run_import_state",
                "artifact_states",
                "artifact_refs",
                "caller",
                "caller_version",
                "reference_sha256",
                "event_count",
                "reason_code",
            },
            label="M13 run summary",
        )
        _text(row["producer_stage_id"], "producer_stage_id", maximum=128)
        _hash(
            row["producer_run_manifest_sha256"],
            "producer_run_manifest_sha256",
            optional=True,
        )
        if (row["declared_producer_execution_status"] == "complete"
                and row["producer_run_manifest_sha256"] is None):
            raise ValueError("Completed M13 run summaries require a run-manifest digest")
        if (row["producer_workflow_ref"] is None) != (row["execution_record_ref"] is None):
            raise ValueError("M13 run summary execution references are incomplete")
        if row["producer_workflow_ref"] is not None:
            validate_workflow_ref(row["producer_workflow_ref"])
            validate_execution_record_ref(row["execution_record_ref"])
        if row["caller"] is not None:
            _text(row["caller"], "caller", maximum=128)
        if row["caller_version"] is not None:
            _text(row["caller_version"], "caller_version", maximum=128)
        _hash(row["reference_sha256"], "reference_sha256", optional=True)
        if row["producer_status_raw"] is not None:
            _text(row["producer_status_raw"], "producer_status_raw", maximum=128)
            if row["producer_status_raw"] not in M5_EVIDENCE_STATUSES:
                raise ValueError("M13 summary contains an unsupported raw M5 status")
        if row["producer_execution_status_raw"] is not None:
            if row["producer_execution_status_raw"] not in M1_STAGE_STATES:
                raise ValueError("M13 summary contains an unsupported raw M1 state")
        if row["declared_producer_execution_status"] not in M1_STAGE_STATES:
            raise ValueError("M13 summary declared M1 state is unsupported")
        if row["outcome_code"] is not None:
            _text(row["outcome_code"], "outcome_code", maximum=64)
            if row["outcome_code"] not in EXECUTION_OUTCOME_CODES:
                raise ValueError("M13 summary contains an unsupported outcome code")
        if row["failure_code"] is not None:
            _text(row["failure_code"], "failure_code", maximum=64)
        if row["run_import_state"] not in RUN_IMPORT_STATES:
            raise ValueError("M13 summary contains an unsupported run_import_state")
        _exact_fields(row["artifact_states"], ARTIFACT_STATE_KEYS, label="artifact_states")
        if any(state not in ARTIFACT_STATES for state in row["artifact_states"].values()):
            raise ValueError("M13 summary contains an unsupported artifact state")
        if not isinstance(row["artifact_refs"], list):
            raise ValueError("M13 summary artifact_refs must be an array")
        for ref in row["artifact_refs"]:
            m12_contracts.validate_artifact_ref(ref)
            if ref["artifact_type"] not in M5_ARTIFACT_TYPES:
                raise ValueError("M13 summary contains a non-M5 artifact reference")
        count = row["event_count"]
        if count is not None and (
                not isinstance(count, int) or isinstance(count, bool) or count < 0):
            raise ValueError("M13 per-run event_count must be null or non-negative")
        if row["run_import_state"] == "IMPORTED_WITH_EVENTS":
            if count is None or count == 0 or row["producer_status_raw"] != "DVG_EVIDENCE_DETECTED":
                raise ValueError("M13 imported event state requires validated nonempty events")
        if row["run_import_state"] == "IMPORTED_COMPLETED_ZERO":
            if count != 0 or row["producer_status_raw"] != "NO_DVG_EVIDENCE_DETECTED":
                raise ValueError("M13 completed-zero state requires validated empty evidence")
        if count is not None:
            total_events += count
        identity = (
            row["producer_stage_id"],
            row["producer_run_manifest_sha256"] or (
                row["execution_record_ref"]["sha256"]
                if row["execution_record_ref"] is not None
                else row["reason_code"]
            ),
        )
        if identity in identities:
            raise ValueError("M13 summary contains a duplicate producer run")
        identities.add(identity)
        _text(row["reason_code"], "reason_code", maximum=128)
    if total_events != value["event_count"]:
        raise ValueError("M13 summary event_count does not match per-run counts")
    expected_completeness = (
        "COMPLETE"
        if all(row["run_import_state"] in complete_states for row in runs)
        else "PARTIAL"
    )
    if value["summary_completeness"] != expected_completeness:
        raise ValueError("M13 summary completeness does not match per-run import states")


def validate_result_bundle(value):
    _exact_fields(
        value,
        {
            "schema",
            "input_schema",
            "semantic_version",
            "candidate_id",
            "input_manifest_sha256",
            "stage_cache_context_sha256",
            "implementation",
            "producer_runs",
            "outputs",
            "limitations",
        },
        label="M13 result bundle",
    )
    if value["schema"] != RESULT_BUNDLE_SCHEMA or value["input_schema"] != INPUT_SCHEMA:
        raise ValueError("M13 result-bundle schema is unsupported")
    if value["semantic_version"] != SEMANTIC_VERSION:
        raise ValueError("M13 result-bundle semantic version is unsupported")
    _text(value["candidate_id"], "candidate_id", maximum=256)
    _hash(value["input_manifest_sha256"], "input_manifest_sha256")
    _hash(value["stage_cache_context_sha256"], "stage_cache_context_sha256")
    implementation = value["implementation"]
    _exact_fields(
        implementation,
        {"semantic_version", "source_sha256"},
        label="M13 implementation identity",
    )
    if implementation["semantic_version"] != SEMANTIC_VERSION:
        raise ValueError("M13 implementation semantic version is unsupported")
    _hash(implementation["source_sha256"], "implementation source_sha256")
    if not isinstance(value["producer_runs"], list):
        raise ValueError("M13 result bundle producer_runs must be an array")
    for row in value["producer_runs"]:
        _exact_fields(
            row,
            {
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
            },
            label="M13 result-bundle producer run",
        )
        _text(row["producer_stage_id"], "producer_stage_id", maximum=128)
        _hash(row["producer_run_manifest_sha256"], "producer_run_manifest_sha256", optional=True)
        if row["producer_execution_status_raw"] == "complete" and (
                row["producer_run_manifest_sha256"] is None):
            raise ValueError("Completed producer runs require a run-manifest digest")
        if row["producer_status_raw"] is not None:
            _text(row["producer_status_raw"], "producer_status_raw", maximum=128)
            if row["producer_status_raw"] not in M5_EVIDENCE_STATUSES:
                raise ValueError("M13 result bundle contains an unsupported raw M5 status")
        if row["producer_execution_status_raw"] is not None:
            if row["producer_execution_status_raw"] not in M1_STAGE_STATES:
                raise ValueError("M13 result bundle contains an unsupported M1 state")
        if row["outcome_code"] is not None:
            _text(row["outcome_code"], "outcome_code", maximum=64)
            if row["outcome_code"] not in EXECUTION_OUTCOME_CODES:
                raise ValueError("M13 result bundle contains an unsupported outcome code")
        if row["failure_code"] is not None:
            _text(row["failure_code"], "failure_code", maximum=64)
        if row["run_import_state"] not in RUN_IMPORT_STATES:
            raise ValueError("M13 result bundle contains an unsupported run_import_state")
        if not isinstance(row["artifact_refs"], list):
            raise ValueError("M13 result-bundle artifact_refs must be an array")
        seen_artifacts = set()
        for artifact_ref in row["artifact_refs"]:
            m12_contracts.validate_artifact_ref(artifact_ref)
            if artifact_ref["artifact_type"] not in M5_ARTIFACT_TYPES:
                raise ValueError("M13 result bundle contains a non-M5 artifact")
            if artifact_ref["producer_stage_id"] != row["producer_stage_id"]:
                raise ValueError("M13 result-bundle artifact stage identity is inconsistent")
            if artifact_ref["producer_run_manifest_sha256"] != row[
                    "producer_run_manifest_sha256"]:
                raise ValueError("M13 result-bundle artifact digest is inconsistent")
            if artifact_ref["artifact_type"] in seen_artifacts:
                raise ValueError("M13 result-bundle producer has duplicate artifact types")
            seen_artifacts.add(artifact_ref["artifact_type"])
        if (row["producer_workflow_ref"] is None) != (row["execution_record_ref"] is None):
            raise ValueError("M13 result-bundle execution references are incomplete")
        if row["producer_workflow_ref"] is not None:
            validate_workflow_ref(row["producer_workflow_ref"])
            validate_execution_record_ref(row["execution_record_ref"])
    expected_outputs = {
        "m13_event_index",
        "m13_hypothesis_matrix",
        "m13_summary",
    }
    if not isinstance(value["outputs"], dict) or set(value["outputs"]) != expected_outputs:
        raise ValueError("M13 result bundle output inventory is incomplete")
    for artifact_type, row in value["outputs"].items():
        _exact_fields(
            row,
            {"artifact_type", "artifact_contract_version", "sha256"},
            label=f"M13 {artifact_type} output reference",
        )
        if row["artifact_type"] != artifact_type:
            raise ValueError("M13 result-bundle output type does not match its key")
        if row["artifact_contract_version"] != OUTPUT_CONTRACT_VERSION:
            raise ValueError("M13 result-bundle output contract version is unsupported")
        _hash(row["sha256"], f"{artifact_type}.sha256")
    if not isinstance(value["limitations"], list) or not value["limitations"]:
        raise ValueError("M13 result bundle must retain its scientific limitations")
    for limitation in value["limitations"]:
        _text(limitation, "M13 limitation", maximum=1024)


def validate_output_file(path, artifact_type):
    value = read_json(path)
    validators = {
        "m13_event_index": validate_event_index,
        "m13_hypothesis_matrix": validate_hypothesis_matrix,
        "m13_summary": validate_summary,
        "m13_result_bundle": validate_result_bundle,
    }
    validator = validators.get(artifact_type)
    if validator is None:
        raise ValueError(f"No M13 output validator is registered for {artifact_type!r}")
    validator(value)
    if artifact_type == "m13_event_index":
        count = len(value["events"])
    elif artifact_type == "m13_hypothesis_matrix":
        count = len(value["hypotheses"])
    elif artifact_type == "m13_summary":
        count = value["run_count"]
    else:
        count = len(value["producer_runs"])
    return {"schema": value["schema"], "record_count": count}