"""Fail-closed, synthetic-only preparation checks for the M36 Phase 2A gates.

This module prepares and validates evidence. It deliberately does not launch
the registered M36 assembly matrix or perform downstream screening.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess


CASE_ID = re.compile(r"case-[a-f0-9]{24}\Z")
STAGE_ID = re.compile(r"stage-[a-f0-9]{24}-s[0-9]{2}\Z")
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
TERMINAL_STATUSES = {
    "COMPLETE", "GENERATOR_INVALID", "INPUT_DIGEST_MISMATCH",
    "ASSEMBLER_MISSING", "ASSEMBLY_EXECUTION_FAILED",
    "ASSEMBLY_INTERRUPTED", "INTERRUPTED_BUDGET",
    "NOT_RUN_BUDGET_EXHAUSTED", "ASSEMBLY_OUTPUT_INVALID",
    "SUPPORT_EVIDENCE_INVALID", "DOWNSTREAM_HANDOFF_FAILED",
    "UNEVALUABLE_NO_SUPPORTED_ASSEMBLY", "NOT_RUN_WITH_BLOCKER",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def registered_assignments(design: dict) -> list[dict]:
    """Expand the frozen registry and reject missing, duplicate, or invalid cases."""
    manifest = design.get("registered_case_manifest")
    if not isinstance(manifest, dict):
        raise ValueError("registered case manifest is missing")
    families = manifest.get("families")
    repeats = manifest.get("repeat_ids")
    blocks = manifest.get("blocks")
    if not isinstance(families, list) or len(set(families)) != len(families):
        raise ValueError("registered family list is invalid")
    if not isinstance(repeats, list) or len(set(repeats)) != len(repeats) or not repeats:
        raise ValueError("registered repeat list is invalid")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("registered blocks are missing")
    assignments = []
    seen = set()
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("registered block is malformed")
        block_id = block.get("block_id")
        block_families = block.get("family_ids")
        conditions = block.get("condition_ids")
        assemblers = block.get("assembler_ids")
        if (not isinstance(block_id, str) or not block_id
                or not all(isinstance(rows, list) and rows for rows in
                           (block_families, conditions, assemblers))):
            raise ValueError("registered block dimensions are invalid")
        if (len(set(block_families)) != len(block_families)
                or len(set(conditions)) != len(conditions)
                or len(set(assemblers)) != len(assemblers)
                or not set(block_families) <= set(families)):
            raise ValueError(f"{block_id}: duplicate or unregistered dimensions")
        for family in block_families:
            for condition in conditions:
                for repeat in repeats:
                    for assembler in assemblers:
                        key = (block_id, family, condition, repeat, assembler)
                        if key in seen:
                            raise ValueError("duplicate registered assignment")
                        seen.add(key)
                        assignments.append({
                            "block_id": block_id, "family_id": family,
                            "condition_id": condition, "repeat_id": repeat,
                            "assembler_id": assembler,
                        })
    expected = design.get("planned_totals", {}).get("assembly_executions_max")
    if len(assignments) != expected:
        raise ValueError(
            f"registered assignment denominator mismatch: {len(assignments)} != {expected}"
        )
    return assignments


def _read_fastq_bytes(payload: bytes) -> list[tuple[str, str, str]]:
    try:
        text = gzip.decompress(payload).decode("ascii")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("generated FASTQ is not valid gzip ASCII") from error
    rows = text.splitlines()
    if len(rows) % 4:
        raise ValueError("generated FASTQ has an incomplete record")
    result = []
    for index in range(0, len(rows), 4):
        header, sequence, plus, quality = rows[index:index + 4]
        if (not header.startswith("@") or not sequence or not plus.startswith("+")
                or len(sequence) != len(quality)
                or set(sequence.upper()) - set("ACGTN")):
            raise ValueError("generated FASTQ contains a malformed record")
        result.append((header[1:].split()[0], sequence.upper(), quality))
    if not result:
        raise ValueError("generated FASTQ contains no records")
    return result


def _sequence_metrics(sequence: str) -> dict:
    sequence = sequence.upper()
    if not sequence or set(sequence) - set("ACGT"):
        raise ValueError("synthetic sequence must be a non-empty A/C/G/T string")
    kmers = [sequence[i:i + 5] for i in range(max(0, len(sequence) - 4))]
    counts = {base: sequence.count(base) for base in "ACGT"}
    return {
        "length": len(sequence),
        "gc_fraction": (counts["G"] + counts["C"]) / len(sequence),
        "base_counts": counts,
        "distinct_5mer_count": len(set(kmers)),
        "distinct_5mer_fraction": len(set(kmers)) / len(kmers) if kmers else 0.0,
    }


def audit_m25_generator(*, seed: int = 360001, target_to_background: str | None = None) -> dict:
    """Run only a small synthetic generator fixture and independently inspect it.

    The optional 1:9 setting is reported as available only if the generated
    number of target-derived reads is exactly one ninth of background reads.
    Technical-reference reads are not counted as synthetic background.
    """
    from unittest.mock import patch
    from . import m19_benchmark as m19
    from . import m25_read_coverage as m25

    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if target_to_background not in (None, "1:9"):
        raise ValueError("only the preregistered 1:9 ratio audit is supported")
    target = ("ACGTTGCA" * 113)[:900]
    background = ("TTGCAACG" * 1013)[:8100] if target_to_background == "1:9" else "TGCA" * 225
    case = {
        "analysis_id": "case-" + secrets.token_hex(12),
        "m25_read_length": 100,
        "coverage": 48,
        "read_start_mode": "random",
        "error_rate": 0.02,
        "insertion_rate": 0.01,
        "deletion_rate": 0.01,
        "m25_background_read_coverage": True,
        "m25_apply_background_errors": True,
    }
    params = {"coverage": 48, "error_rate": 0.02}
    with patch.object(m19, "SEED", seed):
        state_a = dict(case)
        payload_a = m25._make_fastq(state_a, target, "G" * 1000, params, (background,))
        state_b = dict(case)
        payload_b = m25._make_fastq(state_b, target, "G" * 1000, params, (background,))
        other = dict(case)
        with patch.object(m19, "SEED", seed + 1):
            payload_other = m25._make_fastq(other, target, "G" * 1000, params, (background,))
    reads = _read_fastq_bytes(payload_a)
    provenance = state_a.get("_m25_layout", {}).get("read_provenance")
    if not isinstance(provenance, dict) or len(provenance) != len(reads):
        raise ValueError("M25 placement ledger does not account for every read")
    ids = [row[0] for row in reads]
    if len(ids) != len(set(ids)) or set(ids) != set(provenance):
        raise ValueError("M25 read identities do not match the placement ledger")
    role_counts = {}
    sources = ["G" * 1000, background, target]
    observed_errors = {kind: 0 for kind in ("substitutions", "insertions", "deletions")}
    covered_target_positions = set()
    source_bases = 0
    for read_id, sequence, quality in reads:
        record = provenance[read_id]
        role = record.get("source_role")
        role_counts[role] = role_counts.get(role, 0) + 1
        if not sequence or len(sequence) != len(quality):
            raise ValueError("M25 read payload failed independent integrity checks")
        interval = record.get("source_interval")
        origins = record.get("base_origins")
        if (not isinstance(interval, list) or len(interval) != 2
                or interval[1] <= interval[0]
                or not isinstance(origins, list)
                or len(origins) != len(sequence)):
            raise ValueError("M25 placement coordinates are incomplete")
        source_index = record.get("source_index", 2 if role == "target_truth" else None)
        if not isinstance(source_index, int) or not 0 <= source_index < len(sources):
            raise ValueError("M25 source role/index is not verifiable")
        source = sources[source_index]
        if record.get("source_record_sha256") != _sha(source.encode("ascii")):
            raise ValueError("M25 placement ledger source digest mismatch")
        start, end = interval
        if start < 0 or end > len(source):
            raise ValueError("M25 placement interval is outside its source")
        source_bases += end - start
        mapped = [origin for origin in origins if origin is not None]
        if any(not isinstance(origin, int) or origin < start or origin >= end for origin in mapped):
            raise ValueError("M25 base-origin coordinates are outside the declared interval")
        independent_errors = {
            "substitutions": sum(
                sequence[index] != source[origin]
                for index, origin in enumerate(origins) if origin is not None
            ),
            "insertions": sum(origin is None for origin in origins),
            "deletions": len(set(range(start, end)) - set(mapped)),
        }
        if any(record.get(kind) != count for kind, count in independent_errors.items()):
            raise ValueError("M25 ledger error counts disagree with generated read bytes")
        for kind, count in independent_errors.items():
            observed_errors[kind] += count
        if role == "target_truth":
            covered_target_positions.update(mapped)
    target_count = role_counts.get("target_truth", 0)
    background_count = role_counts.get("synthetic_background", 0)
    absent_payload = None
    if target_to_background == "1:9":
        if not target_count or background_count != 9 * target_count:
            absent_payload = "NOT_RUN: generated target/background read counts are not exactly 1:9"
    # Negative control uses the same small fixture but intentionally no target sequence.
    absent_case = dict(case)
    absent_case["analysis_id"] = "case-" + secrets.token_hex(12)
    negative = m25._make_fastq(absent_case, None, "G" * 1000, params, (background,))
    negative_state = absent_case["_m25_layout"]["read_provenance"]
    if any(row.get("source_role") == "target_truth" for row in negative_state.values()):
        raise ValueError("target-absent fixture unexpectedly contains target-derived reads")
    return {
        "status": "PASS",
        "seed": seed,
        "deterministic_same_seed": payload_a == payload_b
        and state_a["_m25_layout"]["read_provenance"] == state_b["_m25_layout"]["read_provenance"],
        "distinct_seed_changes_generated_bytes": payload_a != payload_other,
        "read_count": len(reads),
        "read_counts_by_source_role": role_counts,
        "observed_errors": observed_errors,
        "realized_error_rates_per_source_read_base": {
            "substitution": observed_errors["substitutions"] /
                max(1, source_bases),
            "insertion": observed_errors["insertions"] /
                max(1, source_bases),
            "deletion": observed_errors["deletions"] /
                max(1, source_bases),
        },
        "realized_target_coverage": len(covered_target_positions) / len(target),
        "target_sequence_metrics": _sequence_metrics(target),
        "background_sequence_metrics": _sequence_metrics(background),
        "target_absent_control": {
            "status": "PASS",
            "read_count": sum(1 for row in negative_state.values()
                              if row.get("source_role") == "synthetic_background"),
            "target_derived_reads": 0,
        },
        "target_to_background_read_ratio": (
            target_count / background_count if background_count else None
        ),
        "one_to_nine_status": (
            "PASS" if target_to_background == "1:9" and target_count
            and background_count == 9 * target_count
            else absent_payload if target_to_background == "1:9" else "NOT_REQUESTED"
        ),
        "placement_ledger_sha256": _sha(json.dumps(
            provenance, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")),
        "generated_fastq_sha256": _sha(payload_a),
        "experimental_matrix_executed": False,
    }


def create_restricted_sidecar(path: str | Path, entries: list[dict]) -> dict:
    """Write evaluator-only mappings with restrictive file permissions."""
    if os.name == "nt":
        raise PermissionError(
            "Windows ACL ownership cannot be verified by this sidecar writer"
        )
    destination = Path(path)
    if not isinstance(entries, list) or not entries:
        raise ValueError("sidecar entries are required")
    normalized = []
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict) or not all(
            key in entry for key in ("family_id", "split", "truth", "factor", "condition")
        ):
            raise ValueError("sidecar entry is incomplete")
        token = entry.get("opaque_case_id") or "case-" + secrets.token_hex(12)
        if not isinstance(token, str) or not CASE_ID.fullmatch(token) or token in ids:
            raise ValueError("sidecar opaque case IDs must be unique random tokens")
        ids.add(token)
        normalized.append({**entry, "opaque_case_id": token})
    body = {"schema": "m36-restricted-evaluator-sidecar-v1", "entries": normalized}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.parent.stat().st_mode & 0o077:
        raise PermissionError("sidecar directory must be owner-only")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if destination.stat().st_mode & 0o077:
        destination.unlink(missing_ok=True)
        raise PermissionError("evaluator sidecar permissions are broader than owner-only")
    return {"path": str(destination), "sha256": _sha(payload), "entry_count": len(normalized)}


def preserve_restricted_raw_evidence(root: str | Path, artifacts: dict[str, bytes]) -> dict:
    """Store raw evidence bytes unchanged in a private tree and return digests."""
    if os.name == "nt":
        raise PermissionError(
            "Windows ACL ownership cannot be verified by this raw-evidence writer"
        )
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_mode & 0o077:
        raise PermissionError("raw evidence directory must be owner-only")
    written = {}
    for name, payload in artifacts.items():
        relative = Path(name)
        if (relative.is_absolute() or not relative.parts
                or any(part in ("", ".", "..") for part in relative.parts)
                or not isinstance(payload, bytes)):
            raise ValueError("raw evidence entry must be safe relative path and bytes")
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.parent.stat().st_mode & 0o077:
            raise PermissionError("raw evidence subdirectory must be owner-only")
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if target.read_bytes() != payload:
            raise OSError("raw evidence bytes changed during restricted storage")
        written[name] = _sha(payload)
    return {"status": "PASS", "files": written, "raw_bytes_modified": False}


def validate_blinded_artifacts(
    artifacts: dict[str, str | bytes], *, case_ids: set[str],
    forbidden_values: set[str] | None = None,
) -> None:
    """Reject truth/factor leakage from analyst-visible artifacts without mutation."""
    if not case_ids or any(not CASE_ID.fullmatch(value) for value in case_ids):
        raise ValueError("analysis-visible case IDs are not opaque tokens")
    forbidden = {value.casefold() for value in (forbidden_values or set()) if value}
    for artifact_path, content in artifacts.items():
        path = Path(artifact_path)
        if any(part.casefold() in forbidden for part in path.parts):
            raise ValueError(f"truth or condition label leaked into path: {artifact_path}")
        raw = content if isinstance(content, bytes) else content.encode("utf-8")
        text = raw.decode("utf-8", errors="replace")
        folded = text.casefold()
        if any(value in folded for value in forbidden):
            raise ValueError(f"truth or condition label leaked into {artifact_path}")
        if artifact_path.lower().endswith((".fastq", ".fq", ".fastq.gz", ".fq.gz")):
            payload = gzip.decompress(raw) if artifact_path.lower().endswith(".gz") else raw
            for line in payload.decode("ascii").splitlines()[::4]:
                header = line[1:].split() if line.startswith("@") else []
                if len(header) != 1 or not any(header[0].startswith(token + "-r") for token in case_ids):
                    raise ValueError("FASTQ header is not bound to one opaque case token")
        if "stage_id" in text:
            ids = re.findall(r"stage-[A-Za-z0-9_-]+", text)
            if any(not STAGE_ID.fullmatch(value) for value in ids):
                raise ValueError("analyst-visible stage ID is not opaque")


def validate_truth_support_crosswalk(
    *, truth_sequence: str, read_sequences: dict[str, str],
    placement_ledger: dict, contigs: dict[str, str],
    support_evidence: dict,
) -> dict:
    """Validate synthetic-only links while keeping generation/support failures distinct."""
    if not truth_sequence or not isinstance(read_sequences, dict) or not read_sequences:
        raise ValueError("truth and generated reads are required")
    ledger = placement_ledger.get("read_provenance")
    if not isinstance(ledger, dict) or set(ledger) != set(read_sequences):
        raise ValueError("placement ledger/read set mismatch")
    target_reads = []
    for read_id, sequence in read_sequences.items():
        record = ledger[read_id]
        if record.get("source_role") == "target_truth":
            interval = record.get("source_interval")
            if (not isinstance(interval, list) or len(interval) != 2
                    or truth_sequence[interval[0]:interval[1]] == ""):
                raise ValueError("target read has invalid source-truth coordinates")
            if record.get("source_record_sha256") != _sha(truth_sequence.encode("ascii")):
                raise ValueError("target read provenance does not bind to source truth")
            source_slice = truth_sequence[interval[0]:interval[1]]
            if record.get("source_sequence_sha256") != _sha(source_slice.encode("ascii")):
                raise ValueError("target read provenance does not bind to its truth interval")
            target_reads.append(read_id)
    if not target_reads:
        return {"generation": "NO_TARGET_READS", "assembly": "NOT_EVALUATED",
                "support": "NOT_EVALUATED", "downstream_handoff": "NOT_EVALUATED"}
    if not isinstance(contigs, dict) or not contigs:
        return {"generation": "PASS", "assembly": "NO_CONTIGS",
                "support": "NOT_EVALUATED", "downstream_handoff": "NOT_EVALUATED"}
    supported = set(support_evidence.get("supported_read_ids", []))
    if not supported <= set(read_sequences):
        raise ValueError("support evidence names reads outside the generated input")
    supported_contigs = set(support_evidence.get("supported_contig_ids", []))
    if not supported_contigs <= set(contigs):
        raise ValueError("support evidence names contigs outside the assembly")
    read_digests = support_evidence.get("supported_read_sha256", {})
    contig_digests = support_evidence.get("supported_contig_sha256", {})
    if (not isinstance(read_digests, dict) or not isinstance(contig_digests, dict)
            or set(read_digests) != supported or set(contig_digests) != supported_contigs):
        raise ValueError("support evidence is missing the read/contig digest crosswalk")
    if any(read_digests[key] != _sha(read_sequences[key].encode("ascii")) for key in supported):
        raise ValueError("support evidence read digest does not match generated input")
    if any(contig_digests[key] != _sha(contigs[key].encode("ascii")) for key in supported_contigs):
        raise ValueError("support evidence contig digest does not match assembled sequence")
    if not supported or not supported_contigs:
        return {"generation": "PASS", "assembly": "CONTIGS_EMITTED",
                "support": "NO_SUPPORTED_ASSEMBLY", "downstream_handoff": "NOT_EVALUATED"}
    placements = support_evidence.get("read_placements")
    if not isinstance(placements, list) or not placements:
        raise ValueError("support evidence lacks read-to-contig alignment placements")
    placed_reads = set()
    for placement in placements:
        if not isinstance(placement, dict):
            raise ValueError("malformed read-placement row")
        read_id, contig_id = placement.get("read_id"), placement.get("contig_id")
        start, cigar = placement.get("start"), placement.get("cigar")
        if (read_id not in supported or contig_id not in supported_contigs
                or read_id in placed_reads or type(start) is not int or start < 0
                or not isinstance(cigar, str)):
            raise ValueError("read placement has invalid identity or coordinates")
        ops = re.findall(r"(\d+)([M=XID])", cigar)
        if not ops or "".join(count + op for count, op in ops) != cigar:
            raise ValueError("read placement has malformed CIGAR")
        query_pos = 0
        ref_pos = start
        read = read_sequences[read_id].upper()
        contig = contigs[contig_id].upper()
        for count_text, operation in ops:
            count = int(count_text)
            if count <= 0:
                raise ValueError("read placement has non-positive CIGAR length")
            if operation in "M=X":
                query_part = read[query_pos:query_pos + count]
                ref_part = contig[ref_pos:ref_pos + count]
                if len(query_part) != count or len(ref_part) != count:
                    raise ValueError("read placement extends beyond its read or contig")
                if operation == "=" and query_part != ref_part:
                    raise ValueError("read placement '=' operation disagrees with sequences")
                if operation == "X" and query_part == ref_part:
                    raise ValueError("read placement 'X' operation has no mismatch")
                query_pos += count
                ref_pos += count
            elif operation == "I":
                query_pos += count
            else:
                ref_pos += count
        if query_pos != len(read):
            raise ValueError("read placement does not account for the complete read")
        placed_reads.add(read_id)
    if not supported <= placed_reads:
        raise ValueError("not every supported read has an actual contig placement")
    return {
        "generation": "PASS",
        "assembly": "CONTIGS_EMITTED",
        "support": "READ_SUPPORTED_ASSEMBLY",
        "supported_read_count": len(supported),
        "supported_contig_count": len(supported_contigs),
        "verified_read_placement_count": len(placed_reads),
        "downstream_handoff": "NOT_EVALUATED",
    }


def inspect_assembler_provenance() -> dict:
    """Inspect registered tool identities and limits without running an assembler."""
    from .assembly_adapters import (
        AssemblyWorkflowAdapter,
        SpadesAssemblyAdapter,
        TadpoleAssemblyAdapter,
    )

    registry = AssemblyWorkflowAdapter((SpadesAssemblyAdapter(), TadpoleAssemblyAdapter()))
    report = registry.inspect_dependency()
    result = {}
    for name in ("spades", "tadpole"):
        tool = report.get("assemblers", {}).get(name, {})
        deps = tool.get("dependencies", [])
        primary = deps[0] if deps else {}
        runtime = tool.get("runtime", {})
        version = runtime.get("version") or primary.get("version_output")
        digest = primary.get("sha256")
        result[name] = {
            "available": tool.get("status") == "available",
            "version": version.strip() if isinstance(version, str) else None,
            "executable_sha256": digest if isinstance(digest, str) and SHA256.fullmatch(digest) else None,
            "runtime_sha256": runtime.get("installation_sha256"),
            "archive_sha256": runtime.get("archive_sha256"),
            "default_resource_requirements": {
                "threads": 1,
                "memory_mb": 2048 if name == "spades" else 512,
                "enforcement": "adapter thread/memory arguments; no hard OS quota",
            },
            "status": "PASS" if (
                tool.get("status") == "available"
                and version and digest and SHA256.fullmatch(str(digest))
                and (name != "tadpole" or (
                    SHA256.fullmatch(str(runtime.get("installation_sha256", "")))
                    and runtime.get("archive_sha256") == "36b1c7be738f16185e967e33cab909e660b0f33a905b1fe06043f24a314a3725"
                ))
            ) else "BLOCKED",
        }
    return {
        "status": "PASS" if all(row["status"] == "PASS" for row in result.values()) else "BLOCKED",
        "tools": result,
        "assembly_executed": False,
    }


def _actual_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        value = result.stdout.strip()
        return value if re.fullmatch(r"[0-9a-f]{40,64}", value) else None
    except (OSError, subprocess.SubprocessError):
        return None


def _checkout_is_clean(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=no"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        return not result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False


def verify_evidence_files(evidence: dict, *, root: str | Path) -> dict:
    """Recompute manifest-bound evidence digests from regular files under root."""
    root = Path(root).resolve()
    manifest = evidence.get("evidence_files")
    if not isinstance(manifest, list) or not manifest:
        return {"status": "BLOCKED", "files": [], "reason": "evidence file manifest is missing"}
    verified = []
    seen = set()
    for row in manifest:
        if not isinstance(row, dict):
            return {"status": "BLOCKED", "files": verified, "reason": "malformed evidence manifest row"}
        relative, expected = row.get("path"), row.get("sha256")
        if (not isinstance(relative, str) or not relative
                or not isinstance(expected, str) or not SHA256.fullmatch(expected)):
            return {"status": "BLOCKED", "files": verified, "reason": "invalid path or expected digest"}
        candidate = Path(relative)
        if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
            return {"status": "BLOCKED", "files": verified, "reason": "unsafe evidence path"}
        raw_path = root / candidate
        path = raw_path.resolve()
        has_symlink_component = any(
            (root.joinpath(*candidate.parts[:index])).is_symlink()
            for index in range(1, len(candidate.parts) + 1)
        )
        if (has_symlink_component or not path.is_relative_to(root)
                or not path.is_file()):
            return {"status": "BLOCKED", "files": verified, "reason": f"missing or unsafe evidence file: {relative}"}
        if relative in seen:
            return {"status": "BLOCKED", "files": verified, "reason": f"duplicate evidence path: {relative}"}
        seen.add(relative)
        actual = _actual_sha256(path)
        verified.append({"path": relative, "expected_sha256": expected, "actual_sha256": actual})
        if actual != expected:
            return {"status": "BLOCKED", "files": verified, "reason": f"digest mismatch: {relative}"}
    return {"status": "PASS", "files": verified}


def validate_readiness(
    design: dict, evidence: dict, *, root: str | Path | None = None,
    design_path: str | Path | None = None,
) -> dict:
    """Evaluate pre-execution gates; never requires or invents execution outcomes."""
    assignments = registered_assignments(design)
    blockers = []
    checks = {
        "registered_assignments": {
            "status": "PASS" if len(assignments) == 520 else "BLOCKED",
            "observed": len(assignments), "expected": 520,
        },
    }
    if len(assignments) != 520:
        blockers.append("registered assignment count is not 520")
    root_path = Path(root).resolve() if root else Path.cwd().resolve()
    file_report = verify_evidence_files(evidence, root=root_path)
    design_digest = None
    if design_path:
        candidate = Path(design_path).resolve()
        if candidate.is_file() and candidate.is_relative_to(root_path):
            design_digest = _actual_sha256(candidate)
    current_revision = _source_revision(root_path)
    checkout_clean = _checkout_is_clean(root_path)
    hashes_ok = (
        file_report["status"] == "PASS"
        and design_digest is not None
        and evidence.get("design_sha256") == design_digest
        and current_revision is not None
        and evidence.get("source_commit") == current_revision
        and checkout_clean
    )
    checks["evidence_integrity"] = {
        "status": "PASS" if hashes_ok else "BLOCKED",
        "files": file_report.get("files", []),
        "design_sha256": design_digest,
        "source_commit": current_revision,
        "checkout_clean": checkout_clean,
        "reason": file_report.get("reason"),
    }
    if not hashes_ok:
        blockers.append("actual evidence files, design digest, or source commit do not match the expected manifest")
    tools = evidence.get("tools", {})
    detected_tool_report = inspect_assembler_provenance()
    detected_tools = detected_tool_report.get("tools", {})
    identity_fields = (
        "available", "version", "executable_sha256", "runtime_sha256",
        "archive_sha256",
    )
    tools_ok = all(
        isinstance(tools.get(name), dict)
        and detected_tools.get(name, {}).get("status") == "PASS"
        and all(tools[name].get(field) == detected_tools[name].get(field)
                for field in identity_fields)
        for name in ("spades", "tadpole")
    )
    checks["assembler_provenance"] = {"status": "PASS" if tools_ok else "BLOCKED"}
    if not tools_ok:
        blockers.append("exact SPAdes and Tadpole runtime identity is not available and digest-bound")
    generator = evidence.get("generator_audit", {})
    generator_ok = (
        generator.get("status") == "PASS"
        and generator.get("deterministic_same_seed") is True
        and generator.get("target_absent_control", {}).get("target_derived_reads") == 0
        and generator.get("one_to_nine_status") == "PASS"
    )
    checks["generator_and_ratio_audit"] = {"status": "PASS" if generator_ok else "BLOCKED"}
    if not generator_ok:
        blockers.append("generator semantics, target-absent behavior, or exact 1:9 ratio is unverified")
    isolation = evidence.get("blinding_audit", {})
    isolation_ok = (
        isolation.get("sidecar_isolated") is True
        and isolation.get("raw_evidence_preserved") is True
        and isolation.get("leakage_checks_passed") is True
    )
    checks["restricted_sidecar_and_leakage"] = {
        "status": "PASS" if isolation_ok else "BLOCKED"
    }
    if not isolation_ok:
        blockers.append("restricted sidecar, raw evidence isolation, or leakage checks are incomplete")
    crosswalk = evidence.get("truth_support_crosswalk", {})
    crosswalk_ok = (
        crosswalk.get("generation") == "PASS"
        and crosswalk.get("assembly") == "CONTIGS_EMITTED"
        and crosswalk.get("support") == "READ_SUPPORTED_ASSEMBLY"
    )
    checks["truth_to_support_crosswalk"] = {
        "status": "PASS" if crosswalk_ok else "BLOCKED"
    }
    if not crosswalk_ok:
        blockers.append("truth-to-support crosswalk has not passed the synthetic compatibility fixture")
    compatibility = evidence.get("compatibility_smoke", {})
    compatibility_ok = compatibility.get("status") == "PASS"
    checks["assembler_compatibility"] = {
        "status": "PASS" if compatibility_ok else "BLOCKED"
    }
    if not compatibility_ok:
        blockers.append("assembler input/output compatibility smoke check is missing or failed")
    resource = evidence.get("resource_limits", {})
    cpu_ok = (resource.get("max_vcpus_per_attempt") == 1
              and resource.get("enforcement_verified") is True
              and bool(resource.get("enforcement_mechanism")))
    checks["one_vcpu_limit"] = {"status": "PASS" if cpu_ok else "BLOCKED"}
    if not cpu_ok:
        blockers.append("one-vCPU enforcement is not evidenced; CPU budget remains conditional")
    # The roster is a plan, not an execution receipt. Every blocked assignment
    # carries the gate reasons; no attempt result or raw-output digest is made up.
    pre_execution_ready = not blockers
    assignment_manifest = [
        {**row, "status": "PLANNED" if pre_execution_ready else "BLOCKED",
         **({} if pre_execution_ready else {"blocked_reasons": list(blockers)})}
        for row in assignments
    ]
    checks["assignment_accounting"] = {
        "status": "PASS" if len(assignment_manifest) == 520 else "BLOCKED",
        "planned": sum(row["status"] == "PLANNED" for row in assignment_manifest),
        "blocked": sum(row["status"] == "BLOCKED" for row in assignment_manifest),
        "execution_outcomes_required": False,
    }
    if len(assignment_manifest) != 520:
        blockers.append("pre-execution assignment roster does not cover the registered denominator")
    governance = design.get("governance", {})
    governance_ok = (
        design.get("status") == "DESIGN_ONLY"
        and design.get("design_only") is True
        and governance.get("m36_experiments_executed") is False
        and governance.get("biological_execution_authorized") is False
        and governance.get("production_promotion") is False
        and evidence.get("matrix_execution_requested") is not True
    )
    checks["governance_restrictions"] = {"status": "PASS" if governance_ok else "BLOCKED"}
    if not governance_ok:
        blockers.append("governance is not restricted to design/preparation-only work")
    return {
        "schema": "m36-phase2a-pre-execution-readiness-v2",
        "status": "BLOCKED" if blockers else "PRE-EXECUTION READY",
        "checks": checks,
        "blockers": blockers,
        "registered_assignment_count": len(assignments),
        "assignment_manifest": assignment_manifest,
        "execution_statuses": None,
        "matrix_execution_performed": False,
        "phase2b_authorized": False,
    }


def validate_post_execution_results(
    design: dict, statuses: list[dict], *, root: str | Path,
) -> dict:
    """Validate terminal results only when each row binds to actual evidence bytes."""
    assignments = registered_assignments(design)
    expected = {
        (row["block_id"], row["family_id"], row["condition_id"],
         row["repeat_id"], row["assembler_id"])
        for row in assignments
    }
    observed = []
    valid = isinstance(statuses, list) and len(statuses) == len(assignments)
    evidence_files = []
    if valid:
        for row in statuses:
            if (not isinstance(row, dict) or row.get("status") not in TERMINAL_STATUSES
                    or not all(isinstance(row.get(key), str) for key in (
                        "block_id", "family_id", "condition_id", "repeat_id", "assembler_id"
                    ))
                    or not isinstance(row.get("evidence_path"), str)
                    or not SHA256.fullmatch(str(row.get("evidence_sha256", "")))):
                valid = False
                break
            evidence_files.append({
                "path": row["evidence_path"], "sha256": row["evidence_sha256"],
            })
            observed.append((
                row["block_id"], row["family_id"], row["condition_id"],
                row["repeat_id"], row["assembler_id"],
            ))
        valid = valid and len(set(observed)) == len(assignments) and set(observed) == expected
        verified = verify_evidence_files({"evidence_files": evidence_files}, root=root)
        valid = valid and verified["status"] == "PASS"
    else:
        verified = {"status": "BLOCKED"}
    return {
        "schema": "m36-phase2a-post-execution-validation-v1",
        "status": "PASS" if valid else "BLOCKED",
        "registered_assignment_count": len(assignments),
        "terminal_result_count": len(statuses) if isinstance(statuses, list) else 0,
        "evidence_integrity": verified,
    }
