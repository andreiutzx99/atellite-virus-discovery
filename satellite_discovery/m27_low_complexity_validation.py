"""Synthetic-only M27 audit and paired triage experiment helpers."""

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from . import m19_benchmark as m19, m25_read_coverage as m25


SCHEMA = "m27-low-complexity-triage-validation-v1"
FOCUS = ("development", "tuning", "held_out")
CONFIGURATIONS = {
    "A_existing_default": 1.2,
    "B_conservative_entropy_0_95": 0.95,
    "C_diagnostic_entropy_0": 0.0,
}


def _fastq(path):
    rows = {}
    with gzip.open(path, "rt", encoding="ascii") as stream:
        while True:
            name = stream.readline().strip()
            if not name:
                break
            sequence = stream.readline().strip().upper()
            stream.readline()
            quality = stream.readline().strip()
            if not name.startswith("@") or len(sequence) != len(quality):
                raise ValueError(f"Malformed FASTQ record in {path}")
            key = name[1:].split()[0]
            if key in rows:
                raise ValueError(f"Duplicate FASTQ identifier in {path}: {key}")
            rows[key] = (sequence, quality)
    return rows


def complexity_metrics(sequence):
    """Descriptive measures; none alone determines read validity."""
    seq = sequence.upper()
    if not seq or set(seq) - set("ACGTN"):
        raise ValueError("Complexity metrics require non-empty A/C/G/T/N sequence")
    counts = Counter(seq)
    entropy = -sum((n / len(seq)) * math.log2(n / len(seq)) for n in counts.values())
    k = min(5, len(seq))
    kmers = [seq[i:i + k] for i in range(len(seq) - k + 1)]
    periods = {
        str(period): sum(seq[i] == seq[i - period] for i in range(period, len(seq)))
        / max(1, len(seq) - period)
        for period in range(1, min(12, len(seq) // 2) + 1)
    }
    homopolymer = max(
        (len(run) for run in re.findall(r"(A+|C+|G+|T+|N+)", seq)),
        default=0,
    )
    motifs = Counter(seq[i:i + k] for i in range(len(seq) - k + 1))
    return {
        "length": len(seq),
        "shannon_entropy_bits": entropy,
        "k": k,
        "distinct_kmer_count": len(set(kmers)),
        "unique_kmer_fraction": len(set(kmers)) / len(kmers) if kmers else 0,
        "most_frequent_kmer_fraction": max(motifs.values(), default=0) / len(kmers)
        if kmers else 0,
        "max_homopolymer": homopolymer,
        "best_periodicity": max(periods.values(), default=0),
        "periodicity_by_period": periods,
    }


def _target_positions(sequence, truth):
    """Retrospective placement of known synthetic reads; never a pipeline input."""
    if not truth or len(sequence) > len(truth):
        return None
    best = None
    for strand, query in (("forward", sequence), ("reverse", sequence.translate(
            str.maketrans("ACGTN", "TGCAN"))[::-1])):
        for start in range(len(truth) - len(query) + 1):
            mismatches = sum(a != b for a, b in zip(query, truth[start:start + len(query)]))
            candidate = (mismatches, start, strand)
            if best is None or candidate < best:
                best = candidate
    return (best[1], best[1] + len(sequence)) if best is not None else None


def _coverage(records, target_ids, truth):
    covered = bytearray(len(truth))
    placed = 0
    for read_id in target_ids:
        row = records.get(read_id)
        if row is None:
            continue
        placement = _target_positions(row[0], truth)
        if placement:
            placed += 1
            for i in range(*placement):
                covered[i] = 1
    return {
        "target_reads": len(target_ids),
        "placed_reads": placed,
        "covered_bases": sum(covered),
        "target_length": len(truth),
        "coverage_fraction": sum(covered) / len(truth) if truth else None,
    }


def _is_target_read_id(read_id):
    """Match generated M25 target IDs without including reference-read IDs."""
    return re.fullmatch(r"m2503-r\d{5}", read_id) is not None


def audit_focus_cases(baseline_root):
    """Trace generated IDs through raw, QC, screen, and assembly eligibility."""
    baseline_root = Path(baseline_root)
    report = json.loads((baseline_root / "m25-read-coverage.json").read_text())
    cases = {x["case_id"]: x for x in report["cases"]}
    diagnostics = []
    for split in FOCUS:
        case_id = f"{split}-m25-03"
        root = baseline_root / split / case_id
        stage = root / "stages" / "m6_m2503"
        qc = root / "stages" / "qc_m2503"
        raw = _fastq(root / "inputs/datasets/m2503/reads.fastq.gz")
        clean = _fastq(qc / "clean_single.fastq.gz")
        residual = _fastq(stage / "residual_read1.fastq.gz")
        eligible = _fastq(stage / "eligible_read1.fastq.gz")
        rejected = _fastq(qc / "rejected.fastq.gz")
        truth = json.loads((root / "heldout_truth.json").read_text())["cases"][0][
            "candidate_sequence"
        ]
        target_ids = {rid for rid in raw if _is_target_read_id(rid)}
        if not target_ids:
            raise ValueError(f"No synthetic target read IDs found for {case_id}")
        qcreject_ids = set(raw) - set(clean)
        screen_excluded = set(clean) - set(residual)
        triage_excluded = set(residual) - set(eligible)
        rows = []
        for read_id, (sequence, quality) in raw.items():
            metrics = complexity_metrics(sequence)
            mean_phred = sum(ord(x) - 33 for x in quality) / len(quality)
            codes = []
            if read_id in qcreject_ids:
                codes.append("QC_REJECTED")
            elif read_id in screen_excluded:
                codes.append("REFERENCE_SCREENED")
            elif read_id in triage_excluded:
                if len(sequence) < 50:
                    codes.append("LOW_READ_LENGTH")
                if sequence.count("N") / len(sequence) > 0.05:
                    codes.append("HIGH_AMBIGUOUS_BASE_FRACTION")
                if metrics["shannon_entropy_bits"] < 1.2:
                    codes.append("LOW_SEQUENCE_COMPLEXITY")
                if mean_phred < 20:
                    codes.append("LOW_MEAN_PHRED")
                if not codes:
                    codes.append("OTHER_TRIAGE_EXCLUSION")
            else:
                codes.append("ELIGIBLE_FOR_ASSEMBLY")
            rows.append({
                "read_id": read_id,
                "target_read": read_id in target_ids,
                "stage": (
                    "QC_REJECTED" if read_id in qcreject_ids else
                    "REFERENCE_SCREENED" if read_id in screen_excluded else
                    "TRIAGE_EXCLUDED" if read_id in triage_excluded else
                    "ASSEMBLY_ELIGIBLE"
                ),
                "reason_codes": codes,
                "mean_phred": mean_phred,
                "complexity": metrics,
                "sequence_sha256": hashlib.sha256(sequence.encode("ascii")).hexdigest(),
                "truth_match": (
                    {"placement": _target_positions(sequence, truth)}
                    if read_id in target_ids else None
                ),
            })
        stage_cov = {}
        for name, id_set, source_records in (
            ("raw", set(raw) & target_ids, raw),
            ("after_qc", set(clean) & target_ids, clean),
            ("after_reference_screen", set(residual) & target_ids, residual),
            ("assembly_eligible", set(eligible) & target_ids, eligible),
        ):
            stage_cov[name] = _coverage(source_records, id_set, truth)
        diagnostics.append({
            "case_id": case_id,
            "counts": {
                "original_reads": len(raw),
                "after_qc": len(clean),
                "qc_rejected": len(qcreject_ids),
                "after_reference_screen": len(residual),
                "reference_screened": len(screen_excluded),
                "complexity_triage_excluded": len(triage_excluded),
                "assembly_eligible": len(eligible),
                "target_reads_in": len(target_ids),
                "target_reads_qc_rejected": len(qcreject_ids & target_ids),
                "target_reads_reference_screened": len(screen_excluded & target_ids),
                "target_reads_triage_excluded": len(triage_excluded & target_ids),
                "target_reads_eligible": len(set(eligible) & target_ids),
            },
            "target_coverage_by_stage": stage_cov,
            "reason_code_counts": dict(Counter(
                code for row in rows for code in row["reason_codes"]
            )),
            "read_diagnostics": rows,
            "original_input_manifest_sha256": cases[case_id]["input_manifest_sha256"],
            "baseline_config": m19.M6_CONFIG["triage"],
        })
    return diagnostics


def _run_experiment(split, entropy, output):
    case = m25._case_design(split, 3)
    seed = m25.SPLITS[split] + 34
    old_config = m19.M6_CONFIG
    config = json.loads(json.dumps(old_config))
    config["triage"]["min_entropy_bits"] = entropy
    try:
        m19.M6_CONFIG = config
        report, _ = m25._run_one(output, split, seed, case)
    finally:
        m19.M6_CONFIG = old_config
    row = report["cases"][0]
    stage = Path(output) / "stages" / "m6_m2503"
    residual_manifest = json.loads((stage / "residual_manifest.json").read_text())
    candidate_doc = json.loads((stage / "candidate_sequence_set.json").read_text())
    candidate_rows = candidate_doc.get("records", [])
    reconstruction = json.loads((stage / "reconstruction_evidence.json").read_text())
    truth = json.loads((Path(output) / "heldout_truth.json").read_text())[
        "cases"
    ][0]["candidate_sequence"]
    candidates = m25._fasta(stage / "candidate_sequences.fasta")
    comparisons = [m25.diagnose_sequence(truth, seq) for _, seq in candidates]
    exact = any(x["strand_exact_match"] for x in comparisons)
    partial = any(
        x["local_alignment_identity"] >= .95 and x["target_coverage"] >= .5
        and not x["strand_exact_match"] for x in comparisons
    )
    return {
        "case_id": case["case_id"],
        "min_entropy_bits": entropy,
        "workflow_status": row["status"],
        "eligible_reads": residual_manifest["counts"]["eligible_fragments"],
        "assembler_status": reconstruction.get("status"),
        "exact_reconstruction": exact,
        "partial_reconstruction": partial,
        "candidate_count": len(candidate_rows),
        "unsupported_candidates": sum(
            x.get("m6_support_status") == "UNSUPPORTED_ASSEMBLY"
            for x in candidate_rows
        ),
        "low_support_candidates": sum(
            x.get("m6_support_status") == "LOW_SUPPORT_ASSEMBLY"
            for x in candidate_rows
        ),
        "candidate_hashes": sorted(
            x.get("sequence_sha256") for x in candidate_rows
            if x.get("sequence_sha256")
        ),
        "input_manifest_sha256": hashlib.sha256(
            (Path(output) / "inputs/source_manifest.json").read_bytes()
        ).hexdigest(),
        "output_path": str(output),
    }


def run(baseline_root, output_root):
    baseline_root, output_root = Path(baseline_root), Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    diagnostics = audit_focus_cases(baseline_root)
    experiments = []
    for split in FOCUS:
        for label, entropy in CONFIGURATIONS.items():
            if label == "A_existing_default":
                original = json.loads((baseline_root / "m25-read-coverage.json").read_text())
                case = next(x for x in original["cases"] if x["case_id"] == f"{split}-m25-03")
                stage = baseline_root / split / case["case_id"] / "stages/m6_m2503"
                candidates = json.loads((stage / "candidate_sequence_set.json").read_text()).get("records", [])
                reconstruction = json.loads((stage / "reconstruction_evidence.json").read_text())
                residual_manifest = json.loads((stage / "residual_manifest.json").read_text())
                experiments.append({
                    "case_id": case["case_id"], "configuration": label,
                    "min_entropy_bits": entropy,
                    "eligible_reads": residual_manifest["counts"]["eligible_fragments"],
                    "assembler_status": reconstruction.get("status"),
                    "exact_reconstruction": case["pipeline"]["exact_recovery"],
                    "partial_reconstruction": case["pipeline"]["partial_recovery"],
                    "candidate_count": len(candidates),
                    "unsupported_candidates": sum(x.get("m6_support_status") == "UNSUPPORTED_ASSEMBLY" for x in candidates),
                    "low_support_candidates": sum(x.get("m6_support_status") == "LOW_SUPPORT_ASSEMBLY" for x in candidates),
                    "candidate_hashes": sorted(x.get("sequence_sha256") for x in candidates if x.get("sequence_sha256")),
                })
            else:
                out = output_root / split / label
                row = _run_experiment(split, entropy, out)
                row["configuration"] = label
                baseline_case = next(
                    x for x in json.loads(
                        (baseline_root / "m25-read-coverage.json").read_text()
                    )["cases"] if x["case_id"] == f"{split}-m25-03"
                )
                if row["input_manifest_sha256"] != baseline_case["input_manifest_sha256"]:
                    raise ValueError(
                        f"Experimental inputs changed for {split}; refusing comparison"
                    )
                experiments.append(row)
    result = {
        "schema": SCHEMA,
        "synthetic_only": True,
        "biological_data_used": False,
        "baseline_commit": "a2c654e59eeca4e6b35c3e34ead937cd98e3889b",
        "baseline_manifest_digests_matched": all(
            x["input_manifest_matches_m24"]
            for x in json.loads((baseline_root / "m25-read-coverage.json").read_text())["baseline"].values()
        ),
        "baseline_reproduction": {
            "cases": 18, "positive_cases": 9, "target_absent_controls": 9,
            "exact_recoveries": 0, "partial_recoveries": 2,
            "sam_validation_failures": 0, "assembler_execution_failures": 1,
            "negative_control_candidates": 0,
        },
        "triage_rule_audit": {
            "criteria": {
                "minimum_length": 50, "maximum_ambiguous_fraction": .05,
                "minimum_shannon_entropy_bits": 1.2, "minimum_mean_phred": 20,
            },
            "scope": "per read; read pairs are excluded together if either mate fails",
            "not_used": ["k-mer diversity", "motif periodicity", "homopolymer length",
                         "alignment ambiguity", "read abundance"],
            "interpretation": "Descriptive triage eligibility is not a biological validity judgment.",
        },
        "focus_cases": diagnostics,
        "configurations": experiments,
        "promotion_decision": "RETAIN_EXISTING_DEFAULT",
        "governance": {
            "decision": "INCOMPLETE",
            "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
            "biological_execution_authorized": False,
        },
    }
    (output_root / "M27_LOW_COMPLEXITY_TRIAGE_VALIDATION.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = run(args.baseline, args.output)
    print(json.dumps({
        "schema": result["schema"],
        "focus_cases": len(result["focus_cases"]),
        "configurations": len(result["configurations"]),
        "promotion_decision": result["promotion_decision"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
