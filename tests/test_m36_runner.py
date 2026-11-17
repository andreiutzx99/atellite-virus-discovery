import json
import os
import base64
import hashlib
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

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
    expected_condition_parameters,
    condition_catalog_sha256,
    FROZEN_SEED_POLICY,
    validate_input_identity,
    verify_byte_artifacts,
    verify_tool_identity,
    run_registered_matrix,
)
from satellite_discovery.m36_security import (
    AUTHORIZATION_SCHEMA,
    RestrictedEvidenceStore,
    canonical_json_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
DESIGN = json.loads(
    (ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json").read_text()
)


def _non_cooperative_fixture(*_args):
    while True:
        time.sleep(0.02)


def evaluator_fixture():
    assignments = registered_assignments(DESIGN)
    split_for = {
        f"f{index:02d}": (
            "development" if index <= 4 else
            "held_out" if index <= 8 else "tuning"
        )
        for index in range(1, 13)
    }
    parameters = expected_condition_parameters(DESIGN)
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
            "condition_parameters": parameters[
                (assignment["block_id"], assignment["condition_id"])
            ],
        })
    return {
        "schema": "m36-evaluator-execution-manifest-v2",
        "design_sha256": _sha(
            (ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json").read_bytes()
        ),
        "condition_catalog_sha256": condition_catalog_sha256(DESIGN),
        "seed_policy": FROZEN_SEED_POLICY,
        "assignments": rows,
    }


class M36RunnerTests(unittest.TestCase):
    def test_evaluator_manifest_covers_registry_and_preserves_pairing(self):
        manifest = evaluator_fixture()
        result = validate_evaluator_manifest(
            DESIGN, manifest, design_sha256=manifest["design_sha256"],
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["assignment_count"], 520)
        self.assertEqual(result["held_out_assignments"], 184)
        manifest["assignments"].pop()
        with self.assertRaisesRegex(RunnerBlocked, "cover all"):
            validate_evaluator_manifest(
                DESIGN, manifest, design_sha256=manifest["design_sha256"],
            )

    def test_evaluator_manifest_rejects_changed_family_seed_and_split(self):
        manifest = evaluator_fixture()
        manifest["assignments"][1]["family_seed"] += 1
        with self.assertRaisesRegex(RunnerBlocked, "family sequence seed"):
            validate_evaluator_manifest(
                DESIGN, manifest, design_sha256=manifest["design_sha256"],
            )
        manifest = evaluator_fixture()
        manifest["assignments"][1]["split"] = "held_out"
        with self.assertRaisesRegex(RunnerBlocked, "family split"):
            validate_evaluator_manifest(
                DESIGN, manifest, design_sha256=manifest["design_sha256"],
            )
        manifest = evaluator_fixture()
        paired = [
            row for row in manifest["assignments"]
            if row["block_id"] == "alternative_assemblers"
        ]
        paired[1]["read_seed"] += 1
        with self.assertRaisesRegex(RunnerBlocked, "byte-identical"):
            validate_evaluator_manifest(
                DESIGN, manifest, design_sha256=manifest["design_sha256"],
            )

    def test_evaluator_manifest_rejects_parameter_drift(self):
        manifest = evaluator_fixture()
        manifest["assignments"][0]["condition_parameters"]["nominal_coverage"] = 999
        with self.assertRaisesRegex(RunnerBlocked, "condition parameters differ"):
            validate_evaluator_manifest(
                DESIGN, manifest, design_sha256=manifest["design_sha256"],
            )

    def test_evaluator_manifest_rejects_malformed_split_type(self):
        manifest = evaluator_fixture()
        manifest["assignments"][0]["split"] = []
        with self.assertRaisesRegex(RunnerBlocked, "lacks frozen seeds"):
            validate_evaluator_manifest(
                DESIGN, manifest, design_sha256=manifest["design_sha256"],
            )

    def test_actual_input_hashes_enforce_pairing_and_repeat_independence(self):
        assignments = [
            {
                "block_id": "alternative_assemblers",
                "family_id": "f01", "condition_id": "c01",
                "repeat_id": repeat, "assembler_id": assembler,
            }
            for repeat, digest in (("r01", "a" * 64), ("r02", "b" * 64))
            for assembler in ("spades", "tadpole")
        ]
        results = [{"input_sha256": {"read1": "a" * 64}} for _ in range(2)]
        results += [{"input_sha256": {"read1": "b" * 64}} for _ in range(2)]
        self.assertEqual(validate_input_identity(assignments, results), {})
        results[1]["input_sha256"]["read1"] = "c" * 64
        self.assertEqual(
            validate_input_identity(assignments, results),
            {0: "paired assemblers received different input bytes",
             1: "paired assemblers received different input bytes"},
        )
        results[1]["input_sha256"]["read1"] = "a" * 64
        results[2]["input_sha256"]["read1"] = "a" * 64
        results[3]["input_sha256"]["read1"] = "a" * 64
        self.assertEqual(
            set(validate_input_identity(assignments, results)),
            {0, 1, 2, 3},
        )

    def test_artifact_digests_are_recomputed_from_actual_bytes(self):
        normalized, digests = verify_byte_artifacts(
            {"reads.fastq": b"ACGT"},
            {"reads.fastq": hashlib.sha256(b"ACGT").hexdigest()},
        )
        self.assertEqual(normalized["reads.fastq"], b"ACGT")
        with self.assertRaisesRegex(RunnerBlocked, "actual bytes"):
            verify_byte_artifacts(
                {"reads.fastq": b"ACGT"},
                {"reads.fastq": "0" * 64},
            )
        with self.assertRaisesRegex(RunnerBlocked, "path"):
            verify_byte_artifacts({"../escape": b"bad"})

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
        payload = {
            "schema": "m36-phase2b-production-approval-v1",
            "design_sha256": "a" * 64,
            "source_commit": "b" * 40,
            "tool_identity_sha256": "c" * 64,
            "evaluator_manifest_sha256": "d" * 64,
            "scope": "m36-synthetic-520-assignment-matrix",
            "synthetic_only": True,
            "resource_budget": {
                "workers": 4,
                "attempt_timeout_seconds": 180,
                "matrix_window_seconds": 23400,
                "slot_budget_seconds": 93600,
                "total_budget_seconds": 28800,
            },
        }
        private_key = Ed25519PrivateKey.generate()
        envelope = {
            "schema": AUTHORIZATION_SCHEMA,
            "payload": payload,
            "signature_ed25519": base64.b64encode(
                private_key.sign(canonical_json_bytes(payload))
            ).decode("ascii"),
        }
        args = {
            "design_sha256": payload["design_sha256"],
            "source_commit": payload["source_commit"],
            "tool_identity_sha256": payload["tool_identity_sha256"],
            "evaluator_manifest_sha256": payload["evaluator_manifest_sha256"],
        }
        with self.assertRaisesRegex(RunnerBlocked, "envelope"):
            verify_execution_authorization({}, **args)
        with patch(
            "satellite_discovery.m36_security._load_external_public_key",
            return_value=private_key.public_key(),
        ):
            verify_execution_authorization(envelope, **args)
            envelope["payload"]["resource_budget"]["workers"] = 5
            with self.assertRaisesRegex(RunnerBlocked, "exact run scope and budget"):
                verify_execution_authorization(envelope, **args)
        payload["resource_budget"]["workers"] = 4
        envelope["payload"] = payload
        envelope["signature_ed25519"] = base64.b64encode(
            private_key.sign(canonical_json_bytes(payload))
        ).decode("ascii")
        with patch(
            "satellite_discovery.m36_security.TRUST_ANCHOR_PATH",
            Path(tempfile.gettempdir()) / "m36-missing-trust-anchor.pem",
        ):
            with self.assertRaisesRegex(RunnerBlocked, "trust"):
                verify_execution_authorization(envelope, **args)

    @unittest.skipUnless(os.name == "posix", "registered execution storage is Linux-only")
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
            public = Path(folder) / "public"
            public.mkdir(mode=0o700)
            manifest_path = restricted / "evaluator_manifest.json"
            manifest_path.write_bytes(canonical_json_bytes(manifest))
            manifest_path.chmod(0o600)
            with patch(
                "satellite_discovery.m36_runner.subprocess.run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, "1" * 40, ""),
                    subprocess.CompletedProcess([], 0, "", ""),
                ],
            ):
                with self.assertRaisesRegex(RunnerBlocked, "envelope"):
                    run_registered_matrix(
                        DESIGN, manifest_path,
                        lambda *_: started.append(True),
                        authorization={},
                        design_sha256=_sha(
                            (ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json").read_bytes()
                        ),
                        source_commit="1" * 40, source_root=ROOT,
                        design_path=ROOT / "docs/M36_POSITIVE_CONTROL_ASSEMBLY_INVESTIGATION.json",
                        tool_identity_sha256=tool_digest,
                        expected_tools=tools, observed_tools=tools,
                        public_root=public,
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
            with (
                patch("satellite_discovery.m36_runner.os", SimpleNamespace(name="posix")),
                patch("satellite_discovery.m36_runner.Path.is_file", return_value=True),
            ):
                result = bounded_systemd_command(
                    ["spades.py", "-h"], cwd=folder, run=fake_run,
                )
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["enforcement_evidence"], proof)

    def test_bounded_command_timeout_stops_and_verifies_service_cleanup(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if "systemd-run" in command:
                raise subprocess.TimeoutExpired(command, timeout=195)
            if "is-active" in command:
                return subprocess.CompletedProcess(command, 3, "", "")
            if "show" in command:
                return subprocess.CompletedProcess(command, 1, "", "")
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            patch("satellite_discovery.m36_runner.os", SimpleNamespace(name="posix")),
            patch("satellite_discovery.m36_runner.Path.is_file", return_value=True),
        ):
            result = bounded_systemd_command(
                ["spades.py", "-h"], cwd=tempfile.gettempdir(), run=fake_run,
            )
        self.assertEqual(result["status"], "ASSEMBLY_INTERRUPTED")
        self.assertTrue(result["cleanup_verified"])
        self.assertTrue(any("kill" in command for command in calls))
        self.assertTrue(any("stop" in command for command in calls))

    def test_corrupt_evidence_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "manifest.json").write_text("{}")
            report = verify_evidence_files({
                "evidence_files": [{"path": "manifest.json", "sha256": "0" * 64}],
            }, root=root)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("digest mismatch", report["reason"])

    @unittest.skipUnless(os.name == "posix", "owner-only POSIX storage is required")
    def test_restricted_store_is_owner_only_immutable_and_outside_public_roots(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source, public, restricted = (
                base / "source", base / "public", base / "restricted",
            )
            for path in (source, public, restricted):
                path.mkdir(mode=0o700)
                path.chmod(0o700)
            store = RestrictedEvidenceStore(
                restricted, source_root=source, public_root=public,
            )
            digest = store.write_bytes("attempts/raw.log", b"partial synthetic log")
            self.assertEqual(digest, _sha(b"partial synthetic log"))
            self.assertEqual(
                store.inventory_directory("attempts"),
                {"raw.log": digest},
            )
            self.assertEqual(
                (restricted / "attempts/raw.log").stat().st_mode & 0o777,
                0o600,
            )
            with self.assertRaises((FileExistsError, RunnerBlocked)):
                store.write_bytes("attempts/raw.log", b"overwrite")
            with self.assertRaisesRegex(RunnerBlocked, "unsafe"):
                store.write_bytes("../public/leak.txt", b"no")
            with self.assertRaisesRegex(RunnerBlocked, "overlaps"):
                RestrictedEvidenceStore(
                    source, source_root=source, public_root=public,
                )
            terminal = {
                "case_id": "case-" + "c" * 24,
                "status": "ASSEMBLY_EXECUTION_FAILED",
            }
            store.write_terminal_record(terminal["case_id"], terminal)
            with self.assertRaises((FileExistsError, RunnerBlocked)):
                store.write_terminal_record(terminal["case_id"], terminal)
            duplicate_keys = restricted / "bad-manifest.json"
            duplicate_keys.write_bytes(b'{"schema":"one","schema":"two"}')
            duplicate_keys.chmod(0o600)
            with self.assertRaisesRegex(RunnerBlocked, "malformed"):
                store.load_manifest(duplicate_keys)

    @unittest.skipUnless(os.name == "posix", "registered execution is Linux-only")
    def test_non_cooperative_worker_is_killed_at_deadline(self):
        from satellite_discovery.m36_runner import run_isolated_attempt

        message = run_isolated_attempt(
            _non_cooperative_fixture, (),
            deadline=time.monotonic() + 0.3,
            cancel_event=threading.Event(),
        )
        self.assertEqual(message["kind"], "interrupted")
        self.assertTrue(message["cleanup_verified"])

    def test_analysis_visible_leakage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "leaked"):
            validate_blinded_artifacts(
                {"logs/case.log": "split=held_out"},
                case_ids={"case-" + "a" * 24},
                forbidden_values={"held_out"},
            )


if __name__ == "__main__":
    unittest.main()

