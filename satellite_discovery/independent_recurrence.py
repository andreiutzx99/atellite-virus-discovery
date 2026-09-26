"""M7 exact recurrence over independently produced M6 evidence artifacts.

This stage compares supported contig records only. It never reads or combines
raw reads, assembles sequences, or assigns biological classifications.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re

from . import artifact_contracts, sequence_catalogue, sequence_downloader, stage_lock
from .portable_paths import portable_name
from .sequence_downloader import checksum, write_json


STAGE_VERSION = "1"
SCHEMA_OBSERVATIONS = "m7-observations-v1"
SCHEMA_EXACT = "m7-exact-recurrence-v1"
SCHEMA_SUMMARY = "m7-independence-summary-v1"
SCHEMA_PROVENANCE = "m7-recurrence-provenance-v1"
SCHEMA_VALIDATION = "m7-validation-report-v1"

MAX_OBSERVATIONS = 100
MAX_SEQUENCE_RECORDS = 100_000
MAX_TOTAL_BASES = 100_000_000
MAX_MANIFEST_BYTES = 2_000_000

_INPUT_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_UNKNOWN_METADATA = {
    "unknown", "not provided", "not_provided", "not-provided",
    "n/a", "na", "none", "null",
}

INPUT_TYPES = {
    "evidence_input": "reconstruction_evidence",
    "residual_manifest_input": "residual_read_manifest",
    "contigs_input": "canonical_contig_fasta",
}

OUTPUT_CONTRACTS = {
    "observations.json": "m7_observation_table",
    "exact_recurrence.json": "m7_exact_recurrence_table",
    "recurrence_summary.json": "m7_independence_summary",
    "validation_report.json": "m7_validation_report",
    "recurrence_provenance.json": "m7_provenance_manifest",
    "report.html": "report",
}

_M6_RECONSTRUCTION_STATUS = {
    "READ_SUPPORTED_ASSEMBLY",
    "NO_SUPPORTED_ASSEMBLY",
    "DEPENDENCY_UNAVAILABLE",
    "EXECUTION_FAILED",
    "INTERRUPTED",
    "INVALID_OUTPUT",
    "READ_SUPPORT_FAILED",
    "INVALID_SUPPORT_OUTPUT",
    "ASSEMBLY_NOT_ATTEMPTED",
}

_M6_CONTIG_STATUS = {
    "READ_SUPPORTED_ASSEMBLY",
    "LOW_SUPPORT_ASSEMBLY",
    "UNSUPPORTED_ASSEMBLY",
    "AMBIGUOUS_ASSEMBLY",
}

_DNA_COMPLEMENT = str.maketrans(
    "ACGTRYSWKMBDHVN",
    "TGCAYRSWMKVHDBN",
)
_RNA_COMPLEMENT = str.maketrans(
    "ACGURYSWKMBDHVN",
    "UGCAYRSWMKVHDBN",
)
_DNA_ALPHABET = set("ACGTRYSWKMBDHVN")
_RNA_ALPHABET = set("ACGURYSWKMBDHVN")


def _text(value, field, *, required=False, token=False, maximum=128):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string" if required else
                         f"{field} must be a string or null")
    result = value.strip()
    if not result and not required:
        raise ValueError(f"{field} must be null when missing")
    if (not result or len(result) > maximum or
            any(ord(char) < 32 for char in result)):
        raise ValueError(f"{field} must be bounded non-empty text")
    if token and not _IDENTIFIER.fullmatch(result):
        raise ValueError(f"{field} must be a safe identifier")
    return result


def _metadata_identifier(value, field):
    result = _text(value, field)
    if result is None or result.casefold() in _UNKNOWN_METADATA:
        return None
    if not _IDENTIFIER.fullmatch(result):
        raise ValueError(f"{field} must be a safe identifier or null")
    return result


def _observed_at(value):
    result = _text(value, "observed_at", maximum=64)
    if result is None:
        return None
    try:
        parsed = datetime.fromisoformat(result[:-1] + "+00:00"
                                        if result.endswith("Z") else result)
    except ValueError as error:
        raise ValueError("observed_at must be an ISO 8601 date-time") from error
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    return result


def validate_config(config):
    """Validate declared observations without inferring missing metadata."""
    if not isinstance(config, dict) or set(config) - {
        "observations", "orientation_policy",
    }:
        raise ValueError("Independent recurrence config contains unsupported fields")
    observations = config.get("observations")
    if (not isinstance(observations, list) or
            not 1 <= len(observations) <= MAX_OBSERVATIONS):
        raise ValueError(
            f"Declare between one and {MAX_OBSERVATIONS} M6 observations"
        )
    orientation = config.get("orientation_policy", "forward_only")
    if orientation not in {"forward_only", "reverse_complement_invariant"}:
        raise ValueError(
            "orientation_policy must be forward_only or reverse_complement_invariant"
        )

    normalized = []
    seen_ids = set()
    input_types = {}
    allowed_fields = {
        "observation_id", "candidate_id", "sample_id", "sequencing_run_id",
        "study_id", "source_artifact_id", "upstream_workflow_id",
        "observed_at", "molecule_type", "m6_state", "evidence_input",
        "residual_manifest_input", "contigs_input", "upstream_status",
        "upstream_reason",
    }
    for row in observations:
        if not isinstance(row, dict) or set(row) - allowed_fields:
            raise ValueError("Each M7 observation contains unsupported fields")
        observation_id = _text(
            row.get("observation_id"), "observation_id", required=True, token=True,
        )
        if observation_id.casefold() in seen_ids:
            raise ValueError("Observation identifiers must be unique")
        seen_ids.add(observation_id.casefold())
        state = row.get("m6_state")
        if state not in {"available", "unavailable", "failed"}:
            raise ValueError("m6_state must be available, unavailable or failed")

        candidate_id = _metadata_identifier(row.get("candidate_id"), "candidate_id")
        sample_id = _metadata_identifier(row.get("sample_id"), "sample_id")
        run_id = _metadata_identifier(row.get("sequencing_run_id"), "sequencing_run_id")
        study_id = _metadata_identifier(row.get("study_id"), "study_id")
        source_artifact_id = _text(
            row.get("source_artifact_id"), "source_artifact_id", maximum=1024,
        )
        if (source_artifact_id is not None and
                source_artifact_id.casefold() in _UNKNOWN_METADATA):
            source_artifact_id = None
        upstream_workflow_id = _metadata_identifier(
            row.get("upstream_workflow_id"), "upstream_workflow_id",
        )
        observed_at = _observed_at(row.get("observed_at"))
        molecule_type = row.get("molecule_type", "unknown")
        if molecule_type not in {"DNA", "RNA", "unknown"}:
            raise ValueError("molecule_type must be DNA, RNA or unknown")

        item = {
            "observation_id": observation_id,
            "candidate_id": candidate_id,
            "sample_id": sample_id,
            "sequencing_run_id": run_id,
            "study_id": study_id,
            "source_artifact_id": source_artifact_id,
            "upstream_workflow_id": upstream_workflow_id,
            "observed_at": observed_at,
            "molecule_type": molecule_type,
            "m6_state": state,
            "evidence_input": None,
            "residual_manifest_input": None,
            "contigs_input": None,
            "upstream_status": None,
            "upstream_reason": None,
        }
        if state == "available":
            for name in ("evidence_input", "residual_manifest_input"):
                input_name = _text(row.get(name), name, required=True, token=True)
                if not _INPUT_NAME.fullmatch(input_name):
                    raise ValueError(f"{name} must match a safe workflow input name")
                item[name] = input_name
                _register_input_type(input_types, input_name, INPUT_TYPES[name])
            contigs_input = _text(row.get("contigs_input"), "contigs_input", token=True)
            if contigs_input is not None:
                if not _INPUT_NAME.fullmatch(contigs_input):
                    raise ValueError("contigs_input must match a safe workflow input name")
                item["contigs_input"] = contigs_input
                _register_input_type(
                    input_types, contigs_input, INPUT_TYPES["contigs_input"],
                )
            if row.get("upstream_status") is not None or row.get("upstream_reason") is not None:
                raise ValueError(
                    "Available M6 observations derive status from reconstruction evidence"
                )
        else:
            if any(row.get(name) is not None for name in INPUT_TYPES):
                raise ValueError(
                    "Unavailable or failed M6 observations must not declare M6 artifacts"
                )
            item["upstream_status"] = _text(
                row.get("upstream_status"), "upstream_status", required=True,
                maximum=128,
            )
            item["upstream_reason"] = _text(
                row.get("upstream_reason"), "upstream_reason", maximum=1000,
            )
        normalized.append(item)
    return {
        "observations": sorted(
            normalized, key=lambda row: row["observation_id"],
        ),
        "orientation_policy": orientation,
    }


def _register_input_type(input_types, name, artifact_type):
    prior = input_types.get(name)
    if prior is not None and prior != artifact_type:
        raise ValueError("An M7 workflow input cannot serve different artifact roles")
    input_types[name] = artifact_type


def expected_input_types(config):
    """Return dynamic input names and their exact M6 contracts."""
    normalized = validate_config(config)
    result = {}
    for observation in normalized["observations"]:
        if observation["m6_state"] != "available":
            continue
        for field, artifact_type in INPUT_TYPES.items():
            name = observation[field]
            if name is not None:
                _register_input_type(result, name, artifact_type)
    return result


def _canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")


def _hash_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _read_json(path):
    if path.stat().st_size > 32_000_000:
        raise ValueError("M6 JSON input exceeds the 32 MB limit")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("M6 evidence inputs must contain JSON objects")
    return value


def _read_upstream_manifest(paths):
    manifests = []
    for path in paths:
        marker = path.parent / "manifest.json"
        if not marker.exists():
            manifests.append(None)
            continue
        if marker.is_symlink() or not marker.is_file():
            raise ValueError("M6 stage manifest must be a regular file")
        if marker.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError("M6 stage manifest exceeds the 2 MB limit")
        value = _read_json(marker)
        outputs = value.get("output_sha256")
        digest = checksum(path)
        if (value.get("status") != "complete" or not isinstance(outputs, dict)
                or outputs.get(path.name) != digest):
            raise ValueError("M6 artifact is not bound to its adjacent stage manifest")
        identity = value.get("identity")
        identity_sha256 = _hash_text(_canonical_json(identity).decode("utf-8")) if identity is not None else None
        manifests.append({
            "sha256": checksum(marker),
            "stage_id": value.get("stage_id"),
            "workflow_id": value.get("workflow_id"),
            "identity_sha256": identity_sha256,
        })
    present = [item for item in manifests if item is not None]
    if present and len(present) != len(manifests):
        raise ValueError("M6 artifacts must have consistent stage-manifest provenance")
    if present and len({item["sha256"] for item in present}) != 1:
        raise ValueError("M6 artifacts must come from the same completed stage manifest")
    return present[0] if present else None


def _input_artifact(path, artifact_type):
    if path.is_symlink() or not path.is_file():
        raise ValueError("M7 inputs must be regular non-symlink files")
    artifact_contracts.validate_artifact(path, artifact_type)
    return {
        "sha256": checksum(path),
        "size_bytes": path.stat().st_size,
        "artifact_type": artifact_type,
    }


def _m6_contigs(evidence, contigs_path, molecule_type, orientation_policy):
    rows = evidence.get("contigs")
    if not isinstance(rows, list):
        raise ValueError("M6 reconstruction evidence must contain a contig list")
    declared = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("M6 contig records must be objects")
        contig_id = row.get("contig_id")
        length = row.get("contig_length")
        status = row.get("status")
        if (not isinstance(contig_id, str) or not contig_id or
                not isinstance(length, int) or isinstance(length, bool) or length < 1 or
                status not in _M6_CONTIG_STATUS or contig_id in declared):
            raise ValueError("M6 contig record is malformed or duplicated")
        declared[contig_id] = {"length": length, "status": status}

    top_status = evidence.get("status")
    supported = [name for name, row in declared.items()
                 if row["status"] == "READ_SUPPORTED_ASSEMBLY"]
    if top_status == "READ_SUPPORTED_ASSEMBLY":
        if not supported or contigs_path is None:
            raise ValueError(
                "Supported M6 evidence requires supported-contig FASTA and contig records"
            )
    elif supported or contigs_path is not None:
        raise ValueError(
            "M6 contigs that did not pass support cannot be supplied as recurrence candidates"
        )

    sequences = {}
    if contigs_path is not None:
        fasta = sequence_catalogue.read_fasta(contigs_path)
        if {record[0] for record in fasta} != set(declared):
            raise ValueError("M6 contig FASTA IDs do not match reconstruction evidence")
        sequences = {identifier: sequence for identifier, _header, sequence in fasta}
        for identifier, sequence in sequences.items():
            if len(sequence) != declared[identifier]["length"]:
                raise ValueError("M6 contig length does not match its FASTA sequence")

    contig_rows = []
    sequence_rows = []
    for contig_id in sorted(declared):
        metadata = declared[contig_id]
        sequence = sequences.get(contig_id)
        is_supported = metadata["status"] == "READ_SUPPORTED_ASSEMBLY"
        sequence_sha256 = _hash_text(sequence) if sequence is not None else None
        contig_row = {
            "sequence_id": contig_id,
            "sequence_length": metadata["length"],
            "sequence_sha256": sequence_sha256,
            "m6_contig_status": metadata["status"],
            "evaluated_for_recurrence": is_supported,
        }
        contig_rows.append(contig_row)
        if is_supported:
            canonical, orientation = _sequence_key(
                sequence, orientation_policy, molecule_type,
            )
            sequence_rows.append({
                "sequence_id": contig_id,
                "sequence_length": len(sequence),
                "sequence_sha256": sequence_sha256,
                "match_sha256": _hash_text(canonical),
                "orientation_to_canonical": orientation,
                "_canonical_sequence": canonical,
            })
    return contig_rows, sequence_rows


def _sequence_key(sequence, policy, molecule_type):
    if policy == "forward_only":
        return sequence, "forward"
    if molecule_type == "DNA":
        if not set(sequence) <= _DNA_ALPHABET:
            raise ValueError("DNA reverse-complement matching found non-DNA symbols")
        reverse = sequence.translate(_DNA_COMPLEMENT)[::-1]
    elif molecule_type == "RNA":
        if not set(sequence) <= _RNA_ALPHABET:
            raise ValueError("RNA reverse-complement matching found non-RNA symbols")
        reverse = sequence.translate(_RNA_COMPLEMENT)[::-1]
    else:
        raise ValueError(
            "Reverse-complement matching requires an explicit DNA or RNA molecule_type"
        )
    if sequence == reverse:
        return sequence, "palindromic"
    if sequence < reverse:
        return sequence, "forward"
    return reverse, "reverse_complement"


def _source_fingerprint(residual_manifest):
    source_reads = residual_manifest.get("source_reads")
    if not isinstance(source_reads, dict) or set(source_reads) not in (
        {"read1"}, {"read1", "read2"},
    ):
        raise ValueError("M6 residual manifest must identify read1 and optional read2")
    digests = {}
    for role in sorted(source_reads):
        entry = source_reads[role]
        if (not isinstance(entry, dict) or
                not isinstance(entry.get("sha256"), str) or
                not _HASH.fullmatch(entry["sha256"])):
            raise ValueError("M6 source-read provenance contains an invalid checksum")
        digests[role] = entry["sha256"]
    return _hash_text(_canonical_json(digests).decode("utf-8")), digests


def _validate_m6_observation(observation, paths, orientation_policy):
    evidence_path = paths[observation["evidence_input"]]
    residual_path = paths[observation["residual_manifest_input"]]
    contigs_path = (
        paths[observation["contigs_input"]]
        if observation["contigs_input"] is not None else None
    )
    evidence_artifact = _input_artifact(evidence_path, "reconstruction_evidence")
    residual_artifact = _input_artifact(residual_path, "residual_read_manifest")
    contigs_artifact = (
        _input_artifact(contigs_path, "canonical_contig_fasta")
        if contigs_path is not None else None
    )

    evidence = _read_json(evidence_path)
    residual = _read_json(residual_path)
    m6_status = evidence.get("status")
    if m6_status not in _M6_RECONSTRUCTION_STATUS:
        raise ValueError("M6 reconstruction status is unsupported by M7")
    m6_sample_id = evidence.get("sample_id")
    if not isinstance(m6_sample_id, str) or not m6_sample_id.strip():
        raise ValueError("M6 reconstruction evidence must preserve sample_id")
    if residual.get("sample_id") != m6_sample_id:
        raise ValueError("M6 reconstruction and residual artifacts disagree on sample_id")
    sample_id = _metadata_identifier(m6_sample_id, "M6 sample_id")
    if observation["sample_id"] is not None and observation["sample_id"] != sample_id:
        raise ValueError("Declared M7 sample_id does not match the M6 artifact")
    qc_sha256 = residual.get("qc_artifact", {}).get("sha256")
    if (not isinstance(qc_sha256, str) or not _HASH.fullmatch(qc_sha256) or
            evidence.get("provenance", {}).get("qc_sha256") != qc_sha256):
        raise ValueError("M6 reconstruction and residual artifacts disagree on QC provenance")
    reference_sha256 = residual.get("comparison", {}).get("reference_sha256")
    if (not isinstance(reference_sha256, str) or
            evidence.get("reference_sha256") != reference_sha256):
        raise ValueError("M6 reconstruction and residual artifacts disagree on reference provenance")

    source_fingerprint, source_read_digests = _source_fingerprint(residual)
    sidecar_paths = [evidence_path, residual_path]
    if contigs_path is not None:
        sidecar_paths.append(contigs_path)
    upstream_manifest = _read_upstream_manifest(sidecar_paths)
    contig_rows, sequence_rows = _m6_contigs(
        evidence, contigs_path, observation["molecule_type"], orientation_policy,
    )
    evidence_class = {
        "READ_SUPPORTED_ASSEMBLY": "TECHNICALLY_SUPPORTED_RECONSTRUCTION",
        "NO_SUPPORTED_ASSEMBLY": "UNSUPPORTED_RECONSTRUCTION",
        "ASSEMBLY_NOT_ATTEMPTED": "UNRESOLVED_UNASSEMBLED_RESIDUAL_EVIDENCE",
        "DEPENDENCY_UNAVAILABLE": "UPSTREAM_UNAVAILABLE",
        "EXECUTION_FAILED": "UPSTREAM_FAILED",
        "INTERRUPTED": "UPSTREAM_FAILED",
        "INVALID_OUTPUT": "UPSTREAM_FAILED",
        "READ_SUPPORT_FAILED": "UPSTREAM_FAILED",
        "INVALID_SUPPORT_OUTPUT": "UPSTREAM_FAILED",
    }[m6_status]
    missing = [
        field for field in (
            "candidate_id", "sequencing_run_id", "study_id",
            "source_artifact_id", "observed_at",
        ) if observation[field] is None
    ]
    if sample_id is None:
        missing.append("sample_id")
    if (observation["upstream_workflow_id"] is None and
            (upstream_manifest or {}).get("workflow_id") is None):
        missing.append("upstream_workflow_id")
    counts = residual.get("counts")
    if not isinstance(counts, dict):
        raise ValueError("M6 residual manifest is missing completion counts")
    residual_counts = {}
    for field in (
        "input_fragments", "residual_fragments", "eligible_fragments",
        "retained_unassembled_fragments",
    ):
        value = counts.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"M6 residual count {field!r} is invalid")
        residual_counts[field] = value
    return {
        "observation": {
            "observation_id": observation["observation_id"],
            "candidate_id": observation["candidate_id"],
            "sample_id": sample_id,
            "m6_sample_id": m6_sample_id,
            "sequencing_run_id": observation["sequencing_run_id"],
            "study_id": observation["study_id"],
            "source_artifact_id": observation["source_artifact_id"],
            "upstream_workflow_id": (
                observation["upstream_workflow_id"] or
                (upstream_manifest or {}).get("workflow_id")
            ),
            "upstream_stage_id": (upstream_manifest or {}).get("stage_id"),
            "upstream_manifest_sha256": (upstream_manifest or {}).get("sha256"),
            "observed_at": observation["observed_at"],
            "molecule_type": observation["molecule_type"],
            "m6_state": "available",
            "m6_status": m6_status,
            "evidence_class": evidence_class,
            "residual_counts": residual_counts,
            "source_dataset_fingerprint": source_fingerprint,
            "source_read_sha256": source_read_digests,
            "source_artifacts": {
                observation["evidence_input"]: evidence_artifact,
                observation["residual_manifest_input"]: residual_artifact,
                **({
                    observation["contigs_input"]: contigs_artifact,
                } if contigs_artifact is not None else {}),
            },
            "metadata_missing": missing,
            "contigs": contig_rows,
        },
        "sequences": sequence_rows,
    }


def _metadata_missing(observation):
    return [
        field for field in (
            "candidate_id", "sample_id", "sequencing_run_id", "study_id",
            "source_artifact_id", "upstream_workflow_id", "observed_at",
        ) if observation[field] is None
    ]


def _dataset_profiles(members):
    by_fingerprint = defaultdict(dict)
    for member in members:
        by_fingerprint[member["source_dataset_fingerprint"]][
            member["observation_id"]
        ] = member
    profiles = []
    conflicts = []
    for fingerprint in sorted(by_fingerprint):
        rows = list(by_fingerprint[fingerprint].values())
        profile = {
            "source_dataset_fingerprint": fingerprint,
            "observation_ids": sorted(row["observation_id"] for row in rows),
        }
        for field in ("sample_id", "sequencing_run_id", "study_id"):
            values = sorted({row[field] for row in rows if row[field] is not None})
            complete = all(row[field] is not None for row in rows)
            profile[field] = values[0] if complete and len(values) == 1 else None
            if len(values) > 1:
                conflicts.append({
                    "source_dataset_fingerprint": fingerprint,
                    "field": field,
                    "values": values,
                })
        profiles.append(profile)
    return profiles, conflicts


def _recurrence_categories(members):
    profiles, conflicts = _dataset_profiles(members)
    categories = []
    if len(profiles) <= 1:
        categories.append("SINGLE_OBSERVATION")
    else:
        sample_groups = defaultdict(list)
        study_counts = Counter()
        known_samples = set()
        known_studies = set()
        for profile in profiles:
            sample = profile["sample_id"]
            run_id = profile["sequencing_run_id"]
            study = profile["study_id"]
            if sample is not None:
                sample_groups[sample].append(profile)
                known_samples.add(sample)
            if study is not None:
                study_counts[study] += 1
                known_studies.add(study)
        if any(len(group) >= 2 for group in sample_groups.values()):
            categories.append("REPEATED_SAME_SAMPLE")
        if any(
            len({row["sequencing_run_id"] for row in group
                 if row["sequencing_run_id"] is not None}) >= 2
            for group in sample_groups.values()
        ):
            categories.append("RECURRENT_ACROSS_RUNS")
        if len(known_samples) >= 2:
            categories.append("RECURRENT_ACROSS_SAMPLES")
        if len(known_studies) >= 2:
            categories.append("RECURRENT_ACROSS_STUDIES")
        if any(count >= 2 for count in study_counts.values()):
            categories.append("REPEATED_WITHIN_DECLARED_STUDY")
        if not categories:
            categories.append("RECURRENT_INDEPENDENCE_UNRESOLVED")
    summary = {
        "source_dataset_count": len(profiles),
        "observation_count": len({row["observation_id"] for row in members}),
        "known_sample_ids": sorted({
            item["sample_id"] for item in profiles
            if item["sample_id"] is not None
        }),
        "known_run_ids": sorted({
            item["sequencing_run_id"] for item in profiles
            if item["sequencing_run_id"] is not None
        }),
        "known_study_ids": sorted({
            item["study_id"] for item in profiles
            if item["study_id"] is not None
        }),
        "source_datasets_with_unknown_sample": sum(
            item["sample_id"] is None for item in profiles
        ),
        "source_datasets_with_unknown_run": sum(
            item["sequencing_run_id"] is None for item in profiles
        ),
        "source_datasets_with_unknown_study": sum(
            item["study_id"] is None for item in profiles
        ),
        "source_metadata_conflicts": conflicts,
        "source_datasets": profiles,
    }
    return categories, summary


def _build_exact_groups(sequence_rows, orientation_policy):
    grouped = defaultdict(list)
    canonical_by_hash = {}
    for row in sequence_rows:
        match_hash = row["match_sha256"]
        canonical = row["_canonical_sequence"]
        previous = canonical_by_hash.get(match_hash)
        if previous is not None and previous != canonical:
            raise ValueError("SHA256 collision detected for canonical sequence content")
        canonical_by_hash[match_hash] = canonical
        grouped[match_hash].append(row)

    groups = []
    for match_hash in sorted(grouped):
        members = sorted(
            grouped[match_hash],
            key=lambda row: (row["observation_id"], row["sequence_id"]),
        )
        categories, independence = _recurrence_categories(members)
        groups.append({
            "group_id": "exact-" + match_hash,
            "match_sha256": match_hash,
            "sequence_length": members[0]["sequence_length"],
            "orientation_policy": orientation_policy,
            "sequence_observation_count": len(members),
            "observation_count": independence["observation_count"],
            "source_dataset_count": independence["source_dataset_count"],
            "recurrence_categories": categories,
            "independence": independence,
            "members": [
                {key: value for key, value in row.items()
                 if not key.startswith("_")}
                for row in members
            ],
        })
    return groups


def _implementation_identity():
    files = {
        "independent_recurrence.py": Path(__file__),
        "artifact_contracts.py": Path(artifact_contracts.__file__),
        "sequence_catalogue.py": Path(sequence_catalogue.__file__),
        "sequence_downloader.py": Path(sequence_downloader.__file__),
        "stage_lock.py": Path(stage_lock.__file__),
        "portable_paths.py": Path(__file__).with_name("portable_paths.py"),
    }
    return {
        "stage_version": STAGE_VERSION,
        "algorithm": "m7-exact-sequence-recurrence-v1",
        "source_sha256": {
            name: checksum(path) for name, path in sorted(files.items())
        },
    }


def _write_report(path, summary, groups):
    body = [
        "<!doctype html><html><head><meta charset=\"utf-8\">",
        "<title>M7 independent recurrence</title>",
        "<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}",
        "table{border-collapse:collapse}td,th{border:1px solid #aaa;padding:.4rem;text-align:left}",
        "</style></head><body><h1>M7 independent recurrence</h1>",
        "<p>Exact recurrence among individually supported M6 contigs only.</p>",
        "<dl>",
    ]
    for label, key in (
        ("Result", "result_status"),
        ("Analysis completeness", "analysis_completeness"),
        ("Declared observations", "observation_count"),
        ("Supported sequence observations", "supported_sequence_observation_count"),
        ("Exact sequence groups", "exact_group_count"),
        ("Recurrent source-dataset groups", "recurrent_group_count"),
    ):
        body.append(
            "<dt>" + html.escape(label) + "</dt><dd>" +
            html.escape(str(summary[key])) + "</dd>"
        )
    body.append("</dl><h2>Exact sequence groups</h2>")
    if groups:
        body.append(
            "<table><thead><tr><th>Group</th><th>Length</th>"
            "<th>Observations</th><th>Source datasets</th><th>Categories</th>"
            "</tr></thead><tbody>"
        )
        for group in groups:
            body.append(
                "<tr><td><code>" + html.escape(group["group_id"]) + "</code></td>"
                "<td>" + str(group["sequence_length"]) + "</td>"
                "<td>" + str(group["observation_count"]) + "</td>"
                "<td>" + str(group["source_dataset_count"]) + "</td>"
                "<td>" + html.escape(", ".join(group["recurrence_categories"])) +
                "</td></tr>"
            )
        body.append("</tbody></table>")
    else:
        body.append("<p>No eligible supported contig sequences were evaluated.</p>")
    body.append("<h2>Interpretation limits</h2><ul>")
    for item in summary["limitations"]:
        body.append("<li>" + html.escape(item) + "</li>")
    body.append("</ul></body></html>")
    path.write_text("".join(body), encoding="utf-8")


def _produce(paths, output, config, input_types):
    observations = []
    sequence_rows = []
    total_contigs = 0
    total_bases = 0
    for item in sorted(config["observations"], key=lambda row: row["observation_id"]):
        if item["m6_state"] != "available":
            evidence_class = (
                "UPSTREAM_UNAVAILABLE" if item["m6_state"] == "unavailable"
                else "UPSTREAM_FAILED"
            )
            observations.append({
                "observation_id": item["observation_id"],
                "candidate_id": item["candidate_id"],
                "sample_id": item["sample_id"],
                "m6_sample_id": None,
                "sequencing_run_id": item["sequencing_run_id"],
                "study_id": item["study_id"],
                "source_artifact_id": item["source_artifact_id"],
                "upstream_workflow_id": item["upstream_workflow_id"],
                "upstream_stage_id": None,
                "upstream_manifest_sha256": None,
                "observed_at": item["observed_at"],
                "molecule_type": item["molecule_type"],
                "m6_state": item["m6_state"],
                "m6_status": item["upstream_status"],
                "upstream_reason": item["upstream_reason"],
                "evidence_class": evidence_class,
                "residual_counts": None,
                "source_dataset_fingerprint": None,
                "source_read_sha256": {},
                "source_artifacts": {},
                "metadata_missing": _metadata_missing(item),
                "contigs": [],
            })
            continue
        result = _validate_m6_observation(
            item, paths, config["orientation_policy"],
        )
        observation = result["observation"]
        observation["upstream_reason"] = None
        for field in (
            "candidate_id", "sample_id", "sequencing_run_id", "study_id",
            "source_artifact_id", "upstream_workflow_id", "observed_at",
        ):
            if item[field] is not None:
                observation[field] = item[field]
        observation["metadata_missing"] = [
            field for field in observation["metadata_missing"]
            if not (field == "sample_id" and observation["sample_id"] is not None)
        ]
        contig_count = len(observation["contigs"])
        base_count = sum(row["sequence_length"] for row in observation["contigs"])
        total_contigs += contig_count
        total_bases += base_count
        if total_contigs > MAX_SEQUENCE_RECORDS or total_bases > MAX_TOTAL_BASES:
            raise ValueError("M7 input exceeds aggregate sequence resource limits")
        observations.append(observation)
        for sequence in result["sequences"]:
            sequence_rows.append({
                **sequence,
                "observation_id": observation["observation_id"],
                "candidate_id": observation["candidate_id"],
                "sample_id": observation["sample_id"],
                "sequencing_run_id": observation["sequencing_run_id"],
                "study_id": observation["study_id"],
                "source_dataset_fingerprint": observation["source_dataset_fingerprint"],
                "molecule_type": observation["molecule_type"],
            })

    if config["orientation_policy"] == "reverse_complement_invariant":
        # An explicit molecule type is required only when a supported sequence
        # is actually being compared; missing M6 candidates remain missing.
        for row in sequence_rows:
            if row["molecule_type"] not in {"DNA", "RNA"}:
                raise ValueError(
                    "Reverse-complement matching requires DNA or RNA for every supported observation"
                )

    groups = _build_exact_groups(sequence_rows, config["orientation_policy"])
    recurrent_groups = [
        group for group in groups if group["source_dataset_count"] > 1
    ]
    state_counts = Counter(
        row["evidence_class"] for row in observations
    )
    if not sequence_rows:
        result_status = (
            "UPSTREAM_UNAVAILABLE_OR_FAILED"
            if observations and all(row["evidence_class"] in {
                "UPSTREAM_UNAVAILABLE", "UPSTREAM_FAILED",
            } for row in observations)
            else "NO_ELIGIBLE_SUPPORTED_SEQUENCES"
        )
    elif recurrent_groups:
        result_status = "RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS"
    else:
        result_status = "NO_RECURRENCE_DETECTED_WITHIN_EVALUATED_OBSERVATIONS"
    has_upstream_gaps = any(
        row["evidence_class"] in {"UPSTREAM_UNAVAILABLE", "UPSTREAM_FAILED"}
        for row in observations
    )
    summary = {
        "schema": SCHEMA_SUMMARY,
        "result_status": result_status,
        "analysis_completeness": "PARTIAL" if has_upstream_gaps else "COMPLETE",
        "observation_count": len(observations),
        "m6_evidence_class_counts": dict(sorted(state_counts.items())),
        "supported_sequence_observation_count": len(sequence_rows),
        "exact_group_count": len(groups),
        "recurrent_group_count": len(recurrent_groups),
        "orientation_policy": config["orientation_policy"],
        "comparison_method": "exact canonical nucleotide sequence content",
        "related_sequence_clustering": "not implemented",
        "thresholds": None,
        "limitations": [
            "Recurrence is limited to individually supported M6 contigs in the declared observations.",
            "Different sample, run or study identifiers are user-declared metadata and are not independently verified.",
            "Repeated processing of identical M6 source-read bytes counts as one source dataset for independence summaries.",
            "No recurrence detected applies only within evaluated observations; it is not evidence of universal absence.",
            "Recurrence does not establish satellite identity, novelty, helper dependence, biological function, replication, pathogenicity or complete-genome status.",
            "No raw reads are pooled and no candidates are reassembled by M7.",
        ],
    }
    observation_table = {
        "schema": SCHEMA_OBSERVATIONS,
        "record_count": len(observations),
        "sequence_observation_count": len(sequence_rows),
        "observations": observations,
        "sequence_observations": [
            {key: value for key, value in row.items()
             if not key.startswith("_") and key != "molecule_type"}
            for row in sorted(
                sequence_rows,
                key=lambda row: (row["observation_id"], row["sequence_id"]),
            )
        ],
    }
    exact_table = {
        "schema": SCHEMA_EXACT,
        "orientation_policy": config["orientation_policy"],
        "record_count": len(groups),
        "groups": groups,
    }
    validation = {
        "schema": SCHEMA_VALIDATION,
        "status": "partial" if has_upstream_gaps else "complete",
        "observation_count": len(observations),
        "available_m6_count": sum(
            row["m6_state"] == "available" for row in observations
        ),
        "unavailable_count": sum(
            row["evidence_class"] == "UPSTREAM_UNAVAILABLE" for row in observations
        ),
        "failed_count": sum(
            row["evidence_class"] == "UPSTREAM_FAILED" for row in observations
        ),
        "unsupported_count": sum(
            row["evidence_class"] == "UNSUPPORTED_RECONSTRUCTION" for row in observations
        ),
        "unresolved_count": sum(
            row["evidence_class"] == "UNRESOLVED_UNASSEMBLED_RESIDUAL_EVIDENCE"
            for row in observations
        ),
        "supported_sequence_observation_count": len(sequence_rows),
        "warnings": [
            "Missing metadata remains null and is excluded from independence categories.",
            "Only contigs individually marked READ_SUPPORTED_ASSEMBLY by M6 enter exact recurrence groups.",
        ],
    }

    write_json(output / "observations.json", observation_table)
    write_json(output / "exact_recurrence.json", exact_table)
    write_json(output / "recurrence_summary.json", summary)
    write_json(output / "validation_report.json", validation)
    _write_report(output / "report.html", summary, groups)

    input_artifacts = {
        name: {
            "artifact_type": input_types[name],
            "sha256": checksum(path),
            "size_bytes": path.stat().st_size,
        }
        for name, path in sorted(paths.items())
    }
    output_hashes = {
        name: checksum(output / name)
        for name in (
            "observations.json", "exact_recurrence.json",
            "recurrence_summary.json", "validation_report.json", "report.html",
        )
    }
    provenance = {
        "schema": SCHEMA_PROVENANCE,
        "status": "complete",
        "stage_version": STAGE_VERSION,
        "configuration": config,
        "configuration_sha256": _hash_text(_canonical_json(config).decode("utf-8")),
        "input_artifacts": input_artifacts,
        "observation_source_datasets": [
            {
                "observation_id": row["observation_id"],
                "m6_state": row["m6_state"],
                "m6_status": row["m6_status"],
                "source_dataset_fingerprint": row["source_dataset_fingerprint"],
                "source_artifacts": row["source_artifacts"],
                "upstream_workflow_id": row["upstream_workflow_id"],
                "upstream_stage_id": row["upstream_stage_id"],
                "upstream_manifest_sha256": row["upstream_manifest_sha256"],
            }
            for row in observations
        ],
        "comparison": {
            "method": "exact canonical nucleotide sequence content",
            "orientation_policy": config["orientation_policy"],
            "related_sequence_clustering": False,
            "thresholds": None,
            "source_dataset_deduplication": "SHA256 of declared M6 source-read artifact digests",
        },
        "implementation": _implementation_identity(),
        "output_sha256": output_hashes,
        "execution_state": summary["analysis_completeness"],
    }
    write_json(output / "recurrence_provenance.json", provenance)
    for name, contract in OUTPUT_CONTRACTS.items():
        artifact_contracts.validate_artifact(output / name, contract)
    return list(OUTPUT_CONTRACTS)


def _stage_identity(config, inputs):
    implementation = _implementation_identity()
    return {
        "schema": "m7-stage-identity-v1",
        "stage_version": STAGE_VERSION,
        "configuration": config,
        "inputs": {
            name: {
                "sha256": checksum(path),
                "artifact_type": expected_input_types(config)[name],
            }
            for name, path in sorted(inputs.items())
        },
        "implementation": implementation,
    }


def _verify_reused_outputs(output, manifest):
    digests = manifest.get("output_sha256")
    if not isinstance(digests, dict) or not digests:
        raise ValueError("M7 completed manifest has no output checksums")
    for name, digest in digests.items():
        if (not isinstance(name, str) or not portable_name(name) or
                name.casefold() == "manifest.json" or not isinstance(digest, str) or
                not _HASH.fullmatch(digest)):
            raise ValueError("M7 manifest contains an invalid output inventory")
        path = output / name
        if (path.is_symlink() or not path.is_file() or
                not path.resolve().is_relative_to(output) or checksum(path) != digest):
            raise ValueError("M7 output integrity failure; existing result preserved")
    for name, contract in OUTPUT_CONTRACTS.items():
        if name not in digests:
            raise ValueError("M7 output manifest is missing a declared artifact")
        artifact_contracts.validate_artifact(output / name, contract)


def run_stage(inputs, output, config):
    """Execute M7 with config-bound, checksum-verified reuse."""
    config = validate_config(config)
    input_types = expected_input_types(config)
    if set(inputs) != set(input_types):
        raise ValueError("M7 workflow inputs must match the observation declarations exactly")
    paths = {}
    for name, value in inputs.items():
        raw = Path(value)
        if raw.is_symlink():
            raise ValueError("M7 inputs must not be symbolic links")
        path = raw.resolve(strict=True)
        if not path.is_file():
            raise ValueError("M7 inputs must be regular files")
        paths[name] = path

    output = Path(output).resolve()
    if any(path.is_relative_to(output) for path in paths.values()):
        raise ValueError("M7 inputs must be outside its output folder")
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".m7.lock"
    token = stage_lock.acquire(lock)
    marker = output / "manifest.json"
    result = None
    try:
        identity = _stage_identity(config, paths)
        if marker.exists():
            if marker.is_symlink() or not marker.is_file():
                raise ValueError("M7 manifest must be a regular file")
            prior = json.loads(marker.read_text(encoding="utf-8"))
            if prior.get("identity") != identity:
                raise ValueError("M7 inputs, metadata, configuration or implementation changed")
            if prior.get("status") == "complete":
                _verify_reused_outputs(output, prior)
                return prior
        elif any(path != lock for path in output.iterdir()):
            raise ValueError("M7 output folder is not empty and has no matching manifest")

        result = {
            "schema": "m7-stage-manifest-v1",
            "status": "running",
            "identity": identity,
            "input_artifacts": identity["inputs"],
            "configuration": config,
            "started_utc": datetime.now(timezone.utc).isoformat(),
        }
        sequence_downloader.write_json(marker, result)
        names = _produce(paths, output, config, input_types)
        if (not names or
                any(not portable_name(name) or name.casefold() == "manifest.json"
                    for name in names) or
                len({name.casefold() for name in names}) != len(names)):
            raise ValueError("M7 produced invalid output names")
        output_hashes = {}
        for name in names:
            path = output / name
            if (path.is_symlink() or not path.is_file() or
                    not path.resolve().is_relative_to(output)):
                raise ValueError("M7 output is missing, unsafe or redirected")
            output_hashes[name] = checksum(path)
        for name, path in paths.items():
            if checksum(path) != identity["inputs"][name]["sha256"]:
                raise ValueError("M7 input changed during recurrence analysis")
        result.update(
            status="complete",
            finished_utc=datetime.now(timezone.utc).isoformat(),
            output_sha256=output_hashes,
        )
        sequence_downloader.write_json(marker, result)
        return result
    except BaseException as error:
        if result is not None:
            result.update(status="failed", error=str(error))
            sequence_downloader.write_json(marker, result)
        raise
    finally:
        stage_lock.release(lock, token)


def _cache_implementation_identity():
    """Exclude package-wide M8-only edits from M7 stage cache identity."""
    files = {
        "independent_recurrence.py": Path(__file__),
        "sequence_catalogue.py": Path(sequence_catalogue.__file__),
        "sequence_downloader.py": Path(sequence_downloader.__file__),
        "stage_lock.py": Path(stage_lock.__file__),
        "portable_paths.py": Path(__file__).with_name("portable_paths.py"),
    }
    return {
        "stage": "m7-independent-recurrence",
        "stage_version": STAGE_VERSION,
        "implementation_sha256": {
            name: checksum(path) for name, path in sorted(files.items())
        },
    }


run_stage.cache_implementation_identity = _cache_implementation_identity