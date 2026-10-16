"""Deterministic synthetic-only benchmark of the registered M6 residual path."""

import argparse
import gzip
import hashlib
import html
from io import BytesIO
import json
import math
from pathlib import Path
import random

from . import artifact_workflow
from .m8_candidate_handoff import validate_candidate_sequence_set

SCHEMA = "m19-synthetic-benchmark-v1"
READ_LENGTH = 100
SEQUENCE_LENGTH = 800
SEED = 190076
SYNTHETIC_FLAGS = {
    "synthetic_only": True,
    "biological_data_used": False,
    "biological_claims_authorized": False,
}
CASES = (
    {"case_id": "baseline", "error_rate": 0.0, "coverage": 60, "divergence": 0.25,
     "repeat_complexity": "low", "positive": True},
    {"case_id": "high_error", "error_rate": 0.05, "coverage": 60, "divergence": 0.25,
     "repeat_complexity": "low", "positive": True},
    {"case_id": "low_coverage", "error_rate": 0.0, "coverage": 16, "divergence": 0.25,
     "repeat_complexity": "low", "positive": True},
    {"case_id": "high_divergence", "error_rate": 0.0, "coverage": 60, "divergence": 0.45,
     "repeat_complexity": "low", "positive": True},
    {"case_id": "high_repeat", "error_rate": 0.0, "coverage": 60, "divergence": 0.25,
     "repeat_complexity": "high", "positive": True},
    {"case_id": "negative_control", "error_rate": 0.0, "coverage": 60, "divergence": 0.25,
     "repeat_complexity": "low", "positive": False},
)
M6_CONFIG = {
    "layout": "single-end", "assembly_enabled": True, "assembler": "spades",
    "threads": 1, "memory_mb": 2048,
    "triage": {"min_read_length": 50, "max_ambiguous_fraction": 0.05,
               "min_entropy_bits": 1.2, "min_mean_phred": 20},
    "support": {"min_mapq": 20, "min_alignment_fraction": 0.8,
                "min_sequence_identity": 0.95, "min_coverage_breadth": 0.8,
                "min_mean_depth": 2, "min_distinct_fragments": 2,
                "coverage_window_size": 100},
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes() != data)):
        raise ValueError(f"Refusing to overwrite changed M19 input: {path.name}")
    if not path.exists():
        path.write_bytes(data)


def _sequence(rng):
    return "".join(rng.choice("ACGT") for _ in range(SEQUENCE_LENGTH))


def _mutate(sequence, rate, rng):
    result = list(sequence)
    count = round(len(sequence) * rate)
    positions = rng.sample(range(len(sequence)), count)
    for position in positions:
        result[position] = rng.choice("ACGT".replace(result[position], ""))
    return "".join(result)


def _fastq(case, truth, reference, params):
    rng = random.Random(SEED + sum(case["case_id"].encode()))
    reads = []
    for i in range(8):
        start = round(i * (len(reference) - READ_LENGTH) / 7)
        reads.append((f"{case['case_id']}-ref-{i}", reference[start:start + READ_LENGTH], "I" * READ_LENGTH))
    if truth is not None:
        count = math.ceil(params["coverage"] * len(truth) / READ_LENGTH)
        starts = [round(i * (len(truth) - READ_LENGTH) / max(1, count - 1)) for i in range(count)]
        for i, start in enumerate(starts):
            original = truth[start:start + READ_LENGTH]
            sequence = list(original)
            quality = ["I"] * len(sequence)
            errors = round(len(sequence) * params["error_rate"])
            for position in rng.sample(range(len(sequence)), errors):
                sequence[position] = rng.choice("ACGT".replace(sequence[position], ""))
                quality[position] = "5"
            reads.append((f"{case['case_id']}-cand-{i:04d}", "".join(sequence), "".join(quality)))
    text = "".join(f"@{name}\n{seq}\n+\n{qual}\n" for name, seq, qual in reads).encode()
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as out:
        out.write(text)
    return buffer.getvalue()


def generate_inputs(root):
    """Build reproducible read/reference inputs and a separate, held-out truth file."""
    root = Path(root)
    files, heldout = {}, {"schema": "m19-heldout-synthetic-truth-v1", "cases": []}
    for index, case in enumerate(CASES):
        rng = random.Random(SEED + index * 101)
        truth = _sequence(rng) if case["positive"] else None
        if truth and case["repeat_complexity"] == "high":
            truth = ("ACGTGCAATG" * 80)
        reference = _mutate(truth, case["divergence"], random.Random(SEED + index * 101 + 1)) if truth else _sequence(rng)
        folder = Path("datasets") / case["case_id"]
        fastq = _fastq(case, truth, reference, case)
        reference_fasta = f">m19-reference-{case['case_id']}\n{reference}\n".encode()
        roles = ("reference_id,reference_role,reference_source,reference_version\n"
                 f"m19-reference-{case['case_id']},technical_reference,m19-synthetic,M19-v1\n").encode()
        for name, data in (("reads.fastq.gz", fastq), ("reference.fasta", reference_fasta),
                           ("reference_roles.csv", roles)):
            rel = (folder / name).as_posix()
            files[rel] = data
        heldout["cases"].append({
            "case_id": case["case_id"], "positive": case["positive"],
            "candidate_sequence": truth,
            "candidate_sha256": _sha(truth.encode()) if truth else None,
        })
    for rel, data in files.items():
        _write(root / rel, data)
    source = {"schema": "m19-synthetic-inputs-v1", "seed": SEED, **SYNTHETIC_FLAGS,
              "files": {k: {"sha256": _sha(v), "bytes": len(v)} for k, v in sorted(files.items())}}
    _write(root / "source_manifest.json", _json_bytes(source))
    return source, heldout


