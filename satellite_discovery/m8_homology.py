"""Typed M8 nucleotide homology workflow stage.

M8 consumes a checksum-bound M6 candidate handoff and an explicitly declared,
externally materialized reference snapshot. It records sequence-similarity
evidence only; it does not classify candidate biology.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import re
import shutil
import tempfile
from pathlib import Path

from . import m8_blastn_profile as profile
from . import m8_contracts, m8_reference_panels, m8_search_adapters
from .m8_candidate_handoff import (
    fasta_record_metadata,
    validate_candidate_sequence_set,
)
from .review_stage import execute
from .sequence_downloader import checksum, write_json


STAGE_VERSION = "1"
QUERY_STATUS_SCHEMA = "m8-query-status-v1"
MATCH_EVIDENCE_SCHEMA = "m8-match-evidence-v1"
SUMMARY_SCHEMA = "m8-homology-summary-v1"
MASKING_BRANCHES = ("dust_masked", "dust_unmasked")
_COMPLETED = {
    "SEARCH_COMPLETED_MATCHES_REPORTED",
    "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES",
}
_M7_INPUT_TYPES = {
    "m7_observations": "m7_observation_table",
    "m7_recurrence": "m7_exact_recurrence_table",
    "m7_independence": "m7_independence_summary",
    "m7_validation": "m7_validation_report",
    "m7_provenance": "m7_provenance_manifest",
}


class ReferencePanelIncompleteError(ValueError):
    """The manifest is valid, but a declared payload input is absent."""


def payload_input_name(filename):
    """Return the stable workflow input name for one manifest payload file."""
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        raise ValueError("Reference payload filename must be a simple filename")
    slug = re.sub(r"[^A-Za-z0-9_-]", "_", filename)
    if len(slug) > 44:
        slug = slug[:32] + "_" + hashlib.sha256(filename.encode("utf-8")).hexdigest()[:10]
    name = "reference_payload_" + slug
    if len(name) > 64 or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
        raise ValueError("Reference payload filename cannot be mapped to a safe input name")
    return name


def validate_config(config):
    """Validate the fixed M8 search scope without exposing BLAST tunables."""
    allowed = {"role_plan", "blastn_executable", "makeblastdb_executable",
               "timeout_seconds", "max_bytes"}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("M8 config contains unsupported fields")
    plan = config.get("role_plan")
    if not isinstance(plan, dict) or set(plan) != set(m8_contracts.PANEL_ROLES):
        raise ValueError("M8 role_plan must explicitly account for every canonical panel role")
    normalized_plan = {}
    for role in sorted(m8_contracts.PANEL_ROLES):
        entry = plan[role]
        if not isinstance(entry, dict) or set(entry) - {"status", "reason"}:
            raise ValueError(f"M8 role_plan entry for {role!r} is invalid")
        status = entry.get("status")
        if status not in {"SELECTED", "NOT_SELECTED", "NOT_APPLICABLE"}:
            raise ValueError(f"M8 role_plan status for {role!r} is invalid")
        reason = entry.get("reason")
        if status == "SELECTED":
            if reason not in (None, ""):
                raise ValueError(f"Selected M8 role {role!r} cannot have an exclusion reason")
            normalized_plan[role] = {"status": status}
        else:
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
                raise ValueError(f"M8 role {role!r} requires a bounded exclusion reason")
            normalized_plan[role] = {"status": status, "reason": reason.strip()}

    normalized = {"role_plan": normalized_plan}
    for name in ("blastn_executable", "makeblastdb_executable"):
        value = config.get(name)
        if value is not None:
            if (not isinstance(value, str) or not value.strip()
                    or "\x00" in value or len(value) > 4096):
                raise ValueError(f"{name} must be a non-empty executable path")
            normalized[name] = value
    timeout = config.get("timeout_seconds", 180)
    if type(timeout) is not int or not 1 <= timeout <= 86_400:
        raise ValueError("timeout_seconds must be an integer from 1 to 86400")
    normalized["timeout_seconds"] = timeout
    max_bytes = config.get("max_bytes", 400_000_000)
    if type(max_bytes) is not int or not 1_000_000 <= max_bytes <= 2_000_000_000:
        raise ValueError("max_bytes must be between 1000000 and 2000000000")
    normalized["max_bytes"] = max_bytes
    return normalized


def inspect_dependency(config):
    """Expose the pinned runtime identity to the workflow cache and report."""
    config = validate_config(config)
    return m8_search_adapters.inspect_blast_runtime(config)


def implementation_identity():
    """Hash only code that can change M8 output or its validated contracts."""
    paths = (
        Path(__file__),
        Path(__file__).with_name("m8_reference_panels.py"),
        Path(__file__).with_name("m8_search_adapters.py"),
        Path(__file__).with_name("m8_blastn_profile.py"),
        Path(__file__).with_name("m8_contracts.py"),
        Path(__file__).with_name("m8_candidate_handoff.py"),
        Path(__file__).with_name("bounded_process.py"),
        Path(__file__).with_name("artifact_contracts.py"),
        Path(__file__).with_name("artifact_workflow.py"),
    )
    return {
        "schema": "m8-implementation-identity-v1",
        "source_sha256": {
            path.name: checksum(path) for path in paths
        },
    }


def _read_fasta(path):
    """Read already validated FASTA bytes without normalizing their sequence."""
    fasta_record_metadata(path)
    records = {}
    current_id = None
    chunks = []

    def finish():
        if current_id is not None:
            records[current_id] = "".join(chunks)

    with Path(path).open("rb") as handle:
        for raw in handle:
            line = raw.rstrip(b"\r\n")
            if not line:
                continue
            if line.startswith(b">"):
                finish()
                token = line[1:].split(None, 1)[0]
                current_id = token.decode("ascii")
                chunks = []
            else:
                chunks.append(line.decode("ascii"))
    finish()
    return records


def _load_candidate_set(path):
    details = validate_candidate_sequence_set(path)
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    availability = document["availability"]
    sequences = {}
    fasta_ref = availability.get("fasta_artifact")
    if fasta_ref is not None:
        sequences = _read_fasta(Path(path).parent / fasta_ref["path"])
    candidates = []
    for raw in document["records"]:
        record = dict(raw)
        sequence = None
        if record.get("sequence_bytes_available") is True:
            sequence = sequences.get(record["fasta_record_id"])
            if sequence is None:
                raise ValueError(
                    f"Available candidate FASTA record is missing: {record['fasta_record_id']}")
            if (len(sequence) != record["sequence_length"]
                    or hashlib.sha256(sequence.encode("ascii")).hexdigest()
                    != record["sequence_sha256"]):
                raise ValueError(
                    f"Candidate sequence identity mismatch: {record['candidate_id']}")
        candidates.append({"record": record, "sequence": sequence})
    return details, document, candidates


def _external_payloads(inputs, manifest_path, metadata=None):
    metadata = metadata or m8_reference_panels.validate_snapshot_manifest(
        manifest_path)
    filenames = [metadata["panel_fasta_filename"]] + [
        row["filename"] for row in metadata["index_files"]
    ]
    names = [payload_input_name(name) for name in filenames]
    if len(set(names)) != len(names):
        raise ValueError("Reference payload filenames collide after input-name normalization")
    payloads = {}
    for filename, input_name in zip(filenames, names):
        if input_name not in inputs:
            raise ReferencePanelIncompleteError(
                f"Declared reference payload input is missing: {input_name}")
        payloads[filename] = inputs[input_name]
    extra = {name for name in inputs if name.startswith("reference_payload_")} - set(names)
    if extra:
        raise ValueError(f"Unexpected reference payload inputs: {sorted(extra)}")
    return metadata, payloads


def _copy_branch_files(result, scratch, output, candidate_id, role, branch):
    stem = f"blastn_{hashlib.sha256(candidate_id.encode('utf-8')).hexdigest()}_{role}_{branch}"
    artifacts = {}
    raw_path = result.get("raw_output")
    source_files = []
    if raw_path:
        raw_path = Path(raw_path)
        if raw_path.is_file() and not raw_path.is_symlink():
            source_files.append((raw_path, stem + ".tsv"))
    for suffix in ("stdout.log", "stderr.log"):
        log_path = Path(scratch) / f"blastn_{branch}.{suffix}"
        if log_path.is_file() and not log_path.is_symlink():
            source_files.append((log_path, stem + "." + suffix))
    for source, name in source_files:
        target = Path(output) / name
        shutil.copyfile(source, target)
        artifacts[name] = {
            "path": name,
            "sha256": checksum(target),
            "size_bytes": target.stat().st_size,
        }
    return artifacts


def _branch_status_for_role(result, role):
    status = result.get("status")
    rows = result.get("rows") if isinstance(result.get("rows"), list) else []
    role_rows = [
        row for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("reference"), dict)
        and row["reference"].get("role") == role
    ]
    if status in _COMPLETED:
        return (
            "SEARCH_COMPLETED_MATCHES_REPORTED" if role_rows
            else "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"
        ), role_rows
    if status in m8_contracts.SEARCH_STATUSES:
        return status, role_rows
    return "SEARCH_FAILED", role_rows


def _match_record(candidate, role, branch, row, snapshot, raw_path):
    record = candidate["record"]
    reference = row["reference"]
    m6_evidence = candidate.get("m6_evidence") or {}
    return {
        "candidate_id": record["candidate_id"],
        "sequence_id": record["sequence_id"],
        "query_fasta_record_id": record["fasta_record_id"],
        "query_sequence_sha256": record["sequence_sha256"],
        "query_length": record["sequence_length"],
        "molecule_type": record.get("molecule_type"),
        "completeness_state": record["completeness_state"],
        "m6_support_status": record["m6_support_status"],
        "source_artifact": {
            "path": record["source_artifact_id"],
            "sha256": record["source_artifact_sha256"],
        },
        "m6_evidence": {
            "reconstruction_status": m6_evidence.get("reconstruction_status"),
            "support_status": m6_evidence.get("support_status"),
            "artifact": m6_evidence.get("artifact"),
        },
        "m7_context_artifacts": candidate.get("m7_context_artifacts", {}),
        "reference_snapshot": {
            "snapshot_id": snapshot["snapshot_id"],
            "snapshot_digest": snapshot["snapshot_digest"],
            "membership_digest": snapshot["membership_digest"],
        },
        "panel_role": role,
        "masking_branch": branch,
        "reference": {
            "accession_version": reference["accession_version"],
            "role": reference["role"],
            "subrole": reference.get("subrole"),
            "sequence_sha256": reference["sequence_sha256"],
            "length": reference["length"],
            "taxid": reference.get("taxid"),
            "source_organism": reference.get("source_organism"),
            "curation_state": reference["curation_state"],
            "source_study_ids": reference.get("source_study_ids", []),
            "source_response_sha256": reference["source_response_sha256"],
        },
        "alignment": {
            "percent_identity": row["percent_identity"],
            "alignment_length": row["alignment_length"],
            "mismatches": row["mismatches"],
            "gap_openings": row["gap_openings"],
            "query_start": row["query_start"],
            "query_end": row["query_end"],
            "reference_start": row["reference_start"],
            "reference_end": row["reference_end"],
            "query_length": row["query_length"],
            "reference_length": row["reference_length"],
            "query_coverage_bases": row["query_coverage_bases"],
            "query_coverage": row["query_coverage"],
            "reference_coverage_bases": row["reference_coverage_bases"],
            "reference_coverage": row["reference_coverage"],
            "strand": row["strand"],
            "evalue": row["evalue"],
            "bitscore": row["bitscore"],
        },
        "raw_output": {
            "path": raw_path,
            "sha256": row["raw_output_sha256"],
            "row_ordinal": row["raw_row_ordinal"],
        },
    }


def _role_aggregate(candidate, role, branch_rows, role_state, reason=None):
    if role_state != "SELECTED":
        return {
            "candidate_id": candidate["record"].get("candidate_id"),
            "sequence_id": candidate["record"].get("sequence_id"),
            "panel_role": role,
            "status": role_state,
            "aggregate_status": "PARTIAL",
            "reason": reason,
            "branches": [],
        }
    statuses = [row["status"] for row in branch_rows]
    aggregate = m8_contracts.aggregate_search_status(
        statuses, required_branch_count=len(MASKING_BRANCHES))
    if aggregate == "COMPLETE":
        status = (
            "SEARCH_COMPLETED_MATCHES_REPORTED"
            if any(value == "SEARCH_COMPLETED_MATCHES_REPORTED" for value in statuses)
            else "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"
        )
    else:
        status = "PARTIAL"
    return {
        "candidate_id": candidate["record"].get("candidate_id"),
        "sequence_id": candidate["record"].get("sequence_id"),
        "panel_role": role,
        "status": status,
        "aggregate_status": aggregate,
        "branches": branch_rows,
    }


def run_stage(inputs, output, config):
    """Execute M8 with explicit panel, candidate, branch, and failure accounting."""
    config = validate_config(config)
    required = {"candidate_sequence_set", "reference_snapshot_manifest"}
    if not required <= set(inputs):
        raise ValueError("M8 requires candidate_sequence_set and reference_snapshot_manifest")
    if set(inputs) - required - set(_M7_INPUT_TYPES) - {
        name for name in inputs if name.startswith("reference_payload_")
    }:
        raise ValueError("M8 received an undeclared input name")

    def produce(paths, directory):
        output_names = []
        candidate_error = None
        candidate_details = {"availability_state": "INVALID_OUTPUT",
                             "record_count": 0, "available_sequence_count": 0}
        candidate_document = {}
        candidates = []
        try:
            candidate_details, candidate_document, candidates = _load_candidate_set(
                paths["candidate_sequence_set"])
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
            candidate_error = str(error)[:4000]

        panel_error = None
        panel_details = None
        panel_metadata = None
        panel_state = "INCOMPLETE"
        database_prefix = None
        try:
            panel_metadata = m8_reference_panels.validate_snapshot_manifest(
                paths["reference_snapshot_manifest"])
            panel_metadata, payloads = _external_payloads(
                paths, paths["reference_snapshot_manifest"], panel_metadata)
            panel_details = m8_reference_panels.validate_external_snapshot_files(
                paths["reference_snapshot_manifest"], payloads)
            panel_paths = [Path(item["path"]) for item in panel_details["index_files"]]
            parents = {item.parent.resolve() for item in panel_paths}
            prefixes = {item.name.rsplit(".", 1)[0] for item in panel_paths}
            if len(parents) != 1 or len(prefixes) != 1:
                raise ValueError("Declared BLAST index files do not share one directory and prefix")
            database_prefix = str(next(iter(parents)) / next(iter(prefixes)))
            panel_state = "VALID"
        except ReferencePanelIncompleteError as error:
            panel_error = str(error)[:4000]
            panel_state = "INCOMPLETE"
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
            panel_error = str(error)[:4000]
            panel_state = "INVALID"

        runtime = inspect_dependency(config)
        m7_artifacts = {
            name: {"path": str(paths[name]), "sha256": checksum(paths[name]),
                   "size_bytes": paths[name].stat().st_size}
            for name in sorted(_M7_INPUT_TYPES) if name in paths
        }
        selected_roles = [
            role for role, value in config["role_plan"].items()
            if value["status"] == "SELECTED"
        ]
        snapshot_roles = set(panel_metadata["roles"]) if panel_metadata else set()
        scope_error = None
        if panel_metadata and selected_roles and set(selected_roles) != snapshot_roles:
            scope_error = (
                "Selected roles must exactly match the roles present in the shared "
                "reference index; role filtering is not implicit."
            )

        sequence_state = candidate_details["availability_state"]
        queries = []
        matches = []
        commands = []
        raw_artifacts = {}
        for candidate in candidates:
            candidate["m6_evidence"] = candidate_document.get("m6_evidence")
            candidate["m7_context_artifacts"] = m7_artifacts
            record = candidate["record"]
            for role, role_config in sorted(config["role_plan"].items()):
                role_state = role_config["status"]
                if role_state != "SELECTED":
                    queries.append(_role_aggregate(
                        candidate, role, [], role_state, role_config.get("reason")))
                    continue
                branch_rows = []
                if candidate_error:
                    unavailable_status = "INPUT_INVALID"
                    unavailable_reason = candidate_error
                elif record.get("sequence_bytes_available") is not True:
                    unavailable_status = "CANDIDATE_SEQUENCE_UNAVAILABLE"
                    unavailable_reason = record.get("sequence_unavailable_reason")
                elif panel_state == "INCOMPLETE":
                    unavailable_status = "REFERENCE_PANEL_INCOMPLETE"
                    unavailable_reason = panel_error
                elif panel_state == "INVALID":
                    unavailable_status = "REFERENCE_PANEL_INVALID"
                    unavailable_reason = panel_error
                elif scope_error:
                    unavailable_status = "REFERENCE_PANEL_INCOMPLETE"
                    unavailable_reason = scope_error
                else:
                    unavailable_status = None
                    unavailable_reason = None

                for branch in MASKING_BRANCHES:
                    branch_result = {}
                    branch_artifacts = {}
                    if unavailable_status:
                        status = unavailable_status
                    elif not candidate["sequence"]:
                        status = "CANDIDATE_SEQUENCE_UNAVAILABLE"
                        unavailable_reason = "Candidate sequence bytes are unavailable."
                    else:
                        applicability = profile.method_applicability(
                            record["sequence_length"])
                        if not applicability["informative"]:
                            status = "INSUFFICIENT_INFORMATION"
                            branch_result = {
                                "status": status, "task": applicability["task"],
                                "reason": applicability["reason"], "rows": [],
                            }
                        elif runtime["status"] != "available":
                            status = "DEPENDENCY_UNAVAILABLE"
                            branch_result = {
                                "status": status, "runtime": runtime, "rows": [],
                            }
                        else:
                            candidate_token = hashlib.sha256(
                                record["candidate_id"].encode("utf-8")).hexdigest()
                            with tempfile.TemporaryDirectory(
                                    prefix=f"m8-{candidate_token[:12]}-{branch}-") as scratch:
                                query_path = Path(scratch) / "query.fasta"
                                query_path.write_text(
                                    f">{record['fasta_record_id']}\n{candidate['sequence']}\n",
                                    encoding="ascii",
                                )
                                try:
                                    branch_result = m8_search_adapters.run_blast_branch(
                                        query_path, database_prefix, scratch,
                                        {
                                            "query_id": record["fasta_record_id"],
                                            "candidate_id": record["candidate_id"],
                                            "sequence_id": record["sequence_id"],
                                            "query_length": record["sequence_length"],
                                        },
                                        {
                                            item["accession_version"]: item
                                            for item in panel_details["references"]
                                        },
                                        branch,
                                        config=config,
                                        runtime=runtime,
                                        timeout=config["timeout_seconds"],
                                        max_bytes=config["max_bytes"],
                                    )
                                except (OSError, ValueError, TimeoutError) as error:
                                    branch_result = {
                                        "status": "SEARCH_FAILED", "rows": [],
                                        "error": str(error)[:4000],
                                    }
                                branch_status, role_hits = _branch_status_for_role(
                                    branch_result, role)
                                branch_artifacts = _copy_branch_files(
                                    branch_result, scratch, directory,
                                    record["candidate_id"], role, branch)
                            status = branch_status
                            for row in role_hits:
                                tsv_artifact = next(
                                    (value for value in branch_artifacts.values()
                                     if value["path"].endswith(".tsv")), None)
                                if tsv_artifact is None:
                                    continue
                                matches.append(_match_record(
                                    candidate, role, branch, row, panel_details,
                                    tsv_artifact["path"]))
                    branch_row = {
                        "candidate_id": record["candidate_id"],
                        "sequence_id": record["sequence_id"],
                        "panel_role": role,
                        "masking_branch": branch,
                        "status": status,
                        "reason": unavailable_reason,
                        "task": branch_result.get("task"),
                        "error": branch_result.get("error"),
                        "raw_output_path": next(
                            (value["path"] for value in branch_artifacts.values()
                             if value["path"].endswith(".tsv")), None),
                        "raw_output_sha256": branch_result.get("raw_output_sha256"),
                        "truncated": branch_result.get("truncated", status == "SEARCH_TRUNCATED"),
                    }
                    branch_rows.append(branch_row)
                    for name, artifact in branch_artifacts.items():
                        raw_artifacts[name] = artifact
                    commands.append({
                        "candidate_id": record["candidate_id"],
                        "sequence_id": record["sequence_id"],
                        "panel_role": role,
                        "masking_branch": branch,
                        "status": status,
                        "argv": branch_result.get("argv"),
                        "raw_outputs": list(branch_artifacts.values()),
                    })
                queries.append(_role_aggregate(
                    candidate, role, branch_rows, role_state, unavailable_reason))

        if not candidates and selected_roles:
            upstream_status = (
                "INPUT_INVALID" if candidate_error
                else "CANDIDATE_SEQUENCE_UNAVAILABLE"
            )
            reason = candidate_error or candidate_document.get(
                "availability", {}).get("reason")
            for role in selected_roles:
                branches = [{
                    "candidate_id": None, "sequence_id": None,
                    "panel_role": role, "masking_branch": branch,
                    "status": upstream_status, "reason": reason,
                    "task": None, "error": candidate_error,
                    "raw_output_path": None, "raw_output_sha256": None,
                    "truncated": False,
                } for branch in MASKING_BRANCHES]
                queries.append({
                    "candidate_id": None, "sequence_id": None,
                    "panel_role": role, "status": upstream_status,
                    "aggregate_status": "PARTIAL", "reason": reason,
                    "branches": branches,
                })

        queries.sort(key=lambda row: (
            row.get("candidate_id") or "", row.get("sequence_id") or "",
            row["panel_role"],
        ))
        matches.sort(key=lambda row: (
            row["candidate_id"], row["panel_role"], row["masking_branch"],
            row["reference"]["accession_version"],
            row["raw_output"]["row_ordinal"],
        ))

        selected_queries = [row for row in queries if row["panel_role"] in selected_roles]
        all_selected_complete = bool(selected_roles and selected_queries) and all(
            row["aggregate_status"] == "COMPLETE" for row in selected_queries
        )
        fully_available = (
            candidate_details["availability_state"] == "AVAILABLE"
            and bool(candidates)
            and all(item["record"].get("sequence_bytes_available") is True for item in candidates)
        )
        panel_scope_valid = panel_state == "VALID" and scope_error is None
        aggregate_status = (
            "COMPLETE"
            if all_selected_complete and fully_available and panel_scope_valid
            else "PARTIAL"
        )

        role_summaries = []
        for role, role_config in sorted(config["role_plan"].items()):
            role_queries = [row for row in queries if row["panel_role"] == role]
            selected = role_config["status"] == "SELECTED"
            role_summaries.append({
                "panel_role": role,
                "status": role_config["status"],
                "reason": role_config.get("reason"),
                "reference_record_count": (
                    sum(1 for item in panel_details["references"]
                        if item["role"] == role) if panel_details else 0
                ),
                "candidate_count": len(candidates) if selected else 0,
                "match_count": sum(
                    1 for item in matches if item["panel_role"] == role
                ),
                "completed_candidate_count": sum(
                    1 for row in role_queries
                    if selected and row["aggregate_status"] == "COMPLETE"
                ),
                "no_hit_candidate_count": sum(
                    1 for row in role_queries
                    if selected and row["status"] ==
                    "SEARCH_COMPLETED_NO_MATCH_WITHIN_SEARCHED_REFERENCES"
                ),
                "partial_candidate_count": sum(
                    1 for row in role_queries
                    if selected and row["aggregate_status"] != "COMPLETE"
                ),
            })

        panel_summary = None
        if panel_metadata:
            panel_summary = {
                "snapshot_id": panel_metadata["snapshot_id"],
                "snapshot_digest": panel_metadata["snapshot_digest"],
                "schema": panel_metadata["schema"],
                "roles": panel_metadata["roles"],
                "membership_digest": panel_metadata["membership_digest"],
                "panel_fasta": (
                    panel_details["panel_fasta"] if panel_details else None
                ),
                "index_files": (
                    panel_details["index_files"] if panel_details
                    else panel_metadata["index_files"]
                ),
                "rights": panel_metadata["rights"],
                "database_prefix": database_prefix,
            }
        query_document = {
            "schema": QUERY_STATUS_SCHEMA,
            "stage_version": STAGE_VERSION,
            "aggregate_status": aggregate_status,
            "candidate_availability_state": candidate_details["availability_state"],
            "candidate_record_count": candidate_details["record_count"],
            "panel_state": (
                "INCOMPLETE" if panel_state == "VALID" and scope_error
                else panel_state
            ),
            "panel_error": panel_error,
            "scope_error": scope_error,
            "queries": queries,
        }
        match_document = {
            "schema": MATCH_EVIDENCE_SCHEMA,
            "stage_version": STAGE_VERSION,
            "match_count": len(matches),
            "matches": matches,
        }
        summary_document = {
            "schema": SUMMARY_SCHEMA,
            "stage_version": STAGE_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "aggregate_status": aggregate_status,
            "candidate_set": {
                "availability_state": candidate_details["availability_state"],
                "record_count": candidate_details["record_count"],
                "available_sequence_count": candidate_details["available_sequence_count"],
                "producer": candidate_document.get("producer"),
                "source_artifact": candidate_document.get("source_artifact"),
                "assembly_manifest": candidate_document.get("assembly_manifest"),
                "m6_evidence": candidate_document.get("m6_evidence"),
            },
            "m7_context_artifacts": m7_artifacts,
            "reference_panel_state": (
                "INCOMPLETE" if panel_state == "VALID" and scope_error
                else panel_state
            ),
            "reference_panel_error": panel_error,
            "reference_panel": panel_summary,
            "selected_role_scope_error": scope_error,
            "role_plan": config["role_plan"],
            "panel_role_results": role_summaries,
            "candidate_query_count": len(queries),
            "match_count": len(matches),
            "branch_count": sum(len(row.get("branches", [])) for row in queries),
            "branch_status_counts": dict(Counter(
                branch["status"] for query in queries
                for branch in query.get("branches", [])
            )),
            "search_profile": {
                "profile_id": profile.BLAST_PROFILE_ID,
                "release": profile.BLAST_RELEASE,
                "masking_branches": list(MASKING_BRANCHES),
                "toolchain": runtime,
            },
            "raw_outputs": [raw_artifacts[name] for name in sorted(raw_artifacts)],
            "limitations": [
                "A no-hit status applies only to the complete declared snapshot and configured search profile.",
                "Sequence-similarity evidence does not establish novelty, biological class, function, causality, or ranking.",
                "Candidates retain separate identities even when their sequence bytes are identical.",
                "M7 context is optional provenance and does not change M6 eligibility or evidence.",
            ],
        }
        commands_document = {
            "schema": "m8-search-commands-v1",
            "profile_id": profile.BLAST_PROFILE_ID,
            "runtime": runtime,
            "branches": commands,
        }
        for name, value in (
            ("query_status.json", query_document),
            ("matches.json", match_document),
            ("summary.json", summary_document),
            ("commands.json", commands_document),
        ):
            write_json(Path(directory) / name, value)
            output_names.append(name)
        output_names.extend(sorted(raw_artifacts))
        return output_names

    return execute("m8-homology-v1", inputs, output, __file__, produce)


def validate_m8_artifact(path, artifact_type):
    """Validate M8 output schemas and return compact descriptor details."""
    path = Path(path)
    if artifact_type == "m8_reference_snapshot_manifest":
        result = m8_reference_panels.validate_snapshot_manifest(path)
        return {
            "schema": result["schema"],
            "snapshot_id": result["snapshot_id"],
            "snapshot_digest": result["snapshot_digest"],
            "record_count": len(result["references"]),
            "roles": result["roles"],
        }
    if artifact_type in {"m8_reference_payload", "m8_raw_blast_output"}:
        if artifact_type == "m8_reference_payload" and path.stat().st_size == 0:
            raise ValueError("Reference payload files must be non-empty")
        return {"size_bytes": path.stat().st_size}
    if path.stat().st_size > 32_000_000:
        raise ValueError("M8 structured artifact exceeds the 32 MB contract limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("M8 structured artifacts must be JSON objects")
    expected_schemas = {
        "m8_query_status": QUERY_STATUS_SCHEMA,
        "m8_match_evidence": MATCH_EVIDENCE_SCHEMA,
        "m8_summary": SUMMARY_SCHEMA,
        "m8_search_commands": "m8-search-commands-v1",
    }
    if artifact_type not in expected_schemas:
        raise ValueError(f"Unsupported M8 artifact contract: {artifact_type}")
    expected = expected_schemas[artifact_type]
    if value.get("schema") != expected:
        raise ValueError(f"{artifact_type} has an unsupported schema")
    if artifact_type == "m8_query_status":
        queries = value.get("queries")
        if not isinstance(queries, list):
            raise ValueError("M8 query-status queries must be an array")
        if value.get("panel_state") not in {"VALID", "INVALID", "INCOMPLETE"}:
            raise ValueError("M8 query-status panel state is invalid")
        if value.get("aggregate_status") not in m8_contracts.AGGREGATE_STATUSES:
            raise ValueError("M8 query-status aggregate status is invalid")
        allowed = (
            m8_contracts.SEARCH_STATUSES
            | m8_contracts.LIFECYCLE_STATUSES
            | m8_contracts.AGGREGATE_STATUSES
        )
        for query in queries:
            if not isinstance(query, dict) or query.get("status") not in allowed:
                raise ValueError("M8 query-status row has an unknown status")
            branches = query.get("branches", [])
            if not isinstance(branches, list):
                raise ValueError("M8 query-status branches must be an array")
            if any(not isinstance(row, dict) or row.get("status") not in allowed
                   for row in branches):
                raise ValueError("M8 branch has an unknown status")
        return {
            "aggregate_status": value.get("aggregate_status"),
            "query_count": len(queries),
            "branch_count": sum(len(row.get("branches", [])) for row in queries),
        }
    if artifact_type == "m8_match_evidence":
        matches = value.get("matches")
        if not isinstance(matches, list) or value.get("match_count") != len(matches):
            raise ValueError("M8 match evidence count does not match its rows")
        required = {
            "candidate_id", "sequence_id", "query_sequence_sha256",
            "reference_snapshot", "panel_role", "masking_branch", "reference",
            "alignment", "raw_output",
        }
        if any(not isinstance(row, dict) or not required <= set(row) for row in matches):
            raise ValueError("M8 match evidence row is incomplete")
        return {"match_count": len(matches)}
    if artifact_type == "m8_search_commands":
        branches = value.get("branches")
        if not isinstance(branches, list):
            raise ValueError("M8 search commands require a branch array")
        for branch in branches:
            if not isinstance(branch, dict):
                raise ValueError("M8 search command entries must be objects")
            argv = branch.get("argv")
            if argv is not None and (
                not isinstance(argv, list)
                or any(not isinstance(arg, str) or "\x00" in arg for arg in argv)
            ):
                raise ValueError("M8 search argv must be a safe argument array")
        return {"branch_count": len(branches)}
    if value.get("aggregate_status") not in m8_contracts.AGGREGATE_STATUSES:
        raise ValueError("M8 summary aggregate status is invalid")
    if value.get("reference_panel_state") not in {
        "VALID", "INVALID", "INCOMPLETE",
    }:
        raise ValueError("M8 summary reference panel state is invalid")
    if not isinstance(value.get("panel_role_results"), list):
        raise ValueError("M8 summary requires per-role results")
    return {
        "aggregate_status": value["aggregate_status"],
        "candidate_query_count": value.get("candidate_query_count", 0),
        "match_count": value.get("match_count", 0),
        "role_count": len(value["panel_role_results"]),
    }


run_stage.cache_implementation_identity = implementation_identity
run_stage.handles_dependency_missing = True