"""Read-back evidence calculations for assembled contigs.

Only alignment evidence is measured here; no sequence is assigned a biological
meaning.  SAM is parsed strictly so incomplete results cannot look supported.
"""
import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path

from .sequence_catalogue import read_fasta

_CIGAR = re.compile(r"(\d+)([MIDNSHP=X])")
_REF = set("MDN=X")
_QUERY = set("MIS=X")
_QUERY_ALIGNED = set("MI=X")
MAX_SAM_BYTES = 200_000_000
MAX_SAM_RECORDS = 4_000_000
MAX_SAM_LINE_BYTES = 1_000_000


def _cigar(value):
    if value == "*" or not value:
        raise ValueError("Missing CIGAR")
    result = [(int(n), op) for n, op in _CIGAR.findall(value)]
    if "".join(f"{n}{op}" for n, op in result) != value or not result:
        raise ValueError("Malformed CIGAR")
    if any(n <= 0 for n, _ in result):
        raise ValueError("Malformed CIGAR length")
    if any(op == "N" for _, op in result):
        raise ValueError("Reference-skip CIGAR operations are not valid contig read-support evidence")
    return result


def _tag(fields, name):
    for tag in fields[11:]:
        if tag.startswith(name + ":"):
            try:
                return int(tag.split(":", 2)[2])
            except ValueError as error:
                raise ValueError("Malformed SAM NM tag") from error
    return None


def _reverse_complement(sequence):
    return sequence.translate(str.maketrans("ACGTN", "TGCAN"))[::-1]


def _validate_query_sequence(fields, flag, metadata):
    sequence = fields[9].upper()
    quality = fields[10]
    if (sequence == "*" or set(sequence) - set("ACGTN")
            or len(sequence) != metadata["query_length"]
            or len(quality) != len(sequence)):
        raise ValueError("SAM query sequence or quality does not match residual-read metadata")
    original_orientation = _reverse_complement(sequence) if flag & 0x10 else sequence
    digest = hashlib.sha256(original_orientation.encode("ascii")).hexdigest()
    if digest != metadata.get("sequence_sha256"):
        raise ValueError("SAM query sequence does not match the original residual read")
    return sequence


def _sweep(intervals, length):
    events = defaultdict(int)
    for start, end in intervals:
        if start < 1 or end <= start or end > length + 1:
            raise ValueError("Alignment interval outside contig")
        events[start] += 1; events[end] -= 1
    points = sorted({1, length + 1} | set(events))
    # Sweep breakpoints rather than allocating one value per reference base.
    depth = 0; covered = 0; weighted = 0; previous = 1
    for point in points:
        if point > previous:
            span = point - previous
            if depth:
                covered += span; weighted += depth * span
        depth += events[point]
        previous = point
    return covered / length, weighted / length


