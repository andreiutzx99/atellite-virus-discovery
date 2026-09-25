"""Phase 3 orchestration; download/QC failures cannot masquerade as completion."""
import copy
import json
import os
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .acquisition_fallback import AcquisitionFailed, diagnostic, run as run_acquisition
from .acquisition_providers import AcquisitionContext, default_provider_registry
from . import acquisition_fallback, acquisition_providers
from .database_query import Client
from .quality_control import QCConfig, run_qc
from .sequence_downloader import check_disk, checksum, download_file, make_plan, write_json
from .model_scope import enforce, POLICY_SHA256


def prepare_reads(directory, max_runs=1, max_bytes=1_000_000_000, offline=False, qc_config=None):
    directory = Path(directory)
    source = directory / "datasets.json"
    rows = [enforce(row) for row in json.loads(source.read_text(encoding="utf-8"))]
    qc_config = qc_config or QCConfig()
    qc_config.validate()
    stage = directory / "phase3"
    stage.mkdir(parents=True, exist_ok=True)
    lock = stage / ".running.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError("Phase 3 is already running or was interrupted. See phase3/.running.lock and recovery instructions.") from None
    os.close(descriptor)
    lock.write_text(str(os.getpid()))
    try:
        return _prepare(source, rows, stage, max_runs, max_bytes, offline, qc_config)
    finally:
        lock.unlink(missing_ok=True)


