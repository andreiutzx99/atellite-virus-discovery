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
    m19_benchmark as m19,
    m29_assembly_root_cause_recovery as m29,
    m31_synthetic_evidence_screening as m31,
    m8_candidate_handoff,
    m8_contracts,
    m8_search_adapters,
)
from .m8_homology import payload_input_name

SCHEMA = "m32-end-to-end-synthetic-evidence-v1"
PANEL_SEED = 32032026
PANEL_SNAPSHOT_ID = "m32-preregistered-synthetic-panel-v1"


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
    """Separate known-reference execution from reference-independent identification."""
    metrics = report["benchmark_metrics"]["cases"]
    by_case = {row["case_id"]: row for row in report["candidate_triage"]}
    known_reference = next((row for row in metrics
                             if row["split"] == "held_out"
                             and row["experiment_type"] == "known_reference_positive"), None)
    if not known_reference or not all(known_reference[key] for key in (
            "assembly_recovery", "supported_exact_recovery", "m6_to_m8_handoff",
            "m8_search_complete")):
        raise RuntimeError("M32 held-out known-reference control did not complete its evidence chain")
    if known_reference["reference_panel_status"] != "PRESENT":
        raise RuntimeError("M32 known-reference control is not bound to its pre-registered panel target")
    expected = known_reference["expected_triage_outcome"]
    known_row = by_case[known_reference["case_id"]]
    exact_supported_ids = set(known_reference["supported_exact_contig_ids"])
    if expected != "REVIEW_PRIORITY" or not any(
            item.get("candidate_id") in exact_supported_ids
            and item.get("outcome") == expected
            for item in known_row.get("outcome", [])):
        raise RuntimeError("M32 known-reference exact supported contig missed its expected triage outcome")

    independent = next((row for row in metrics
                        if row["experiment_type"] == "reference_independent_challenge"), None)
    if not independent or independent["reference_panel_status"] != "ABSENT":
        raise RuntimeError("M32 is missing a reference-absent independent challenge")
    if independent["m8_search_complete"]:
        independent_row = by_case[independent["case_id"]]
        exact_ids = set(independent["supported_exact_contig_ids"])
        if any(item.get("candidate_id") in exact_ids
               and item.get("outcome") != independent["expected_triage_outcome"]
               for item in independent_row.get("outcome", [])):
            raise RuntimeError("M32 reference-absent challenge did not abstain as pre-registered")
        if independent["expected_triage_outcome"] != "INSUFFICIENT_EVIDENCE":
            raise RuntimeError("M32 reference-absent challenge cannot count as target identification")

    for metric in metrics:
        if metric["experiment_type"] == "known_reference_positive" or not metric["m8_search_complete"]:
            continue
        triage_case = by_case[metric["case_id"]]
        candidate_status = {
            row["candidate_id"]: row.get("triage_status")
            for row in triage_case.get("candidate_records", [])
        }
        if not candidate_status:
            candidate_status = {
                row.get("candidate_id"): row.get("outcome")
                for row in triage_case.get("outcome", [])
                if isinstance(row, dict) and row.get("candidate_id")
            }
        for candidate_id in metric.get("supported_contig_ids", []):
            expected_non_target = metric.get(
                "expected_non_target_triage_outcome", "INSUFFICIENT_EVIDENCE")
            if candidate_status.get(candidate_id) != expected_non_target:
                raise RuntimeError(
                    "M32 target-absent or reference-absent supported contig missed its pre-registered abstention"
                )

    negative = next((row for row in metrics
                     if row["experiment_type"] == "target_absent_no_contig"), None)
    if not negative:
        raise RuntimeError("M32 benchmark is missing its target-absent control")
    negative_row = by_case[negative["case_id"]]
    if negative["m8_search_complete"] or negative_row.get("reason") != "M6 produced no assembled contigs; M8 was not run.":
        raise RuntimeError("M32 no-contig negative must remain unassessed by M8")

    background = next((row for row in metrics
                       if row["experiment_type"] == "target_absent_supported_background"), None)
    if not background:
        raise RuntimeError("M32 benchmark is missing its target-absent background control")
    if background["supported_contig_ids"] and not (
            background["m6_to_m8_handoff"] and background["m8_search_complete"]):
        raise RuntimeError("M32 supported background contigs did not complete M8 screening")
    for row in report["candidate_triage"]:
        for artifact in row.get("raw_outputs", []):
            path = Path(output) / artifact["path"]
            if not path.is_file() or path.stat().st_size != artifact["size_bytes"] \
                    or _sha(path.read_bytes()) != artifact["sha256"]:
                raise RuntimeError(f"M32 raw M8 output failed digest validation: {artifact['path']}")


