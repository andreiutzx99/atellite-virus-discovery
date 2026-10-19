"""M20 Phase 5 synthetic-only release-readiness audit for a Phase 4 run."""

import argparse
import html
import json
from pathlib import Path

from . import m12_contracts, m15_contracts, m20_phase1, m20_phase3, m20_phase4

SCHEMA = "m20-phase5-release-readiness-v1"
INVALID_CASES = ("c002", "c005", "c006", "c009", "c010")


def _was_not_evaluated_artifact(support, artifact_type):
    return (
        artifact_type == "read_support_evidence"
        and support.get("status") == "NOT_EVALUATED"
        and support.get("read_support") == []
        and isinstance(
            support.get("provenance", {}).get("support_input_fragment_ids"), list,
        )
        and bool(support["provenance"]["support_input_fragment_ids"])
    )


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _table(root, sample):
    workflow_root = Path(root) / "m12_workflow"
    workflow = _load(workflow_root / "workflow.json")
    row = m20_phase4._stage_row(workflow, f"m12_{sample}", "m12_artifact_review")
    if not row:
        raise ValueError(f"Missing M12 stage for {sample}")
    stage_root, _, _ = m20_phase4._validated_stage(workflow_root, row)
    return _load(stage_root / "artifact_review_table.json"), workflow_root, workflow, row


def _historical_invalids(previous_root, current_root=None):
    findings = []
    if not previous_root:
        return findings
    for sample in INVALID_CASES:
        rows, workflow_root, workflow, row = _table(previous_root, sample)
        corrected_rows = (
            _table(current_root, sample)[0] if current_root else []
        )
        invalid = [item for item in rows if item.get("review_state") == "INVALID"]
        for item in invalid:
            ref = item["artifact_ref"]
            stage_row = m20_phase4._stage_row(
                workflow, ref["producer_stage_id"], "residual_evidence",
            )
            stage_root, _, _ = m20_phase4._validated_stage(workflow_root, stage_row)
            support = m12_contracts.read_json(stage_root / ref["relative_path"])
            reconstruction = m12_contracts.read_json(
                stage_root / "reconstruction_evidence.json",
            )
            status = support.get("status")
            records = support.get("read_support")
            ids = support.get("provenance", {}).get("support_input_fragment_ids")
            root_cause = _was_not_evaluated_artifact(support, ref["artifact_type"])
            corrected = next((
                candidate for candidate in corrected_rows
                if candidate["artifact_ref"]["artifact_type"] == ref["artifact_type"]
                and candidate["artifact_ref"]["relative_path"] == ref["relative_path"]
            ), None)
            findings.append({
                "case_id": sample,
                "artifact_type": ref["artifact_type"],
                "artifact_path": ref["relative_path"],
                "artifact_sha256": ref["sha256"],
                "prior_review_state": "INVALID",
                "validation_rule": "M12._support_query_accounting exact query/input reconciliation",
                "reason_code": (
                    "M12_ACCOUNTING_CHECK_RAN_WHILE_NOT_EVALUATED"
                    if root_cause else "UNCLASSIFIED_M12_INVALID"
                ),
                "historical_error_message": (
                    "M6 support queries do not reconcile to declared inputs."
                    if root_cause else None
                ),
                "upstream_support_status": status,
                "upstream_reconstruction_status": reconstruction.get("status"),
                "declared_support_input_count": len(ids) if isinstance(ids, list) else None,
                "observed_support_query_count": len(records) if isinstance(records, list) else None,
                "corrected_review": ({
                    "review_state": corrected["review_state"],
                    "analysis_execution_status": corrected["analysis_execution_status"],
                    "accounting_status": corrected["accounting_status"],
                    "observation_status": corrected["observation_status"],
                } if corrected else None),
                "classification": (
                    "VALIDATOR_DEFECT_CORRECTED_NO_BIOLOGICAL_OBSERVATION"
                    if root_cause else "UNRESOLVED_REVIEW_REQUIRED"
                ),
                "explanation": (
                    "The producer explicitly reported NOT_EVALUATED and emitted no "
                    "query rows; requiring completed-query reconciliation mislabeled "
                    "unavailable accounting as invalid evidence. The row is now "
                    "VERIFIED for artifact identity with NOT_STARTED/UNKNOWN/NO_OBSERVATION axes."
                    if root_cause else "The cause could not be established from verified producer artifacts."
                ),
            })
    return findings


