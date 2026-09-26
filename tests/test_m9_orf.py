import hashlib
import unittest

from satellite_discovery.m9_orf import enumerate_orfs


def digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class M9OrfTests(unittest.TestCase):
    def run_orfs(self, sequence, molecule_type=None):
        return enumerate_orfs(
            sequence,
            candidate_id="candidate-1",
            sequence_id="sequence-1",
            sequence_sha256=digest(sequence),
            molecule_type=molecule_type,
        )

    def test_complete_short_and_stop_coordinates(self):
        result = self.run_orfs("ATGTTTTAA")
        rows = [row for row in result["orfs"]
                if row["strand"] == "+" and row["frame"] == 0]
        complete = next(row for row in rows if not row["partial"])
        self.assertEqual(complete["protein_sequence"], "MF")
        self.assertEqual(complete["protein_length"], 2)
        self.assertEqual(complete["coordinates"], [0, 9])
        self.assertEqual(complete["stop_codon"], "TAA")
        self.assertEqual(complete["stop_coordinates"], [6, 9])
        self.assertEqual(result["status"], "ORF_PREDICTED")

    def test_nested_and_overlapping_starts_are_retained(self):
        result = self.run_orfs("ATGAAAATGCCCTAA")
        rows = [row for row in result["orfs"]
                if row["strand"] == "+" and row["frame"] == 0
                and not row["partial"]]
        self.assertEqual([row["protein_sequence"] for row in rows], ["MKMP", "MP"])
        self.assertEqual([row["coordinates"] for row in rows], [[0, 15], [6, 15]])

    def test_start_after_earlier_stop_gets_later_downstream_stop(self):
        result = self.run_orfs("TAAATGAAATAA")
        rows = [row for row in result["orfs"]
                if row["strand"] == "+" and row["frame"] == 0]
        complete = next(row for row in rows if not row["partial"])
        self.assertEqual(complete["protein_sequence"], "MK")
        self.assertEqual(complete["start_codon"], "ATG")
        self.assertEqual(complete["stop_codon"], "TAA")
        self.assertEqual(complete["coordinates"], [3, 12])

    def test_reverse_and_offset_frames(self):
        reverse = self.run_orfs("TTATTTCAT")
        row = next(row for row in reverse["orfs"] if row["strand"] == "-"
                   and row["frame"] == 0 and not row["partial"])
        self.assertEqual(row["protein_sequence"], "MK")
        self.assertEqual(row["coordinates"], [0, 9])
        for sequence, frame in (("AATGAAATAA", 1), ("AAATGAAATAA", 2)):
            result = self.run_orfs(sequence)
            self.assertTrue(any(row["strand"] == "+" and row["frame"] == frame
                                and row["protein_sequence"] == "MK"
                                for row in result["orfs"]))

    def test_boundary_partials_are_distinct(self):
        five = self.run_orfs("CCCAAATAA")
        five_row = next(row for row in five["orfs"]
                        if row["strand"] == "+" and row["frame"] == 0
                        and row["partial_5_prime"])
        self.assertEqual(five_row["protein_sequence"], "PK")
        self.assertIsNone(five_row["start_codon"])
        three = self.run_orfs("ATGAAAC")
        three_row = next(row for row in three["orfs"]
                         if row["strand"] == "+" and row["frame"] == 0
                         and row["partial_3_prime"])
        self.assertEqual(three_row["protein_sequence"], "MK")
        self.assertIsNone(three_row["stop_codon"])

    def test_ambiguous_codons_are_x_and_not_starts_or_stops(self):
        result = self.run_orfs("ATGNNNTAA")
        row = next(row for row in result["orfs"]
                   if row["strand"] == "+" and row["frame"] == 0
                   and not row["partial"])
        self.assertEqual(row["protein_sequence"], "MX")
        self.assertEqual(row["ambiguous_source_codons"][0]["codon"], "NNN")
        self.assertEqual(row["ambiguous_codon_positions"], [3])
        self.assertFalse(any(row["protein_sequence"] == ""
                             for row in result["orfs"]))

    def test_no_orf_and_all_metadata_are_explicit(self):
        sequence = "CCCCCCCC"
        result = self.run_orfs(sequence)
        self.assertEqual(result["status"], "NO_ORF_PREDICTED_WITHIN_POLICY")
        self.assertEqual(result["orfs"], [])
        self.assertEqual(result["expected_orf_count"], 0)
        self.assertEqual(result["observed_orf_count"], 0)
        self.assertEqual(result["sequence"], sequence)
        self.assertEqual(result["sequence_sha256"], digest(sequence))
        self.assertEqual(result["translation_table"], 1)
        self.assertEqual(result["policy"]["translation_table"], 1)

    def test_rna_translation_view_preserves_original_and_hashes(self):
        sequence = "AUGAAAUAA"
        result = self.run_orfs(sequence, molecule_type="RNA")
        self.assertEqual(result["sequence"], sequence)
        self.assertEqual(result["sequence_sha256"], digest(sequence))
        self.assertEqual(result["translation_view"]["sequence"], "ATGAAATAA")
        self.assertEqual(result["translation_view"]["sha256"], digest("ATGAAATAA"))
        self.assertEqual(result["translation_view"]["source_alphabet"], "RNA")
        self.assertEqual(result["orfs"][0]["protein_sequence"], "MK")
        row = next(row for row in result["orfs"]
                   if row["strand"] == "+" and row["frame"] == 0
                   and not row["partial"])
        self.assertEqual(row["start_codon"], "AUG")
        self.assertEqual(row["start_translation_codon"], "ATG")
        self.assertEqual(row["source_codons"][0]["codon"], "AUG")
        self.assertEqual(row["source_codons"][0]["source_codon"], "AUG")
        self.assertEqual(row["source_codons"][0]["translation_codon"], "ATG")
        self.assertTrue(result["translation_view"]["u_to_t_applied"])
        self.assertTrue(result["translation_view"]["normalization_applied"])

    def test_molecule_type_must_be_text_or_null(self):
        with self.assertRaises(ValueError):
            self.run_orfs("ATG", molecule_type=1)

    def test_ids_and_order_are_deterministic(self):
        first = self.run_orfs("ATGAAAATGCCCTAA")
        second = self.run_orfs("ATGAAAATGCCCTAA")
        self.assertEqual(first, second)
        self.assertEqual(
            [row["orf_id"] for row in first["orfs"]],
            [row["orf_id"] for row in second["orfs"]],
        )
        self.assertEqual(len(first["orfs"]), len(set(row["orf_id"] for row in first["orfs"])))

    def test_hash_mismatch_and_invalid_sequence_rejected(self):
        with self.assertRaises(ValueError):
            enumerate_orfs("ATG", candidate_id="c", sequence_id="s",
                           sequence_sha256="0" * 64)
        with self.assertRaises(ValueError):
            enumerate_orfs("ATG!", candidate_id="c", sequence_id="s",
                           sequence_sha256=digest("ATG!"))


if __name__ == "__main__":
    unittest.main()