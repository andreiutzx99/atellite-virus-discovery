import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery import (
    artifact_contracts, m20_phase2b, m20_phase3, m9_reference_snapshot,
)


def _fixture_report(root, result):
    return {
        "fixtures": {
            **result,
            "unchanged_after_execution": True,
            "truth_outside_analysis_inputs": True,
        }
    }


class M20Phase3FixtureTests(unittest.TestCase):
    def test_frozen_phase2b_accepts_current_and_timeout_bound_legacy_manifest(self):
        for legacy in (False, True):
            with self.subTest(legacy_manifest=legacy), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                result = m20_phase2b.generate_fixtures(root)
                if legacy:
                    path = root / "benchmark_manifest.json"
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                    manifest["matrix"]["resource_bounds"].pop("stage_timeout_seconds")
                    path.write_bytes(m20_phase2b._canonical(manifest))
                    result["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(
                    (result["manifest_sha256"], result["heldout_truth_sha256"]),
                    m20_phase3._verify_frozen_phase2b(root, _fixture_report(root, result)),
                )
                self.assertFalse((root / "inputs/heldout_truth.json").exists())

    def test_frozen_phase2b_rejects_changed_input_even_if_report_is_updated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = m20_phase2b.generate_fixtures(root)
            path = root / "inputs/c001/reads.fastq.gz"
            path.write_bytes(path.read_bytes() + b"tamper")
            with self.assertRaisesRegex(ValueError, "input changed"):
                m20_phase3._verify_frozen_phase2b(root, _fixture_report(root, result))

    def test_legacy_manifest_exception_rejects_unrelated_missing_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = m20_phase2b.generate_fixtures(root)
            path = root / "benchmark_manifest.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest.pop("cases")
            path.write_bytes(m20_phase2b._canonical(manifest))
            result["manifest_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "manifest differs"):
                m20_phase3._verify_frozen_phase2b(
                    root, _fixture_report(root, result),
                )

    def test_output_verification_is_pinned_to_stage_manifest_and_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = root / "m6_c001"
            stage.mkdir()
            output = stage / "candidate_sequence_set.json"
            output.write_bytes(b"{}")
            identity = {"stage": "m6-residual-evidence", "producer_run": "run-a"}
            document = {
                "identity": identity,
                "output_contract": {
                    "candidate_sequence_set.json": "m8_candidate_sequence_set",
                },
                "output_inventory": [{
                    "path": output.name,
                    "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                }],
            }
            manifest_path = stage / "manifest.json"
            manifest_path.write_bytes(m20_phase2b._canonical(document))
            row = {
                "output_path": stage.name,
                "stage_manifest_sha256": hashlib.sha256(
                    manifest_path.read_bytes(),
                ).hexdigest(),
                "stage_manifest_identity": identity,
            }
            with patch.object(artifact_contracts, "validate_artifact"):
                verified = m20_phase3._verified_output(
                    root, row, output.name, "m8_candidate_sequence_set",
                )
                self.assertIsNotNone(verified)
                self.assertTrue(output.samefile(verified))
                output.write_bytes(b'{"changed":true}')
                self.assertIsNone(m20_phase3._verified_output(
                    root, row, output.name, "m8_candidate_sequence_set",
                ))
                output.write_bytes(b"{}")
                document["identity"] = {
                    "stage": "m6-residual-evidence", "producer_run": "run-b",
                }
                manifest_path.write_bytes(m20_phase2b._canonical(document))
                row["stage_manifest_sha256"] = hashlib.sha256(
                    manifest_path.read_bytes(),
                ).hexdigest()
                self.assertIsNone(m20_phase3._verified_output(
                    root, row, output.name, "m8_candidate_sequence_set",
                ))

    def test_synthetic_protein_snapshot_is_digest_validated(self):
        with tempfile.TemporaryDirectory() as temporary:
            manifest_path, payload_path = m20_phase3._protein_snapshot(Path(temporary))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            checked = m9_reference_snapshot.validate_snapshot(manifest, payload_path)
            self.assertEqual("m20-phase3-protein-v1", checked["snapshot_id"])
            self.assertEqual({"SYNPROT1", "SYNPROT2"}, set(checked["reference_map"]))

    def test_missing_optional_runtime_is_a_distinct_stage_state(self):
        workflow = {"stages": [{"id": "blastp", "status": "dependency_missing"}]}
        self.assertEqual("DEPENDENCY_MISSING", m20_phase3._stage_state(workflow, "blastp"))
        self.assertEqual("NOT_EVALUATED", m20_phase3._stage_state(workflow, "absent"))

    def test_m8_summary_preserves_no_match_and_dependency_missing_as_distinct(self):
        document = {
            "aggregate_status": "PARTIAL",
            "panel_state": "COMPLETE",
            "queries": [{
                "candidate_id": "synthetic-candidate",
                "branches": [
                    {"masking_branch": "plain",
                     "status": "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"},
                    {"masking_branch": "softmask",
                     "status": "DEPENDENCY_UNAVAILABLE"},
                ],
            }],
        }
        summary = m20_phase3._m8_result_summary(document)
        statuses = [branch["status"] for branch in summary["queries"][0]["branches"]]
        self.assertEqual([
            "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
            "DEPENDENCY_UNAVAILABLE",
        ], statuses)
        self.assertNotEqual(statuses[0], statuses[1])


@unittest.skipUnless(
    shutil.which("blastn") and shutil.which("makeblastdb") and shutil.which("blastdbcmd"),
    "synthetic M8 panel test requires BLAST+ tools",
)
class M20Phase3PanelTests(unittest.TestCase):
    def test_synthetic_nucleotide_panel_contains_only_verified_artificial_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            panel, error = m20_phase3._m8_panel(Path(temporary))
            self.assertIsNone(error)
            manifest_path, payloads = panel
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual({"SYNM8A.1", "SYNM8B.1"},
                             {row["accession_version"] for row in document["records"]})
            self.assertEqual(8, len(payloads))


@unittest.skipUnless(
    shutil.which("spades.py") and shutil.which("minimap2"),
    "Phase 3 end-to-end test requires the Phase 2B assembler toolchain",
)
class M20Phase3LiveTests(unittest.TestCase):
    def test_all_cases_run_through_typed_m8_m9_m10_handoffs_without_mutating_baseline(self):
        with tempfile.TemporaryDirectory(prefix="m20-phase3-live-") as temporary:
            root = Path(temporary)
            upstream = root / "phase2b"
            baseline = m20_phase2b.run(upstream)
            watched = [
                upstream / "report.json",
                upstream / "benchmark_manifest.json",
                upstream / "heldout_truth.json",
                upstream / "inputs/c001/reads.fastq.gz",
            ]
            before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched}

            report = m20_phase3.run(root / "phase3", upstream)

            self.assertEqual("COMPLETE", report["status"])
            self.assertEqual(baseline["fixtures"]["manifest_sha256"],
                             report["upstream"]["phase2b_fixture_manifest_sha256"])
            self.assertEqual(10, len(report["cases"]))
            self.assertEqual(
                ["c001", "c002", "c003", "c004", "c005",
                 "c006", "c007", "c008", "c009", "c010"],
                [row["sample_id"] for row in report["cases"]],
            )
            for row in report["cases"]:
                self.assertEqual("COMPLETE", row["m9_orf"]["status"])
                self.assertEqual("COMPLETE", row["m10"]["status"])
                self.assertIn(row["m9_blastp"]["status"],
                              {"COMPLETE", "DEPENDENCY_MISSING"})
                self.assertIn(row["m8"]["stage_status"],
                              {"COMPLETE", "DEPENDENCY_UNAVAILABLE"})
                self.assertTrue(row["candidate_producer"]["stage_manifest_sha256"])
                if row["m8"]["stage_status"] == "COMPLETE":
                    branch_statuses = {
                        branch["status"]
                        for query in row["m8"]["query_status"]["queries"]
                        for branch in query["branches"]
                    }
                    self.assertTrue(branch_statuses)
                contexts = row["m10"]["summary"]["optional_context_state"]
                self.assertEqual("SUPPLIED", contexts["m7"]["state"])
                self.assertEqual("SUPPLIED", contexts["m9"]["state"])
                if row["m8"]["stage_status"] == "COMPLETE":
                    self.assertEqual("SUPPLIED", contexts["m8"]["state"])
                    self.assertEqual(
                        "VERIFIED", row["m9_orf"]["m8_context_validation"]["state"]
                    )
                    self.assertTrue(
                        row["m9_orf"]["m8_context_validation"]["stage_manifest_sha256"]
                    )
            after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in watched}
            self.assertEqual(before, after)
            specs = list((root / "phase3/cases").glob("*/**/workflow.json"))
            self.assertTrue(specs)
            for path in specs:
                spec = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotIn("heldout_truth", json.dumps(spec).lower())
                self.assertNotIn("expected_role", json.dumps(spec).lower())
            self.assertTrue(any(
                "M10 exact architecture is not functional annotation" in item
                for item in report["limitations"]
            ))


if __name__ == "__main__":
    unittest.main()
