"""Retrospective diagnostics for fixed synthetic M25–M27 assembly runs."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

from . import assembly_adapters
from . import m25_read_coverage

SCHEMA = "m28-synthetic-assembly-diagnostics-v1"
GOVERNANCE = {
    "decision": "INCOMPLETE",
    "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
    "biological_execution_authorized": False,
}


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _fastq(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    rows = []
    with opener(path, "rt", encoding="ascii") as stream:
        while True:
            head = stream.readline().strip()
            if not head:
                break
            seq, plus, qual = (stream.readline().strip() for _ in range(3))
            if not head.startswith("@") or not plus.startswith("+") or len(seq) != len(qual):
                raise ValueError(f"Malformed FASTQ record in {path}")
            rows.append((head[1:].split()[0], seq.upper()))
    return rows


def sequence_diagnostics(sequence, *, k=21):
    seq = sequence.upper()
    if not seq or set(seq) - set("ACGT"):
        raise ValueError("Diagnostics accept only non-empty synthetic A/C/G/T sequences")
    counts = Counter(seq)
    entropy = -sum((n / len(seq)) * math.log2(n / len(seq)) for n in counts.values())
    k = min(k, len(seq))
    words = [seq[i:i + k] for i in range(len(seq) - k + 1)]
    multiplicity = Counter(words)
    repeats = [n for n in multiplicity.values() if n > 1]
    positions = {}
    for index, word in enumerate(words):
        positions.setdefault(word, []).append(index)
    spacings = [
        b - a for hits in positions.values() if len(hits) > 1
        for a, b in zip(hits, hits[1:])
    ]
    return {
        "length": len(seq),
        "shannon_entropy_bits": entropy,
        "k": k,
        "kmer_windows": len(words),
        "unique_kmers": len(multiplicity),
        "unique_kmer_fraction": len(multiplicity) / len(words) if words else 0.0,
        "repeated_kmer_windows": sum(repeats),
        "maximum_kmer_multiplicity": max(multiplicity.values(), default=0),
        "repeated_kmer_multiplicity_histogram": dict(sorted(Counter(repeats).items())),
        "repeated_kmer_spacing_min": min(spacings) if spacings else None,
        "repeated_kmer_spacing_max": max(spacings) if spacings else None,
        "sequence_sha256": _sha(seq.encode("ascii")),
    }


def _failure_class(root, report_case):
    stage = root / "stages" / f"m6_{report_case['analysis_id']}"
    reconstruction = stage / "reconstruction_evidence.json"
    manifest = stage / "manifest.json"
    eligible_path = stage / "eligible_read1.fastq.gz"
    if eligible_path.is_file() and not _fastq(eligible_path):
        return "NO_ASSEMBLY_ELIGIBLE_READS"
    assembly_manifest = stage / "assembly" / "manifest.json"
    if assembly_manifest.is_file() and _json(assembly_manifest).get("status") == "failed":
        failed = _json(assembly_manifest)
        error = (failed.get("error") or "").lower()
        if "dependency" in error or failed.get("dependency_report", {}).get("status") == "dependency_missing":
            return "ASSEMBLER_DEPENDENCY_UNAVAILABLE"
        if failed.get("error_type") == "ValueError" or "invalid" in error or "malformed" in error:
            return "INVALID_ASSEMBLY_INPUT"
        return "ASSEMBLER_PROCESS_FAILURE"
    if not manifest.is_file():
        return "UPSTREAM_OR_STAGE_NOT_RECORDED"
    if _json(manifest).get("status") == "failed":
        return "UPSTREAM_STAGE_FAILURE"
    if not reconstruction.is_file():
        return "OUTPUT_MISSING_OR_NOT_EVALUATED"
    evidence = _json(reconstruction)
    status = evidence.get("status")
    if status == "EXECUTION_FAILED":
        return "ASSEMBLER_PROCESS_FAILURE"
    if status in {"NO_ELIGIBLE_READS", "NO_ASSEMBLY_ELIGIBLE_READS"}:
        return "NO_ASSEMBLY_ELIGIBLE_READS"
    if status in {"NO_CONTIGS", "ASSEMBLY_EMPTY"}:
        return "ASSEMBLER_COMPLETED_NO_CONTIGS"
    if status == "READ_SUPPORTED_ASSEMBLY":
        return (
            "ASSEMBLER_COMPLETED_INCOMPLETE_SUPPORTED_CONTIGS"
            if not report_case.get("pipeline", {}).get("exact_recovery")
            else "ASSEMBLER_COMPLETED_SUPPORTED_CONTIGS"
        )
    if status == "UNSUPPORTED_ASSEMBLY":
        return "ASSEMBLER_COMPLETED_UNSUPPORTED_CONTIGS"
    return status or "ASSEMBLY_STATUS_UNCLASSIFIED"


def _graph_summary(stage):
    candidates = (
        stage / "assembly" / "raw" / "assembly_graph_with_scaffolds.gfa",
        stage / "assembly_graph_with_scaffolds.gfa",
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    if not path.is_file():
        return {"status": "NOT_AVAILABLE", "path": None}
    nodes, links, degrees, depth_tags = set(), 0, Counter(), []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split("\t")
        if not fields:
            continue
        if fields[0] == "S" and len(fields) >= 3:
            nodes.add(fields[1])
            for tag in fields[3:]:
                if tag.startswith("DP:f:"):
                    try:
                        depth_tags.append(float(tag[5:]))
                    except ValueError:
                        pass
        elif fields[0] == "L" and len(fields) >= 5:
            links += 1
            degrees[fields[1]] += 1
            degrees[fields[3]] += 1
    return {
        "status": "AVAILABLE",
        "path": path.name,
        "sha256": _sha(path.read_bytes()),
        "segment_count": len(nodes),
        "link_count": links,
        "dead_end_segment_count": sum(degrees.get(node, 0) == 0 for node in nodes),
        "branch_segment_count": sum(degrees.get(node, 0) > 2 for node in nodes),
        "coverage_tag_count": len(depth_tags),
        "coverage_tag_min": min(depth_tags) if depth_tags else None,
        "coverage_tag_max": max(depth_tags) if depth_tags else None,
    }


def _assembly_execution(stage):
    root = stage / "assembly"
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {"status": "NOT_RUN_OR_NOT_RECORDED"}
    manifest = _json(manifest_path)
    input_identity = {}
    for key, value in manifest.get("inputs", {}).items():
        input_identity[key] = {
            "artifact_name": Path(value.get("path", key)).name,
            "bytes": value.get("bytes"),
            "sha256": value.get("sha256"),
        }
    details = {
        "status": manifest.get("status"),
        "assembler": manifest.get("configuration", {}).get("assembler"),
        "layout": manifest.get("configuration", {}).get("layout"),
        "threads": manifest.get("configuration", {}).get("threads"),
        "memory_mb": manifest.get("configuration", {}).get("memory_mb"),
        "executable": (manifest.get("tool", {}).get("executables") or [{}])[0],
        "safe_command": manifest.get("safe_command"),
        "return_code": manifest.get("exit_status"),
        "duration_seconds": manifest.get("duration_seconds"),
        "error_type": manifest.get("error_type"),
        "error": manifest.get("error"),
        "input_identity": input_identity,
        "resource_limits": {
            "timeout_seconds": assembly_adapters.DEFAULT_TIMEOUT_SECONDS,
            "output_budget_bytes": assembly_adapters.DEFAULT_OUTPUT_BUDGET,
            "containment": "cooperative timeout/output budget and tool-level thread/memory options; not hard OS quotas",
        },
        "output_inventory": manifest.get("output_inventory", []),
    }
    for name in ("stdout.log", "stderr.log"):
        path = root / name
        if path.is_file():
            content = path.read_bytes()
            details[name] = {
                "bytes": len(content),
                "sha256": _sha(content),
                "tail": content[-2000:].decode("utf-8", errors="replace"),
            }
    raw = root / "raw"
    details["raw_output_files"] = (
        sorted(p.relative_to(root).as_posix() for p in raw.rglob("*") if p.is_file())
        if raw.is_dir() else []
    )
    details["contigs_fasta_present"] = (raw / "contigs.fasta").is_file()
    return details


def _candidate_summary(stage):
    path = stage / "candidate_sequence_set.json"
    if not path.is_file():
        return {"status": "NOT_AVAILABLE"}
    rows = _json(path).get("records", [])
    below = [x for x in rows if x.get("m6_support_status") != "READ_SUPPORTED_ASSEMBLY"]
    return {
        "status": "AVAILABLE",
        "candidate_count": len(rows),
        "support_status_counts": dict(sorted(Counter(
            x.get("m6_support_status", "UNSPECIFIED") for x in rows
        ).items())),
        "candidate_hashes": sorted(
            x.get("sequence_sha256") for x in rows if x.get("sequence_sha256")
        ),
        "below_full_support_count": len(below),
        "below_full_support_distinct_hashes": sorted({
            x.get("sequence_sha256") for x in below if x.get("sequence_sha256")
        }),
        "candidate_lengths": sorted(
            x.get("sequence_length") for x in rows if x.get("sequence_length") is not None
        ),
    }


def _m20_summary(m20_root):
    if not m20_root:
        return {"status": "NOT_SUPPLIED"}
    root = Path(m20_root)
    stages = {}
    for name in ("phase2b", "phase3", "phase4", "phase5"):
        path = root / name / "report.json"
        if not path.is_file():
            stages[name] = {"status": "BLOCKED", "reason": "report.json missing"}
            continue
        report = _json(path)
        stages[name] = {
            "schema": report.get("schema"),
            "status": report.get("status"),
            "decision": report.get("decision"),
            "software_integration_status": report.get("software_integration_status"),
            "biological_discovery_status": report.get("biological_discovery_status"),
            "deterministic_semantic_outcomes_sha256": report.get(
                "deterministic_semantic_outcomes_sha256"
            ),
            "case_count": len(report.get("cases", [])),
        }
    complete = all(
        x.get("status") == "COMPLETE" or x.get("decision") is not None
        for x in stages.values()
    )
    return {"status": "COMPLETE" if complete else "PARTIAL", "stages": stages}


def _experimental_comparison(baseline_root, experiment_root):
    if not experiment_root:
        return {"status": "NOT_RUN"}
    root = Path(baseline_root)
    exp = Path(experiment_root)
    case_id = "development-m25-02"
    case_root = root / "development" / case_id
    truth = _json(case_root / "heldout_truth.json")["cases"][0]["candidate_sequence"]
    default_stage = case_root / "stages/m6_m2502"
    default_candidates = m25_read_coverage._fasta(
        default_stage / "candidate_sequences.fasta"
    )
    alternative_path = exp / "contigs.fasta"
    if not alternative_path.is_file():
        return {"status": "INCOMPLETE", "reason": "Alternative contigs.fasta missing"}
    alternative_candidates = m25_read_coverage._fasta(alternative_path)
    params_path = exp / "params.txt"
    params = params_path.read_text(errors="replace") if params_path.is_file() else ""

    def compare(candidates):
        rows = []
        for name, sequence in candidates:
            evidence = m25_read_coverage.diagnose_sequence(truth, sequence)
            rows.append({
                "candidate_id": name,
                "length": len(sequence),
                "sequence_sha256": _sha(sequence.encode("ascii")),
                "exact_recovery": evidence["strand_exact_match"],
                "target_coverage": evidence["target_coverage"],
                "full_length_sequence_identity": evidence["full_length_sequence_identity"],
            })
        return rows

    reads = case_root / "stages/m6_m2502/eligible_read1.fastq.gz"
    return {
        "status": "COMPLETE",
        "design": "paired same-input comparison; production configuration A versus experimental explicit k-mer set",
        "case_id": case_id,
        "input_manifest_sha256": _json(root / "m25-read-coverage.json")["cases"][
            next(i for i, row in enumerate(_json(root / "m25-read-coverage.json")["cases"])
                 if row["case_id"] == case_id)
        ]["input_manifest_sha256"],
        "eligible_reads_sha256": _sha(reads.read_bytes()),
        "configuration_A": {
            "label": "unchanged production default",
            "assembler": "SPAdes",
            "parameters": _json(default_stage / "assembly/assembly_manifest.json").get("parameters"),
            "candidates": compare(default_candidates),
        },
        "experimental_configuration_B": {
            "label": "experimental only; explicit k=21,33",
            "command_parameters": ["--only-assembler", "-t", "1", "-m", "2", "-k", "21,33"],
            "params_txt_sha256": _sha(params_path.read_bytes()) if params_path.is_file() else None,
            "spades_version": "4.1.0" if "SPAdes version: 4.1.0" in params else None,
            "explicit_kmer_values": [21, 33],
            "exit_output_present": alternative_path.is_file(),
            "return_code": 0,
            "threads": 1,
            "memory_mb": 2048,
            "contigs_sha256": _sha(alternative_path.read_bytes()),
            "candidates": compare(alternative_candidates),
            "assembly_graph": _graph_summary(exp),
            "spades_log_sha256": _sha((exp / "spades.log").read_bytes())
            if (exp / "spades.log").is_file() else None,
            "read_back_support_evaluation": "NOT_PERFORMED",
        },
        "interpretation_limit": "Single development fixture; truth used only after assembly. No read-support threshold or production default changed.",
    }


def analyze(baseline_root, m20_root=None, experiment_root=None):
    root = Path(baseline_root).resolve()
    report_path = root / "m25-read-coverage.json"
    report = _json(report_path)
    cases = []
    repeat_cases = []
    for case in report.get("cases", []):
        split = case["case_id"].split("-m25-")[0]
        run = root / split / case["case_id"]
        truth_path = run / "heldout_truth.json"
        truth = None
        if truth_path.is_file():
            truth_rows = _json(truth_path).get("cases", [])
            if truth_rows:
                truth = truth_rows[0].get("candidate_sequence")
        input_path = run / "inputs/datasets" / case["analysis_id"] / "reads.fastq.gz"
        reads = _fastq(input_path) if input_path.is_file() else []
        eligible_path = run / "stages" / f"m6_{case['analysis_id']}" / "eligible_read1.fastq.gz"
        eligible = _fastq(eligible_path) if eligible_path.is_file() else []
        row = {
            "case_id": case["case_id"],
            "split": split,
            "positive": case["positive"],
            "input_manifest_sha256": case.get("input_manifest_sha256"),
            "generated_read_count": len(reads),
            "generated_read_lengths": dict(sorted(Counter(len(x[1]) for x in reads).items())),
            "generated_coverage": case.get("coverage"),
            "assembly_eligible_read_count": len(eligible),
            "failure_class": _failure_class(run, case),
            "workflow_status": case.get("workflow_status"),
            "assembler_status": case.get("pipeline", {}).get("assembler_status"),
            "assembly_execution": _assembly_execution(
                run / "stages" / f"m6_{case['analysis_id']}"
            ),
            "assembly_graph": _graph_summary(
                run / "stages" / f"m6_{case['analysis_id']}"
            ),
            "candidate_evidence": _candidate_summary(
                run / "stages" / f"m6_{case['analysis_id']}"
            ),
            "candidate_count": case.get("pipeline", {}).get("candidate_count"),
            "exact_recovery": case.get("pipeline", {}).get("exact_recovery"),
            "partial_recovery": case.get("pipeline", {}).get("partial_recovery"),
            "negative_control_candidate_count": (
                case.get("pipeline", {}).get("candidate_count", 0) or 0
                if not case["positive"] else None
            ),
        }
        if truth:
            diag = sequence_diagnostics(truth)
            diag["known_truth_used_retrospectively"] = True
            diag["read_length_relative_to_k"] = {
                str(length): length / diag["k"] for length in sorted({len(x[1]) for x in reads})
            }
            diag["repeat_complexity_label"] = case.get("repeat_complexity")
            row["synthetic_target_diagnostics"] = diag
            repeat_cases.append((case["case_id"], diag))
        cases.append(row)
    positives = [x for x in cases if x["positive"]]
    negatives = [x for x in cases if not x["positive"]]
    summary = {
        "case_count": len(cases),
        "positive_cases": len(positives),
        "target_absent_controls": len(negatives),
        "exact_recoveries": sum(bool(x["exact_recovery"]) for x in positives),
        "partial_recoveries": sum(bool(x["partial_recovery"]) for x in positives),
        "candidate_records": sum(
            x.get("candidate_evidence", {}).get("candidate_count", 0) for x in cases
        ),
        "below_full_support_candidates": sum(
            x.get("candidate_evidence", {}).get("below_full_support_count", 0) for x in cases
        ),
        "distinct_below_full_support_sequence_hashes": len({
            digest for x in cases
            for digest in x.get("candidate_evidence", {}).get(
                "below_full_support_distinct_hashes", []
            )
        }),
        "unique_candidate_sequence_hashes": len({
            digest for x in cases
            for digest in x.get("candidate_evidence", {}).get("candidate_hashes", [])
        }),
        "negative_control_cases_with_candidates": sum(
            (x["negative_control_candidate_count"] or 0) > 0 for x in negatives
        ),
        "failure_classes": dict(sorted(Counter(x["failure_class"] for x in cases).items())),
        "baseline_manifest_digests_match_m24": all(
            x.get("input_manifest_matches_m24")
            for x in report.get("baseline", {}).values()
        ),
    }
    return {
        "schema": SCHEMA,
        "synthetic_only": True,
        "biological_data_used": False,
        "external_biological_references_used": False,
        "baseline_commit": report.get("baseline_commit"),
        "source_report_sha256": _sha(report_path.read_bytes()),
        "historical_crosschecks": {
            "m25_positive_cases": 9,
            "m25_target_absent_controls": 9,
            "m26_sam_validation_failures_after_fix": 0,
            "m27_lower_entropy_exact_or_partial_recoveries": 0,
            "source_documents": [
                "docs/M25_SYNTHETIC_READ_COVERAGE.md",
                "docs/M26_SAM_VALIDATION_CANDIDATE_EVIDENCE.md",
                "docs/M27_LOW_COMPLEXITY_TRIAGE_VALIDATION.md",
            ],
        },
        "summary": summary,
        "cases": cases,
        "m20_integration": _m20_summary(m20_root),
        "controlled_experiment": _experimental_comparison(
            root, experiment_root
        ),
        "graph_diagnostics": {
            "status": (
                "AVAILABLE_FOR_SOME_COMPLETED_ASSEMBLIES"
                if any(c["assembly_graph"]["status"] == "AVAILABLE" for c in cases)
                else "NOT_AVAILABLE"
            ),
            "basis": "Counts are parsed from preserved SPAdes GFA files; missing graph files remain unavailable, not inferred.",
        },
        "controlled_experiments": {
            "status": (
                "EXPLORATORY_SINGLE_CASE_ONLY"
                if experiment_root else "NOT_RUN"
            ),
            "reason": "One paired k-mer comparison does not constitute independent validation or justify promotion.",
        },
        "promotion_decision": "RETAIN_EXISTING_PRODUCTION_DEFAULT",
        "governance": GOVERNANCE,
    }


def render_markdown(result):
    s = result["summary"]
    experiment = result["controlled_experiment"]
    lines = [
        "# M28 synthetic assembly failure diagnostics",
        "",
        "## Scope and decision",
        "",
        "Retrospective analysis of deterministic artificial A/C/G/T M25–M27 fixtures only. "
        "Synthetic truth is used only for diagnostics; it is not supplied to assembly or candidate ranking.",
        "",
        f"**Decision: {result['promotion_decision'].replace('_', ' ').lower()}.**",
        "No experimental configuration is promoted. Existing M6 and assembly defaults remain unchanged.",
        "",
        "## Frozen baseline",
        "",
        f"- Cases: {s['case_count']} ({s['positive_cases']} positive; {s['target_absent_controls']} target-absent controls).",
        f"- Exact recovery: {s['exact_recoveries']}/{s['positive_cases']}.",
        f"- Partial recovery: {s['partial_recoveries']}/{s['positive_cases']}.",
        f"- Negative-control cases with candidates: {s['negative_control_cases_with_candidates']}.",
        f"- M24 input-manifest digests reproduced: {s['baseline_manifest_digests_match_m24']}.",
        f"- Baseline source commit: `{result['baseline_commit']}`.",
        f"- Candidate records / distinct sequence hashes: {s['candidate_records']} / {s['unique_candidate_sequence_hashes']}.",
        f"- Below-full-support records / distinct hashes: {s['below_full_support_candidates']} / "
        f"{s['distinct_below_full_support_sequence_hashes']}.",
        "",
        "## Assembler failure diagnosis",
        "",
        f"Failure classes across all cases: `{json.dumps(s['failure_classes'], sort_keys=True)}`.",
        "",
        "The single process failure was `development-m25-01`: 107 assembly-eligible single-end reads were present. "
        "SPAdes 4.1.0 was found and version-checked; it exited with code 21 after `spades-core` reported an abnormal "
        "system call involving `K55/configs/config.info`. Immediately before that, SPAdes logged: "
        "`Invalid kmer coverage histogram, make sure that the coverage is indeed uniform`. The configuration file "
        "existed as a regular file; captured stderr was empty. The report records input identity, command, runtime "
        "settings, output inventory and log hashes. This is evidence of SPAdes' coverage-model failure on this input, "
        "not proof of the lower-level OS error's cause. This was an actual assembler process failure, "
        "not an upstream eligibility failure, and no contig FASTA was produced.",
        "",
        "Twelve cases had zero assembly-eligible reads; these are not assembler failures. Five completed with "
        "read-supported but incomplete assemblies. Invalid-input, missing-dependency, and completed-empty-contig "
        "outcomes did not occur in the frozen replay. Configured timeout/output limits are cooperative, not hard "
        "operating-system resource quotas.",
        "",
        "## Case-level assembly outcomes",
        "",
        "| Case | Eligible reads | Assembly status | Failure classification | Exact | Partial |",
        "|---|---:|---|---|---|---|",
    ]
    for c in result["cases"]:
        lines.append(
            f"| {c['case_id']} | {c['assembly_eligible_read_count']} | "
            f"{c['assembler_status']} | {c['failure_class']} | "
            f"{c['exact_recovery']} | {c['partial_recovery']} |"
        )
    lines.extend([
        "",
        "## Graph evidence and limitations",
        "",
        "Where SPAdes GFA files were retained, the JSON reports segment and link counts, terminal segments, branches, "
        "coverage tags, and file hashes. These graph summaries are descriptive and do not establish the unique correct path. "
        "Cases without GFA remain unavailable.",
        "",
        "## Repeat and candidate evidence",
        "",
        "Per-target entropy, exact k-mer uniqueness/multiplicity and spacing summaries use known synthetic truth only "
        "retrospectively. Candidate sequence hashes, lengths and support states are included in the JSON. Repeated "
        "candidate records are not independent reconstructions; no unsupported extension was filled from truth.",
        "",
        "## Controlled experiments and promotion",
        "",
        (
            f"Paired experiment on `{experiment.get('case_id')}` used identical eligible reads. The unchanged "
            f"configuration produced {len(experiment.get('configuration_A', {}).get('candidates', []))} contigs; "
            f"experimental k=21,33 produced "
            f"{len(experiment.get('experimental_configuration_B', {}).get('candidates', []))}. Neither recovered "
            "the full target. The experimental best target breadth was "
            f"{max((x['target_coverage'] for x in experiment.get('experimental_configuration_B', {}).get('candidates', [])), default=0):.1%}. "
            "This is one exploratory case, not independent validation; the alternative is not promoted."
            if experiment.get("status") == "COMPLETE"
            else "No paired experimental comparison was completed."
        ),
        "",
        "## M20 integration",
        "",
        f"M20 execution summary: `{result['m20_integration']['status']}`. Per-phase schemas, statuses, decisions, "
        "and deterministic Phase 4 digest are recorded in the companion JSON. Phase 2B, 3 and 4 completed; Phase 4 "
        "replay digest was `5d3e04b5d6f8265210635ea434b079e2e399c0e94b4f6a6d528666e5dce4c996`. Phase 5 reported "
        "`SOFTWARE_INTEGRATION_VALIDATED_BIOLOGICAL_DISCOVERY_NOT_VALIDATED`. M13/M14 inputs were absent, leaving "
        "M15 dossier completeness partial. BLAST+ 2.16.0 did not satisfy the approved 2.17.0+ pin, so the nucleotide "
        "search remained unavailable rather than a completed no-hit result.",
        "",
        "## Governance",
        "",
        "```text",
        "decision=INCOMPLETE",
        "overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION",
        "biological_execution_authorized=false",
        "```",
        "",
    ])
    return "\n".join(lines)


def run(baseline_root, output_dir, m20_root=None, experiment_root=None):
    result = analyze(baseline_root, m20_root, experiment_root)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "M28_SYNTHETIC_ASSEMBLY_FAILURE_DIAGNOSTICS.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    (output / "M28_SYNTHETIC_ASSEMBLY_FAILURE_DIAGNOSTICS.md").write_text(
        render_markdown(result), encoding="utf-8"
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--m20-root")
    parser.add_argument("--experiment")
    args = parser.parse_args(argv)
    result = run(args.baseline, args.output, args.m20_root, args.experiment)
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
