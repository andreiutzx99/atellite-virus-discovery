import hashlib
import unittest

from satellite_discovery.m10_algorithms import M10Limits, analyze_sequence


class M10AlgorithmTests(unittest.TestCase):
    def run_seq(self, seq, molecule="DNA", **kwargs):
        return analyze_sequence(
            seq, candidate_id="c1", sequence_id="s1", molecule_type=molecule,
            terminal_boundaries_resolved=True, limits=M10Limits(**kwargs))

    def test_digests_and_nested_terminal(self):
        result = self.run_seq("aaaa")
        self.assertEqual(result["source_sha256"], hashlib.sha256(b"aaaa").hexdigest())
        self.assertEqual([x["span"] for x in result["branches"][
            "M10_TERMINAL_DIRECT_V1"]["evidence"]], [1, 2, 3])

    def test_dna_rna_ambiguity_and_mixed(self):
        self.assertTrue(self.run_seq("AT", "DNA")["branches"][
            "M10_TERMINAL_INVERTED_V1"]["evidence"])
        self.assertTrue(self.run_seq("AU", "RNA")["branches"][
            "M10_TERMINAL_INVERTED_V1"]["evidence"])
        self.assertEqual(self.run_seq("ACGA", "DNA")["branches"][
            "M10_TERMINAL_INVERTED_V1"]["branch_status"],
            "COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY")
        mixed = self.run_seq("ATU", "DNA")
        self.assertEqual(mixed["branches"]["M10_TERMINAL_INVERTED_V1"][
            "branch_status"], "INSUFFICIENT_INFORMATION")
        self.assertFalse(self.run_seq("NN", "DNA")["branches"][
            "M10_TERMINAL_DIRECT_V1"]["evidence"])

    def test_inverted_internal_coordinates(self):
        # The internal arms at [1,2) and [4,5) are reverse complements.
        result = self.run_seq("AAAATA")
        rows = result["branches"]["M10_INTERNAL_INVERTED_V1"]["evidence"]
        self.assertTrue(any(r["source_intervals"] == [[1, 2], [4, 5]]
                            for r in rows))
        self.assertEqual(result["reverse_complement_view"]["alphabet_id"], "DNA")

    def test_output_cap_exact_and_over(self):
        exact = self.run_seq("AAAA", max_evidence_rows_per_branch=3)
        self.assertEqual(exact["branches"]["M10_TERMINAL_DIRECT_V1"][
            "branch_status"], "COMPLETED_MATCHES_REPORTED")
        over = self.run_seq("AAAA", max_evidence_rows_per_branch=2)
        branch = over["branches"]["M10_TERMINAL_DIRECT_V1"]
        self.assertEqual(branch["branch_status"], "TRUNCATED")
        self.assertEqual(len(branch["evidence"]), 2)

    def test_comparison_cap(self):
        result = self.run_seq("AAAA", max_symbol_comparisons_per_branch=2)
        self.assertEqual(result["branches"]["M10_TERMINAL_DIRECT_V1"][
            "branch_status"], "TRUNCATED")
        self.assertFalse(result["branches"]["M10_TERMINAL_DIRECT_V1"][
            "full_accounting_proven"])
        self.assertEqual(
            [row["span"] for row in result["branches"][
                "M10_TERMINAL_DIRECT_V1"]["evidence"]],
            [1],
        )
        internal = self.run_seq(
            "AAAAAA", max_symbol_comparisons_per_branch=1)
        self.assertEqual(internal["branches"]["M10_INTERNAL_DIRECT_V1"][
            "branch_status"], "TRUNCATED")
        self.assertEqual(internal["branches"]["M10_INTERNAL_DIRECT_V1"][
            "evidence"], [])

    def test_boundary_and_ambiguity_accounting(self):
        boundary = analyze_sequence(
            "ACG", candidate_id="c1", sequence_id="s1",
            molecule_type="DNA", terminal_boundaries_resolved=False,
            limits=M10Limits())
        direct = boundary["branches"]["M10_TERMINAL_DIRECT_V1"]
        self.assertEqual(direct["branch_status"], "BOUNDARY_LIMITATION")
        self.assertFalse(direct["full_accounting_proven"])
        self.assertEqual(boundary["aggregate_status"], "PARTIAL")

        compatible = self.run_seq("RA")
        branch = compatible["branches"]["M10_TERMINAL_DIRECT_V1"]
        self.assertEqual(branch["ambiguity_compatible_comparisons"], 1)
        self.assertEqual(branch["evidence"], [])
        incompatible = self.run_seq("RY")
        self.assertEqual(incompatible["branches"]["M10_TERMINAL_DIRECT_V1"][
            "ambiguity_incompatible_comparisons"], 1)

    def test_stable_evidence_identity_binds_source_digest(self):
        first = self.run_seq("AACAA")
        second = self.run_seq("ATCAA")
        first_ids = {
            row["evidence_id"] for row in first["branches"][
                "M10_TERMINAL_DIRECT_V1"]["evidence"]
        }
        second_ids = {
            row["evidence_id"] for row in second["branches"][
                "M10_TERMINAL_DIRECT_V1"]["evidence"]
        }
        self.assertTrue(first_ids)
        self.assertTrue(second_ids)
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_short_empty_invalid_and_policy_provenance(self):
        one = self.run_seq("A")
        self.assertEqual(one["aggregate_status"], "COMPLETE")
        self.assertEqual(one["branches"]["M10_INTERNAL_DIRECT_V1"][
            "branch_status"], "COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY")
        empty = self.run_seq("")
        self.assertEqual(empty["input_status"], "INPUT_INVALID")
        invalid = self.run_seq("AC-")
        self.assertEqual(invalid["input_status"], "INPUT_INVALID")
        self.assertEqual(invalid["branches"]["M10_TERMINAL_DIRECT_V1"][
            "full_accounting_proven"], False)
        self.assertEqual(one["branches"]["M10_TERMINAL_DIRECT_V1"][
            "effective_limits"]["max_candidate_symbols"], 1_000_000)


if __name__ == "__main__":
    unittest.main()