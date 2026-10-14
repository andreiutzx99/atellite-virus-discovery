"""Dry-run preflight and permanently disabled one-run FASTQ acquisition API.

The production API fails closed before archive retrieval or FASTQ transfer.
This module never invokes QC, assembly, or analysis.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

from . import sequence_downloader
from .public_virus_acquisition_preflight import (
    build_acquisition_preflight,
)

LINKAGE_FIELDS = (
    "run_accession", "experiment_accession", "sample_accession", "biosample",
    "study_accession", "bioproject",
)

LIVE_ACQUISITION_BLOCK_CODE = "trusted_authorization_unavailable"
LIVE_ACQUISITION_BLOCK_DETAIL = (
    "Live FASTQ acquisition is disabled: no independently trusted, "
    "replay-protected operator authorization mechanism is implemented."
)
MAX_ARCHIVE_SNAPSHOT_FILES = 64
MAX_ARCHIVE_SNAPSHOT_BYTES = 50 * 1024 * 1024
ENA_REDIRECT_HOSTS = frozenset({"ftp.sra.ebi.ac.uk", "ftp.ebi.ac.uk"})


class TrustedAuthorizationUnavailable(RuntimeError):
    """Raised at the controlled transfer boundary until trusted authorization exists."""


def _blocked(code, detail):
    return {"code": code, "detail": detail}


def _retain_archive_snapshots(source, destination, snapshot_index):
    """Atomically preserve a bounded exact-byte copy of fresh archive snapshots."""
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_dir():
        raise ValueError("Fresh archive snapshot directory is missing or unsafe")
    if not isinstance(snapshot_index, list) or not snapshot_index:
        raise ValueError("Fresh archive snapshot index is missing")
    if len(snapshot_index) > MAX_ARCHIVE_SNAPSHOT_FILES:
        raise ValueError("Fresh archive snapshot file-count limit exceeded")
    names = []
    for item in snapshot_index:
        if not isinstance(item, dict) or not {"name", "sha256"} <= set(item):
            raise ValueError("Malformed fresh archive snapshot index entry")
        name = item["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name):
            raise ValueError("Unsafe archive snapshot filename")
        if name in names or name in {".", ".."}:
            raise ValueError("Duplicate or unsafe archive snapshot filename")
        if not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("Malformed archive snapshot SHA256")
        names.append(name)
    actual = list(source.iterdir())
    if len(actual) != len(names) or {p.name for p in actual} != set(names):
        raise ValueError("Fresh archive snapshots are missing, duplicated or unindexed")
    records = []
    total = 0
    for item in snapshot_index:
        path = source / item["name"]
        if path.is_symlink() or not path.is_file():
            raise ValueError("Fresh archive snapshot is not a regular file")
        size = path.stat().st_size
        total += size
        if total > MAX_ARCHIVE_SNAPSHOT_BYTES:
            raise ValueError("Fresh archive snapshot byte limit exceeded")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError("Fresh archive snapshot digest mismatch")
        records.append({"name": item["name"], "sha256": digest, "bytes": size})
    destination = destination.absolute()
    parent = destination.parent
    current = Path(destination.anchor)
    for part in destination.parts[1:-1]:
        current = current / part
        if current.exists() and (current.is_symlink() or getattr(current, "is_junction", lambda: False)()):
            raise ValueError("Archive evidence destination traverses a link")
    if not parent.is_dir() or destination.exists() or destination.is_symlink():
        raise FileExistsError("Archive evidence destination is unavailable or already exists")
    destination.mkdir()
    try:
        for item in records:
            data = (source / item["name"]).read_bytes()
            if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
                raise ValueError("Archive snapshot changed while being preserved")
            target = destination / item["name"]
            temporary = destination / ("." + item["name"] + ".tmp")
            with temporary.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        manifest = {
            "schema": "controlled-acquisition-archive-evidence-v1",
            "source_identity": "NCBI SRA / ENA (retrieval claim; not authenticated)",
            "snapshots": records,
            "total_bytes": total,
        }
        temporary = destination / ".snapshot_manifest.json.tmp"
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination / "snapshot_manifest.json")
        return manifest
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _safe_output_path(output_directory, storage_directory):
    output, storage = Path(output_directory), Path(storage_directory)
    if ".." in output.parts or ".." in storage.parts:
        raise ValueError("Output or approved storage path contains traversal")
    for path in (output, storage):
        current = Path(path.absolute().anchor)
        for part in path.absolute().parts[1:]:
            current = current / part
            if current.exists() and (
                current.is_symlink() or getattr(current, "is_junction", lambda: False)()
            ):
                raise ValueError("Output or storage path traverses a link")
    try:
        storage = storage.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Approved storage scope cannot be resolved") from exc
    output = output.resolve(strict=False)
    try:
        output.relative_to(storage)
    except ValueError as exc:
        raise ValueError("Output is outside approved storage scope") from exc
    return output


def _check_destination_space(output_directory, compressed_bytes, storage_cap_bytes):
    output = Path(output_directory)
    if compressed_bytes < 0 or storage_cap_bytes < 0:
        raise ValueError("Storage budgets must be non-negative")
    required = 3 * compressed_bytes + 256 * 1024 * 1024
    if required > storage_cap_bytes:
        raise RuntimeError("Required destination headroom exceeds approved storage cap")
    destination_volume = output if output.exists() else output.parent
    free = shutil.disk_usage(destination_volume).free
    if free < required:
        raise RuntimeError(f"Insufficient destination filesystem headroom: need {required:,} bytes")
    return {"required_bytes": required, "free_bytes": free}


def _atomic_audit_write(path, data):
    path = Path(path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Acquisition audit path is unsafe")
    fd, temporary = tempfile.mkstemp(prefix=".acquisition-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _create_acquisition_lock(output):
    output = Path(output)
    lock = output.parent / ("." + output.name + ".acquisition.lock")
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError("Acquisition destination is already locked") from None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"status": "owned", "pid": os.getpid()}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    return lock


def _validate_ena_redirect_target(url):
    parts = urlsplit(url)
    if (
        parts.scheme != "https" or parts.hostname not in ENA_REDIRECT_HOSTS
        or parts.port is not None or parts.username or parts.password
    ):
        raise ValueError("Unapproved ENA redirect destination")
    return url


class _ENARedirectHandler(HTTPRedirectHandler):
    """Reject an unapproved redirect before urllib makes the redirected request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            _validate_ena_redirect_target(newurl)
        except ValueError:
            raise HTTPError(req.full_url, code, "Unapproved ENA redirect destination", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _controlled_ena_opener():
    return build_opener(_ENARedirectHandler())


def _require_trusted_authorization():
    """Fail closed; local files, callbacks, environment and CLI flags are not trust anchors."""
    raise TrustedAuthorizationUnavailable(LIVE_ACQUISITION_BLOCK_DETAIL)


def plan_single_run(
    accession_document, raw_metadata_directory, review_decision, *,
    provenance_document=None, storage_directory=None,
):
    """Recompute the local review gate and return a non-executable dry-run plan."""
    return build_acquisition_preflight(
        accession_document, raw_metadata_directory, review_decision,
        provenance_document=provenance_document,
        storage_directory=storage_directory,
    )


def _fresh_revalidation(
    accession_document, review_decision, *, provenance_document, storage_directory,
    retriever, evidence_directory,
):
    original = accession_document.get("record", {})
    run = original.get("run_accession")
    virus = (original.get("public_virus") or {}).get("virus")
    with tempfile.TemporaryDirectory(prefix="controlled-fastq-fresh-") as temp:
        try:
            fresh = retriever(run, virus, temp, offline=False)
        except Exception as exc:
            return None, None, None, None, [_blocked(
                "fresh_archive_retrieval_failed",
                f"Fresh archive metadata could not be retrieved ({type(exc).__name__}).",
            )]
        retrieved_utc = datetime.now(timezone.utc).isoformat()
        manifest = fresh.get("manifest", {})
        fresh_record = fresh.get("record", {})
        try:
            retained_evidence = _retain_archive_snapshots(
                Path(temp) / "raw_metadata", evidence_directory,
                manifest.get("snapshot_index"),
            )
        except (OSError, TypeError, ValueError) as exc:
            return None, fresh, None, retrieved_utc, [_blocked(
                "fresh_archive_evidence_unavailable",
                f"Fresh archive evidence could not be safely retained ({type(exc).__name__}).",
            )]
        manifest["retained_archive_evidence"] = retained_evidence
        reasons = []
        if manifest.get("retrieval_mode") != "archive_client":
            reasons.append(_blocked(
                "fresh_archive_retrieval_unverified",
                "Fresh revalidation did not use the online archive client.",
            ))
        if manifest.get("archive_errors"):
            reasons.append(_blocked(
                "fresh_archive_metadata_incomplete",
                "NCBI or ENA metadata retrieval reported errors.",
            ))
        if any(original.get(key) != fresh_record.get(key) for key in LINKAGE_FIELDS):
            reasons.append(_blocked(
                "fresh_archive_linkage_changed",
                "Fresh metadata changed or omitted a run/sample/study relationship.",
            ))
        if (fresh_record.get("public_virus") or {}).get("virus") != virus:
            reasons.append(_blocked(
                "fresh_archive_virus_changed",
                "Fresh metadata no longer resolves to the reviewed virus.",
            ))
        if reasons:
            return None, fresh, None, retrieved_utc, reasons
        fresh_plan = build_acquisition_preflight(
            fresh, Path(temp) / "raw_metadata", review_decision,
            provenance_document=provenance_document,
            storage_directory=storage_directory,
        )
        if fresh_plan.get("status") != "ready_for_operator_confirmation":
            return fresh_plan, fresh, None, retrieved_utc, [
                _blocked(
                    "fresh_preflight_blocked",
                    "Fresh archive metadata did not pass the complete acquisition preflight.",
                ),
                *fresh_plan.get("reasons", []),
            ]
        try:
            fresh_files = sequence_downloader.files_for_run(fresh_record)
        except (KeyError, TypeError, ValueError):
            return fresh_plan, fresh, None, retrieved_utc, [_blocked(
                "fresh_fastq_manifest_invalid",
                "Fresh metadata does not contain a complete valid FASTQ file set.",
            )]
        return fresh_plan, fresh, fresh_files, retrieved_utc, []


def acquire_single_run(
    accession_document, raw_metadata_directory, review_decision, output_directory,
    storage_directory, confirmation_callback, **kwargs,
):
    """Production acquisition entry point; permanently fail closed in this release."""
    try:
        _require_trusted_authorization()
    except TrustedAuthorizationUnavailable as exc:
        return {
            "status": "blocked",
            "reasons": [_blocked(LIVE_ACQUISITION_BLOCK_CODE, str(exc))],
        }


def main():
    parser = argparse.ArgumentParser(
        description="Dry-run or interactively acquire one explicitly reviewed public-virus FASTQ run."
    )
    parser.add_argument("--intake", required=True, help="Original public_accession.json")
    parser.add_argument("--raw-metadata", required=True, help="Original intake raw_metadata directory")
    parser.add_argument("--decision", required=True, help="Human review decision JSON")
    parser.add_argument("--storage", required=True, help="Directory used for the disk-headroom check")
    parser.add_argument("--output", required=True, help="Directory for FASTQ files and acquisition audit")
    parser.add_argument("--provenance", help="Optional provenance JSON")
    parser.add_argument("--execute", action="store_true", help="Freshly revalidate, then request interactive confirmation")
    args = parser.parse_args()
    load = lambda filename: json.loads(Path(filename).read_text(encoding="utf-8"))
    intake, decision = load(args.intake), load(args.decision)
    provenance = load(args.provenance) if args.provenance else None
    if not args.execute:
        result = plan_single_run(
            intake, args.raw_metadata, decision, provenance_document=provenance,
            storage_directory=args.storage,
        )
    else:
        def confirm(request):
            print(json.dumps(request, indent=2))
            run = input("Type the exact run accession to confirm: ").strip()
            compressed = input("Type the approved maximum compressed bytes: ").strip()
            storage = input("Type the approved maximum storage bytes: ").strip()
            try:
                return {
                    "run_accession": run,
                    "max_compressed_bytes": int(compressed),
                    "max_storage_bytes": int(storage),
                }
            except ValueError:
                return None
        result = acquire_single_run(
            intake, args.raw_metadata, decision, args.output, args.storage,
            confirm, provenance_document=provenance,
        )
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") in {"complete", "ready_for_operator_confirmation"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
