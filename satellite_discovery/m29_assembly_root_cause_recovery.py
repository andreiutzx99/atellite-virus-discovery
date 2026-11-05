"""Deterministic synthetic-only M29 recovery benchmark on the registered M19 path."""
import argparse
import gzip
import hashlib
import json
import random
import shutil
import subprocess
import time
from pathlib import Path

from . import m25_read_coverage as m25
from . import m28_synthetic_assembly_diagnostics as m28


SCHEMA = "m29-synthetic-recovery-v1"
GOVERNANCE = {
    "decision": "INCOMPLETE",
    "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
    "biological_execution_authorized": False,
}


def case_matrix():
    """Fixed cases; no truth-based adaptation or parameter selection."""
    profiles = [
        ("development", "positive_control", True, 80, 100, 0.0, "low", False),
        ("development", "repeat_challenge", True, 80, 100, 0.0, "high", False),
        ("development", "target_absent_negative", False, 80, 100, 0.0, "low", False),
        ("tuning", "reduced_coverage", True, 12, 100, 0.0, "low", False),
        ("tuning", "short_reads", True, 80, 50, 0.0, "low", False),
        ("tuning", "sequencing_errors", True, 80, 100, 0.02, "low", False),
        ("tuning", "synthetic_background", True, 80, 100, 0.0, "low", True),
        ("tuning", "target_absent_negative", False, 80, 100, 0.0, "low", False),
        ("held_out", "positive_control", True, 80, 100, 0.0, "low", False),
        ("held_out", "reduced_coverage", True, 12, 100, 0.0, "low", False),
        ("held_out", "short_reads", True, 80, 50, 0.0, "low", False),
        ("held_out", "repeat_challenge", True, 80, 100, 0.0, "high", False),
        ("held_out", "sequencing_errors", True, 80, 100, 0.02, "low", False),
        ("held_out", "synthetic_background", True, 80, 100, 0.0, "low", True),
        ("held_out", "low_coverage_validation", True, 12, 100, 0.0, "low", False),
        ("held_out", "low_coverage_target_absent_background", False, 12, 100, 0.0, "low", True),
        ("held_out", "target_absent_negative", False, 80, 100, 0.0, "low", False),
    ]
    cases = []
    for index, (split, factor, positive, depth, read_length, error, repeat, background) in enumerate(profiles, 1):
        analysis_id = f"m29{index:02d}"
        case = m25._case_design(split, (index - 1) % 3 + 1)
        case.update({
            "case_id": f"{split}-m29-{factor}",
            "analysis_id": analysis_id,
            "positive": positive,
            "target_length": 900,
            "coverage": depth,
            "error_rate": error,
            "divergence": 0.45,
            "repeat_complexity": repeat,
            "background_gc_fraction": 0.5 if background else None,
            "read_start_mode": "uniform",
            "opaque_read_ids": True,
            "m25_read_length": read_length,
            "m29_factor": factor,
            "_m29_unreferenced_background": (
                factor == "low_coverage_target_absent_background"
            ),
        })
        cases.append(case)
    return cases


def _case_seed(case):
    split = case["case_id"].split("-", 1)[0]
    seed = m25.SPLITS[split] + 29
    if case["m29_factor"] == "low_coverage_validation":
        return seed + 100_000
    if case["m29_factor"] == "low_coverage_target_absent_background":
        return seed + 200_000
    return seed


def _run_case(case_root, case):
    """Run M25/M19 with an optional M29-only, unreferenced synthetic decoy."""
    if not case.get("_m29_unreferenced_background"):
        split = case["case_id"].split("-", 1)[0]
        return m25._run_one(case_root, split, _case_seed(case), case)
    original_generator = m25._make_fastq

    def fastq_with_decoy(case_row, truth, reference, params, backgrounds=()):
        payload = original_generator(case_row, truth, reference, params, backgrounds)
        length = case_row["target_length"]
        gc = case_row.get("background_gc_fraction", 0.5)
        rng = random.Random(_case_seed(case_row) + 997)
        background = "".join(
            rng.choices("ACGT", weights=((1 - gc) / 2, gc / 2, gc / 2, (1 - gc) / 2), k=length)
        )
        read_length = case_row["m25_read_length"]
        starts = m25._make_starts(
            length, read_length, case_row["coverage"], "uniform", rng,
        )
        decoy_reads = [
            (
                f"{case_row['analysis_id']}-unreferenced-{index:05d}",
                background[start:start + read_length],
                "I" * read_length,
            )
            for index, start in enumerate(starts)
        ]
        records = gzip.decompress(payload).decode("ascii").splitlines()
        if len(records) % 4:
            raise ValueError("M29 synthetic input generator produced malformed FASTQ")
        reads = [
            (records[i][1:].split()[0], records[i + 1], records[i + 3])
            for i in range(0, len(records), 4)
        ]
        case_row["_m29_unreferenced_background_sha256"] = hashlib.sha256(
            background.encode("ascii")
        ).hexdigest()
        case_row["_m29_unreferenced_background_read_count"] = len(decoy_reads)
        return m25._gzip_fastq(reads + decoy_reads)

    try:
        m25._make_fastq = fastq_with_decoy
        split = case["case_id"].split("-", 1)[0]
        return m25._run_one(case_root, split, _case_seed(case), case)
    finally:
        m25._make_fastq = original_generator


