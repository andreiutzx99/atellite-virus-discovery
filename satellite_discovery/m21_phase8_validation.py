"""Bounded, deterministic synthetic validation for the M21 Phase 8 report."""

import argparse
import hashlib
import json
from pathlib import Path

from . import m19_benchmark
from .m8_candidate_handoff import validate_candidate_sequence_set


SCHEMA = "m21-phase8-synthetic-validation-v1"
PARTIAL_MIN_IDENTITY = 0.95
PARTIAL_MIN_TRUTH_COVERAGE = 0.50
ALIGN_MATCH = 2
ALIGN_MISMATCH = -1
ALIGN_GAP = -2


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _fasta_sequences(path):
    sequences, current = [], []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        if line.startswith(">"):
            if current:
                sequences.append("".join(current).upper())
                current = []
        elif line.strip():
            current.append(line.strip())
    if current:
        sequences.append("".join(current).upper())
    return sequences


def _best_local_alignment(truth, candidate):
    """Return raw local identity/target coverage without a biological claim."""
    truth, candidate = truth.upper(), candidate.upper()
    if not truth or not candidate:
        return {"identity": 0.0, "truth_coverage": 0.0, "aligned_columns": 0}

    width = len(candidate) + 1
    trace = bytearray((len(truth) + 1) * width)
    previous = [0] * width
    best_score = best_i = best_j = 0
    for i, truth_base in enumerate(truth, 1):
        current = [0] * width
        for j, candidate_base in enumerate(candidate, 1):
            diagonal = previous[j - 1] + (
                ALIGN_MATCH if truth_base == candidate_base else ALIGN_MISMATCH
            )
            up = previous[j] + ALIGN_GAP
            left = current[j - 1] + ALIGN_GAP
            score = max(0, diagonal, up, left)
            current[j] = score
            if score:
                direction = 1 if score == diagonal else 2 if score == up else 3
                trace[i * width + j] = direction
                if score > best_score:
                    best_score, best_i, best_j = score, i, j
        previous = current

    i, j = best_i, best_j
    matches = columns = truth_bases = 0
    while i and j:
        direction = trace[i * width + j]
        if direction == 0:
            break
        columns += 1
        if direction == 1:
            if truth[i - 1] == candidate[j - 1]:
                matches += 1
            truth_bases += 1
            i -= 1
            j -= 1
        elif direction == 2:
            truth_bases += 1
            i -= 1
        else:
            j -= 1
    return {
        "identity": matches / columns if columns else 0.0,
        "truth_coverage": truth_bases / len(truth),
        "aligned_columns": columns,
    }


def _safe_child(root, relative):
    root = Path(root).resolve()
    rel = Path(relative)
    candidate = root / rel
    resolved = candidate.resolve()
    current = root
    symlink_component = False
    for part in rel.parts:
        current = current / part
        symlink_component = symlink_component or current.is_symlink()
    if (
        rel.is_absolute()
        or ".." in rel.parts
        or symlink_component
        or not resolved.is_relative_to(root)
    ):
        raise ValueError("Phase 8 artifact path escapes its run directory")
    return resolved


