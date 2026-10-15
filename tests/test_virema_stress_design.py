"""Deterministic design checks for the optional ViReMa stress benchmark."""
from pathlib import Path
import tempfile
import unittest

from scripts.virema_stress import GENOME_SEEDS, build_stress_cases


class ViReMaStressDesignTests(unittest.TestCase):
    def test_benchmark_is_bounded_and_spans_the_requested_factors(self):
        with tempfile.TemporaryDirectory() as folder:
            positive, negative = build_stress_cases(Path(folder))
        self.assertEqual(len(positive), 13)
        self.assertEqual(len(negative), 7)
        self.assertEqual({case['seed'] for case in positive}, set(GENOME_SEEDS))
        self.assertEqual(
            {case['read_length'] for case in positive}, {50, 75, 100, 150}
        )
        self.assertEqual({case['support'] for case in positive}, {1, 2, 5, 10, 20})
        self.assertEqual(
            {case['error_rate_percent'] for case in positive}, {0, 1, 2, 5}
        )
        self.assertEqual(
            {case['pattern'] for case in positive},
            {'leader_body_like', 'internal_deletion_like', 'reverse_order_like'},
        )

    def test_truth_is_outside_caller_inputs_and_cases_have_distinct_references(self):
        with tempfile.TemporaryDirectory() as root_a, \
                tempfile.TemporaryDirectory() as root_b:
            positives_a, negatives_a = build_stress_cases(Path(root_a))
            positives_b, negatives_b = build_stress_cases(Path(root_b))
            all_a = positives_a + negatives_a
            all_b = positives_b + negatives_b
            self.assertEqual(
                [case['label'] for case in all_a],
                [case['label'] for case in all_b],
            )
            self.assertEqual(
                [case['reads_path'].read_bytes() for case in all_a],
                [case['reads_path'].read_bytes() for case in all_b],
            )
            for case in all_a:
                reference = case['reference_path'].read_text(encoding='ascii')
                fastq = case['reads_path'].read_text(encoding='ascii')
                self.assertEqual(reference.count('>'), 1)
                self.assertNotIn('junction', reference.lower())
                self.assertNotIn(case['label'], fastq)
                self.assertNotIn('SYNTHETIC_GENOME_SEED', fastq)
                self.assertNotIn('SYNTHETIC_NEGATIVE_SEED', fastq)
                if case['expected_breakpoints']:
                    for breakpoint in case['expected_breakpoints']:
                        self.assertNotIn(str(breakpoint), fastq)

    def test_negative_controls_are_independent_and_include_technical_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            _positive, negative = build_stress_cases(Path(folder))
        self.assertEqual(len({case['reads_path'] for case in negative}), 7)
        self.assertEqual(len({case['reference_path'] for case in negative}), 7)
        self.assertTrue(all(case['support'] == 20 for case in negative))
        self.assertTrue(all(case['expected_breakpoints'] is None for case in negative))
        self.assertEqual(
            {case['label'] for case in negative},
            {
                'negative_continuous',
                'negative_substitution',
                'negative_repetitive_ambiguous',
                'negative_low_complexity',
                'negative_adapter_chimera',
                'negative_low_quality',
                'negative_short_continuous',
            },
        )


if __name__ == '__main__':
    unittest.main()
