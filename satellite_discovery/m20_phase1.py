"""M20 Phase 1 contract map and deterministic synthetic fixture generator."""

import argparse
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import random

from .artifact_workflow import build_default_registry
from . import m12_contracts, m15_contracts


SCHEMA = "m20-phase1-synthetic-fixtures-v1"
SEED = 20261016
READ_LENGTH = 100
COVERAGE = 10
CANDIDATE_LENGTH = 400
DECOY_LENGTH = 600
SAMPLE_IDS = ("s01", "s02", "s03")
POSITIVE_IDS = SAMPLE_IDS[:2]
CONTRACT_MAP_SCHEMA = "m20-registered-contract-map-v1"
AUDITED_MAIN = "135ec519f47dc49eb50563398a52423723a4ce95"
CONTRACT_KINDS = (
    "fastq_qc", "residual_evidence", "independent_recurrence",
    "m8_homology", "m9_orf_translation", "m9_blastp",
    "m10_exact_first", "m12_artifact_review", "m15_evidence_dossier",
)
_CODONS = (
    "GCT", "GCC", "GCA", "GCG", "ACT", "ACC", "ACA", "ACG",
    "GGT", "GGC", "GGA", "GGG", "CAA", "CAG", "AAT", "AAC",
    "GAA", "GAG", "TTC", "TTT", "CTG", "CTA", "ATT", "ATC",
)


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _fq_bytes(sequence, seed):
    rng = random.Random(seed)
    read_count = (COVERAGE * len(sequence) + READ_LENGTH - 1) // READ_LENGTH
    reads = []
    for index in range(read_count):
        start = rng.randint(0, len(sequence) - READ_LENGTH)
        bases = list(sequence[start:start + READ_LENGTH])
        # Low-rate deterministic substitutions make the two positive read sets
        # independent while keeping all inputs artificial and reproducible.
        if rng.random() < 0.08:
            pos = rng.randrange(READ_LENGTH)
            bases[pos] = rng.choice("ACGT".replace(bases[pos], ""))
        reads.append((f"r{index + 1:04d}", "".join(bases), "I" * READ_LENGTH))
    text = "".join(f"@{name}\n{seq}\n+\n{qual}\n" for name, seq, qual in reads).encode("ascii")
    buffer = BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0, compresslevel=9) as out:
        out.write(text)
    return buffer.getvalue()


def _expected_files():
    candidate_rng = random.Random(SEED)
    candidate = "".join(candidate_rng.choice("ACGT") for _ in range(CANDIDATE_LENGTH))
    orf_rng = random.Random(SEED + 1)
    orf = "ATG" + "".join(orf_rng.choice(_CODONS) for _ in range(28)) + "TAA"
    orf_start = 60
    candidate = candidate[:orf_start] + orf + candidate[orf_start + len(orf):]
    decoy_rng = random.Random(SEED + 2)
    decoy = "".join(decoy_rng.choice("ACGT") for _ in range(DECOY_LENGTH))

    files = {}
    truth_cases = []
    for index, sample_id in enumerate(SAMPLE_IDS):
        is_positive = sample_id in POSITIVE_IDS
        sequence = candidate if is_positive else decoy
        reads = _fq_bytes(sequence, SEED + 100 + index)
        base = f"{sample_id}/"
        files[f"{base}reads.fastq.gz"] = reads
        files[f"{base}reference.fasta"] = f">ref01\n{decoy}\n".encode("ascii")
        files[f"{base}reference_roles.csv"] = (
            "reference_id,reference_role,reference_source,reference_version\n"
            "ref01,technical_reference,m20-synthetic,M20-phase1\n"
        ).encode("ascii")
        truth_cases.append({
            "sample_id": sample_id,
            "expected_role": "positive" if is_positive else "negative",
            "candidate_sequence": candidate if is_positive else None,
            "expected_recurrence": "shared_candidate" if is_positive else "absent",
            "planted_orf": (
                {"start": orf_start, "end": orf_start + len(orf), "strand": "+",
                 "coordinate_system": "zero-based-half-open"}
                if is_positive else None
            ),
        })
    manifest = {
        "schema": SCHEMA,
        "seed": SEED,
        "synthetic_only": True,
        "read_length": READ_LENGTH,
        "nominal_coverage": COVERAGE,
        "files": {
            path: {"artifact_type": _input_type(path), "bytes": len(data), "sha256": _sha(data)}
            for path, data in sorted(files.items())
        },
    }
    truth = {"schema": "m20-heldout-truth-v1", "cases": truth_cases}
    return files, _canonical(manifest), _canonical(truth)


def _input_type(path):
    if path.endswith("reads.fastq.gz"):
        return "raw_read"
    if path.endswith("reference.fasta"):
        return "raw_fasta"
    return "reference_roles"


