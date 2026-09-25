"""Immutable, provenance-rich imports of FASTA records in verified snapshots."""
import csv
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import sqlite3

from . import __version__, reproducibility
from .portable_paths import portable_name
from .reference_snapshot import verified_snapshot
from .review_stage import execute
from .sequence_downloader import checksum, write_json

MAX_FILE_BYTES = 100_000_000
MAX_RECORDS = 10_000
MAX_BASES = 20_000_000
MAX_VALIDATION_ISSUES = 500
STAGE = "reference-record-import-v1"
OUTPUTS = ("records.csv", "records.fasta", "catalogue.sqlite", "snapshot.json",
           "conflicts.json", "validation.json", "report.html")

ALPHABET = set("ACGTURYSWKMBDHVN")
ACCESSION_VERSION = re.compile(
    r"(?P<accession>(?:[A-Z]{1,6}_\d{4,}|[A-Z]{1,4}\d{5,7}))\.(?P<version>\d+)\Z"
)
ACCESSION = re.compile(r"(?:[A-Z]{1,6}_\d{4,}|[A-Z]{1,4}\d{5,7})\Z")
FASTA_SUFFIXES = {".fa", ".fasta", ".fna"}

RECORD_FIELDS = (
    "record_id", "reference_id", "reference_file", "fasta_id", "original_header",
    "accession", "accession_version", "description", "display_name",
    "sequence_length", "sequence_sha256", "exact_sequence_group_size",
    "source", "category", "parent_snapshot_id", "parent_snapshot_checksum",
    "reference_version", "database_version", "imported_utc", "provenance_json",
)
METADATA_FIELDS = (
    "record_id", "reference_id", "reference_file", "fasta_id", "original_header",
    "accession", "accession_version", "description", "display_name",
    "sequence_length", "sequence_sha256", "exact_sequence_group_size",
    "source", "category", "parent_snapshot_id", "parent_snapshot_checksum",
    "reference_version", "database_version", "imported_utc", "provenance",
)


def _read_parent_table(path):
    supplied_path = Path(path)
    if supplied_path.is_symlink():
        raise ValueError("Reference snapshot table must not be a symbolic link")
    path = supplied_path.resolve(strict=True)
    if path.name != "references.csv":
        raise ValueError("Use references.csv from a completed reference snapshot")
    parent_rows, manifest = verified_snapshot(path.parent)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"name", "source", "version", "role", "snapshot_id", "reference_id"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("Reference snapshot table is missing provenance fields")
        rows = [{key: (value or "").strip() for key, value in row.items()}
                for row in reader]
    if rows != parent_rows:
        raise ValueError("Reference snapshot table changed during verification")
    snapshot_ids = {row.get("snapshot_id") for row in rows}
    if len(snapshot_ids) != 1 or not next(iter(snapshot_ids)):
        raise ValueError("Reference snapshot contains conflicting or missing snapshot IDs")
    for row in rows:
        if not portable_name(row.get("name", "")):
            raise ValueError("Unsafe reference filename in verified snapshot")
        raw_target = path.parent / row["name"]
        if raw_target.is_symlink():
            raise ValueError("Reference snapshot member must not be a symbolic link")
        target = raw_target.resolve(strict=True)
        if target.parent != path.parent.resolve() or not target.is_file():
            raise ValueError("Reference snapshot member is not a regular file")
    return path, path.parent.resolve(), rows, manifest, next(iter(snapshot_ids))


def _parse_accession(header, fasta_id):
    """Parse only explicit accession-shaped tokens; never derive an accession from sequence."""
    candidates = [fasta_id]
    candidates.extend(part for part in header.split("|") if part)
    for candidate in candidates:
        match = ACCESSION_VERSION.fullmatch(candidate)
        if match:
            return match.group("accession"), match.group("version")
        if ACCESSION.fullmatch(candidate):
            return candidate, None
    return None, None


