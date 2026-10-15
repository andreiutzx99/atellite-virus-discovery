"""Offline synthetic QC, short-read mapping, coverage, and reporting demonstration.

This entry point generates its own software-only sequences. It has no interface
for archive access or caller-supplied reads, and must not be treated as a
biological analysis workflow.
"""
import argparse
import gzip
import hashlib
import json
import random
import shutil
import subprocess
import time
from pathlib import Path

from . import coverage_review
from .quality_control import run_qc
from .review_stage import report

SCHEMA = "hcov229e-technical-pilot-synthetic-v1"
NOTES = [
    "All reads and references are generated software fixtures, not biological samples.",
    "Mapping to a reference does not establish viral presence in an acquired sample.",
    "No-hit does not establish novelty; this demo performs no candidate discovery.",
    "DVG-compatible patterns and helper dependence are not assessed or inferred.",
    "This synthetic-only command cannot read archive data or accept external FASTQ inputs.",
]


def _sequence(seed, length):
    rng = random.Random(seed)
    return "".join(rng.choice("ACGT") for _ in range(length))


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_fastq(path, reads):
    with Path(path).open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as stream:
            for item in reads:
                name, sequence = item[:2]
                quality = item[2] if len(item) == 3 else "I" * len(sequence)
                if len(quality) != len(sequence):
                    raise ValueError("Synthetic FASTQ sequence and quality lengths differ.")
                stream.write(f"@{name}\n{sequence}\n+\n{quality}\n".encode("ascii"))


