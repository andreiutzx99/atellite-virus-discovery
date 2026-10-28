import unittest

from satellite_discovery.m24_terminal_recovery import _extensions


class M24TerminalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.candidate = "ACGTTGCAAGTCGATCGGATCCTAGGCTAACCGTTAAGCTTGAC"

    def test_requires_two_reads_and_unique_exact_context(self):
        left = "TTGCA" + self.candidate[:35]
        accepted, _ = _extensions(
            self.candidate, [("read-1", left), ("read-2", left)])
        self.assertEqual({"left": "TTGCA"}, accepted)

        single, _ = _extensions(self.candidate, [("read-1", left)])
        self.assertEqual({}, single)

    def test_repeated_context_is_not_extended(self):
        repeated = "ACGT" * 20
        read = "TTGCA" + repeated[:35]
        accepted, _ = _extensions(repeated, [("r1", read), ("r2", read)])
        self.assertNotIn("left", accepted)

    def test_conflicting_overhangs_are_not_extended(self):
        first = "TTGCA" + self.candidate[:35]
        second = "AAGGA" + self.candidate[:35]
        accepted, _ = _extensions(
            self.candidate, [("r1", first), ("r2", first),
                             ("r3", second), ("r4", second)])
        self.assertNotIn("left", accepted)


if __name__ == "__main__":
    unittest.main()
