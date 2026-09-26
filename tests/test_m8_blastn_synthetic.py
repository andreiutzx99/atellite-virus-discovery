"""Synthetic-only BLASTN validation for the reviewed M8 technical profile.

Run with BLASTN_EXECUTABLE and MAKEBLASTDB_EXECUTABLE set to the two binaries
from one verified NCBI BLAST+ release. No external or biological databases are
used.
"""
import hashlib
import os
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from satellite_discovery.m8_contracts import completed_search_status
from satellite_discovery.m8_blastn_profile import (
    OUTFMT_FIELDS,
    build_blastn_args,
    output_cap_reached,
    task_for_query_length,
)


def _reverse_complement(sequence):
    return sequence.translate(str.maketrans("ACGT", "TGCA"))[::-1]


def _synthetic_sequence(length, seed):
    generator = random.Random(seed)
    return "".join(generator.choice("ACGT") for _ in range(length))


def _parse_normalized(raw_text):
    rows = []
    for line in raw_text.splitlines():
        values = line.split("\t")
        if len(values) != len(OUTFMT_FIELDS):
            raise ValueError("BLAST tabular output has the wrong field count")
        row = dict(zip(OUTFMT_FIELDS, values))
        qstart, qend = int(row["qstart"]), int(row["qend"])
        sstart, send = int(row["sstart"]), int(row["send"])
        normalized = {
            "query_id": row["qseqid"],
            "reference_id": row["sseqid"],
            "identity_percent": float(row["pident"]),
            "alignment_length": int(row["length"]),
            "mismatch_count": int(row["mismatch"]),
            "gap_open_count": int(row["gapopen"]),
            "query_start_0": min(qstart, qend) - 1,
            "query_end_0": max(qstart, qend),
            "reference_start_0": min(sstart, send) - 1,
            "reference_end_0": max(sstart, send),
            "evalue": float(row["evalue"]),
            "bit_score": float(row["bitscore"]),
            "query_length": int(row["qlen"]),
            "reference_length": int(row["slen"]),
            "subject_strand": row["sstrand"].lower(),
        }
        rows.append(normalized)
    return sorted(rows, key=lambda row: (
        row["query_id"], row["reference_id"], row["query_start_0"],
        row["query_end_0"], row["reference_start_0"],
        row["reference_end_0"], row["subject_strand"],
        row["alignment_length"], row["identity_percent"],
    ))


def _task_for_length(length):
    return task_for_query_length(length)


