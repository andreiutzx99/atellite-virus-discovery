"""Trusted, pinned local BLASTN adapter for M8.

This module is deliberately a narrow execution boundary.  It does not acquire
tools or references and it never assigns a biological meaning to a hit.
"""
import hashlib
import math
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from . import bounded_process, m8_blastn_profile as profile


_VERSION_RE = re.compile(r"\b2\.17\.0\+")
_HEX = re.compile(r"^[0-9a-f]{64}$")
_STATUS_OK = "SEARCH_COMPLETED_MATCHES_REPORTED"
_STATUS_EMPTY = "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _executable(config, key, env_key, fallback):
    aliases = {
        "blastn_executable": ("blastn_path", "blastn"),
        "makeblastdb_executable": ("makeblastdb_path", "makeblastdb"),
    }
    value = ((config or {}).get(key)
             or next(((config or {}).get(alias) for alias in aliases.get(key, ())
                       if (config or {}).get(alias)), None)
             or os.environ.get(env_key))
    if value:
        return Path(value).expanduser().resolve()
    found = shutil.which(fallback)
    return Path(found).resolve() if found else None


def _probe(path, expected_hash, tool):
    row = {
        "tool": tool, "path": str(path) if path else "",
        "status": "not_found", "version_output": "", "sha256": "",
    }
    if path is None:
        return row
    try:
        if not path.is_file():
            return row
        row["sha256"] = _sha256(path)
        hash_ok = row["sha256"] == expected_hash
        row["hash_pinned"] = hash_ok
        if not hash_ok:
            row["status"] = "version_check_failed"
            row["version_output"] = "Executable SHA-256 does not match the approved pin"
            return row
        with tempfile.TemporaryDirectory(prefix="m8-blast-probe-") as directory:
            try:
                result = bounded_process.run_captured(
                    [str(path), "-version"], directory, "probe.stdout.log",
                    "probe.stderr.log", timeout=15, max_bytes=256_000)
            except (OSError, subprocess.SubprocessError, TimeoutError, ValueError):
                stdout = (Path(directory) / "probe.stdout.log").read_text(
                    encoding="utf-8", errors="replace")
                stderr = (Path(directory) / "probe.stderr.log").read_text(
                    encoding="utf-8", errors="replace")
                row["version_output"] = (stdout + "\n" + stderr).strip()[:4000]
                raise
            stdout = (Path(directory) / "probe.stdout.log").read_text(
                encoding="utf-8", errors="replace")
            stderr = (Path(directory) / "probe.stderr.log").read_text(
                encoding="utf-8", errors="replace")
        row["version_output"] = (stdout + "\n" + stderr).strip()[:4000]
        version_ok = result.returncode == 0 and _VERSION_RE.search(row["version_output"])
        row["status"] = "version_check_passed" if version_ok and hash_ok else "version_check_failed"
        row["version"] = profile.BLAST_RELEASE if version_ok else None
    except (OSError, subprocess.SubprocessError, TimeoutError, ValueError) as error:
        row["status"] = "version_check_failed"
        row["version_output"] = str(error)[:4000]
    return row


def inspect_blast_runtime(config=None):
    """Inspect only the reviewed Linux x86-64 BLAST+ runtime.

    A returned ``dependency_missing`` state is intentional and must not be
    interpreted as an empty search.
    """
    config = config if config is not None else {}
    if not isinstance(config, dict):
        raise ValueError("BLAST runtime configuration must be an object")
    system, machine = platform.system(), platform.machine()
    blast_path = _executable(config, "blastn_executable", "BLASTN_EXECUTABLE", "blastn")
    make_path = _executable(config, "makeblastdb_executable", "MAKEBLASTDB_EXECUTABLE", "makeblastdb")
    blast = _probe(blast_path, profile.BLASTN_BINARY_SHA256, "blastn")
    make = _probe(make_path, profile.MAKEBLASTDB_BINARY_SHA256, "makeblastdb")
    supported_platform = system.lower() == "linux" and machine.lower() == "x86_64"
    available = supported_platform and blast["status"] == "version_check_passed" and make["status"] == "version_check_passed"
    return {
        "status": "available" if available else "dependency_missing",
        "platform": {"system": system, "machine": machine, "supported": supported_platform},
        "blastn": blast,
        "makeblastdb": make,
        "release": profile.BLAST_RELEASE,
        "profile_id": profile.BLAST_PROFILE_ID,
    }


