import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from satellite_discovery.m36_preparation import (
    _sha,
    registered_assignments,
    validate_blinded_artifacts,
    verify_evidence_files,
)
from satellite_discovery.m36_runner import (
    ATTEMPT_TIMEOUT_SECONDS,
    MATRIX_WINDOW_SECONDS,
    AttemptInterrupted,
    RunnerBlocked,
    RunnerBudget,
    bounded_systemd_command,
    run_synthetic_dry_run,
    validate_evaluator_manifest,
    verify_execution_authorization,
    verify_tool_identity,
    run_registered_matrix,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = json.loads(
    (ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json").read_text()
)


def evaluator_fixture():
    assignments = registered_assignments(DESIGN)
    split_for = {
        f"f{index:02d}": (
            "development" if index <= 4 else
            "tuning" if index <= 8 else "held_out"
        )
        for index in range(1, 13)
    }
    seed_by_input = {}
    rows = []
    for index, assignment in enumerate(assignments):
        key = tuple(assignment[name] for name in (
            "block_id", "family_id", "condition_id", "repeat_id",
        ))
        seed_key = key
        read_seed = seed_by_input.setdefault(seed_key, 100_000 + len(seed_by_input))
        rows.append({
            **assignment,
            "split": split_for[assignment["family_id"]],
            "family_seed": 20_000 + int(assignment["family_id"][1:]),
            "read_seed": read_seed,
            "condition_parameters": {"fixture_only": True},
        })
    return {"schema": "m36-evaluator-execution-manifest-v1", "assignments": rows}


class M36RunnerTests(unittest.TestCase):
    def test_evaluator_manifest_covers_registry_and_preserves_pairing(self):
        manifest = evaluator_fixture()
        result = validate_evaluator_manifest(DESIGN, manifest)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["assignment_count"], 520)
        self.assertEqual(result["held_out_assignments"], 152)
        manifest["assignments"].pop()
        with self.assertRaisesRegex(RunnerBlocked, "cover all"):
            validate_evaluator_manifest(DESIGN, manifest)

    def test_evaluator_manifest_rejects_changed_family_seed_and_split(self):
        manifest = evaluator_fixture()
        manifest["assignments"][1]["family_seed"] += 1
        with self.assertRaisesRegex(RunnerBlocked, "family sequence seed"):
            validate_evaluator_manifest(DESIGN, manifest)
        manifest = evaluator_fixture()
        manifest["assignments"][1]["split"] = "held_out"
        with self.assertRaisesRegex(RunnerBlocked, "family split"):
            validate_evaluator_manifest(DESIGN, manifest)
        manifest = evaluator_fixture()
        paired = [
            row for row in manifest["assignments"]
            if row["block_id"] == "alternative_assemblers"
        ]
        paired[1]["read_seed"] += 1
        with self.assertRaisesRegex(RunnerBlocked, "byte-identical"):
            validate_evaluator_manifest(DESIGN, manifest)

    def test_scheduler_runs_only_small_synthetic_fixture_set(self):
        assignments = registered_assignments(DESIGN)[:3]
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "public"
            def execute(row, destination):
                destination.mkdir()
                return {"status": "COMPLETE", "evidence_path": "fixture.json"}
            report = run_synthetic_dry_run(
                assignments, execute, output_root=output,
            )
            self.assertEqual(report["status"], "PASS")
            self.assertFalse(report["registered_matrix_executed"])
            self.assertEqual(report["assignments_received"], 3)
            self.assertEqual([row["status"] for row in report["results"]], ["COMPLETE"] * 3)

    def test_scheduler_rejects_matrix_sized_dry_run(self):
        assignments = registered_assignments(DESIGN)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RunnerBlocked, "never the registered matrix"):
                run_synthetic_dry_run(
                    assignments, lambda *_: {"status": "COMPLETE"},
                    output_root=Path(folder) / "public",
                )

    def test_budget_exhaustion_marks_queued_fixtures_not_run(self):
        assignments = registered_assignments(DESIGN)[:2]
        calls = 0
        def clock():
            nonlocal calls
            calls += 1
            return 0 if calls == 1 else MATRIX_WINDOW_SECONDS
        with tempfile.TemporaryDirectory() as folder:
            report = run_synthetic_dry_run(
                assignments, lambda *_: {"status": "COMPLETE"},
                output_root=Path(folder) / "public", clock=clock,
            )
        self.assertEqual(
            [row["status"] for row in report["results"]],
            ["NOT_RUN_BUDGET_EXHAUSTED"] * 2,
        )

    def test_operator_interruption_is_distinct_and_stops_queued_work(self):
        assignments = registered_assignments(DESIGN)[:1]
        with tempfile.TemporaryDirectory() as folder:
            report = run_synthetic_dry_run(
                assignments,
                lambda *_: (_ for _ in ()).throw(AttemptInterrupted("cancel")),
                output_root=Path(folder) / "public",
            )
        self.assertEqual(report["status"], "CANCELLED")
        self.assertEqual(report["results"][0]["status"], "ASSEMBLY_INTERRUPTED")

    def test_authorization_requires_verified_signature_and_exact_scope(self):
        values = {
            "design_sha256": "a" * 64,
            "source_commit": "b" * 40,
            "tool_identity_sha256": "c" * 64,
            "evaluator_manifest_sha256": "d" * 64,
            "scope": "m36-synthetic-520-assignment-matrix",
        }
        with self.assertRaisesRegex(RunnerBlocked, "signature"):
            verify_execution_authorization(values, **{
                "design_sha256": values["design_sha256"],
                "source_commit": values["source_commit"],
                "tool_identity_sha256": values["tool_identity_sha256"],
            "evaluator_manifest_sha256": values["evaluator_manifest_sha256"],
            })
        verify_execution_authorization(
            values,
            design_sha256=values["design_sha256"],
            source_commit=values["source_commit"],
            tool_identity_sha256=values["tool_identity_sha256"],
            evaluator_manifest_sha256=values["evaluator_manifest_sha256"],
            signature_verifier=lambda _: True,
        )

    def test_registered_matrix_is_blocked_before_attempts_without_trusted_approval(self):
        manifest = evaluator_fixture()
        tools = {
            "spades": {"version": "SPAdes 3.15.5", "executable_sha256": "a" * 64},
            "tadpole": {
                "version": "BBTools 40.01", "executable_sha256": "b" * 64,
                "runtime_sha256": "c" * 64, "archive_sha256": "d" * 64,
            },
            "spades_package_sha256": "e" * 64,
        }
        tool_digest = _sha(json.dumps(
            tools, sort_keys=True, separators=(",", ":")
        ).encode())
        started = []
        with tempfile.TemporaryDirectory() as folder:
            restricted = Path(folder) / "restricted"
            restricted.mkdir(mode=0o700)
            restricted.chmod(0o700)
            with patch(
                "satellite_discovery.m36_runner.subprocess.run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "1" * 40, ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                ],
            ):
                with self.assertRaisesRegex(RunnerBlocked, "signature"):
                    run_registered_matrix(
                        DESIGN, manifest,
                        lambda *_: started.append(True),
                        authorization={}, signature_verifier=None,
                        design_sha256=_sha(
                            (ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json").read_bytes()
                        ),
                        source_commit="1" * 40, source_root=ROOT,
                        design_path=ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json",
                        tool_identity_sha256=tool_digest,
                        expected_tools=tools, observed_tools=tools,
                        public_root=Path(folder) / "public",
                        restricted_root=restricted,
                    )
        self.assertEqual(started, [])

    def test_tool_identity_mismatch_fails_closed(self):
        with self.assertRaisesRegex(RunnerBlocked, "spades"):
            verify_tool_identity(
                {"spades": {"version": "v1", "executable_sha256": "a"},
                 "tadpole": {"version": "v2", "executable_sha256": "b",
                             "runtime_sha256": "c", "archive_sha256": "d"},
                 "spades_package_sha256": "e"},
                {"spades": {"version": "v2", "executable_sha256": "a"},
                 "tadpole": {"version": "v2", "executable_sha256": "b",
                             "runtime_sha256": "c", "archive_sha256": "d"},
                 "spades_package_sha256": "e"},
            )

    def test_bounded_command_requires_resource_evidence(self):
        proof = {
            "cgroup": "/system.slice/m36.service",
            "cpu_max": [100000, 100000],
            "memory_max_bytes": 4 * 1024**3,
            "child_processes_inherit_cgroup": True,
        }
        with tempfile.TemporaryDirectory() as folder:
            def fake_run(command, **kwargs):
                self.assertIn("--property=CPUQuota=100%", command)
                self.assertIn(f"--property=MemoryMax={4 * 1024**3}", command)
                self.assertIn(f"--property=RuntimeMaxSec={ATTEMPT_TIMEOUT_SECONDS}s", command)
                return subprocess.CompletedProcess(
                    command, 0,
                    "M36_RESOURCE_EVIDENCE " + json.dumps(proof) + "\nassembly ok\n",
                    "",
                )
            result = bounded_systemd_command(
                ["spades.py", "-h"], cwd=folder, run=fake_run,
            )
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["enforcement_evidence"], proof)

    def test_corrupt_evidence_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifest.json").write_text("{}")
            report = verify_evidence_files({
                "evidence_files": [{"path": "manifest.json", "sha256": "0" * 64}],
            }, root=root)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("digest mismatch", report["reason"])

    def test_analysis_visible_leakage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "leaked"):
            validate_blinded_artifacts(
                {"logs/case.log": "split=held_out"},
                case_ids={"case-" + "a" * 24},
                forbidden_values={"held_out"},
            )


if __name__ == "__main__":
    unittest.main()

