#!/usr/bin/env python3
"""Run every Phase 7 adversarial case and emit run-bound synthetic evidence."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from satellite_discovery import m21_phase6_governance as gov  # noqa: E402
from satellite_discovery import m21_phase7_evidence as phase7  # noqa: E402
from tests import test_m21_phase7_acceptance_matrix as acceptance  # noqa: E402


def _tested_commit_sha() -> str:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.environ.get("GITHUB_EVENT_NAME") == "pull_request":
        try:
            payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
            return payload["pull_request"]["head"]["sha"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Cannot read pull request head SHA from event payload: {exc}")
    return os.environ.get("GITHUB_SHA", "")


def main() -> int:
    suite = unittest.TestSuite(
        acceptance.M21Phase7AdversarialAcceptanceMatrix("test_" + case)
        for case in phase7.PHASE7_ACCEPTANCE_CASES
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if (not result.wasSuccessful() or result.testsRun != len(phase7.PHASE7_ACCEPTANCE_CASES)
            or result.skipped):
        return 1

    cases = [{
        "case_id": case, "test_name": "test_" + case,
        "expected": "FAIL", "observed": "FAIL",
    } for case in phase7.PHASE7_ACCEPTANCE_CASES]
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    workflow_ref = os.environ.get("GITHUB_WORKFLOW_REF", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    try:
        attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", ""))
    except ValueError:
        return 2
    statement = {
        "schema_version": "m21-phase7-ci-run-statement-v1",
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "workflow": ".github/workflows/tests.yml",
        "workflow_ref": workflow_ref,
        "run_id": run_id,
        "run_attempt": attempt,
        "run_sha": os.environ.get("GITHUB_SHA", ""),
        "tested_commit_sha": _tested_commit_sha(),
        "event_name": event_name,
        "acceptance_tests_conclusion": "success",
        "matrix_results": cases,
        "matrix_results_sha256": gov.digest(cases),
    }
    required = (
        statement["repository"], statement["workflow_ref"], statement["run_id"],
        statement["run_sha"], statement["tested_commit_sha"],
    )
    if not all(required) or event_name not in {"push", "pull_request"} or attempt < 1:
        return 2
    Path("m21_phase7_ci_run_statement.json").write_text(
        json.dumps(statement, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
