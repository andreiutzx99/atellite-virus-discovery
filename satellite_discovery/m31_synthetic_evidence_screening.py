"""Execute the frozen M8 similarity stage on deterministic synthetic fixtures."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

from . import artifact_workflow, m8_blastn_profile as profile, m8_contracts
from .m8_homology import payload_input_name
from .m8_search_adapters import inspect_blast_runtime


SEED = 31031
SCHEMA = "m31-synthetic-evidence-screening-v1"
ROLES = ("satellite_subviral", "virus_helper")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _dna(seed, length):
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(length))


def _digest_json(document):
    material = {key: value for key, value in document.items()
                if key not in {"snapshot_digest", "snapshot_digest_algorithm"}}
    return sha(json.dumps(material, sort_keys=True, separators=(",", ":")).encode())


def _write_json(path, document):
    Path(path).write_text(json.dumps(document, sort_keys=True, indent=2) + "\n")


def _synthetic_sequences():
    target = _dna(SEED, 900)
    rng = random.Random(SEED + 1)
    near = list(target)
    for position in rng.sample(range(len(near)), 24):
        near[position] = next(base for base in "ACGT" if base != near[position])
    distant = list(target)
    for position in rng.sample(range(len(distant)), 180):
        distant[position] = next(base for base in "ACGT" if base != distant[position])
    helper = _dna(SEED + 2, 900)
    background = _dna(SEED + 3, 900)
    held_out_target = _dna(SEED + 5, 900)
    repeat = "ACGT" * 225
    return {
        "panel": {
            "SYN001.1": target,
            "SYN002.1": "".join(near),
            "SYN003.1": "".join(distant),
            "SYN004.1": helper,
            "SYN005.1": repeat,
            "SYN006.1": held_out_target,
        },
        "queries": [
            ("q001", target, "development"),
            ("q002", "".join(near), "development"),
            ("q003", helper, "development"),
            ("q004", background, "development"),
            ("q005", repeat, "tuning"),
            ("q006", target + helper, "tuning"),
            ("q007", held_out_target[:42], "held_out"),
            ("q008", held_out_target[:140], "held_out"),
            ("q009", _dna(SEED + 4, 900), "held_out"),
        ],
        "truth": [
            {"candidate_id": cid, "split": split, "scenario": scenario}
            for cid, split, scenario in [
                ("q001", "development", "exact_synthetic_target"),
                ("q002", "development", "near_synthetic_target"),
                ("q003", "development", "synthetic_helper_background"),
                ("q004", "development", "unrelated_background"),
                ("q005", "tuning", "low_complexity_repeat"),
                ("q006", "tuning", "conflicting_target_and_helper"),
                ("q007", "held_out", "short_query"),
                ("q008", "held_out", "partial_target"),
                ("q009", "held_out", "target_absent"),
            ]
        ],
    }


def _candidate_handoff(root, queries):
    root = Path(root)
    source = root / "assembly" / "contigs.fasta"
    source.parent.mkdir(parents=True, exist_ok=True)
    fasta_bytes = "".join(f">{cid}\n{seq}\n" for cid, seq, _ in queries).encode()
    source.write_bytes(fasta_bytes)
    ref = {"path": "assembly/contigs.fasta", "sha256": sha(fasta_bytes),
           "size_bytes": len(fasta_bytes)}
    candidate_fasta = root / "candidate_sequences.fasta"
    candidate_fasta.write_bytes(fasta_bytes)
    fasta_ref = {"path": "candidate_sequences.fasta", "sha256": sha(fasta_bytes),
                 "size_bytes": len(fasta_bytes)}
    assembly_manifest = root / "assembly" / "assembly_manifest.json"
    assembly_bytes = json.dumps({
        "schema": "assembly-manifest-v1", "workflow_status": "complete",
        "contig_count": len(queries), "assembler": "M31 deterministic fixture generator",
        "external_tool_version": "synthetic-only",
    }, sort_keys=True).encode()
    assembly_manifest.write_bytes(assembly_bytes)
    assembly_ref = {"path": "assembly/assembly_manifest.json",
                    "sha256": sha(assembly_bytes), "size_bytes": len(assembly_bytes)}
    evidence_path = root / "reconstruction_evidence.json"
    evidence_bytes = json.dumps({
        "schema": "m6-reconstruction-evidence-v1",
        "status": "NOT_SUPPLIED",
        "note": "M31 synthetic sequence fixture; not measured M6 or M29 evidence.",
        "contigs": [], "configuration": {}, "provenance": {},
    }, sort_keys=True).encode()
    evidence_path.write_bytes(evidence_bytes)
    records = []
    for cid, seq, _split in queries:
        records.append({
            "candidate_id": cid, "sequence_id": cid, "fasta_record_id": cid,
            "sequence_sha256": sha(seq.encode()), "sequence_length": len(seq),
            "sequence_bytes_available": True, "sequence_unavailable_reason": None,
            "molecule_type": "DNA", "sequence_alphabet": "IUPAC_NUCLEOTIDE",
            "completeness_state": "UNKNOWN",
            "source_artifact_id": ref["path"], "source_artifact_sha256": ref["sha256"],
            "m6_support_status": "NOT_EVALUATED", "m7_context": None,
        })
    document = {
        "schema": "m8-candidate-sequence-set-v1",
        "producer": {"stage_kind": "residual_evidence", "stage_id": "m31-synthetic-fixture",
                     "adapter_name": "deterministic-fixture", "adapter_version": "1"},
        "source_artifact": ref, "assembly_manifest": assembly_ref,
        "m6_evidence": {"reconstruction_status": "NOT_SUPPLIED",
                        "support_status": "NOT_EVALUATED",
                         "artifact": {"path": "reconstruction_evidence.json",
                                     "sha256": sha(evidence_bytes)}},
        "m7_context": None,
        "availability": {"state": "AVAILABLE", "reason": None,
            "fasta_artifact": fasta_ref, "record_count": len(records)},
        "records": records,
    }
    path = root / "candidate_sequence_set.json"
    _write_json(path, document)
    return path


def _panel(root, sequences, blastn, makeblastdb, blastdbcmd):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    fasta_path = root / "panel.fasta"
    fasta_bytes = "".join(f">{name}\n{seq}\n" for name, seq in sequences.items()).encode()
    fasta_path.write_bytes(fasta_bytes)
    prefix = root / "synthetic_panel"
    subprocess.run([makeblastdb, "-in", str(fasta_path), "-dbtype", "nucl",
                    "-parse_seqids", "-out", str(prefix)],
                   check=True, capture_output=True, text=True, timeout=120)
    info = subprocess.run([blastdbcmd, "-db", str(prefix), "-info"],
                          check=True, capture_output=True, text=True, timeout=30)
    entries = subprocess.run([blastdbcmd, "-db", str(prefix), "-entry", "all",
                              "-outfmt", "%i"],
                             check=True, capture_output=True, text=True, timeout=30)
    returned_ids = {
        line.split()[0].removeprefix("lcl|")
        for line in entries.stdout.splitlines() if line.strip()
    }
    expected_ids = set(sequences)
    if returned_ids != expected_ids or f"{len(sequences)} sequences" not in info.stdout:
        raise RuntimeError("blastdbcmd index membership does not match synthetic panel FASTA")
    indexes = sorted(root.glob(prefix.name + ".*"))
    records = []
    for index, (name, seq) in enumerate(sequences.items(), 1):
        role = (
            "satellite_subviral"
            if index <= 3 or name == "SYN006.1" else "virus_helper"
        )
        records.append({
            "accession_version": f"SYN{index:03d}.1", "role": role,
            "subrole": "satellite_rna" if role == "satellite_subviral" else "other_virus",
            "curation_state": "REVIEWED", "source_study_ids": [f"m31-synthetic-{index}"],
            "taxid": 0, "source_organism": None, "length": len(seq),
            "sequence_sha256": sha(seq.encode()), "source_response_sha256": sha(name.encode()),
        })
    document = {
        "schema": "m8-reference-snapshot-manifest-v1",
        "snapshot_id": "m31-synthetic-panel-v1",
        "retrieved_utc": "2026-01-01T00:00:00Z", "status": "EXTERNAL_ONLY",
        "provider": "M31 deterministic synthetic generator", "database": "synthetic-only",
        "request_endpoint": "fixture://m31", "retrieval_method": "fixed-seed generator",
        "normalization": "uppercase ASCII; deterministic A/C/G/T",
        "taxonomy_provenance": "synthetic fixture; no taxonomy claim",
        "rights": {"redistribution_class": "A", "provider_policy_urls": ["https://example.invalid/synthetic"],
                   "record_scan": "synthetic", "analysis_disposition": "synthetic-only",
                   "redistribution_disposition": "APPROVED", "publication_supplements": "synthetic"},
        "payload_storage": "M31 generated workspace output",
        "panel_fasta": {"external_filename": fasta_path.name, "sha256": sha(fasta_bytes),
                        "size_bytes": len(fasta_bytes), "record_count": len(records),
                        "total_bases": sum(map(len, sequences.values()))},
        "blast_toolchain": {
            "release": profile.BLAST_RELEASE, "archive_url": profile.BLAST_ARCHIVE_URL,
            "archive_md5_from_ncbi_sidecar": profile.BLAST_ARCHIVE_MD5,
            "archive_sha256_recomputed_from_fresh_download": profile.BLAST_ARCHIVE_SHA256,
            "blastn_sha256": profile.BLASTN_BINARY_SHA256,
            "makeblastdb_sha256": profile.MAKEBLASTDB_BINARY_SHA256,
            "makeblastdb_command": "makeblastdb -in panel.fasta -dbtype nucl -parse_seqids -out synthetic_panel",
            "index_validation": "blastdbcmd -info reported complete synthetic database; blastdbcmd -entry all returned the same sequence IDs listed below",
            "database_search_performed": False,
            "index_files_external": [{"filename": p.name, "sha256": sha(p.read_bytes()),
                                      "size_bytes": p.stat().st_size} for p in indexes],
        },
        "records": records,
        "snapshot_digest_algorithm": "SHA-256 canonical JSON excluding snapshot digest fields",
    }
    document["snapshot_digest"] = _digest_json(document)
    manifest = root / "manifest.json"
    _write_json(manifest, document)
    return manifest, fasta_path, indexes, document


def _strong(rows):
    return any(
        row.get("alignment", {}).get("percent_identity", 0) >= 90
        and row.get("alignment", {}).get("query_coverage", 0) >= 0.30
        for row in rows
    )


def triage(query_rows, matches):
    """Triage synthetic evidence only; never infer biological identity."""
    by_candidate = {}
    for match in matches:
        by_candidate.setdefault(match["candidate_id"], {}).setdefault(
            match["panel_role"], []).append(match)
    grouped = {}
    for query in query_rows:
        grouped.setdefault(query["candidate_id"], {})[query["panel_role"]] = query
    outcomes = []
    for cid, roles in sorted(grouped.items()):
        target = _strong(by_candidate.get(cid, {}).get("satellite_subviral", []))
        helper = _strong(by_candidate.get(cid, {}).get("virus_helper", []))
        completed = all(roles.get(role, {}).get("aggregate_status") == "COMPLETE"
                        for role in ROLES)
        if not completed:
            outcome, reason = "INSUFFICIENT_EVIDENCE", "M8 aggregate search is incomplete."
        elif _low_complexity(cid, by_candidate.get(cid, {}), query_rows):
            outcome, reason = "INSUFFICIENT_EVIDENCE", "Alignment is low-complexity-sensitive and requires review."
        elif target and helper:
            outcome, reason = "CONFLICTING_EVIDENCE", "Strong alignments occur in both synthetic panel roles."
        elif target:
            outcome, reason = "REVIEW_PRIORITY", "Strong synthetic target-role similarity; identity and M29 support remain unestablished."
        elif helper:
            outcome, reason = "BACKGROUND_LIKE", "Strong helper-role synthetic similarity; this is panel-relative only."
        else:
            outcome, reason = "INSUFFICIENT_EVIDENCE", "No qualifying synthetic-panel alignment; this is not evidence of novelty."
        outcomes.append({"candidate_id": cid, "split": "see separate truth sidecar",
                         "outcome": outcome, "reason": reason,
                         "m29_linkage": "NOT_SUPPLIED",
                         "m29_reason": "No original M29 assembly/read-support artifact bundle was supplied."})
    return outcomes


def _low_complexity(candidate_id, _matches, query_rows):
    # Candidate-sequence complexity is derived from the synthetic input bytes,
    # never from retrospective labels; the actual sequence is attached below.
    row = next((value for value in query_rows if value.get("candidate_id") == candidate_id), {})
    return row.get("low_complexity") is True


def run(output, blastn, makeblastdb, blastdbcmd=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtime = inspect_blast_runtime({"blastn_executable": str(Path(blastn).resolve()),
                                     "makeblastdb_executable": str(Path(makeblastdb).resolve())})
    if runtime["status"] != "available":
        raise RuntimeError(f"Frozen M8 runtime verification failed: {runtime}")
    blastdbcmd = blastdbcmd or str(Path(makeblastdb).with_name("blastdbcmd"))
    fixture = _synthetic_sequences()
    candidate = _candidate_handoff(output / "candidate_input", fixture["queries"])
    manifest, fasta, indexes, panel_doc = _panel(output / "reference", fixture["panel"], blastn, makeblastdb, blastdbcmd)
    _write_json(output / "candidate_truth.json", {"schema": "m31-retrospective-truth-v1", "cases": fixture["truth"]})
    _write_json(output / "reference_truth.json", {
        "schema": "m31-reference-truth-v1",
        "records": [{"panel_id": key, "synthetic_role": (
            "target" if idx <= 3 or key == "SYN006.1" else "background"
        )} for idx, key in enumerate(fixture["panel"], 1)],
    })
    roles = {role: ({"status": "SELECTED"} if role in ROLES else
                    {"status": "NOT_SELECTED", "reason": "outside synthetic panel"})
             for role in sorted(m8_contracts.PANEL_ROLES)}
    spec_inputs = {
        "candidate_sequence_set": {"path": str(candidate.relative_to(output)), "artifact_type": "m8_candidate_sequence_set"},
        "reference_snapshot_manifest": {"path": str(manifest.relative_to(output)), "artifact_type": "m8_reference_snapshot_manifest"},
    }
    for path in [fasta, *indexes]:
        spec_inputs[payload_input_name(path.name)] = {
            "path": str(path.relative_to(output)), "artifact_type": "m8_reference_payload",
        }
    spec = {"schema": "artifact-workflow-v1", "stages": [{
        "id": "m8-synthetic", "kind": "m8_homology", "inputs": spec_inputs,
        "config": {"role_plan": roles, "blastn_executable": str(Path(blastn).resolve()),
                   "makeblastdb_executable": str(Path(makeblastdb).resolve())},
    }]}
    spec_path = output / "workflow_spec.json"
    _write_json(spec_path, spec)
    artifact_workflow.run(spec_path, output / "workflow", artifact_workflow.build_default_registry())
    workflow = json.loads((output / "workflow" / "workflow.json").read_text())
    stage_dir = output / "workflow" / workflow["stages"][0]["output_path"]
    query_doc = json.loads((stage_dir / "query_status.json").read_text())
    match_doc = json.loads((stage_dir / "matches.json").read_text())
    query_for_triage = []
    for query in query_doc["queries"]:
        query_for_triage.append({**query, "low_complexity": False})
    sequence_by_id = {cid: seq for cid, seq, _split in fixture["queries"]}
    for row in query_for_triage:
        seq = sequence_by_id.get(row["candidate_id"], "")
        if len(seq) >= 3:
            counts = {}
            for i in range(len(seq) - 2):
                kmer = seq[i:i + 3]
                counts[kmer] = counts.get(kmer, 0) + 1
            row["low_complexity"] = max(counts.values(), default=0) / max(1, len(seq) - 2) >= 0.20
    outcomes = triage(query_for_triage, match_doc["matches"])
    split_by_id = {row["candidate_id"]: row["split"] for row in fixture["truth"]}
    for row in outcomes:
        row["split"] = split_by_id[row["candidate_id"]]
    summary_doc = json.loads((stage_dir / "summary.json").read_text())
    commands_doc = json.loads((stage_dir / "commands.json").read_text())
    raw_files = sorted(stage_dir.glob("*.tsv"))
    report = {
        "schema": SCHEMA, "synthetic_only": True, "external_biological_queries": False,
        "biological_data_used": False, "production_defaults_changed": False,
        "governance": {"decision": "INCOMPLETE", "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
                       "biological_execution_authorized": False},
        "runtime": runtime, "m8_aggregate_status": query_doc["aggregate_status"],
        "candidate_count": len(fixture["queries"]), "m8_match_count": len(match_doc["matches"]),
        "panel_snapshot_digest": panel_doc["snapshot_digest"],
        "synthetic_design": {
            "seed": SEED,
            "panel_roles": {
                "satellite_subviral": ["SYN001.1", "SYN002.1", "SYN003.1", "SYN006.1"],
                "virus_helper": ["SYN004.1", "SYN005.1"],
            },
            "held_out_sequence_family": "SYN006.1 is generated from an independent seed, separate from development target SYN001.1.",
            "truth_sidecars": ["candidate_truth.json", "reference_truth.json"],
            "truth_passed_to_screening_or_triage": False,
        },
        "candidate_input_sha256": sha(candidate.read_bytes()),
        "reference_fasta_sha256": sha(fasta.read_bytes()),
        "m29_linkage_status": "NOT_SUPPLIED",
        "m29_linkage_reason": "The merged M29 report is present, but no original per-run assembly/read-support artifacts were retained in the repository or supplied with this request.",
        "triage_rules": {
            "strong_alignment": "percent_identity >= 90 and query_coverage >= 0.30",
            "review_priority": "strong satellite_subviral synthetic-panel hit only",
            "background_like": "strong virus_helper synthetic-panel hit only",
            "conflicting_evidence": "strong hits to both synthetic panel roles",
            "insufficient_evidence": "incomplete selected-role screen, low-complexity-sensitive query, or no qualifying hit",
            "abstention_boundary": "Missing M29 support permits panel-relative triage but blocks biological acceptance; incomplete M8 evidence forces triage abstention.",
            "claim_boundary": "Triage is panel-relative and does not identify a biological sequence.",
        },
        "triage": outcomes, "m8_queries": query_doc["queries"], "m8_matches": match_doc["matches"],
        "m8_summary": summary_doc, "search_commands": commands_doc,
        "raw_output_artifacts": [{"filename": p.name, "sha256": sha(p.read_bytes()),
                                  "size_bytes": p.stat().st_size} for p in raw_files],
        "conclusion": "Frozen M8 executed with the verified pinned runtime on synthetic inputs. Triage summarizes only synthetic-panel similarity; M29 measured support is NOT_SUPPLIED and final biological sensitivity/specificity remain NOT_EVALUATED.",
    }
    _write_json(output / "M31_SYNTHETIC_EVIDENCE_SCREENING.json", report)
    (output / "M31_SYNTHETIC_EVIDENCE_SCREENING.md").write_text(
        render_markdown(report), encoding="utf-8",
    )
    return report


def render_markdown(report):
    lines = [
        "# M31 — Reproducible Synthetic Evidence Screening and Candidate Triage",
        "",
        "**Conclusion:** " + report["conclusion"],
        "",
        "## Runtime verification",
        "",
        f"Profile: `{report['runtime']['profile_id']}`; release `{report['runtime']['release']}`.",
        "",
        "| Executable | Version | SHA-256 | Pinned |",
        "|---|---|---|---|",
    ]
    for name in ("blastn", "makeblastdb"):
        row = report["runtime"][name]
        lines.append(f"| {name} | {row.get('version')} | `{row.get('sha256')}` | {row.get('hash_pinned')} |")
    lines += [
        "",
        f"Platform: {report['runtime']['platform']['system']} {report['runtime']['platform']['machine']}. "
        f"M8 aggregate status: **{report['m8_aggregate_status']}**.",
        "",
        "## Frozen screening and triage",
        "",
        f"Panel digest: `{report['panel_snapshot_digest']}`. Candidate input digest: `{report['candidate_input_sha256']}`. "
        f"Synthetic reference FASTA digest: `{report['reference_fasta_sha256']}`.",
        "",
        "The short and partial held-out queries derive from the separately seeded SYN006.1 family, not the development target. "
        "Retrospective truth is stored in separate sidecars and is not passed to M8 or triage.",
        "",
        "The unmodified M8 workflow ran both frozen DUST masking branches and selected its task by query length. "
        "M8 alignments remain similarity evidence only. Triage criteria were frozen in code before the held-out cases were evaluated.",
        "",
        "| Candidate | Split | M8 outcome | Triage | Reason | M29 linkage |",
        "|---|---|---|---|---|---|",
    ]
    for item in report["triage"]:
        lines.append(f"| {item['candidate_id']} | {item['split']} | completed stage; see JSON | "
                     f"{item['outcome']} | {item['reason']} | {item['m29_linkage']} |")
    lines += [
        "",
        "Full normalized alignment rows, both masking-branch statuses, commands, truncation indicators, and raw-output hashes are in the JSON report and generated M8 run directory.",
        "",
        "## M29 linkage and final metrics",
        "",
        f"**M29 linkage: {report['m29_linkage_status']}.** {report['m29_linkage_reason']}",
        "",
        "The M31 candidate handoff is a synthetic M8 contract fixture with M6 support set to NOT_EVALUATED; it is not real M6 or M29 support. The truth files are retrospective-only and are not passed to M8 or triage.",
        "",
        "Final biological discovery sensitivity, specificity and false-discovery rate: **NOT_EVALUATED**. Triage is not a biological acceptance classifier.",
        "",
        "## Reproduction",
        "",
        "Download the archive from the pinned URL in `m8_blastn_profile.py`, verify its SHA-256 and both executable hashes, extract BLAST+ 2.17.0+, then run:",
        "",
        "```sh",
        "export LD_LIBRARY_PATH=/path/to/libgomp-directory${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}",
        "PYTHONPATH=. python -m satellite_discovery.m31_synthetic_evidence_screening --output /tmp/m31-run --blastn /path/to/blastn --makeblastdb /path/to/makeblastdb",
        "```",
        "",
        "Only deterministic synthetic sequences are generated. No external biological reference database is queried.",
        "",
        "## Governance",
        "",
        "```text",
        f"decision={report['governance']['decision']}",
        f"overall_state={report['governance']['overall_state']}",
        f"biological_execution_authorized={str(report['governance']['biological_execution_authorized']).lower()}",
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--blastn", default=os.environ.get("BLASTN_EXECUTABLE"))
    parser.add_argument("--makeblastdb", default=os.environ.get("MAKEBLASTDB_EXECUTABLE"))
    parser.add_argument("--blastdbcmd", default=os.environ.get("BLASTDBCMD_EXECUTABLE"))
    args = parser.parse_args(argv)
    if not args.blastn or not args.makeblastdb:
        parser.error("provide --blastn/--makeblastdb or BLASTN_EXECUTABLE/MAKEBLASTDB_EXECUTABLE")
    print(json.dumps(run(args.output, args.blastn, args.makeblastdb, args.blastdbcmd)["governance"], sort_keys=True))


if __name__ == "__main__":
    main()
