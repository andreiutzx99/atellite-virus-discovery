import gzip
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import residual_reads
from satellite_discovery.residual_reads import prepare_normalized_fastqs, screen_and_triage


class ResidualReadTests(unittest.TestCase):
    def test_unsafe_prefix_and_bad_mate_flags_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "reads.fastq"
            source.write_text("@pair/1\nACGT\n+\nIIII\n", encoding="ascii")
            with self.assertRaises(ValueError):
                prepare_normalized_fastqs(source, None, root / "out", prefix="../escape")
            sam = root / "bad.sam"
            sam.write_text("m6r000000000001\t0\t*\t0\t0\t*\t*\t0\t0\tACGT\tIIII\n", encoding="ascii")
            with self.assertRaises(ValueError):
                screen_and_triage(source, None, sam, root / "triage",
                                  config={"min_read_length": 1, "max_ambiguous_fraction": 1,
                                          "min_entropy_bits": 0, "min_mean_phred": 0},
                                  paired=False)

    def test_normalization_and_triage_preserve_original_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "reads.fastq"
            source.write_bytes(b"@original 1\nACGTACGT\n+\nIIIIIIII\n@second\nNNNNNNNN\n+\n!!!!!!!!\n")
            normalized = prepare_normalized_fastqs(source, None, root / "normalized")
            self.assertEqual(normalized["fragment_count"], 2)
            sam = root / "screen.sam"
            sam.write_text(
                "@HD\tVN:1.6\n"
                "m6r000000000001\t4\t*\t0\t0\t*\t*\t0\t0\tACGTACGT\tIIIIIIII\n"
                "m6r000000000002\t4\t*\t0\t0\t*\t*\t0\t0\tNNNNNNNN\t!!!!!!!!\n",
                encoding="ascii",
            )
            result = screen_and_triage(
                source, None, sam, root / "triage",
                config={"min_read_length": 4, "max_ambiguous_fraction": .5,
                        "min_entropy_bits": 1, "min_mean_phred": 10},
                paired=False,
            )
            self.assertEqual(result["eligible_fragment_ids"], ["m6r000000000001"])
            self.assertEqual(result["retained_unassembled_fragment_ids"], ["m6r000000000002"])
            with gzip.open(root / "triage" / "residual_read1.fastq.gz", "rb") as handle:
                self.assertEqual(handle.read(), source.read_bytes())

    def test_incomplete_primary_accounting_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "reads.fastq"
            source.write_text("@r\nACGT\n+\nIIII\n", encoding="ascii")
            sam = root / "empty.sam"
            sam.write_text("@HD\tVN:1.6\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "Missing primary"):
                screen_and_triage(source, None, sam, root / "out",
                                  config={"min_read_length": 1, "max_ambiguous_fraction": 1,
                                          "min_entropy_bits": 0, "min_mean_phred": 0},
                                  paired=False)

    def test_reference_screen_must_match_declared_collection(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "reads.fastq"
            source.write_text("@read\nACGT\n+\nIIII\n", encoding="ascii")
            sam = root / "wrong-reference.sam"
            sam.write_text(
                "@HD\tVN:1.6\n@SQ\tSN:other\tLN:4\n"
                "m6r000000000001\t4\t*\t0\t0\t*\t*\t0\t0\tACGT\tIIII\n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(ValueError, "sequence dictionary"):
                screen_and_triage(
                    source, None, sam, root / "out",
                    config={"min_read_length": 1, "max_ambiguous_fraction": 1,
                            "min_entropy_bits": 0, "min_mean_phred": 0},
                    paired=False, references={"ref": 4},
                )
            self.assertFalse((root / "out" / "residual_read1.fastq.gz").exists())

    def test_paired_reference_match_excludes_both_mates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            read1, read2 = root / "r1.fastq", root / "r2.fastq"
            read1.write_text("@pair/1\nACGTACGT\n+\nIIIIIIII\n", encoding="ascii")
            read2.write_text("@pair/2\nTGCATGCA\n+\nIIIIIIII\n", encoding="ascii")
            sam = root / "screen.sam"
            sam.write_text(
                "@SQ\tSN:ref\tLN:32\n"
                "m6r000000000001\t65\tref\t1\t60\t8M\t*\t0\t0\tACGTACGT\tIIIIIIII\tNM:i:0\n"
                "m6r000000000001\t141\t*\t0\t0\t*\t*\t0\t0\tTGCATGCA\tIIIIIIII\n",
                encoding="ascii",
            )
            result = screen_and_triage(
                read1, read2, sam, root / "out",
                config={"min_read_length": 1, "max_ambiguous_fraction": 1,
                        "min_entropy_bits": 0, "min_mean_phred": 0},
                paired=True,
            )
            self.assertEqual(result["counts"]["residual_fragments"], 0)
            with gzip.open(root / "out" / "residual_read1.fastq.gz", "rb") as handle:
                self.assertEqual(handle.read(), b"")
            with gzip.open(root / "out" / "residual_read2.fastq.gz", "rb") as handle:
                self.assertEqual(handle.read(), b"")

    def test_changed_input_during_triage_leaves_no_final_residual(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "reads.fastq"
            source.write_text("@read\nACGT\n+\nIIII\n", encoding="ascii")
            sam = root / "screen.sam"
            sam.write_text("@HD\tVN:1.6\n", encoding="ascii")

            def mutate_after_first_pass(path, *, paired, expected, references=None):
                source.write_text("@read\nTGCA\n+\nIIII\n", encoding="ascii")
                return {key: 4 for key in expected}

            with patch.object(residual_reads, "_sam", side_effect=mutate_after_first_pass):
                with self.assertRaisesRegex(ValueError, "changed during residual triage"):
                    screen_and_triage(
                        source, None, sam, root / "out",
                        config={"min_read_length": 1, "max_ambiguous_fraction": 1,
                                "min_entropy_bits": 0, "min_mean_phred": 0},
                        paired=False,
                    )
            self.assertFalse((root / "out" / "residual_read1.fastq.gz").exists())
            self.assertFalse((root / "out" / "read_triage.csv").exists())

    def test_normalization_enforces_total_base_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "reads.fastq"
            source.write_text("@read\nACGTACGT\n+\nIIIIIIII\n", encoding="ascii")
            with patch.object(residual_reads, "MAX_TOTAL_BASES", 4):
                with self.assertRaisesRegex(ValueError, "resource limits"):
                    prepare_normalized_fastqs(source, None, root / "out")


if __name__ == "__main__":
    unittest.main()