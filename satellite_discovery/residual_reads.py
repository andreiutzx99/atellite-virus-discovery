"""Conservative, mapper-neutral residual read preparation and triage.

This module deliberately performs no biological interpretation.  A residual
read is merely one not accounted for by a completed SAM comparison.
"""
import csv
import gzip
import hashlib
import math
import os
import re
from collections import Counter
from itertools import zip_longest
from pathlib import Path

from .assembly_adapters import _read_fastq
from .quality_control import check_mate, pair_id

MAX_READ_COUNT = 1_000_000
MAX_TOTAL_BASES = 200_000_000
MAX_TOTAL_FASTQ_BYTES = 1_000_000_000
MAX_SAM_BYTES = 200_000_000
MAX_SAM_LINE_BYTES = 1_000_000
_SAFE_PREFIX = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_CIGAR = re.compile(r"(?:[1-9][0-9]*[MIDNSHP=X])+")


def _records(path):
    """Yield exact FASTQ records without materializing the input."""
    path = Path(path)
    with gzip.open(path, "rt", encoding="ascii", newline="") if path.name.lower().endswith(".gz") else path.open("r", encoding="ascii", newline="") as h:
        while True:
            raw = [
                h.readline(4099), h.readline(10003),
                h.readline(4099), h.readline(10003),
            ]
            if not raw[0]:
                if any(raw[1:]):
                    raise ValueError("Incomplete FASTQ record")
                break
            if any(x == "" for x in raw):
                raise ValueError("Incomplete FASTQ record")
            if (len(raw[0]) > 4098 or len(raw[1]) > 10002
                    or len(raw[2]) > 4098 or len(raw[3]) > 10002
                    or any(not line.endswith("\n") for line in raw[:3])
                    or any(len(line) in {4099, 10003} for line in raw)):
                raise ValueError("FASTQ record line exceeds the supported line length")
            lines = [x.rstrip("\r\n") for x in raw]
            header, sequence, plus, quality = lines
            if not header.startswith("@") or len(header) < 2 or not plus.startswith("+"):
                raise ValueError("Malformed FASTQ record")
            if not sequence or len(sequence) != len(quality) or len(sequence) > 10000:
                raise ValueError("Invalid FASTQ sequence/quality lengths")
            if set(sequence.upper()) - set("ACGTN") or any(not 33 <= ord(c) <= 126 for c in quality):
                raise ValueError("Unsupported FASTQ base or quality encoding")
            if plus[1:] and plus[1:].split()[0] != header[1:].split()[0]:
                raise ValueError("FASTQ separator identifier mismatch")
            yield (header, sequence, plus, quality, "".join(raw))


