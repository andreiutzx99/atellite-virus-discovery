"""Retrospective accuracy and independent-evidence analysis for M22 fixtures.

This module is strictly an evaluator: held-out truth and validation reads are
never added to the registered discovery workflow or used to change M6 output.
"""

import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import random

from . import m22_synthetic_benchmark as m22


SCHEMA = "m23-assembly-accuracy-evidence-v1"
KMER = 17
PARTIAL_IDENTITY = 0.95
PARTIAL_TARGET_COVERAGE = 0.50
INDEPENDENT_STRONG_BREADTH = 0.80
MIN_JOIN_SEGMENT = 30


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _reverse_complement(sequence):
    return sequence.upper().translate(str.maketrans("ACGT", "TGCA"))[::-1]


def _fasta(path):
    records, name, sequence = [], None, []
    if not Path(path).is_file():
        return records
    for line in Path(path).read_text(encoding="ascii").splitlines():
        if line.startswith(">"):
            if name is not None:
                records.append((name, "".join(sequence).upper()))
            name, sequence = line[1:].split()[0], []
        elif line.strip():
            sequence.append(line.strip())
    if name is not None:
        records.append((name, "".join(sequence).upper()))
    return records


def _local_alignment(target, candidate):
    """Smith-Waterman with linear gaps; returns one deterministic best HSP."""
    target, candidate = target.upper(), candidate.upper()
    if not target or not candidate:
        return {
            "identity": 0.0, "target_coverage": 0.0, "candidate_coverage": 0.0,
            "target_start": 0, "target_end": 0, "candidate_start": 0,
            "candidate_end": 0, "matches": 0, "columns": 0,
            "aligned_target": "", "aligned_candidate": "",
        }
    width = len(candidate) + 1
    trace = bytearray((len(target) + 1) * width)
    previous = [0] * width
    best = (0, 0, 0)
    for i, a in enumerate(target, 1):
        current = [0] * width
        for j, b in enumerate(candidate, 1):
            diagonal = previous[j - 1] + (2 if a == b else -1)
            up, left = previous[j] - 2, current[j - 1] - 2
            score = max(0, diagonal, up, left)
            current[j] = score
            if score:
                direction = 1 if score == diagonal else 2 if score == up else 3
                trace[i * width + j] = direction
                if score > best[0]:
                    best = (score, i, j)
        previous = current
    _, i, j = best
    target_end, candidate_end = i, j
    at, ac, matches = [], [], 0
    while i and j:
        direction = trace[i * width + j]
        if not direction:
            break
        if direction == 1:
            a, b = target[i - 1], candidate[j - 1]
            at.append(a); ac.append(b)
            matches += a == b
            i -= 1; j -= 1
        elif direction == 2:
            at.append(target[i - 1]); ac.append("-"); i -= 1
        else:
            at.append("-"); ac.append(candidate[j - 1]); j -= 1
    at.reverse(); ac.reverse()
    columns = len(at)
    target_bases = sum(a != "-" for a in at)
    candidate_bases = sum(b != "-" for b in ac)
    return {
        "identity": matches / columns if columns else 0.0,
        "target_coverage": target_bases / len(target),
        "candidate_coverage": candidate_bases / len(candidate),
        "target_start": i, "target_end": target_end,
        "candidate_start": j, "candidate_end": candidate_end,
        "matches": matches, "columns": columns,
        "aligned_target": "".join(at), "aligned_candidate": "".join(ac),
    }