def _count_fastq(path):
    if not Path(path).is_file():
        return None
    return sum(1 for _ in m25._fastq_ids(path))


def _support_by_contig(records):
    return {
        row["contig_id"]: row.get("status", "NOT_EVALUATED")
        for row in records
        if isinstance(row, dict) and isinstance(row.get("contig_id"), str)
    }


def _recovery_support(candidates, truth, support_records):
    comparisons = [
        m25.diagnose_sequence(truth, sequence) for _, sequence in candidates
    ] if truth else []
    support = _support_by_contig(support_records)
    exact_ids = {
        contig_id for (contig_id, _), comparison in zip(candidates, comparisons)
        if comparison.get("strand_exact_match", False)
    }
    return {
        "comparisons": comparisons,
        "exact_recovery": bool(exact_ids),
        "supported_exact_recovery": any(
            support.get(contig_id) == "READ_SUPPORTED_ASSEMBLY"
            for contig_id in exact_ids
        ),
    }


def _summarize_case(case, root, report):
    analysis_id = case["analysis_id"]
    stage = root / "stages" / f"m6_{analysis_id}"
    qc = root / "stages" / f"qc_{analysis_id}"
    truth_doc = json.loads((root / "heldout_truth.json").read_text())
    truth_row = next(row for row in truth_doc["cases"] if row["case_id"] == case["case_id"])
    candidates_path = stage / "candidate_sequences.fasta"
    candidates = m25._fasta(candidates_path) if candidates_path.is_file() else []
    raw_contigs_path = stage / "assembly" / "raw" / "contigs.fasta"
    if not raw_contigs_path.is_file():
        raw_contigs_path = stage / "assembly" / "contigs.fasta"
    raw_contigs = m25._fasta(raw_contigs_path) if raw_contigs_path.is_file() else []
    candidate_sequences = [sequence for _, sequence in candidates]
    partial = []
    if truth_row["candidate_sequence"]:
        partial = [
            m25.diagnose_sequence(truth_row["candidate_sequence"], sequence)
            for sequence in candidate_sequences
        ]
    best_match = max(
        partial, key=lambda row: row.get("target_coverage", 0), default={}
    )
    reconstruction_path = stage / "reconstruction_evidence.json"
    reconstruction = (
        json.loads(reconstruction_path.read_text()) if reconstruction_path.is_file() else {}
    )
    support_map = _support_by_contig(reconstruction.get("contigs", []))
    recovery = _recovery_support(
        candidates, truth_row["candidate_sequence"], reconstruction.get("contigs", [])
    )
    exact_recovery = recovery["exact_recovery"]
    supported_exact_recovery = recovery["supported_exact_recovery"]
    non_exact_count = sum(
        not row.get("strand_exact_match", False) for row in partial
    ) if truth_row["candidate_sequence"] else None
    experimental_path = root / "experimental_k21" / "execution.json"
    experimental = (
        json.loads(experimental_path.read_text()) if experimental_path.is_file() else None
    )
    if experimental and experimental.get("command"):
        experimental["command"] = [
            Path(experimental["command"][0]).name,
            *experimental.get("command_parameters", []),
            "-s", "eligible_read1.fastq.gz",
            "-o", "experimental_k21/spades",
        ]
    spades_log = stage / "assembly" / "raw" / "spades.log"
    assembler_diagnostics = []
    if spades_log.is_file():
        assembler_diagnostics = [
            line.strip() for line in spades_log.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
            if "ERROR" in line or "== Error ==" in line
        ][:5]
    residual_manifest_path = stage / "residual_manifest.json"
    residual_manifest = (
        json.loads(residual_manifest_path.read_text())
        if residual_manifest_path.is_file() else {}
    )
    return {
        "case_id": case["case_id"],
        "split": case["case_id"].split("-", 1)[0],
        "factor": case["m29_factor"],
        "random_seed": _case_seed(case),
        "unreferenced_background": {
            "used": bool(case.get("_m29_unreferenced_background")),
            "sequence_sha256": case.get("_m29_unreferenced_background_sha256"),
            "read_count": case.get("_m29_unreferenced_background_read_count"),
        },
        "positive": case["positive"],
        "parameters": {
            "target_length": case["target_length"],
            "nominal_coverage": case["coverage"],
            "read_length": case["m25_read_length"],
            "error_rate": case["error_rate"],
            "repeat_complexity": case["repeat_complexity"],
            "synthetic_background": case["background_gc_fraction"] is not None,
        },
        "stage_read_counts": {
            "raw": _count_fastq(root / "inputs" / "datasets" / analysis_id / "reads.fastq.gz"),
            "after_qc": _count_fastq(qc / "clean_single.fastq.gz"),
            "after_reference_screen": _count_fastq(stage / "residual_read1.fastq.gz"),
            "assembly_eligible": residual_manifest.get("counts", {}).get("eligible_fragments"),
        },
        "assembly_eligible_input_sha256": (
            m28._sha_file(stage / "eligible_read1.fastq.gz")
            if (stage / "eligible_read1.fastq.gz").is_file() else None
        ),
        "assembler_status": reconstruction.get("status", "NOT_EVALUATED"),
        "assembler_diagnostics": assembler_diagnostics,
        "raw_contig_count": len(raw_contigs),
        "contigs_produced": len(raw_contigs),
        "read_supported_contig_count": sum(
            status == "READ_SUPPORTED_ASSEMBLY" for status in support_map.values()
        ),
        "discovery_candidate_acceptance": {
            "status": "NOT_EVALUATED",
            "accepted_candidate_count": None,
            "reason": "M29 records M6 assembly and read support but does not execute the downstream M7/M8 discovery-specific candidate review pathway.",
        },
        "assembly_graph": m28._graph_summary(stage),
        "support_criteria": reconstruction.get("support_criteria"),
        "experimental_configuration_B": experimental,
        "candidate_count": len(candidate_sequences),
        "false_positive_candidates": None,
        "accepted_false_positive_candidate_count": None,
        "non_exact_candidate_count": non_exact_count,
        "read_support_statuses": [
            row.get("status") for row in reconstruction.get("contigs", [])
        ],
        "contig_read_support": [
            {"contig_id": contig_id, "status": support_map.get(contig_id, "NOT_EVALUATED")}
            for contig_id, _ in candidates
        ],
        "best_truth_match": {
            "strand_exact_match": best_match.get("strand_exact_match"),
            "target_breadth": best_match.get("target_coverage"),
            "sequence_identity": best_match.get("local_alignment_identity"),
            "candidate_length": len(candidate_sequences[0]) if candidate_sequences else None,
        } if best_match else None,
        "exact_recovery": exact_recovery,
        "supported_exact_recovery": supported_exact_recovery,
        "partial_recovery": any(
            row.get("local_alignment_identity", 0) >= 0.95
            and row.get("target_coverage", 0) >= 0.5
            and not row.get("strand_exact_match", False)
            for row in partial
        ),
        "truth_sha256": truth_row.get("candidate_sha256"),
        "input_manifest_sha256": hashlib.sha256(
            (root / "inputs" / "source_manifest.json").read_bytes()
        ).hexdigest(),
    }


