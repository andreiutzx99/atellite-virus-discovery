"""Synthetic-only M20 Phase 4 M12/M15 authenticated handoff runner."""

import argparse
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import shutil

from . import (
    artifact_contracts, artifact_workflow, m12_artifact_review, m12_contracts,
    m15_contracts, m20_phase2b, m20_phase3,
)

SCHEMA = "m20-phase4-report-v1"
EXTERNAL_EVIDENCE = {
    name: {"state": "NOT_SUPPLIED", "note": None}
    for name in m12_contracts.EXTERNAL_EVIDENCE_KEYS
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _safe_relative(value):
    if (not isinstance(value, str) or not value or "\\" in value
            or value.startswith("/") or ":" in value):
        raise ValueError("Producer output path is unsafe")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Producer output path is unsafe")
    return PurePosixPath(*parts)


def _workflow(root):
    path = Path(root) / "workflow.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Producer workflow manifest is missing: {path}")
    value = _read_json(path)
    if value.get("schema") != "artifact-workflow-manifest-v2":
        raise ValueError(f"Unsupported producer workflow manifest: {path}")
    return path, value


def _stage_row(workflow, stage_id, stage_kind=None):
    rows = [row for row in workflow.get("stages", [])
            if isinstance(row, dict) and row.get("id") == stage_id]
    if len(rows) != 1 or (stage_kind and rows[0].get("kind") != stage_kind):
        return None
    return rows[0]


def _validated_stage(root, row):
    root = Path(root).resolve(strict=True)
    relative = _safe_relative(row.get("output_path"))
    stage_root = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Producer output path contains a symlink")
    stage_root = stage_root.resolve(strict=True)
    if not stage_root.is_relative_to(root) or not stage_root.is_dir():
        raise ValueError("Producer output path escapes its workflow")
    manifest_path = stage_root / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Producer stage manifest is unavailable")
    raw = manifest_path.read_bytes()
    manifest = json.loads(raw.decode("utf-8"))
    digest = _sha(raw)
    if (row.get("stage_manifest_sha256") != digest
            or row.get("stage_manifest_identity") != manifest.get("identity")
            or row.get("status") != manifest.get("status")):
        raise ValueError("Producer workflow row and stage manifest disagree")
    return stage_root, manifest, digest


def _tree_inventory(root):
    root = Path(root)
    inventory = {}
    for current, dirs, files in os.walk(root):
        base = Path(current)
        for name in dirs:
            path = base / name
            if path.is_symlink():
                raise ValueError("Producer bundle contains a symlink")
            inventory[path.relative_to(root).as_posix()] = ("directory",)
        for name in files:
            path = base / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("Producer bundle contains an unsafe file")
            inventory[path.relative_to(root).as_posix()] = (
                "file", _sha(path.read_bytes()),
            )
    return inventory


def _copy_bundle(source_root, row, destination):
    source_root = Path(source_root).resolve(strict=True)
    workflow_path, workflow = _workflow(source_root)
    if not isinstance(workflow.get("workflow_id"), str):
        raise ValueError("Producer workflow ID is missing")
    stage_root, manifest, stage_digest = _validated_stage(source_root, row)
    relative = _safe_relative(row["output_path"])
    destination = Path(destination)
    target_stage = destination.joinpath(*relative.parts)
    if destination.exists():
        if (destination / "workflow.json").is_symlink() or not (
            destination / "workflow.json"
        ).is_file() or (destination / "workflow.json").read_bytes() != workflow_path.read_bytes():
            raise ValueError("Existing producer bundle has a changed workflow manifest")
        if target_stage.is_symlink() or not target_stage.is_dir():
            raise ValueError("Existing producer bundle has no verified stage output")
        if _tree_inventory(stage_root) != _tree_inventory(target_stage):
            raise ValueError("Existing producer bundle contents differ")
    else:
        destination.mkdir(parents=True)
        shutil.copyfile(workflow_path, destination / "workflow.json")
        target_stage.parent.mkdir(parents=True, exist_ok=True)
        for current, dirs, files in os.walk(stage_root):
            current_path = Path(current)
            for name in dirs + files:
                if (current_path / name).is_symlink():
                    raise ValueError("Producer bundle contains a symlink")
        shutil.copytree(stage_root, target_stage)
    copied = (target_stage / "manifest.json").read_bytes()
    if _sha(copied) != stage_digest or json.loads(copied) != manifest:
        raise ValueError("Producer bundle changed while being copied")
    return destination


