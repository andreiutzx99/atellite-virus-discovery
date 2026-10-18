"""Synthetic-only M8/M9/M10 continuation of the frozen M20 Phase 2B run."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import random
import shutil
import subprocess
import sys

from . import (
    artifact_contracts, artifact_workflow, m20_phase2, m20_phase2b,
    m8_homology, m8_reference_panels, m9_reference_snapshot,
)

M7_TYPES = {
    "m7_observations": ("observations.json", "m7_observation_table"),
    "m7_recurrence": ("exact_recurrence.json", "m7_exact_recurrence_table"),
    "m7_independence": ("recurrence_summary.json", "m7_independence_summary"),
    "m7_validation": ("validation_report.json", "m7_validation_report"),
    "m7_provenance": ("recurrence_provenance.json", "m7_provenance_manifest"),
}
def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _verified_output(root, row, filename, artifact_type):
    stage_dir = m20_phase2._stage_dir(root, row)
    if stage_dir is None:
        return None
    manifest_path = stage_dir / "manifest.json"
    manifest = m20_phase2._json_at(stage_dir, "manifest.json")
    if not isinstance(manifest, dict):
        return None
    manifest_bytes = manifest_path.read_bytes()
    if (row.get("stage_manifest_sha256") != _sha(manifest_bytes)
            or row.get("stage_manifest_identity") != manifest.get("identity")):
        return None
    path = stage_dir / filename
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(stage_dir):
        return None
    data = path.read_bytes()
    descriptor = row.get("artifacts", {}).get(filename)
    if isinstance(descriptor, dict):
        if (descriptor.get("artifact_type") != artifact_type
                or descriptor.get("sha256") != _sha(data)
                or descriptor.get("path") != (Path(row["output_path"]) / filename).as_posix()):
            return None
        if manifest.get("output_sha256", {}).get(filename) != _sha(data):
            return None
    else:
        contract = manifest.get("output_contract", {})
        record = next((r for r in manifest.get("output_inventory", [])
                       if isinstance(r, dict) and r.get("path") == filename), None)
        if (contract.get(filename) != artifact_type or not record
                or _sha(data) != record.get("sha256")):
            return None
    try:
        artifact_contracts.validate_artifact(path, artifact_type)
    except (ValueError, OSError):
        return None
    return path


def _m7_inputs(output):
    root = Path(output) / "stages/m7"
    manifest = m20_phase2._json_at(root, "workflow.json")
    if not isinstance(manifest, dict) or manifest.get("status") != "complete":
        return {}
    row = next((r for r in manifest.get("stages", [])
                if isinstance(r, dict) and r.get("id") == "m7_recurrence"), None)
    if not row or row.get("kind") != "independent_recurrence":
        return {}
    stage_dir = m20_phase2._stage_dir(root, row)
    stage_manifest = m20_phase2._json_at(stage_dir, "manifest.json")
    if (not isinstance(stage_manifest, dict) or stage_manifest.get("status") != "complete"
            or stage_dir is None):
        return {}
    stage_manifest_path = stage_dir / "manifest.json"
    identity = stage_manifest.get("identity")
    if (row.get("stage_manifest_sha256") != _sha(stage_manifest_path.read_bytes())
            or row.get("stage_manifest_identity") != identity
            or not isinstance(identity, dict)
            or not isinstance(identity.get("implementation"), dict)
            or identity.get("schema") != "m7-stage-identity-v2"
            or identity["implementation"].get("algorithm")
            != "m7-exact-sequence-recurrence-v1"):
        return {}
    hashes = stage_manifest.get("output_sha256", {})
    artifacts = {}
    for input_name, (filename, artifact_type) in M7_TYPES.items():
        path = stage_dir / filename
        if (path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(stage_dir)
                or _sha(path.read_bytes()) != hashes.get(filename)):
            return {}
        try:
            artifact_contracts.validate_artifact(path, artifact_type)
        except (ValueError, OSError):
            return {}
        artifacts[input_name] = (path, artifact_type)
    return artifacts if len(artifacts) == len(M7_TYPES) else {}


def _run_stage(directory, stage_id, kind, inputs, config, runner, registry):
    directory.mkdir(parents=True, exist_ok=True)
    spec_path = directory / "workflow.json"
    spec_path.write_text(json.dumps({
        "schema": "artifact-workflow-v1",
        "stages": [{"id": stage_id, "kind": kind, "inputs": {
            name: {"path": str(Path(path).resolve()), "artifact_type": artifact_type}
            for name, (path, artifact_type) in inputs.items()
        }, "config": config}],
    }, sort_keys=True), encoding="utf-8")
    error = m20_phase2._execute_workflow(runner, spec_path, directory / "stages", registry)
    manifest, manifest_error = m20_phase2._safe_manifest(directory / "stages/workflow.json", None)
    return manifest, error or manifest_error, directory / "stages"


def _m8_panel(root):
    """Build a deterministic artificial nucleotide snapshot and verify its BLAST index."""
    blastn, makeblastdb, blastdbcmd = (
        shutil.which("blastn"), shutil.which("makeblastdb"), shutil.which("blastdbcmd"),
    )
    if not (blastn and makeblastdb and blastdbcmd):
        return None, "BLASTN, makeblastdb and blastdbcmd are required for the synthetic snapshot."
    panel_dir = root / "m8_panel"
    panel_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(203001)
    refs = []
    for accession, role in (("SYNM8A.1", ("satellite_subviral", "satellite_rna")),
                            ("SYNM8B.1", ("virus_helper", "other_virus"))):
        sequence = "".join(rng.choice("ACGT") for _ in range(400))
        refs.append((accession, role, sequence))
    fasta = panel_dir / "synthetic-panel.fasta"
    fasta.write_text("".join(f">{acc}\n{seq}\n" for acc, _, seq in refs), encoding="ascii")
    prefix = panel_dir / "db"
    make = subprocess.run(
        [makeblastdb, "-in", str(fasta), "-dbtype", "nucl", "-parse_seqids",
         "-out", str(prefix)], capture_output=True, text=True, timeout=60, check=False,
    )
    if make.returncode:
        return None, f"makeblastdb failed ({make.returncode}): {make.stderr[-500:]}"
    query = subprocess.run(
        [blastdbcmd, "-db", str(prefix), "-entry", "all", "-outfmt", "%a"],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if query.returncode or set(query.stdout.split()) != {r[0] for r in refs}:
        return None, "blastdbcmd could not verify exact synthetic panel membership."
    indexes = []
    for suffix in (".ndb", ".nhr", ".nin", ".not", ".nsq", ".ntf", ".nto"):
        generated = Path(str(prefix) + suffix)
        if not generated.is_file():
            return None, f"BLAST database index missing {suffix}."
        name = "synthetic-panel" + suffix
        target = panel_dir / name
        shutil.copyfile(generated, target)
        indexes.append({"filename": name, "sha256": _sha(target.read_bytes()),
                        "size_bytes": target.stat().st_size})
    fasta_bytes = fasta.read_bytes()
    tool_version = subprocess.run([blastn, "-version"], capture_output=True, text=True,
                                  timeout=10, check=False).stdout.splitlines()[0]
    records = [{
        "accession_version": acc, "role": role[0], "subrole": role[1],
        "curation_state": "SYNTHETIC_FIXED_FIXTURE", "source_study_ids": ["m20-phase3-v1"],
        "taxid": 0, "source_organism": None, "length": len(seq),
        "sequence_sha256": _sha(seq.encode()), "source_response_sha256": _sha(seq.encode()),
    } for acc, role, seq in refs]
    doc = {
        "schema": "m8-reference-snapshot-manifest-v1", "snapshot_id": "m20-phase3-synthetic-v1",
        "retrieved_utc": "2030-01-01T00:00:00Z", "status": "EXTERNAL_ONLY",
        "provider": "deterministic-synthetic-generator", "database": "M20-Phase3-only",
        "request_endpoint": "fixture://m20-phase3", "retrieval_method": "fixed synthetic sequence generator",
        "normalization": "uppercase ASCII", "taxonomy_provenance": "no taxonomy; artificial sequences",
        "rights": {"redistribution_class": "A", "provider_policy_urls": ["fixture://synthetic-terms"],
                   "record_scan": "artificial only", "analysis_disposition": "internal synthetic test",
                   "redistribution_disposition": "SYNTHETIC", "publication_supplements": "not applicable"},
        "payload_storage": "local output directory",
        "panel_fasta": {"external_filename": fasta.name, "sha256": _sha(fasta_bytes),
                        "size_bytes": len(fasta_bytes), "record_count": len(refs),
                        "total_bases": sum(len(r[2]) for r in refs)},
        "blast_toolchain": {
            "release": tool_version, "archive_url": "local installed runtime",
            "archive_md5_from_ncbi_sidecar": "not applicable",
            "archive_sha256_recomputed_from_fresh_download": "not applicable",
            "blastn_sha256": _sha(Path(blastn).read_bytes()),
            "makeblastdb_sha256": _sha(Path(makeblastdb).read_bytes()),
            "makeblastdb_command": "makeblastdb -in synthetic-panel.fasta -dbtype nucl -parse_seqids",
            "index_validation": "blastdbcmd -entry all returned the same accession.version IDs as the declared FASTA",
            "database_search_performed": False, "index_files_external": indexes,
        },
        "records": records,
        "snapshot_digest_algorithm": "SHA-256 canonical JSON excluding snapshot digest fields",
    }
    doc["snapshot_digest"] = _sha(_canonical({k: v for k, v in doc.items()
                                              if k not in {"snapshot_digest", "snapshot_digest_algorithm"}}))
    manifest = panel_dir / "manifest.json"
    manifest.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
    payloads = {m8_homology.payload_input_name(x["filename"]): panel_dir / x["filename"]
                for x in indexes}
    payloads[m8_homology.payload_input_name(fasta.name)] = fasta
    m8_reference_panels.validate_external_snapshot_files(
        manifest, {x["filename"]: panel_dir / x["filename"] for x in indexes}
        | {fasta.name: fasta},
    )
    return (manifest, payloads), None


def _protein_snapshot(root):
    directory = root / "m9_protein_panel"
    directory.mkdir(parents=True, exist_ok=True)
    sequences = [("SYNPROT1", "MKTIIALSYIFCLVFADYKDDDDK"),
                 ("SYNPROT2", "MPEPTIDEACDEFGHIKLMNPQ")]
    fasta = directory / "synthetic-proteins.faa"
    fasta.write_text("".join(f">{name}\n{seq}\n" for name, seq in sequences), encoding="ascii")
    raw = fasta.read_bytes()
    doc = {
        "schema": m9_reference_snapshot.SCHEMA, "snapshot_id": "m20-phase3-protein-v1",
        "payload_sha256": _sha(raw), "completeness": "complete",
        "records": [{"record_id": name, "accession_version": name + ".1",
                     "role": "synthetic_control", "length": len(seq),
                     "sha256": _sha(seq.encode())} for name, seq in sequences],
        "provenance": {"source": "deterministic synthetic generator", "release": "M20-Phase3-v1",
                       "rights": "artificial sequence", "terms": "fixture-only"},
    }
    doc["snapshot_digest"] = _sha(_canonical(doc))
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps(doc, sort_keys=True), encoding="utf-8")
    m9_reference_snapshot.validate_snapshot(doc, fasta)
    return manifest, fasta


def _all_artifacts(root, manifest, stage_id):
    row = next((r for r in manifest.get("stages", [])
                if isinstance(r, dict) and r.get("id") == stage_id), None)
    if not row or m20_phase2._status(row) != "COMPLETE":
        return row, {}
    stage_dir = m20_phase2._stage_dir(root, row)
    stage_manifest = m20_phase2._json_at(stage_dir, "manifest.json")
    if not isinstance(stage_manifest, dict):
        return row, {}
    found = {}
    descriptors = row.get("artifacts", {})
    for filename, descriptor in descriptors.items():
        artifact_type = descriptor.get("artifact_type") if isinstance(descriptor, dict) else None
        if not artifact_type:
            continue
        path = _verified_output(root, row, filename, artifact_type)
        if path:
            found[filename] = (path, artifact_type)
    if not descriptors:
        for filename, artifact_type in stage_manifest.get("output_contract", {}).items():
            path = _verified_output(root, row, filename, artifact_type)
            if path:
                found[filename] = (path, artifact_type)
    return row, found


def _stage_state(manifest, stage_id):
    row = next((r for r in (manifest or {}).get("stages", [])
                if isinstance(r, dict) and r.get("id") == stage_id), None)
    raw = row.get("status") if row else None
    return {
        "complete": "COMPLETE",
        "dependency_missing": "DEPENDENCY_MISSING",
        "blocked": "BLOCKED",
        "failed": "FAILED",
        "interrupted": "INCOMPLETE",
    }.get(raw, "NOT_EVALUATED")


def _context_inputs(artifacts):
    values = {}
    for filename, (path, artifact_type) in artifacts.items():
        if artifact_type == "m7_observation_table":
            name = "m7_observations"
        elif artifact_type == "m7_exact_recurrence_table":
            name = "m7_recurrence"
        elif artifact_type == "m7_independence_summary":
            name = "m7_independence"
        elif artifact_type == "m7_validation_report":
            name = "m7_validation"
        elif artifact_type == "m7_provenance_manifest":
            name = "m7_provenance"
        elif artifact_type == "m8_query_status":
            name = "m8_query_status"
        elif artifact_type == "m8_match_evidence":
            name = "m8_match_evidence"
        elif artifact_type == "m8_summary":
            name = "m8_summary"
        elif artifact_type == "m8_search_commands":
            name = "m8_search_commands"
        elif artifact_type == "m8_raw_blast_output":
            name = "m8_raw_output_" + m8_homology.payload_input_name(Path(filename).name)[18:]
        elif artifact_type == "m9_orf_results":
            name = "m9_orf_results"
        elif artifact_type == "m9_protein_fasta":
            name = "m9_protein_fasta"
        elif artifact_type == "m9_orf_bundle":
            name = "m9_orf_bundle"
        elif artifact_type == "m9_protein_search_status":
            name = "m9_protein_search_status"
        elif artifact_type == "m9_protein_match_evidence":
            name = "m9_protein_match_evidence"
        elif artifact_type == "m9_protein_summary":
            name = "m9_protein_summary"
        elif artifact_type == "m9_search_commands":
            name = "m9_search_commands"
        elif artifact_type == "m9_output_bundle":
            name = "m9_output_bundle"
        elif artifact_type == "m9_raw_blast_output":
            name = "m9_raw_output_" + m8_homology.payload_input_name(Path(filename).name)[18:]
        else:
            continue
        values[name] = (path, artifact_type)
    return values


def _compact_context_state(state):
    result = {}
    for group, details in (state or {}).items():
        artifacts = details.get("artifacts", [])
        result[group] = {
            "state": details.get("state"),
            "artifact_count": len(artifacts),
            "artifacts": [
                {"input_name": row.get("input_name"),
                 "artifact_type": row.get("artifact_type"),
                 "sha256": row.get("sha256")}
                for row in artifacts if isinstance(row, dict)
            ],
        }
    return result


def _m8_result_summary(document):
    if not isinstance(document, dict):
        return None
    return {
        "aggregate_status": document.get("aggregate_status"),
        "panel_state": document.get("panel_state"),
        "queries": [
            {
                "candidate_id": row.get("candidate_id"),
                "sequence_id": row.get("sequence_id"),
                "panel_role": row.get("panel_role"),
                "status": row.get("status"),
                "branches": [
                    {"masking_branch": branch.get("masking_branch"),
                     "status": branch.get("status"),
                     "reason": branch.get("reason")}
                    for branch in row.get("branches", []) if isinstance(branch, dict)
                ],
            }
            for row in document.get("queries", []) if isinstance(row, dict)
        ],
    }


def _m10_result_summary(bundle, artifacts):
    if not isinstance(bundle, dict):
        return None
    source = bundle.get("source_inputs", {})
    return {
        "aggregate_status": bundle.get("aggregate_status"),
        "input_status": bundle.get("input_status"),
        "candidate_count": bundle.get("candidate_count"),
        "optional_context_state": _compact_context_state(
            source.get("optional_context_state", {}),
        ),
        "outputs": {
            Path(path).name: {"artifact_type": artifact_type, "sha256": _sha(Path(path).read_bytes())}
            for path, artifact_type in artifacts.values()
        },
    }


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _read_jsonl_header(path):
    try:
        with Path(path).open(encoding="utf-8") as source:
            value = json.loads(source.readline())
        return value if isinstance(value, dict) else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _verify_frozen_phase2b(root, report):
    """Verify the published fixture bytes, accepting the frozen pre-timeout-bound manifest."""
    root = Path(root)
    files, expected_manifest, expected_truth = m20_phase2b._expected_files()
    expected_inputs = root / "inputs"
    observed = set()
    if expected_inputs.is_symlink():
        raise ValueError("Frozen Phase 2B inputs may not be symlinks.")
    for path in expected_inputs.rglob("*"):
        if path.is_symlink():
            raise ValueError("Frozen Phase 2B inputs may not contain symlinks.")
        if path.is_file():
            observed.add(path.relative_to(expected_inputs).as_posix())
    if observed != set(files):
        raise ValueError("Frozen Phase 2B input inventory differs from its fixed fixture.")
    for relative, expected in files.items():
        if (expected_inputs / relative).read_bytes() != expected:
            raise ValueError(f"Frozen Phase 2B input changed: {relative}")

    actual_manifest_path = root / "benchmark_manifest.json"
    actual_truth_path = root / "heldout_truth.json"
    if any(path.is_symlink() or not path.is_file()
           for path in (actual_manifest_path, actual_truth_path)):
        raise ValueError("Frozen Phase 2B metadata files must be regular files.")
    actual_manifest = json.loads(actual_manifest_path.read_text(encoding="utf-8"))
    expected_document = json.loads(expected_manifest)
    # The existing v2 run predates a timeout-bound-only metadata addition. All
    # fixture bytes, seeds, case definitions and other manifest values stay exact.
    frozen_document = json.loads(expected_manifest)
    frozen_document.get("matrix", {}).get("resource_bounds", {}).pop(
        "stage_timeout_seconds", None,
    )
    if actual_manifest not in (expected_document, frozen_document):
        raise ValueError("Frozen Phase 2B manifest differs beyond the known timeout-bound field.")
    actual_manifest_bytes = actual_manifest_path.read_bytes()
    truth_bytes = actual_truth_path.read_bytes()
    if truth_bytes != expected_truth:
        raise ValueError("Frozen Phase 2B held-out file differs from its fixed synthetic fixture.")
    fixtures = report.get("fixtures", {})
    if (fixtures.get("manifest_sha256") != _sha(actual_manifest_bytes)
            or fixtures.get("heldout_truth_sha256") != _sha(truth_bytes)
            or fixtures.get("case_count") != len(expected_document["cases"])
            or fixtures.get("unchanged_after_execution") is not True
            or fixtures.get("truth_outside_analysis_inputs") is not True):
        raise ValueError("Phase 2B report does not bind the verified frozen fixture hashes.")
    return _sha(actual_manifest_bytes), _sha(truth_bytes)


def _run_case(output, case, phase2b_output, m6_manifest, m7_context,
              panel, protein_snapshot, runner, registry):
    sample, case_root = case["sample_id"], Path(output) / "cases" / case["sample_id"]
    m6_root = Path(phase2b_output) / "stages/m4_m6"
    m6_row = next((r for r in m6_manifest.get("stages", [])
                   if isinstance(r, dict) and r.get("id") == f"m6_{sample}"), None)
    candidate = _verified_output(m6_root, m6_row, "candidate_sequence_set.json",
                                 "m8_candidate_sequence_set")
    candidate_state, candidate_error = "UNAVAILABLE", "M6 candidate artifact failed provenance checks."
    candidate_doc = None
    if candidate:
        from .m8_candidate_handoff import validate_candidate_sequence_set
        try:
            candidate_validation = validate_candidate_sequence_set(candidate)
            candidate_doc = _read_json(candidate)
            candidate_state = candidate_doc["availability"]["state"]
            candidate_error = candidate_validation.get("status", "VALID")
        except (ValueError, OSError, KeyError, TypeError) as error:
            candidate = None
            candidate_error = f"{type(error).__name__}: {error}"

    m8_manifest = None
    m8_error = None
    m8_artifacts = {}
    m8_result = "NOT_EVALUATED_UPSTREAM_UNAVAILABLE"
    if candidate and panel:
        manifest_path, payloads = panel
        inputs = {
            "candidate_sequence_set": (candidate, "m8_candidate_sequence_set"),
            "reference_snapshot_manifest": (manifest_path, "m8_reference_snapshot_manifest"),
        }
        inputs.update({name: (path, "m8_reference_payload") for name, path in payloads.items()})
        if m7_context:
            inputs.update(m7_context)
        role_plan = {
            role: ({"status": "SELECTED"} if role in {"satellite_subviral", "virus_helper"}
                   else {"status": "NOT_SELECTED", "reason": "outside synthetic panel scope"})
            for role in sorted(m8_homology.m8_contracts.PANEL_ROLES)
        }
        m8_manifest, m8_error, m8_outroot = _run_stage(
            case_root / "m8", "m8", "m8_homology", inputs,
            {"role_plan": role_plan, "timeout_seconds": 180, "max_bytes": 1_000_000},
            runner, registry,
        )
        _row, m8_artifacts = _all_artifacts(m8_outroot, m8_manifest, "m8")
        m8_result = _stage_state(m8_manifest, "m8")
    elif not panel:
        m8_error = "Synthetic nucleotide snapshot was unavailable."
        m8_result = "DEPENDENCY_UNAVAILABLE"

    m9_manifest = None
    m9_error = None
    m9_artifacts = {}
    m9_status = "NOT_EVALUATED"
    if candidate:
        inputs = {"candidate_sequence_set": (candidate, "m8_candidate_sequence_set")}
        if m7_context:
            inputs.update(m7_context)
        # Supply M8 context only as a complete, digest-verified producer set.
        required_m8 = {"m8_query_status", "m8_match_evidence", "m8_summary", "m8_search_commands"}
        m8_context = _context_inputs(m8_artifacts)
        if m8_result == "COMPLETE" and required_m8 <= set(m8_context):
            inputs.update(m8_context)
        m9_manifest, m9_error, m9_root = _run_stage(
            case_root / "m9_orf", "m9_orf", "m9_orf_translation",
            inputs, {}, runner, registry,
        )
        _row, m9_artifacts = _all_artifacts(m9_root, m9_manifest, "m9_orf")
        m9_status = _stage_state(m9_manifest, "m9_orf")

    blastp_manifest, blastp_error, blastp_artifacts = None, None, {}
    blastp_status = "NOT_EVALUATED_UPSTREAM_UNAVAILABLE"
    if (m9_status == "COMPLETE"
            and {"m9_orf_results", "m9_protein_fasta"} <= {
                artifact_type for _, artifact_type in m9_artifacts.values()
            }):
        protein_manifest, protein_fasta = protein_snapshot
        blast_inputs = {
            "orf_results": next(path for path, t in m9_artifacts.values()
                                if t == "m9_orf_results"),
            "protein_fasta": next(path for path, t in m9_artifacts.values()
                                  if t == "m9_protein_fasta"),
            "reference_manifest": protein_manifest,
            "reference_payload": protein_fasta,
        }
        # Convert the four required inputs to their declared artifact contracts.
        blast_inputs = {
            "orf_results": (blast_inputs["orf_results"], "m9_orf_results"),
            "protein_fasta": (blast_inputs["protein_fasta"], "m9_protein_fasta"),
            "reference_manifest": (blast_inputs["reference_manifest"], "m9_protein_reference_manifest"),
            "reference_payload": (blast_inputs["reference_payload"], "m9_protein_reference_payload"),
        }
        blastp_manifest, blastp_error, blastp_root = _run_stage(
            case_root / "m9_blastp", "m9_blastp", "m9_blastp",
            blast_inputs, {"timeout_seconds": 180, "max_output_bytes": 1_000_000},
            runner, registry,
        )
        _row, blastp_artifacts = _all_artifacts(blastp_root, blastp_manifest, "m9_blastp")
        blastp_status = _stage_state(blastp_manifest, "m9_blastp")

    m10_manifest, m10_error, m10_artifacts, m10_status = None, None, {}, "NOT_EVALUATED"
    if candidate:
        inputs = {"candidate_sequence_set": (candidate, "m8_candidate_sequence_set")}
        if m7_context:
            inputs.update(m7_context)
        m8_context = _context_inputs(m8_artifacts)
        if m8_result == "COMPLETE":
            inputs.update(m8_context)
        inputs.update(_context_inputs(m9_artifacts))
        inputs.update(_context_inputs(blastp_artifacts))
        m10_manifest, m10_error, m10_root = _run_stage(
            case_root / "m10", "m10", "m10_exact_first",
            inputs, {"max_candidate_symbols": 100_000,
                     "max_symbol_comparisons_per_branch": 2_000_000,
                     "max_evidence_rows_per_branch": 20_000}, runner, registry,
        )
        _row, m10_artifacts = _all_artifacts(m10_root, m10_manifest, "m10")
        m10_status = _stage_state(m10_manifest, "m10")

    def stage_identity(workflow, stage_id):
        row = next((r for r in (workflow or {}).get("stages", [])
                    if isinstance(r, dict) and r.get("id") == stage_id), None)
        return {
            "workflow_id": (workflow or {}).get("workflow_id"),
            "stage_id": stage_id,
            "stage_status": row.get("status") if row else None,
            "dependency_report": row.get("dependency_report") if row else None,
            "cache_key": row.get("cache_key") if row else None,
            "stage_manifest_sha256": row.get("stage_manifest_sha256") if row else None,
            "output_digests": {
                name: {"artifact_type": value.get("artifact_type"),
                       "sha256": value.get("sha256")}
                for name, value in (row.get("artifacts", {}) if row else {}).items()
                if isinstance(value, dict)
            },
            "input_digests": {
                name: {
                    "artifact_type": value.get("artifact_type"),
                    "sha256": value.get("sha256"),
                }
                for name, value in (row.get("inputs", {}) if row else {}).items()
                if isinstance(value, dict)
            },
        }

    m8_dir = next((Path(p).parent for p, t in m8_artifacts.values()
                   if t == "m8_query_status"), None)
    m9_dir = next((Path(p).parent for p, t in m9_artifacts.values()
                   if t == "m9_orf_results"), None)
    blastp_dir = next((Path(p).parent for p, t in blastp_artifacts.values()
                       if t == "m9_protein_search_status"), None)
    m10_dir = next((Path(p).parent for p, t in m10_artifacts.values()
                    if t == "m10_result_bundle"), None)
    m8_query = _read_json(m8_dir / "query_status.json") if m8_dir else None
    m8_matches = _read_json(m8_dir / "matches.json") if m8_dir else None
    m8_summary = _read_json(m8_dir / "summary.json") if m8_dir else None
    orf_results = _read_json(m9_dir / "orf_results.json") if m9_dir else None
    m8_context_validation = (
        orf_results.get("m8_context") if orf_results else None
    )
    blastp_summary = _read_json(blastp_dir / "summary.json") if blastp_dir else None
    m10_bundle = _read_json(m10_dir / "m10_bundle.json") if m10_dir else None
    m10_context = _read_jsonl_header(m10_dir / "candidate_accounting.jsonl") if m10_dir else None
    return {
        "sample_id": sample, "candidate_availability": candidate_state,
        "candidate_validation": candidate_error,
        "candidate_producer": {
            "stage_id": m6_row.get("id") if m6_row else None,
            "workflow_id": m6_manifest.get("workflow_id"),
            "stage_manifest_sha256": m6_row.get("stage_manifest_sha256") if m6_row else None,
            "candidate_artifact_sha256": _sha(candidate.read_bytes()) if candidate else None,
            "candidate_set_producer": candidate_doc.get("candidate_set") if candidate_doc else None,
        },
        "m8": {"stage_status": m8_result, "analysis_status": (
                    m8_query.get("aggregate_status") if m8_query else None),
               "error": m8_error,
               "query_status": _m8_result_summary(m8_query),
               "summary": m8_summary,
               "matches": m8_matches,
               "provenance": stage_identity(m8_manifest, "m8")},
        "m9_orf": {"status": m9_status, "error": m9_error,
                   "analysis_status": orf_results.get("aggregate_status") if orf_results else None,
                   "results_available": bool(orf_results),
                   "candidate_count": len(orf_results.get("candidates", []))
                   if orf_results else None,
                   "orf_count": sum(len(c.get("orfs", [])) for c in orf_results.get("candidates", []))
                   if orf_results else None,
                   "m8_context_validation": {
                       key: m8_context_validation.get(key)
                       for key in ("state", "reason", "stage_manifest_sha256")
                       if m8_context_validation and key in m8_context_validation
                   } if m8_context_validation else None,
                   "provenance": stage_identity(m9_manifest, "m9_orf")},
        "m9_blastp": {"status": blastp_status, "error": blastp_error,
                      "analysis_status": blastp_summary.get("aggregate_status")
                      if blastp_summary else None,
                      "summary": {
                          key: blastp_summary.get(key)
                          for key in ("schema", "aggregate_status", "query_count",
                                      "match_count", "no_hit_count", "reference_state")
                          if blastp_summary and key in blastp_summary
                      } if blastp_summary else None,
                      "provenance": stage_identity(blastp_manifest, "m9_blastp")},
        "m10": {"status": m10_status, "error": m10_error,
                "summary": _m10_result_summary(m10_bundle, m10_artifacts),
                "accounting_context": _compact_context_state(
                    m10_context.get("optional_context_state", {}) if m10_context else {}
                ),
                "provenance": stage_identity(m10_manifest, "m10")},
    }


def run(output, phase2b_output, runner=None):
    output, upstream = Path(output).absolute(), Path(phase2b_output).absolute()
    output.mkdir(parents=True, exist_ok=True)
    baseline = _read_json(upstream / "report.json")
    if (not baseline or baseline.get("schema") != "m20-phase2b-report-v2"
            or baseline.get("status") != "COMPLETE"):
        raise ValueError("Phase 3 requires a Phase 2B v2 report as its frozen upstream run.")
    if output == upstream or output.is_relative_to(upstream) or upstream.is_relative_to(output):
        raise ValueError("Phase 3 output and the frozen Phase 2B run must be separate directories.")
    manifest_hash, truth_hash = _verify_frozen_phase2b(upstream, baseline)
    m6_manifest = m20_phase2._read_json(upstream / "stages/m4_m6/workflow.json")
    if m6_manifest.get("status") != "complete":
        raise ValueError("Phase 3 requires the completed Phase 2B M4/M6 workflow.")
    m7_context = _m7_inputs(upstream)
    panel, panel_error = _m8_panel(output)
    protein_snapshot = _protein_snapshot(output)
    runner = runner or artifact_workflow.run
    registry = artifact_workflow.build_default_registry()
    records = [
        _run_case(output, case, upstream, m6_manifest, m7_context, panel,
                  protein_snapshot, runner, registry)
        for case in ({"sample_id": row["sample_id"]} for row in baseline["cases"])
    ]
    report = {
        "schema": "m20-phase3-report-v1",
        "status": "COMPLETE",
        "upstream": {
            "phase2b_schema": baseline["schema"],
            "phase2b_fixture_manifest_sha256": manifest_hash,
            "phase2b_truth_sha256": truth_hash,
            "phase1_baseline": baseline["fixtures"]["phase1_baseline"],
            "m7_context_state": "AVAILABLE" if m7_context else "UNAVAILABLE",
        },
        "reference_panels": {
            "m8_nucleotide": {
                "state": "AVAILABLE" if panel else "DEPENDENCY_UNAVAILABLE",
                "error": panel_error,
                "manifest_sha256": _sha(panel[0].read_bytes()) if panel else None,
            },
            "m9_protein": {
                "schema": "m9-protein-reference-snapshot-v1",
                "manifest_sha256": _sha(protein_snapshot[0].read_bytes()),
            },
        },
        "execution_environment": {
            "platform": platform.platform(), "python": sys.version,
            "machine": platform.machine(),
        },
        "cases": records,
        "limitations": [
            "All candidate and reference sequences are artificial; these are software-only results.",
            "M8 no-hit is limited to the synthetic snapshot and is not evidence of novelty.",
            "M9 ORFs are predictions; M10 exact architecture is not functional annotation.",
            "No biological classification, helper dependence, or accuracy claim is made.",
        ],
    }
    (output / "report.json").write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8",
    )
    from html import escape
    lines = ["# M20 Phase 3 synthetic M8/M9/M10 report", "",
             f"- Upstream Phase 2B fixture: `{report['upstream']['phase2b_fixture_manifest_sha256']}`",
             f"- M7 optional context: `{report['upstream']['m7_context_state']}`", "",
             "| Case | Candidate state | M8 | M9 ORF | M9 BLASTP | M10 |",
             "|---|---|---|---|---|---|"]
    for row in records:
        lines.append(f"| {row['sample_id']} | {row['candidate_availability']} | "
                     f"{row['m8']['stage_status']} / {row['m8']['analysis_status']} | "
                     f"{row['m9_orf']['status']} | "
                     f"{row['m9_blastp']['status']} | {row['m10']['status']} |")
    lines.extend(["", "All sequences and reference records are synthetic. M8 no-hit is "
                  "snapshot-limited; M9 ORFs are predictions; M10 output is exact "
                  "sequence architecture only.", ""])
    md = "\n".join(lines)
    (output / "report.md").write_text(md, encoding="utf-8")
    (output / "report.html").write_text(
        "<!doctype html><meta charset=utf-8><title>M20 Phase 3</title>"
        "<pre>" + escape(md) + "</pre>\n", encoding="utf-8",
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase2b-output", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output, args.phase2b_output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
