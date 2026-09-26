"""Typed, checksum-bound local BLASTP stage for M9 protein hypotheses."""

from datetime import datetime, timezone
import json
import shutil
import tempfile
from pathlib import Path

from . import artifact_contracts
from .m9_reference_snapshot import (
    ReferenceSnapshotError,
    validate_snapshot,
)
from .m9_search_adapters import (
    PROFILE_ID,
    STATUS_EMPTY,
    STATUS_MATCH,
    build_protein_database,
    inspect_blastp_runtime,
    profile_identity,
    run_blastp,
)
from .review_stage import execute
from .sequence_downloader import checksum, write_json


STAGE_VERSION = "1"
_INPUT_TYPES = {
    "orf_results": "m9_orf_results",
    "protein_fasta": "m9_protein_fasta",
    "reference_manifest": "m9_protein_reference_manifest",
    "reference_payload": "m9_protein_reference_payload",
}
_OUTPUT_TYPES = {
    "query_status.json": "m9_protein_search_status",
    "matches.json": "m9_protein_match_evidence",
    "summary.json": "m9_protein_summary",
    "commands.json": "m9_search_commands",
    "m9_bundle.json": "m9_output_bundle",
}
_SEMANTIC_TYPES = frozenset({
    *_INPUT_TYPES.values(),
    "m9_protein_search_status",
    "m9_protein_match_evidence",
    "m9_protein_summary",
    "m9_search_commands",
    "m9_output_bundle",
    "m9_raw_blast_output",
})
_CONFIG_FIELDS = {
    "blastp_executable", "makeblastdb_executable",
    "timeout_seconds", "max_output_bytes",
}


def validate_config(config):
    if not isinstance(config, dict) or set(config) - _CONFIG_FIELDS:
        raise ValueError("M9 BLASTP configuration has unsupported fields")
    result = dict(config)
    for key in ("blastp_executable", "makeblastdb_executable"):
        value = result.get(key)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"{key} must be a non-empty executable path")
    timeout = result.get("timeout_seconds", 180)
    byte_limit = result.get("max_output_bytes", 400_000_000)
    if type(timeout) is not int or not 1 <= timeout <= 86_400:
        raise ValueError("timeout_seconds must be an integer from 1 to 86400")
    if type(byte_limit) is not int or not 1 <= byte_limit <= 400_000_000:
        raise ValueError("max_output_bytes must be an integer from 1 to 400000000")
    result["timeout_seconds"] = timeout
    result["max_output_bytes"] = byte_limit
    return result


def implementation_identity():
    paths = (
        Path(__file__),
        Path(__file__).with_name("m9_search_adapters.py"),
        Path(__file__).with_name("m9_reference_snapshot.py"),
        Path(__file__).with_name("m9_contracts.py"),
        Path(__file__).with_name("review_stage.py"),
        Path(__file__).with_name("sequence_downloader.py"),
        Path(__file__).with_name("bounded_process.py"),
        Path(__file__).with_name("stage_lock.py"),
        Path(__file__).with_name("portable_paths.py"),
    )
    return {
        "schema": "m9-blastp-stage-identity-v1",
        "artifact_contract_semantics": artifact_contracts.semantic_identity(
            _SEMANTIC_TYPES),
        "source_sha256": {path.name: checksum(path) for path in paths},
        "profile": profile_identity(),
    }


def inspect_dependency(config):
    """Report the pinned ordinary BLASTP runtime in workflow-compatible form."""
    config = validate_config(config or {})
    runtime = inspect_blastp_runtime(config)
    dependencies = []
    for name in ("blastp", "makeblastdb"):
        row = runtime[name]
        dependencies.append({
            "tool": name,
            "status": "available" if row.get("pinned") else "missing",
            "path": row.get("path"),
            "version": row.get("version"),
            "sha256": row.get("sha256"),
        })
    return {
        "status": "available" if runtime["status"] == "available" else "dependency_missing",
        "dependencies": dependencies,
        "runtime": runtime,
        "profile": runtime["profile"],
    }


def _read_proteins(path):
    records = {}
    current = None
    chunks = []

    def finish():
        if current is not None:
            records[current] = "".join(chunks)

    with Path(path).open("rb") as stream:
        for raw in stream:
            line = raw.rstrip(b"\r\n")
            if not line:
                continue
            if line.startswith(b">"):
                finish()
                token = line[1:].split(None, 1)[0]
                current = token.decode("ascii")
                if not current or current in records:
                    raise ValueError("duplicate or empty protein FASTA identifier")
                chunks = []
            else:
                if current is None:
                    raise ValueError("protein sequence precedes FASTA header")
                chunks.append(line.decode("ascii"))
    finish()
    return records


