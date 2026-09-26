"""Typed M6-to-M9 ORF and protein derivation stage.

This stage preserves M6 candidate identity and provenance while deriving
table-1 protein hypotheses. It does not call a search tool or classify biology.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from . import artifact_contracts
from .m8_candidate_handoff import (
    fasta_record_metadata,
    validate_candidate_sequence_set,
)
from .m9_orf import enumerate_orfs
from .review_stage import execute
from .sequence_downloader import checksum, write_json


STAGE_VERSION = "1"
RESULTS_SCHEMA = "m9-orf-results-v1"
BUNDLE_SCHEMA = "m9-output-bundle-v1"

_CONTEXT_TYPES = {
    "m7_observations": "m7_observation_table",
    "m7_recurrence": "m7_exact_recurrence_table",
    "m7_independence": "m7_independence_summary",
    "m7_validation": "m7_validation_report",
    "m7_provenance": "m7_provenance_manifest",
    "m8_query_status": "m8_query_status",
    "m8_match_evidence": "m8_match_evidence",
    "m8_summary": "m8_summary",
    "m8_search_commands": "m8_search_commands",
}
_M8_RAW_PREFIX = "m8_raw_output_"
_OUTPUT_TYPES = {
    "orf_results.json": "m9_orf_results",
    "proteins.faa": "m9_protein_fasta",
    "orf_bundle.json": "m9_orf_bundle",
}
_SEMANTIC_TYPES = frozenset({
    "m8_candidate_sequence_set",
    "m7_observation_table", "m7_exact_recurrence_table",
    "m7_independence_summary", "m7_validation_report",
    "m7_provenance_manifest", "m8_query_status", "m8_match_evidence",
    "m8_summary", "m8_search_commands", "m8_raw_blast_output",
    "m9_orf_results", "m9_protein_fasta", "m9_orf_bundle",
})


def validate_config(config):
    if not isinstance(config, dict) or config:
        raise ValueError("M9 ORF translation accepts no configuration")
    return {}


def implementation_identity():
    """Scope cache identity to ORF derivation and the contracts it uses."""
    paths = (
        Path(__file__),
        Path(__file__).with_name("m9_orf.py"),
        Path(__file__).with_name("m8_candidate_handoff.py"),
        Path(__file__).with_name("review_stage.py"),
        Path(__file__).with_name("sequence_downloader.py"),
        Path(__file__).with_name("stage_lock.py"),
        Path(__file__).with_name("portable_paths.py"),
    )
    return {
        "schema": "m9-orf-stage-identity-v1",
        "artifact_contract_semantics": artifact_contracts.semantic_identity(
            _SEMANTIC_TYPES),
        "source_sha256": {path.name: checksum(path) for path in paths},
    }


def _read_fasta(path):
    fasta_record_metadata(path)
    records = {}
    record_id = None
    chunks = []

    def finish():
        if record_id is not None:
            records[record_id] = "".join(chunks)

    with Path(path).open("rb") as source:
        for raw_line in source:
            line = raw_line.rstrip(b"\r\n")
            if not line:
                continue
            if line.startswith(b">"):
                finish()
                header = line[1:].split(None, 1)[0]
                record_id = header.decode("ascii")
                chunks = []
            else:
                chunks.append(line.decode("ascii"))
    finish()
    return records


def _policy_digest(policy):
    canonical = json.dumps(
        policy, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _context_artifact(path, name, artifact_type):
    return {
        "input_name": name,
        "artifact_type": artifact_type,
        "path": Path(path).name,
        "sha256": checksum(path),
        "size_bytes": Path(path).stat().st_size,
    }


def _verify_m8_context(paths, candidate_sha256):
    """Verify optional M8 artifacts against one completed M8 stage manifest."""
    supplied = [
        (name, path, (
            "m8_raw_blast_output" if name.startswith(_M8_RAW_PREFIX)
            else _CONTEXT_TYPES[name]
        ))
        for name, path in sorted(paths.items())
        if name.startswith("m8_")
    ]
    if not supplied:
        return {
            "state": "NOT_SUPPLIED",
            "reason": None,
            "stage_manifest_sha256": None,
            "artifacts": [],
            "statuses": {},
        }

    manifest_paths = set()
    try:
        manifest_documents = []
        for name, path, artifact_type in supplied:
            path = Path(path)
            artifact_contracts.validate_artifact(path, artifact_type)
            manifest_path = path.parent / "manifest.json"
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise ValueError("M8 context has no regular stage manifest")
            manifest_paths.add(manifest_path.resolve())
            manifest_documents.append(json.loads(
                manifest_path.read_text(encoding="utf-8")))
        if len(manifest_paths) != 1:
            raise ValueError("M8 context artifacts do not share one stage manifest")
        manifest_path = next(iter(manifest_paths))
        manifest = manifest_documents[0]
        identity = manifest.get("identity", {})
        output_hashes = manifest.get("output_sha256", {})
        if (manifest.get("status") != "complete"
                or identity.get("stage") != "m8-homology-v1"
                or identity.get("inputs", {}).get("candidate_sequence_set")
                != candidate_sha256):
            raise ValueError(
                "M8 context is not a completed result for this M6 candidate set")
        for name, path, _artifact_type in supplied:
            path = Path(path)
            if output_hashes.get(path.name) != checksum(path):
                raise ValueError(
                    f"M8 context artifact {name!r} is not bound by its stage manifest")

        statuses = {}
        for name, path, _artifact_type in supplied:
            if name in {
                "m8_query_status", "m8_summary", "m8_match_evidence",
                "m8_search_commands",
            }:
                document = json.loads(Path(path).read_text(encoding="utf-8"))
                statuses[name] = {
                    key: document.get(key)
                    for key in ("aggregate_status", "panel_state",
                                "reference_panel_state", "match_count")
                    if key in document
                }
        return {
            "state": "VERIFIED",
            "reason": None,
            "stage_manifest_sha256": checksum(manifest_path),
            "artifacts": [
                _context_artifact(path, name, artifact_type)
                for name, path, artifact_type in supplied
            ],
            "statuses": statuses,
        }
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        return {
            "state": "INVALID_OR_INCOMPLETE",
            "reason": str(error)[:1000],
            "stage_manifest_sha256": (
                checksum(next(iter(manifest_paths)))
                if len(manifest_paths) == 1 and next(iter(manifest_paths)).is_file()
                else None
            ),
            "artifacts": [
                _context_artifact(path, name, artifact_type)
                for name, path, artifact_type in supplied
                if Path(path).is_file()
            ],
            "statuses": {},
        }


def _context_inputs(paths):
    rows = []
    for name, path in sorted(paths.items()):
        if name == "candidate_sequence_set":
            continue
        artifact_type = (
            "m8_raw_blast_output" if name.startswith(_M8_RAW_PREFIX)
            else _CONTEXT_TYPES.get(name)
        )
        if artifact_type is None:
            raise ValueError(f"Unsupported M9 context input {name!r}")
        rows.append(_context_artifact(path, name, artifact_type))
    return rows


def _candidate_set_summary(document, input_path):
    return {
        "schema": document.get("schema"),
        "sha256": checksum(input_path),
        "availability_state": document.get("availability", {}).get("state"),
        "record_count": document.get("availability", {}).get("record_count"),
        "producer": document.get("producer"),
        "source_artifact": document.get("source_artifact"),
        "assembly_manifest": document.get("assembly_manifest"),
        "m6_evidence": document.get("m6_evidence"),
    }


def run_stage(inputs, output, config):
    """Create checksum-bound ORF rows and a separate protein FASTA artifact."""
    validate_config(config)
    if "candidate_sequence_set" not in inputs:
        raise ValueError("M9 ORF translation requires candidate_sequence_set")
    if set(inputs) - ({"candidate_sequence_set"} | set(_CONTEXT_TYPES)
                      | {name for name in inputs if name.startswith(_M8_RAW_PREFIX)}):
        raise ValueError("M9 ORF translation received an undeclared input")

    def produce(paths, directory):
        input_path = paths["candidate_sequence_set"]
        details = validate_candidate_sequence_set(input_path)
        candidate_document = json.loads(input_path.read_text(encoding="utf-8"))
        fasta_ref = candidate_document["availability"].get("fasta_artifact")
        sequences = (
            _read_fasta(input_path.parent / fasta_ref["path"])
            if fasta_ref else {}
        )
        context_rows = _context_inputs(paths)
        m8_context = _verify_m8_context(
            paths, checksum(input_path))

        candidate_rows = []
        protein_records = []
        aggregate_status = "COMPLETE"
        for record in candidate_document["records"]:
            sequence_available = record["sequence_bytes_available"] is True
            row = {
                "candidate_id": record["candidate_id"],
                "sequence_id": record["sequence_id"],
                "sequence_bytes_available": record["sequence_bytes_available"],
                "sequence_sha256": (
                    record.get("sequence_sha256") if sequence_available else None
                ),
                "sequence_length": (
                    record.get("sequence_length") if sequence_available else None
                ),
                "m6_support_status": record["m6_support_status"],
                "completeness_state": record["completeness_state"],
                "molecule_type": record.get("molecule_type"),
                "fasta_record_id": (
                    record.get("fasta_record_id") if sequence_available else None
                ),
                "m6_evidence": candidate_document.get("m6_evidence"),
                "source_artifact": candidate_document.get("source_artifact"),
                "m6_record": record,
                "orf_status": "CANDIDATE_SEQUENCE_UNAVAILABLE",
                "expected_orf_count": 0,
                "observed_orf_count": 0,
                "orfs": [],
            }
            if not sequence_available:
                aggregate_status = "PARTIAL"
                candidate_rows.append(row)
                continue

            sequence = sequences.get(record["fasta_record_id"])
            if sequence is None:
                row["orf_status"] = "INPUT_INVALID"
                row["reason"] = "Validated candidate FASTA record disappeared."
                aggregate_status = "PARTIAL"
                candidate_rows.append(row)
                continue
            try:
                derivation = enumerate_orfs(
                    sequence,
                    candidate_id=record["candidate_id"],
                    sequence_id=record["sequence_id"],
                    sequence_sha256=record["sequence_sha256"],
                    molecule_type=record.get("molecule_type"),
                )
            except (TypeError, ValueError) as error:
                row["orf_status"] = "INPUT_INVALID"
                row["reason"] = str(error)[:1000]
                aggregate_status = "PARTIAL"
                candidate_rows.append(row)
                continue

            policy_sha256 = _policy_digest(derivation["policy"])
            row["orf_status"] = derivation["status"]
            row["expected_orf_count"] = derivation["expected_orf_count"]
            row["observed_orf_count"] = derivation["observed_orf_count"]
            row["translation_view"] = {
                key: value for key, value in derivation["translation_view"].items()
                if key != "sequence"
            }
            row["trailing_nucleotides"] = derivation["trailing_nucleotides"]
            row["policy"] = derivation["policy"]
            row["policy_sha256"] = policy_sha256
            for orf in derivation["orfs"]:
                orf.update({
                    "source_artifact_id": record["source_artifact_id"],
                    "source_artifact_sha256": record["source_artifact_sha256"],
                    "m6_support_status": record["m6_support_status"],
                    "completeness_state": record["completeness_state"],
                    "molecule_type": record.get("molecule_type"),
                    "derivation_policy_sha256": policy_sha256,
                })
                row["orfs"].append(orf)
                protein_records.append((orf["orf_id"], orf["protein_sequence"]))
            candidate_rows.append(row)

        if details["availability_state"] in {"UPSTREAM_UNAVAILABLE", "INVALID_OUTPUT"}:
            aggregate_status = "PARTIAL"
        candidate_rows.sort(key=lambda item: (item["candidate_id"], item["sequence_id"]))
        protein_records.sort(key=lambda item: item[0])
        results = {
            "schema": RESULTS_SCHEMA,
            "stage_version": STAGE_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "aggregate_status": aggregate_status,
            "candidate_set": _candidate_set_summary(candidate_document, input_path),
            "candidate_count": len(candidate_rows),
            "upstream_context_artifacts": context_rows,
            "m8_context": m8_context,
            "candidates": candidate_rows,
            "expected_orf_count": sum(row["expected_orf_count"] for row in candidate_rows),
            "observed_orf_count": sum(row["observed_orf_count"] for row in candidate_rows),
            "limitations": [
                "ORFs and translations are deterministic table-1 technical hypotheses, not gene calls.",
                "NO_ORF_PREDICTED_WITHIN_POLICY is not a noncoding conclusion.",
                "M6 support, optional M7 recurrence and optional M8 nucleotide evidence remain separate.",
                "Protein similarity is assessed in a separate stage and does not establish function or classification.",
            ],
        }
        results_path = Path(directory) / "orf_results.json"
        proteins_path = Path(directory) / "proteins.faa"
        write_json(results_path, results)
        proteins_path.write_text(
            "".join(f">{record_id}\n{sequence}\n"
                    for record_id, sequence in protein_records),
            encoding="ascii",
        )
        outputs = {
            "orf_results.json": {
                "artifact_type": "m9_orf_results",
                "sha256": checksum(results_path),
                "size_bytes": results_path.stat().st_size,
            },
            "proteins.faa": {
                "artifact_type": "m9_protein_fasta",
                "sha256": checksum(proteins_path),
                "size_bytes": proteins_path.stat().st_size,
            },
        }
        bundle = {
            "schema": BUNDLE_SCHEMA,
            "bundle_kind": "ORF_DERIVATION",
            "source_inputs": {
                "candidate_sequence_set": {
                    "artifact_type": "m8_candidate_sequence_set",
                    "sha256": checksum(input_path),
                    "size_bytes": input_path.stat().st_size,
                },
                "optional_context": context_rows,
            },
            "outputs": outputs,
            "aggregate_status": aggregate_status,
        }
        write_json(Path(directory) / "orf_bundle.json", bundle)
        return list(_OUTPUT_TYPES)

    return execute("m9-orf-translation-v1", inputs, output, __file__, produce)


run_stage.cache_implementation_identity = implementation_identity