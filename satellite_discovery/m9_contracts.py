"""Small, fail-closed validators for the M9 file contracts.

The validators deliberately validate declarations and content hashes, but do
not attempt to interpret biological results.
"""
import hashlib
import json
import math
import re
from pathlib import Path

_HEX = re.compile(r"^[0-9a-f]{64}$")
_STATUSES = {
    "SEARCH_COMPLETED_MATCHES_REPORTED",
    "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
    "INSUFFICIENT_INFORMATION", "CANDIDATE_SEQUENCE_UNAVAILABLE", "INPUT_INVALID",
    "REFERENCE_SNAPSHOT_INVALID", "REFERENCE_SNAPSHOT_INCOMPLETE",
    "DEPENDENCY_UNAVAILABLE", "SEARCH_FAILED", "SEARCH_INTERRUPTED",
    "SEARCH_TRUNCATED", "NOT_RUN_NO_ORF",
}
_MATCH_STATUS = "SEARCH_COMPLETED_MATCHES_REPORTED"
_NO_MATCH_STATUS = "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"
_ORF_STATUSES = {"ORF_PREDICTED", "NO_ORF_PREDICTED_WITHIN_POLICY",
                 "CANDIDATE_SEQUENCE_UNAVAILABLE", "INPUT_INVALID"}
_AA = set("ACDEFGHIKLMNPQRSTVWYBXZJUO*")


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError("invalid JSON artifact") from e


def _obj(v, name="artifact"):
    if not isinstance(v, dict):
        raise ValueError(f"{name} must be an object")
    return v


def _required(v, keys, name="artifact"):
    missing = [k for k in keys if k not in v]
    if missing:
        raise ValueError(f"{name} missing required fields")


def _text(v, name):
    if not isinstance(v, str) or not v:
        raise ValueError(f"{name} must be non-empty text")


def _hash(v, name):
    if not isinstance(v, str) or not _HEX.fullmatch(v):
        raise ValueError(f"{name} is not a SHA-256")


def _integer(v, name, minimum=0):
    if type(v) is not int or v < minimum:
        raise ValueError(f"{name} is not a valid integer")


def _count(v, rows, name):
    _integer(v, name)
    if v != len(rows):
        raise ValueError(f"{name} disagrees with rows")


def _digest(v):
    return hashlib.sha256(v).hexdigest()


