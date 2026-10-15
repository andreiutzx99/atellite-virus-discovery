"""Opt-in synthetic M17 coordinator using frozen M8/M9/M10 contracts."""

import argparse
import hashlib
import json
from pathlib import Path

from . import artifact_workflow
from .m8_candidate_handoff import validate_candidate_sequence_set

SCHEMA = "m17-synthetic-workflow-v1"
SCENARIOS = (
    ("syn-candidate-001", "reference-compatible-like RNA control", "RNA",
     "ATG" * 10 + "TAA" + "ACGT" * 6),
    ("syn-candidate-002", "RNA residual-review candidate", "RNA",
     "ACGTTGCA" * 8 + "GGTACC" * 3),
    ("syn-candidate-003", "RNA junction-like pattern", "RNA",
     "ATGCGTAC" * 5 + "GGTTAACCGG" + "CGTATGCA" * 5),
    ("syn-candidate-004", "reference-compatible-like DNA control", "DNA",
     "ATGC" * 12 + "TAA" + "GCTA" * 6),
    ("syn-candidate-005", "DNA review candidate", "DNA",
     "CGAT" * 8 + "AACCGGTT" * 3),
    ("syn-candidate-006", "ambiguous contaminant control", "DNA",
     "NNNNACGTNNNN" * 4),
    ("syn-candidate-007", "short low-information control", "RNA", "ACGT" * 6),
)
STAGE_PLAN = (
    ("m9_orfs", "m9_orf_translation", "M9", "RNA and DNA"),
    ("m10_architecture", "m10_exact_first", "M10", "RNA and DNA"),
)
M10_BRANCHES = (
    "M10_TERMINAL_DIRECT_V1", "M10_TERMINAL_INVERTED_V1",
    "M10_INTERNAL_DIRECT_V1", "M10_INTERNAL_INVERTED_V1",
)
UNIMPLEMENTED = {
    "M7 recurrence": {
        "status": "SKIPPED",
        "reason": "No independent source-read datasets are present in this fixture.",
    },
    "M8 homology": {
        "status": "UNAVAILABLE",
        "reason": "No declared reference snapshot is supplied.",
    },
    "M11 RNA folding": {
        "status": "NOT_EVALUATED",
        "reason": "Optional RNA-only stage is outside this vertical slice.",
    },
    "M12 technical artifact review": {
        "status": "NOT_EVALUATED",
        "reason": "No controls or read-origin artifacts are supplied.",
    },
    "M13 DVG differential": {
        "status": "NOT_EVALUATED",
        "reason": "No caller-specific junction evidence is supplied.",
    },
    "M14 helper association": {
        "status": "NOT_EVALUATED",
        "reason": "No matched candidate/helper observations are supplied.",
    },
    "M15 evidence dossier": {
        "status": "NOT_EVALUATED",
        "reason": "No authenticated M5-M14 producer bundle is supplied.",
    },
    "DNA circularity and structural variants": {
        "status": "UNAVAILABLE",
        "reason": "No validated DNA-specific methods are registered.",
    },
}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing to follow a symlink while writing {path.name}")
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError(f"Refusing to overwrite changed or non-file artifact {path.name}")
    else:
        path.write_bytes(data)
    return {"path": path.name, "sha256": _sha(data)}


