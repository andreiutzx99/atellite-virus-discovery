"""M34 deterministic synthetic negative-control and indel robustness study."""
import argparse
import hashlib
import json
import random
from pathlib import Path
from unittest.mock import patch

from . import m25_read_coverage as m25
from . import m29_assembly_root_cause_recovery as m29
from . import m32_end_to_end_synthetic_evidence as m32
from . import m33_independent_synthetic_robustness as m33

GOVERNANCE = {
    "decision": "INCOMPLETE",
    "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
    "biological_execution_authorized": False,
}
NEGATIVE_CATEGORIES = (
    "random", "gc_rich", "gc_poor", "low_complexity", "repetitive",
    "partial_reference_similarity", "near_target_divergence", "mixed_background",
)
ERROR_CONDITIONS = (
    ("zero_error", 0.0, 0.0, 0.0, 48, 100),
    ("substitution_only", 0.02, 0.0, 0.0, 48, 100),
    ("insertion_only", 0.0, 0.01, 0.0, 48, 100),
    ("deletion_only", 0.0, 0.0, 0.01, 48, 100),
    ("combined_low", 0.01, 0.005, 0.005, 24, 75),
    ("combined_moderate", 0.02, 0.01, 0.01, 48, 100),
    ("combined_higher", 0.05, 0.03, 0.03, 80, 150),
)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _wilson(k, n):
    if not n:
        return None
    z = 1.959963984540054
    p = k / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [max(0.0, center - margin), min(1.0, center + margin)]


def preregistered_design(negative_per_category=8):
    if not isinstance(negative_per_category, int) or negative_per_category < 1:
        raise ValueError("negative_per_category must be a positive integer")
    base = m29.case_matrix()
    known_ids = {
        "development-m29-positive_control",
        "tuning-m29-synthetic_background",
        "held_out-m29-positive_control",
    }
    cases = [dict(row) for row in base if row["case_id"] in known_ids]
    category_by_id, seed_by_id, generator_seed_by_id = {}, {}, {}
    condition_by_id, negative_condition_by_id = {}, {}
    for case in cases:
        seed_by_id[case["case_id"]] = m29._case_seed(case)
        generator_seed_by_id[case["case_id"]] = (
            seed_by_id[case["case_id"]] + sum(case["analysis_id"].encode())
        )
    serial = 0
    for category_index, category in enumerate(NEGATIVE_CATEGORIES):
        for replicate in range(negative_per_category):
            serial += 1
            seed = 34_000_001 + category_index * 10_007 + replicate * 101
            split = ("development", "tuning", "held_out")[replicate % 3]
            case = m25._case_design(split, replicate + 1)
            condition_index = replicate % len(ERROR_CONDITIONS)
            condition, sub, ins, dele, coverage, read_length = ERROR_CONDITIONS[condition_index]
            case.update(
                case_id=f"{split}-m34-c{serial:04d}", analysis_id=f"m34x{serial:04d}",
                positive=False, target_length=900, coverage=coverage,
                error_rate=sub, insertion_rate=ins, deletion_rate=dele,
                m25_apply_background_errors=True,
                m25_background_read_coverage=True,
                m29_factor="m34_expanded_target_absent_control",
                m25_read_length=read_length,
                repeat_complexity="low", opaque_read_ids=True,
            )
            cases.append(case)
            category_by_id[case["case_id"]] = category
            seed_by_id[case["case_id"]] = seed
            generator_seed_by_id[case["case_id"]] = seed + sum(case["analysis_id"].encode())
            negative_condition_by_id[case["case_id"]] = condition
    indel_cases = []
    for index, (name, sub, ins, dele, coverage, read_length) in enumerate(ERROR_CONDITIONS):
        serial += 1
        split = ("development", "tuning", "held_out")[index % 3]
        case = m25._case_design(split, index + 1)
        case.update(
            case_id=f"{split}-m34-i{index + 1:03d}", analysis_id=f"m34i{index + 1:03d}",
            positive=True, target_length=900, coverage=coverage, error_rate=sub,
            insertion_rate=ins, deletion_rate=dele, m25_read_length=read_length,
            m29_factor="m34_indel_robustness",
            repeat_complexity="low", opaque_read_ids=True,
        )
        cases.append(case)
        seed_by_id[case["case_id"]] = 34_900_001 + index * 997
        generator_seed_by_id[case["case_id"]] = (
            seed_by_id[case["case_id"]] + sum(case["analysis_id"].encode())
        )
        condition_by_id[case["case_id"]] = name
        indel_cases.append(case)
    contracts = {}
    for case in cases:
        if case["case_id"] in known_ids:
            kind, expected = "known_reference_positive", "REVIEW_PRIORITY"
        elif case["positive"]:
            kind, expected = "reference_independent_challenge", "INSUFFICIENT_EVIDENCE"
        else:
            kind, expected = "target_absent_supported_background", "INSUFFICIENT_EVIDENCE"
        contracts[case["case_id"]] = {
            "experiment_type": kind,
            "expected_triage_outcome": expected,
            "expected_exact_target_triage_outcome": (
                "REVIEW_PRIORITY" if kind == "known_reference_positive"
                else "INSUFFICIENT_EVIDENCE"
            ),
            "expected_non_target_triage_outcome": "INSUFFICIENT_EVIDENCE",
        }
    return {
        "cases": cases, "contracts": contracts, "seed_by_id": seed_by_id,
        "generator_seed_by_id": generator_seed_by_id,
        "category_by_id": category_by_id, "condition_by_id": condition_by_id,
        "negative_condition_by_id": negative_condition_by_id,
        "indel_cases": indel_cases,
    }


