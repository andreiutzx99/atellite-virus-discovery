"""Pure policy and serialization helpers for the optional M11 RNA MFE stage."""

import hashlib
import json
import math


STAGE_VERSION = "1"
CONTRACT_VERSION = "m11-rna-mfe-v1"
ACCOUNTING_SCHEMA = "m11-candidate-accounting-v1"
FOLD_ACCOUNTING_SCHEMA = "m11-fold-accounting-v1"
EVIDENCE_SCHEMA = "m11-rna-structure-evidence-v1"
BUNDLE_SCHEMA = "m11-result-bundle-v1"
METHOD_ID = "VIENNARNA_SINGLE_SEQUENCE_MFE"
PROFILE_ID = "M11-VIENNARNA-MFE-TURNER2004-T37-DANGLES2-v1"
ENGINE_RELEASE = "2.7.2"
SOURCE_ALPHABET = frozenset("ACGTURYSWKMBDHVN")
CANONICAL_RNA = frozenset("ACGU")
CANONICAL_DNA = frozenset("ACGT")
POLICY_IDS = {
    "source_alphabet": "M11-IUPAC-ALPHABET-v1",
    "rna_view": "M11-RNA-VIEW-v1",
    "dna_conversion": "M11-DNA-T-TO-RNA-U-v1",
    "coordinate_system": "ZERO_BASED_HALF_OPEN_SOURCE",
    "orientation": "AS_SUPPLIED",
}


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def stable_request_id(candidate_id, sequence_id, source_sha256, start, end):
    key = [
        "M11-FOLD-REQUEST-v1", candidate_id, sequence_id, source_sha256,
        start, end, METHOD_ID, PROFILE_ID,
    ]
    return sha256(canonical_json(key).encode("utf-8"))


def stable_evidence_id(run_identity, request_id):
    return sha256(
        b"M11-RNA-STRUCTURE-EVIDENCE-v1\0"
        + run_identity.encode("ascii")
        + b"\0"
        + request_id.encode("ascii")
    )


def source_digest(sequence):
    return sha256(sequence.encode("ascii"))


def view_digest(view_bytes):
    return sha256(b"M11-RNA-VIEW-v1\0" + view_bytes)


def validate_source(sequence):
    """Return INPUT_INVALID for invalid source bytes; otherwise INPUT_VALID."""
    if not isinstance(sequence, str) or not sequence:
        return "INPUT_INVALID", None
    try:
        sequence.encode("ascii")
    except UnicodeEncodeError:
        return "INPUT_INVALID", None
    upper = sequence.upper()
    if any(symbol not in SOURCE_ALPHABET for symbol in upper):
        return "INPUT_INVALID", None
    return "INPUT_VALID", upper


def resolve_applicability(sequence_upper, molecule_type, start, end):
    """Apply the frozen status precedence and return status plus view metadata."""
    if (
        type(start) is not int or type(end) is not int
        or start < 0 or start >= end or end > len(sequence_upper)
    ):
        return "INPUT_INVALID", "NOT_EVALUATED", None

    declared = molecule_type.upper() if isinstance(molecule_type, str) else ""
    if declared not in {"RNA", "DNA"}:
        return "INSUFFICIENT_INFORMATION", "INSUFFICIENT_INFORMATION", None
    if (declared == "DNA" and "U" in sequence_upper) or (
        declared == "RNA" and "T" in sequence_upper
    ):
        return "INSUFFICIENT_INFORMATION", "INSUFFICIENT_INFORMATION", None

    selected = sequence_upper[start:end]
    canonical = CANONICAL_RNA if declared == "RNA" else CANONICAL_DNA
    if any(symbol not in canonical for symbol in selected):
        return "INPUT_VALID", "NOT_APPLICABLE", None

    source_slice = sequence_upper[start:end]
    view = source_slice.replace("T", "U") if declared == "DNA" else source_slice
    return "INPUT_VALID", "APPLICABLE", {
        "molecule_type": declared,
        "source_region_sequence": source_slice,
        "view_sequence": view,
        "view_sha256": view_digest(view.encode("ascii")),
        "view_length": len(view),
        "source_region": {"start": start, "end": end},
        "coordinate_map": {
            "kind": "IDENTITY_OFFSET",
            "view_start": 0,
            "view_end": len(view),
            "source_start": start,
            "source_end": end,
            "one_to_one": True,
        },
        "transformation": (
            "ASCII_UPPERCASE_AND_DNA_T_TO_RNA_U"
            if declared == "DNA"
            else "ASCII_UPPERCASE"
        ),
    }


def normalize_energy(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("ViennaRNA energy must be finite")
    return "0.00" if value == 0 else f"{value:.2f}"


def validate_dot_bracket(structure, expected_length):
    if not isinstance(structure, str) or len(structure) != expected_length:
        return False
    depth = 0
    for symbol in structure:
        if symbol == "(":
            depth += 1
        elif symbol == ")":
            depth -= 1
            if depth < 0:
                return False
        elif symbol != ".":
            return False
    return depth == 0


def axes_for_branch(branch_status):
    table = {
        "PREDICTION_REPORTED": (
            "INPUT_VALID", "APPLICABLE", "COMPLETED", "EVIDENCE_FOUND",
        ),
        "INPUT_INVALID": (
            "INPUT_INVALID", "NOT_EVALUATED", "NOT_STARTED",
            "NO_EVIDENCE_REPORTED",
        ),
        "SEQUENCE_UNAVAILABLE": (
            "SEQUENCE_UNAVAILABLE", "NOT_EVALUATED", "NOT_STARTED",
            "NO_EVIDENCE_REPORTED",
        ),
        "INSUFFICIENT_INFORMATION": (
            "INPUT_VALID", "INSUFFICIENT_INFORMATION", "NOT_STARTED",
            "NO_EVIDENCE_REPORTED",
        ),
        "NOT_APPLICABLE": (
            "INPUT_VALID", "NOT_APPLICABLE", "NOT_STARTED",
            "NO_EVIDENCE_REPORTED",
        ),
        "DEPENDENCY_UNAVAILABLE": (
            "INPUT_VALID", "APPLICABLE", "DEPENDENCY_UNAVAILABLE",
            "NO_EVIDENCE_REPORTED",
        ),
        "EXECUTION_FAILED": (
            "INPUT_VALID", "APPLICABLE", "EXECUTION_FAILED",
            "NO_EVIDENCE_REPORTED",
        ),
        "OUTPUT_INVALID": (
            "INPUT_VALID", "APPLICABLE", "OUTPUT_INVALID",
            "NO_EVIDENCE_REPORTED",
        ),
        "INTERRUPTED": (
            "INPUT_VALID", "APPLICABLE", "INTERRUPTED",
            "NO_EVIDENCE_REPORTED",
        ),
        "TRUNCATED": (
            "INPUT_VALID", "APPLICABLE", "TRUNCATED",
            "NO_EVIDENCE_REPORTED",
        ),
        "NOT_SELECTED": (
            "INPUT_VALID", "NOT_EVALUATED", "NOT_STARTED",
            "NO_EVIDENCE_REPORTED",
        ),
    }
    try:
        input_status, applicability, execution, evidence = table[branch_status]
    except KeyError as error:
        raise ValueError(f"Unsupported M11 branch status: {branch_status}") from error
    return {
        "input_status": input_status,
        "applicability_status": applicability,
        "execution_status": execution,
        "evidence_status": evidence,
        "branch_status": branch_status,
    }