def _target_sequence_from_design(case):
    """Regenerate a known-reference control from its frozen case design, never truth files."""
    rng = random.Random(m29._case_seed(case))
    sequence = m19._sequence(rng, case["target_length"], case.get("gc_fraction"))
    if case.get("repeat_complexity") == "high":
        sequence = ("ACGTGCAATG" * ((len(sequence) + 9) // 10))[:len(sequence)]
    elif case.get("repeat_complexity") == "low_complexity":
        sequence = ("AAAAC" * ((len(sequence) + 4) // 5))[:len(sequence)]
    return sequence


def preregistered_panel(cases):
    """Freeze a synthetic panel from declared controls before generating any outcomes."""
    by_id = {case["case_id"]: case for case in cases}
    known_ids = (
        "development-m29-positive_control",
        "tuning-m29-synthetic_background",
        "held_out-m29-positive_control",
    )
    known = []
    by_id = {case["case_id"]: case for case in cases}
    for case_id in known_ids:
        if case_id not in by_id:
            raise ValueError(f"Missing pre-registered known-reference case: {case_id}")
        known.append((case_id, _target_sequence_from_design(by_id[case_id])))
    near = list(known[2][1])
    near_rng = random.Random(PANEL_SEED)
    for position in near_rng.sample(range(len(near)), 24):
        near[position] = next(base for base in "ACGT" if base != near[position])
    sequences = {
        "SYN001.1": known[0][1],
        "SYN002.1": known[1][1],
        "SYN003.1": "".join(near),
        "SYN004.1": m31._dna(PANEL_SEED + 2, 900),
        "SYN005.1": "ACGT" * 225,
        "SYN006.1": known[2][1],
        "SYN007.1": m31._dna(PANEL_SEED + 3, 900),
    }
    records = []
    for name, source in zip(("SYN001.1", "SYN002.1", "SYN006.1"), known):
        case = by_id[source[0]]
        records.append({"accession_version": name, "role": "satellite_subviral",
                        "intent": "known_reference_positive", "source_case_id": source[0],
                        "seed": m29._case_seed(case), "target_length": case["target_length"],
                        "gc_fraction": case.get("gc_fraction"),
                        "repeat_complexity": case.get("repeat_complexity"),
                        "sequence_sha256": _sha(sequences[name].encode())})
    records.extend([
        {"accession_version": "SYN003.1", "role": "satellite_subviral",
         "intent": "fixed_synthetic_near_reference", "seed": PANEL_SEED,
         "source_case_id": known[2][0], "derived_from_accession": "SYN006.1",
         "substitution_count": 24,
         "sequence_sha256": _sha(sequences["SYN003.1"].encode())},
        {"accession_version": "SYN004.1", "role": "virus_helper",
         "intent": "fixed_synthetic_helper", "seed": PANEL_SEED + 2,
         "sequence_sha256": _sha(sequences["SYN004.1"].encode())},
        {"accession_version": "SYN005.1", "role": "virus_helper",
         "intent": "fixed_low_complexity_control", "sequence_sha256": _sha(sequences["SYN005.1"].encode())},
        {"accession_version": "SYN007.1", "role": "virus_helper",
         "intent": "fixed_synthetic_background", "seed": PANEL_SEED + 3,
         "sequence_sha256": _sha(sequences["SYN007.1"].encode())},
    ])
    return sequences, {"schema": "m32-preregistered-reference-design-v1",
                       "seed": PANEL_SEED, "records": records,
                       "reference_independent_case_ids": ["held_out-m29-sequencing_errors"]}


def _benchmark_design(matrix):
    """Declare experiment roles and controls before any M6 run is generated."""
    chosen = [matrix[i] for i in (0, 1, 6, 8, 12, 16)]
    background = dict(matrix[15])
    background.update({
        "case_id": "held_out-m32-target_absent_background",
        "analysis_id": "m32bg01",
        "coverage": 80,
        "m25_read_length": 100,
        "background_gc_fraction": 0.5,
    })
    cases = [dict(case) for case in chosen] + [background]
    kinds = {
        cases[0]["case_id"]: ("known_reference_positive", "REVIEW_PRIORITY"),
        cases[1]["case_id"]: ("reference_absent_adversarial", "INSUFFICIENT_EVIDENCE"),
        cases[2]["case_id"]: ("known_reference_positive", "REVIEW_PRIORITY"),
        cases[3]["case_id"]: ("known_reference_positive", "REVIEW_PRIORITY"),
        cases[4]["case_id"]: ("reference_independent_challenge", "INSUFFICIENT_EVIDENCE"),
        cases[5]["case_id"]: ("target_absent_no_contig", "INSUFFICIENT_EVIDENCE"),
        cases[6]["case_id"]: ("target_absent_supported_background", "INSUFFICIENT_EVIDENCE"),
    }
    contracts = {
        case_id: {
            "experiment_type": kind,
            "expected_triage_outcome": expected,
            "expected_exact_target_triage_outcome": (
                "REVIEW_PRIORITY" if kind == "known_reference_positive"
                else "INSUFFICIENT_EVIDENCE"),
            "expected_non_target_triage_outcome": "INSUFFICIENT_EVIDENCE",
        }
        for case_id, (kind, expected) in kinds.items()
    }
    return cases, contracts


def _m8_workflow_spec(case, handoff, output, manifest, fasta, indexes, blastn, makeblastdb):
    """Create screening inputs only from validated M6 artifacts and frozen panel bytes."""
    inputs = {
        "candidate_sequence_set": {
            "path": str(handoff["path"].relative_to(output)),
            "artifact_type": "m8_candidate_sequence_set",
        },
        "reference_snapshot_manifest": {
            "path": str(manifest.relative_to(output)),
            "artifact_type": "m8_reference_snapshot_manifest",
        },
    }
    for refpath in [fasta, *indexes]:
        inputs[payload_input_name(refpath.name)] = {
            "path": str(refpath.relative_to(output)),
            "artifact_type": "m8_reference_payload",
        }
    role_plan = {
        role: ({"status": "SELECTED"} if role in m31.ROLES else
               {"status": "NOT_SELECTED", "reason": "outside synthetic panel"})
        for role in sorted(m8_contracts.PANEL_ROLES)
    }
    return {"schema": "artifact-workflow-v1", "stages": [{
        "id": "m8-" + case["analysis_id"], "kind": "m8_homology", "inputs": inputs,
        "config": {"role_plan": role_plan,
                   "blastn_executable": str(Path(blastn).resolve()),
                   "makeblastdb_executable": str(Path(makeblastdb).resolve())},
    }]}


def _freeze_m32_panel(output, cases, contracts, blastn, makeblastdb, blastdbcmd):
    sequences, design = preregistered_panel(cases)
    manifest, fasta, indexes, panel_doc = m31._panel(
        output / "reference", sequences, blastn, makeblastdb, blastdbcmd)
    panel_doc["snapshot_id"] = PANEL_SNAPSHOT_ID
    panel_doc["provider"] = "M32 pre-registered deterministic synthetic design"
    panel_doc["request_endpoint"] = "fixture://m32-preregistered"
    panel_doc["retrieval_method"] = "pre-registered deterministic generator; no candidate truth read"
    panel_doc["snapshot_digest"] = m31._digest_json(panel_doc)
    _json(manifest, panel_doc)
    design["panel_fasta_sha256"] = _sha(fasta.read_bytes())
    design["snapshot_digest"] = panel_doc["snapshot_digest"]
    design["reference_panel_status_by_case"] = {
        case_id: ("PRESENT" if metadata["experiment_type"] == "known_reference_positive"
                  else "ABSENT" if metadata["experiment_type"] == "reference_independent_challenge"
                  else "NOT_APPLICABLE")
        for case_id, metadata in contracts.items()
    }
    design["design_digest"] = _sha(json.dumps(
        design, sort_keys=True, separators=(",", ":")).encode())
    _json(output / "M32_REFERENCE_PANEL_PREREGISTRATION.json", design)
    return manifest, fasta, indexes, panel_doc, design


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

    # Freeze the reference panel and its case contracts before any M6 outcome or
    # retrospective truth file is generated or opened.
    matrix = m29.case_matrix()
    cases, contracts = _benchmark_design(matrix)
    manifest, fasta, indexes, panel_doc, panel_design = _freeze_m32_panel(
        output, cases, contracts, blastn, makeblastdb, blastdbcmd)
    panel_target_digests = {
        row["sequence_sha256"] for row in panel_doc["records"]
        if row["role"] == "satellite_subviral"
    }
    execution, runs = [], []
    for case in cases:
        case_root = output / "reconstruction" / case["case_id"]
        report, case_state = m29._run_case(case_root, dict(case))
        stage = case_root / "stages" / f"m6_{case['analysis_id']}"
        handoff = _handoff(stage, output / "handoffs" / case["case_id"], case["case_id"])
        reconstruction = json.loads((stage / "reconstruction_evidence.json").read_text())
        contract = contracts[case["case_id"]]
        execution.append({"case_id": case["case_id"], "split": case["case_id"].split("-", 1)[0],
                           **contract,
                          "assembly_status": reconstruction.get("status", "NOT_EVALUATED"),
                          "contig_count": len(handoff["records"]) if handoff else 0,
                          "handoff": handoff["validation"] if handoff else {"status": "NO_CONTIGS"},
                          "assembler": reconstruction.get("assembler"),
                          "assembly_configuration": reconstruction.get("configuration"),
                          "support_criteria": reconstruction.get("support_criteria"),
                          "assembly_graph": m29.m28._graph_summary(stage),
                          "read_input_sha256": _sha((case_root / "inputs" / "datasets"
                                                    / case["analysis_id"] / "reads.fastq.gz").read_bytes()),
                           "synthetic_background_source_sha256": case_state.get(
                               "_m29_unreferenced_background_sha256"),
                           "synthetic_background_read_count": case_state.get(
                               "_m29_unreferenced_background_read_count"),
                          "source_manifest_sha256": _sha((case_root / "inputs"
                                                          / "source_manifest.json").read_bytes()),
                          "m6_reconstruction_sha256": _sha((stage / "reconstruction_evidence.json").read_bytes())})
        runs.append((case, handoff, contract, case_state))

    triage_results = []
    for case, handoff, contract, _case_state in runs:
        if not handoff:
            triage_results.append({"case_id": case["case_id"], "outcome": "INSUFFICIENT_EVIDENCE",
                                   "experiment_type": contract["experiment_type"],
                                   "expected_triage_outcome": contract["expected_triage_outcome"],
                                   "reason": "M6 produced no assembled contigs; M8 was not run.",
                                   "candidate_records": [], "raw_outputs": []})
            continue
        case_id = case["case_id"]
        spec = _m8_workflow_spec(case, handoff, output, manifest, fasta, indexes,
                                 blastn, makeblastdb)
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
        outcome_by_id = {row["candidate_id"]: row for row in outcome}
        matches_by_id = {}
        for match in matches:
            matches_by_id.setdefault(match["candidate_id"], []).append(match)
        query_by_id = {}
        for query in qdoc["queries"]:
            query_by_id.setdefault(query["candidate_id"], []).append(query)
        candidate_records = []
        for candidate_id, sequence in handoff["records"]:
            candidate_queries = query_by_id.get(candidate_id, [])
            candidate_matches = matches_by_id.get(candidate_id, [])
            selected_queries = [row for row in candidate_queries
                                if row.get("status") != "NOT_SELECTED"]
            reference_entries = {
                row.get("reference", {}).get("accession_version")
                for row in candidate_matches
                if row.get("reference", {}).get("accession_version")
            }
            candidate_records.append({
                "candidate_id": candidate_id,
                "query_sha256": _sha(sequence.encode()),
                "query_length": len(sequence),
                "read_support_status": supported.get(candidate_id, "NOT_EVALUATED"),
                "m8_aggregate_status": (
                    "COMPLETE" if selected_queries and all(
                        row.get("aggregate_status") == "COMPLETE" for row in selected_queries
                    ) else "INCOMPLETE"
                ),
                "reference_panel_entries": sorted(reference_entries),
                "reference_panel_result": "MATCH_REPORTED" if candidate_matches else "NO_REPORTED_MATCH",
                "triage_status": outcome_by_id.get(candidate_id, {}).get(
                    "outcome", "INSUFFICIENT_EVIDENCE"),
            })
        triage_results.append({"case_id": case_id, "outcome": outcome,
                               "experiment_type": contract["experiment_type"],
                               "expected_triage_outcome": contract["expected_triage_outcome"],
                               "query_status": qdoc, "matches": matches,
                               "search_commands": json.loads((stage_dir / "commands.json").read_text()),
                               "raw_outputs": raw_outputs, "support_by_contig": supported,
                               "candidate_records": candidate_records})
    # Retrospective scoring occurs only after every M8 search and triage result.
    benchmark_metrics = []
    triage_by_case = {row["case_id"]: row for row in triage_results}
    truths = []
    for case, handoff, contract, case_state in runs:
        case_root = output / "reconstruction" / case["case_id"]
        truth = json.loads((case_root / "heldout_truth.json").read_text())["cases"][0]
        truths.append({"case_id": case["case_id"], "positive": case["positive"],
                       "split": case["case_id"].split("-", 1)[0],
                       "candidate_sha256": truth.get("candidate_sha256"),
                       "experiment_type": contract["experiment_type"]})
        candidate_rows = handoff["records"] if handoff else []
        target = truth.get("candidate_sequence")
        support_by_id = ({row["contig_id"]: row.get("status")
                          for row in handoff["support"]} if handoff else {})
        triage_row = triage_by_case[case["case_id"]]
        query_doc = triage_row.get("query_status", {})
        exact_ids, supported_ids = [], []
        candidate_by_id = {row["candidate_id"]: row for row in triage_row.get("candidate_records", [])}
        for cid, sequence in candidate_rows:
            raw_comparison = (m29.m25.diagnose_sequence(target, sequence) if target else None)
            comparison = ({key: value for key, value in raw_comparison.items() if key != "_local"}
                          if raw_comparison else None)
            exact = bool(comparison and comparison.get("strand_exact_match"))
            background_exact = (
                not target and case_state.get("_m29_unreferenced_background_sha256")
                == _sha(sequence.encode())
            )
            is_supported = support_by_id.get(cid) == "READ_SUPPORTED_ASSEMBLY"
            if exact:
                exact_ids.append(cid)
            if exact and is_supported:
                supported_ids.append(cid)
            candidate_by_id.setdefault(cid, {
                "candidate_id": cid, "query_sha256": _sha(sequence.encode()),
                "query_length": len(sequence),
                "read_support_status": support_by_id.get(cid, "NOT_EVALUATED"),
                "m8_aggregate_status": "NOT_RUN",
                "reference_panel_entries": [],
                "reference_panel_result": "NOT_ASSESSED",
                "triage_status": "INSUFFICIENT_EVIDENCE",
            })
            candidate_by_id[cid]["retrospective_truth_comparison"] = {
                "exact_target_match": exact,
                "comparison": comparison,
                "exact_synthetic_background_match": bool(background_exact),
            }
            candidate_by_id[cid]["retrospective_expected_triage_outcome"] = (
                contract["expected_exact_target_triage_outcome"] if exact
                else contract["expected_non_target_triage_outcome"]
            )
        if target and contract["experiment_type"] == "reference_independent_challenge":
            target_digest = _sha(target.encode())
            if target_digest in panel_target_digests:
                raise RuntimeError("Reference-independent target is present in the frozen panel")
        supported_contig_ids = [
            cid for cid, status in support_by_id.items() if status == "READ_SUPPORTED_ASSEMBLY"
        ]
        panel_status = (
            "PRESENT" if target and _sha(target.encode()) in panel_target_digests
            else "ABSENT" if target else "NOT_APPLICABLE"
        )
        exact_triage_success = any(
            cid in supported_ids
            and candidate_by_id.get(cid, {}).get("triage_status")
            == contract["expected_triage_outcome"]
            for cid in exact_ids
        )
        benchmark_metrics.append({
            "case_id": case["case_id"], "split": case["case_id"].split("-", 1)[0],
            "positive_control": bool(case["positive"]),
            **contract,
            "reference_panel_status": panel_status,
            "assembly_recovery": bool(exact_ids),
            "exact_contig_ids": sorted(exact_ids),
            "supported_exact_recovery": bool(supported_ids),
            "supported_exact_contig_ids": sorted(supported_ids),
            "expected_triage_success_on_exact_contig": exact_triage_success,
            "supported_contig_ids": sorted(supported_contig_ids),
            "m6_to_m8_handoff": bool(handoff and handoff["validation"]["status"] == "VALIDATED"),
            "m8_search_complete": query_doc.get("aggregate_status") == "COMPLETE",
            "triage_outcome_count": len(triage_row.get("outcome", []))
            if isinstance(triage_row.get("outcome"), list) else 0,
            "target_absent": not bool(case["positive"]),
        })
        triage_row["candidate_records"] = [candidate_by_id[cid] for cid, _ in candidate_rows]
    _json(output / "retrospective_truth.json", {"cases": truths})
    report = {
        "schema": SCHEMA, "synthetic_only": True, "external_biological_queries": False,
        "production_defaults_changed": False, "runtime": runtime,
        "panel_digest": panel_doc["snapshot_digest"], "panel_preregistration": panel_design,
        "reconstruction_and_handoffs": execution,
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
            "known_reference_retrieval": {
                "case_ids": [row["case_id"] for row in benchmark_metrics
                             if row["experiment_type"] == "known_reference_positive"],
                "exact_supported_expected_triage_successes": sum(
                    bool(row["expected_triage_success_on_exact_contig"])
                    for row in benchmark_metrics
                    if row["experiment_type"] == "known_reference_positive"),
                "interpretation": "synthetic retrieval/integration control, not independent discovery",
            },
            "reference_independent_challenge": [
                {key: row[key] for key in (
                    "case_id", "reference_panel_status", "assembly_recovery",
                    "supported_exact_recovery", "m8_search_complete",
                    "expected_triage_outcome")}
                for row in benchmark_metrics
                if row["experiment_type"] == "reference_independent_challenge"
            ],
            "target_absent_background_control": [
                {key: row[key] for key in (
                    "case_id", "supported_contig_ids", "m6_to_m8_handoff",
                    "m8_search_complete", "expected_triage_outcome")}
                for row in benchmark_metrics
                if row["experiment_type"] == "target_absent_supported_background"
            ],
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
             "## Pre-registered case outcomes", "",
             "| Case | Experiment | Reference panel | Expected triage |",
             "|---|---|---|---|"]
    metric_by_case = {row["case_id"]: row for row in report["benchmark_metrics"]["cases"]}
    for row in report["benchmark_metrics"]["cases"]:
        lines.append(f"| {row['case_id']} | {row['experiment_type']} | "
                     f"{row['reference_panel_status']} | {row['expected_triage_outcome']} |")
    lines += ["", "Known-reference cases measure synthetic retrieval/integration, not independent "
              "discovery. The reference-independent challenge is checked against the frozen panel "
              "without consulting held-out truth during screening.", "",
             "## Reconstruction and M6-to-M8 handoff", "",
              "| Case | Split | Assembly | Contigs | Handoff |",
              "|---|---|---|---:|---|"]
    for row in report["reconstruction_and_handoffs"]:
        lines.append(f"| {row['case_id']} | {row['split']} | {row['assembly_status']} | "
                     f"{row['contig_count']} | {row['handoff']['status']} |")
    lines += ["", "## M8 and triage", "",
              "Triage is panel-relative synthetic evidence only; it is not biological acceptance.", "",
              "| Case | Candidate | Query SHA-256 | M6 support | M8 | Panel result | Triage |",
              "|---|---|---|---|---|---|---|"]
    for row in report["candidate_triage"]:
        if row.get("candidate_records"):
            for candidate in row["candidate_records"]:
                lines.append(
                    f"| {row['case_id']} | {candidate['candidate_id']} | "
                    f"{candidate['query_sha256']} | {candidate['read_support_status']} | "
                    f"{candidate['m8_aggregate_status']} | "
                    f"{candidate['reference_panel_result']} "
                    f"{','.join(candidate['reference_panel_entries'])} | "
                    f"{candidate['triage_status']} |"
                )
        else:
            lines.append(f"| {row['case_id']} | — | — | — | NOT_RUN | — | "
                         f"{row.get('outcome', 'INSUFFICIENT_EVIDENCE')} |")
    metrics = report["benchmark_metrics"]
    background = metrics["target_absent_background_control"][0]
    lines += ["", "Target-absent background control: "
              f"{len(background['supported_contig_ids'])} M6-supported contig(s); "
              f"M8 complete={background['m8_search_complete']}. This is a synthetic technical "
              "control and is not biological acceptance.", "", "## Limits", "",
              "Biological sensitivity, specificity, and false-discovery rate are NOT_EVALUATED. "
              "M6 support is technical read-back evidence, not independent biological validation.", "",
              "Retrospective truth comparisons are reported only after every available M8 search "
              "and triage result.", "",
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
