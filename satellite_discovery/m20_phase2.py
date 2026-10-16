"""Opt-in registered M4 QC -> M6 residual evidence -> M7 recurrence run."""

import argparse
import html
import json
from pathlib import Path

from . import artifact_workflow, independent_recurrence, m20_phase1


QC_CONFIG = {
    "min_length": 30, "end_quality": 20, "min_mean_quality": 20,
    "max_n_fraction": 0.05, "adapters": [], "min_adapter_overlap": 12,
}
M6_CONFIG = {
    "layout": "single-end", "assembly_enabled": True, "assembler": "spades",
    "threads": 1, "memory_mb": 2048,
    "triage": {
        "min_read_length": 50, "max_ambiguous_fraction": 0.05,
        "min_entropy_bits": 1.2, "min_mean_phred": 20,
    },
    "support": {
        "min_mapq": 20, "min_alignment_fraction": 0.8,
        "min_sequence_identity": 0.95, "min_coverage_breadth": 0.8,
        "min_mean_depth": 2, "min_distinct_fragments": 2,
        "coverage_window_size": 100,
    },
}
M7_FILES = tuple(independent_recurrence.OUTPUT_CONTRACTS)


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _stage_ref(stage, artifact):
    return {"stage": stage, "artifact": artifact}


def build_m4_m6_workflow_spec():
    stages = []
    for sample in m20_phase1.SAMPLE_IDS:
        qc_id, m6_id = f"qc_{sample}", f"m6_{sample}"
        folder = f"inputs/{sample}"
        stages.extend([
            {
                "id": qc_id, "kind": "fastq_qc", "config": QC_CONFIG,
                "inputs": {"read1": {
                    "path": f"{folder}/reads.fastq.gz", "artifact_type": "raw_read",
                }},
            },
            {
                "id": m6_id, "kind": "residual_evidence",
                "config": {**M6_CONFIG, "sample_id": sample},
                "inputs": {
                    "read1": _stage_ref(qc_id, "clean_single.fastq.gz"),
                    "qc_manifest": _stage_ref(qc_id, "qc.json"),
                    "reference": {
                        "path": f"{folder}/reference.fasta", "artifact_type": "raw_fasta",
                    },
                    "roles": {
                        "path": f"{folder}/reference_roles.csv",
                        "artifact_type": "reference_roles",
                    },
                },
            },
        ])
    spec = {"schema": "artifact-workflow-v1", "stages": stages}
    _assert_truth_free(spec)
    return spec


def _assert_truth_free(spec):
    encoded = _json_bytes(spec).decode().lower()
    if any(secret in encoded for secret in (
        "heldout_truth", "candidate_sequence", "expected_role", "shared_candidate",
    )):
        raise ValueError("Held-out truth or expected labels entered the analysis graph")


def _m7_artifact_path(output, m6_root, m6_row, filename, artifact_type):
    stage_dir = _stage_dir(m6_root, m6_row)
    if stage_dir is None:
        return None
    path = stage_dir / filename
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(stage_dir):
        return None
    manifest = _json_at(stage_dir, "manifest.json")
    inventory = manifest.get("output_inventory", []) if isinstance(manifest, dict) else []
    contracts = manifest.get("output_contract", {}) if isinstance(manifest, dict) else {}
    record = next(
        (item for item in inventory if isinstance(item, dict) and item.get("path") == filename),
        None,
    )
    if not isinstance(contracts, dict) or not record or contracts.get(filename) != artifact_type:
        return None
    import hashlib
    if hashlib.sha256(path.read_bytes()).hexdigest() != record.get("sha256"):
        return None
    return path.resolve().relative_to(Path(output).resolve()).as_posix()


