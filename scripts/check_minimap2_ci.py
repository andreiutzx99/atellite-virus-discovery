"""Exercise minimap2 on artificial read-screening and read-back fixtures."""
import json
from pathlib import Path
import random
import sys

from satellite_discovery import bounded_process, read_support, residual_reads
from satellite_discovery.dependency_review import inspect_executable
from satellite_discovery.sequence_downloader import checksum, write_json


def _sequence(rng, length):
    return "".join(rng.choice("ACGT") for _ in range(length))


def _write_fastq(path, sequences):
    with Path(path).open("w", encoding="ascii", newline="") as output:
        for index, sequence in enumerate(sequences, 1):
            output.write(f"@fixture{index}\n{sequence}\n+\n{'I' * len(sequence)}\n")


def _run(executable, command, directory, stdout, stderr):
    result = bounded_process.run_captured(
        [executable, *command], directory, stdout, stderr,
        timeout=120, max_bytes=200_000_000,
    )
    if result.returncode:
        raise RuntimeError(
            f"minimap2 exited with {result.returncode}; see {directory / stderr}"
        )


def main():
    dependency = inspect_executable("minimap2", "minimap2", ("--version",))
    if not dependency["path"]:
        raise RuntimeError("minimap2 is required for the optional runtime check")

    root = (Path(".tools") / "m6-minimap2-diagnostic").resolve()
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(60126)
    screen_reference = _sequence(rng, 180)
    assembled_sequence = _sequence(rng, 160)
    mutated_read = list(assembled_sequence)
    mutated_read[80] = next(base for base in "ACGT" if base != mutated_read[80])
    reads = [screen_reference, assembled_sequence, "".join(mutated_read)]

    source_reads = root / "synthetic_reads.fastq"
    _write_fastq(source_reads, reads)
    reference = root / "screen_reference.fasta"
    reference.write_text(f">screen_ref\n{screen_reference}\n", encoding="ascii")
    contigs = root / "assembled_contigs.fasta"
    contigs.write_text(f">fixture_contig\n{assembled_sequence}\n", encoding="ascii")

    normalized = residual_reads.prepare_normalized_fastqs(
        source_reads, None, root / "screen_normalized", prefix="screen",
    )
    screen_sam = root / "reference_screen.sam"
    _run(
        dependency["path"],
        ["-a", "-x", "sr", "--secondary=no", "-t", "1", "-o",
         str(screen_sam), str(reference), str(normalized["read1"])],
        root, "screen.stdout.log", "screen.stderr.log",
    )
    triage = residual_reads.screen_and_triage(
        source_reads, None, screen_sam, root / "triage",
        config={
            "min_read_length": 50, "max_ambiguous_fraction": .05,
            "min_entropy_bits": 1.2, "min_mean_phred": 20,
        },
        paired=False, references={"screen_ref": len(screen_reference)},
    )
    if triage["counts"]["input_fragments"] != 3:
        raise AssertionError("Screen fixture did not account for all input fragments")
    if triage["counts"]["residual_fragments"] != 2:
        raise AssertionError("Expected one reference-matched and two residual fragments")

    support_reads = residual_reads.prepare_normalized_fastqs(
        source_reads, None, root / "support_normalized",
        include_fragment_ids=triage["residual_fragment_ids"],
        prefix="support",
    )
    support_sam = root / "support_alignments.sam"
    _run(
        dependency["path"],
        ["-a", "-x", "sr", "--secondary=no", "-t", "1", "-o",
         str(support_sam), str(contigs), str(support_reads["read1"])],
        root, "support.stdout.log", "support.stderr.log",
    )
    support = read_support.assess_read_support(
        support_sam, contigs, triage["read_metadata"],
        paired=False,
        thresholds={
            "min_mapq": 20, "min_alignment_fraction": .8,
            "min_sequence_identity": .95, "min_coverage_breadth": .8,
            "min_mean_depth": 2, "min_distinct_fragments": 2,
        },
    )
    if support["status"] != "READ_SUPPORTED_ASSEMBLY":
        raise AssertionError(f"Artificial read-back did not meet criteria: {support['status']}")
    if len(support["resolved_fragment_ids"]) != 2:
        raise AssertionError("Read-back failed to resolve both artificial residual fragments")

    summary = {
        "schema": "m6-minimap2-runtime-check-v1",
        "fixture_scope": "artificial sequences only; not a biological performance benchmark",
        "tool": {
            "name": dependency["tool"],
            "version": dependency.get("version_output"),
            "binary_sha256": dependency.get("sha256"),
        },
        "screen": {
            "input_fragments": triage["counts"]["input_fragments"],
            "residual_fragments": triage["counts"]["residual_fragments"],
            "reference_ids": ["screen_ref"],
            "sam_sha256": checksum(screen_sam),
        },
        "read_back": {
            "status": support["status"],
            "resolved_fragments": len(support["resolved_fragment_ids"]),
            "contig_status": support["contigs"][0]["status"],
            "sam_sha256": checksum(support_sam),
        },
    }
    write_json(root / "summary.json", summary)
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, RuntimeError, ValueError) as error:
        print(f"minimap2 runtime validation failed: {error}", file=sys.stderr)
        raise