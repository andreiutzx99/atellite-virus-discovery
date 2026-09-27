"""Typed, deterministic M10 exact-first stage over the validated M6 handoff."""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from . import artifact_contracts
from .m10_algorithms import M10Limits, analyze_sequence
from .m8_candidate_handoff import validate_candidate_sequence_set
from .sequence_downloader import checksum


STAGE_VERSION = "1"
ACCOUNTING_SCHEMA = "m10-candidate-accounting-v1"
EVIDENCE_SCHEMA = "m10-repeat-evidence-v1"
BUNDLE_SCHEMA = "m10-result-bundle-v1"
BRANCH_IDS = (
    "M10_TERMINAL_DIRECT_V1",
    "M10_TERMINAL_INVERTED_V1",
    "M10_INTERNAL_DIRECT_V1",
    "M10_INTERNAL_INVERTED_V1",
)
POLICY_IDS = {
    "alphabet": "M10-IUPAC-ALPHABET-V1",
    "comparison_view": "M10-COMPARE-IUPAC-v1",
    "reverse_complement": "M10-REVERSE-COMPLEMENT-v1",
    "terminal_enumeration": "M10-PROPER-TERMINAL-ALL-LENGTHS-V1",
    "internal_enumeration": "M10-MAXIMAL-INTERNAL-EXACT-V1",
    "canonicalization": "M10-SOURCE-INTERVAL-PAIR-V1",
    "precap_ordering": "M10-PRECAP-TRAVERSAL-V1",
    "serialization_ordering": "M10-CANONICAL-SERIALIZATION-V1",
}

_OPTIONAL_INPUT_TYPES = {
    "m7_observations": "m7_observation_table",
    "m7_recurrence": "m7_exact_recurrence_table",
    "m7_independence": "m7_independence_summary",
    "m7_validation": "m7_validation_report",
    "m7_provenance": "m7_provenance_manifest",
    "m8_query_status": "m8_query_status",
    "m8_match_evidence": "m8_match_evidence",
    "m8_summary": "m8_summary",
    "m8_search_commands": "m8_search_commands",
    "m9_orf_results": "m9_orf_results",
    "m9_protein_fasta": "m9_protein_fasta",
    "m9_orf_bundle": "m9_orf_bundle",
    "m9_protein_search_status": "m9_protein_search_status",
    "m9_protein_match_evidence": "m9_protein_match_evidence",
    "m9_protein_summary": "m9_protein_summary",
    "m9_search_commands": "m9_search_commands",
    "m9_output_bundle": "m9_output_bundle",
}
_OUTPUT_TYPES = {
    "candidate_accounting.jsonl": "m10_candidate_accounting",
    "repeat_evidence.jsonl": "m10_repeat_evidence",
    "m10_bundle.json": "m10_result_bundle",
}


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("M10 configuration must be an object")
    allowed = {
        "max_candidate_symbols",
        "max_symbol_comparisons_per_branch",
        "max_evidence_rows_per_branch",
    }
    if set(config) - allowed:
        raise ValueError("M10 configuration contains an unknown option")
    values = {
        "max_candidate_symbols": 1_000_000,
        "max_symbol_comparisons_per_branch": 50_000_000,
        "max_evidence_rows_per_branch": 100_000,
    }
    for name, value in config.items():
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        values[name] = value
    return values


def _canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )


def _sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _index_fasta(path):
    """Index validated FASTA records without retaining sequence strings."""
    index = {}
    current_id = None
    start = None
    with Path(path).open("rb") as source:
        while True:
            position = source.tell()
            line = source.readline()
            if not line:
                if current_id is not None:
                    index[current_id] = (start, position)
                break
            if line.startswith(b">"):
                if current_id is not None:
                    index[current_id] = (start, position)
                token = line[1:].strip().split(None, 1)[0]
                current_id = token.decode("ascii")
                if current_id in index:
                    raise ValueError("Candidate FASTA has duplicate record identifiers")
                start = source.tell()
    return index


def _read_fasta_sequence(path, span):
    start, end = span
    with Path(path).open("rb") as source:
        source.seek(start)
        payload = source.read(end - start)
    return b"".join(payload.splitlines()).decode("ascii")


def _context_type(name):
    if name in _OPTIONAL_INPUT_TYPES:
        return _OPTIONAL_INPUT_TYPES[name]
    if name.startswith("m8_raw_output_"):
        return "m8_raw_blast_output"
    if name.startswith("m9_raw_output_"):
        return "m9_raw_blast_output"
    return None


def _status_fields(path):
    if Path(path).stat().st_size > 32_000_000:
        return {}
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(document, dict):
        return {}
    names = (
        "status", "aggregate_status", "analysis_completeness", "result_status",
        "panel_state", "reference_panel_state", "availability_state",
    )
    return {name: document[name] for name in names if name in document}


