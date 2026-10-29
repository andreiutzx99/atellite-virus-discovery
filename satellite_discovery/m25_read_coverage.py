"""Synthetic-only read-coverage and reconstruction experiment for M25.

Coverage calculations use known synthetic coordinates for measurement only.
The registered M19 workflow receives reads and technical references, never truth.
"""

import argparse
import gzip
import hashlib
import json
import math
import random
from pathlib import Path

from . import m19_benchmark as m19, m22_synthetic_benchmark as m22
from .m23_assembly_accuracy import _fasta, diagnose_sequence


SPLITS = {"development": 250101, "tuning": 250201, "held_out": 250301}
MODES = ("random", "uniform", "terminal_enriched")
READ_LENGTHS = (75, 100, 150)
DEPTHS = (16, 48, 80)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _coverage(length, starts, read_length):
    depth = [0] * length
    for start in starts:
        for pos in range(start, min(length, start + read_length)):
            depth[pos] += 1
    return depth


def _theory(length, read_length, count):
    """Exact endpoint and per-base probabilities for iid uniform valid starts."""
    starts = length - read_length + 1
    endpoint_p = 1.0 / starts
    base_probs = [
        min(read_length, i + 1, length - i, starts) / starts
        for i in range(length)
    ]
    return {
        "first_base_covered_probability": 1 - (1 - endpoint_p) ** count,
        "last_base_covered_probability": 1 - (1 - endpoint_p) ** count,
        "expected_target_coverage": sum(1 - (1 - p) ** count for p in base_probs) / length,
        "maximum_single_base_coverage_probability": 1 - (1 - max(base_probs)) ** count,
        "both_ends_covered_probability": (
            1 - 2 * (1 - endpoint_p) ** count
            + (1 - 2 * endpoint_p) ** count if starts > 1 else endpoint_p ** count
        ),
        "assumptions": "independent starts uniformly sampled from all valid read starts",
    }


def coverage_summary(truth, starts, read_length, qualities=None):
    if not truth:
        return {
            "target_length": 0, "read_length": read_length, "read_count": len(starts),
            "nominal_depth": 0, "mean_per_base_depth": 0, "minimum_per_base_depth": 0,
            "covered_bases": 0, "target_coverage": 0, "coverage_gaps": 0,
            "first_base_depth": 0, "last_base_depth": 0, "first_25_depth": 0,
            "last_25_depth": 0, "terminal_5_independent_reads": 0,
            "terminal_3_independent_reads": 0, "read_start_min": None,
            "read_start_max": None, "read_start_mean": None, "read_start_sd": None,
            "read_error_bases": sum(qualities or []), "read_error_rate_observed": 0,
        }
    depth = _coverage(len(truth), starts, read_length)
    covered = sum(value > 0 for value in depth)
    return {
        "target_length": len(truth),
        "read_length": read_length,
        "read_count": len(starts),
        "nominal_depth": len(starts) * read_length / len(truth),
        "mean_per_base_depth": sum(depth) / len(depth),
        "minimum_per_base_depth": min(depth, default=0),
        "covered_bases": covered,
        "target_coverage": covered / len(truth) if truth else 0,
        "coverage_gaps": sum(value == 0 for value in depth),
        "first_base_depth": depth[0] if depth else 0,
        "last_base_depth": depth[-1] if depth else 0,
        "first_25_depth": sum(depth[:25]) / min(25, len(depth)),
        "last_25_depth": sum(depth[-25:]) / min(25, len(depth)),
        "terminal_5_independent_reads": sum(
            start <= 4 and start + read_length > 0 for start in starts
        ),
        "terminal_3_independent_reads": sum(
            start < len(truth) and start + read_length >= len(truth) - 4
            for start in starts
        ),
        "read_start_min": min(starts, default=None),
        "read_start_max": max(starts, default=None),
        "read_start_mean": sum(starts) / len(starts) if starts else None,
        "read_start_sd": (
            math.sqrt(sum((x - sum(starts) / len(starts)) ** 2 for x in starts) / len(starts))
            if starts else None
        ),
        "read_error_bases": sum(qualities or []),
        "read_error_rate_observed": (
            sum(qualities or []) / (len(starts) * read_length) if starts else 0
        ),
    }


