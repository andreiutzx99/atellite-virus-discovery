import gzip
import json
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
    validate_truth_support_crosswalk,
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
            },
        )
        self.assertEqual(supported["support"], "READ_SUPPORTED_ASSEMBLY")
        self.assertEqual(supported["downstream_handoff"], "NOT_EVALUATED")
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
        self.assertEqual(report["checks"]["status_accounting"]["status"], "BLOCKED")

        assignments = registered_assignments(DESIGN)
        evidence = {
            "hashes": {name: "a" * 64 for name in (
                "design", "source_commit", "generator", "inputs", "tool executables",
                "raw outputs", "artifact inventory", "archive",
            )},
            "tools": {name: {"available": True, "version": "pinned",
                             "executable_sha256": "b" * 64,
                             **({"archive_sha256": "d" * 64, "runtime_sha256": "e" * 64}
                                if name == "tadpole" else {})}
                      for name in ("spades", "tadpole")},
            "generator_audit": {
                "status": "PASS", "deterministic_same_seed": True,
                "target_absent_control": {"target_derived_reads": 0},
                "one_to_nine_status": "PASS",
            },
            "blinding_audit": {
                "sidecar_isolated": True, "raw_evidence_preserved": True,
                "leakage_checks_passed": True,
            },
            "truth_support_crosswalk": {
                "generation": "PASS", "assembly": "CONTIGS_EMITTED",
                "support": "READ_SUPPORTED_ASSEMBLY",
            },
            "compatibility_smoke": {"status": "PASS"},
            "resource_limits": {"max_vcpus_per_attempt": 1,
                                "enforcement_verified": True,
                                "enforcement_mechanism": "test cgroup"},
            "assignment_statuses": [
                {**row, "status": "COMPLETE", "evidence_sha256": "c" * 64}
                for row in assignments
            ],
            "matrix_execution_requested": False,
        }
        passing = validate_readiness(DESIGN, evidence)
        self.assertEqual(passing["status"], "PREPARATION_GATES_PASS")
        evidence["assignment_statuses"].pop()
        blocked = validate_readiness(DESIGN, evidence)
        self.assertEqual(blocked["checks"]["status_accounting"]["status"], "BLOCKED")

    def test_tool_inventory_never_runs_assembly(self):
        report = inspect_assembler_provenance()
        self.assertEqual(set(report["tools"]), {"spades", "tadpole"})
        self.assertFalse(report["assembly_executed"])
        for row in report["tools"].values():
            self.assertIn(row["status"], {"PASS", "BLOCKED"})
            self.assertEqual(row["default_resource_requirements"]["threads"], 1)


if __name__ == "__main__":
    unittest.main()