def validate_orf_results(path):
    v = _obj(_json(path))
    _required(v, ("schema", "aggregate_status", "candidate_set", "candidate_count", "candidates"))
    if (v["schema"] != "m9-orf-results-v1"
            or not isinstance(v["aggregate_status"], str)
            or v["aggregate_status"] not in {"COMPLETE", "PARTIAL"}):
        raise ValueError("invalid ORF results schema or aggregate status")
    _obj(v["candidate_set"], "candidate_set")
    _hash(v["candidate_set"].get("sha256"), "candidate_set.sha256")
    if not isinstance(v["candidates"], list): raise ValueError("candidates must be a list")
    _count(v["candidate_count"], v["candidates"], "candidate_count")
    if not isinstance(v["candidate_set"].get("availability_state"), str):
        raise ValueError("candidate_set availability state is missing")
    candidate_ids = set()
    sequence_ids = set()
    orf_ids = set()
    for c in v["candidates"]:
        _obj(c, "candidate")
        _required(c, ("candidate_id", "sequence_id", "sequence_bytes_available",
                      "sequence_sha256", "sequence_length", "m6_support_status",
                      "completeness_state", "molecule_type", "fasta_record_id",
                      "m6_evidence", "orf_status", "expected_orf_count",
                      "observed_orf_count", "orfs"), "candidate")
        for k in ("candidate_id", "sequence_id", "m6_support_status",
                  "completeness_state"):
            _text(c[k], k)
        if c["candidate_id"] in candidate_ids or c["sequence_id"] in sequence_ids:
            raise ValueError("candidate and sequence identities must be unique")
        candidate_ids.add(c["candidate_id"])
        sequence_ids.add(c["sequence_id"])
        if c["molecule_type"] is not None:
            _text(c["molecule_type"], "molecule_type")
        if c["fasta_record_id"] is not None:
            _text(c["fasta_record_id"], "fasta_record_id")
        if type(c["sequence_bytes_available"]) is not bool: raise ValueError("invalid byte availability")
        if c["sequence_bytes_available"]:
            _hash(c["sequence_sha256"], "sequence_sha256"); _integer(c["sequence_length"], "sequence_length", 1)
            if not isinstance(c["fasta_record_id"], str) or not c["fasta_record_id"]:
                raise ValueError("available sequence must have a FASTA record ID")
        elif c["sequence_sha256"] is not None or c["sequence_length"] is not None:
            raise ValueError("unavailable sequence must have null hash and length")
        if (not isinstance(c["orf_status"], str)
                or c["orf_status"] not in _ORF_STATUSES
                or not isinstance(c["m6_evidence"], (dict, list))):
            raise ValueError("invalid candidate status/evidence")
        if (c["sequence_bytes_available"]
                and c["orf_status"] == "CANDIDATE_SEQUENCE_UNAVAILABLE"):
            raise ValueError("available candidate cannot have unavailable status")
        if (not c["sequence_bytes_available"]
                and c["orf_status"] != "CANDIDATE_SEQUENCE_UNAVAILABLE"):
            raise ValueError("unavailable candidate has an inconsistent ORF status")
        if not isinstance(c["orfs"], list): raise ValueError("orfs must be a list")
        _count(c["expected_orf_count"], c["orfs"], "expected_orf_count")
        _count(c["observed_orf_count"], c["orfs"], "observed_orf_count")
        if c["orf_status"] == "ORF_PREDICTED" and not c["orfs"]: raise ValueError("predicted candidate has no ORFs")
        if (c["orf_status"] in {
                "NO_ORF_PREDICTED_WITHIN_POLICY",
                "CANDIDATE_SEQUENCE_UNAVAILABLE", "INPUT_INVALID",
        } and c["orfs"]):
            raise ValueError("candidate status cannot contain ORF rows")
        for o in c["orfs"]:
            _obj(o, "ORF")
            _required(o, ("candidate_id", "sequence_id", "source_sequence_sha256",
                          "source_sequence_length", "orf_id", "strand", "frame",
                          "original_span", "partial", "partial_5_prime",
                          "partial_3_prime", "translation_table", "derivation_policy",
                          "protein_sequence", "protein_sha256", "protein_length",
                          "ambiguous_codon_positions"), "ORF")
            if o["candidate_id"] != c["candidate_id"] or o["sequence_id"] != c["sequence_id"]:
                raise ValueError("ORF identity does not bind candidate")
            if c["sequence_bytes_available"]:
                if o["source_sequence_sha256"] != c["sequence_sha256"] or o["source_sequence_length"] != c["sequence_length"]:
                    raise ValueError("ORF source sequence mismatch")
            _hash(o["source_sequence_sha256"], "ORF source hash"); _integer(o["source_sequence_length"], "ORF source length", 1)
            _text(o["orf_id"], "orf_id")
            if o["orf_id"] in orf_ids:
                raise ValueError("ORF identifiers must be unique")
            orf_ids.add(o["orf_id"])
            if o["strand"] not in {"+", "-"} or o["frame"] not in {0, 1, 2}: raise ValueError("invalid ORF strand/frame")
            span = o["original_span"]
            if not isinstance(span, list) or len(span) != 2 or any(type(x) is not int for x in span) or not 0 <= span[0] < span[1] <= o["source_sequence_length"]:
                raise ValueError("invalid ORF coordinates")
            if any(type(o[k]) is not bool for k in ("partial", "partial_5_prime", "partial_3_prime")):
                raise ValueError("invalid ORF partial flags")
            if o["partial"] != (o["partial_5_prime"] or o["partial_3_prime"]):
                raise ValueError("ORF partial flags are inconsistent")
            if o["translation_table"] != 1: raise ValueError("M9 baseline requires translation table 1")
            _text(o["derivation_policy"], "derivation_policy")
            _text(o["protein_sequence"], "protein_sequence")
            if any(x.upper() not in _AA for x in o["protein_sequence"]): raise ValueError("invalid protein alphabet")
            if o["protein_sha256"] != _digest(o["protein_sequence"].encode()) or o["protein_length"] != len(o["protein_sequence"]):
                raise ValueError("protein hash or length mismatch")
            if not isinstance(o["ambiguous_codon_positions"], list) or any(type(x) is not int or x < 0 for x in o["ambiguous_codon_positions"]):
                raise ValueError("invalid ambiguous codon positions")
    return {"schema": v["schema"], "candidate_count": len(v["candidates"]), "aggregate_status": v["aggregate_status"]}