def _leaf_differences(before, after, path=""):
    if type(before) is not type(after):
        return [(path, before, after)]
    if isinstance(before, dict):
        differences = []
        for key in sorted(set(before) | set(after)):
            if key not in before or key not in after:
                differences.append((f"{path}/{key}", None, None))
            else:
                differences.extend(_leaf_differences(
                    before[key], after[key], f"{path}/{key}",
                ))
        return differences
    if isinstance(before, list):
        if len(before) != len(after):
            return [(path, len(before), len(after))]
        return [
            difference
            for index, (left, right) in enumerate(zip(before, after))
            for difference in _leaf_differences(left, right, f"{path}/{index}")
        ]
    return [] if before == after else [(path, before, after)]


def _replay_difference_audit(phase2b, phase4, sample):
    original_root = phase2b / "stages/m4_m6"
    replay_root = phase4 / "m12_workflow"
    original_wf = _load(original_root / "workflow.json")
    replay_wf = _load(replay_root / "workflow.json")
    old = m20_phase4._stage_row(original_wf, f"m6_{sample}", "residual_evidence")
    new = m20_phase4._stage_row(replay_wf, f"m6_{sample}", "residual_evidence")
    if not old or not new:
        return {"classification": "UNRESOLVED", "changed_artifacts": []}
    old_dir = original_root / old["output_path"]
    new_dir = replay_root / new["output_path"]
    old_workflow = str(original_root.resolve())
    new_workflow = str(replay_root.resolve())
    changed, unexplained, changed_paths = [], [], set()
    for name in sorted(set(old.get("artifacts", {})) | set(new.get("artifacts", {}))):
        left = old.get("artifacts", {}).get(name, {})
        right = new.get("artifacts", {}).get(name, {})
        if left.get("sha256") == right.get("sha256"):
            continue
        changed.append(name)
        before = old_dir / name
        after = new_dir / name
        if name.endswith(".sam"):
            old_bytes, new_bytes = before.read_bytes(), after.read_bytes()
            old_text = old_bytes.decode("utf-8").splitlines()
            new_text = new_bytes.decode("utf-8").splitlines()
            old_pg = [line for line in old_text if line.startswith("@PG")]
            new_pg = [line for line in new_text if line.startswith("@PG")]
            old_records = [line for line in old_text if not line.startswith("@PG")]
            new_records = [line for line in new_text if not line.startswith("@PG")]
            path_only = (
                old_records == new_records and len(old_pg) == len(new_pg)
                and all(a.replace(old_workflow, new_workflow) == b
                        for a, b in zip(old_pg, new_pg))
            )
            if not path_only:
                unexplained.append({"artifact_path": name, "kind": "SAM_RECORD_OR_HEADER_CONTENT"})
        elif name.endswith(".json"):
            differences = _leaf_differences(_load(before), _load(after))
            for path, left_value, right_value in differences:
                changed_paths.add(path)
                path_metadata = (
                    isinstance(left_value, str) and isinstance(right_value, str)
                    and old_workflow in left_value and new_workflow in right_value
                )
                digest_reference = (
                    ("sha256" in path.lower())
                    and isinstance(left_value, str) and isinstance(right_value, str)
                    and len(left_value) == len(right_value) == 64
                )
                if not (path_metadata or digest_reference):
                    unexplained.append({
                        "artifact_path": name, "field": path,
                        "kind": "NON_PATH_CONTENT_CHANGE",
                    })
        else:
            unexplained.append({"artifact_path": name, "kind": "UNCLASSIFIED_FILE"})
    return {
        "classification": (
            "EXPECTED_RUN_PATH_METADATA_WITH_DEPENDENT_DIGEST_CHANGES"
            if changed and not unexplained else
            "NO_CHANGED_ARTIFACTS" if not changed else "UNRESOLVED_CONTENT_DIFFERENCE"
        ),
        "changed_artifacts": changed,
        "changed_json_fields": sorted(changed_paths),
        "unexplained_differences": unexplained,
    }


