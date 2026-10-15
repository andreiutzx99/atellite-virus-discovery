import json
import shutil
import tempfile
import unittest
from pathlib import Path

from satellite_discovery.technical_pilot import run_synthetic_demo


@unittest.skipUnless(shutil.which("minimap2"), "minimap2 is required for the synthetic mapping test")
class SyntheticTechnicalPilotTests(unittest.TestCase):
    def test_synthetic_qc_mapping_coverage_and_reporting(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "technical-pilot"
            result = run_synthetic_demo(output)

            self.assertEqual(result["schema"], "hcov229e-technical-pilot-synthetic-v1")
            self.assertEqual(result["status"], "synthetic_fixture_only")
            self.assertEqual(result["public_virus_status"], "HELD")
            self.assertEqual(result["sequence_confirmation_status"], "NOT_ASSESSED")
            self.assertFalse(result["authorizing"])
            self.assertEqual(result["read_quality"]["reads_before"], 5)
            self.assertEqual(result["read_quality"]["reads_after"], 4)
            self.assertEqual(result["read_quality"]["reads_with_adapter_match"], 1)
            self.assertGreater(result["read_quality"]["bases_trimmed"], 0)
            self.assertEqual(result["read_quality"]["rejected_reads"], 1)
            self.assertEqual(result["mapping"]["records_total"], 4)
            self.assertEqual(result["mapping"]["mapped_primary_records"], 3)
            self.assertEqual(result["mapping"]["unmapped_records"], 1)
            self.assertTrue(result["mapping"]["unmapped_reads_retained_in_sam"])
            self.assertEqual(
                {row["synthetic_role"] for row in result["mapping"]["references"]},
                {"host_like", "virus_reference_like"},
            )
            mapped_by_role = {
                row["synthetic_role"]: row["mapped_records"]
                for row in result["mapping"]["references"]
            }
            self.assertEqual(mapped_by_role, {"host_like": 2, "virus_reference_like": 1})
            self.assertTrue(all(row["breadth_fraction"] > 0 for row in result["coverage"]))
            self.assertEqual(result["biological_interpretation"]["viral_presence"], "not_assessed")
            self.assertEqual(result["biological_interpretation"]["satellite_virus_discovery"], "not_claimed")
            self.assertTrue((output / "qc" / "qc.json").is_file())
            self.assertTrue((output / "synthetic_alignment.sam").is_file())
            self.assertTrue((output / "reference_provenance.json").is_file())
            self.assertTrue((output / "report.html").is_file())
            saved = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, result)

            with self.assertRaisesRegex(ValueError, "never overwritten"):
                run_synthetic_demo(output)


if __name__ == "__main__":
    unittest.main()
