"""Fail-closed M36 stage adapter and unregistered integration harness.

The harness exercises M25 generation and distinct downstream evidence
checkpoints with small synthetic inputs. It is not a registered-attempt runner.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import patch

from . import m19_benchmark as m19
from . import m25_read_coverage as m25
from . import m31_synthetic_evidence_screening as m31
from . import m8_contracts, m8_homology
from . import m8_reference_panels
from .artifact_workflow import build_default_registry, run as run_artifact_workflow
from .m36_preparation import (
    RunnerBlocked,
    _read_fastq_bytes,
    validate_truth_support_crosswalk,
)
from .m8_candidate_handoff import validate_candidate_sequence_set


STAGES = ("generation", "assembly", "support", "detection")


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def _receipt(stage: str, status: str, inputs: dict, outputs: dict) -> dict:
    if stage not in STAGES:
        raise ValueError("unknown M36 evidence checkpoint")
    return {
        "stage": stage,
        "status": status,
        "input_sha256": {
            key: _digest(value) for key, value in sorted(inputs.items())
        },
        "output_sha256": {
            key: _digest(value) for key, value in sorted(outputs.items())
        },
    }


def validate_m6_to_m8_handoff(candidate_sequence_set: str | Path) -> dict:
    """Validate the frozen typed M6 candidate artifact before an M8 handoff."""
    return validate_candidate_sequence_set(candidate_sequence_set)


def build_m6_candidate_handoff(
    assembly_dir: str | Path,
    output_dir: str | Path,
    *,
    support_evidence: dict,
    support_status: str,
) -> Path:
    """Build and validate the existing typed M6-to-M8 candidate contract."""
    assembly_dir, output_dir = Path(assembly_dir), Path(output_dir)
    contigs_path = assembly_dir / "canonical_contigs.fasta"
    assembly_manifest_path = assembly_dir / "assembly_manifest.json"
    if not contigs_path.is_file() or not assembly_manifest_path.is_file():
        raise ValueError("M8 handoff requires completed assembly artifacts")
    if support_status not in {
        "READ_SUPPORTED_ASSEMBLY", "NO_SUPPORTED_ASSEMBLY",
        "NOT_EVALUATED", "READ_SUPPORT_FAILED", "INVALID_SUPPORT_OUTPUT",
    }:
        raise ValueError("M6 support status is not recognized")
    output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    (output_dir / "assembly").mkdir(mode=0o700)
    copied_contigs = output_dir / "assembly" / "contigs.fasta"
    copied_assembly_manifest = output_dir / "assembly" / "assembly_manifest.json"
    shutil.copyfile(contigs_path, copied_contigs)
    shutil.copyfile(assembly_manifest_path, copied_assembly_manifest)
    fasta_bytes = copied_contigs.read_bytes()
    assembly_bytes = copied_assembly_manifest.read_bytes()
    sequence_by_id = {}
    current_id = None
    for line in fasta_bytes.decode("ascii").splitlines():
        if line.startswith(">"):
            current_id = line[1:].split()[0]
            sequence_by_id[current_id] = ""
        elif current_id is not None:
            sequence_by_id[current_id] += line
    if not sequence_by_id:
        raise ValueError("completed assembly emitted no canonical contigs")
    (output_dir / "candidate_sequences.fasta").write_bytes(fasta_bytes)
    reconstruction = {
        "schema": "m6-reconstruction-evidence-v1",
        "status": support_status,
        "contigs": [
            {"contig_id": identifier, "m6_support_status": (
                "READ_SUPPORTED_ASSEMBLY"
                if identifier in set(support_evidence.get("supported_contig_ids", []))
                else "UNSUPPORTED_ASSEMBLY"
            )}
            for identifier in sorted(sequence_by_id)
        ],
        "configuration": {},
        "provenance": {"upstream": "M36 unregistered synthetic fixture"},
    }
    reconstruction_bytes = _json_bytes(reconstruction)
    (output_dir / "reconstruction_evidence.json").write_bytes(reconstruction_bytes)
    fasta_ref = {
        "path": "candidate_sequences.fasta",
        "sha256": _digest(fasta_bytes),
    }
    source_ref = {
        "path": "assembly/contigs.fasta",
        "sha256": _digest(fasta_bytes),
    }
    assembly_ref = {
        "path": "assembly/assembly_manifest.json",
        "sha256": _digest(assembly_bytes),
    }
    evidence_ref = {
        "path": "reconstruction_evidence.json",
        "sha256": _digest(reconstruction_bytes),
    }
    records = []
    for index, (contig_id, sequence) in enumerate(sorted(sequence_by_id.items())):
        identifier = hashlib.sha256(
            f"{index}\0{contig_id}".encode("utf-8")
        ).hexdigest()[:20]
        records.append({
            "candidate_id": f"m36-{identifier}",
            "sequence_id": f"m36-seq-{identifier}",
            "fasta_record_id": contig_id,
            "sequence_sha256": _digest(sequence.encode("ascii")),
            "sequence_length": len(sequence),
            "sequence_bytes_available": True,
            "sequence_unavailable_reason": None,
            "molecule_type": "DNA",
            "sequence_alphabet": "IUPAC_NUCLEOTIDE",
            "completeness_state": "UNKNOWN",
            "source_artifact_id": source_ref["path"],
            "source_artifact_sha256": source_ref["sha256"],
            "m6_support_status": (
                "READ_SUPPORTED_ASSEMBLY"
                if contig_id in set(support_evidence.get("supported_contig_ids", []))
                else "UNSUPPORTED_ASSEMBLY"
            ),
            "m7_context": None,
        })
    document = {
        "schema": "m8-candidate-sequence-set-v1",
        "producer": {
            "stage_kind": "residual_evidence",
            "stage_id": "m36-unregistered-fixture",
            "adapter_name": "m36-phase2b-fixture-handoff",
            "adapter_version": "1",
        },
        "source_artifact": source_ref,
        "assembly_manifest": assembly_ref,
        "m6_evidence": {
            "reconstruction_status": support_status,
            "support_status": support_status,
            "artifact": evidence_ref,
        },
        "m7_context": None,
        "availability": {
            "state": "AVAILABLE",
            "reason": None,
            "fasta_artifact": fasta_ref,
            "record_count": len(records),
        },
        "records": records,
    }
    manifest_path = output_dir / "candidate_sequence_set.json"
    manifest_path.write_bytes(_json_bytes(document))
    validate_m6_to_m8_handoff(manifest_path)
    return manifest_path


def triage_m8_outputs(query_rows: list[dict], matches: list[dict],
                      sequences: dict[str, str]) -> list[dict]:
    """Apply the frozen M31 triage rules only to explicit M8 result rows."""
    if not isinstance(query_rows, list) or not isinstance(matches, list):
        raise ValueError("M8 query and match outputs must be arrays")
    if not isinstance(sequences, dict):
        raise ValueError("candidate sequence map is required for M31 triage")
    prepared = []
    for row in query_rows:
        if not isinstance(row, dict) or row.get("candidate_id") not in sequences:
            raise ValueError("M8 query row does not match a handed-off candidate")
        sequence = sequences[row["candidate_id"]].upper()
        counts = {}
        for index in range(max(0, len(sequence) - 2)):
            kmer = sequence[index:index + 3]
            counts[kmer] = counts.get(kmer, 0) + 1
        low_complexity = (
            len(sequence) >= 3
            and max(counts.values(), default=0) / max(1, len(sequence) - 2) >= 0.20
        )
        prepared.append({**row, "low_complexity": low_complexity})
    return m31.triage(prepared, matches)


def run_frozen_m8_m31_handoff(
    candidate_sequence_set: str | Path,
    reference_snapshot_manifest: str | Path,
    reference_root: str | Path,
    output_root: str | Path,
    *,
    blastn_executable: str,
    makeblastdb_executable: str,
) -> dict:
    """Run the existing M8 workflow and M31 triage on an explicit snapshot."""
    candidate_path = Path(candidate_sequence_set).resolve(strict=True)
    validate_m6_to_m8_handoff(candidate_path)
    manifest_path = Path(reference_snapshot_manifest).resolve(strict=True)
    reference_root = Path(reference_root).resolve(strict=True)
    snapshot = m8_reference_panels.validate_snapshot_manifest(manifest_path)
    output_root = Path(output_root)
    output_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    roles = set(snapshot["roles"])
    role_plan = {
        role: ({"status": "SELECTED"} if role in roles else {
            "status": "NOT_SELECTED", "reason": "not present in supplied snapshot",
        })
        for role in sorted(m8_contracts.PANEL_ROLES)
    }
    inputs = {
        "candidate_sequence_set": {
            "path": str(candidate_path),
            "artifact_type": "m8_candidate_sequence_set",
        },
        "reference_snapshot_manifest": {
            "path": str(manifest_path),
            "artifact_type": "m8_reference_snapshot_manifest",
        },
    }
    filenames = [
        snapshot["panel_fasta_filename"],
        *(row["filename"] for row in snapshot["index_files"]),
    ]
    for filename in filenames:
        payload = reference_root / filename
        if payload.is_symlink() or not payload.is_file():
            raise ValueError("declared frozen M8 reference payload is missing or unsafe")
        inputs[m8_homology.payload_input_name(filename)] = {
            "path": str(payload.resolve(strict=True)),
            "artifact_type": "m8_reference_payload",
        }
    spec = {
        "schema": "artifact-workflow-v1",
        "stages": [{
            "id": "m36-frozen-m8",
            "kind": "m8_homology",
            "inputs": inputs,
            "config": {
                "role_plan": role_plan,
                "blastn_executable": str(Path(blastn_executable).resolve(strict=True)),
                "makeblastdb_executable": str(Path(makeblastdb_executable).resolve(strict=True)),
            },
        }],
    }
    spec_path = output_root / "workflow_spec.json"
    spec_path.write_bytes(_json_bytes(spec))
    run_artifact_workflow(
        spec_path, output_root / "workflow", build_default_registry(),
    )
    workflow = json.loads(
        (output_root / "workflow" / "workflow.json").read_text(encoding="utf-8")
    )
    stage_root = output_root / "workflow" / workflow["stages"][0]["output_path"]
    query_doc = json.loads((stage_root / "query_status.json").read_text(encoding="utf-8"))
    match_doc = json.loads((stage_root / "matches.json").read_text(encoding="utf-8"))
    candidate_doc = json.loads(candidate_path.read_text(encoding="utf-8"))
    fasta_path = candidate_path.parent / candidate_doc["availability"]["fasta_artifact"]["path"]
    sequences = {}
    for row in candidate_doc["records"]:
        identifier = row["fasta_record_id"]
        sequence = ""
        current = None
        for line in fasta_path.read_text(encoding="ascii").splitlines():
            if line.startswith(">"):
                current = line[1:].split()[0]
            elif current == identifier:
                sequence += line
        sequences[row["candidate_id"]] = sequence
    outcomes = triage_m8_outputs(query_doc["queries"], match_doc["matches"], sequences)
    summary = {
        "schema": "m36-m8-m31-handoff-v1",
        "m8_aggregate_status": query_doc.get("aggregate_status"),
        "candidate_count": len(candidate_doc["records"]),
        "snapshot_digest": snapshot["snapshot_digest"],
        "triage": outcomes,
        "truth_or_split_mapping_included": False,
    }
    (output_root / "m36_m8_m31_handoff.json").write_bytes(_json_bytes(summary))
    return summary


def run_unregistered_fixture(
    output_root: str | Path,
    *,
    truth_sequence: str,
    technical_reference: str,
    backgrounds: tuple[str, ...],
    seed: int,
    read_length: int,
    coverage: int,
    error_rate: float,
    insertion_rate: float = 0.0,
    deletion_rate: float = 0.0,
    assembler: str,
    assembly_stage,
    support_stage,
    detection_stage=None,
) -> dict:
    """Exercise ordered stage handoffs on caller-supplied synthetic fixtures.

    Stage callables are explicit so tests can use tiny deterministic stand-ins.
    No registered assignment, private manifest, biological input, or public
    artifact is accepted by this harness.
    """
    if assembler not in {"spades", "tadpole"}:
        raise ValueError("assembler must be a frozen SPAdes or Tadpole arm")
    if type(seed) is not int or seed < 0:
        raise ValueError("synthetic fixture seed must be a non-negative integer")
    if not callable(assembly_stage) or not callable(support_stage):
        raise ValueError("assembly and read-support stages are required")
    if not truth_sequence or not technical_reference:
        raise ValueError("synthetic truth and technical reference are required")

    root = Path(output_root)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    generation_dir = root / "generation"
    assembly_dir = root / "assembly"
    support_dir = root / "support"
    detection_dir = root / "detection"
    for directory in (generation_dir, assembly_dir, support_dir, detection_dir):
        directory.mkdir(mode=0o700)

    case = {
        "analysis_id": "case-" + hashlib.sha256(
            f"m36-unregistered-{seed}".encode("ascii")
        ).hexdigest()[:24],
        "m25_read_length": read_length,
        "coverage": coverage,
        "read_start_mode": "uniform",
        "error_rate": error_rate,
        "insertion_rate": insertion_rate,
        "deletion_rate": deletion_rate,
        "m25_background_read_coverage": True,
        "m25_apply_background_errors": True,
    }
    params = {"coverage": coverage, "error_rate": error_rate}
    with patch.object(m19, "SEED", seed):
        fastq_bytes = m25._make_fastq(
            case, truth_sequence, technical_reference, params, backgrounds,
        )
    reads = _read_fastq_bytes(fastq_bytes)
    provenance = case.get("_m25_layout", {}).get("read_provenance")
    if not isinstance(provenance, dict) or set(provenance) != {row[0] for row in reads}:
        raise RunnerBlocked("M25 output and placement ledger do not reconcile")
    fastq_path = generation_dir / "generated_reads.fastq.gz"
    fastq_path.write_bytes(fastq_bytes)
    ledger_bytes = _json_bytes({"read_provenance": provenance})
    (generation_dir / "placement_ledger.json").write_bytes(ledger_bytes)
    receipts = [_receipt("generation", "PASS", {}, {
        "generated_reads.fastq.gz": fastq_bytes,
        "placement_ledger.json": ledger_bytes,
    })]

    assembly = assembly_stage(fastq_path, assembly_dir, assembler)
    contigs = assembly.get("contigs") if isinstance(assembly, dict) else None
    if (not isinstance(assembly, dict)
            or assembly.get("status") not in {"PASS", "COMPLETE"}
            or not isinstance(contigs, dict) or not contigs
            or any(not isinstance(name, str) or not name
                   or not isinstance(sequence, str) or not sequence
                   for name, sequence in contigs.items())):
        return {
            "status": "ASSEMBLY_OUTPUT_INVALID",
            "checkpoints": receipts + [
                _receipt("assembly", "INVALID", {"reads": fastq_bytes}, {}),
            ],
            "registered_matrix_executed": False,
        }
    contig_bytes = "".join(
        f">{name}\n{sequence}\n" for name, sequence in sorted(contigs.items())
    ).encode("ascii")
    (assembly_dir / "canonical_contigs.fasta").write_bytes(contig_bytes)
    assembly_manifest_path = assembly_dir / "assembly_manifest.json"
    if not assembly_manifest_path.exists():
        assembly_manifest_path.write_bytes(_json_bytes({
            "schema": "assembly-manifest-v1",
            "stage_id": "m36-unregistered-fixture",
            "assembler": assembler,
            "external_tool_version": "UNREGISTERED_FIXTURE_STAGE",
            "workflow_status": "complete",
            "contig_count": len(contigs),
        }))
    assembly_evidence = assembly.get("evidence", b"")
    if isinstance(assembly_evidence, str):
        assembly_evidence = assembly_evidence.encode("utf-8")
    if not isinstance(assembly_evidence, bytes):
        raise ValueError("assembly evidence must be bytes or text")
    receipts.append(_receipt("assembly", "PASS", {"reads": fastq_bytes}, {
        "canonical_contigs.fasta": contig_bytes,
        "assembly_evidence": assembly_evidence,
    }))

    read_sequences = {row[0]: row[1] for row in reads}
    support = support_stage(fastq_path, contigs, read_sequences)
    if not isinstance(support, dict):
        raise ValueError("read-support stage must return an evidence object")
    support_bytes = _json_bytes(support)
    (support_dir / "read_support.json").write_bytes(support_bytes)
    crosswalk = validate_truth_support_crosswalk(
        truth_sequence=truth_sequence,
        read_sequences=read_sequences,
        placement_ledger={"read_provenance": provenance},
        contigs=contigs,
        support_evidence=support,
    )
    support_status = crosswalk["support"]
    receipts.append(_receipt("support", support_status, {
        "reads": fastq_bytes, "contigs": contig_bytes,
    }, {"read_support.json": support_bytes}))

    candidate_path = build_m6_candidate_handoff(
        assembly_dir,
        detection_dir / "m6-handoff",
        support_evidence=support,
        support_status=support_status,
    )
    detection = {"status": "NOT_EVALUATED",
                 "reason": "No explicit frozen M8 reference snapshot was supplied."}
    if support_status == "READ_SUPPORTED_ASSEMBLY" and detection_stage is not None:
        detection = detection_stage(
            candidate_path, assembly_dir, support_dir, detection_dir,
        )
        if not isinstance(detection, dict) or not isinstance(
            detection.get("status"), str,
        ):
            raise ValueError("detection handoff must return an explicit status")
    detection_bytes = _json_bytes(detection)
    (detection_dir / "downstream_result.json").write_bytes(detection_bytes)
    receipts.append(_receipt("detection", detection["status"], {
        "contigs": contig_bytes, "support": support_bytes,
        "m6_candidate_set": candidate_path.read_bytes(),
    }, {"downstream_result.json": detection_bytes}))

    return {
        "status": (
            "PASS" if detection.get("status") == "PASS"
            and support_status == "READ_SUPPORTED_ASSEMBLY"
            else "INCOMPLETE"
        ),
        "checkpoints": receipts,
        "generation": {"read_count": len(reads), "fastq_sha256": _digest(fastq_bytes)},
        "assembly": {"contig_count": len(contigs), "assembler": assembler},
        "support": crosswalk,
        "detection": detection,
        "registered_matrix_executed": False,
    }


class M36Phase2BAttemptAdapter:
    """Registered entry point intentionally disabled pending scientific review."""

    REGISTERED_EXECUTION_READY = False

    def __call__(self, *_args, **_kwargs):
        raise RunnerBlocked(
            "registered M36 stage adapter is not execution-ready; resolve the "
            "scientific specification and frozen M8 reference-panel contract first"
        )