def _source_input(path, artifact_type):
    path = Path(path)
    return {
        "artifact_type": artifact_type,
        "sha256": checksum(path),
        "size_bytes": path.stat().st_size,
    }


def _raw_record(path, artifact_type):
    path = Path(path)
    return {
        "path": path.name,
        "artifact_type": artifact_type,
        "sha256": checksum(path),
        "size_bytes": path.stat().st_size,
    }


def _copy_log(source, destination):
    source = Path(source)
    if source.is_file():
        shutil.copyfile(source, destination)
        return Path(destination)
    return None


def _validate_inputs(paths):
    details = {}
    for name, artifact_type in _INPUT_TYPES.items():
        if name not in paths:
            raise ValueError(f"M9 BLASTP requires {name}")
        details[name] = artifact_contracts.validate_artifact(
            paths[name], artifact_type)
    return details


def _collect_orfs(results):
    queries = {}
    candidates = results.get("candidates", [])
    for candidate in candidates:
        for orf in candidate.get("orfs", []):
            query_id = orf["orf_id"]
            if query_id in queries:
                raise ValueError("duplicate ORF identifier in M9 results")
            queries[query_id] = {
                "length": orf["protein_length"],
                "sequence": orf["protein_sequence"],
                "sequence_sha256": orf["protein_sha256"],
                "candidate_id": orf["candidate_id"],
                "sequence_id": orf["sequence_id"],
                "source_sequence_sha256": orf["source_sequence_sha256"],
                "source_sequence_length": orf["source_sequence_length"],
                "orf": orf,
            }
    return candidates, queries


def _query_status(query_id, query, status, *, row_count=0, reason=None,
                  snapshot_id=None, snapshot_digest=None):
    orf = query["orf"]
    return {
        "query_id": query_id,
        "candidate_id": query["candidate_id"],
        "sequence_id": query["sequence_id"],
        "source_sequence_sha256": query["source_sequence_sha256"],
        "source_sequence_length": query["source_sequence_length"],
        "query_sha256": query["sequence_sha256"],
        "query_length": query["length"],
        "orf_partial": orf["partial"],
        "orf_coordinates": orf["original_span"],
        "strand": orf["strand"],
        "frame": orf["frame"],
        "status": status,
        "row_count": row_count,
        "reason": reason,
        "snapshot_id": snapshot_id,
        "snapshot_digest": snapshot_digest,
    }


def _candidate_statuses(candidates, query_statuses):
    by_candidate = {}
    for row in query_statuses:
        by_candidate.setdefault(row["candidate_id"], []).append(row)
    rows = []
    for candidate in candidates:
        matching = by_candidate.get(candidate["candidate_id"], [])
        if candidate["orf_status"] == "NO_ORF_PREDICTED_WITHIN_POLICY":
            status = "NOT_RUN_NO_ORF"
        elif candidate["orf_status"] == "CANDIDATE_SEQUENCE_UNAVAILABLE":
            status = "CANDIDATE_SEQUENCE_UNAVAILABLE"
        elif candidate["orf_status"] == "INPUT_INVALID":
            status = "INPUT_INVALID"
        elif matching:
            bad = next((row["status"] for row in matching
                        if row["status"] not in {
                            STATUS_MATCH, STATUS_EMPTY,
                            "REFERENCE_SNAPSHOT_INCOMPLETE",
                        }), None)
            if bad:
                status = bad
            elif any(row["status"] == STATUS_MATCH for row in matching):
                status = STATUS_MATCH
            elif any(row["status"] == "REFERENCE_SNAPSHOT_INCOMPLETE"
                     for row in matching):
                status = "REFERENCE_SNAPSHOT_INCOMPLETE"
            else:
                status = STATUS_EMPTY
        else:
            status = "INPUT_INVALID"
        rows.append({
            "candidate_id": candidate["candidate_id"],
            "sequence_id": candidate["sequence_id"],
            "orf_status": candidate["orf_status"],
            "expected_query_count": candidate["expected_orf_count"],
            "observed_query_count": len(matching),
            "status": status,
        })
    return rows


