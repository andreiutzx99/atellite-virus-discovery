"""Opt-in, synthetic-only read-to-candidate workflow through registered M6."""

import argparse
import csv
import gzip
import hashlib
import html
from io import BytesIO
import json
from pathlib import Path
import random

from . import artifact_workflow
from .assembly_adapters import _read_fastq
from .m8_candidate_handoff import validate_candidate_sequence_set

SCHEMA = "m18-synthetic-read-workflow-v1"
MASTER_SEED = 180076
GENERATOR_VERSION = "m18-random-acgt-v2"
READ_LENGTH = 100
REFERENCE_LENGTH = 400
CANDIDATE_LENGTH = 1000
CASE_SPECS = (
    ("rna_supported", "RNA", "supported residual candidate", 18101, "supported"),
    ("dna_supported", "DNA", "supported residual candidate", 18102, "supported"),
    ("rna_reference_only", "RNA", "reference-accounted-only control", 18103, "reference_only"),
    ("dna_insufficient_support", "DNA", "insufficient read-back support", 18104, "low_support"),
)
SYNTHETIC_FLAGS = {
    "synthetic_only": True,
    "real_biological_reads": False,
    "real_biological_reference": False,
    "independent_biological_evidence": False,
}
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


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing to write through symlink: {path.name}")
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise ValueError(f"Refusing to overwrite changed M18 fixture: {path.name}")
    else:
        path.write_bytes(data)
    return {"path": path.name, "sha256": _sha(data)}


