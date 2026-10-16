import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from satellite_discovery import m18_workflow


class M18FixtureTests(unittest.TestCase):
    def test_fixture_generation_is_deterministic_and_guarded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first, second = root / "first", root / "second"
            m18_workflow.generate_fixture_bundle(first)
            m18_workflow.generate_fixture_bundle(second)
            paths = sorted(path.relative_to(first) for path in first.rglob("*") if path.is_file())
            self.assertEqual(
                {str(path): (first / path).read_bytes() for path in paths},
                {str(path): (second / path).read_bytes() for path in paths},
            )
            source = m18_workflow.validate_fixture_bundle(first)
            self.assertTrue(source["synthetic_only"])
            self.assertEqual(12, len(source["files"]))
            truth = json.loads((first / "fixture_truth.json").read_text())
            self.assertEqual({"RNA", "DNA"}, {case["pathway"] for case in truth["cases"]})
            self.assertEqual(4, len(truth["cases"]))
            self.assertFalse((first / "fixture_truth.json").resolve().is_relative_to(
                (first / "datasets").resolve()
            ))

    def test_provenance_manifest_cannot_self_attest_altered_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m18_workflow.generate_fixture_bundle(root)
            read_path = root / "datasets/rna_supported/reads.fastq.gz"
            read_path.write_bytes(b"not the deterministic fixture")
            with self.assertRaisesRegex(ValueError, "altered fixture bytes"):
                m18_workflow.validate_fixture_bundle(root)

    def test_workflow_graph_uses_registered_stages_and_excludes_truth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            m18_workflow._build_workflow(root)
            specification = json.loads((root / "m18-workflow.json").read_text())
            self.assertEqual(16, len(specification["stages"]))
            kinds = [stage["kind"] for stage in specification["stages"]]
            self.assertEqual(4, kinds.count("fastq_qc"))
            self.assertEqual(4, kinds.count("residual_evidence"))
            self.assertEqual(4, kinds.count("m9_orf_translation"))
            self.assertEqual(4, kinds.count("m10_exact_first"))
            encoded = json.dumps(specification)
            self.assertNotIn("fixture_truth", encoded)
            self.assertNotIn("scenario_label", encoded)
            for stage in specification["stages"]:
                if stage["kind"] == "residual_evidence":
                    self.assertEqual("fastq_qc", next(
                        row["kind"] for row in specification["stages"]
                        if row["id"] == stage["inputs"]["read1"]["stage"]
                    ))
                    self.assertEqual("candidate_sequence_set.json",
                                     next(row for row in specification["stages"]
                                          if row["id"] == f"m9_{stage['config']['sample_id']}")
                                     ["inputs"]["candidate_sequence_set"]["artifact"])


@unittest.skipUnless(os.environ.get("RUN_OPTIONAL_TOOL_TESTS") == "1",
                     "Optional live minimap2/SPAdes integration job")
class M18LiveWorkflowTests(unittest.TestCase):
    def test_real_registered_qc_m6_m9_m10_graph(self):
        if not shutil.which("minimap2") or not (shutil.which("spades.py") or shutil.which("spades")):
            self.skipTest("minimap2 or SPAdes is unavailable")
        with tempfile.TemporaryDirectory(prefix="m18-live-") as folder:
            report = m18_workflow.run(Path(folder) / "m18")
            self.assertEqual("complete", report["workflow_status"])
            cases = {case["case_id"]: case for case in report["cases"]}
            for case_id in ("rna_supported", "dna_supported"):
                row = cases[case_id]
                self.assertEqual("AVAILABLE", row["assembly_and_read_back"]["candidate_availability"])
                self.assertEqual(["READ_SUPPORTED_ASSEMBLY"],
                                 row["assembly_and_read_back"]["candidate_support_statuses"])
                self.assertEqual("COMPLETE", row["m9_orf_evidence"]["aggregate_status"])
                self.assertEqual(1, row["m10_architecture_evidence"]["candidate_count"])
            self.assertEqual("UPSTREAM_UNAVAILABLE",
                             cases["rna_reference_only"]["assembly_and_read_back"]["candidate_availability"])
            low_support = cases["dna_insufficient_support"]["assembly_and_read_back"]
            self.assertEqual("AVAILABLE", low_support["candidate_availability"])
            self.assertEqual(["LOW_SUPPORT_ASSEMBLY"], low_support["candidate_support_statuses"])
            self.assertEqual(1000, low_support["support_thresholds"]["min_distinct_fragments"])
            self.assertGreaterEqual(cases["rna_supported"]["qc"]["rejected_reads"], 2)


if __name__ == "__main__":
    unittest.main()
