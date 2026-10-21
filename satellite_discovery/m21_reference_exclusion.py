"""Offline synthetic reference-panel exclusion checks for M21 Phase 5."""

from __future__ import annotations

import hashlib
import json
import re
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


def _best_local_alignment(query: str, reference: str, max_cells: int) -> dict[str, float | int]:
    """Smith-Waterman local alignment with bounded cells and explicit identity/coverage."""
    rows, cols = len(query) + 1, len(reference) + 1
    if rows * cols > max_cells:
        raise OverflowError("Alignment cell limit exceeded.")
    scores = [[0] * cols for _ in range(rows)]
    trace = [bytearray(cols) for _ in range(rows)]
    best_score = best_i = best_j = 0
    for i in range(1, rows):
        qi = query[i - 1]
        row = scores[i]
        prev = scores[i - 1]
        for j in range(1, cols):
            diag = prev[j - 1] + (2 if qi == reference[j - 1] else -1)
            up = prev[j] - 2
            left = row[j - 1] - 2
            score = max(0, diag, up, left)
            row[j] = score
            trace[i][j] = 0 if score == 0 else 1 if score == diag else 2 if score == up else 3
            if score > best_score:
                best_score, best_i, best_j = score, i, j
    i, j = best_i, best_j
    aligned_query = matches = aligned_columns = 0
    while i and j and scores[i][j] > 0:
        direction = trace[i][j]
        if direction == 1:
            aligned_query += 1
            aligned_columns += 1
            matches += query[i - 1] == reference[j - 1]
            i -= 1
            j -= 1
        elif direction == 2:
            aligned_query += 1
            aligned_columns += 1
            i -= 1
        elif direction == 3:
            aligned_columns += 1
            j -= 1
        else:
            break
    identity = matches / max(1, aligned_columns)
    coverage = aligned_query / len(query)
    return {"score": best_score, "identity": identity, "query_coverage": coverage,
            "aligned_query_bases": aligned_query}


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
        for ref_id, reference in records:
            matches = []
            for excluded_item in excluded:
                query = excluded_item["sequence"].upper()
                forward = _best_local_alignment(query, reference, policy["max_alignment_cells"])
                reverse = _best_local_alignment(_reverse_complement(query), reference,
                                                policy["max_alignment_cells"])
                best = max((forward, reverse), key=lambda value: (value["query_coverage"], value["identity"], value["score"]))
                if (best["query_coverage"] >= policy["min_query_coverage"]
                        and best["identity"] >= policy["min_identity"]):
                    matches.append({
                        "sequence_id": excluded_item["sequence_id"],
                        "orientation": "REVERSE_COMPLEMENT" if best is reverse else "FORWARD",
                        "query_coverage": round(float(best["query_coverage"]), 6),
                        "identity": round(float(best["identity"]), 6),
                        "aligned_query_bases": best["aligned_query_bases"],
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