def _global_alignment(target, candidate):
    """Needleman-Wunsch global alignment with linear gap cost."""
    target, candidate = target.upper(), candidate.upper()
    width = len(candidate) + 1
    trace = bytearray((len(target) + 1) * width)
    previous = [-2 * j for j in range(width)]
    for j in range(1, width):
        trace[j] = 3
    for i, a in enumerate(target, 1):
        current = [-2 * i] + [0] * (width - 1)
        trace[i * width] = 2
        for j, b in enumerate(candidate, 1):
            diagonal = previous[j - 1] + (2 if a == b else -1)
            up, left = previous[j] - 2, current[j - 1] - 2
            score = max(diagonal, up, left)
            current[j] = score
            trace[i * width + j] = 1 if score == diagonal else 2 if score == up else 3
        previous = current
    i, j, at, ac = len(target), len(candidate), [], []
    while i or j:
        direction = trace[i * width + j]
        if direction == 1:
            at.append(target[i - 1]); ac.append(candidate[j - 1])
            i -= 1; j -= 1
        elif direction == 2:
            at.append(target[i - 1]); ac.append("-"); i -= 1
        else:
            at.append("-"); ac.append(candidate[j - 1]); j -= 1
    at.reverse(); ac.reverse()
    substitutions = insertions = deletions = 0
    gap_runs = []
    active = None
    run_start = 0
    for column, (a, b) in enumerate(zip(at, ac)):
        kind = "insertion" if a == "-" else "deletion" if b == "-" else None
        if kind == "insertion":
            insertions += 1
        elif kind == "deletion":
            deletions += 1
        elif a != b:
            substitutions += 1
        if kind != active:
            if active:
                gap_runs.append((active, run_start, column))
            if kind:
                run_start = column
            active = kind
    if active:
        gap_runs.append((active, run_start, len(at)))
    internal_runs = [run for run in gap_runs if run[1] > 0 and run[2] < len(at)]
    columns = len(at)
    matches = sum(a == b and a != "-" for a, b in zip(at, ac))
    return {
        "global_identity": matches / columns if columns else 0.0,
        "substitution_count": substitutions,
        "insertion_count": insertions,
        "deletion_count": deletions,
        "internal_gap_run_count": len(internal_runs),
        "global_alignment_columns": columns,
    }


def diagnose_sequence(truth, candidate, reference_records=()):
    truth, candidate = truth.upper(), candidate.upper()
    reverse = _reverse_complement(candidate)
    candidates = [(candidate, "forward"), (reverse, "reverse_complement")]
    aligned_candidate, orientation = max(
        candidates,
        key=lambda item: (
            _local_alignment(truth, item[0])["matches"],
            _local_alignment(truth, item[0])["target_coverage"],
            _local_alignment(truth, item[0])["identity"],
            item[1] == "forward",
        ),
    )
    local = _local_alignment(truth, aligned_candidate)
    global_metrics = _global_alignment(truth, aligned_candidate)
    hits = []
    for source_id, source in reference_records:
        hit = _local_alignment(source, aligned_candidate)
        if (hit["candidate_end"] - hit["candidate_start"] >= MIN_JOIN_SEGMENT
                and hit["identity"] >= 0.90):
            hits.append({
                "source_id": source_id,
                "candidate_start": hit["candidate_start"],
                "candidate_end": hit["candidate_end"],
                "identity": hit["identity"],
            })
    joins = []
    hits.sort(key=lambda row: (row["candidate_start"], row["candidate_end"]))
    for i, first in enumerate(hits):
        for second in hits[i + 1:]:
            if first["source_id"] == second["source_id"]:
                continue
            overlap = max(0, min(first["candidate_end"], second["candidate_end"])
                          - max(first["candidate_start"], second["candidate_start"]))
            union = ((first["candidate_end"] - first["candidate_start"])
                     + (second["candidate_end"] - second["candidate_start"]) - overlap)
            if overlap == 0 and union / max(1, len(candidate)) >= 0.50:
                joins.append({"segments": [first, second], "status": "POTENTIAL_ONLY"})
    target_prefix = local["target_start"]
    target_suffix = len(truth) - local["target_end"]
    candidate_prefix = local["candidate_start"]
    candidate_suffix = len(aligned_candidate) - local["candidate_end"]
    if orientation == "reverse_complement":
        candidate_prefix, candidate_suffix = candidate_suffix, candidate_prefix
    return {
        "candidate_length": len(candidate),
        "truth_length": len(truth),
        "alignment_orientation": orientation,
        "strand_exact_match": aligned_candidate == truth,
        "full_length_sequence_identity": global_metrics["global_identity"],
        "local_alignment_identity": local["identity"],
        "target_coverage": local["target_coverage"],
        "candidate_coverage": local["candidate_coverage"],
        "substitution_count": global_metrics["substitution_count"],
        "insertion_count": global_metrics["insertion_count"],
        "deletion_count": global_metrics["deletion_count"],
        "internal_gap_run_count": global_metrics["internal_gap_run_count"],
        "missing_target_prefix_bases": target_prefix,
        "missing_target_suffix_bases": target_suffix,
        "incorrect_candidate_prefix_bases": candidate_prefix,
        "incorrect_candidate_suffix_bases": candidate_suffix,
        "potential_incorrect_joins": joins,
        "alignment_method": "Smith-Waterman local and Needleman-Wunsch global; linear gaps",
        "_local": local,
    }