def build_m7_workflow_spec(output, m6_manifest, m6_root):
    observations = []
    inputs = {}
    rows = {
        row.get("id"): row for row in m6_manifest.get("stages", [])
        if isinstance(row, dict)
    }
    for sample in m20_phase1.SAMPLE_IDS:
        stage_id = f"m6_{sample}"
        row = rows.get(stage_id)
        evidence_path = _m7_artifact_path(
            output, m6_root, row, "reconstruction_evidence.json", "reconstruction_evidence",
        )
        residual_path = _m7_artifact_path(
            output, m6_root, row, "residual_manifest.json", "residual_read_manifest",
        )
        evidence = _json_at(_stage_dir(m6_root, row), "reconstruction_evidence.json")
        contigs_path = _m7_artifact_path(
            output, m6_root, row, "supported_contigs.fasta", "canonical_contig_fasta",
        )
        available = (
            _status(row) == "COMPLETE" and evidence_path is not None
            and residual_path is not None and evidence is not None
        )
        m6_state = "available" if available else (
            "unavailable" if _status(row) in {"UNAVAILABLE", "BLOCKED"} else "failed"
        )
        observation = {
            "observation_id": f"obs_{sample}",
            "candidate_id": None,
            "sample_id": sample,
            "sequencing_run_id": f"run_{sample}",
            "study_id": f"study_{sample}",
            "source_artifact_id": None,
            "upstream_workflow_id": m6_manifest.get("workflow_id"),
            "molecule_type": "DNA",
            "m6_state": m6_state,
        }
        if available:
            import hashlib
            evidence_name, residual_name = f"evidence_{sample}", f"residual_{sample}"
            evidence_digest = hashlib.sha256(
                (Path(output) / evidence_path).read_bytes()
            ).hexdigest()
            observation.update({
                "evidence_input": evidence_name,
                "residual_manifest_input": residual_name,
                "source_artifact_id": f"{stage_id}:reconstruction_evidence:{evidence_digest}",
            })
            inputs[evidence_name] = {
                "path": evidence_path, "artifact_type": "reconstruction_evidence",
            }
            inputs[residual_name] = {
                "path": residual_path, "artifact_type": "residual_read_manifest",
            }
            if contigs_path is not None:
                contigs_name = f"contigs_{sample}"
                observation["contigs_input"] = contigs_name
                inputs[contigs_name] = {
                    "path": contigs_path, "artifact_type": "canonical_contig_fasta",
                }
            elif evidence.get("status") == "READ_SUPPORTED_ASSEMBLY":
                observation.update({
                    "m6_state": "failed",
                    "upstream_status": "INVALID_OUTPUT",
                    "upstream_reason": "M6 reports a read-supported assembly but the typed contig output is missing.",
                })
                observation.pop("evidence_input", None)
                observation.pop("residual_manifest_input", None)
                inputs.pop(f"evidence_{sample}", None)
                inputs.pop(f"residual_{sample}", None)
        else:
            invalid_completed_output = _status(row) == "COMPLETE"
            observation.update({
                "upstream_status": (
                    "INVALID_OUTPUT" if invalid_completed_output else
                    row.get("status", "unavailable") if isinstance(row, dict)
                    else "missing_m6_stage"
                ),
                "upstream_reason": (
                    "M6 completed, but required outputs were missing, unsafe, or digest-invalid."
                    if invalid_completed_output else
                    row.get("reason") or row.get("failure_reason")
                    if isinstance(row, dict) else "M6 stage is absent from its execution manifest."
                ),
            })
        observations.append(observation)
    spec = {
        "schema": "artifact-workflow-v1",
        "stages": [{
            "id": "m7_recurrence",
            "kind": "independent_recurrence",
            "config": {
                "observations": observations,
                "orientation_policy": "reverse_complement_invariant",
            },
            "inputs": inputs,
        }],
    }
    _assert_truth_free(spec)
    return spec


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _status(row):
    if not isinstance(row, dict):
        return "UNAVAILABLE"
    return {
        "complete": "COMPLETE",
        "blocked": "BLOCKED",
        "dependency_missing": "UNAVAILABLE",
        "unavailable": "UNAVAILABLE",
        "interrupted": "INCOMPLETE",
    }.get(row.get("status"), "INCOMPLETE")


