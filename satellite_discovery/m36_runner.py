"""Fail-closed coordinator for the M36 synthetic Phase 2B matrix.

This module does not launch work at import time. Real matrix execution requires
an independently verified, commit-scoped authorization and evaluator manifest.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import pickle
import secrets
import signal
import subprocess
import sys
import threading
import time
from typing import Callable

from .m36_preparation import (
    RunnerBlocked,
    SHA256,
    TERMINAL_STATUSES,
    preserve_restricted_raw_evidence,
    registered_assignments,
    validate_blinded_artifacts,
    verify_evidence_files,
)
from .m36_security import (
    RestrictedEvidenceStore,
    canonical_json_bytes,
    verify_scoped_authorization,
)

MAX_WORKERS = 4
ATTEMPT_TIMEOUT_SECONDS = 180
MATRIX_WINDOW_SECONDS = int(6.5 * 3600)
TOTAL_BUDGET_SECONDS = int(8 * 3600)
MEMORY_MAX_BYTES = 4 * 1024**3
RUNNER_SCHEMA = "m36-phase2b-runner-report-v1"
ASSIGNMENT_FIELDS = (
    "block_id", "family_id", "condition_id", "repeat_id", "assembler_id",
)
FROZEN_SEED_POLICY = {
    "family_seed_role": "independent_sequence_family",
    "read_seed_role": "independent_read_simulation",
    "technical_repeat_rule": "distinct_read_seed",
    "paired_assembler_rule": "same_read_seed_within_assignment",
}


class AttemptInterrupted(RuntimeError):
    """An attempt was stopped by an operator or host interruption."""


@dataclass(frozen=True)
class RunnerBudget:
    workers: int = MAX_WORKERS
    attempt_timeout_seconds: int = ATTEMPT_TIMEOUT_SECONDS
    matrix_window_seconds: int = MATRIX_WINDOW_SECONDS
    total_budget_seconds: int = TOTAL_BUDGET_SECONDS
    slot_budget_seconds: int = 26 * 3600

    def validate(self) -> None:
        if (
            self.workers != MAX_WORKERS
            or self.attempt_timeout_seconds != ATTEMPT_TIMEOUT_SECONDS
            or self.matrix_window_seconds != MATRIX_WINDOW_SECONDS
            or self.total_budget_seconds != TOTAL_BUDGET_SECONDS
            or self.slot_budget_seconds != 26 * 3600
        ):
            raise RunnerBlocked("runner limits differ from the frozen M36 budget")


def assignment_key(row: dict) -> tuple[str, ...]:
    try:
        key = tuple(row[name] for name in ASSIGNMENT_FIELDS)
    except (KeyError, TypeError) as error:
        raise RunnerBlocked("assignment is missing a registered identity field") from error
    if any(not isinstance(value, str) or not value for value in key):
        raise RunnerBlocked("assignment identity values must be non-empty strings")
    return key


def expected_condition_parameters(design: dict) -> dict[tuple[str, str], dict]:
    """Derive exact declared parameters from the frozen preregistration."""
    baseline = design.get("frozen_baseline")
    blocks = design.get("matrix")
    if not isinstance(baseline, dict) or not isinstance(blocks, list):
        raise RunnerBlocked("frozen condition specification is missing")
    base = {
        "generator": baseline.get("generator"),
        "target_length_nt": baseline.get("target_length_nt"),
        "nominal_coverage": baseline.get("nominal_coverage"),
        "read_length_nt": baseline.get("read_length_nt"),
        "substitution_rate": baseline.get("substitution_rate"),
        "insertion_rate": baseline.get("insertion_rate"),
        "deletion_rate": baseline.get("deletion_rate"),
        "read_start_mode": baseline.get("read_start_mode"),
        "synthetic_background_coverage": baseline.get("synthetic_background_coverage"),
        "report_realized_values": baseline.get("report_realized_values"),
        "target_background_specification": "frozen_m35_generator_baseline",
    }
    if any(value is None for value in base.values()):
        raise RunnerBlocked("frozen baseline condition parameters are incomplete")
    expected: dict[tuple[str, str], dict] = {}
    for block in blocks:
        block_id = block["block_id"]
        conditions = block.get("conditions")
        if block_id == "alternative_assemblers":
            conditions = block.get("locked_arms")
        if not isinstance(conditions, list):
            raise RunnerBlocked(f"{block_id}: preregistered conditions are missing")
        for index, label in enumerate(conditions, start=1):
            params = dict(base)
            params["preregistered_condition"] = label
            if "_x_abundance_1_to_9" in label:
                params["nominal_coverage"] = int(label.split("_", 2)[1])
                params["target_to_background_ratio"] = [1, 9]
                params["execution_state"] = "BLOCKED_GENERATOR_AUDIT"
            elif label.startswith("coverage_"):
                params["nominal_coverage"] = int(label.split("_", 1)[1])
            elif label.startswith("read_length_"):
                params["read_length_nt"] = int(label.rsplit("_", 1)[1])
            if "abundance_1_to_9" in label:
                params["target_to_background_ratio"] = [1, 9]
                params["execution_state"] = "BLOCKED_GENERATOR_AUDIT"
            if "low_complexity" in label:
                params["sequence_complexity"] = "low_complexity_stress_sequence"
                params["execution_state"] = "BLOCKED_SEQUENCE_SPECIFICATION"
            if label.startswith("substitution_rate_"):
                encoded = label.removeprefix("substitution_rate_")
                params["substitution_rate"] = float(encoded.replace("_", "."))
            if label == "alternate_error_position_distribution_same_rates":
                params["error_position_distribution"] = "alternate_same_declared_rates"
                params["execution_state"] = "BLOCKED_DISTRIBUTION_UNSPECIFIED"
            if label == "background_only_at_frozen_baseline":
                params["target_present"] = False
                params["target_to_background_ratio"] = [0, 1]
            if label == "zero_substitution_input":
                params["substitution_rate"] = 0.0
            expected[(block_id, f"c{index:02d}")] = params
    return expected


def condition_catalog_sha256(design: dict) -> str:
    catalog = expected_condition_parameters(design)
    rows = [
        {"block_id": block, "condition_id": condition, "parameters": parameters}
        for (block, condition), parameters in sorted(catalog.items())
    ]
    return hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def validate_evaluator_manifest(
    design: dict, manifest: dict, *, design_sha256: str,
) -> dict:
    """Validate the private per-attempt seed/condition map without exposing it."""
    if not isinstance(manifest, dict):
        raise RunnerBlocked("restricted evaluator manifest must be a JSON object")
    if manifest.get("schema") != "m36-evaluator-execution-manifest-v2":
        raise RunnerBlocked("missing or unsupported evaluator execution manifest")
    if manifest.get("design_sha256") != design_sha256:
        raise RunnerBlocked("evaluator manifest is not bound to the preregistration digest")
    if manifest.get("condition_catalog_sha256") != condition_catalog_sha256(design):
        raise RunnerBlocked("evaluator manifest condition catalog differs from preregistration")
    if manifest.get("seed_policy") != FROZEN_SEED_POLICY:
        raise RunnerBlocked("evaluator manifest seed roles differ from the frozen policy")
    expected = {assignment_key(row) for row in registered_assignments(design)}
    parameter_catalog = expected_condition_parameters(design)
    rows = manifest.get("assignments")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise RunnerBlocked("evaluator manifest does not cover all registered assignments")
    observed = []
    family_seeds: dict[str, int] = {}
    family_splits: dict[str, str] = {}
    splits_by_block: dict[str, dict[str, set[str]]] = {}
    for row in rows:
        key = assignment_key(row)
        if (
            type(row.get("family_seed")) is not int
            or type(row.get("read_seed")) is not int
            or row["family_seed"] < 0 or row["read_seed"] < 0
            or not isinstance(row.get("condition_parameters"), dict)
            or not row["condition_parameters"]
            or not isinstance(row.get("split"), str)
            or row["split"] not in {"development", "tuning", "held_out"}
        ):
            raise RunnerBlocked("evaluator entry lacks frozen seeds, split, or parameters")
        declared_parameters = parameter_catalog.get((row["block_id"], row["condition_id"]))
        try:
            parameters_match = (
                declared_parameters is not None
                and canonical_json_bytes(row["condition_parameters"])
                == canonical_json_bytes(declared_parameters)
            )
        except (TypeError, ValueError):
            parameters_match = False
        if not parameters_match:
            raise RunnerBlocked(
                "condition parameters differ from the frozen scientific preregistration"
            )
        family = row["family_id"]
        prior_seed = family_seeds.setdefault(family, row["family_seed"])
        if prior_seed != row["family_seed"]:
            raise RunnerBlocked("family sequence seed changes across assignments")
        prior_split = family_splits.setdefault(family, row["split"])
        if prior_split != row["split"]:
            raise RunnerBlocked("family split changes across assignments")
        splits_by_block.setdefault(row["block_id"], {}).setdefault(
            row["split"], set()
        ).add(family)
        observed.append(key)
    if len(set(observed)) != len(expected) or set(observed) != expected:
        raise RunnerBlocked("evaluator manifest contains duplicate or unregistered assignments")
    split_counts = {
        split: sum(value == split for value in family_splits.values())
        for split in ("development", "tuning", "held_out")
    }
    if split_counts != {"development": 4, "tuning": 4, "held_out": 4}:
        raise RunnerBlocked("family splits do not match the frozen 4/4/4 allocation")
    alternative_splits = splits_by_block.get("alternative_assemblers", {})
    if {
        split: len(alternative_splits.get(split, set()))
        for split in ("development", "tuning", "held_out")
    } != {"development": 4, "tuning": 0, "held_out": 4}:
        raise RunnerBlocked(
            "alternative assembler assignments must use four development and four held-out families"
        )
    if len(set(family_seeds.values())) != len(family_seeds):
        raise RunnerBlocked("independent families must have distinct family seeds")
    if set(family_seeds.values()) & {row["read_seed"] for row in rows}:
        raise RunnerBlocked("family-generation and read-simulation seeds must be separate")
    repeat_seeds: dict[tuple[str, str, str], dict[str, set[int]]] = {}
    for row in rows:
        group = (row["block_id"], row["family_id"], row["condition_id"])
        repeat_seeds.setdefault(group, {}).setdefault(row["repeat_id"], set()).add(
            row["read_seed"]
        )
    for block, family, condition in repeat_seeds:
        per_repeat = repeat_seeds[(block, family, condition)]
        if any(len(seeds) != 1 for seeds in per_repeat.values()):
            raise RunnerBlocked("paired assemblers must use byte-identical per-repeat reads")
        if len(per_repeat) > 1 and len({next(iter(s)) for s in per_repeat.values()}) != len(per_repeat):
            raise RunnerBlocked("technical repeats must use independent read seeds")
    return {
        "status": "PASS",
        "assignment_count": len(rows),
        "family_count": len(family_seeds),
        "held_out_assignments": sum(row["split"] == "held_out" for row in rows),
        "condition_catalog_sha256": condition_catalog_sha256(design),
    }


def validate_input_identity(assignments: list[dict], results: list[dict]) -> dict[int, str]:
    """Compare actual generated-byte hashes across paired tools and repeats."""
    by_pair: dict[tuple, list[tuple[int, dict, dict]]] = {}
    by_repeat: dict[tuple, list[tuple[int, dict, dict]]] = {}
    for index, (assignment, result) in enumerate(zip(assignments, results)):
        digests = result.get("input_sha256")
        if not isinstance(digests, dict) or not digests:
            continue
        base = (
            assignment["block_id"], assignment["family_id"],
            assignment["condition_id"],
        )
        pair = (*base, assignment["repeat_id"])
        by_pair.setdefault(pair, []).append((index, assignment, digests))
        by_repeat.setdefault(base, []).append((index, assignment, digests))
    mismatches = {}
    for group, entries in by_pair.items():
        assemblers = {entry[1]["assembler_id"] for entry in entries}
        if len(assemblers) > 1 and len({canonical_json_bytes(entry[2]) for entry in entries}) != 1:
            for index, _, _ in entries:
                mismatches[index] = "paired assemblers received different input bytes"
    for group, entries in by_repeat.items():
        by_repeat_id: dict[str, list[dict]] = {}
        for _, assignment, digests in entries:
            by_repeat_id.setdefault(assignment["repeat_id"], []).append(digests)
        if len(by_repeat_id) > 1:
            representatives = [
                canonical_json_bytes(rows[0])
                for _, rows in sorted(by_repeat_id.items())
                if rows
            ]
            if len(set(representatives)) != len(representatives):
                for index, assignment, _ in entries:
                    if assignment["repeat_id"] in by_repeat_id:
                        mismatches[index] = "technical repeats reused identical input bytes"
    return mismatches


def verify_byte_artifacts(
    artifacts: dict,
    declared_sha256: dict | None = None,
    *,
    allow_empty: bool = False,
) -> tuple[dict[str, bytes], dict[str, str]]:
    """Normalize artifact bytes and recompute each digest from the payload."""
    if not isinstance(artifacts, dict) or (not artifacts and not allow_empty):
        raise RunnerBlocked("artifact byte mapping is missing or empty")
    if declared_sha256 is not None and not isinstance(declared_sha256, dict):
        raise RunnerBlocked("declared artifact digest mapping is malformed")
    normalized: dict[str, bytes] = {}
    for name, content in artifacts.items():
        if (
            not isinstance(name, str) or not name or Path(name).is_absolute()
            or "\\" in name
            or ":" in name.split("/", 1)[0]
            or any(part in ("", ".", "..") for part in Path(name).parts)
        ):
            raise RunnerBlocked("artifact path is malformed")
        if isinstance(content, bytes):
            normalized[name] = content
        elif isinstance(content, str):
            normalized[name] = content.encode("utf-8")
        else:
            raise RunnerBlocked("artifact payload must be bytes or text")
    digests = {
        name: hashlib.sha256(content).hexdigest()
        for name, content in sorted(normalized.items())
    }
    if declared_sha256 is not None and declared_sha256 != digests:
        raise RunnerBlocked("declared artifact digests differ from actual bytes")
    return normalized, digests


def write_public_artifact(
    public_root: Path, case_id: str, name: str, content: bytes, expected_sha256: str,
) -> str:
    relative = Path(name)
    if (
        not name or relative.is_absolute() or "\\" in name
        or ":" in name.split("/", 1)[0]
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise RunnerBlocked("public artifact path is malformed")
    base = public_root / case_id
    if base.is_symlink() or not base.is_dir():
        raise RunnerBlocked("public attempt output directory is unsafe")
    target = base
    parts = relative.parts
    for part in parts[:-1]:
        target = target / part
        if target.is_symlink():
            raise RunnerBlocked("public artifact path contains a symlink")
        target.mkdir(mode=0o755, exist_ok=True)
        if not target.is_dir():
            raise RunnerBlocked("public artifact parent is not a directory")
    target = target / parts[-1]
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(target, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        observed = target.read_bytes()
        digest = hashlib.sha256(observed).hexdigest()
        if observed != content or digest != expected_sha256:
            raise RunnerBlocked("public output bytes changed during storage")
        return digest
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def verify_tool_identity(expected: dict, observed: dict) -> None:
    """Bind both assembler identities and package/runtime digests before execution."""
    for name in ("spades", "tadpole"):
        left, right = expected.get(name), observed.get(name)
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise RunnerBlocked(f"{name} identity is missing")
        fields = ("version", "executable_sha256")
        if (
            left.get("status") not in (None, "PASS")
            or right.get("status") not in (None, "PASS")
            or any(not left.get(field) or left.get(field) != right.get(field)
                   for field in fields)
            or not SHA256.fullmatch(str(left.get("executable_sha256", "")))
        ):
            raise RunnerBlocked(f"{name} executable identity differs from the frozen manifest")
    if expected["tadpole"].get("runtime_sha256") != observed["tadpole"].get("runtime_sha256"):
        raise RunnerBlocked("Tadpole runtime digest differs from the frozen manifest")
    if expected["tadpole"].get("archive_sha256") != observed["tadpole"].get("archive_sha256"):
        raise RunnerBlocked("Tadpole archive digest differs from the frozen manifest")
    if expected.get("spades_package_sha256") != observed.get("spades_package_sha256"):
        raise RunnerBlocked("SPAdes package digest differs from the frozen manifest")


def assert_isolated_storage(public_root: str | Path, restricted_root: str | Path) -> None:
    public = Path(public_root).resolve()
    restricted = Path(restricted_root).resolve()
    if public == restricted or public.is_relative_to(restricted) or restricted.is_relative_to(public):
        raise RunnerBlocked("restricted evidence storage must be separate from public artifacts")
    if not restricted.is_dir():
        raise RunnerBlocked("restricted evidence storage is not provisioned")
    if os.name == "posix" and restricted.stat().st_mode & 0o077:
        raise RunnerBlocked("restricted storage must be owner-only")


def verify_execution_authorization(
    authorization: dict,
    *,
    design_sha256: str,
    source_commit: str,
    tool_identity_sha256: str,
    evaluator_manifest_sha256: str,
    budget: RunnerBudget = RunnerBudget(),
) -> None:
    """Verify a scoped Ed25519 approval against the host-installed trust anchor."""
    budget.validate()
    verify_scoped_authorization(
        authorization,
        expected_payload={
            "schema": "m36-phase2b-production-approval-v1",
            "design_sha256": design_sha256,
            "source_commit": source_commit,
            "tool_identity_sha256": tool_identity_sha256,
            "evaluator_manifest_sha256": evaluator_manifest_sha256,
            "scope": "m36-synthetic-520-assignment-matrix",
            "synthetic_only": True,
            "resource_budget": {
                "workers": budget.workers,
                "attempt_timeout_seconds": budget.attempt_timeout_seconds,
                "matrix_window_seconds": budget.matrix_window_seconds,
                "slot_budget_seconds": budget.slot_budget_seconds,
                "total_budget_seconds": budget.total_budget_seconds,
            },
        },
    )


def bounded_systemd_command(
    command: list[str],
    *,
    cwd: str | Path,
    timeout_seconds: int = ATTEMPT_TIMEOUT_SECONDS,
    memory_max_bytes: int = MEMORY_MAX_BYTES,
    run: Callable = subprocess.run,
) -> dict:
    """Run one external stage in a kernel-enforced, child-inheriting cgroup."""
    if not command or any(not isinstance(part, str) or not part for part in command):
        raise RunnerBlocked("assembler command is empty or malformed")
    if timeout_seconds != ATTEMPT_TIMEOUT_SECONDS or memory_max_bytes != MEMORY_MAX_BYTES:
        if not (1 <= timeout_seconds <= ATTEMPT_TIMEOUT_SECONDS
                and 1 <= memory_max_bytes <= MEMORY_MAX_BYTES):
            raise RunnerBlocked("attempt resource limits exceed frozen M36 limits")
    if os.name != "posix" or not Path("/sys/fs/cgroup/cgroup.controllers").is_file():
        raise RunnerBlocked("Linux cgroup v2 is required for matrix execution")
    unit = "m36-attempt-" + hashlib.sha256(
        (str(time.time_ns()) + "\0" + "\0".join(command)).encode()
    ).hexdigest()[:20]
    probe = (
        "import json,os,sys;"
        "line=next((x for x in open('/proc/self/cgroup').read().splitlines() if x.startswith('0::')),None);"
        "assert line is not None,'unified cgroup missing';"
        "p='/sys/fs/cgroup'+line.split('::',1)[1];"
        "q,period=map(int,open(p+'/cpu.max').read().split());"
        "m=open(p+'/memory.max').read().strip();"
        "assert q>0 and period>0 and q<=period,'CPU quota exceeds one vCPU';"
        "assert m!='max' and int(m)<=4294967296,'memory limit missing or too high';"
        "print('M36_RESOURCE_EVIDENCE '+json.dumps({'cgroup':line,'cpu_max':[q,period],"
        "'memory_max_bytes':int(m),'child_processes_inherit_cgroup':True}),flush=True);"
        "os.execvpe(sys.argv[1],sys.argv[1:],os.environ)"
    )
    wrapped = [
        "sudo", "systemd-run", "--quiet", "--wait", "--pipe", "--collect",
        f"--unit={unit}", "--property=Type=exec", "--property=CPUQuota=100%",
        f"--property=MemoryMax={memory_max_bytes}",
        f"--property=RuntimeMaxSec={timeout_seconds}s",
        "--property=KillMode=control-group", "--property=SendSIGKILL=yes",
        "--property=TimeoutStopSec=2s",
        "--property=TasksMax=512", f"--working-directory={Path(cwd).resolve()}",
        "--", sys.executable, "-c", probe, *command,
    ]
    started = time.monotonic()
    try:
        result = run(
            wrapped, cwd=cwd, capture_output=True, text=True,
            timeout=timeout_seconds + 15, check=False,
        )
        lines = result.stdout.splitlines()
        proof = None
        if lines and lines[0].startswith("M36_RESOURCE_EVIDENCE "):
            proof = json.loads(lines.pop(0).removeprefix("M36_RESOURCE_EVIDENCE "))
        outcome = (
            "COMPLETE" if result.returncode == 0 and proof
            else "ASSEMBLY_EXECUTION_FAILED"
        )
        cleanup_verified = None
        if outcome != "COMPLETE":
            cleanup_verified = _terminate_systemd_unit(unit, run=run)
            if not cleanup_verified:
                raise RunnerBlocked(
                    "failed systemd attempt or child-process cleanup could not be verified"
                )
        return {
            "status": outcome, "returncode": result.returncode,
            "stdout": "\n".join(lines), "stderr": result.stderr,
            "command": command, "service_unit": unit,
            "enforcement_evidence": proof,
            "cleanup_verified": cleanup_verified,
            "resource_limits": {
                "cpu_quota": "100%", "memory_max_bytes": memory_max_bytes,
                "timeout_seconds": timeout_seconds,
                "children_inherit_cgroup": True,
            },
            "elapsed_seconds": time.monotonic() - started,
        }
    except subprocess.TimeoutExpired as error:
        if not _terminate_systemd_unit(unit, run=run):
            raise RunnerBlocked(
                "timed-out systemd unit or child-process cleanup could not be verified"
            ) from error
        return {
            "status": "ASSEMBLY_INTERRUPTED", "returncode": None,
            "stdout": error.stdout or "", "stderr": error.stderr or "",
            "command": command, "service_unit": unit,
            "reason": "attempt timeout; systemd unit and child cleanup verified",
            "cleanup_verified": True,
            "resource_limits": {
                "cpu_quota": "100%", "memory_max_bytes": memory_max_bytes,
                "timeout_seconds": timeout_seconds,
                "children_inherit_cgroup": True,
            },
            "elapsed_seconds": time.monotonic() - started,
        }
    except KeyboardInterrupt:
        if not _terminate_systemd_unit(unit, run=run):
            raise RunnerBlocked(
                "cancelled systemd unit or child-process cleanup could not be verified"
            )
        raise AttemptInterrupted("operator cancelled the attempt")


def _terminate_systemd_unit(unit: str, *, run: Callable) -> bool:
    """Stop the transient unit's whole cgroup and verify that it is inactive."""
    base = [
        "sudo", "systemctl", "kill", "--kill-who=all",
        "--signal=SIGKILL", unit,
    ]
    try:
        run(base, capture_output=True, text=True, timeout=5, check=False)
        run(
            ["sudo", "systemctl", "stop", unit],
            capture_output=True, text=True, timeout=5, check=False,
        )
        inactive = run(
            ["sudo", "systemctl", "is-active", "--quiet", unit],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if inactive.returncode == 0:
            return False
        group = run(
            ["sudo", "systemctl", "show", "--property=ControlGroup", "--value", unit],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    group_name = (group.stdout or "").strip()
    if group.returncode != 0 or not group_name:
        # --collect removes an inactive unit and its cgroup after the service exits.
        return inactive.returncode != 0
    cgroup_root = Path("/sys/fs/cgroup").resolve()
    cgroup = (cgroup_root / group_name.lstrip("/")).resolve()
    if not cgroup.is_relative_to(cgroup_root):
        return False
    try:
        return all(
            not tuple(path.read_text().split())
            for path in cgroup.rglob("cgroup.procs")
        )
    except OSError:
        return False


def _terminal_row(assignment: dict, status: str, evidence_path: str | None, **extra) -> dict:
    if status not in TERMINAL_STATUSES:
        raise RunnerBlocked(f"unrecognized terminal status: {status}")
    return {**assignment, "status": status, "evidence_path": evidence_path, **extra}


def _isolated_attempt_entry(connection, execute_attempt: Callable, args: tuple) -> None:
    if os.name == "posix":
        os.setsid()
    try:
        outcome = execute_attempt(*args)
        if not isinstance(outcome, dict):
            raise TypeError("attempt adapter must return a mapping")
        connection.send({"kind": "result", "value": outcome})
    except BaseException as error:
        try:
            connection.send({
                "kind": "error", "error_type": type(error).__name__,
                "reason": str(error),
            })
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


def _kill_process_tree(process, *, grace_seconds: float = 1.0) -> bool:
    if process.is_alive() and os.name == "posix":
        try:
            if os.getpgid(process.pid) == process.pid:
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except (ProcessLookupError, PermissionError):
            process.terminate()
    elif process.is_alive():
        process.terminate()
    process.join(timeout=grace_seconds)
    if process.is_alive():
        if os.name == "posix":
            try:
                if os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except (ProcessLookupError, PermissionError):
                process.kill()
        else:
            process.kill()
        process.join(timeout=2)
    return not process.is_alive()


def run_isolated_attempt(
    execute_attempt: Callable,
    args: tuple,
    *,
    deadline: float,
    cancel_event: threading.Event,
) -> dict:
    """Execute a picklable adapter in a killable process group."""
    if os.name != "posix":
        raise RunnerBlocked("registered attempts require Linux process-group cleanup")
    try:
        pickle.dumps((execute_attempt, args))
    except Exception as error:
        raise RunnerBlocked("attempt adapter and inputs must be process-serializable") from error
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_isolated_attempt_entry,
        args=(sender, execute_attempt, args),
        daemon=False,
    )
    process.start()
    sender.close()
    try:
        while True:
            if receiver.poll():
                try:
                    message = receiver.recv()
                except EOFError:
                    message = None
                process.join(timeout=0.5)
                if process.is_alive() and not _kill_process_tree(process):
                    return {
                        "kind": "error", "error_type": "WorkerCleanupFailed",
                        "reason": "attempt worker did not exit after returning",
                    }
                return message or {
                    "kind": "error", "error_type": "WorkerExited",
                    "reason": f"attempt worker exited with {process.exitcode}",
                }
            if not process.is_alive():
                return {
                    "kind": "error", "error_type": "WorkerExited",
                    "reason": f"attempt worker exited with {process.exitcode}",
                }
            if cancel_event.is_set() or time.monotonic() >= deadline:
                stopped = _kill_process_tree(process)
                if not stopped:
                    return {
                        "kind": "error", "error_type": "WorkerCleanupFailed",
                        "reason": "attempt process tree could not be stopped",
                    }
                return {
                    "kind": "interrupted",
                    "reason": "coordinator cancellation" if cancel_event.is_set()
                    else "attempt deadline exceeded",
                    "cleanup_verified": True,
                }
            time.sleep(0.025)
    finally:
        receiver.close()


def run_synthetic_dry_run(
    assignments: list[dict],
    execute_fixture: Callable[[dict, Path], dict],
    *,
    output_root: str | Path,
    max_workers: int = 4,
    budget: RunnerBudget = RunnerBudget(),
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Exercise scheduler logic on at most four injected synthetic fixtures."""
    budget.validate()
    if max_workers != MAX_WORKERS:
        raise RunnerBlocked("dry-run worker count must match the production cap")
    if not 1 <= len(assignments) <= MAX_WORKERS:
        raise RunnerBlocked("dry-run accepts one to four fixtures, never the registered matrix")
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    started = clock()
    results: dict[int, dict] = {}
    pending: dict[Future, tuple[int, dict, float]] = {}
    next_index = 0
    slot_seconds = 0.0
    attempts_started = 0
    cancelled = False
    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        while next_index < len(assignments) or pending:
            elapsed = clock() - started
            if elapsed >= budget.matrix_window_seconds or slot_seconds >= budget.slot_budget_seconds:
                for future, (index, assignment, _) in list(pending.items()):
                    if future.cancel():
                        results[index] = _terminal_row(
                            assignment, "NOT_RUN_BUDGET_EXHAUSTED", None,
                            reason="budget exhausted before fixture started",
                        )
                        pending.pop(future)
                while next_index < len(assignments):
                    assignment = assignments[next_index]
                    results[next_index] = _terminal_row(
                        assignment, "NOT_RUN_BUDGET_EXHAUSTED", None,
                        reason="budget exhausted before fixture started",
                    )
                    next_index += 1
                if not pending:
                    break
            while next_index < len(assignments) and len(pending) < MAX_WORKERS:
                assignment = assignments[next_index]
                future = pool.submit(
                    execute_fixture, assignment,
                    root / f"fixture-{next_index:02d}",
                )
                pending[future] = (next_index, assignment, clock())
                next_index += 1
            done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in done:
                index, assignment, began = pending.pop(future)
                slot_seconds += clock() - began
                try:
                    value = future.result()
                    status = value.get("status")
                    if status not in TERMINAL_STATUSES:
                        status = "ASSEMBLY_OUTPUT_INVALID"
                    evidence = value.get("evidence_path")
                    results[index] = _terminal_row(assignment, status, evidence)
                except AttemptInterrupted:
                    cancelled = True
                    results[index] = _terminal_row(
                        assignment, "ASSEMBLY_INTERRUPTED", None,
                        reason="operator cancellation",
                    )
                except BaseException as error:
                    results[index] = _terminal_row(
                        assignment, "ASSEMBLY_EXECUTION_FAILED", None,
                        error_type=type(error).__name__,
                    )
            if cancelled:
                for future, (index, assignment, _) in list(pending.items()):
                    if future.cancel():
                        results[index] = _terminal_row(
                            assignment, "INTERRUPTED_BUDGET", None,
                            reason="cancelled after operator interruption",
                        )
                        pending.pop(future)
                while next_index < len(assignments):
                    assignment = assignments[next_index]
                    results[next_index] = _terminal_row(
                        assignment, "NOT_RUN_WITH_BLOCKER", None,
                        reason="operator cancelled dry-run",
                    )
                    next_index += 1
    except KeyboardInterrupt:
        cancelled = True
        for future, (index, assignment, _) in list(pending.items()):
            if future.cancel():
                results[index] = _terminal_row(
                    assignment, "INTERRUPTED_BUDGET", None,
                    reason="runner cancelled",
                )
                pending.pop(future)
        while next_index < len(assignments):
            assignment = assignments[next_index]
            results[next_index] = _terminal_row(
                assignment, "NOT_RUN_WITH_BLOCKER", None,
                reason="runner cancelled",
            )
            next_index += 1
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
    statuses = [results[index] for index in range(len(assignments))]
    return {
        "schema": RUNNER_SCHEMA,
        "mode": "synthetic_dry_run",
        "status": "CANCELLED" if cancelled else "PASS",
        "registered_matrix_executed": False,
        "assignments_received": len(assignments),
        "max_workers": MAX_WORKERS,
        "attempt_timeout_seconds": ATTEMPT_TIMEOUT_SECONDS,
        "slot_seconds_consumed": slot_seconds,
        "results": statuses,
    }


def run_registered_matrix(
    design: dict,
    evaluator_manifest_path: str | Path,
    execute_attempt: Callable,
    *,
    authorization: dict,
    design_sha256: str,
    source_commit: str,
    source_root: str | Path,
    design_path: str | Path,
    tool_identity_sha256: str,
    expected_tools: dict,
    observed_tools: dict,
    public_root: str | Path,
    restricted_root: str | Path,
    budget: RunnerBudget = RunnerBudget(),
    clock: Callable[[], float] = time.monotonic,
) -> dict:
    """Coordinate the authorized registry; never called by tests or CI.

    Only the source-controlled M36 adapter class may perform registered work.
    It must consume authenticated seeds/parameters, use
    :func:`bounded_systemd_command`, and return separated evidence.
    """
    workflow_started = clock()
    budget.validate()
    if not callable(execute_attempt):
        raise RunnerBlocked("the condition-specific stage adapter is not provisioned")
    if not SHA256.fullmatch(design_sha256) or not SHA256.fullmatch(tool_identity_sha256):
        raise RunnerBlocked("design or tool identity digest is malformed")
    if len(source_commit) != 40 or any(c not in "0123456789abcdef" for c in source_commit):
        raise RunnerBlocked("source commit is malformed")
    source_root = Path(source_root).resolve()
    design_file = Path(design_path).resolve(strict=True)
    if not design_file.is_relative_to(source_root):
        raise RunnerBlocked("design file must be inside the authenticated source checkout")
    if hashlib.sha256(design_file.read_bytes()).hexdigest() != design_sha256:
        raise RunnerBlocked("design digest does not match the frozen design file")
    actual_commit = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    clean = subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if actual_commit != source_commit or clean:
        raise RunnerBlocked("source checkout is dirty or differs from the approved commit")
    verify_tool_identity(expected_tools, observed_tools)
    tool_digest = hashlib.sha256(
        canonical_json_bytes(expected_tools)
    ).hexdigest()
    if tool_digest != tool_identity_sha256:
        raise RunnerBlocked("tool identity digest does not match the pinned inventory")
    assert_isolated_storage(public_root, restricted_root)
    public = Path(public_root).resolve()
    restricted = Path(restricted_root).resolve()
    if not public.is_dir():
        raise RunnerBlocked("public evidence directory is not provisioned")
    if restricted.is_relative_to(source_root):
        raise RunnerBlocked("restricted evidence must not be stored in the source checkout")
    if any(public.iterdir()):
        raise RunnerBlocked("public evidence directory must be empty before execution")
    restricted_store = RestrictedEvidenceStore(
        restricted,
        source_root=source_root,
        public_root=public,
    )
    evaluator_manifest, evaluator_digest = restricted_store.load_manifest(
        evaluator_manifest_path
    )
    validate_evaluator_manifest(
        design, evaluator_manifest, design_sha256=design_sha256,
    )
    verify_execution_authorization(
        authorization,
        design_sha256=design_sha256,
        source_commit=source_commit,
        tool_identity_sha256=tool_identity_sha256,
        evaluator_manifest_sha256=evaluator_digest,
        budget=budget,
    )
    try:
        from .m36_adapters import M36Phase2BAttemptAdapter
    except ImportError as error:
        raise RunnerBlocked(
            "registered condition-specific M36 stage adapter is not implemented"
        ) from error
    if type(execute_attempt) is not M36Phase2BAttemptAdapter:
        raise RunnerBlocked(
            "registered matrix requires the source-controlled M36 stage adapter"
        )
    try:
        pickle.dumps(execute_attempt)
    except Exception as error:
        raise RunnerBlocked(
            "attempt adapter must be a process-serializable isolated worker"
        ) from error
    assignments = registered_assignments(design)
    private_rows = {
        assignment_key(row): row for row in evaluator_manifest["assignments"]
    }
    run_token = secrets.token_hex(12)
    mapping_path = restricted / f"m36-{run_token}-evaluation-map.json"
    mapping = []
    case_ids = {}
    for assignment in assignments:
        token = "case-" + secrets.token_hex(12)
        case_ids[assignment_key(assignment)] = token
        mapping.append({"analysis_case_id": token, **assignment})
    payload = canonical_json_bytes(mapping)
    mapping_digest = restricted_store.write_bytes(
        mapping_path.relative_to(restricted).as_posix(), payload,
    )
    manifest_by_key = private_rows
    matrix_started = clock()
    matrix_deadline = matrix_started + budget.matrix_window_seconds
    total_deadline = workflow_started + budget.total_budget_seconds
    rows = [None] * len(assignments)
    public_candidates: dict[int, dict[str, dict[str, str]]] = {}
    pending: dict[Future, tuple[int, dict, str, float]] = {}
    next_index = 0
    slot_seconds = 0.0
    attempts_started = 0
    cancelled = False
    cancel_event = threading.Event()
    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)

    def record_attempt_failure(token: str, event: dict) -> dict:
        attempt_relative = f"m36-{run_token}-{token}"
        partial_hashes = restricted_store.inventory_directory(attempt_relative)
        failure_digest = restricted_store.write_bytes(
            f"{attempt_relative}/failure.json",
            canonical_json_bytes({
                **event,
                "partial_files_sha256": partial_hashes,
            }) + b"\n",
        )
        return {
            "failure_evidence_sha256": failure_digest,
            "partial_sha256": partial_hashes,
        }

    try:
        while next_index < len(assignments) or pending:
            if cancelled:
                while next_index < len(assignments):
                    assignment = assignments[next_index]
                    rows[next_index] = {
                        "case_id": case_ids[assignment_key(assignment)],
                        "status": "NOT_RUN_WITH_BLOCKER",
                    }
                    next_index += 1
                if not pending:
                    break
            now = clock()
            if now >= matrix_deadline or now >= total_deadline:
                cancelled = True
                cancel_event.set()
                while next_index < len(assignments):
                    assignment = assignments[next_index]
                    rows[next_index] = {
                        "case_id": case_ids[assignment_key(assignment)],
                        "status": "NOT_RUN_BUDGET_EXHAUSTED",
                    }
                    next_index += 1
                if not pending:
                    break
            while (
                not cancelled
                and next_index < len(assignments)
                and len(pending) < MAX_WORKERS
                and slot_seconds + sum(clock() - item[3] for item in pending.values())
                    < budget.slot_budget_seconds
            ):
                assignment = assignments[next_index]
                key = assignment_key(assignment)
                token = case_ids[key]
                private_attempt = manifest_by_key[key]
                attempt_public = public / token
                attempt_restricted = restricted / f"m36-{run_token}-{token}"
                attempt_public.mkdir(mode=0o700)
                attempt_restricted.mkdir(mode=0o700)
                condition_state = private_attempt["condition_parameters"].get(
                    "execution_state", "READY"
                )
                if condition_state != "READY":
                    evidence = record_attempt_failure(token, {
                            "status": "NOT_RUN_WITH_BLOCKER",
                            "condition_state": condition_state,
                            "preregistered_condition": private_attempt[
                                "condition_parameters"
                            ]["preregistered_condition"],
                        })
                    rows[next_index] = {
                        "case_id": token,
                        "status": "NOT_RUN_WITH_BLOCKER",
                        **evidence,
                    }
                    next_index += 1
                    continue
                deadline = min(
                    clock() + budget.attempt_timeout_seconds,
                    matrix_deadline, total_deadline,
                )
                future = pool.submit(
                    run_isolated_attempt,
                    execute_attempt,
                    (
                        private_attempt, token, attempt_public,
                        attempt_restricted, deadline,
                    ),
                    deadline=deadline,
                    cancel_event=cancel_event,
                )
                pending[future] = (next_index, assignment, token, clock())
                next_index += 1
                attempts_started += 1
            if (
                next_index < len(assignments)
                and slot_seconds + sum(clock() - item[3] for item in pending.values())
                    >= budget.slot_budget_seconds
            ):
                cancelled = True
                cancel_event.set()
                while next_index < len(assignments):
                    assignment = assignments[next_index]
                    rows[next_index] = {
                        "case_id": case_ids[assignment_key(assignment)],
                        "status": "NOT_RUN_BUDGET_EXHAUSTED",
                    }
                    next_index += 1
            done, _ = wait(pending, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in done:
                index, assignment, token, began = pending.pop(future)
                elapsed = clock() - began
                slot_seconds += elapsed
                try:
                    message = future.result()
                    if not isinstance(message, dict):
                        raise RunnerBlocked("isolated attempt returned no result envelope")
                    if message.get("kind") == "interrupted":
                        status = (
                            "INTERRUPTED_BUDGET"
                            if "budget" in message.get("reason", "")
                            or "coordinator cancellation" in message.get("reason", "")
                            else "ASSEMBLY_INTERRUPTED"
                        )
                        evidence = record_attempt_failure(token, message)
                        rows[index] = {
                            "case_id": token, "status": status,
                            **evidence,
                            "elapsed_seconds": elapsed,
                        }
                        if message.get("error_type") == "WorkerCleanupFailed":
                            cancelled = True
                            cancel_event.set()
                        continue
                    if message.get("kind") == "error":
                        status = "ASSEMBLY_EXECUTION_FAILED"
                        evidence = record_attempt_failure(token, message)
                        rows[index] = {
                            "case_id": token, "status": status,
                            **evidence,
                            "elapsed_seconds": elapsed,
                        }
                        if message.get("error_type") == "WorkerCleanupFailed":
                            cancelled = True
                            cancel_event.set()
                        continue
                    if message.get("kind") != "result":
                        raise RunnerBlocked("isolated attempt result envelope is invalid")
                    outcome = message["value"]
                    status = outcome.get("status")
                    public_files = outcome.get("public_artifacts", {})
                    raw_files = outcome.get("restricted_artifacts", {})
                    provenance = {
                        "source_commit": source_commit,
                        "design_sha256": design_sha256,
                        "tool_identity_sha256": tool_identity_sha256,
                    }
                    if outcome.get("provenance") != provenance:
                        status = "INPUT_DIGEST_MISMATCH"
                    if clock() >= matrix_deadline or clock() >= total_deadline:
                        status = "INTERRUPTED_BUDGET"
                    elif status not in TERMINAL_STATUSES:
                        status = "ASSEMBLY_OUTPUT_INVALID"
                    if not isinstance(public_files, dict) or not isinstance(raw_files, dict):
                        status = "ASSEMBLY_OUTPUT_INVALID"
                        public_files, raw_files = {}, {}
                    input_files = outcome.get("input_artifacts", {})
                    declared_input_hashes = outcome.get("input_sha256", {})
                    try:
                        input_bytes, actual_input_hashes = verify_byte_artifacts(
                            input_files, declared_input_hashes, allow_empty=True,
                        )
                    except RunnerBlocked:
                        status = "INPUT_DIGEST_MISMATCH"
                        input_bytes, actual_input_hashes = {}, {}
                    for name, content in input_bytes.items():
                        try:
                            stored_digest = restricted_store.write_bytes(
                                f"m36-{run_token}-{token}/inputs/{name}", content,
                            )
                            if stored_digest != actual_input_hashes[name]:
                                status = "INPUT_DIGEST_MISMATCH"
                        except (OSError, RunnerBlocked, ValueError):
                            status = "INPUT_DIGEST_MISMATCH"
                    try:
                        public_bytes, computed_public_hashes = verify_byte_artifacts(
                            public_files, allow_empty=True,
                        )
                    except RunnerBlocked:
                        status = "ASSEMBLY_OUTPUT_INVALID"
                        public_bytes, computed_public_hashes = {}, {}
                    if raw_files:
                        stored_files = {}
                        for name, content in raw_files.items():
                            digest = restricted_store.write_bytes(
                                f"m36-{run_token}-{token}/raw/{name}", content,
                            )
                            stored_files[name] = digest
                        stored = {
                            "files": stored_files,
                            "raw_bytes_modified": False,
                        }
                    else:
                        stored = {"files": {}, "raw_bytes_modified": True}
                        status = "ASSEMBLY_OUTPUT_INVALID"
                    if stored["raw_bytes_modified"] is not False:
                        status = "ASSEMBLY_OUTPUT_INVALID"
                    if public_bytes:
                        forbidden = {
                            str(value) for value in (
                                assignment["block_id"], assignment["family_id"],
                                assignment["condition_id"], assignment["repeat_id"],
                                assignment["assembler_id"],
                                private_rows[assignment_key(assignment)]["split"],
                                private_rows[assignment_key(assignment)]["family_seed"],
                                private_rows[assignment_key(assignment)]["read_seed"],
                                *private_rows[assignment_key(assignment)]["condition_parameters"].keys(),
                                *private_rows[assignment_key(assignment)]["condition_parameters"].values(),
                            )
                        }
                        validate_blinded_artifacts(
                            public_bytes, case_ids={token},
                            forbidden_values=forbidden,
                        )
                        candidate_hashes = {}
                        for name, content in public_bytes.items():
                            relative = f"m36-{run_token}-{token}/public-candidate/{name}"
                            digest = restricted_store.write_bytes(relative, content)
                            if digest != computed_public_hashes[name]:
                                raise RunnerBlocked(
                                    "candidate output bytes changed during restricted storage"
                                )
                            candidate_hashes[name] = {
                                "path": relative, "sha256": digest,
                            }
                        public_candidates[index] = candidate_hashes
                    else:
                        candidate_hashes = {}
                    resource_proofs = outcome.get("assembly_resource_proofs", [])
                    assembly_started = outcome.get("assembly_started") is True
                    if assembly_started and (
                        not isinstance(resource_proofs, list) or not resource_proofs
                        or any(
                            not isinstance(proof, dict)
                            or proof.get("status") != "PASS"
                            or not proof.get("cgroup")
                            or proof.get("child_processes_inherit_cgroup") is not True
                            or not isinstance(proof.get("cpu_max"), list)
                            or len(proof["cpu_max"]) != 2
                            or any(type(value) is not int or value <= 0
                                   for value in proof["cpu_max"])
                            or proof["cpu_max"][0] > proof["cpu_max"][1]
                            or type(proof.get("memory_max_bytes")) is not int
                            or proof["memory_max_bytes"] > MEMORY_MAX_BYTES
                            for proof in resource_proofs
                        )
                    ):
                        status = "ASSEMBLY_OUTPUT_INVALID"
                    if status == "COMPLETE" and (
                        not assembly_started or not public_bytes
                        or not actual_input_hashes
                    ):
                        status = "INPUT_DIGEST_MISMATCH"
                    rows[index] = {
                        "case_id": token, "status": status,
                        "elapsed_seconds": elapsed,
                        "provenance": provenance,
                        "input_sha256": actual_input_hashes,
                        "assembly_resource_proofs": resource_proofs,
                        "public_artifacts": [],
                        "restricted_artifacts": sorted(
                            [f"inputs/{name}" for name in actual_input_hashes]
                            + [f"raw/{name}" for name in stored["files"]]
                            + [f"public-candidate/{name}" for name in candidate_hashes]
                        ),
                        "restricted_sha256": {
                            **{
                                f"inputs/{name}": digest
                                for name, digest in actual_input_hashes.items()
                            },
                            **{
                                f"raw/{name}": digest
                                for name, digest in stored["files"].items()
                            },
                            **{
                                f"public-candidate/{name}": item["sha256"]
                                for name, item in candidate_hashes.items()
                            },
                        },
                        "public_sha256": {},
                    }
                except AttemptInterrupted:
                    cancelled = True
                    cancel_event.set()
                    rows[index] = {"case_id": token, "status": "ASSEMBLY_INTERRUPTED"}
                except (RunnerBlocked, ValueError) as error:
                    cancelled = True
                    cancel_event.set()
                    evidence = record_attempt_failure(token, {
                            "error_type": type(error).__name__,
                            "reason": str(error),
                        })
                    rows[index] = {
                        "case_id": token, "status": "ASSEMBLY_OUTPUT_INVALID",
                        **evidence,
                    }
                except BaseException as error:
                    evidence = record_attempt_failure(token, {
                            "error_type": type(error).__name__,
                            "reason": str(error),
                        })
                    rows[index] = {
                        "case_id": token, "status": "ASSEMBLY_EXECUTION_FAILED",
                        **evidence,
                    }
            if cancelled and not pending:
                while next_index < len(assignments):
                    assignment = assignments[next_index]
                    rows[next_index] = {
                        "case_id": case_ids[assignment_key(assignment)],
                        "status": "NOT_RUN_BUDGET_EXHAUSTED",
                    }
                    next_index += 1
    except KeyboardInterrupt:
        cancelled = True
        cancel_event.set()
        for future, (index, assignment, token, _) in list(pending.items()):
            if future.cancel():
                rows[index] = {"case_id": token, "status": "INTERRUPTED_BUDGET"}
                pending.pop(future)
        while next_index < len(assignments):
            assignment = assignments[next_index]
            rows[next_index] = {
                "case_id": case_ids[assignment_key(assignment)],
                "status": "NOT_RUN_WITH_BLOCKER",
            }
            next_index += 1
    finally:
        if cancelled:
            cancel_event.set()
        pool.shutdown(wait=True, cancel_futures=True)
    for index, (assignment, row) in enumerate(zip(assignments, rows)):
        if row is None:
            token = case_ids[assignment_key(assignment)]
            status = "INTERRUPTED_BUDGET" if cancelled else "ASSEMBLY_EXECUTION_FAILED"
            failure_digest = restricted_store.write_bytes(
                f"m36-{run_token}-{token}/failure.json",
                canonical_json_bytes({
                    "reason": "coordinator ended without a worker terminal response",
                    "status": status,
                }) + b"\n",
            )
            row = {
                "case_id": token, "status": status,
                "failure_evidence_sha256": failure_digest,
            }
            rows[index] = row
    input_mismatches = validate_input_identity(assignments, rows)
    for index, reason in input_mismatches.items():
        token = rows[index]["case_id"]
        evidence_path = f"m36-{run_token}-{token}/input-identity.json"
        digest = restricted_store.write_bytes(
            evidence_path,
            canonical_json_bytes({
                "status": "INPUT_DIGEST_MISMATCH",
                "reason": reason,
                "input_sha256": rows[index].get("input_sha256", {}),
            }) + b"\n",
        )
        rows[index]["status"] = "INPUT_DIGEST_MISMATCH"
        rows[index]["failure_evidence_sha256"] = digest
    for index, row in enumerate(rows):
        token = row["case_id"]
        candidates = public_candidates.get(index, {})
        if row["status"] == "COMPLETE" and not candidates:
            row["status"] = "ASSEMBLY_OUTPUT_INVALID"
            row.update(record_attempt_failure(token, {
                "reason": "completed attempt has no validated public output candidate",
            }))
        if row["status"] == "COMPLETE":
            written = []
            public_hashes = {}
            try:
                for name, candidate in candidates.items():
                    content = restricted_store.read_bytes(
                        candidate["path"], expected_sha256=candidate["sha256"],
                    )
                    public_hashes[name] = write_public_artifact(
                        public, token, name, content, candidate["sha256"],
                    )
                    written.append(public / token / name)
                row["public_artifacts"] = sorted(public_hashes)
                row["public_sha256"] = public_hashes
            except (OSError, RunnerBlocked, ValueError) as error:
                for path in written:
                    path.unlink(missing_ok=True)
                row["status"] = "ASSEMBLY_OUTPUT_INVALID"
                row.update(record_attempt_failure(token, {
                    "error_type": type(error).__name__,
                    "reason": str(error),
                }))
        restricted_store.write_terminal_record(
            token,
            {
                "case_id": token,
                "status": row["status"],
                "evidence_sha256": row.get("failure_evidence_sha256"),
                "restricted_sha256": row.get("restricted_sha256", {}),
                "partial_sha256": row.get("partial_sha256", {}),
                "public_sha256": row.get("public_sha256", {}),
            },
        )
    if (
        len(rows) != len(assignments)
        or any(row is None or row.get("status") not in TERMINAL_STATUSES for row in rows)
    ):
        raise RunnerBlocked("terminal accounting does not cover every registered assignment")
    status_counts = {
        status: sum(row is not None and row["status"] == status for row in rows)
        for status in sorted(TERMINAL_STATUSES)
    }
    if sum(status_counts.values()) != len(assignments):
        raise RunnerBlocked("each assignment must have exactly one terminal status")
    report = {
        "schema": RUNNER_SCHEMA, "run_token": run_token,
        "status": "CANCELLED" if cancelled else "COMPLETE",
        "design_sha256": design_sha256, "source_commit": source_commit,
        "tool_identity_sha256": tool_identity_sha256,
        "restricted_mapping_sha256": mapping_digest,
        "evaluator_manifest_sha256": evaluator_digest,
        "registered_assignment_count": len(assignments),
        "attempts_started": attempts_started,
        "terminal_result_count": len([row for row in rows if row is not None]),
        "registered_matrix_executed": attempts_started > 0,
        "slot_seconds_consumed": slot_seconds,
        "matrix_window_seconds": budget.matrix_window_seconds,
        "total_workflow_budget_seconds": budget.total_budget_seconds,
        "slot_budget_seconds": budget.slot_budget_seconds,
        "maximum_workers": MAX_WORKERS,
        "automatic_retries": False,
        "elapsed_seconds": clock() - workflow_started,
        "status_counts": status_counts,
        "results": rows,
    }
    report_path = public / "m36_runner_report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    inventory = validate_public_inventory(public, restricted_paths=set())
    (public / "public_evidence_manifest.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    )
    return report


def validate_public_inventory(
    public_root: str | Path, *, restricted_paths: set[str],
) -> dict:
    """Reject accidental sidecar/raw path inclusion in a public evidence set."""
    root = Path(public_root).resolve()
    paths = sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())
    if set(paths) & restricted_paths:
        raise RunnerBlocked("restricted sidecar or raw evidence entered public artifacts")
    evidence = [{
        "path": name,
        "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
    } for name in paths]
    verified = verify_evidence_files({"evidence_files": evidence}, root=root)
    if verified["status"] != "PASS":
        raise RunnerBlocked("public evidence inventory failed digest verification")
    return {"status": "PASS", "files": evidence}

