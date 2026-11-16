"""Fail-closed coordinator for the M36 synthetic Phase 2B matrix.

This module does not launch work at import time. Real matrix execution requires
an independently verified, commit-scoped authorization and evaluator manifest.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from typing import Callable

from .m36_preparation import (
    SHA256,
    TERMINAL_STATUSES,
    preserve_restricted_raw_evidence,
    registered_assignments,
    validate_blinded_artifacts,
    verify_evidence_files,
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


class RunnerBlocked(RuntimeError):
    """Raised when an execution prerequisite is missing or inconsistent."""


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


def validate_evaluator_manifest(design: dict, manifest: dict) -> dict:
    """Validate the private per-attempt seed/condition map without exposing it."""
    if manifest.get("schema") != "m36-evaluator-execution-manifest-v1":
        raise RunnerBlocked("missing or unsupported evaluator execution manifest")
    expected = {assignment_key(row) for row in registered_assignments(design)}
    rows = manifest.get("assignments")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise RunnerBlocked("evaluator manifest does not cover all registered assignments")
    observed = []
    family_seeds: dict[str, int] = {}
    family_splits: dict[str, str] = {}
    read_seeds: dict[tuple[str, ...], int] = {}
    for row in rows:
        key = assignment_key(row)
        if (
            type(row.get("family_seed")) is not int
            or type(row.get("read_seed")) is not int
            or row["family_seed"] < 0 or row["read_seed"] < 0
            or not isinstance(row.get("condition_parameters"), dict)
            or not row["condition_parameters"]
            or row.get("split") not in {"development", "tuning", "held_out"}
        ):
            raise RunnerBlocked("evaluator entry lacks frozen seeds, split, or parameters")
        family = row["family_id"]
        prior_seed = family_seeds.setdefault(family, row["family_seed"])
        if prior_seed != row["family_seed"]:
            raise RunnerBlocked("family sequence seed changes across assignments")
        prior_split = family_splits.setdefault(family, row["split"])
        if prior_split != row["split"]:
            raise RunnerBlocked("family split changes across assignments")
        read_seeds[key] = row["read_seed"]
        observed.append(key)
    if len(set(observed)) != len(expected) or set(observed) != expected:
        raise RunnerBlocked("evaluator manifest contains duplicate or unregistered assignments")
    split_counts = {
        split: sum(value == split for value in family_splits.values())
        for split in ("development", "tuning", "held_out")
    }
    if split_counts != {"development": 4, "tuning": 4, "held_out": 4}:
        raise RunnerBlocked("family splits do not match the frozen 4/4/4 allocation")
    if len(set(family_seeds.values())) != len(family_seeds):
        raise RunnerBlocked("independent families must have distinct family seeds")
    if any(row["family_seed"] == row["read_seed"] for row in rows):
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
    }


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
    signature_verifier: Callable[[dict], bool] | None = None,
) -> None:
    """Check scoped approval fields and require a trusted signature verifier."""
    if not callable(signature_verifier) or signature_verifier(authorization) is not True:
        raise RunnerBlocked("independent authorization signature is not verified")
    expected = {
        "design_sha256": design_sha256,
        "source_commit": source_commit,
        "tool_identity_sha256": tool_identity_sha256,
        "evaluator_manifest_sha256": evaluator_manifest_sha256,
        "scope": "m36-synthetic-520-assignment-matrix",
    }
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise RunnerBlocked("authorization is not bound to this design, commit, tools, and scope")


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
        return {
            "status": outcome, "returncode": result.returncode,
            "stdout": "\n".join(lines), "stderr": result.stderr,
            "command": command, "service_unit": unit,
            "enforcement_evidence": proof,
            "resource_limits": {
                "cpu_quota": "100%", "memory_max_bytes": memory_max_bytes,
                "timeout_seconds": timeout_seconds,
                "children_inherit_cgroup": True,
            },
            "elapsed_seconds": time.monotonic() - started,
        }
    except subprocess.TimeoutExpired as error:
        return {
            "status": "ASSEMBLY_INTERRUPTED", "returncode": None,
            "stdout": error.stdout or "", "stderr": error.stderr or "",
            "command": command, "service_unit": unit,
            "resource_limits": {
                "cpu_quota": "100%", "memory_max_bytes": memory_max_bytes,
                "timeout_seconds": timeout_seconds,
                "children_inherit_cgroup": True,
            },
            "elapsed_seconds": time.monotonic() - started,
        }
    except KeyboardInterrupt:
        raise AttemptInterrupted("operator cancelled the attempt")


def _terminal_row(assignment: dict, status: str, evidence_path: str | None, **extra) -> dict:
    if status not in TERMINAL_STATUSES:
        raise RunnerBlocked(f"unrecognized terminal status: {status}")
    return {**assignment, "status": status, "evidence_path": evidence_path, **extra}


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
    evaluator_manifest: dict,
    execute_attempt: Callable,
    *,
    authorization: dict,
    signature_verifier: Callable[[dict], bool] | None,
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

    The injected stage adapter must consume the authenticated per-assignment
    seeds and condition parameters, invoke each assembly through
    :func:`bounded_systemd_command`, and return separate public and restricted
    evidence. An operator signature verifier is mandatory.
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
    validate_evaluator_manifest(design, evaluator_manifest)
    verify_tool_identity(expected_tools, observed_tools)
    tool_digest = hashlib.sha256(
        json.dumps(expected_tools, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if tool_digest != tool_identity_sha256:
        raise RunnerBlocked("tool identity digest does not match the pinned inventory")
    evaluator_digest = hashlib.sha256(
        json.dumps(
            evaluator_manifest, sort_keys=True, separators=(",", ":"),
        ).encode()
    ).hexdigest()
    verify_execution_authorization(
        authorization,
        design_sha256=design_sha256,
        source_commit=source_commit,
        tool_identity_sha256=tool_identity_sha256,
        evaluator_manifest_sha256=evaluator_digest,
        signature_verifier=signature_verifier,
    )
    assert_isolated_storage(public_root, restricted_root)
    public = Path(public_root).resolve()
    restricted = Path(restricted_root).resolve()
    if not public.is_dir():
        raise RunnerBlocked("public evidence directory is not provisioned")
    if restricted.is_relative_to(source_root):
        raise RunnerBlocked("restricted evidence must not be stored in the source checkout")
    if any(public.iterdir()):
        raise RunnerBlocked("public evidence directory must be empty before execution")
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
    payload = json.dumps(mapping, sort_keys=True, separators=(",", ":")).encode()
    fd = os.open(mapping_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
    manifest_by_key = private_rows
    matrix_started = clock()
    matrix_deadline = matrix_started + budget.matrix_window_seconds
    total_deadline = workflow_started + budget.total_budget_seconds
    rows = [None] * len(assignments)
    pending: dict[Future, tuple[int, dict, str, float]] = {}
    next_index = 0
    slot_seconds = 0.0
    attempts_started = 0
    cancelled = False
    pool = ThreadPoolExecutor(max_workers=MAX_WORKERS)
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
                deadline = min(
                    clock() + budget.attempt_timeout_seconds,
                    matrix_deadline, total_deadline,
                )
                future = pool.submit(
                    execute_attempt, private_attempt, token,
                    attempt_public, attempt_restricted, deadline,
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
                    outcome = future.result()
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
                    if raw_files:
                        stored = preserve_restricted_raw_evidence(
                            restricted / f"m36-{run_token}-{token}" / "raw",
                            raw_files,
                        )
                    else:
                        stored = {"files": {}, "raw_bytes_modified": True}
                        status = "ASSEMBLY_OUTPUT_INVALID"
                    if stored["raw_bytes_modified"] is not False:
                        status = "ASSEMBLY_OUTPUT_INVALID"
                    if public_files:
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
                            public_files, case_ids={token},
                            forbidden_values=forbidden,
                        )
                        for name, content in public_files.items():
                            target = (public / token / name).resolve()
                            if not target.is_relative_to((public / token).resolve()):
                                raise RunnerBlocked("public attempt output escaped its directory")
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_bytes(
                                content if isinstance(content, bytes)
                                else str(content).encode("utf-8")
                            )
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
                        not assembly_started or not public_files
                        or not isinstance(outcome.get("input_sha256"), dict)
                        or not outcome["input_sha256"]
                        or any(not SHA256.fullmatch(str(value))
                               for value in outcome["input_sha256"].values())
                    ):
                        status = "INPUT_DIGEST_MISMATCH"
                    rows[index] = {
                        "case_id": token, "status": status,
                        "elapsed_seconds": elapsed,
                        "provenance": provenance,
                        "input_sha256": outcome.get("input_sha256"),
                        "assembly_resource_proofs": resource_proofs,
                        "public_artifacts": sorted(public_files),
                        "restricted_artifacts": sorted(stored["files"]),
                        "public_sha256": {
                            name: hashlib.sha256(
                                (public_files[name] if isinstance(public_files[name], bytes)
                                 else str(public_files[name]).encode("utf-8"))
                            ).hexdigest()
                            for name in sorted(public_files)
                        },
                    }
                except AttemptInterrupted:
                    cancelled = True
                    rows[index] = {"case_id": token, "status": "ASSEMBLY_INTERRUPTED"}
                except (RunnerBlocked, ValueError):
                    cancelled = True
                    rows[index] = {"case_id": token, "status": "ASSEMBLY_OUTPUT_INVALID"}
                except BaseException:
                    rows[index] = {"case_id": token, "status": "ASSEMBLY_EXECUTION_FAILED"}
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
        pool.shutdown(wait=True, cancel_futures=True)
    status_counts = {
        status: sum(row is not None and row["status"] == status for row in rows)
        for status in sorted(TERMINAL_STATUSES)
    }
    report = {
        "schema": RUNNER_SCHEMA, "run_token": run_token,
        "status": "CANCELLED" if cancelled else "COMPLETE",
        "design_sha256": design_sha256, "source_commit": source_commit,
        "tool_identity_sha256": tool_identity_sha256,
        "restricted_mapping_sha256": hashlib.sha256(payload).hexdigest(),
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

