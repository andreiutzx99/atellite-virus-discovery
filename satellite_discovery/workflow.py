import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .database_query import Client, helper_query
from .metadata import parse_packages, enrich_ena
from .metadata_filter import assess
from .report_generator import write_reports


def discover(helper, limit, min_spots, include_controls, directory, offline=False, query=None):
    if not 1 <= limit <= 1000 or min_spots < 0:
        raise ValueError("limit must be 1–1000 and min_spots must be nonnegative")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / "parameters.json"
    stored = json.loads(config_path.read_text()) if config_path.exists() else {}
    resolved_query = query or (stored.get("query") if stored.get("helper") == helper else None) or helper_query(helper)
    config = dict(helper=helper, experiment_limit=limit, min_spots=min_spots,
                  include_study_context=include_controls, query=resolved_query, version=__version__)
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError("This output directory belongs to different parameters. Choose a new run directory.")
    config_path.write_text(json.dumps(config, indent=2))
    client = Client(directory / "raw_metadata", offline)
    manifest = {"software_version": __version__, "python": platform.python_version(),
                "platform": platform.platform(), "command": sys.argv,
                "started_utc": datetime.now(timezone.utc).isoformat(), "parameters": config,
                "database_versions": "Live NCBI/ENA responses archived with retrieval times and SHA256; no fixed release",
                "status": "running", "errors": []}
    rows = []
    def log(message):
        print(message, flush=True)
        with (directory / "run.log").open("a", encoding="utf-8") as handle:
            handle.write(datetime.now(timezone.utc).isoformat() + " " + message + "\n")
    try:
        log("Searching NCBI SRA metadata")
        # Avoid spending the entire pilot budget on one recently deposited
        # study. Sample at most two experiments before trying another study.
        seen_ids, seen_studies, seen_experiments = set(), set(), set()
        manifest["search_rounds"] = []
        while len(seen_ids) < limit:
            exclusions = sorted(seen_studies | seen_experiments)
            term = config["query"]
            if exclusions:
                term += " NOT (" + " OR ".join(x + "[All Fields]" for x in exclusions) + ")"
            search = client.search(term, min(2, limit - len(seen_ids)))
            manifest["search_rounds"].append({"query": term, **search})
            ids = [uid for uid in search["ids"] if uid not in seen_ids]
            if not ids:
                break
            seen_ids.update(ids)
            batch = parse_packages(client.fetch(ids), helper)
            rows.extend(batch)
            seen_studies.update(r["study_accession"] for r in batch if r.get("study_accession"))
            seen_experiments.update(r["experiment_accession"] for r in batch if r.get("experiment_accession"))
            if not batch:
                break
        manifest["examined_experiment_ids"] = sorted(seen_ids)
        if include_controls:
            studies = sorted({r["study_accession"] for r in rows if r.get("study_accession")})
            # Explicit bounded expansion: not a claim of complete control ascertainment.
            manifest["study_context_limit_per_study"] = 5
            manifest["study_context_max_studies"] = 3
            manifest["study_context_studies"] = studies[:3]
            for study in studies[:3]:
                log("Retrieving possible study controls/context: " + study)
                context = client.search(study + "[All Fields]", 5)
                if context["ids"]:
                    rows.extend(parse_packages(client.fetch(context["ids"]), helper, "study_context"))
        rows = list({r["run_accession"]: r for r in reversed(rows)}.values())
        rows.sort(key=lambda r: r["run_accession"])
        for row in rows:
            log("Checking FASTQ metadata: " + row["run_accession"])
            try:
                enrich_ena(client, row)
            except (RuntimeError, ValueError) as exc:
                row["ena_status"] = "failed"
                manifest["errors"].append({"accession": row["run_accession"], "step": "ena", "message": str(exc)})
            assess(row, min_spots)
        write_reports(directory, rows)
        manifest["run_accessions"] = [r["run_accession"] for r in rows]
        manifest["status"] = "partial" if manifest["errors"] else "complete"
        log(f"Wrote {len(rows)} dataset records; status={manifest['status']}")
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["errors"].append({"step": "discovery", "message": str(exc)})
        log("FAILED: " + str(exc))
        raise
    finally:
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["response_snapshots"] = [p.name for p in sorted((directory / "raw_metadata").glob("*.json"))]
        manifest["output_sha256"] = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                                     for name in ("datasets.json", "datasets.csv", "report.html") if (directory / name).exists()}
        (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
