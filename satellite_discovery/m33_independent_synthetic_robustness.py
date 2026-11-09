"""M33 independent synthetic robustness and false-alarm stress benchmark.

This layer reuses M29's real read generation/M6 path and M32's validated
M6→M8→M31 execution. It never changes their defaults or triage thresholds.
"""
import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from . import m29_assembly_root_cause_recovery as m29
from . import m32_end_to_end_synthetic_evidence as m32

SCHEMA = "m33-independent-synthetic-robustness-v2"
SEEDS = (33_010_101, 33_020_202, 33_030_303)
REGISTERED_ROLES = {
    0: ("known_reference_positive", "REVIEW_PRIORITY"),
    1: ("reference_absent_adversarial", "INSUFFICIENT_EVIDENCE"),
    6: ("known_reference_positive", "REVIEW_PRIORITY"),
    8: ("known_reference_positive", "REVIEW_PRIORITY"),
    12: ("reference_independent_challenge", "INSUFFICIENT_EVIDENCE"),
    15: ("target_absent_supported_background", "INSUFFICIENT_EVIDENCE"),
    16: ("target_absent_no_contig", "INSUFFICIENT_EVIDENCE"),
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def preregistered_trials(replicates=3):
    """Freeze three independent, deterministic parameter sets before execution."""
    if not isinstance(replicates, int) or not 1 <= replicates <= len(SEEDS):
        raise ValueError("replicates must be an integer from 1 to 3")
    base = m29.case_matrix()
    trials = []
    for rep, seed in enumerate(SEEDS[:replicates]):
        cases = [dict(row) for row in base]
        # M32 selects fixed indices; retain their registered IDs and roles while
        # varying only declared synthetic conditions across independent seeds.
        conditions = {
            0: (80, 100, 0.00, "low"),
            1: (80, 100, (0.02, 0.05, 0.00)[rep], "high"),
            6: ((48, 24, 80)[rep], 100, (0.00, 0.02, 0.00)[rep], "low"),
            8: ((80, 48, 24)[rep], (100, 75, 50)[rep], (0.00, 0.02, 0.05)[rep], "low"),
            12: (80, 100, (0.02, 0.05, 0.00)[rep], "low"),
            15: ((80, 48, 24)[rep], (100, 75, 50)[rep], 0.00, "low"),
            16: (80, 100, 0.00, "low"),
        }
        seed_map = {}
        for index, (coverage, read_length, error, repeat) in conditions.items():
            case = cases[index]
            case.update(coverage=coverage, m25_read_length=read_length,
                        error_rate=error, repeat_complexity=repeat)
            case["_m33_seed"] = seed + index * 101
            seed_map[case["case_id"]] = case["_m33_seed"]
        seed_map["held_out-m32-target_absent_background"] = seed + 99_999
        # M32 turns matrix[15] into a separate target-absent background control.
        trials.append({
            "replicate": f"r{rep + 1}",
            "seed": seed,
            "cases": cases,
            "seed_map": seed_map,
        })
    return trials


def wilson_interval(successes, total, z=1.959963984540054):
    if total <= 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _analysis_category(target_present, experiment_type):
    if not target_present:
        return "target_absent"
    if experiment_type in {
        "reference_absent_adversarial", "reference_independent_challenge",
    }:
        return "target_positive_adversarial"
    return "positive_retrieval_control"


def _review_priority_metrics(case_rows):
    """Score the supplied truth category only when support and M8 are evaluable."""
    eligible_cases, eligible_contigs = [], []
    unevaluable = []
    for case in case_rows:
        supported = [row for row in case.get("candidate_records", [])
                     if row.get("read_support_status") == "READ_SUPPORTED_ASSEMBLY"]
        if not case.get("m8_search_complete") or not supported:
            unevaluable.append({
                "case_id": case["case_id"],
                "experiment_type": case.get("experiment_type", "unclassified"),
                "reason": "no supported contig or M8 incomplete",
            })
            continue
        eligible_cases.append((case, supported))
        eligible_contigs.extend((case, row) for row in supported)
    case_hits = sum(any(row.get("triage_status") == "REVIEW_PRIORITY"
                        for row in supported)
                    for _, supported in eligible_cases)
    contig_hits = sum(row.get("triage_status") == "REVIEW_PRIORITY"
                      for _, row in eligible_contigs)
    return {
        "case_level": {
            "review_priority": case_hits, "eligible_denominator": len(eligible_cases),
            "rate": case_hits / len(eligible_cases) if eligible_cases else None,
            "wilson_95": wilson_interval(case_hits, len(eligible_cases)),
        },
        "contig_level": {
            "review_priority": contig_hits, "eligible_denominator": len(eligible_contigs),
            "rate": contig_hits / len(eligible_contigs) if eligible_contigs else None,
            "wilson_95": wilson_interval(contig_hits, len(eligible_contigs)),
        },
        "unevaluable": unevaluable,
    }


def false_alarm_metrics(case_rows):
    """Keep target-absent false alarms distinct from target-positive challenges."""
    target_absent = [row for row in case_rows
                     if row.get("analysis_category") == "target_absent"]
    positive_adversarial = [
        row for row in case_rows
        if row.get("analysis_category") == "target_positive_adversarial"
    ]

    def summarize(cases):
        summary = _review_priority_metrics(cases)
        summary["by_experiment_type"] = {
            kind: _review_priority_metrics([
                row for row in cases
                if row.get("experiment_type", "unclassified") == kind
            ])
            for kind in sorted({row.get("experiment_type", "unclassified")
                                for row in cases})
        }
        return summary

    # Retain the previous mixed subset for explicit comparison with the first
    # M33 report; it is not a target-absent false-alarm estimate.
    historical_mixed = [
        row for row in case_rows
        if not row.get("target_present_in_synthetic_truth", row.get("positive_control", False))
        or row.get("experiment_type") == "reference_absent_adversarial"
    ]
    return {
        "target_absent_synthetic_false_alarms": summarize(target_absent),
        "target_positive_adversarial_triage": summarize(positive_adversarial),
        "combined_diagnostic_stress": summarize(target_absent + positive_adversarial),
        "historical_mixed_category_comparison": summarize(historical_mixed),
    }


def _reproducibility_signature(report):
    reconstruction = {}
    graph_fields = (
        "status", "sha256", "segment_count", "link_count", "branch_segment_count",
        "dead_end_segment_count", "coverage_tag_count", "coverage_tag_min",
        "coverage_tag_max",
    )
    for row in report["reconstruction_and_handoffs"]:
        graph = row.get("assembly_graph", {})
        reconstruction[row["case_id"]] = {
            "read_input_sha256": row["read_input_sha256"],
            "assembly_status": row["assembly_status"],
            "contig_count": row["contig_count"],
            "handoff_status": row["handoff"]["status"],
            "handoff_candidate_count": row["handoff"].get("candidate_count"),
            # M6 artifact digests include run-specific provenance. Compare the
            # normalized graph evidence instead of those raw bundle digests.
            "assembly_graph": {key: graph.get(key) for key in graph_fields},
        }
    screening = {}
    alignments = {}
    for row in report["candidate_triage"]:
        screening[row["case_id"]] = tuple(sorted(
            (candidate.get("candidate_id"), candidate.get("query_sha256"),
             candidate.get("read_support_status"), candidate.get("m8_aggregate_status"),
             tuple(candidate.get("reference_panel_entries", ())),
             candidate.get("triage_status"))
            for candidate in row.get("candidate_records", [])
        ))
        normalized = [{
            "candidate_id": match.get("candidate_id"),
            "accession_version": match.get("reference", {}).get("accession_version"),
            "panel_role": match.get("panel_role"),
            "masking_branch": match.get("masking_branch"),
            "alignment": match.get("alignment"),
        } for match in row.get("matches", [])]
        alignments[row["case_id"]] = _sha(json.dumps(
            sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True)),
            sort_keys=True, separators=(",", ":")).encode())
    return {"reconstruction": reconstruction, "screening": screening,
            "normalized_alignment_sha256": alignments}