def _artifact_records(root, row, allowed_types):
    stage_root, manifest, stage_digest = _validated_stage(root, row)
    outputs = row.get("artifacts")
    if not isinstance(outputs, dict):
        raise ValueError("Producer workflow row has no typed output inventory")
    records = []
    for name, descriptor in sorted(outputs.items()):
        if not isinstance(descriptor, dict):
            continue
        artifact_type = descriptor.get("artifact_type")
        if artifact_type not in allowed_types:
            continue
        relative = _safe_relative(name)
        path = stage_root.joinpath(*relative.parts)
        current = stage_root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"Producer artifact is a symlink: {name}")
        path = path.resolve(strict=True)
        if not path.is_relative_to(stage_root) or not path.is_file():
            raise ValueError(f"Producer artifact path is invalid: {name}")
        digest = _sha(path.read_bytes())
        if (descriptor.get("sha256") != digest
                or manifest.get("output_sha256", {}).get(name) != digest):
            raise ValueError(f"Producer artifact digest mismatch: {name}")
        artifact_contracts.validate_artifact(path, artifact_type)
        version = artifact_contracts.semantic_identity(
            {artifact_type})["contracts"][artifact_type]
        records.append({
            "name": name, "path": path, "artifact_type": artifact_type,
            "sha256": digest, "contract_version": version,
            "producer_contract_version": descriptor.get("contract_version"),
            "stage_manifest_sha256": stage_digest,
        })
    return records


def _m12_manifest(sample, workflow_root, workflow, m6_row, input_dir):
    if not m6_row or m6_row.get("status") != "complete":
        return None, "M6 producer is not complete"
    try:
        artifacts = _artifact_records(
            workflow_root, m6_row, m12_contracts.PRODUCER_TYPES["M6"])
        if not any(item["artifact_type"] == "residual_read_manifest"
                   for item in artifacts):
            return None, "M6 residual_read_manifest is missing"
        refs = [{
            "producer_milestone": "M6",
            "producer_stage_id": m6_row["id"],
            "producer_run_manifest_sha256": item["stage_manifest_sha256"],
            "producer_status": m6_row["status"],
            "artifact_type": item["artifact_type"],
            "relative_path": item["name"],
            "sha256": item["sha256"],
            "artifact_contract_version": item["contract_version"],
        } for item in artifacts]
        document = {
            "schema": m12_contracts.INPUT_SCHEMA,
            "candidate_id": sample,
            "producer_artifacts": refs,
            "external_evidence": EXTERNAL_EVIDENCE,
        }
        m12_contracts.validate_input_manifest(document)
        input_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = input_dir / f"{sample}.json"
        m12_contracts.write_json(manifest_path, document)
        stage_inputs = {
            "manifest": {
                "path": f"m12_workflow/m12_inputs/{sample}.json",
                "artifact_type": "m12_input_manifest",
            }
        }
        for index, item in enumerate(artifacts):
            stage_inputs[f"m6_{index:03d}"] = {
                "stage": m6_row["id"], "artifact": item["name"],
            }
        return (document, stage_inputs), None
    except (OSError, ValueError, KeyError, TypeError) as error:
        return None, f"{type(error).__name__}: {error}"


def _phase2b_spec(upstream):
    spec = m20_phase2b._workflow_spec()
    for stage in spec["stages"]:
        for value in stage.get("inputs", {}).values():
            if isinstance(value, dict) and "path" in value:
                value["path"] = str((Path(upstream) / value["path"]).resolve())
    return spec


def _copy_source_for_m12(phase2b_output, m12_root):
    if m12_root.exists():
        _workflow(m12_root)
    else:
        m12_root.mkdir(parents=True)


