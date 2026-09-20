"""Portable streaming QC for archive-generated Illumina FASTQ.

This is an explicit baseline, not fastp or a biologically validated filter.
All rejected reads and surviving unpaired mates are retained for auditing.
"""
import gzip
import json
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from itertools import zip_longest
from pathlib import Path

from . import __version__
from .sequence_downloader import checksum, write_json


@dataclass(frozen=True)
class QCConfig:
    min_length: int = 30
    end_quality: int = 20
    min_mean_quality: float = 20.0
    max_n_fraction: float = 0.05
    adapters: tuple = ("AGATCGGAAGAGC",)
    min_adapter_overlap: int = 12

    def validate(self):
        if not 1 <= self.min_length <= 10000 or not 0 <= self.end_quality <= 93:
            raise ValueError("Invalid minimum read length or Phred end threshold")
        if not 0 <= self.min_mean_quality <= 93 or not 0 <= self.max_n_fraction <= 1:
            raise ValueError("Invalid mean-quality or N-fraction threshold")
        if self.min_adapter_overlap < 8:
            raise ValueError("Adapter overlap must be at least 8 bases")
        if any(len(a) < self.min_adapter_overlap or set(a) - set("ACGT") for a in self.adapters):
            raise ValueError("Adapters must contain A/C/G/T and meet the overlap length")


def records(path):
    """Reject malformed records, unequal lengths, non-ACGTN and invalid Phred+33."""
    with gzip.open(path, "rt", encoding="ascii", newline="") as handle:
        index = 0
        while True:
            header = handle.readline()
            if not header:
                return
            sequence, plus, quality = (handle.readline() for _ in range(3))
            index += 1
            header, sequence, plus, quality = (s.rstrip("\r\n") for s in (header, sequence, plus, quality))
            if not header.startswith("@") or len(header) < 2 or not plus.startswith("+"):
                raise ValueError(f"Malformed FASTQ record {index} in {Path(path).name}")
            sequence = sequence.upper()
            if not sequence or len(sequence) != len(quality) or len(sequence) > 10000:
                raise ValueError(f"Invalid FASTQ lengths at record {index} in {Path(path).name}")
            if set(sequence) - set("ACGTN") or any(not 33 <= ord(q) <= 126 for q in quality):
                raise ValueError(f"Unsupported base or Phred+33 encoding at record {index}")
            if plus[1:] and plus[1:].split()[0] != header[1:].split()[0]:
                raise ValueError(f"FASTQ separator identifier mismatch at record {index}")
            yield header, sequence, quality


def pair_id(header):
    token = header.split()[0]
    return token[:-2] if token.endswith(("/1", "/2")) else token


def check_mate(header, role):
    pieces = header.split()
    token = pieces[0]
    if token.endswith(("/1", "/2")) and not token.endswith("/" + role):
        raise ValueError("FASTQ mate is in the wrong R1/R2 file")
    if len(pieces) > 1 and pieces[1].startswith(("1:", "2:")) and not pieces[1].startswith(role + ":"):
        raise ValueError("CASAVA mate is in the wrong R1/R2 file")


class Metrics:
    def __init__(self):
        self.reads = self.bases = self.q20 = self.q30 = self.qsum = 0
        self.composition = Counter()
        self.lengths = Counter()

    def add(self, record):
        _, sequence, quality = record
        scores = [ord(q) - 33 for q in quality]
        self.reads += 1
        self.bases += len(sequence)
        self.qsum += sum(scores)
        self.q20 += sum(q >= 20 for q in scores)
        self.q30 += sum(q >= 30 for q in scores)
        self.composition.update(sequence)
        self.lengths[len(sequence)] += 1

    def export(self):
        return {"reads": self.reads, "bases": self.bases,
                "mean_phred": self.qsum / self.bases if self.bases else None,
                "q20_fraction": self.q20 / self.bases if self.bases else None,
                "q30_fraction": self.q30 / self.bases if self.bases else None,
                "gc_fraction_all_bases": (self.composition['G'] + self.composition['C']) / self.bases if self.bases else None,
                "base_counts": dict(self.composition), "length_histogram": dict(self.lengths)}


def trim(record, config):
    header, seq, qual = record
    stop = len(seq)
    adapter_hit = False
    for adapter in config.adapters:
        position = seq.find(adapter)
        if position >= 0 and position < stop:
            stop, adapter_hit = position, True
        for overlap in range(min(len(adapter) - 1, len(seq)), config.min_adapter_overlap - 1, -1):
            if seq.endswith(adapter[:overlap]) and len(seq) - overlap < stop:
                stop, adapter_hit = len(seq) - overlap, True
                break
    start = 0
    while start < stop and ord(qual[start]) - 33 < config.end_quality:
        start += 1
    while stop > start and ord(qual[stop - 1]) - 33 < config.end_quality:
        stop -= 1
    seq, qual = seq[start:stop], qual[start:stop]
    reason = None
    if len(seq) < config.min_length:
        reason = "too_short_after_trimming"
    elif seq.count("N") / len(seq) > config.max_n_fraction:
        reason = "too_many_N_bases"
    elif sum(ord(q) - 33 for q in qual) / len(qual) < config.min_mean_quality:
        reason = "low_mean_quality"
    return (header, seq, qual), reason, adapter_hit