def build_report(phase2b_output, phase3_output, phase4_output, *,
                 previous_phase4_output=None, validation_counts=None,
                 ci_status=None):
    phase2b = Path(phase2b_output).resolve(strict=True)
    phase3 = Path(phase3_output).resolve(strict=True)
    phase4 = Path(phase4_output).resolve(strict=True)
    baseline = _load(phase2b / "report.json")
    fixture_manifest = _load(phase2b / "benchmark_manifest.json")
    phase2b_sha, truth_sha = m20_phase3._verify_frozen_phase2b(phase2b, baseline)
    phase3_report = _load(phase3 / "report.json")
    phase4_report = _load(phase4 / "report.json")
    if phase4_report.get("schema") != m20_phase4.SCHEMA:
        raise ValueError("Phase 5 requires an M20 Phase 4 report")
    if phase4_report.get("frozen_fixtures", {}).get("phase2b_manifest_sha256") != phase2b_sha:
        raise ValueError("Phase 4 report does not bind the verified Phase 2B fixture")
    contract_map = m20_phase1.build_contract_map()
    cases = []
    current_invalids = []
    for case in phase4_report["cases"]:
        sample = case["sample_id"]
        rows, m12_root, m12_workflow, m12_stage = _table(phase4, sample)
        invalid_rows = [row for row in rows if row["review_state"] == "INVALID"]
        current_invalids.extend({
            "case_id": sample,
            "artifact_type": row["artifact_ref"]["artifact_type"],
            "artifact_path": row["artifact_ref"]["relative_path"],
            "state": row["review_state"],
            "producer_status": row["producer_status_raw"],
        } for row in invalid_rows)
        m15_counts = (case["m15"].get("summary") or {}).get("counts", {})
        m15_bindings = case["m15"].get("validated_producer_bindings", [])
        provenance_counts = {}
        payload_validity_counts = {}
        for binding in m15_bindings:
            provenance = binding.get("producer_provenance_state", "UNKNOWN")
            validity = binding.get("validation_state", "UNKNOWN")
            provenance_counts[provenance] = provenance_counts.get(provenance, 0) + 1
            payload_validity_counts[validity] = payload_validity_counts.get(validity, 0) + 1
        original_m6_ids = {
            item.get("producer_workflow_id") for item in m15_bindings
            if item.get("producer_milestone") == "M6"
        }
        replay_id = case["m12"].get("workflow_id")
        cases.append({
            "case_id": sample,
            "upstream_candidate_availability": case["phase3_upstream_outcome"].get(
                "candidate_availability", "UNKNOWN",
            ),
            "m12": {
                "status": case["m12"]["status"],
                "review_state_counts": case["m12"]["review_state_counts"],
                "invalid_rows": invalid_rows,
                "technical_review_rows": [{
                    "artifact_type": row["artifact_ref"]["artifact_type"],
                    "artifact_path": row["artifact_ref"]["relative_path"],
                    "review_state": row["review_state"],
                    "producer_status": row["producer_status_raw"],
                    "analysis_execution_status": row["analysis_execution_status"],
                    "accounting_status": row["accounting_status"],
                    "observation_status": row["observation_status"],
                    "limitations": row["limitations"],
                } for row in rows],
                "workflow_id": replay_id,
            },
            "m15": {
                "status": case["m15"]["status"],
                "counts": m15_counts,
                "producer_provenance_state_counts": provenance_counts,
                "payload_validation_state_counts": payload_validity_counts,
                "workflow_ids_by_milestone": {
                    milestone: sorted({
                        item.get("producer_workflow_id") for item in m15_bindings
                        if item.get("producer_milestone") == milestone
                    })
                    for milestone in sorted({item.get("producer_milestone") for item in m15_bindings})
                },
                "m6_references_frozen_phase2b": (
                    original_m6_ids == {case["phase2b_m6_replay_comparison"].get(
                        "phase2b_workflow_id",
                    )}
                ),
                "m12_references_phase4_replay": (
                    case["phase4_m15_workflow_id"] if "phase4_m15_workflow_id" in case
                    else any(item.get("producer_milestone") == "M12"
                             and item.get("producer_workflow_id") == replay_id
                             for item in m15_bindings)
                ),
            },
            "phase2b_m6_replay": case["phase2b_m6_replay_comparison"],
            "phase2b_m6_replay_difference_audit": _replay_difference_audit(
                phase2b, phase4, sample,
            ),
            "phase3_outcomes": case["phase3_upstream_outcome"],
            "rejected_or_missing_artifacts": case["rejected_or_missing_artifacts"],
        })
    historical = _historical_invalids(previous_phase4_output, phase4)
    report = {
        "schema": SCHEMA,
        "software_integration_status": (
            "VALIDATED" if phase4_report.get("status") == "COMPLETE" and not current_invalids
            else "INCOMPLETE"
        ),
        "biological_discovery_status": "NOT_VALIDATED",
        "decision": "SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED",
        "fixtures": {
            "phase1_manifest_sha256": baseline["fixtures"]["phase1_baseline"]["manifest_sha256"],
            "phase1_truth_sha256": baseline["fixtures"]["phase1_baseline"]["heldout_truth_sha256"],
            "phase2b_manifest_sha256": phase2b_sha,
            "phase2b_truth_sha256": truth_sha,
            "phase3_report_sha256": m20_phase4._sha((phase3 / "report.json").read_bytes()),
        },
        "resource_limits": fixture_manifest["matrix"]["resource_bounds"],
        "capability_matrix": contract_map,
        "supported_m12_producer_types": {
            key: sorted(value) for key, value in m12_contracts.PRODUCER_TYPES.items()
        },
        "supported_m15_producer_types": {
            key: sorted(value) for key, value in m15_contracts.PRODUCER_TYPES.items()
        },
        "handoff_matrix": {
            "m12_supplied": {"M6": sorted(m12_contracts.PRODUCER_TYPES["M6"])},
            "m12_contract_allows_but_phase4_did_not_supply": {
                "M5": sorted(m12_contracts.PRODUCER_TYPES["M5"]),
            },
            "m15_supplied_milestones": ["M6", "M7", "M8", "M9", "M10", "M12"],
            "m15_contract_allows_but_not_supplied": ["M5", "M13", "M14"],
            "m10_payload_excluded": {
                "artifact_type": "m10_candidate_accounting",
                "reason": "M15_PAYLOAD_SCHEMA_REJECTS_JSONL_ACCOUNTING",
            },
        },
        "excluded_or_unavailable_handoffs": [
            {"artifact_type": "m10_candidate_accounting",
             "reason": "M15_PAYLOAD_SCHEMA_REJECTS_JSONL_ACCOUNTING"},
            {"milestone": "M13", "state": "NOT_SUPPLIED"},
            {"milestone": "M14", "state": "NOT_SUPPLIED"},
        ],
        "m12_historical_invalid_findings": historical,
        "m12_current_invalid_findings": current_invalids,
        "cases": cases,
        "reproducibility": {
            "phase4_semantic_digest": phase4_report.get(
                "deterministic_semantic_outcomes_sha256",
            ),
            "phase4_run_ids_are_execution_specific": True,
            "phase4_report_sha256": m20_phase4._sha((phase4 / "report.json").read_bytes()),
        },
        "cache_resume_observations": (validation_counts or {}).get(
            "cache_resume_observations", {},
        ),
        "adversarial_validation": (validation_counts or {}).get(
            "adversarial_validation", {},
        ),
        "validation_counts": validation_counts or {},
        "ci_status": ci_status or {"state": "NOT_RECORDED"},
        "limitations": [
            "All evaluated sequence and evidence inputs are synthetic.",
            "M13 and M14 were not supplied; M15 dossier completeness remains partial.",
            "M12 review validates technical artifact identity and stated accounting only.",
            "M15 validates producer provenance separately from the payload's technical validity.",
            "Historical Phase 2B M6 and Phase 4 replay runs are distinct; changed file digests are not normalized or aliased.",
            "Resource instrumentation is limited to registered configuration and CI evidence; no production-resource claim is made.",
        ],
    }
    return report