def _prepare(source, rows, stage, max_runs, max_bytes, offline, qc_config):
    def log(message):
        print(message, flush=True)
        with (stage / "run.log").open("a", encoding="utf-8") as handle:
            handle.write(datetime.now(timezone.utc).isoformat() + " " + message + "\n")

    plan = make_plan(rows, max_runs, max_bytes)
    registry = default_provider_registry()
    parameters = {"version": __version__, "datasets_sha256": checksum(source), "max_runs": max_runs,
                  "max_bytes": max_bytes, "scope_policy_sha256": POLICY_SHA256,
                  "qc": json.loads(json.dumps(asdict(qc_config))),
                  "acquisition_providers": registry.describe(),
                  "acquisition_source_sha256": {
                      "orchestration": checksum(Path(__file__)),
                      "providers": checksum(acquisition_providers.__file__),
                      "fallback": checksum(acquisition_fallback.__file__),
                      "downloader": checksum(Path(__file__).with_name("sequence_downloader.py")),
                      "metadata": checksum(Path(__file__).with_name("metadata.py")),
                      "process_runner": checksum(Path(__file__).with_name("bounded_process.py")),
                      "fastq_qc": checksum(Path(__file__).with_name("quality_control.py")),
                  }}
    parameters_path = stage / "parameters.json"
    if parameters_path.exists() and json.loads(parameters_path.read_text()) != parameters:
        raise ValueError("Phase 3 parameters changed: use a new run output directory")
    write_json(parameters_path, parameters)
    write_json(stage / "download_plan.json", plan)
    previous_history = {}
    prior_manifest_path = stage / "manifest.json"
    if prior_manifest_path.exists():
        try:
            prior_manifest = json.loads(prior_manifest_path.read_text(encoding="utf-8"))
            if prior_manifest.get("parameters") == parameters:
                previous_history = {
                    item.get("accession"): item
                    for item in prior_manifest.get("runs", [])
                    if isinstance(item, dict) and item.get("accession")
                }
        except (OSError, ValueError, TypeError):
            previous_history = {}
    client = Client(stage.parent / "raw_metadata", offline)
    manifest = {"status": "running", "version": __version__, "python": platform.python_version(),
                "command": sys.argv, "started_utc": datetime.now(timezone.utc).isoformat(),
                "parameters": parameters, "runs": [], "errors": [],
                "provider_registry": registry.describe(),
                "provider_fallback_policy": [
                    "timeout", "remote_unavailable", "metadata_unavailable",
                    "record_unavailable", "file_unavailable", "integrity_failure",
                ],
                "biological_validation": "not_performed", "candidate_analysis": "not_implemented"}
    write_json(stage / "manifest.json", manifest)
    try:
        if not plan["selected"]:
            manifest["status"] = "no_suitable_downloads"
            log("No complete FASTQ runs fit current availability, library and byte budgets. See download_plan.json.")
            return manifest
        check_disk(stage, plan["planned_bytes"])
        unknown_sizes = len(plan.get("unknown_size_accessions", []))
        log(f"Plan: {len(plan['selected'])} runs; {plan['planned_bytes'] / 1_000_000:.1f} MB reserved"
            + (f"; {unknown_sizes} run(s) have unknown primary-provider size" if unknown_sizes else ""))
        rows_by_accession = {row["run_accession"]: row for row in rows}
        for run in plan["selected"]:
            prior = previous_history.get(run["accession"], {})
            item = {"accession": run["accession"], "status": "acquiring", "downloads": [],
                    "acquisition_attempts": copy.deepcopy(prior.get("acquisition_attempts", [])),
                    "transfer_attempts": copy.deepcopy(prior.get("transfer_attempts", []))}
            manifest["runs"].append(item)
            write_json(stage / "manifest.json", manifest)

            def save_attempts(attempts):
                item["acquisition_attempts"] = copy.deepcopy(attempts)
                write_json(stage / "manifest.json", manifest)

            def save_transfer_attempt(entry):
                write_json(stage / "manifest.json", manifest)

            try:
                row = rows_by_accession.get(run["accession"])
                if row is None:
                    raise ValueError("Selected run is missing from datasets.json")
                request = AcquisitionContext(
                    row=row,
                    directory=stage / run["accession"],
                    max_bytes=run["budget_reservation"],
                    offline=offline,
                    client=client,
                    progress=log,
                    transfer_attempts=item["transfer_attempts"],
                    transfer_recorder=save_transfer_attempt,
                    downloader=download_file,
                )
                method_names = ["ena_fastq"]
                if not offline and "ncbi_sra_toolkit" in run.get("providers", []):
                    method_names.append("ncbi_sra_toolkit")
                configured = registry.ordered(method_names)
                provider_functions = {
                    provider.name: (lambda selected=provider: selected.acquire(request))
                    for provider in configured
                }

                def verify_provider(artifact):
                    return registry.get(artifact.get("provider")).verify(artifact, request)

                log("Acquiring " + run["accession"] + " via " + " then ".join(method_names))
                artifact = run_acquisition(
                    method_names, provider_functions, verify_provider, save_attempts,
                    retries=0, history=item["acquisition_attempts"],
                    fallback_on={
                        "timeout", "remote_unavailable", "metadata_unavailable",
                        "record_unavailable", "file_unavailable", "integrity_failure",
                    },
                )
                inputs = {}
                for file in artifact["files"]:
                    path = Path(file["path"])
                    inputs[file["role"]] = path
                    item["downloads"].append({
                        **file, "provider": artifact["provider"], "verified": True,
                    })
                item["provider"] = artifact["provider"]
                item["provider_provenance"] = artifact["provenance"]
                item["status"] = "quality_control"
                write_json(stage / "manifest.json", manifest)
                qc = run_qc(inputs, stage / run["accession"] / "qc", qc_config, log)
                item.update({"status": "complete", "input_reads": qc["before"]["reads"],
                             "retained_reads": qc["after"]["reads"], "warnings": qc["warnings"],
                             "qc_report": run["accession"] + "/qc/qc.json"})
                log(f"{run['accession']}: QC complete; {qc['after']['reads']:,}/{qc['before']['reads']:,} reads retained")
            except AcquisitionFailed as exc:
                item["failed_stage"] = item["status"]
                item["acquisition_attempts"] = copy.deepcopy(exc.attempts)
                classes = [attempt.get("failure_class") for attempt in exc.attempts
                           if attempt.get("status") == "failed"]
                item["status"] = "dependency_missing" if classes and classes[-1] == "dependency_missing" else "failed"
                item["failure"] = diagnostic(exc, exc.attempts)
                manifest["errors"].append({
                    "accession": run["accession"], "message": str(exc), **item["failure"],
                })
                log("Run acquisition failed: " + str(exc))
            except Exception as exc:
                item['failed_stage'] = item['status']
                item["status"] = "failed"
                item['failure'] = diagnostic(exc, item.get("acquisition_attempts"))
                manifest["errors"].append({"accession": run["accession"], "message": str(exc), **item['failure']})
                log("Run failed: " + str(exc))
            write_json(stage / "manifest.json", manifest)
        successes = sum(r["status"] == "complete" for r in manifest["runs"])
        all_dependencies_missing = bool(manifest["runs"]) and all(
            row["status"] == "dependency_missing" for row in manifest["runs"]
        )
        manifest["status"] = (
            "complete" if successes == len(manifest["runs"])
            else "partial" if successes
            else "dependency_missing" if all_dependencies_missing
            else "failed"
        )
        return manifest
    except BaseException as exc:
        manifest["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        manifest["errors"].append({"message": str(exc) or type(exc).__name__})
        raise
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(stage / "manifest.json", manifest)
