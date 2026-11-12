#!/usr/bin/env python3
"""Run M36 preparation checks only; never launches registered matrix attempts."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from satellite_discovery.m36_preparation import (
    audit_m25_generator,
    inspect_assembler_provenance,
    validate_readiness,
)


DESIGN = json.loads(
    (ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json")
    .read_text(encoding="utf-8")
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--evidence",
        type=Path,
        help="evaluator-side readiness evidence JSON; omit to show current blockers",
    )
    parser.add_argument(
        "--audit-one-to-nine",
        action="store_true",
        help="run the small synthetic 1:9 generator fixture only",
    )
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else {}
    result = {
        "readiness": validate_readiness(DESIGN, evidence),
        "m25_generator_audit": audit_m25_generator(
            target_to_background="1:9" if args.audit_one_to_nine else None
        ),
        "assembler_provenance": inspect_assembler_provenance(),
        "registered_matrix_executed": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["readiness"]["status"] == "PREPARATION_GATES_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