def run_stage(inputs, output, config):
    """Run one scoped ordinary BLASTP plan and retain explicit query status."""
    config = validate_config(config)
    if set(inputs) != set(_INPUT_TYPES):
        raise ValueError("M9 BLASTP requires exactly its four typed inputs")

    def produce(paths, directory):
        details = _validate_inputs(paths)
        try:
            results = json.loads(paths["orf_results"].read_text(encoding="utf-8"))
            candidates, query_map = _collect_orfs(results)
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError,
                TypeError, ValueError) as error:
            results = {}
            candidates = []
            query_map = {}
            input_error = str(error)[:1000]
        else:
            input_error = None

        expected_ids = sorted(query_map)
        snapshot = None
        snapshot_state = "INVALID"
        snapshot_error = None
        try:
            reference_manifest = json.loads(
                paths["reference_manifest"].read_text(encoding="utf-8"))
            snapshot = validate_snapshot(
                reference_manifest, paths["reference_payload"],
                require_complete=False,
            )
            snapshot_state = (
                "VALID" if snapshot["completeness"] == "complete"
                else "INCOMPLETE"
            )
        except (OSError, UnicodeError, json.JSONDecodeError,
                ReferenceSnapshotError, TypeError, ValueError) as error:
            snapshot_error = str(error)[:1000]

        query_statuses = []
        match_rows = []
        runtime_report = inspect_blastp_runtime(config)
        build_report = None
        search_report = None
        raw_records = []
        timeout = config["timeout_seconds"]
        max_bytes = config["max_output_bytes"]

        try:
            proteins = _read_proteins(paths["protein_fasta"])
        except (OSError, UnicodeError, ValueError) as error:
            proteins = {}
            input_error = input_error or str(error)[:1000]
        expected_proteins = {
            query_id: query["sequence"] for query_id, query in query_map.items()
        }
        if proteins != expected_proteins:
            input_error = input_error or (
                "Protein FASTA records do not match the checksum-bound ORF results.")

        if input_error:
            query_statuses = [
                _query_status(
                    query_id, query, "INPUT_INVALID", reason=input_error,
                    snapshot_id=(snapshot or {}).get("snapshot_id"),
                    snapshot_digest=(snapshot or {}).get("snapshot_digest"),
                )
                for query_id, query in sorted(query_map.items())
            ]
        elif not query_map:
            query_statuses = []
        elif snapshot_state == "INVALID":
            query_statuses = [
                _query_status(
                    query_id, query, "REFERENCE_SNAPSHOT_INVALID",
                    reason=snapshot_error or "Reference snapshot validation failed.",
                )
                for query_id, query in sorted(query_map.items())
            ]
        elif runtime_report["status"] != "available":
            query_statuses = [
                _query_status(
                    query_id, query, "DEPENDENCY_UNAVAILABLE",
                    reason="Pinned BLASTP 2.16.0 runtime is unavailable.",
                    snapshot_id=snapshot["snapshot_id"],
                    snapshot_digest=snapshot["snapshot_digest"],
                )
                for query_id, query in sorted(query_map.items())
            ]
        else:
            with tempfile.TemporaryDirectory(
                    prefix="m9-blastp-", dir=str(directory)) as temporary:
                temporary = Path(temporary)
                database_prefix = temporary / "protein_reference"
                build_report = build_protein_database(
                    paths["reference_payload"], database_prefix,
                    config=config, output_directory=temporary,
                    timeout=timeout, max_bytes=max_bytes,
                )
                for source_name, output_name in (
                    ("makeblastdb.stdout.log", "makeblastdb.stdout.log"),
                    ("makeblastdb.stderr.log", "makeblastdb.stderr.log"),
                ):
                    copied = _copy_log(temporary / source_name,
                                       Path(directory) / output_name)
                    if copied:
                        raw_records.append(_raw_record(copied, "m9_raw_blast_output"))

                if build_report["status"] != "SEARCH_COMPLETED":
                    status = build_report["status"]
                    if status not in {
                        "DEPENDENCY_UNAVAILABLE", "SEARCH_FAILED",
                        "SEARCH_INTERRUPTED", "SEARCH_TRUNCATED",
                    }:
                        status = "SEARCH_FAILED"
                    query_statuses = [
                        _query_status(
                            query_id, query, status,
                            reason="Protein reference database build did not complete.",
                            snapshot_id=snapshot["snapshot_id"],
                            snapshot_digest=snapshot["snapshot_digest"],
                        )
                        for query_id, query in sorted(query_map.items())
                    ]
                else:
                    search_report = run_blastp(
                        paths["protein_fasta"], database_prefix,
                        directory, query_map, snapshot["reference_map"],
                        config=config, runtime=runtime_report,
                        timeout=timeout, max_bytes=max_bytes,
                    )
                    raw_path = search_report.get("raw_output")
                    if raw_path and Path(raw_path).is_file():
                        raw_records.append(_raw_record(
                            raw_path, "m9_raw_blast_output"))
                    for output_name in ("blastp.stdout.log", "blastp.stderr.log"):
                        output_path = Path(directory) / output_name
                        if output_path.is_file():
                            raw_records.append(_raw_record(
                                output_path, "m9_raw_blast_output"))

                    by_query = {}
                    for adapter_row in search_report.get("rows", []):
                        by_query.setdefault(adapter_row["query_id"], []).append(
                            adapter_row)
                        query = query_map[adapter_row["query_id"]]
                        reference = adapter_row.pop("reference")
                        row = dict(adapter_row)
                        row.update({
                            "candidate_id": query["candidate_id"],
                            "source_sequence_sha256": query["source_sequence_sha256"],
                            "query_id": adapter_row["query_id"],
                            "query_sha256": query["sequence_sha256"],
                            "snapshot_id": snapshot["snapshot_id"],
                            "snapshot_digest": snapshot["snapshot_digest"],
                            "reference_id": adapter_row["reference_id"],
                            "role": reference["role"],
                            "reference_accession_version": reference["accession_version"],
                            "reference_sha256": reference["sha256"],
                            "reference_length": reference["length"],
                            "reference_sequence_sha256": reference["sha256"],
                            "query_coverage_denominator": adapter_row["query_coverage_denominator"],
                            "reference_coverage_denominator": adapter_row["reference_coverage_denominator"],
                            "raw_score": adapter_row["score"],
                            "bit_score": adapter_row["bitscore"],
                            "gap_count": adapter_row["gap_openings"],
                            "method": "BLASTP",
                            "profile": profile_identity(),
                            "profile_id": PROFILE_ID,
                            "scope_state": (
                                "VALID" if snapshot_state == "VALID" else "INCOMPLETE"
                            ),
                        })
                        match_rows.append(row)

                    if search_report["status"] in {STATUS_MATCH, STATUS_EMPTY}:
                        for query_id, query in sorted(query_map.items()):
                            rows = by_query.get(query_id, [])
                            if snapshot_state == "INCOMPLETE":
                                status = "REFERENCE_SNAPSHOT_INCOMPLETE"
                                reason = (
                                    "Matches, if any, are limited to an incomplete reference snapshot; "
                                    "no no-hit conclusion is available.")
                            else:
                                status = STATUS_MATCH if rows else STATUS_EMPTY
                                reason = None
                            query_statuses.append(_query_status(
                                query_id, query, status, row_count=len(rows),
                                reason=reason,
                                snapshot_id=snapshot["snapshot_id"],
                                snapshot_digest=snapshot["snapshot_digest"],
                            ))
                    else:
                        status = search_report["status"]
                        for query_id, query in sorted(query_map.items()):
                            query_statuses.append(_query_status(
                                query_id, query, status,
                                reason=search_report.get(
                                    "error", "BLASTP did not complete with usable output."),
                                snapshot_id=snapshot["snapshot_id"],
                                snapshot_digest=snapshot["snapshot_digest"],
                            ))

        if snapshot_state == "INVALID":
            query_statuses = [
                _query_status(
                    query_id, query, "REFERENCE_SNAPSHOT_INVALID",
                    reason=snapshot_error or "Reference snapshot validation failed.",
                )
                for query_id, query in sorted(query_map.items())
            ]
            match_rows = []

        query_statuses.sort(key=lambda item: item["query_id"])
        match_rows.sort(key=lambda item: (
            item["query_id"], item["reference_id"], item["query_start"],
            item["reference_start"], item["hsp_ordinal"],
        ))
        accounted_ids = [row["query_id"] for row in query_statuses]
        missing_ids = sorted(set(expected_ids) - set(accounted_ids))
        candidate_statuses = _candidate_statuses(candidates, query_statuses)
        all_complete = (
            not missing_ids
            and snapshot_state == "VALID"
            and results.get("aggregate_status") == "COMPLETE"
            and all(row["status"] in {
                STATUS_MATCH, STATUS_EMPTY, "NOT_RUN_NO_ORF",
            } for row in query_statuses + candidate_statuses)
        )
        aggregate_status = "COMPLETE" if all_complete else "PARTIAL"
        accounting = {
            "expected_query_ids": expected_ids,
            "observed_query_ids": accounted_ids,
            "missing_query_ids": missing_ids,
            "match_row_count": len(match_rows),
            "queries_with_matches": sum(
                1 for row in query_statuses if row["row_count"] > 0),
            "queries_without_matches": sum(
                1 for row in query_statuses
                if row["status"] == STATUS_EMPTY),
        }
        source_inputs = {
            name: _source_input(path, _INPUT_TYPES[name])
            for name, path in sorted(paths.items())
        }
        snapshot_provenance = None
        if snapshot is not None:
            snapshot_provenance = {
                "state": snapshot_state,
                "snapshot_id": snapshot["snapshot_id"],
                "snapshot_digest": snapshot["snapshot_digest"],
                "payload_sha256": snapshot["payload_sha256"],
                "completeness": snapshot["completeness"],
                "record_count": len(snapshot["reference_map"]),
                "provenance": snapshot["provenance"],
            }
        else:
            snapshot_provenance = {
                "state": "INVALID",
                "reason": snapshot_error,
            }

        status_doc = {
            "schema": "m9-protein-search-status-v1",
            "stage_version": STAGE_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "aggregate_status": aggregate_status,
            "reference_snapshot_state": snapshot_state,
            "candidate_count": len(candidates),
            "expected_orf_query_count": len(expected_ids),
            "observed_query_count": len(accounted_ids),
            "query_accounting": {
                "expected_query_ids": expected_ids,
                "observed_query_ids": accounted_ids,
                "missing_query_ids": missing_ids,
            },
            "queries": query_statuses,
            "candidate_statuses": candidate_statuses,
            "input_error": input_error,
            "snapshot_error": snapshot_error,
            "limitations": [
                "Protein alignments are similarity evidence, not functional or biological classification.",
                "A no-hit applies only to a successfully searched, complete declared reference snapshot.",
                "Partial ORFs remain explicitly partial hypotheses.",
            ],
        }
        match_doc = {
            "schema": "m9-protein-match-evidence-v1",
            "match_count": len(match_rows),
            "matches": match_rows,
            "source_inputs": source_inputs,
            "snapshot": snapshot_provenance,
            "profile": profile_identity(),
        }
        summary_doc = {
            "schema": "m9-protein-summary-v1",
            "stage_version": STAGE_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "aggregate_status": aggregate_status,
            "source_inputs": source_inputs,
            "snapshot": snapshot_provenance,
            "tool": runtime_report,
            "profile": profile_identity(),
            "settings": {
                "timeout_seconds": timeout,
                "max_output_bytes": max_bytes,
                "dependency_identity": runtime_report,
            },
            "accounting": accounting,
            "raw_output_provenance": raw_records,
            "limitations": [
                "This stage performs local ordinary BLASTP only; it does not retrieve references.",
                "No-hit status is valid only for complete reference scope and completed output accounting.",
                "No result establishes expression, function, novelty, helper dependence, or biological reality.",
            ],
        }
        commands_doc = {
            "schema": "m9-search-commands-v1",
            "stage_version": STAGE_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "aggregate_status": aggregate_status,
            "source_inputs": source_inputs,
            "snapshot": snapshot_provenance,
            "tool": runtime_report,
            "profile": profile_identity(),
            "settings": {
                "timeout_seconds": timeout,
                "max_output_bytes": max_bytes,
            },
            "accounting": accounting,
            "database_build": build_report,
            "search": search_report,
            "raw_output_provenance": raw_records,
            "limitations": [
                "Commands are executed locally against the supplied snapshot only.",
                "Optional BLASTP-short, BLASTX and HMMER profiles are not part of this baseline.",
            ],
        }

        for filename, document in (
            ("query_status.json", status_doc),
            ("matches.json", match_doc),
            ("summary.json", summary_doc),
            ("commands.json", commands_doc),
        ):
            write_json(Path(directory) / filename, document)

        outputs = {}
        for filename, artifact_type in _OUTPUT_TYPES.items():
            if filename == "m9_bundle.json":
                continue
            path = Path(directory) / filename
            if path.is_file():
                outputs[filename] = {
                    "artifact_type": artifact_type,
                    "sha256": checksum(path),
                    "size_bytes": path.stat().st_size,
                }
        for row in raw_records:
            name = row["path"]
            path = Path(directory) / name
            if path.is_file():
                outputs[name] = {
                    "artifact_type": row["artifact_type"],
                    "sha256": row["sha256"],
                    "size_bytes": row["size_bytes"],
                }
        bundle = {
            "schema": "m9-output-bundle-v1",
            "bundle_kind": "PROTEIN_SEARCH",
            "source_inputs": source_inputs,
            "outputs": outputs,
            "aggregate_status": aggregate_status,
        }
        write_json(Path(directory) / "m9_bundle.json", bundle)
        return [name for name in _OUTPUT_TYPES if (Path(directory) / name).is_file()]

    return execute("m9-blastp-v1", inputs, output, __file__, produce)


run_stage.cache_implementation_identity = implementation_identity
run_stage.inspect_dependency = inspect_dependency
run_stage.handles_dependency_missing = True