"""Validation of a generic, offline M9 protein reference snapshot.

The exact v1 schema is a JSON object with ``schema`` equal to
``m9-protein-reference-snapshot-v1``, ``snapshot_id``, ``snapshot_digest``
(SHA-256 of canonical JSON with that member omitted), ``payload_sha256``,
``completeness`` (``complete`` or ``incomplete``), ``records`` (a list), and
``provenance``.  Each record has unique ``record_id``, ``accession_version``,
``role``, ``length``, and ``sha256`` (the SHA-256 of its exact FASTA letters).
Provenance has non-empty ``source``, ``release``, ``rights``, and ``terms``.
The separately supplied FASTA is hashed byte-for-byte and must contain exactly
the manifest records, in any order.  Sequences use only the IUPAC-like protein
alphabet ``ACDEFGHIKLMNPQRSTVWYBXZJUO*`` (case is normalized for checking);
this module never retrieves or interprets biological resources.
"""
import hashlib
import json
import re
from pathlib import Path

ALPHABET = frozenset("ACDEFGHIKLMNPQRSTVWYBXZJUO*")
SCHEMA = "m9-protein-reference-snapshot-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReferenceSnapshotError(ValueError):
    """Base class for malformed or unusable snapshots."""


class ReferenceSnapshotInvalid(ReferenceSnapshotError):
    """Manifest or payload contradicts the declared snapshot."""


class ReferenceSnapshotIncomplete(ReferenceSnapshotError):
    """The declared snapshot is incomplete and cannot support a no-hit."""