def _replace_generated(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError(f"Refusing to replace unsafe generated artifact: {path.name}")
    path.write_bytes(data)


def _random_sequence(rng, length):
    return "".join(rng.choice("ACGT") for _ in range(length))


def _windows(sequence, count, read_length=READ_LENGTH):
    if len(sequence) < read_length or count < 1:
        raise ValueError("Synthetic sequence is too short for the requested read windows")
    last_start = len(sequence) - read_length
    starts = [round(index * last_start / max(count - 1, 1)) for index in range(count)]
    return [sequence[start:start + read_length] for start in starts]


def _fastq_record(name, sequence, quality="I"):
    return f"@{name}\n{sequence}\n+\n{quality * len(sequence)}\n"


def _gzip_bytes(data):
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as out:
        out.write(data)
    return buffer.getvalue()


def _fixture_payloads():
    payloads = {}
    truth_cases = []
    for case_id, pathway, label, seed, mode in CASE_SPECS:
        rng = random.Random(seed)
        reference = _random_sequence(rng, REFERENCE_LENGTH)
        candidate = _random_sequence(rng, CANDIDATE_LENGTH)
        if candidate in reference or reference in candidate:
            raise AssertionError("Independent PRNG draws unexpectedly produced nested sequences")
        reads = []
        for index, sequence in enumerate(_windows(reference, 7), 1):
            reads.append((f"{case_id}-ref-{index:03d}", sequence, "I"))
        expected_candidate = mode in {"supported", "low_support"}
        if expected_candidate:
            # High-depth overlapping artificial fragments mirror a proven SPAdes
            # fixture geometry; each repeat remains a distinct FASTQ fragment.
            starts = range(0, CANDIDATE_LENGTH - READ_LENGTH + 1, 5)
            for repeat in range(4):
                for index, start in enumerate(starts):
                    sequence = candidate[start:start + READ_LENGTH]
                    reads.append((f"{case_id}-res-{repeat:02d}-{index:03d}", sequence, "I"))
        if case_id == "rna_supported":
            reads.extend([
                (f"{case_id}-low-quality", _random_sequence(rng, READ_LENGTH), "!"),
                (f"{case_id}-ambiguous", "N" * 16 + _random_sequence(rng, READ_LENGTH - 16), "I"),
                (f"{case_id}-low-complexity", "A" * READ_LENGTH, "I"),
            ])
        fastq = _gzip_bytes("".join(_fastq_record(*row) for row in reads).encode("ascii"))
        reference_bytes = f">m18-reference-{case_id}\n{reference}\n".encode("ascii")
        roles_text = (
            "reference_id,reference_role,reference_source,reference_version\n"
            f"m18-reference-{case_id},technical_reference,m18-synthetic-fixture,{GENERATOR_VERSION}\n"
        )
        for name, payload in (
            ("reads.fastq.gz", fastq), ("reference.fasta", reference_bytes),
            ("reference_roles.csv", roles_text.encode("utf-8")),
        ):
            relative = (Path("datasets") / case_id / name).as_posix()
            payloads[relative] = payload
        truth_cases.append({
            "case_id": case_id, "pathway": pathway, "scenario_label": label,
            "seed": seed, "mode": mode, "candidate_expected": expected_candidate,
        })
    truth = {
        "schema": "m18-synthetic-truth-v1", "synthetic_only": True,
        "warning": "Scenario labels and RNA/DNA pathways are generator metadata, not read-derived findings.",
        "cases": truth_cases,
    }
    return payloads, truth


def _source_manifest(payloads):
    return {
        "schema": "m18-synthetic-source-v1", **SYNTHETIC_FLAGS,
        "generator": GENERATOR_VERSION, "master_seed": MASTER_SEED,
        "files": {
            relative: {"sha256": _sha(payload), "bytes": len(payload)}
            for relative, payload in sorted(payloads.items())
        },
        "note": "Random A/C/G/T strings only; no biological sequence templates or reads.",
    }


def generate_fixture_bundle(root):
    """Generate deterministic A/C/G/T FASTQ and reference files; truth stays separate."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    payloads, truth = _fixture_payloads()
    for relative, payload in payloads.items():
        _write(root / relative, payload)
    source = _source_manifest(payloads)
    _write(root / "synthetic_source_manifest.json", _json_bytes(source))
    _write(root / "fixture_truth.json", _json_bytes(truth))
    validate_fixture_bundle(root)
    return root


def validate_fixture_bundle(root):
    """Validate M18's own provenance boundary and every generated input digest."""
    root = Path(root)
    source = json.loads((root / "synthetic_source_manifest.json").read_text(encoding="utf-8"))
    payloads, expected_truth = _fixture_payloads()
    if source != _source_manifest(payloads):
        raise ValueError("M18 synthetic-only provenance guard rejected source manifest")
    for relative, expected_payload in payloads.items():
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"M18 synthetic provenance guard rejected input file: {relative}")
        data = path.read_bytes()
        if data != expected_payload:
            raise ValueError(f"M18 synthetic-only guard rejected altered fixture bytes: {relative}")
    truth = json.loads((root / "fixture_truth.json").read_text(encoding="utf-8"))
    if truth != expected_truth:
        raise ValueError("M18 synthetic-only provenance guard rejected fixture truth")
    for case_id, *_ in CASE_SPECS:
        case_root = root / "datasets" / case_id
        sum(1 for _ in _read_fastq(case_root / "reads.fastq.gz"))
        with (case_root / "reference_roles.csv").open(encoding="utf-8") as handle:
            roles = list(csv.DictReader(handle))
        if len(roles) != 1 or roles[0]["reference_id"] != f"m18-reference-{case_id}":
            raise ValueError("M18 synthetic-only provenance guard rejected reference roles")
    return source


def _stage_ref(stage, artifact):
    return {"stage": stage, "artifact": artifact}


