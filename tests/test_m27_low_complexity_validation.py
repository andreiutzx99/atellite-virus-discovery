import unittest

from satellite_discovery.m27_low_complexity_validation import complexity_metrics


class M27ComplexityMetricTests(unittest.TestCase):
    def test_metrics_distinguish_periodic_from_mixed_sequence(self):
        periodic = complexity_metrics("ACGT" * 25)
        mixed = complexity_metrics("ACGTTGCAAGTC" * 8)
        self.assertEqual(periodic["length"], 100)
        self.assertAlmostEqual(periodic["shannon_entropy_bits"], 2.0)
        self.assertAlmostEqual(periodic["best_periodicity"], 1.0)
        self.assertGreater(mixed["unique_kmer_fraction"], periodic["unique_kmer_fraction"])

    def test_homopolymer_and_kmer_metrics_are_reported(self):
        metrics = complexity_metrics("A" * 20 + "CGTACGTACGTACGTACGT")
        self.assertEqual(metrics["max_homopolymer"], 20)
        self.assertEqual(metrics["k"], 5)
        self.assertLess(metrics["unique_kmer_fraction"], 1.0)

    def test_metrics_reject_empty_or_unsupported_sequence(self):
        for sequence in ("", "ACGTX"):
            with self.subTest(sequence=sequence):
                with self.assertRaises(ValueError):
                    complexity_metrics(sequence)


if __name__ == "__main__":
    unittest.main()
