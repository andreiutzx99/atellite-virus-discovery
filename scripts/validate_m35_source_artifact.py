"""Validate the original M34 Actions artifact before using it as source evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from satellite_discovery.m34_negative_control_indel_robustness import (
    validate_review_summary,
)

EXPECTED_ARTIFACT_ID = 13670022421
EXPECTED_RUN_ID = 42609565425
EXPECTED_ARTIFACT_NAME = "m34-negative-control-indel-robustness"
REQUIRED_CASES = {
    "development-m34-c0049",
    "tuning-m34-c0050",
    "held_out-m34-c0051",
    "development-m34-c0052",
    "tuning-m34-c0056",
}


def _read_json(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"required M34 artifact file is missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON in M34 artifact file: {path}") from exc


def _check_digest(path: Path, expected: str) -> None:
    if not path.is_file():
        raise ValueError(f"digest-indexed evidence is missing: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"M34 evidence digest mismatch: {path}")


def _fasta_sequences(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"candidate assembly FASTA is missing: {path}")
    records, current, sequence = {}, None, []
    for line in path.read_text(encoding="ascii").splitlines():
        if line.startswith(">"):
            if current is not None:
                records[current] = "".join(sequence)
            current, sequence = line[1:].split()[0], []
        elif line.strip():
            sequence.append(line.strip())
    if current is not None:
        records[current] = "".join(sequence)
    return records


def validate_artifact_metadata(artifact_id: int, run_id: int, name: str) -> None:
    if artifact_id != EXPECTED_ARTIFACT_ID:
        raise ValueError("M34 artifact ID does not match the registered source")
    if run_id != EXPECTED_RUN_ID:
        raise ValueError("M34 workflow run ID does not match the registered source")
    if name != EXPECTED_ARTIFACT_NAME:
        raise ValueError("M34 artifact name does not match the registered source")


def validate_source_artifact(artifact_dir: Path, summary_path: Path) -> dict:
    artifact_dir = artifact_dir.resolve()
    summary = _read_json(summary_path)
    provenance = summary.get("provenance", {})
    validate_artifact_metadata(
        provenance.get("artifact_id"),
        provenance.get("workflow_run_id"),
        provenance.get("artifact_name"),
    )

    result = _read_json(artifact_dir / "M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.json")
    validate_review_summary(summary, result)
    if result.get("governance") != {
        "decision": "INCOMPLETE",
        "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
        "biological_execution_authorized": False,
    }:
        raise ValueError("M34 source artifact governance mismatch")

    benchmark = artifact_dir / "benchmark"
    m32 = _read_json(benchmark / "M32_END_TO_END_SYNTHETIC_EVIDENCE.json")
    read_index = _read_json(benchmark / "M34_READ_PROVENANCE_INDEX.json")
    truth_validation = _read_json(benchmark / "M34_TARGET_ABSENCE_VALIDATION.json")
    case_rows = {row["case_id"]: row for row in result.get("case_level_results", [])}
    m32_metrics = {
        row["case_id"]: row
        for row in m32.get("benchmark_metrics", {}).get("cases", [])
    }
    triage = {row["case_id"]: row for row in m32.get("candidate_triage", [])}
    truth_rows = truth_validation.get("cases", {})
    read_rows = read_index

    if REQUIRED_CASES - case_rows.keys() or REQUIRED_CASES - m32_metrics.keys():
        raise ValueError("one or more registered M34 false-alarm cases are absent")
    verified = []
    for case_id in sorted(REQUIRED_CASES):
        summary_case = case_rows[case_id]
        if summary_case.get("synthetic_truth_target_present") is not False:
            raise ValueError(f"{case_id}: source summary does not establish target absence")
        source_truth = truth_rows.get(case_id)
        if not source_truth or source_truth.get("candidate_sequence_absent") is not True:
            raise ValueError(f"{case_id}: target-absence sidecar evidence is missing")
        truth_path = benchmark / "reconstruction" / case_id / "heldout_truth.json"
        _check_digest(truth_path, source_truth["source_truth_sidecar_sha256"])
        truth_doc = _read_json(truth_path)
        truth_cases = truth_doc.get("cases", [])
        if len(truth_cases) != 1 or truth_cases[0].get("candidate_sequence") is not None:
            raise ValueError(f"{case_id}: target-absence source truth is inconsistent")

        read_provenance = read_rows.get(case_id)
        if not read_provenance:
            raise ValueError(f"{case_id}: read-provenance index entry is missing")
        _check_digest(
            benchmark / read_provenance["path"], read_provenance["sha256"]
        )

        metric = m32_metrics[case_id]
        triage_case = triage.get(case_id)
        if not metric.get("m8_search_complete") or triage_case is None:
            raise ValueError(f"{case_id}: original M8 evidence is incomplete")
        candidate_sha = next(
            (
                item["candidate"]["sha256"]
                for item in summary["false_alarm_investigations"]
                if item["case_id"] == case_id
            ),
            None,
        )
        matching_candidates = [
            item for item in triage_case.get("candidate_records", [])
            if item.get("query_sha256") == candidate_sha
        ]
        if len(matching_candidates) != 1:
            raise ValueError(f"{case_id}: source candidate identity is missing or ambiguous")
        candidate = matching_candidates[0]
        if candidate.get("read_support_status") != "READ_SUPPORTED_ASSEMBLY":
            raise ValueError(f"{case_id}: source candidate lacks measured read support")
        if candidate.get("m8_aggregate_status") != "COMPLETE":
            raise ValueError(f"{case_id}: source candidate M8 search is not complete")
        if candidate.get("triage_status") != "REVIEW_PRIORITY":
            raise ValueError(f"{case_id}: source candidate is not REVIEW_PRIORITY")
        analysis_id = summary_case.get("analysis_id")
        if not analysis_id:
            raise ValueError(f"{case_id}: registered analysis identity is missing")
        stage = benchmark / "reconstruction" / case_id / "stages" / f"m6_{analysis_id}"
        assembled = _fasta_sequences(stage / "assembly" / "contigs.fasta")
        candidate_id = candidate.get("candidate_id")
        sequence = assembled.get(candidate_id)
        if sequence is None or hashlib.sha256(sequence.encode("ascii")).hexdigest() != candidate_sha:
            raise ValueError(f"{case_id}: candidate sequence digest does not match its M6 contig")
        support = _read_json(stage / "read_support.json")
        support_rows = {
            row.get("contig_id"): row.get("status")
            for row in support.get("contigs", [])
        }
        if support_rows.get(candidate_id) != "READ_SUPPORTED_ASSEMBLY":
            raise ValueError(f"{case_id}: raw M6 support evidence does not support the candidate")

        raw_outputs = triage_case.get("raw_outputs", [])
        if not raw_outputs:
            raise ValueError(f"{case_id}: original M8 raw output index is missing")
        for raw in raw_outputs:
            _check_digest(benchmark / raw["path"], raw["sha256"])
        verified.append({
            "case_id": case_id,
            "candidate_sha256": candidate_sha,
            "read_provenance_sha256": read_provenance["sha256"],
            "source_truth_sha256": source_truth["source_truth_sidecar_sha256"],
            "m8_raw_output_count": len(raw_outputs),
            "source_triage": "REVIEW_PRIORITY",
            "status": "SOURCE_EVIDENCE_VERIFIED_NOT_RERUN",
        })

    panel_path = benchmark / "reference" / "panel.fasta"
    panel_digest = hashlib.sha256(panel_path.read_bytes()).hexdigest() \
        if panel_path.is_file() else None
    if panel_digest != m32.get("panel_preregistration", {}).get("panel_fasta_sha256") \
            or panel_digest != summary.get("reference_panel", {}).get("panel_fasta_sha256"):
        raise ValueError("M34 source panel digest mismatch")
    return {
        "schema": "m35-m34-source-artifact-validation-v1",
        "artifact_id": EXPECTED_ARTIFACT_ID,
        "workflow_run_id": EXPECTED_RUN_ID,
        "artifact_name": EXPECTED_ARTIFACT_NAME,
        "status": "VERIFIED_SOURCE_EVIDENCE",
        "rerun_status": "NOT_RUN",
        "cases": verified,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_dir", type=Path)
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("docs/M34_NEGATIVE_CONTROL_INDEL_ROBUSTNESS.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = validate_source_artifact(args.artifact_dir, args.summary)
    rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
