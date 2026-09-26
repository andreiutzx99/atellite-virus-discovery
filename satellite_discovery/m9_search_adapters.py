"""Pinned ordinary local BLASTP adapter for the M9 synthetic baseline."""
import hashlib
import math
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import bounded_process

BLAST_RELEASE = "2.16.0"
BLASTP_SHA256 = "e17de0fd689f89dcb095eea2626710a206ab3d016a183f064c388f963ecbc7c4"
MAKEBLASTDB_SHA256 = "6797dd00e0dddfa0529de795ded12b41738792c9b75bf3643e1f03a782d2008f"
PROFILE_ID = "m9-blastp-linux-x86_64-v1"
FIELDS = ("qseqid","sseqid","pident","length","nident","positive","mismatch","gapopen",
          "qstart","qend","sstart","send","evalue","bitscore","score","qlen","slen")
STATUS_MATCH = "SEARCH_COMPLETED_MATCHES_REPORTED"
STATUS_EMPTY = "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"
_HEX = re.compile(r"^[0-9a-f]{64}$")


def profile_identity():
    return {"profile_id": PROFILE_ID, "release": BLAST_RELEASE, "task": "blastp",
            "matrix": "BLOSUM62", "gapopen": 11, "gapextend": 1, "seg": "yes",
            "comp_based_stats": 2, "evalue": 2000, "max_target_seqs": 1000,
            "max_hsps": 100, "num_threads": 1, "outfmt_fields": list(FIELDS)}


def blastp_profile_identity():
    """Return the immutable profile identity for audit callers."""
    return profile_identity()


def _path(config, key, env, name):
    value = (config or {}).get(key) or os.environ.get(env)
    found = value or shutil.which(name)
    return Path(found).resolve() if found else None


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def _raw_identity(path):
    try:
        return {"raw_output": str(path), "raw_output_sha256": _sha(path)}
    except OSError:
        return {"raw_output": None, "raw_output_sha256": None}


def inspect_blastp_runtime(config=None):
    config = config or {}
    system, machine = platform.system(), platform.machine()
    rows = {}
    for key, env, name, pin in (("blastp_executable","BLASTP_EXECUTABLE","blastp",BLASTP_SHA256),
                                ("makeblastdb_executable","MAKEBLASTDB_EXECUTABLE","makeblastdb",MAKEBLASTDB_SHA256)):
        path = _path(config, key, env, name)
        row = {"tool": name, "path": str(path) if path else None, "sha256": None, "version": None}
        if path and path.is_file():
            row["sha256"] = _sha(path)
            if row["sha256"] == pin:
                try:
                    with tempfile.TemporaryDirectory(prefix="m9-blast-probe-") as directory:
                        process = bounded_process.run_captured(
                            [str(path), "-version"], directory, "stdout.log", "stderr.log",
                            timeout=15, max_bytes=256_000)
                        stdout = (Path(directory) / "stdout.log").read_text(
                            encoding="utf-8", errors="replace")
                        stderr = (Path(directory) / "stderr.log").read_text(
                            encoding="utf-8", errors="replace")
                    if process.returncode == 0 and BLAST_RELEASE in stdout + stderr:
                        row["version"] = BLAST_RELEASE
                except (OSError, subprocess.SubprocessError, TimeoutError, ValueError):
                    pass
        row["pinned"] = row["sha256"] == pin and row["version"] == BLAST_RELEASE
        rows[name] = row
    supported = system.lower() == "linux" and machine.lower() == "x86_64"
    return {"status": "available" if supported and all(x["pinned"] for x in rows.values()) else "DEPENDENCY_UNAVAILABLE",
            "platform": {"system": system, "machine": machine, "supported": supported},
            "blastp": rows["blastp"], "makeblastdb": rows["makeblastdb"], "profile": profile_identity()}


