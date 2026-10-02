"""Frozen synthetic/offline M15 input and output contracts.

M15 preserves producer artifacts and records only explicitly supported
normalizations. It does not classify, rank, or assign biological meaning.
"""

import hashlib
import json
from pathlib import Path
import re


LEGACY_INPUT_SCHEMA = "m15-input-v1"
INPUT_SCHEMA = "m15-input-v2"
ENVELOPE_SCHEMA = "m15-evidence-envelope-v2"
EDGES_SCHEMA = "m15-dependency-edges-v2"
SUMMARY_SCHEMA = "m15-dossier-summary-v2"
RESULT_BUNDLE_SCHEMA = "m15-result-bundle-v2"
SEMANTIC_VERSION = "2"
OUTPUT_CONTRACT_VERSION = "2"
OUTPUT_SCHEMA_VERSION = "m15-output-schema-v2"
INPUT_SEMANTICS_VERSION = "m15-authenticated-producer-bindings-v2"
AUTHENTICATED_PRODUCER_MODE = "AUTHENTICATED_PRODUCER"
CALLER_SNAPSHOT_MODE = "CALLER_SNAPSHOT"

PRODUCER_TYPES = {
    "M5": frozenset({
        "dvg_raw_output", "dvg_evidence", "dvg_evidence_summary",
        "dvg_parameters",
    }),
    "M6": frozenset({
        "residual_read_manifest", "read_triage_table", "read_alignment_sam",
        "read_support_evidence", "read_support_table",
        "reconstruction_evidence", "m8_candidate_sequence_set",
    }),
    "M7": frozenset({
        "m7_observation_table", "m7_exact_recurrence_table",
        "m7_independence_summary", "m7_validation_report",
        "m7_provenance_manifest",
    }),
    "M8": frozenset({
        "m8_raw_blast_output", "m8_query_status", "m8_match_evidence",
        "m8_summary", "m8_search_commands",
        "m8_reference_snapshot_manifest",
    }),
    "M9": frozenset({
        "m9_orf_results", "m9_protein_fasta", "m9_orf_bundle",
        "m9_protein_search_status", "m9_protein_match_evidence",
        "m9_protein_summary", "m9_search_commands", "m9_output_bundle",
        "m9_raw_blast_output", "m9_protein_reference_manifest",
    }),
    "M10": frozenset({
        "m10_candidate_accounting", "m10_repeat_evidence",
        "m10_result_bundle",
    }),
    "M12": frozenset({
        "m12_artifact_review_table", "m12_summary", "m12_result_bundle",
    }),
    "M13": frozenset({
        "m13_event_index", "m13_hypothesis_matrix", "m13_summary",
        "m13_result_bundle",
    }),
    "M14": frozenset({
        "m14_observation_table", "m14_descriptive_summary",
        "m14_result_bundle",
    }),
}
ALL_INPUT_TYPES = frozenset().union(*PRODUCER_TYPES.values())
MILESTONES = frozenset(PRODUCER_TYPES)
PRODUCER_STAGE_KINDS = {
    "M5": "dvg_virema",
    "M6": "residual_evidence",
    "M7": "independent_recurrence",
    "M8": "m8_homology",
    "M9_ORF": "m9_orf_translation",
    "M9_SEARCH": "m9_blastp",
    "M10": "m10_exact_first",
    "M12": "m12_artifact_review",
    "M13": "m13_m5_evidence_matrix",
    "M14": "m14_descriptive_observations",
}
OPTIONAL_STAGES = ("M12", "M13", "M14")
OPTIONAL_STAGE_STATES = frozenset({
    "PRESENT", "NOT_SUPPLIED", "NOT_AUTHORIZED", "UNAVAILABLE",
    "NOT_APPLICABLE", "UNKNOWN", "FAILED", "INTERRUPTED", "INCOMPLETE",
    "INVALID",
})
RESULT_COMPLETENESS = frozenset({
    "COMPLETE_WITHIN_SUPPLIED_SCOPE", "PARTIAL", "NOT_EVALUATED", "INVALID",
})
AXIS_VALUES = {
    "artifact_validity": frozenset({"VALID", "INVALID", "UNKNOWN"}),
    "applicability": frozenset({"APPLICABLE", "NOT_APPLICABLE", "UNKNOWN"}),
    "execution": frozenset({
        "pending", "running", "complete", "skipped", "dependency_missing",
        "external_module_required", "failed", "interrupted", "UNKNOWN",
    }),
    "completeness": frozenset({"COMPLETE", "INCOMPLETE", "TRUNCATED", "UNKNOWN"}),
    "observation": frozenset({
        "OBSERVED", "NOT_DETECTED_WITHIN_SCOPE", "NO_OBSERVATION", "UNKNOWN",
    }),
    "interpretation": frozenset({
        "SUPPORTS", "CONFLICTS", "UNRESOLVED", "NOT_INTERPRETED",
    }),
}
EDGE_RELATIONS = frozenset({
    "DERIVED_FROM", "SAME_INPUT", "SAME_READ_SOURCE", "SHARED_REFERENCE",
    "SAME_DECLARED_UNIT", "POTENTIAL_OVERLAP", "UNKNOWN",
})
EDGE_VERIFICATION_STATES = frozenset({
    "VERIFIED", "DECLARED_UNVERIFIED", "UNKNOWN",
})

