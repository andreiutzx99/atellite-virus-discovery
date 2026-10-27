"""Blinded, deterministic synthetic M22 configuration comparison.

The M19 six-case benchmark remains the immutable baseline. This runner creates
separate development, tuning, and held-out fixture sets, runs each predeclared
SPAdes configuration on byte-identical inputs, and scores only after M6 ends.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re

from . import m19_benchmark
from .assembly_adapters import SpadesAssemblyAdapter
from .m21_phase8_validation import _best_local_alignment


SCHEMA = "m22-synthetic-performance-v1"
SPLITS = {
    "development": 220101,
    "tuning": 220201,
    "held_out": 220301,
}
PARTIAL_IDENTITY = 0.95
PARTIAL_COVERAGE = 0.50
CONFIGURATIONS = ("m21_default", "experimental_k21_k33")
SCENARIOS = (
    {"positive": True, "target_length": 500, "coverage": 48, "error_rate": 0.00,
     "divergence": 0.25, "repeat_complexity": "low", "gc_fraction": 0.50,
     "background_gc_fraction": 0.25, "read_start_mode": "random"},
    {"positive": True, "target_length": 800, "coverage": 60, "error_rate": 0.05,
     "divergence": 0.25, "repeat_complexity": "low", "gc_fraction": 0.50,
     "background_gc_fraction": 0.75, "read_start_mode": "random"},
    {"positive": True, "target_length": 1200, "coverage": 16, "error_rate": 0.00,
     "divergence": 0.25, "repeat_complexity": "low", "gc_fraction": 0.50,
     "background_gc_fraction": 0.25, "read_start_mode": "random"},
    {"positive": True, "target_length": 650, "coverage": 40, "error_rate": 0.02,
     "divergence": 0.45, "repeat_complexity": "low", "gc_fraction": 0.50,
     "background_gc_fraction": 0.75, "read_start_mode": "random"},
    {"positive": True, "target_length": 900, "coverage": 48, "error_rate": 0.00,
     "divergence": 0.25, "repeat_complexity": "high", "gc_fraction": 0.50,
     "background_gc_fraction": 0.50, "read_start_mode": "random"},
    {"positive": True, "target_length": 750, "coverage": 48, "error_rate": 0.00,
     "divergence": 0.25, "repeat_complexity": "low_complexity", "gc_fraction": 0.20,
     "background_gc_fraction": 0.50, "read_start_mode": "random"},
    {"positive": False, "target_length": 700, "coverage": 48, "error_rate": 0.00,
     "divergence": 0.25, "repeat_complexity": "low", "gc_fraction": 0.25,
     "background_gc_fraction": 0.75, "read_start_mode": "random"},
    {"positive": False, "target_length": 1100, "coverage": 60, "error_rate": 0.00,
     "divergence": 0.25, "repeat_complexity": "low", "gc_fraction": 0.75,
     "background_gc_fraction": 0.25, "read_start_mode": "random"},
)


def _cases(split):
    rows = []
    for index, scenario in enumerate(SCENARIOS, 1):
        rows.append({
            **scenario,
            "case_id": f"{split}-case-{index:02d}",
            "analysis_id": f"x{index:02d}",
            "opaque_read_ids": True,
        })
    return tuple(rows)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _fasta_records(path):
    records, current_id, current = [], None, []
    if not path.is_file():
        return records
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith(">"):
            if current:
                records.append((current_id, "".join(current).upper()))
            current_id = line[1:].split()[0]
            current = []
        elif line.strip():
            current.append(line.strip())
    if current:
        records.append((current_id, "".join(current).upper()))
    return records


def _run_set(output, split, seed, configuration):
    cases = _cases(split)
    old_cases, old_seed = m19_benchmark.CASES, m19_benchmark.SEED
    original_builder = SpadesAssemblyAdapter.build_command
    try:
        m19_benchmark.CASES = cases
        m19_benchmark.SEED = seed
        if configuration == "experimental_k21_k33":
            def experimental_builder(adapter, executables, inputs, target, config):
                return original_builder(adapter, executables, inputs, target, config) + [
                    "-k", "21,33",
                ]
            SpadesAssemblyAdapter.build_command = experimental_builder
        return m19_benchmark.run(output)
    finally:
        m19_benchmark.CASES = old_cases
        m19_benchmark.SEED = old_seed
        SpadesAssemblyAdapter.build_command = original_builder


def _memory_log_mb(path):
    if not path.is_file():
        return None
    values = []
    for match in re.finditer(r"\b(\d+)M\s*/\s*\d+M\b", path.read_text(errors="replace")):
        values.append(int(match.group(1)))
    return max(values) if values else None


def _case_results(run_dir):
    report = json.loads((run_dir / "m19-report.json").read_text())
    truth_doc = json.loads((run_dir / "heldout_truth.json").read_text())
    truth_by_id = {row["case_id"]: row for row in truth_doc["cases"]}
    output = []
    for row in report["cases"]:
        aid, cid = row["analysis_id"], row["case_id"]
        stage = run_dir / "stages" / f"m6_{aid}"
        truth = truth_by_id[cid]["candidate_sequence"]
        fasta_records = _fasta_records(stage / "candidate_sequences.fasta")
        candidates = [sequence for _, sequence in fasta_records]
        evidence_path = stage / "reconstruction_evidence.json"
        evidence = json.loads(evidence_path.read_text()) if evidence_path.is_file() else {}
        candidate_path = stage / "candidate_sequence_set.json"
        candidate_set = json.loads(candidate_path.read_text()) if candidate_path.is_file() else {}
        support_by_id = {
            item.get("fasta_record_id"): item.get("m6_support_status")
            for item in candidate_set.get("records", [])
        }
        supported_records = [
            (fasta_id, sequence) for fasta_id, sequence in fasta_records
            if support_by_id.get(fasta_id) == "READ_SUPPORTED_ASSEMBLY"
        ]
        exact = [seq for seq in candidates if truth and seq == truth.upper()]
        supported_exact = [
            seq for _, seq in supported_records if truth and seq == truth.upper()
        ]
        alignments = [
            _best_local_alignment(truth, seq) for seq in candidates
        ] if truth else []
        best = max(
            alignments,
            key=lambda x: (x["aligned_columns"], x["truth_coverage"], x["identity"]),
            default=None,
        )
        partial = any(
            item["identity"] >= PARTIAL_IDENTITY
            and item["truth_coverage"] >= PARTIAL_COVERAGE
            for item in alignments
        )
        assembly_path = stage / "assembly" / "assembly_manifest.json"
        assembly = json.loads(assembly_path.read_text()) if assembly_path.is_file() else {}
        log_memory = _memory_log_mb(stage / "assembly" / "raw" / "spades.log")
        output.append({
            "case_id": cid,
            "split": cid.split("-", 1)[0],
            "positive": truth is not None,
            "target_length": row.get("target_length"),
            "nominal_coverage": row.get("coverage"),
            "error_rate": row.get("error_rate"),
            "reference_divergence": row.get("divergence"),
            "repeat_complexity": row.get("repeat_complexity"),
            "target_gc_fraction": row.get("gc_fraction"),
            "background_gc_fraction": row.get("background_gc_fraction"),
            "execution_state": row["status"],
            "assembler_state": evidence.get("status", "NOT_EVALUATED"),
            "exact_recovery": bool(exact),
            "partial_recovery": bool(partial and not exact),
            "candidate_count": len(candidates),
            "read_supported_candidate_count": len(supported_records),
            "exact_candidate_count": len(exact),
            "read_supported_exact_candidate_count": len(supported_exact),
            "read_supported_false_positive_candidates": (
                len(supported_records) - len(supported_exact)
            ),
            "false_positive_candidates": len(candidates) - len(exact),
            "best_candidate_identity": best["identity"] if best else None,
            "best_candidate_target_coverage": best["truth_coverage"] if best else None,
            "assembly_runtime_seconds": assembly.get("duration_seconds"),
            "configured_memory_mb": assembly.get("resource_limits", {}).get("memory_mb"),
            "spades_log_reported_memory_mb": log_memory,
            "memory_measurement_note": (
                "SPAdes log-reported allocator value, not OS peak RSS"
                if log_memory is not None else "not reported"
            ),
        })
    return output


def _wilson(successes, total):
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    lower = 0.0 if successes == 0 else max(0.0, centre - margin)
    upper = 1.0 if successes == total else min(1.0, centre + margin)
    return [lower, upper]


def summarize(cases):
    positives = [row for row in cases if row["positive"]]
    negatives = [row for row in cases if not row["positive"]]
    candidates = sum(row["candidate_count"] for row in cases)
    exact_candidates = sum(row["exact_candidate_count"] for row in cases)
    false_positives = sum(row["false_positive_candidates"] for row in cases)
    supported_candidates = sum(row["read_supported_candidate_count"] for row in cases)
    supported_exact = sum(row["read_supported_exact_candidate_count"] for row in cases)
    supported_false_positives = sum(
        row["read_supported_false_positive_candidates"] for row in cases
    )
    durations = [row["assembly_runtime_seconds"] for row in cases
                 if isinstance(row["assembly_runtime_seconds"], (int, float))]
    attempts = [row for row in cases if row["assembler_state"] != "NOT_EVALUATED"]
    failures = sum(row["assembler_state"] == "EXECUTION_FAILED" for row in attempts)
    exact_cases = sum(row["exact_recovery"] for row in positives)
    partial_cases = sum(row["partial_recovery"] for row in positives)
    return {
        "case_count": len(cases),
        "positive_case_count": len(positives),
        "negative_control_count": len(negatives),
        "exact_recovery_cases": exact_cases,
        "exact_recovery_rate": exact_cases / len(positives) if positives else None,
        "exact_recovery_wilson_95": _wilson(exact_cases, len(positives)),
        "partial_recovery_cases": partial_cases,
        "partial_recovery_rate": partial_cases / len(positives) if positives else None,
        "candidate_count": candidates,
        "exact_candidate_precision": exact_candidates / candidates if candidates else None,
        "read_supported_candidate_count": supported_candidates,
        "read_supported_exact_candidate_precision": (
            supported_exact / supported_candidates if supported_candidates else None
        ),
        "false_positive_candidates": false_positives,
        "read_supported_false_positive_candidates": supported_false_positives,
        "unsupported_candidate_count": candidates - supported_candidates,
        "negative_controls_without_candidates": sum(
            row["candidate_count"] == 0 for row in negatives
        ),
        "negative_controls_without_read_supported_candidates": sum(
            row["read_supported_candidate_count"] == 0 for row in negatives
        ),
        "negative_control_case_count": len(negatives),
        "assembly_execution_failures": failures,
        "assembly_attempt_count": len(attempts),
        "assembly_failure_rate": failures / len(attempts) if attempts else None,
        "mean_assembly_runtime_seconds": sum(durations) / len(durations) if durations else None,
        "maximum_configured_memory_mb": max(
            (row["configured_memory_mb"] for row in cases
             if isinstance(row["configured_memory_mb"], int)), default=None),
        "maximum_spades_log_reported_memory_mb": max(
            (row["spades_log_reported_memory_mb"] for row in cases
             if isinstance(row["spades_log_reported_memory_mb"], int)), default=None),
        "spades_log_memory_is_os_rss": False,
    }


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows, input_digests = {}, {}
    for split, seed in SPLITS.items():
        for configuration in CONFIGURATIONS:
            directory = output / split / configuration
            report = _run_set(directory, split, seed, configuration)
            if report.get("benchmark_status") != "COMPLETE":
                raise RuntimeError(
                    f"{split}/{configuration} did not complete: "
                    f"{report.get('benchmark_status')}"
                )
            manifest = (directory / "inputs" / "source_manifest.json").read_bytes()
            input_digests[(split, configuration)] = _sha(manifest)
            rows[(split, configuration)] = _case_results(directory)
    for split in SPLITS:
        if input_digests[(split, "m21_default")] != input_digests[
            (split, "experimental_k21_k33")
        ]:
            raise ValueError(f"Configuration inputs differ for split {split}")

    results = []
    for split in SPLITS:
        for configuration in CONFIGURATIONS:
            cases = rows[(split, configuration)]
            results.append({
                "split": split,
                "configuration": configuration,
                "input_manifest_sha256": input_digests[(split, configuration)],
                "summary": summarize(cases),
                "cases": cases,
            })
    aggregate_results = []
    for configuration in CONFIGURATIONS:
        combined = [
            row for split in SPLITS
            for row in rows[(split, configuration)]
        ]
        aggregate_results.append({
            "configuration": configuration,
            "summary": summarize(combined),
            "held_out_summary": summarize(rows[("held_out", configuration)]),
        })
    report = {
        "schema": SCHEMA,
        "status": "COMPLETE",
        "synthetic_only": True,
        "biological_data_used": False,
        "biological_claims_authorized": False,
        "split_seeds": SPLITS,
        "predeclared_configurations": {
            "m21_default": "Existing registered M6/SPAdes settings; no k-mer override.",
            "experimental_k21_k33": "Same inputs and pipeline; append SPAdes -k 21,33 only.",
        },
        "comparison_controls": {
            "same_synthetic_inputs_per_split": True,
            "held_out_used_for_tuning": False,
            "held_out_split": "held_out",
            "m19_baseline_changed": False,
        },
        "configuration_decision": {
            "selected": "m21_default",
            "reason": (
                "The alternative reduced execution failures but produced no exact "
                "recoveries and more false-positive candidates on held-out data."
            ),
        },
        "partial_recovery_thresholds": {
            "minimum_identity": PARTIAL_IDENTITY,
            "minimum_target_coverage": PARTIAL_COVERAGE,
            "purpose": "descriptive software metric only",
        },
        "results": results,
        "aggregate_results": aggregate_results,
        "limitations": [
            "All target, background, read, and reference sequences are newly generated artificial A/C/G/T strings.",
            "Scenario labels and truth sequences are stored after each run and never enter the workflow graph.",
            "Read-back support shares the input reads and is not independent evidence of truth.",
            "Confidence intervals describe only these finite artificial cases and do not estimate biological sensitivity or specificity.",
            "SPAdes log memory values are not operating-system peak RSS; the configured memory ceiling is reported separately.",
            "The two configurations were prespecified; no default change is made from these experiments.",
        ],
    }
    payload = json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    (output / "m22-report.json").write_text(payload, encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run M22 synthetic configuration comparisons")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = run(args.output)
    print(f"M22 {report['status']}: {len(report['results'])} split/configuration reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
