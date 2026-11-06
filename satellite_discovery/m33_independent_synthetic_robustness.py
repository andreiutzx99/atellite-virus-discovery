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

SCHEMA = "m33-independent-synthetic-robustness-v1"
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


def false_alarm_metrics(case_rows):
    """Score only negative/decoy cases with supported contigs and completed M8."""
    eligible_cases, eligible_contigs = [], []
    unevaluable = []
    for case in case_rows:
        if not case.get("negative_or_decoy"):
            continue
        candidates = case.get("candidate_records", [])
        supported = [row for row in candidates
                     if row.get("read_support_status") == "READ_SUPPORTED_ASSEMBLY"]
        if not case.get("m8_search_complete") or not supported:
            unevaluable.append({"case_id": case["case_id"],
                                "reason": "no supported contig or M8 incomplete"})
            continue
        eligible_cases.append(case)
        eligible_contigs.extend((case, row) for row in supported)
    case_hits = sum(any(row.get("triage_status") == "REVIEW_PRIORITY"
                        for row in case["candidate_records"]
                        if row.get("read_support_status") == "READ_SUPPORTED_ASSEMBLY")
                    for case in eligible_cases)
    contig_hits = sum(row.get("triage_status") == "REVIEW_PRIORITY"
                      for _, row in eligible_contigs)
    result = {
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
    result["by_experiment_type"] = {}
    for kind in sorted({row.get("experiment_type", "unclassified") for row in case_rows
                        if row.get("negative_or_decoy")}):
        subset = [row for row in case_rows
                  if row.get("negative_or_decoy")
                  and row.get("experiment_type", "unclassified") == kind]
        eligible = []
        contigs = []
        for case in subset:
            supported = [row for row in case.get("candidate_records", [])
                         if row.get("read_support_status") == "READ_SUPPORTED_ASSEMBLY"]
            if case.get("m8_search_complete") and supported:
                eligible.append((case, supported))
                contigs.extend(supported)
        case_hits = sum(any(row.get("triage_status") == "REVIEW_PRIORITY"
                            for row in supported) for _, supported in eligible)
        contig_hits = sum(row.get("triage_status") == "REVIEW_PRIORITY" for row in contigs)
        result["by_experiment_type"][kind] = {
            "case_level": {
                "review_priority": case_hits, "eligible_denominator": len(eligible),
                "rate": case_hits / len(eligible) if eligible else None,
                "wilson_95": wilson_interval(case_hits, len(eligible)),
            },
            "contig_level": {
                "review_priority": contig_hits, "eligible_denominator": len(contigs),
                "rate": contig_hits / len(contigs) if contigs else None,
                "wilson_95": wilson_interval(contig_hits, len(contigs)),
            },
        }
    return result


def _reproducibility_signature(report):
    reconstruction = {
        row["case_id"]: (row["read_input_sha256"], row["assembly_status"],
                         row["contig_count"], row["handoff"]["status"])
        for row in report["reconstruction_and_handoffs"]
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
        alignments[row["case_id"]] = _sha(json.dumps(
            sorted(row.get("matches", []),
                   key=lambda item: json.dumps(item, sort_keys=True)),
            sort_keys=True, separators=(",", ":")).encode())
    return {"reconstruction": reconstruction, "screening": screening,
            "normalized_alignment_sha256": alignments}


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

    reproducibility = {
        "repeat": "repeat-r1",
        "reference": "r1",
        "reconstruction_and_screening_stable": (
            _reproducibility_signature(reports[0][1])
            == _reproducibility_signature(reports[-1][1])
        ),
    }

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
    return report


def render_markdown(report):
    rates = report["synthetic_review_priority_false_alarm_rates"]
    lines = [
        "# M33 — Independent synthetic robustness and false-alarm stress testing", "",
        "Synthetic-only diagnostic; biological satellite-virus discovery remains NOT_EVALUATED.", "",
        f"Cases: {report['case_count']} across {report['replicate_count']} independent seeded runs.", "",
        "## Synthetic negative/decoy REVIEW_PRIORITY rates", "",
        "| Unit | REVIEW_PRIORITY | Eligible denominator | Rate | Wilson 95% interval |",
        "|---|---:|---:|---:|---|",
    ]
    for label, key in (("Case", "case_level"), ("Contig", "contig_level")):
        row = rates[key]
        interval = row["wilson_95"]
        lines.append(f"| {label} | {row['review_priority']} | {row['eligible_denominator']} | "
                     f"{row['rate']} | {interval} |")
    lines += ["", "## Unevaluable cases", ""]
    lines.extend(f"- {row['case_id']}: {row['reason']}" for row in rates["unevaluable"])
    lines += ["", "Unevaluable negative/decoy cases are retained with reasons in the JSON report.",
              "Substitution errors are exercised; insertion/deletion errors are not modeled by the reused generator.",
              "These rates are synthetic triage false alarms, not biological false-positive estimates.", "",
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
