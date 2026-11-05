"""Synthetic-only M30 audit of existing candidate evidence and specificity."""
import argparse
import hashlib
import json
import platform
import random
import shutil
import subprocess
from pathlib import Path

from .m8_blastn_profile import BLAST_RELEASE, is_supported_runtime


GOVERNANCE = {
    "decision": "INCOMPLETE",
    "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
    "biological_execution_authorized": False,
}
SCHEMA = "m30-synthetic-candidate-specificity-v1"
CASES = (
    ("development", "target_like_supported"),
    ("development", "background_supported"),
    ("development", "near_target_decoy"),
    ("development", "repeat_challenge"),
    ("tuning", "truncated_target"),
    ("tuning", "unsupported_exact_target"),
    ("held_out", "target_like_supported"),
    ("held_out", "background_supported"),
    ("held_out", "near_target_decoy"),
    ("held_out", "target_absent"),
    ("held_out", "ambiguous_insufficient_evidence"),
)


def _sequence(seed, length):
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(length))


def _digest(text):
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _fixture_rows():
    target = _sequence(3001, 900)
    rows, truth = [], []
    for index, (split, scenario) in enumerate(CASES, 1):
        cid = f"m30q{index:03d}"
        if scenario in {"target_like_supported", "unsupported_exact_target"}:
            seq = target
            has_target = True
        elif scenario == "near_target_decoy":
            source = list(target)
            rng = random.Random(3100 + index)
            for pos in rng.sample(range(len(source)), 55):
                source[pos] = next(base for base in "ACGT" if base != source[pos])
            seq, has_target = "".join(source), False
        elif scenario == "repeat_challenge":
            seq, has_target = "ACGT" * 225, False
        elif scenario == "truncated_target":
            seq, has_target = target[:320], False
        elif scenario == "ambiguous_insufficient_evidence":
            seq, has_target = target, True
        elif scenario == "target_absent":
            seq, has_target = "", False
        else:
            seq, has_target = _sequence(9000 + index, 900), False
        support = (
            "UNSUPPORTED_ASSEMBLY" if scenario == "unsupported_exact_target"
            else "AMBIGUOUS_ASSEMBLY" if scenario == "ambiguous_insufficient_evidence"
            else "READ_SUPPORTED_ASSEMBLY" if scenario in {
                "target_like_supported", "background_supported", "near_target_decoy",
                "repeat_challenge", "truncated_target",
            } else "NOT_EVALUATED"
        )
        rows.append({
            "candidate_id": cid,
            "source_case_id": cid,
            "split": split,
            "sequence": seq,
            "sequence_sha256": _digest(seq) if seq else None,
            "sequence_length": len(seq),
            "m6_support_status": support,
            "support_provenance": "synthetic_fixture_declaration_not_measured_M6_evidence",
        })
        truth.append({
            "candidate_id": cid,
            "scenario": scenario,
            "target_present": has_target,
            "target_sequence_sha256": _digest(target) if has_target else None,
        })
    return rows, truth


def _tool_version(command):
    executable = shutil.which(command)
    if not executable:
        return {"path": None, "version": None}
    try:
        proc = subprocess.run(
            [executable, "-version"], capture_output=True, text=True,
            timeout=10, check=False,
        )
        first = (proc.stdout or proc.stderr).splitlines()[0]
        version = first.split()[-1].rstrip(",") if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, IndexError):
        version = None
    return {"path": executable, "version": version}


