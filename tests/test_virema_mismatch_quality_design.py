"""Offline invariants for controlled ViReMa mismatch/quality comparisons."""
import unittest

from scripts.virema_mismatch_quality import (
    GENOMES, _condition_rows, _read,
)


class ViReMaMismatchQualityDesignTests(unittest.TestCase):
    def test_bounded_design_covers_quality_substitution_and_settings(self):
        rows = _condition_rows()
        self.assertEqual(len(rows), 39)
        self.assertEqual({row[1] for row in rows}, set(GENOMES))
        self.assertEqual({row[5] for row in rows}, {0, 1, 2, 3})
        self.assertEqual(
            sum(row[6] == 'quality_only' for row in rows), 9
        )
        self.assertEqual(sum(row[6] == 'substitution_only' for row in rows), 6)
        self.assertEqual(sum(row[6] == 'combined' for row in rows), 6)
        self.assertEqual(sum(row[6] == 'mismatch_sweep' for row in rows), 6)
        self.assertEqual(sum(row[6] == 'negative_control' for row in rows), 4)
        self.assertEqual(sum(row[6] == 'pr72_anchor' for row in rows), 8)

    def test_controlled_pairs_hold_sequence_and_truth_constant(self):
        rows = {row[0]: row for row in _condition_rows()}
        for seed in GENOMES:
            exact_names = [f's{seed}_exact_q{score}' for score in (0, 20, 40)]
            exact_sequences = {rows[name][3] for name in exact_names}
            self.assertEqual(len(exact_sequences), 1)
            for rate in (2, 5):
                q40 = rows[f's{seed}_{rate}pct_q40']
                q0 = rows[f's{seed}_{rate}pct_q0mut']
                self.assertEqual(q40[3], q0[3])
                self.assertEqual(q40[4].count('I'), len(q40[3]))
                self.assertEqual(q0[4].count('!'), rate)
                self.assertEqual(q40[2], rate)
                self.assertEqual(q0[2], rate)
        for mismatches in (0, 1, 2, 3):
            q40 = rows[f'pr72_anchor_q40_n{mismatches}']
            q0 = rows[f'pr72_anchor_q0mut_n{mismatches}']
            self.assertEqual(q40[1:4], q0[1:4])
            self.assertEqual(q40[5], q0[5])

    def test_deterministic_mutations_use_same_genome_and_breakpoint(self):
        for seed in GENOMES:
            genome_a, exact_a, altered_a, positions_a = _read(seed, 5)
            genome_b, exact_b, altered_b, positions_b = _read(seed, 5)
            self.assertEqual(genome_a, genome_b)
            self.assertEqual(exact_a, exact_b)
            self.assertEqual(altered_a, altered_b)
            self.assertEqual(positions_a, positions_b)
            self.assertEqual(len(positions_a), 5)
            self.assertNotEqual(exact_a, altered_a)


if __name__ == '__main__':
    unittest.main()