def _m15_ref(sample, milestone, source_root, row, record, bundle_root):
    workflow_path, workflow = _workflow(source_root)
    stage_kind = row.get("kind")
    if stage_kind != m15_contracts.expected_producer_stage_kind({
            "producer_milestone": milestone,
            "artifact_type": record["artifact_type"]}):
        raise ValueError("M15 producer stage kind is not allowlisted")
    relative = _safe_relative(row["output_path"])
    bundle_rel = bundle_root.relative_to(bundle_root.parents[1]).as_posix()
    stage_path = relative / PurePosixPath(*_safe_relative(record["name"]).parts)
    execution_ref = {
        "schema": "producer-execution-ref-v1",
        "producer_workflow_ref": {
            "path": "workflow.json",
            "sha256": _sha(workflow_path.read_bytes()),
            "workflow_id": workflow["workflow_id"],
        },
        "producer_stage_id": row["id"],
        "producer_stage_kind": stage_kind,
        "producer_stage_manifest_sha256": record["stage_manifest_sha256"],
    }
    ref = {
        "producer_milestone": milestone,
        "producer_stage_id": row["id"],
        "producer_run_manifest_sha256": record["stage_manifest_sha256"],
        "producer_status": row["status"],
        "artifact_type": record["artifact_type"],
        "artifact_contract_version": record["producer_contract_version"],
        "relative_path": record["name"],
        "sha256": record["sha256"],
        "provenance_mode": m15_contracts.AUTHENTICATED_PRODUCER_MODE,
        "producer_execution_ref": execution_ref,
        "producer_bundle_path": bundle_rel,
    }
    m15_contracts.validate_artifact_ref(ref, input_schema=m15_contracts.INPUT_SCHEMA)
    return ref, stage_path.as_posix()


def _m15_sources(sample, phase2b_output, phase3_output, m12_root, m12_workflow):
    sources = []
    phase2b = Path(phase2b_output)
    phase3 = Path(phase3_output)
    m6_workflow_root = phase2b / "stages/m4_m6"
    m6_workflow = _read_json(m6_workflow_root / "workflow.json")
    m6_row = _stage_row(m6_workflow, f"m6_{sample}", "residual_evidence")
    if m6_row:
        sources.append(("M6", m6_workflow_root, m6_row))
    m7_root = phase2b / "stages/m7"
    m7_workflow = _read_json(m7_root / "workflow.json")
    m7_row = next((row for row in m7_workflow.get("stages", [])
                   if isinstance(row, dict)
                   and row.get("kind") == "independent_recurrence"), None)
    if m7_row:
        sources.append(("M7", m7_root, m7_row))
    for milestone, subdir, stage_id, kind in (
        ("M8", "m8", "m8", "m8_homology"),
        ("M9", "m9_orf", "m9_orf", "m9_orf_translation"),
        ("M9", "m9_blastp", "m9_blastp", "m9_blastp"),
        ("M10", "m10", "m10", "m10_exact_first"),
    ):
        root = phase3 / "cases" / sample / subdir / "stages"
        if not (root / "workflow.json").is_file():
            continue
        workflow = _read_json(root / "workflow.json")
        row = _stage_row(workflow, stage_id, kind)
        if row:
            sources.append((milestone, root, row))
    m12_workflow_value = _read_json(Path(m12_root) / "workflow.json")
    m12_row = _stage_row(m12_workflow_value, f"m12_{sample}", "m12_artifact_review")
    if m12_row and m12_row.get("status") == "complete":
        sources.append(("M12", Path(m12_root), m12_row))
    return sources, m12_row