def _stable_record_id(reference_id, fasta_id):
    key = (reference_id + "\0" + fasta_id).encode("utf-8")
    return "rr-" + hashlib.sha256(key).hexdigest()


def _parse_fasta(path, reference, record_limit=MAX_RECORDS, base_limit=MAX_BASES):
    errors = []
    records = []
    seen = {}
    header = None
    header_line = None
    chunks = []
    total_bases = 0

    def issue(code, message, line=None, identifier=None):
        if len(errors) < MAX_VALIDATION_ISSUES:
            row = {"code": code, "message": message, "file": reference["name"]}
            if line is not None:
                row["line"] = line
            if identifier is not None:
                row["fasta_id"] = identifier
            errors.append(row)

    def finish():
        nonlocal header, chunks
        if header is None:
            return
        if len(records) >= record_limit:
            issue("record_limit_exceeded", "FASTA exceeds the record limit", header_line)
            header, chunks = None, []
            return
        fasta_id = header.split()[0] if header.split() else ""
        if not fasta_id:
            issue("missing_identifier", "FASTA record has no identifier", header_line)
            header, chunks = None, []
            return
        sequence = "".join(chunks)
        if not sequence:
            issue("empty_sequence", "FASTA record has no nucleotide sequence",
                  header_line, fasta_id)
        if fasta_id in seen:
            issue("duplicate_identifier",
                  "FASTA identifier is repeated within this reference file",
                  header_line, fasta_id)
        else:
            seen[fasta_id] = header_line
        records.append({
            "fasta_id": fasta_id,
            "header": header,
            "description": header[len(fasta_id):].strip() or None,
            "sequence": sequence,
            "line": header_line,
            "reference": reference,
        })
        header, chunks = None, []

    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return [], [{"code": "file_too_large", "message": "FASTA exceeds the 100 MB input cap",
                         "file": reference["name"]}]
        with path.open(encoding="utf-8-sig") as source:
            for line_number, raw in enumerate(source, 1):
                line = raw.strip()
                if not line:
                    continue
                if line.startswith(">"):
                    finish()
                    if len(records) >= record_limit:
                        issue("record_limit_exceeded", "FASTA exceeds the record limit", line_number)
                        break
                    header = line[1:].strip()
                    header_line = line_number
                    chunks = []
                    if (not header or len(header) > 1000
                            or any(ord(char) < 32 for char in header)):
                        issue("invalid_header", "FASTA header is empty, too long or contains controls",
                              line_number)
                    else:
                        first = header.split()[0] if header.split() else ""
                        if not first or len(first) > 1000:
                            issue("invalid_identifier",
                                  "FASTA identifier is empty or longer than 1,000 characters",
                                  line_number, first or None)
                    continue
                if header is None:
                    issue("sequence_before_header", "Sequence appears before a FASTA header",
                          line_number)
                    continue
                sequence = "".join(line.split()).upper()
                invalid = sorted(set(sequence) - ALPHABET)
                if invalid:
                    issue("invalid_nucleotide_symbol",
                          "Unsupported nucleotide symbol(s): " + "".join(invalid),
                          line_number, header.split()[0] if header.split() else None)
                total_bases += len(sequence)
                if total_bases > base_limit:
                    issue("base_limit_exceeded", "FASTA exceeds the configured base limit",
                          line_number)
                    break
                chunks.append(sequence)
            finish()
    except UnicodeDecodeError:
        issue("invalid_encoding", "FASTA is not valid UTF-8 text")
    except OSError as exc:
        issue("file_read_error", "Unable to read FASTA: " + str(exc))

    if not records and not errors:
        issue("no_records", "FASTA contains no sequence records")
    return records, errors


def _write_csv(path, records):
    with Path(path).open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=RECORD_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            writer.writerow({**row, "provenance_json": json.dumps(row["provenance"], sort_keys=True)})


