"""Frozen input and output contracts for the artifact-bounded M12 review."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import re


INPUT_SCHEMA = "m12-input-v1"
REVIEW_TABLE_SCHEMA = "m12-artifact-review-table-v1"
SUMMARY_SCHEMA = "m12-summary-v1"
RESULT_BUNDLE_SCHEMA = "m12-result-bundle-v1"
SEMANTIC_VERSION = "1"
OUTPUT_CONTRACT_VERSION = "1"

PRODUCER_TYPES = {
    "M5": frozenset({
        "dvg_raw_output",
        "dvg_evidence",
        "dvg_evidence_summary",
        "dvg_parameters",
    }),
    "M6": frozenset({
        "residual_read_manifest",
        "read_triage_table",
        "read_alignment_sam",
        "read_support_evidence",
        "read_support_table",
        "reconstruction_evidence",
        "m8_candidate_sequence_set",
    }),
}
TYPE_MILESTONE = {
    artifact_type: milestone
    for milestone, artifact_types in PRODUCER_TYPES.items()
    for artifact_type in artifact_types
}

EXTERNAL_EVIDENCE_STATES = frozenset({
    "PRESENT_NOT_CONSUMED",
    "NOT_SUPPLIED",
    "NOT_AUTHORIZED",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
    "UNKNOWN",
})
EXTERNAL_EVIDENCE_KEYS = (
    "source_reads",
    "controls",
    "sample_metadata",
    "independent_evidence",
)

REVIEW_STATES = frozenset({
    "VERIFIED",
    "NOT_EVALUATED",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
    "INVALID",
    "INCOMPLETE",
    "FAILED",
    "INTERRUPTED",
})
EXECUTION_STATES = frozenset({
    "COMPLETED",
    "NOT_STARTED",
    "DEPENDENCY_UNAVAILABLE",
    "FAILED",
    "INTERRUPTED",
    "UNKNOWN",
    "NOT_APPLICABLE",
})
ACCOUNTING_STATES = frozenset({
    "COMPLETE",
    "INCOMPLETE",
    "TRUNCATED",
    "INVALID",
    "UNKNOWN",
    "NOT_APPLICABLE",
})
OBSERVATION_STATES = frozenset({
    "OBSERVATION_REPORTED",
    "NO_SIGNAL_WITHIN_SCOPE",
    "NO_OBSERVATION",
    "UNKNOWN",
    "NOT_APPLICABLE",
})
COMPLETENESS_STATES = frozenset({
    "COMPLETE_WITHIN_SUPPLIED_ARTIFACT_SCOPE",
    "PARTIAL",
    "NOT_EVALUATED",
    "INVALID",
})

ARTIFACT_REF_FIELDS = frozenset({
    "producer_milestone",
    "producer_stage_id",
    "producer_run_manifest_sha256",
    "producer_status",
    "artifact_type",
    "relative_path",
    "sha256",
    "artifact_contract_version",
})
REVIEW_RECORD_FIELDS = frozenset({
    "candidate_id",
    "artifact_ref",
    "review_state",
    "producer_status_raw",
    "scope",
    "analysis_execution_status",
    "accounting_status",
    "observation_status",
    "limitations",
    "dependency_refs",
})
HASH_RE = re.compile(r"^[a-f0-9]{64}$")
STAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ARTIFACT_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")


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
    if path.stat().st_size > max_bytes:
        raise ValueError("M12 JSON input exceeds the size limit")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("M12 JSON must not contain a UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("M12 JSON is not valid UTF-8 JSON") from error


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
        raise ValueError("M12 output is not finite JSON data") from error
    return (text + "\n").encode("utf-8")


def write_json(path, value):
    path = Path(path)
    payload = canonical_json_bytes(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _require_exact_fields(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError(f"{label} must contain exactly the declared fields")


def _require_short_text(value, label, *, maximum=512):
    if (not isinstance(value, str) or not value.strip()
            or len(value) > maximum
            or any(ord(char) < 32 and char not in "\t" for char in value)):
        raise ValueError(f"{label} must be short non-empty text")


def _require_hash(value, label):
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _validate_relative_path(value):
    if (not isinstance(value, str) or not value or "\\" in value
            or value.startswith("/")
            or re.match(r"^[A-Za-z]:", value)):
        raise ValueError("ArtifactRef.relative_path must be a normalized relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("ArtifactRef.relative_path must not contain path traversal")
    path = PurePosixPath(value)
    if path.as_posix() != value:
        raise ValueError("ArtifactRef.relative_path must be normalized")


def validate_artifact_ref(value):
    _require_exact_fields(value, ARTIFACT_REF_FIELDS, "ArtifactRef")
    milestone = value["producer_milestone"]
    artifact_type = value["artifact_type"]
    if milestone not in PRODUCER_TYPES or TYPE_MILESTONE.get(artifact_type) != milestone:
        raise ValueError("ArtifactRef producer milestone and artifact type do not match")
    _require_short_text(value["producer_stage_id"], "producer_stage_id", maximum=128)
    if not STAGE_ID_RE.fullmatch(value["producer_stage_id"]):
        raise ValueError("producer_stage_id is not a safe stage identifier")
    _require_hash(value["producer_run_manifest_sha256"], "producer_run_manifest_sha256")
    _require_short_text(value["producer_status"], "producer_status", maximum=128)
    _validate_relative_path(value["relative_path"])
    _require_hash(value["sha256"], "ArtifactRef.sha256")
    if (not isinstance(value["artifact_contract_version"], str)
            or not ARTIFACT_VERSION_RE.fullmatch(value["artifact_contract_version"])):
        raise ValueError("artifact_contract_version is unsupported")
    return value


def _validate_external_evidence(value):
    _require_exact_fields(value, EXTERNAL_EVIDENCE_KEYS, "external_evidence")
    for name in EXTERNAL_EVIDENCE_KEYS:
        entry = value[name]
        _require_exact_fields(entry, {"state", "note"}, f"external_evidence.{name}")
        if entry["state"] not in EXTERNAL_EVIDENCE_STATES:
            raise ValueError(f"external_evidence.{name}.state is unsupported")
        note = entry["note"]
        if note is not None:
            _require_short_text(note, f"external_evidence.{name}.note", maximum=280)


def validate_input_manifest(value):
    _require_exact_fields(
        value,
        {"schema", "candidate_id", "producer_artifacts", "external_evidence"},
        "M12 input manifest",
    )
    if value["schema"] != INPUT_SCHEMA:
        raise ValueError("M12 input schema is unsupported")
    _require_short_text(value["candidate_id"], "candidate_id", maximum=256)
    refs = value["producer_artifacts"]
    if not isinstance(refs, list):
        raise ValueError("producer_artifacts must be an array")
    identities = set()
    handoffs = set()
    by_run = {}
    for ref in refs:
        validate_artifact_ref(ref)
        identity = (
            ref["producer_run_manifest_sha256"],
            ref["artifact_type"],
            ref["sha256"],
        )
        if identity in identities:
            raise ValueError("Duplicate ArtifactRef identity")
        identities.add(identity)
        handoff = (
            ref["producer_stage_id"],
            ref["relative_path"],
            ref["artifact_type"],
        )
        if handoff in handoffs:
            raise ValueError("Duplicate producer handoff reference")
        handoffs.add(handoff)
        run_key = (
            ref["producer_milestone"],
            ref["producer_stage_id"],
            ref["producer_run_manifest_sha256"],
        )
        by_run.setdefault(run_key, set()).add(ref["artifact_type"])

    for (milestone, stage_id, _), types in by_run.items():
        required = (
            {"dvg_evidence_summary", "dvg_parameters"}
            if milestone == "M5"
            else {"residual_read_manifest"}
        )
        if not required <= types:
            raise ValueError(
                f"{milestone} stage {stage_id!r} is missing required typed artifacts"
            )

    _validate_external_evidence(value["external_evidence"])
    return value


def load_input_manifest(path):
    return validate_input_manifest(read_json(path))


def validate_input_manifest_file(path):
    value = load_input_manifest(path)
    return {"schema": value["schema"], "artifact_count": len(value["producer_artifacts"])}


def _validate_dependency_refs(value):
    if not isinstance(value, list):
        raise ValueError("dependency_refs must be an array")
    identities = set()
    for ref in value:
        _require_exact_fields(ref, {"artifact_ref", "relation", "note"}, "dependency reference")
        validate_artifact_ref(ref["artifact_ref"])
        _require_short_text(ref["relation"], "dependency relation", maximum=96)
        _require_short_text(ref["note"], "dependency note", maximum=280)
        identity = (
            ref["artifact_ref"]["producer_run_manifest_sha256"],
            ref["artifact_ref"]["artifact_type"],
            ref["artifact_ref"]["sha256"],
        )
        if identity in identities:
            raise ValueError("Duplicate dependency reference")
        identities.add(identity)


def validate_review_table(value):
    if not isinstance(value, list):
        raise ValueError("M12 artifact review table must be a JSON array")
    previous_key = None
    seen = set()
    for row in value:
        _require_exact_fields(row, REVIEW_RECORD_FIELDS, "M12 review row")
        _require_short_text(row["candidate_id"], "review candidate_id", maximum=256)
        validate_artifact_ref(row["artifact_ref"])
        for field, allowed in (
            ("review_state", REVIEW_STATES),
            ("analysis_execution_status", EXECUTION_STATES),
            ("accounting_status", ACCOUNTING_STATES),
            ("observation_status", OBSERVATION_STATES),
        ):
            if row[field] not in allowed:
                raise ValueError(f"Unsupported M12 {field}")
        if (not isinstance(row["producer_status_raw"], str)
                or not row["producer_status_raw"].strip()):
            raise ValueError("M12 row must preserve a raw producer status")
        if (
            row["producer_status_raw"] != row["artifact_ref"]["producer_status"]
            and row["review_state"] not in {"INVALID", "UNAVAILABLE"}
        ):
            raise ValueError(
                "A producer status mismatch must remain an invalid or unavailable review row"
            )
        if not isinstance(row["scope"], dict):
            raise ValueError("M12 review scope must be an object")
        if not isinstance(row["limitations"], list) or any(
            not isinstance(item, str) or not item for item in row["limitations"]
        ):
            raise ValueError("M12 limitations must be non-empty strings")
        _validate_dependency_refs(row["dependency_refs"])
        ref = row["artifact_ref"]
        identity = (
            row["candidate_id"],
            ref["producer_milestone"],
            ref["producer_stage_id"],
            ref["artifact_type"],
            ref["sha256"],
        )
        if identity in seen:
            raise ValueError("Duplicate M12 review row")
        seen.add(identity)
        if previous_key is not None and identity < previous_key:
            raise ValueError("M12 review rows are not canonically sorted")
        previous_key = identity
    return {"record_count": len(value)}


def _validate_external_summary(value):
    _validate_external_evidence(value)


def validate_summary(value):
    fields = {
        "schema",
        "candidate_id",
        "external_evidence",
        "artifact_counts",
        "review_completeness",
        "unassessed_dimensions",
        "biological_conclusion",
    }
    _require_exact_fields(value, fields, "M12 summary")
    if value["schema"] != SUMMARY_SCHEMA:
        raise ValueError("M12 summary schema is unsupported")
    _require_short_text(value["candidate_id"], "summary candidate_id", maximum=256)
    _validate_external_summary(value["external_evidence"])
    _require_exact_fields(
        value["artifact_counts"],
        {"by_producer_milestone", "by_review_state"},
        "artifact_counts",
    )
    producers = value["artifact_counts"]["by_producer_milestone"]
    _require_exact_fields(producers, {"M5", "M6"}, "by_producer_milestone")
    for count in producers.values():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("M12 artifact counts must be non-negative integers")
    states = value["artifact_counts"]["by_review_state"]
    _require_exact_fields(states, REVIEW_STATES, "by_review_state")
    for count in states.values():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("M12 review-state counts must be non-negative integers")
    if value["review_completeness"] not in COMPLETENESS_STATES:
        raise ValueError("M12 review completeness is unsupported")
    if not isinstance(value["unassessed_dimensions"], list) or any(
        not isinstance(item, str) or not item for item in value["unassessed_dimensions"]
    ):
        raise ValueError("M12 unassessed dimensions must be descriptive strings")
    if value["biological_conclusion"] != "NONE":
        raise ValueError("M12 biological_conclusion must be NONE")
    return {"record_count": sum(producers.values())}


def validate_result_bundle(value):
    fields = {
        "schema",
        "input_schema",
        "semantic_version",
        "candidate_id",
        "input_manifest_sha256",
        "implementation_source_sha256",
        "resolved_handoffs",
        "external_evidence",
        "outputs",
        "biological_conclusion",
    }
    _require_exact_fields(value, fields, "M12 result bundle")
    if (value["schema"] != RESULT_BUNDLE_SCHEMA
            or value["input_schema"] != INPUT_SCHEMA
            or value["semantic_version"] != SEMANTIC_VERSION):
        raise ValueError("M12 result bundle schema identity is unsupported")
    _require_short_text(value["candidate_id"], "bundle candidate_id", maximum=256)
    _require_hash(value["input_manifest_sha256"], "input_manifest_sha256")
    _require_hash(value["implementation_source_sha256"], "implementation_source_sha256")
    if not isinstance(value["resolved_handoffs"], list):
        raise ValueError("M12 resolved_handoffs must be an array")
    previous = None
    for handoff in value["resolved_handoffs"]:
        _require_exact_fields(handoff, {"artifact_ref", "resolved"}, "resolved handoff")
        artifact = validate_artifact_ref(handoff["artifact_ref"])
        resolved = handoff["resolved"]
        _require_exact_fields(
            resolved,
            {
                "producer_stage_id",
                "producer_run_manifest_sha256",
                "producer_status_raw",
                "artifact_type",
                "artifact_contract_version",
                "sha256",
                "available",
                "identity_matches",
                "identity_errors",
            },
            "resolved handoff identity",
        )
        _require_short_text(resolved["producer_stage_id"], "resolved producer_stage_id", maximum=128)
        if resolved["producer_run_manifest_sha256"] is not None:
            _require_hash(
                resolved["producer_run_manifest_sha256"],
                "resolved producer_run_manifest_sha256",
            )
        if resolved["producer_status_raw"] is not None and not isinstance(
            resolved["producer_status_raw"], str
        ):
            raise ValueError("Resolved producer status must be text or null")
        if resolved["artifact_type"] is not None and not isinstance(
            resolved["artifact_type"], str
        ):
            raise ValueError("Resolved artifact type must be text or null")
        if resolved["artifact_contract_version"] is not None and not isinstance(
            resolved["artifact_contract_version"], str
        ):
            raise ValueError("Resolved artifact contract version must be text or null")
        if resolved["sha256"] is not None:
            _require_hash(resolved["sha256"], "resolved artifact sha256")
        if (not isinstance(resolved["available"], bool)
                or not isinstance(resolved["identity_matches"], bool)
                or not isinstance(resolved["identity_errors"], list)
                or any(not isinstance(item, str) for item in resolved["identity_errors"])):
            raise ValueError("Resolved handoff state is malformed")
        key = (
            artifact["producer_milestone"],
            artifact["producer_stage_id"],
            artifact["artifact_type"],
            artifact["sha256"],
        )
        if previous is not None and key < previous:
            raise ValueError("M12 consumed artifacts are not canonically sorted")
        previous = key
    _validate_external_summary(value["external_evidence"])
    outputs = value["outputs"]
    _require_exact_fields(
        outputs,
        {"m12_artifact_review_table", "m12_summary"},
        "M12 outputs",
    )
    for name, entry in outputs.items():
        _require_exact_fields(
            entry,
            {"artifact_type", "artifact_contract_version", "sha256"},
            f"M12 output {name}",
        )
        if entry["artifact_type"] != name:
            raise ValueError("M12 output type does not match its result key")
        if entry["artifact_contract_version"] != OUTPUT_CONTRACT_VERSION:
            raise ValueError("M12 output contract version is unsupported")
        _require_hash(entry["sha256"], f"{name}.sha256")
    if value["biological_conclusion"] != "NONE":
        raise ValueError("M12 biological_conclusion must be NONE")
    return {"record_count": len(value["resolved_handoffs"])}


def validate_output_file(path, artifact_type):
    value = read_json(path)
    if artifact_type == "m12_artifact_review_table":
        return validate_review_table(value)
    if artifact_type == "m12_summary":
        return validate_summary(value)
    if artifact_type == "m12_result_bundle":
        return validate_result_bundle(value)
    raise ValueError(f"No M12 output validator is registered for {artifact_type!r}")
