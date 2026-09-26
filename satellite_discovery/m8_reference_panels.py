"""Validation of immutable, externally materialized M8 reference snapshots.

This module deliberately does not acquire, build, or redistribute reference
data.  A snapshot manifest is provenance and an integrity contract; sequence
and BLAST database files are supplied by the caller and checked read-only.
"""

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import re

from .m8_contracts import normalize_panel_role


SCHEMA = "m8-reference-snapshot-manifest-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ACCESSION = re.compile(r"^[A-Za-z][A-Za-z0-9_]*\.[0-9]+$")
_DNA = frozenset("ACGTURYSWKMBDHVN")


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    return value


def _mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _digest(value, label):
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _canonical_digest(document):
    material = {
        key: value for key, value in document.items()
        if key not in {"snapshot_digest", "snapshot_digest_algorithm"}
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _digest_bytes(encoded)


def _parse_fasta(path):
    """Return ordered (identifier, uppercase sequence) records.

    FASTA headers use the first whitespace-delimited token as the stable
    accession.version identifier.  No sequence transformation other than
    uppercasing for the declared record digest is performed.
    """
    records = []
    seen = set()
    current_id = None
    sequence = []

    def finish():
        if current_id is None:
            return
        if not sequence:
            raise ValueError(f"FASTA record {current_id!r} is empty")
        value = "".join(sequence)
        records.append((current_id, value))

    try:
        with Path(path).open("rb") as handle:
            for number, raw in enumerate(handle, 1):
                line = raw.rstrip(b"\r\n")
                if not line:
                    continue
                if line.startswith(b">"):
                    finish()
                    token = line[1:].split(None, 1)[0] if line[1:].strip() else b""
                    try:
                        current_id = token.decode("ascii")
                    except UnicodeDecodeError as error:
                        raise ValueError("FASTA identifiers must be ASCII") from error
                    if not current_id:
                        raise ValueError(f"FASTA header on line {number} is empty")
                    if current_id in seen:
                        raise ValueError(f"Duplicate FASTA identifier: {current_id!r}")
                    seen.add(current_id)
                    sequence = []
                    continue
                if current_id is None:
                    raise ValueError("FASTA sequence appears before its first header")
                try:
                    text = line.decode("ascii")
                except UnicodeDecodeError as error:
                    raise ValueError("FASTA sequence must be ASCII") from error
                if any(character.upper() not in _DNA for character in text):
                    raise ValueError(f"Invalid nucleotide symbol on FASTA line {number}")
                sequence.append(text)
    except OSError as error:
        raise ValueError(f"Unable to read external FASTA: {path}") from error
    finish()
    if not records:
        raise ValueError("External FASTA contains no records")
    return records


def _validate_manifest(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Snapshot manifest must be a regular file")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Snapshot manifest is not valid UTF-8 JSON") from error
    _mapping(document, "Snapshot manifest")
    if document.get("schema") != SCHEMA:
        raise ValueError("Unsupported M8 snapshot manifest schema")
    _text(document.get("snapshot_id"), "snapshot_id")
    _text(document.get("retrieved_utc"), "retrieved_utc")
    _text(document.get("provider"), "provider")
    _text(document.get("database"), "database")
    _text(document.get("normalization"), "normalization")
    _text(document.get("taxonomy_provenance"), "taxonomy_provenance")

    rights = _mapping(document.get("rights"), "rights")
    for field in (
        "redistribution_class", "record_scan", "analysis_disposition",
        "redistribution_disposition", "publication_supplements",
    ):
        _text(rights.get(field), f"rights.{field}")
    policies = rights.get("provider_policy_urls")
    if not isinstance(policies, list) or not policies or not all(
        isinstance(item, str) and item.strip() for item in policies
    ):
        raise ValueError("rights.provider_policy_urls must be non-empty text entries")
    panel = _mapping(document.get("panel_fasta"), "panel_fasta")
    filename = _text(panel.get("external_filename"), "panel_fasta.external_filename")
    if Path(filename).name != filename or Path(filename).is_absolute():
        raise ValueError("panel_fasta.external_filename must be a simple filename")
    _digest(panel.get("sha256"), "panel_fasta.sha256")
    for field in ("size_bytes", "record_count", "total_bases"):
        minimum = 1
        if type(panel.get(field)) is not int or panel[field] < minimum:
            raise ValueError(f"panel_fasta.{field} must be a non-negative integer")

    toolchain = _mapping(document.get("blast_toolchain"), "blast_toolchain")
    for field in ("release", "makeblastdb_command", "index_validation"):
        _text(toolchain.get(field), f"blast_toolchain.{field}")
    # The manifest is the only portable description of an externally built
    # BLAST database.  Require an explicit membership validation statement;
    # file hashes alone cannot establish that an index contains every declared
    # accession (or that it contains no stale membership).
    validation_text = toolchain["index_validation"].lower()
    if "blastdbcmd" not in validation_text or "same" not in validation_text or "id" not in validation_text:
        raise ValueError(
            "blast_toolchain.index_validation must record complete BLAST "
            "membership validation with blastdbcmd"
        )
    if toolchain.get("database_search_performed") is not False:
        raise ValueError("Snapshot manifest must record database_search_performed=false")
    indexes = toolchain.get("index_files_external")
    if not isinstance(indexes, list) or not indexes:
        raise ValueError("blast_toolchain.index_files_external must be non-empty")
    index_names = set()
    core_suffixes = {".ndb", ".nhr", ".nin", ".not", ".nsq", ".ntf", ".nto"}
    for index in indexes:
        index = _mapping(index, "index_files_external entry")
        name = _text(index.get("filename"), "index filename")
        if Path(name).name != name or Path(name).is_absolute() or name in index_names:
            raise ValueError("Index filenames must be unique simple filenames")
        index_names.add(name)
        _digest(index.get("sha256"), f"index {name} sha256")
        if type(index.get("size_bytes")) is not int or index["size_bytes"] < 1:
            raise ValueError(f"index {name} size_bytes must be positive")
    if {Path(name).suffix for name in index_names} < core_suffixes:
        raise ValueError(
            "BLASTDB v5 index is incomplete; required core suffixes are missing"
        )

    records = document.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("Snapshot records must be a non-empty array")
    accessions = set()
    normalized = []
    for number, raw in enumerate(records):
        record = _mapping(raw, f"records[{number}]")
        accession = _text(record.get("accession_version"), f"records[{number}].accession_version")
        if not _ACCESSION.fullmatch(accession):
            raise ValueError(f"Invalid accession.version: {accession!r}")
        if accession in accessions:
            raise ValueError(f"Duplicate accession.version: {accession}")
        accessions.add(accession)
        try:
            role = normalize_panel_role(
                record.get("role"), record.get("subrole"),
                accession_version=accession,
            )
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid role for {accession}: {error}") from error
        _text(record.get("curation_state"), f"records[{number}].curation_state")
        for field in ("taxid", "source_organism"):
            if record.get(field) is not None and (
                field == "source_organism" and
                (not isinstance(record[field], str) or not record[field].strip())
            ):
                raise ValueError(f"records[{number}].{field} must be text or null")
        studies = record.get("source_study_ids")
        if not isinstance(studies, list) or not all(
            isinstance(item, str) and item.strip() for item in studies
        ):
            raise ValueError(f"records[{number}].source_study_ids must be text entries")
        if record.get("taxid") is not None and (
            type(record["taxid"]) is not int or record["taxid"] < 0
        ):
            raise ValueError(f"records[{number}].taxid must be a non-negative integer or null")
        if type(record.get("length")) is not int or record["length"] < 1:
            raise ValueError(f"records[{number}].length must be positive")
        _digest(record.get("sequence_sha256"), f"records[{number}].sequence_sha256")
        _digest(record.get("source_response_sha256"), f"records[{number}].source_response_sha256")
        normalized.append({**record, **role})

    expected_digest = _digest(document.get("snapshot_digest"), "snapshot_digest")
    if _canonical_digest(document) != expected_digest:
        raise ValueError("Snapshot manifest canonical digest does not match")
    return document, normalized, filename, indexes


def validate_snapshot_manifest(path):
    """Validate metadata and return a JSON-safe snapshot identity summary."""
    document, records, panel_filename, indexes = _validate_manifest(path)
    roles = sorted({record["role"] for record in records})
    membership = [
        {"accession_version": record["accession_version"],
         "role": record["role"], "subrole": record.get("subrole")}
        for record in records
    ]
    membership_digest = _digest_bytes(
        json.dumps(membership, sort_keys=True, separators=(",", ":")).encode()
    )
    return {
        "snapshot_id": document["snapshot_id"],
        "snapshot_digest": document["snapshot_digest"],
        "schema": SCHEMA,
        "panel_fasta_filename": panel_filename,
        "roles": roles,
        "membership_digest": membership_digest,
        "references": records,
        "index_files": [
            {"filename": item["filename"], "sha256": item["sha256"],
             "size_bytes": item["size_bytes"]}
            for item in indexes
        ],
        "rights": {
            "redistribution_class": document["rights"]["redistribution_class"],
            "redistribution_disposition": document["rights"]["redistribution_disposition"],
        },
    }


def validate_external_snapshot_files(manifest_path, payload_files: Mapping[str, Path]):
    """Verify explicitly supplied FASTA/index files against a snapshot manifest."""
    if not isinstance(payload_files, Mapping):
        raise ValueError("payload_files must be a mapping of manifest filenames to paths")
    document, records, panel_filename, indexes = _validate_manifest(manifest_path)
    expected = {panel_filename} | {item["filename"] for item in indexes}
    supplied = set(payload_files)
    if supplied != expected:
        missing = sorted(expected - supplied)
        extra = sorted(supplied - expected)
        raise ValueError(f"External payload mapping mismatch (missing={missing}, extra={extra})")

    paths = {}
    for name in sorted(expected):
        value = Path(payload_files[name])
        if value.is_symlink() or not value.is_file():
            raise ValueError(f"External payload {name!r} must be a regular file")
        paths[name] = value.resolve()
    panel_path = paths[panel_filename]
    panel = document["panel_fasta"]
    if _sha256(panel_path) != panel["sha256"] or panel_path.stat().st_size != panel["size_bytes"]:
        raise ValueError("External panel FASTA hash or size does not match manifest")
    observed = _parse_fasta(panel_path)
    if len(observed) != panel["record_count"] or sum(len(seq) for _, seq in observed) != panel["total_bases"]:
        raise ValueError("External FASTA record count or base total does not match manifest")
    by_id = {identifier: sequence for identifier, sequence in observed}
    expected_ids = {record["accession_version"] for record in records}
    if set(by_id) != expected_ids:
        raise ValueError("External FASTA accession.version membership does not match manifest")
    for record in records:
        sequence = by_id[record["accession_version"]]
        if len(sequence) != record["length"] or _digest_bytes(sequence.upper().encode("ascii")) != record["sequence_sha256"]:
            raise ValueError(f"External sequence identity mismatch for {record['accession_version']}")

    index_identity = []
    for index in indexes:
        path = paths[index["filename"]]
        if _sha256(path) != index["sha256"] or path.stat().st_size != index["size_bytes"]:
            raise ValueError(f"External BLAST index mismatch for {index['filename']}")
        index_identity.append({
            "filename": index["filename"], "path": str(path),
            "sha256": index["sha256"], "size_bytes": index["size_bytes"],
        })
    result = validate_snapshot_manifest(manifest_path)
    result["panel_fasta"] = {"filename": panel_filename, "path": str(panel_path),
                             "sha256": panel["sha256"], "size_bytes": panel["size_bytes"],
                             "record_count": panel["record_count"],
                             "total_bases": panel["total_bases"]}
    result["index_files"] = index_identity
    result["supplied_paths"] = {name: str(paths[name]) for name in sorted(paths)}
    return result