def _digest_object(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _fasta(data):
    try:
        text = data.decode("utf-8") if isinstance(data, bytes) else data
    except UnicodeDecodeError as error:
        raise ReferenceSnapshotInvalid("FASTA is not valid UTF-8") from error
    if not isinstance(text, str):
        raise ReferenceSnapshotInvalid("FASTA must be bytes or text")
    records = {}
    current = None
    for line in text.splitlines():
        if line.startswith(">"):
            tokens = line[1:].strip().split()
            ident = tokens[0] if tokens else ""
            if (not ident or ident in records or not all(
                    ord(c) < 128 and (c.isalnum() or c in "._:-") for c in ident)):
                raise ReferenceSnapshotInvalid("duplicate or empty FASTA identifier")
            current, records[ident] = "", ""
        elif current is None:
            if line.strip():
                raise ReferenceSnapshotInvalid("FASTA sequence precedes header")
        else:
            sequence = "".join(line.split())
            if sequence:
                records[current] += sequence
        if line.startswith(">"):
            current = ident
    if not records:
        raise ReferenceSnapshotInvalid("FASTA contains no records")
    return records


def validate_snapshot(manifest, payload, *, require_complete=True):
    """Validate and return ``{"reference_map": ..., "provenance": ...}``.

    ``payload`` is a FASTA path or bytes/string.  Incomplete manifests raise
    :class:`ReferenceSnapshotIncomplete` after structural validation.
    """
    if not isinstance(manifest, dict):
        raise ReferenceSnapshotInvalid("manifest must be an object")
    required = {"schema", "snapshot_id", "snapshot_digest", "payload_sha256",
                "completeness", "records", "provenance"}
    if not required <= set(manifest):
        raise ReferenceSnapshotInvalid("manifest is missing required fields")
    if manifest["schema"] != SCHEMA or not isinstance(manifest["snapshot_id"], str) or not manifest["snapshot_id"]:
        raise ReferenceSnapshotInvalid("invalid schema or snapshot_id")
    if (not isinstance(manifest.get("snapshot_digest"), str)
            or not _SHA256.fullmatch(manifest["snapshot_digest"])):
        raise ReferenceSnapshotInvalid("invalid snapshot digest")
    if manifest["snapshot_digest"] != _digest_object({k: v for k, v in manifest.items()
                                                        if k != "snapshot_digest"}):
        raise ReferenceSnapshotInvalid("snapshot_digest mismatch")
    if not isinstance(manifest["payload_sha256"], str) or not _SHA256.fullmatch(manifest["payload_sha256"]):
        raise ReferenceSnapshotInvalid("invalid payload hash")
    if not isinstance(manifest["completeness"], str) or manifest["completeness"] not in {"complete", "incomplete"}:
        raise ReferenceSnapshotInvalid("invalid completeness")
    if type(require_complete) is not bool:
        raise ReferenceSnapshotInvalid("require_complete must be boolean")
    provenance = manifest["provenance"]
    if not isinstance(provenance, dict) or any(not isinstance(provenance.get(k), str) or not provenance[k]
                                               for k in ("source", "release", "rights", "terms")):
        raise ReferenceSnapshotInvalid("incomplete provenance")
    records = manifest["records"]
    if not isinstance(records, list):
        raise ReferenceSnapshotInvalid("records must be a list")
    if manifest["completeness"] == "complete" and not records:
        raise ReferenceSnapshotInvalid("complete reference snapshot contains no records")
    ids = set(); accessions = set(); roles = set(); expected = {}
    for row in records:
        if not isinstance(row, dict) or any(k not in row for k in
                ("record_id", "accession_version", "role", "length", "sha256")):
            raise ReferenceSnapshotInvalid("invalid record")
        rid, acc, role = row["record_id"], row["accession_version"], row["role"]
        if (not all(isinstance(x, str) and x and all(ord(c) < 128 and (c.isalnum() or c in "._:-") for c in x)
                    for x in (rid, acc, role)) or rid in ids or acc in accessions):
            raise ReferenceSnapshotInvalid("record identifiers must be unique")
        if (type(row["length"]) is not int or row["length"] < 1
                or not isinstance(row["sha256"], str)
                or not _SHA256.fullmatch(row["sha256"])):
            raise ReferenceSnapshotInvalid("invalid record length or hash")
        ids.add(rid); accessions.add(acc); roles.add(role); expected[rid] = row
    if isinstance(payload, (str, Path)) and Path(payload).exists():
        raw = Path(payload).read_bytes()
        fasta = _fasta(raw)
    else:
        raw = payload.encode() if isinstance(payload, str) else payload
        if not isinstance(raw, bytes):
            raise ReferenceSnapshotInvalid("payload must be FASTA path or bytes")
        fasta = _fasta(raw)
    if hashlib.sha256(raw).hexdigest() != manifest["payload_sha256"]:
        raise ReferenceSnapshotInvalid("payload_sha256 mismatch")
    if set(fasta) != set(expected):
        raise ReferenceSnapshotInvalid("FASTA membership mismatch")
    reference_map = {}
    for rid, row in expected.items():
        seq = fasta[rid]
        if not seq or any(c.upper() not in ALPHABET for c in seq):
            raise ReferenceSnapshotInvalid("invalid protein alphabet")
        if len(seq) != row["length"] or hashlib.sha256(seq.encode()).hexdigest() != row["sha256"]:
            raise ReferenceSnapshotInvalid("sequence length/hash mismatch")
        reference_map[rid] = dict(row, sequence=seq)
    result = {"reference_map": reference_map, "provenance": dict(provenance),
              "snapshot_id": manifest["snapshot_id"], "snapshot_digest": manifest["snapshot_digest"],
              "payload_sha256": manifest["payload_sha256"], "completeness": manifest["completeness"]}
    if manifest["completeness"] != "complete" and require_complete:
        raise ReferenceSnapshotIncomplete("snapshot is declared incomplete")
    return result


def reference_map_and_provenance(manifest, payload):
    """Compatibility convenience returning the validated mapping and provenance."""
    result = validate_snapshot(manifest, payload)
    return result["reference_map"], result


def validate_reference_snapshot(manifest, payload):
    """Explicitly named alias for :func:`validate_snapshot`."""
    return validate_snapshot(manifest, payload)