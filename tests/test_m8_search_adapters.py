"""Offline synthetic tests for the pinned M8 BLASTN adapter."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from satellite_discovery import m8_blastn_profile as profile
from satellite_discovery import m8_search_adapters as adapter


def _row(query="q1", reference="r1", qlen=16, slen=32, strand="plus",
         qstart=1, qend=16, sstart=4, send=19):
    return "\t".join(map(str, (
        query, reference, "100.00", qend - qstart + 1, 0, 0,
        qstart, qend, sstart, send, "1e-20", "40", qlen, slen, strand)))


class M8BlastAdapterTests(unittest.TestCase):
    def test_profile_selector_and_applicability(self):
        self.assertEqual(profile.task_for_query_length(49), "blastn-short")
        self.assertEqual(profile.task_for_query_length(50), "blastn")
        self.assertEqual(profile.task_for_query_length(51), "blastn")
        self.assertEqual(profile.method_applicability(16)["task"], "blastn-short")
        self.assertFalse(profile.method_applicability(6)["informative"])

    def test_parser_exact_reverse_partial_and_deterministic_rows(self):
        raw = _row() + "\n" + _row(reference="r2", strand="minus", qend=8, send=27) + "\n"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        rows = adapter.parse_blast_tabular(
            raw, {"query_id": "q1", "query_length": 16},
            {"r1": {"reference_sha256": "a" * 64},
             "r2": {"reference_sha256": "b" * 64}}, digest)
        self.assertEqual([row["reference_id"] for row in rows], ["r1", "r2"])
        self.assertEqual(rows[0]["query_coverage"], 1.0)
        self.assertEqual(rows[1]["strand"], "-")
        self.assertEqual(rows[1]["raw_row_ordinal"], 2)
        self.assertEqual(rows[1]["reference_coverage"], 24 / 32)

    def test_parser_rejects_malformed_rows_and_unknown_references(self):
        digest = "a" * 64
        with self.assertRaises(ValueError):
            adapter.parse_blast_tabular("q1\tr1\n", {"query_id": "q1", "query_length": 16}, {"r1": {}}, digest)
        with self.assertRaises(ValueError):
            adapter.parse_blast_tabular(_row(reference="missing"), {"query_id": "q1", "query_length": 16}, {"r1": {}}, digest)
        with self.assertRaises(ValueError):
            adapter.parse_blast_tabular(_row().replace("100.00", "nan"), {"query_id": "q1", "query_length": 16}, {"r1": {}}, digest)
        with self.assertRaises(ValueError):
            adapter.parse_blast_tabular(_row().replace("\t0\t0\t1\t16", "\t20\t0\t1\t16"), {"query_id": "q1", "query_length": 16}, {"r1": {}}, digest)

    def test_runtime_wrong_version_and_platform_are_dependency_missing(self):
        missing = {"tool": "blastn", "path": "", "status": "not_found",
                   "version_output": "", "sha256": ""}
        with patch.object(adapter, "_probe", return_value=missing), \
             patch.object(adapter.platform, "system", return_value="Linux"), \
             patch.object(adapter.platform, "machine", return_value="x86_64"):
            result = adapter.inspect_blast_runtime({"blastn_executable": "/nope",
                                                     "makeblastdb_executable": "/nope"})
        self.assertEqual(result["status"], "dependency_missing")

    def test_short_query_does_not_run_and_is_insufficient(self):
        with patch.object(adapter, "inspect_blast_runtime") as inspect:
            result = adapter.run_blast_branch(
                "query.fa", "panel", tempfile.gettempdir(), {"query_id": "q", "query_length": 6},
                {}, "dust_masked")
        inspect.assert_not_called()
        self.assertEqual(result["status"], "INSUFFICIENT_INFORMATION")

    def test_missing_dependency_never_becomes_empty_success(self):
        with patch.object(adapter, "inspect_blast_runtime", return_value={"status": "dependency_missing"}):
            result = adapter.run_blast_branch(
                "query.fa", "panel", tempfile.gettempdir(), {"query_id": "q", "query_length": 16},
                {}, "dust_unmasked")
        self.assertEqual(result["status"], "DEPENDENCY_UNAVAILABLE")

    def test_run_uses_argv_and_reports_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            query = root / "query.fa"
            query.write_text(">q1\n" + "A" * 16 + "\n", encoding="utf-8")
            (root / "blastn_dust_masked.tsv").write_text(_row() + "\n", encoding="utf-8")
            runtime = {
                "status": "available",
                "blastn": {"path": "/opt/blast with spaces/blastn"},
            }
            fake_process = type("Process", (), {"returncode": 0})()
            with patch.object(adapter, "inspect_blast_runtime", return_value=runtime), \
                 patch.object(adapter.bounded_process, "run_captured", return_value=fake_process) as run:
                result = adapter.run_blast_branch(
                    query, root / "panel", root, {"query_id": "q1", "query_length": 16},
                    {"r1": {}}, "dust_masked")
            self.assertEqual(result["status"], "SEARCH_COMPLETED_MATCHES_REPORTED")
            command = run.call_args.args[0]
            self.assertIsInstance(command, list)
            self.assertIn("-strand", command)
            self.assertIn("both", command)
            self.assertIn("-task", command)
            self.assertIn("blastn-short", command)

    def test_timeout_and_byte_limit_are_typed_and_keep_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            query = root / "query.fa"
            query.write_text(">q1\n" + "A" * 16 + "\n", encoding="utf-8")
            output = root / "blastn_dust_masked.tsv"
            output.write_text(_row() + "\n", encoding="utf-8")
            runtime = {"status": "available", "blastn": {"path": "/p/blastn"}}
            with patch.object(adapter, "inspect_blast_runtime", return_value=runtime), \
                 patch.object(adapter.bounded_process, "run_captured", side_effect=TimeoutError("time budget")):
                result = adapter.run_blast_branch(
                    query, root / "panel", root, {"query_id": "q1", "query_length": 16},
                    {"r1": {}}, "dust_masked")
            self.assertEqual(result["status"], "SEARCH_INTERRUPTED")
            self.assertEqual(result["raw_output"], str(output))
            with patch.object(adapter, "inspect_blast_runtime", return_value=runtime), \
                 patch.object(adapter.bounded_process, "run_captured", side_effect=ValueError("output exceeds stage byte budget")):
                result = adapter.run_blast_branch(
                    query, root / "panel", root, {"query_id": "q1", "query_length": 16},
                    {"r1": {}}, "dust_unmasked")
            self.assertEqual(result["status"], "SEARCH_TRUNCATED")

    def test_masking_branches_use_distinct_log_names(self):
        calls = []
        runtime = {"status": "available", "blastn": {"path": "/p/blastn"}}
        fake = type("Process", (), {"returncode": 1})()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            query = root / "query.fa"
            query.write_text(">q1\n" + "A" * 16 + "\n", encoding="utf-8")
            def capture(command, folder, stdout, stderr, **kwargs):
                calls.append((stdout, stderr))
                return fake
            with patch.object(adapter, "inspect_blast_runtime", return_value=runtime), \
                 patch.object(adapter.bounded_process, "run_captured", side_effect=capture):
                for branch in ("dust_masked", "dust_unmasked"):
                    adapter.run_blast_branch(
                        query, root / "panel", root, {"query_id": "q1", "query_length": 16},
                        {"r1": {}}, branch)
        self.assertEqual(calls, [
            ("blastn_dust_masked.stdout.log", "blastn_dust_masked.stderr.log"),
            ("blastn_dust_unmasked.stdout.log", "blastn_dust_unmasked.stderr.log"),
        ])


if __name__ == "__main__":
    unittest.main()