def validate_protein_fasta(path):
    raw = Path(path).read_bytes()
    if not raw: return {"record_count": 0, "empty": True}
    records = {}; current = None
    for line in raw.decode("utf-8").splitlines():
        if line.startswith(">"):
            ident = line[1:].strip().split()[0] if line[1:].strip() else ""
            if not ident or ident in records: raise ValueError("duplicate or empty FASTA identifier")
            records[ident] = ""; current = ident
        elif line.strip():
            if current is None: raise ValueError("FASTA sequence precedes header")
            records[current] += "".join(line.split()).upper()
    if not records: raise ValueError("FASTA contains no records")
    if any(not seq or any(x not in _AA for x in seq) for seq in records.values()): raise ValueError("invalid protein FASTA sequence")
    return {"record_count": len(records), "record_ids": sorted(records)}


def _validate_status_doc(path, schema):
    v = _obj(_json(path)); _required(v, ("schema", "aggregate_status"), schema)
    if (v["schema"] != schema or not isinstance(v["aggregate_status"], str)
            or v["aggregate_status"] not in {"COMPLETE", "PARTIAL"}):
        raise ValueError("invalid schema/aggregate")
    return v


def validate_protein_search_status(path):
    v = _validate_status_doc(path, "m9-protein-search-status-v1")
    _required(v, ("reference_snapshot_state", "candidate_count", "expected_orf_query_count",
                  "observed_query_count", "query_accounting", "queries", "candidate_statuses"))
    for k in ("candidate_count", "expected_orf_query_count", "observed_query_count"): _integer(v[k], k)
    if (not isinstance(v["reference_snapshot_state"], str)
            or v["reference_snapshot_state"] not in {"VALID", "INCOMPLETE", "INVALID"}):
        raise ValueError("invalid reference snapshot state")
    if not isinstance(v["queries"], list) or not isinstance(v["candidate_statuses"], list): raise ValueError("invalid status rows")
    a = _obj(v["query_accounting"], "query_accounting")
    _required(a, ("expected_query_ids", "observed_query_ids", "missing_query_ids"), "query_accounting")
    if any(not isinstance(a[k], list) or len(set(a[k])) != len(a[k]) or any(not isinstance(x, str) or not x for x in a[k]) for k in ("expected_query_ids", "observed_query_ids", "missing_query_ids")): raise ValueError("invalid query accounting")
    if set(a["missing_query_ids"]) != set(a["expected_query_ids"]) - set(a["observed_query_ids"]): raise ValueError("query accounting mismatch")
    if not set(a["observed_query_ids"]) <= set(a["expected_query_ids"]):
        raise ValueError("observed query IDs are not a subset of expected IDs")
    if v["expected_orf_query_count"] != len(a["expected_query_ids"]) or v["observed_query_count"] != len(a["observed_query_ids"]): raise ValueError("query counts mismatch")
    query_ids = [row.get("query_id") for row in v["queries"] if isinstance(row, dict)]
    if (len(query_ids) != len(v["queries"]) or len(set(query_ids)) != len(query_ids)
            or set(query_ids) != set(a["observed_query_ids"])):
        raise ValueError("query status rows do not match query accounting")
    if v["candidate_count"] != len(v["candidate_statuses"]):
        raise ValueError("candidate statuses do not match candidate count")
    for row in v["queries"] + v["candidate_statuses"]:
        _obj(row, "status row")
        status = row.get("status", row.get("branch_status"))
        if status not in _STATUSES: raise ValueError("non-canonical M9 status")
    if v["reference_snapshot_state"] != "VALID" and any(
            row["status"] in {_MATCH_STATUS, _NO_MATCH_STATUS}
            for row in v["queries"]):
        raise ValueError("invalid or incomplete snapshot cannot report a scoped result")
    if v["aggregate_status"] == "COMPLETE":
        if (v["reference_snapshot_state"] != "VALID" or a["missing_query_ids"]
                or any(row["status"] not in {_MATCH_STATUS, _NO_MATCH_STATUS}
                       for row in v["queries"])
                or any(row["status"] not in {_MATCH_STATUS, _NO_MATCH_STATUS, "NOT_RUN_NO_ORF"}
                       for row in v["candidate_statuses"])):
            raise ValueError("complete aggregate has incomplete branch accounting")
    return {"schema": v["schema"], "aggregate_status": v["aggregate_status"], "query_count": len(v["queries"])}