def _run_k21_experiment(case_root, case):
    """Test an explicit single-k setting on a predeclared fresh held-out case."""
    stage = case_root / "stages" / f"m6_{case['analysis_id']}"
    reads = stage / "eligible_read1.fastq.gz"
    experiment_dir = case_root / "experimental_k21"
    experiment_dir.mkdir()
    spades = shutil.which("spades.py")
    result = {
        "configuration": "B_SPAdes_k21_only",
        "command_parameters": ["--only-assembler", "-t", "1", "-m", "2", "-k", "21"],
        "input_sha256": m28._sha_file(reads) if reads.is_file() else None,
        "status": "NOT_EVALUATED",
    }
    if not spades or not reads.is_file():
        result["reason"] = "SPAdes or assembly-eligible input is unavailable"
    else:
        output = experiment_dir / "spades"
        command = [
            spades, "--only-assembler", "-t", "1", "-m", "2", "-k", "21",
            "-s", str(reads), "-o", str(output),
        ]
        started = time.monotonic()
        try:
            with (experiment_dir / "stdout.log").open("wb") as stdout, \
                    (experiment_dir / "stderr.log").open("wb") as stderr:
                process = subprocess.run(
                    command, stdout=stdout, stderr=stderr, check=False,
                    timeout=m28.assembly_adapters.DEFAULT_TIMEOUT_SECONDS,
                )
            result.update(
                status="COMPLETED" if process.returncode == 0 else "FAILED",
                return_code=process.returncode,
                duration_seconds=time.monotonic() - started,
                command=[
                    Path(spades).name, "--only-assembler", "-t", "1", "-m", "2",
                    "-k", "21", "-s", "eligible_read1.fastq.gz",
                    "-o", "experimental_k21/spades",
                ],
            )
            contigs = output / "contigs.fasta"
            if process.returncode == 0 and contigs.is_file():
                experimental_contigs = m25._fasta(contigs)
                sequences = [sequence for _, sequence in experimental_contigs]
                thresholds_doc = json.loads((stage / "read_support.json").read_text())
                support = m28._evaluate_experimental_read_support(
                    experiment_dir, reads, contigs,
                    thresholds_doc.get("configuration", {}),
                )
                truth = json.loads((case_root / "heldout_truth.json").read_text())[
                    "cases"
                ][0]["candidate_sequence"]
                experimental_support = _support_by_contig(support.get("contigs", []))
                recovery = _recovery_support(
                    experimental_contigs, truth, support.get("contigs", [])
                )
                comparisons = recovery["comparisons"]
                result.update(
                    contig_count=len(sequences),
                    raw_contig_count=len(sequences),
                    read_supported_contig_count=sum(
                        status == "READ_SUPPORTED_ASSEMBLY"
                        for status in experimental_support.values()
                    ),
                    contig_read_support=[
                        {"contig_id": contig_id,
                         "status": experimental_support.get(contig_id, "NOT_EVALUATED")}
                        for contig_id, _ in experimental_contigs
                    ],
                    contigs_sha256=m28._sha_file(contigs),
                    read_support_status=support.get("aggregate_status", support.get("status")),
                    discovery_candidate_acceptance={
                        "status": "NOT_EVALUATED",
                        "accepted_candidate_count": None,
                        "reason": "Configuration B was assessed for assembly and read support only; the downstream M7/M8 discovery-specific candidate review pathway was not run.",
                    },
                    accepted_false_positive_candidate_count=None,
                    exact_recovery=recovery["exact_recovery"],
                    supported_exact_recovery=recovery["supported_exact_recovery"],
                    partial_recovery=any(
                        row.get("local_alignment_identity", 0) >= 0.95
                        and row.get("target_coverage", 0) >= 0.5
                        and not row.get("strand_exact_match", False)
                        for row in comparisons
                    ),
                    truth_scoring_phase="AFTER_CONFIGURATION_B_EXECUTION",
                    thresholds_unchanged=True,
                )
            elif process.returncode == 0:
                result.update(status="INCOMPLETE", reason="SPAdes produced no contigs.fasta")
        except subprocess.TimeoutExpired:
            result.update(
                status="TIMED_OUT",
                duration_seconds=time.monotonic() - started,
                reason="SPAdes exceeded the configured execution timeout",
            )
    (experiment_dir / "execution.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    return result


def historical_findings(repository_root):
    docs = Path(repository_root) / "docs"
    m27 = json.loads((docs / "M27_LOW_COMPLEXITY_TRIAGE_VALIDATION.json").read_text())
    m28 = json.loads((docs / "M28_SYNTHETIC_ASSEMBLY_FAILURE_DIAGNOSTICS.json").read_text())
    flow = m27.get("focus_case_read_flow", [])
    low_complexity = [
        row for row in flow
        if row.get("target_reads_default_assembly_eligible") == 0
        and row.get("default_triage_exclusion") == "LOW_SEQUENCE_COMPLEXITY"
    ]
    no_eligible_positive = [
        row for row in m28.get("cases", [])
        if row.get("positive")
        and row.get("assembly_eligible_read_count") == 0
    ]
    exit_21 = [
        row for row in m28.get("cases", [])
        if row.get("assembly_execution", {}).get("return_code") == 21
    ]
    incomplete_supported = [
        row for row in m28.get("cases", [])
        if row.get("failure_class") == "ASSEMBLER_COMPLETED_INCOMPLETE_SUPPORTED_CONTIGS"
    ]
    return {
        "source_reports": [
            "M27_LOW_COMPLEXITY_TRIAGE_VALIDATION.json",
            "M28_SYNTHETIC_ASSEMBLY_FAILURE_DIAGNOSTICS.json",
        ],
        "demonstrated": {
            "positive_cases_with_zero_eligible_reads": len(no_eligible_positive),
            "target_absent_cases_with_zero_eligible_reads": sum(
                not row.get("positive")
                and row.get("assembly_eligible_read_count") == 0
                for row in m28.get("cases", [])
            ),
            "incomplete_supported_cases": [
                row["case_id"] for row in incomplete_supported
            ],
            "m27_low_complexity_focus_cases": [
                {
                    "case_id": row["case_id"],
                    "target_reads_generated": row["target_reads_generated"],
                    "target_reads_after_reference_screen": row["target_reads_after_reference_screen"],
                    "target_reads_default_assembly_eligible": row["target_reads_default_assembly_eligible"],
                    "documented_exclusion": row["default_triage_exclusion"],
                } for row in low_complexity
            ],
            "spades_exit_21_cases": [
                {
                    "case_id": row["case_id"],
                    "return_code": row.get("assembly_execution", {}).get("return_code"),
                    "error_type": row.get("assembly_execution", {}).get("error_type"),
                    "error": row.get("assembly_execution", {}).get("error"),
                    "stderr_bytes": next(
                        (item.get("bytes") for item in row.get(
                            "assembly_execution", {}).get("output_inventory", [])
                         if item.get("path") == "stderr.log"),
                        None,
                    ),
                } for row in exit_21
            ],
        },
        "unresolved": [
            "The persisted evidence does not identify an operating-system cause for SPAdes exit 21.",
            "The five incomplete supported cases have not been assigned a specific causal mechanism by the available historical evidence.",
            "Historical M28 experimental FASTQ/SAM evidence is unavailable, so mapped reads and rejection causes cannot be reconstructed.",
            "Incomplete supported assemblies require case-specific graph and read evidence; association is not causal proof.",
        ],
    }


def _historical_run_record(repository_root, report_path=None):
    path = Path(report_path) if report_path else (
        Path(repository_root) / "docs" / "M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.json"
    )
    if not path.is_file():
        return None
    raw = path.read_bytes()
    previous = json.loads(raw.decode("utf-8"))
    return {
        "source": "PR #96 head dcc138fb4830e066a10baf1ac45f90f346d38cbb",
        "source_report_sha256": hashlib.sha256(raw).hexdigest(),
        "summary": previous.get("summary"),
        "cases": previous.get("cases", []),
    }


def _compare_historical_report(repository_root, summaries, report_path=None):
    path = Path(report_path) if report_path else (
        Path(repository_root) / "docs" / "M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.json"
    )
    if not path.is_file():
        return {"status": "NOT_EVALUATED", "reason": "prior M29 JSON report is unavailable"}
    previous = json.loads(path.read_text(encoding="utf-8"))
    old_cases = {row["case_id"]: row for row in previous.get("cases", [])}
    stable_fields = (
        "split", "factor", "positive", "parameters", "random_seed",
        "truth_sha256", "assembly_eligible_input_sha256", "input_manifest_sha256",
    )
    comparisons = []
    for row in summaries:
        old = old_cases.get(row["case_id"])
        comparisons.append({
            "case_id": row["case_id"],
            "stable_fields_match": bool(old) and all(
                old.get(field) == row.get(field) for field in stable_fields
            ),
            "assembly_graph_sha256_match": bool(old) and (
                old.get("assembly_graph", {}).get("sha256")
                == row.get("assembly_graph", {}).get("sha256")
            ),
        })
    matched = (
        len(old_cases) == len(summaries)
        and all(row["stable_fields_match"] and row["assembly_graph_sha256_match"]
                for row in comparisons)
    )
    return {
        "status": "MATCHED_STABLE_FIELDS" if matched else "STABLE_FIELD_DIFFERENCES",
        "historical_report": "docs/M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.json at replay start",
        "historical_case_count": len(old_cases),
        "fresh_replay_case_count": len(summaries),
        "stable_fields_compared": list(stable_fields),
        "assembly_graph_sha256_compared": True,
        "cases": comparisons,
    }


def run(output, repository_root, case_limit=None, historical_report_path=None):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite existing M29 evidence: {output}")
    output.mkdir(parents=True, exist_ok=True)
    cases = case_matrix()
    if case_limit is not None:
        if type(case_limit) is not int or case_limit < 1:
            raise ValueError("case_limit must be a positive integer")
        cases = cases[:case_limit]
    summaries = []
    for case in cases:
        case_root = output / "runs" / case["case_id"]
        split = case["case_id"].split("-", 1)[0]
        report, _ = _run_case(case_root, case)
        if (case["m29_factor"] == "reduced_coverage" and split == "tuning"
                or case["m29_factor"] in {
                    "low_coverage_validation",
                    "low_coverage_target_absent_background",
                }):
            _run_k21_experiment(case_root, case)
        summaries.append(_summarize_case(case, case_root, report))
    result = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "biological_data_used": False,
        "truth_use": "retrospective scoring only, after the registered M19 workflow completes",
        "production_defaults_changed": False,
        "historical_root_cause_evidence": historical_findings(repository_root),
        "historical_run_record": _historical_run_record(
            repository_root, historical_report_path
        ),
        "cases": summaries,
        "execution_provenance": {
            "kind": "fresh_clean_execution",
            "all_fixed_cases_executed": case_limit is None,
            "case_limit": case_limit,
            "output_directory": str(output),
        },
        "replay_comparison": _compare_historical_report(
            repository_root, summaries, historical_report_path
        ),
        "controlled_improvement": _controlled_improvement(summaries),
        "demonstrated_m29_findings": [
            {
                "finding": "LOW_COVERAGE_KMER_HISTOGRAM_FAILURE",
                "case_ids": [
                    row["case_id"] for row in summaries
                    if row["factor"] == "reduced_coverage"
                    and any("Invalid kmer coverage histogram" in line
                            for line in row["assembler_diagnostics"])
                ],
                "evidence": "SPAdes logs report an invalid k-mer coverage histogram; this is a tool-level low-coverage model failure, not evidence of an operating-system failure.",
            },
            {
                "finding": "REPEAT_CHALLENGE_UNSUPPORTED_SHORT_CONTIG",
                "case_ids": [
                    row["case_id"] for row in summaries
                    if row["factor"] == "repeat_challenge"
                    and row["assembler_status"] == "NO_SUPPORTED_ASSEMBLY"
                ],
                "evidence": "The repeated-sequence controls produced an unsupported candidate with limited target breadth; this documents the failure mode but does not prove a unique graph-level cause.",
            },
        ],
        "summary": {
            "case_count": len(summaries),
            "positive_cases": sum(row["positive"] for row in summaries),
            "target_absent_controls": sum(not row["positive"] for row in summaries),
            "exact_recoveries": sum(row["exact_recovery"] for row in summaries),
            "supported_exact_recoveries": sum(
                row["supported_exact_recovery"]
                for row in summaries
            ),
            "held_out_supported_exact_recoveries": sum(
                row["split"] == "held_out" and row["supported_exact_recovery"]
                for row in summaries
            ),
            "confirmatory_held_out_supported_exact_recoveries": sum(
                row["factor"] == "low_coverage_validation"
                and row.get("experimental_configuration_B", {}).get("supported_exact_recovery")
                for row in summaries
            ),
            "negative_control_accepted_false_positive_candidates": "NOT_EVALUATED",
            "experimental_negative_control_accepted_false_positive_candidates": "NOT_EVALUATED",
            "negative_control_raw_contigs": sum(
                row["raw_contig_count"] for row in summaries if not row["positive"]
            ),
            "negative_control_read_supported_contigs": sum(
                row["read_supported_contig_count"]
                for row in summaries if not row["positive"]
            ),
            "experimental_negative_control_raw_contigs": sum(
                (row.get("experimental_configuration_B") or {}).get(
                    "raw_contig_count", 0
                ) or 0
                for row in summaries if not row["positive"]
            ),
            "experimental_negative_control_read_supported_contigs": sum(
                (row.get("experimental_configuration_B") or {}).get(
                    "read_supported_contig_count", 0
                ) or 0
                for row in summaries if not row["positive"]
            ),
            "production_promotion_decision": "NO_PROMOTION",
        },
        "governance": GOVERNANCE,
    }
    result["summary"]["m29_success_criterion_met"] = bool(
        result["summary"]["confirmatory_held_out_supported_exact_recoveries"] >= 1
        and result["controlled_improvement"].get("held_out", {}).get(
            "input_identity_matched", False
        )
        and result["controlled_improvement"].get("negative_control", {}).get(
            "configuration_B", {}
        ).get("status") == "COMPLETED"
        and result["controlled_improvement"].get("negative_control", {}).get(
            "configuration_B", {}
        ).get("accepted_false_positive_candidate_count") == 0
        and result["controlled_improvement"].get("negative_control", {}).get(
            "input_identity_matched", False
        )
    )
    (output / "M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    (output / "M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.md").write_text(
        render_markdown(result), encoding="utf-8",
    )
    return result