def generate_fixture_bundle(root):
    """Create deterministic, wholly artificial M6-shaped candidate inputs."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Synthetic fixture root must be a regular directory")
    fasta = "".join(f">{candidate_id}\n{sequence}\n"
                    for candidate_id, _label, _molecule, sequence in SCENARIOS).encode("ascii")
    fasta_ref = _write(root / "candidate_sequences.fasta", fasta)
    source_ref = _write(
        root / "synthetic_source_manifest.json",
        _json_bytes({"schema": "m17-synthetic-source-v1", "synthetic_only": True,
                     "note": "No reads, specimens, or biological references are represented."}),
    )
    assembly = _json_bytes({
        "schema": "assembly-manifest-v1", "workflow_status": "complete",
        "contig_count": len(SCENARIOS), "assembler": "M17 deterministic fixture generator",
        "external_tool_version": "not-run",
    })
    assembly_ref = _write(root / "assembly_manifest.json", assembly)
    reconstruction = _json_bytes({
        "schema": "m6-reconstruction-evidence-v1",
        "status": "SYNTHETIC_FIXTURE_ONLY", "contigs": [],
        "configuration": {"synthetic_fixture_generator": SCHEMA}, "provenance": {},
    })
    evidence_ref = _write(root / "reconstruction_evidence.json", reconstruction)
    records = []
    for candidate_id, _label, molecule, sequence in SCENARIOS:
        seq = sequence.encode("ascii")
        records.append({
            "candidate_id": candidate_id, "sequence_id": candidate_id,
            "fasta_record_id": candidate_id, "sequence_sha256": _sha(seq),
            "sequence_length": len(sequence), "sequence_bytes_available": True,
            "sequence_unavailable_reason": None, "molecule_type": molecule,
            "sequence_alphabet": "IUPAC_NUCLEOTIDE", "completeness_state": "UNKNOWN",
            "source_artifact_id": source_ref["path"],
            "source_artifact_sha256": source_ref["sha256"],
            "m6_support_status": "LOW_SUPPORT_ASSEMBLY", "m7_context": None,
        })
    candidate = {
        "schema": "m8-candidate-sequence-set-v1",
        "producer": {"stage_kind": "residual_evidence", "stage_id": "m17-fixture",
                     "adapter_name": "m17-synthetic-fixture", "adapter_version": "1"},
        "source_artifact": source_ref, "assembly_manifest": assembly_ref,
        "m6_evidence": {
            "reconstruction_status": "SYNTHETIC_FIXTURE_ONLY",
            "support_status": "SYNTHETIC_FIXTURE_ONLY", "artifact": evidence_ref,
        },
        "m7_context": None,
        "availability": {"state": "AVAILABLE", "reason": None,
                         "fasta_artifact": fasta_ref, "record_count": len(records)},
        "records": records,
    }
    candidate_path = root / "candidate_sequence_set.json"
    _write(candidate_path, _json_bytes(candidate))
    validate_candidate_sequence_set(candidate_path)
    truth = {
        "schema": "m17-synthetic-fixture-truth-v1", "synthetic_only": True,
        "warning": "These generator labels are not pipeline inferences or biological truth.",
        "scenarios": [
            {"candidate_id": candidate_id, "pathway": molecule, "scenario_label": label}
            for candidate_id, label, molecule, _sequence in SCENARIOS
        ],
    }
    _write(root / "fixture_truth.json", _json_bytes(truth))
    return candidate_path


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _m10_scope_result(candidate_id, branches):
    branch_statuses = {
        name: details.get("branch_status")
        for name, details in sorted(branches.items())
        if isinstance(details, dict)
    }
    evidence_reported = any(
        details.get("evidence_status") == "EVIDENCE_FOUND"
        for details in branches.values() if isinstance(details, dict)
    )
    fully_completed = (
        set(branch_statuses) == set(M10_BRANCHES)
        and all(status in {
            "COMPLETED_MATCHES_REPORTED", "COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY",
        } for status in branch_statuses.values())
    )
    scope_state = (
        "EVIDENCE_REPORTED_WITHIN_M10_SCOPE" if evidence_reported
        else "NO_SIGNAL_WITHIN_TESTED_M10_SCOPE" if fully_completed
        else "INCOMPLETE_OR_UNRESOLVED"
    )
    return {
        "candidate_id": candidate_id, "stage": "M10",
        "scope_state": scope_state, "branch_statuses": branch_statuses,
    }


def run(output):
    """Run the existing M9→M10 artifact workflow over generated fixtures."""
    output = Path(output).resolve()
    input_root = output / "inputs"
    candidate_path = generate_fixture_bundle(input_root)
    workflow_spec = output / "m17-workflow.json"
    spec = {
        "schema": "artifact-workflow-v1",
        "stages": [
            {"id": "m9_orfs", "kind": "m9_orf_translation", "config": {},
             "inputs": {"candidate_sequence_set": {
                 "path": "inputs/candidate_sequence_set.json",
                 "artifact_type": "m8_candidate_sequence_set"}}},
            {"id": "m10_architecture", "kind": "m10_exact_first", "config": {},
             "inputs": {
                 "candidate_sequence_set": {
                     "path": "inputs/candidate_sequence_set.json",
                     "artifact_type": "m8_candidate_sequence_set"},
                 "m9_orf_results": {
                     "stage": "m9_orfs", "artifact": "orf_results.json"},
             }},
        ],
    }
    workflow_spec.parent.mkdir(parents=True, exist_ok=True)
    _write(workflow_spec, _json_bytes(spec))
    artifact_workflow.run(
        workflow_spec, output / "stages", artifact_workflow.build_default_registry())
    stage_manifest = _read_json(output / "stages" / "workflow.json")
    stages = []
    for stage_id, kind, milestone, pathways in STAGE_PLAN:
        actual = next((row for row in stage_manifest["stages"]
                       if row.get("id") == stage_id), {})
        stage_dir = output / "stages" / actual.get("output_path", "")
        output_names = []
        if stage_dir.is_dir():
            for artifact in sorted(stage_dir.iterdir()):
                if artifact.is_file() and artifact.name != "manifest.json":
                    output_names.append(artifact.name)
        stages.append({
            "stage_id": stage_id, "stage_kind": kind, "milestone": milestone,
            "pathways": pathways, "status": actual.get("status", "not_evaluated"),
            "outputs": output_names,
        })
    candidate_set = _read_json(candidate_path)
    m10_accounting_path = output / "stages" / "m10_architecture" / "candidate_accounting.jsonl"
    accounting = [
        json.loads(line) for line in m10_accounting_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    candidate_scope_results = []
    for row in accounting:
        candidate_id = row.get("candidate_id")
        branches = row.get("branches")
        if not isinstance(candidate_id, str) or not isinstance(branches, dict):
            continue
        candidate_scope_results.append(_m10_scope_result(candidate_id, branches))
    report = {
        "schema": SCHEMA, "workflow_status": stage_manifest.get("status", "not_evaluated"),
        "synthetic_only": True, "candidate_count": len(candidate_set["records"]),
        "execution_manifest": "stages/workflow.json",
        "input_sha256": _sha(candidate_path.read_bytes()),
        "configuration_sha256": stage_manifest["configuration_sha256"],
        "stage_dependencies": stage_manifest.get("stage_graph", []),
        "stages": stages, "candidate_scope_results": candidate_scope_results,
        "unimplemented_or_unavailable": UNIMPLEMENTED,
        "interpretation_limits": [
            "Fixture labels are kept in inputs/fixture_truth.json, not treated as inferred results.",
            "ORFs and exact repeats are descriptive computational evidence only.",
            "No novelty, satellite, virus identity, DVG function, or helper-dependence claim is made.",
            "The fixture source identity is synthetic; no biological reads or references are used.",
        ],
    }
    _write(output / "m17-report.json", _json_bytes(report))
    rows = [
        "<!doctype html><meta charset='utf-8'><title>M17 synthetic workflow</title>",
        "<h1>M17 synthetic workflow demonstration</h1>",
        "<p>Artificial inputs only. This report does not demonstrate biological discovery.</p>",
        "<table><thead><tr><th>Stage</th><th>Status</th><th>Outputs</th></tr></thead><tbody>",
    ]
    for stage in stages:
        rows.append("<tr><td>" + stage["milestone"] + " " + stage["stage_kind"]
                    + "</td><td>" + str(stage["status"]) + "</td><td>"
                    + ", ".join(stage["outputs"]) + "</td></tr>")
    rows.extend(["</tbody></table><h2>Not run / unavailable</h2><ul>"])
    rows.extend("<li>" + key + " [" + value["status"] + "]: "
                + value["reason"] + "</li>" for key, value in UNIMPLEMENTED.items())
    rows.extend(["</ul><h2>Interpretation limits</h2><ul>"])
    rows.extend("<li>" + item + "</li>" for item in report["interpretation_limits"])
    rows.extend(["</ul>"])
    _write(output / "m17-report.html", ("\n".join(rows) + "\n").encode("utf-8"))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the offline M17 synthetic discovery workflow")
    parser.add_argument("--output", required=True, help="Output directory; rerunning resumes verified stages")
    args = parser.parse_args(argv)
    result = run(args.output)
    print(f"M17 {result['workflow_status']}: {result['candidate_count']} synthetic candidates")
    print(Path(args.output).resolve() / "m17-report.html")
    return 0 if result["workflow_status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
