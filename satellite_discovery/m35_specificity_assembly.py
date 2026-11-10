"""M35 preregistration helpers for synthetic-only diagnostic studies.

This module defines the experiment before results are observed.  It does not
change M6/M8/M31 behavior and does not authorize biological execution.
"""

from __future__ import annotations

import hashlib
import json
import argparse
import copy
import random
import re
from pathlib import Path
from unittest.mock import patch

SCHEMA = "m35-preregistered-design-v1"
SIMILARITY_LEVELS = (1.00, 0.98, 0.95, 0.92, 0.90, 0.85, 0.80, 0.70)
DECOY_SIMILARITY_LEVELS = SIMILARITY_LEVELS[1:]
SEEDS = (35_100_001, 35_100_101, 35_100_201)
SPLITS = ("development", "tuning", "held_out")
GOVERNANCE = {
    "decision": "INCOMPLETE",
    "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
    "biological_execution_authorized": False,
}


def preregistered_design(panel_fasta: bytes, target_sequence: str) -> dict:
    """Freeze a balanced, truth-blind similarity design and its input digests.

    Similarity labels describe the designed nucleotide divergence only; they
    are not a definition of biological target identity.  Truth is assigned
    independently and held-out labels are not part of screening inputs.
    """
    if not panel_fasta or not target_sequence:
        raise ValueError("frozen panel and synthetic target sequence are required")
    if set(target_sequence.upper()) - set("ACGT"):
        raise ValueError("target sequence must contain only A/C/G/T")
    if len(target_sequence) < 100:
        raise ValueError("target sequence is too short for the registered design")

    cases = []
    for seed_index, seed in enumerate(SEEDS):
        split = SPLITS[seed_index]
        # One exact positive reference control per independent sequence family.
        positive_case = {
            "case_id": f"{split}-m35-positive-s{seed_index + 1}",
            "family_id": f"family-s{seed_index + 1}",
            "seed": seed,
            "split": split,
            "similarity_level": 1.0,
            "condition": "known_target_positive_control",
        }
        if split != "held_out":
            positive_case["truth_target_present"] = True
        cases.append(positive_case)
        for level_index, identity in enumerate(DECOY_SIMILARITY_LEVELS):
            decoy_case = {
                "case_id": f"{split}-m35-decoy-s{seed_index + 1}-i{level_index:02d}",
                "family_id": f"family-s{seed_index + 1}",
                "seed": seed,
                "split": split,
                "similarity_level": identity,
                "condition": "target_absent_near_target_decoy",
                "substitutions": round(len(target_sequence) * (1 - identity)),
            }
            if split != "held_out":
                decoy_case["truth_target_present"] = False
            cases.append(decoy_case)

    body = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "similarity_levels": list(SIMILARITY_LEVELS),
        "independent_seeds": list(SEEDS),
        "split_by_seed": {str(seed): SPLITS[i] for i, seed in enumerate(SEEDS)},
        "panel_sha256": hashlib.sha256(panel_fasta).hexdigest(),
        "target_sequence_sha256": hashlib.sha256(
            target_sequence.upper().encode("ascii")
        ).hexdigest(),
        "target_length": len(target_sequence),
        "cases": cases,
        "truth_policy": (
            "Truth labels are stored outside screening inputs; similarity is a "
            "synthetic design factor and never defines target identity."
        ),
        "metrics": {
            "primary": "case-level REVIEW_PRIORITY rate by truth stratum and similarity level",
            "unit": "independent synthetic family",
            "unevaluable": "reported separately; excluded from the eligible denominator",
        },
        "governance": dict(GOVERNANCE),
    }
    digestable = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    body["design_sha256"] = hashlib.sha256(digestable).hexdigest()
    return body