def assess_read_support(sam_path, contigs_path, read_metadata, *, paired, thresholds):
    contigs = {identifier: sequence for identifier, _, sequence in read_fasta(contigs_path)}
    required = set(read_metadata)
    if not required:
        raise ValueError("Read-support validation requires at least one residual read")
    if paired:
        fragment_mates = defaultdict(set)
        for query_id, mate in required:
            if mate not in {1, 2}:
                raise ValueError("Paired read metadata has an invalid mate index")
            fragment_mates[query_id].add(mate)
        if any(mates != {1, 2} for mates in fragment_mates.values()):
            raise ValueError("Paired read-support metadata must contain both mates of every fragment")
    elif any(mate != 0 for _, mate in required):
        raise ValueError("Single-end read metadata has an invalid mate index")
    primary = {}
    alignments = []
    declared_contigs = {}
    if Path(sam_path).stat().st_size > MAX_SAM_BYTES:
        raise ValueError("SAM exceeds the maximum supported byte size")
    consumed = 0
    record_count = 0
    with Path(sam_path).open("r", encoding="ascii", newline="") as source:
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
            tags = {}
            for field in line.rstrip("\r\n").split("\t")[1:]:
                if ":" not in field:
                    raise ValueError("Malformed SAM contig dictionary")
                name, value = field.split(":", 1)
                if name in tags:
                    raise ValueError("Duplicate SAM contig dictionary tag")
                tags[name] = value
            try:
                contig_id, length = tags["SN"], int(tags["LN"])
            except (KeyError, ValueError) as error:
                raise ValueError("Malformed SAM contig dictionary") from error
            if not contig_id or length < 1 or contig_id in declared_contigs:
                raise ValueError("Invalid or duplicate SAM contig declaration")
            declared_contigs[contig_id] = length
            continue
        if not line or line.startswith("@"):
          continue
        f = line.rstrip("\r\n").split("\t")
        if len(f) < 11:
            raise ValueError("Malformed SAM alignment")
        try:
            flag, mapq, pos = int(f[1]), int(f[4]), int(f[3])
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
        key = (f[0], mate)
        if flag & (0x100 | 0x800):
            continue
        if key not in required:
            raise ValueError("Unknown primary support query")
        if key in primary:
            raise ValueError("Duplicate primary support query")
        primary[key] = (f, flag, mapq, pos)
        record_count += 1
        if record_count > MAX_SAM_RECORDS:
            raise ValueError("SAM exceeds the maximum supported record count")
    if set(primary) != required:
        raise ValueError("Missing primary support query accounting")
    if declared_contigs != {name: len(sequence) for name, sequence in contigs.items()}:
        raise ValueError("SAM contig dictionary does not match the assembled sequences")
    by_contig = defaultdict(list)
    support_reads = []
    min_mapq = thresholds.get("min_mapq", 20)
    min_fraction = thresholds.get("min_alignment_fraction", .8)
    min_identity = thresholds.get("min_sequence_identity", .95)
    min_mean_phred = thresholds.get("min_mean_phred", 20)
    max_ambiguous_fraction = thresholds.get("max_ambiguous_fraction", .05)
    for key, (f, flag, mapq, pos) in primary.items():
        query_sequence = _validate_query_sequence(f, flag, read_metadata[key])
        if flag & 4:
            if f[2] != "*" or pos != 0 or f[5] != "*":
                raise ValueError("Unmapped SAM record has inconsistent fields")
            support_reads.append({"query_id": key[0], "mate": key[1], "mapped": False, "qualifying": False})
            continue
        if f[2] not in contigs or pos < 1:
            raise ValueError("Unknown contig or invalid SAM position")
        ops = _cigar(f[5]); qlen = read_metadata[key]["query_length"]
        query_consumed = sum(n for n, op in ops if op in _QUERY)
        if len(query_sequence) != query_consumed or len(f[10]) != query_consumed or query_consumed != qlen:
            raise ValueError("SAM SEQ/QUAL length does not match CIGAR")
        query_aligned = sum(n for n, op in ops if op in _QUERY_ALIGNED)
        ref_aligned = sum(n for n, op in ops if op in {"M", "=", "X"})
        nm = _tag(f, "NM")
        if nm is None or nm < 0:
            raise ValueError("Mapped support alignment requires valid NM")
        reference_span = sum(n for n, op in ops if op in _REF)
        if pos + reference_span - 1 > len(contigs[f[2]]):
            raise ValueError("Alignment extends beyond contig bounds")
        denominator = max(query_aligned, reference_span)
        if not denominator or nm > denominator:
            raise ValueError("Mapped support alignment has invalid NM")
        query_cursor, reference_cursor, actual_nm = 0, pos - 1, 0
        reference = contigs[f[2]].upper()
        for length, operation in ops:
            if operation in {"M", "=", "X"}:
                read_segment = query_sequence[query_cursor:query_cursor + length]
                reference_segment = reference[reference_cursor:reference_cursor + length]
                if len(read_segment) != length or len(reference_segment) != length:
                    raise ValueError("CIGAR alignment exceeds query or contig sequence")
                mismatches = sum(a != b for a, b in zip(read_segment, reference_segment))
                if ((operation == "=" and mismatches != 0)
                        or (operation == "X" and mismatches != length)):
                    raise ValueError("CIGAR equality/mismatch operation contradicts the sequences")
                actual_nm += mismatches
                query_cursor += length
                reference_cursor += length
            elif operation == "I":
                actual_nm += length
                query_cursor += length
            elif operation == "D":
                actual_nm += length
                reference_cursor += length
            elif operation == "S":
                query_cursor += length
        if query_cursor != len(query_sequence) or actual_nm != nm:
            raise ValueError("SAM NM tag or CIGAR does not match the aligned sequences")
        identity = max(0, 1 - actual_nm / denominator)
        intervals = []; cursor = pos
        for n, op in ops:
            if op in _REF:
                if op != "D":
                    intervals.append((cursor, cursor + n))
                cursor += n
        breadth, mean_depth = _sweep(intervals, len(contigs[f[2]]))
        # SAM MAPQ 255 means unavailable, not maximal confidence.
        quality_eligible = (
            read_metadata[key].get("mean_phred", min_mean_phred) >= min_mean_phred
            and read_metadata[key].get("ambiguous_fraction", 0) <= max_ambiguous_fraction
        )
        qualifying = (quality_eligible and mapq != 255 and mapq >= min_mapq
                      and query_aligned / qlen >= min_fraction and identity >= min_identity)
        rec = {"query_id": key[0], "mate": key[1], "contig_id": f[2], "mapped": True,
               "mapq": mapq, "query_aligned_bases": query_aligned, "reference_aligned_bases": ref_aligned,
               "aligned_query_fraction": query_aligned / qlen, "sequence_identity": identity,
               "quality_eligible": quality_eligible, "qualifying": qualifying,
               "intervals": [(a, b - 1) for a, b in intervals]}
        support_reads.append(rec)
        if qualifying:
            by_contig[f[2]].append((key, rec))
    min_breadth = thresholds.get("min_coverage_breadth", .8)
    min_depth = thresholds.get("min_mean_depth", 2)
    min_fragments = thresholds.get("min_distinct_fragments", 2)
    fragment_contigs = defaultdict(set)
    for entries in by_contig.values():
        for key, rec in entries:
            fragment_contigs[key[0]].add(rec["contig_id"])
    ambiguous_fragments = {
        fragment_id for fragment_id, contig_ids in fragment_contigs.items()
        if len(contig_ids) > 1
    }
    records = []
    supported_contigs = set()
    for cid, sequence in contigs.items():
        entries = by_contig[cid]
        intervals = [x for _, rec in entries for x in rec["intervals"]]
        breadth, depth = _sweep([(a, b + 1) for a, b in intervals], len(sequence)) if intervals else (0, 0)
        hashes = {read_metadata[key]["sequence_sha256"] for key, _ in entries}
        fragments = {key[0] for key, _ in entries}
        if any(key[0] in ambiguous_fragments for key, _ in entries):
            status = "AMBIGUOUS_ASSEMBLY"
        elif (len(hashes) >= 2 and len(fragments) >= min_fragments
              and breadth >= min_breadth and depth >= min_depth):
            status = "READ_SUPPORTED_ASSEMBLY"; supported_contigs.add(cid)
        elif entries:
            status = "LOW_SUPPORT_ASSEMBLY"
        else:
            status = "UNSUPPORTED_ASSEMBLY"
        window_size = max(1, int(thresholds.get("coverage_window_size", 100)))
        windows = []
        for start in range(1, len(sequence) + 1, window_size):
            end = min(len(sequence), start + window_size - 1)
            window_intervals = []
            for alignment_start, alignment_end in intervals:
                clipped_start = max(start, alignment_start)
                clipped_end = min(end + 1, alignment_end + 1)
                if clipped_start < clipped_end:
                    window_intervals.append((
                        clipped_start - start + 1,
                        clipped_end - start + 1,
                    ))
            covered, window_depth = _sweep(
                window_intervals, end - start + 1,
            ) if window_intervals else (0, 0)
            windows.append({"start": start, "end": end, "breadth": covered, "mean_depth": window_depth})
        records.append({"contig_id": cid, "contig_length": len(sequence),
                        "supporting_read_count": len(entries), "distinct_sequence_count": len(hashes),
                        "distinct_fragment_count": len(fragments),
                        "coverage_breadth": breadth, "mean_depth": depth, "coverage_windows": windows,
                        "weak_or_no_support_windows": [w for w in windows if w["breadth"] < min_breadth],
                        "status": status})
    resolved = []
    for qname in {k[0] for k in required}:
        mates = [k for k in required if k[0] == qname]
        qualifying_contigs = {
            rec.get("contig_id") for rec in support_reads
            if rec.get("query_id") == qname and rec.get("qualifying")
        }
        for contig in qualifying_contigs & supported_contigs:
            if all(any(rec.get("query_id") == qname and rec.get("mate") == k[1]
                       and rec.get("qualifying") and rec.get("contig_id") == contig
                       for rec in support_reads) for k in mates):
                resolved.append(qname)
                break
    aggregate = "READ_SUPPORTED_ASSEMBLY" if supported_contigs else "NO_SUPPORTED_ASSEMBLY"
    return {"contigs": records, "read_support": support_reads,
            "resolved_fragment_ids": sorted(resolved), "status": aggregate}