def _build_workflow(root):
    stages = []
    for case_id, _pathway, _label, _seed, _mode in CASE_SPECS:
        case_root = Path("inputs") / "datasets" / case_id
        qc_id, m6_id = f"qc_{case_id}", f"m6_{case_id}"
        m9_id, m10_id = f"m9_{case_id}", f"m10_{case_id}"
        stages.extend([
            {
                "id": qc_id, "kind": "fastq_qc", "config": QC_CONFIG,
                "inputs": {"read1": {
                    "path": (case_root / "reads.fastq.gz").as_posix(),
                    "artifact_type": "raw_read",
                }},
            },
            {
                "id": m6_id, "kind": "residual_evidence",
                "config": {
                    **M6_CONFIG, "sample_id": case_id,
                    "support": {
                        **M6_CONFIG["support"],
                        "min_distinct_fragments": 1000 if case_id == "dna_insufficient_support" else 2,
                    },
                },
                "inputs": {
                    "read1": _stage_ref(qc_id, "clean_single.fastq.gz"),
                    "qc_manifest": _stage_ref(qc_id, "qc.json"),
                    "reference": {
                        "path": (case_root / "reference.fasta").as_posix(),
                        "artifact_type": "raw_fasta",
                    },
                    "roles": {
                        "path": (case_root / "reference_roles.csv").as_posix(),
                        "artifact_type": "reference_roles",
                    },
                },
            },
            {
                "id": m9_id, "kind": "m9_orf_translation", "config": {},
                "inputs": {"candidate_sequence_set": _stage_ref(m6_id, "candidate_sequence_set.json")},
            },
            {
                "id": m10_id, "kind": "m10_exact_first", "config": {},
                "inputs": {
                    "candidate_sequence_set": _stage_ref(m6_id, "candidate_sequence_set.json"),
                    "m9_orf_results": _stage_ref(m9_id, "orf_results.json"),
                },
            },
        ])
    spec = {"schema": "artifact-workflow-v1", "stages": stages}
    _replace_generated(root / "m18-workflow.json", _json_bytes(spec))
    return {"path": "m18-workflow.json"}


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _stage_row(manifest, stage_id):
    stages = manifest.get("stages", [])
    return next((item for item in stages if item.get("id") == stage_id), None)


def _jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _stage_artifacts(output, manifest, stage_id, required):
    """Gate reads on M4 completion and the presence of every required artifact."""
    row = _stage_row(manifest, stage_id)
    raw_status = row.get("status") if row else None
    if row is None:
        report_status = "UNAVAILABLE"
    elif raw_status == "complete":
        report_status = "COMPLETE"
    elif raw_status == "blocked":
        report_status = "BLOCKED"
    elif raw_status in {"dependency_missing", "unavailable"}:
        report_status = "UNAVAILABLE"
    else:
        report_status = "NOT_EVALUATED"

    stage_root = (Path(output) / "stages").resolve()
    base = None
    if row and isinstance(row.get("output_path"), str):
        relative = Path(row["output_path"])
        if not relative.is_absolute() and ".." not in relative.parts:
            candidate = stage_root / relative
            if candidate.resolve().is_relative_to(stage_root) and not candidate.is_symlink():
                base = candidate

    paths = {}
    missing = []
    if report_status == "COMPLETE":
        for name in required:
            path = base / name if base is not None else None
            if (path is None or path.is_symlink() or not path.is_file()
                    or not path.resolve().is_relative_to(stage_root)):
                missing.append(name)
            else:
                paths[name] = path
        if missing:
            report_status = "INCOMPLETE"

    diagnostics = {"m4_status": raw_status or "UNAVAILABLE", "report_status": report_status}
    if row is None:
        diagnostics["reason"] = "M4 execution manifest has no row for this stage."
    else:
        for key in ("error", "reason", "message", "errors", "failure_reason",
                    "dependency_status", "dependency"):
            if key in row:
                diagnostics[key] = row[key]
    if missing:
        diagnostics["missing_artifacts"] = missing
        diagnostics.setdefault("reason", "M4 marked the stage complete but required outputs are missing.")
    return report_status, paths, diagnostics


