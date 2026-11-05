"""Focused safety and reproducibility tests for M31's synthetic triage."""
import json
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m31_synthetic_evidence_screening import (
    ROLES,
    _candidate_handoff,
    _synthetic_sequences,
    triage,
)


def _queries(candidate_id, *, incomplete=False, low_complexity=False):
    return [
        {
            "candidate_id": candidate_id,
            "panel_role": role,
            "aggregate_status": (
                "PARTIAL" if incomplete and role == "virus_helper" else "COMPLETE"
            ),
            "low_complexity": low_complexity,
        }
        for role in ROLES
    ]


def _match(candidate_id, role, identity=99.0, coverage=0.8):
    return {
        "candidate_id": candidate_id,
        "panel_role": role,
        "alignment": {
            "percent_identity": identity,
            "query_coverage": coverage,
        },
    }


class M31SyntheticEvidenceTests(unittest.TestCase):
    def test_fixed_seed_sequences_and_truth_are_separate(self):
        first = _synthetic_sequences()
        second = _synthetic_sequences()
        self.assertEqual(first, second)
        self.assertEqual(len(first["queries"]), 9)
        self.assertEqual(len(first["panel"]), 6)
        self.assertTrue(all("scenario" in case for case in first["truth"]))
        panel = first["panel"]
        queries = {candidate_id: sequence for candidate_id, sequence, _ in first["queries"]}
        self.assertEqual(queries["q007"], panel["SYN006.1"][:42])
        self.assertEqual(queries["q008"], panel["SYN006.1"][:140])
        self.assertNotEqual(panel["SYN006.1"], panel["SYN001.1"])

    def test_candidate_handoff_excludes_retrospective_truth(self):
        fixture = _synthetic_sequences()
        with tempfile.TemporaryDirectory() as temporary:
            path = _candidate_handoff(temporary, fixture["queries"])
            document = json.loads(path.read_text())
        serialized = json.dumps(document).lower()
        self.assertNotIn("truth", document)
        self.assertNotIn("split", serialized)
        self.assertNotIn("scenario", serialized)
        self.assertTrue(all(
            record["m6_support_status"] == "NOT_EVALUATED"
            for record in document["records"]
        ))
        self.assertEqual(document["m6_evidence"]["support_status"], "NOT_EVALUATED")

    def test_triage_reports_target_helper_conflict_and_abstention(self):
        query_rows = (
            _queries("target")
            + _queries("helper")
            + _queries("conflict")
            + _queries("absent")
            + _queries("repetitive", low_complexity=True)
            + _queries("partial", incomplete=True)
        )
        matches = [
            _match("target", "satellite_subviral"),
            _match("helper", "virus_helper"),
            _match("conflict", "satellite_subviral"),
            _match("conflict", "virus_helper"),
            _match("partial", "satellite_subviral"),
        ]
        results = {row["candidate_id"]: row for row in triage(query_rows, matches)}
        self.assertEqual(results["target"]["outcome"], "REVIEW_PRIORITY")
        self.assertEqual(results["helper"]["outcome"], "BACKGROUND_LIKE")
        self.assertEqual(results["conflict"]["outcome"], "CONFLICTING_EVIDENCE")
        self.assertEqual(results["absent"]["outcome"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(results["repetitive"]["outcome"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(results["partial"]["outcome"], "INSUFFICIENT_EVIDENCE")
        self.assertTrue(all(row["m29_linkage"] == "NOT_SUPPLIED" for row in results.values()))

    def test_low_coverage_does_not_qualify_as_strong_similarity(self):
        rows = _queries("short")
        result = triage(rows, [_match("short", "satellite_subviral", coverage=0.1)])
        self.assertEqual(result[0]["outcome"], "INSUFFICIENT_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
