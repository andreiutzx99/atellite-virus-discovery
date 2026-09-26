"""Typed M6-to-M8 candidate-sequence handoff validation.

This module describes sequence and provenance artifacts only. It does not
search references or assign biological roles.
"""
import hashlib
import json
from pathlib import Path
import re


SCHEMA = "m8-candidate-sequence-set-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DNA_IUPAC = frozenset("ACGTURYSWKMBDHVN")
_AVAILABILITY_STATES = frozenset({
    "AVAILABLE",
    "PARTIALLY_AVAILABLE",
    "UPSTREAM_UNAVAILABLE",
    "INVALID_OUTPUT",
    "COMPLETE_EMPTY",
})


def _is_sha256(value):
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fasta_record_metadata(path):
    """Return FASTA IDs, exact sequence-string hashes, and lengths.

    Line wrapping is not part of the sequence digest. Letter case is retained;
    whitespace, empty records, duplicate IDs, and non-IUPAC nucleotide symbols
    are rejected. No minimum sequence length is imposed beyond non-empty bytes.
    """
    records = []
    seen = set()
    current_id = None
    current_digest = None
    current_length = 0

    def finish_record():
        if current_id is None:
            return
        if current_length < 1:
            raise ValueError(f"FASTA record {current_id!r} has no sequence bytes")
        records.append({
            "fasta_record_id": current_id,
            "sequence_length": current_length,
            "sequence_sha256": current_digest.hexdigest(),
        })

    with Path(path).open("rb") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            line = raw_line.rstrip(b"\r\n")
            if not line:
                continue
            if line.startswith(b">"):
                finish_record()
                header = line[1:].split(None, 1)[0] if line[1:].strip() else b""
                if not header:
                    raise ValueError(f"FASTA header on line {line_number} is empty")
                try:
                    current_id = header.decode("ascii")
                except UnicodeDecodeError as exc:
                    raise ValueError("FASTA identifiers must be ASCII") from exc
                if current_id in seen:
                    raise ValueError(f"Duplicate FASTA identifier: {current_id!r}")
                seen.add(current_id)
                current_digest = hashlib.sha256()
                current_length = 0
                continue
            if current_id is None:
                raise ValueError("FASTA sequence data appears before the first header")
            if any(byte in b" \t\v\f" for byte in line):
                raise ValueError(f"Whitespace inside FASTA sequence on line {line_number}")
            try:
                letters = line.decode("ascii")
            except UnicodeDecodeError as exc:
                raise ValueError("FASTA sequence bytes must be ASCII") from exc
            if any(letter.upper() not in _DNA_IUPAC for letter in letters):
                raise ValueError(f"Invalid nucleotide symbol on FASTA line {line_number}")
            current_digest.update(line)
            current_length += len(line)

    finish_record()
    if not records:
        raise ValueError("FASTA contains no sequence records")
    return records


def _require_mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _validate_artifact_ref(value, label):
    value = _require_mapping(value, label)
    artifact_path = _require_text(value.get("path"), f"{label}.path")
    parsed_path = Path(artifact_path)
    if parsed_path.is_absolute() or ".." in parsed_path.parts:
        raise ValueError(f"{label}.path must remain within the producer artifact")
    if not _is_sha256(value.get("sha256")):
        raise ValueError(f"{label}.sha256 must be a lowercase SHA-256 digest")
    return value


def _verify_artifact_ref(path, artifact_ref, label):
    if artifact_ref is None:
        return
    root = Path(path).parent.resolve()
    target = (Path(path).parent / artifact_ref["path"])
    if target.is_symlink() or not target.is_file():
        raise ValueError(f"{label} is missing or is not a regular artifact file")
    resolved = target.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{label} resolves outside the producer artifact")
    if _file_sha256(resolved) != artifact_ref["sha256"]:
        raise ValueError(f"{label} checksum does not match its manifest")