def _validate_report_payloads(name, payload):
    if name == "m10":
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ValueError("M10 candidate accounting is not a list of JSON objects")
    elif not isinstance(payload, dict) or any(not isinstance(value, dict) for value in payload.values()):
        raise ValueError(f"{name.upper()} artifact bundle is not a JSON object bundle")
    if name == "qc":
        document = payload["qc.json"]
        if not all(isinstance(document.get(section), dict) for section in ("before", "after", "counts")):
            raise ValueError("QC manifest is missing before/after/counts summaries")
        for section in ("before", "after"):
            if not isinstance(document[section].get("reads"), int):
                raise ValueError(f"QC manifest has no integer {section}.reads count")
        if document["before"]["reads"] < document["after"]["reads"]:
            raise ValueError("QC manifest retained more reads than it received")
    elif name == "m6":
        residual = payload["residual_manifest.json"]
        if not isinstance(residual.get("comparison"), dict) or not isinstance(residual.get("counts"), dict):
            raise ValueError("M6 residual manifest is missing comparison/count summaries")
        if not isinstance(residual["comparison"].get("status"), str) or not isinstance(
                residual["comparison"].get("accounted_read_count"), int):
            raise ValueError("M6 residual manifest has incomplete reference-accounting evidence")
        for key in ("residual_fragments", "eligible_fragments", "retained_unassembled_fragments"):
            if not isinstance(residual["counts"].get(key), int):
                raise ValueError(f"M6 residual manifest has no integer {key} count")
        if not isinstance(payload["reconstruction_evidence.json"].get("status"), str):
            raise ValueError("M6 reconstruction evidence has no status")
        support = payload["read_support.json"]
        if not isinstance(support.get("status"), str) or not isinstance(support.get("contigs"), list):
            raise ValueError("M6 read-support evidence is incomplete")
        document = payload["candidate_sequence_set.json"]
        if not isinstance(document.get("availability"), dict) or not isinstance(document.get("records"), list):
            raise ValueError("M6 candidate sequence set is incomplete")
    elif name == "m9":
        document = payload["orf_results.json"]
        if not isinstance(document.get("aggregate_status"), str) or not isinstance(document.get("candidates"), list):
            raise ValueError("M9 ORF results are incomplete")
        for key in ("candidate_count", "expected_orf_count", "observed_orf_count"):
            if not isinstance(document.get(key), int):
                raise ValueError(f"M9 ORF results have no integer {key}")
    elif name == "m10":
        manifest = next((row for row in payload if row.get("record_type") == "manifest"), None)
        if (manifest is None or not isinstance(manifest.get("aggregate_status"), str)
                or not isinstance(manifest.get("candidate_count"), int)
                or not isinstance(manifest.get("required_branches"), list)):
            raise ValueError("M10 candidate accounting has no manifest row")


def _stage_failure_status(report_status):
    if report_status in {"BLOCKED", "UNAVAILABLE"}:
        return report_status
    return "NOT_EVALUATED"


