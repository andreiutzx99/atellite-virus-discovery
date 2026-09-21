import argparse
from datetime import datetime
from pathlib import Path
import json
import webbrowser
from .database_query import HELPERS
from .workflow import discover
from .quality_control import QCConfig
from .read_workflow import prepare_reads
from .report_generator import write_reports
from . import __version__


def main():
    parser = argparse.ArgumentParser(description="Public sequencing metadata discovery and bounded FASTQ download/QC")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--helper", choices=HELPERS)
    parser.add_argument("--limit", type=int, default=10, help="Maximum SRA experiments, not runs (1–1000)")
    parser.add_argument("--min-spots", type=int, default=1_000_000)
    parser.add_argument("--include-controls", action="store_true", help="Retrieve bounded same-study context; controls remain unverified")
    parser.add_argument("--output", default=None)
    parser.add_argument("--stage", choices=["metadata", "qc"], default="metadata", help="qc downloads complete runs and performs baseline read QC")
    parser.add_argument("--max-runs", type=int, default=1, help="Maximum complete runs to download/QC")
    parser.add_argument("--max-download-mb", type=int, default=1000, help="Total compressed input budget in decimal MB")
    parser.add_argument("--min-length", type=int, default=30, help="Minimum retained read length; baseline QC setting")
    parser.add_argument("--adapter", action="append", help="Exact adapter sequence; repeat for multiple adapters (default common Illumina core)")
    parser.add_argument("--offline", action="store_true", help="Replay existing response snapshots without network")
    parser.add_argument("--query", help="Additional SRA filter within the selected exact-model scope")
    parser.add_argument("--wizard", action="store_true", help="Interactive prompts for beginners")
    args = parser.parse_args()
    if args.wizard:
        helpers = list(HELPERS)
        for i, helper in enumerate(helpers, 1):
            print(f"{i}. {HELPERS[helper]['name']} ({HELPERS[helper]['catalog']})")
        try:
            choice = int(input("Helper number [1]: ") or "1")
            if not 1 <= choice <= len(helpers):
                raise ValueError()
            args.helper = helpers[choice - 1]
            args.limit = int(input("Maximum experiments [10]: ") or "10")
            args.include_controls = input("Retrieve possible study controls? [y/N]: ").lower() == "y"
            choice = input("Stage: 1 = metadata only, 2 = download and QC [2]: ") or "2"
            if choice not in {"1", "2"}:
                raise ValueError()
            args.stage = "qc" if choice == "2" else "metadata"
            if args.stage == "qc":
                args.max_runs = int(input("Maximum complete runs to download [1]: ") or "1")
                args.max_download_mb = int(input("Total compressed download budget in MB [1000]: ") or "1000")
            default_output = "runs/" + datetime.now().strftime("%Y%m%d-%H%M%S")
            args.output = input(f"Output folder [{default_output}]: ") or default_output
        except (ValueError, EOFError):
            parser.error("Invalid wizard entry. Restart with a number from the displayed choices.")
    if not args.helper:
        parser.error("Use --helper or --wizard")
    args.output = args.output or "runs/" + datetime.now().strftime("%Y%m%d-%H%M%S")
    if not 1 <= args.max_runs <= 100 or args.max_download_mb <= 0:
        parser.error("--max-runs must be 1–100 and --max-download-mb must be positive")
    qc_config = QCConfig(min_length=args.min_length,
                         adapters=tuple(a.upper() for a in args.adapter) if args.adapter else QCConfig().adapters)
    try:
        qc_config.validate()
        result = discover(args.helper, args.limit, args.min_spots, args.include_controls,
                          args.output, args.offline, args.query)
        read_result = None
        if args.stage == "qc":
            read_result = prepare_reads(args.output, args.max_runs, args.max_download_mb * 1_000_000,
                                        args.offline, qc_config)
            write_reports(args.output, json.loads((Path(args.output) / "datasets.json").read_text(encoding="utf-8")))
    except KeyboardInterrupt:
        source = Path(args.output) / "datasets.json"
        if source.exists():
            write_reports(args.output, json.loads(source.read_text(encoding="utf-8")))
        parser.exit(130, "Interrupted. Rerun the same command to resume verified downloads and unfinished QC.\n")
    except Exception as exc:
        source = Path(args.output) / "datasets.json"
        if source.exists():
            write_reports(args.output, json.loads(source.read_text(encoding="utf-8")))
        parser.exit(1, "Discovery failed: " + str(exc) + "\n")
    report = (Path(args.output) / "report.html").resolve()
    print("Open " + str(report))
    if args.wizard:
        webbrowser.open(report.as_uri())
    if read_result and read_result["status"] != "complete":
        parser.exit(2, "Download/QC status: " + read_result["status"] + ". See the report for next steps.\n")
    if result["status"] == "partial":
        parser.exit(2, "Partial result: see manifest.json for failed metadata requests.\n")