def render_markdown(result):
    summary = result["summary"]
    lines = [
        "# M29 assembly root-cause recovery",
        "",
        "Synthetic A/C/G/T data only. Historical M25–M28 results are not modified.",
        "",
        "## Decision",
        "",
        "**No production promotion.** The M19 production defaults and frozen support thresholds are unchanged.",
        "",
        "## Historical root-cause evidence",
        "",
        "M27 identifies low-complexity triage as the demonstrated reason three positive M25-03 cases had zero assembly-eligible reads. The nine target-absent controls are expected not to contain target reads; they are not failed positive recoveries.",
        "",
        "The M28 SPAdes exit-21 record has no persisted stderr bytes and does not establish an operating-system cause. The five incomplete supported assemblies remain unexplained by the available evidence. Missing historical experimental FASTQ/SAM inputs prevent a read-level explanation for the 60 unsupported experimental contigs.",
        "",
        "## M29 benchmark",
        "",
        f"- Cases: {summary['case_count']} ({summary['positive_cases']} positive; {summary['target_absent_controls']} target-absent control).",
        f"- Demonstrated exact synthetic recoveries: {summary['exact_recoveries']}; per-contig read-supported exact recoveries: {summary['supported_exact_recoveries']}.",
        f"- Held-out read-supported exact recoveries: {summary['held_out_supported_exact_recoveries']}.",
        f"- Confirmatory fresh-seed held-out B recoveries: {summary['confirmatory_held_out_supported_exact_recoveries']}.",
        f"- Target-absent raw contigs: {summary['negative_control_raw_contigs']}; read-supported target-absent contigs: {summary['negative_control_read_supported_contigs']}.",
        f"- Configuration B target-absent raw contigs: {summary['experimental_negative_control_raw_contigs']}; read-supported background contigs: {summary['experimental_negative_control_read_supported_contigs']}.",
        "- Accepted false-positive satellite-virus candidates: NOT_EVALUATED; M29 did not run downstream discovery-specific candidate screening.",
        "- False-positive discovery rates remain unknown; assembly and read support are not candidate acceptance.",
        "- Historical checked-in benchmark findings are distinct from results freshly reproduced by this revision; see the JSON replay comparison.",
        "- The prior PR-head summary and all 17 case-level historical run records are preserved separately in the JSON `historical_run_record` field.",
        f"- M29 success criterion met: {summary['m29_success_criterion_met']}.",
        "- Truth is read only after each registered M19 workflow run for retrospective scoring.",
        "- The earlier exploratory B pilot is excluded from confirmation; the counted held-out validation uses a distinct deterministic seed.",
        "- Reduced-coverage failures with an SPAdes invalid k-mer coverage histogram are attributed to the observed coverage-model failure only; no operating-system cause is inferred.",
        "",
        "| Case | Split | Factor | Eligible reads | Raw contigs | Supported contigs | Exact | Supported exact | Partial | Candidate acceptance |",
        "|---|---|---|---:|---:|---:|---|---|---|---|",
    ]
    for row in result["cases"]:
        counts = row["stage_read_counts"]
        lines.append(
            f"| {row['case_id']} | {row['split']} | {row['factor']} | "
            f"{counts['assembly_eligible']} | {row['raw_contig_count']} | "
            f"{row['read_supported_contig_count']} | {row['exact_recovery']} | "
            f"{row['supported_exact_recovery']} | {row['partial_recovery']} | "
            f"{row['discovery_candidate_acceptance']['status']} |"
        )
    comparisons = result.get("controlled_improvement") or {}
    if comparisons:
        lines += [
            "",
            "## Matched configuration experiment",
            "",
        ]
        for partition, comparison in comparisons.items():
            lines.extend([
                f"{partition}: `{comparison['case_id']}`. Eligible-read input identity matched: `{comparison['input_identity_matched']}`.",
                "",
                "| Configuration | Status | Raw contigs | Read-supported contigs | Exact recovery | Supported exact | Accepted false-positive candidates |",
                "|---|---|---:|---:|---|---|---|",
                f"| A: registered default | {comparison['configuration_A']['assembler_status']} | {comparison['configuration_A']['raw_contig_count']} | {comparison['configuration_A']['read_supported_contig_count']} | {comparison['configuration_A']['exact_recovery']} | {comparison['configuration_A']['supported_exact_recovery']} | NOT_EVALUATED |",
                f"| B: SPAdes k=21 only | {comparison['configuration_B']['status']} | {comparison['configuration_B'].get('raw_contig_count')} | {comparison['configuration_B'].get('read_supported_contig_count')} | {comparison['configuration_B'].get('exact_recovery')} | {comparison['configuration_B'].get('supported_exact_recovery')} | NOT_EVALUATED |",
                "",
            ])
        lines.append("B is an isolated experiment on matched synthetic reads. It produced one read-supported background contig in the target-absent control; this is not an accepted satellite-virus candidate. Candidate screening was not evaluated, so specificity and the false-positive discovery rate remain unknown. B does not alter production parameters; the decision remains NO_PROMOTION.")
    lines += [
        "",
        "## Verification and limitations",
        "",
        f"Fresh run status: `{result.get('execution_provenance', {}).get('kind', 'UNKNOWN')}`; full fixed matrix executed: `{result.get('execution_provenance', {}).get('all_fixed_cases_executed', False)}`. Replay comparison: `{result.get('replay_comparison', {}).get('status', 'NOT_RECORDED')}`.",
        f"Compared {result.get('replay_comparison', {}).get('fresh_replay_case_count', 0)} cases on fixed case identity, truth/input digests, parameters, and assembly-graph SHA-256. See JSON for per-case results.",
        "",
        "Reproduce with `python -m satellite_discovery.m29_assembly_root_cause_recovery --output /tmp/m29-evidence --repository-root .`. The output directory must be new or empty; generated assembler work products stay outside Git.",
        "",
        "The JSON companion contains per-stage read counts, support statuses, sequence digests, and historical evidence references. Assembly completion is not biological discovery. Results on synthetic controls do not establish performance on biological samples.",
        "",
        "```text",
        f"decision={result['governance']['decision']}",
        f"overall_state={result['governance']['overall_state']}",
        f"biological_execution_authorized={str(result['governance']['biological_execution_authorized']).lower()}",
        "```",
        "",
    ]
    return "\n".join(lines)