def run(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    input_root = output / "inputs"
    generate_fixture_bundle(input_root)
    validate_fixture_bundle(input_root)
    _build_workflow(output)
    manifest_path = output / "stages" / "workflow.json"
    manifest_before = _sha(manifest_path.read_bytes()) if manifest_path.is_file() else None
    execution_error = None
    try:
        artifact_workflow.run(
            output / "m18-workflow.json", output / "stages",
            artifact_workflow.build_default_registry(),
        )
    except Exception as error:
        execution_error = {"type": type(error).__name__, "message": str(error)}
    if not manifest_path.is_file():
        if execution_error:
            raise RuntimeError(
                "M4 did not leave an execution manifest; no M18 scientific summary can be generated. "
                f"{execution_error['type']}: {execution_error['message']}"
            )
        raise FileNotFoundError("M4 execution manifest was not produced.")
    manifest_after = _sha(manifest_path.read_bytes())
    stale_manifest = execution_error is not None and manifest_before == manifest_after
    try:
        manifest = _read_json(manifest_path) if not stale_manifest else {"status": "execution_error", "stages": []}
        if (not isinstance(manifest, dict) or not isinstance(manifest.get("stages"), list)
                or any(not isinstance(row, dict) for row in manifest["stages"])):
            raise ValueError("M4 execution manifest has an invalid structure")
    except (OSError, ValueError, TypeError) as error:
        manifest = {"status": "invalid_manifest", "stages": []}
        execution_error = execution_error or {
            "type": type(error).__name__, "message": f"M4 execution manifest could not be parsed: {error}"
        }
    if stale_manifest:
        execution_error["stale_manifest_ignored"] = True

    cases = []
    for case_id, pathway, label, seed, mode in CASE_SPECS:
        stages = {
            "qc": _stage_artifacts(output, manifest, f"qc_{case_id}", ["qc.json"]),
            "m6": _stage_artifacts(output, manifest, f"m6_{case_id}", [
                "residual_manifest.json", "reconstruction_evidence.json",
                "read_support.json", "candidate_sequence_set.json",
            ]),
            "m9": _stage_artifacts(output, manifest, f"m9_{case_id}", ["orf_results.json"]),
            "m10": _stage_artifacts(output, manifest, f"m10_{case_id}", ["candidate_accounting.jsonl"]),
        }
        diagnostics = {name: item[2] for name, item in stages.items()
                       if item[2]["report_status"] != "COMPLETE"}
        parsed = {}
        for name, required in (("qc", ["qc.json"]), ("m6", [
                "residual_manifest.json", "reconstruction_evidence.json",
                "read_support.json", "candidate_sequence_set.json"]),
                ("m9", ["orf_results.json"]), ("m10", ["candidate_accounting.jsonl"])):
            report_status, paths, stage_diagnostic = stages[name]
            if report_status == "COMPLETE":
                try:
                    if name == "m10":
                        parsed[name] = _jsonl(paths[required[0]])
                    else:
                        parsed[name] = {
                            artifact: _read_json(paths[artifact]) for artifact in required
                        }
                    if name == "m6":
                        validate_candidate_sequence_set(paths["candidate_sequence_set.json"])
                    _validate_report_payloads(name, parsed[name])
                except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
                    stage_diagnostic["report_status"] = "INCOMPLETE"
                    stage_diagnostic["reason"] = (
                        f"Required stage artifact validation failed: {type(error).__name__}: {error}"
                    )
                    diagnostics[name] = stage_diagnostic
                    parsed[name] = None

        qc_doc = parsed.get("qc", {}).get("qc.json") if parsed.get("qc") else None
        residual = parsed.get("m6", {}).get("residual_manifest.json") if parsed.get("m6") else None
        evidence = parsed.get("m6", {}).get("reconstruction_evidence.json") if parsed.get("m6") else None
        support = parsed.get("m6", {}).get("read_support.json") if parsed.get("m6") else None
        candidate_set = parsed.get("m6", {}).get("candidate_sequence_set.json") if parsed.get("m6") else None
        orfs = parsed.get("m9", {}).get("orf_results.json") if parsed.get("m9") else None
        accounting = parsed.get("m10")
        accounting_manifest = next(
            (row for row in accounting if row.get("record_type") == "manifest"), {}
        ) if accounting is not None else {}
        accounting_candidates = [
            row for row in accounting if row.get("record_type") == "candidate"
        ] if accounting is not None else []
        qc_success = qc_doc is not None and stages["qc"][2]["report_status"] == "COMPLETE"
        m6_success = residual is not None and stages["m6"][2]["report_status"] == "COMPLETE"
        m9_success = orfs is not None and stages["m9"][2]["report_status"] == "COMPLETE"
        m10_success = accounting is not None and stages["m10"][2]["report_status"] == "COMPLETE"
        case = {
            "case_id": case_id, "pathway": pathway,
            "scenario_label": label, "source_dataset": f"inputs/datasets/{case_id}/reads.fastq.gz",
            "source_seed": seed, "m4_stage_statuses": {
                name: diagnostic["m4_status"] for name, diagnostic in
                ((name, stages[name][2]) for name in ("qc", "m6", "m9", "m10"))
            },
            "qc": ({
                "input_reads": qc_doc["before"]["reads"],
                "retained_reads": qc_doc["after"]["reads"],
                "rejected_reads": qc_doc["before"]["reads"] - qc_doc["after"]["reads"],
            } if qc_success else {
                "status": stages["qc"][2]["report_status"],
                "input_reads": None, "retained_reads": None, "rejected_reads": None,
            }),
            "reference_screening": {
                "status": (residual["comparison"]["status"] if m6_success else
                           _stage_failure_status(stages["m6"][2]["report_status"])),
                "accounted_reads": (residual["comparison"]["accounted_read_count"] if m6_success else None),
                "residual_fragments": (residual["counts"]["residual_fragments"] if m6_success else None),
                "eligible_fragments": (residual["counts"]["eligible_fragments"] if m6_success else None),
                "retained_unassembled_fragments": (
                    residual["counts"]["retained_unassembled_fragments"] if m6_success else None
                ),
            },
            "assembly_and_read_back": {
                "status": (evidence["status"] if m6_success else
                           _stage_failure_status(stages["m6"][2]["report_status"])),
                "candidate_availability": (
                    candidate_set["availability"]["state"] if m6_success else
                    _stage_failure_status(stages["m6"][2]["report_status"])
                ),
                "candidate_count": len(candidate_set["records"]) if m6_success else None,
                "support_status": support["status"] if m6_success else "NOT_EVALUATED",
                "candidate_support_statuses": (sorted({
                    record["m6_support_status"] for record in candidate_set["records"]
                }) if m6_success else None),
                "support_thresholds": evidence.get("support_criteria", {}) if m6_success else None,
                "supported_contig_count": (sum(
                    row.get("status") == "READ_SUPPORTED_ASSEMBLY"
                    for row in support.get("contigs", [])
                ) if m6_success else None),
                "assembler": evidence.get("assembler", {}).get("assembler") if m6_success else None,
            },
            "m9_orf_evidence": {
                "aggregate_status": (orfs["aggregate_status"] if m9_success else
                                     _stage_failure_status(stages["m9"][2]["report_status"])),
                "candidate_count": orfs["candidate_count"] if m9_success else None,
                "expected_orf_count": orfs["expected_orf_count"] if m9_success else None,
                "observed_orf_count": orfs["observed_orf_count"] if m9_success else None,
            },
            "m10_architecture_evidence": {
                "aggregate_status": (accounting_manifest.get("aggregate_status", "UNAVAILABLE")
                                     if m10_success else
                                     _stage_failure_status(stages["m10"][2]["report_status"])),
                "candidate_count": accounting_manifest.get("candidate_count") if m10_success else None,
                "branch_statuses": ({
                    branch: sorted({
                        details.get("branch_status", "UNAVAILABLE")
                        for row in accounting_candidates
                        for details in [row.get("branches", {}).get(branch, {})]
                    })
                    for branch in accounting_manifest.get("required_branches", [])
                } if m10_success else None),
            },
            "not_run_or_unavailable": [
                "M8 homology: no biological reference snapshot is used.",
                "M11 RNA folding and all interpretation stages: not part of M18.",
                "DNA circularity/structural-variant analysis: no validated method is registered.",
            ],
            "interpretation_limits": [
                "All reads and reference sequences are deterministic artificial A/C/G/T strings.",
                "RNA/DNA labels are declared fixture metadata, not inferred from FASTQ.",
                "M6 mapping, assembly, and read-back are synthetic technical execution only.",
                "ORFs and M10 repeats do not establish biological identity, function, novelty, or satellite status.",
            ],
        }
        if diagnostics:
            case["stage_diagnostics"] = diagnostics
        if m6_success and evidence.get("status") in {"EXECUTION_FAILED", "DEPENDENCY_MISSING"}:
            case.setdefault("stage_diagnostics", {})["m6"] = {
                "m4_status": stages["m6"][2]["m4_status"],
                "report_status": (
                    "UNAVAILABLE" if evidence["status"] == "DEPENDENCY_MISSING" else "INCOMPLETE"
                ),
                "evidence_status": evidence["status"],
                **{key: evidence[key] for key in ("error", "reason") if key in evidence},
            }
        cases.append(case)
    expected_outcomes = {
        "rna_supported": lambda case: case["assembly_and_read_back"]["candidate_support_statuses"]
        == ["READ_SUPPORTED_ASSEMBLY"],
        "dna_supported": lambda case: case["assembly_and_read_back"]["candidate_support_statuses"]
        == ["READ_SUPPORTED_ASSEMBLY"],
        "rna_reference_only": lambda case: (
            case["assembly_and_read_back"]["candidate_availability"] == "UPSTREAM_UNAVAILABLE"
            and case["reference_screening"]["residual_fragments"] == 0
        ),
        "dna_insufficient_support": lambda case: case["assembly_and_read_back"]["candidate_support_statuses"]
        == ["LOW_SUPPORT_ASSEMBLY"],
    }
    for case in cases:
        case["expected_fixture_outcome_met"] = expected_outcomes[case["case_id"]](case)
    integration_complete = (
        manifest.get("status") == "complete"
        and all(case["expected_fixture_outcome_met"] for case in cases)
    )
    report = {
        "schema": SCHEMA, **SYNTHETIC_FLAGS,
        "workflow_status": manifest.get("status", "not_evaluated"),
        "integration_status": "COMPLETE" if integration_complete and not execution_error else "INCOMPLETE",
        "execution_manifest": "stages/workflow.json",
        "source_manifest": "inputs/synthetic_source_manifest.json",
        "cases": cases,
        "interpretation_limits": [
            "Synthetic execution validates software paths, not biological discovery performance.",
            "M6 read-back uses the same generated fragments supplied to assembly and is not independent evidence.",
            "No real reads, biological reference data, HCoV-229E pilot, or high-risk workflow is used.",
        ],
        "m19_backlog": [
            "Add a separately approved synthetic benchmark matrix for read error, coverage, and reference-divergence factors.",
            "Evaluate optional read-pair layouts and assembler versions with resource-bounded integration tests.",
            "Add explicitly declared artificial reference snapshots to test M8 homology without biological curation.",
        ],
    }
    if execution_error:
        report["execution_error"] = execution_error
    _replace_generated(output / "m18-report.json", _json_bytes(report))
    rows = [
        "<!doctype html><meta charset='utf-8'><title>M18 synthetic workflow</title>",
        "<h1>M18 synthetic read-to-candidate workflow</h1>",
        f"<p>M4: {html.escape(str(report['workflow_status']))}; M18: "
        f"{html.escape(report['integration_status'])}. Artificial reads only; "
        "technical execution is not biological validation.</p>",
        "<table><thead><tr><th>Case</th><th>Pathway</th><th>QC retained/rejected</th>",
        "<th>M6 status</th><th>Candidate availability</th><th>Read-back support</th>",
        "<th>M9 ORFs</th><th>M10 scope</th><th>Stage diagnostics</th></tr></thead><tbody>",
    ]
    for case in cases:
        rows.append("<tr>" + "".join(
            f"<td>{html.escape(str(value))}</td>" for value in (
                case["case_id"], case["pathway"],
                f'{case["qc"]["retained_reads"]}/{case["qc"]["rejected_reads"]}',
                case["assembly_and_read_back"]["status"],
                case["assembly_and_read_back"]["candidate_availability"],
                case["assembly_and_read_back"]["support_status"],
                case["m9_orf_evidence"]["observed_orf_count"],
                ", ".join(
                    f"{branch}:{'|'.join(statuses)}"
                    for branch, statuses in
                    (case["m10_architecture_evidence"]["branch_statuses"] or {}).items()
                ),
                "; ".join(
                    f"{stage}: {detail.get('report_status')} — "
                    f"{detail.get('reason') or detail.get('error') or 'incomplete'}"
                    for stage, detail in case.get("stage_diagnostics", {}).items()
                ),
            )
        ) + "</tr>")
    rows.extend(["</tbody></table><h2>Interpretation limits</h2><ul>"])
    rows.extend(f"<li>{html.escape(item)}</li>" for item in report["interpretation_limits"])
    rows.extend(["</ul>"])
    _replace_generated(output / "m18-report.html", ("\n".join(rows) + "\n").encode("utf-8"))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the synthetic-only M18 FASTQ-to-candidate workflow"
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = run(args.output)
    print(f"M18 {result['workflow_status']}: {len(result['cases'])} synthetic datasets")
    print(Path(args.output).resolve() / "m18-report.html")
    return 0 if result["integration_status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
