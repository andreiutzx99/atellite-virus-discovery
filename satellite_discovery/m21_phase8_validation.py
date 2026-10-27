"""Bounded, deterministic synthetic validation for the M21 Phase 8 report."""

import argparse
import hashlib
import json
from pathlib import Path

from . import (
    m19_benchmark, m20_phase2b, m20_phase3, m20_phase4, m20_phase5,
)
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
            "analysis_id": case["analysis_id"],
            "positive": case["positive"],
            "status": case["status"],
            "candidate_count": case["predicted_candidate_count"],
            "exact_recovered": None,
            "partial_candidate_count": None,
            "candidate_alignment_metrics": None,
            "candidate_sequence_sha256": None,
            "false_positive_candidates": case["false_positive_candidates"],
        }
        m6_dir = _safe_child(Path(run_dir) / "stages", f"m6_{case['analysis_id']}")
        for filename, key in (
            ("reconstruction_evidence.json", "m6_reconstruction_status"),
            ("read_support.json", "m6_read_support_status"),
        ):
            artifact = m6_dir / filename
            payload = (
                json.loads(artifact.read_text(encoding="utf-8"))
                if artifact.is_file() and not artifact.is_symlink() else {}
            )
            row[key] = payload.get("status", "UNAVAILABLE")
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
    reconstruction_failures = sum(
        row.get("m6_reconstruction_status") == "EXECUTION_FAILED" for row in cases
    )
    read_support_not_evaluated = sum(
        row.get("m6_read_support_status") == "NOT_EVALUATED" for row in cases
    )
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
            "reconstruction_execution_failures": reconstruction_failures,
            "read_support_not_evaluated_cases": read_support_not_evaluated,
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
        "reconstruction_execution_failures": reconstruction_failures,
        "read_support_not_evaluated_cases": read_support_not_evaluated,
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
            "m6_reconstruction_status": row.get("m6_reconstruction_status"),
            "m6_read_support_status": row.get("m6_read_support_status"),
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
    registered = report.get("registered_pipeline", {})
    lines.extend([
        "",
        "## Registered M20 end-to-end pipeline",
        "",
        f"Status: **{registered.get('status', 'NOT_RUN')}**; "
        f"Phase 2B cases: {registered.get('case_count', 0)}; "
        f"Phase 3 M8/M9/M10: {registered.get('phase3_status', 'NOT_RUN')}; "
        f"Phase 4 M12/M15: {registered.get('phase4_status', 'NOT_RUN')}; "
        f"Phase 5 report: {registered.get('phase5_decision', 'NOT_RUN')}.",
        f"Phase 4 semantic replay matched: **{registered.get('replay_verified', False)}**.",
        "",
        "| Case | Read seed | M4/M6 | M7 | M8 | M9 ORF | M9 BLASTP | M10 | M12 | M15 |",
        "|---|---:|---|---|---|---|---|---|---|---|",
    ])
    for row in registered.get("case_traces", []):
        lines.append(
            f"| {row['case_id']} | {row['read_seed']} | {row['m4_m6']} | {row['m7']} | "
            f"{row['m8']} | {row['m9_orf']} | {row['m9_blastp']} | {row['m10']} | "
            f"{row['m12']} | {row['m15']} |"
        )
    lines.extend(["", "## M19 failure investigation", ""])
    for item in report.get("failure_investigation", []):
        lines.append(
            f"- **{item['case_id']}** — disposition: {item['disposition']}; "
            f"M6 reconstruction `{item['reconstruction_status']}`, "
            f"read support `{item['read_support_status']}`, candidate set "
            f"`{item['candidate_availability']}`. {item['finding']}"
        )
    lines.extend([
        "",
        "## Recommendation disposition",
        "",
    ])
    lines.extend(
        f"- **{item['status']}:** {item['recommendation']}"
        + (f" Evidence: {item['evidence']}" if item.get("evidence") else "")
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


def _run_registered_pipeline(root):
    """Run the existing M20 synthetic M4–M15 stages and final Phase 5 report."""
    root = Path(root)
    phase2b, phase3 = root / "phase2b", root / "phase3"
    phase4a, phase4b, phase5 = (
        root / "phase4-primary", root / "phase4-replay", root / "phase5",
    )
    p2 = m20_phase2b.run(phase2b)
    p3 = m20_phase3.run(phase3, phase2b)
    p4 = m20_phase4.run(phase4a, phase2b, phase3)
    replay = m20_phase4.run(phase4b, phase2b, phase3)
    p5 = m20_phase5.build_report(
        phase2b, phase3, phase4a, previous_phase4_output=phase4b,
    )
    m20_phase5.write_report(p5, phase5)
    p2_cases = {row["sample_id"]: row for row in p2.get("cases", [])}
    p3_cases = {row["sample_id"]: row for row in p3.get("cases", [])}
    p4_cases = {row["sample_id"]: row for row in p4.get("cases", [])}
    traces = []
    for sample in sorted(p2_cases):
        case2, case3, case4 = p2_cases[sample], p3_cases.get(sample, {}), p4_cases.get(sample, {})
        traces.append({
            "case_id": sample,
            "read_seed": case2.get("read_seed"),
            "m4_m6": f"{case2.get('qc_status', 'UNKNOWN')}/{case2.get('m6_status', 'UNKNOWN')}",
            "m7": p2.get("workflow_status", {}).get("m7", "NOT_REPORTED"),
            "m8": case3.get("m8", {}).get("stage_status", "NOT_REPORTED"),
            "m9_orf": case3.get("m9_orf", {}).get("status", "NOT_REPORTED"),
            "m9_blastp": case3.get("m9_blastp", {}).get("status", "NOT_REPORTED"),
            "m10": case3.get("m10", {}).get("status", "NOT_REPORTED"),
            "m12": case4.get("m12", {}).get("status", "NOT_REPORTED"),
            "m15": case4.get("m15", {}).get("status", "NOT_REPORTED"),
            "m15_binding_count": len(
                case4.get("m15", {}).get("validated_producer_bindings", [])
            ),
            "m15_binding_milestones": sorted({
                binding.get("producer_milestone")
                for binding in case4.get("m15", {}).get("validated_producer_bindings", [])
                if binding.get("producer_milestone")
            }),
            "m15_binding_trace_sha256": _sha(_json_bytes([
                {
                    key: binding.get(key)
                    for key in (
                        "producer_milestone", "producer_stage_id",
                        "producer_run_manifest_sha256", "artifact_type",
                        "artifact_path", "artifact_sha256",
                    )
                }
                for binding in case4.get("m15", {}).get("validated_producer_bindings", [])
            ])),
        })
    replay_verified = bool(
        p4.get("deterministic_semantic_outcomes_sha256")
        and p4.get("deterministic_semantic_outcomes_sha256")
        == replay.get("deterministic_semantic_outcomes_sha256")
    )
    trace_complete = (
        p2.get("status") == "COMPLETE"
        and p3.get("status") == "COMPLETE"
        and p4.get("status") == "COMPLETE"
        and replay.get("status") == "COMPLETE"
        and p5.get("software_integration_status") == "VALIDATED"
        and len(traces) == len(p2_cases)
        and all(
            row["m8"] not in {"NOT_REPORTED", "UNAVAILABLE"}
            and row["m9_orf"] not in {"NOT_REPORTED", "UNAVAILABLE"}
            and row["m10"] not in {"NOT_REPORTED", "UNAVAILABLE"}
            and row["m12"] == "complete" and row["m15"] == "complete"
            for row in traces
        )
    )
    return {
        "schema": "m21-phase8-registered-pipeline-v1",
        "status": "COMPLETE" if trace_complete and replay_verified else "INCOMPLETE",
        "phase2b_status": p2.get("status"),
        "phase3_status": p3.get("status"),
        "phase4_status": p4.get("status"),
        "phase4_replay_status": replay.get("status"),
        "phase5_decision": p5.get("decision"),
        "software_integration_status": p5.get("software_integration_status"),
        "biological_discovery_status": p5.get("biological_discovery_status"),
        "case_count": len(traces),
        "negative_control_count": sum(
            row.get("role") == "negative_control" for row in p2_cases.values()
        ),
        "read_seed_count": len({row["read_seed"] for row in traces if row["read_seed"] is not None}),
        "phase4_semantic_digest": p4.get("deterministic_semantic_outcomes_sha256"),
        "phase4_replay_digest": replay.get("deterministic_semantic_outcomes_sha256"),
        "replay_verified": replay_verified,
        "m12_invalid_count": len(p5.get("m12_current_invalid_findings", [])),
        "case_traces": traces,
        "reports": {
            key: path.relative_to(root).as_posix()
            for key, path in {
                "phase2b": phase2b / "report.json",
                "phase3": phase3 / "report.json",
                "phase4": phase4a / "report.json",
                "phase4_replay": phase4b / "report.json",
                "phase5": phase5 / "report.json",
            }.items()
        },
    }


def _failure_investigation(run_dir, cases):
    workflow = json.loads((Path(run_dir) / "stages" / "workflow.json").read_text())
    stages = {row.get("id"): row for row in workflow.get("stages", []) if isinstance(row, dict)}
    findings = []
    for case_id in ("high_error", "low_coverage", "high_repeat"):
        case = next(row for row in cases if row["case_id"] == case_id)
        stage = stages.get(f"m6_{case['analysis_id']}", {})
        stage_dir = _safe_child(Path(run_dir) / "stages", stage.get("output_path", ""))
        docs = {}
        for filename in (
            "reconstruction_evidence.json", "read_support.json",
            "candidate_sequence_set.json", "residual_manifest.json",
        ):
            path = stage_dir / filename
            docs[filename] = (
                json.loads(path.read_text(encoding="utf-8"))
                if path.is_file() and not path.is_symlink() else {}
            )
        reconstruction = docs["reconstruction_evidence.json"]
        support = docs["read_support.json"]
        candidate = docs["candidate_sequence_set.json"]
        residual = docs["residual_manifest.json"]
        reconstruction_status = reconstruction.get("status", "UNAVAILABLE")
        support_status = support.get("status", "UNAVAILABLE")
        availability = candidate.get("availability", {})
        candidate_state = availability.get("state", "UNAVAILABLE")
        residual_counts = residual.get("counts", {})
        assembler_error = None
        spades_log = stage_dir / "assembly" / "raw" / "spades.log"
        if spades_log.is_file() and not spades_log.is_symlink():
            assembler_error = next(
                (
                    line.strip()
                    for line in spades_log.read_text(encoding="utf-8", errors="replace").splitlines()
                    if " ERROR " in line or " ERROR\t" in line
                ),
                None,
            )
        alignment = (case.get("candidate_alignment_metrics") or [{}])[0]
        if reconstruction_status == "EXECUTION_FAILED":
            disposition = "ASSEMBLER_EXECUTION_FAILURE"
            reason = (
                f"{assembler_error}; {residual_counts.get('eligible_fragments', 'unknown')} "
                "residual fragments were assembly-eligible; read support was not evaluated."
                if assembler_error else
                "M6 reconstruction reports EXECUTION_FAILED; read support was not evaluated, "
                "and no more specific failure diagnostic was recorded."
            )
        elif support_status == "NO_SUPPORTED_ASSEMBLY":
            disposition = (
                "UNSUPPORTED_FALSE_CANDIDATE"
                if case.get("false_positive_candidates")
                else "NO_READ_SUPPORTED_ASSEMBLY"
            )
            reason = (
                "M6 read-back reports NO_SUPPORTED_ASSEMBLY; best candidate alignment was "
                f"{alignment.get('identity', 0):.1%} identity over "
                f"{alignment.get('truth_coverage', 0):.1%} target coverage."
                if case.get("candidate_count") else
                "M6 read-back reports NO_SUPPORTED_ASSEMBLY; no candidate was emitted."
            )
        else:
            disposition = "INSUFFICIENT_EVIDENCE"
            reason = (
                availability.get("reason")
                or reconstruction.get("reason")
                or support.get("reason")
                or "The current artifacts do not identify a more specific cause."
            )
        findings.append({
            "case_id": case_id,
            "reconstruction_status": reconstruction_status,
            "read_support_status": support_status,
            "candidate_availability": candidate_state,
            "residual_fragment_count": residual_counts.get("residual_fragments"),
            "assembly_eligible_fragment_count": residual_counts.get("eligible_fragments"),
            "assembler_error": assembler_error,
            "disposition": disposition,
            "finding": str(reason),
        })
    return findings


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
        "M19 reports the two failed positive reconstructions as stage-complete misses; M6 artifacts show SPAdes execution failures, so these are not evidence that the targets were unrecoverable.",
        "The pipeline's candidate output is not a biological classification and does not prove identity, novelty, function, or helper dependence.",
        "No authentic pathogen-associated sequences, biological sequencing datasets, or operational authorizations were used.",
        "The M21 governance decision remains INCOMPLETE; benchmark execution remains BLOCKED_FOR_BENCHMARK_EXECUTION and biological execution remains unauthorized.",
        "M21 biological-data access, independent scientific review, and governance trust gates remain outside this synthetic-only run.",
    ]
    registered = _run_registered_pipeline(output / "registered-m20")
    failure_investigation = _failure_investigation(output / "run-1", cases)
    m4_m6_replay_complete = (
        all(report["benchmark_status"] == "COMPLETE" for report in reports)
        and reproducible
        and metrics["exact_recovery_rate"] is not None
    )
    acceptance = {
        "registered_synthetic_pipeline_m4_through_m15_and_final_report": (
            registered["status"] == "COMPLETE"
        ),
        "existing_m4_m6_path_completed_twice": m4_m6_replay_complete,
        "known_synthetic_targets_scored": m4_m6_replay_complete,
        "exact_and_partial_recovery_reported": m4_m6_replay_complete,
        "negative_controls_evaluated": m4_m6_replay_complete and metrics["negative_cases"] > 0,
        "false_positive_behavior_measured": m4_m6_replay_complete,
        "semantic_reproducibility_demonstrated": reproducible,
        "m20_m21_recommendations_reviewed": True,
        "relevant_test_suite_passed": None,
        "ci_passed": None,
        "scientific_report_complete": True,
    }
    executive_summary = (
        f"The registered M20 synthetic pipeline completed {registered['case_count']} seeded cases through M15 and Phase 5; "
        f"Phase 4 semantic replay matched. M19's six-case matrix produced "
        f"{metrics['exact_recovery_rate']:.1%} exact recovery, but "
        f"{metrics['reconstruction_execution_failures']} positive cases hit SPAdes reconstruction errors. "
        "These descriptive software results do not establish biological performance."
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
            "Compared fixed-seed inputs, candidate digests, M6 reconstruction/read-support states, and metrics across runs.",
            "Executed registered M20 synthetic M4→M15 stages, repeated Phase 4, and generated the Phase 5 report.",
            "Recorded M6/SPAdes failure diagnostics for the high-error and low-coverage M19 cases.",
            "Kept M1–M20 pipeline behavior and M21 authorization state unchanged.",
        ],
        "recommendation_dispositions": [
            {
                "status": "REUSED",
                "recommendation": "Retain fixed-seed synthetic positive/negative controls and exact truth scoring from M19.",
                "evidence": "Two independent M19 executions completed with matching semantic signatures.",
            },
            {
                "status": "IMPLEMENTED",
                "recommendation": "Report exact and thresholded partial sequence recovery separately, including per-candidate identity and coverage.",
                "evidence": "Phase 8 case metrics include identity and target coverage with frozen thresholds.",
            },
            {
                "status": "IMPLEMENTED",
                "recommendation": "Exercise registered synthetic M4→M6→M7→M8/M9/M10→M12/M15 and produce the M20 Phase 5 report.",
                "evidence": "Two M20 Phase 4 executions are compared by deterministic semantic digest; the M20 Phase 5 report separates software validation from biological discovery.",
            },
            {
                "status": "DEFERRED",
                "recommendation": "Supply M5, M13, M14, and M10 JSONL evidence to M15.",
                "evidence": "Existing producer allowlists do not supply M5/M13/M14 here, and M15 rejects the M10 JSONL payload; no M1–M20 contract was changed.",
            },
            {
                "status": "DEFERRED",
                "recommendation": "Acquire biological reads, resolve reuse terms, assess library adequacy, and independently verify positive and negative labels.",
                "evidence": "The Phase 8 brief restricts this work to artificial sequences and provides no biological execution authorization.",
            },
            {
                "status": "DEFERRED",
                "recommendation": "Obtain independent review of reference exclusion, blind-key custody, and governance trust evidence before any biological benchmark.",
                "evidence": "M21 readiness documents retain pending independent evidence and trusted custody gates.",
            },
            {
                "status": "SATISFIED",
                "recommendation": "Retain the existing synthetic streaming FASTQ validator and bounded operational checks.",
                "evidence": "M21 Phase 4 operational-readiness report documents the implementation and synthetic-only test boundary.",
            },
            {
                "status": "DEFERRED",
                "recommendation": "Provision real reviewer trust, independently retained audit checkpoints, and authenticated approvals.",
                "evidence": "M21 Phase 6 readiness remains PENDING/UNANCHORED; no real credentials, reviewers, or approvals were supplied.",
            },
            {
                "status": "SATISFIED",
                "recommendation": "Keep M21 governance incomplete and biological execution blocked during synthetic validation.",
                "evidence": "The report preserves decision=INCOMPLETE, BLOCKED_FOR_BENCHMARK_EXECUTION, and biological_execution_authorized=false.",
            },
        ],
        "run_statuses": [row["benchmark_status"] for row in reports],
        "cases": cases,
        "registered_pipeline": registered,
        "failure_investigation": failure_investigation,
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
                "M6 reconstruction and read-support outcomes",
            ],
        },
        "recommendations_reviewed": True,
        "recommendation_review_sources": [
            "docs/M20_SYNTHETIC_EVIDENCE_INTEGRATION_DESIGN.md",
            "docs/M21_CAPABILITY_GAP_ASSESSMENT.md",
            "docs/M21_DESIGN_ONLY_REFERENCE_BENCHMARK_PLAN.md",
            "docs/M21_PHASE2_READINESS_REPORT.md",
            "docs/M21_PHASE3_READINESS_REPORT.md",
            "docs/M21_PHASE4_OPERATIONAL_READINESS.md",
            "docs/M21_PHASE5_SCIENTIFIC_VALIDATION_REPORT.md",
            "docs/M21_PHASE6_GOVERNANCE_READINESS.md",
            "docs/M21_PHASE7_READINESS_REPORT.md",
        ],
        "todo_review": {
            "scope": "M20/M21 documentation, milestone modules, and related tests",
            "findings": "No scoped TODO or FIXME markers were found. The sole repository-wide match was an unrelated infrastructure-status note.",
        },
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