def _background(category, seed, length, target_reference):
    rng = random.Random(seed)
    if category == "partial_reference_similarity":
        fragment = target_reference[250:250 + length]
        seq = list(fragment.ljust(length, "A"))
        for i in rng.sample(range(len(seq)), max(1, round(len(seq) * 0.18))):
            seq[i] = rng.choice("ACGT".replace(seq[i], ""))
        return "".join(seq)
    if category == "near_target_divergence":
        seq = list(target_reference[:length].ljust(length, "A"))
        for i in rng.sample(range(len(seq)), max(1, round(len(seq) * 0.10))):
            seq[i] = rng.choice("ACGT".replace(seq[i], ""))
        return "".join(seq)
    if category == "low_complexity":
        return ("A" * length)
    if category == "repetitive":
        return ("ACGT" * ((length + 3) // 4))[:length]
    if category == "mixed_background":
        first = length // 3
        second = length // 3
        third = length - first - second
        return ("A" * first
                + ("ACGT" * ((second + 3) // 4))[:second]
                + "".join(rng.choices("ACGT", k=third)))
    gc = {"gc_rich": .8, "gc_poor": .2}.get(category, .5)
    return "".join(rng.choices("ACGT", weights=((1-gc)/2, gc/2, gc/2, (1-gc)/2),
                               k=length))


def _metrics(cases):
    eligible, unevaluable = [], []
    for row in cases:
        supported = [x for x in row["candidate_records"]
                     if x.get("read_support_status") == "READ_SUPPORTED_ASSEMBLY"]
        if row["m8_search_complete"] and supported:
            eligible.append((row, supported))
        else:
            unevaluable.append({"case_id": row["case_id"], "reason": row.get("failure_reason")
                                or "no supported contig or M8 incomplete"})
    case_hits = sum(any(x.get("triage_status") == "REVIEW_PRIORITY" for x in supported)
                    for _, supported in eligible)
    contigs = [x for _, group in eligible for x in group]
    contig_hits = sum(x.get("triage_status") == "REVIEW_PRIORITY" for x in contigs)
    return {
        "case_level": {"review_priority": case_hits, "eligible_denominator": len(eligible),
                       "rate": case_hits / len(eligible) if eligible else None,
                       "wilson_95": _wilson(case_hits, len(eligible))},
        "contig_level": {"review_priority": contig_hits,
                         "eligible_denominator": len(contigs),
                         "rate": contig_hits / len(contigs) if contigs else None,
                         "wilson_95": None,
                         "interval_note": (
                             "not computed because contigs cluster within cases; "
                             "case is the inferential unit"
                         )},
        "unevaluable": unevaluable,
    }


def _validate_m34_pipeline(report, output):
    metrics = report["benchmark_metrics"]["cases"]
    by_case = {row["case_id"]: row for row in report["candidate_triage"]}
    known = next((row for row in metrics if row["split"] == "held_out"
                  and row["experiment_type"] == "known_reference_positive"), None)
    required = ("assembly_recovery", "supported_exact_recovery",
                "m6_to_m8_handoff", "m8_search_complete")
    if not known or not all(known[key] for key in required):
        raise RuntimeError("M34 held-out known-reference control failed its evidence chain")
    if known["reference_panel_status"] != "PRESENT":
        raise RuntimeError("M34 held-out known-reference control is absent from its frozen panel")
    known_triage = by_case[known["case_id"]]
    exact_ids = set(known["supported_exact_contig_ids"])
    if not any(item.get("candidate_id") in exact_ids
               and item.get("outcome") == "REVIEW_PRIORITY"
               for item in known_triage.get("outcome", [])):
        raise RuntimeError("M34 known-reference control missed its expected triage outcome")

    for metric in metrics:
        if metric["experiment_type"] == "known_reference_positive" \
                or not metric["m8_search_complete"]:
            continue
    for triage in report["candidate_triage"]:
        for artifact in triage.get("raw_outputs", []):
            path = Path(output) / artifact["path"]
            if not path.is_file() or path.stat().st_size != artifact["size_bytes"] \
                    or m32._sha(path.read_bytes()) != artifact["sha256"]:
                raise RuntimeError(f"M34 raw M8 output failed digest validation: {artifact['path']}")


def _save_read_provenance(output, captured):
    import hashlib

    output = Path(output)
    rows = {}
    for case_id, layout in captured.items():
        data = (json.dumps(layout, sort_keys=True, separators=(",", ":")) + "\n").encode()
        path = output / "read_provenance" / f"{case_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        rows[case_id] = {
            "path": str(path.relative_to(output)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "read_count": len(layout.get("read_provenance", {})),
        }
    return rows


def _validate_target_absence_truth(output, cases):
    output = Path(output)
    validations = {}
    for case in cases:
        if case["positive"]:
            continue
        path = output / "reconstruction" / case["case_id"] / "heldout_truth.json"
        if not path.is_file():
            raise RuntimeError(f"M34 target-absent truth sidecar is missing: {case['case_id']}")
        document = json.loads(path.read_text(encoding="utf-8"))
        truth_cases = document.get("cases", [])
        if len(truth_cases) != 1 or truth_cases[0].get("candidate_sequence") is not None:
            raise RuntimeError(
                f"M34 target-absent source truth contains a target: {case['case_id']}"
            )
        validations[case["case_id"]] = {
            "candidate_sequence_absent": True,
            "source_truth_sidecar_sha256": _sha(path.read_bytes()),
        }
    return {
        "status": "VERIFIED",
        "method": "registered held-out synthetic truth sidecar has null candidate_sequence",
        "case_count": len(validations),
        "cases": validations,
    }


def _execute_bundle(output, design, cases, blastn, makeblastdb, blastdbcmd):
    captured = {}
    original_run_case = m29._run_case
    original_seed = m29._case_seed
    original_fastq = m25._make_fastq
    target_reference = m32._target_sequence_from_design(
        next(c for c in cases if c["case_id"] == "held_out-m29-positive_control")
    )

    def seed_for(case):
        return design["seed_by_id"].get(case["case_id"], original_seed(case))

    def fastq(case, truth, reference, params, backgrounds=()):
        category = design["category_by_id"].get(case["case_id"])
        if category:
            bg = _background(category, design["seed_by_id"][case["case_id"]], 900,
                             target_reference)
            backgrounds = (*backgrounds, bg)
        return original_fastq(case, truth, reference, params, backgrounds)

    def run_case(root, case):
        report, state = original_run_case(root, case)
        captured[case["case_id"]] = state.get("_m25_layout", {})
        return report, state

    with patch.object(m29, "case_matrix", return_value=list(cases)), \
         patch.object(m29, "_case_seed", side_effect=seed_for), \
         patch.object(m29, "_run_case", side_effect=run_case), \
         patch.object(m25, "_make_fastq", side_effect=fastq), \
         patch.object(m32, "_benchmark_design",
                      return_value=(list(cases), design["contracts"])), \
         patch.object(m32, "validate_success_criteria",
                      side_effect=lambda report, path: _validate_m34_pipeline(report, path)):
        report = m32.run(output, blastn, makeblastdb, blastdbcmd)
    absence_validation = _validate_target_absence_truth(output, cases)
    provenance_index = _save_read_provenance(output, captured)
    report["m34_read_provenance"] = provenance_index
    report["m34_target_absence_validation"] = absence_validation
    (Path(output) / "M34_READ_PROVENANCE_INDEX.json").write_text(
        json.dumps(provenance_index, sort_keys=True, indent=2) + "\n")
    (Path(output) / "M34_TARGET_ABSENCE_VALIDATION.json").write_text(
        json.dumps(absence_validation, sort_keys=True, indent=2) + "\n")
    return report, captured


def run(output, blastn, makeblastdb, blastdbcmd=None, negative_per_category=8):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite M34 output: {output}")
    if negative_per_category < len(ERROR_CONDITIONS):
        raise ValueError(
            "M34 requires at least seven negative replicates per category to cover every error condition"
        )
    design = preregistered_design(negative_per_category)
    design_doc = {
        "schema": "m34-preregistered-design-v1",
        "independent_seeds": design["seed_by_id"],
        "effective_read_generator_seeds": design["generator_seed_by_id"],
        "target_absent_categories": list(NEGATIVE_CATEGORIES),
        "negative_case_ids_by_category": {
            category: [cid for cid, value in design["category_by_id"].items()
                       if value == category] for category in NEGATIVE_CATEGORIES
        },
        "indel_conditions": {
            cid: {"name": design["condition_by_id"][cid],
                  "substitution_rate": case["error_rate"],
                  "insertion_rate": case["insertion_rate"],
                  "deletion_rate": case["deletion_rate"],
                  "coverage": case["coverage"], "read_length": case["m25_read_length"]}
            for cid, case in ((x["case_id"], x) for x in design["indel_cases"])
        },
        "target_absent_error_conditions": {
            cid: name for cid, name in design["negative_condition_by_id"].items()
        },
        "case_factors": {
            case["case_id"]: {
                "seed": design["seed_by_id"][case["case_id"]],
                "effective_read_generator_seed": design["generator_seed_by_id"][case["case_id"]],
                "target_present": bool(case["positive"]),
                "read_length": case["m25_read_length"],
                "coverage": case["coverage"],
                "substitution_rate": case.get("error_rate", 0.0),
                "insertion_rate": case.get("insertion_rate", 0.0),
                "deletion_rate": case.get("deletion_rate", 0.0),
                "apply_errors_to_target_absent_background": case.get(
                    "m25_apply_background_errors", False),
                "background_read_coverage": case.get("m25_background_read_coverage", False),
                "background_category": design["category_by_id"].get(case["case_id"]),
                "indel_condition": design["condition_by_id"].get(case["case_id"]),
                "target_absent_error_condition": design["negative_condition_by_id"].get(
                    case["case_id"]),
            } for case in design["cases"]
        },
        "truth_policy": (
            "generator truth selects target presence; held-out sequence truth and category labels "
            "are excluded from M6/M8 inputs, which use opaque case IDs and generated reads"
        ),
        "sample_size_target": {
            "minimum_target_absent_cases": 30,
            "planned_target_absent_cases": len(design["category_by_id"]),
            "achieved_target_absent_cases": len(design["category_by_id"]),
        },
        "governance": GOVERNANCE,
    }
    design_doc["design_sha256"] = _sha(json.dumps(
        design_doc, sort_keys=True, separators=(",", ":")).encode())
    (output / "M34_PREREGISTERED_DESIGN.json").write_text(
        json.dumps(design_doc, sort_keys=True, indent=2) + "\n")
    report, error_provenance = _execute_bundle(
        output / "benchmark", design, design["cases"], blastn, makeblastdb, blastdbcmd)
    triage = {x["case_id"]: x for x in report["candidate_triage"]}
    execution = {x["case_id"]: x for x in report["reconstruction_and_handoffs"]}
    metric_rows = {x["case_id"]: x for x in report["benchmark_metrics"]["cases"]}
    rows = []
    for case in design["cases"]:
        cid = case["case_id"]
        metric, triage_row, executed = metric_rows[cid], triage[cid], execution[cid]
        category = design["category_by_id"].get(cid)
        condition = design["condition_by_id"].get(cid)
        provenance = error_provenance.get(cid, {})
        candidate_records = triage_row.get("candidate_records", [])
        exact_supported = bool(metric["supported_exact_recovery"])
        partial_supported = bool(case["positive"] and not exact_supported and any(
            (comparison := item.get("retrospective_truth_comparison", {}).get("comparison"))
            and not comparison.get("strand_exact_match")
            and comparison.get("local_alignment_identity", 0) >= .95
            and comparison.get("target_coverage", 0) >= .50
            and item.get("read_support_status") == "READ_SUPPORTED_ASSEMBLY"
            for item in candidate_records
        ))
        rows.append({
            "case_id": cid, "analysis_id": case["analysis_id"],
            "synthetic_truth_target_present": bool(case["positive"]),
            "seed": design["seed_by_id"][cid],
            "effective_read_generator_seed": design["generator_seed_by_id"][cid],
            "coverage": case["coverage"],
            "read_length": case["m25_read_length"],
            "background_category": category,
            "indel_condition": condition,
            "target_absent_error_condition": design["negative_condition_by_id"].get(cid),
            "error_model": {k: case.get(k, 0.0) for k in
                            ("error_rate", "insertion_rate", "deletion_rate")},
            "realized_error_totals": {
                op: sum(r.get(op, 0) for r in provenance.get("read_provenance", {}).values())
                for op in ("substitutions", "insertions", "deletions")},
            "read_provenance_count": len(provenance.get("read_provenance", {})),
            "assembly_status": executed["assembly_status"],
            "assembly_graph": executed.get("assembly_graph"),
            "read_support_outcomes": triage_row.get("support_by_contig", {}),
            "handoff_success": executed["handoff"]["status"],
            "m8_search_complete": metric["m8_search_complete"],
            "triage_outcome": triage_row["outcome"],
            "candidate_records": candidate_records,
            "exact_supported_reconstruction": exact_supported,
            "partial_reconstruction": partial_supported,
            "failure_reason": triage_row.get("reason"),
        })
    negatives = [row for row in rows if row["background_category"]]
    by_category = {category: _metrics([r for r in negatives
                                       if r["background_category"] == category])
                   for category in NEGATIVE_CATEGORIES}
    for category, category_metrics in by_category.items():
        category_metrics["generated_cases"] = sum(
            row["background_category"] == category for row in negatives
        )
    target_absent = _metrics(negatives)
    target_absent["generated_cases"] = len(negatives)
    target_absent_by_error_condition = {
        condition: _metrics([row for row in negatives
                             if row["target_absent_error_condition"] == condition])
        for condition in dict.fromkeys(design["negative_condition_by_id"].values())
    }
    for condition, condition_metrics in target_absent_by_error_condition.items():
        condition_metrics["generated_cases"] = sum(
            row["target_absent_error_condition"] == condition for row in negatives
        )
    indel_rows = [r for r in rows if r["indel_condition"]]
    by_condition = {
        design["condition_by_id"][row["case_id"]]: {
            "exact_supported": bool(row["exact_supported_reconstruction"]),
            "partial_supported": bool(row["partial_reconstruction"]),
            "case_id": row["case_id"], "assembly_status": row["assembly_status"],
            "error_model": row["error_model"],
            "coverage": row["coverage"], "read_length": row["read_length"],
            "read_support_outcomes": row["read_support_outcomes"],
            "handoff_success": row["handoff_success"],
            "m8_search_complete": row["m8_search_complete"],
            "triage_outcome": row["triage_outcome"],
        } for row in indel_rows
    }
    repeat_negative = next(
        (c for c in design["cases"]
         if design["negative_condition_by_id"].get(c["case_id"]) == "combined_higher"),
        next(c for c in design["cases"] if c["case_id"] in design["category_by_id"]),
    )
    repeat_cases = [c for c in design["cases"] if c["case_id"] in {
        "development-m29-positive_control", "tuning-m29-synthetic_background",
        "held_out-m29-positive_control",
    }] + [design["indel_cases"][-1], repeat_negative]
    repeat, repeat_provenance = _execute_bundle(
        output / "repeat", design, repeat_cases, blastn, makeblastdb, blastdbcmd)
    repeat_ids = {case["case_id"] for case in repeat_cases}
    reference_subset = {
        **report,
        "reconstruction_and_handoffs": [
            row for row in report["reconstruction_and_handoffs"]
            if row["case_id"] in repeat_ids
        ],
        "candidate_triage": [
            row for row in report["candidate_triage"] if row["case_id"] in repeat_ids
        ],
    }
    reproducibility = m33.compare_reproducibility(
        m33._reproducibility_signature(reference_subset),
        m33._reproducibility_signature(repeat),
    )
    differences = dict(reproducibility["differing_stages"])
    provenance_differences = sorted(
        cid for cid in repeat_ids
        if report["m34_read_provenance"].get(cid, {}).get("sha256")
        != repeat["m34_read_provenance"].get(cid, {}).get("sha256")
    )
    truth_differences = sorted(
        cid for cid in repeat_ids
        if report["m34_target_absence_validation"]["cases"].get(cid, {}).get(
            "source_truth_sidecar_sha256")
        != repeat["m34_target_absence_validation"]["cases"].get(cid, {}).get(
            "source_truth_sidecar_sha256")
    )
    if provenance_differences:
        differences["read_provenance"] = provenance_differences
    if truth_differences:
        differences["source_truth"] = truth_differences
    if report.get("panel_digest") != repeat.get("panel_digest"):
        differences["frozen_panel"] = ["panel_digest"]
    if report.get("runtime") != repeat.get("runtime"):
        differences["runtime"] = ["runtime"]
    reproducibility.update({
        "differing_stages": differences,
        "fully_reproducible": not differences,
        "status": "REPRODUCIBILITY_MISMATCH" if differences else "REPRODUCIBLE",
    })
    reproducibility.update({"reference_bundle": "benchmark", "repeat_bundle": "repeat"})
    positive_recovery = {
        "generated_cases": len(indel_rows),
        "exact_supported": sum(row["exact_supported_reconstruction"] for row in indel_rows),
        "partial_supported": sum(row["partial_reconstruction"] for row in indel_rows),
    }
    positive_recovery["exact_rate"] = (
        positive_recovery["exact_supported"] / len(indel_rows) if indel_rows else None)
    positive_recovery["exact_wilson_95"] = _wilson(
        positive_recovery["exact_supported"], len(indel_rows))
    positive_recovery["partial_rate"] = (
        positive_recovery["partial_supported"] / len(indel_rows) if indel_rows else None)
    positive_recovery["partial_wilson_95"] = _wilson(
        positive_recovery["partial_supported"], len(indel_rows))
    result = {
        "schema": "m34-negative-control-indel-robustness-v1",
        "synthetic_only": True, "case_count": len(rows),
        "target_absent_generated": len(negatives),
        "target_absent_eligible": target_absent["case_level"]["eligible_denominator"],
        "target_absent_false_alarm_rates": target_absent,
        "target_absent_by_category": by_category,
        "target_absent_by_error_condition": target_absent_by_error_condition,
        "positive_indel_recovery": positive_recovery,
        "indel_robustness_by_condition": by_condition,
        "case_level_results": rows,
        "reproducibility": reproducibility,
        "read_provenance_bundles": {
            "benchmark": report["m34_read_provenance"],
            "repeat": repeat["m34_read_provenance"],
        },
        "target_absence_source_truth": {
            "benchmark": report["m34_target_absence_validation"],
            "repeat": repeat["m34_target_absence_validation"],
        },
        "runtime": report["runtime"],
        "reference_panel": report["panel_preregistration"],
        "governance": GOVERNANCE,
        "limitations": [
            "This declared synthetic error model is not a validated platform error distribution.",
            "Synthetic performance does not estimate biological sensitivity, specificity, or FDR.",
            "Contig-level rates are descriptive; no contig-level Wilson interval is computed because contigs cluster within cases.",
            "Case count is the replication unit.",
        ],
    }
    (output / "M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n")
    (output / "M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.md").write_text(
        render_markdown(result), encoding="utf-8")
    if not reproducibility["fully_reproducible"]:
        raise RuntimeError("REPRODUCIBILITY_MISMATCH: " + json.dumps(
            reproducibility["differing_stages"], sort_keys=True))
    return result


def render_markdown(report):
    rates = report["target_absent_false_alarm_rates"]
    lines = [
        "# M34 — Expanded synthetic negative-control and indel robustness", "",
        f"Generated target-absent cases: {report['target_absent_generated']}; "
        f"eligible after read support and completed M8: {report['target_absent_eligible']}.",
        f"Same-seed repeat: **{report['reproducibility']['status']}**.", "",
        "| Unit | REVIEW_PRIORITY | Eligible | Rate | Wilson 95% |",
        "|---|---:|---:|---:|---|",
    ]
    for name, key in (("Case", "case_level"), ("Contig", "contig_level")):
        row = rates[key]
        lines.append(f"| {name} | {row['review_priority']} | {row['eligible_denominator']} | "
                     f"{row['rate']} | {row['wilson_95'] if row['wilson_95'] else 'not computed'} |")
    lines += ["", "## Target-absent results by category", ""]
    for category, metrics in report["target_absent_by_category"].items():
        c, t = metrics["case_level"], metrics["contig_level"]
        lines.append(f"- {category}: generated={metrics['generated_cases']}; "
                     f"cases {c['review_priority']}/{c['eligible_denominator']} "
                     f"(case-level Wilson {c['wilson_95']}); contigs "
                     f"{t['review_priority']}/{t['eligible_denominator']} "
                     f"(descriptive only; no interval); unevaluable={len(metrics['unevaluable'])}.")
    lines += ["", "## Target-absent error-condition results", ""]
    for condition, metrics in report["target_absent_by_error_condition"].items():
        c = metrics["case_level"]
        lines.append(f"- {condition}: generated={metrics['generated_cases']}; "
                     f"false-alarm cases={c['review_priority']}/{c['eligible_denominator']} "
                     f"(Wilson {c['wilson_95']}); unevaluable={len(metrics['unevaluable'])}.")
    recovery = report["positive_indel_recovery"]
    lines += [
        "", "## Target-positive indel recovery", "",
        f"Exact supported recovery: {recovery['exact_supported']}/"
        f"{recovery['generated_cases']} (Wilson {recovery['exact_wilson_95']}); "
        f"partial supported recovery: {recovery['partial_supported']}/"
        f"{recovery['generated_cases']} (Wilson {recovery['partial_wilson_95']}).",
        "",
    ]
    lines += ["", "## Indel robustness", ""]
    for condition, row in report["indel_robustness_by_condition"].items():
        lines.append(f"- {condition}: exact-supported={row['exact_supported']}; "
                     f"partial-supported={row['partial_supported']}; "
                     f"assembly={row['assembly_status']}; M8={row['m8_search_complete']}; "
                     f"triage={row['triage_outcome']}.")
    lines += ["", "Synthetic-only; no biological dataset or reference was used.",
              "The synthetic error model is not a validated sequencing-platform model.", "",
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
    parser.add_argument("--negative-per-category", type=int, default=8)
    args = parser.parse_args(argv)
    result = run(args.output, args.blastn, args.makeblastdb, args.blastdbcmd,
                 args.negative_per_category)
    print(json.dumps({"case_count": result["case_count"],
                      "target_absent_eligible": result["target_absent_eligible"],
                      "reproducibility": result["reproducibility"],
                      "governance": result["governance"]}, sort_keys=True))


if __name__ == "__main__":
    main()
