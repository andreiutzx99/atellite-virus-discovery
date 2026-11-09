"""M35 preregistration helpers for synthetic-only diagnostic studies.

This module defines the experiment before results are observed.  It does not
change M6/M8/M31 behavior and does not authorize biological execution.
"""

from __future__ import annotations

import hashlib
import json

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