def run_synthetic_demo(output_dir, minimap2_executable="minimap2"):
    """Run a tiny synthetic-only end-to-end technical workflow."""
    requested_output = Path(output_dir)
    if requested_output.is_symlink():
        raise ValueError("Output directory must not be a symlink.")
    output = requested_output.resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Use a new or empty output directory; existing results are never overwritten.")
    output.mkdir(parents=True, exist_ok=True)
    binary = shutil.which(minimap2_executable)
    if not binary:
        raise FileNotFoundError("minimap2 is required for the synthetic mapping demonstration.")

    input_dir = output / "synthetic_inputs"
    input_dir.mkdir()
    references = [
        ("synthetic_host_like", "host_like", _sequence(4101, 420)),
        ("synthetic_virus_reference_like", "virus_reference_like", _sequence(4102, 420)),
    ]
    reads = [
        ("synthetic_host_read", references[0][2][61:136]),
        ("synthetic_virus_read", references[1][2][211:286]),
        ("synthetic_unrelated_read", _sequence(9901, 75)),
        ("synthetic_adapter_read", references[0][2][251:299] + "AGATCGGAAGAGC"),
        ("synthetic_low_quality_read", _sequence(9902, 75), "!" * 75),
    ]
    reference_path = input_dir / "synthetic_references.fasta"
    reference_path.write_text(
        "".join(f">{name}\n{sequence}\n" for name, _role, sequence in references),
        encoding="ascii",
    )
    reads_path = input_dir / "synthetic_reads.fastq.gz"
    _write_fastq(reads_path, reads)
    provenance = {
        "schema": "synthetic-reference-provenance-v1",
        "classification": "software_fixture_only",
        "records": [
            {"reference_id": name, "role": role, "length": len(sequence),
             "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
             "source": "deterministically generated synthetic sequence"}
            for name, role, sequence in references
        ],
    }
    (output / "reference_provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )

    started = time.monotonic()
    qc = run_qc({"single": reads_path}, output / "qc", progress=lambda _message: None)
    clean_reads = output / "qc" / "clean_single.fastq.gz"
    version = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, timeout=15, check=True,
    ).stdout.strip()
    command = [
        binary, "-a", "-x", "sr", "--secondary=no", "-t", "1",
        str(reference_path), str(clean_reads),
    ]
    aligned = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if aligned.returncode:
        raise RuntimeError("minimap2 failed on the synthetic fixture: " + aligned.stderr[-2000:])
    sam_bytes = aligned.stdout.encode("utf-8")
    if len(sam_bytes) > 2_000_000 or len(aligned.stderr.encode("utf-8")) > 2_000_000:
        raise ValueError("Synthetic alignment output exceeded its 2 MB limit.")
    sam_path = output / "synthetic_alignment.sam"
    sam_path.write_bytes(sam_bytes)

    records_total = mapped = unmapped = excluded = 0
    mapped_by_reference = {}
    for line in aligned.stdout.splitlines():
        if not line or line.startswith("@"):
            continue
        fields = line.split("\t")
        if len(fields) < 11:
            raise ValueError("minimap2 returned malformed SAM.")
        records_total += 1
        flag = int(fields[1])
        if flag & 4:
            unmapped += 1
        elif flag & (256 | 512 | 1024 | 2048):
            excluded += 1
        else:
            mapped += 1
            mapped_by_reference[fields[2]] = mapped_by_reference.get(fields[2], 0) + 1
    refs, blocks, skipped = coverage_review.read_sam(sam_path)
    coverage = coverage_review.calculate(
        refs, [{"sample_id": "synthetic_fixture"}],
        [dict(block, sample_id="synthetic_fixture") for block in blocks],
    )
    role_by_id = {name: role for name, role, _sequence_value in references}
    mapping_rows = [
        {"reference_id": row["reference_id"], "synthetic_role": role_by_id[row["reference_id"]],
         "mapped_records": mapped_by_reference.get(row["reference_id"], 0),
         "breadth_fraction": next(
             item["breadth_fraction"] for item in coverage
             if item["reference_id"] == row["reference_id"]
         )}
        for row in refs
    ]
    quality_row = {
        "reads_before": qc["before"]["reads"], "reads_after": qc["after"]["reads"],
        "mean_phred_before": qc["before"]["mean_phred"],
        "q30_fraction_before": qc["before"]["q30_fraction"],
        "retained_reads": qc["counts"].get("retained_single_reads", 0),
        "rejected_reads": qc["counts"].get("rejected_reads", 0),
        "reads_with_adapter_match": qc["counts"].get("reads_with_adapter_match", 0),
        "bases_trimmed": qc["counts"].get("bases_trimmed", 0),
        "rejection_reasons": qc["rejection_reasons"],
    }
    elapsed = time.monotonic() - started
    summary = {
        "schema": SCHEMA, "status": "synthetic_fixture_only",
        "public_virus_status": "HELD",
        "sequence_confirmation_status": "NOT_ASSESSED",
        "authorizing": False,
        "input_integrity": {
            "reads": {"sha256": _sha256(reads_path), "bytes": reads_path.stat().st_size},
            "reference_panel": {"sha256": _sha256(reference_path), "bytes": reference_path.stat().st_size},
        },
        "read_quality": quality_row,
        "mapping": {
            "tool": "minimap2", "version": version, "command": command,
            "records_total": records_total, "mapped_primary_records": mapped,
            "unmapped_records": unmapped, "excluded_records": excluded,
            "unmapped_reads_retained_in_sam": True,
            "alignment_file": sam_path.name,
            "skipped_by_sam_parser": skipped, "references": mapping_rows,
        },
        "coverage": coverage,
        "reference_provenance": provenance,
        "resource_use": {
            "elapsed_seconds": round(elapsed, 6), "synthetic_input_bytes":
                reads_path.stat().st_size + reference_path.stat().st_size,
            "alignment_output_bytes": len(sam_bytes), "threads": 1,
        },
        "warnings": NOTES,
        "biological_interpretation": {
            "viral_presence": "not_assessed", "novelty": "not_assessed",
            "dvg_status": "not_assessed", "helper_dependence": "not_assessed",
            "satellite_virus_discovery": "not_claimed",
        },
    }
    report(output, "Synthetic technical pilot demonstration", {
        "quality": [quality_row], "mapping": mapping_rows, "coverage": coverage,
    }, NOTES)
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New output directory for synthetic-only results")
    parser.add_argument("--minimap2", default="minimap2", help="minimap2 executable name or path")
    args = parser.parse_args(argv)
    result = run_synthetic_demo(args.output, args.minimap2)
    print(json.dumps({"status": result["status"], "output": str(Path(args.output).resolve())}, indent=2))


if __name__ == "__main__":
    main()
