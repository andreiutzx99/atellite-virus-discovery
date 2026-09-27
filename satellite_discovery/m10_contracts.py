"""Fail-closed validators for deterministic M10 result artifacts."""

import hashlib
import json
from pathlib import Path
import re

from .m10_algorithms import _reverse_view
from .sequence_downloader import checksum


_HASH = re.compile(r"^[0-9a-f]{64}$")
_BRANCHES = (
    "M10_TERMINAL_DIRECT_V1",
    "M10_TERMINAL_INVERTED_V1",
    "M10_INTERNAL_DIRECT_V1",
    "M10_INTERNAL_INVERTED_V1",
)
_BRANCH_STATUSES = {
    "COMPLETED_MATCHES_REPORTED",
    "COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY",
    "INSUFFICIENT_INFORMATION",
    "BOUNDARY_LIMITATION",
    "INPUT_INVALID",
    "SEQUENCE_UNAVAILABLE",
    "DEPENDENCY_UNAVAILABLE",
    "EXECUTION_FAILED",
    "OUTPUT_INVALID",
    "INTERRUPTED",
    "TRUNCATED",
    "NOT_SELECTED",
    "NOT_APPLICABLE",
    "NOT_STARTED",
    "RUNNING",
}
_INPUT_STATUSES = {
    "INPUT_VALID", "INPUT_INVALID", "SEQUENCE_UNAVAILABLE",
    "COMPLETE_EMPTY_INPUT_SET",
}
_ACCOUNTING_NAME = "candidate_accounting.jsonl"
_EVIDENCE_NAME = "repeat_evidence.jsonl"