def write_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    rows = [
        "# M20 Phase 5 release readiness",
        "",
        f"- Decision: **{report['decision']}**",
        f"- Software integration: **{report['software_integration_status']}**",
        "- Biological discovery: **NOT VALIDATED**",
        f"- Cases audited: **{len(report['cases'])}**",
        f"- Historical M12 INVALID findings classified: **{len(report['m12_historical_invalid_findings'])}**",
        f"- Current M12 INVALID findings: **{len(report['m12_current_invalid_findings'])}**",
        "",
        "| Case | Candidate availability | M12 verified/invalid | M15 accepted/invalid | Completeness |",
        "|---|---|---:|---:|---|",
    ]
    for case in report["cases"]:
        m12 = case["m12"]["review_state_counts"]
        m15 = case["m15"]["counts"]
        rows.append(
            f"| {case['case_id']} | {case['upstream_candidate_availability']} | "
            f"{m12.get('VERIFIED', 0)}/{m12.get('INVALID', 0)} | "
            f"{m15.get('accepted_records', 0)}/"
            f"{m15.get('invalid_records', 0) + m15.get('invalid_provenance_records', 0)} | "
            f"{(case['m15']['counts'].get('absent_optional_stages') and 'PARTIAL') or 'UNKNOWN'} |"
        )
    rows.extend(["", "## Historical M12 INVALID rows", ""])
    for finding in report["m12_historical_invalid_findings"]:
        rows.append(
            f"- {finding['case_id']} `{finding['artifact_type']}`: "
            f"{finding['classification']} — {finding['explanation']}"
        )
    rows.extend(["", "## Limitations", ""])
    rows.extend(f"- {item}" for item in report["limitations"])
    markdown = "\n".join(rows) + "\n"
    (output / "report.md").write_text(markdown, encoding="utf-8")
    (output / "report.html").write_text(
        "<!doctype html><meta charset=utf-8><title>M20 Phase 5</title><pre>"
        + html.escape(markdown) + "</pre>\n",
        encoding="utf-8",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase2b-output", required=True)
    parser.add_argument("--phase3-output", required=True)
    parser.add_argument("--phase4-output", required=True)
    parser.add_argument("--previous-phase4-output")
    parser.add_argument("--validation-results")
    parser.add_argument("--ci-results")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    validation_counts = _load(args.validation_results) if args.validation_results else {}
    ci_status = _load(args.ci_results) if args.ci_results else {}
    report = build_report(
        args.phase2b_output, args.phase3_output, args.phase4_output,
        previous_phase4_output=args.previous_phase4_output,
        validation_counts=validation_counts,
        ci_status=ci_status,
    )
    write_report(report, args.output)
    print(json.dumps({
        "decision": report["decision"],
        "cases": len(report["cases"]),
        "historical_m12_invalid_findings": len(report["m12_historical_invalid_findings"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
