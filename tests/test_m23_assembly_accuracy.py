import unittest

from satellite_discovery import m23_assembly_accuracy as m23


class M23AssemblyAccuracyTests(unittest.TestCase):
    def test_exact_substitution_indel_and_terminal_diagnostics(self):
        exact = m23.diagnose_sequence("AACCGGTT", "AACCGGTT")
        self.assertEqual(1.0, exact["full_length_sequence_identity"])
        self.assertEqual(1.0, exact["target_coverage"])
        self.assertEqual(0, exact["substitution_count"])
        reverse = m23.diagnose_sequence("AACCGGTA", "TACCGGTT")
        self.assertTrue(reverse["strand_exact_match"])
        self.assertEqual("reverse_complement", reverse["alignment_orientation"])

        changed = m23.diagnose_sequence("AACCGGTT", "AATCGGTT")
        self.assertEqual(1, changed["substitution_count"])

        deleted = m23.diagnose_sequence("AACCGGTT", "AACGGTT")
        self.assertEqual(1, deleted["deletion_count"])
        self.assertEqual(0, deleted["missing_target_suffix_bases"])

        truncated = m23.diagnose_sequence("AACCGGTT", "AACCGGT")
        self.assertEqual(1, truncated["missing_target_suffix_bases"])

        inserted = m23.diagnose_sequence("AACCGGTT", "AACCTGGTT")
        self.assertEqual(1, inserted["insertion_count"])

        extended = m23.diagnose_sequence("AACCGGTT", "TAACCGGTTG")
        self.assertEqual(1, extended["incorrect_candidate_prefix_bases"])
        self.assertEqual(1, extended["incorrect_candidate_suffix_bases"])

    def test_potential_join_is_flagged_only_as_a_hypothesis(self):
        left = "ACGTTGCA" * 5
        right = "GATCCGTA" * 5
        result = m23.diagnose_sequence(
            "T" * 80,
            left + right,
            [("synthetic-left", left), ("synthetic-right", right)],
        )
        self.assertTrue(result["potential_incorrect_joins"])
        self.assertEqual(
            {"POTENTIAL_ONLY"},
            {row["status"] for row in result["potential_incorrect_joins"]},
        )

    def test_independent_kmer_evidence_and_terminal_trim_are_deterministic(self):
        candidate = "ACGT" * 40
        reads = [candidate[8:108], candidate[28:128]]
        first = m23._independent_evidence(candidate, reads)
        second = m23._independent_evidence(candidate, reads)
        self.assertEqual(first["candidate_coverage_breadth"],
                         second["candidate_coverage_breadth"])
        self.assertEqual(first["supported_read_count"], 2)
        trimmed, prefix, suffix = m23._trim_unsupported_ends(
            "TT" + candidate + "GG",
            bytearray([0, 0] + [1] * len(candidate) + [0, 0]),
        )
        self.assertEqual(candidate, trimmed)
        self.assertEqual((2, 2), (prefix, suffix))


if __name__ == "__main__":
    unittest.main()