def _create_database(path, records):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("""CREATE TABLE sequences (
            sha256 TEXT PRIMARY KEY,
            sequence TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE records (
            record_id TEXT PRIMARY KEY,
            reference_id TEXT NOT NULL,
            reference_file TEXT NOT NULL,
            fasta_id TEXT NOT NULL,
            original_header TEXT NOT NULL,
            accession TEXT,
            accession_version TEXT,
            description TEXT,
            display_name TEXT,
            sequence_length INTEGER NOT NULL,
            sequence_sha256 TEXT NOT NULL REFERENCES sequences(sha256),
            exact_sequence_group_size INTEGER NOT NULL,
            source TEXT NOT NULL,
            category TEXT,
            parent_snapshot_id TEXT NOT NULL,
            parent_snapshot_checksum TEXT NOT NULL,
            reference_version TEXT,
            database_version TEXT,
            imported_utc TEXT NOT NULL,
            provenance_json TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX records_fasta_id_idx ON records(fasta_id)")
        db.execute("CREATE INDEX records_accession_version_idx ON records(accession, accession_version)")
        db.execute("CREATE INDEX records_sequence_sha256_idx ON records(sequence_sha256)")
        db.execute("CREATE INDEX records_reference_id_idx ON records(reference_id)")
        for row in records:
            db.execute("INSERT OR IGNORE INTO sequences VALUES (?,?)",
                       (row["sequence_sha256"], row["_sequence"]))
            db.execute("""INSERT INTO records VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )""", tuple(row.get(field) for field in (
                "record_id", "reference_id", "reference_file", "fasta_id", "original_header",
                "accession", "accession_version", "description", "display_name",
                "sequence_length", "sequence_sha256", "exact_sequence_group_size",
                "source", "category", "parent_snapshot_id", "parent_snapshot_checksum",
                "reference_version", "database_version", "imported_utc", "provenance_json",
            )))


def _conflicts(records):
    conflicts = []
    by_fasta_id = defaultdict(list)
    by_accession = defaultdict(list)
    by_accession_version = defaultdict(list)
    for row in records:
        by_fasta_id[row["fasta_id"]].append(row)
        if row["accession"]:
            by_accession[row["accession"]].append(row)
            by_accession_version[(row["accession"], row["accession_version"])].append(row)

    for fasta_id, group in sorted(by_fasta_id.items()):
        if len(group) > 1:
            conflicts.append({
                "type": "fasta_identifier_reused",
                "identifier": fasta_id,
                "record_ids": sorted(row["record_id"] for row in group),
                "sequence_sha256": sorted({row["sequence_sha256"] for row in group}),
                "different_sequences": len({row["sequence_sha256"] for row in group}) > 1,
            })
    for accession, group in sorted(by_accession.items()):
        versions = sorted({row["accession_version"] for row in group},
                          key=lambda value: "" if value is None else value)
        if len(versions) > 1:
            conflicts.append({
                "type": "accession_version_conflict",
                "accession": accession,
                "versions": versions,
                "record_ids": sorted(row["record_id"] for row in group),
            })
    for (accession, version), group in sorted(
        by_accession_version.items(),
        key=lambda item: (item[0][0], "" if item[0][1] is None else item[0][1]),
    ):
        hashes = sorted({row["sequence_sha256"] for row in group})
        if len(hashes) > 1:
            conflicts.append({
                "type": ("accession_version_sequence_conflict"
                         if version is not None else "accession_sequence_conflict"),
                "accession": accession,
                "accession_version": version,
                "record_ids": sorted(row["record_id"] for row in group),
                "sequence_sha256": hashes,
            })
    return conflicts


def import_from_snapshot(references_table, output):
    """Create a new immutable record snapshot from a verified file-level snapshot."""
    table_path, parent_dir, reference_rows, parent_manifest, parent_snapshot_id = \
        _read_parent_table(references_table)
    fasta_rows = [row for row in reference_rows
                  if Path(row["name"]).suffix.lower() in FASTA_SUFFIXES]
    if not fasta_rows:
        raise ValueError("Reference snapshot contains no FASTA files to import")
    for row in reference_rows:
        if not isinstance(row.get("reference_id"), str) or not row["reference_id"].strip():
            raise ValueError("Reference snapshot contains a missing reference ID")
    inputs = {"references_table": table_path, "parent_manifest": parent_manifest}
    source_paths = []
    for index, row in enumerate(fasta_rows):
        path = (parent_dir / row["name"]).resolve(strict=True)
        if not path.is_relative_to(parent_dir):
            raise ValueError("Reference FASTA path escapes its snapshot")
        if checksum(path) != row["sha256"] or path.stat().st_size != int(row["bytes"]):
            raise ValueError("Reference FASTA failed parent snapshot integrity check: " + row["name"])
        key = f"fasta_{index:04d}"
        inputs[key] = path
        source_paths.append((key, path, row))

    parent_checksum = checksum(parent_manifest)

    def produce(paths, directory):
        imported_utc = datetime.now(timezone.utc).isoformat()
        records = []
        errors = []
        total_bases = 0
        for index, (key, _, reference) in enumerate(source_paths):
            remaining_records = max(0, MAX_RECORDS - len(records))
            remaining_bases = max(0, MAX_BASES - total_bases)
            parsed, issues = _parse_fasta(
                paths[key], reference,
                record_limit=remaining_records + 1,
                base_limit=remaining_bases + 1,
            )
            if len(parsed) > remaining_records:
                issues.append({"code": "record_limit_exceeded",
                               "message": "Reference snapshot exceeds the 10,000-record limit",
                               "file": reference["name"]})
                parsed = parsed[:remaining_records]
            errors.extend(issues)
            records.extend(parsed)
            total_bases += sum(len(row["sequence"]) for row in parsed)
            if total_bases > MAX_BASES:
                errors.append({"code": "base_limit_exceeded",
                               "message": "Reference snapshot exceeds the 20-million-base limit"})
                break
        if len(records) > MAX_RECORDS:
            errors.append({"code": "record_limit_exceeded",
                           "message": "Reference snapshot exceeds the 10,000-record limit"})
        if total_bases > MAX_BASES:
            errors.append({"code": "base_limit_exceeded",
                           "message": "Reference snapshot exceeds the 20-million-base limit"})
        validation = {"status": "invalid" if errors else "valid",
                      "record_count": len(records), "error_count": len(errors),
                      "errors": errors[:MAX_VALIDATION_ISSUES]}
        if errors:
            write_json(directory / "validation.json", validation)
            raise ValueError("Reference record validation failed; see validation.json")

        parent_ids = {row["reference_id"] for row in fasta_rows}
        if len(parent_ids) != len(fasta_rows):
            validation.update(status="invalid", error_count=1,
                              errors=[{"code": "duplicate_reference_id",
                                       "message": "Parent snapshot contains duplicate reference IDs"}])
            write_json(directory / "validation.json", validation)
            raise ValueError("Reference record validation failed; duplicate parent reference IDs")

        sequence_groups = Counter(row["sequence"] for row in records)
        record_rows = []
        for parsed in records:
            reference = parsed["reference"]
            fasta_id = parsed["fasta_id"]
            reference_id = reference["reference_id"]
            accession, accession_version = _parse_accession(parsed["header"], fasta_id)
            sequence = parsed["sequence"]
            seq_hash = hashlib.sha256(sequence.encode("ascii")).hexdigest()
            provenance = {
                "source": reference.get("source") or None,
                "category": reference.get("category") or reference.get("role") or None,
                "reference_version": reference.get("version") or None,
                "database_version": reference.get("database_version") or None,
                "supplied_provenance": reference.get("provenance") or None,
                "parent_accession": reference.get("accession") or None,
                "parent_reference_id": reference_id,
                "parent_file_sha256": reference["sha256"],
            }
            record_rows.append({
                "record_id": _stable_record_id(reference_id, fasta_id),
                "reference_id": reference_id,
                "reference_file": reference["name"],
                "fasta_id": fasta_id,
                "original_header": parsed["header"],
                "accession": accession,
                "accession_version": accession_version,
                "description": parsed["description"],
                "display_name": parsed["description"],
                "sequence_length": len(sequence),
                "sequence_sha256": seq_hash,
                "exact_sequence_group_size": sequence_groups[sequence],
                "source": reference["source"],
                "category": reference.get("category") or reference.get("role"),
                "parent_snapshot_id": parent_snapshot_id,
                "parent_snapshot_checksum": parent_checksum,
                "reference_version": reference.get("version"),
                "database_version": reference.get("database_version") or None,
                "imported_utc": imported_utc,
                "provenance": provenance,
                "provenance_json": json.dumps(provenance, sort_keys=True),
                "_sequence": sequence,
            })
        record_rows.sort(key=lambda row: row["record_id"])
        conflicts = _conflicts(record_rows)
        validation.update(status="review_required" if conflicts else "valid",
                          conflict_count=len(conflicts), conflicts=conflicts)
        runtime = reproducibility.environment()
        importer_sha256 = checksum(Path(__file__))
        identity_payload = {
            "parent_snapshot_id": parent_snapshot_id,
            "parent_snapshot_checksum": parent_checksum,
            "importer_version": __version__,
            "importer_sha256": importer_sha256,
            "records": [{key: row.get(key) for key in METADATA_FIELDS if key != "imported_utc"}
                        for row in record_rows],
        }
        snapshot_id = "refrec-" + hashlib.sha256(
            json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        snapshot = {
            "schema": STAGE,
            "snapshot_id": snapshot_id,
            "parent_snapshot_id": parent_snapshot_id,
            "parent_snapshot_checksum": parent_checksum,
            "record_count": len(record_rows),
            "imported_utc": imported_utc,
            "importer_version": __version__,
            "importer_sha256": importer_sha256,
            "git_revision": runtime.get("git_revision"),
            "git_dirty": runtime.get("git_dirty"),
            "validation_status": validation["status"],
            "record_hashes": {row["record_id"]: row["sequence_sha256"] for row in record_rows},
            "records": [{key: row.get(key) for key in METADATA_FIELDS}
                        for row in record_rows],
            "limitations": [
                "Sequences are uppercased and whitespace is removed before SHA256 calculation.",
                "Accession/version are parsed only from explicitly accession-shaped FASTA header tokens.",
                "Repeated identifiers and accession/version conflicts are reported, never collapsed.",
                "This importer does not infer database completeness, taxonomy or biological suitability.",
            ],
        }

        _write_csv(directory / "records.csv", record_rows)
        _create_database(directory / "catalogue.sqlite", record_rows)
        with (directory / "records.fasta").open("w", encoding="utf-8", newline="\n") as target:
            for row in record_rows:
                target.write(f">{row['record_id']} source_id={row['fasta_id']}\n")
                sequence = row["_sequence"]
                for offset in range(0, len(sequence), 80):
                    target.write(sequence[offset:offset + 80] + "\n")
        write_json(directory / "snapshot.json", snapshot)
        write_json(directory / "conflicts.json", {"conflicts": conflicts})
        write_json(directory / "validation.json", validation)
        rows_html = "".join(
            "<tr>" + "".join(
                "<td>" + html.escape(str(row.get(field) if row.get(field) is not None else "")) + "</td>"
                for field in ("record_id", "fasta_id", "accession", "accession_version",
                              "sequence_length", "sequence_sha256", "source", "category")
            ) + "</tr>"
            for row in record_rows
        )
        (directory / "report.html").write_text(
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>Reference record snapshot</title>"
            "<style>body{font:15px system-ui;margin:2rem}table{border-collapse:collapse}"
            "td,th{border:1px solid #bbb;padding:.35rem;text-align:left}code{overflow-wrap:anywhere}</style>"
            "</head><body><h1>Reference record snapshot</h1>"
            f"<p>Snapshot <code>{html.escape(snapshot_id)}</code>; {len(record_rows)} records; "
            f"validation: {html.escape(validation['status'])}.</p>"
            "<p>Every record remains distinct. Conflicts are reported, not resolved automatically.</p>"
            "<table><thead><tr><th>Internal ID</th><th>FASTA ID</th><th>Accession</th>"
            "<th>Version</th><th>Length</th><th>Sequence SHA256</th><th>Source</th>"
            "<th>Category</th></tr></thead><tbody>" + rows_html + "</tbody></table></body></html>",
            encoding="utf-8",
        )
        return list(OUTPUTS)

    return execute(STAGE, inputs, output, __file__, produce)


def verified_record_snapshot(directory):
    """Verify a completed record snapshot before lookup or comparison."""
    directory = Path(directory).resolve(strict=True)
    manifest = directory / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file() or not manifest.resolve().is_relative_to(directory):
        raise ValueError("Record snapshot manifest path is invalid")
    if manifest.stat().st_size > 2_000_000:
        raise ValueError("Record snapshot manifest exceeds 2 MB")
    state = json.loads(manifest.read_text(encoding="utf-8"))
    if (not isinstance(state, dict) or state.get("status") != "complete"
            or not isinstance(state.get("identity"), dict)
            or state["identity"].get("stage") != STAGE):
        raise ValueError("Use a completed reference record snapshot")
    digests = state.get("output_sha256")
    if not isinstance(digests, dict) or set(digests) != set(OUTPUTS):
        raise ValueError("Invalid reference record output manifest")
    for name, digest in digests.items():
        target = directory / name
        if (not portable_name(name) or target.is_symlink()
                or not target.resolve().is_relative_to(directory) or not target.is_file()
                or not isinstance(digest, str) or checksum(target) != digest):
            raise ValueError("Reference record snapshot integrity failure: " + str(name))
    snapshot_path = directory / "snapshot.json"
    if snapshot_path.stat().st_size > 64_000_000:
        raise ValueError("Reference record snapshot data exceeds 64 MB")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, dict):
        raise ValueError("Invalid reference record snapshot data")
    rows = snapshot.get("records")
    if (snapshot.get("schema") != STAGE or not isinstance(rows, list)
            or len(rows) > MAX_RECORDS or snapshot.get("record_count") != len(rows)
            or not isinstance(snapshot.get("snapshot_id"), str)
            or not snapshot["snapshot_id"].startswith("refrec-")):
        raise ValueError("Invalid reference record snapshot data")
    expected_hashes = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("record_id"), str)
                or not isinstance(row.get("sequence_sha256"), str)
                or not re.fullmatch(r"rr-[0-9a-f]{64}", row["record_id"])
                or not re.fullmatch(r"[0-9a-f]{64}", row["sequence_sha256"])
                or row["record_id"] in expected_hashes):
            raise ValueError("Invalid record metadata in reference snapshot")
        expected_hashes[row["record_id"]] = row["sequence_sha256"]
    if snapshot.get("record_hashes") != expected_hashes:
        raise ValueError("Record snapshot hash index does not match its records")
    return snapshot, manifest


def lookup_records(directory, *, record_id=None, fasta_id=None, accession=None,
                   accession_version=None, sequence_sha256=None):
    """Indexed exact lookup by internal ID, FASTA ID, accession/version or sequence SHA256."""
    simple = [("record_id", record_id), ("fasta_id", fasta_id),
              ("sequence_sha256", sequence_sha256)]
    simple = [(key, value) for key, value in simple if value is not None]
    if simple:
        if len(simple) != 1 or accession is not None or accession_version is not None:
            raise ValueError("Provide exactly one lookup key")
        key, value = simple[0]
    elif accession is not None:
        key, value = "accession", accession
    else:
        raise ValueError("Provide exactly one lookup key")
    if not isinstance(value, str) or not value:
        raise ValueError("Lookup values must be nonempty text")
    if accession_version is not None and (
        key != "accession" or not isinstance(accession_version, str) or not accession_version
    ):
        raise ValueError("Accession version can only be combined with a nonempty accession")
    verified_record_snapshot(directory)
    queries = {
        "record_id": ("record_id = ?", (value,)),
        "fasta_id": ("fasta_id = ?", (value,)),
        "accession": ("accession = ?", (value,)),
        "sequence_sha256": ("sequence_sha256 = ?", (value,)),
    }
    clause, params = queries[key]
    if key == "accession" and accession_version is not None:
        clause += " AND accession_version = ?"
        params = (value, accession_version)
    elif key != "accession" and accession_version is not None:
        raise ValueError("Accession version can only be combined with accession")
    with closing(sqlite3.connect(Path(directory) / "catalogue.sqlite")) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT records.*, sequences.sequence FROM records "
            "JOIN sequences ON sequences.sha256 = records.sequence_sha256 "
            "WHERE " + clause + " ORDER BY record_id",
            params,
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["provenance"] = json.loads(item.pop("provenance_json"))
        result.append(item)
    return result


def compare_record_snapshots(previous, current, output):
    """Write a read-only per-record comparison; neither source snapshot is changed."""
    before, before_manifest = verified_record_snapshot(previous)
    after, after_manifest = verified_record_snapshot(current)
    fields = (
        "fasta_id", "accession", "accession_version", "description", "display_name",
        "sequence_length", "sequence_sha256", "source", "category", "reference_version",
        "database_version", "parent_snapshot_id", "parent_snapshot_checksum", "provenance",
    )
    inputs = {"previous_manifest": before_manifest, "current_manifest": after_manifest}
    for prefix, base in (("previous", Path(previous)), ("current", Path(current))):
        state = json.loads((Path(base) / "manifest.json").read_text(encoding="utf-8"))
        for name in state["output_sha256"]:
            inputs[prefix + "_" + name.replace(".", "_")] = Path(base) / name

    def produce(paths, directory):
        old = {row["record_id"]: row for row in before["records"]}
        new = {row["record_id"]: row for row in after["records"]}
        changes = []
        for record_id in sorted(old.keys() | new.keys()):
            a, b = old.get(record_id), new.get(record_id)
            changed = [field for field in fields
                       if a is not None and b is not None and a.get(field) != b.get(field)]
            status = "added" if a is None else "removed" if b is None else "changed" if changed else "unchanged"
            changes.append({
                "record_id": record_id,
                "status": status,
                "changed_fields": ",".join(changed),
                "previous_sequence_sha256": a.get("sequence_sha256") if a else "",
                "current_sequence_sha256": b.get("sequence_sha256") if b else "",
            })
        with (directory / "changes.csv").open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=("record_id", "status", "changed_fields",
                                                         "previous_sequence_sha256", "current_sequence_sha256"))
            writer.writeheader()
            writer.writerows(changes)
        summary = {
            "previous_snapshot_id": before["snapshot_id"],
            "current_snapshot_id": after["snapshot_id"],
            "added": sum(row["status"] == "added" for row in changes),
            "removed": sum(row["status"] == "removed" for row in changes),
            "changed": sum(row["status"] == "changed" for row in changes),
            "unchanged": sum(row["status"] == "unchanged" for row in changes),
            "changes": changes,
            "limitations": ["Comparison is by stable internal record ID and supplied metadata.",
                            "No source snapshot is modified or replaced."],
        }
        write_json(directory / "summary.json", summary)
        (directory / "report.html").write_text(
            "<!doctype html><meta charset=\"utf-8\"><title>Reference record changes</title>"
            "<h1>Reference record snapshot changes</h1>"
            f"<p>Added {summary['added']}; removed {summary['removed']}; "
            f"changed {summary['changed']}; unchanged {summary['unchanged']}.</p>",
            encoding="utf-8",
        )
        return ["changes.csv", "summary.json", "report.html"]

    return execute("reference-record-comparison-v1", inputs, output, __file__, produce)