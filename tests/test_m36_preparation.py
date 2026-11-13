import gzip
import json
import os
import tempfile
import unittest
from pathlib import Path

from satellite_discovery.m36_preparation import (
    audit_m25_generator,
    create_restricted_sidecar,
    inspect_assembler_provenance,
    preserve_restricted_raw_evidence,
    registered_assignments,
    validate_blinded_artifacts,
    validate_readiness,
    validate_post_execution_results,
    validate_truth_support_crosswalk,
    verify_evidence_files,
    _read_fastq_bytes,
)
from satellite_discovery.m36_preparation import _sha


DESIGN = json.loads(Path(__file__).resolve().parents[1].joinpath(
    "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json"
).read_text(encoding="utf-8"))


class M36PreparationTests(unittest.TestCase):
    def test_registry_expands_to_all_520_unique_assignments(self):
        assignments = registered_assignments(DESIGN)
        self.assertEqual(len(assignments), 520)
        self.assertEqual(len({
            (row["block_id"], row["family_id"], row["condition_id"],
             row["repeat_id"], row["assembler_id"])
            for row in assignments
        }), 520)
        broken = json.loads(json.dumps(DESIGN))
        broken["registered_case_manifest"]["blocks"][0]["condition_ids"].pop()
        with self.assertRaisesRegex(ValueError, "denominator mismatch"):
            registered_assignments(broken)

    def test_m25_generator_audit_checks_seed_ledger_and_target_absent_control(self):
        report = audit_m25_generator(seed=360001)
        self.assertEqual(report["status"], "PASS")
        self.assertTrue(report["deterministic_same_seed"])
        self.assertTrue(report["distinct_seed_changes_generated_bytes"])
        self.assertEqual(report["target_absent_control"]["target_derived_reads"], 0)
        self.assertEqual(
            report["read_count"],
            sum(report["read_counts_by_source_role"].values()),
        )
        self.assertFalse(report["experimental_matrix_executed"])
        with self.assertRaises(ValueError):
            audit_m25_generator(seed=-1)

    def test_one_to_nine_arm_fails_closed_unless_exactly_verified(self):
        report = audit_m25_generator(seed=360002, target_to_background="1:9")
        self.assertEqual(report["one_to_nine_status"], "PASS")
        self.assertEqual(
            report["read_counts_by_source_role"]["synthetic_background"],
            report["read_counts_by_source_role"]["target_truth"] * 9,
        )

    def test_sidecar_is_opaque_and_owner_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "restricted" / "evaluator.json"
            if os.name == "nt":
                with self.assertRaisesRegex(PermissionError, "ACL"):
                    create_restricted_sidecar(path, [{
                        "family_id": "f01", "split": "held_out",
                        "truth": "synthetic", "factor": "coverage_24",
                        "condition": "c01",
                    }])
                with self.assertRaisesRegex(PermissionError, "ACL"):
                    preserve_restricted_raw_evidence(
                        Path(folder) / "raw", {"raw/tool.log": b"restricted"}
                    )
                self.assertFalse(path.exists())
                return
            result = create_restricted_sidecar(path, [{
                "family_id": "f01", "split": "held_out", "truth": "synthetic",
                "factor": "coverage_24", "condition": "c01",
            }])
            body = json.loads(path.read_text(encoding="utf-8"))
            token = body["entries"][0]["opaque_case_id"]
            self.assertRegex(token, r"^case-[a-f0-9]{24}$")
            self.assertEqual(result["sha256"], _sha(path.read_bytes()))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                create_restricted_sidecar(path, body["entries"])
            raw_root = Path(folder) / "raw"
            raw_bytes = b"unmodified restricted log\n"
            stored = preserve_restricted_raw_evidence(
                raw_root, {"raw/tool.log": raw_bytes}
            )
            self.assertEqual((raw_root / "raw/tool.log").read_bytes(), raw_bytes)
            self.assertEqual(stored["files"]["raw/tool.log"], _sha(raw_bytes))
            self.assertFalse(stored["raw_bytes_modified"])

    def test_analysis_visible_paths_fastq_and_logs_reject_truth_leakage(self):
        case = "case-" + "a" * 24
        stage = "stage-" + "b" * 24 + "-s01"
        fastq = gzip.compress(f"@{case}-r00001\nACGT\n+\nIIII\n".encode("ascii"))
        validate_blinded_artifacts({
            f"runs/{case}/reads.fastq.gz": fastq,
            f"runs/{stage}/manifest.json": json.dumps({"stage_id": stage}),
            "logs/analysis.log": f"case={case} completed",
        }, case_ids={case}, forbidden_values={"held_out_truth_secret", "coverage_24"})
        bad_cases = [
            ({"runs/held_out/reads.fastq": "@r1\nACGT\n+\nIIII\n"}, {"held_out"}),
            ({"runs/manifest.json": json.dumps({"stage_id": "stage-held-out-s01"})}, {"truth-secret"}),
            ({"logs/run.log": "condition=coverage_24"}, {"coverage_24"}),
        ]
        for artifacts, forbidden in bad_cases:
            with self.subTest(artifacts=artifacts):
                with self.assertRaises(ValueError):
                    validate_blinded_artifacts(
                        artifacts, case_ids={case}, forbidden_values=forbidden
                    )
        with self.assertRaisesRegex(ValueError, "FASTQ header"):
            validate_blinded_artifacts(
                {"reads.fastq": "@family-f01\nACGT\n+\nIIII\n"},
                case_ids={case},
            )

    def test_synthetic_blind_handoff_scans_paths_commands_manifests_and_logs(self):
        with tempfile.TemporaryDirectory() as folder:
            if os.name == "nt":
                self.skipTest("Owner-only evaluator sidecar cannot be verified on Windows")
            sidecar_path = Path(folder) / "restricted" / "evaluator.json"
            create_restricted_sidecar(sidecar_path, [{
                "family_id": "f01", "split": "held_out", "truth": "ACGT",
                "factor": "coverage_24", "condition": "c01",
            }])
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            opaque = sidecar["entries"][0]["opaque_case_id"]
            fastq = gzip.compress(
                f"@{opaque}-r00001\nACGT\n+\nIIII\n".encode("ascii")
            )
            visible = {
                f"runs/{opaque}/reads.fastq.gz": fastq,
                f"runs/stage-{('b' * 24)}-s01/manifest.json":
                    json.dumps({"stage_id": "stage-" + "b" * 24 + "-s01"}),
                "commands/assembler.txt": f"assembler reads/{opaque}/reads.fastq.gz",
                "logs/sanitized.log": f"completed {opaque}",
            }
            validate_blinded_artifacts(
                visible, case_ids={opaque},
                forbidden_values={"held_out", "coverage_24", "ACGT"},
            )
            for name, value in (
                ("commands/argv.txt", "run --condition coverage_24"),
                ("logs/sanitized.log", "split=held_out"),
                ("runs/held_out/reads.fastq", "@r1\nACGT\n+\nIIII\n"),
            ):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    validate_blinded_artifacts(
                        {name: value}, case_ids={opaque},
                        forbidden_values={"held_out", "coverage_24", "ACGT"},
                    )

    def test_malformed_fastq_and_unavailable_registered_condition_fail_closed(self):
        for payload in (
            b"not-gzip",
            gzip.compress(b"@read\nACGT\n+\nIII\n"),
            gzip.compress(b"@read\nACGT\n+\nIIII\npartial\n"),
        ):
            with self.subTest(payload=payload[:20]):
                with self.assertRaises(ValueError):
                    _read_fastq_bytes(payload)
        broken = json.loads(json.dumps(DESIGN))
        broken["registered_case_manifest"]["blocks"][0]["condition_ids"].remove("c01")
        with self.assertRaisesRegex(ValueError, "denominator mismatch"):
            registered_assignments(broken)

    def test_truth_to_support_crosswalk_keeps_pipeline_stages_separate(self):
        truth = "ACGTACGT"
        reads = {"read-1": "ACGT"}
        ledger = {"read_provenance": {"read-1": {
            "source_role": "target_truth", "source_interval": [0, 4],
            "source_record_sha256": _sha(truth.encode("ascii")),
            "source_sequence_sha256": _sha(b"ACGT"),
        }}}
        no_contigs = validate_truth_support_crosswalk(
            truth_sequence=truth, read_sequences=reads, placement_ledger=ledger,
            contigs={}, support_evidence={},
        )
        self.assertEqual(no_contigs["generation"], "PASS")
        self.assertEqual(no_contigs["assembly"], "NO_CONTIGS")
        supported = validate_truth_support_crosswalk(
            truth_sequence=truth, read_sequences=reads, placement_ledger=ledger,
            contigs={"contig-1": truth},
            support_evidence={
                "supported_read_ids": ["read-1"],
                "supported_contig_ids": ["contig-1"],
                "supported_read_sha256": {"read-1": _sha(b"ACGT")},
                "supported_contig_sha256": {"contig-1": _sha(truth.encode("ascii"))},
                "read_placements": [{
                    "read_id": "read-1", "contig_id": "contig-1",
                    "start": 0, "cigar": "4=",
                }],
            },
        )
        self.assertEqual(supported["support"], "READ_SUPPORTED_ASSEMBLY")
        self.assertEqual(supported["verified_read_placement_count"], 1)
        self.assertEqual(supported["downstream_handoff"], "NOT_EVALUATED")
        mismatched_placement = {
            "supported_read_ids": ["read-1"],
            "supported_contig_ids": ["contig-1"],
            "supported_read_sha256": {"read-1": _sha(b"ACGT")},
            "supported_contig_sha256": {"contig-1": _sha(truth.encode("ascii"))},
            "read_placements": [{
                "read_id": "read-1", "contig_id": "contig-1",
                "start": 1, "cigar": "4=",
            }],
        }
        with self.assertRaisesRegex(ValueError, "disagrees with sequences"):
            validate_truth_support_crosswalk(
                truth_sequence=truth, read_sequences=reads, placement_ledger=ledger,
                contigs={"contig-1": truth},
                support_evidence=mismatched_placement,
            )
        bad = {"read_provenance": {"read-1": {
            **ledger["read_provenance"]["read-1"], "source_record_sha256": "0" * 64
        }}}
        with self.assertRaisesRegex(ValueError, "source truth"):
            validate_truth_support_crosswalk(
                truth_sequence=truth, read_sequences=reads, placement_ledger=bad,
                contigs={}, support_evidence={},
            )

    def test_readiness_checker_blocks_missing_tools_budget_and_accounting(self):
        report = validate_readiness(DESIGN, {})
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["registered_assignment_count"], 520)
        self.assertFalse(report["matrix_execution_performed"])
        self.assertFalse(report["phase2b_authorized"])
        self.assertEqual(report["checks"]["governance_restrictions"]["status"], "PASS")
        self.assertEqual(report["checks"]["one_vcpu_limit"]["status"], "BLOCKED")
        self.assertEqual(report["checks"]["assignment_accounting"]["status"], "PASS")
        self.assertEqual(report["checks"]["assignment_accounting"]["blocked"], 520)
        self.assertTrue(all(
            row["status"] == "BLOCKED" and row["blocked_reasons"]
            for row in report["assignment_manifest"]
        ))
        self.assertIsNone(report["execution_statuses"])
        self.assertNotIn("status_accounting", report["checks"])

    def test_evidence_manifest_recomputes_digest_and_rejects_placeholders(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            payload = b"actual fixture evidence\n"
            (root / "evidence.bin").write_bytes(payload)
            good = verify_evidence_files({
                "evidence_files": [{
                    "path": "evidence.bin", "sha256": _sha(payload),
                }],
            }, root=root)
            self.assertEqual(good["status"], "PASS")
            wrong = verify_evidence_files({
                "evidence_files": [{
                    "path": "evidence.bin", "sha256": "a" * 64,
                }],
            }, root=root)
            self.assertEqual(wrong["status"], "BLOCKED")
            self.assertIn("digest mismatch", wrong["reason"])
            malformed = verify_evidence_files({
                "evidence_files": [{"path": "evidence.bin", "sha256": "a" * 63}],
            }, root=root)
            self.assertEqual(malformed["status"], "BLOCKED")
            traversal = verify_evidence_files({
                "evidence_files": [{"path": "../outside", "sha256": "a" * 64}],
            }, root=root)
            self.assertEqual(traversal["status"], "BLOCKED")

    def test_post_execution_validation_is_separate_and_requires_exact_terminal_roster(self):
        assignments = registered_assignments(DESIGN)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            empty = validate_post_execution_results(DESIGN, [], root=root)
            self.assertEqual(empty["status"], "BLOCKED")
            self.assertEqual(empty["terminal_result_count"], 0)
            actual = []
            for index, row in enumerate(assignments):
                path = root / f"evidence-{index:03d}.json"
                payload = f"synthetic validator fixture {index}\n".encode()
                path.write_bytes(payload)
                actual.append({
                    **row, "status": "COMPLETE", "evidence_path": path.name,
                    "evidence_sha256": _sha(payload),
                })
            self.assertEqual(
                validate_post_execution_results(DESIGN, actual, root=root)["status"],
                "PASS",
            )
            actual[0]["evidence_sha256"] = "c" * 64
            self.assertEqual(
                validate_post_execution_results(DESIGN, actual, root=root)["status"],
                "BLOCKED",
            )

    def test_tool_inventory_never_runs_assembly(self):
        report = inspect_assembler_provenance()
        self.assertEqual(set(report["tools"]), {"spades", "tadpole"})
        self.assertFalse(report["assembly_executed"])
        for row in report["tools"].values():
            self.assertIn(row["status"], {"PASS", "BLOCKED"})
            self.assertEqual(row["default_resource_requirements"]["threads"], 1)


if __name__ == "__main__":
    unittest.main()