def _make_starts(length, read_length, depth, mode, rng):
    count = math.ceil(depth * length / read_length)
    last = length - read_length
    if last < 0:
        raise ValueError("target must be at least one read long")
    if mode == "random":
        return [rng.randrange(last + 1) for _ in range(count)]
    if mode == "uniform":
        return [round(i * last / max(1, count - 1)) for i in range(count)]
    starts = [0, last][:count]
    starts.extend(rng.randrange(last + 1) for _ in range(count - len(starts)))
    return starts


def _case_design(split, replicate):
    mode = MODES[(replicate - 1) % len(MODES)]
    length = (500, 900, 1400)[(replicate + len(split)) % 3]
    read_length = READ_LENGTHS[(replicate - 1) % len(READ_LENGTHS)]
    depth = DEPTHS[(replicate - 1) % len(DEPTHS)]
    error = (0.0, 0.02, 0.05)[(replicate - 1) % 3]
    repeat = ("low", "high", "low_complexity")[(replicate - 1) % 3]
    gc = (0.25, 0.50, 0.75)[(replicate - 1) % 3]
    return {
        "case_id": f"{split}-m25-{replicate:02d}",
        "analysis_id": f"m25{replicate:02d}",
        "positive": True,
        "target_length": length,
        "coverage": depth,
        "error_rate": error,
        "divergence": 0.25,
        "repeat_complexity": repeat,
        "gc_fraction": gc,
        "background_gc_fraction": 0.5,
        "read_start_mode": mode,
        "opaque_read_ids": True,
        "m25_read_length": read_length,
        "m25_replicate": replicate,
    }


def _make_controls(split, offset):
    return [{
        "case_id": f"{split}-m25-negative-{i}",
        "analysis_id": f"m25n{i}",
        "positive": False, "target_length": length, "coverage": depth,
        "error_rate": 0.0, "divergence": 0.25,
        "repeat_complexity": "low", "gc_fraction": 0.5,
        "background_gc_fraction": 0.5,
        "read_start_mode": MODES[(i - 1 + offset) % len(MODES)],
        "opaque_read_ids": True, "m25_read_length": read_length,
        "m25_replicate": i,
    } for i, (length, depth, read_length) in enumerate(
        ((500, 16, 75), (900, 48, 100), (1400, 80, 150)), 1
    )]


def _make_fastq(case, truth, reference, params, backgrounds=()):
    """M25 read generator; read coordinates remain outside the workflow inputs."""
    read_length = case.get("m25_read_length", m19.READ_LENGTH)
    rng = random.Random(m19.SEED + sum(case["analysis_id"].encode()))
    reads = []
    for bg_index, seq in enumerate((reference, *backgrounds)):
        for i in range(8):
            start = round(i * (len(seq) - read_length) / 7)
            rid = f"{case['analysis_id']}-ref-{bg_index}-{i}"
            reads.append((rid, seq[start:start + read_length], "I" * read_length))
    starts = []
    error_counts = []
    target_read_ids = {}
    if truth is not None:
        starts = _make_starts(len(truth), read_length, params["coverage"],
                              case["read_start_mode"], rng)
        for i, start in enumerate(starts):
            seq = list(truth[start:start + read_length])
            quality = ["I"] * len(seq)
            errors = round(len(seq) * params["error_rate"])
            error_counts.append(errors)
            for position in rng.sample(range(len(seq)), errors):
                seq[position] = rng.choice("ACGT".replace(seq[position], ""))
                quality[position] = "5"
            read_id = f"{case['analysis_id']}-r{i:05d}"
            target_read_ids[read_id] = start
            reads.append((read_id, "".join(seq), "".join(quality)))
    case["_m25_layout"] = {"starts": starts, "error_counts": error_counts,
                           "read_length": read_length, "target_read_ids": target_read_ids}
    return m19._gzip_fastq(reads) if hasattr(m19, "_gzip_fastq") else _gzip_fastq(reads)