class ReproducibilityMismatchError(RuntimeError):
    """Raised after reports are saved when the same-seed repeat differs."""


def compare_reproducibility(reference, repeat):
    stage_keys = {
        "reconstruction": "reconstruction",
        "screening_triage": "screening",
        "normalized_alignment": "normalized_alignment_sha256",
    }
    differences = {}
    for stage, key in stage_keys.items():
        left, right = reference[key], repeat[key]
        differences[stage] = sorted(
            case_id for case_id in set(left) | set(right)
            if left.get(case_id) != right.get(case_id)
        )
    differences = {stage: cases for stage, cases in differences.items() if cases}
    return {
        "status": "REPRODUCIBILITY_MISMATCH" if differences else "REPRODUCIBLE",
        "fully_reproducible": not differences,
        "differing_stages": differences,
    }


def validate_reproducibility(outcome):
    if not outcome["fully_reproducible"]:
        raise ReproducibilityMismatchError(
            "M33 same-seed repeat mismatch: "
            + json.dumps(outcome["differing_stages"], sort_keys=True)
        )


def run(output, blastn, makeblastdb, blastdbcmd=None, replicates=3):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite M33 output: {output}")
    trials = preregistered_trials(replicates)
    prereg = {
        "schema": "m33-preregistered-design-v1",
        "seeds": list(SEEDS),
        "cases": [{
            "replicate": trial["replicate"],
            "case_id": case["case_id"],
            "split": case["case_id"].split("-", 1)[0],
            "seed": trial["seed_map"].get(case["case_id"], trial["seed"]),
            "positive": bool(case["positive"]),
            "coverage": case["coverage"],
            "read_length": case["m25_read_length"],
            "substitution_error_rate": case["error_rate"],
            "repeat_complexity": case["repeat_complexity"],
            "analysis_id": case["analysis_id"],
            "experiment_type": REGISTERED_ROLES[
                next(index for index, row in enumerate(trial["cases"])
                     if row["case_id"] == case["case_id"])
            ][0],
            "expected_triage_outcome": REGISTERED_ROLES[
                next(index for index, row in enumerate(trial["cases"])
                     if row["case_id"] == case["case_id"])
            ][1],
        } for trial in trials for case in trial["cases"]
          if case["case_id"] in trial["seed_map"]],
        "appended_background_controls": [{
            "replicate": trial["replicate"],
            "case_id": "held_out-m32-target_absent_background",
            "seed": trial["seed_map"]["held_out-m32-target_absent_background"],
            "experiment_type": "target_absent_supported_background",
            "expected_triage_outcome": "INSUFFICIENT_EVIDENCE",
            "coverage": trial["cases"][15]["coverage"],
            "read_length": trial["cases"][15]["m25_read_length"],
        } for trial in trials],
        "held_out_truth_policy": (
            "Panel and conditions are frozen before M6; truth is read only by "
            "the reused M32 retrospective scoring stage after M8 triage."
        ),
        "repeat_run": {"reference": "r1", "repeat": "repeat-r1",
                       "same_preregistered_seed": True},
        "limitations": [
            "The reused read generator models substitutions; insertion/deletion stress is unavailable.",
            "The matrix is a bounded synthetic diagnostic, not biological validation.",
        ],
        "governance": {
            "decision": "INCOMPLETE",
            "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
            "biological_execution_authorized": False,
        },
    }
    prereg["design_sha256"] = _sha(json.dumps(
        prereg, sort_keys=True, separators=(",", ":")).encode())
    (output / "M33_PREREGISTERED_DESIGN.json").write_text(
        json.dumps(prereg, sort_keys=True, indent=2) + "\n")

    reports = []
    original_seed = m29._case_seed
    for trial in trials + [dict(trials[0], replicate="repeat-r1")]:
        def seed_for(case):
            return trial["seed_map"].get(case["case_id"], original_seed(case))
        trial_output = output / trial["replicate"]
        # The M32 success gate is intentionally replaced only in this isolated
        # diagnostic invocation: stress failures are data, not silently dropped.
        with patch.object(m29, "case_matrix", return_value=trial["cases"]), \
             patch.object(m29, "_case_seed", side_effect=seed_for), \
             patch.object(m32, "validate_success_criteria", return_value=None):
            result = m32.run(trial_output, blastn, makeblastdb, blastdbcmd)
        for triage_row in result["candidate_triage"]:
            for artifact in triage_row.get("raw_outputs", []):
                artifact_path = trial_output / artifact["path"]
                if (not artifact_path.is_file()
                        or artifact_path.stat().st_size != artifact["size_bytes"]
                        or _sha(artifact_path.read_bytes()) != artifact["sha256"]):
                    raise RuntimeError(f"M33 raw M8 output failed digest validation: {artifact['path']}")
        reports.append((trial["replicate"], result, trial_output))

    reproducibility = compare_reproducibility(
        _reproducibility_signature(reports[0][1]),
        _reproducibility_signature(reports[-1][1]),
    )
    reproducibility.update({
        "repeat": "repeat-r1",
        "reference": "r1",
        "result_bundles": {"reference": "r1", "repeat": "repeat-r1"},
    })

    family_digests = {}
    for replicate, report, _ in reports[:-1]:
        family_digests[replicate] = {
            row["sequence_sha256"]
            for row in report["panel_preregistration"]["records"]
            if row.get("role") == "satellite_subviral"
        }
    independent_reports = reports[:-1]
    for left_index, left in enumerate(independent_reports):
        for right in independent_reports[left_index + 1:]:
            shared = family_digests[left[0]] & family_digests[right[0]]
            if shared:
                raise RuntimeError(
                    f"M33 independent target families overlap: {left[0]} / {right[0]}"
                )

    all_cases = []
    for replicate, report, trial_output in reports[:-1]:
        triage = {row["case_id"]: row for row in report["candidate_triage"]}
        execution = {row["case_id"]: row for row in report["reconstruction_and_handoffs"]}
        trial = next(row for row in trials if row["replicate"] == replicate)
        design_by_id = {row["case_id"]: row for row in trial["cases"]}
        for metric in report["benchmark_metrics"]["cases"]:
            case_id = metric["case_id"]
            triage_row = triage[case_id]
            executed = execution[case_id]
            design = (trial["cases"][15] if case_id == "held_out-m32-target_absent_background"
                      else design_by_id[case_id])
            all_cases.append({
                "case_id": f"{replicate}:{case_id}",
                "source_case_id": case_id,
                "replicate": replicate,
                "split": metric["split"],
                "experiment_type": metric["experiment_type"],
                "positive_control": metric["positive_control"],
                "target_present_in_synthetic_truth": bool(metric["positive_control"]),
                "analysis_category": _analysis_category(
                    bool(metric["positive_control"]), metric["experiment_type"]),
                "coverage": design["coverage"],
                "read_length": design["m25_read_length"],
                "substitution_error_rate": design["error_rate"],
                "negative_or_decoy": (
                    not metric["positive_control"]
                    or metric["experiment_type"] in {
                        "reference_absent_adversarial", "target_absent_supported_background",
                    }
                ),
                "assembly_recovery": metric["assembly_recovery"],
                "supported_exact_recovery": metric["supported_exact_recovery"],
                "handoff_complete": metric["m6_to_m8_handoff"],
                "m8_search_complete": metric["m8_search_complete"],
                "supported_contig_ids": metric["supported_contig_ids"],
                "candidate_records": triage_row.get("candidate_records", []),
                "failure_reason": triage_row.get("reason"),
                "assembly_status": executed["assembly_status"],
                "contig_count": executed["contig_count"],
                "read_input_sha256": executed["read_input_sha256"],
                "source_manifest_sha256": executed["source_manifest_sha256"],
                "m6_reconstruction_sha256": executed["m6_reconstruction_sha256"],
                "assembler": executed["assembler"],
                "assembly_configuration": executed["assembly_configuration"],
                "support_criteria": executed["support_criteria"],
                "raw_m8_outputs": triage_row.get("raw_outputs", []),
            })
    false_alarms = false_alarm_metrics(all_cases)
    outcomes = {}
    for case in all_cases:
        for candidate in case["candidate_records"]:
            label = candidate.get("triage_status", "NOT_REPORTED")
            outcomes[label] = outcomes.get(label, 0) + 1
    by_condition = {}
    for case in all_cases:
        if not case["positive_control"]:
            continue
        key = (case["coverage"], case["read_length"], case["substitution_error_rate"])
        row = by_condition.setdefault(key, {"cases": 0, "exact_supported": 0,
                                             "completed_m8": 0})
        row["cases"] += 1
        row["exact_supported"] += bool(case["supported_exact_recovery"])
        row["completed_m8"] += bool(case["m8_search_complete"])
    report = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "production_defaults_changed": False,
        "case_count": len(all_cases),
        "replicate_count": len(reports) - 1,
        "repeat_run_count": 1,
        "independent_replicate_count": len(reports) - 1,
        "reproducibility": reproducibility,
        "runtime_by_replicate": {
            name: {
                "runtime": report["runtime"],
                "panel_digest": report["panel_digest"],
                "panel_preregistration": report["panel_preregistration"],
            } for name, report, _ in reports
        },
        "cases": all_cases,
        "technical_summary": {
            "positive_case_count": sum(row["positive_control"] for row in all_cases),
            "exact_supported_reconstructions": sum(
                row["supported_exact_recovery"] for row in all_cases if row["positive_control"]),
            "supported_exact_reconstruction_rate": (
                sum(row["supported_exact_recovery"] for row in all_cases if row["positive_control"])
                / max(1, sum(row["positive_control"] for row in all_cases))
            ),
            "no_assembly_cases": sum(row["assembly_status"] == "NO_SUPPORTED_ASSEMBLY"
                                     for row in all_cases),
            "validated_handoffs": sum(row["handoff_complete"] for row in all_cases),
            "completed_m8": sum(row["m8_search_complete"] for row in all_cases),
            "triage_outcomes_by_contig": outcomes,
            "positive_results_by_coverage_read_length_substitution_rate": [
                {"coverage": key[0], "read_length": key[1], "substitution_error_rate": key[2],
                 **value}
                for key, value in sorted(by_condition.items())
            ],
        },
        "synthetic_review_priority_false_alarm_rates": false_alarms,
        "governance": prereg["governance"],
        "interpretation": (
            "Rates describe synthetic triage false alarms only; biological "
            "specificity and biological false-discovery rate are NOT_EVALUATED."
        ),
    }
    (output / "M33_INDEPENDENT_SYNTHETIC_ROBUSTNESS.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n")
    (output / "M33_INDEPENDENT_SYNTHETIC_ROBUSTNESS.md").write_text(
        render_markdown(report), encoding="utf-8")
    validate_reproducibility(reproducibility)
    return report