def _build_m15_case(sample, sources, m12_row, input_root):
    refs, input_rows, issues = [], [], []
    bundle_root = input_root / "bundles"
    bundle_root.mkdir(parents=True, exist_ok=True)
    for milestone, source_root, row in sources:
        allowed = m15_contracts.PRODUCER_TYPES.get(milestone, frozenset())
        try:
            records = _artifact_records(source_root, row, allowed)
            compatible = []
            for record in records:
                if record["artifact_type"] == "m10_candidate_accounting":
                    issues.append({
                        "producer_milestone": milestone,
                        "stage_id": row.get("id"),
                        "artifact_type": record["artifact_type"],
                        "state": "REJECTED",
                        "reason": "M15_PAYLOAD_SCHEMA_REJECTS_JSONL_ACCOUNTING",
                    })
                    continue
                ref_shape = {
                    "producer_milestone": milestone,
                    "artifact_type": record["artifact_type"],
                }
                expected_kind = m15_contracts.expected_producer_stage_kind(ref_shape)
                if row.get("kind") != expected_kind:
                    issues.append({
                        "producer_milestone": milestone,
                        "stage_id": row.get("id"),
                        "artifact_type": record["artifact_type"],
                        "state": "REJECTED",
                        "reason": "M15_PRODUCER_STAGE_KIND_NOT_ALLOWLISTED",
                    })
                    continue
                if record["producer_contract_version"] != artifact_contracts.CONTRACT_VERSION:
                    issues.append({
                        "producer_milestone": milestone,
                        "stage_id": row.get("id"),
                        "artifact_type": record["artifact_type"],
                        "state": "REJECTED",
                        "reason": "M15_PRODUCER_CONTRACT_VERSION_MISMATCH",
                        "producer_contract_version": record["producer_contract_version"],
                        "required_contract_version": artifact_contracts.CONTRACT_VERSION,
                    })
                    continue
                compatible.append(record)
            records = compatible
            if not records:
                issues.append({
                    "producer_milestone": milestone, "stage_id": row.get("id"),
                    "state": row.get("status"), "reason": "NO_ALLOWLISTED_VALID_OUTPUTS",
                })
                continue
            bundle_key = f"{sample}_{milestone.lower()}_{row['id']}"
            destination = bundle_root / bundle_key
            _copy_bundle(source_root, row, destination)
            for record in records:
                ref, relative_artifact = _m15_ref(
                    sample, milestone, source_root, row, record, destination,
                )
                refs.append(ref)
                input_rows.append({
                    "path": f"m15_inputs/bundles/{bundle_key}/{relative_artifact}",
                    "artifact_type": record["artifact_type"],
                })
        except (OSError, ValueError, KeyError, TypeError) as error:
            issues.append({
                "producer_milestone": milestone, "stage_id": row.get("id"),
                "state": row.get("status"),
                "reason": f"{type(error).__name__}: {error}",
            })
    states = {
        "M12": "PRESENT" if any(
            ref["producer_milestone"] == "M12" for ref in refs
        ) else "UNAVAILABLE",
        "M13": "NOT_SUPPLIED", "M14": "NOT_SUPPLIED",
    }
    document = {
        "schema": m15_contracts.INPUT_SCHEMA,
        "candidate_id": sample,
        "artifact_refs": refs,
        "optional_stage_states": states,
    }
    m15_contracts.validate_input_manifest(document)
    manifest_path = input_root / f"{sample}.json"
    m15_contracts.write_json(manifest_path, document)
    workflow_stage = {
        "id": f"m15_{sample}", "kind": "m15_evidence_dossier",
        "config": {},
        "inputs": {
            "manifest": {
                "path": f"m15_inputs/{sample}.json",
                "artifact_type": "m15_input_manifest",
            },
            **{f"artifact_{index:04d}": row
               for index, row in enumerate(input_rows)},
        },
    }
    return document, workflow_stage, issues


def _load_stage_outputs(workflow_root, row, expected):
    try:
        root, manifest, _ = _validated_stage(workflow_root, row)
        records = _artifact_records(workflow_root, row, set(expected))
        output = {}
        for item in records:
            output[item["artifact_type"]] = item
        missing = sorted(set(expected) - set(output))
        return output, missing, None
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {}, sorted(expected), f"{type(error).__name__}: {error}"


