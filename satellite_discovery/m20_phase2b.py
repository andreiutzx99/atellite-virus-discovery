"""Versioned, synthetic-only M20 Phase 2B assembler-recovery benchmark."""

import gzip
import hashlib
from io import BytesIO
import json
import random
import platform
from pathlib import Path
import argparse
import sys
import tempfile

from . import artifact_workflow, m20_phase1, m20_phase2


SCHEMA = "m20-phase2b-synthetic-benchmark-v2"
SEED = 20261116
GENERATOR_VERSION = "m20-phase2b-generator-v2"
READ_LENGTH = 100
SEQUENCE_LENGTH = 400
SAMPLING = ("random_start", "stratified_start")
COVERAGES = (10, 30)
REPLICATES = (1, 2)
NEGATIVE_CONTROLS = 2
M6_CONFIG = {
    **m20_phase2.M6_CONFIG,
}
MAX_READS_PER_CASE = 120


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _random_sequence(seed, length=SEQUENCE_LENGTH):
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(length))


def _fastq(sequence, seed, coverage, strategy):
    count = (coverage * len(sequence) + READ_LENGTH - 1) // READ_LENGTH
    if count > MAX_READS_PER_CASE:
        raise ValueError("Prespecified case exceeds the read-count resource bound")
    rng = random.Random(seed)
    reads = []
    for index in range(count):
        if strategy == "random_start":
            start = rng.randrange(len(sequence) - READ_LENGTH + 1)
        elif strategy == "stratified_start":
            span = len(sequence) - READ_LENGTH + 1
            start = min(span - 1, (index * span // count) + rng.randrange(max(1, span // count)))
        else:
            raise ValueError(f"Unsupported read sampling strategy: {strategy}")
        reads.append((f"r{index + 1:04d}", sequence[start:start + READ_LENGTH]))
    text = "".join(f"@{name}\n{seq}\n+\n{'I' * READ_LENGTH}\n" for name, seq in reads).encode("ascii")
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0, compresslevel=9) as out:
        out.write(text)
    return buffer.getvalue()


def _expected_files():
    candidate = _random_sequence(SEED)
    files, cases, truths, pairs = {}, [], [], []
    case_index = 0
    for strategy in SAMPLING:
        for coverage in COVERAGES:
            pair_id = f"p{len(pairs) + 1:02d}"
            pair_members = []
            for replicate in REPLICATES:
                case_index += 1
                sample_id = f"c{case_index:03d}"
                read_seed = SEED + 1000 + case_index
                sequence = candidate
                reads = _fastq(sequence, read_seed, coverage, strategy)
                decoy = _random_sequence(SEED + 5000 + case_index)
                files[f"{sample_id}/reads.fastq.gz"] = reads
                files[f"{sample_id}/reference.fasta"] = f">ref01\n{decoy}\n".encode("ascii")
                files[f"{sample_id}/reference_roles.csv"] = (
                    "reference_id,reference_role,reference_source,reference_version\n"
                    "ref01,technical_reference,m20-synthetic,M20-phase2b-v2\n"
                ).encode("ascii")
                cases.append({
                    "sample_id": sample_id, "sampling": strategy, "nominal_coverage": coverage,
                    "replicate": replicate, "read_seed": read_seed,
                    "read_count": (coverage * SEQUENCE_LENGTH + READ_LENGTH - 1)
                    // READ_LENGTH,
                    "files": {
                        f"{sample_id}/{name}": {"bytes": len(data), "sha256": _sha(data)}
                        for name, data in (
                            ("reads.fastq.gz", reads),
                            ("reference.fasta", files[f"{sample_id}/reference.fasta"]),
                            ("reference_roles.csv", files[f"{sample_id}/reference_roles.csv"]),
                        )
                    },
                })
                truths.append({
                    "sample_id": sample_id, "role": "positive", "pair_id": pair_id,
                    "candidate_sequence": candidate,
                })
                pair_members.append(sample_id)
            pairs.append({"pair_id": pair_id, "sampling": strategy,
                          "nominal_coverage": coverage, "samples": pair_members})

    for negative_index in range(NEGATIVE_CONTROLS):
        case_index += 1
        sample_id = f"c{case_index:03d}"
        read_seed = SEED + 1000 + case_index
        background = _random_sequence(SEED + 7000 + case_index)
        decoy = _random_sequence(SEED + 9000 + case_index)
        coverage = 10
        reads = _fastq(background, read_seed, coverage, "stratified_start")
        files[f"{sample_id}/reads.fastq.gz"] = reads
        files[f"{sample_id}/reference.fasta"] = f">ref01\n{decoy}\n".encode("ascii")
        files[f"{sample_id}/reference_roles.csv"] = (
            "reference_id,reference_role,reference_source,reference_version\n"
            "ref01,technical_reference,m20-synthetic,M20-phase2b-v2\n"
        ).encode("ascii")
        cases.append({
            "sample_id": sample_id, "sampling": "stratified_start",
            "nominal_coverage": coverage, "replicate": negative_index + 1,
            "read_seed": read_seed, "read_count": 40,
            "files": {
                f"{sample_id}/{name}": {"bytes": len(data), "sha256": _sha(data)}
                for name, data in (
                    ("reads.fastq.gz", reads),
                    ("reference.fasta", files[f"{sample_id}/reference.fasta"]),
                    ("reference_roles.csv", files[f"{sample_id}/reference_roles.csv"]),
                )
            },
        })
        truths.append({
            "sample_id": sample_id, "role": "negative_control",
            "pair_id": None, "candidate_sequence": None,
        })
    manifest = {
        "schema": SCHEMA, "generator_version": GENERATOR_VERSION,
        "synthetic_only": True, "seed": SEED,
        "sequence_length": SEQUENCE_LENGTH, "read_length": READ_LENGTH,
        "matrix": {
            "sampling": list(SAMPLING), "nominal_coverage": list(COVERAGES),
            "independent_replicates_per_stratum": len(REPLICATES),
            "negative_controls": NEGATIVE_CONTROLS,
            "negative_control_coverage": 10,
            "resource_bounds": {"max_reads_per_case": MAX_READS_PER_CASE,
                                "threads": 1, "memory_mb": 2048,
                                "stage_timeout_seconds": 180},
        },
        "cases": cases, "recurrence_pairs": pairs,
    }
    truth = {"schema": "m20-phase2b-heldout-truth-v2", "cases": truths}
    return files, _canonical(manifest), _canonical(truth)


def generate_fixtures(output):
    """Create v2 inputs; keep scenario truth and the parameter manifest out of inputs."""
    root = Path(output)
    m20_phase1._reject_symlink_ancestors(root)
    root.mkdir(parents=True, exist_ok=True)
    files, manifest, truth = _expected_files()
    for relative, content in files.items():
        target = m20_phase1._safe_path(root / "inputs", relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != content:
            raise ValueError(f"Refusing to reuse changed v2 fixture: {relative}")
        if not target.exists():
            target.write_bytes(content)
    for relative, content in (
        ("benchmark_manifest.json", manifest), ("heldout_truth.json", truth),
    ):
        target = m20_phase1._safe_path(root, relative)
        if target.exists() and target.read_bytes() != content:
            raise ValueError(f"Refusing to reuse changed v2 metadata: {relative}")
        if not target.exists():
            target.write_bytes(content)
    return verify_fixtures(root)


def verify_fixtures(output):
    root = Path(output)
    files, manifest, truth = _expected_files()
    m20_phase1._reject_unexpected_inputs(root, files)
    inputs = root / "inputs"
    actual = set()
    if inputs.is_symlink():
        raise ValueError("V2 input directory may not be a symlink")
    if inputs.exists():
        for path in inputs.rglob("*"):
            if path.is_symlink():
                raise ValueError("V2 fixture inputs may not contain symlinks")
            if path.is_file():
                actual.add(path.relative_to(inputs).as_posix())
    if actual != set(files):
        raise ValueError("V2 input tree contains missing or unexpected files")
    for relative, expected in files.items():
        path = m20_phase1._safe_path(root / "inputs", relative)
        if not path.is_file() or path.read_bytes() != expected:
            raise ValueError(f"V2 fixture differs from deterministic generator: {relative}")
    for relative, expected in (("benchmark_manifest.json", manifest),
                               ("heldout_truth.json", truth)):
        path = m20_phase1._safe_path(root, relative)
        if not path.is_file() or path.read_bytes() != expected:
            raise ValueError(f"V2 metadata differs from deterministic generator: {relative}")
    return {
        "schema": SCHEMA, "case_count": len(json.loads(manifest)["cases"]),
        "manifest_sha256": _sha(manifest), "heldout_truth_sha256": _sha(truth),
    }


def _workflow_spec():
    stages = []
    manifest = json.loads(_expected_files()[1])
    for case in manifest["cases"]:
        sample = case["sample_id"]
        qc, m6, folder = f"qc_{sample}", f"m6_{sample}", f"inputs/{sample}"
        stages.extend([
            {"id": qc, "kind": "fastq_qc", "config": m20_phase2.QC_CONFIG,
             "inputs": {"read1": {"path": f"{folder}/reads.fastq.gz",
                                  "artifact_type": "raw_read"}}},
            {"id": m6, "kind": "residual_evidence",
             "config": {**M6_CONFIG, "sample_id": sample},
             "inputs": {
                 "read1": {"stage": qc, "artifact": "clean_single.fastq.gz"},
                 "qc_manifest": {"stage": qc, "artifact": "qc.json"},
                 "reference": {"path": f"{folder}/reference.fasta",
                               "artifact_type": "raw_fasta"},
                 "roles": {"path": f"{folder}/reference_roles.csv",
                           "artifact_type": "reference_roles"},
             }},
        ])
    spec = {"schema": "artifact-workflow-v1", "stages": stages}
    m20_phase2._assert_truth_free(spec)
    return spec


def _m7_spec(output, manifest, m6_root):
    observations, inputs = [], {}
    rows = {row.get("id"): row for row in manifest.get("stages", []) if isinstance(row, dict)}
    cases = json.loads(_expected_files()[1])["cases"]
    for case in cases:
        sample, stage_id = case["sample_id"], f"m6_{case['sample_id']}"
        row = rows.get(stage_id)
        paths = {
            "evidence": m20_phase2._m7_artifact_path(
                output, m6_root, row, "reconstruction_evidence.json", "reconstruction_evidence"),
            "residual": m20_phase2._m7_artifact_path(
                output, m6_root, row, "residual_manifest.json", "residual_read_manifest"),
            "contigs": m20_phase2._m7_artifact_path(
                output, m6_root, row, "supported_contigs.fasta", "canonical_contig_fasta"),
        }
        evidence = m20_phase2._json_at(m20_phase2._stage_dir(m6_root, row),
                                       "reconstruction_evidence.json")
        available = (m20_phase2._status(row) == "COMPLETE" and evidence is not None
                     and paths["evidence"] and paths["residual"])
        obs = {
            "observation_id": f"obs_{sample}", "candidate_id": None,
            "sample_id": sample, "sequencing_run_id": f"run_{sample}",
            "study_id": f"study_{sample}", "source_artifact_id": None,
            "upstream_workflow_id": manifest.get("workflow_id"),
            "molecule_type": "DNA", "m6_state": "available" if available else
            ("unavailable" if m20_phase2._status(row) in {"UNAVAILABLE", "BLOCKED"} else "failed"),
        }
        if available:
            evidence_name, residual_name = f"evidence_{sample}", f"residual_{sample}"
            obs.update({"evidence_input": evidence_name,
                        "residual_manifest_input": residual_name,
                        "source_artifact_id": f"{stage_id}:reconstruction_evidence:"
                        f"{_sha((Path(output) / paths['evidence']).read_bytes())}"})
            inputs[evidence_name] = {"path": paths["evidence"],
                                     "artifact_type": "reconstruction_evidence"}
            inputs[residual_name] = {"path": paths["residual"],
                                     "artifact_type": "residual_read_manifest"}
            if paths["contigs"]:
                name = f"contigs_{sample}"
                obs["contigs_input"] = name
                inputs[name] = {"path": paths["contigs"],
                                "artifact_type": "canonical_contig_fasta"}
            elif evidence.get("status") == "READ_SUPPORTED_ASSEMBLY":
                obs.update({"m6_state": "failed", "upstream_status": "INVALID_OUTPUT",
                            "upstream_reason": "Supported assembly lacks typed contigs."})
                obs.pop("evidence_input", None)
                obs.pop("residual_manifest_input", None)
                inputs.pop(evidence_name, None)
                inputs.pop(residual_name, None)
        else:
            obs.update({"upstream_status": "INVALID_OUTPUT" if m20_phase2._status(row) == "COMPLETE"
                        else (row.get("status", "unavailable") if row else "missing_m6_stage"),
                        "upstream_reason": "M6 outputs missing, unsafe or digest-invalid."
                        if m20_phase2._status(row) == "COMPLETE" else
                        (row.get("reason") or row.get("failure_reason") if row else
                         "M6 stage is absent.")})
        observations.append(obs)
    spec = {"schema": "artifact-workflow-v1", "stages": [{
        "id": "m7_recurrence", "kind": "independent_recurrence",
        "config": {"observations": observations,
                   "orientation_policy": "reverse_complement_invariant"},
        "inputs": inputs,
    }]}
    m20_phase2._assert_truth_free(spec)
    return spec


def _report_paths(output, m6_manifest, m7_manifest):
    rows = {row.get("id"): row for row in m6_manifest.get("stages", [])
            if isinstance(row, dict)}
    m7_rows = {row.get("id"): row for row in m7_manifest.get("stages", [])
               if isinstance(row, dict)}
    m6_root = Path(output) / "stages/m4_m6"
    truth_doc = json.loads((Path(output) / "heldout_truth.json").read_text())
    truth = {row["sample_id"]: row for row in truth_doc["cases"]}
    manifest_doc = json.loads((Path(output) / "benchmark_manifest.json").read_text())
    candidate = next(row["candidate_sequence"] for row in truth_doc["cases"]
                     if row["candidate_sequence"])
    cases = []
    for item in manifest_doc["cases"]:
        sample = item["sample_id"]
        qc_row, m6_row = rows.get(f"qc_{sample}"), rows.get(f"m6_{sample}")
        stage_dir = m20_phase2._stage_dir(m6_root, m6_row)
        evidence = m20_phase2._json_at(stage_dir, "reconstruction_evidence.json")
        residual = m20_phase2._json_at(stage_dir, "residual_manifest.json")
        support = m20_phase2._json_at(stage_dir, "read_support.json")
        candidate_set = m20_phase2._json_at(stage_dir, "candidate_sequence_set.json")
        observed = m20_phase2._candidate_sequences(candidate_set, stage_dir)
        availability = (candidate_set.get("availability", {}).get("state")
                        if isinstance(candidate_set, dict) else "NOT_EVALUATED")
        if availability == "AVAILABLE" and observed is None:
            availability = "INVALID_OUTPUT"
        target_sequence = truth[sample]["candidate_sequence"] or candidate
        candidate_path, candidate_digest = None, None
        if observed is not None and isinstance(candidate_set, dict):
            reference = candidate_set.get("availability", {}).get("fasta_artifact")
            if isinstance(reference, dict):
                relative = Path(reference.get("path", ""))
                if relative and not relative.is_absolute() and ".." not in relative.parts:
                    candidate_path = stage_dir / relative
                    candidate_digest = reference.get("sha256")
        comparison = m20_phase2._sequence_comparison(
            target_sequence, candidate_path, candidate_digest,
        )
        read_summary = m20_phase2._fastq_summary(
            Path(output) / "inputs" / sample / "reads.fastq.gz",
        )
        counts = residual.get("counts") if isinstance(residual, dict) else None
        negative_eval = None
        if truth[sample]["role"] == "negative_control":
            can_evaluate = m20_phase2._status(m6_row) == "COMPLETE" and observed is not None
            negative_eval = {
                "state": "EVALUATED" if can_evaluate else "UNEVALUABLE",
                "prediction_count": len(observed) if can_evaluate else None,
                "result": ("ZERO_PREDICTIONS" if not observed else "CANDIDATES_DETECTED")
                if can_evaluate else None,
                "reason": None if can_evaluate else
                (candidate_set.get("availability", {}).get("reason")
                 if isinstance(candidate_set, dict) else None) or
                "M6 did not produce a validated candidate set.",
            }
        cases.append({
            "sample_id": sample, "role": truth[sample]["role"],
            "pair_id": truth[sample]["pair_id"], "sampling": item["sampling"],
            "nominal_coverage": item["nominal_coverage"], "replicate": item["replicate"],
            "read_seed": item["read_seed"], "read_sha256": item["files"][
                f"{sample}/reads.fastq.gz"]["sha256"],
            "qc_status": m20_phase2._status(qc_row),
            "m6_status": m20_phase2._status(m6_row),
            "residual_read_counts": counts,
            "residual_eligible": (
                counts.get("eligible_fragments") if isinstance(counts, dict) else None
            ),
            "assembler": m20_phase2._assembler_diagnostics(
                output, stage_dir, read_summary,
            ),
            "reconstruction_status": (
                evidence.get("status") if isinstance(evidence, dict) else "NOT_EVALUATED"
            ),
            "read_support_status": (
                support.get("status") if isinstance(support, dict) else "NOT_EVALUATED"
            ),
            "candidate_availability": availability,
            "candidate_count": len(observed) if observed is not None else None,
            "supported_contig_count": (
                candidate_set.get("availability", {}).get("record_count")
                if isinstance(candidate_set, dict) else None
            ),
            "exact_full_length_recovery": comparison.get("full_length_exact_recovery"),
            "alignment": comparison.get("alignment"),
            "fragmentation": comparison.get("fragmentation"),
            "negative_control_evaluation": negative_eval,
            "_truth": truth[sample],
        })
    m7_row = m7_rows.get("m7_recurrence")
    m7_dir = m20_phase2._stage_dir(Path(output) / "stages/m7", m7_row)
    exact = m20_phase2._json_at(m7_dir, "exact_recurrence.json")
    summary = m20_phase2._json_at(m7_dir, "recurrence_summary.json")
    group_members = []
    for group in exact.get("groups", []) if isinstance(exact, dict) else []:
        members = group.get("members", []) if isinstance(group, dict) else []
        group_members.append({
            member.get("observation_id", "").removeprefix("obs_")
            for member in members if isinstance(member, dict)
        })
    pairs = []
    manifest_doc = json.loads((Path(output) / "benchmark_manifest.json").read_text())
    for pair in manifest_doc["recurrence_pairs"]:
        ids = set(pair["samples"])
        matched = any(ids <= members for members in group_members)
        cases_by_id = {row["sample_id"]: row for row in cases}
        both_supported = all(
            cases_by_id[sample]["read_support_status"] == "READ_SUPPORTED_ASSEMBLY"
            for sample in ids
        )
        pairs.append({
            **pair,
            "state": "EVALUATED" if both_supported and m20_phase2._status(m7_row) == "COMPLETE"
            else "UNEVALUABLE",
            "m7_exact_recurrence": bool(matched) if both_supported else None,
            "reason": None if both_supported else
            "At least one pair member lacks a read-supported M6 sequence.",
        })
    for case in cases:
        case.pop("_truth", None)
    return cases, pairs, {
        "status": m20_phase2._status(m7_row),
        "recurrence_status": summary.get("result_status") if isinstance(summary, dict)
        else "NOT_EVALUATED",
        "exact_group_count": summary.get("exact_group_count") if isinstance(summary, dict) else None,
        "recurrent_group_count": summary.get("recurrent_group_count")
        if isinstance(summary, dict) else None,
        "supported_sequence_observation_count": summary.get("supported_sequence_observation_count")
        if isinstance(summary, dict) else None,
    }


def _write_report(output, report):
    path = Path(output)
    (path / "report.json").write_bytes(_canonical(report))
    lines = [
        "# M20 Phase 2B v2 assembler-recovery benchmark",
        "",
        f"- Status: **{report['status']}**",
        f"- Fixture schema: `{report['fixtures']['schema']}`",
        f"- Fixture integrity after run: **{report['fixtures']['unchanged_after_execution']}**",
        f"- M4/M6 workflow: `{report['workflow_status']['m4_m6']}`; M7: `{report['workflow_status']['m7']}`",
        "",
        "## Prespecified case results",
        "",
        "| Case | Role | Sampling | Coverage | Reads | QC | M6 | Eligible | SPAdes | Candidates | Exact recovery | Negative control |",
        "|---|---|---|---:|---:|---|---|---:|---|---:|---|---|",
    ]
    for row in report["cases"]:
        role = "negative_control" if row["negative_control_evaluation"] else "positive"
        neg = row["negative_control_evaluation"]
        lines.append(
            f"| {row['sample_id']} | {role} | {row['sampling']} | {row['nominal_coverage']} | "
            f"{row['assembler']['input_reads'].get('read_count')} | {row['qc_status']} | "
            f"{row['m6_status']} | {row['residual_eligible']} | "
            f"{row['assembler'].get('exit_status')} | {row['candidate_count']} | "
            f"{row['exact_full_length_recovery']} | "
            f"{neg['state'] + ':' + str(neg['result']) if neg else 'n/a'} |"
        )
    lines.extend(["", "## M7 recurrence by independent pair", ""])
    for row in report["recurrence_pairs"]:
        lines.append(
            f"- {row['pair_id']} ({row['sampling']}, {row['nominal_coverage']}x): "
            f"{row['state']}, exact recurrence `{row['m7_exact_recurrence']}`."
        )
    lines.extend([
        "", "## Interpretation limits", "",
        "All inputs are deterministic artificial sequences. Recovery and recurrence "
        "measure software behavior only; negative controls do not estimate biological "
        "specificity. Failed, missing, and unevaluable cases are retained.",
        "",
    ])
    markdown = "\n".join(lines)
    (path / "report.md").write_text(markdown, encoding="utf-8")
    from html import escape
    (path / "report.html").write_text(
        "<!doctype html><meta charset=\"utf-8\"><title>M20 Phase 2B v2</title>"
        "<style>body{font:16px/1.55 system-ui;max-width:1100px;margin:40px auto;padding:0 20px}"
        "pre{white-space:pre-wrap}</style><pre>" + escape(markdown) + "</pre>\n",
        encoding="utf-8",
    )


def run(output, runner=None):
    output = Path(output).absolute()
    m20_phase1._reject_symlink_ancestors(output)
    output.mkdir(parents=True, exist_ok=True)
    fixture_before = generate_fixtures(output)
    with tempfile.TemporaryDirectory(prefix="m20-phase2b-baseline-") as baseline:
        baseline_fixtures = m20_phase1.generate_fixtures(baseline)
    expected_phase1 = {
        "manifest_sha256": "24a4cdc9c0337f373d49ee49482f6c49eb91de03d8993cbe9ac2358925ccacac",
        "heldout_truth_sha256": "1d6e16d1c31975181dfa8cd86260297f2151d89914ff796d4ae23934936e2614",
    }
    phase1_unchanged = all(
        baseline_fixtures.get(key) == value for key, value in expected_phase1.items()
    )
    run_workflow = runner or artifact_workflow.run
    registry = artifact_workflow.build_default_registry()
    spec_path = output / "m4-m6-workflow.json"
    spec_path.write_bytes(_canonical(_workflow_spec()))
    m6_root = output / "stages/m4_m6"
    m6_before = m20_phase2._manifest_digest(m6_root / "workflow.json")
    m6_error = m20_phase2._execute_workflow(run_workflow, spec_path, m6_root, registry)
    m6_manifest, m6_stale = m20_phase2._safe_manifest(m6_root / "workflow.json", m6_before)
    m6_error = m6_error or m6_stale
    m7_spec = _m7_spec(output, m6_manifest, m6_root)
    m7_path = output / "m7-workflow.json"
    m7_path.write_bytes(_canonical(m7_spec))
    m7_root = output / "stages/m7"
    m7_before = m20_phase2._manifest_digest(m7_root / "workflow.json")
    m7_error = m20_phase2._execute_workflow(run_workflow, m7_path, m7_root, registry)
    m7_manifest, m7_stale = m20_phase2._safe_manifest(m7_root / "workflow.json", m7_before)
    m7_error = m7_error or m7_stale
    fixture_after = verify_fixtures(output)
    cases, pairs, m7_summary = _report_paths(output, m6_manifest, m7_manifest)
    report = {
        "schema": "m20-phase2b-report-v2",
        "status": "COMPLETE" if fixture_before == fixture_after
        and phase1_unchanged
        and m6_manifest.get("status") == "complete"
        and m7_manifest.get("status") == "complete" else "INCOMPLETE",
        "benchmark_definition": json.loads(
            (output / "benchmark_manifest.json").read_text(encoding="utf-8")
        ),
        "execution_environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "implementation": platform.python_implementation(),
            "machine": platform.machine(),
        },
        "fixtures": {
            **fixture_before, "unchanged_after_execution": fixture_before == fixture_after,
            "truth_outside_analysis_inputs": True,
            "phase1_baseline": {**baseline_fixtures,
                                "matches_frozen_digests": phase1_unchanged},
        },
        "workflow_status": {"m4_m6": m6_manifest.get("status", "unavailable"),
                            "m7": m7_manifest.get("status", "unavailable")},
        "execution_error": {"m4_m6": m6_error, "m7": m7_error},
        "cases": cases, "recurrence_pairs": pairs, "m7": m7_summary,
        "limitations": [
            "Synthetic software benchmark only; no biological sensitivity or specificity.",
            "All planned cases are reported, including failures and unavailable outcomes.",
            "M7 recurrence is computed only from independently validated M6 outputs.",
        ],
    }
    _write_report(output, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True,
                        help="Dedicated output directory for the v2 benchmark")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
