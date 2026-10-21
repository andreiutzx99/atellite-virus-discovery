"""Offline synthetic reference-panel exclusion checks for M21 Phase 5."""

from __future__ import annotations

import hashlib
import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any

POLICY_VERSION = "m21-reference-exclusion-policy-v1"
DNA = frozenset("ACGTN")
POLICY_ID = re.compile(r"EXCL-[A-Z0-9]{10}\Z")
REF_ID = re.compile(r"SYNTHREF-[A-Z0-9]{8}\Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reverse_complement(sequence: str) -> str:
    return sequence.translate(str.maketrans("ACGTN", "TGCAN"))[::-1]


def _fasta(path: Path, max_sequence_length: int, max_total_bases: int) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    current_id: str | None = None
    chunks: list[str] = []
    total = 0

    def finish() -> None:
        nonlocal total
        if current_id is None:
            return
        seq = "".join(chunks).upper()
        if not seq or any(base not in DNA for base in seq):
            raise ValueError("FASTA sequence is empty or contains unsupported symbols.")
        if len(seq) > max_sequence_length:
            raise OverflowError("Reference sequence length limit exceeded.")
        total += len(seq)
        if total > max_total_bases:
            raise OverflowError("Reference panel base limit exceeded.")
        records.append((current_id, seq))

    with path.open("r", encoding="ascii", newline="") as stream:
        for raw in stream:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(">"):
                finish()
                current_id = line[1:].split()[0] if line[1:].strip() else ""
                chunks = []
                if not current_id or not REF_ID.fullmatch(current_id):
                    raise ValueError("Reference FASTA identifiers must be opaque synthetic IDs.")
            else:
                if current_id is None:
                    raise ValueError("FASTA sequence occurs before its header.")
                chunks.append(line)
        finish()
    if not records or len({identifier for identifier, _ in records}) != len(records):
        raise ValueError("Reference panel is empty or has duplicate identifiers.")
    return records


def _find_qualifying_alignment(
    query: str,
    reference: str,
    min_query_coverage: float,
    min_identity: float,
    budget: dict[str, int],
) -> dict[str, float | int] | None:
    """Exhaustively test query substrings against reference substrings within a shared cell budget.

    For each query substring meeting coverage, a semiglobal DP maximizes
    matches/columns against the approved identity threshold. This tests for
    existence directly rather than trusting a single highest-scoring local hit.
    """
    coverage_fraction = Fraction(str(min_query_coverage))
    identity_fraction = Fraction(str(min_identity))
    min_bases = (coverage_fraction.numerator * len(query) + coverage_fraction.denominator - 1) // coverage_fraction.denominator
    penalty = identity_fraction.numerator
    match_score = identity_fraction.denominator - penalty
    ref_len = len(reference)

    for start in range(len(query)):
        if budget["used"] + ref_len + 1 > budget["limit"]:
            raise OverflowError("Complete alignment search exceeded its cell budget.")
        budget["used"] += ref_len + 1
        previous_score = [0] * (ref_len + 1)  # free reference prefix
        previous_matches = [0] * (ref_len + 1)
        previous_columns = [0] * (ref_len + 1)
        for query_end in range(start + 1, len(query) + 1):
            if budget["used"] + ref_len + 1 > budget["limit"]:
                raise OverflowError("Complete alignment search exceeded its cell budget.")
            budget["used"] += ref_len + 1
            current_score = [0] * (ref_len + 1)
            current_matches = [0] * (ref_len + 1)
            current_columns = [0] * (ref_len + 1)
            current_score[0] = -penalty * (query_end - start)
            current_columns[0] = query_end - start
            base = query[query_end - 1]
            for j in range(1, ref_len + 1):
                is_match = base == reference[j - 1]
                match = int(is_match)
                candidates = (
                    (previous_score[j - 1] + (match_score if is_match else -penalty),
                     previous_matches[j - 1] + match, previous_columns[j - 1] + 1),
                    (previous_score[j] - penalty, previous_matches[j], previous_columns[j] + 1),
                    (current_score[j - 1] - penalty, current_matches[j - 1], current_columns[j - 1] + 1),
                )
                score, matches, columns = max(candidates, key=lambda item: item[0])
                current_score[j] = score
                current_matches[j] = matches
                current_columns[j] = columns
            query_bases = query_end - start
            if query_bases >= min_bases:
                best_end = max(range(1, ref_len + 1), key=current_score.__getitem__)
                if current_score[best_end] >= 0:
                    columns = current_columns[best_end]
                    return {
                        "identity": current_matches[best_end] / max(columns, 1),
                        "query_coverage": query_bases / len(query),
                        "aligned_query_bases": query_bases,
                    }
            previous_score, previous_matches, previous_columns = (
                current_score, current_matches, current_columns
            )
    return None


def exclusion_policy_digest(policy: dict[str, Any]) -> str:
    return _sha(_canonical(policy))


def validate_reference_exclusions(
    reference_path: str | Path,
    policy: Any,
    *,
    expected_policy_sha256: str | None,
    expected_reference_sha256: str | None,
) -> dict[str, Any]:
    """Validate an approved exclusion policy against local synthetic FASTA bytes.

    Similarity is a sequence-level exclusion signal only; it does not establish
    biological relatedness. No network access or reference retrieval is performed.
    """
    issues: list[str] = []
    if not isinstance(policy, dict):
        return {"status": "FAIL", "results": [], "issues": ["Exclusion policy must be an object."]}
    required = {"schema_version", "policy_id", "min_query_coverage", "min_identity",
                "max_sequence_length", "max_total_bases", "max_panel_bytes", "max_references",
                "max_alignment_cells", "excluded_sequences"}
    if set(policy) != required:
        issues.append("Exclusion policy has missing or unknown fields.")
    if policy.get("schema_version") != POLICY_VERSION or not POLICY_ID.fullmatch(str(policy.get("policy_id", ""))):
        issues.append("Exclusion policy identity or version is invalid.")
    for name in ("min_query_coverage", "min_identity"):
        value = policy.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 < value <= 1:
            issues.append(f"{name} must be a number in (0, 1].")
    for name in ("max_sequence_length", "max_total_bases", "max_panel_bytes", "max_references",
                 "max_alignment_cells"):
        value = policy.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            issues.append(f"{name} must be a positive integer.")
    excluded = policy.get("excluded_sequences")
    if not isinstance(excluded, list) or not excluded:
        issues.append("At least one exclusion sequence is required.")
        excluded = []
    seen_ids: set[str] = set()
    for item in excluded:
        if not isinstance(item, dict) or set(item) != {"sequence_id", "sequence", "sha256"}:
            issues.append("Malformed excluded-sequence record.")
            continue
        seq_id, sequence, digest = item["sequence_id"], item["sequence"], item["sha256"]
        if (not isinstance(seq_id, str) or not re.fullmatch(r"SYNTH-[A-Z0-9]{8}", seq_id)
                or seq_id in seen_ids or not isinstance(sequence, str) or not sequence
                or any(base not in DNA for base in sequence.upper())
                or not isinstance(digest, str) or digest != _sha(sequence.upper().encode("ascii"))):
            issues.append("Invalid, duplicate, or digest-mismatched excluded sequence.")
        elif len(sequence) > policy.get("max_sequence_length", 0):
            issues.append("Excluded sequence exceeds the configured length limit.")
        else:
            seen_ids.add(seq_id)
    policy_sha = exclusion_policy_digest(policy)
    if not isinstance(expected_policy_sha256, str) or policy_sha != expected_policy_sha256:
        issues.append("Exclusion policy is missing independent digest binding or has been altered.")
    if issues:
        return {"status": "FAIL", "policy_sha256": policy_sha, "results": [],
                "issues": sorted(set(issues))}

    path = Path(reference_path)
    try:
        if path.stat().st_size > policy["max_panel_bytes"]:
            raise OverflowError("Reference panel byte limit exceeded.")
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
    except OSError:
        return {"status": "INCOMPLETE", "policy_sha256": policy_sha, "results": [],
                "issues": ["Reference-panel bytes are unavailable."]}
    except OverflowError as exc:
        return {"status": "INCOMPLETE", "policy_sha256": policy_sha, "results": [],
                "issues": [str(exc)]}
    panel_sha = hasher.hexdigest()
    if not isinstance(expected_reference_sha256, str) or panel_sha != expected_reference_sha256:
        return {"status": "FAIL", "policy_sha256": policy_sha, "reference_sha256": panel_sha,
                "results": [], "issues": ["Reference panel is missing its approved digest or has changed."]}
    try:
        records = _fasta(path, policy["max_sequence_length"], policy["max_total_bases"])
        if len(records) > policy["max_references"]:
            raise OverflowError("Reference count limit exceeded.")
        results = []
        alignment_budget = {"used": 0, "limit": policy["max_alignment_cells"]}
        for ref_id, reference in records:
            matches = []
            for excluded_item in excluded:
                query = excluded_item["sequence"].upper()
                found = _find_qualifying_alignment(
                    query, reference, policy["min_query_coverage"], policy["min_identity"],
                    alignment_budget,
                )
                orientation = "FORWARD"
                if found is None:
                    found = _find_qualifying_alignment(
                        _reverse_complement(query), reference, policy["min_query_coverage"],
                        policy["min_identity"], alignment_budget,
                    )
                    orientation = "REVERSE_COMPLEMENT"
                if found is not None:
                    matches.append({
                        "sequence_id": excluded_item["sequence_id"],
                        "orientation": orientation,
                        "query_coverage": round(float(found["query_coverage"]), 6),
                        "identity": round(float(found["identity"]), 6),
                        "aligned_query_bases": found["aligned_query_bases"],
                    })
            results.append({"reference_id": ref_id, "decision": "REJECT" if matches else "ACCEPT",
                            "reason": "excluded-sequence threshold met" if matches else "no exclusion threshold met",
                            "matches": matches})
        if _hash_file(path) != panel_sha:
            return {"status": "FAIL", "policy_sha256": policy_sha,
                    "reference_sha256": panel_sha, "results": [],
                    "issues": ["Reference panel changed during exclusion verification."]}
    except OverflowError as exc:
        return {"status": "INCOMPLETE", "policy_sha256": policy_sha, "reference_sha256": panel_sha,
                "results": [], "issues": [str(exc)]}
    except (OSError, UnicodeError, ValueError) as exc:
        return {"status": "FAIL", "policy_sha256": policy_sha, "reference_sha256": panel_sha,
                "results": [], "issues": [str(exc)]}
    status = "FAIL" if any(item["decision"] == "REJECT" for item in results) else "PASS"
    evidence = {"policy_sha256": policy_sha, "reference_sha256": panel_sha,
                "excluded_sequence_sha256": sorted(item["sha256"] for item in excluded)}
    return {"status": status, "policy_sha256": policy_sha, "reference_sha256": panel_sha,
            "evidence_sha256": _sha(_canonical(evidence)), "results": results, "issues": []}