def _provenance_fields(path):
    if Path(path).stat().st_size > 32_000_000:
        return {}
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(document, dict):
        return {}
    names = (
        "source_inputs", "provenance", "identity", "producer",
        "configuration_sha256", "raw_output_provenance",
    )
    return {name: document[name] for name in names if name in document}


def _describe_inputs(inputs):
    if "candidate_sequence_set" not in inputs:
        raise ValueError("M10 requires candidate_sequence_set")
    context = []
    candidate_descriptor = None
    for name, path in sorted(inputs.items()):
        if name == "candidate_sequence_set":
            artifact_type = "m8_candidate_sequence_set"
        else:
            artifact_type = _context_type(name)
            if artifact_type is None:
                raise ValueError(f"Unsupported M10 input name: {name!r}")
        details = artifact_contracts.validate_artifact(path, artifact_type)
        item = {
            "input_name": name,
            "artifact_type": artifact_type,
            "artifact_id": Path(path).name,
            "sha256": checksum(path),
            "size_bytes": Path(path).stat().st_size,
            "validation_state": "valid",
            "validation_metadata": details,
            "original_status_fields": _status_fields(path),
            "provenance_fields": _provenance_fields(path),
        }
        if name == "candidate_sequence_set":
            candidate_descriptor = item
        else:
            context.append(item)
    return candidate_descriptor, context


def _optional_context_state(context_descriptors):
    groups = {
        name: {"state": "NOT_SUPPLIED", "artifacts": []}
        for name in ("m7", "m8", "m9")
    }
    for descriptor in context_descriptors:
        group = descriptor["input_name"][:2]
        groups[group]["state"] = "SUPPLIED"
        groups[group]["artifacts"].append(descriptor)
    return groups


def implementation_identity():
    paths = (
        Path(__file__),
        Path(__file__).with_name("m10_algorithms.py"),
        Path(__file__).with_name("m10_contracts.py"),
        Path(__file__).with_name("m8_candidate_handoff.py"),
    )
    contract_types = {
        "m8_candidate_sequence_set",
        "m10_candidate_accounting", "m10_repeat_evidence", "m10_result_bundle",
    }
    return {
        "schema": "m10-exact-first-stage-identity-v1",
        "stage_version": STAGE_VERSION,
        "source_sha256": {path.name: checksum(path) for path in paths},
        "artifact_contract_semantics": artifact_contracts.semantic_identity(
            contract_types),
        "policy_ids": POLICY_IDS,
        "required_branches": list(BRANCH_IDS),
    }


def _terminal_resolved(completeness_state):
    return isinstance(completeness_state, str) and \
        completeness_state.upper() in {
            "COMPLETE", "COMPLETE_SEQUENCE", "BOTH_TERMINI_RESOLVED",
            "TERMINAL_BOUNDARIES_RESOLVED",
        }