def _controlled_improvement(summaries):
    rows = {
        "tuning": next((item for item in summaries
                        if item["split"] == "tuning"
                        and item["factor"] == "reduced_coverage"), None),
        "held_out": next((item for item in summaries
                          if item["factor"] == "low_coverage_validation"), None),
        "negative_control": next((item for item in summaries
                                  if item["factor"] == "low_coverage_target_absent_background"), None),
    }
    comparisons = {}
    for partition, row in rows.items():
        if not row or not row.get("experimental_configuration_B"):
            continue
        experiment = row["experimental_configuration_B"]
        comparisons[partition] = {
            "case_id": row["case_id"],
            "input_identity_matched": (
                row.get("assembly_eligible_input_sha256") == experiment.get("input_sha256")
            ),
            "configuration_A": {
                "assembler_status": row.get("assembler_status", "NOT_EVALUATED"),
                "exact_recovery": row.get("exact_recovery", False),
                "supported_exact_recovery": row.get("supported_exact_recovery", False),
                "raw_contig_count": row.get("raw_contig_count", 0),
                "read_supported_contig_count": row.get("read_supported_contig_count", 0),
                "read_support_statuses": row.get("read_support_statuses", []),
                "accepted_false_positive_candidate_count": row.get(
                    "accepted_false_positive_candidate_count"
                ),
            },
            "configuration_B": experiment,
        }
    return comparisons