def _args(exe, query, db, out, max_target_seqs=1000, max_hsps=100):
    return [str(exe), "-query", str(query), "-db", str(db), "-task", "blastp",
            "-matrix", "BLOSUM62", "-gapopen", "11", "-gapextend", "1", "-seg", "yes",
            "-comp_based_stats", "2", "-evalue", "2000", "-max_target_seqs", str(max_target_seqs),
            "-max_hsps", str(max_hsps), "-num_threads", "1", "-outfmt", "6 " + " ".join(FIELDS),
            "-out", str(out)]


def build_protein_database(fasta_path, database_prefix, *, config=None, output_directory=None, timeout=180, max_bytes=400_000_000):
    runtime = inspect_blastp_runtime(config)
    if runtime["status"] != "available": return {"status": "DEPENDENCY_UNAVAILABLE", "runtime": runtime}
    directory = Path(output_directory or Path(database_prefix).parent).resolve(); directory.mkdir(parents=True, exist_ok=True)
    argv = [runtime["makeblastdb"]["path"], "-in", str(Path(fasta_path).resolve(strict=True)), "-dbtype", "prot",
            "-parse_seqids", "-out", str(Path(database_prefix).resolve()), "-title", "M9 protein reference snapshot"]
    try:
        result = bounded_process.run_captured(argv, directory, "makeblastdb.stdout.log", "makeblastdb.stderr.log", timeout, max_bytes)
        indexes = []
        for path in sorted(directory.glob(Path(database_prefix).name + ".*")):
            if path.is_file():
                indexes.append({"path": str(path), "size": path.stat().st_size, "sha256": _sha(path)})
        status = "SEARCH_COMPLETED" if result.returncode == 0 and indexes else "SEARCH_FAILED"
        return {"status": status, "argv": argv,
                "runtime": runtime, "stdout_path": str(directory / "makeblastdb.stdout.log"),
                "stderr_path": str(directory / "makeblastdb.stderr.log"), "database_indexes": indexes}
    except TimeoutError:
        return {"status": "SEARCH_INTERRUPTED", "argv": argv, "runtime": runtime}
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return {"status": "SEARCH_TRUNCATED" if "byte" in str(exc).lower() else "SEARCH_FAILED", "error": str(exc), "argv": argv}


def parse_blastp_tabular(text, query_map, reference_map, raw_output_hash):
    if not isinstance(text, str) or not isinstance(query_map, dict) or not isinstance(reference_map, dict) or not _HEX.fullmatch(raw_output_hash or ""):
        raise ValueError("invalid parser arguments")
    rows = []
    for ordinal, line in enumerate(text.splitlines(), 1):
        if not line.strip(): continue
        f = line.split("\t")
        if len(f) != len(FIELDS): raise ValueError("malformed BLASTP row")
        qid, sid = f[0], f[1]
        if qid not in query_map or sid not in reference_map: raise ValueError("unknown query/reference")
        try:
            nums = [float(x) for x in f[2:]]
            ints = [int(f[i]) for i in (3,4,5,6,7,8,9,10,11,15,16)]
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid BLASTP number") from exc
        qlen, slen = ints[-2:]
        metadata_q = query_map[qid].get("length", query_map[qid].get("query_length"))
        metadata_s = reference_map[sid].get("length", reference_map[sid].get("reference_length"))
        if metadata_q is not None and qlen != metadata_q or metadata_s is not None and slen != metadata_s:
            raise ValueError("BLASTP length disagrees with metadata")
        if min(qlen, slen, ints[0]) < 1: raise ValueError("invalid dimensions")
        qstart, qend, sstart, send = ints[5:9]
        if not 0 <= nums[0] <= 100: raise ValueError("invalid percent identity")
        if not (0 <= ints[1] <= ints[0] and 0 <= ints[2] <= ints[0] and
                0 <= ints[3] <= ints[0] and 0 <= ints[4] <= ints[0]):
            raise ValueError("inconsistent alignment counts")
        if not (1 <= qstart <= qlen and 1 <= qend <= qlen and 1 <= sstart <= slen and 1 <= send <= slen): raise ValueError("invalid coordinates")
        reference_metadata = {
            key: value for key, value in reference_map[sid].items()
            if key != "sequence"
        }
        row = {"query_id": qid, "reference_id": sid, "hsp_ordinal": ordinal, "percent_identity": nums[0],
               "alignment_length": ints[0], "identities": ints[1], "positives": ints[2], "mismatches": ints[3],
               "gap_openings": ints[4], "query_start": min(qstart,qend)-1, "query_end": max(qstart,qend),
               "reference_start": min(sstart,send)-1, "reference_end": max(sstart,send),
               "query_length": qlen, "reference_length": slen, "query_coverage": abs(qend-qstart)+1,
               "reference_coverage": abs(send-sstart)+1, "evalue": float(f[12]), "bitscore": float(f[13]),
                "score": float(f[14]),
                "raw_output_sha256": raw_output_hash, "reference": reference_metadata}
        row["coordinate_convention"] = "zero-based half-open; BLAST inclusive coordinates normalized"
        row["query_coverage_denominator"] = qlen
        row["reference_coverage_denominator"] = slen
        row["query_coverage_fraction"] = row["query_coverage"]/qlen
        row["reference_coverage_fraction"] = row["reference_coverage"]/slen
        if not all(math.isfinite(row[k]) for k in ("percent_identity","evalue","bitscore","score")): raise ValueError("nonfinite score")
        rows.append(row)
    return sorted(rows, key=lambda r: (r["query_id"], r["reference_id"], r["query_start"], r["reference_start"], r["hsp_ordinal"]))