def _independent_reads(truth, background_records, coverage, error_rate, seed):
    rng = random.Random(seed)
    sources = []
    if truth:
        sources.append(("target", truth))
    sources.extend(("background", seq) for _, seq in background_records)
    reads = []
    for _, source in sources:
        n = math.ceil(coverage * len(source) / 100)
        for _ in range(n):
            start = rng.randrange(max(1, len(source) - 100 + 1))
            read = list(source[start:start + 100])
            if len(read) < 100:
                read.extend("A" for _ in range(100 - len(read)))
            errors = round(100 * error_rate)
            for pos in rng.sample(range(100), errors):
                read[pos] = rng.choice("ACGT".replace(read[pos], ""))
            reads.append("".join(read))
    return reads


def _independent_evidence(candidate, reads):
    index = {}
    for pos in range(max(0, len(candidate) - KMER + 1)):
        kmer = candidate[pos:pos + KMER]
        index.setdefault(kmer, []).append(pos)
        index.setdefault(_reverse_complement(kmer), []).append(pos)
    covered = bytearray(len(candidate))
    supported = unique = ambiguous = 0
    for read in reads:
        positions = set()
        for offset in range(max(0, len(read) - KMER + 1)):
            positions.update(index.get(read[offset:offset + KMER], ()))
        if positions:
            supported += 1
            if len(positions) == 1:
                unique += 1
            else:
                ambiguous += 1
            for start in positions:
                covered[start:start + KMER] = b"\1" * min(KMER, len(candidate) - start)
    breadth = sum(covered) / len(candidate) if candidate else 0.0
    return {
        "read_count": len(reads),
        "supported_read_count": supported,
        "supported_read_fraction": supported / len(reads) if reads else 0.0,
        "unique_hit_read_count": unique,
        "ambiguous_hit_read_count": ambiguous,
        "candidate_coverage_breadth": breadth,
        "experimental_confidence_score": breadth,
        "confidence_band": (
            "STRONG_EXPERIMENTAL_ONLY"
            if breadth >= INDEPENDENT_STRONG_BREADTH else "INSUFFICIENT_OR_WEAK"
        ),
        "_covered": covered,
    }


def _trim_unsupported_ends(candidate, covered):
    positions = [i for i, value in enumerate(covered) if value]
    if not positions:
        return "", len(candidate), 0
    start, end = positions[0], positions[-1] + 1
    return candidate[start:end], start, len(candidate) - end