def _safe_path(root, relative):
    rel = PurePosixPath(str(relative))
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("Fixture path must be relative and traversal-free")
    root = Path(root)
    if root.is_symlink():
        raise ValueError("Fixture root may not be a symlink")
    resolved_root = root.resolve()
    current = root
    for part in rel.parts[:-1]:
        current = current / part
        if current.is_symlink() or (current.exists() and not current.is_dir()):
            raise ValueError("Fixture parent is a symlink or non-directory")
    target = current / rel.parts[-1]
    if target.is_symlink() or not target.resolve().is_relative_to(resolved_root):
        raise ValueError("Fixture path escapes its root")
    return target


def _reject_symlink_ancestors(path):
    current = Path(path).absolute()
    for item in (current, *current.parents):
        if item.is_symlink():
            raise ValueError("Fixture output path may not pass through a symlink")


def _reject_unexpected_inputs(root, expected):
    inputs = root / "inputs"
    if not inputs.exists():
        return
    if inputs.is_symlink():
        raise ValueError("Input directory may not be a symlink")
    actual = set()
    for path in inputs.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlinks are not allowed in fixture inputs")
        if path.is_file():
            actual.add(path.relative_to(inputs).as_posix())
    allowed = set(expected) | {"source_manifest.json"}
    extra = actual - allowed
    if extra:
        raise ValueError(f"Unexpected or stale fixture inputs: {sorted(extra)}")


def generate_fixtures(output_root):
    """Create deterministic analysis inputs and a truth sidecar outside inputs/."""
    root = Path(output_root)
    _reject_symlink_ancestors(root)
    files, manifest, truth = _expected_files()
    _reject_unexpected_inputs(root, files)
    for relative, data in files.items():
        target = _safe_path(root / "inputs", relative)
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise ValueError(f"Refusing to reuse changed fixture: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    for relative, data in (
        ("inputs/source_manifest.json", manifest),
        ("heldout_truth.json", truth),
    ):
        target = _safe_path(root, relative)
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise ValueError(f"Refusing to reuse changed fixture metadata: {relative}")
        if not target.exists():
            target.write_bytes(data)
    return verify_fixtures(root)


def verify_fixtures(output_root):
    """Recompute expected fixture bytes; do not trust self-reported hashes."""
    root = Path(output_root)
    _reject_symlink_ancestors(root)
    files, manifest, truth = _expected_files()
    if root.is_symlink():
        raise ValueError("Fixture root may not be a symlink")
    _reject_unexpected_inputs(root, files)
    for relative, expected in files.items():
        path = _safe_path(root / "inputs", relative)
        if not path.is_file() or path.read_bytes() != expected:
            raise ValueError(f"Fixture bytes differ from deterministic generator: {relative}")
    for relative, expected in (
        ("inputs/source_manifest.json", manifest),
        ("heldout_truth.json", truth),
    ):
        path = _safe_path(root, relative)
        if not path.is_file() or path.read_bytes() != expected:
            raise ValueError(f"Fixture metadata differs from deterministic generator: {relative}")
    return {"schema": SCHEMA, "sample_count": len(SAMPLE_IDS),
            "files_verified": len(files), "manifest_sha256": _sha(manifest),
            "heldout_truth_sha256": _sha(truth)}


def _norm_contracts(mapping):
    return {name: sorted(value if isinstance(value, (tuple, list, set, frozenset)) else [value])
            for name, value in sorted((mapping or {}).items())}


