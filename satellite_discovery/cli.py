import argparse
from .database_query import HELPERS
from .workflow import discover


def main():
    parser = argparse.ArgumentParser(description="Phase 2: public SRA metadata discovery (no read analysis)")
    parser.add_argument("--helper", choices=HELPERS)
    parser.add_argument("--limit", type=int, default=10, help="Maximum SRA experiments, not runs (1–1000)")
    parser.add_argument("--min-spots", type=int, default=1_000_000)
    parser.add_argument("--include-controls", action="store_true", help="Retrieve bounded same-study context; controls remain unverified")
    parser.add_argument("--output", default="runs/first-search")
    parser.add_argument("--offline", action="store_true", help="Replay existing response snapshots without network")
    parser.add_argument("--query", help="Override SRA metadata query, e.g. a known-positive benchmark search")
    parser.add_argument("--wizard", action="store_true", help="Interactive prompts for beginners")
    args = parser.parse_args()
    if args.wizard:
        helpers = list(HELPERS)
        for i, helper in enumerate(helpers, 1):
            print(f"{i}. {helper}")
        try:
            choice = int(input("Helper number [1]: ") or "1")
            if not 1 <= choice <= len(helpers):
                raise ValueError()
            args.helper = helpers[choice - 1]
            args.limit = int(input("Maximum experiments [10]: ") or "10")
            args.include_controls = input("Retrieve possible study controls? [y/N]: ").lower() == "y"
            args.output = input("Output folder [runs/first-search]: ") or "runs/first-search"
        except (ValueError, EOFError):
            parser.error("Invalid wizard entry. Restart with a number from the displayed choices.")
    if not args.helper:
        parser.error("Use --helper or --wizard")
    try:
        result = discover(args.helper, args.limit, args.min_spots, args.include_controls,
                          args.output, args.offline, args.query)
    except Exception as exc:
        parser.exit(1, "Discovery failed: " + str(exc) + "\n")
    print("Open " + args.output + "/report.html")
    if result["status"] == "partial":
        parser.exit(2, "Partial result: see manifest.json for failed metadata requests.\n")