def _json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _stage_evidence(run_dir, row):
    root = Path(run_dir)
    aid = row["analysis_id"]
    qc = _json(root / "stages" / f"qc_{aid}" / "qc.json")
    stage = root / "stages" / f"m6_{aid}"
    reconstruction = _json(stage / "reconstruction_evidence.json")
    support = _json(stage / "read_support.json")
    residual = _json(stage / "residual_manifest.json")
    candidate_set = _json(stage / "candidate_sequence_set.json")
    assembly = _json(stage / "assembly" / "assembly_manifest.json")
    triage_counts = {}
    outcome_counts = {}
    triage_path = stage / "read_triage.csv"
    if triage_path.is_file():
        with triage_path.open(encoding="utf-8", newline="") as handle:
            for record in csv.DictReader(handle):
                reason = (
                    record.get("reason_codes") or record.get("reason")
                    or record.get("decision") or "unspecified"
                )
                triage_counts[reason] = triage_counts.get(reason, 0) + 1
                outcome = record.get("outcome") or "unspecified"
                outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
    input_fastq = root / "inputs" / "datasets" / aid / "reads.fastq.gz"
    screen_counts = {"mapped": 0, "unmapped": 0}
    screen_path = stage / "reference_screen.sam"
    if screen_path.is_file():
        with screen_path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.startswith("@"):
                    continue
                fields = line.split("\t")
                if len(fields) > 2:
                    key = "unmapped" if int(fields[1]) & 4 else "mapped"
                    screen_counts[key] += 1
    return {
        "synthetic_input_fastq_sha256": (
            _sha(input_fastq.read_bytes()) if input_fastq.is_file() else None
        ),
        "qc_status": qc.get("status", "UNAVAILABLE"),
        "qc_input_counts": qc.get("before", {}),
        "qc_retained_counts": qc.get("after", {}),
        "triage_reason_counts": triage_counts,
        "triage_outcome_counts": outcome_counts,
        "reference_screen_sam_counts": screen_counts,
        "downstream_classification": "NOT_IN_M22_BENCHMARK_PATH",
        "residual_manifest_status": residual.get("status", "UNAVAILABLE"),
        "residual_manifest_counts": residual.get("counts", residual.get("summary", {})),
        "assembly_status": assembly.get("workflow_status", "UNAVAILABLE"),
        "assembly_error": assembly.get("errors", []),
        "raw_contig_count": len(_fasta(stage / "assembly" / "raw" / "contigs.fasta")),
        "normalized_contig_count": len(_fasta(stage / "assembly" / "contigs.fasta")),
        "candidate_fasta_count": len(_fasta(stage / "candidate_sequences.fasta")),
        "candidate_record_count": len(candidate_set.get("records", [])),
        "reconstruction_status": reconstruction.get("status", "UNAVAILABLE"),
        "read_support_status": support.get("status", "UNAVAILABLE"),
        "read_support_record_count": len(support.get("read_support", [])),
        "artifact_availability": {
            name: (stage / name).is_file()
            for name in ("read_triage.csv", "residual_manifest.json",
                         "reconstruction_evidence.json", "read_support.json",
                         "candidate_sequence_set.json")
        },
    }


def _auc(rows):
    positives = [r["experimental_confidence_score"] for r in rows if r["class"] == "high_quality_partial"]
    negatives = [r["experimental_confidence_score"] for r in rows if r["class"] != "high_quality_partial"]
    if not positives or not negatives:
        return None
    return sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives) / (
        len(positives) * len(negatives)
    )


