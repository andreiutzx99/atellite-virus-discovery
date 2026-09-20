"""Bounded, checksum-verified ENA FASTQ retrieval; never truncate a dataset."""
import hashlib
import http.client
import json
import re
import shutil
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def checksum(path, algorithm="sha256"):
    digest = hashlib.new(algorithm)
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, data):
    path = Path(path)
    part = path.with_suffix(path.suffix + ".tmp")
    part.write_text(json.dumps(data, indent=2), encoding="utf-8")
    part.replace(path)


def files_for_run(row):
    accession = row["run_accession"]
    if not re.fullmatch(r"[SED]RR\d+", accession):
        raise ValueError("Invalid run accession")
    columns = [str(row.get(k) or "").split(";") for k in ("fastq_ftp", "fastq_md5", "fastq_bytes")]
    if not columns[0][0] or len({len(c) for c in columns}) != 1:
        raise ValueError("Missing or inconsistent ENA file/MD5/size metadata")
    files = []
    for url, md5, size in zip(*columns):
        url = url if "://" in url else "https://" + url
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.hostname not in {"ftp.sra.ebi.ac.uk", "ftp.ebi.ac.uk"} or parts.port or parts.query or parts.fragment or parts.username:
            raise ValueError("Unsupported ENA download URL")
        name = parts.path.rsplit("/", 1)[-1]
        match = re.fullmatch(re.escape(accession) + r"(?:_([12]))?\.fastq\.gz", name)
        if not match or not re.fullmatch(r"[0-9a-fA-F]{32}", md5) or not size.isdigit() or int(size) <= 0:
            raise ValueError("Unsupported filename or invalid checksum/size")
        files.append({"url": url, "name": name, "md5": md5.lower(), "bytes": int(size),
                      "role": "R" + match[1] if match[1] else "single"})
    roles = [f["role"] for f in files]
    if len(set(roles)) != len(roles):
        raise ValueError("Duplicate ENA file roles")
    if row.get("layout") == "PAIRED":
        if not {"R1", "R2"}.issubset(roles):
            raise ValueError("Paired library has no complete R1/R2 pair; needs format review")
    elif row.get("layout") != "SINGLE" or roles != ["single"]:
        raise ValueError("Unsupported library layout")
    return sorted(files, key=lambda f: f["role"])


def make_plan(rows, max_runs, max_bytes):
    if not 1 <= max_runs <= 100 or max_bytes <= 0:
        raise ValueError("max_runs must be 1–100 and download budget must be positive")
    possible, skipped = [], []
    for row in rows:
        try:
            if row["selection"] == "excluded":
                raise ValueError("Excluded by dataset suitability filters")
            if row.get("platform") != "ILLUMINA":
                raise ValueError("Current QC supports Illumina Phred+33 archive FASTQ only")
            if row.get("library_strategy", "").upper() not in {"RNA-SEQ", "WGS"}:
                raise ValueError("Library strategy needs manual method review")
            if row.get("total_spots") is None:
                raise ValueError("Sequencing depth unknown; not automatically selected")
            files = files_for_run(row)
            possible.append({"accession": row["run_accession"], "study": row.get("study_accession"),
                             "layout": row["layout"], "files": files, "bytes": sum(f["bytes"] for f in files)})
        except ValueError as exc:
            skipped.append({"accession": row["run_accession"], "reason": str(exc)})
    selected, used, studies = [], 0, set()
    # Prefer affordable runs from different studies. This is a compute pilot,
    # not a representative cohort or evidence of biological independence.
    while possible:
        possible.sort(key=lambda r: (r["study"] in studies, r["bytes"], r["accession"]))
        item = possible.pop(0)
        if len(selected) >= max_runs:
            skipped.append({"accession": item["accession"], "reason": "Run budget reached"})
        elif used + item["bytes"] > max_bytes:
            skipped.append({"accession": item["accession"], "required_bytes": item["bytes"],
                            "reason": f"Complete run needs {item['bytes'] / 1_000_000:.1f} MB; {(max_bytes - used) / 1_000_000:.1f} MB remains in the input budget"})
        else:
            selected.append(item)
            used += item["bytes"]
            studies.add(item["study"])
    return {"selected": selected, "skipped": skipped, "planned_bytes": used,
            "max_runs": max_runs, "max_bytes": max_bytes, "selection_policy": "study_diversity_then_smallest_complete_run"}


def download_file(spec, directory, offline=False, progress=print):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / spec["name"]
    partial = path.with_suffix(path.suffix + ".part")
    if path.exists():
        if path.stat().st_size != spec["bytes"] or checksum(path, "md5") != spec["md5"]:
            raise ValueError("Existing FASTQ failed integrity check: " + path.name)
        progress("Reusing verified " + path.name)
        return path
    if offline:
        raise RuntimeError("Offline FASTQ unavailable: " + path.name)
    for attempt in range(3):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > spec["bytes"]:
            raise ValueError("Partial file exceeds expected size: " + path.name)
        if offset == spec["bytes"]:
            if checksum(partial, "md5") != spec["md5"]:
                raise ValueError("Downloaded file MD5 mismatch; partial retained: " + path.name)
            partial.replace(path)
            return path
        try:
            headers = {"User-Agent": "satellite-discovery/0.2.0", "Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            with urlopen(Request(spec["url"], headers=headers), timeout=45) as response:
                status = response.status
                if status == 206:
                    expected = f"bytes {offset}-{spec['bytes'] - 1}/{spec['bytes']}"
                    if response.headers.get("Content-Range") != expected:
                        raise ValueError("Invalid Content-Range; refusing corrupt resume")
                elif status == 200:
                    offset = 0  # Server ignored Range: safely restart, never append.
                else:
                    raise ValueError("Unexpected download HTTP status: " + str(status))
                last = time.monotonic()
                with partial.open("ab" if offset else "wb") as output:
                    total = offset
                    while True:
                        data = response.read(1024 * 1024)
                        if not data:
                            break
                        total += len(data)
                        if total > spec["bytes"]:
                            raise ValueError("Response exceeds declared byte budget")
                        output.write(data)
                        if time.monotonic() - last > 10:
                            progress(f"Downloading {path.name}: {total / spec['bytes']:.0%}")
                            last = time.monotonic()
                if total != spec["bytes"]:
                    raise URLError("Incomplete transfer")
            if checksum(partial, "md5") != spec["md5"]:
                raise ValueError("Downloaded file MD5 mismatch; partial retained: " + path.name)
            partial.replace(path)
            progress("Verified " + path.name)
            return path
        except HTTPError as exc:
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError(f"FASTQ transfer failed with HTTP {exc.code}") from None
            time.sleep(2 ** attempt)
        except (URLError, TimeoutError, ConnectionError, http.client.IncompleteRead):
            if attempt == 2:
                raise RuntimeError("FASTQ connection failed; partial download retained for resume") from None
            time.sleep(2 ** attempt)


def check_disk(directory, compressed_bytes):
    # gzip output and preserved rejected reads need headroom; streaming still
    # handles disk-full errors without marking a stage complete.
    required = 3 * compressed_bytes + 256 * 1024 * 1024
    if shutil.disk_usage(directory).free < required:
        raise RuntimeError(f"Insufficient disk space: need at least {required:,} bytes for this pilot")
