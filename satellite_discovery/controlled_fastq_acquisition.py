"""Explicit, one-run FASTQ acquisition guarded by fresh archive revalidation.

Dry-run is the default. This module never invokes QC, assembly, or analysis.
"""
import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import public_virus, sequence_downloader
from .public_virus_acquisition_preflight import (
    MAX_COMPRESSED_BYTES,
    build_acquisition_preflight,
    fastq_manifest_sha256,
)

LINKAGE_FIELDS = (
    "run_accession", "experiment_accession", "sample_accession", "biosample",
    "study_accession", "bioproject",
)


def _blocked(code, detail):
    return {"code": code, "detail": detail}


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
    retriever,
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
    storage_directory, confirmation_callback, *, provenance_document=None,
    retriever=None, downloader=None, disk_checker=None,
):
    """Acquire exactly one reviewed run after fresh checks and live confirmation.

    ``confirmation_callback`` is called only after fresh metadata and preflight
    succeed. It must return the exact run and approved resource caps. This keeps
    a saved approval JSON or dry-run plan from acting as a download command.
    """
    if os.environ.get("CI", "").strip().casefold() in {"1", "true", "yes"}:
        return {
            "status": "blocked",
            "reasons": [_blocked(
                "acquisition_disabled_in_ci",
                "Real FASTQ acquisition is disabled in CI environments.",
            )],
        }
    retriever = retriever or public_virus.retrieve_accession
    downloader = downloader or sequence_downloader.download_file
    disk_checker = disk_checker or sequence_downloader.check_disk
    initial = plan_single_run(
        accession_document, raw_metadata_directory, review_decision,
        provenance_document=provenance_document,
        storage_directory=storage_directory,
    )
    if initial.get("status") != "ready_for_operator_confirmation":
        return {"status": "blocked", "plan": initial, "reasons": initial["reasons"]}

    fresh_plan, fresh_document, files, retrieved_utc, fresh_reasons = _fresh_revalidation(
        accession_document, review_decision,
        provenance_document=provenance_document,
        storage_directory=storage_directory,
        retriever=retriever,
    )
    if fresh_reasons:
        return {"status": "blocked", "plan": fresh_plan, "reasons": fresh_reasons}
    if fresh_plan.get("fastq_manifest_sha256") != initial.get("fastq_manifest_sha256"):
        return {
            "status": "blocked", "plan": fresh_plan,
            "reasons": [_blocked(
                "fastq_manifest_changed",
                "Fresh complete FASTQ manifest differs from the original reviewed plan.",
            )],
        }

    run = fresh_plan["run_accession"]
    scope = review_decision["scope"]
    request = {
        "run_accession": run,
        "selected_virus": fresh_plan["selected_virus"],
        "fastq_manifest_sha256": fresh_plan["fastq_manifest_sha256"],
        "expected_compressed_bytes": fresh_plan["expected_compressed_bytes"],
        "required_storage_headroom_bytes": fresh_plan["required_storage_headroom_bytes"],
        "approved_max_compressed_bytes": scope["max_compressed_bytes"],
        "approved_max_storage_bytes": scope["max_storage_bytes"],
    }
    confirmation = confirmation_callback(request) if callable(confirmation_callback) else None
    if not isinstance(confirmation, dict) or any((
        confirmation.get("run_accession") != run,
        confirmation.get("max_compressed_bytes") != scope["max_compressed_bytes"],
        confirmation.get("max_storage_bytes") != scope["max_storage_bytes"],
    )):
        return {
            "status": "blocked", "plan": fresh_plan,
            "reasons": [_blocked(
                "operator_confirmation_missing_or_mismatched",
                "After revalidation, confirm the exact run accession and both approved resource caps.",
            )],
        }

    if not isinstance(files, list):
        return {
            "status": "blocked", "plan": fresh_plan,
            "reasons": [_blocked("fresh_fastq_manifest_invalid", "Fresh FASTQ metadata is unavailable.")],
        }
    if fastq_manifest_sha256(files) != fresh_plan["fastq_manifest_sha256"]:
        return {
            "status": "blocked", "plan": fresh_plan,
            "reasons": [_blocked("fastq_manifest_changed", "FASTQ manifest changed before transfer.")],
        }
    total_bytes = sum(item["bytes"] for item in files)
    if total_bytes > MAX_COMPRESSED_BYTES or total_bytes > scope["max_compressed_bytes"]:
        return {
            "status": "blocked", "plan": fresh_plan,
            "reasons": [_blocked("compressed_byte_limit_exceeded", "Complete run exceeds the approved byte limit.")],
        }
    try:
        disk_checker(storage_directory, total_bytes)
    except (OSError, RuntimeError, TypeError, ValueError):
        return {
            "status": "blocked", "plan": fresh_plan,
            "reasons": [_blocked("insufficient_or_unavailable_storage", "Storage check failed immediately before transfer.")],
        }

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
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
        "fresh_retrieval_mode": "isolated_empty_snapshot_directory",
        "fresh_archive_manifest": fresh_document.get("manifest", {}),
        "fresh_archive_record": fresh_document.get("record", {}),
        "retrieval_observed_utc": retrieved_utc,
        "acquisition_started_utc": datetime.now(timezone.utc).isoformat(),
        "download_attempts": [],
        "files": [],
        "limitations": [
            "Local retrieval timestamps and snapshot hashes do not authenticate archive origin.",
            "Acquisition records are audit evidence, not proof of biological identity.",
        ],
    }
    sequence_downloader.write_json(audit_path, audit)
    try:
        for spec in files:
            if downloader is sequence_downloader.download_file:
                path = downloader(
                    spec, output, attempt_history=audit["download_attempts"],
                    attempt_recorder=lambda item: sequence_downloader.write_json(
                        audit_path, audit,
                    ),
                )
            else:
                path = downloader(spec, output)
            sequence_downloader.write_json(audit_path, audit)
            item = {
                "name": spec["name"], "url": spec["url"], "role": spec["role"],
                "expected_bytes": spec["bytes"], "observed_bytes": path.stat().st_size,
                "expected_md5": spec["md5"], "observed_md5": sequence_downloader.checksum(path, "md5"),
                "path": path.name,
            }
            if item["observed_bytes"] != spec["bytes"] or item["observed_md5"] != spec["md5"]:
                raise ValueError("Downloader output failed post-transfer integrity verification")
            audit["files"].append(item)
            sequence_downloader.write_json(audit_path, audit)
    except Exception as exc:
        audit["status"] = "failed"
        audit["failure"] = {"type": type(exc).__name__, "detail": str(exc)}
        audit["finished_utc"] = datetime.now(timezone.utc).isoformat()
        sequence_downloader.write_json(audit_path, audit)
        return {"status": "failed", "audit_path": str(audit_path), "error": str(exc)}
    audit["status"] = "complete"
    audit["finished_utc"] = datetime.now(timezone.utc).isoformat()
    sequence_downloader.write_json(audit_path, audit)
    return {"status": "complete", "audit_path": str(audit_path), "files": audit["files"]}


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