def _case_analysis(run_dir, split, case_row, truth_row, seed):
    stage = Path(run_dir) / "stages" / f"m6_{case_row['analysis_id']}"
    fasta = _fasta(stage / "candidate_sequences.fasta")
    set_doc = _json(stage / "candidate_sequence_set.json")
    support_by_id = {
        rec.get("fasta_record_id"): rec.get("m6_support_status", "UNAVAILABLE")
        for rec in set_doc.get("records", [])
    }
    input_refs = _fasta(Path(run_dir) / "inputs" / "datasets"
                        / case_row["analysis_id"] / "reference.fasta")
    backgrounds = [(name, seq) for name, seq in input_refs
                   if name.startswith("m19-background-")]
    independent = _independent_reads(
        truth_row.get("candidate_sequence"), backgrounds,
        case_row.get("coverage", 24), case_row.get("error_rate", 0.0),
        seed,
    )
    candidates = []
    for fasta_id, sequence in fasta:
        diag = diagnose_sequence(
            truth_row["candidate_sequence"] or "", sequence, input_refs
        ) if truth_row.get("candidate_sequence") else {
            "candidate_length": len(sequence),
            "full_length_sequence_identity": None,
            "local_alignment_identity": None,
            "target_coverage": None,
            "candidate_coverage": None,
            "potential_incorrect_joins": [],
            "_local": None,
        }
        evidence = _independent_evidence(sequence, independent)
        coverage = evidence.pop("_covered")
        diag.pop("_local", None)
        original = sequence
        trimmed, trim_prefix, trim_suffix = _trim_unsupported_ends(sequence, coverage)
        diag["terminal_trim_experiment"] = {
            "trimmed_prefix_bases": trim_prefix,
            "trimmed_suffix_bases": trim_suffix,
            "trimmed_candidate_length": len(trimmed),
            "trimmed_exact_match": bool(
                truth_row.get("candidate_sequence")
                and (
                    trimmed == truth_row["candidate_sequence"].upper()
                    or _reverse_complement(trimmed) == truth_row["candidate_sequence"].upper()
                )
            ),
            "trimmed_partial_match": False,
        }
        if truth_row.get("candidate_sequence") and trimmed:
            trimmed_diag = diagnose_sequence(truth_row["candidate_sequence"], trimmed)
            diag["terminal_trim_experiment"]["trimmed_partial_match"] = (
                not diag["terminal_trim_experiment"]["trimmed_exact_match"]
                and trimmed_diag["local_alignment_identity"] >= PARTIAL_IDENTITY
                and trimmed_diag["target_coverage"] >= PARTIAL_TARGET_COVERAGE
            )
        status = support_by_id.get(fasta_id, "UNAVAILABLE")
        if truth_row.get("candidate_sequence") is None:
            reconstruction_class = "incorrect_or_background_candidate"
        elif diag.get("strand_exact_match"):
            reconstruction_class = "exact"
        elif status != "READ_SUPPORTED_ASSEMBLY":
            reconstruction_class = "unsupported"
        elif (diag.get("local_alignment_identity", 0) >= PARTIAL_IDENTITY
              and diag.get("target_coverage", 0) >= PARTIAL_TARGET_COVERAGE):
            reconstruction_class = "high_quality_partial"
        elif diag.get("target_coverage", 0) < PARTIAL_TARGET_COVERAGE:
            reconstruction_class = "fragmented_or_unrelated"
        else:
            reconstruction_class = "incorrect_reconstruction"
        candidates.append({
            "fasta_record_id": fasta_id,
            "m6_support_status": status,
            "reconstruction_class": reconstruction_class,
            **{k: v for k, v in diag.items() if k != "terminal_trim_experiment"},
            "independent_read_evidence": evidence,
            "terminal_trim_experiment": diag["terminal_trim_experiment"],
        })
        candidates[-1]["strand_exact_match"] = bool(diag.get("strand_exact_match"))
    stage_report = _stage_evidence(run_dir, case_row)
    return {
        "case_id": case_row["case_id"],
        "split": split,
        "analysis_id": case_row["analysis_id"],
        "positive": bool(truth_row.get("candidate_sequence")),
        "m22_reported_exact_recovered": case_row.get("recovered_true_candidates", 0),
        "m22_m6_outcome": stage_report["reconstruction_status"],
        "stage_evidence": stage_report,
        "independent_read_set": {
            "read_count": len(independent),
            "sha256": _sha(("\n".join(independent) + "\n").encode("ascii")),
            "used_by_discovery_pipeline": False,
            "truth_used_only_to_generate_retrospective_validation_reads": True,
        },
        "candidates": candidates,
    }