def audit_runtime():
    blastn = _tool_version("blastn")
    makeblastdb = _tool_version("makeblastdb")
    supported = is_supported_runtime(
        platform.system(), platform.machine(), blastn["version"],
        makeblastdb["version"],
    )
    if supported:
        reason = (
            "Pinned M8 toolchain is present, but M30 does not contain an "
            "M6-produced candidate handoff and approved frozen reference snapshot."
        )
        status = "NOT_EVALUATED"
    else:
        reason = (
            f"M8 requires verified {BLAST_RELEASE} on Linux x86_64; detected "
            f"blastn={blastn['version']!r}, makeblastdb={makeblastdb['version']!r}."
        )
        status = "DEPENDENCY_UNAVAILABLE"
    return {
        "m7": {
            "status": "NOT_EVALUATED",
            "reason": "M7 recurrence requires independent, provenance-backed observations; synthetic candidate fixtures do not provide them.",
            "role": "Optional recurrence/context evidence; not a classifier.",
        },
        "m8": {
            "status": status,
            "reason": reason,
            "blastn": blastn,
            "makeblastdb": makeblastdb,
            "role": "Frozen nucleotide similarity evidence only; M8 does not accept or reject satellite-virus candidates.",
        },
        "m9_m15": {
            "status": "NO_END_TO_END_ACCEPTANCE_STAGE",
            "reason": "Available downstream stages produce ORF, repeat, RNA-fold, review, evidence-dossier, descriptive and provenance outputs; none implements a frozen final satellite-virus acceptance classifier.",
        },
        "m9": {"status": "AVAILABLE_EVIDENCE_STAGE", "role": "ORF translation/protein-search evidence; not identity or acceptance."},
        "m10": {"status": "AVAILABLE_EVIDENCE_STAGE", "role": "Repeat and sequence-pattern evidence; not acceptance."},
        "m11": {"status": "AVAILABLE_PREDICTION_STAGE", "role": "RNA fold predictions; prediction is not demonstrated function."},
        "m12": {"status": "AVAILABLE_REVIEW_STAGE", "role": "Artifact review and evidence validation; not an automated final classifier."},
        "m13": {"status": "AVAILABLE_DOSSIER_STAGE", "role": "Evidence dossier; does not establish candidate identity."},
        "m14": {"status": "AVAILABLE_DESCRIPTIVE_STAGE", "role": "Descriptive observations; not classification."},
        "m15": {"status": "AVAILABLE_PROVENANCE_STAGE", "role": "Provenance and workflow-state reporting; not biological acceptance."},
    }


