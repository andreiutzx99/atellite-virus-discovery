import hashlib
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from satellite_discovery import m9_search_adapters
from satellite_discovery.m9_search_adapters import (
    parse_blastp_tabular,
    profile_identity,
)


class SearchAdapterTests(unittest.TestCase):
    def test_profile_and_parser_order(self):
        q = {"q": {"length": 10}}
        refs = {"b": {"length": 20}, "a": {"length": 20}}
        row = "q\t{sid}\t50\t4\t2\t3\t1\t0\t2\t5\t7\t10\t1e-2\t4\t8\t10\t20"
        text = row.format(sid="b") + "\n" + row.format(sid="a") + "\n"
        rows = parse_blastp_tabular(text, q, refs, hashlib.sha256(b"x").hexdigest())
        self.assertEqual([r["reference_id"] for r in rows], ["a", "b"])
        self.assertEqual(profile_identity()["task"], "blastp")
        self.assertEqual(rows[0]["query_start"], 1)
        self.assertEqual(rows[0]["query_end"], 5)
        self.assertEqual(rows[0]["reference_start"], 6)
        self.assertEqual(rows[0]["reference_end"], 10)
        self.assertEqual(rows[0]["query_coverage_fraction"], 0.4)
        self.assertEqual(rows[0]["reference_coverage_fraction"], 0.2)
        self.assertNotIn("sequence", rows[0]["reference"])

    def test_malformed_row(self):
        with self.assertRaises(ValueError):
            parse_blastp_tabular("q\ta\n", {"q": {}}, {"a": {}}, "0" * 64)

    def test_output_cap_is_reported_as_truncation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            query = root / "query.faa"
            query.write_text(">q\nM\n", encoding="ascii")
            runtime = {
                "status": "available",
                "blastp": {"path": "/synthetic/blastp"},
            }

            def write_capped(argv, directory, _stdout, _stderr, _timeout, _max_bytes):
                output = Path(argv[argv.index("-out") + 1])
                output.write_bytes(b"x" * 20)
                return SimpleNamespace(returncode=0)

            with patch.object(
                    m9_search_adapters.bounded_process, "run_captured",
                    side_effect=write_capped):
                result = m9_search_adapters.run_blastp(
                    query, root / "db", root / "out",
                    {"q": {"length": 1}}, {"s": {"length": 1}},
                    runtime=runtime, max_bytes=10,
                )
            self.assertEqual(result["status"], "SEARCH_TRUNCATED")
            self.assertEqual(result["raw_output_sha256"], hashlib.sha256(
                b"x" * 20).hexdigest())


if __name__ == "__main__":
    unittest.main()