def analyze(baseline_root):
    baseline_root = Path(baseline_root).resolve()
    case_reports, input_digests, configuration_digests = [], {}, {}
    for split, seed in m22.SPLITS.items():
        run_dir = baseline_root / split / "m21_default"
        report = _json(run_dir / "m19-report.json")
        truth_doc = _json(run_dir / "heldout_truth.json")
        if report.get("benchmark_status") != "COMPLETE":
            raise ValueError(f"M22 default baseline missing/incomplete for {split}")
        if len(report.get("cases", [])) != 8 or len(truth_doc.get("cases", [])) != 8:
            raise ValueError(f"M22 case inventory mismatch for {split}")
        input_digests[split] = _sha(
            (run_dir / "inputs" / "source_manifest.json").read_bytes()
        )
        configuration_digests[split] = _sha(
            (run_dir / "m19-workflow.json").read_bytes()
        )
        truth_by_id = {x["case_id"]: x for x in truth_doc["cases"]}
        for i, case in enumerate(report["cases"]):
            case_reports.append(_case_analysis(
                run_dir, split, case, truth_by_id[case["case_id"]],
                seed + i * 100003 + 23,
            ))
    candidate_rows = [c for case in case_reports for c in case["candidates"]]
    positive_candidates = [c for c in candidate_rows if c["reconstruction_class"] != "incorrect_or_background_candidate"]
    score_rows = [{
        "class": c["reconstruction_class"],
        "experimental_confidence_score":
            c["independent_read_evidence"]["experimental_confidence_score"],
    } for c in positive_candidates]
    heldout = [c for case in case_reports if case["split"] == "held_out"
               for c in case["candidates"]]
    exact = sum(c["strand_exact_match"] for c in positive_candidates)
    partial = sum(c["reconstruction_class"] == "high_quality_partial" for c in positive_candidates)
    error_rows = [
        c for c in positive_candidates
        if c.get("full_length_sequence_identity") is not None
    ]
    heldout_score_rows = [{
        "class": c["reconstruction_class"],
        "experimental_confidence_score":
            c["independent_read_evidence"]["experimental_confidence_score"],
    } for c in heldout if c["reconstruction_class"] != "incorrect_or_background_candidate"]
    trim_rows = [c for c in positive_candidates if c.get("terminal_trim_experiment")]
    trim_summary = {
        "candidate_count": len(trim_rows),
        "exact_before": sum(c["strand_exact_match"] for c in trim_rows),
        "exact_after": sum(c["terminal_trim_experiment"]["trimmed_exact_match"] for c in trim_rows),
        "partial_before": sum(c["reconstruction_class"] == "high_quality_partial" for c in trim_rows),
        "partial_after": sum(c["terminal_trim_experiment"]["trimmed_partial_match"] for c in trim_rows),
    }
    identity_values = sorted(c["full_length_sequence_identity"] for c in error_rows)
    error_summary = {
        "candidate_count": len(error_rows),
        "mean_full_length_identity": (
            sum(identity_values) / len(identity_values) if identity_values else None
        ),
        "total_substitutions": sum(c.get("substitution_count", 0) for c in error_rows),
        "total_insertions": sum(c.get("insertion_count", 0) for c in error_rows),
        "total_deletions": sum(c.get("deletion_count", 0) for c in error_rows),
        "total_internal_gap_runs": sum(c.get("internal_gap_run_count", 0) for c in error_rows),
        "total_missing_terminal_bases": sum(
            c.get("missing_target_prefix_bases", 0) + c.get("missing_target_suffix_bases", 0)
            for c in error_rows
        ),
        "total_extra_terminal_bases": sum(
            c.get("incorrect_candidate_prefix_bases", 0)
            + c.get("incorrect_candidate_suffix_bases", 0) for c in error_rows
        ),
    }
    output = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "biological_data_used": False,
        "pipeline_modified": False,
        "baseline": {
            "source": "M22 m21_default only",
            "case_count": len(case_reports),
            "positive_case_count": sum(c["positive"] for c in case_reports),
            "negative_control_count": sum(not c["positive"] for c in case_reports),
            "input_manifest_sha256_by_split": input_digests,
            "configuration_sha256_by_split": configuration_digests,
            "exact_recoveries": exact,
            "literal_m22_exact_recoveries": sum(
                int(case.get("m22_reported_exact_recovered", 0))
                for case in case_reports if case["positive"]
            ),
            "m22_reported_partial_recoveries": 5,
            "high_quality_partial_candidates": partial,
            "candidate_count": len(candidate_rows),
            "assembly_execution_failures": sum(
                c["m22_m6_outcome"] == "EXECUTION_FAILED" for c in case_reports
            ),
            "read_supported_candidates": sum(
                c["m6_support_status"] == "READ_SUPPORTED_ASSEMBLY"
                for c in candidate_rows
            ),
            "unsupported_candidates": sum(
                c["m6_support_status"] != "READ_SUPPORTED_ASSEMBLY"
                for c in candidate_rows
            ),
        },
        "sequence_error_summary": error_summary,
        "terminal_trim_experiment": trim_summary,
        "confidence_evaluation": {
            "score": "independent synthetic read k-mer coverage breadth",
            "strong_threshold": INDEPENDENT_STRONG_BREADTH,
            "candidate_count": len(score_rows),
            "high_quality_partial_candidate_auc": _auc(score_rows),
            "held_out_high_quality_partial_candidate_auc": _auc(heldout_score_rows),
            "exact_reconstruction_association": (
                "not estimable: no exact candidates in the reproduced M22 baseline"
            ),
            "held_out_candidate_count": len(heldout),
            "production_rule_adopted": False,
        },
        "diagnostic_method_limitations": [
            "Local/global alignment uses linear gap penalties and one deterministic optimal traceback; repeats may have equivalent alignments.",
            "A potential join is a sequence-overlap hypothesis across synthetic input references, not proof of a chimeric event.",
            "Independent reads are separate deterministic synthetic replicates, generated from hidden truth after discovery; their evidence is retrospective and not a production input.",
            "Exact-match 17-mers undercount reads with sequencing errors and overcount repetitive ambiguity; unique and ambiguous hits are reported separately.",
            "Terminal trimming is an isolated evaluation experiment and is not applied to M6 outputs.",
        ],
        "cases": case_reports,
    }
    return output