def validate_protein_match_evidence(path):
    v = _obj(_json(path))
    if v.get("schema") != "m9-protein-match-evidence-v1": raise ValueError("invalid match evidence schema")
    _required(v, ("match_count", "matches")); matches = v["matches"]
    if not isinstance(matches, list): raise ValueError("matches must be a list")
    _count(v["match_count"], matches, "match_count")
    required = ("candidate_id", "source_sequence_sha256", "query_id", "query_sha256",
                "query_length", "snapshot_id", "snapshot_digest", "reference_id",
                "reference_length", "reference_accession_version",
                "reference_sequence_sha256", "percent_identity", "alignment_length",
                "mismatches", "raw_score", "bit_score", "evalue", "gap_count",
                "profile_id", "scope_state", "coordinate_convention",
                "role", "query_start", "query_end", "reference_start", "reference_end",
                "query_coverage_denominator", "reference_coverage_denominator",
                "query_coverage_fraction", "reference_coverage_fraction",
                "raw_output_sha256", "method", "profile")
    for r in matches:
        _obj(r, "match"); _required(r, required, "match")
        for k in ("source_sequence_sha256", "query_sha256", "snapshot_digest",
                  "reference_sequence_sha256", "raw_output_sha256"):
            _hash(r[k], k)
        for k in ("candidate_id", "query_id", "snapshot_id", "reference_id",
                  "reference_accession_version", "role", "method", "profile_id"):
            _text(r[k], k)
        if r["scope_state"] not in {"VALID", "INCOMPLETE"}:
            raise ValueError("invalid match scope state")
        if r["coordinate_convention"] != "zero-based half-open; BLAST inclusive coordinates normalized":
            raise ValueError("invalid coordinate convention")
        _obj(r["profile"], "profile")
        for k in ("identities", "positives"):
            if k not in r: raise ValueError("match missing identity counts")
        gaps = r["gap_count"]
        for k in ("query_length", "query_start", "query_end", "reference_start", "reference_end", "query_coverage_denominator", "reference_coverage_denominator", "identities", "positives"): _integer(r[k], k)
        _integer(gaps, "gaps")
        raw_score = r.get("raw_score", r.get("score"))
        if raw_score is None or "bit_score" not in r or "evalue" not in r: raise ValueError("match missing scores")
        for k in ("query_coverage_fraction", "reference_coverage_fraction", "raw_score", "bit_score", "evalue"):
            value = raw_score if k == "raw_score" else r[k]
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0: raise ValueError("invalid match quantitative field")
        if not isinstance(r.get("percent_identity"), (int, float)) or not 0 <= r["percent_identity"] <= 100:
            raise ValueError("invalid percent identity")
        if not math.isfinite(r["percent_identity"]):
            raise ValueError("invalid percent identity")
        for k in ("alignment_length", "mismatches", "reference_length"):
            _integer(r.get(k), k, 1 if k in {"alignment_length", "reference_length"} else 0)
        if r["query_end"] <= r["query_start"] or r["reference_end"] <= r["reference_start"]: raise ValueError("invalid match coordinates")
        if (r["query_end"] > r["query_length"]
                or r["reference_end"] > r["reference_length"]
                or r["query_coverage_denominator"] != r["query_length"]
                or r["reference_coverage_denominator"] != r["reference_length"]):
            raise ValueError("match coordinates or coverage denominators are inconsistent")
        expected_q = (r["query_end"] - r["query_start"]) / r["query_length"]
        expected_s = (r["reference_end"] - r["reference_start"]) / r["reference_length"]
        if (not math.isclose(r["query_coverage_fraction"], expected_q, rel_tol=1e-9)
                or not math.isclose(r["reference_coverage_fraction"], expected_s, rel_tol=1e-9)):
            raise ValueError("match coverage fractions are inconsistent")
    return {"schema": v["schema"], "match_count": len(matches)}