def validate_candidate_sequence_set(path):
    """Validate a candidate-set manifest and any paired FASTA bytes."""
    path = Path(path)
    if path.stat().st_size > 32_000_000:
        raise ValueError("Candidate-sequence manifest exceeds the 32 MB limit")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Candidate-sequence manifest is not valid UTF-8 JSON") from exc
    document = _require_mapping(document, "Candidate-sequence manifest")
    if document.get("schema") != SCHEMA:
        raise ValueError("Candidate-sequence manifest schema is unsupported")

    producer = _require_mapping(document.get("producer"), "producer")
    if producer.get("stage_kind") != "residual_evidence":
        raise ValueError("Candidate producer must identify the M6 residual-evidence stage")
    _require_text(producer.get("stage_id"), "producer.stage_id")
    _require_text(producer.get("adapter_name"), "producer.adapter_name")
    _require_text(producer.get("adapter_version"), "producer.adapter_version")

    source_artifact = document.get("source_artifact")
    if source_artifact is not None:
        _validate_artifact_ref(source_artifact, "source_artifact")
        _verify_artifact_ref(path, source_artifact, "source_artifact")
    assembly_manifest = document.get("assembly_manifest")
    assembly_manifest_details = None
    if assembly_manifest is not None:
        _validate_artifact_ref(assembly_manifest, "assembly_manifest")
        _verify_artifact_ref(path, assembly_manifest, "assembly_manifest")
        from .artifact_contracts import validate_artifact
        assembly_manifest_details = validate_artifact(
            path.parent / assembly_manifest["path"], "assembly_manifest")
        assembly_contig_count = assembly_manifest_details.get("record_count")
        if type(assembly_contig_count) is not int or assembly_contig_count < 0:
            raise ValueError(
                "Assembly manifest must declare a non-negative contig_count")

    m6_evidence = _require_mapping(document.get("m6_evidence"), "m6_evidence")
    _require_text(m6_evidence.get("reconstruction_status"),
                  "m6_evidence.reconstruction_status")
    _require_text(m6_evidence.get("support_status"), "m6_evidence.support_status")
    evidence_artifact = _validate_artifact_ref(
        m6_evidence.get("artifact"), "m6_evidence.artifact")
    if evidence_artifact["path"] != "reconstruction_evidence.json":
        raise ValueError("M6 evidence must reference reconstruction_evidence.json")
    _verify_artifact_ref(path, evidence_artifact, "M6 reconstruction evidence")

    m7_context = document.get("m7_context")
    if m7_context is not None:
        raise ValueError(
            "M7 artifacts must be supplied separately as typed optional M8 inputs; "
            "the M6 candidate-set artifact cannot embed M7 context")

    availability = _require_mapping(document.get("availability"), "availability")
    state = availability.get("state")
    if state not in _AVAILABILITY_STATES:
        raise ValueError("Candidate sequence availability state is not recognized")
    reason = availability.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ValueError("availability.reason must be text or null")
    fasta_ref = availability.get("fasta_artifact")
    if fasta_ref is not None:
        fasta_ref = _validate_artifact_ref(fasta_ref, "availability.fasta_artifact")
        if fasta_ref["path"] != "candidate_sequences.fasta":
            raise ValueError("Candidate FASTA must be named candidate_sequences.fasta")

    records = document.get("records")
    if not isinstance(records, list):
        raise ValueError("Candidate records must be an array")
    if type(availability.get("record_count")) is not int:
        raise ValueError("availability.record_count must be an integer")
    if availability["record_count"] != len(records):
        raise ValueError("Candidate record count does not match the manifest")

    candidate_ids = set()
    sequence_ids = set()
    available_records = {}
    unavailable_count = 0
    for index, raw_record in enumerate(records):
        record = _require_mapping(raw_record, f"records[{index}]")
        for field in ("candidate_id", "sequence_id", "source_artifact_id",
                      "m6_support_status", "completeness_state"):
            _require_text(record.get(field), f"records[{index}].{field}")
        if record.get("molecule_type") is not None:
            _require_text(record["molecule_type"], f"records[{index}].molecule_type")
        if record["candidate_id"] in candidate_ids:
            raise ValueError("Candidate IDs must be unique within an observation set")
        if record["sequence_id"] in sequence_ids:
            raise ValueError("Sequence IDs must be unique within an observation set")
        candidate_ids.add(record["candidate_id"])
        sequence_ids.add(record["sequence_id"])

        if record.get("molecule_type") is not None:
            _require_text(record["molecule_type"], f"records[{index}].molecule_type")
        if record.get("sequence_bytes_available") is True:
            alphabet = _require_text(
                record.get("sequence_alphabet"),
                f"records[{index}].sequence_alphabet")
            if alphabet != "IUPAC_NUCLEOTIDE":
                raise ValueError(
                    "Available candidate sequences must declare "
                    "sequence_alphabet IUPAC_NUCLEOTIDE")
            fasta_id = _require_text(
                record.get("fasta_record_id"), f"records[{index}].fasta_record_id")
            length = record.get("sequence_length")
            if type(length) is not int or length < 1:
                raise ValueError("Available sequences require a positive sequence length")
            if not _is_sha256(record.get("sequence_sha256")):
                raise ValueError("Available sequences require an exact sequence SHA-256")
            if record.get("sequence_unavailable_reason") is not None:
                raise ValueError("Available sequences cannot have an unavailable reason")
            if not _is_sha256(record.get("source_artifact_sha256")):
                raise ValueError("Available sequences require their source artifact hash")
            if (source_artifact is None
                    or record["source_artifact_id"] != source_artifact["path"]
                    or record["source_artifact_sha256"] != source_artifact["sha256"]):
                raise ValueError("Candidate record source identity conflicts with its set")
            if fasta_id in available_records:
                raise ValueError("FASTA record IDs must be unique in the candidate set")
            available_records[fasta_id] = record
        elif record.get("sequence_bytes_available") is False:
            unavailable_count += 1
            if record.get("fasta_record_id") is not None:
                raise ValueError("Unavailable sequences cannot name a FASTA record")
            if record.get("sequence_length") is not None:
                raise ValueError("Unavailable sequences cannot claim a sequence length")
            if record.get("sequence_sha256") is not None:
                raise ValueError("Unavailable sequences cannot claim a sequence hash")
            _require_text(record.get("sequence_unavailable_reason"),
                          f"records[{index}].sequence_unavailable_reason")
        else:
            raise ValueError("sequence_bytes_available must be boolean")

    if records:
        if assembly_manifest_details is None:
            raise ValueError(
                "Candidate records require a validated completed assembly manifest")
        if assembly_manifest_details["record_count"] != len(records):
            raise ValueError(
                "Assembly contig_count does not match the complete candidate record set")

    if state == "AVAILABLE" and (not records or unavailable_count):
        raise ValueError("AVAILABLE requires non-empty records with all sequence bytes")
    if state == "PARTIALLY_AVAILABLE" and (
            not available_records or not unavailable_count):
        raise ValueError("PARTIALLY_AVAILABLE requires available and unavailable records")
    if state in {"UPSTREAM_UNAVAILABLE", "INVALID_OUTPUT"}:
        _require_text(reason, "availability.reason")
        if records or fasta_ref is not None:
            raise ValueError(f"{state} cannot silently contain a partial sequence set")
    if state == "COMPLETE_EMPTY" and (records or reason is not None):
        raise ValueError("COMPLETE_EMPTY requires no records and no failure reason")
    if state in {"AVAILABLE", "PARTIALLY_AVAILABLE"} and fasta_ref is None:
        raise ValueError(f"{state} requires a candidate FASTA artifact")
    if available_records and source_artifact is None:
        raise ValueError("Available sequences require a source artifact identity")

    if fasta_ref is not None:
        fasta_path = path.parent / fasta_ref["path"]
        if not fasta_path.is_file():
            raise ValueError("Candidate FASTA artifact is missing")
        if _file_sha256(fasta_path) != fasta_ref["sha256"]:
            raise ValueError("Candidate FASTA checksum does not match its manifest")
        parsed = fasta_record_metadata(fasta_path)
        parsed_by_id = {row["fasta_record_id"]: row for row in parsed}
        if set(parsed_by_id) != set(available_records):
            raise ValueError("Candidate FASTA IDs do not match available manifest records")
        for fasta_id, record in available_records.items():
            observed = parsed_by_id[fasta_id]
            if (observed["sequence_length"] != record["sequence_length"]
                    or observed["sequence_sha256"] != record["sequence_sha256"]):
                raise ValueError(
                    f"Candidate FASTA sequence identity mismatch for {fasta_id!r}")
    elif available_records:
        raise ValueError("Available candidate bytes require a FASTA artifact")

    return {
        "availability_state": state,
        "record_count": len(records),
        "available_sequence_count": len(available_records),
    }