OUTPUT_CONTRACTS = {
    "evidence_envelope.json": "m15_evidence_envelope",
    "dependency_edges.json": "m15_dependency_edges",
    "dossier_summary.json": "m15_dossier_summary",
    "result_bundle.json": "m15_result_bundle",
}

HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_TEXT_RE = re.compile(r"^[^\x00-\x1f\x7f]+$")
_STAGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")
_REF_REQUIRED = frozenset({
    "producer_milestone", "producer_stage_id",
    "producer_run_manifest_sha256", "artifact_type",
    "artifact_contract_version", "relative_path", "sha256",
    "producer_status",
})
_SNAPSHOT_ONLY_TYPES = frozenset({
    "m8_reference_snapshot_manifest", "m9_protein_reference_manifest",
})


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON value is not allowed: {value}")


def read_json_value(path, *, max_bytes=32_000_000):
    path = Path(path)
    info = path.lstat()
    if path.is_symlink() or not path.is_file():
        raise ValueError("M15 JSON must be a regular non-symlink file")
    if info.st_size > max_bytes:
        raise ValueError("M15 JSON exceeds the 32 MB contract limit")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("M15 JSON must not contain a UTF-8 BOM")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("M15 JSON is not valid UTF-8 JSON") from error
    return value


def read_json(path, *, max_bytes=32_000_000):
    value = read_json_value(path, max_bytes=max_bytes)
    if not isinstance(value, dict):
        raise ValueError("M15 JSON document must be an object")
    return value


def canonical_json_bytes(value):
    try:
        text = json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("M15 output is not finite JSON data") from error
    return (text + "\n").encode("utf-8")


def write_json(path, value):
    payload = canonical_json_bytes(value)
    Path(path).write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(value, label, *, maximum=512):
    if (not isinstance(value, str) or not value or len(value) > maximum
            or not _TEXT_RE.fullmatch(value)):
        raise ValueError(f"{label} must be non-empty bounded text")
    return value