def _object(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _hash(value, label):
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _nonnegative_int(value, label):
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")


def _read_lines(path):
    try:
        with Path(path).open("r", encoding="utf-8") as source:
            for number, line in enumerate(source, 1):
                if not line.endswith("\n"):
                    raise ValueError(f"Malformed M10 JSONL row {number}")
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(f"Invalid M10 JSONL row {number}") from error
                yield _object(value, f"M10 JSONL row {number}")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("M10 JSONL artifact is unreadable") from error


def _validate_candidate_row(row, identities):
    required = {
        "record_type", "candidate_id", "sequence_id", "source_sequence",
        "source_sha256", "source_length", "source_artifact",
        "candidate_set_sha256", "candidate_set_validation_state",
        "molecule_type", "sequence_bytes_available", "completeness_state",
        "source_alphabet", "comparison_view", "reverse_complement_view",
        "terminal_boundaries_resolved", "input_status", "aggregate_status",
        "configuration_sha256", "branch_plan", "branches",
        "expected_evidence_rows", "accounted_evidence_rows",
    }
    if not required <= set(row) or row.get("record_type") != "candidate":
        raise ValueError("M10 candidate accounting record is incomplete")
    candidate_id, sequence_id = row["candidate_id"], row["sequence_id"]
    if (not isinstance(candidate_id, str) or not candidate_id
            or not isinstance(sequence_id, str) or not sequence_id
            or candidate_id in identities["candidates"]
            or sequence_id in identities["sequences"]):
        raise ValueError("M10 candidate or sequence identity is invalid or duplicated")
    identities["candidates"].add(candidate_id)
    identities["sequences"].add(sequence_id)
    if row["input_status"] not in _INPUT_STATUSES - {"COMPLETE_EMPTY_INPUT_SET"}:
        raise ValueError("M10 candidate input status is invalid")
    if row["aggregate_status"] not in {"COMPLETE", "PARTIAL"}:
        raise ValueError("M10 candidate aggregate status is invalid")
    if row["candidate_set_validation_state"] != "valid":
        raise ValueError("M10 candidate set validation state is not valid")
    _hash(row["candidate_set_sha256"], "candidate_set_sha256")
    if (row["candidate_set_sha256"] != identities.get("candidate_set_sha256")
            or row["configuration_sha256"] != identities.get(
                "configuration_sha256")):
        raise ValueError("M10 candidate accounting provenance is inconsistent")
    source_artifact = _object(row["source_artifact"], "source_artifact")
    if (not isinstance(source_artifact.get("artifact_id"), str)
            or not source_artifact["artifact_id"]):
        raise ValueError("M10 source artifact identity is missing")
    if source_artifact.get("sha256") is not None:
        _hash(source_artifact["sha256"], "source_artifact.sha256")
    _hash(row["configuration_sha256"], "configuration_sha256")
    _nonnegative_int(row["accounted_evidence_rows"], "accounted_evidence_rows")
    if type(row["sequence_bytes_available"]) is not bool:
        raise ValueError("M10 sequence-byte availability must be boolean")
    if (row["molecule_type"] is not None
            and (not isinstance(row["molecule_type"], str)
                 or not row["molecule_type"].strip())):
        raise ValueError("M10 declared molecule type is invalid")
    if (row["completeness_state"] is not None
            and not isinstance(row["completeness_state"], str)):
        raise ValueError("M10 completeness state is invalid")
    source = row["source_sequence"]
    if row["sequence_bytes_available"]:
        if row["input_status"] not in {"INPUT_VALID", "INPUT_INVALID"}:
            raise ValueError("Available M10 candidate has an unavailable input status")
        if not isinstance(source, str) or not source:
            raise ValueError("Available M10 candidate must preserve source letters")
        try:
            source_bytes = source.encode("ascii")
        except UnicodeEncodeError as error:
            raise ValueError("M10 source sequence must be ASCII") from error
        digest = hashlib.sha256(source_bytes).hexdigest()
        if (digest != row["source_sha256"]
                or len(source) != row["source_length"]):
            raise ValueError("M10 source sequence identity does not match its digest")
        _hash(row["source_sha256"], "source_sha256")
        _nonnegative_int(row["source_length"], "source_length")
        upper = source.upper()
        if any(symbol not in "ACGTURYSWKMBDHVN" for symbol in upper):
            raise ValueError("M10 source sequence contains a non-IUPAC symbol")
        source_alphabet = _object(row["source_alphabet"], "source_alphabet")
        if (source_alphabet.get("policy_id") != "M10-IUPAC-ALPHABET-V1"
                or source_alphabet.get("state") != "OBSERVED"
                or source_alphabet.get("observed_symbols")
                != sorted(set(upper))):
            raise ValueError("M10 source alphabet description is inconsistent")
        comparison_view = _object(row["comparison_view"], "comparison_view")
        comparison_digest = hashlib.sha256(
            b"M10-COMPARE-IUPAC-v1\0" + upper.encode("ascii")
        ).hexdigest()
        if comparison_view != {
                "digest": comparison_digest,
                "length": len(source),
                "policy": "M10-COMPARE-IUPAC-v1",
        }:
            raise ValueError("M10 comparison-view identity is inconsistent")
        molecule = (
            row["molecule_type"].upper()
            if isinstance(row["molecule_type"], str) else ""
        )
        reverse_applicable = molecule in {"DNA", "RNA"} and not (
            ("U" in upper and molecule == "DNA")
            or ("T" in upper and molecule == "RNA")
            or ("T" in upper and "U" in upper)
        )
        reverse_view = row["reverse_complement_view"]
        if reverse_applicable:
            reverse = _reverse_view(upper, molecule)
            expected_reverse = {
                "digest": hashlib.sha256(
                    b"M10-REVERSE-COMPLEMENT-v1\0"
                    + molecule.encode("ascii") + b"\0" + reverse.encode("ascii")
                ).hexdigest(),
                "length": len(source),
                "alphabet_id": molecule,
                "policy": "M10-REVERSE-COMPLEMENT-v1",
                "coordinate_map": "view interval [a,b) -> source [n-b,n-a)",
            }
            if reverse_view != expected_reverse:
                raise ValueError("M10 reverse-complement view identity is inconsistent")
        elif reverse_view is not None:
            raise ValueError("Inapplicable M10 reverse-complement view was emitted")
    elif (source is not None or row["source_sha256"] is not None
          or row["source_length"] is not None
          or row["input_status"] != "SEQUENCE_UNAVAILABLE"):
        raise ValueError("Unavailable M10 candidate has inconsistent source identity")
    else:
        source_alphabet = _object(row["source_alphabet"], "source_alphabet")
        if (source_alphabet.get("policy_id") != "M10-IUPAC-ALPHABET-V1"
                or source_alphabet.get("state") != "BYTES_UNAVAILABLE"
                or source_alphabet.get("observed_symbols") is not None
                or row["comparison_view"] is not None
                or row["reverse_complement_view"] is not None):
            raise ValueError("Unavailable M10 candidate has derived-view metadata")
    if type(row["terminal_boundaries_resolved"]) is not bool:
        raise ValueError("M10 terminal-boundary state must be boolean")
    if row["branch_plan"] != list(_BRANCHES):
        raise ValueError("M10 required branch plan is incomplete or reordered")
    branches = _object(row["branches"], "M10 branches")
    if set(branches) != set(_BRANCHES):
        raise ValueError("M10 branch accounting is incomplete")
    accounted = 0
    every_branch_complete = True
    for branch_id in _BRANCHES:
        branch = _object(branches[branch_id], branch_id)
        if (branch.get("branch_id") != branch_id
                or branch.get("branch_status") not in _BRANCH_STATUSES
                or branch.get("evidence_status") not in {
                    "EVIDENCE_FOUND", "NO_EVIDENCE_REPORTED",
                }):
            raise ValueError("M10 branch status or identity is invalid")
        count = branch.get("evidence_rows")
        _nonnegative_int(count, f"{branch_id}.evidence_rows")
        for field in (
                "accounted_comparisons", "ambiguity_compatible_comparisons",
                "ambiguity_incompatible_comparisons"):
            _nonnegative_int(branch.get(field), f"{branch_id}.{field}")
        if (branch["ambiguity_compatible_comparisons"]
                + branch["ambiguity_incompatible_comparisons"]
                > branch["accounted_comparisons"]):
            raise ValueError("M10 ambiguity accounting exceeds comparisons")
        limits = _object(branch.get("effective_limits"), f"{branch_id}.effective_limits")
        for field in (
                "max_candidate_symbols", "max_symbol_comparisons_per_branch",
                "max_evidence_rows_per_branch"):
            _nonnegative_int(limits.get(field), f"{branch_id}.{field}")
            if limits[field] < 1:
                raise ValueError("M10 effective caps must be positive")
        if (count > limits["max_evidence_rows_per_branch"]
                or branch["accounted_comparisons"]
                > limits["max_symbol_comparisons_per_branch"]):
            raise ValueError("M10 branch accounting exceeds its effective caps")
        accounted += count
        full = branch.get("full_accounting_proven")
        if type(full) is not bool:
            raise ValueError("M10 full-accounting state must be boolean")
        complete = branch["branch_status"] in {
            "COMPLETED_MATCHES_REPORTED",
            "COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY",
        }
        if full != complete:
            raise ValueError("M10 full-accounting state conflicts with branch status")
        if (complete and row["sequence_bytes_available"]
                and row["source_length"] > limits["max_candidate_symbols"]):
            raise ValueError("M10 completed branch exceeds its candidate-symbol cap")
        if complete and (
                (count > 0) != (branch["branch_status"] == "COMPLETED_MATCHES_REPORTED")):
            raise ValueError("M10 completed branch status conflicts with evidence count")
        if (branch["evidence_status"] == "EVIDENCE_FOUND") != (count > 0):
            raise ValueError("M10 evidence status conflicts with evidence count")
        if not complete:
            every_branch_complete = False
    if accounted != row["accounted_evidence_rows"]:
        raise ValueError("M10 candidate evidence accounting does not sum")
    if row["aggregate_status"] == "COMPLETE":
        if (not every_branch_complete or row["input_status"] != "INPUT_VALID"
                or row["expected_evidence_rows"] != accounted):
            raise ValueError("M10 complete candidate has incomplete branch accounting")
    elif row["expected_evidence_rows"] is not None:
        _nonnegative_int(row["expected_evidence_rows"], "expected_evidence_rows")


def validate_candidate_accounting(path):
    rows = iter(_read_lines(path))
    try:
        header = next(rows)
    except StopIteration as error:
        raise ValueError("M10 candidate accounting is empty") from error
    if (header.get("record_type") != "manifest"
            or header.get("schema") != "m10-candidate-accounting-v1"
            or header.get("input_status") not in _INPUT_STATUSES
            or header.get("aggregate_status") not in {"COMPLETE", "PARTIAL"}):
        raise ValueError("M10 candidate accounting header is malformed")
    _nonnegative_int(header.get("candidate_count"), "candidate_count")
    if (not isinstance(header.get("candidate_set"), dict)
            or not isinstance(header.get("context_artifacts"), list)
            or not isinstance(header.get("optional_context_state"), dict)
            or not isinstance(header.get("configuration"), dict)
            or not isinstance(header.get("implementation"), dict)
            or not isinstance(header.get("policy_ids"), dict)):
        raise ValueError("M10 accounting header lacks typed provenance")
    if header.get("required_branches") != list(_BRANCHES):
        raise ValueError("M10 accounting header has an invalid branch plan")
    _hash(header.get("configuration_sha256"), "configuration_sha256")
    candidate_set = _object(header.get("candidate_set"), "candidate_set")
    _hash(candidate_set.get("sha256"), "candidate_set.sha256")
    canonical_configuration = json.dumps(
        header["configuration"], sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")
    if hashlib.sha256(canonical_configuration).hexdigest() != header[
            "configuration_sha256"]:
        raise ValueError("M10 configuration digest is inconsistent")
    if (header["configuration"].get("policy_ids") != header.get("policy_ids")
            or header["configuration"].get("required_branches") != list(_BRANCHES)):
        raise ValueError("M10 configuration policy identity is inconsistent")
    identities = {
        "candidates": set(),
        "sequences": set(),
        "candidate_set_sha256": candidate_set["sha256"],
        "configuration_sha256": header["configuration_sha256"],
    }
    total_evidence = 0
    every_candidate_complete = header["candidate_count"] > 0
    for row in rows:
        _validate_candidate_row(row, identities)
        total_evidence += row["accounted_evidence_rows"]
        if row["aggregate_status"] != "COMPLETE":
            every_candidate_complete = False
    if len(identities["candidates"]) != header["candidate_count"]:
        raise ValueError("M10 candidate count disagrees with accounting records")
    if (header["aggregate_status"] == "COMPLETE"
            and (header["input_status"] != "INPUT_VALID"
                 or not every_candidate_complete)):
        raise ValueError("M10 empty or invalid input cannot have complete aggregate status")
    return {
        "schema": header["schema"],
        "candidate_count": header["candidate_count"],
        "record_count": header["candidate_count"],
        "input_status": header["input_status"],
        "aggregate_status": header["aggregate_status"],
        "accounted_evidence_rows": total_evidence,
        "configuration_sha256": header["configuration_sha256"],
    }


def _validate_evidence_row(row):
    required = {
        "evidence_id", "candidate_id", "sequence_id", "source_sha256",
        "source_sequence_length", "branch_id", "method_id",
        "relationship_class", "relationship_classes", "orientation",
        "source_intervals", "span", "aligned_length",
        "candidate_set_sha256", "source_artifact_id", "source_artifact_sha256",
        "completeness_state", "terminal_boundaries_resolved",
        "definite_identical_base_count", "definite_identical_base_denominator",
        "ambiguity_compatible_count", "ambiguity_incompatible_count",
        "source_intervals_overlap", "view_digest", "branch_status",
        "evidence_status", "configuration_sha256", "coordinate_system",
        "view_to_source_coordinate_map",
        "exact_match_disposition", "policy_ids",
    }
    if not required <= set(row):
        raise ValueError("M10 repeat evidence row is incomplete")
    if (not isinstance(row["candidate_id"], str) or not row["candidate_id"]
            or not isinstance(row["sequence_id"], str) or not row["sequence_id"]):
        raise ValueError("M10 evidence candidate identity is invalid")
    _hash(row["evidence_id"], "evidence_id")
    _hash(row["source_sha256"], "source_sha256")
    _hash(row["candidate_set_sha256"], "candidate_set_sha256")
    if not isinstance(row["source_artifact_id"], str) or not row["source_artifact_id"]:
        raise ValueError("M10 evidence source artifact identity is invalid")
    if row["source_artifact_sha256"] is not None:
        _hash(row["source_artifact_sha256"], "source_artifact_sha256")
    if (row["completeness_state"] is not None
            and not isinstance(row["completeness_state"], str)):
        raise ValueError("M10 evidence completeness state is invalid")
    if type(row["terminal_boundaries_resolved"]) is not bool:
        raise ValueError("M10 evidence terminal-boundary state is invalid")
    _hash(row["view_digest"], "view_digest")
    _hash(row["configuration_sha256"], "configuration_sha256")
    _nonnegative_int(row["source_sequence_length"], "source_sequence_length")
    span = row["span"]
    _nonnegative_int(span, "span")
    _nonnegative_int(row["aligned_length"], "aligned_length")
    if span < 1 or row["aligned_length"] != span:
        raise ValueError("M10 repeat span is invalid")
    if row["branch_id"] not in _BRANCHES or row["method_id"] != row["branch_id"]:
        raise ValueError("M10 repeat branch or method identity is invalid")
    if row["orientation"] not in {"DIRECT", "REVERSE_COMPLEMENT"}:
        raise ValueError("M10 repeat orientation is invalid")
    expected_orientation = (
        "REVERSE_COMPLEMENT"
        if row["branch_id"] in {
            "M10_TERMINAL_INVERTED_V1", "M10_INTERNAL_INVERTED_V1",
        }
        else "DIRECT"
    )
    if row["orientation"] != expected_orientation:
        raise ValueError("M10 orientation does not match its branch")
    expected_mapping = (
        "IDENTITY_SOURCE_INTERVALS"
        if row["orientation"] == "DIRECT"
        else "REVERSE_COMPLEMENT_VIEW:[a,b)->SOURCE:[n-b,n-a)"
    )
    if row["view_to_source_coordinate_map"] != expected_mapping:
        raise ValueError("M10 evidence coordinate mapping is invalid")
    intervals = row["source_intervals"]
    if not isinstance(intervals, list) or len(intervals) != 2:
        raise ValueError("M10 repeat must have two source intervals")
    normalized_intervals = []
    for interval in intervals:
        if (not isinstance(interval, list) or len(interval) != 2
                or any(type(value) is not int for value in interval)
                or interval[0] < 0 or interval[1] <= interval[0]
                or interval[1] > row["source_sequence_length"]
                or interval[1] - interval[0] != span):
            raise ValueError("M10 repeat source coordinates are invalid")
        normalized_intervals.append(interval)
    if normalized_intervals[0] == normalized_intervals[1]:
        raise ValueError("M10 repeat cannot compare an interval with itself")
    if tuple(normalized_intervals[0]) > tuple(normalized_intervals[1]):
        raise ValueError("M10 source interval pair is not canonically ordered")
    expected_relationship = {
        "M10_TERMINAL_DIRECT_V1": "SUFFIX_PREFIX",
        "M10_TERMINAL_INVERTED_V1": "INVERTED_TERMINAL",
        "M10_INTERNAL_DIRECT_V1": "INTERNAL_DIRECT_REPEAT",
        "M10_INTERNAL_INVERTED_V1": "INTERNAL_REVERSE_COMPLEMENT_REPEAT",
    }[row["branch_id"]]
    if row["relationship_class"] != expected_relationship:
        raise ValueError("M10 relationship class does not match its branch")
    if row["branch_id"] in {
            "M10_TERMINAL_DIRECT_V1", "M10_TERMINAL_INVERTED_V1"}:
        if (normalized_intervals[0][0] != 0
                or normalized_intervals[1][1] != row["source_sequence_length"]):
            raise ValueError("M10 terminal evidence is not proper-border geometry")
    if row["relationship_class"] in {
            "INTERNAL_DIRECT_REPEAT", "INTERNAL_REVERSE_COMPLEMENT_REPEAT"}:
        if (normalized_intervals[0][0] <= 0 or normalized_intervals[1][0] <= 0
                or normalized_intervals[0][1] >= row["source_sequence_length"]
                or normalized_intervals[1][1] >= row["source_sequence_length"]
                or tuple(normalized_intervals[0]) > tuple(normalized_intervals[1])):
            raise ValueError("M10 internal repeat coordinates are not canonical")
    expected_classes = (
        ["SUFFIX_PREFIX", "DIRECT_TERMINAL"]
        if row["branch_id"] == "M10_TERMINAL_DIRECT_V1"
        else [expected_relationship]
    )
    if row["relationship_classes"] != expected_classes:
        raise ValueError("M10 relationship-class linkage is invalid")
    if (type(row["source_intervals_overlap"]) is not bool
            or row["source_intervals_overlap"] != (
                normalized_intervals[0][0] < normalized_intervals[1][1]
                and normalized_intervals[1][0] < normalized_intervals[0][1])):
        raise ValueError("M10 interval-overlap flag is inconsistent")
    metric_fields = (
        "definite_identical_base_count", "definite_identical_base_denominator",
        "ambiguity_compatible_count", "ambiguity_incompatible_count",
    )
    if (any(type(row[name]) is not int for name in metric_fields)
            or row["definite_identical_base_count"] != span
            or row["definite_identical_base_denominator"] != span
            or row["ambiguity_compatible_count"] != 0
            or row["ambiguity_incompatible_count"] != 0):
        raise ValueError("M10 exact evidence metrics are inconsistent")
    if (row["branch_status"] not in _BRANCH_STATUSES
            or row["evidence_status"] != "EVIDENCE_FOUND"
            or row["coordinate_system"] != "ZERO_BASED_HALF_OPEN_SOURCE"
            or row["exact_match_disposition"] != "DEFINITE_EXACT_MATCH"):
        raise ValueError("M10 repeat evidence status or coordinate system is invalid")
    if (not isinstance(row["policy_ids"], dict)
            or any(not isinstance(value, str) or not value
                   for value in row["policy_ids"].values())):
        raise ValueError("M10 evidence policy identity is missing")
    evidence_payload = json.dumps(
        [
            row["candidate_id"], row["sequence_id"], row["branch_id"],
            row["orientation"], row["source_sha256"], row["view_digest"],
            normalized_intervals[0], normalized_intervals[1],
            row["relationship_class"],
        ],
        separators=(",", ":"),
    ).encode()
    if hashlib.sha256(evidence_payload).hexdigest() != row["evidence_id"]:
        raise ValueError("M10 evidence ID does not match its stable identity")


def validate_repeat_evidence(path):
    count = 0
    identifiers = set()
    for row in _read_lines(path):
        _validate_evidence_row(row)
        if row["evidence_id"] in identifiers:
            raise ValueError("M10 evidence identifiers must be unique")
        identifiers.add(row["evidence_id"])
        count += 1
    return {"schema": "m10-repeat-evidence-v1", "record_count": count}


def _candidate_rows(path):
    rows = iter(_read_lines(path))
    header = next(rows)
    if not isinstance(header.get("candidate_set"), dict):
        raise ValueError("M10 accounting header lacks candidate-set provenance")
    return header, rows


def _matches_source(candidate, evidence):
    source = candidate["source_sequence"]
    if not isinstance(source, str):
        return False
    source = source.upper()
    (a0, a1), (b0, b1) = evidence["source_intervals"]
    first, second = source[a0:a1], source[b0:b1]
    orientation = evidence["orientation"]
    if orientation == "DIRECT":
        exact = first == second and all(base in "ACGTU" for base in first + second)
    else:
        molecule = (
            candidate["molecule_type"].upper()
            if isinstance(candidate["molecule_type"], str) else ""
        )
        canonical = "ACGT" if molecule == "DNA" else "ACGU" if molecule == "RNA" else ""
        reverse = _reverse_view(second, molecule) if canonical else None
        exact = (
            reverse is not None and first == reverse
            and all(base in canonical for base in first + second)
        )
    if not exact:
        return False
    if evidence["relationship_class"] not in {
            "INTERNAL_DIRECT_REPEAT",
            "INTERNAL_REVERSE_COMPLEMENT_REPEAT"}:
        return True

    n = len(source)
    if orientation == "DIRECT":
        extends_left = (
            a0 > 1 and b0 > 1
            and source[a0 - 1] == source[b0 - 1]
            and source[a0 - 1] in "ACGTU"
        )
        extends_right = (
            a1 < n - 1 and b1 < n - 1
            and source[a1] == source[b1]
            and source[a1] in "ACGTU"
        )
    else:
        molecule = candidate["molecule_type"].upper()
        extends_left = (
            a0 > 1 and b1 < n - 1
            and source[a0 - 1] == _reverse_view(source[b1], molecule)
            and source[a0 - 1] in "ACGTU"
            and source[b1] in "ACGTU"
        )
        extends_right = (
            a1 < n - 1 and b0 > 1
            and source[a1] == _reverse_view(source[b0 - 1], molecule)
            and source[a1] in "ACGTU"
            and source[b0 - 1] in "ACGTU"
        )
    return not (extends_left or extends_right)


def validate_bundle(path):
    bundle_path = Path(path)
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("M10 result bundle is unreadable") from error
    _object(bundle, "M10 result bundle")
    if (bundle.get("schema") != "m10-result-bundle-v1"
            or bundle.get("stage") != "m10_exact_first"
            or bundle.get("stage_version") != "1"
            or bundle.get("input_status") not in _INPUT_STATUSES
            or bundle.get("aggregate_status") not in {"COMPLETE", "PARTIAL"}):
        raise ValueError("M10 result bundle header is invalid")
    source_inputs = _object(bundle.get("source_inputs"), "M10 source inputs")
    candidate_source = _object(
        source_inputs.get("candidate_sequence_set"), "candidate_sequence_set")
    if (candidate_source.get("artifact_type") != "m8_candidate_sequence_set"
            or candidate_source.get("validation_state") != "valid"):
        raise ValueError("M10 source candidate handoff is not valid")
    _hash(candidate_source.get("sha256"), "candidate_sequence_set.sha256")
    if (not isinstance(candidate_source.get("artifact_id"), str)
            or not candidate_source["artifact_id"]
            or not isinstance(candidate_source.get("validation_metadata"), dict)):
        raise ValueError("M10 candidate source descriptor is incomplete")
    if not isinstance(source_inputs.get("optional_context"), list):
        raise ValueError("M10 optional context descriptors are malformed")
    context_state = _object(
        source_inputs.get("optional_context_state"), "optional_context_state")
    if set(context_state) != {"m7", "m8", "m9"}:
        raise ValueError("M10 optional context state is incomplete")
    for name, state in context_state.items():
        state = _object(state, f"{name} context state")
        if (state.get("state") not in {"SUPPLIED", "NOT_SUPPLIED"}
                or not isinstance(state.get("artifacts"), list)
                or (state["state"] == "SUPPLIED") != bool(state["artifacts"])):
            raise ValueError("M10 optional context state conflicts with its artifacts")
        for artifact in state["artifacts"]:
            artifact = _object(artifact, f"{name} context artifact")
            if (not isinstance(artifact.get("input_name"), str)
                    or artifact["input_name"][:2] != name
                    or not isinstance(artifact.get("artifact_id"), str)
                    or not artifact["artifact_id"]
                    or not isinstance(artifact.get("artifact_type"), str)
                    or artifact.get("validation_state") != "valid"
                    or not isinstance(artifact.get("validation_metadata"), dict)
                    or not isinstance(artifact.get("original_status_fields"), dict)
                    or not isinstance(artifact.get("provenance_fields"), dict)):
                raise ValueError("M10 context artifact identity conflicts with its group")
            _hash(artifact.get("sha256"), "context artifact sha256")
    flattened_context = [
        artifact
        for name in ("m7", "m8", "m9")
        for artifact in context_state[name]["artifacts"]
    ]
    if flattened_context != source_inputs["optional_context"]:
        raise ValueError("M10 optional context groups disagree with their descriptors")
    outputs = _object(bundle.get("outputs"), "M10 outputs")
    if set(outputs) != {_ACCOUNTING_NAME, _EVIDENCE_NAME}:
        raise ValueError("M10 result bundle must bind both normalized output artifacts")
    validated = {}
    for name, expected_type in (
            (_ACCOUNTING_NAME, "m10_candidate_accounting"),
            (_EVIDENCE_NAME, "m10_repeat_evidence")):
        descriptor = _object(outputs[name], f"M10 output {name}")
        if (descriptor.get("artifact_type") != expected_type
                or descriptor.get("size_bytes") is None):
            raise ValueError("M10 output artifact descriptor is invalid")
        _hash(descriptor.get("sha256"), f"{name}.sha256")
        _nonnegative_int(descriptor.get("size_bytes"), f"{name}.size_bytes")
        target = bundle_path.parent / name
        if (target.is_symlink() or not target.is_file()
                or target.stat().st_size != descriptor["size_bytes"]
                or checksum(target) != descriptor["sha256"]):
            raise ValueError("M10 bundle output failed its integrity check")
        validated[name] = (
            validate_candidate_accounting(target)
            if expected_type == "m10_candidate_accounting"
            else validate_repeat_evidence(target)
        )
    accounting = validated[_ACCOUNTING_NAME]
    evidence_count = validated[_EVIDENCE_NAME]["record_count"]
    accounting_header, candidate_rows = _candidate_rows(
        bundle_path.parent / _ACCOUNTING_NAME)
    if (accounting_header["candidate_set"].get("sha256")
            != candidate_source["sha256"]
            or accounting_header.get("context_artifacts")
            != source_inputs["optional_context"]
            or accounting_header.get("optional_context_state") != context_state
            or accounting_header.get("configuration") != bundle.get("configuration")
            or accounting_header.get("implementation") != bundle.get("implementation")
            or accounting_header.get("policy_ids") != bundle.get("policy_ids")):
        raise ValueError("M10 bundle provenance differs from candidate accounting")
    evidence_rows = iter(_read_lines(bundle_path.parent / _EVIDENCE_NAME))
    evidence = next(evidence_rows, None)
    previous_candidate_key = None
    for candidate in candidate_rows:
        candidate_key = (candidate["candidate_id"], candidate["sequence_id"])
        if previous_candidate_key is not None and candidate_key <= previous_candidate_key:
            raise ValueError("M10 candidate records are not in canonical order")
        previous_candidate_key = candidate_key
        observed = {branch_id: 0 for branch_id in _BRANCHES}
        previous_branch_index = -1
        while evidence is not None:
            evidence_key = (evidence["candidate_id"], evidence["sequence_id"])
            if evidence_key < candidate_key:
                raise ValueError("M10 evidence refers to an unaccounted candidate")
            if evidence_key > candidate_key:
                break
            branch_id = evidence["branch_id"]
            branch_index = _BRANCHES.index(branch_id)
            if branch_index < previous_branch_index:
                raise ValueError("M10 evidence branches are not in canonical order")
            previous_branch_index = branch_index
            branch = candidate["branches"][branch_id]
            source_artifact = candidate["source_artifact"]
            view = (
                candidate["comparison_view"]
                if evidence["orientation"] == "DIRECT"
                else candidate["reverse_complement_view"]
            )
            if (candidate["source_sha256"] != evidence["source_sha256"]
                    or candidate["source_length"]
                    != evidence["source_sequence_length"]
                    or candidate["configuration_sha256"]
                    != evidence["configuration_sha256"]
                    or candidate["candidate_set_sha256"]
                    != evidence["candidate_set_sha256"]
                    or source_artifact.get("artifact_id")
                    != evidence["source_artifact_id"]
                    or source_artifact.get("sha256")
                    != evidence["source_artifact_sha256"]
                    or candidate["completeness_state"]
                    != evidence["completeness_state"]
                    or candidate["terminal_boundaries_resolved"]
                    != evidence["terminal_boundaries_resolved"]
                    or not isinstance(view, dict)
                    or view.get("digest") != evidence["view_digest"]
                    or branch.get("branch_status") != evidence["branch_status"]
                    or branch.get("evidence_status") != evidence["evidence_status"]
                    or evidence["policy_ids"] != bundle.get("policy_ids")
                    or not _matches_source(candidate, evidence)):
                raise ValueError("M10 evidence is not bound to its candidate source")
            observed[branch_id] += 1
            evidence = next(evidence_rows, None)
        for branch_id in _BRANCHES:
            expected_count = candidate["branches"][branch_id]["evidence_rows"]
            if expected_count != observed[branch_id]:
                raise ValueError("M10 evidence row count disagrees with branch accounting")
    if evidence is not None:
        raise ValueError("M10 evidence refers to an unaccounted candidate")
    if (accounting["candidate_count"] != bundle.get("candidate_count")
            or accounting["input_status"] != bundle["input_status"]
            or accounting["aggregate_status"] != bundle["aggregate_status"]
            or accounting["configuration_sha256"] != bundle.get("configuration_sha256")
            or evidence_count != accounting["accounted_evidence_rows"]):
        raise ValueError("M10 result bundle disagrees with its accounting artifacts")
    _hash(bundle.get("configuration_sha256"), "configuration_sha256")
    if not isinstance(bundle.get("implementation"), dict):
        raise ValueError("M10 bundle implementation identity is missing")
    return {
        "schema": bundle["schema"],
        "record_count": accounting["candidate_count"],
        "aggregate_status": bundle["aggregate_status"],
        "input_status": bundle["input_status"],
        "evidence_count": evidence_count,
    }