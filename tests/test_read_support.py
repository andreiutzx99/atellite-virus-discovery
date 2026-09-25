import hashlib
import tempfile
import unittest
from pathlib import Path

from satellite_discovery.read_support import assess_read_support


class ReadSupportTests(unittest.TestCase):
    def test_soft_clip_does_not_inflate_fraction_and_bounds_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "c.fasta").write_text(">c\nACGTACGT\n", encoding="ascii")
            sequence = "TTACGTACGT"
            metadata = {("m6r000000000001", 0): {
                "query_length": 10,
                "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
            }}
            sam = root / "soft.sam"
            sam.write_text(
                "@SQ\tSN:c\tLN:8\n"
                f"m6r000000000001\t0\tc\t1\t60\t2S8M\t*\t0\t0\t{sequence}\tIIIIIIIIII\tNM:i:0\n",
                encoding="ascii",
            )
            result = assess_read_support(sam, root / "c.fasta", metadata, paired=False,
                                         thresholds={"min_alignment_fraction": .9})
            self.assertFalse(result["read_support"][0]["qualifying"])
            sam.write_text(f"m6r000000000001\t0\tc\t3\t60\t10M\t*\t0\t0\t{sequence}\tIIIIIIIIII\tNM:i:0\n", encoding="ascii")
            with self.assertRaises(ValueError):
                assess_read_support(sam, root / "c.fasta", metadata, paired=False, thresholds={})

    def test_indel_nm_can_exceed_aligned_query_bases(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "c.fasta").write_text(">c\nACGTACGT\n", encoding="ascii")
            sam = root / "indel.sam"
            sequence = "ACGTAACGT"
            sam.write_text(
                "@SQ\tSN:c\tLN:8\n"
                f"m6r000000000001\t0\tc\t1\t60\t4M1I4M\t*\t0\t0\t{sequence}\tIIIIIIIII\tNM:i:1\n",
                encoding="ascii",
            )
            result = assess_read_support(
                sam, root / "c.fasta",
                {("m6r000000000001", 0): {
                    "query_length": 9,
                    "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                }},
                paired=False, thresholds={"min_sequence_identity": .8})
            self.assertEqual(result["contigs"][0]["contig_id"], "c")

    def test_supported_contig_requires_distinct_sequences(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            contigs = root / "contigs.fasta"
            contigs.write_text(">c1\nACGTACGT\n", encoding="ascii")
            sam = root / "support.sam"
            sam.write_text(
                "@SQ\tSN:c1\tLN:8\n"
                "m6r000000000001\t0\tc1\t1\t60\t8M\t*\t0\t0\tACGTACGT\tIIIIIIII\tNM:i:0\n"
                "m6r000000000002\t0\tc1\t1\t60\t8M\t*\t0\t0\tACGTACGA\tIIIIIIII\tNM:i:1\n",
                encoding="ascii",
            )
            sequences = ("ACGTACGT", "ACGTACGA")
            metadata = {
                ("m6r000000000001", 0): {
                    "query_length": 8, "sequence_sha256": hashlib.sha256(sequences[0].encode()).hexdigest(),
                },
                ("m6r000000000002", 0): {
                    "query_length": 8, "sequence_sha256": hashlib.sha256(sequences[1].encode()).hexdigest(),
                },
            }
            result = assess_read_support(
                sam, contigs, metadata, paired=False,
                thresholds={"min_mapq": 20, "min_alignment_fraction": .8,
                            "min_sequence_identity": .8, "min_coverage_breadth": .8,
                            "min_mean_depth": 2},
            )
            self.assertEqual(result["contigs"][0]["status"], "READ_SUPPORTED_ASSEMBLY")
            self.assertEqual(result["resolved_fragment_ids"],
                             ["m6r000000000001", "m6r000000000002"])

    def test_unrelated_read_does_not_support_a_contig(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            contigs = root / "contigs.fasta"
            contigs.write_text(">c1\nACGTACGT\n", encoding="ascii")
            sequence = "TTTTTTTT"
            sam = root / "unrelated.sam"
            sam.write_text(
                "@SQ\tSN:c1\tLN:8\n"
                "m6r000000000001\t4\t*\t0\t0\t*\t*\t0\t0\t"
                f"{sequence}\tIIIIIIII\n",
                encoding="ascii",
            )
            metadata = {("m6r000000000001", 0): {
                "query_length": len(sequence),
                "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
            }}

            result = assess_read_support(
                sam, contigs, metadata, paired=False, thresholds={},
            )

            self.assertEqual(result["status"], "NO_SUPPORTED_ASSEMBLY")
            self.assertEqual(result["contigs"][0]["status"], "UNSUPPORTED_ASSEMBLY")
            self.assertEqual(result["resolved_fragment_ids"], [])

    def test_insufficient_support_is_low_support_not_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            contigs = root / "contigs.fasta"
            sequence = "ACGTACGT"
            contigs.write_text(f">c1\n{sequence}\n", encoding="ascii")
            sam = root / "weak.sam"
            sam.write_text(
                "@SQ\tSN:c1\tLN:8\n"
                f"m6r000000000001\t0\tc1\t1\t60\t8M\t*\t0\t0\t"
                f"{sequence}\tIIIIIIII\tNM:i:0\n",
                encoding="ascii",
            )
            metadata = {("m6r000000000001", 0): {
                "query_length": len(sequence),
                "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
            }}

            result = assess_read_support(
                sam, contigs, metadata, paired=False,
                thresholds={
                    "min_mapq": 20, "min_alignment_fraction": .8,
                    "min_sequence_identity": .95, "min_coverage_breadth": .8,
                    "min_mean_depth": 2, "min_distinct_fragments": 2,
                },
            )

            self.assertEqual(result["status"], "NO_SUPPORTED_ASSEMBLY")
            self.assertEqual(result["contigs"][0]["status"], "LOW_SUPPORT_ASSEMBLY")

    def test_sequence_and_nm_must_match_reference_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "c.fasta").write_text(">c\nACGTACGT\n", encoding="ascii")
            sequence = "ACGTACGT"
            metadata = {("m6r000000000001", 0): {
                "query_length": 8,
                "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
            }}
            sam = root / "corrupt.sam"
            sam.write_text(
                "@SQ\tSN:c\tLN:8\n"
                "m6r000000000001\t0\tc\t1\t60\t8M\t*\t0\t0\tACGTTCGT\tIIIIIIII\tNM:i:0\n",
                encoding="ascii",
            )
            with self.assertRaisesRegex(ValueError, "does not match the original residual read"):
                assess_read_support(sam, root / "c.fasta", metadata, paired=False, thresholds={})

    def test_paired_fragments_spanning_contigs_are_ambiguous(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            contigs = root / "contigs.fasta"
            contigs.write_text(
                ">c1\nACGTACGT\n>c2\nTTGCAATT\n", encoding="ascii",
            )
            records = [
                ("m6r000000000001", 1, 65, "c1", "ACGTACGT", 0),
                ("m6r000000000001", 2, 129, "c2", "TTGCAATT", 0),
                ("m6r000000000002", 1, 65, "c1", "ACGTACGA", 1),
                ("m6r000000000002", 2, 129, "c2", "TTGCAATA", 1),
            ]
            sam = root / "split-pairs.sam"
            sam.write_text(
                "@SQ\tSN:c1\tLN:8\n@SQ\tSN:c2\tLN:8\n"
                + "".join(
                    f"{query_id}\t{flag}\t{contig}\t1\t60\t8M\t*\t0\t0\t"
                    f"{sequence}\tIIIIIIII\tNM:i:{nm}\n"
                    for query_id, _mate, flag, contig, sequence, nm in records
                ),
                encoding="ascii",
            )
            metadata = {
                (query_id, mate): {
                    "query_length": len(sequence),
                    "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                }
                for query_id, mate, _flag, _contig, sequence, _nm in records
            }

            result = assess_read_support(
                sam, contigs, metadata, paired=True,
                thresholds={
                    "min_mapq": 20, "min_alignment_fraction": .8,
                    "min_sequence_identity": .8, "min_coverage_breadth": .8,
                    "min_mean_depth": 2, "min_distinct_fragments": 2,
                },
            )

            self.assertEqual(result["status"], "NO_SUPPORTED_ASSEMBLY")
            self.assertEqual(
                [row["status"] for row in result["contigs"]],
                ["AMBIGUOUS_ASSEMBLY", "AMBIGUOUS_ASSEMBLY"],
            )
            self.assertEqual(result["resolved_fragment_ids"], [])

    def test_paired_support_requires_both_mates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "c.fasta").write_text(">c\nACGTACGT\n", encoding="ascii")
            sam = root / "paired.sam"
            sam.write_text("@SQ\tSN:c\tLN:8\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "both mates"):
                assess_read_support(
                    sam, root / "c.fasta",
                    {("m6r000000000001", 1): {
                        "query_length": 8,
                        "sequence_sha256": hashlib.sha256(b"ACGTACGT").hexdigest(),
                    }},
                    paired=True, thresholds={},
                )

    def test_unknown_query_and_malformed_cigar_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "c.fasta").write_text(">c\nACGT\n", encoding="ascii")
            (root / "bad.sam").write_text(
                "@SQ\tSN:c\tLN:4\n"
                "unknown\t0\tc\t1\t60\tbad\t*\t0\t0\tACGT\tIIII\tNM:i:0\n",
                encoding="ascii")
            with self.assertRaises(ValueError):
                assess_read_support(root / "bad.sam", root / "c.fasta",
                                     {("m6r000000000001", 0): {"query_length": 4,
                                      "sequence_sha256": "x"}},
                                     paired=False, thresholds={})

    def test_contig_dictionary_must_match_assembly_fasta(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            contigs = root / "contigs.fasta"
            contigs.write_text(">c\nACGT\n", encoding="ascii")
            sam = root / "wrong-contig.sam"
            sam.write_text(
                "@SQ\tSN:other\tLN:4\n"
                "m6r000000000001\t4\t*\t0\t0\t*\t*\t0\t0\tACGT\tIIII\n",
                encoding="ascii",
            )
            sequence = "ACGT"
            with self.assertRaisesRegex(ValueError, "dictionary does not match"):
                assess_read_support(
                    sam, contigs,
                    {("m6r000000000001", 0): {
                        "query_length": 4,
                        "sequence_sha256": hashlib.sha256(sequence.encode()).hexdigest(),
                    }},
                    paired=False, thresholds={},
                )

    def test_coverage_windows_are_clipped_in_local_coordinates(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            contig = ("ACGT" * 62) + "AC"
            read = contig[:200]
            contigs = root / "contigs.fasta"
            contigs.write_text(f">c\n{contig}\n", encoding="ascii")
            sam = root / "windows.sam"
            sam.write_text(
                f"@SQ\tSN:c\tLN:{len(contig)}\n"
                f"m6r000000000001\t0\tc\t1\t60\t200M\t*\t0\t0\t{read}\t"
                f"{'I' * len(read)}\tNM:i:0\n",
                encoding="ascii",
            )
            result = assess_read_support(
                sam, contigs,
                {("m6r000000000001", 0): {
                    "query_length": len(read),
                    "sequence_sha256": hashlib.sha256(read.encode()).hexdigest(),
                }},
                paired=False, thresholds={
                    "min_alignment_fraction": .8, "min_sequence_identity": .9,
                    "coverage_window_size": 100,
                },
            )
            windows = result["contigs"][0]["coverage_windows"]
            self.assertEqual([(window["start"], window["end"]) for window in windows],
                             [(1, 100), (101, 200), (201, 250)])
            self.assertEqual(windows[0]["breadth"], 1)
            self.assertEqual(windows[1]["breadth"], 1)
            self.assertEqual(windows[2]["breadth"], 0)


if __name__ == "__main__":
    unittest.main()