def _relative_path(value, label):
    if (not isinstance(value, str) or not value or "\\" in value
            or value.startswith("/") or re.match(r"^[A-Za-z]:", value)):
        raise ValueError(f"{label} must be a normalized relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"{label} must not contain path traversal")
    if value != "/".join(parts):
        raise ValueError(f"{label} must be normalized")
    return value


def validate_artifact_ref(value, *, input_schema=None):
    if not isinstance(value, dict) or not _REF_REQUIRED <= set(value):
        raise ValueError("M15 ArtifactRef is missing required identity fields")
    if input_schema is None:
        input_schema = (
            INPUT_SCHEMA if "provenance_mode" in value
            else LEGACY_INPUT_SCHEMA
        )
    if input_schema not in {LEGACY_INPUT_SCHEMA, INPUT_SCHEMA}:
        raise ValueError("M15 ArtifactRef input schema is unsupported")
    milestone = value["producer_milestone"]
    if milestone not in MILESTONES:
        raise ValueError("M15 ArtifactRef has an unsupported producer milestone")
    _text(value["producer_stage_id"], "producer_stage_id", maximum=128)
    if not _STAGE_ID_RE.fullmatch(value["producer_stage_id"]):
        raise ValueError("M15 producer_stage_id is not a safe identifier")
    _text(value["producer_status"], "producer_status", maximum=256)
    artifact_type = _text(value["artifact_type"], "artifact_type", maximum=128)
    if artifact_type not in ALL_INPUT_TYPES:
        raise ValueError("M15 ArtifactRef has an unsupported artifact type")
    if (not isinstance(value["producer_run_manifest_sha256"], str)
            or not HASH_RE.fullmatch(value["producer_run_manifest_sha256"])):
        raise ValueError("M15 producer run-manifest digest must be lowercase SHA-256")
    if (not isinstance(value["sha256"], str)
            or not HASH_RE.fullmatch(value["sha256"])):
        raise ValueError("M15 artifact digest must be lowercase SHA-256")
    if (not isinstance(value["artifact_contract_version"], str)
            or not _VERSION_RE.fullmatch(value["artifact_contract_version"])):
        raise ValueError("M15 artifact contract version is invalid")
    _relative_path(value["relative_path"], "M15 ArtifactRef.relative_path")
    if input_schema == INPUT_SCHEMA:
        required_v2 = {
            "provenance_mode", "producer_execution_ref",
            "producer_bundle_path",
        }
        if not required_v2 <= set(value):
            raise ValueError("M15 v2 ArtifactRef lacks authenticated provenance fields")
        mode = value["provenance_mode"]
        if mode == AUTHENTICATED_PRODUCER_MODE:
            if artifact_type in _SNAPSHOT_ONLY_TYPES:
                raise ValueError("M15 snapshot manifests are not producer-stage artifacts")
            if not isinstance(value["producer_execution_ref"], dict):
                raise ValueError("M15 authenticated ArtifactRef requires producer_execution_ref")
            _relative_path(value["producer_bundle_path"], "M15 producer_bundle_path")
        elif mode == CALLER_SNAPSHOT_MODE:
            if (artifact_type not in _SNAPSHOT_ONLY_TYPES
                    or value["producer_execution_ref"] is not None
                    or value["producer_bundle_path"] is not None):
                raise ValueError("M15 caller-snapshot mode is invalid for this ArtifactRef")
        else:
            raise ValueError("M15 ArtifactRef provenance_mode is unsupported")
    # Preserve optional provenance fields exactly. Reject values that could not
    # be represented losslessly in canonical JSON.
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("M15 ArtifactRef contains non-JSON provenance") from error
    return value


def producer_type_allowed(ref):
    return (
        isinstance(ref, dict)
        and ref.get("producer_milestone") in PRODUCER_TYPES
        and ref.get("artifact_type")
        in PRODUCER_TYPES.get(ref.get("producer_milestone"), ())
    )


def expected_producer_stage_kind(ref):
    milestone = ref.get("producer_milestone")
    artifact_type = ref.get("artifact_type")
    if milestone == "M9":
        if artifact_type in {
            "m9_orf_results", "m9_protein_fasta", "m9_orf_bundle",
        }:
            return PRODUCER_STAGE_KINDS["M9_ORF"]
        return PRODUCER_STAGE_KINDS["M9_SEARCH"]
    return PRODUCER_STAGE_KINDS.get(milestone)


def validate_input_manifest(value):
    if (not isinstance(value, dict)
            or set(value) != {
                "schema", "candidate_id", "artifact_refs",
                "optional_stage_states",
            }):
        raise ValueError("M15 input manifest must contain exactly its frozen fields")
    schema = value["schema"]
    if schema not in {LEGACY_INPUT_SCHEMA, INPUT_SCHEMA}:
        raise ValueError("M15 input manifest schema is unsupported")
    _text(value["candidate_id"], "candidate_id", maximum=256)
    refs = value["artifact_refs"]
    if not isinstance(refs, list) or len(refs) > 10_000:
        raise ValueError("M15 artifact_refs must be a bounded array")
    for ref in refs:
        validate_artifact_ref(ref, input_schema=schema)
    states = value["optional_stage_states"]
    if not isinstance(states, dict) or set(states) != set(OPTIONAL_STAGES):
        raise ValueError("M15 optional_stage_states must contain exactly M12/M13/M14")
    for milestone, state in states.items():
        if state not in OPTIONAL_STAGE_STATES:
            raise ValueError(f"Unsupported M15 optional state for {milestone}")
        if state == "PRESENT" and not any(
            ref["producer_milestone"] == milestone for ref in refs
        ):
            raise ValueError(f"{milestone} PRESENT requires a matching ArtifactRef")
    return value


def validate_input_manifest_file(path):
    value = validate_input_manifest(read_json(path))
    return {
        "schema": value["schema"],
        "candidate_id": value["candidate_id"],
        "artifact_ref_count": len(value["artifact_refs"]),
    }


def empty_axes(artifact_validity="UNKNOWN"):
    return {
        "artifact_validity": artifact_validity,
        "applicability": "UNKNOWN",
        "execution": "UNKNOWN",
        "completeness": "UNKNOWN",
        "observation": "UNKNOWN",
        "interpretation": "NOT_INTERPRETED",
    }


def map_explicit_axes(document, *, artifact_validity="VALID"):
    """Copy exact standardized axis values only; never infer from status labels."""
    axes = empty_axes(artifact_validity)
    if not isinstance(document, dict):
        return axes
    explicit = document.get("semantic_axes")
    if not isinstance(explicit, dict):
        explicit = document
    for axis in ("applicability", "execution", "completeness", "observation"):
        value = explicit.get(axis)
        if isinstance(value, str) and value in AXIS_VALUES[axis]:
            if axis != "observation" or value != "NOT_DETECTED_WITHIN_SCOPE" \
                    or document.get("accounting_valid") is True:
                axes[axis] = value
    interpretation = explicit.get("interpretation")
    if (isinstance(interpretation, str)
            and interpretation in AXIS_VALUES["interpretation"]
            and interpretation != "NOT_INTERPRETED"
            and document.get("hypothesis_ref") is not None):
        axes["interpretation"] = interpretation
    return axes


def _exact_fields(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f"{label} must contain exactly its declared fields")


def validate_envelope(value):
    if not isinstance(value, dict) or value.get("schema") != ENVELOPE_SCHEMA:
        raise ValueError("M15 evidence envelope schema is invalid")
    if set(value) != {
        "schema", "candidate_id", "records", "compatibility_warnings",
    }:
        raise ValueError("M15 evidence envelope fields are invalid")
    _text(value["candidate_id"], "candidate_id", maximum=256)
    records = value["records"]
    if not isinstance(records, list):
        raise ValueError("M15 envelope records must be an array")
    ids = []
    for record in records:
        _exact_fields(record, {
            "evidence_id", "candidate_id", "producer_ref",
            "producer_status_raw", "producer_schema_raw",
            "producer_provenance_state", "producer_provenance_error_code",
            "producer_binding_sha256", "producer_execution_state",
            "source_row_ref", "semantic_axes", "dependency_edge_ids",
            "validation_state", "reason_code",
        }, "M15 evidence record")
        if record["candidate_id"] != value["candidate_id"]:
            raise ValueError("M15 evidence record candidate_id does not match")
        evidence_id = _text(record["evidence_id"], "evidence_id", maximum=128)
        if not HASH_RE.fullmatch(evidence_id):
            raise ValueError("M15 evidence_id must be lowercase SHA-256")
        ids.append(record["evidence_id"])
        validate_artifact_ref(record["producer_ref"])
        if record["producer_status_raw"] != record["producer_ref"]["producer_status"]:
            raise ValueError("M15 raw producer status must match its ArtifactRef")
        _text(record["producer_schema_raw"], "producer_schema_raw", maximum=256)
        if record["producer_provenance_state"] not in {
            "VERIFIED", "INVALID_PROVENANCE", "UNAVAILABLE", "INCOMPLETE",
            "DECLARED_UNVERIFIED", "INVALID",
        }:
            raise ValueError("M15 producer provenance state is invalid")
        if record["producer_provenance_error_code"] is not None:
            _text(record["producer_provenance_error_code"],
                  "producer_provenance_error_code", maximum=128)
        binding_sha256 = record["producer_binding_sha256"]
        if binding_sha256 is not None and (
                not isinstance(binding_sha256, str)
                or not HASH_RE.fullmatch(binding_sha256)):
            raise ValueError("M15 producer binding digest is invalid")
        if (record["producer_provenance_state"] == "VERIFIED"
                and binding_sha256 is None):
            raise ValueError("Verified M15 evidence requires a binding digest")
        execution_state = record["producer_execution_state"]
        if (not isinstance(execution_state, str) or not execution_state
                or len(execution_state) > 256):
            raise ValueError("M15 producer execution state is invalid")
        if record["source_row_ref"] is not None:
            raise ValueError("M15 whole-artifact records require a null source_row_ref")
        if not isinstance(record["semantic_axes"], dict) \
                or set(record["semantic_axes"]) != set(AXIS_VALUES):
            raise ValueError("M15 evidence record must contain all six semantic axes")
        for axis, values in AXIS_VALUES.items():
            if record["semantic_axes"][axis] not in values:
                raise ValueError(f"Invalid M15 semantic axis value for {axis}")
        if record["validation_state"] not in {
            "ACCEPTED", "INVALID", "UNAVAILABLE", "INCOMPLETE",
            "INVALID_PROVENANCE", "UNVERIFIED",
        }:
            raise ValueError("M15 evidence validation state is invalid")
        if (record["validation_state"] == "ACCEPTED"
                and record["semantic_axes"]["artifact_validity"] not in {
                    "VALID", "UNKNOWN",
                }):
            raise ValueError("Accepted M15 evidence cannot have invalid artifact bytes")
        expected_validity = {
            "INVALID": "INVALID",
            "UNAVAILABLE": "UNKNOWN",
            "INCOMPLETE": "UNKNOWN",
            "INVALID_PROVENANCE": "UNKNOWN",
            "UNVERIFIED": "UNKNOWN",
        }.get(record["validation_state"])
        if (expected_validity is not None
                and record["semantic_axes"]["artifact_validity"]
                != expected_validity):
            raise ValueError(
                "M15 rejected evidence validity must distinguish invalid from unavailable"
            )
        if (not isinstance(record["dependency_edge_ids"], list)
                or any(not isinstance(item, str) for item in record["dependency_edge_ids"])
                or record["dependency_edge_ids"] != sorted(
                    set(record["dependency_edge_ids"]))):
            raise ValueError("M15 dependency_edge_ids must be strings")
        if record["reason_code"] is not None and not isinstance(record["reason_code"], str):
            raise ValueError("M15 reason_code must be text or null")
        if (record["validation_state"] == "ACCEPTED"
                and record["reason_code"] is not None):
            raise ValueError("Accepted M15 evidence cannot have an error reason")
        if (record["validation_state"] != "ACCEPTED"
                and not record["reason_code"]):
            raise ValueError("Rejected M15 evidence requires an error reason")
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ValueError("M15 evidence IDs must be unique and sorted")
    warnings = value["compatibility_warnings"]
    if not isinstance(warnings, list) or any(
            not isinstance(item, str) or not item for item in warnings):
        raise ValueError("M15 compatibility_warnings must be an array")
    if warnings != sorted(set(warnings)):
        raise ValueError("M15 compatibility warnings must be unique and sorted")
    return {"record_count": len(records)}


def validate_edges(value):
    if not isinstance(value, dict) or set(value) != {"schema", "edges"} \
            or value["schema"] != EDGES_SCHEMA:
        raise ValueError("M15 dependency edge artifact is malformed")
    if not isinstance(value["edges"], list):
        raise ValueError("M15 dependency edges must be an array")
    previous = None
    ids = set()
    for edge in value["edges"]:
        _exact_fields(edge, {
            "edge_id", "source_evidence_id", "target_evidence_id", "relation",
            "verification_state", "source_provenance_ref",
        }, "M15 dependency edge")
        for key in ("edge_id", "source_evidence_id", "target_evidence_id"):
            text = _text(edge[key], key, maximum=128)
            if not HASH_RE.fullmatch(text):
                raise ValueError(f"M15 {key} must be lowercase SHA-256")
        if edge["relation"] not in EDGE_RELATIONS:
            raise ValueError("M15 dependency edge relation is invalid")
        if edge["verification_state"] not in EDGE_VERIFICATION_STATES:
            raise ValueError("M15 dependency edge verification state is invalid")
        if not isinstance(edge["source_provenance_ref"], dict):
            raise ValueError("M15 dependency edge provenance must be an object")
        identity = {
            key: edge[key] for key in (
                "source_evidence_id", "target_evidence_id", "relation",
                "verification_state", "source_provenance_ref",
            )
        }
        expected_id = hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
        if edge["edge_id"] != expected_id:
            raise ValueError("M15 dependency edge ID does not match its identity")
        if edge["edge_id"] in ids:
            raise ValueError("M15 dependency edge IDs must be unique")
        ids.add(edge["edge_id"])
        current = (
            edge["source_evidence_id"], edge["relation"],
            edge["target_evidence_id"],
        )
        if previous is not None and current < previous:
            raise ValueError("M15 dependency edges are not canonically sorted")
        previous = current
    return {"edge_count": len(value["edges"])}


def validate_summary(value):
    if not isinstance(value, dict) or value.get("schema") != SUMMARY_SCHEMA:
        raise ValueError("M15 dossier summary schema is invalid")
    required = {
        "schema", "candidate_id", "result_completeness",
        "optional_stage_states", "counts", "by_producer",
    }
    if set(value) != required:
        raise ValueError("M15 dossier summary fields are invalid")
    _text(value["candidate_id"], "candidate_id", maximum=256)
    if value["result_completeness"] not in RESULT_COMPLETENESS:
        raise ValueError("M15 result completeness is invalid")
    states = value["optional_stage_states"]
    if not isinstance(states, dict) or set(states) != set(OPTIONAL_STAGES) \
            or any(state not in OPTIONAL_STAGE_STATES for state in states.values()):
        raise ValueError("M15 summary optional states are invalid")
    counts = value["counts"]
    count_keys = {
        "supplied_artifacts", "accepted_records", "invalid_records",
        "invalid_provenance_records", "unavailable_records",
        "incomplete_records", "unverified_records",
        "absent_optional_stages", "unresolved_records",
        "compatibility_warnings",
    }
    if not isinstance(counts, dict) or set(counts) != count_keys:
        raise ValueError("M15 summary counts are invalid")
    for key in count_keys - {"absent_optional_stages"}:
        if isinstance(counts[key], bool) or not isinstance(counts[key], int) \
                or counts[key] < 0:
            raise ValueError(f"M15 summary count {key} must be a nonnegative integer")
    if not isinstance(counts["absent_optional_stages"], list):
        raise ValueError("M15 absent_optional_stages must be an array")
    expected_absent = sorted(
        milestone for milestone, state in states.items()
        if state not in {"PRESENT", "NOT_APPLICABLE"}
    )
    if counts["absent_optional_stages"] != expected_absent:
        raise ValueError("M15 absent optional-stage count does not match its states")
    if (counts["supplied_artifacts"] != counts["accepted_records"]
            + counts["invalid_records"] + counts["unavailable_records"]
            + counts["incomplete_records"] + counts["unverified_records"]):
        raise ValueError("M15 supplied-artifact count does not reconcile")
    if counts["invalid_provenance_records"] > counts["invalid_records"]:
        raise ValueError("M15 invalid-provenance count exceeds invalid records")
    by_producer = value["by_producer"]
    if not isinstance(by_producer, list):
        raise ValueError("M15 by_producer must be an array of objects")
    producer_ids = []
    producer_totals = {
        "supplied_artifacts": 0,
        "accepted_records": 0,
        "invalid_records": 0,
        "invalid_provenance_records": 0,
        "unavailable_records": 0,
        "incomplete_records": 0,
        "unverified_records": 0,
    }
    for row in by_producer:
        row_keys = {
            "producer_milestone", "supplied_artifacts", "accepted_records",
            "invalid_records", "invalid_provenance_records",
            "unavailable_records", "incomplete_records", "unverified_records",
        }
        if not isinstance(row, dict) or set(row) != row_keys:
            raise ValueError("M15 by_producer row fields are invalid")
        milestone = row["producer_milestone"]
        if milestone not in MILESTONES:
            raise ValueError("M15 by_producer has an unsupported milestone")
        producer_ids.append(milestone)
        for key in producer_totals:
            count = row[key]
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"M15 by_producer count {key} is invalid")
            producer_totals[key] += count
    if producer_ids != sorted(set(producer_ids)):
        raise ValueError("M15 by_producer rows must be unique and sorted")
    if any(producer_totals[key] != counts[key] for key in producer_totals):
        raise ValueError("M15 by_producer counts do not reconcile")
    return {"record_count": counts["supplied_artifacts"]}


