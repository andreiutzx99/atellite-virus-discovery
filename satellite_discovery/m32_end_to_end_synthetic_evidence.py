"""Synthetic-only M6→M8 integration with candidate-level provenance checks."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil

from . import (
    artifact_workflow,
    m29_assembly_root_cause_recovery as m29,
    m31_synthetic_evidence_screening as m31,
    m8_blastn_profile as profile,
    m8_candidate_handoff,
    m8_contracts,
    m8_search_adapters,
)
from .m8_homology import payload_input_name

SCHEMA = "m32-end-to-end-synthetic-evidence-v1"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _json(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def validate_handoff(directory, expected_contigs, support):
    """Reject identity swaps and incomplete measured M6 evidence."""
    directory = Path(directory)
    fasta = directory / "assembly" / "contigs.fasta"
    parsed = m8_candidate_handoff.fasta_record_metadata(fasta)
    if {r["fasta_record_id"]: r for r in parsed} != expected_contigs:
        raise ValueError("M6-to-M8 handoff contig IDs or sequence digests mismatch")
    handoff = directory / "candidate_sequence_set.json"
    details = m8_candidate_handoff.validate_candidate_sequence_set(handoff)
    document = json.loads(handoff.read_text())
    evidence = json.loads((directory / "reconstruction_evidence.json").read_text())
    support_by_id = {row["contig_id"]: row for row in support}
    for row in document["records"]:
        measured = support_by_id.get(row["candidate_id"])
        if not measured or measured.get("status") != row["m6_support_status"]:
            raise ValueError(f"Measured support does not bind to {row['candidate_id']}")
        if row["sequence_sha256"] != expected_contigs[row["candidate_id"]]["sequence_sha256"]:
            raise ValueError(f"Sequence digest mismatch for {row['candidate_id']}")
    if evidence.get("status") not in {"READ_SUPPORTED_ASSEMBLY", "NO_SUPPORTED_ASSEMBLY"}:
        raise ValueError("M6 reconstruction evidence is incomplete or failed")
    return {"status": "VALIDATED", "candidate_count": details["record_count"],
            "support_artifact_sha256": _sha((directory / "read_support.json").read_bytes())}


def validate_success_criteria(report, output):
    """Fail closed unless the held-out target completes the full evidence chain."""
    metrics = report["benchmark_metrics"]["cases"]
    held_out = next((row for row in metrics
                     if row["split"] == "held_out" and row["positive_control"]), None)
    if not held_out or not all(held_out[key] for key in (
            "assembly_recovery", "supported_exact_recovery", "m6_to_m8_handoff",
            "m8_search_complete")):
        raise RuntimeError("M32 held-out positive did not complete the required evidence chain")
    held_row = next(row for row in report["candidate_triage"]
                    if row["case_id"] == held_out["case_id"])
    if not any(item.get("outcome") in {"REVIEW_PRIORITY", "BACKGROUND_LIKE",
                                      "CONFLICTING_EVIDENCE"}
               for item in held_row.get("outcome", [])):
        raise RuntimeError("M32 held-out positive lacks a completed triage outcome")
    negative = next((row for row in metrics if row["target_absent"]), None)
    if not negative:
        raise RuntimeError("M32 benchmark is missing its target-absent control")
    negative_row = next(row for row in report["candidate_triage"]
                        if row["case_id"] == negative["case_id"])
    if negative_row.get("outcome") not in {"INSUFFICIENT_EVIDENCE", "BACKGROUND_LIKE"}:
        raise RuntimeError("M32 target-absent control was unexpectedly promoted")
    for row in report["candidate_triage"]:
        for artifact in row.get("raw_outputs", []):
            path = Path(output) / artifact["path"]
            if not path.is_file() or path.stat().st_size != artifact["size_bytes"] \
                    or _sha(path.read_bytes()) != artifact["sha256"]:
                raise RuntimeError(f"M32 raw M8 output failed digest validation: {artifact['path']}")


def _read_fasta(path):
    rows = []
    current = None
    seq = []
    for line in Path(path).read_text().splitlines():
        if line.startswith(">"):
            if current is not None:
                rows.append((current, "".join(seq)))
            current, seq = line[1:].split()[0], []
        elif line.strip():
            seq.append(line.strip())
    if current is not None:
        rows.append((current, "".join(seq)))
    return rows


def _is_low_complexity(sequence):
    if len(sequence) < 3:
        return True
    kmers = [sequence[index:index + 3] for index in range(len(sequence) - 2)]
    return max((kmers.count(kmer) for kmer in set(kmers)), default=0) / len(kmers) >= 0.20


def _handoff(source_stage, out, case_id):
    out = Path(out)
    (out / "assembly").mkdir(parents=True, exist_ok=True)
    src_assembly = source_stage / "assembly"
    if not (src_assembly / "contigs.fasta").is_file():
        return None
    shutil.copy2(src_assembly / "contigs.fasta", out / "assembly" / "contigs.fasta")
    if not (src_assembly / "assembly_manifest.json").is_file():
        raise ValueError("M6 emitted contigs without the declared assembly manifest")
    shutil.copy2(src_assembly / "assembly_manifest.json", out / "assembly" / "assembly_manifest.json")
    for name in ("reconstruction_evidence.json", "read_support.json"):
        shutil.copy2(source_stage / name, out / name)
    source_bytes = (out / "assembly" / "contigs.fasta").read_bytes()
    records = _read_fasta(out / "assembly" / "contigs.fasta")
    if not records:
        return None
    support_doc = json.loads((out / "read_support.json").read_text())
    support = support_doc.get("contigs", [])
    support_by_id = {row["contig_id"]: row for row in support}
    source_ref = {"path": "assembly/contigs.fasta", "sha256": _sha(source_bytes),
                  "size_bytes": len(source_bytes)}
    fasta = out / "candidate_sequences.fasta"
    shutil.copy2(out / "assembly" / "contigs.fasta", fasta)
    fasta_bytes = fasta.read_bytes()
    assembly_path = out / "assembly" / "assembly_manifest.json"
    assembly_bytes = assembly_path.read_bytes()
    reconstruction = json.loads((out / "reconstruction_evidence.json").read_text())
    entries = []
    for cid, seq in records:
        support_row = support_by_id.get(cid, {})
        entries.append({
            "candidate_id": cid, "sequence_id": cid, "fasta_record_id": cid,
            "sequence_sha256": _sha(seq.encode()), "sequence_length": len(seq),
            "sequence_bytes_available": True, "sequence_unavailable_reason": None,
            "molecule_type": "DNA", "sequence_alphabet": "IUPAC_NUCLEOTIDE",
            "completeness_state": "UNKNOWN", "source_artifact_id": source_ref["path"],
            "source_artifact_sha256": source_ref["sha256"],
            "m6_support_status": support_row.get("status", "NOT_EVALUATED"),
            "m7_context": None,
        })
    doc = {
        "schema": "m8-candidate-sequence-set-v1",
        "producer": {"stage_kind": "residual_evidence", "stage_id": case_id,
                     "adapter_name": "M6 residual_evidence", "adapter_version": "1"},
        "source_artifact": source_ref,
        "assembly_manifest": {"path": "assembly/assembly_manifest.json",
                              "sha256": _sha(assembly_bytes), "size_bytes": len(assembly_bytes)},
        "m6_evidence": {"reconstruction_status": reconstruction["status"],
                        "support_status": support_doc.get("status", support_doc.get("aggregate_status")),
                        "artifact": {"path": "reconstruction_evidence.json",
                                     "sha256": _sha((out / "reconstruction_evidence.json").read_bytes())}},
        "m7_context": None,
        "availability": {"state": "AVAILABLE", "reason": None,
                         "fasta_artifact": {"path": "candidate_sequences.fasta",
                                            "sha256": _sha(fasta_bytes), "size_bytes": len(fasta_bytes)},
                         "record_count": len(entries)},
        "records": entries,
    }
    _json(out / "candidate_sequence_set.json", doc)
    expected = {cid: {"fasta_record_id": cid, "sequence_length": len(seq),
                      "sequence_sha256": _sha(seq.encode())} for cid, seq in records}
    validation = validate_handoff(out, expected, support)
    return {"path": out / "candidate_sequence_set.json", "validation": validation,
            "records": records, "support": support}


def run(output, blastn, makeblastdb, blastdbcmd=None):
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite M32 output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    runtime = m8_search_adapters.inspect_blast_runtime({
        "blastn_executable": str(Path(blastn).resolve()),
        "makeblastdb_executable": str(Path(makeblastdb).resolve()),
    })
    if runtime["status"] != "available":
        raise RuntimeError(f"Frozen M8 runtime verification failed: {runtime}")
    blastdbcmd = blastdbcmd or str(Path(makeblastdb).with_name("blastdbcmd"))

    # Predeclared cases: one per split plus an independent held-out negative.
    matrix = m29.case_matrix()
    cases = [matrix[0], matrix[1], matrix[6], matrix[8], matrix[16]]
    execution, truths, runs = [], [], []
    for case in cases:
        case_root = output / "reconstruction" / case["case_id"]
        report, _ = m29._run_case(case_root, dict(case))
        truth_doc = json.loads((case_root / "heldout_truth.json").read_text())
        truth = truth_doc["cases"][0]
        truths.append({"case_id": case["case_id"], "positive": case["positive"],
                       "split": case["case_id"].split("-", 1)[0],
                       "truth_sha256": truth.get("candidate_sha256")})
        stage = case_root / "stages" / f"m6_{case['analysis_id']}"
        handoff = _handoff(stage, output / "handoffs" / case["case_id"], case["case_id"])
        reconstruction = json.loads((stage / "reconstruction_evidence.json").read_text())
        execution.append({"case_id": case["case_id"], "split": case["case_id"].split("-", 1)[0],
                          "assembly_status": reconstruction.get("status", "NOT_EVALUATED"),
                          "contig_count": len(handoff["records"]) if handoff else 0,
                          "handoff": handoff["validation"] if handoff else {"status": "NO_CONTIGS"},
                          "assembler": reconstruction.get("assembler"),
                          "assembly_configuration": reconstruction.get("configuration"),
                          "support_criteria": reconstruction.get("support_criteria"),
                          "assembly_graph": m29.m28._graph_summary(stage),
                          "read_input_sha256": _sha((case_root / "inputs" / "datasets"
                                                    / case["analysis_id"] / "reads.fastq.gz").read_bytes()),
                          "source_manifest_sha256": _sha((case_root / "inputs"
                                                          / "source_manifest.json").read_bytes()),
                          "m6_reconstruction_sha256": _sha((stage / "reconstruction_evidence.json").read_bytes())})
        runs.append((case, handoff, truth))

    # The panel is a synthetic-only fixture. Truth is written only after all M8
    # runs and triage, keeping labels out of screening code and inputs.
    panel_seqs = {}
    seen_targets = set()
    for case, _, truth in runs:
        if case["m29_factor"] == "repeat_challenge":
            continue
        seq = truth.get("candidate_sequence")
        if seq and _sha(seq.encode()) not in seen_targets:
            accession = f"SYN{len(panel_seqs) + 1:03d}.1"
            panel_seqs[accession] = seq
            seen_targets.add(_sha(seq.encode()))
    panel_seqs[f"SYN{len(panel_seqs) + 1:03d}.1"] = m31._dna(32032, 900)
    manifest, fasta, indexes, panel_doc = m31._panel(
        output / "reference", panel_seqs, blastn, makeblastdb, blastdbcmd)
    triage_results = []
    for case, handoff, _truth in runs:
        if not handoff:
            triage_results.append({"case_id": case["case_id"], "outcome": "INSUFFICIENT_EVIDENCE",
                                  "reason": "M6 produced no assembled contigs; M8 was not run."})
            continue
        case_id = case["case_id"]
        role_plan = {role: ({"status": "SELECTED"} if role in m31.ROLES else
                            {"status": "NOT_SELECTED", "reason": "outside synthetic panel"})
                     for role in sorted(m8_contracts.PANEL_ROLES)}
        inputs = {
            "candidate_sequence_set": {"path": str(handoff["path"].relative_to(output)),
                                       "artifact_type": "m8_candidate_sequence_set"},
            "reference_snapshot_manifest": {"path": str(manifest.relative_to(output)),
                                            "artifact_type": "m8_reference_snapshot_manifest"},
        }
        for refpath in [fasta, *indexes]:
            inputs[payload_input_name(refpath.name)] = {
                "path": str(refpath.relative_to(output)), "artifact_type": "m8_reference_payload"}
        spec = {"schema": "artifact-workflow-v1", "stages": [{
            "id": "m8-" + case["analysis_id"], "kind": "m8_homology", "inputs": inputs,
            "config": {"role_plan": role_plan, "blastn_executable": str(Path(blastn).resolve()),
                       "makeblastdb_executable": str(Path(makeblastdb).resolve())},
        }]}
        spec_path = output / f"m8_workflow_{case['analysis_id']}.json"
        _json(spec_path, spec)
        wfout = output / "m8_runs" / case["analysis_id"]
        artifact_workflow.run(spec_path, wfout, artifact_workflow.build_default_registry())
        workflow = json.loads((wfout / "workflow.json").read_text())
        stage_dir = wfout / workflow["stages"][0]["output_path"]
        qdoc = json.loads((stage_dir / "query_status.json").read_text())
        matches = json.loads((stage_dir / "matches.json").read_text())["matches"]
        sequence_by_id = dict(handoff["records"])
        qrows = [{**row, "low_complexity": _is_low_complexity(
            sequence_by_id.get(row["candidate_id"], ""))} for row in qdoc["queries"]]
        outcome = m31.triage(qrows, matches)
        supported = {row["contig_id"]: row.get("status") for row in handoff["support"]}
        for row in outcome:
            if supported.get(row["candidate_id"]) != "READ_SUPPORTED_ASSEMBLY":
                row["outcome"] = "INSUFFICIENT_EVIDENCE"
                row["reason"] = "M6 did not report qualifying read support for this exact contig."
        raw_outputs = [
            {"path": str(raw.relative_to(output)), "sha256": _sha(raw.read_bytes()),
             "size_bytes": raw.stat().st_size}
            for raw in sorted(stage_dir.glob("*.tsv"))
        ]
        triage_results.append({"case_id": case_id, "outcome": outcome,
                               "query_status": qdoc, "matches": matches,
                               "search_commands": json.loads((stage_dir / "commands.json").read_text()),
                               "raw_outputs": raw_outputs, "support_by_contig": supported})
    # Retrospective scoring occurs only after every M8 search and triage result.
    benchmark_metrics = []
    triage_by_case = {row["case_id"]: row for row in triage_results}
    for case, handoff, truth in runs:
        candidate_rows = handoff["records"] if handoff else []
        target = truth.get("candidate_sequence")
        comparisons = [
            m29.m25.diagnose_sequence(target, seq) for _, seq in candidate_rows
        ] if target else []
        exact_ids = {
            cid for (cid, _), comparison in zip(candidate_rows, comparisons)
            if comparison.get("strand_exact_match")
        }
        support_by_id = ({row["contig_id"]: row.get("status")
                          for row in handoff["support"]} if handoff else {})
        supported_exact = any(
            support_by_id.get(cid) == "READ_SUPPORTED_ASSEMBLY" for cid in exact_ids
        )
        triage_row = triage_by_case[case["case_id"]]
        query_doc = triage_row.get("query_status", {})
        benchmark_metrics.append({
            "case_id": case["case_id"], "split": case["case_id"].split("-", 1)[0],
            "positive_control": bool(case["positive"]),
            "assembly_recovery": bool(exact_ids), "supported_exact_recovery": supported_exact,
            "m6_to_m8_handoff": bool(handoff and handoff["validation"]["status"] == "VALIDATED"),
            "m8_search_complete": query_doc.get("aggregate_status") == "COMPLETE",
            "triage_outcome_count": len(triage_row.get("outcome", []))
            if isinstance(triage_row.get("outcome"), list) else 0,
            "target_absent": not bool(case["positive"]),
        })
    _json(output / "retrospective_truth.json", {"cases": truths})
    report = {
        "schema": SCHEMA, "synthetic_only": True, "external_biological_queries": False,
        "production_defaults_changed": False, "runtime": runtime,
        "panel_digest": panel_doc["snapshot_digest"], "reconstruction_and_handoffs": execution,
        "candidate_triage": triage_results,
        "benchmark_metrics": {
            "case_denominator": len(benchmark_metrics),
            "assembly_recovery": {
                "successes": sum(bool(row["assembly_recovery"]) for row in benchmark_metrics
                                 if row["positive_control"]),
                "denominator": sum(bool(row["positive_control"]) for row in benchmark_metrics),
            },
            "measured_support_success": {
                "successes": sum(bool(row["supported_exact_recovery"]) for row in benchmark_metrics
                                 if row["positive_control"]),
                "denominator": sum(bool(row["positive_control"]) for row in benchmark_metrics),
            },
            "successful_handoffs": sum(bool(row["m6_to_m8_handoff"]) for row in benchmark_metrics),
            "handoff_denominator": len(benchmark_metrics),
            "completed_m8_searches": sum(bool(row["m8_search_complete"]) for row in benchmark_metrics),
            "m8_denominator": sum(row["triage_outcome_count"] > 0 for row in benchmark_metrics),
            "target_absent_controls": sum(bool(row["target_absent"]) for row in benchmark_metrics),
            "cases": benchmark_metrics,
            "biological_discovery_sensitivity_specificity_fdr": "NOT_EVALUATED",
        },
        "truth_separated_from_screening": True,
        "biological_discovery_metrics": "NOT_EVALUATED",
        "governance": {"decision": "INCOMPLETE", "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
                       "biological_execution_authorized": False},
    }
    validate_success_criteria(report, output)
    _json(output / "M32_END_TO_END_SYNTHETIC_EVIDENCE.json", report)
    (output / "M32_END_TO_END_SYNTHETIC_EVIDENCE.md").write_text(
        render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report):
    lines = ["# M32 — End-to-end synthetic evidence integration", "",
             "Synthetic-only software integration; no biological discovery claims.", "",
             "## Reconstruction and M6-to-M8 handoff", "",
             "| Case | Split | Assembly | Contigs | Handoff |", "|---|---|---|---:|---|"]
    for row in report["reconstruction_and_handoffs"]:
        lines.append(f"| {row['case_id']} | {row['split']} | {row['assembly_status']} | "
                     f"{row['contig_count']} | {row['handoff']['status']} |")
    lines += ["", "## M8 and triage", "",
              "Triage is panel-relative synthetic evidence only; it is not biological acceptance.", "",
              "| Case | Candidate outcomes | Raw M8 files |", "|---|---|---:|"]
    for row in report["candidate_triage"]:
        raw = row.get("outcome", [])
        outcomes = ", ".join(item["outcome"] for item in raw) if isinstance(raw, list) else raw
        lines.append(f"| {row['case_id']} | {outcomes or row.get('reason', 'not evaluated')} | "
                     f"{len(row.get('raw_outputs', []))} |")
    lines += ["", "## Limits", "",
              "Biological sensitivity, specificity, and false-discovery rate are NOT_EVALUATED. "
              "M6 support is technical read-back evidence, not independent biological validation.", "",
              "Retrospective assembly and handoff metrics are reported only after M8 and triage have completed.", "",
              "```text", "decision=INCOMPLETE",
              "overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION",
              "biological_execution_authorized=false", "```", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blastn", default=os.environ.get("BLASTN_EXECUTABLE"))
    parser.add_argument("--makeblastdb", default=os.environ.get("MAKEBLASTDB_EXECUTABLE"))
    parser.add_argument("--blastdbcmd", default=os.environ.get("BLASTDBCMD_EXECUTABLE"))
    args = parser.parse_args(argv)
    if not args.blastn or not args.makeblastdb:
        parser.error("provide frozen M8 BLASTN and makeblastdb executables")
    print(json.dumps(run(args.output, args.blastn, args.makeblastdb, args.blastdbcmd)["governance"],
                     sort_keys=True))


if __name__ == "__main__":
    main()