def _number(value, label, integer=False):
    try:
        result = int(value) if integer else float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid BLAST {label}") from error
    if result < 0:
        raise ValueError(f"Invalid BLAST {label}")
    return result


def parse_blast_tabular(text, query_metadata, reference_map, raw_output_hash):
    """Parse the frozen 15-column BLAST outfmt-6 output strictly.

    ``reference_map`` maps stable database IDs to reference metadata.  Native
    row order is retained by ``raw_row_ordinal``; returned rows are then sorted
    deterministically for downstream storage.
    """
    if not isinstance(text, str) or not isinstance(query_metadata, dict) or not isinstance(reference_map, dict):
        raise ValueError("BLAST parser requires text, query metadata, and reference map")
    if not isinstance(raw_output_hash, str) or not _HEX.fullmatch(raw_output_hash):
        raise ValueError("BLAST raw output hash is invalid")
    query_id = query_metadata.get(
        "query_id", query_metadata.get("fasta_record_id", query_metadata.get("candidate_id")))
    if not isinstance(query_id, str) or not query_id:
        raise ValueError("Query metadata requires query_id")
    query_length = query_metadata.get("query_length", query_metadata.get("length"))
    if type(query_length) is not int or query_length < 1:
        raise ValueError("Query metadata requires positive query_length")
    rows = []
    for ordinal, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) != len(profile.OUTFMT_FIELDS):
            raise ValueError(f"BLAST row {ordinal} must contain exactly 15 fields")
        qid, sid = fields[0], fields[1]
        if qid != query_id or sid not in reference_map:
            raise ValueError(f"BLAST row {ordinal} has an unknown query or reference")
        reference = reference_map[sid]
        if not isinstance(reference, dict):
            raise ValueError("Reference metadata must be mappings")
        slen = _number(fields[13], "subject length", integer=True)
        if slen < 1:
            raise ValueError("BLAST subject length must be positive")
        aligned = _number(fields[3], "alignment length", integer=True)
        if aligned < 1:
            raise ValueError("BLAST alignment length must be positive")
        qstart, qend = _number(fields[6], "query start", integer=True), _number(fields[7], "query end", integer=True)
        sstart, send = _number(fields[8], "subject start", integer=True), _number(fields[9], "subject end", integer=True)
        if not (1 <= qstart <= query_length and 1 <= qend <= query_length and 1 <= sstart <= slen and 1 <= send <= slen):
            raise ValueError(f"BLAST row {ordinal} coordinates exceed denominators")
        strand = {"plus": "+", "minus": "-"}.get(fields[14].lower())
        if strand is None:
            raise ValueError(f"BLAST row {ordinal} has invalid subject strand")
        percent_identity = _number(fields[2], "percent identity")
        mismatches = _number(fields[4], "mismatches", True)
        gap_openings = _number(fields[5], "gap openings", True)
        if not math.isfinite(percent_identity) or not 0 <= percent_identity <= 100:
            raise ValueError(f"BLAST row {ordinal} has invalid percent identity")
        if mismatches + gap_openings > aligned:
            raise ValueError(f"BLAST row {ordinal} has inconsistent mismatch/gap counts")
        expected_slen = reference.get("reference_length", reference.get("length"))
        if expected_slen is not None and (type(expected_slen) is not int or expected_slen != slen):
            raise ValueError(f"BLAST row {ordinal} subject length disagrees with reference metadata")
        row = {
            "query_id": qid, "reference_id": sid, "raw_row_ordinal": ordinal,
            "percent_identity": percent_identity, "alignment_length": aligned,
            "mismatches": mismatches, "gap_openings": gap_openings,
            "query_start": qstart, "query_end": qend, "reference_start": sstart,
            "reference_end": send, "evalue": float(fields[10]), "bitscore": float(fields[11]),
            "query_length": _number(fields[12], "query length", True), "reference_length": slen,
            "strand": strand,
            "query_coverage_bases": abs(qend - qstart) + 1,
            "reference_coverage_bases": abs(send - sstart) + 1,
            "raw_output_sha256": raw_output_hash,
            "reference": reference,
        }
        if not math.isfinite(row["evalue"]) or not math.isfinite(row["bitscore"]):
            raise ValueError(f"BLAST row {ordinal} has non-finite score")
        if row["query_length"] != query_length:
            raise ValueError(f"BLAST row {ordinal} query length disagrees with metadata")
        row["query_coverage"] = row["query_coverage_bases"] / query_length
        row["reference_coverage"] = row["reference_coverage_bases"] / slen
        rows.append(row)
    return sorted(rows, key=lambda row: (
        row["query_id"], row["reference_id"], row["query_start"], row["query_end"],
        row["reference_start"], row["reference_end"], row["strand"], row["raw_row_ordinal"],
    ))


