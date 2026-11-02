import json
from pathlib import Path
import tempfile
import unittest

from satellite_discovery.m28_synthetic_assembly_diagnostics import (
    _failure_class,
    sequence_diagnostics,
)


class M28SyntheticAssemblyDiagnosticsTests(unittest.TestCase):
    def test_unique_and_repeated_kmers_are_described(self):
        unique = sequence_diagnostics("ACGTTGCA", k=4)
        repeated = sequence_diagnostics("ACGTACGT", k=4)
        self.assertEqual(unique["length"], 8)
        self.assertEqual(unique["unique_kmer_fraction"], 1.0)
        self.assertLess(repeated["unique_kmer_fraction"], 1.0)
        self.assertGreater(repeated["maximum_kmer_multiplicity"], 1)

    def test_upstream_failure_is_not_called_assembler_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stage = root / "stages/m6_fixture"
            stage.mkdir(parents=True)
            (stage / "manifest.json").write_text(json.dumps({"status": "failed"}))
            self.assertEqual(
                _failure_class(root, {"analysis_id": "fixture"}),
                "UPSTREAM_STAGE_FAILURE",
            )

    def test_missing_output_is_not_inferred_as_scientific_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stage = root / "stages/m6_fixture"
            stage.mkdir(parents=True)
            (stage / "manifest.json").write_text(json.dumps({"status": "complete"}))
            self.assertEqual(
                _failure_class(root, {"analysis_id": "fixture"}),
                "OUTPUT_MISSING_OR_NOT_EVALUATED",
            )


if __name__ == "__main__":
    unittest.main()