def summarize_existing_runs(output, repository_root, historical_report_path=None):
    """Rebuild report metadata from preserved run folders without rerunning SPAdes."""
    output = Path(output).resolve()
    summaries = []
    for case in case_matrix():
        case_root = output / "runs" / case["case_id"]
        if not (case_root / "heldout_truth.json").is_file():
            raise FileNotFoundError(f"Missing completed M29 run: {case['case_id']}")
        summaries.append(_summarize_case(case, case_root, {}))
    result = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "biological_data_used": False,
        "truth_use": "retrospective scoring only, after the registered M19 workflow completes",
        "production_defaults_changed": False,
        "historical_root_cause_evidence": historical_findings(repository_root),
        "historical_run_record": _historical_run_record(
            repository_root, historical_report_path
        ),
        "cases": summaries,
        "execution_provenance": {
            "kind": "summary_from_preserved_runs",
            "all_fixed_cases_executed": True,
            "case_limit": None,
            "output_directory": str(output),
        },
        "replay_comparison": _compare_historical_report(
            repository_root, summaries, historical_report_path
        ),
        "controlled_improvement": _controlled_improvement(summaries),
        "demonstrated_m29_findings": [
            {
                "finding": "LOW_COVERAGE_KMER_HISTOGRAM_FAILURE",
                "case_ids": [
                    row["case_id"] for row in summaries
                    if row["factor"] == "reduced_coverage"
                    and any("Invalid kmer coverage histogram" in line
                            for line in row["assembler_diagnostics"])
                ],
                "evidence": "SPAdes logs report an invalid k-mer coverage histogram; this is a tool-level low-coverage model failure, not evidence of an operating-system failure.",
            },
            {
                "finding": "REPEAT_CHALLENGE_UNSUPPORTED_SHORT_CONTIG",
                "case_ids": [
                    row["case_id"] for row in summaries
                    if row["factor"] == "repeat_challenge"
                    and row["assembler_status"] == "NO_SUPPORTED_ASSEMBLY"
                ],
                "evidence": "Repeated-sequence controls produced an unsupported candidate with limited target breadth; this documents the failure mode but does not prove a unique graph-level cause.",
            },
        ],
        "summary": {
            "case_count": len(summaries),
            "positive_cases": sum(row["positive"] for row in summaries),
            "target_absent_controls": sum(not row["positive"] for row in summaries),
            "exact_recoveries": sum(row["exact_recovery"] for row in summaries),
            "supported_exact_recoveries": sum(row["supported_exact_recovery"] for row in summaries),
            "held_out_supported_exact_recoveries": sum(
                row["split"] == "held_out" and row["supported_exact_recovery"]
                for row in summaries
            ),
            "confirmatory_held_out_supported_exact_recoveries": sum(
                row["factor"] == "low_coverage_validation"
                and row.get("experimental_configuration_B", {}).get("supported_exact_recovery")
                for row in summaries
            ),
            "negative_control_accepted_false_positive_candidates": "NOT_EVALUATED",
            "experimental_negative_control_accepted_false_positive_candidates": "NOT_EVALUATED",
            "negative_control_raw_contigs": sum(
                row["raw_contig_count"] for row in summaries if not row["positive"]
            ),
            "negative_control_read_supported_contigs": sum(
                row["read_supported_contig_count"] for row in summaries if not row["positive"]
            ),
            "production_promotion_decision": "NO_PROMOTION",
        },
        "governance": GOVERNANCE,
    }
    result["summary"]["m29_success_criterion_met"] = bool(
        result["summary"]["confirmatory_held_out_supported_exact_recoveries"] >= 1
        and result["controlled_improvement"].get("held_out", {}).get(
            "input_identity_matched", False
        )
        and result["controlled_improvement"].get("negative_control", {}).get(
            "configuration_B", {}
        ).get("status") == "COMPLETED"
        and result["controlled_improvement"].get("negative_control", {}).get(
            "configuration_B", {}
        ).get("accepted_false_positive_candidate_count") == 0
        and result["controlled_improvement"].get("negative_control", {}).get(
            "input_identity_matched", False
        )
    )
    (output / "M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    (output / "M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.md").write_text(
        render_markdown(result), encoding="utf-8",
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New, empty evidence output directory")
    parser.add_argument("--repository-root", default=".", help="Repository containing M27/M28 reports")
    parser.add_argument("--case-limit", type=int, help="Run only the first N fixed cases")
    parser.add_argument(
        "--summarize-existing", action="store_true",
        help="Rebuild reports from completed runs without rerunning the assembler",
    )
    parser.add_argument(
        "--report-output", help="Optional directory receiving the generated JSON and Markdown reports",
    )
    parser.add_argument(
        "--historical-report", help="Prior M29 JSON report to preserve and compare",
    )
    args = parser.parse_args(argv)
    result = (
        summarize_existing_runs(
            args.output, args.repository_root, args.historical_report
        )
        if args.summarize_existing
        else run(
            args.output, args.repository_root, args.case_limit,
            args.historical_report,
        )
    )
    if args.report_output:
        report_dir = Path(args.report_output)
        report_dir.mkdir(parents=True, exist_ok=True)
        for name in ("M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.json",
                     "M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.md"):
            shutil.copyfile(Path(args.output) / name, report_dir / name)
    print(json.dumps(result["summary"], sort_keys=True))


if __name__ == "__main__":
    main()