def run_qc(inputs, directory, config=None, progress=print):
    config = config or QCConfig()
    config.validate()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if not inputs or set(inputs) - {"R1", "R2", "single"} or (("R1" in inputs) != ("R2" in inputs)):
        raise ValueError("QC requires single reads or a complete R1/R2 pair")
    fingerprint = {"software_version": __version__, "config": json.loads(json.dumps(asdict(config))),
                   "inputs": {role: {"sha256": checksum(path), "bytes": Path(path).stat().st_size}
                              for role, path in sorted(inputs.items())}}
    report_path = directory / "qc.json"
    if report_path.exists():
        previous = json.loads(report_path.read_text())
        if previous["fingerprint"] != fingerprint:
            raise ValueError("QC inputs or parameters changed: choose a new output directory")
        if all((directory / name).exists() and checksum(directory / name) == digest for name, digest in previous["output_sha256"].items()):
            progress("Reusing verified QC results")
            return previous
        raise ValueError("Existing QC output failed integrity check")
    before, after = Metrics(), Metrics()
    reasons, counts = Counter(), Counter()
    names = ["clean_single.fastq.gz", "rejected.fastq.gz"]
    if "R1" in inputs:
        names += ["clean_R1.fastq.gz", "clean_R2.fastq.gz", "orphan_R1.fastq.gz", "orphan_R2.fastq.gz"]
    with ExitStack() as stack:
        handles = {}
        for name in names:
            raw = stack.enter_context((directory / (name + ".part")).open("wb"))
            handles[name] = stack.enter_context(gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0))

        def emit(name, record):
            h, s, q = record
            handles[name].write(f"{h}\n{s}\n+\n{q}\n".encode("ascii"))

        def process(record):
            before.add(record)
            result, reason, hit = trim(record, config)
            counts["reads_with_adapter_match"] += int(hit)
            counts["bases_trimmed"] += len(record[1]) - len(result[1])
            if reason:
                reasons[reason] += 1
                emit("rejected.fastq.gz", record)  # Original record retained.
                counts["rejected_reads"] += 1
            else:
                after.add(result)
                counts["retained_reads"] += 1
            if before.reads % 100000 == 0:
                progress(f"QC: {before.reads:,} reads processed")
            return result, reason

        if "R1" in inputs:
            for a, b in zip_longest(records(inputs["R1"]), records(inputs["R2"])):
                if a is None or b is None:
                    raise ValueError("Paired FASTQ files contain different record counts")
                if pair_id(a[0]) != pair_id(b[0]):
                    raise ValueError("Paired FASTQ identifiers do not match")
                check_mate(a[0], "1")
                check_mate(b[0], "2")
                a_out, a_bad = process(a)
                b_out, b_bad = process(b)
                if not a_bad and not b_bad:
                    emit("clean_R1.fastq.gz", a_out)
                    emit("clean_R2.fastq.gz", b_out)
                    counts["retained_pairs"] += 1
                else:
                    for role, result, bad in (("R1", a_out, a_bad), ("R2", b_out, b_bad)):
                        if not bad:
                            emit("orphan_" + role + ".fastq.gz", result)
                            counts["retained_orphans"] += 1
        if "single" in inputs:
            for record in records(inputs["single"]):
                result, bad = process(record)
                if not bad:
                    emit("clean_single.fastq.gz", result)
                    counts["retained_single_reads"] += 1
    if before.reads == 0:
        raise ValueError("FASTQ inputs contain no reads")
    for name in names:
        (directory / (name + ".part")).replace(directory / name)
    result = {"status": "complete", "engine": "portable_baseline_phred33", "fingerprint": fingerprint,
              "before": before.export(), "after": after.export(), "counts": dict(counts),
              "rejection_reasons": dict(reasons), "output_sha256": {name: checksum(directory / name) for name in names},
              "limitations": ["Exact adapter/prefix matching only; no mismatch-tolerant or overlap-based detection",
                              "No host/helper mapping, contamination classification or biological validation",
                              "No deduplication or low-complexity removal; original reads preserved"],
              "warnings": ["No reads survived QC"] if not after.reads else []}
    write_json(report_path, result)
    return result