def render_markdown(report):
    lines = [
        "# M33 — Independent synthetic robustness and false-alarm stress testing", "",
        "Synthetic-only diagnostic; biological satellite-virus discovery remains NOT_EVALUATED.", "",
        f"Cases: {report['case_count']} across {report['replicate_count']} independent seeded runs.", "",
    ]
    reproducibility = report["reproducibility"]
    lines += [
        "## Same-seed reproducibility",
        "",
        f"Status: **{reproducibility['status']}**.",
        f"Fully reproducible: `{str(reproducibility['fully_reproducible']).lower()}`.",
    ]
    if reproducibility["differing_stages"]:
        lines += ["", "Differing stages and cases:"]
        for stage, case_ids in sorted(reproducibility["differing_stages"].items()):
            lines.append(f"- {stage}: {', '.join(case_ids)}")
    lines += ["", "Both result bundles are retained under the reference and repeat output directories.",
              "", "## Synthetic triage outcomes by truth category", ""]
    categories = report["synthetic_review_priority_false_alarm_rates"]
    for key, title in (
        ("target_absent_synthetic_false_alarms", "Target-absent synthetic false alarms"),
        ("target_positive_adversarial_triage", "Target-positive adversarial triage"),
        ("combined_diagnostic_stress", "Combined diagnostic stress (mixed categories)"),
        ("historical_mixed_category_comparison", "Historical mixed-category comparison"),
    ):
        metrics = categories[key]
        lines += [
            f"### {title}", "",
            "| Unit | REVIEW_PRIORITY | Eligible denominator | Rate | Wilson 95% interval |",
            "|---|---:|---:|---:|---|",
        ]
        for label, field in (("Case", "case_level"), ("Contig", "contig_level")):
            row = metrics[field]
            lines.append(
                f"| {label} | {row['review_priority']} | {row['eligible_denominator']} | "
                f"{row['rate']} | {row['wilson_95']} |"
            )
        lines += ["", "Unevaluable cases:"]
        if metrics["unevaluable"]:
            lines.extend(f"- {row['case_id']}: {row['reason']}"
                         for row in metrics["unevaluable"])
        else:
            lines.append("- None")
        lines.append("")
    lines += ["Unevaluable cases are retained with reasons in the JSON report.",
              "Substitution errors are exercised; insertion/deletion errors are not modeled by the reused generator.",
              "Target-positive challenges are not counted as target-absent false alarms. "
              "These are synthetic triage outcomes, not biological false-positive estimates.", "",
              "```text", "decision=INCOMPLETE",
              "overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION",
              "biological_execution_authorized=false", "```", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blastn", required=True)
    parser.add_argument("--makeblastdb", required=True)
    parser.add_argument("--blastdbcmd")
    parser.add_argument("--replicates", type=int, choices=(1, 2, 3), default=3)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output, args.blastn, args.makeblastdb,
                         args.blastdbcmd, args.replicates)["governance"]))


if __name__ == "__main__":
    main()