def _gzip_fastq(reads):
    import io
    import gzip as gz
    out = io.BytesIO()
    with gz.GzipFile(fileobj=out, mode="wb", filename="", mtime=0) as handle:
        handle.write("".join(
            f"@{name}\n{seq}\n+\n{qual}\n" for name, seq, qual in reads
        ).encode("ascii"))
    return out.getvalue()


def _run_one(output, split, seed, case):
    old_cases, old_seed, old_length, old_fastq = (
        m19.CASES, m19.SEED, m19.READ_LENGTH, m19._fastq
    )
    try:
        m19.CASES = (case,)
        m19.SEED = seed
        m19.READ_LENGTH = case["m25_read_length"]
        m19._fastq = _make_fastq
        report = m19.run(output)
        case_state = {**case, "_m25_layout": case.get("_m25_layout", {})}
    finally:
        m19.CASES, m19.SEED, m19.READ_LENGTH, m19._fastq = (
            old_cases, old_seed, old_length, old_fastq
        )
    return report, case_state


def _reproduce_m24_baseline(output):
    expected = {
        "development": "6aa757fad5a443dbbf709ccdacd4b60045e8f2b9c24cbd20eebd52e25063a066",
        "tuning": "ba1ad7dc54b9be99ccafd674aac5d51ccc21696d478d260ecb0dd8d4c4cdd812",
        "held_out": "b9b9964aac89a6d6a20a3b4f87b79370096e2f0717bfad7aa0ead6af3e5f2107",
    }
    rows = {}
    for split, seed in m22.SPLITS.items():
        run_dir = output / "m24-baseline" / split / "m21_default"
        old_cases, old_seed = m19.CASES, m19.SEED
        try:
            m19.CASES = m22._cases(split)
            m19.SEED = seed
            report = m19.run(run_dir)
        finally:
            m19.CASES, m19.SEED = old_cases, old_seed
        digest = _sha((run_dir / "inputs/source_manifest.json").read_bytes())
        rows[split] = {
            "status": report["benchmark_status"],
            "case_count": len(report["cases"]),
            "input_manifest_sha256": digest,
            "expected_input_manifest_sha256": expected[split],
            "input_manifest_matches_m24": digest == expected[split],
            "configuration_sha256": _sha((run_dir / "m19-workflow.json").read_bytes()),
            "exact_recovery_cases": sum(
                r.get("recovery_rate") == 1 for r in report["cases"] if r["positive"]
            ),
        }
    return rows


def _fastq_ids(path):
    with gzip.open(path, "rt", encoding="ascii") as handle:
        while True:
            name = handle.readline().strip()
            if not name:
                break
            seq = handle.readline().strip()
            handle.readline()
            qual = handle.readline().strip()
            yield name[1:].split()[0], seq, qual


def _classification(summary):
    if summary["coverage_gaps"]:
        return "COVERAGE_INSUFFICIENT"
    if min(summary["terminal_5_independent_reads"],
           summary["terminal_3_independent_reads"]) >= 3:
        return "TERMINAL_EVIDENCE_SUFFICIENT"
    return "COVERAGE_COMPLETE_TERMINAL_SUPPORT_BELOW_THRESHOLD"


def _wilson(successes, total):
    if not total:
        return None
    z = 1.959963984540054
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return [max(0, centre - margin), min(1, centre + margin)]