def _compare_m6_runs(original_workflow, replay_workflow, sample):
    stage_id = f"m6_{sample}"
    original = _stage_row(original_workflow, stage_id, "residual_evidence")
    replay = _stage_row(replay_workflow, stage_id, "residual_evidence")
    if not original or not replay:
        return {"identical_outputs": False, "reason": "M6_STAGE_UNAVAILABLE"}
    old = {
        name: {"artifact_type": item.get("artifact_type"), "sha256": item.get("sha256")}
        for name, item in original.get("artifacts", {}).items()
    }
    new = {
        name: {"artifact_type": item.get("artifact_type"), "sha256": item.get("sha256")}
        for name, item in replay.get("artifacts", {}).items()
    }
    changes = [{
        "artifact_path": name,
        "phase2b": old.get(name),
        "phase4_replay": new.get(name),
    } for name in sorted(set(old) | set(new)) if old.get(name) != new.get(name)]
    return {
        "phase2b_workflow_id": original_workflow.get("workflow_id"),
        "phase2b_stage_manifest_sha256": original.get("stage_manifest_sha256"),
        "phase2b_status": original.get("status"),
        "phase4_workflow_id": replay_workflow.get("workflow_id"),
        "phase4_stage_manifest_sha256": replay.get("stage_manifest_sha256"),
        "phase4_status": replay.get("status"),
        "identical_outputs": original.get("status") == replay.get("status") and not changes,
        "changed_artifacts": changes,
    }


def _case_result(sample, m12_root, m12_row, m15_root, m15_row, issues, m12_error):
    m12_data, m12_missing, m12_load_error = _load_stage_outputs(
        m12_root, m12_row, m12_artifact_review.OUTPUT_CONTRACTS.values(),
    ) if m12_row else (
        {}, list(m12_artifact_review.OUTPUT_CONTRACTS.values()), m12_error,
    )
    m12_table = None
    if "m12_artifact_review_table" in m12_data:
        m12_table = _read_json(m12_data["m12_artifact_review_table"]["path"])
    m12_counts = {}
    for row in m12_table or []:
        state = row.get("review_state", "UNKNOWN")
        m12_counts[state] = m12_counts.get(state, 0) + 1
    m12_bindings = [{
        "producer_milestone": row["artifact_ref"]["producer_milestone"],
        "producer_workflow_id": _read_json(m12_root / "workflow.json").get("workflow_id"),
        "producer_stage_id": row["artifact_ref"]["producer_stage_id"],
        "producer_run_manifest_sha256": row["artifact_ref"]["producer_run_manifest_sha256"],
        "artifact_type": row["artifact_ref"]["artifact_type"],
        "artifact_path": row["artifact_ref"]["relative_path"],
        "artifact_sha256": row["artifact_ref"]["sha256"],
        "review_state": row["review_state"],
    } for row in m12_table or []]
    m15_data, m15_missing, m15_load_error = _load_stage_outputs(
        m15_root, m15_row, m15_contracts.OUTPUT_CONTRACTS.values(),
    ) if m15_row else ({}, list(m15_contracts.OUTPUT_CONTRACTS.values()), "M15 did not run")
    m15_summary = None
    if "m15_dossier_summary" in m15_data:
        m15_summary = _read_json(m15_data["m15_dossier_summary"]["path"])
    m15_envelope = None
    if "m15_evidence_envelope" in m15_data:
        m15_envelope = _read_json(m15_data["m15_evidence_envelope"]["path"])
    m15_bindings = []
    for record in (m15_envelope or {}).get("records", []):
        ref = record.get("producer_ref", {})
        workflow_ref = ref.get("producer_execution_ref", {}).get(
            "producer_workflow_ref", {},
        )
        m15_bindings.append({
            "producer_milestone": ref.get("producer_milestone"),
            "producer_workflow_id": workflow_ref.get("workflow_id"),
            "producer_stage_id": ref.get("producer_stage_id"),
            "producer_run_manifest_sha256": ref.get("producer_run_manifest_sha256"),
            "artifact_type": ref.get("artifact_type"),
            "artifact_path": ref.get("relative_path"),
            "artifact_sha256": ref.get("sha256"),
            "validation_state": record.get("validation_state"),
            "producer_provenance_state": record.get("producer_provenance_state"),
            "reason_code": record.get("reason_code"),
        })
    return {
        "sample_id": sample,
        "m12": {
            "status": m12_row.get("status") if m12_row else "UNAVAILABLE",
            "workflow_id": (_read_json(m12_root / "workflow.json").get("workflow_id")),
            "error": m12_row.get("error") if m12_row else m12_error,
            "review_state_counts": m12_counts,
            "validated_producer_bindings": m12_bindings,
            "outputs": {name: item["sha256"] for name, item in m12_data.items()},
            "missing_outputs": m12_missing,
            "output_error": m12_load_error,
        },
        "m15": {
            "status": m15_row.get("status") if m15_row else "UNAVAILABLE",
            "error": m15_row.get("error") if m15_row else m15_load_error,
            "summary": m15_summary,
            "validated_producer_bindings": m15_bindings,
            "outputs": {name: item["sha256"] for name, item in m15_data.items()},
            "missing_outputs": m15_missing,
            "output_error": m15_load_error,
        },
        "rejected_or_missing_artifacts": issues,
    }