@unittest.skipUnless(
    os.environ.get("BLASTN_EXECUTABLE")
    and os.environ.get("MAKEBLASTDB_EXECUTABLE"),
    "Set BLASTN_EXECUTABLE and MAKEBLASTDB_EXECUTABLE to run pinned BLAST fixtures",
)
class SyntheticBlastnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blastn = os.environ["BLASTN_EXECUTABLE"]
        cls.makeblastdb = os.environ["MAKEBLASTDB_EXECUTABLE"]
        cls.blastn_version_output = subprocess.run(
            [cls.blastn, "-version"], check=True, capture_output=True, text=True,
        ).stdout.splitlines()[0]
        cls.makeblastdb_version_output = subprocess.run(
            [cls.makeblastdb, "-version"], check=True, capture_output=True, text=True,
        ).stdout.splitlines()[0]
        cls.blastn_version = cls.blastn_version_output.split()[-1]
        cls.makeblastdb_version = cls.makeblastdb_version_output.split()[-1]
        if cls.blastn_version != cls.makeblastdb_version:
            raise RuntimeError("blastn and makeblastdb releases do not match")
        if cls.blastn_version != "2.17.0+":
            raise RuntimeError(f"Unexpected BLASTN release: {cls.blastn_version}")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _write_fasta(self, path, records):
        Path(path).write_text(
            "".join(f">{name}\n{sequence}\n" for name, sequence in records),
            encoding="ascii",
        )

    def _build_db(self, records, name="panel"):
        fasta = self.root / f"{name}.fasta"
        self._write_fasta(fasta, records)
        prefix = self.root / f"{name}-db"
        result = subprocess.run(
            [self.makeblastdb, "-in", str(fasta), "-dbtype", "nucl",
             "-parse_seqids", "-out", str(prefix)],
            cwd=self.root, capture_output=True, text=True, timeout=60,
        )
        if result.returncode:
            self.fail(f"makeblastdb failed on synthetic panel: {result.stderr}")
        return prefix

    def _run(self, query, database, *, dust="yes", max_targets=1000,
             max_hsps=1000, output_name="hits.tsv"):
        query_path = self.root / "query.fasta"
        self._write_fasta(query_path, [("synthetic_query", query)])
        output_path = self.root / output_name
        branch = {"yes": "dust_masked", "no": "dust_unmasked"}.get(dust)
        if branch is None:
            raise ValueError(f"Unsupported DUST setting: {dust!r}")
        command = build_blastn_args(
            self.blastn, query_path, database, output_path, len(query), branch,
            max_target_seqs=max_targets, max_hsps=max_hsps,
        )
        result = subprocess.run(
            command, cwd=self.root, capture_output=True, text=True, timeout=60,
        )
        return command, result, output_path

    def test_word_size_and_49_50_51_selector_keep_short_queries(self):
        lengths = (7, 16, 49, 50, 51)
        sequences = {
            length: _synthetic_sequence(length, 3000 + length)
            for length in lengths
        }
        database = self._build_db([
            (f"ref_{length}", sequence) for length, sequence in sequences.items()
        ])
        self.assertEqual(
            [_task_for_length(length) for length in (7, 49, 50, 51)],
            ["blastn-short", "blastn-short", "blastn", "blastn"],
        )
        for length, query in sequences.items():
            task = _task_for_length(length)
            _command, result, raw_path = self._run(
                query, database, output_name=f"length-{length}.tsv")
            self.assertEqual(result.returncode, 0, result.stderr)
            raw = raw_path.read_text(encoding="utf-8")
            rows = _parse_normalized(raw)
            self.assertTrue(any(
                row["reference_id"] == f"ref_{length}"
                and row["query_length"] == length
                for row in rows
            ), (length, raw))

    def test_exact_forward_reverse_complement_and_raw_readback_determinism(self):
        query = _synthetic_sequence(64, 64001)
        database = self._build_db([
            ("forward_ref", query),
            ("reverse_ref", _reverse_complement(query)),
        ])
        first_command, first, first_path = self._run(
            query, database, output_name="first.tsv")
        _second_command, second, second_path = self._run(
            query, database, output_name="second.tsv")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        first_raw = first_path.read_bytes()
        second_raw = second_path.read_bytes()
        self.assertEqual(hashlib.sha256(first_raw).digest(),
                         hashlib.sha256(second_raw).digest())
        first_rows = _parse_normalized(first_raw.decode("utf-8"))
        second_rows = _parse_normalized(second_raw.decode("utf-8"))
        self.assertEqual(first_rows, second_rows)
        by_reference = {
            row["reference_id"]: row for row in first_rows
            if row["alignment_length"] == len(query)
        }
        self.assertIn("forward_ref", by_reference)
        self.assertEqual(by_reference["forward_ref"]["subject_strand"], "plus")
        self.assertIn("reverse_ref", by_reference)
        self.assertEqual(by_reference["reverse_ref"]["subject_strand"], "minus")
        self.assertEqual(by_reference["reverse_ref"]["query_start_0"], 0)
        self.assertEqual(by_reference["reverse_ref"]["query_end_0"], len(query))
        self.assertEqual(by_reference["reverse_ref"]["reference_start_0"], 0)
        self.assertEqual(by_reference["reverse_ref"]["reference_end_0"], len(query))
        self.assertEqual(by_reference["forward_ref"]["query_start_0"], 0)
        self.assertEqual(by_reference["forward_ref"]["query_end_0"], len(query))
        self.assertEqual(by_reference["forward_ref"]["reference_start_0"], 0)
        self.assertEqual(by_reference["forward_ref"]["reference_end_0"], len(query))
        self.assertIn("-num_threads", first_command)
        self.assertEqual(first_command[first_command.index("-num_threads") + 1], "1")

    def test_partial_local_hsp_preserves_coordinates_and_competing_hits(self):
        query = _synthetic_sequence(90, 901)
        segment = query[23:66]
        database = self._build_db([
            ("partial_ref", "GGGG" + segment + "CCCC"),
            ("competing_a", query),
            ("competing_b", query),
        ])
        _command, result, raw_path = self._run(query, database)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = _parse_normalized(raw_path.read_text(encoding="utf-8"))
        partial = next(row for row in rows if row["reference_id"] == "partial_ref")
        self.assertLess(partial["alignment_length"], partial["query_length"])
        self.assertLessEqual(partial["query_start_0"], 23)
        self.assertGreater(partial["query_end_0"], 65)
        self.assertGreaterEqual(partial["reference_start_0"], 0)
        self.assertLessEqual(partial["reference_end_0"], partial["reference_length"])
        competitors = {row["reference_id"] for row in rows
                       if row["reference_id"].startswith("competing_")}
        self.assertEqual(competitors, {"competing_a", "competing_b"})

    def test_low_complexity_mask_branches_are_separate_and_no_hit_is_complete(self):
        for length in (49, 64):
            with self.subTest(query_length=length):
                repeated = "A" * length
                database = self._build_db(
                    [("repeat_ref", repeated)], name=f"repeat-{length}")
                _masked_command, masked, masked_path = self._run(
                    repeated, database, dust="yes",
                    output_name=f"masked-{length}.tsv")
                _unmasked_command, unmasked, unmasked_path = self._run(
                    repeated, database, dust="no",
                    output_name=f"unmasked-{length}.tsv")
                self.assertEqual(masked.returncode, 0, masked.stderr)
                self.assertEqual(unmasked.returncode, 0, unmasked.stderr)
                self.assertEqual(masked_path.read_text(encoding="utf-8"), "")
                self.assertTrue(_parse_normalized(
                    unmasked_path.read_text(encoding="utf-8")))

        unrelated = _synthetic_sequence(64, 64567)
        no_hit_db = self._build_db([("unrelated_ref", unrelated)], name="no-hit")
        _command, no_hit, no_hit_path = self._run(
            _synthetic_sequence(64, 999), no_hit_db, output_name="no-hit.tsv")
        self.assertEqual(no_hit.returncode, 0, no_hit.stderr)
        self.assertEqual(no_hit_path.read_text(encoding="utf-8"), "")
        self.assertEqual(
            completed_search_status(hit_count=0, accounting_complete=True),
            "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
        )

    def test_target_cap_is_reported_as_truncation_not_a_complete_hit_set(self):
        query = _synthetic_sequence(64, 1234)
        database = self._build_db([
            ("cap_a", query), ("cap_b", query), ("cap_c", query),
        ])
        _command, result, raw_path = self._run(
            query, database, max_targets=1, output_name="capped.tsv")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = _parse_normalized(raw_path.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 1)
        cap_reached = output_cap_reached(rows, max_target_seqs=1)
        self.assertTrue(cap_reached)
        self.assertEqual(
            completed_search_status(
                hit_count=len(rows), accounting_complete=not cap_reached,
                output_truncated=cap_reached),
            "SEARCH_TRUNCATED",
        )

    def test_hsp_cap_is_detected_for_multiple_local_alignments(self):
        first_segment = _synthetic_sequence(36, 777001)
        second_segment = _synthetic_sequence(36, 777002)
        query = (
            first_segment
            + _synthetic_sequence(500, 777003)
            + second_segment
        )
        reference = (
            first_segment
            + _synthetic_sequence(500, 777004)
            + second_segment
        )
        database = self._build_db([("two_locus_ref", reference)])
        _full_command, full_result, full_path = self._run(
            query, database, dust="no", max_hsps=1000,
            output_name="uncapped-hsps.tsv")
        _capped_command, capped_result, capped_path = self._run(
            query, database, dust="no", max_hsps=1,
            output_name="capped-hsps.tsv")
        self.assertEqual(full_result.returncode, 0, full_result.stderr)
        self.assertEqual(capped_result.returncode, 0, capped_result.stderr)
        full_rows = _parse_normalized(full_path.read_text(encoding="utf-8"))
        capped_rows = _parse_normalized(capped_path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(
            sum(row["reference_id"] == "two_locus_ref" for row in full_rows), 2)
        self.assertEqual(
            sum(row["reference_id"] == "two_locus_ref" for row in capped_rows), 1)
        self.assertTrue(output_cap_reached(capped_rows, max_hsps=1))
        self.assertEqual(
            completed_search_status(
                hit_count=len(capped_rows), accounting_complete=False,
                output_truncated=True),
            "SEARCH_TRUNCATED",
        )

    def test_invalid_dependency_database_execution_failure_and_interruption(self):
        query = _synthetic_sequence(64, 7788)
        database = self._build_db([("valid_ref", query)])
        query_path = self.root / "query.fasta"
        self._write_fasta(query_path, [("synthetic_query", query)])
        with self.assertRaises(FileNotFoundError):
            subprocess.run(
                [str(self.root / "missing-blastn"), "-version"],
                check=True, capture_output=True, text=True,
            )
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=False,
                dependency_available=False),
            "DEPENDENCY_UNAVAILABLE",
        )

        invalid_db = self.root / "invalid-database"
        invalid = subprocess.run(
            [self.blastn, "-query", str(query_path), "-db", str(invalid_db),
             "-task", "blastn", "-out", str(self.root / "invalid.tsv")],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(invalid.returncode, 0)
        failure = subprocess.run(
            [self.blastn, "-query", str(query_path), "-db", str(database),
             "-task", "not-a-blast-task", "-out", str(self.root / "failed.tsv")],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(failure.returncode, 0)
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=False, execution_state="FAILED"),
            "SEARCH_FAILED",
        )

        sleeper = subprocess.Popen(
            [shutil.which("python") or "python", "-c", "import time; time.sleep(30)"],
            cwd=self.root,
        )
        sleeper.terminate()
        sleeper.wait(timeout=5)
        self.assertEqual(
            completed_search_status(
                hit_count=0, accounting_complete=False,
                execution_state="INTERRUPTED"),
            "SEARCH_INTERRUPTED",
        )


if __name__ == "__main__":
    unittest.main()