def validate_design(design: dict) -> None:
    """Reject unbalanced designs, truth leakage, and changes to governance."""
    if design.get("schema") != SCHEMA or design.get("governance") != GOVERNANCE:
        raise ValueError("M35 schema or governance mismatch")
    cases = design.get("cases")
    if not isinstance(cases, list):
        raise ValueError("M35 cases must be a list")
    ids = [row.get("case_id") for row in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate M35 case ID")
    held_out = [row for row in cases if row.get("split") == "held_out"]
    if not held_out or any("truth_target_present" in row for row in held_out):
        raise ValueError("held-out truth must not be exposed to screening cases")
    decoys = [row for row in cases if row.get("condition") == "target_absent_near_target_decoy"]
    expected = len(SEEDS) * len(DECOY_SIMILARITY_LEVELS)
    if len(decoys) != expected or any(
        ("truth_target_present" in row if row.get("split") == "held_out"
         else row.get("truth_target_present") is not False)
        for row in decoys
    ):
        raise ValueError("target-absent decoy design is incomplete or mislabeled")
    for level in DECOY_SIMILARITY_LEVELS:
        if sum(row.get("similarity_level") == level for row in decoys) != len(SEEDS):
            raise ValueError(f"similarity level {level} lacks independent seeds")


def validate_evidence_bundle(design: dict, bundle: dict) -> None:
    """Validate case identity, blinded truth, candidate support, and failures.

    The input schema is intentionally narrow: screening case records must not
    contain truth fields; truth is provided separately by source sidecars.
    """
    if bundle.get("panel_sha256") != design.get("panel_sha256"):
        raise ValueError("reference panel digest mismatch")
    expected_ids = {row["case_id"] for row in design["cases"]}
    cases = bundle.get("cases")
    if not isinstance(cases, list):
        raise ValueError("case records are missing")
    ids = [row.get("case_id") for row in cases]
    if len(ids) != len(set(ids)) or set(ids) != expected_ids:
        raise ValueError("case IDs are missing, duplicated, or swapped")
    truth = bundle.get("truth_sidecars")
    if not isinstance(truth, dict) or set(truth) != expected_ids:
        raise ValueError("source truth sidecars are missing or miskeyed")

    design_by_id = {row["case_id"]: row for row in design["cases"]}
    identity_index = bundle.get("candidate_identity")
    if not isinstance(identity_index, dict):
        raise ValueError("candidate identity index is missing")

    for case in cases:
        case_id = case["case_id"]
        registered = design_by_id[case_id]
        if case.get("split") != registered["split"] \
                or case.get("family_id") != registered["family_id"]:
            raise ValueError(f"{case_id}: case ID is attached to the wrong family or split")
        source_truth = truth[case_id]
        if not isinstance(source_truth.get("target_present"), bool):
            raise ValueError(f"{case_id}: source truth is not boolean")
        expected_truth = registered.get("truth_target_present")
        if expected_truth is not None and source_truth["target_present"] is not expected_truth:
            raise ValueError(f"{case_id}: target-absent/positive truth misclassified")
        if any(key in case for key in ("truth", "truth_sidecar", "truth_target_present",
                                       "source_truth", "candidate_sequence_truth")):
            raise ValueError(f"{case_id}: truth-sidecar leakage into screening record")

        assembly = case.get("assembly_status")
        candidates = case.get("candidate_records", [])
        if not isinstance(candidates, list):
            raise ValueError(f"{case_id}: candidate records are invalid")
        if assembly == "EXECUTION_FAILED":
            stderr = case.get("assembler_stderr")
            if not isinstance(stderr, dict) or not stderr.get("text"):
                raise ValueError(f"{case_id}: assembler stderr is missing")
            digest = hashlib.sha256(stderr["text"].encode("utf-8")).hexdigest()
            if stderr.get("sha256") != digest or not isinstance(stderr.get("exit_code"), int):
                raise ValueError(f"{case_id}: assembler stderr provenance mismatch")
            if case.get("m8_search_complete") or candidates:
                raise ValueError(f"{case_id}: execution failure misclassified as assembled")
            continue
        if assembly not in ("ASSEMBLED_COMPLETE", "ASSEMBLED_PARTIAL",
                            "ASSEMBLED_UNSUPPORTED"):
            raise ValueError(f"{case_id}: invalid stage-level assembly classification")
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id")
            sequence = candidate.get("sequence")
            if not candidate_id or not isinstance(sequence, str):
                raise ValueError(f"{case_id}: candidate identity is incomplete")
            actual = hashlib.sha256(sequence.encode("ascii")).hexdigest()
            if candidate.get("sha256") != actual:
                raise ValueError(f"{case_id}: incorrect candidate hash")
            if identity_index.get(candidate_id) != actual:
                raise ValueError(f"{case_id}: candidate ID digest mismatch")
            if candidate.get("read_support_status") == "READ_SUPPORTED_ASSEMBLY" \
                    and not candidate.get("support_evidence"):
                raise ValueError(f"{case_id}: read-supported candidate lacks support")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _wilson(successes, total):
    if total == 0:
        return None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * (
        p * (1 - p) / total + z * z / (4 * total * total)
    ) ** 0.5 / denominator
    return [max(0.0, center - margin), min(1.0, center + margin)]


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _artifact_hashes(root):
    root = Path(root)
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): _file_hash(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _m35_handoff(handoff, source_stage, out, case_id):
    """Treat an empty M6 FASTA as no assembly; preserve strict nonempty checks."""
    contigs = Path(source_stage) / "assembly" / "contigs.fasta"
    if contigs.is_file() and contigs.stat().st_size == 0:
        return None
    return handoff(source_stage, out, case_id)


def _execute_m35_bundle(m34, m32, output, design, cases, blastn, makeblastdb,
                        blastdbcmd):
    original_handoff = m32._handoff
    with patch.object(
        m32, "_handoff",
        side_effect=lambda stage, out, case_id: _m35_handoff(
            original_handoff, stage, out, case_id
        ),
    ):
        return m34._execute_bundle(
            output, design, cases, blastn, makeblastdb, blastdbcmd
        )


def _support_semantics_sha256(path):
    path = Path(path)
    if not path.is_file():
        return None
    document = _read_json(path)
    if not document:
        return None
    semantic_fields = {
        key: value for key, value in document.items() if key != "provenance"
    }
    return hashlib.sha256(json.dumps(
        semantic_fields, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _case_map(report):
    return {row["case_id"]: row for row in report.get("case_level_results", [])}


def _review_priority(row):
    return any(candidate.get("triage_status") == "REVIEW_PRIORITY"
               for candidate in row.get("candidate_records", []))


def reproduce_m34(m34_current_dir, m34_archive_dir):
    """Compare a fresh M34 Actions execution with the inspected archived baseline."""
    from scripts.validate_m35_source_artifact import REQUIRED_CASES

    current_root, archive_root = Path(m34_current_dir), Path(m34_archive_dir)
    current = _read_json(current_root / "M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.json")
    archived = _read_json(archive_root / "M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.json")
    now, before = _case_map(current), _case_map(archived)
    false_alarms = []
    for case_id in sorted(REQUIRED_CASES):
        old, fresh = before.get(case_id), now.get(case_id)
        false_alarms.append({
            "case_id": case_id,
            "archived_observation": (
                "REVIEW_PRIORITY" if old and _review_priority(old) else "NOT_VERIFIED"
            ),
            "independent_rerun_observation": (
                "REVIEW_PRIORITY" if fresh and _review_priority(fresh)
                else "NOT_REPRODUCED" if fresh else "NOT_EVALUATED"
            ),
            "reproduced": bool(
                old and fresh and _review_priority(old) and _review_priority(fresh)
            ),
            "rerun_read_provenance_sha256": current.get(
                "read_provenance_bundles", {}).get("benchmark", {}).get(case_id, {}).get("sha256"),
            "rerun_candidate_records": fresh.get("candidate_records", []) if fresh else [],
            "archived_raw_evidence_sha256": _artifact_hashes(
                archive_root / "benchmark" / "reconstruction" / case_id
            ),
            "rerun_raw_evidence_sha256": _artifact_hashes(
                current_root / "benchmark" / "reconstruction" / case_id
            ) | _artifact_hashes(
                current_root / "benchmark" / "m8_runs"
                / ((fresh or old or {}).get("analysis_id", ""))
            ),
        })

    failure_ids = (
        "tuning-m34-i002", "tuning-m34-i005",
        "held_out-m34-i006", "development-m34-i007",
    )
    failures = []
    for case_id in failure_ids:
        old, fresh = before.get(case_id), now.get(case_id)
        failures.append({
            "case_id": case_id,
            "archived_status": old.get("assembly_status") if old else "NOT_EVALUATED",
            "independent_rerun_status": (
                fresh.get("assembly_status") if fresh else "NOT_EVALUATED"
            ),
            "reproduced": bool(
                fresh and fresh.get("assembly_status") == "EXECUTION_FAILED"
            ),
            "failure_reason": fresh.get("failure_reason") if fresh else None,
            "realized_error_totals": fresh.get("realized_error_totals") if fresh else None,
            "archived_raw_evidence_sha256": _artifact_hashes(
                archive_root / "benchmark" / "reconstruction" / case_id
            ),
            "rerun_raw_evidence_sha256": _artifact_hashes(
                current_root / "benchmark" / "reconstruction" / case_id
            ),
        })
    return {
        "source_kind": "fresh M34 pipeline execution in this Actions run",
        "archived_source_kind": "inspection of frozen M34 Actions artifact",
        "false_alarm_reproductions": false_alarms,
        "false_alarm_denominator": {
            "reproduced": sum(row["reproduced"] for row in false_alarms), "registered": 5,
        },
        "false_alarm_wilson_95": _wilson(
            sum(row["reproduced"] for row in false_alarms), 5
        ),
        "spades_failure_reproductions": failures,
        "spades_failure_denominator": {
            "reproduced": sum(row["reproduced"] for row in failures), "registered": 4,
        },
        "spades_failure_wilson_95": _wilson(
            sum(row["reproduced"] for row in failures), 4
        ),
    }


def _decoy_sequence(target, identity, seed):
    sequence = list(target)
    count = round(len(target) * (1 - identity))
    rng = random.Random(seed)
    for position in rng.sample(range(len(sequence)), count):
        sequence[position] = rng.choice("ACGT".replace(sequence[position], ""))
    return "".join(sequence)


def _sequence_features(sequence, target):
    kmers = [sequence[i:i + 3] for i in range(max(0, len(sequence) - 2))]
    counts = {kmer: kmers.count(kmer) for kmer in set(kmers)}
    return {
        "length": len(sequence),
        "gc_fraction": (sequence.count("G") + sequence.count("C")) / len(sequence),
        "unique_3mer_fraction": len(counts) / max(1, len(kmers)),
        "maximum_3mer_fraction": max(counts.values(), default=0) / max(1, len(kmers)),
        "substitutions_from_target": sum(a != b for a, b in zip(sequence, target)),
    }


def _gradient_cases(design, target, controls, control_contracts):
    from . import m32_end_to_end_synthetic_evidence as m32
    from . import m25_read_coverage as m25

    cases = [dict(case) for case in controls]
    contracts = {key: dict(value) for key, value in control_contracts.items()}
    sequence_by_id, target_by_id, seed_by_id = {}, {}, {}
    for registered in design["cases"]:
        split = registered["split"]
        case = m25._case_design(split, 1 + len(cases) % 3)
        case.update({
            "case_id": registered["case_id"],
            "analysis_id": "m35" + hashlib.sha256(
                registered["case_id"].encode("utf-8")
            ).hexdigest()[:9],
            "positive": registered["condition"] == "known_target_positive_control",
            "target_length": len(target), "coverage": 48,
            "m25_read_length": 100, "error_rate": 0.0,
            "insertion_rate": 0.0, "deletion_rate": 0.0,
            "divergence": 0.45, "repeat_complexity": "low",
            "m29_factor": "m35_similarity_gradient", "opaque_read_ids": True,
            "read_start_mode": "uniform", "m25_background_read_coverage": True,
        })
        cases.append(case)
        seed_by_id[case["case_id"]] = registered["seed"]
        target_by_id[case["case_id"]] = target
        if registered["condition"] == "target_absent_near_target_decoy":
            sequence_by_id[case["case_id"]] = _decoy_sequence(
                target, registered["similarity_level"], registered["seed"]
            )
            contracts[case["case_id"]] = {
                "experiment_type": "target_absent_supported_background",
                "expected_triage_outcome": "INSUFFICIENT_EVIDENCE",
                "expected_exact_target_triage_outcome": "INSUFFICIENT_EVIDENCE",
                "expected_non_target_triage_outcome": "INSUFFICIENT_EVIDENCE",
            }
        else:
            contracts[case["case_id"]] = {
                "experiment_type": "known_reference_positive",
                "expected_triage_outcome": "REVIEW_PRIORITY",
                "expected_exact_target_triage_outcome": "REVIEW_PRIORITY",
                "expected_non_target_triage_outcome": "INSUFFICIENT_EVIDENCE",
            }
    # Include the three fixed M32 reference controls needed to regenerate its panel.
    from . import m29_assembly_root_cause_recovery as m29
    for case in cases[:len(controls)]:
        seed_by_id[case["case_id"]] = m29._case_seed(case)
    return cases, contracts, {
        "seed_by_id": seed_by_id, "category_by_id": {},
        "background_sequence_by_id": sequence_by_id,
        "target_sequence_by_id": target_by_id, "contracts": contracts,
    }


def _candidate_features(triage_rows, report, design, target, sequence_by_id,
                        bundle_dir=None):
    metrics = {row["case_id"]: row for row in report["benchmark_metrics"]["cases"]}
    outcomes = {row["case_id"]: row for row in triage_rows}
    execution = {row["case_id"]: row for row in report["reconstruction_and_handoffs"]}
    result = []
    for registered in design["cases"]:
        case_id = registered["case_id"]
        outcome = outcomes[case_id]
        execution_row = execution[case_id]
        candidate_matches = {}
        for match in outcome.get("matches", []):
            candidate_matches.setdefault(match.get("candidate_id"), []).append(match)
        assembled = {}
        if bundle_dir is not None:
            fasta_path = (
                Path(bundle_dir) / "reconstruction" / case_id / "stages"
                / f"m6_{execution_row['analysis_id']}" / "assembly" / "contigs.fasta"
            )
            if fasta_path.is_file():
                from . import m32_end_to_end_synthetic_evidence as m32
                assembled = dict(m32._read_fasta(fasta_path))
        candidates = []
        for candidate in outcome.get("candidate_records", []):
            matches = candidate_matches.get(candidate["candidate_id"], [])
            candidate_sequence = assembled.get(candidate["candidate_id"])
            ranked = sorted(matches, key=lambda match: (
                (match.get("alignment") or {}).get("percent_identity", 0),
                (match.get("alignment") or {}).get("query_coverage", 0),
            ), reverse=True)
            candidates.append({
                **candidate,
                "best_alignment": (
                    ranked[0].get("alignment") if ranked else None
                ),
                "secondary_match_count": max(0, len(ranked) - 1),
                "distinct_reference_count": len({
                    match.get("reference", {}).get("accession_version")
                    for match in ranked
                }),
                "all_alignment_matches": matches,
                "sequence_features": (
                    _sequence_features(candidate_sequence, target)
                    if candidate_sequence else None
                ),
            })
        sequence = sequence_by_id.get(case_id)
        result.append({
            **registered,
            "assembly_status": execution_row.get("assembly_status"),
            "read_input_sha256": execution_row.get("read_input_sha256"),
            "m8_search_complete": metrics[case_id]["m8_search_complete"],
            "read_supported_candidate_count": sum(
                row.get("read_support_status") == "READ_SUPPORTED_ASSEMBLY"
                for row in candidates
            ),
            "review_priority": any(
                row.get("triage_status") == "REVIEW_PRIORITY" for row in candidates
            ),
            "candidates": candidates,
            "raw_m8_outputs": outcome.get("raw_outputs", []),
            "decoy_sequence_features": (
                _sequence_features(sequence, target) if sequence else None
            ),
        })
    return result


def _summarize_gradient(rows):
    summaries = []
    for identity in SIMILARITY_LEVELS:
        truth_condition = (
            "known_target_positive_control" if identity == 1.0
            else "target_absent_near_target_decoy"
        )
        level_rows = [row for row in rows
                      if row["similarity_level"] == identity
                      and row["condition"] == truth_condition]
        eligible = [row for row in level_rows
                    if row["m8_search_complete"] and row["read_supported_candidate_count"]]
        positives = sum(row["review_priority"] for row in eligible)
        summaries.append({
            "similarity_level": identity,
            "truth_stratum": "positive_control" if identity == 1.0 else "target_absent_decoy",
            "split_denominators": {
                split: sum(row["split"] == split for row in eligible)
                for split in SPLITS
            },
            "generated_cases": len(level_rows),
            "eligible_cases": len(eligible),
            "unevaluable_cases": len(level_rows) - len(eligible),
            "review_priority_cases": positives,
            "review_priority_rate": positives / len(eligible) if eligible else None,
            "wilson_95": _wilson(positives, len(eligible)),
        })
    return summaries


def _feature_diagnostics(rows):
    from . import m31_synthetic_evidence_screening as m31

    def qualifying_target_match(matches):
        return m31._strong([
            match for match in matches
            if match.get("panel_role") == "satellite_subviral"
        ])

    summaries = []
    for identity in SIMILARITY_LEVELS:
        expected_condition = (
            "known_target_positive_control" if identity == 1.0
            else "target_absent_near_target_decoy"
        )
        cases = [row for row in rows
                 if row["similarity_level"] == identity
                 and row["condition"] == expected_condition]
        target_alignments = [
            match for case in cases for candidate in case["candidates"]
            for match in candidate["all_alignment_matches"]
            if match.get("panel_role") == "satellite_subviral"
        ]
        qualifying = [match for match in target_alignments
                      if qualifying_target_match([match])]
        candidates = [candidate for case in cases for candidate in case["candidates"]]
        review = [candidate for candidate in candidates
                  if candidate.get("triage_status") == "REVIEW_PRIORITY"]
        summaries.append({
            "similarity_level": identity,
            "truth_stratum": "positive_control" if identity == 1.0 else "target_absent_decoy",
            "target_role_alignment_count": len(target_alignments),
            "qualifying_target_alignment_count": len(qualifying),
            "qualifying_cases": len({
                case["case_id"] for case in cases
                if any(
                    qualifying_target_match(candidate["all_alignment_matches"])
                    for candidate in case["candidates"]
                )
            }),
            "review_priority_candidates": len(review),
            "review_priority_with_qualifying_alignment": sum(
                qualifying_target_match(candidate["all_alignment_matches"])
                for candidate in review
            ),
            "multiple_reference_candidates": sum(
                candidate["distinct_reference_count"] > 1 for candidate in candidates
            ),
            "secondary_alignment_count": sum(
                candidate["secondary_match_count"] for candidate in candidates
            ),
        })
    return summaries


def _oat_settings():
    baseline = {
        "coverage": 48, "read_length": 100,
        "substitution_rate": 0.02, "insertion_rate": 0.01, "deletion_rate": 0.01,
    }
    settings = [{"factor": "baseline", "level": "combined_moderate", **baseline}]
    for factor, key, values in (
        ("coverage", "coverage", (24, 80)),
        ("read_length", "read_length", (75, 150)),
        ("substitutions", "substitution_rate", (0.0, 0.01, 0.05)),
        ("insertions", "insertion_rate", (0.0, 0.005, 0.03)),
        ("deletions", "deletion_rate", (0.0, 0.005, 0.03)),
    ):
        for value in values:
            row = dict(baseline)
            row[key] = value
            settings.append({"factor": factor, "level": value, **row})
    return settings


def _oat_factor_comparisons(rows):
    baseline = next((row for row in rows if row["factor"] == "baseline"), None)
    if baseline is None:
        return []
    baseline_rate = (
        baseline["execution_failure_count"] / baseline["execution_denominator"]
        if baseline["execution_denominator"] else None
    )
    comparisons = []
    for row in rows:
        if row["factor"] == "baseline":
            continue
        rate = (
            row["execution_failure_count"] / row["execution_denominator"]
            if row["execution_denominator"] else None
        )
        comparisons.append({
            "factor": row["factor"],
            "level": row["level"],
            "execution_failures": row["execution_failure_count"],
            "denominator": row["execution_denominator"],
            "not_run_replicates": sum(
                replicate["assembly_status"] == "NOT_RUN"
                for replicate in row["repetitions"]
            ),
            "failure_rate": rate,
            "baseline_failure_rate": baseline_rate,
            "difference_from_baseline": (
                rate - baseline_rate if rate is not None and baseline_rate is not None else None
            ),
            "interpretation": (
                "descriptive one-factor association only; not a causal finding"
            ),
        })
    return comparisons


def _run_oat(output):
    from . import m25_read_coverage as m25
    from . import m29_assembly_root_cause_recovery as m29

    output = Path(output)
    base = m25._case_design("development", 1)
    results = []
    for index, settings in enumerate(_oat_settings(), 1):
        repetitions = []
        case_id = f"development-m35-oat-{index:02d}"
        for replicate in (1, 2):
            analysis_id = f"m35o{index:02d}"
            case = dict(base)
            case.update({
                "case_id": case_id, "analysis_id": analysis_id, "positive": True,
                "target_length": 900, "coverage": settings["coverage"],
                "m25_read_length": settings["read_length"],
                "error_rate": settings["substitution_rate"],
                "insertion_rate": settings["insertion_rate"],
                "deletion_rate": settings["deletion_rate"],
                "divergence": 0.45, "repeat_complexity": "low",
                "m29_factor": "m35_one_factor_at_a_time",
                "opaque_read_ids": True, "read_start_mode": "uniform",
            })
            case_root = output / f"repeat-{replicate}" / case_id
            try:
                m29._run_case(case_root, case)
                stage = case_root / "stages" / f"m6_{analysis_id}"
                reconstruction_path = stage / "reconstruction_evidence.json"
                evidence = _read_json(reconstruction_path) if reconstruction_path.is_file() else {}
                assembly_manifest_path = stage / "assembly" / "manifest.json"
                assembly_manifest = (
                    _read_json(assembly_manifest_path)
                    if assembly_manifest_path.is_file() else {}
                )
                reads = case_root / "inputs" / "datasets" / analysis_id / "reads.fastq.gz"
                contigs = stage / "assembly" / "contigs.fasta"
                support = stage / "read_support.json"
                spades_log = stage / "assembly" / "raw" / "spades.log"
                error_lines = []
                if spades_log.is_file():
                    error_lines = [
                        line.strip() for line in spades_log.read_text(
                            encoding="utf-8", errors="replace"
                        ).splitlines()
                        if re.search(r"\bERROR\b", line, re.IGNORECASE)
                    ]
                support_semantics_sha256 = _support_semantics_sha256(support)
                exit_status = assembly_manifest.get("exit_status")
                repetitions.append({
                    "replicate": replicate,
                    "assembly_status": evidence.get("status", "NOT_EVALUATED"),
                    "assembler": evidence.get("assembler"),
                    "configuration": evidence.get("configuration"),
                    "assembly_manifest_status": assembly_manifest.get("status"),
                    "assembler_exit_status": exit_status,
                    "failure_reason": (
                        error_lines[-1] if error_lines else evidence.get("failure_reason")
                    ),
                    "evidence_sha256": {
                        "reads": _file_hash(reads) if reads.is_file() else None,
                        "contigs": _file_hash(contigs) if contigs.is_file() else None,
                        "read_support": _file_hash(support) if support.is_file() else None,
                        "read_support_semantic": support_semantics_sha256,
                        "reconstruction": (
                            _file_hash(reconstruction_path) if reconstruction_path.is_file() else None
                        ),
                        "assembly_manifest": (
                            _file_hash(assembly_manifest_path)
                            if assembly_manifest_path.is_file() else None
                        ),
                        "spades_log": _file_hash(spades_log) if spades_log.is_file() else None,
                    },
                    "raw_evidence_sha256": _artifact_hashes(case_root),
                })
            except Exception as exc:
                repetitions.append({
                    "replicate": replicate, "assembly_status": "NOT_RUN",
                    "blocker": f"{type(exc).__name__}: {exc}", "evidence_sha256": {},
                })
        signature = lambda row: (
            row["assembly_status"],
            row["evidence_sha256"].get("reads"),
            row["evidence_sha256"].get("contigs"),
            row["evidence_sha256"].get("read_support_semantic"),
            row.get("failure_reason"),
        )
        reproducible = signature(repetitions[0]) == signature(repetitions[1])
        results.append({
            **settings, "case_id": case_id, "repetitions": repetitions,
            "execution_failure_count": sum(
                row["assembly_status"] == "EXECUTION_FAILED" for row in repetitions
            ),
            "execution_denominator": sum(
                row["assembly_status"] != "NOT_RUN" for row in repetitions
            ),
            "repeatability": (
                "NOT_EVALUATED" if any(row["assembly_status"] == "NOT_RUN"
                                        for row in repetitions)
                else "REPRODUCIBLE" if reproducible else "MISMATCH"
            ),
        })
    return results


def validate_result_report(report, gradient_dir):
    if report.get("schema") != "m35-synthetic-investigation-v1":
        raise ValueError("M35 result schema mismatch")
    design = report.get("preregistered_design", {})
    if design.get("similarity_levels") != list(SIMILARITY_LEVELS):
        raise ValueError("M35 report changed the registered similarity levels")
    gradient = report.get("similarity_gradient", {})
    if gradient.get("status") == "EXECUTED":
        if len(gradient.get("case_level_results", [])) != 24:
            raise ValueError("M35 report does not contain all registered gradient cases")
        raw = Path(gradient_dir) / "M32_END_TO_END_SYNTHETIC_EVIDENCE.json"
        if not raw.is_file() or _file_hash(raw) != gradient.get("raw_report_sha256"):
            raise ValueError("M35 gradient report is not bound to generated M32 output")
        generated = _read_json(raw)
        raw_metrics = {
            row["case_id"]: row for row in generated["benchmark_metrics"]["cases"]
        }
        raw_triage = {row["case_id"]: row for row in generated["candidate_triage"]}
        for row in gradient["case_level_results"]:
            case_id = row["case_id"]
            if case_id not in raw_metrics or case_id not in raw_triage:
                raise ValueError(f"M35 case is absent from raw M32 output: {case_id}")
            if row["m8_search_complete"] != raw_metrics[case_id]["m8_search_complete"]:
                raise ValueError(f"M35 M8 status differs from raw M32 output: {case_id}")
            statuses = {
                candidate.get("triage_status")
                for candidate in raw_triage[case_id].get("candidate_records", [])
            }
            if row["review_priority"] != ("REVIEW_PRIORITY" in statuses):
                raise ValueError(f"M35 triage differs from raw M32 output: {case_id}")
        repeatability = gradient.get("repeatability", {})
        if repeatability.get("status") == "ASSESSED":
            if len(repeatability.get("repeated_cases", [])) != 8:
                raise ValueError("M35 held-out repeat bundle is incomplete")
        elif repeatability.get("status") != "NOT_RUN" or not repeatability.get("blocker"):
            raise ValueError("M35 repeatability status is missing or invalid")
    elif gradient.get("status") != "NOT_RUN" or not gradient.get("blocker"):
        raise ValueError("M35 gradient failure is missing its exact blocker")
    if len(report.get("spades_one_factor_at_a_time", [])) != len(_oat_settings()):
        raise ValueError("M35 report does not contain the full OAT design")
    false_alarms = report["m34_independent_reproduction"]["false_alarm_reproductions"]
    if len(false_alarms) != 5:
        raise ValueError("M35 M34 false-alarm rerun accounting is incomplete")
    return True


def run(output, blastn, makeblastdb, blastdbcmd, m34_current_dir,
        m34_archive_dir, actions_run_id="unknown"):
    """Execute M35 only against synthetic designs and the pinned M32/M34 path."""
    from . import m25_read_coverage as m25
    from . import m29_assembly_root_cause_recovery as m29
    from . import m32_end_to_end_synthetic_evidence as m32
    from . import m34_negative_control_indel_robustness as m34

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite M35 output: {output}")
    reproduction = reproduce_m34(m34_current_dir, m34_archive_dir)

    controls, control_contracts = m32._benchmark_design(m29.case_matrix())
    target = m32._target_sequence_from_design(next(
        case for case in controls if case["case_id"] == "held_out-m29-positive_control"
    ))
    panel_sequences, _ = m32.preregistered_panel(controls)
    panel_bytes = "".join(
        f">{name}\n{sequence}\n" for name, sequence in panel_sequences.items()
    ).encode("ascii")
    design = preregistered_design(panel_bytes, target)
    validate_design(design)
    cases, contracts, bundle_design = _gradient_cases(
        design, target, controls, control_contracts
    )
    if design["panel_sha256"] != "ced54090aadd76a48642cce73ee72bb749b198f5a2be90ab921ad489744140df":
        raise ValueError("M35 generated panel differs from the preregistered frozen panel")

    gradient_dir = output / "similarity-gradient"
    gradient_dir.mkdir()
    try:
        m34_report, _captured = _execute_m35_bundle(
            m34, m32, gradient_dir, bundle_design, cases,
            blastn, makeblastdb, blastdbcmd,
        )
        gradient_rows = _candidate_features(
            m34_report["candidate_triage"], m34_report, design, target,
        bundle_design["background_sequence_by_id"], gradient_dir,
        )
        repeatability = {
            "status": "NOT_RUN",
            "scope": "all eight conditions in the held-out seed family",
            "blocker": "Repeat bundle execution did not complete.",
            "repeated_cases": [],
        }
        try:
            repeat_design = dict(design, cases=[
                case for case in design["cases"] if case["split"] == "held_out"
            ])
            repeat_cases, _repeat_contracts, repeat_bundle = _gradient_cases(
                repeat_design, target, controls, control_contracts
            )
            repeat_dir = output / "similarity-gradient-repeat"
            repeat_dir.mkdir()
            repeat_report, _ = _execute_m35_bundle(
                m34, m32, repeat_dir, repeat_bundle, repeat_cases,
                blastn, makeblastdb, blastdbcmd,
            )
            first_case_rows = {
                row["case_id"]: row for row in gradient_rows if row["split"] == "held_out"
            }
            repeat_rows = _candidate_features(
                repeat_report["candidate_triage"], repeat_report, repeat_design, target,
                repeat_bundle["background_sequence_by_id"], repeat_dir,
            )
            repeat_read_index = _read_json(repeat_dir / "M34_READ_PROVENANCE_INDEX.json")
            first_read_index = _read_json(gradient_dir / "M34_READ_PROVENANCE_INDEX.json")
            repeated_cases = []
            for repeat_row in repeat_rows:
                case_id = repeat_row["case_id"]
                first, second = first_case_rows[case_id], repeat_row
                read_equal = (
                    first_read_index.get(case_id, {}).get("sha256")
                    == repeat_read_index.get(case_id, {}).get("sha256")
                )
                same_outcome = (
                    first["assembly_status"] == second["assembly_status"]
                    and first["m8_search_complete"] == second["m8_search_complete"]
                    and first["review_priority"] == second["review_priority"]
                    and first["read_supported_candidate_count"]
                    == second["read_supported_candidate_count"]
                )
                repeated_cases.append({
                    "case_id": case_id,
                    "same_read_provenance": read_equal,
                    "same_pipeline_outcome": same_outcome,
                    "status": "REPRODUCIBLE" if read_equal and same_outcome else "MISMATCH",
                })
            repeatability = {
                "status": "ASSESSED",
                "scope": "all eight conditions in the held-out seed family",
                "repeated_cases": repeated_cases,
                "reproduced": sum(
                    row["status"] == "REPRODUCIBLE" for row in repeated_cases
                ),
                "denominator": len(repeated_cases),
            }
        except Exception as exc:
            repeatability["blocker"] = f"{type(exc).__name__}: {exc}"
        gradient = {
            "status": "EXECUTED",
            "case_level_results": gradient_rows,
            "by_similarity_level": _summarize_gradient(gradient_rows),
            "feature_diagnostics": _feature_diagnostics(gradient_rows),
            "raw_report_sha256": _file_hash(
                gradient_dir / "M32_END_TO_END_SYNTHETIC_EVIDENCE.json"
            ),
            "runtime": m34_report.get("runtime"),
            "panel_fasta_sha256": design["panel_sha256"],
            "read_provenance_index_sha256": _file_hash(
                gradient_dir / "M34_READ_PROVENANCE_INDEX.json"
            ),
            "target_absence_validation_sha256": _file_hash(
                gradient_dir / "M34_TARGET_ABSENCE_VALIDATION.json"
            ),
            "repeatability": repeatability,
        }
    except Exception as exc:
        gradient = {
            "status": "NOT_RUN",
            "blocker": f"{type(exc).__name__}: {exc}",
            "case_level_results": [],
        }
    oat_dir = output / "spades-one-factor-at-a-time"
    oat_dir.mkdir()
    oat = _run_oat(oat_dir)
    report = {
        "schema": "m35-synthetic-investigation-v1",
        "status": (
            "INCOMPLETE_WITH_NOT_RUN_EXPERIMENTS"
            if gradient["status"] == "NOT_RUN"
            or gradient.get("repeatability", {}).get("status") == "NOT_RUN"
            or any(row["repeatability"] == "NOT_EVALUATED" for row in oat)
            else "INCOMPLETE_PENDING_INDEPENDENT_REVIEW"
        ),
        "synthetic_only": True,
        "execution_authorization": "synthetic-only M35 execution; biological execution remains unauthorized",
        "biological_data_used": False,
        "m6_settings_changed": False,
        "m8_settings_changed": False,
        "m31_thresholds_changed": False,
        "m31_screening_source_sha256": _file_hash(
            Path(__file__).with_name("m31_synthetic_evidence_screening.py")
        ),
        "actions_run_id": str(actions_run_id),
        "preregistered_design": {
            "design_sha256": design["design_sha256"],
            "similarity_levels": list(SIMILARITY_LEVELS),
            "independent_seeds": list(SEEDS),
            "split_by_seed": design["split_by_seed"],
            "panel_sha256": design["panel_sha256"],
            "target_sequence_sha256": design["target_sequence_sha256"],
        },
        "m34_independent_reproduction": reproduction,
        "similarity_gradient": gradient,
        "spades_one_factor_at_a_time": oat,
        "oat_factor_comparisons": _oat_factor_comparisons(oat),
        "uncertainty_method": (
            "Wilson 95% intervals use independent seed-family case as the unit; "
            "unevaluable cases are excluded and reported separately. OAT repeats are "
            "technical reproducibility checks, not independent inferential replicates."
        ),
        "limitations": [
            "These results are synthetic pipeline diagnostics, not biological specificity estimates.",
            "A controlled factor association is not proof of an assembler mechanism.",
            "Similarity-gradient repeatability uses the complete held-out seed family; "
            "development and tuning families were not repeated.",
        ],
    }
    (output / "M35_PREREGISTERED_DESIGN.json").write_text(
        json.dumps(design, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    validate_result_report(report, gradient_dir)
    (output / "M35_SYNTHETIC_INVESTIGATION.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output / "M35_SYNTHETIC_INVESTIGATION.md").write_text(
        render_results_markdown(report), encoding="utf-8"
    )
    return report


def render_results_markdown(report):
    lines = [
        "# M35 Synthetic Investigation Results",
        "",
        f"Status: **{report['status']}**. Synthetic-only; no M6/M8/M31 setting changes.",
        "",
        "## Independent M34 reruns",
        "",
        f"- False alarms reproduced: {report['m34_independent_reproduction']['false_alarm_denominator']}",
        f"- SPAdes failures reproduced: {report['m34_independent_reproduction']['spades_failure_denominator']}",
        "- Archived artifact inspection and fresh Actions execution are recorded separately.",
        "",
        "## Similarity gradient",
        "",
        "| Identity | REVIEW_PRIORITY | Eligible | Generated | Unevaluable | Wilson 95% |",
        "|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["similarity_gradient"].get("by_similarity_level", []):
        lines.append(
            f"| {row['similarity_level']:.0%} | {row['review_priority_cases']} | "
            f"{row['eligible_cases']} | {row['generated_cases']} | "
            f"{row['unevaluable_cases']} | {row['wilson_95']} |"
        )
    if report["similarity_gradient"]["status"] == "NOT_RUN":
        lines.append(
            f"\nNOT_RUN blocker: {report['similarity_gradient']['blocker']}"
        )
    elif report["similarity_gradient"].get("repeatability", {}).get("status") == "NOT_RUN":
        lines.append(
            "\nGradient repeatability NOT_RUN blocker: "
            + report["similarity_gradient"]["repeatability"]["blocker"]
        )
    lines.extend(["", "## Controlled SPAdes comparisons", ""])
    for row in report["spades_one_factor_at_a_time"]:
        statuses = ", ".join(item["assembly_status"] for item in row["repetitions"])
        lines.append(
            f"- {row['factor']}={row['level']}: {statuses}; "
            f"execution failures={row['execution_failure_count']}/"
            f"{row['execution_denominator']}; repeatability={row['repeatability']}"
        )
        for item in row["repetitions"]:
            if item.get("blocker"):
                lines.append(f"  - replicate {item['replicate']} NOT_RUN: {item['blocker']}")
    lines.extend(["", "### Descriptive factor comparisons", ""])
    for row in report["oat_factor_comparisons"]:
        lines.append(
            f"- {row['factor']}={row['level']}: failure rate {row['failure_rate']} "
            f"vs baseline {row['baseline_failure_rate']}; "
            f"not-run={row['not_run_replicates']}. Descriptive only."
        )
    lines.extend(["", "No causal or biological claim is made from these synthetic results.", ""])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blastn", required=True)
    parser.add_argument("--makeblastdb", required=True)
    parser.add_argument("--blastdbcmd", required=True)
    parser.add_argument("--m34-current-dir", required=True)
    parser.add_argument("--m34-archive-dir", required=True)
    parser.add_argument("--actions-run-id", default="unknown")
    args = parser.parse_args(argv)
    result = run(
        args.output, args.blastn, args.makeblastdb, args.blastdbcmd,
        args.m34_current_dir, args.m34_archive_dir, args.actions_run_id,
    )
    print(json.dumps({
        "status": result["status"],
        "similarity_cases": len(result["similarity_gradient"]["case_level_results"]),
        "oat_cases": len(result["spades_one_factor_at_a_time"]),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