def _semantic_result_digest(cases, frozen_fixtures, phase3_report_sha256):
    semantic_cases = []
    for case in cases:
        summary = case["m15"].get("summary") or {}
        semantic_cases.append({
            "sample_id": case["sample_id"],
            "phase3_upstream_outcome": case["phase3_upstream_outcome"],
            "phase2b_m6_replay_comparison": {
                "identical_outputs": case["phase2b_m6_replay_comparison"].get(
                    "identical_outputs",
                ),
                "changed_artifact_paths": [
                    item["artifact_path"]
                    for item in case["phase2b_m6_replay_comparison"].get(
                        "changed_artifacts", [],
                    )
                ],
            },
            "m12": {
                "status": case["m12"]["status"],
                "review_state_counts": case["m12"]["review_state_counts"],
            },
            "m15": {
                "status": case["m15"]["status"],
                "result_completeness": summary.get("result_completeness"),
                "counts": summary.get("counts"),
            },
            "rejected_or_missing_artifacts": case["rejected_or_missing_artifacts"],
        })
    payload = {
        "schema": "m20-phase4-semantic-outcomes-v1",
        "frozen_fixtures": frozen_fixtures,
        "phase3_report_sha256": phase3_report_sha256,
        "cases": semantic_cases,
    }
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def run(output, phase2b_output, phase3_output, runner=None):
    output = Path(output).absolute()
    upstream = Path(phase2b_output).resolve(strict=True)
    phase3 = Path(phase3_output).resolve(strict=True)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("M20 Phase 4 output directory must be empty")
    baseline = _read_json(upstream / "report.json")
    phase2b_hash, truth_hash = m20_phase3._verify_frozen_phase2b(upstream, baseline)
    phase3_report = _read_json(phase3 / "report.json")
    if phase3_report.get("schema") != "m20-phase3-report-v1":
        raise ValueError("Phase 4 requires a Phase 3 v1 report")
    if (phase3_report.get("upstream", {}).get("phase2b_fixture_manifest_sha256")
            != phase2b_hash
            or phase3_report.get("upstream", {}).get("phase2b_truth_sha256")
            != truth_hash):
        raise ValueError("Phase 3 report is not bound to the supplied frozen Phase 2B run")
    samples = [row["sample_id"] for row in baseline["cases"]]
    phase3_cases = {row.get("sample_id"): row for row in phase3_report.get("cases", [])}
    if set(phase3_cases) != set(samples):
        raise ValueError("Phase 3 report case set differs from Phase 2B")

    m12_root = output / "m12_workflow"
    _copy_source_for_m12(upstream, m12_root)
    input_root = m12_root / "m12_inputs"
    phase2b_manifest = _read_json(upstream / "stages/m4_m6/workflow.json")
    base_spec = _phase2b_spec(upstream)
    spec_path = output / "m12_workflow_spec.json"
    spec_path.write_text(json.dumps(base_spec, sort_keys=True), encoding="utf-8")
    execute = runner or artifact_workflow.run
    registry = artifact_workflow.build_default_registry()
    execute(spec_path, m12_root, registry)
    base_workflow = _read_json(m12_root / "workflow.json")
    stage_by_sample = {}
    for sample in samples:
        m6_row = _stage_row(base_workflow, f"m6_{sample}", "residual_evidence")
        if m6_row:
            stage_by_sample[sample] = m6_row
    m12_errors = {}
    m12_stages = []
    for sample in samples:
        m6_row = stage_by_sample.get(sample)
        built, error = _m12_manifest(
            sample, m12_root, base_workflow,
            m6_row, input_root,
        )
        if error:
            m12_errors[sample] = error
            continue
        _, stage_inputs = built
        m12_stages.append({
            "id": f"m12_{sample}", "kind": "m12_artifact_review",
            "config": {}, "inputs": stage_inputs,
        })
    spec = {**base_spec, "stages": base_spec["stages"] + m12_stages}
    spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
    execute(spec_path, m12_root, registry)
    m12_manifest = _read_json(m12_root / "workflow.json")
    m15_root = output / "m15_workflow"
    m15_inputs = output / "m15_inputs"
    m15_stages, m15_issues_by_sample = [], {}
    m12_rows = {
        row["id"]: row for row in m12_manifest.get("stages", [])
        if isinstance(row, dict)
    }
    for sample in samples:
        sources, m12_row = _m15_sources(
            sample, upstream, phase3, m12_root, m12_manifest,
        )
        document, stage, issues = _build_m15_case(
            sample, sources, m12_row, m15_inputs,
        )
        m15_stages.append(stage)
        m15_issues_by_sample[sample] = issues
    m15_spec = {
        "schema": "artifact-workflow-v1",
        "stages": m15_stages,
    }
    m15_spec_path = output / "m15_workflow_spec.json"
    m15_spec_path.write_text(json.dumps(m15_spec, sort_keys=True), encoding="utf-8")
    execute(m15_spec_path, m15_root, registry)
    m15_manifest = _read_json(m15_root / "workflow.json")
    m15_rows = {
        row["id"]: row for row in m15_manifest.get("stages", [])
        if isinstance(row, dict)
    }
    cases = []
    for sample in samples:
        m12_row = m12_rows.get(f"m12_{sample}")
        m15_row = m15_rows.get(f"m15_{sample}")
        cases.append(_case_result(
            sample, m12_root, m12_row, m15_root, m15_row,
            m15_issues_by_sample[sample], m12_errors.get(sample),
        ))
        cases[-1]["phase3_upstream_outcome"] = phase3_cases[sample]
        cases[-1]["phase2b_m6_replay_comparison"] = _compare_m6_runs(
            phase2b_manifest, m12_manifest, sample,
        )
    report = {
        "schema": SCHEMA,
        "status": (
            "COMPLETE" if all(row["m15"]["status"] == "complete" for row in cases)
            else "INCOMPLETE"
        ),
        "frozen_fixtures": {
            "phase1_manifest_sha256": baseline["fixtures"]["phase1_baseline"]["manifest_sha256"],
            "phase1_truth_sha256": baseline["fixtures"]["phase1_baseline"]["heldout_truth_sha256"],
            "phase2b_manifest_sha256": phase2b_hash,
            "phase2b_truth_sha256": truth_hash,
        },
        "phase3_report_sha256": _sha((phase3 / "report.json").read_bytes()),
        "phase4_m12_workflow_id": m12_manifest.get("workflow_id"),
        "phase4_m15_workflow_id": m15_manifest.get("workflow_id"),
        "cases": cases,
        "deterministic_semantic_outcomes_sha256": _semantic_result_digest(
            cases,
            {
                "phase1_manifest_sha256": baseline["fixtures"]["phase1_baseline"]["manifest_sha256"],
                "phase1_truth_sha256": baseline["fixtures"]["phase1_baseline"]["heldout_truth_sha256"],
                "phase2b_manifest_sha256": phase2b_hash,
                "phase2b_truth_sha256": truth_hash,
            },
            _sha((phase3 / "report.json").read_bytes()),
        ),
        "limitations": [
            "All inputs are deterministic synthetic fixtures and prior M20 synthetic outputs.",
            "M12 reviews only allowlisted M6 artifacts; it does not assess external evidence or biological claims.",
            "M15 authenticates artifact lineage and reports dossier completeness; it does not classify or interpret biology.",
            "M12's same-workflow requirement uses a fresh Phase 4 M4/M6 run; its artifact digests are compared with, but are not substituted for, the frozen Phase 2B M6 run supplied separately to M15.",
            "Missing M8/M9 optional outputs retain their upstream unavailable or incomplete state.",
            "M15 does not consume the M10 JSONL candidate-accounting table; the existing parser rejects that payload format.",
        ],
    }
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
                           encoding="utf-8")
    rows = ["# M20 Phase 4 synthetic M12/M15 handoffs", "",
            f"- Overall state: **{report['status']}**",
            f"- Phase 2B fixtures: `{phase2b_hash}` / truth `{truth_hash}`", "",
            "| Case | M12 | Verified / invalid | M15 | Accepted / invalid | Completeness |",
            "|---|---|---:|---|---:|---|"]
    for case in cases:
        summary = case["m15"]["summary"] or {}
        m12_states = case["m12"]["review_state_counts"]
        m15_counts = summary.get("counts", {})
        rows.append(
            f"| {case['sample_id']} | {case['m12']['status']} | "
            f"{m12_states.get('VERIFIED', 0)} / {m12_states.get('INVALID', 0)} | "
            f"{case['m15']['status']} | "
            f"{m15_counts.get('accepted_records', 0)} / "
            f"{m15_counts.get('invalid_records', 0) + m15_counts.get('invalid_provenance_records', 0)} | "
            f"{summary.get('result_completeness', 'UNKNOWN')} |"
        )
        upstream = case["phase3_upstream_outcome"]
        rows.extend([
            "",
            f"## {case['sample_id']}",
            f"- Phase 3 candidate availability: `{upstream.get('candidate_availability', 'UNKNOWN')}`",
            "- Phase 3 stages: " + ", ".join(
                f"{name}=`{(upstream.get(name) or {}).get('analysis_status', (upstream.get(name) or {}).get('status', 'UNKNOWN'))}`"
                for name in ("m8", "m9_orf", "m9_blastp", "m10")
            ),
            f"- M12 workflow: `{case['m12']['workflow_id']}`; review states: "
            f"`{json.dumps(case['m12']['review_state_counts'], sort_keys=True)}`",
            f"- M15 workflow: `{report['phase4_m15_workflow_id']}`; missing optional stages: "
            f"`{', '.join((summary.get('counts') or {}).get('absent_optional_stages', []))}`",
            f"- Phase 4 M6 replay matches frozen Phase 2B outputs: "
            f"`{case['phase2b_m6_replay_comparison']['identical_outputs']}`; "
            f"changed output files: `{len(case['phase2b_m6_replay_comparison']['changed_artifacts'])}`.",
            "- M12 source bindings:",
        ])
        for binding in case["m12"]["validated_producer_bindings"]:
            rows.append(
                f"  - {binding['producer_milestone']}/{binding['producer_stage_id']} "
                f"workflow `{binding['producer_workflow_id']}`, run "
                f"`{binding['producer_run_manifest_sha256']}`; "
                f"{binding['artifact_type']} `{binding['artifact_path']}` "
                f"sha256 `{binding['artifact_sha256']}` — {binding['review_state']}."
            )
        rows.append("- M15 authenticated bindings:")
        for binding in case["m15"]["validated_producer_bindings"]:
            rows.append(
                f"  - {binding['producer_milestone']}/{binding['producer_stage_id']} "
                f"workflow `{binding['producer_workflow_id']}`, run "
                f"`{binding['producer_run_manifest_sha256']}`; "
                f"{binding['artifact_type']} `{binding['artifact_path']}` "
                f"sha256 `{binding['artifact_sha256']}` — "
                f"{binding['validation_state']} ({binding['reason_code'] or 'no error'})."
            )
        rows.append("- Rejected or missing artifacts:")
        if case["rejected_or_missing_artifacts"]:
            rows.extend(
                f"  - `{json.dumps(item, sort_keys=True)}`"
                for item in case["rejected_or_missing_artifacts"]
            )
        else:
            rows.append("  - None.")
    rows.extend(["", "All source sequences are synthetic. M12/M15 results describe "
                 "artifact review, provenance, and completeness only.", ""])
    markdown = "\n".join(rows)
    (output / "report.md").write_text(markdown, encoding="utf-8")
    (output / "report.html").write_text(
        "<!doctype html><meta charset=utf-8><title>M20 Phase 4</title><pre>"
        + html.escape(markdown) + "</pre>\n", encoding="utf-8",
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase2b-output", required=True)
    parser.add_argument("--phase3-output", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output, args.phase2b_output, args.phase3_output),
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