def _load_case_predictions(run_dir, analysis_id):
    run_dir = Path(run_dir).resolve()
    workflow_path = run_dir / "stages" / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    rows = [row for row in workflow.get("stages", []) if row.get("id") == f"m6_{analysis_id}"]
    if len(rows) != 1 or rows[0].get("status") != "complete":
        return []
    stage_dir = _safe_child(run_dir / "stages", rows[0].get("output_path", ""))
    manifest_path = stage_dir / "candidate_sequence_set.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Phase 8 candidate sequence manifest is missing")
    validate_candidate_sequence_set(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fasta_ref = manifest.get("availability", {}).get("fasta_artifact")
    if not fasta_ref:
        return []
    fasta_path = _safe_child(stage_dir, fasta_ref["path"])
    data = fasta_path.read_bytes()
    if _sha(data) != fasta_ref.get("sha256"):
        raise ValueError("Phase 8 candidate FASTA digest does not match its manifest")
    return _fasta_sequences(fasta_path)


def _case_results(run_dir, benchmark_report, heldout):
    truth_by_id = {row["case_id"]: row for row in heldout["cases"]}
    results = []
    for case in benchmark_report["cases"]:
        row = {
            "case_id": case["case_id"],
            "positive": case["positive"],
            "status": case["status"],
            "candidate_count": case["predicted_candidate_count"],
            "exact_recovered": None,
            "partial_candidate_count": None,
            "candidate_alignment_metrics": None,
            "candidate_sequence_sha256": None,
            "false_positive_candidates": case["false_positive_candidates"],
        }
        if case["status"] == "COMPLETE":
            predictions = _load_case_predictions(run_dir, case["analysis_id"])
            truth = truth_by_id[case["case_id"]]["candidate_sequence"]
            row["candidate_sequence_sha256"] = [
                _sha(seq.encode("ascii")) for seq in predictions
            ]
            if truth is not None:
                alignments = [_best_local_alignment(truth, seq) for seq in predictions]
                partial = [
                    metrics
                    for seq, metrics in zip(predictions, alignments)
                    if seq != truth.upper()
                    and metrics["identity"] >= PARTIAL_MIN_IDENTITY
                    and metrics["truth_coverage"] >= PARTIAL_MIN_TRUTH_COVERAGE
                ]
                row.update({
                    "exact_recovered": any(seq == truth.upper() for seq in predictions),
                    "partial_candidate_count": len(partial),
                    "candidate_alignment_metrics": alignments,
                })
        results.append(row)
    return results


def _metrics(cases):
    positives = [row for row in cases if row["positive"]]
    negatives = [row for row in cases if not row["positive"]]
    evaluated_pos = [row for row in positives if row["exact_recovered"] is not None]
    evaluated_neg = [row for row in negatives if row["candidate_count"] is not None]
    if (
        not positives
        or not negatives
        or len(evaluated_pos) != len(positives)
        or len(evaluated_neg) != len(negatives)
    ):
        return {
            "positive_cases": len(positives),
            "negative_cases": len(negatives),
            "evaluated_positive_cases": len(evaluated_pos),
            "evaluated_negative_cases": len(evaluated_neg),
            "detected_positive_cases": None,
            "synthetic_detection_rate": None,
            "exact_recovery_rate": None,
            "partial_recovery_cases": None,
            "candidate_precision": None,
            "negative_control_specificity": None,
            "false_positive_negative_controls": None,
            "performance_claim_status": "NOT_VALIDATED",
        }
    exact_tp = sum(bool(row["exact_recovered"]) for row in evaluated_pos)
    detected = sum(
        bool(row["exact_recovered"]) or (row["partial_candidate_count"] or 0) > 0
        for row in evaluated_pos
    )
    partial_only = sum(
        not row["exact_recovered"] and (row["partial_candidate_count"] or 0) > 0
        for row in evaluated_pos
    )
    false_candidates = sum(row["false_positive_candidates"] or 0 for row in cases)
    predictions = sum(row["candidate_count"] or 0 for row in cases)
    false_positive_negatives = sum((row["candidate_count"] or 0) > 0 for row in evaluated_neg)
    return {
        "positive_cases": len(positives),
        "negative_cases": len(negatives),
        "evaluated_positive_cases": len(evaluated_pos),
        "evaluated_negative_cases": len(evaluated_neg),
        "detected_positive_cases": detected,
        "synthetic_detection_rate": detected / len(evaluated_pos),
        "exact_recovery_rate": exact_tp / len(evaluated_pos),
        "partial_recovery_cases": partial_only,
        "candidate_precision": exact_tp / predictions if predictions else None,
        "negative_control_specificity": 1 - false_positive_negatives / len(evaluated_neg),
        "false_positive_negative_controls": false_positive_negatives,
        "false_positive_candidate_count": false_candidates,
        "candidate_count": predictions,
        "performance_claim_status": "DESCRIPTIVE_SYNTHETIC_ONLY",
    }


def _signature(source_manifest, heldout, cases):
    semantic_cases = [
        {
            "case_id": row["case_id"],
            "status": row["status"],
            "exact_recovered": row["exact_recovered"],
            "partial_candidate_count": row["partial_candidate_count"],
            "candidate_count": row["candidate_count"],
            "candidate_alignment_metrics": row["candidate_alignment_metrics"],
            "candidate_sequence_sha256": row["candidate_sequence_sha256"],
            "false_positive_candidates": row["false_positive_candidates"],
        }
        for row in cases
    ]
    return _sha(_json_bytes({
        "source_manifest": source_manifest,
        "heldout_truth": heldout,
        "cases": semantic_cases,
    }))


def _markdown(report):
    lines = [
        "# M21 Phase 8 synthetic scientific validation",
        "",
        f"**Status:** {report['phase8_status']}",
        "",
        "## Executive summary",
        "",
        report["executive_summary"],
        "",
        "All sequences are fixed-seed artificial A/C/G/T strings. These software results "
        "do not establish biological sensitivity, specificity, identity, function, or readiness.",
        "",
        "## Pipeline status",
        "",
        f"Existing path: `{report['existing_pipeline']}`. "
        f"Status: **{report['software_pipeline_status']}**.",
        "Candidate classification and downstream M20/M21 scientific interpretation are not "
        "part of this M4→M6 benchmark path.",
        "",
        "## Results",
        "",
        "| Case | Expected target | Pipeline | Exact recovery | Partial candidates | Candidates | False candidates |",
        "|---|---:|---|---:|---:|---:|---:|",
    ]
    for row in report["cases"]:
        lines.append(
            f"| {row['case_id']} | {row['positive']} | {row['status']} | "
            f"{row['exact_recovered']} | {row['partial_candidate_count']} | "
            f"{row['candidate_count']} | {row['false_positive_candidates']} |"
        )
    lines.extend([
        "",
        "## Aggregate metrics",
        "",
        "```json",
        json.dumps(report["metrics"], indent=2, sort_keys=True),
        "```",
        "",
        "Partial recovery means a non-exact candidate with at least "
        f"{PARTIAL_MIN_IDENTITY:.0%} local identity and "
        f"{PARTIAL_MIN_TRUTH_COVERAGE:.0%} truth-sequence coverage. These are descriptive "
        "engineering thresholds, not validated biological criteria.",
        "",
        "## Reproducibility",
        "",
        f"Two-run semantic reproducibility: **{report['reproducibility']['verified']}** "
        f"(signature `{report['reproducibility']['signature']}`).",
        "",
        "## Improvements implemented",
        "",
    ])
    lines.extend(f"- {item}" for item in report["improvements_implemented"])
    lines.extend([
        "",
        "## Recommendation disposition",
        "",
    ])
    lines.extend(
        f"- **{item['status']}:** {item['recommendation']}"
        for item in report["recommendation_dispositions"]
    )
    lines.extend([
        "",
        "## Limitations and readiness",
        "",
        "Readiness dimensions:",
        "",
        "```json",
        json.dumps(report["acceptance"], indent=2, sort_keys=True),
        "```",
        "",
    ])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.extend([
        "",
        "Phase 8 technical acceptance is not claimed unless every required criterion "
        "has direct evidence. `INCOMPLETE` does not authorize biological execution.",
        "",
    ])
    return "\n".join(lines)


def run(output):
    output = Path(output)
    if output.is_symlink():
        raise ValueError("Refusing a symlink Phase 8 output directory")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError("Phase 8 output directory must be empty")

    reports = []
    heldouts = []
    sources = []
    case_runs = []
    for run_id in ("run-1", "run-2"):
        run_dir = output / run_id
        benchmark = m19_benchmark.run(run_dir)
        heldout = json.loads((run_dir / "heldout_truth.json").read_text(encoding="utf-8"))
        source = json.loads((run_dir / "inputs" / "source_manifest.json").read_text(encoding="utf-8"))
        cases = _case_results(run_dir, benchmark, heldout)
        reports.append(benchmark)
        heldouts.append(heldout)
        sources.append(source)
        case_runs.append(cases)

    sigs = [_signature(source, truth, cases) for source, truth, cases in zip(sources, heldouts, case_runs)]
    reproducible = sigs[0] == sigs[1]
    primary_report = reports[0]
    cases = case_runs[0]
    metrics = _metrics(cases) if primary_report["benchmark_status"] == "COMPLETE" else {
        **_metrics(cases),
        "exact_recovery_rate": None,
        "partial_recovery_cases": None,
        "candidate_precision": None,
        "negative_control_specificity": None,
        "false_positive_negative_controls": None,
        "performance_claim_status": "NOT_EVALUATED",
    }
    limitations = [
        "All reads, references, and labels are artificial and generated from fixed seeds.",
        "The existing M4 QC to M6 residual-evidence workflow was reused; M1-M20 behavior was not changed.",
        "Exact recovery requires a full case-insensitive sequence match; partial recovery uses the explicitly stated local-alignment thresholds.",
        "The six-case matrix has one realization per condition and one negative control; aggregate metrics are descriptive and not scientifically validated.",
        "The pipeline's candidate output is not a biological classification and does not prove identity, novelty, function, or helper dependence.",
        "No authentic pathogen-associated sequences, biological sequencing datasets, or operational authorizations were used.",
        "The M21 governance decision remains INCOMPLETE; benchmark execution remains BLOCKED_FOR_BENCHMARK_EXECUTION and biological execution remains unauthorized.",
        "The broad M20/M21 recommendation backlog has not been fully reviewed or dispositioned in this report.",
    ]
    m4_m6_replay_complete = (
        all(report["benchmark_status"] == "COMPLETE" for report in reports)
        and reproducible
        and metrics["exact_recovery_rate"] is not None
    )
    acceptance = {
        "synthetic_pipeline_end_to_end_through_candidate_classification": False,
        "existing_m4_m6_path_completed_twice": m4_m6_replay_complete,
        "known_synthetic_targets_scored": m4_m6_replay_complete,
        "exact_and_partial_recovery_reported": m4_m6_replay_complete,
        "negative_controls_evaluated": m4_m6_replay_complete and metrics["negative_cases"] > 0,
        "false_positive_behavior_measured": m4_m6_replay_complete,
        "semantic_reproducibility_demonstrated": reproducible,
        "m20_m21_recommendations_reviewed": False,
        "relevant_test_suite_passed": None,
        "ci_passed": None,
        "scientific_report_complete": True,
    }
    executive_summary = (
        f"The existing M4→M6 synthetic workflow completed {len(cases)} fixed-seed cases "
        f"on both runs; exact recovery was {metrics['exact_recovery_rate']:.1%} across "
        f"{metrics['evaluated_positive_cases']} positive cases, with "
        f"{metrics['partial_recovery_cases']} partial-only recovery cases. "
        "The benchmark is descriptive and does not establish biological performance."
        if metrics["exact_recovery_rate"] is not None
        else "The synthetic benchmark did not produce evaluable metrics; no performance "
        "claim is made."
    )
    report = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "biological_data_used": False,
        "biological_execution_authorized": False,
        "decision": "INCOMPLETE",
        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
        "phase8_status": "INCOMPLETE",
        "software_pipeline_status": "M4_M6_COMPLETE" if m4_m6_replay_complete else "INCOMPLETE",
        "executive_summary": executive_summary,
        "acceptance": acceptance,
        "existing_pipeline": "M4 QC -> M6 residual evidence and assembly",
        "improvements_implemented": [
            "Added a bounded Phase 8 wrapper that runs the existing synthetic M19 M4→M6 path twice.",
            "Added local-alignment identity and truth-coverage metrics so partial candidates are separated from exact recovery.",
            "Compared fixed-seed input/truth manifests, candidate sequence digests, statuses, and metrics across runs.",
            "Kept M1–M20 pipeline behavior and M21 authorization state unchanged.",
        ],
        "recommendation_dispositions": [
            {
                "status": "REUSED",
                "recommendation": "Retain fixed-seed synthetic positive/negative controls and exact truth scoring from M19.",
            },
            {
                "status": "IMPLEMENTED",
                "recommendation": "Report exact and thresholded partial sequence recovery separately, including per-candidate identity and coverage.",
            },
            {
                "status": "DEFERRED",
                "recommendation": "Complete the M4-to-final-candidate classification and evidence-report integration; the current benchmark stops at M6 plus truth scoring.",
            },
            {
                "status": "NOT_REVIEWED",
                "recommendation": "The full M20/M21 recommendation backlog requires a separate item-by-item review; no broader disposition is claimed.",
            },
        ],
        "run_statuses": [row["benchmark_status"] for row in reports],
        "cases": cases,
        "metrics": metrics,
        "reproducibility": {
            "verified": reproducible,
            "signature": sigs[0] if reproducible else None,
            "run_signatures": sigs,
            "semantic_fields": [
                "fixed-seed source manifest",
                "held-out truth",
                "per-case status and exact/partial recovery",
                "candidate counts, alignment metrics, and false-positive counts",
                "candidate sequence digests",
            ],
        },
        "recommendations_reviewed": False,
        "limitations": limitations,
    }
    (output / "phase8-report.json").write_bytes(_json_bytes(report))
    (output / "phase8-report.md").write_text(_markdown(report), encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the bounded synthetic-only M21 Phase 8 scientific validation"
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = run(args.output)
    print(f"Phase 8 {report['phase8_status']}; M21 decision remains {report['decision']}")
    return 0 if report["phase8_status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