def build_contract_map():
    """Snapshot registered stage contracts and the M12/M15 producer allowlists."""
    registry = build_default_registry()
    stages = {}
    for kind in CONTRACT_KINDS:
        stage = registry._stages[kind]
        validator = stage.config_validator
        stages[kind] = {
            "required_input_fields": sorted(stage.input_fields or ()),
            "optional_input_fields": sorted(stage.optional_input_fields or ()),
            "dynamic_inputs": bool(stage.dynamic_inputs),
            "external_tool": bool(stage.external_tool),
            "input_contracts": _norm_contracts(stage.input_contracts),
            "output_contracts": _norm_contracts(stage.output_contracts),
            "config_validator": (
                f"{validator.__module__}.{validator.__name__}" if validator else None
            ),
        }
    m12 = {key: sorted(value) for key, value in m12_contracts.PRODUCER_TYPES.items()}
    m15 = {key: sorted(value) for key, value in m15_contracts.PRODUCER_TYPES.items()}
    return {
        "schema": CONTRACT_MAP_SCHEMA,
        "audited_main_commit": AUDITED_MAIN,
        "stages": stages,
        "producer_bindings": {
            "M12": m12,
            "M15": m15,
            "M15_stage_kinds": dict(sorted(m15_contracts.PRODUCER_STAGE_KINDS.items())),
        },
        "validators": {
            "artifacts": "satellite_discovery.artifact_contracts.validate_artifact",
            "M12_inputs": "satellite_discovery.m12_contracts.validate_input_manifest",
            "M12_outputs": "satellite_discovery.m12_contracts.validate_output_file",
            "M15_inputs": "satellite_discovery.m15_contracts.validate_input_manifest",
            "M15_bindings": "satellite_discovery.m15_stage._validate_ref",
        },
        "supported_edges": [
            {"from": "fastq_qc", "to": "residual_evidence",
             "artifact_types": ["qc_fastq", "qc_manifest"]},
            {"from": "residual_evidence", "to": "independent_recurrence",
             "artifact_types": ["reconstruction_evidence", "residual_read_manifest",
                                "canonical_contig_fasta"]},
            {"from": "residual_evidence", "to": "m8_homology",
             "artifact_types": ["m8_candidate_sequence_set", "m8_reference_snapshot_manifest",
                                "m8_reference_payload"]},
            {"from": "independent_recurrence", "to": "m8_homology",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M7"])},
            {"from": "residual_evidence", "to": "m9_orf_translation",
             "artifact_types": ["m8_candidate_sequence_set"]},
            {"from": "independent_recurrence", "to": "m9_orf_translation",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M7"])},
            {"from": "m8_homology", "to": "m9_orf_translation",
             "artifact_types": ["m8_query_status", "m8_match_evidence", "m8_summary",
                                "m8_search_commands", "m8_raw_blast_output"]},
            {"from": "m9_orf_translation", "to": "m9_blastp",
             "artifact_types": ["m9_orf_results", "m9_protein_fasta"],
             "additional_external_inputs": ["m9_protein_reference_manifest",
                                            "m9_protein_reference_payload"]},
            {"from": "residual_evidence", "to": "m12_artifact_review",
             "artifact_types": sorted(m12_contracts.PRODUCER_TYPES["M6"])},
            {"from": "residual_evidence", "to": "m10_exact_first",
             "artifact_types": ["m8_candidate_sequence_set"]},
            {"from": "independent_recurrence", "to": "m10_exact_first",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M7"])},
            {"from": "m8_homology", "to": "m10_exact_first",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M8"] - {"m8_reference_snapshot_manifest"})},
            {"from": "m9_orf_translation", "to": "m10_exact_first",
             "artifact_types": ["m9_orf_results", "m9_protein_fasta", "m9_orf_bundle"]},
            {"from": "m9_blastp", "to": "m10_exact_first",
             "artifact_types": ["m9_protein_search_status", "m9_protein_match_evidence",
                                "m9_protein_summary", "m9_search_commands",
                                "m9_output_bundle", "m9_raw_blast_output"]},
            {"from": "residual_evidence", "to": "m15_evidence_dossier",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M6"])},
            {"from": "independent_recurrence", "to": "m15_evidence_dossier",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M7"])},
            {"from": "m8_homology", "to": "m15_evidence_dossier",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M8"])},
            {"from": "m9_orf_translation/m9_blastp", "to": "m15_evidence_dossier",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M9"])},
            {"from": "m10_exact_first", "to": "m15_evidence_dossier",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M10"])},
            {"from": "m12_artifact_review", "to": "m15_evidence_dossier",
             "artifact_types": sorted(m15_contracts.PRODUCER_TYPES["M12"])},
        ],
        "unsupported_edges": [
            {"from": "fastq_qc", "to": "m12_artifact_review", "reason": "M12 accepts only M5/M6 producer types."},
            {"from": "fastq_qc", "to": "m15_evidence_dossier", "reason": "M15 has no M4 QC artifact types."},
            {"from": "independent_recurrence", "to": "m12_artifact_review", "reason": "M12 does not accept M7 types."},
            {"from": "m8_homology", "to": "m12_artifact_review", "reason": "M12 does not accept M8 types."},
            {"from": "m9_orf_translation", "to": "m12_artifact_review", "reason": "M12 does not accept M9 types."},
            {"from": "m10_exact_first", "to": "m12_artifact_review", "reason": "M12 does not accept M10 types."},
        ],
    }


def _write_contract_map(path):
    Path(path).write_bytes(_canonical(build_contract_map()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Generate fixtures in this dedicated output directory")
    parser.add_argument("--write-contract-map", help="Write the registered contract map JSON")
    args = parser.parse_args(argv)
    if args.write_contract_map:
        _write_contract_map(args.write_contract_map)
        print(f"Wrote registered contract map: {args.write_contract_map}")
    if args.output:
        print(json.dumps(generate_fixtures(args.output), sort_keys=True))
    if not args.output and not args.write_contract_map:
        parser.error("provide --output and/or --write-contract-map")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