def _stage_dir(workflow_root, row):
    if not isinstance(row, dict) or not isinstance(row.get("output_path"), str):
        return None
    root = Path(workflow_root).resolve()
    relative = Path(row["output_path"])
    unresolved = root / relative
    resolved = unresolved.resolve()
    if (relative.is_absolute() or ".." in relative.parts or unresolved.is_symlink()
            or not resolved.is_relative_to(root)):
        return None
    return resolved


def _json_at(stage_dir, name):
    path = stage_dir / name if stage_dir else None
    if (path is None or path.is_symlink() or not path.is_file()
            or not path.resolve().is_relative_to(stage_dir.resolve())):
        return None
    try:
        return _read_json(path)
    except (OSError, ValueError, TypeError):
        return None


def _safe_manifest(path, before):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        return {"schema": "artifact-workflow-manifest-v2", "status": "unavailable", "stages": []}, {
            "type": "WorkflowManifestUnavailable",
            "message": "M4 did not produce a readable workflow manifest.",
        }
    import hashlib
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if before is not None and digest == before:
        return {"schema": "artifact-workflow-manifest-v2", "status": "incomplete", "stages": []}, {
            "type": "StaleWorkflowManifest",
            "message": "The previous workflow manifest was unchanged after execution.",
        }
    try:
        data = _read_json(path)
        if not isinstance(data, dict) or not isinstance(data.get("stages"), list):
            raise ValueError("invalid workflow manifest shape")
        return data, None
    except (OSError, ValueError, TypeError) as error:
        return {"schema": "artifact-workflow-manifest-v2", "status": "incomplete", "stages": []}, {
            "type": type(error).__name__, "message": str(error),
        }


def _candidate_sequences(candidate_set, stage_dir):
    if not isinstance(candidate_set, dict):
        return None
    availability = candidate_set.get("availability")
    if not isinstance(availability, dict) or availability.get("state") != "AVAILABLE":
        return None
    reference = availability.get("fasta_artifact")
    if not isinstance(reference, dict) or not isinstance(reference.get("path"), str):
        return None
    relative = Path(reference["path"])
    if relative.is_absolute() or ".." in relative.parts:
        return None
    fasta = stage_dir / relative if stage_dir else None
    if (fasta is None or fasta.is_symlink() or not fasta.is_file()
            or not fasta.resolve().is_relative_to(stage_dir.resolve())):
        return None
    import hashlib
    data = fasta.read_bytes()
    if hashlib.sha256(data).hexdigest() != reference.get("sha256"):
        return None
    manifest = _json_at(stage_dir, "manifest.json")
    inventory = manifest.get("output_inventory", []) if isinstance(manifest, dict) else []
    contracts = manifest.get("output_contract", {}) if isinstance(manifest, dict) else {}
    output_record = next(
        (item for item in inventory if isinstance(item, dict)
         and item.get("path") == relative.as_posix()),
        None,
    )
    if (not isinstance(contracts, dict) or not output_record
            or contracts.get(relative.as_posix()) != "canonical_contig_fasta"
            or output_record.get("sha256") != reference.get("sha256")):
        return None
    records = []
    headers = []
    current = []
    saw_header = False
    for line in data.decode("ascii").splitlines():
        if line.startswith(">"):
            if current:
                records.append("".join(current))
            headers.append(line[1:].split()[0])
            current = []
            saw_header = True
        elif line.strip():
            if not saw_header:
                return None
            current.append(line.strip())
    if current:
        records.append("".join(current))
    metadata = candidate_set.get("records")
    if (not isinstance(metadata, list) or len(records) != len(metadata)
            or len(records) != availability.get("record_count")):
        return None
    import hashlib
    for header, sequence, row in zip(headers, records, metadata):
        if (not isinstance(row, dict) or header != row.get("fasta_record_id")
                or hashlib.sha256(sequence.encode("ascii")).hexdigest()
                != row.get("sequence_sha256")):
            return None
    return records