def _workflow_spec():
    stages = []
    for case in CASES:
        cid = case["case_id"]
        qc, m6 = f"qc_{cid}", f"m6_{cid}"
        folder = f"inputs/datasets/{cid}"
        stages.extend([
            {"id": qc, "kind": "fastq_qc", "config": {
                "min_length": 30, "end_quality": 20, "min_mean_quality": 20,
                "max_n_fraction": 0.05, "adapters": [], "min_adapter_overlap": 12,
            }, "inputs": {"read1": {"path": f"{folder}/reads.fastq.gz", "artifact_type": "raw_read"}}},
            {"id": m6, "kind": "residual_evidence", "config": {**M6_CONFIG, "sample_id": f"m19-{cid}"},
             "inputs": {
                 "read1": {"stage": qc, "artifact": "clean_single.fastq.gz"},
                 "qc_manifest": {"stage": qc, "artifact": "qc.json"},
                 "reference": {"path": f"{folder}/reference.fasta", "artifact_type": "raw_fasta"},
                 "roles": {"path": f"{folder}/reference_roles.csv", "artifact_type": "reference_roles"},
             }},
        ])
    return {"schema": "artifact-workflow-v1", "stages": stages}


def score_sequences(truth, predictions):
    """Exact-sequence software metric; truth is never an analysis-stage input."""
    normalized = [sequence.upper() for sequence in predictions]
    recovered = 1 if truth is not None and truth.upper() in normalized else 0
    false_positives = sum(1 for sequence in normalized if truth is None or sequence != truth.upper())
    return {
        "predicted_candidate_count": len(normalized),
        "true_candidate_count": 1 if truth is not None else 0,
        "recovered_true_candidates": recovered,
        "missed_true_candidates": (1 - recovered) if truth is not None else None,
        "recovery_rate": recovered if truth is not None else None,
        "false_positive_candidates": false_positives,
        "false_discovery_fraction": false_positives / len(normalized) if normalized else None,
        "metric_definition": "exact case-insensitive full-sequence match; synthetic software metric only",
    }


def _read_fasta(path):
    records, current = [], []
    for line in Path(path).read_text(encoding="ascii").splitlines():
        if line.startswith(">"):
            if current:
                records.append("".join(current))
            current = []
        elif line.strip():
            current.append(line.strip())
    if current:
        records.append("".join(current))
    return records


