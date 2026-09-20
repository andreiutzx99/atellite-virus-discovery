"""Phase 3 orchestration; download/QC failures cannot masquerade as completion."""
import json
import os
import platform
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .quality_control import QCConfig, run_qc
from .sequence_downloader import check_disk, checksum, download_file, make_plan, write_json


def prepare_reads(directory, max_runs=1, max_bytes=1_000_000_000, offline=False, qc_config=None):
    directory = Path(directory)
    source = directory / "datasets.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
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
    parameters = {"version": __version__, "datasets_sha256": checksum(source), "max_runs": max_runs,
                  "max_bytes": max_bytes, "qc": json.loads(json.dumps(asdict(qc_config)))}
    parameters_path = stage / "parameters.json"
    if parameters_path.exists() and json.loads(parameters_path.read_text()) != parameters:
        raise ValueError("Phase 3 parameters changed: use a new run output directory")
    write_json(parameters_path, parameters)
    write_json(stage / "download_plan.json", plan)
    manifest = {"status": "running", "version": __version__, "python": platform.python_version(),
                "command": sys.argv, "started_utc": datetime.now(timezone.utc).isoformat(),
                "parameters": parameters, "runs": [], "errors": [],
                "biological_validation": "not_performed", "candidate_analysis": "not_implemented"}
    write_json(stage / "manifest.json", manifest)
    try:
        if not plan["selected"]:
            manifest["status"] = "no_suitable_downloads"
            log("No complete FASTQ runs fit current availability, library and byte budgets. See download_plan.json.")
            return manifest
        check_disk(stage, plan["planned_bytes"])
        log(f"Plan: {len(plan['selected'])} complete runs; {plan['planned_bytes'] / 1_000_000:.1f} MB compressed")
        for run in plan["selected"]:
            item = {"accession": run["accession"], "status": "downloading", "downloads": []}
            manifest["runs"].append(item)
            write_json(stage / "manifest.json", manifest)
            try:
                inputs = {}
                for file in run["files"]:
                    log("Retrieving " + file["name"])
                    path = download_file(file, stage / run["accession"] / "raw", offline, log)
                    inputs[file["role"]] = path
                    item["downloads"].append({**file, "sha256": checksum(path), "verified": True})
                item["status"] = "quality_control"
                write_json(stage / "manifest.json", manifest)
                qc = run_qc(inputs, stage / run["accession"] / "qc", qc_config, log)
                item.update({"status": "complete", "input_reads": qc["before"]["reads"],
                             "retained_reads": qc["after"]["reads"], "warnings": qc["warnings"],
                             "qc_report": run["accession"] + "/qc/qc.json"})
                log(f"{run['accession']}: QC complete; {qc['after']['reads']:,}/{qc['before']['reads']:,} reads retained")
            except Exception as exc:
                item["status"] = "failed"
                manifest["errors"].append({"accession": run["accession"], "message": str(exc)})
                log("Run failed: " + str(exc))
            write_json(stage / "manifest.json", manifest)
        successes = sum(r["status"] == "complete" for r in manifest["runs"])
        manifest["status"] = "complete" if successes == len(manifest["runs"]) else "partial" if successes else "failed"
        return manifest
    except BaseException as exc:
        manifest["status"] = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        manifest["errors"].append({"message": str(exc) or type(exc).__name__})
        raise
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(stage / "manifest.json", manifest)