def run_stage(inputs, output, config):
    normalized_config = validate_config(config)
    limits = M10Limits(**normalized_config)
    candidate_path = Path(inputs["candidate_sequence_set"]).resolve(strict=True)
    candidate_descriptor, context_descriptors = _describe_inputs(inputs)
    optional_context_state = _optional_context_state(context_descriptors)
    document = json.loads(candidate_path.read_text(encoding="utf-8"))
    handoff_validation = validate_candidate_sequence_set(candidate_path)
    records = document.get("records", [])
    availability = document["availability"]
    fasta_path = (
        candidate_path.parent / availability["fasta_artifact"]["path"]
        if availability.get("fasta_artifact") else None
    )
    fasta_index = _index_fasta(fasta_path) if fasta_path else {}
    fasta_records = {
        record["fasta_record_id"]: record
        for record in records if record.get("sequence_bytes_available") is True
    }
    if set(fasta_index) != set(fasta_records):
        raise ValueError("Validated candidate FASTA index disagrees with candidate records")

    configuration = {
        "limits": normalized_config,
        "policy_ids": POLICY_IDS,
        "required_branches": list(BRANCH_IDS),
    }
    configuration_sha256 = _sha_bytes(_canonical_json(configuration).encode("utf-8"))
    implementation = implementation_identity()
    source_artifact = document.get("source_artifact")
    assembly_manifest = document.get("assembly_manifest")
    m6_evidence = document.get("m6_evidence", {})
    input_status = {
        "AVAILABLE": "INPUT_VALID",
        "PARTIALLY_AVAILABLE": "INPUT_VALID",
        "COMPLETE_EMPTY": "COMPLETE_EMPTY_INPUT_SET",
        "UPSTREAM_UNAVAILABLE": "SEQUENCE_UNAVAILABLE",
        "INVALID_OUTPUT": "INPUT_INVALID",
    }[availability["state"]]
    aggregate_status = "PARTIAL"
    candidate_count = len(records)

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    accounting_path = output / "candidate_accounting.jsonl"
    evidence_path = output / "repeat_evidence.jsonl"
    bundle_path = output / "m10_bundle.json"
    header = {
        "record_type": "manifest",
        "schema": ACCOUNTING_SCHEMA,
        "input_status": input_status,
        "aggregate_status": aggregate_status,
        "candidate_count": candidate_count,
        "candidate_set": {
            **candidate_descriptor,
            "availability_state": availability["state"],
            "producer": document.get("producer"),
            "source_artifact": source_artifact,
            "assembly_manifest": assembly_manifest,
            "m6_evidence": m6_evidence,
            "validation_metadata": handoff_validation,
        },
        "context_artifacts": context_descriptors,
        "optional_context_state": optional_context_state,
        "configuration": configuration,
        "configuration_sha256": configuration_sha256,
        "implementation": implementation,
        "required_branches": list(BRANCH_IDS),
        "policy_ids": POLICY_IDS,
        "limitations": [
            "Exact sequence architecture only; no biological topology or function is inferred.",
            "No biological database searches, reference retrieval, or external repeat tools were used.",
            "A scoped no-match describes only a fully accounted branch under the recorded exact policy.",
        ],
    }
    all_complete = input_status == "INPUT_VALID" and candidate_count > 0
    with tempfile.TemporaryDirectory(prefix=".m10-stage-", dir=output) as temporary:
        temporary = Path(temporary)
        candidate_rows_path = temporary / "candidates.jsonl"
        evidence_rows_path = temporary / "evidence.jsonl"
        with candidate_rows_path.open("w", encoding="utf-8", newline="\n") as candidate_target, \
                evidence_rows_path.open("w", encoding="utf-8", newline="\n") as evidence_target:
            for record in sorted(records, key=lambda item: (
                    item["candidate_id"], item["sequence_id"])):
                available = record["sequence_bytes_available"] is True
                sequence = (
                    _read_fasta_sequence(
                        fasta_path, fasta_index[record["fasta_record_id"]])
                    if available else None
                )
                boundary_resolved = _terminal_resolved(
                    record.get("completeness_state"))
                analysis = analyze_sequence(
                    sequence,
                    candidate_id=record["candidate_id"],
                    sequence_id=record["sequence_id"],
                    molecule_type=record.get("molecule_type"),
                    terminal_boundaries_resolved=boundary_resolved,
                    limits=limits,
                )
                if analysis["aggregate_status"] != "COMPLETE":
                    all_complete = False
                source_digest = analysis.get(
                    "source_sha256", record.get("sequence_sha256"))
                branch_accounting = {}
                for branch_id in BRANCH_IDS:
                    branch = analysis["branches"][branch_id]
                    branch_accounting[branch_id] = {
                        key: value for key, value in branch.items()
                        if key != "evidence"
                    }
                    for row in branch["evidence"]:
                        normalized = {
                            **row,
                            "source_sequence_length": analysis.get(
                                "source_length", record.get("sequence_length")),
                            "branch_status": branch["branch_status"],
                            "evidence_status": branch["evidence_status"],
                            "configuration_sha256": configuration_sha256,
                            "candidate_set_sha256": candidate_descriptor["sha256"],
                            "source_artifact_id": record["source_artifact_id"],
                            "source_artifact_sha256": record.get(
                                "source_artifact_sha256"),
                            "completeness_state": record["completeness_state"],
                            "terminal_boundaries_resolved": boundary_resolved,
                            "coordinate_system": "ZERO_BASED_HALF_OPEN_SOURCE",
                            "view_to_source_coordinate_map": (
                                "IDENTITY_SOURCE_INTERVALS"
                                if row["orientation"] == "DIRECT"
                                else "REVERSE_COMPLEMENT_VIEW:[a,b)->SOURCE:[n-b,n-a)"
                            ),
                            "exact_match_disposition": "DEFINITE_EXACT_MATCH",
                            "policy_ids": POLICY_IDS,
                        }
                        evidence_target.write(_canonical_json(normalized) + "\n")
                candidate_row = {
                    "record_type": "candidate",
                    "candidate_id": record["candidate_id"],
                    "sequence_id": record["sequence_id"],
                    "fasta_record_id": record.get("fasta_record_id"),
                    "source_sequence": analysis.get("source_sequence"),
                    "source_sha256": source_digest,
                    "source_length": analysis.get(
                        "source_length", record.get("sequence_length")),
                    "source_artifact": {
                        "artifact_id": record["source_artifact_id"],
                        "sha256": record.get("source_artifact_sha256"),
                    },
                    "candidate_set_sha256": candidate_descriptor["sha256"],
                    "candidate_set_validation_state": "valid",
                    "candidate_set_availability_state": availability["state"],
                    "m6_assembly_state": (
                        assembly_manifest.get("workflow_status")
                        if isinstance(assembly_manifest, dict) else None
                    ),
                    "m6_support_status": record["m6_support_status"],
                    "m6_reconstruction_status": m6_evidence.get(
                        "reconstruction_status"),
                    "m6_evidence_status": m6_evidence.get("support_status"),
                    "molecule_type": record.get("molecule_type"),
                    "source_alphabet": {
                        "policy_id": POLICY_IDS["alphabet"],
                        "state": "OBSERVED" if available else "BYTES_UNAVAILABLE",
                        "observed_symbols": (
                            sorted(set(sequence.upper())) if available else None
                        ),
                    },
                    "comparison_view": analysis.get("comparison_view"),
                    "reverse_complement_view": analysis.get(
                        "reverse_complement_view"),
                    "sequence_bytes_available": available,
                    "sequence_unavailable_reason": record.get(
                        "sequence_unavailable_reason"),
                    "completeness_state": record["completeness_state"],
                    "terminal_boundaries_resolved": boundary_resolved,
                    "input_status": analysis["input_status"],
                    "aggregate_status": analysis["aggregate_status"],
                    "configuration_sha256": configuration_sha256,
                    "branch_plan": list(BRANCH_IDS),
                    "branches": branch_accounting,
                    "expected_evidence_rows": (
                        sum(item["evidence_rows"]
                            for item in branch_accounting.values())
                        if analysis["aggregate_status"] == "COMPLETE" else None
                    ),
                    "accounted_evidence_rows": sum(
                        item["evidence_rows"]
                        for item in branch_accounting.values()),
                    "limitations": [
                        "Internal repeat records describe exact interval relationships only."
                    ],
                }
                candidate_target.write(_canonical_json(candidate_row) + "\n")

        if all_complete:
            aggregate_status = "COMPLETE"
        header["aggregate_status"] = aggregate_status
        accounting_temp = temporary / "accounting.jsonl"
        with accounting_temp.open("w", encoding="utf-8", newline="\n") as target:
            target.write(_canonical_json(header) + "\n")
            with candidate_rows_path.open("r", encoding="utf-8") as source:
                shutil.copyfileobj(source, target)
        evidence_temp = temporary / evidence_path.name
        shutil.copyfile(evidence_rows_path, evidence_temp)
        accounting_temp.replace(accounting_path)
        evidence_temp.replace(evidence_path)

    output_descriptors = {}
    for name, artifact_type in _OUTPUT_TYPES.items():
        if name == "m10_bundle.json":
            continue
        path = output / name
        output_descriptors[name] = {
            "artifact_type": artifact_type,
            "sha256": checksum(path),
            "size_bytes": path.stat().st_size,
        }
    bundle = {
        "schema": BUNDLE_SCHEMA,
        "stage": "m10_exact_first",
        "stage_version": STAGE_VERSION,
        "input_status": input_status,
        "aggregate_status": aggregate_status,
        "candidate_count": candidate_count,
        "source_inputs": {
            "candidate_sequence_set": candidate_descriptor,
            "optional_context": context_descriptors,
            "optional_context_state": optional_context_state,
        },
        "configuration": configuration,
        "configuration_sha256": configuration_sha256,
        "implementation": implementation,
        "policy_ids": POLICY_IDS,
        "required_branches": list(BRANCH_IDS),
        "outputs": output_descriptors,
    }
    bundle_path.write_text(_canonical_json(bundle) + "\n", encoding="utf-8")
    final_handoff_validation = validate_candidate_sequence_set(candidate_path)
    if final_handoff_validation != handoff_validation:
        raise ValueError("M10 candidate handoff changed during analysis")
    for name, path in inputs.items():
        if checksum(path) != (
                candidate_descriptor["sha256"] if name == "candidate_sequence_set"
                else next(row["sha256"] for row in context_descriptors
                          if row["input_name"] == name)):
            raise ValueError("M10 input changed during analysis")
    manifest = {
        "status": "complete",
        "stage": "m10_exact_first",
        "stage_version": STAGE_VERSION,
        "output_sha256": {
            name: checksum(output / name) for name in _OUTPUT_TYPES
        },
    }
    (output / "manifest.json").write_text(
        _canonical_json(manifest) + "\n", encoding="utf-8")
    return list(_OUTPUT_TYPES)


run_stage.cache_implementation_identity = implementation_identity
run_stage.cache_input_contract_semantics = True
run_stage.cache_input_contract_semantics_version = (
    "m10-input-contract-semantics-v1"
)