def run(output, runner=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    source, truth = generate_inputs(output / "inputs")
    truth_path = output / "heldout_truth.json"
    _write(truth_path, _json_bytes(truth))
    spec_path = output / "m19-workflow.json"
    spec = _workflow_spec()
    if "heldout_truth" in json.dumps(spec) or "candidate_sequence" in json.dumps(spec):
        raise ValueError("M19 held-out truth must not enter the M4 analysis graph")
    _write(spec_path, _json_bytes(spec))
    manifest_path = output / "stages" / "workflow.json"
    manifest_before = _sha(manifest_path.read_bytes()) if manifest_path.is_file() else None
    execution_error = None
    try:
        (runner or artifact_workflow.run)(
            spec_path, output / "stages", artifact_workflow.build_default_registry())
    except Exception as exc:
        execution_error = {"type": type(exc).__name__, "message": str(exc)}
    manifest_after = _sha(manifest_path.read_bytes()) if manifest_path.is_file() else None
    stale_manifest = execution_error is not None and manifest_before == manifest_after
    try:
        manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() and not stale_manifest else {
            "status": "execution_error" if stale_manifest else "unavailable", "stages": [],
        }
        if not isinstance(manifest, dict) or not isinstance(manifest.get("stages"), list):
            raise ValueError("M4 workflow manifest has an invalid shape")
    except (OSError, ValueError, TypeError) as exc:
        manifest = {"status": "incomplete", "stages": []}
        execution_error = execution_error or {"type": type(exc).__name__, "message": str(exc)}
    if stale_manifest:
        execution_error["stale_manifest_ignored"] = True

    truth_by_id = {row["case_id"]: row for row in truth["cases"]}
    reports = []
    stages = {row.get("id"): row for row in manifest["stages"] if isinstance(row, dict)}
    for case in CASES:
        cid = case["case_id"]
        row = stages.get(f"m6_{cid}")
        status = row.get("status") if row else "unavailable"
        stage_root = (output / "stages").resolve()
        stage_dir = None
        if row and isinstance(row.get("output_path"), str):
            relative = Path(row["output_path"])
            unresolved = stage_root / relative
            candidate = unresolved.resolve()
            if (not relative.is_absolute() and ".." not in relative.parts
                    and not unresolved.is_symlink() and candidate.is_relative_to(stage_root)):
                stage_dir = candidate
            else:
                status = "incomplete"
        candidate_manifest = stage_dir / "candidate_sequence_set.json" if stage_dir else None
        predictions, diagnostics = [], None
        state = {"complete": "COMPLETE", "blocked": "BLOCKED",
                 "dependency_missing": "UNAVAILABLE", "unavailable": "UNAVAILABLE",
                 "incomplete": "INCOMPLETE", "failed": "INCOMPLETE"}.get(
                     status, "NOT_EVALUATED")
        if state == "COMPLETE":
            if (candidate_manifest is None or candidate_manifest.is_symlink()
                    or not candidate_manifest.is_file()):
                state, diagnostics = "INCOMPLETE", "candidate_sequence_set.json is missing"
            else:
                try:
                    validate_candidate_sequence_set(candidate_manifest)
                    document = json.loads(candidate_manifest.read_text())
                    fasta_ref = document.get("availability", {}).get("fasta_artifact")
                    if fasta_ref:
                        fasta_unresolved = stage_dir / fasta_ref["path"]
                        fasta_path = fasta_unresolved.resolve()
                        if (fasta_unresolved.is_symlink() or not fasta_path.is_relative_to(stage_dir)
                                or not fasta_path.is_file()):
                            raise ValueError("candidate FASTA artifact is missing or escapes the M6 output")
                        predictions = _read_fasta(fasta_path)
                    elif document.get("records"):
                        raise ValueError("candidate records have no FASTA artifact")
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    state, diagnostics = "INCOMPLETE", f"{type(exc).__name__}: {exc}"
        metrics = score_sequences(truth_by_id[cid]["candidate_sequence"], predictions) if state == "COMPLETE" else {
            "predicted_candidate_count": None, "true_candidate_count": 1 if case["positive"] else 0,
            "recovered_true_candidates": None, "missed_true_candidates": None,
            "recovery_rate": None, "false_positive_candidates": None,
            "false_discovery_fraction": None,
            "metric_definition": "not evaluated because M6 output is unavailable or incomplete",
        }
        reports.append({
            **case, "status": state, "m4_stage_status": status,
            "m4_error": row.get("error") or row.get("reason") if row else "M6 stage row is absent",
            "diagnostics": diagnostics, **metrics,
        })
    complete = all(row["status"] == "COMPLETE" for row in reports)
    report = {
        "schema": SCHEMA, **SYNTHETIC_FLAGS, "workflow_status": manifest.get("status", "unavailable"),
        "benchmark_status": "COMPLETE" if complete and not execution_error else "INCOMPLETE",
        "execution_manifest": "stages/workflow.json", "source_manifest": "inputs/source_manifest.json",
        "heldout_truth": "heldout_truth.json", "cases": reports,
        "limitations": [
            "All reads, references, and labels are artificial and generated from fixed seeds.",
            "Held-out truth is excluded from the M4 input graph; it is used only after execution for scoring.",
            "Exact sequence matching is a strict software metric, not biological sensitivity or specificity.",
            "This bounded matrix is not an empirical benchmark, does not identify satellites, and does not validate biological function.",
            "Read-back and assembly evidence share generated reads and are not independent biological validation.",
        ],
    }
    if execution_error:
        report["execution_error"] = execution_error
    (output / "m19-report.json").write_bytes(_json_bytes(report))
    rows = [
        "<!doctype html><meta charset='utf-8'><title>M19 synthetic benchmark</title>",
        f"<h1>M19 synthetic benchmark: {html.escape(report['benchmark_status'])}</h1>",
        "<p>Software-only benchmark; no biological datasets or claims.</p>",
        "<table><thead><tr><th>Case</th><th>Error</th><th>Coverage</th><th>Divergence</th>",
        "<th>Repeat</th><th>Status</th><th>Recovery rate</th><th>False positives</th>",
        "<th>False-discovery fraction</th></tr></thead><tbody>",
    ]
    for row in reports:
        rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(value))}</td>" for value in (
                row["case_id"], row["error_rate"], row["coverage"], row["divergence"],
                row["repeat_complexity"], row["status"], row["recovery_rate"],
                row["false_positive_candidates"], row["false_discovery_fraction"],
            )
        ) + "</tr>")
    rows.extend(["</tbody></table><h2>Limitations</h2><ul>"])
    rows.extend(f"<li>{html.escape(item)}</li>" for item in report["limitations"])
    rows.append("</ul>")
    (output / "m19-report.html").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the synthetic-only M19 quantitative benchmark")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = run(args.output)
    print(f"M19 {report['benchmark_status']}: {len(report['cases'])} synthetic cases")
    return 0 if report["benchmark_status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
