import unittest

from satellite_discovery.m8_blastn_profile import (
    BLAST_ARCHIVE_MD5,
    BLAST_ARCHIVE_SHA256,
    BLASTN_BINARY_SHA256,
    EVALUE,
    MAKEBLASTDB_BINARY_SHA256,
    MASKING_BRANCHES,
    MAX_HSPS,
    MAX_TARGET_SEQS,
    NUM_THREADS,
    OUTFMT,
    OUTFMT_FIELDS,
    QUERY_LENGTH_CUTOFF,
    TASK_SETTINGS,
    build_blastn_args,
    is_supported_runtime,
    method_applicability,
    output_cap_reached,
    task_for_query_length,
)
from satellite_discovery.m8_contracts import completed_search_status


class BlastnProfileTests(unittest.TestCase):
    def test_pinned_profile_and_selector_boundary(self):
        self.assertEqual(BLAST_ARCHIVE_MD5, "bdec166721de3b55f90a3badc83538e8")
        self.assertEqual(
            BLAST_ARCHIVE_SHA256,
            "3888112d8207831aa47371d93583c601f058f88b5db22dc782438b039a3a411b",
        )
        self.assertEqual(
            BLASTN_BINARY_SHA256,
            "33b64bc67d3149cee2459b2f7766b363323df632cf12c099546de00aea9698b5",
        )
        self.assertEqual(
            MAKEBLASTDB_BINARY_SHA256,
            "c1ffdcf6f15d1d8d75377cc9f37afa42bc9fa06678903bad77c2641e60778fce",
        )
        self.assertEqual(QUERY_LENGTH_CUTOFF, 50)
        self.assertEqual(
            [task_for_query_length(length) for length in (1, 16, 49, 50, 51)],
            ["blastn-short", "blastn-short", "blastn-short", "blastn", "blastn"],
        )
        self.assertEqual(method_applicability(6), {
            "informative": False,
            "reason": "QUERY_SHORTER_THAN_WORD_SIZE",
            "task": "blastn-short",
            "word_size": 7,
        })
        self.assertTrue(method_applicability(7)["informative"])
        self.assertTrue(method_applicability(16)["informative"])
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=True,
                method_informative=method_applicability(6)["informative"]),
            "INSUFFICIENT_INFORMATION",
        )
        self.assertEqual(len(OUTFMT_FIELDS), 15)
        self.assertEqual(
            OUTFMT,
            "6 qseqid sseqid pident length mismatch gapopen qstart qend "
            "sstart send evalue bitscore qlen slen sstrand",
        )
        self.assertEqual(MAX_TARGET_SEQS, 1000)
        self.assertEqual(MAX_HSPS, 1000)
        self.assertEqual(NUM_THREADS, 1)
        self.assertEqual(EVALUE, "1000")
        self.assertEqual(MASKING_BRANCHES, {
            "dust_masked": "yes",
            "dust_unmasked": "no",
        })
        self.assertEqual(TASK_SETTINGS["blastn-short"], {
            "word_size": 7, "reward": 1, "penalty": -3,
            "gapopen": 5, "gapextend": 2,
        })
        self.assertEqual(TASK_SETTINGS["blastn"], {
            "word_size": 11, "reward": 2, "penalty": -3,
            "gapopen": 5, "gapextend": 2,
        })

    def test_argv_freezes_every_production_parameter(self):
        command = build_blastn_args(
            "/usr/bin/blastn", "query.fa", "refs/db", "hits.tsv",
            50, "dust_masked",
        )
        options = dict(zip(command[1::2], command[2::2]))
        self.assertEqual(command[0], "/usr/bin/blastn")
        self.assertEqual(options, {
            "-query": "query.fa",
            "-db": "refs/db",
            "-task": "blastn",
            "-strand": "both",
            "-dust": "yes",
            "-soft_masking": "true",
            "-word_size": "11",
            "-reward": "2",
            "-penalty": "-3",
            "-gapopen": "5",
            "-gapextend": "2",
            "-evalue": "1000",
            "-max_target_seqs": "1000",
            "-max_hsps": "1000",
            "-num_threads": "1",
            "-outfmt": OUTFMT,
            "-out": "hits.tsv",
        })
        short = build_blastn_args(
            "blastn", "q.fa", "db", "out.tsv", 49, "dust_unmasked",
        )
        short_options = dict(zip(short[1::2], short[2::2]))
        self.assertEqual(short_options["-task"], "blastn-short")
        self.assertEqual(short_options["-word_size"], "7")
        self.assertEqual(short_options["-reward"], "1")
        self.assertEqual(short_options["-dust"], "no")

    def test_cap_accounting_is_conservative_for_targets_and_hsps(self):
        rows = [
            {"query_id": "q", "reference_id": "r1"},
            {"query_id": "q", "reference_id": "r1"},
        ]
        self.assertTrue(output_cap_reached(rows, max_hsps=2))
        self.assertFalse(output_cap_reached(rows, max_hsps=3))
        target_rows = [
            {"query_id": "q", "reference_id": "r1"},
            {"query_id": "q", "reference_id": "r2"},
        ]
        self.assertTrue(output_cap_reached(target_rows, max_target_seqs=2))
        self.assertFalse(output_cap_reached([], max_target_seqs=1))

    def test_unvalidated_platforms_are_typed_dependency_unavailable(self):
        self.assertTrue(is_supported_runtime("Linux", "x86_64", "2.17.0+", "2.17.0+"))
        for system, machine in (
            ("Windows", "AMD64"),
            ("Darwin", "arm64"),
            ("Linux", "aarch64"),
        ):
            with self.subTest(system=system, machine=machine):
                available = is_supported_runtime(
                    system, machine, "2.17.0+", "2.17.0+")
                self.assertFalse(available)
                self.assertEqual(
                    completed_search_status(
                        hit_count=0, accounting_complete=True,
                        dependency_available=available),
                    "DEPENDENCY_UNAVAILABLE",
                )
        self.assertFalse(
            is_supported_runtime("Linux", "x86_64", "2.17.0", "2.17.0+"))


if __name__ == "__main__":
    unittest.main()