def run_blastp(query_fasta, database_prefix, output_directory, query_map, reference_map, *, config=None, runtime=None, timeout=180, max_bytes=400_000_000):
    runtime = runtime or inspect_blastp_runtime(config)
    if runtime["status"] != "available": return {"status": "DEPENDENCY_UNAVAILABLE", "rows": [], "runtime": runtime}
    directory = Path(output_directory).resolve(); directory.mkdir(parents=True, exist_ok=True)
    output = directory / "blastp.tsv"; argv = _args(runtime["blastp"]["path"], Path(query_fasta).resolve(strict=True), Path(database_prefix).resolve(), output)
    try:
        result = bounded_process.run_captured(argv, directory, "blastp.stdout.log", "blastp.stderr.log", timeout, max_bytes)
        if result.returncode:
            return {"status": "SEARCH_FAILED", "rows": [], "argv": argv, **_raw_identity(output)}
        raw = output.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        if len(raw) > max_bytes:
            return {"status": "SEARCH_TRUNCATED", "rows": [], "argv": argv,
                    "raw_output": str(output), "raw_output_sha256": digest}
        rows = parse_blastp_tabular(raw.decode(), query_map, reference_map, digest)
        by_query = {}
        for row in rows:
            by_query.setdefault(row["query_id"], {}).setdefault(row["reference_id"], 0)
            by_query[row["query_id"]][row["reference_id"]] += 1
        capped = any(len(refs) >= 1000 or any(count >= 100 for count in refs.values())
                     for refs in by_query.values())
        status = "SEARCH_TRUNCATED" if capped else (STATUS_MATCH if rows else STATUS_EMPTY)
        return {"status": status, "rows": rows, "argv": argv, "raw_output": str(output), "raw_output_sha256": digest,
                "stdout_path": str(directory / "blastp.stdout.log"), "stderr_path": str(directory / "blastp.stderr.log"),
                "runtime": runtime, "profile": profile_identity(),
                "query_fasta": str(Path(query_fasta).resolve()), "database_prefix": str(Path(database_prefix).resolve())}
    except (TimeoutError, KeyboardInterrupt):
        return {"status": "SEARCH_INTERRUPTED", "rows": [], "argv": argv, **_raw_identity(output)}
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        status = "SEARCH_TRUNCATED" if "byte" in str(exc).lower() or "output exceeds" in str(exc).lower() else "SEARCH_FAILED"
        return {"status": status, "rows": [], "error": str(exc), "argv": argv, **_raw_identity(output)}