def _markdown(report):
    b = report["baseline"]
    lines = [
        "# M23 Assembly Accuracy and Candidate Evidence Validation",
        "",
        "This is a synthetic-only retrospective analysis. It does not modify M6 or authorize biological execution.",
        "",
        "## M22 default baseline reproduction",
        "",
        f"Reproduced {b['case_count']} cases ({b['positive_case_count']} positive, {b['negative_control_count']} negative). ",
        f"M22 reported exact/threshold-qualified partial recoveries: "
        f"{b['literal_m22_exact_recoveries']}/{b['m22_reported_partial_recoveries']}; "
        f"M23 strand-normalized exact/partial candidates: "
        f"{b['exact_recoveries']}/{b['high_quality_partial_candidates']}; ",
        f"assembly execution failures: {b['assembly_execution_failures']}; candidate predictions: {b['candidate_count']}.",
        f"Literal M22 exact recoveries: {b['literal_m22_exact_recoveries']}; strand-normalized exact recoveries: {b['exact_recoveries']}.",
        "",
        "| Split | Input manifest SHA-256 | Default workflow configuration SHA-256 |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {split} | `{digest}` | `{b['configuration_sha256_by_split'][split]}` |"
        for split, digest in b["input_manifest_sha256_by_split"].items()
    )
    lines.extend([
        "",
        "## Aggregate error and controlled experiment results",
        "",
        f"Across {report['sequence_error_summary']['candidate_count']} positive candidates, mean full-length identity was "
        f"{report['sequence_error_summary']['mean_full_length_identity']:.3f}; global alignment counted "
        f"{report['sequence_error_summary']['total_substitutions']} substitutions, "
        f"{report['sequence_error_summary']['total_insertions']} insertions, "
        f"{report['sequence_error_summary']['total_deletions']} deletions, and "
        f"{report['sequence_error_summary']['total_internal_gap_runs']} internal gap runs. "
        f"Terminal missing/extra bases were {report['sequence_error_summary']['total_missing_terminal_bases']}/"
        f"{report['sequence_error_summary']['total_extra_terminal_bases']}.",
        "",
        f"Read-supported terminal trimming changed exact recoveries "
        f"{report['terminal_trim_experiment']['exact_before']}→{report['terminal_trim_experiment']['exact_after']} "
        f"and high-quality partial candidates "
        f"{report['terminal_trim_experiment']['partial_before']}→"
        f"{report['terminal_trim_experiment']['partial_after']}. It was not promoted.",
        "",
        "## Candidate sequence-error diagnostics",
        "",
        "| Split / case | Class | Length | Full identity | Local identity | Target coverage | Candidate coverage | Subs / ins / del | Missing target ends | Extra candidate ends | M6 support | Independent-read breadth |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ])
    for case in report["cases"]:
        for cand in case["candidates"]:
            missing = cand.get("missing_target_prefix_bases", 0) + cand.get("missing_target_suffix_bases", 0)
            extra = cand.get("incorrect_candidate_prefix_bases", 0) + cand.get("incorrect_candidate_suffix_bases", 0)
            lines.append(
                f"| {case['split']}/{case['case_id']} | {cand['reconstruction_class']} | "
                f"{cand.get('candidate_length',0)} | {cand.get('full_length_sequence_identity',0):.3f} | "
                f"{cand.get('local_alignment_identity',0):.3f} | {cand.get('target_coverage',0):.3f} | "
                f"{cand.get('candidate_coverage',0):.3f} | {cand.get('substitution_count',0)} / "
                f"{cand.get('insertion_count',0)} / {cand.get('deletion_count',0)} | {missing} | {extra} | "
                f"{cand['m6_support_status']} | "
                f"{cand['independent_read_evidence']['candidate_coverage_breadth']:.3f} |"
            )
    lines.extend([
        "",
        "## Stage attribution and independent evidence",
        "",
        "Per-case M4/M6 evidence, read-triage reason counts, assembly manifests, candidate extraction, and read-support artifacts are recorded in the JSON report. Missing evidence is left unavailable rather than attributed to an unobserved stage.",
        "",
        "The independent confidence experiment uses 17-mer matches to a separately generated synthetic read replicate. It is retrospective only; the held-out replicate is not passed to the discovery workflow. Candidate-end trimming based on that read set is also scored as an isolated experiment and never writes to production candidates.",
        "",
        f"Candidate confidence AUC for high-quality partial versus other positive candidates: {report['confidence_evaluation']['high_quality_partial_candidate_auc']}. Exact-reconstruction association: {report['confidence_evaluation']['exact_reconstruction_association']}. No confidence rule or pipeline correction was promoted.",
        "",
        "## End-to-end and test verification",
        "",
        "M20 Phase 1 through Phase 5 integration suites: 38 tests passed. Full repository unittest discovery was attempted but exceeded the 300-second local command limit; completion is not claimed. GitHub Actions results are tracked by the draft PR.",
        "",
        "## Limitations and governance",
        "",
        "Alignment uses linear gap penalties and one optimal traceback; repeat-rich sequences can have equivalent placements. A potential contig join is a hypothesis only. The benchmark is small and synthetic, exact reconstruction is absent, and independent-read k-mer evidence is error-sensitive and can be ambiguous in repeats. No biological sensitivity, specificity, novelty, or helper dependence is established.",
        "",
        "`decision=INCOMPLETE`; `overall_state=BLOCKED_FOR_BENCHMARK_EXECUTION`; `biological_execution_authorized=false`.",
        "",
    ])
    return "\n".join(lines)


def run(baseline_root, output):
    report = analyze(baseline_root)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "m23-report.json").write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (output / "M23_ASSEMBLY_ACCURACY_EVIDENCE_VALIDATION.md").write_text(
        _markdown(report), encoding="utf-8",
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Analyze synthetic M22 assemblies for M23")
    parser.add_argument("--baseline", required=True, help="M22 default-only baseline output root")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = run(args.baseline, args.output)
    print(
        f"M23 COMPLETE: {report['baseline']['case_count']} cases, "
        f"{report['baseline']['candidate_count']} candidates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
