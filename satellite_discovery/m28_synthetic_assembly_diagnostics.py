"""Retrospective diagnostics for fixed synthetic M25–M27 assembly runs."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time

from . import artifact_contracts, assembly_adapters, read_support
from . import m25_read_coverage

SCHEMA = "m28-synthetic-assembly-diagnostics-v1"
GOVERNANCE = {
    "decision": "INCOMPLETE",
    "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
    "biological_execution_authorized": False,
}
FOLLOW_UP_SCIENTIFIC_LIMITATION = (
    "The original experimental FASTQ and SAM evidence was unavailable for this follow-up analysis. "
    "Consequently, mapped/unmapped read counts and the relative contributions of absent alignments versus "
    "rejected low-confidence alignments could not be independently determined. Unsupported classifications "
    "reflect the previously recorded frozen M6 support criteria and must not be interpreted as proof that no reads aligned."
)


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _fastq(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    rows = []
    with opener(path, "rt", encoding="ascii") as stream:
        while True:
            head = stream.readline().strip()
            if not head:
                break
            seq, plus, qual = (stream.readline().strip() for _ in range(3))
            if not head.startswith("@") or not plus.startswith("+") or len(seq) != len(qual):
                raise ValueError(f"Malformed FASTQ record in {path}")
            rows.append((head[1:].split()[0], seq.upper()))
    return rows


def sequence_diagnostics(sequence, *, k=21):
    seq = sequence.upper()
    if not seq or set(seq) - set("ACGT"):
        raise ValueError("Diagnostics accept only non-empty synthetic A/C/G/T sequences")
    counts = Counter(seq)
    entropy = -sum((n / len(seq)) * math.log2(n / len(seq)) for n in counts.values())
    k = min(k, len(seq))
    words = [seq[i:i + k] for i in range(len(seq) - k + 1)]
    multiplicity = Counter(words)
    repeats = [n for n in multiplicity.values() if n > 1]
    positions = {}
    for index, word in enumerate(words):
        positions.setdefault(word, []).append(index)
    spacings = [
        b - a for hits in positions.values() if len(hits) > 1
        for a, b in zip(hits, hits[1:])
    ]
    return {
        "length": len(seq),
        "shannon_entropy_bits": entropy,
        "k": k,
        "kmer_windows": len(words),
        "unique_kmers": len(multiplicity),
        "unique_kmer_fraction": len(multiplicity) / len(words) if words else 0.0,
        "repeated_kmer_windows": sum(repeats),
        "maximum_kmer_multiplicity": max(multiplicity.values(), default=0),
        "repeated_kmer_multiplicity_histogram": dict(sorted(Counter(repeats).items())),
        "repeated_kmer_spacing_min": min(spacings) if spacings else None,
        "repeated_kmer_spacing_max": max(spacings) if spacings else None,
        "sequence_sha256": _sha(seq.encode("ascii")),
    }


def _failure_class(root, report_case):
    stage = root / "stages" / f"m6_{report_case['analysis_id']}"
    reconstruction = stage / "reconstruction_evidence.json"
    manifest = stage / "manifest.json"
    eligible_path = stage / "eligible_read1.fastq.gz"
    if eligible_path.is_file() and not _fastq(eligible_path):
        return "NO_ASSEMBLY_ELIGIBLE_READS"
    assembly_manifest = stage / "assembly" / "manifest.json"
    if assembly_manifest.is_file() and _json(assembly_manifest).get("status") == "failed":
        failed = _json(assembly_manifest)
        error = (failed.get("error") or "").lower()
        if "dependency" in error or failed.get("dependency_report", {}).get("status") == "dependency_missing":
            return "ASSEMBLER_DEPENDENCY_UNAVAILABLE"
        if failed.get("error_type") == "ValueError" or "invalid" in error or "malformed" in error:
            return "INVALID_ASSEMBLY_INPUT"
        return "ASSEMBLER_PROCESS_FAILURE"
    if not manifest.is_file():
        return "UPSTREAM_OR_STAGE_NOT_RECORDED"
    if _json(manifest).get("status") == "failed":
        return "UPSTREAM_STAGE_FAILURE"
    if not reconstruction.is_file():
        return "OUTPUT_MISSING_OR_NOT_EVALUATED"
    evidence = _json(reconstruction)
    status = evidence.get("status")
    if status == "EXECUTION_FAILED":
        return "ASSEMBLER_PROCESS_FAILURE"
    if status in {"NO_ELIGIBLE_READS", "NO_ASSEMBLY_ELIGIBLE_READS"}:
        return "NO_ASSEMBLY_ELIGIBLE_READS"
    if status in {"NO_CONTIGS", "ASSEMBLY_EMPTY"}:
        return "ASSEMBLER_COMPLETED_NO_CONTIGS"
    if status == "READ_SUPPORTED_ASSEMBLY":
        return (
            "ASSEMBLER_COMPLETED_INCOMPLETE_SUPPORTED_CONTIGS"
            if not report_case.get("pipeline", {}).get("exact_recovery")
            else "ASSEMBLER_COMPLETED_SUPPORTED_CONTIGS"
        )
    if status == "UNSUPPORTED_ASSEMBLY":
        return "ASSEMBLER_COMPLETED_UNSUPPORTED_CONTIGS"
    return status or "ASSEMBLY_STATUS_UNCLASSIFIED"


def _graph_summary(stage):
    candidates = (
        stage / "assembly" / "raw" / "assembly_graph_with_scaffolds.gfa",
        stage / "assembly_graph_with_scaffolds.gfa",
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    if not path.is_file():
        return {"status": "NOT_AVAILABLE", "path": None}
    nodes, links, degrees, depth_tags = set(), 0, Counter(), []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split("\t")
        if not fields:
            continue
        if fields[0] == "S" and len(fields) >= 3:
            nodes.add(fields[1])
            for tag in fields[3:]:
                if tag.startswith("DP:f:"):
                    try:
                        depth_tags.append(float(tag[5:]))
                    except ValueError:
                        pass
        elif fields[0] == "L" and len(fields) >= 5:
            links += 1
            degrees[fields[1]] += 1
            degrees[fields[3]] += 1
    return {
        "status": "AVAILABLE",
        "path": path.name,
        "sha256": _sha(path.read_bytes()),
        "segment_count": len(nodes),
        "link_count": links,
        "dead_end_segment_count": sum(degrees.get(node, 0) == 0 for node in nodes),
        "branch_segment_count": sum(degrees.get(node, 0) > 2 for node in nodes),
        "coverage_tag_count": len(depth_tags),
        "coverage_tag_min": min(depth_tags) if depth_tags else None,
        "coverage_tag_max": max(depth_tags) if depth_tags else None,
    }


def _sha_file(path):
    return _sha(Path(path).read_bytes())


def _fastq_with_metadata(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    records, metadata = [], {}
    with opener(path, "rt", encoding="ascii", newline="") as stream:
        while True:
            header = stream.readline()
            if not header:
                break
            sequence, plus, quality = (stream.readline() for _ in range(3))
            header, sequence, plus, quality = (
                header.rstrip("\r\n"), sequence.rstrip("\r\n"),
                plus.rstrip("\r\n"), quality.rstrip("\r\n"),
            )
            if (not header.startswith("@") or not plus.startswith("+")
                    or len(sequence) != len(quality) or not sequence):
                raise ValueError("Malformed FASTQ input for read-support evaluation")
            query_id = header[1:].split()[0]
            if query_id in metadata:
                raise ValueError("Duplicate FASTQ query ID in read-support input")
            sequence = sequence.upper()
            metadata[(query_id, 0)] = {
                "query_length": len(sequence),
                "sequence_sha256": _sha(sequence.encode("ascii")),
                "mean_phred": sum(ord(char) - 33 for char in quality) / len(quality),
                "ambiguous_fraction": sum(char not in "ACGT" for char in sequence) / len(sequence),
            }
            records.append(query_id)
    if not records:
        raise ValueError("Read-support evaluation requires non-empty FASTQ input")
    return records, metadata


def _evaluate_experimental_read_support(experiment_dir, reads_path, contigs_path, thresholds):
    experiment_dir = Path(experiment_dir)
    mapper = shutil.which("minimap2")
    result_path = experiment_dir / "read_support.json"
    if not mapper:
        result = {"status": "NOT_EVALUATED", "reason": "minimap2 is unavailable"}
        result_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        return result
    records, metadata = _fastq_with_metadata(reads_path)
    sam_path = experiment_dir / "support_alignments.sam"
    stderr_path = experiment_dir / "support_mapper.stderr.log"
    command = [mapper, "-a", "-x", "sr", "-t", "1", str(contigs_path), str(reads_path)]
    started = time.monotonic()
    with sam_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        process = subprocess.run(command, stdout=stdout, stderr=stderr, check=False)
    mapper_run = {
        "executable": mapper,
        "return_code": process.returncode,
        "duration_seconds": time.monotonic() - started,
        "sam_sha256": _sha_file(sam_path),
        "stderr_sha256": _sha_file(stderr_path),
        "input_reads_sha256": _sha_file(reads_path),
        "contigs_sha256": _sha_file(contigs_path),
        "query_count": len(records),
        "thresholds": thresholds,
    }
    if process.returncode != 0:
        result = {
            "status": "FAILED",
            "reason": "minimap2 returned a non-zero exit status",
            "mapper_execution": mapper_run,
        }
    else:
        try:
            assessed = read_support.assess_read_support(
                sam_path, contigs_path, metadata, paired=False, thresholds=thresholds,
            )
            counts = Counter(row["status"] for row in assessed["contigs"])
            result = {
                "schema": "m28-experimental-read-support-v1",
                "status": "EVALUATED",
                "aggregate_status": assessed["status"],
                "contig_count": len(assessed["contigs"]),
                "contig_status_counts": dict(sorted(counts.items())),
                "contigs": assessed["contigs"],
                "read_evidence": _read_support_diagnostics(assessed, thresholds),
                "mapper_execution": mapper_run,
            }
        except (OSError, ValueError) as error:
            result = {
                "status": "INCOMPLETE",
                "reason": f"read-support SAM validation failed: {error}",
                "mapper_execution": mapper_run,
            }
    result_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def _read_support_diagnostics(assessed, thresholds):
    """Summarize primary alignment outcomes without changing support thresholds."""
    reads = assessed["read_support"]
    min_mapq = thresholds.get("min_mapq", 20)
    min_fraction = thresholds.get("min_alignment_fraction", .8)
    min_identity = thresholds.get("min_sequence_identity", .95)
    mapped = [row for row in reads if row["mapped"]]
    unmapped_count = len(reads) - len(mapped)
    criteria = {
        "mapq": lambda row: row.get("mapq") == 255 or row.get("mapq", 0) < min_mapq,
        "alignment_fraction": lambda row: row.get("aligned_query_fraction", 0) < min_fraction,
        "sequence_identity": lambda row: row.get("sequence_identity", 0) < min_identity,
        "other_read_quality": lambda row: not row.get("quality_eligible", False),
    }
    rejected = [row for row in mapped if not row["qualifying"]]
    rejected_counts = {
        name: sum(test(row) for row in mapped)
        for name, test in criteria.items()
    }
    by_contig = {}
    for row in mapped:
        item = by_contig.setdefault(row["contig_id"], {"mapped": [], "qualifying": 0})
        item["mapped"].append(row)
        item["qualifying"] += bool(row["qualifying"])
    contigs = []
    for contig in assessed["contigs"]:
        cid = contig["contig_id"]
        evidence = by_contig.get(cid, {"mapped": [], "qualifying": 0})
        rejected_on_contig = [row for row in evidence["mapped"] if not row["qualifying"]]
        qualifying = evidence["qualifying"]
        contigs.append({
            "contig_id": cid,
            "mapped_primary_read_count": len(evidence["mapped"]),
            "rejected_mapped_primary_read_count": len(rejected_on_contig),
            "qualifying_supporting_read_count": qualifying,
            "rejected_by_criterion": {
                name: sum(test(row) for row in rejected_on_contig)
                for name, test in criteria.items()
            },
            "zero_qualifying_support_interpretation": (
                None if qualifying else (
                    "MAPPED_ALIGNMENTS_REJECTED_BY_CONFIGURED_CRITERIA"
                    if evidence["mapped"] else "NO_PRIMARY_READS_ALIGNED_TO_CONTIG"
                )
            ),
        })
    return {
        "primary_reads": {
            "total_input_reads": len(reads),
            "mapped": len(mapped),
            "unmapped": unmapped_count,
            "mapped_with_qualifying_alignment": sum(row["qualifying"] for row in mapped),
            "mapped_rejected_by_one_or_more_support_criteria": len(rejected),
        },
        "mapped_reads_rejected_by_criterion": rejected_counts,
        "criterion_counts_overlap": True,
        "contigs": contigs,
    }


def execute_experimental_assemblies(baseline_root, output_root):
    """Run the fixed experimental setting and preserve execution/support evidence."""
    baseline_root, output_root = Path(baseline_root), Path(output_root)
    report = _json(baseline_root / "m25-read-coverage.json")
    cases = {row["case_id"]: row for row in report.get("cases", [])}
    spades = shutil.which("spades.py")
    outputs = []
    for split in ("development", "tuning", "held_out"):
        case_id = f"{split}-m25-02"
        case_root = baseline_root / split / case_id
        stage = case_root / "stages/m6_m2502"
        reads_path = stage / "eligible_read1.fastq.gz"
        target = output_root / split
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite experimental evidence: {target}")
        target.mkdir(parents=True)
        expected_input = _sha_file(reads_path)
        thresholds_doc = _json(stage / "read_support.json")
        thresholds = thresholds_doc.get("configuration")
        if not isinstance(thresholds, dict):
            thresholds = {}
        execution = {
            "schema": "m28-experimental-assembly-execution-v1",
            "case_id": case_id,
            "split": split,
            "input_manifest_sha256": cases.get(case_id, {}).get("input_manifest_sha256"),
            "input": {"artifact_name": reads_path.name, "bytes": reads_path.stat().st_size,
                      "sha256": expected_input},
            "command_parameters": ["--only-assembler", "-t", "1", "-m", "2", "-k", "21,33"],
            "thread_count": 1,
            "memory_gb": 2,
            "memory_mb": 2048,
            "k_values": [21, 33],
            "return_code": None,
            "status": "NOT_EVALUATED",
            "output": None,
        }
        if not spades:
            execution["reason"] = "spades.py is unavailable"
        else:
            command = [
                spades, "--only-assembler", "-t", "1", "-m", "2", "-k", "21,33",
                "-s", str(reads_path), "-o", str(target),
            ]
            execution["executable"] = spades
            execution["command"] = command
            started = time.monotonic()
            log_root = output_root / "logs"
            log_root.mkdir(parents=True, exist_ok=True)
            try:
                with (log_root / f"{split}.stdout.log").open("wb") as stdout, (log_root / f"{split}.stderr.log").open("wb") as stderr:
                    process = subprocess.run(
                        command, stdout=stdout, stderr=stderr, check=False,
                        timeout=assembly_adapters.DEFAULT_TIMEOUT_SECONDS,
                    )
                execution["duration_seconds"] = time.monotonic() - started
                execution["return_code"] = process.returncode
                if process.returncode != 0:
                    execution.update(status="FAILED", reason="SPAdes exited non-zero")
                else:
                    contigs = target / "contigs.fasta"
                    try:
                        artifact_contracts.validate_artifact(contigs, "canonical_contig_fasta")
                        output = {
                            "artifact_name": contigs.name,
                            "bytes": contigs.stat().st_size,
                            "sha256": _sha_file(contigs),
                            "record_count": len(m25_read_coverage._fasta(contigs)),
                        }
                        if output["record_count"] < 1:
                            raise ValueError("SPAdes returned an empty contig FASTA")
                        execution.update(status="COMPLETED", output=output)
                    except (OSError, ValueError) as error:
                        execution.update(status="INCOMPLETE", reason=f"invalid or missing contigs FASTA: {error}")
            except subprocess.TimeoutExpired:
                execution.update(
                    status="TIMED_OUT",
                    duration_seconds=time.monotonic() - started,
                    reason="SPAdes exceeded its configured timeout",
                )
        if execution["status"] == "COMPLETED":
            execution["read_support"] = _evaluate_experimental_read_support(
                target, reads_path, target / "contigs.fasta", thresholds,
            )
        (target / "execution.json").write_text(
            json.dumps(execution, sort_keys=True, indent=2) + "\n", encoding="utf-8",
        )
        outputs.append({"split": split, "status": execution["status"],
                        "return_code": execution["return_code"]})
    return outputs


def _validate_experiment_execution(experiment_dir, expected_reads, expected_manifest_sha):
    """Validate persisted execution evidence before accepting any assembly output."""
    experiment_dir = Path(experiment_dir)
    manifest_path = experiment_dir / "execution.json"
    if not manifest_path.is_file():
        return {"status": "NOT_EVALUATED", "reason": "execution.json is missing"}
    try:
        manifest = _json(manifest_path)
    except (OSError, ValueError):
        return {"status": "INCOMPLETE", "reason": "execution.json is malformed"}
    required = {
        "schema", "status", "return_code", "input_manifest_sha256",
        "input", "command_parameters", "output",
    }
    if (not isinstance(manifest, dict) or not required.issubset(manifest)
            or manifest.get("schema") != "m28-experimental-assembly-execution-v1"):
        return {"status": "INCOMPLETE", "reason": "execution record is missing required fields"}
    if not isinstance(manifest.get("input"), dict):
        return {"status": "INCOMPLETE", "reason": "execution input identity is malformed"}
    if manifest["status"] in {"FAILED", "TIMED_OUT"} or manifest["return_code"] not in (0, None):
        return {"status": "FAILED", "reason": manifest.get("reason", "assembler did not complete"),
                "return_code": manifest.get("return_code")}
    if manifest["status"] != "COMPLETED" or manifest["return_code"] != 0:
        return {"status": "INCOMPLETE", "reason": manifest.get("reason", "execution did not complete")}
    try:
        actual_input_sha = _sha_file(expected_reads)
        actual_input_bytes = Path(expected_reads).stat().st_size
    except OSError as error:
        return {"status": "INCOMPLETE", "reason": f"paired baseline input is unavailable: {error}"}
    if (manifest["input_manifest_sha256"] != expected_manifest_sha
            or manifest["input"].get("sha256") != actual_input_sha
            or manifest["input"].get("bytes") != actual_input_bytes):
        return {"status": "INCOMPLETE", "reason": "paired input identity does not match frozen baseline"}
    if manifest["command_parameters"] != ["--only-assembler", "-t", "1", "-m", "2", "-k", "21,33"]:
        return {"status": "INCOMPLETE", "reason": "execution parameters do not match the declared comparison"}
    try:
        memory_index = manifest["command_parameters"].index("-m")
        command_memory_gb = int(manifest["command_parameters"][memory_index + 1])
    except (IndexError, TypeError, ValueError):
        return {"status": "INCOMPLETE", "reason": "SPAdes memory command metadata is malformed"}
    if command_memory_gb < 1:
        return {"status": "INCOMPLETE", "reason": "SPAdes memory command metadata is invalid"}
    if (manifest.get("memory_gb") != command_memory_gb
            or manifest.get("memory_mb") != command_memory_gb * 1024):
        manifest["memory_metadata_correction"] = {
            "source": "SPAdes -m command parameter is in GB",
            "previous_memory_gb": manifest.get("memory_gb"),
            "previous_memory_mb": manifest.get("memory_mb"),
            "corrected_memory_gb": command_memory_gb,
            "corrected_memory_mb": command_memory_gb * 1024,
        }
    manifest["memory_gb"] = command_memory_gb
    manifest["memory_mb"] = command_memory_gb * 1024
    output = manifest.get("output")
    contigs = experiment_dir / "contigs.fasta"
    if (not isinstance(output, dict) or output.get("artifact_name") != "contigs.fasta"
            or not contigs.is_file()):
        return {"status": "INCOMPLETE", "reason": "output FASTA is missing"}
    try:
        artifact_contracts.validate_artifact(contigs, "canonical_contig_fasta")
        if (_sha_file(contigs) != output.get("sha256")
                or contigs.stat().st_size != output.get("bytes")
                or len(m25_read_coverage._fasta(contigs)) != output.get("record_count")):
            raise ValueError("output FASTA provenance does not match execution record")
    except (OSError, ValueError) as error:
        return {"status": "INCOMPLETE", "reason": f"output FASTA failed validation: {error}"}
    return {"status": "COMPLETED", "manifest": manifest, "contigs_path": contigs}


def _assembly_execution(stage):
    root = stage / "assembly"
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {"status": "NOT_RUN_OR_NOT_RECORDED"}
    manifest = _json(manifest_path)
    input_identity = {}
    for key, value in manifest.get("inputs", {}).items():
        input_identity[key] = {
            "artifact_name": Path(value.get("path", key)).name,
            "bytes": value.get("bytes"),
            "sha256": value.get("sha256"),
        }
    details = {
        "status": manifest.get("status"),
        "assembler": manifest.get("configuration", {}).get("assembler"),
        "layout": manifest.get("configuration", {}).get("layout"),
        "threads": manifest.get("configuration", {}).get("threads"),
        "memory_mb": manifest.get("configuration", {}).get("memory_mb"),
        "executable": (manifest.get("tool", {}).get("executables") or [{}])[0],
        "safe_command": manifest.get("safe_command"),
        "return_code": manifest.get("exit_status"),
        "duration_seconds": manifest.get("duration_seconds"),
        "error_type": manifest.get("error_type"),
        "error": manifest.get("error"),
        "input_identity": input_identity,
        "resource_limits": {
            "timeout_seconds": assembly_adapters.DEFAULT_TIMEOUT_SECONDS,
            "output_budget_bytes": assembly_adapters.DEFAULT_OUTPUT_BUDGET,
            "containment": "cooperative timeout/output budget and tool-level thread/memory options; not hard OS quotas",
        },
        "output_inventory": manifest.get("output_inventory", []),
    }
    for name in ("stdout.log", "stderr.log"):
        path = root / name
        if path.is_file():
            content = path.read_bytes()
            details[name] = {
                "bytes": len(content),
                "sha256": _sha(content),
                "tail": content[-2000:].decode("utf-8", errors="replace"),
            }
    raw = root / "raw"
    details["raw_output_files"] = (
        sorted(p.relative_to(root).as_posix() for p in raw.rglob("*") if p.is_file())
        if raw.is_dir() else []
    )
    details["contigs_fasta_present"] = (raw / "contigs.fasta").is_file()
    return details


def _candidate_summary(stage):
    path = stage / "candidate_sequence_set.json"
    if not path.is_file():
        return {"status": "NOT_AVAILABLE"}
    rows = _json(path).get("records", [])
    below = [x for x in rows if x.get("m6_support_status") != "READ_SUPPORTED_ASSEMBLY"]
    return {
        "status": "AVAILABLE",
        "candidate_count": len(rows),
        "support_status_counts": dict(sorted(Counter(
            x.get("m6_support_status", "UNSPECIFIED") for x in rows
        ).items())),
        "candidate_hashes": sorted(
            x.get("sequence_sha256") for x in rows if x.get("sequence_sha256")
        ),
        "below_full_support_count": len(below),
        "below_full_support_distinct_hashes": sorted({
            x.get("sequence_sha256") for x in below if x.get("sequence_sha256")
        }),
        "candidate_lengths": sorted(
            x.get("sequence_length") for x in rows if x.get("sequence_length") is not None
        ),
    }


def _m20_summary(m20_root):
    if not m20_root:
        return {"status": "NOT_SUPPLIED"}
    root = Path(m20_root)
    stages = {}
    for name in ("phase2b", "phase3", "phase4", "phase5"):
        path = root / name / "report.json"
        if not path.is_file():
            stages[name] = {"status": "BLOCKED", "reason": "report.json missing"}
            continue
        report = _json(path)
        stages[name] = {
            "schema": report.get("schema"),
            "status": report.get("status"),
            "decision": report.get("decision"),
            "software_integration_status": report.get("software_integration_status"),
            "biological_discovery_status": report.get("biological_discovery_status"),
            "deterministic_semantic_outcomes_sha256": report.get(
                "deterministic_semantic_outcomes_sha256"
            ),
            "case_count": len(report.get("cases", [])),
        }
    complete = all(
        x.get("status") == "COMPLETE" or x.get("decision") is not None
        for x in stages.values()
    )
    return {"status": "COMPLETE" if complete else "PARTIAL", "stages": stages}


def _experimental_comparison(baseline_root, experiment_root):
    if not experiment_root:
        return {"status": "NOT_RUN"}
    root = Path(baseline_root)
    exp_root = Path(experiment_root)
    report = _json(root / "m25-read-coverage.json")
    input_digests = {row["case_id"]: row["input_manifest_sha256"] for row in report["cases"]}
    runs = []
    for split in ("development", "tuning", "held_out"):
        case_id = f"{split}-m25-02"
        case_root = root / split / case_id
        exp = exp_root / split
        if not exp.is_dir() and split == "development":
            exp = exp_root
        reads = case_root / "stages/m6_m2502/eligible_read1.fastq.gz"
        execution = _validate_experiment_execution(
            exp, reads, input_digests.get(case_id),
        )
        if execution["status"] == "COMPLETED":
            manifest = execution["manifest"]
            if manifest.get("case_id") != case_id or manifest.get("split") != split:
                execution = {
                    "status": "INCOMPLETE",
                    "reason": "execution record identifies a different case or partition",
                }
        row = {
            "split": split,
            "case_id": case_id,
            "execution_status": execution["status"],
            "execution_reason": execution.get("reason"),
        }
        if execution["status"] != "COMPLETED":
            row["status"] = execution["status"]
            runs.append(row)
            continue
        alternative_path = execution["contigs_path"]
        support_path = exp / "read_support.json"
        if not support_path.is_file():
            row.update(
                status="INCOMPLETE",
                read_back_support={"status": "NOT_EVALUATED", "reason": "read_support.json is missing"},
            )
            runs.append(row)
            continue
        try:
            support = _json(support_path)
            support_contigs = support.get("contigs", [])
            actual_contigs = m25_read_coverage._fasta(alternative_path)
            mapper = support.get("mapper_execution", {})
            frozen_thresholds = _json(case_root / "stages/m6_m2502/read_support.json").get("configuration")
            sam_path = exp / "support_alignments.sam"
            read_ids, read_metadata = _fastq_with_metadata(reads)
            support_ids = {item.get("contig_id") for item in support_contigs}
            actual_ids = {item[0] for item in actual_contigs}
            if (support.get("schema") != "m28-experimental-read-support-v1"
                    or support.get("status") != "EVALUATED"
                    or mapper.get("return_code") != 0
                    or mapper.get("input_reads_sha256") != _sha_file(reads)
                    or mapper.get("contigs_sha256") != _sha_file(alternative_path)
                    or mapper.get("query_count") != len(read_ids)
                    or not sam_path.is_file()
                    or mapper.get("sam_sha256") != _sha_file(sam_path)
                    or mapper.get("thresholds") != frozen_thresholds
                    or support_ids != actual_ids
                    or len(support_contigs) != len(actual_contigs)
                    or any(item.get("contig_length") != len(dict(actual_contigs)[item["contig_id"]])
                           for item in support_contigs)):
                raise ValueError("read-support evidence is missing, mismatched, or incomplete")
            reassessed = read_support.assess_read_support(
                sam_path, alternative_path, read_metadata, paired=False,
                thresholds=frozen_thresholds,
            )
            if (reassessed["status"] != support.get("aggregate_status")
                    or reassessed["contigs"] != support_contigs):
                raise ValueError("read-support result does not match its SAM evidence")
            read_evidence = _read_support_diagnostics(reassessed, frozen_thresholds)
        except (OSError, ValueError, AttributeError, TypeError) as error:
            row.update(
                status="INCOMPLETE",
                read_back_support={"status": "NOT_EVALUATED", "reason": str(error)},
            )
            runs.append(row)
            continue
        truth = _json(case_root / "heldout_truth.json")["cases"][0]["candidate_sequence"]
        default_stage = case_root / "stages/m6_m2502"
        default_candidates = m25_read_coverage._fasta(
            default_stage / "candidate_sequences.fasta"
        )
        support_by_id = {item["contig_id"]: item for item in support_contigs}
        def compare(candidates):
            rows = []
            for name, sequence in candidates:
                evidence = m25_read_coverage.diagnose_sequence(truth, sequence)
                record = {
                    "candidate_id": name,
                    "length": len(sequence),
                    "sequence_sha256": _sha(sequence.encode("ascii")),
                    "exact_recovery": evidence["strand_exact_match"],
                    "target_coverage": evidence["target_coverage"],
                    "full_length_sequence_identity": evidence["full_length_sequence_identity"],
                }
                if name in support_by_id:
                    sr = support_by_id[name]
                    record["read_support"] = {
                        "status": sr.get("status"),
                        "supporting_read_count": sr.get("supporting_read_count"),
                        "qualifying_supporting_read_count": sr.get("supporting_read_count"),
                        "distinct_sequence_count": sr.get("distinct_sequence_count"),
                        "distinct_fragment_count": sr.get("distinct_fragment_count"),
                        "coverage_breadth": sr.get("coverage_breadth"),
                        "mean_depth": sr.get("mean_depth"),
                    }
                rows.append(record)
            return rows
        execution_manifest = execution["manifest"]
        support_counts = Counter(item.get("status", "UNSPECIFIED") for item in support_contigs)
        support_categories = {
            "supported": {"READ_SUPPORTED_ASSEMBLY"},
            "low_support": {"LOW_SUPPORT_ASSEMBLY", "AMBIGUOUS_ASSEMBLY"},
            "unsupported": {"UNSUPPORTED_ASSEMBLY"},
        }
        candidate_sequences = dict(actual_contigs)
        support_summary = {
            category: [
                {
                    "contig_id": item["contig_id"],
                    "length": item.get("contig_length"),
                    "sequence_sha256": _sha(candidate_sequences[item["contig_id"]].encode("ascii")),
                    "status": item.get("status"),
                }
                for item in support_contigs if item.get("status") in statuses
            ]
            for category, statuses in support_categories.items()
        }
        row.update({
            "status": "COMPLETE",
            "input_manifest_sha256": execution_manifest["input_manifest_sha256"],
            "eligible_reads_sha256": execution_manifest["input"]["sha256"],
            "assembler_execution": {
                "status": execution_manifest["status"],
                "return_code": execution_manifest["return_code"],
                "command_parameters": execution_manifest["command_parameters"],
                "memory_gb": execution_manifest["memory_gb"],
                "memory_mb": execution_manifest["memory_mb"],
                "memory_metadata_correction": execution_manifest.get("memory_metadata_correction"),
                "duration_seconds": execution_manifest.get("duration_seconds"),
                "output": execution_manifest["output"],
            },
            "configuration_A": {
                "label": "unchanged production default",
                "parameters": _json(default_stage / "assembly/assembly_manifest.json").get("parameters"),
                "candidates": compare(default_candidates),
            },
            "experimental_configuration_B": {
                "label": "experimental only; explicit k=21,33",
                "execution_status": "COMPLETED",
                "return_code": execution_manifest["return_code"],
                "parameters": execution_manifest["command_parameters"],
                "output_sha256": execution_manifest["output"]["sha256"],
                "candidates": compare(actual_contigs),
                "read_support": {
                    "status": support["status"],
                    "aggregate_status": support["aggregate_status"],
                    "contig_status_counts": dict(sorted(support_counts.items())),
                    "candidates_by_support": support_summary,
                    "read_evidence": read_evidence,
                    "mapper_execution": support["mapper_execution"],
                },
                "assembly_graph": _graph_summary(exp),
            },
        })
        runs.append(row)
    complete = [run for run in runs if run["status"] == "COMPLETE"]
    return {
        "status": "COMPLETE" if len(complete) == 3 else "PARTIAL",
        "design": "Paired same-input comparisons across frozen development, tuning and held-out partitions.",
        "runs": runs,
        "complete_partition_count": len(complete),
        "interpretation_limit": "Truth was used only after assembly. Read-back status applies the M6 thresholds recorded for the matching frozen baseline case; no production threshold or default changed.",
    }


def analyze(baseline_root, m20_root=None, experiment_root=None):
    root = Path(baseline_root).resolve()
    report_path = root / "m25-read-coverage.json"
    report = _json(report_path)
    cases = []
    repeat_cases = []
    for case in report.get("cases", []):
        split = case["case_id"].split("-m25-")[0]
        run = root / split / case["case_id"]
        truth_path = run / "heldout_truth.json"
        truth = None
        if truth_path.is_file():
            truth_rows = _json(truth_path).get("cases", [])
            if truth_rows:
                truth = truth_rows[0].get("candidate_sequence")
        input_path = run / "inputs/datasets" / case["analysis_id"] / "reads.fastq.gz"
        reads = _fastq(input_path) if input_path.is_file() else []
        eligible_path = run / "stages" / f"m6_{case['analysis_id']}" / "eligible_read1.fastq.gz"
        eligible = _fastq(eligible_path) if eligible_path.is_file() else []
        row = {
            "case_id": case["case_id"],
            "split": split,
            "positive": case["positive"],
            "input_manifest_sha256": case.get("input_manifest_sha256"),
            "generated_read_count": len(reads),
            "generated_read_lengths": dict(sorted(Counter(len(x[1]) for x in reads).items())),
            "generated_coverage": case.get("coverage"),
            "assembly_eligible_read_count": len(eligible),
            "failure_class": _failure_class(run, case),
            "workflow_status": case.get("workflow_status"),
            "assembler_status": case.get("pipeline", {}).get("assembler_status"),
            "assembly_execution": _assembly_execution(
                run / "stages" / f"m6_{case['analysis_id']}"
            ),
            "assembly_graph": _graph_summary(
                run / "stages" / f"m6_{case['analysis_id']}"
            ),
            "candidate_evidence": _candidate_summary(
                run / "stages" / f"m6_{case['analysis_id']}"
            ),
            "candidate_count": case.get("pipeline", {}).get("candidate_count"),
            "exact_recovery": case.get("pipeline", {}).get("exact_recovery"),
            "partial_recovery": case.get("pipeline", {}).get("partial_recovery"),
            "negative_control_candidate_count": (
                case.get("pipeline", {}).get("candidate_count", 0) or 0
                if not case["positive"] else None
            ),
        }
        if truth:
            diag = sequence_diagnostics(truth)
            diag["known_truth_used_retrospectively"] = True
            diag["read_length_relative_to_k"] = {
                str(length): length / diag["k"] for length in sorted({len(x[1]) for x in reads})
            }
            diag["repeat_complexity_label"] = case.get("repeat_complexity")
            row["synthetic_target_diagnostics"] = diag
            repeat_cases.append((case["case_id"], diag))
        cases.append(row)
    positives = [x for x in cases if x["positive"]]
    negatives = [x for x in cases if not x["positive"]]
    summary = {
        "case_count": len(cases),
        "positive_cases": len(positives),
        "target_absent_controls": len(negatives),
        "exact_recoveries": sum(bool(x["exact_recovery"]) for x in positives),
        "partial_recoveries": sum(bool(x["partial_recovery"]) for x in positives),
        "candidate_records": sum(
            x.get("candidate_evidence", {}).get("candidate_count", 0) for x in cases
        ),
        "below_full_support_candidates": sum(
            x.get("candidate_evidence", {}).get("below_full_support_count", 0) for x in cases
        ),
        "distinct_below_full_support_sequence_hashes": len({
            digest for x in cases
            for digest in x.get("candidate_evidence", {}).get(
                "below_full_support_distinct_hashes", []
            )
        }),
        "unique_candidate_sequence_hashes": len({
            digest for x in cases
            for digest in x.get("candidate_evidence", {}).get("candidate_hashes", [])
        }),
        "negative_control_cases_with_candidates": sum(
            (x["negative_control_candidate_count"] or 0) > 0 for x in negatives
        ),
        "failure_classes": dict(sorted(Counter(x["failure_class"] for x in cases).items())),
        "baseline_manifest_digests_match_m24": all(
            x.get("input_manifest_matches_m24")
            for x in report.get("baseline", {}).values()
        ),
    }
    controlled_experiment = _experimental_comparison(root, experiment_root)
    return {
        "schema": SCHEMA,
        "synthetic_only": True,
        "biological_data_used": False,
        "external_biological_references_used": False,
        "baseline_commit": report.get("baseline_commit"),
        "source_report_sha256": _sha(report_path.read_bytes()),
        "historical_evidence": {
            "status": "DOCUMENTED_NOT_INDEPENDENTLY_REVERIFIED",
            "source_documents": [
                "docs/M25_SYNTHETIC_READ_COVERAGE.md",
                "docs/M26_SAM_VALIDATION_CANDIDATE_EVIDENCE.md",
                "docs/M27_LOW_COMPLEXITY_TRIAGE_VALIDATION.md",
            ],
            "note": "Prior report claims are historical evidence; their original run outputs are not included in this checkout.",
        },
        "summary": summary,
        "cases": cases,
        "m20_integration": _m20_summary(m20_root),
        "controlled_experiment": controlled_experiment,
        "follow_up_evidence_status": {
            "original_experimental_results": "DOCUMENTED_HISTORICAL_RESULTS",
            "current_verification": "REPORT_METADATA_AND_TESTS_ONLY; EXPERIMENTS_NOT_RERUN",
            "unavailable_evidence": [
                "original experimental eligible-read FASTQ files",
                "original experimental SAM alignment files",
            ],
            "per_partition": {
                run["split"]: {
                    "total_input_reads_historically_recorded": (
                        run["experimental_configuration_B"]["read_support"]
                        .get("mapper_execution", {}).get("query_count", "NOT_SUPPLIED")
                    ),
                    "mapped_primary_reads": (
                        run["experimental_configuration_B"]["read_support"]["read_evidence"]
                        ["primary_reads"]["mapped"]
                        if run["experimental_configuration_B"]["read_support"].get("read_evidence")
                        else "NOT_SUPPLIED"
                    ),
                    "unmapped_primary_reads": (
                        run["experimental_configuration_B"]["read_support"]["read_evidence"]
                        ["primary_reads"]["unmapped"]
                        if run["experimental_configuration_B"]["read_support"].get("read_evidence")
                        else "NOT_SUPPLIED"
                    ),
                    "per_contig_qualifying_support_counts": (
                        "AVAILABLE_FROM_VALIDATED_SAM"
                        if run["experimental_configuration_B"]["read_support"].get("read_evidence")
                        else "NOT_SUPPLIED"
                    ),
                }
                for run in controlled_experiment.get("runs", [])
                if run.get("status") == "COMPLETE"
            },
            "scientific_limitation": FOLLOW_UP_SCIENTIFIC_LIMITATION,
        },
        "graph_diagnostics": {
            "status": (
                "AVAILABLE_FOR_SOME_COMPLETED_ASSEMBLIES"
                if any(c["assembly_graph"]["status"] == "AVAILABLE" for c in cases)
                else "NOT_AVAILABLE"
            ),
            "basis": "Counts are parsed from preserved SPAdes GFA files; missing graph files remain unavailable, not inferred.",
        },
        "controlled_experiments": {
            "status": controlled_experiment["status"],
            "reason": "Execution and read-back outcomes are derived from persisted partition-level evidence in controlled_experiment.",
        },
        "verification": {
            "status": "NOT_RECORDED_IN_REPORT_INPUTS",
            "note": "Test and CI outcomes must be taken from current test output and final PR-head checks; no verification artifacts were supplied to this report generator.",
        },
        "promotion_decision": "RETAIN_EXISTING_PRODUCTION_DEFAULT",
        "governance": GOVERNANCE,
    }


def render_markdown(result):
    s = result["summary"]
    experiment = result["controlled_experiment"]
    experiment_runs = [x for x in experiment.get("runs", []) if x.get("status") == "COMPLETE"]
    lines = [
        "# M28 synthetic assembly failure diagnostics",
        "",
        "## Scope and decision",
        "",
        "Retrospective analysis of deterministic artificial A/C/G/T M25–M27 fixtures only. "
        "Synthetic truth is used only for diagnostics; it is not supplied to assembly or candidate ranking.",
        "",
        f"**Decision: {result['promotion_decision'].replace('_', ' ').lower()}.**",
        "No experimental configuration is promoted. Existing M6 and assembly defaults remain unchanged.",
        "",
        "## Evidence status",
        "",
        "- Original experimental results: documented historical results; three k=21,33 assemblies completed, yielding 60 contigs recorded as unsupported under frozen M6 thresholds, with no exact recovery.",
        "- Current verification: report metadata and code/test changes only; the experiments were not rerun.",
        "- Unavailable evidence: original experimental eligible-read FASTQ and SAM files; mapped/unmapped counts and alignment-rejection attribution are not supplied.",
        "",
        result.get("follow_up_evidence_status", {}).get(
            "scientific_limitation", FOLLOW_UP_SCIENTIFIC_LIMITATION
        ),
        "",
        "## Frozen baseline",
        "",
        f"- Cases: {s['case_count']} ({s['positive_cases']} positive; {s['target_absent_controls']} target-absent controls).",
        f"- Exact recovery: {s['exact_recoveries']}/{s['positive_cases']}.",
        f"- Partial recovery: {s['partial_recoveries']}/{s['positive_cases']}.",
        f"- Negative-control cases with candidates: {s['negative_control_cases_with_candidates']}.",
        f"- M24 input-manifest digests reproduced: {s['baseline_manifest_digests_match_m24']}.",
        f"- Baseline source commit: `{result['baseline_commit']}`.",
        f"- Candidate records / distinct sequence hashes: {s['candidate_records']} / {s['unique_candidate_sequence_hashes']}.",
        f"- Below-full-support records / distinct hashes: {s['below_full_support_candidates']} / "
        f"{s['distinct_below_full_support_sequence_hashes']}.",
        "",
        "## Assembler failure diagnosis",
        "",
        f"Failure classes across all cases: `{json.dumps(s['failure_classes'], sort_keys=True)}`.",
        "",
        "Failure attribution is derived from persisted M6 stage manifests and reconstruction evidence. A missing "
        "output is not treated as proof of assembler failure; upstream failure and zero eligible reads remain "
        "separate categories. Prior M25–M27 reports contain historical incident descriptions, but their original "
        "run outputs are unavailable here and those details are not independently reverified by this report.",
        "",
        "Configured timeout/output limits are cooperative, not hard operating-system resource quotas.",
        "",
        "## Case-level assembly outcomes",
        "",
        "| Case | Eligible reads | Assembly status | Failure classification | Exact | Partial |",
        "|---|---:|---|---|---|---|",
    ]
    for c in result["cases"]:
        lines.append(
            f"| {c['case_id']} | {c['assembly_eligible_read_count']} | "
            f"{c['assembler_status']} | {c['failure_class']} | "
            f"{c['exact_recovery']} | {c['partial_recovery']} |"
        )
    lines.extend([
        "",
        "## Graph evidence and limitations",
        "",
        "Where SPAdes GFA files were retained, the JSON reports segment and link counts, terminal segments, branches, "
        "coverage tags, and file hashes. These graph summaries are descriptive and do not establish the unique correct path. "
        "Cases without GFA remain unavailable.",
        "",
        "## Repeat and candidate evidence",
        "",
        "Per-target entropy, exact k-mer uniqueness/multiplicity and spacing summaries use known synthetic truth only "
        "retrospectively. Candidate sequence hashes, lengths and support states are included in the JSON. Repeated "
        "candidate records are not independent reconstructions; no unsupported extension was filled from truth.",
        "",
        "## Controlled experiments and promotion",
        "",
        (
            "Paired experiments used identical eligible reads within each frozen partition:\n\n"
            "| Split | Default contigs | Experimental k=21,33 contigs | Default best breadth | Experimental best breadth | Exact recovery | Support (supported / low / unsupported) |\n"
            "|---|---:|---:|---:|---:|---|---|\n"
            + "\n".join(
                f"| {row['split']} | {len(row['configuration_A']['candidates'])} | "
                f"{len(row['experimental_configuration_B']['candidates'])} | "
                f"{max((x['target_coverage'] for x in row['configuration_A']['candidates']), default=0):.1%} | "
                f"{max((x['target_coverage'] for x in row['experimental_configuration_B']['candidates']), default=0):.1%} | "
                f"{any(x['exact_recovery'] for x in row['experimental_configuration_B']['candidates'])} | "
                f"{len(row['experimental_configuration_B']['read_support']['candidates_by_support']['supported'])} / "
                f"{len(row['experimental_configuration_B']['read_support']['candidates_by_support']['low_support'])} / "
                f"{len(row['experimental_configuration_B']['read_support']['candidates_by_support']['unsupported'])} |"
                for row in experiment_runs
            )
            + "\n\nThe unchanged default was not modified. Experimental contigs were evaluated against matching "
            "frozen M6 read-support thresholds. This synthetic comparison does not justify promotion."
            if experiment.get("status") == "COMPLETE"
            else "No paired experimental comparison was completed."
        ),
        "",
        "### Read-alignment and support evidence",
        "",
        "`UNSUPPORTED_ASSEMBLY` means no reads qualified under the configured M6 criteria; it does not mean no reads aligned. "
        "Mapped-primary rejection counts below overlap when a read fails more than one criterion. A contig with zero "
        "qualifying support is labeled separately according to whether any primary reads aligned to it.",
        "",
        "| Split | Total reads | Primary mapped | Primary unmapped | Mapped rejected by any criterion | MAPQ failures | Alignment-fraction failures | Identity failures | Other read-quality failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        *[
            (
                f"| {row['split']} | "
                f"{row['experimental_configuration_B']['read_support'].get('mapper_execution', {}).get('query_count', 'NOT_SUPPLIED')} | "
                "NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | "
                "NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED | NOT_SUPPLIED |"
                if not row["experimental_configuration_B"]["read_support"].get("read_evidence")
                else (
                    f"| {row['split']} | {evidence['primary_reads']['total_input_reads']} | "
                    f"{evidence['primary_reads']['mapped']} | {evidence['primary_reads']['unmapped']} | "
                    f"{evidence['primary_reads']['mapped_rejected_by_one_or_more_support_criteria']} | "
                    f"{evidence['mapped_reads_rejected_by_criterion']['mapq']} | "
                    f"{evidence['mapped_reads_rejected_by_criterion']['alignment_fraction']} | "
                    f"{evidence['mapped_reads_rejected_by_criterion']['sequence_identity']} | "
                    f"{evidence['mapped_reads_rejected_by_criterion']['other_read_quality']} |"
                )
            )
            for row in experiment_runs
            for evidence in [row["experimental_configuration_B"]["read_support"].get("read_evidence", {})]
        ],
        "",
        *(
            [
                "| Split | Contig | Mapped primary reads | Rejected mapped reads | Qualifying supporting reads | Zero-support interpretation |",
                "|---|---|---:|---:|---:|---|",
            ] + [
                (
                    f"| {row['split']} | `{contig['contig_id']}` | {contig['mapped_primary_read_count']} | "
                    f"{contig['rejected_mapped_primary_read_count']} | "
                    f"{contig['qualifying_supporting_read_count']} | "
                    f"{contig['zero_qualifying_support_interpretation'] or 'QUALIFYING_SUPPORT_PRESENT'} |"
                )
                for row in experiment_runs
                for contig in row["experimental_configuration_B"]["read_support"]
                .get("read_evidence", {}).get("contigs", [])
            ]
            if any(
                row["experimental_configuration_B"]["read_support"].get("read_evidence")
                for row in experiment_runs
            )
            else [
                "Per-contig mapped, rejected, and qualifying read counts: `NOT_SUPPLIED`; the original SAM evidence was unavailable."
            ]
        ),
        "",
        "Per-contig mapped/rejected read counts are `NOT_SUPPLIED` where the original SAM is unavailable; no values are inferred.",
        "",
        "SPAdes `-m 2` is recorded as 2 GB (2,048 MB) in the execution metadata; the value matches the actual command.",
        "",
        "## M20 integration",
        "",
        f"M20 execution summary: `{result['m20_integration']['status']}`. Available per-phase evidence is recorded "
        "in the companion JSON; missing artifacts remain unavailable and are not inferred.",
        "",
        "## Testing and CI",
        "",
        "Test and CI outcomes are not embedded in this scientific report. Use current test output and final-head "
        "GitHub Actions checks on the draft PR; historical test counts are not presented as current verification.",
        "",
        "All M28 analyses and assembly comparisons described here use artificial A/C/G/T fixtures.",
        "",
        "## Governance",
        "",
        "```text",
        "decision=INCOMPLETE",
        "overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION",
        "biological_execution_authorized=false",
        "```",
        "",
    ])
    return "\n".join(lines)


def run(baseline_root, output_dir, m20_root=None, experiment_root=None):
    result = analyze(baseline_root, m20_root, experiment_root)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "M28_SYNTHETIC_ASSEMBLY_FAILURE_DIAGNOSTICS.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output / "M28_SYNTHETIC_ASSEMBLY_FAILURE_DIAGNOSTICS.md").write_text(
        render_markdown(result), encoding="utf-8"
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--m20-root")
    parser.add_argument("--experiment")
    args = parser.parse_args(argv)
    result = run(args.baseline, args.output, args.m20_root, args.experiment)
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