def validate_result_bundle(value):
    if not isinstance(value, dict) or value.get("schema") != RESULT_BUNDLE_SCHEMA:
        raise ValueError("M15 result bundle schema is invalid")
    required = {
        "schema", "input_schema", "semantic_version", "candidate_id",
        "result_completeness", "input_manifest_sha256",
        "input_manifest_digest_kind", "input_semantics_version",
        "axis_mapping_semantic_version", "optional_stage_states", "producer_refs",
        "dependency_edges", "contract_semantics", "implementation",
        "outputs", "source_access_provenance",
    }
    if set(value) != required:
        raise ValueError("M15 result bundle fields are invalid")
    _text(value["candidate_id"], "candidate_id", maximum=256)
    if value["result_completeness"] not in RESULT_COMPLETENESS:
        raise ValueError("M15 result bundle completeness is invalid")
    if (value["input_schema"] not in {LEGACY_INPUT_SCHEMA, INPUT_SCHEMA}
            or value["semantic_version"] != SEMANTIC_VERSION
            or value["input_manifest_digest_kind"]
                != "M15_SEMANTIC_PROJECTION_JSON_SHA256"
            or value["input_semantics_version"] != INPUT_SEMANTICS_VERSION
            or not isinstance(value["axis_mapping_semantic_version"], str)
            or not value["axis_mapping_semantic_version"]):
        raise ValueError("M15 result bundle semantic identity is invalid")
    if not isinstance(value["input_manifest_sha256"], str) \
            or not HASH_RE.fullmatch(value["input_manifest_sha256"]):
        raise ValueError("M15 result bundle input digest is invalid")
    if not isinstance(value["producer_refs"], list):
        raise ValueError("M15 result bundle producer_refs must be an array")
    for ref in value["producer_refs"]:
        validate_artifact_ref(ref, input_schema=value["input_schema"])
    if not isinstance(value["dependency_edges"], list):
        raise ValueError("M15 result bundle dependency_edges must be an array")
    validate_edges({"schema": EDGES_SCHEMA, "edges": value["dependency_edges"]})
    states = value["optional_stage_states"]
    if (not isinstance(states, dict) or set(states) != set(OPTIONAL_STAGES)
            or any(state not in OPTIONAL_STAGE_STATES
                   for state in states.values())):
        raise ValueError("M15 result bundle optional-stage states are invalid")
    if not isinstance(value["contract_semantics"], dict) \
            or not isinstance(value["implementation"], dict):
        raise ValueError("M15 result bundle identity fields must be objects")
    outputs = value["outputs"]
    if not isinstance(outputs, dict) or set(outputs) != {
        artifact_type for name, artifact_type in OUTPUT_CONTRACTS.items()
        if name != "result_bundle.json"
    }:
        raise ValueError("M15 result bundle output inventory is invalid")
    output_paths = {
        artifact_type: name for name, artifact_type in OUTPUT_CONTRACTS.items()
        if name != "result_bundle.json"
    }
    for artifact_type, row in outputs.items():
        if (not isinstance(row, dict)
                or set(row) != {"relative_path", "artifact_type", "sha256"}
                or row["relative_path"] != output_paths[artifact_type]
                or not isinstance(row["artifact_type"], str)
                or row["artifact_type"] != artifact_type
                or not isinstance(row["sha256"], str)
                or not HASH_RE.fullmatch(row["sha256"])):
            raise ValueError("M15 result bundle output descriptor is invalid")
    source_access = value["source_access_provenance"]
    if not isinstance(source_access, list):
        raise ValueError("M15 source-access provenance must be an array")
    access_ids = []
    for row in source_access:
        if (not isinstance(row, dict)
                or set(row) != {"evidence_id", "state", "references"}
                or not isinstance(row["evidence_id"], str)
                or not HASH_RE.fullmatch(row["evidence_id"])
                or row["state"] not in {"DECLARED", "UNKNOWN"}
                or not isinstance(row["references"], dict)):
            raise ValueError("M15 source-access provenance row is invalid")
        access_ids.append(row["evidence_id"])
    if access_ids != sorted(set(access_ids)):
        raise ValueError("M15 source-access provenance rows must be unique and sorted")
    return {"producer_ref_count": len(value["producer_refs"])}


def validate_output_document(artifact_type, value):
    validators = {
        "m15_evidence_envelope": validate_envelope,
        "m15_dependency_edges": validate_edges,
        "m15_dossier_summary": validate_summary,
        "m15_result_bundle": validate_result_bundle,
    }
    try:
        validator = validators[artifact_type]
    except KeyError:
        raise ValueError(f"Unknown M15 output artifact type: {artifact_type!r}") from None
    return validator(value)


def validate_output_file(path, artifact_type):
    details = validate_output_document(artifact_type, read_json(path))
    details["schema"] = read_json(path)["schema"]
    return details