def build_makeblastdb_args(executable, fasta_path, database_prefix):
    """Build the approved BLASTDB v5 construction argv; never executes it."""
    return [str(executable), "-in", str(fasta_path), "-dbtype", "nucl",
            "-parse_seqids", "-out", str(database_prefix),
            "-title", "M8 approved accession-version panel"]


def run_blast_branch(query_path, database_prefix, output_directory, query_metadata,
                     reference_map, masking_branch, *, config=None, runtime=None, timeout=180,
                     max_bytes=400_000_000):
    """Run one explicit masked/unmasked branch and return a typed result."""
    try:
        applicability = profile.method_applicability(
            query_metadata.get("query_length", query_metadata.get("length")))
    except (AttributeError, TypeError, ValueError) as error:
        return {"status": "INPUT_INVALID", "rows": [], "error": str(error)}
    if not applicability["informative"]:
        return {"status": "INSUFFICIENT_INFORMATION", "reason": applicability["reason"],
                "task": applicability["task"], "rows": [], "raw_output_sha256": None}
    runtime = runtime if runtime is not None else inspect_blast_runtime(config)
    if runtime["status"] != "available":
        return {"status": "DEPENDENCY_UNAVAILABLE", "runtime": runtime, "rows": []}
    output_directory = Path(output_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f"blastn_{masking_branch}.tsv"
    argv = profile.build_blastn_args(
        runtime["blastn"]["path"], Path(query_path).resolve(strict=True),
        Path(database_prefix).resolve(), output_path,
        query_metadata.get("query_length", query_metadata.get("length")),
        masking_branch,
    )
    try:
        process = bounded_process.run_captured(
            argv, output_directory, f"blastn_{masking_branch}.stdout.log",
            f"blastn_{masking_branch}.stderr.log",
            timeout=timeout, max_bytes=max_bytes,
        )
        if process.returncode:
            return {"status": "SEARCH_FAILED", "returncode": process.returncode, "rows": [], "argv": argv,
                    **_partial_raw(output_path)}
        raw = output_path.read_bytes()
        raw_hash = hashlib.sha256(raw).hexdigest()
        rows = parse_blast_tabular(raw.decode("utf-8"), query_metadata, reference_map, raw_hash)
        truncated = profile.output_cap_reached(rows)
        return {"status": "SEARCH_TRUNCATED" if truncated else (_STATUS_OK if rows else _STATUS_EMPTY),
                "rows": rows, "raw_output": str(output_path), "raw_output_sha256": raw_hash,
                "argv": argv, "truncated": truncated, "runtime": runtime,
                "task": applicability["task"], "masking_branch": masking_branch}
    except (KeyboardInterrupt, SystemExit, TimeoutError):
        return {"status": "SEARCH_INTERRUPTED", "rows": [], "argv": argv,
                **_partial_raw(output_path)}
    except (OSError, UnicodeDecodeError, ValueError) as error:
        message = str(error)
        status = ("SEARCH_TRUNCATED" if "byte budget" in message.lower()
                  or "output exceeds" in message.lower() else "SEARCH_FAILED")
        return {"status": status, "rows": [], "error": message, "argv": argv,
                **_partial_raw(output_path)}


def _partial_raw(path):
    """Return a best-effort identity for output left by a failed process."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return {"raw_output": None, "raw_output_sha256": None}
    return {"raw_output": str(path), "raw_output_sha256": hashlib.sha256(data).hexdigest()}