def _gzip_write(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", filename="", mtime=0) as out:
            for row in rows:
                out.write(row.encode("ascii"))


def _source(read1, read2, paired, *, count_state=None):
    first = _records(read1)
    second = _records(read2) if paired else None
    seen = 0
    pairs = zip_longest(first, second, fillvalue=None) if paired else ((row, None) for row in first)
    for left, right in pairs:
        if left is None or (paired and right is None):
            raise ValueError("Paired FASTQ files contain different record counts")
        seen += 1
        if seen > MAX_READ_COUNT:
            raise ValueError("FASTQ exceeds the maximum supported read count")
        if count_state is not None:
            count_state["reads"] += 2 if paired else 1
            count_state["bases"] += len(left[1]) + (len(right[1]) if right else 0)
            left_bytes = left[4].encode("ascii")
            right_bytes = right[4].encode("ascii") if right else b""
            count_state["bytes"] += len(left_bytes) + len(right_bytes)
            if "hashers" in count_state:
                count_state["hashers"]["read1"].update(left_bytes)
                if right:
                    count_state["hashers"]["read2"].update(right_bytes)
            if (count_state["reads"] > MAX_READ_COUNT * (2 if paired else 1)
                    or count_state["bases"] > MAX_TOTAL_BASES
                    or count_state["bytes"] > MAX_TOTAL_FASTQ_BYTES):
                raise ValueError("FASTQ input exceeds the supported resource limits")
        if paired:
            check_mate(left[0], "1")
            check_mate(right[0], "2")
            if pair_id(left[0]) != pair_id(right[0]):
                raise ValueError("Paired FASTQ record identifiers do not match")
        yield left, right


def _qname(ordinal):
    return f"m6r{ordinal:012d}"


def _sequence_digest(sequence, flag=0):
    value = sequence.upper()
    if flag & 0x10:
        value = value.translate(str.maketrans("ACGTN", "TGCAN"))[::-1]
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def prepare_normalized_fastqs(read1, read2, output_dir, *, include_fragment_ids=None, prefix="screen"):
    if not isinstance(prefix, str) or not _SAFE_PREFIX.fullmatch(prefix) or prefix in {".", ".."}:
        raise ValueError("prefix must be a conservative portable basename")
    paired = read2 is not None
    count_state = {"reads": 0, "bases": 0, "bytes": 0}
    source = _source(read1, read2, paired, count_state=count_state)
    wanted = set(include_fragment_ids) if include_fragment_ids is not None else None
    out = Path(output_dir)
    p1 = out / f"{prefix}_R1.fastq.gz"
    p2 = out / f"{prefix}_R2.fastq.gz" if paired else None
    count = 0
    out.mkdir(parents=True, exist_ok=True)
    with p1.open("wb") as b1, (p2.open("wb") if p2 else open(os.devnull, "wb")) as b2:
        with gzip.GzipFile(fileobj=b1, mode="wb", filename="", mtime=0) as z1:
            z2 = gzip.GzipFile(fileobj=b2, mode="wb", filename="", mtime=0) if p2 else None
            try:
                for ordinal, (left, right) in enumerate(source, 1):
                    if wanted is not None and not (
                        _qname(ordinal) in wanted or str(ordinal) in wanted or pair_id(left[0]) in wanted
                    ):
                        continue
                    name = _qname(ordinal)
                    z1.write(f"@{name}\n{left[1]}\n+\n{left[3]}\n".encode("ascii"))
                    if z2:
                        z2.write(f"@{name}\n{right[1]}\n+\n{right[3]}\n".encode("ascii"))
                    count += 1
            finally:
                if z2:
                    z2.close()
    return {"read1": p1, "read2": p2, "fragment_count": count}


def _sam(path, *, paired, expected, references=None):
    if Path(path).stat().st_size > MAX_SAM_BYTES:
        raise ValueError("SAM exceeds the maximum supported byte size")
    seen = set()
    primary = {}
    declared_references = {}
    consumed = 0
    with Path(path).open("r", encoding="ascii", newline="") as source:
      while True:
        line = source.readline(MAX_SAM_LINE_BYTES + 1)
        if not line:
          break
        if len(line.encode("ascii")) > MAX_SAM_LINE_BYTES:
          raise ValueError("SAM record exceeds the maximum supported line size")
        consumed += len(line.encode("ascii"))
        if consumed > MAX_SAM_BYTES:
            raise ValueError("SAM exceeds the maximum supported byte size")
        if line.startswith("@SQ\t"):
            fields = line.rstrip("\r\n").split("\t")
            tags = {}
            for field in fields[1:]:
                if ":" not in field:
                    raise ValueError("Malformed SAM sequence dictionary")
                key, value = field.split(":", 1)
                if key in tags:
                    raise ValueError("Duplicate SAM sequence dictionary tag")
                tags[key] = value
            try:
                name, length = tags["SN"], int(tags["LN"])
            except (KeyError, ValueError) as error:
                raise ValueError("Malformed SAM sequence dictionary") from error
            if not name or length < 1 or name in declared_references:
                raise ValueError("Invalid or duplicate SAM reference declaration")
            declared_references[name] = length
            continue
        if not line or line.startswith("@"):
          continue
        fields = line.split("\t")
        if len(fields) < 11:
            raise ValueError("Malformed SAM alignment")
        try:
            flag, mapq, pos = int(fields[1]), int(fields[4]), int(fields[3])
        except ValueError as error:
            raise ValueError("Malformed SAM numeric field") from error
        if not 0 <= flag <= 65535 or not 0 <= mapq <= 255:
            raise ValueError("SAM MAPQ is outside 0..255")
        mate = 2 if flag & 0x80 else (1 if paired else 0)
        if paired:
            if not flag & 0x1 or bool(flag & 0x40) == bool(flag & 0x80):
                raise ValueError("Paired SAM record has invalid mate flags")
        elif flag & (0x1 | 0x40 | 0x80):
            raise ValueError("Single-end SAM record claims paired layout")
        mapped = not bool(flag & 4)
        if mapped:
            if fields[2] == "*" or pos < 1 or not _CIGAR.fullmatch(fields[5]):
                raise ValueError("Mapped SAM record has invalid reference fields")
            if references is not None:
                if fields[2] not in references:
                    raise ValueError("Mapped SAM record is outside the declared reference collection")
                operations = [(int(n), op) for n, op in
                              re.findall(r"([1-9][0-9]*)([MIDNSHP=X])", fields[5])]
                if "".join(f"{n}{op}" for n, op in operations) != fields[5]:
                    raise ValueError("Mapped SAM record has malformed CIGAR")
                reference_span = sum(n for n, op in operations if op in "MDN=X")
                if pos + reference_span - 1 > references[fields[2]]:
                    raise ValueError("Mapped SAM record extends beyond the declared reference")
        elif fields[2] != "*" or pos != 0 or fields[5] != "*":
            raise ValueError("Unmapped SAM record has inconsistent fields")
        key = (fields[0], mate)
        if key not in expected:
            raise ValueError("Unknown primary SAM query")
        if not (flag & (0x100 | 0x800)):
            if key in seen:
                raise ValueError("Duplicate primary SAM query")
            seen.add(key)
        if not (flag & (0x100 | 0x800)):
            primary[key] = flag
        if fields[9] == "*" or _sequence_digest(fields[9], flag) != expected[key]:
            raise ValueError("SAM sequence does not match the declared input read")
        if len(primary) > MAX_READ_COUNT * (2 if paired else 1):
            raise ValueError("SAM exceeds the maximum supported record count")
    if set(primary) != set(expected):
        raise ValueError("Missing primary SAM query accounting")
    if references is not None and declared_references != references:
        raise ValueError("SAM sequence dictionary does not match the declared reference collection")
    return primary


def _metrics(sequence, quality, duplicates):
    seq = sequence.upper()
    counts = Counter(seq)
    entropy = -sum((n / len(seq)) * math.log2(n / len(seq)) for n in counts.values())
    return {
        "query_length": len(seq), "ambiguous_fraction": seq.count("N") / len(seq),
        "entropy_bits": entropy, "mean_phred": sum(ord(c) - 33 for c in quality) / len(quality),
        "sequence_sha256": hashlib.sha256(seq.encode("ascii")).hexdigest(),
        "exact_duplicate_count": duplicates[seq],
    }


def screen_and_triage(read1, read2, screen_sam, output_dir, *, config, paired,
                      references=None):
    state = {
        "reads": 0, "bases": 0, "bytes": 0,
        "hashers": {"read1": hashlib.sha256(), "read2": hashlib.sha256()},
    }
    duplicate_counts = Counter()
    sequence_hashes = {}
    fragments = 0
    for left, right in _source(read1, read2, paired, count_state=state):
        fragments += 1
        duplicate_counts[left[1].upper()] += 1
        sequence_hashes[(_qname(fragments), 1 if paired else 0)] = _sequence_digest(left[1])
        if right:
            duplicate_counts[right[1].upper()] += 1
            sequence_hashes[(_qname(fragments), 2)] = _sequence_digest(right[1])
    first_state = {
        "reads": state["reads"], "bases": state["bases"], "bytes": state["bytes"],
        "hashes": {name: digest.hexdigest() for name, digest in state["hashers"].items()
                   if name == "read1" or paired},
    }
    expected = {}
    for i in range(1, fragments + 1):
        expected[(_qname(i), 1 if paired else 0)] = sequence_hashes[(_qname(i), 1 if paired else 0)]
        if paired:
            expected[(_qname(i), 2)] = sequence_hashes[(_qname(i), 2)]
    primary = _sam(screen_sam, paired=paired, expected=expected,
                   references=references)
    thresholds = {
        "min_read_length": config["min_read_length"],
        "max_ambiguous_fraction": config["max_ambiguous_fraction"],
        "min_entropy_bits": config["min_entropy_bits"],
        "min_mean_phred": config["min_mean_phred"],
    }
    residual_ids, eligible_ids, retained_ids = [], [], []
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    metadata = {}
    from contextlib import ExitStack
    temp_names = []
    try:
        with ExitStack() as stack:
            streams = {}
            for stem in ("residual_read", "eligible_read", "retained_unassembled_read"):
                for mate in ("1", "2") if paired else ("1",):
                    final_name = f"{stem}{mate}.fastq.gz"
                    temp_name = final_name + ".part"
                    temp_names.append(temp_name)
                    raw = stack.enter_context((out / temp_name).open("wb"))
                    streams[(stem, mate)] = stack.enter_context(
                        gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0))
            triage_temp = "read_triage.csv.part"
            temp_names.append(triage_temp)
            csvfile = stack.enter_context((out / triage_temp).open("w", newline="", encoding="utf-8"))
            writer = csv.writer(csvfile)
            writer.writerow(["query_id", "mate", "outcome", "residual", "length", "ambiguous_fraction",
                             "entropy", "mean_phred", "sequence_hash", "exact_duplicate_count", "reason_codes"])
            second_state = {
                "reads": 0, "bases": 0, "bytes": 0,
                "hashers": {"read1": hashlib.sha256(), "read2": hashlib.sha256()},
            }
            for i, (left, right) in enumerate(_source(read1, read2, paired, count_state=second_state), 1):
                records = [(1, left)] + ([(2, right)] if paired else [])
                metrics, reason_map = {}, {}
                for mate, record in records:
                    key = (_qname(i), mate if paired else 0)
                    metric = _metrics(record[1], record[3], duplicate_counts)
                    metric.update(query_id=key[0], original_header=record[0], fragment_id=key[0],
                                  mate=key[1], mate_index=key[1], mapped=not bool(primary[key] & 4))
                    reasons = []
                    if metric["query_length"] < thresholds["min_read_length"]: reasons.append("LOW_READ_LENGTH")
                    if metric["ambiguous_fraction"] > thresholds["max_ambiguous_fraction"]: reasons.append("HIGH_AMBIGUOUS_BASE_FRACTION")
                    if metric["entropy_bits"] < thresholds["min_entropy_bits"]: reasons.append("LOW_SEQUENCE_COMPLEXITY")
                    if metric["mean_phred"] < thresholds["min_mean_phred"]: reasons.append("LOW_MEAN_PHRED")
                    metrics[key] = metric; reason_map[key] = reasons
                keys = list(metrics)
                reasons = sorted({r for values in reason_map.values() for r in values})
                mapped = any(metrics[k]["mapped"] for k in keys)
                if mapped:
                    outcome, stem, include = "TECHNICAL_FILTERED", None, False
                    reasons.append("REFERENCE_COMPARISON_MATCH")
                elif reasons:
                    outcome, stem, include = "RETAINED_UNASSEMBLED", "retained_unassembled_read", True
                else:
                    outcome, stem, include = "ELIGIBLE_FOR_ASSEMBLY", "eligible_read", True
                q = _qname(i)
                if include:
                    for key, metric in metrics.items():
                        metadata[key] = metric
                    residual_ids.append(q)
                    (eligible_ids if stem == "eligible_read" else retained_ids).append(q)
                    for mate, record in records:
                        streams[(stem, str(mate))].write(record[4].encode("ascii"))
                        streams[("residual_read", str(mate))].write(record[4].encode("ascii"))
                for key in keys:
                    m = metrics[key]
                    writer.writerow([q, key[1], outcome, include, m["query_length"],
                                     m["ambiguous_fraction"], m["entropy_bits"], m["mean_phred"],
                                     m["sequence_sha256"], m["exact_duplicate_count"], ";".join(reasons)])
        second_hashes = {name: digest.hexdigest() for name, digest in second_state["hashers"].items()
                         if name == "read1" or paired}
        if (second_state["reads"] != first_state["reads"]
                or second_state["bases"] != first_state["bases"]
                or second_state["bytes"] != first_state["bytes"]
                or second_hashes != first_state["hashes"]):
            raise ValueError("FASTQ inputs changed during residual triage")
        for temp_name in temp_names:
            Path(out / temp_name).replace(out / temp_name.removesuffix(".part"))
        temp_names.clear()
    finally:
        for temp_name in temp_names:
            (out / temp_name).unlink(missing_ok=True)
    return {"counts": {"input_fragments": fragments, "residual_fragments": len(residual_ids),
                       "eligible_fragments": len(eligible_ids), "retained_unassembled_fragments": len(retained_ids)},
            "residual_fragment_ids": residual_ids, "eligible_fragment_ids": eligible_ids,
            "retained_unassembled_fragment_ids": retained_ids, "read_metadata": metadata}