def _stage_provenance(row, stage_dir):
    if not isinstance(row, dict):
        return {"status": "UNAVAILABLE"}
    stage_manifest = _json_at(stage_dir, "manifest.json")
    return {
        "stage_id": row.get("id"),
        "stage_kind": row.get("kind"),
        "status": row.get("status"),
        "output_path": row.get("output_path"),
        "cache_key": row.get("cache_key"),
        "input_digests": {
            name: item.get("sha256")
            for name, item in sorted((row.get("inputs") or {}).items())
            if isinstance(item, dict)
        },
        "output_manifest_sha256": (
            __import__("hashlib").sha256((stage_dir / "manifest.json").read_bytes()).hexdigest()
            if stage_dir and (stage_dir / "manifest.json").is_file()
            and not (stage_dir / "manifest.json").is_symlink() else None
        ),
        "output_artifacts": (
            stage_manifest.get("output_inventory", [])
            if isinstance(stage_manifest, dict) else []
        ),
    }


def _render_markdown(report):
    lines = [
        "# M20 Phase 2 synthetic M4–M7 report", "",
        f"- Overall: **{report['status']}**",
        f"- M4/M6 workflow: `{report['workflow_status']['m4_m6']}`",
        f"- M7 workflow: `{report['workflow_status']['m7']}`",
        "- Inputs: deterministic M20 Phase 1 synthetic fixtures only.",
        "- Truth comparison was performed after registered stage execution.",
        "", "## Per-sample results", "",
        "| Sample | QC | M6 stage | Candidate availability | Candidate count | Read-back | M7 status | Exact recovery |",
        "|---|---|---|---|---:|---|---|---|",
    ]
    for row in report["samples"]:
        lines.append(
            f"| {row['sample_id']} | {row['qc_status']} | {row['m6_status']} | "
            f"{row['candidate_availability']} | {row['candidate_count']} | {row['read_back_status']} | "
            f"{row['m7_observation']['recurrence_status']} | "
            f"{row['exact_sequence_recovery']} |"
        )
    lines.extend([
        "", "## M7 recurrence", "",
        f"- Status: **{report['m7']['status']}**",
        f"- Recurrence: `{report['m7'].get('recurrence_status', 'NOT_EVALUATED')}`",
        f"- Exact groups: {report['m7'].get('exact_group_count')}; recurrent groups: "
        f"{report['m7'].get('recurrent_group_count')}; supported observations: "
        f"{report['m7'].get('supported_sequence_observation_count')}.",
        "", "## Limitations", "",
        "These are software-contract observations on artificial reads, not evidence "
        "of biological identity, absence, novelty, function, helper dependence, or "
        "satellite classification. A negative-control zero is not proof of biological absence.",
        "",
    ])
    return "\n".join(lines)


def _write_reports(output, report):
    output = Path(output)
    (output / "report.json").write_bytes(_json_bytes(report))
    markdown = _render_markdown(report)
    (output / "report.md").write_text(markdown, encoding="utf-8")
    escaped = html.escape(markdown)
    (output / "report.html").write_text(
        "<!doctype html><meta charset=\"utf-8\"><title>M20 Phase 2</title>"
        "<style>body{font:16px/1.55 system-ui;max-width:1000px;margin:40px auto;padding:0 20px}"
        "pre{white-space:pre-wrap}</style><pre>" + escaped + "</pre>\n",
        encoding="utf-8",
    )