def _metrics(rows, truth_by_id):
    scored = [
        row for row in rows
        if row.get("screening_status") == "COMPLETED"
        and row.get("final_acceptance_status") in {"ACCEPTED", "REJECTED"}
        and row["candidate_id"] in truth_by_id
    ]
    if not scored:
        return {
            "status": "NOT_EVALUATED",
            "reason": "No candidate completed an end-to-end discovery-specific acceptance pathway.",
            "denominator": 0,
            "true_positives": "NOT_EVALUATED",
            "false_positives": "NOT_EVALUATED",
            "true_negatives": "NOT_EVALUATED",
            "false_negatives": "NOT_EVALUATED",
            "sensitivity": "NOT_EVALUATED",
            "specificity": "NOT_EVALUATED",
            "precision": "NOT_EVALUATED",
            "false_discovery_proportion": "NOT_EVALUATED",
            "confidence_intervals": "NOT_EVALUATED",
        }
    return {"status": "NOT_EVALUATED", "reason": "Scoring for completed classifiers is not enabled in this diagnostic; no frozen end-to-end classifier exists.", "denominator": len(scored)}


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    inputs, truth = _fixture_rows()
    runtime = audit_runtime()
    m29_path = Path(__file__).parents[1] / "docs" / "M29_ASSEMBLY_ROOT_CAUSE_RECOVERY.json"
    m29_prior = json.loads(m29_path.read_text(encoding="utf-8")) if m29_path.is_file() else None
    screening = [{
        "candidate_id": row["candidate_id"],
        "source_case_id": row["source_case_id"],
        "split": row["split"],
        "sequence_sha256": row["sequence_sha256"],
        "assembly_status": "SYNTHETIC_FIXTURE_ONLY",
        "read_support_status": row["m6_support_status"],
        "read_support_provenance": row["support_provenance"],
        "m7_status": "NOT_EVALUATED",
        "m8_status": runtime["m8"]["status"],
        "m8_reason": runtime["m8"]["reason"],
        "m9_m15_status": runtime["m9_m15"]["status"],
        "m9_m15_reason": runtime["m9_m15"]["reason"],
        "screening_stages_executed": [],
        "evidence_used_for_acceptance": [],
        "final_acceptance_status": "NOT_EVALUATED",
        "final_status_reason": "No existing stage implements frozen end-to-end candidate acceptance.",
    } for row in inputs]
    truth_by_id = {row["candidate_id"]: row for row in truth}
    result = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "biological_data_used": False,
        "external_biological_queries": False,
        "production_defaults_changed": False,
        "truth_use": "Retrospective evaluation only; truth and scenarios are stored separately from blinded candidate inputs.",
        "historical_m29_evidence": {
            "source": "M29 synthetic benchmark report on main",
            "summary": m29_prior.get("summary") if m29_prior else "NOT_AVAILABLE",
        },
        "candidate_inputs": "M30_SYNTHETIC_CANDIDATE_INPUTS.json",
        "truth_file": "M30_SYNTHETIC_CANDIDATE_TRUTH.json",
        "stage_audit": runtime,
        "screening": screening,
        "metrics": _metrics(screening, truth_by_id),
        "conclusion": {
            "status": "NOT_VALIDATED",
            "capability": "PARTIAL_SCREENING_CAPABILITY",
            "statement": "M8 defines and implements similarity-evidence searches, but its pinned runtime is unavailable here and its results are not a biological classifier. M7 is optional recurrence context. M9–M15 provide analyses and review/provenance artifacts, not a frozen final acceptance classifier. End-to-end synthetic candidate specificity is therefore not demonstrated.",
        },
        "governance": GOVERNANCE,
    }
    (output / "M30_SYNTHETIC_CANDIDATE_INPUTS.json").write_text(
        json.dumps({"schema": "m30-blinded-candidate-inputs-v1",
                    "candidates": inputs}, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "M30_SYNTHETIC_CANDIDATE_TRUTH.json").write_text(
        json.dumps({"schema": "m30-retrospective-truth-v1",
                    "cases": truth}, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "M30_SYNTHETIC_CANDIDATE_SPECIFICITY.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    (output / "M30_SYNTHETIC_CANDIDATE_SPECIFICITY.md").write_text(
        render_markdown(result), encoding="utf-8",
    )
    return result


def render_markdown(result):
    lines = [
        "# M30 synthetic candidate specificity and false-positive validation",
        "",
        "**Conclusion: NOT_VALIDATED.** The existing repository has partial sequence-evidence capability, but no demonstrated end-to-end candidate-specificity pathway.",
        "",
        "## Stage capability audit",
        "",
        "| Stage | Capability | M30 status |",
        "|---|---|---|",
        f"| M7 | Optional independent recurrence/context evidence; not a classifier | {result['stage_audit']['m7']['status']} |",
        f"| M8 | Frozen BLASTN nucleotide similarity evidence; does not accept/reject candidates | {result['stage_audit']['m8']['status']} |",
        f"| M9–M15 | ORF/repeat/RNA prediction, review, dossiers and provenance; no final acceptance classifier | {result['stage_audit']['m9_m15']['status']} |",
        "",
        "Detailed stage roles:",
        "",
        *[
            f"- {stage.upper()}: {item['status']} — {item['role']}"
            for stage, item in result["stage_audit"].items()
            if stage in {"m9", "m10", "m11", "m12", "m13", "m14", "m15"}
        ],
        "",
        f"M29 historical context: {json.dumps(result['historical_m29_evidence']['summary'], sort_keys=True)}",
        "",
        f"M8 limitation: {result['stage_audit']['m8']['reason']}",
        "",
        "M8 status is similarity evidence only. A match is not a satellite-virus classification; a no-match is limited to the searched synthetic panel. No external biological reference was queried.",
        "",
        "## Blind synthetic fixture matrix",
        "",
        f"Fixtures are split across development, tuning and held-out partitions. Candidate sequences and opaque IDs are in `{result['candidate_inputs']}`; scenario labels and target truth are separate in `{result['truth_file']}`. Candidate inputs contain no scenario or target label. Fixture support statuses are declarations for test design, not measured M6 evidence.",
        "",
        "| Candidate | Split | Sequence SHA-256 | Assembly | Read support | M8 | Final acceptance |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in result["screening"]:
        lines.append(
            f"| {row['candidate_id']} | {row['split']} | {row['sequence_sha256'] or 'NONE'} | "
            f"{row['assembly_status']} | {row['read_support_status']} | {row['m8_status']} | "
            f"{row['final_acceptance_status']} |"
        )
    lines += [
        "",
        "Cases cover exact target-like sequences, unrelated background, target-absent input, near-target decoys, repeats/low complexity, truncated target-like sequence, unsupported exact sequence, and ambiguous evidence.",
        "",
        "## Specificity and sensitivity",
        "",
        f"Metrics status: **{result['metrics']['status']}**. {result['metrics']['reason']}",
        "",
        "No candidates were treated as true negatives merely because screening was unavailable. Sensitivity, specificity, precision, false-discovery proportion, and confidence intervals are NOT_EVALUATED.",
        "",
        "## Reproduction",
        "",
        "Run `python -m satellite_discovery.m30_candidate_specificity --output /tmp/m30-specificity`. The command writes blinded inputs, separate truth labels, and JSON/Markdown reports. It queries no external reference service and executes no biological data.",
        "",
        "## Limitations and governance",
        "",
        result["conclusion"]["statement"],
        "",
        "```text",
        f"decision={result['governance']['decision']}",
        f"overall_state={result['governance']['overall_state']}",
        f"biological_execution_authorized={str(result['governance']['biological_execution_authorized']).lower()}",
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New or existing output directory")
    args = parser.parse_args(argv)
    print(json.dumps(build(args.output)["metrics"], sort_keys=True))


if __name__ == "__main__":
    main()
