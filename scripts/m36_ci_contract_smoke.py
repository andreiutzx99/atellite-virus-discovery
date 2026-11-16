#!/usr/bin/env python3
"""Run only bounded, synthetic M36 tool-contract checks under cgroup v2."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import grp
import re
import subprocess
import sys
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.test_tadpole_runtime import (  # noqa: E402
    ARCHIVE_SHA256,
    COMMIT as TADPOLE_COMMIT,
    PROJECT,
    run as run_tadpole,
)

MEMORY_MAX_BYTES = 4 * 1024**3
ATTEMPT_TIMEOUT_SECONDS = 180
SERVICE_TIMEOUT_SECONDS = 240


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_fasta(path: Path) -> str:
    sequences = []
    current = []
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith(">"):
            if current:
                sequences.append("".join(current).upper())
                current = []
        elif line.strip():
            current.append(line.strip())
    if current:
        sequences.append("".join(current).upper())
    if len(sequences) != 1:
        raise RuntimeError("synthetic assembly must contain exactly one contig")
    return sequences[0]


def read_fastq(path: Path) -> list[tuple[str, str]]:
    payload = path.read_bytes()
    if path.name.endswith(".gz"):
        payload = gzip.decompress(payload)
    rows = payload.decode("ascii").splitlines()
    if not rows or len(rows) % 4:
        raise RuntimeError("synthetic FASTQ is malformed or empty")
    result = []
    for index in range(0, len(rows), 4):
        header, sequence, plus, quality = rows[index:index + 4]
        if not header.startswith("@") or not plus.startswith("+") or len(sequence) != len(quality):
            raise RuntimeError("synthetic FASTQ record failed structural validation")
        result.append((header[1:].split()[0], sequence.upper()))
    return result


def validate_actual_read_support(output: Path, assembler: str, paired: bool) -> dict:
    from satellite_discovery.m36_preparation import (
        _sha,
        validate_truth_support_crosswalk,
    )

    truth = read_fasta(output / "truth.fasta")
    contig = read_fasta(output / "contigs.fasta")
    fastq_name = "reads_1.fastq.gz" if assembler == "spades" else "reads.fastq"
    records = read_fastq(output / fastq_name)
    supported_reads = {}
    ledger = {}
    placements = []
    for read_id, sequence in records:
        match = re.fullmatch(r"fixture_[0-9]+_([0-9]+)(?:/1)?", read_id)
        if not match:
            raise RuntimeError("synthetic read ID does not encode its fixture origin")
        start = int(match.group(1))
        end = start + len(sequence)
        if truth[start:end] != sequence:
            raise RuntimeError("generated synthetic read does not match its truth interval")
        contig_start = contig.find(sequence)
        strand = "+"
        if contig_start < 0:
            reverse = sequence.translate(str.maketrans("ACGTN", "TGCAN"))[::-1]
            contig_start = contig.find(reverse)
            strand = "-"
        if contig_start < 0:
            continue
        supported_reads[read_id] = sequence
        ledger[read_id] = {
            "source_role": "target_truth",
            "source_interval": [start, end],
            "source_record_sha256": _sha(truth.encode("ascii")),
            "source_sequence_sha256": _sha(truth[start:end].encode("ascii")),
        }
        placements.append({
            "read_id": read_id, "contig_id": "contig-1",
            "start": contig_start, "cigar": f"{len(sequence)}=", "strand": strand,
        })
    if not supported_reads:
        raise RuntimeError("assembled contig has no exact synthetic read placements")
    evidence = {
        "supported_read_ids": list(supported_reads),
        "supported_contig_ids": ["contig-1"],
        "supported_read_sha256": {
            key: _sha(value.encode("ascii"))
            for key, value in supported_reads.items()
        },
        "supported_contig_sha256": {
            "contig-1": _sha(contig.encode("ascii")),
        },
        "read_placements": placements,
    }
    result = validate_truth_support_crosswalk(
        truth_sequence=truth,
        read_sequences=supported_reads,
        placement_ledger={"read_provenance": ledger},
        contigs={"contig-1": contig},
        support_evidence=evidence,
    )
    if result.get("support") != "READ_SUPPORTED_ASSEMBLY":
        raise RuntimeError("actual synthetic read placements did not validate")
    result.update(
        input_read_count=len(records),
        supported_read_count=len(supported_reads),
        paired_input=paired,
        support_evidence=evidence,
    )
    return result


def read_cgroup_limits() -> dict:
    """Read kernel-enforced cgroup v2 limits for this process."""
    membership = Path("/proc/self/cgroup").read_text(encoding="ascii").splitlines()
    line = next((row for row in membership if row.startswith("0::")), None)
    if line is None:
        raise RuntimeError("process is not in a unified cgroup v2 hierarchy")
    relative = line.split("::", 1)[1].lstrip("/")
    cgroup = Path("/sys/fs/cgroup") / relative
    cpu_values = (cgroup / "cpu.max").read_text(encoding="ascii").split()
    if len(cpu_values) != 2 or cpu_values[0] == "max":
        raise RuntimeError("cgroup CPU quota is missing or unlimited")
    quota, period = map(int, cpu_values)
    memory_value = (cgroup / "memory.max").read_text(encoding="ascii").strip()
    if memory_value == "max":
        raise RuntimeError("cgroup memory limit is unlimited")
    memory_max = int(memory_value)
    if quota <= 0 or period <= 0 or quota * 1 > period:
        raise RuntimeError("cgroup permits more than one CPU per attempt")
    if memory_max > MEMORY_MAX_BYTES:
        raise RuntimeError("cgroup memory limit exceeds the approved smoke budget")

    child = subprocess.run(
        [
            sys.executable, "-c",
            "from pathlib import Path; print(next(x for x in "
            "Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::')))",
        ],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    if child != line:
        raise RuntimeError("a child process escaped the attempt cgroup")
    return {
        "status": "PASS",
        "mechanism": "systemd transient service with cgroup-v2 CPUQuota and MemoryMax",
        "cgroup_v2_path": "/" + relative,
        "cpu_max": f"{quota} {period}",
        "max_vcpus": quota / period,
        "memory_max_bytes": memory_max,
        "child_process_inherited_cgroup": True,
    }


def provision_tadpole() -> dict:
    """Download and verify only the already-pinned BBTools archive/runtime."""
    tools = ROOT / ".tools"
    tools.mkdir(exist_ok=True)
    archive = tools / "BBTools-40.01.zip"
    if not archive.exists():
        url = f"https://codeload.github.com/bbushnell/BBTools/zip/{TADPOLE_COMMIT}"
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = response.read(40_000_001)
        if len(payload) > 40_000_000:
            raise RuntimeError("pinned Tadpole archive exceeded the download limit")
        archive.write_bytes(payload)
    if sha256(archive) != ARCHIVE_SHA256:
        raise RuntimeError("pinned Tadpole archive SHA-256 mismatch")
    runtime = tools / "bbtools-40.01"
    prefix = f"BBTools-{TADPOLE_COMMIT}/current/"
    classpath = runtime / f"BBTools-{TADPOLE_COMMIT}" / "current"
    if not runtime.exists():
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if sum(row.file_size for row in members) > 200_000_000:
                raise RuntimeError("pinned Tadpole runtime exceeds its extraction budget")
            if any(not (runtime / row.filename).resolve().is_relative_to(runtime.resolve())
                   for row in members):
                raise RuntimeError("pinned Tadpole archive contains an unsafe path")
            bundle.extractall(runtime)
    members = []
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not member.filename.startswith(prefix) or member.is_dir():
                continue
            installed = (runtime / member.filename).resolve()
            if not installed.is_relative_to(classpath.resolve()) or not installed.is_file():
                raise RuntimeError("pinned Tadpole runtime file is missing or unsafe")
            if sha256(installed) != hashlib.sha256(bundle.read(member)).hexdigest():
                raise RuntimeError("pinned Tadpole runtime file digest mismatch")
            members.append(member.filename)
    if not members:
        raise RuntimeError("pinned Tadpole archive contains no runtime files")
    return {
        "archive_sha256": sha256(archive),
        "pinned_archive_sha256": ARCHIVE_SHA256,
        "runtime_file_count": len(members),
        "runtime_tree_sha256": hashlib.sha256(
            "\n".join(
                f"{name} {sha256(runtime / name)}" for name in sorted(members)
            ).encode("utf-8")
        ).hexdigest(),
    }


def inspect_spades_package() -> dict:
    version = subprocess.run(
        ["dpkg-query", "-W", "-f=${Version}", "spades"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout.strip()
    listing = subprocess.run(
        ["dpkg-query", "-L", "spades"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout.splitlines()
    files = []
    for name in listing:
        path = Path(name)
        if path.is_file():
            files.append((name, sha256(path)))
    if not version or not files:
        raise RuntimeError("SPAdes package version or installed file inventory is unavailable")
    return {
        "package_version": version,
        "installed_file_count": len(files),
        "runtime_tree_sha256": hashlib.sha256(
            "\n".join(f"{name} {digest}" for name, digest in sorted(files)).encode("utf-8")
        ).hexdigest(),
    }


def attempt(kind: str, paired: bool, output: Path) -> dict:
    limits = read_cgroup_limits()
    started = time.monotonic()
    if kind == "spades":
        from satellite_discovery.artificial_spades import run as run_spades

        run_spades(output, paired)
        report = json.loads((output / "diagnostic.json").read_text(encoding="utf-8"))
        if report.get("status") != "passed":
            raise RuntimeError("SPAdes synthetic compatibility smoke failed")
        version = report.get("version")
        executable = report.get("executable", {})
        tool = {
            "name": "spades",
            "version_output": version,
            "executable_path": executable.get("path"),
            "executable_sha256": executable.get("sha256"),
            "parameters": report.get("command"),
            "resource_requirements": report.get("limits"),
            "test_result": report,
        }
    elif kind == "tadpole":
        if not run_tadpole(output, paired):
            raise RuntimeError("Tadpole synthetic compatibility smoke failed")
        report = json.loads((output / "test_result.json").read_text(encoding="utf-8"))
        from satellite_discovery.m36_preparation import inspect_assembler_provenance

        runtime = inspect_assembler_provenance()["tools"]["tadpole"]
        assembly_log = (output / "assembly.log").read_text(
            encoding="utf-8", errors="replace"
        )
        version_lines = [
            line.strip() for line in assembly_log.splitlines()
            if "version" in line.casefold()
        ]
        tool = {
            "name": "tadpole",
            "version_output": version_lines[:10],
            "runtime_version": runtime.get("version"),
            "java_version": report.get("java_version"),
            "archive_sha256": report.get("archive_sha256"),
            "runtime_sha256": runtime.get("runtime_sha256"),
            "parameters": report.get("command"),
            "resource_requirements": report.get("limits"),
            "test_result": report,
        }
    else:
        raise ValueError(f"unsupported assembler: {kind}")
    if tool["test_result"].get("status") != "passed":
        raise RuntimeError(f"{kind} did not report a passing smoke")
    support = validate_actual_read_support(output, kind, paired)
    support_path = output / "read_support.json"
    support_path.write_text(
        json.dumps(support, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    files = {}
    for path in sorted(output.rglob("*")):
        if path.is_file():
            files[path.relative_to(output).as_posix()] = sha256(path)
    (output / "evidence_manifest.json").write_text(
        json.dumps(
            {
                "schema": "m36-assembler-contract-evidence-manifest-v1",
                "assembler": kind,
                "layout": "paired" if paired else "single",
                "files": files,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    return {
        "assembler": kind,
        "layout": "paired" if paired else "single",
        "status": "PASS",
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "resource_enforcement": limits,
        "tool": tool,
        "read_support": support,
        "evidence_files": files,
    }


def run_bounded_attempt(kind: str, paired: bool, output: Path, report_path: Path) -> dict:
    unit = f"m36-smoke-{kind}-{'paired' if paired else 'single'}-{os.getpid()}"
    command = [
        "sudo", "systemd-run", "--quiet", "--wait", "--pipe", "--collect",
        f"--unit={unit}",
        "--property=Type=exec",
        "--property=CPUQuota=100%",
        f"--property=MemoryMax={MEMORY_MAX_BYTES}",
        "--property=TasksMax=512",
        f"--property=RuntimeMaxSec={SERVICE_TIMEOUT_SECONDS}s",
        f"--working-directory={ROOT}",
        f"--uid={os.environ.get('USER', 'runner')}",
        f"--gid={grp.getgrgid(os.getgid()).gr_name}",
        sys.executable, str(Path(__file__).resolve()),
        "--attempt", kind, "--output", str(output),
    ]
    if paired:
        command.append("--paired")
    started = time.monotonic()
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=SERVICE_TIMEOUT_SECONDS + 30,
    )
    report_path.write_text(
        json.dumps(
            {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "assembly_attempt_timeout_seconds": ATTEMPT_TIMEOUT_SECONDS,
                "cgroup_service_timeout_seconds": SERVICE_TIMEOUT_SECONDS,
            },
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{kind} {'paired' if paired else 'single'} cgroup smoke failed; "
            f"see {report_path}"
        )
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeError("bounded smoke did not return machine-readable evidence") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", choices=("spades", "tadpole"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--paired", action="store_true")
    args = parser.parse_args()
    if args.attempt:
        result = attempt(args.attempt, args.paired, args.output)
        print(json.dumps(result, sort_keys=True))
        return 0

    args.output.mkdir(parents=True, exist_ok=True)
    evidence = {
        "schema": "m36-phase2a-ci-contract-smoke-v1",
        "source_commit": os.environ.get("GITHUB_SHA"),
        "actions_run_id": os.environ.get("GITHUB_RUN_ID"),
        "actions_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "host": {
            "platform": sys.platform,
            "kernel": os.uname().release if hasattr(os, "uname") else None,
            "cgroup_v2_available": Path("/sys/fs/cgroup/cgroup.controllers").is_file(),
        },
        "spades_package": inspect_spades_package(),
        "design_budget_compatibility": {
            "max_concurrent_attempts": 4,
            "attempt_timeout_seconds": ATTEMPT_TIMEOUT_SECONDS,
            "matrix_slot_hours": 520 * ATTEMPT_TIMEOUT_SECONDS / 3600,
            "wall_time_hours_at_four_workers": (
                520 * ATTEMPT_TIMEOUT_SECONDS / 3600 / 4
            ),
            "setup_and_teardown_reserve_hours": 0.75,
            "validation_reserve_hours": 0.75,
            "total_wall_budget_hours": 8,
            "within_total_wall_budget": (
                520 * ATTEMPT_TIMEOUT_SECONDS / 3600 / 4 + 1.5 <= 8
            ),
        },
        "assemblies_executed": False,
        "registered_matrix_executed": False,
    }
    try:
        from satellite_discovery.m36_preparation import inspect_assembler_provenance

        evidence["tadpole_provisioning"] = provision_tadpole()
        evidence["assembler_provenance"] = inspect_assembler_provenance()
        if evidence["assembler_provenance"].get("status") != "PASS":
            raise RuntimeError("installed SPAdes/Tadpole identity did not pass verification")
        for assembler in ("spades", "tadpole"):
            for paired, layout in ((False, "single"), (True, "paired")):
                destination = args.output / assembler / layout
                destination.parent.mkdir(parents=True, exist_ok=True)
                evidence.setdefault("smokes", []).append(
                    run_bounded_attempt(
                        assembler, paired, destination,
                        args.output / assembler / f"{layout}-launcher.json",
                    )
                )
        if len(evidence.get("smokes", [])) != 4:
            raise RuntimeError("all four synthetic compatibility smokes are required")
        evidence["status"] = "PASS"
    except Exception as error:
        evidence["status"] = "BLOCKED"
        evidence["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        evidence["evidence_files"] = {
            path.relative_to(args.output).as_posix(): sha256(path)
            for path in sorted(args.output.rglob("*"))
            if path.is_file() and path.name != "m36_ci_contract_smoke.json"
        }
        output_file = args.output / "m36_ci_contract_smoke.json"
        output_file.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
