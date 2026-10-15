"""Offline checks for deterministic artificial junction and control fixtures."""
from pathlib import Path
import tempfile
import unittest

from scripts.check_virema_ci import write_synthetic_inputs


class SyntheticJunctionFixtureTests(unittest.TestCase):
    def test_generated_cases_are_reproducible_and_use_one_intact_reference(self):
        with tempfile.TemporaryDirectory() as first_dir, \
                tempfile.TemporaryDirectory() as second_dir:
            first_reference, first_positive, first_negative = write_synthetic_inputs(
                Path(first_dir)
            )
            second_reference, second_positive, second_negative = write_synthetic_inputs(
                Path(second_dir)
            )
            self.assertEqual(first_reference.read_bytes(), second_reference.read_bytes())
            self.assertEqual(first_reference.read_text().count('>'), 1)
            self.assertNotIn('transcript', first_reference.read_text().lower())
            self.assertEqual(
                [case['reads_path'].read_bytes() for case in first_positive],
                [case['reads_path'].read_bytes() for case in second_positive],
            )
            self.assertEqual(
                first_negative['reads_path'].read_bytes(),
                second_negative['reads_path'].read_bytes(),
            )

    def test_positive_truth_is_separate_from_blind_fastq_and_varies_support(self):
        with tempfile.TemporaryDirectory() as folder:
            reference, positives, _negative = write_synthetic_inputs(Path(folder))
            self.assertEqual(len(positives), 5)
            self.assertEqual(
                [case['label'] for case in positives],
                [
                    'leader_body_like',
                    'internal_deletion_like',
                    'alternative_order_rearrangement_like',
                    'leader_body_like_quality_20',
                    'leader_body_like_quality_0',
                ],
            )
            self.assertEqual([case['read_length'] for case in positives], [80, 120, 80, 80, 80])
            self.assertEqual([case['support'] for case in positives], [8, 4, 2, 8, 8])
            self.assertEqual([case['quality_phred'] for case in positives], [40, 40, 40, 20, 0])
            self.assertEqual(
                [case['breakpoints'] for case in positives],
                [
                    (139, 500), (259, 750), (939, 300),
                    (139, 500), (139, 500),
                ],
            )
            self.assertEqual(reference.read_text().count('>'), 1)
            for case in positives:
                fastq = case['reads_path'].read_text(encoding='ascii')
                self.assertEqual(fastq.count('\n+\n'), case['support'])
                self.assertNotIn(str(case['breakpoints'][0]), fastq)
                self.assertNotIn(str(case['breakpoints'][1]), fastq)
                self.assertNotIn(case['label'], fastq)
                self.assertNotIn('junction_transcript', fastq.lower())
                self.assertEqual(set(fastq.splitlines()[3::4]), {
                    case['quality_char'] * case['read_length']
                })

    def test_negative_fixture_covers_continuous_and_technical_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            _reference, _positive, negative = write_synthetic_inputs(Path(folder))
            self.assertEqual(negative['read_count'], 56)
            self.assertEqual(sum(negative['control_read_counts'].values()), 56)
            self.assertEqual(set(negative['control_read_counts']), {
                'continuous_genomic',
                'single_substitution',
                'repetitive_ambiguous',
                'low_complexity',
                'adapter_like',
                'short_continuous_alignment',
                'low_quality_continuous',
            })
            lines = negative['reads_path'].read_text(encoding='ascii').splitlines()
            self.assertEqual(len(lines), negative['read_count'] * 4)
            self.assertTrue(any('!' in quality for quality in lines[3::4]))
            self.assertTrue(all(name.startswith('@synthetic_read_') for name in lines[::4]))


if __name__ == '__main__':
    unittest.main()
