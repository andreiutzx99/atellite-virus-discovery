import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path

from satellite_discovery import m20_phase1


class M20Phase1FixtureTests(unittest.TestCase):
    def test_fixtures_are_reproducible_and_blind(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, second = root / "first", root / "second"
            result = m20_phase1.generate_fixtures(first)
            m20_phase1.generate_fixtures(second)
            self.assertEqual(result, m20_phase1.verify_fixtures(first))
            self.assertEqual(
                (first / "inputs/source_manifest.json").read_bytes(),
                (second / "inputs/source_manifest.json").read_bytes(),
            )
            truth = json.loads((first / "heldout_truth.json").read_text())
            positive = [row for row in truth["cases"] if row["expected_role"] == "positive"]
            self.assertEqual(positive[0]["candidate_sequence"], positive[1]["candidate_sequence"])
            self.assertEqual(
                (first / "inputs/s01/reads.fastq.gz").read_bytes(),
                (second / "inputs/s01/reads.fastq.gz").read_bytes(),
            )
            self.assertNotEqual(
                (first / "inputs/s01/reads.fastq.gz").read_bytes(),
                (first / "inputs/s02/reads.fastq.gz").read_bytes(),
            )
            manifest = json.loads((first / "inputs/source_manifest.json").read_text())
            self.assertEqual(9, len(manifest["files"]))
            self.assertEqual(10, 40 * m20_phase1.READ_LENGTH // m20_phase1.CANDIDATE_LENGTH)
            self.assertFalse({"positive", "negative", "candidate", "truth"} & set(manifest))
            self.assertFalse(any(
                word in path.lower()
                for path in manifest["files"]
                for word in ("positive", "negative", "candidate", "truth")
            ))
            for sample in m20_phase1.SAMPLE_IDS:
                raw = gzip.decompress((first / "inputs" / sample / "reads.fastq.gz").read_bytes()).decode()
                self.assertNotIn("positive", raw.lower())
                self.assertNotIn("negative", raw.lower())
                self.assertNotIn("candidate", raw.lower())
                self.assertTrue(all(
                    line.startswith("@r") for line in raw.splitlines()[::4]
                ))
            self.assertEqual(2, len(positive))
            self.assertEqual("negative", truth["cases"][2]["expected_role"])
            self.assertIsNone(truth["cases"][2]["candidate_sequence"])
            self.assertIn("planted_orf", positive[0])

    def test_rejects_self_rehashed_fixture_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m20_phase1.generate_fixtures(root)
            target = root / "inputs/s01/reads.fastq.gz"
            target.write_bytes(target.read_bytes() + b"tampered")
            manifest_path = root / "inputs/source_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["files"]["s01/reads.fastq.gz"]["sha256"] = m20_phase1._sha(target.read_bytes())
            manifest["files"]["s01/reads.fastq.gz"]["bytes"] = target.stat().st_size
            manifest_path.write_bytes(m20_phase1._canonical(manifest))
            with self.assertRaisesRegex(ValueError, "deterministic generator"):
                m20_phase1.verify_fixtures(root)

    def test_rejects_stale_extra_input_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            m20_phase1.generate_fixtures(root)
            (root / "inputs/s01/old.fastq").write_text("stale")
            with self.assertRaisesRegex(ValueError, "stale"):
                m20_phase1.verify_fixtures(root)
            with self.assertRaisesRegex(ValueError, "traversal"):
                m20_phase1._safe_path(root, "../escape.txt")

    @unittest.skipIf(os.name == "nt", "Directory symlinks are not portable on Windows")
    def test_rejects_symlink_fixture_root_and_sample_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            outside = base / "outside"
            outside.mkdir()
            root_link = base / "root-link"
            root_link.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "(?i)symlink"):
                m20_phase1.generate_fixtures(root_link)
            root = base / "root"
            (root / "inputs").mkdir(parents=True)
            (root / "inputs/s01").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "(?i)symlink"):
                m20_phase1.generate_fixtures(root)
            self.assertEqual([], list(outside.iterdir()))


class M20ContractMapTests(unittest.TestCase):
    def test_checked_in_map_matches_live_registry(self):
        path = Path(__file__).parents[1] / "docs/M20_REGISTERED_CONTRACT_MAP.json"
        actual = json.loads(path.read_text())
        self.assertEqual(m20_phase1.build_contract_map(), actual)
        self.assertEqual(m20_phase1.AUDITED_MAIN, actual["audited_main_commit"])
        self.assertIn("m8_candidate_sequence_set",
                      actual["stages"]["residual_evidence"]["output_contracts"]["candidate_sequence_set.json"])
        unsupported = {(row["from"], row["to"]) for row in actual["unsupported_edges"]}
        self.assertIn(("m8_homology", "m12_artifact_review"), unsupported)
        self.assertIn(("m10_exact_first", "m12_artifact_review"), unsupported)
        m12 = actual["producer_bindings"]["M12"]
        self.assertEqual({"M5", "M6"}, set(m12))
        self.assertNotIn("M7", m12)


if __name__ == "__main__":
    unittest.main()