def _generic_provenance(path, schema):
    v = _validate_status_doc(path, schema)
    for key in ("source_inputs", "snapshot", "tool", "profile", "settings", "accounting", "raw_output_provenance"):
        if key not in v or not isinstance(v[key], (dict, list, str)): raise ValueError("invalid provenance field")
    return {"schema": schema, "aggregate_status": v["aggregate_status"]}


def validate_protein_summary(path): return _generic_provenance(path, "m9-protein-summary-v1")
def validate_search_commands(path): return _generic_provenance(path, "m9-search-commands-v1")


def validate_bundle(path):
    v = _obj(_json(path)); _required(v, ("schema", "bundle_kind", "source_inputs", "outputs"))
    if v["schema"] != "m9-output-bundle-v1" or v["bundle_kind"] not in {"ORF_DERIVATION", "PROTEIN_SEARCH"}: raise ValueError("invalid bundle")
    _obj(v["source_inputs"], "source_inputs"); outputs = _obj(v["outputs"], "outputs")
    if not outputs: raise ValueError("M9 bundle must list at least one local output")
    for name, row in outputs.items():
        if not isinstance(name, str) or Path(name).name != name or Path(name).is_absolute(): raise ValueError("non-portable output name")
        _obj(row, "output"); _required(row, ("artifact_type", "sha256", "size_bytes"), "output")
        _text(row["artifact_type"], "artifact_type"); _hash(row["sha256"], "output hash"); _integer(row["size_bytes"], "size_bytes")
        p = Path(path).parent / name
        if not p.is_file() or p.stat().st_size != row["size_bytes"] or _digest(p.read_bytes()) != row["sha256"]: raise ValueError("bundle output hash mismatch")
    return {"schema": v["schema"], "bundle_kind": v["bundle_kind"], "output_count": len(outputs)}


def validate_reference_manifest(path):
    v = _obj(_json(path)); _required(v, ("schema", "snapshot_id", "snapshot_digest", "payload_sha256", "completeness", "records", "provenance"))
    if (v["schema"] != "m9-protein-reference-snapshot-v1"
            or not isinstance(v["completeness"], str)
            or v["completeness"] not in {"complete", "incomplete"}):
        raise ValueError("invalid reference manifest")
    _text(v["snapshot_id"], "snapshot_id"); _hash(v["snapshot_digest"], "snapshot_digest"); _hash(v["payload_sha256"], "payload_sha256")
    canonical = {k: x for k, x in v.items() if k != "snapshot_digest"}
    if _digest(json.dumps(
            canonical, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
    ).encode()) != v["snapshot_digest"]: raise ValueError("snapshot digest mismatch")
    p = _obj(v["provenance"], "provenance")
    for k in ("source", "release", "rights", "terms"): _text(p.get(k), k)
    if not isinstance(v["records"], list): raise ValueError("records must be a list")
    if v["completeness"] == "complete" and not v["records"]:
        raise ValueError("complete reference manifest must contain records")
    ids = set(); acc = set()
    for r in v["records"]:
        _obj(r, "record"); _required(r, ("record_id", "accession_version", "role", "length", "sha256"), "record")
        for k in ("record_id", "accession_version", "role"): _text(r[k], k)
        if r["record_id"] in ids or r["accession_version"] in acc: raise ValueError("duplicate reference identity")
        ids.add(r["record_id"]); acc.add(r["accession_version"]); _integer(r["length"], "length", 1); _hash(r["sha256"], "record hash")
    return {"schema": v["schema"], "record_count": len(v["records"]), "completeness": v["completeness"]}


def validate_raw_output(path):
    p = Path(path)
    try:
        if p.is_symlink(): raise ValueError("raw output must not be a symbolic link")
        info = p.stat()
    except OSError as e: raise ValueError("raw output is missing") from e
    if not p.is_file() or info.st_size > 400_000_000: raise ValueError("raw output is not a bounded regular file")
    try: p.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e: raise ValueError("raw output is not regular UTF-8") from e
    return {"size_bytes": info.st_size, "sha256": _digest(p.read_bytes())}