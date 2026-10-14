"""Test-only synthetic acquisition runner; not included in the application package."""
from datetime import datetime, timezone
from pathlib import Path

from satellite_discovery import sequence_downloader
from satellite_discovery.controlled_fastq_acquisition import (
    _atomic_audit_write, _blocked, _create_acquisition_lock,
    _fresh_revalidation, _safe_output_path,
    plan_single_run,
)
from satellite_discovery.public_virus_acquisition_preflight import (
    MAX_COMPRESSED_BYTES, fastq_manifest_sha256,
)


def run_synthetic_acquisition(
    accession_document, raw_metadata_directory, review_decision, output_directory,
    storage_directory, confirmation, *, retriever, downloader, disk_checker,
):
    """Exercise orchestration with injected synthetic callbacks, in tests only."""
    original = plan_single_run(
        accession_document, raw_metadata_directory, review_decision,
        storage_directory=storage_directory,
    )
    if original.get("status") != "ready_for_operator_confirmation":
        return {"status": "blocked", "plan": original, "reasons": original["reasons"]}
    fresh_plan, fresh, files, retrieved, reasons = _fresh_revalidation(
        accession_document, review_decision, provenance_document=None,
        storage_directory=storage_directory, retriever=retriever,
        evidence_directory=(
            Path(output_directory).parent /
            (Path(output_directory).name + ".archive-evidence")
        ),
    )
    if reasons:
        return {"status": "blocked", "plan": fresh_plan, "reasons": reasons}
    if fresh_plan.get("fastq_manifest_sha256") != original.get("fastq_manifest_sha256"):
        return {"status": "blocked", "plan": fresh_plan, "reasons": [
            _blocked("fastq_manifest_changed", "Fresh manifest differs from reviewed plan."),
        ]}
    scope = review_decision["scope"]
    run = fresh_plan["run_accession"]
    request = {
        "run_accession": run,
        "selected_virus": fresh_plan["selected_virus"],
        "fastq_manifest_sha256": fresh_plan["fastq_manifest_sha256"],
        "expected_compressed_bytes": fresh_plan["expected_compressed_bytes"],
        "required_storage_headroom_bytes": fresh_plan["required_storage_headroom_bytes"],
        "approved_max_compressed_bytes": scope["max_compressed_bytes"],
        "approved_max_storage_bytes": scope["max_storage_bytes"],
    }
    if callable(confirmation):
        confirmation = confirmation(request)
    if not isinstance(confirmation, dict) or any((
        confirmation.get("run_accession") != run,
        confirmation.get("max_compressed_bytes") != scope["max_compressed_bytes"],
        confirmation.get("max_storage_bytes") != scope["max_storage_bytes"],
    )):
        return {"status": "blocked", "plan": fresh_plan, "reasons": [
            _blocked("operator_confirmation_missing_or_mismatched", "Synthetic confirmation did not match reviewed scope."),
        ]}
    if not isinstance(files, list) or fastq_manifest_sha256(files) != fresh_plan["fastq_manifest_sha256"]:
        return {"status": "blocked", "plan": fresh_plan, "reasons": [
            _blocked("fastq_manifest_changed", "Fresh file manifest changed before synthetic transfer."),
        ]}
    total = sum(file["bytes"] for file in files)
    if total > MAX_COMPRESSED_BYTES or total > scope["max_compressed_bytes"]:
        return {"status": "blocked", "plan": fresh_plan, "reasons": [
            _blocked("compressed_byte_limit_exceeded", "Synthetic run exceeds approved byte cap."),
        ]}
    if 3 * total + 256 * 1024 * 1024 > scope["max_storage_bytes"]:
        return {"status": "blocked", "plan": fresh_plan, "reasons": [
            _blocked("insufficient_or_unavailable_storage", "Synthetic headroom exceeds approved cap."),
        ]}
    try:
        output = _safe_output_path(output_directory, storage_directory)
        disk_checker(output.parent, total)
    except (OSError, RuntimeError, TypeError, ValueError):
        return {"status": "blocked", "plan": fresh_plan, "reasons": [
            _blocked("insufficient_or_unavailable_storage", "Synthetic destination check failed."),
        ]}
    try:
        lock = _create_acquisition_lock(output)
    except (OSError, RuntimeError):
        return {"status": "blocked", "plan": fresh_plan, "reasons": [
            _blocked("acquisition_destination_busy", "Synthetic destination is locked."),
        ]}
    if output.exists():
        lock.unlink(missing_ok=True)
        return {"status": "blocked", "plan": fresh_plan, "reasons": [
            _blocked("acquisition_destination_collision", "Synthetic destination already exists."),
        ]}
    try:
        output.mkdir()
    except OSError:
        lock.unlink(missing_ok=True)
        return {"status": "blocked", "plan": fresh_plan, "reasons": [
            _blocked("acquisition_destination_unavailable", "Synthetic output could not be created."),
        ]}
    audit_path = output / "acquisition.json"
    audit = {
        "schema": "controlled-single-run-fastq-acquisition-v1",
        "status": "in_progress",
        "run_accession": run,
        "selected_virus": fresh_plan["selected_virus"],
        "review_decision_identifier": review_decision["decision_identifier"],
        "operator_confirmation": confirmation,
        "approved_scope": scope,
        "fastq_manifest_sha256": fresh_plan["fastq_manifest_sha256"],
        "fresh_retrieval_mode": "isolated_synthetic_snapshot",
        "fresh_archive_manifest": fresh.get("manifest", {}),
        "fresh_archive_record": fresh.get("record", {}),
        "retrieval_observed_utc": retrieved,
        "acquisition_started_utc": datetime.now(timezone.utc).isoformat(),
        "files": [],
        "limitations": [
            "Synthetic test evidence only; no live acquisition authorization.",
            "Local hashes are consistency evidence, not archive authentication.",
        ],
    }
    _atomic_audit_write(audit_path, audit)
    try:
        for spec in files:
            path = downloader(spec, output)
            item = {
                "name": spec["name"], "role": spec["role"],
                "expected_bytes": spec["bytes"], "observed_bytes": path.stat().st_size,
                "expected_md5": spec["md5"],
                "observed_md5": sequence_downloader.checksum(path, "md5"),
            }
            if item["observed_bytes"] != spec["bytes"] or item["observed_md5"] != spec["md5"]:
                raise ValueError("Synthetic transfer failed size or MD5 verification")
            audit["files"].append(item)
            _atomic_audit_write(audit_path, audit)
    except BaseException as exc:
        audit["status"] = "interrupted" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "failed"
        audit["failure"] = {"type": type(exc).__name__}
        audit["finished_utc"] = datetime.now(timezone.utc).isoformat()
        _atomic_audit_write(audit_path, audit)
        lock.unlink(missing_ok=True)
        if audit["status"] == "interrupted":
            raise
        return {"status": "failed", "audit_path": str(audit_path), "error": str(exc)}
    audit["status"] = "complete"
    audit["finished_utc"] = datetime.now(timezone.utc).isoformat()
    _atomic_audit_write(audit_path, audit)
    lock.unlink(missing_ok=True)
    return {"status": "complete", "audit_path": str(audit_path), "files": audit["files"]}