def run(output, runner=None):
    output = Path(output).absolute()
    m20_phase1._reject_symlink_ancestors(output)
    output.mkdir(parents=True, exist_ok=True)
    fixture_root = output
    fixture_digests = m20_phase1.generate_fixtures(fixture_root)
    run_workflow = runner or artifact_workflow.run
    registry = artifact_workflow.build_default_registry()

    m6_spec = build_m4_m6_workflow_spec()
    m6_spec_path = output / "m4-m6-workflow.json"
    m6_spec_path.write_bytes(_json_bytes(m6_spec))
    m6_root = output / "stages/m4_m6"
    m6_manifest_path = m6_root / "workflow.json"
    m6_before = _manifest_digest(m6_manifest_path)
    m6_error = _execute_workflow(run_workflow, m6_spec_path, m6_root, registry)
    m6_manifest, m6_stale_error = _safe_manifest(m6_manifest_path, m6_before)
    m6_error = m6_error or m6_stale_error

    m7_spec = build_m7_workflow_spec(output, m6_manifest, m6_root)
    m7_spec_path = output / "m7-workflow.json"
    m7_spec_path.write_bytes(_json_bytes(m7_spec))
    m7_root = output / "stages/m7"
    m7_manifest_path = m7_root / "workflow.json"
    m7_before = _manifest_digest(m7_manifest_path)
    m7_error = _execute_workflow(run_workflow, m7_spec_path, m7_root, registry)
    m7_manifest, m7_stale_error = _safe_manifest(m7_manifest_path, m7_before)
    m7_error = m7_error or m7_stale_error

    fixture_after = m20_phase1.verify_fixtures(fixture_root)
    fixtures_unchanged = fixture_digests == fixture_after
    truth = _read_json(fixture_root / "heldout_truth.json")
    truth_by_sample = {row["sample_id"]: row for row in truth["cases"]}
    rows = {row.get("id"): row for row in m6_manifest["stages"] if isinstance(row, dict)}
    m7_rows = {row.get("id"): row for row in m7_manifest["stages"] if isinstance(row, dict)}

    sample_reports = []
    for sample in m20_phase1.SAMPLE_IDS:
        qc_row = rows.get(f"qc_{sample}")
        m6_row = rows.get(f"m6_{sample}")
        m6_dir = _stage_dir(m6_root, m6_row)
        evidence = _json_at(m6_dir, "reconstruction_evidence.json")
        candidates = _json_at(m6_dir, "candidate_sequence_set.json")
        support = _json_at(m6_dir, "read_support.json")
        recon_status = evidence.get("status") if evidence else None
        support_status = support.get("status") if support else None
        observed = _candidate_sequences(candidates, m6_dir)
        candidate_availability = (
            candidates.get("availability", {}).get("state", "NOT_EVALUATED")
            if isinstance(candidates, dict) else "NOT_EVALUATED"
        )
        if candidate_availability == "AVAILABLE" and observed is None:
            candidate_availability = "INCOMPLETE"
        expected = truth_by_sample[sample]
        recovery = (
            ("RECOVERED" if expected["candidate_sequence"] in observed else "NOT_RECOVERED")
            if _status(m6_row) == "COMPLETE" and observed is not None
            else "NOT_EVALUATED"
        ) if expected["candidate_sequence"] else "NOT_APPLICABLE"
        sample_reports.append({
            "sample_id": sample,
            "sequencing_run_id": f"run_{sample}",
            "study_id": f"study_{sample}",
            "qc_status": _status(qc_row),
            "m6_status": _status(m6_row),
            "candidate_availability": candidate_availability,
            "candidate_count": len(observed) if observed is not None else None,
            "read_back_status": support_status or recon_status or "NOT_EVALUATED",
            "exact_sequence_recovery": recovery,
            "m6_reconstruction_status": recon_status or "NOT_EVALUATED",
            "m6_support_status": support_status or "NOT_EVALUATED",
            "stage_provenance": {
                "qc": _stage_provenance(qc_row, _stage_dir(m6_root, qc_row)),
                "m6": _stage_provenance(m6_row, m6_dir),
            },
            "truth_evaluation": {
                "expected_role": expected["expected_role"],
                "candidate_sequence_recovery": recovery,
                "negative_control_predictions": (
                    ("ZERO_PREDICTIONS" if not observed else "CANDIDATES_DETECTED")
                    if _status(m6_row) == "COMPLETE" and observed is not None
                    else "NOT_EVALUATED"
                ) if expected["candidate_sequence"] is None else None,
            },
        })
    m7_row = m7_rows.get("m7_recurrence")
    m7_dir = _stage_dir(m7_root, m7_row)
    m7_observation_doc = _json_at(m7_dir, "observations.json")
    m7_exact = _json_at(m7_dir, "exact_recurrence.json")
    m7_summary = _json_at(m7_dir, "recurrence_summary.json")
    m7_observations = {
        row.get("sample_id"): row for row in (
            m7_observation_doc.get("observations", [])
            if isinstance(m7_observation_doc, dict) else []
        ) if isinstance(row, dict)
    }
    recurrent_samples = set()
    exact_groups = m7_exact.get("groups", []) if isinstance(m7_exact, dict) else []
    for group in exact_groups:
        members = group.get("members", []) if isinstance(group, dict) else []
        if len({row.get("observation_id") for row in members if isinstance(row, dict)}) > 1:
            recurrent_samples.update(
                row.get("sample_id") for row in members if isinstance(row, dict)
            )
    for sample_report in sample_reports:
        observation = m7_observations.get(sample_report["sample_id"])
        contig_count = (
            len(observation.get("contigs", []))
            if observation and isinstance(observation.get("contigs"), list) else 0
        )
        is_recurrent = sample_report["sample_id"] in recurrent_samples
        sample_report["m7_observation"] = (
            {
                "m6_evidence_status": observation.get("m6_status", "NOT_EVALUATED"),
                "recurrence_status": (
                    "RECURRENT" if is_recurrent else
                    "NO_RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS"
                    if contig_count else "NOT_EVALUATED"
                ),
                "evidence_class": observation.get("evidence_class", "NOT_EVALUATED"),
                "contig_count": contig_count,
                "residual_counts": observation.get("residual_counts"),
                "in_recurrent_exact_group": is_recurrent,
            }
            if observation else {
                "m6_evidence_status": "NOT_EVALUATED",
                "recurrence_status": "NOT_EVALUATED",
                "evidence_class": "NOT_EVALUATED",
                "contig_count": None,
                "residual_counts": None,
                "in_recurrent_exact_group": False,
            }
        )
    report = {
        "schema": "m20-phase2-report-v1",
        "status": "COMPLETE" if all(
            row["qc_status"] == "COMPLETE" and row["m6_status"] == "COMPLETE"
            for row in sample_reports
        ) and _status(m7_row) == "COMPLETE" and fixtures_unchanged else "INCOMPLETE",
        "workflow_status": {
            "m4_m6": m6_manifest.get("status", "unavailable"),
            "m7": m7_manifest.get("status", "unavailable"),
        },
        "workflow_ids": {
            "m4_m6": m6_manifest.get("workflow_id"),
            "m7": m7_manifest.get("workflow_id"),
        },
        "execution_error": {"m4_m6": m6_error, "m7": m7_error},
        "fixtures": {
            **fixture_digests,
            "unchanged_after_execution": fixtures_unchanged,
            "truth_sidecar_outside_analysis_inputs": True,
        },
        "samples": sample_reports,
        "m7": {
            "status": _status(m7_row),
            "recurrence_status": (
                m7_summary.get("result_status")
                if isinstance(m7_summary, dict) else "NOT_EVALUATED"
            ),
            "exact_group_count": (
                m7_summary.get("exact_group_count") if isinstance(m7_summary, dict) else None
            ),
            "recurrent_group_count": (
                m7_summary.get("recurrent_group_count")
                if isinstance(m7_summary, dict) else None
            ),
            "supported_sequence_observation_count": (
                m7_summary.get("supported_sequence_observation_count")
                if isinstance(m7_summary, dict) else None
            ),
            "provenance": _stage_provenance(m7_row, m7_dir),
        },
        "limitations": [
            "Synthetic software evaluation only; no biological inference.",
            "Zero predictions in the negative control do not establish biological absence.",
            "The M7 recurrence result reflects only the declared synthetic observations.",
        ],
    }
    _write_reports(output, report)
    return report


def _manifest_digest(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        return None
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execute_workflow(runner, spec_path, stages_root, registry):
    try:
        runner(spec_path, stages_root, registry)
    except Exception as error:
        return {"type": type(error).__name__, "message": str(error)}
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Dedicated M20 Phase 2 output directory")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