def run(output, case_limit=None):
    """Run controlled synthetic cases through the unchanged registered M19 path."""
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    baseline = _reproduce_m24_baseline(output)
    cases, seed_rows = [], {}
    count = case_limit or 3
    for split, base_seed in SPLITS.items():
        designs = [_case_design(split, i) for i in range(1, count + 1)]
        designs.extend(_make_controls(split, len(split)))
        for index, case in enumerate(designs):
            seed = base_seed + index * 17
            run_dir = output / split / case["case_id"]
            report, state = _run_one(run_dir, split, seed, case)
            truth_rows = json.loads((run_dir / "heldout_truth.json").read_text())["cases"]
            truth = truth_rows[0].get("candidate_sequence")
            starts = state.get("_m25_layout", {}).get("starts", [])
            read_length = state.get("_m25_layout", {}).get("read_length", case["m25_read_length"])
            errors = state.get("_m25_layout", {}).get("error_counts", [])
            cov = coverage_summary(truth or "", starts, read_length, errors)
            cov["theory_random"] = _theory(len(truth), read_length, len(starts)) if truth else None
            cov["classification"] = _classification(cov) if truth else "TARGET_ABSENT"
            row = report["cases"][0]
            stage = run_dir / "stages" / f"m6_{case['analysis_id']}"
            candidates = _fasta(stage / "candidate_sequences.fasta")
            diagnostics = [diagnose_sequence(truth, seq) for _, seq in candidates] if truth else []
            exact = any(d["strand_exact_match"] for d in diagnostics)
            partial = any(
                d["local_alignment_identity"] >= .95 and d["target_coverage"] >= .50
                and not d["strand_exact_match"] for d in diagnostics
            )
            best = max(diagnostics, key=lambda d: (d["target_coverage"],
                                                     d["local_alignment_identity"]),
                       default=None)
            support_path = stage / "candidate_sequence_set.json"
            support_rows = json.loads(support_path.read_text()).get("records", []) if support_path.exists() else []
            unsupported = sum(x.get("m6_support_status") != "READ_SUPPORTED_ASSEMBLY"
                              for x in support_rows)
            pipeline = {
                "status": row["status"],
                "assembler_status": (
                    json.loads((stage / "reconstruction_evidence.json").read_text()).get("status")
                    if (stage / "reconstruction_evidence.json").exists() else "NOT_EVALUATED"
                ),
                "candidate_count": len(candidates),
                "exact_recovery": exact,
                "partial_recovery": partial and not exact,
                "full_length_identity": best["full_length_sequence_identity"] if best else None,
                "target_coverage": best["target_coverage"] if best else None,
                "candidate_coverage": best["candidate_coverage"] if best else None,
                "terminal_missing_bases": (
                    best["missing_target_prefix_bases"] + best["missing_target_suffix_bases"]
                    if best else None
                ),
                "incorrect_terminal_extensions": (
                    best["incorrect_candidate_prefix_bases"] + best["incorrect_candidate_suffix_bases"]
                    if best else None
                ),
                "unsupported_candidates": unsupported,
                "false_positive_candidates": row["false_positive_candidates"],
                "assembly_failure": (
                    json.loads((stage / "reconstruction_evidence.json").read_text()).get("status")
                    == "EXECUTION_FAILED"
                    if (stage / "reconstruction_evidence.json").exists()
                    else row["status"] != "COMPLETE"
                ),
            }
            coverage_class = cov["classification"]
            if truth and cov["coverage_gaps"] == 0 and not exact:
                coverage_class = "COVERAGE_COMPLETE_BUT_EXACT_RECONSTRUCTION_UNSUCCESSFUL"
            layout = state.get("_m25_layout", {})
            read_locations = layout.get("target_read_ids", {})
            target_id_sets = {
                "after_qc": {r[0] for r in _fastq_ids(run_dir / "stages" / f"qc_{case['analysis_id']}" / "clean_single.fastq.gz")}
                if (run_dir / "stages" / f"qc_{case['analysis_id']}" / "clean_single.fastq.gz").is_file() else set(),
                "after_reference_screen": {r[0] for r in _fastq_ids(stage / "residual_read1.fastq.gz")}
                if (stage / "residual_read1.fastq.gz").is_file() else set(),
                "assembly_eligible": {r[0] for r in _fastq_ids(stage / "eligible_read1.fastq.gz")}
                if (stage / "eligible_read1.fastq.gz").is_file() else set(),
            }
            stage_coverage = {}
            for stage_name, read_ids in target_id_sets.items():
                kept_starts = [read_locations[rid] for rid in read_ids if rid in read_locations]
                stage_coverage[stage_name] = coverage_summary(truth or "", kept_starts, read_length, [])
                stage_coverage[stage_name]["classification"] = (
                    _classification(stage_coverage[stage_name]) if truth else "TARGET_ABSENT"
                )
            case_row = {k: v for k, v in case.items() if not k.startswith("_")}
            case_row.update({
                "synthetic_only": True,
                "seed": seed,
                "input_manifest_sha256": _sha((run_dir / "inputs/source_manifest.json").read_bytes()),
                "coverage": cov,
                "coverage_classification": coverage_class,
                "coverage_after_stages": stage_coverage,
                "generated_read_orientation": "forward, single-end",
                "pipeline": pipeline,
                "workflow_status": report["workflow_status"],
            })
            cases.append(case_row)
            seed_rows[f"{split}/{case['case_id']}"] = seed
    positives = [x for x in cases if x["positive"]]
    negatives = [x for x in cases if not x["positive"]]
    grouped = {}
    for key, group in (
        ("all", positives),
        *[(mode, [x for x in positives if x["read_start_mode"] == mode]) for mode in MODES],
        *[(label, [x for x in positives if x["coverage_classification"] == label])
          for label in sorted({x["coverage_classification"] for x in positives})],
    ):
        n = len(group)
        exact_count = sum(x["pipeline"]["exact_recovery"] for x in group)
        partial_count = sum(x["pipeline"]["partial_recovery"] for x in group)
        grouped[key] = {
            "n": n, "exact": exact_count, "exact_rate": exact_count / n if n else None,
            "exact_wilson_95": _wilson(exact_count, n),
            "partial": partial_count, "partial_rate": partial_count / n if n else None,
            "assembly_execution_failures": sum(x["pipeline"]["assembly_failure"] for x in group),
            "unsupported_candidates": sum(x["pipeline"]["unsupported_candidates"] for x in group),
            "mean_target_coverage": sum(x["coverage"]["target_coverage"] for x in group) / n if n else None,
        }
    governance = {"decision": "INCOMPLETE",
                  "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
                  "biological_execution_authorized": False}
    result = {
        "schema": "m25-synthetic-read-coverage-v1",
        "status": "COMPLETE" if cases else "INCOMPLETE",
        "synthetic_only": True, "biological_data_used": False,
        "baseline_commit": "5db8b9b79428054bd30b364836057e5e7e377322",
        "baseline": baseline,
        "split_seeds": SPLITS, "run_seeds": seed_rows,
        "design": {"read_start_modes": MODES, "read_lengths": READ_LENGTHS,
                   "nominal_depths": DEPTHS, "negative_controls_in_each_split": 3,
                   "heldout_truth_used_for_scoring_only": True},
        "summary": {
            "positive_cases": len(positives), "negative_controls": len(negatives),
            "groups": grouped,
            "negative_control_candidate_count": sum(x["pipeline"]["candidate_count"] or 0 for x in negatives),
            "negative_control_false_positive_candidates": sum(x["pipeline"]["false_positive_candidates"] for x in negatives),
            "negative_control_cases_with_candidates": sum((x["pipeline"]["candidate_count"] or 0) > 0 for x in negatives),
            "paired_comparison": "Not applicable: modes are independent synthetic realizations, not paired reads.",
        },
        "cases": cases, "governance": governance,
        "limitations": [
            "All sequences, reads, references, and controls are deterministic artificial A/C/G/T fixtures.",
            "Coverage measurements use generated coordinates and are retrospective; coordinates and truth are not workflow inputs.",
            "The registered M19/M6 pipeline is unchanged apart from controlled input generation.",
            "This synthetic experiment is not biological validation or operational benchmark execution.",
        ],
    }
    (output / "m25-read-coverage.json").write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--replicates", type=int, default=3)
    args = parser.parse_args(argv)
    result = run(args.output, args.replicates)
    print(json.dumps({"status": result["status"], "case_count": len(result["cases"]),
                      "governance": result["governance"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
