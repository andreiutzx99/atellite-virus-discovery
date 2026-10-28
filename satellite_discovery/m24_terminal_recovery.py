"""Synthetic-only retrospective terminal-boundary diagnostics for M24.

Experimental extensions use only M22 discovery FASTQ reads and candidates.
Held-out truth is opened only after candidate construction for scoring.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from . import m22_synthetic_benchmark as m22
from .m23_assembly_accuracy import _fasta, _reverse_complement, diagnose_sequence

MIN_OVERLAP = 30
MAX_EXTENSION = 20
MIN_READS = 2


def _reads(path):
    with gzip.open(path, "rt", encoding="ascii") as handle:
        while True:
            name = handle.readline().strip()
            if not name:
                break
            seq = handle.readline().strip().upper()
            handle.readline()
            handle.readline()
            yield name[1:].split()[0], seq


def _extensions(candidate, reads):
    """Return only exact, repeated read-supported terminal overhangs."""
    votes = {"left": {}, "right": {}}
    for read_id, raw in reads:
        for read in (raw, _reverse_complement(raw)):
            best = None
            for overlap in range(min(len(candidate), len(read)), MIN_OVERLAP - 1, -1):
                if candidate.startswith(read[-overlap:]):
                    extra = read[:-overlap]
                    if extra and len(extra) <= MAX_EXTENSION:
                        best = ("left", extra, candidate[:overlap])
                        break
                if candidate.endswith(read[:overlap]):
                    extra = read[overlap:]
                    if extra and len(extra) <= MAX_EXTENSION:
                        best = ("right", extra, candidate[-overlap:])
                        break
            if best:
                side, extra, context = best
                if candidate.count(context) == 1:
                    votes[side].setdefault(extra, set()).add(read_id)
    accepted = {}
    for side in ("left", "right"):
        qualifying = [(seq, ids) for seq, ids in votes[side].items()
                      if len(ids) >= MIN_READS]
        if len(qualifying) == 1:
            accepted[side] = qualifying[0][0]
    return accepted, {
        side: {seq: len(ids) for seq, ids in sorted(votes[side].items())}
        for side in ("left", "right")
    }


def run(baseline_root, output):
    root, output = Path(baseline_root), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases, metrics = [], {"exact_before": 0, "exact_after": 0,
                          "partial_before": 0, "partial_after": 0,
                          "incorrect_extensions": 0, "recovered_bases": 0,
                          "unsupported_candidates": 0, "assembly_failures": 0}
    input_manifest_hashes, configuration_hashes = {}, {}
    pending = []
    for split in m22.SPLITS:
        run_root = root / split / "m21_default"
        report = json.loads((run_root / "m19-report.json").read_text())
        if report.get("benchmark_status") != "COMPLETE" or len(report.get("cases", [])) != 8:
            raise ValueError(f"Incomplete M22 default baseline for {split}")
        input_manifest_hashes[split] = hashlib.sha256(
            (run_root / "inputs" / "source_manifest.json").read_bytes()
        ).hexdigest()
        configuration_hashes[split] = hashlib.sha256(
            (run_root / "m19-workflow.json").read_bytes()
        ).hexdigest()
        for row in report["cases"]:
            aid = row["analysis_id"]
            stage = run_root / "stages" / f"m6_{aid}"
            candidates = _fasta(stage / "candidate_sequences.fasta")
            support_doc = json.loads((stage / "candidate_sequence_set.json").read_text())
            support = {x.get("fasta_record_id"): x.get("m6_support_status")
                       for x in support_doc.get("records", [])}
            seq_reads = list(_reads(run_root / "inputs" / "datasets" / aid / "reads.fastq.gz"))
            reconstruction = json.loads((stage / "reconstruction_evidence.json").read_text())
            case = {"split": split, "case_id": row["case_id"],
                    "assembly_status": reconstruction.get("status", "UNAVAILABLE"),
                    "candidates": []}
            if reconstruction.get("status") == "EXECUTION_FAILED":
                metrics["assembly_failures"] += 1
            for fasta_id, candidate in candidates:
                proposals, votes = _extensions(candidate, seq_reads)
                corrected = proposals.get("left", "") + candidate + proposals.get("right", "")
                case["candidates"].append({
                    "fasta_id": fasta_id, "support": support.get(fasta_id),
                    "original_sequence": candidate, "experimental_sequence": corrected,
                    "original": candidate, "experimental": corrected,
                    "original_length": len(candidate), "experimental_length": len(corrected),
                    "read_supported_extensions": proposals, "overhang_vote_counts": votes,
                })
            pending.append((case, row["case_id"]))

    # Candidate construction is complete before any held-out truth is opened.
    for split in m22.SPLITS:
        run_root = root / split / "m21_default"
        truth_doc = json.loads((run_root / "heldout_truth.json").read_text())
        truth_by_id = {r["case_id"]: r for r in truth_doc["cases"]}
        for case, case_id in [item for item in pending if item[0]["split"] == split]:
            truth = truth_by_id[case_id].get("candidate_sequence")
            for item in case["candidates"]:
                candidate = item["original_sequence"]
                corrected = item["experimental_sequence"]
                before = diagnose_sequence(truth, candidate) if truth else None
                after = diagnose_sequence(truth, corrected) if truth else None
                exact_before = bool(before and before["strand_exact_match"])
                exact_after = bool(after and after["strand_exact_match"])
                partial_before = bool(before and before["local_alignment_identity"] >= .95
                                      and before["target_coverage"] >= .50 and not exact_before)
                partial_after = bool(after and after["local_alignment_identity"] >= .95
                                     and after["target_coverage"] >= .50 and not exact_after)
                metrics["exact_before"] += exact_before
                metrics["exact_after"] += exact_after
                metrics["partial_before"] += partial_before
                metrics["partial_after"] += partial_after
                metrics["recovered_bases"] += len(corrected) - len(candidate)
                metrics["incorrect_extensions"] += bool(
                    corrected != candidate and after and (
                        after["incorrect_candidate_prefix_bases"]
                        or after["incorrect_candidate_suffix_bases"]
                    )
                )
                metrics["unsupported_candidates"] += item["support"] != "READ_SUPPORTED_ASSEMBLY"
                item.update({
                    "exact_before": exact_before, "exact_after": exact_after,
                    "partial_before": partial_before, "partial_after": partial_after,
                    "before": before, "after": after,
                })
            cases.append(case)
    metrics_by_split = {}
    for split in m22.SPLITS:
        split_candidates = [x for case in cases if case["split"] == split
                           for x in case["candidates"]]
        metrics_by_split[split] = {
            key: sum(bool(x[key]) for x in split_candidates)
            for key in ("exact_before", "exact_after", "partial_before", "partial_after")
        }
        metrics_by_split[split]["candidate_count"] = len(split_candidates)
    result = {
        "schema": "m24-terminal-recovery-experiment-v1",
        "synthetic_only": True, "biological_data_used": False,
        "discovery_inputs_used_for_extension": True,
        "heldout_truth_used_to_construct_extensions": False,
        "development_tuning_heldout_separate": True,
        "input_manifest_sha256_by_split": input_manifest_hashes,
        "configuration_sha256_by_split": configuration_hashes,
        "extension_rule": {"minimum_exact_overlap": MIN_OVERLAP,
                           "maximum_extension": MAX_EXTENSION,
                           "minimum_distinct_reads": MIN_READS,
                           "unique_candidate_context_required": True},
        "case_count": sum(len(json.loads(
            ((root / split / "m21_default") / "m19-report.json").read_text()
        )["cases"]) for split in m22.SPLITS),
        "metrics": metrics, "metrics_by_split": metrics_by_split, "cases": cases,
        "governance": {"decision": "INCOMPLETE",
                       "overall_state": "BLOCKED_FOR_BENCHMARK_EXECUTION",
                       "biological_execution_authorized": False},
    }
    (output / "m24-terminal-recovery.json").write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = run(args.baseline, args.output)
    print(json.dumps(result["metrics"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
