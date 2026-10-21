"""Deterministic synthetic-only M21 scoring, separate from blinded analysis."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any

SCORING_POLICY_VERSION = "m21-synthetic-scoring-v1"
OPAQUE_SAMPLE = re.compile(r"BLD-[A-F0-9]{24}\Z")
OPAQUE_CONTROL = re.compile(r"CTL-[A-Z0-9]{10}\Z")
OPAQUE_REVIEWER = re.compile(r"REV-[A-Z0-9]{8}\Z")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8")).hexdigest()


def qualification_digest(record: dict[str, Any]) -> str:
    return canonical_sha256({key: value for key, value in record.items()
                             if key != "qualification_sha256"})


def _not_estimable(reason: str) -> dict[str, Any]:
    return {"value": None, "status": "NOT_ESTIMABLE", "reason": reason,
            "numerator": None, "denominator": None}


def _rate(numerator: int, denominator: int, reason: str) -> dict[str, Any]:
    if denominator <= 0:
        return _not_estimable(reason)
    return {"value": numerator / denominator, "status": "ESTIMATED",
            "numerator": numerator, "denominator": denominator, "reason": None}


def validate_qualification(record: Any) -> list[str]:
    required = {"control_id", "sample_ids", "control_class", "evaluation_status",
                "independently_reviewed", "scoring_eligibility", "exclusion_reason",
                "study_id", "replicate_group", "evidence_strength", "sensitivity_status",
                "review_evidence_sha256", "reviewer_ids", "qualification_sha256"}
    if not isinstance(record, dict):
        return ["Qualification record must be an object."]
    issues = []
    if set(record) != required:
        issues.append("Qualification record has missing or unknown fields.")
    if not isinstance(record.get("control_id"), str) or not OPAQUE_CONTROL.fullmatch(record["control_id"]):
        issues.append("Malformed opaque control identifier.")
    ids = record.get("sample_ids")
    if not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not OPAQUE_SAMPLE.fullmatch(x) for x in ids) or len(set(ids)) != len(ids):
        issues.append("Qualification requires unique opaque sample identifiers.")
    if record.get("control_class") not in {"POSITIVE", "NEGATIVE", "HELPER_POSITIVE", "HELPER_NEGATIVE"}:
        issues.append("Invalid scoring control class.")
    if record.get("evaluation_status") not in {"EVALUABLE", "UNEVALUABLE", "PENDING"}:
        issues.append("Invalid evaluation status.")
    if record.get("evidence_strength") not in {"HIGH", "MODERATE", "LIMITED", "PENDING"}:
        issues.append("Invalid independent evidence strength.")
    if record.get("sensitivity_status") not in {"ADEQUATE", "LIMITED", "UNKNOWN", "NOT_APPLICABLE"}:
        issues.append("Invalid sensitivity status.")
    if not isinstance(record.get("independently_reviewed"), bool):
        issues.append("Independent-review state must be explicit.")
    reviewers = record.get("reviewer_ids")
    if (not isinstance(reviewers, list) or any(not isinstance(item, str) or not OPAQUE_REVIEWER.fullmatch(item) for item in reviewers)
            or len(set(reviewers)) != len(reviewers)):
        issues.append("Reviewer IDs must be unique opaque synthetic IDs.")
    evidence_digest = record.get("review_evidence_sha256")
    if evidence_digest is not None and (not isinstance(evidence_digest, str) or not re.fullmatch(r"[a-f0-9]{64}", evidence_digest)):
        issues.append("Independent review evidence digest is malformed.")
    eligible = record.get("scoring_eligibility")
    reason = record.get("exclusion_reason")
    if not isinstance(eligible, bool) or (eligible and reason is not None) or (not eligible and (not isinstance(reason, str) or not reason.strip())):
        issues.append("Eligibility and exclusion reason are inconsistent.")
    if eligible and (record.get("evaluation_status") != "EVALUABLE" or record.get("independently_reviewed") is not True):
        issues.append("Only independently reviewed, evaluable controls may be eligible.")
    if eligible and (len(reviewers) < 2 or evidence_digest is None):
        issues.append("Eligible controls require independent evidence and two distinct reviewers.")
    if eligible and record.get("control_class") == "POSITIVE" and record.get("evidence_strength") not in {"HIGH", "MODERATE"}:
        issues.append("Eligible positive controls require adequate independent evidence.")
    if eligible and record.get("control_class") == "NEGATIVE" and record.get("sensitivity_status") != "ADEQUATE":
        issues.append("Negative controls with unknown or limited sensitivity cannot be eligible.")
    if not isinstance(record.get("study_id"), str) or not record["study_id"]:
        issues.append("Study identifier is required.")
    if not isinstance(record.get("replicate_group"), str) or not record["replicate_group"]:
        issues.append("Biological sample/replicate group is required.")
    digest = record.get("qualification_sha256")
    if not isinstance(digest, str) or digest != qualification_digest(record):
        issues.append("Qualification digest is missing or invalid.")
    return sorted(set(issues))


def score_synthetic_bundle(
    analysis: Any,
    truth_bundle: Any,
    qualifications: Any,
    *,
    unblinding_authorization: Any,
    expected_policy_sha256: str,
    reference_exclusion_result: Any,
    expected_reference_evidence_sha256: str,
) -> dict[str, Any]:
    """Score exact candidate-ID matches after explicit synthetic unblinding approval."""
    policy = {
        "version": SCORING_POLICY_VERSION,
        "candidate_match": "exact opaque candidate_id",
        "candidate_duplicates": "deduplicate candidate_id within a sample",
        "sample_positive": "positive if at least one truth candidate is detected",
        "sample_negative_false_positive": "one FP per biological replicate_group with any candidate",
        "replicate_aggregation": "group by replicate_group; any positive member detection is detected",
        "truth_item_matching": "one-to-one exact candidate_id within sample",
    }
    policy_sha = canonical_sha256(policy)
    auth = unblinding_authorization
    reviewer_ids = auth.get("reviewer_ids") if isinstance(auth, dict) else None
    reviewers_valid = (
        isinstance(reviewer_ids, list) and len(reviewer_ids) >= 2
        and all(isinstance(item, str) and OPAQUE_REVIEWER.fullmatch(item) for item in reviewer_ids)
        and len(set(reviewer_ids)) == len(reviewer_ids)
    )
    issues: list[str] = []
    if policy_sha != expected_policy_sha256:
        issues.append("Scoring policy digest is missing or does not match the approved policy.")
    exclusion_results = (
        reference_exclusion_result.get("results")
        if isinstance(reference_exclusion_result, dict) else None
    )
    if (not isinstance(reference_exclusion_result, dict)
            or reference_exclusion_result.get("status") != "PASS"
            or reference_exclusion_result.get("evidence_sha256") != expected_reference_evidence_sha256
            or not isinstance(expected_reference_evidence_sha256, str)
            or not re.fullmatch(r"[a-f0-9]{64}", expected_reference_evidence_sha256)
            or reference_exclusion_result.get("issues") != []
            or not isinstance(exclusion_results, list)
            or any(not isinstance(item, dict) or item.get("decision") != "ACCEPT"
                   for item in exclusion_results)):
        issues.append("Approved reference-exclusion evidence is absent, failed, incomplete, or unbound.")
    if not isinstance(analysis, dict) or set(analysis) != {"analysis_sha256", "samples"}:
        issues.append("Analysis output must contain exactly its digest and samples.")
        analysis = {}
    if not isinstance(truth_bundle, dict) or set(truth_bundle) != {"analysis_sha256", "truth_records"}:
        issues.append("Truth bundle has missing or unknown fields.")
        truth_bundle = {}
    if analysis.get("analysis_sha256") != canonical_sha256(analysis.get("samples")):
        issues.append("Analysis output digest is missing or invalid.")
    if truth_bundle.get("analysis_sha256") != analysis.get("analysis_sha256"):
        issues.append("Truth bundle is not bound to the approved analysis output.")
    truth_digest = canonical_sha256(truth_bundle.get("truth_records"))
    if (not isinstance(auth, dict) or set(auth) != {"approved", "reviewer_ids", "truth_bundle_sha256"}
            or auth.get("approved") is not True
            or auth.get("truth_bundle_sha256") != truth_digest
            or not reviewers_valid):
        issues.append("Independent synthetic unblinding authorization is absent or invalid.")

    if not isinstance(analysis.get("samples"), list) or not isinstance(truth_bundle.get("truth_records"), list):
        issues.append("Analysis samples and truth records must be arrays.")
    sample_rows = analysis.get("samples", [])
    truth_rows = truth_bundle.get("truth_records", [])
    if not isinstance(qualifications, list):
        issues.append("Control qualifications must be an array.")
        qualifications = []
    qualification_by_sample: dict[str, dict[str, Any]] = {}
    excluded_controls = []
    for record in qualifications:
        issues.extend(validate_qualification(record))
        if not isinstance(record, dict):
            continue
        if not record.get("scoring_eligibility"):
            excluded_controls.append({"control_id": record.get("control_id"),
                                      "reason": record.get("exclusion_reason") or record.get("evaluation_status")})
        for sample_id in record.get("sample_ids", []):
            if sample_id in qualification_by_sample:
                issues.append("A sample is assigned to more than one control record.")
            qualification_by_sample[sample_id] = record
    if issues:
        return {"status": "FAIL", "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
                "issues": sorted(set(issues)), "scoring_policy_sha256": policy_sha}

    analysis_by_id = {}
    for row in sample_rows:
        if (not isinstance(row, dict) or set(row) != {"sample_id", "candidates", "read_count", "read_unit"}
                or not isinstance(row.get("sample_id"), str) or not OPAQUE_SAMPLE.fullmatch(row["sample_id"])
                or not isinstance(row.get("candidates"), list)
                or not isinstance(row.get("read_count"), int) or isinstance(row.get("read_count"), bool) or row["read_count"] < 0
                or row.get("read_unit") not in {"READS", "READ_PAIRS"}):
            issues.append("Malformed blinded analysis sample.")
            continue
        ids = []
        for candidate in row["candidates"]:
            if not isinstance(candidate, dict) or set(candidate) != {"candidate_id"} or not isinstance(candidate.get("candidate_id"), str):
                issues.append("Candidate calls must contain only opaque candidate_id values.")
            else:
                ids.append(candidate["candidate_id"])
        if row["sample_id"] in analysis_by_id:
            issues.append("Duplicate analysis sample identifier.")
        analysis_by_id[row["sample_id"]] = {**row, "candidate_ids": set(ids)}
    truth_by_id = {}
    for row in truth_rows:
        if (not isinstance(row, dict) or set(row) != {"sample_id", "label", "truth_candidate_ids"}
                or row.get("label") not in {"POSITIVE", "NEGATIVE"}
                or not isinstance(row.get("sample_id"), str) or not OPAQUE_SAMPLE.fullmatch(row["sample_id"])
                or not isinstance(row.get("truth_candidate_ids"), list)
                or any(not isinstance(x, str) for x in row.get("truth_candidate_ids", []))):
            issues.append("Malformed synthetic truth record.")
            continue
        if row["sample_id"] in truth_by_id:
            issues.append("Duplicate truth sample identifier.")
        truth_by_id[row["sample_id"]] = row
    eligible_ids = {sample_id for sample_id, record in qualification_by_sample.items()
                    if record.get("scoring_eligibility") is True}
    if set(truth_by_id) != (set(analysis_by_id) & eligible_ids):
        issues.append("Truth bundle must cover exactly the eligible analysis samples; excluded samples stay blinded.")
    if set(analysis_by_id) - set(qualification_by_sample):
        issues.append("Every analysis sample requires a control qualification or explicit exclusion record.")
    if issues:
        return {"status": "FAIL", "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
                "issues": sorted(set(issues)), "scoring_policy_sha256": policy_sha}

    groups: dict[str, list[tuple[str, str, bool, set[str], set[str]]]] = defaultdict(list)
    negative_group_reads: dict[str, int] = {}
    negative_read_units: set[str] = set()
    for sample_id, truth in truth_by_id.items():
        row = analysis_by_id[sample_id]
        qualification = qualification_by_sample[sample_id]
        calls = row["candidate_ids"]
        expected = set(truth["truth_candidate_ids"])
        if truth["label"] == "POSITIVE" and not expected:
            issues.append("Positive truth records require at least one curated candidate truth item.")
        if truth["label"] == "NEGATIVE" and expected:
            issues.append("Negative truth records cannot contain positive candidate truth items.")
        if len(expected) != len(truth["truth_candidate_ids"]):
            issues.append("Duplicate candidate truth item in one sample.")
        if truth["label"] == "NEGATIVE":
            negative_read_units.add(row["read_unit"])
            negative_group_reads[qualification["replicate_group"]] = max(
                negative_group_reads.get(qualification["replicate_group"], 0), row["read_count"]
            )
        matched = calls & expected
        groups[qualification["replicate_group"]].append(
            (truth["label"], sample_id, bool(matched), calls, expected)
        )
    tp = fp = tn = fn = 0
    candidate_tp = candidate_fp = candidate_fn = 0
    eligible_truth_items = detected_truth_items = false_candidates = 0
    for members in groups.values():
        labels = {member[0] for member in members}
        if len(labels) != 1:
            issues.append("Technical replicates in a biological group have conflicting truth labels.")
            continue
        label = next(iter(labels))
        detected = any(member[2] for member in members)
        any_call = any(member[3] for member in members)
        if label == "POSITIVE":
            tp += int(detected)
            fn += int(not detected)
        else:
            fp += int(any_call)
            tn += int(not any_call)
        calls = set().union(*(member[3] for member in members))
        expected_sets = [member[4] for member in members]
        if any(expected != expected_sets[0] for expected in expected_sets[1:]):
            issues.append("Technical replicates in a biological group have conflicting candidate truth.")
            continue
        expected = expected_sets[0]
        matched = calls & expected
        candidate_tp += len(matched)
        candidate_fp += len(calls - expected)
        candidate_fn += len(expected - calls)
        eligible_truth_items += len(expected)
        detected_truth_items += len(matched)
        if label == "NEGATIVE":
            false_candidates += len(calls)
    if issues:
        return {"status": "FAIL", "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
                "issues": sorted(set(issues)), "scoring_policy_sha256": policy_sha}
    if len(negative_read_units) > 1:
        return {"status": "FAIL", "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
                "issues": ["Evaluable negative denominators mix READS and READ_PAIRS."],
                "scoring_policy_sha256": policy_sha}
    negative_groups = sum(1 for members in groups.values() if members[0][0] == "NEGATIVE")
    positive_groups = sum(1 for members in groups.values() if members[0][0] == "POSITIVE")
    total_reads = sum(negative_group_reads.values())
    per_million = _rate(false_candidates * 1_000_000, total_reads,
                        "No reads or read pairs from evaluable negative groups.")
    return {
        "status": "PASS", "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
        "statement": "SYNTHETIC SOFTWARE VALIDATION — NOT BIOLOGICAL PERFORMANCE EVIDENCE",
        "scoring_policy_version": SCORING_POLICY_VERSION,
        "scoring_policy_sha256": policy_sha,
        "sample_level": {
            "confusion_matrix": {"TP": tp, "FP": fp, "TN": tn, "FN": fn},
            "eligible_positive_groups": positive_groups, "eligible_negative_groups": negative_groups,
            "sensitivity": _rate(tp, tp + fn, "No independently qualified evaluable positive groups."),
            "specificity": _rate(tn, tn + fp, "No independently qualified evaluable negative groups."),
        },
        "candidate_level": {
            "true_positives": candidate_tp, "false_positives": candidate_fp,
            "false_negatives": candidate_fn,
            "precision": _rate(candidate_tp, candidate_tp + candidate_fp, "No candidate calls."),
            "recall": _rate(detected_truth_items, eligible_truth_items, "No curated candidate truth items."),
            "false_candidate_burden_per_evaluable_negative_sample": _rate(false_candidates, negative_groups, "No evaluable negative samples."),
            "false_candidate_burden_per_million_reads_or_pairs": {
                **per_million, "unit": f"false candidates per 1,000,000 {next(iter(negative_read_units), 'READS')}",
                "read_unit": next(iter(negative_read_units), None),
                "denominator": total_reads, "read_groups": negative_groups,
            },
        },
        "excluded_controls": excluded_controls,
        "independent_studies_represented": len({qualification_by_sample[sample_id]["study_id"] for sample_id in truth_by_id}),
        "analysis_sha256": analysis["analysis_sha256"], "truth_bundle_sha256": truth_digest,
        "reference_exclusion_evidence_sha256": expected_reference_evidence_sha256,
        "unblinding_reviewers": sorted(auth["reviewer_ids"]),
        "limitations": ["Synthetic fixtures do not estimate biological performance.",
                        "No confidence intervals are calculated; sample sizes and dependence structures do not support inference."],
        "issues": [],
    }


def scoring_policy_digest() -> str:
    return canonical_sha256({
        "version": SCORING_POLICY_VERSION,
        "candidate_match": "exact opaque candidate_id",
        "candidate_duplicates": "deduplicate candidate_id within a sample",
        "sample_positive": "positive if at least one truth candidate is detected",
        "sample_negative_false_positive": "one FP per biological replicate_group with any candidate",
        "replicate_aggregation": "group by replicate_group; any positive member detection is detected",
        "truth_item_matching": "one-to-one exact candidate_id within sample",
    })


def human_scoring_report(result: dict[str, Any]) -> str:
    """Render the machine result without replacing undefined values with zero."""
    lines = [result.get("statement", "SYNTHETIC SOFTWARE VALIDATION — NOT BIOLOGICAL PERFORMANCE EVIDENCE"),
             f"Scoring status: {result.get('status', 'FAIL')}",
             f"Overall state: {result.get('overall_state', 'BLOCKED_FOR_BENCHMARK_EXECUTION')}"]
    sample = result.get("sample_level", {})
    matrix = sample.get("confusion_matrix", {})
    if matrix:
        lines.append("Sample-level confusion matrix (biological replicate groups): "
                     + ", ".join(f"{key}={matrix.get(key)}" for key in ("TP", "FP", "TN", "FN")))
    for key in ("sensitivity", "specificity"):
        metric = sample.get(key)
        if metric:
            lines.append(f"{key}: {metric['value'] if metric['status'] == 'ESTIMATED' else 'NOT_ESTIMABLE'}"
                         + (f" ({metric.get('reason')})" if metric.get("reason") else ""))
    lines.extend(f"- {issue}" for issue in result.get("issues", []))
    return "\n".join(lines) + "\n"
