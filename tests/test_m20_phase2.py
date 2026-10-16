import json
import hashlib
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from satellite_discovery import artifact_workflow, m20_phase1, m20_phase2


class M20Phase2SpecTests(unittest.TestCase):
    def _m6_manifest(self, output, stage_status="complete"):
        m6_root = output / "stages/m4_m6"
        stage_dir = m6_root / "m6_s01"
        stage_dir.mkdir(parents=True)
        artifacts = {
            "reconstruction_evidence.json": (
                "reconstruction_evidence", b'{"status":"NO_SUPPORTED_ASSEMBLY"}\n',
            ),
            "residual_manifest.json": (
                "residual_read_manifest", b'{"schema":"residual-read-manifest-v1"}\n',
            ),
        }
        inventory, contracts = [], {}
        for name, (artifact_type, content) in artifacts.items():
            (stage_dir / name).write_bytes(content)
            contracts[name] = artifact_type
            inventory.append({
                "path": name, "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            })
        (stage_dir / "manifest.json").write_text(json.dumps({
            "output_inventory": inventory, "output_contract": contracts,
        }))
        return m6_root, {
            "workflow_id": "m6-wf-test",
            "stages": [{
                "id": "m6_s01", "kind": "residual_evidence",
                "status": stage_status, "output_path": "m6_s01",
            }],
        }

    def test_registered_workflow_has_typed_independent_handoffs_and_no_truth(self):
        spec = m20_phase2.build_m4_m6_workflow_spec()
        rows = artifact_workflow.validate(spec, artifact_workflow.build_default_registry())
        self.assertEqual(
            ["fastq_qc", "residual_evidence"] * 3,
            [row["kind"] for row in rows],
        )
        encoded = json.dumps(spec, sort_keys=True).lower()
        for forbidden in ("heldout_truth", "expected_role", "shared_candidate"):
            self.assertNotIn(forbidden, encoded)
        for row in rows:
            if row["kind"] == "residual_evidence":
                self.assertEqual(1, row["config"]["threads"])
                self.assertEqual(2048, row["config"]["memory_mb"])
                self.assertEqual("spades", row["config"]["assembler"])
        m7_spec = m20_phase2.build_m7_workflow_spec(
            Path("/tmp/m20-spec-test"), {"stages": []}, Path("/tmp/m20-spec-test/stages/m4_m6"),
        )
        m7_rows = artifact_workflow.validate(m7_spec, artifact_workflow.build_default_registry())
        self.assertEqual(["independent_recurrence"], [row["kind"] for row in m7_rows])
        observations = m7_rows[0]["config"]["observations"]
        self.assertEqual(["s01", "s02", "s03"], [row["sample_id"] for row in observations])
        self.assertTrue(all(row["m6_state"] == "unavailable" for row in observations))
        self.assertEqual(3, len({row["sequencing_run_id"] for row in observations}))
        self.assertEqual(3, len({row["study_id"] for row in observations}))

    def test_missing_workflow_manifest_is_explicit_and_truth_stays_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            report = m20_phase2.run(output, runner=lambda *_args: None)
            self.assertEqual("INCOMPLETE", report["status"])
            self.assertEqual("UNAVAILABLE", report["m7"]["status"])
            self.assertEqual(
                "WorkflowManifestUnavailable", report["execution_error"]["m4_m6"]["type"],
            )
            self.assertEqual(
                "24a4cdc9c0337f373d49ee49482f6c49eb91de03d8993cbe9ac2358925ccacac",
                report["fixtures"]["manifest_sha256"],
            )
            self.assertEqual(
                "1d6e16d1c31975181dfa8cd86260297f2151d89914ff796d4ae23934936e2614",
                report["fixtures"]["heldout_truth_sha256"],
            )
            self.assertTrue((output / "report.json").is_file())
            self.assertTrue((output / "report.md").is_file())
            self.assertTrue((output / "report.html").is_file())
            self.assertTrue(report["fixtures"]["unchanged_after_execution"])

    def test_m7_handoff_is_bound_to_validated_m6_output_digests(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "run"
            output.mkdir()
            m6_root, manifest = self._m6_manifest(output)
            spec = m20_phase2.build_m7_workflow_spec(output, manifest, m6_root)
            rows = artifact_workflow.validate(spec, artifact_workflow.build_default_registry())
            s01 = rows[0]["config"]["observations"][0]
            self.assertEqual("available", s01["m6_state"])
            self.assertTrue(s01["source_artifact_id"].startswith("m6_s01:reconstruction_evidence:"))
            self.assertEqual(
                {"evidence_s01", "residual_s01"},
                set(rows[0]["inputs"]),
            )
            bad_type = json.loads(json.dumps(spec))
            bad_type["stages"][0]["inputs"]["evidence_s01"]["artifact_type"] = "raw_read"
            with self.assertRaises(ValueError):
                artifact_workflow.validate(bad_type, artifact_workflow.build_default_registry())

            evidence = m6_root / "m6_s01/reconstruction_evidence.json"
            evidence.write_text('{"status":"TAMPERED"}\n')
            tampered = m20_phase2.build_m7_workflow_spec(output, manifest, m6_root)
            tampered_s01 = tampered["stages"][0]["config"]["observations"][0]
            self.assertEqual("failed", tampered_s01["m6_state"])
            self.assertNotIn("evidence_input", tampered_s01)

    def test_interrupted_and_stale_manifests_are_not_reported_as_complete(self):
        self.assertEqual("INCOMPLETE", m20_phase2._status({"status": "interrupted"}))
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "workflow.json"
            manifest.write_text('{"status":"complete","stages":[]}\n')
            digest = m20_phase2._manifest_digest(manifest)
            _data, error = m20_phase2._safe_manifest(manifest, digest)
            self.assertEqual("StaleWorkflowManifest", error["type"])

    def test_post_stage_sequence_diagnostics_keep_strict_recovery_separate_from_alignment(self):
        expected = "A" * 400
        paf = (
            "contig_a\t398\t0\t398\t+\ttruth\t400\t1\t399\t398\t398\t60"
            "\tNM:i:0\tcg:Z:398M\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            fasta = Path(temporary) / "contigs.fasta"
            fasta.write_text(">contig_a\n" + "A" * 398 + "\n")
            with patch.object(m20_phase2.shutil, "which", return_value="/usr/bin/minimap2"), \
                    patch.object(m20_phase2.subprocess, "run", return_value=SimpleNamespace(
                        returncode=0, stdout=paf, stderr="",
                    )):
                result = m20_phase2._sequence_comparison(expected, fasta)
        self.assertFalse(result["full_length_exact_recovery"])
        best = result["alignment"]["best"]
        self.assertEqual(1.0, best["query_breadth"])
        self.assertEqual(0.995, best["reference_breadth"])
        self.assertEqual(1.0, best["sequence_identity"])
        self.assertEqual([1, 1], best["reference_terminal_losses"])
        self.assertEqual(1, result["fragmentation"]["contigs_aligned_to_truth"])

    def test_assembler_diagnostics_preserve_logs_and_distinguish_failure_cause(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            stage = output / "m6_s01"
            (stage / "assembly/raw").mkdir(parents=True)
            (stage / "assembly/manifest.json").write_text(json.dumps({
                "status": "failed", "exit_status": 21,
                "safe_command": ["spades.py", "--only-assembler", "-t", "1", "-m", "2"],
                "configuration": {"threads": 1, "memory_mb": 2048},
                "error": "External tool failed with exit status 21",
                "dependency_report": {
                    "status": "available",
                    "dependencies": [{"tool": "spades", "version_output": "SPAdes 4.1.0"}],
                },
            }))
            (stage / "assembly/raw/spades.log").write_text(
                "Memory limit set to 2 Gb\n"
                "601M / 601M\n"
                "ERROR Invalid kmer coverage histogram, make sure that the coverage is indeed uniform\n"
            )
            result = m20_phase2._assembler_diagnostics(
                output, stage, {"read_count": 40, "lengths": [100]},
            )
        self.assertEqual(21, result["exit_status"])
        self.assertEqual("available", result["dependency_status"])
        self.assertEqual(601, result["max_logged_memory_mb"])
        self.assertEqual(64, len(result["logs"]["spades"]["sha256"]))
        self.assertIn("does not establish why", result["interpretation"])

    def test_missing_dependency_and_symlinked_producer_outputs_are_not_handed_to_m7(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "dependency"
            output.mkdir()
            m6_root, manifest = self._m6_manifest(output, "dependency_missing")
            spec = m20_phase2.build_m7_workflow_spec(output, manifest, m6_root)
            self.assertEqual(
                "unavailable", spec["stages"][0]["config"]["observations"][0]["m6_state"],
            )
            self.assertEqual({}, spec["stages"][0]["inputs"])

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "escape"
            output.mkdir()
            m6_root = output / "stages/m4_m6"
            m6_root.mkdir(parents=True)
            outside = Path(temporary) / "outside"
            outside.mkdir()
            (outside / "reconstruction_evidence.json").write_text('{"status":"READ_SUPPORTED_ASSEMBLY"}')
            (m6_root / "m6_s01").symlink_to(outside, target_is_directory=True)
            manifest = {
                "workflow_id": "m6-wf-test",
                "stages": [{
                    "id": "m6_s01", "kind": "residual_evidence",
                    "status": "complete", "output_path": "m6_s01",
                }],
            }
            spec = m20_phase2.build_m7_workflow_spec(output, manifest, m6_root)
            self.assertEqual(
                "failed", spec["stages"][0]["config"]["observations"][0]["m6_state"],
            )
            self.assertEqual({}, spec["stages"][0]["inputs"])


@unittest.skipUnless(
    shutil.which("minimap2") and shutil.which("spades.py"),
    "optional live M4/M6 integration requires minimap2 and SPAdes",
)
class M20Phase2LiveTests(unittest.TestCase):
    def test_registered_m4_m6_m7_execution_and_heldout_evaluation(self):
        with tempfile.TemporaryDirectory(prefix="m20-phase2-live-") as temporary:
            report = m20_phase2.run(Path(temporary) / "run")
            self.assertTrue(report["fixtures"]["unchanged_after_execution"])
            self.assertEqual(3, len(report["samples"]))
            self.assertIn(report["m7"]["status"], {"COMPLETE", "BLOCKED", "UNAVAILABLE", "INCOMPLETE"})
            for row in report["samples"]:
                self.assertIn(row["qc_status"], {"COMPLETE", "BLOCKED", "UNAVAILABLE", "INCOMPLETE"})
                self.assertIn(row["m6_status"], {"COMPLETE", "BLOCKED", "UNAVAILABLE", "INCOMPLETE"})
                self.assertIn(row["candidate_availability"], {
                    "AVAILABLE", "UPSTREAM_UNAVAILABLE", "INCOMPLETE", "NOT_EVALUATED",
                    "NO_SUPPORTED_ASSEMBLY", "INVALID_OUTPUT",
                })
                if row["candidate_count"] is not None:
                    self.assertGreaterEqual(row["candidate_count"], 0)
                self.assertIn(row["m7_observation"]["recurrence_status"], {
                    "RECURRENT", "NO_RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS",
                    "NOT_EVALUATED",
                })
            self.assertEqual("UNEVALUABLE", report["diagnostics"]["s03_negative_control"]["state"])
            self.assertIsNone(report["diagnostics"]["s03_negative_control"]["prediction_count"])
            self.assertEqual(60, report["diagnostics"]["s03_negative_control"]["residual_counts"]["input_fragments"])
            self.assertEqual(0, report["diagnostics"]["s03_negative_control"]["residual_counts"]["eligible_fragments"])
            self.assertFalse(report["diagnostics"]["s03_negative_control"]["assembly_attempted"])
            self.assertNotEqual(
                report["diagnostics"]["independence"][0]["read_generation_seed"],
                report["diagnostics"]["independence"][1]["read_generation_seed"],
            )
            m6_workflow = json.loads(
                (Path(temporary) / "run/stages/m4_m6/workflow.json").read_text()
            )
            m7_workflow = json.loads(
                (Path(temporary) / "run/stages/m7/workflow.json").read_text()
            )
            self.assertEqual(6, len(m6_workflow["stages"]))
            self.assertEqual(1, len(m7_workflow["stages"]))
            self.assertTrue((Path(temporary) / "run/report.html").is_file())
            self.assertTrue((Path(temporary) / "run/report.md").is_file())


if __name__ == "__main__":
    unittest.main()
