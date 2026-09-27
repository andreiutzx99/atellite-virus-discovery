"""Dependency-free, deterministic exact sequence architecture algorithms (M10)."""

from dataclasses import dataclass
import hashlib
import json
from typing import Any


_SYMBOLS = set("ACGTURYSWKMBDHVN")
_AMBIGUITY = {
    "A": frozenset("A"), "C": frozenset("C"), "G": frozenset("G"),
    "T": frozenset("T"), "U": frozenset("U"),
    "R": frozenset("AG"), "Y": frozenset("CT"), "S": frozenset("CG"),
    "W": frozenset("AT"), "K": frozenset("GT"), "M": frozenset("AC"),
    "B": frozenset("CGT"), "D": frozenset("AGT"), "H": frozenset("ACT"),
    "V": frozenset("ACG"), "N": frozenset("ACGT"),
}
_BRANCHES = (
    "M10_TERMINAL_DIRECT_V1", "M10_TERMINAL_INVERTED_V1",
    "M10_INTERNAL_DIRECT_V1", "M10_INTERNAL_INVERTED_V1",
)


@dataclass(frozen=True)
class M10Limits:
    max_candidate_symbols: int = 1_000_000
    max_symbol_comparisons_per_branch: int = 50_000_000
    max_evidence_rows_per_branch: int = 100_000

    def __post_init__(self):
        for name in ("max_candidate_symbols", "max_symbol_comparisons_per_branch",
                     "max_evidence_rows_per_branch"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")


def _digest(payload):
    return hashlib.sha256(payload).hexdigest()


def _exact(a, b):
    return a in "ACGTU" and a == b


def _comparison(a, b, molecule=None):
    sets = _AMBIGUITY
    if molecule == "RNA":
        sets = {key: frozenset("U" if char == "T" else char for char in value)
                for key, value in _AMBIGUITY.items()}
    if _exact(a, b):
        return True, 0, 0
    if a in sets and b in sets and (
            a not in "ACGTU" or b not in "ACGTU"):
        compatible = bool(sets[a] & sets[b])
        return False, int(compatible), int(not compatible)
    return False, 0, int(a in sets and b in sets)


def _reverse_view(seq, molecule):
    dna = molecule == "DNA"
    comp = {
        "A": "T" if dna else "U", "C": "G", "G": "C",
        "T": "A" if dna else "U", "U": "A",
        "R": "Y", "Y": "R", "S": "S", "W": "W", "K": "M",
        "M": "K", "B": "V", "V": "B", "D": "H", "H": "D", "N": "N",
    }
    return "".join(comp[c] for c in reversed(seq))


def _row(candidate_id, sequence_id, source_digest, branch, orientation,
         a, b, span, relationship, view_digest=None):
    ia, ib = [a, a + span], [b, b + span]
    payload = json.dumps([candidate_id, sequence_id, branch, orientation,
                          source_digest, view_digest, ia, ib, relationship],
                         separators=(",", ":")).encode()
    return {
        "evidence_id": _digest(payload), "candidate_id": candidate_id,
        "sequence_id": sequence_id, "source_sha256": source_digest,
        "branch_id": branch, "method_id": branch, "relationship_class": relationship,
        "relationship_classes": (["SUFFIX_PREFIX", "DIRECT_TERMINAL"]
                                 if relationship == "SUFFIX_PREFIX" else [relationship]),
        "orientation": orientation, "source_intervals": [ia, ib],
        "span": span, "aligned_length": span,
        "definite_identical_base_count": span,
        "definite_identical_base_denominator": span,
        "ambiguity_compatible_count": 0, "ambiguity_incompatible_count": 0,
        "source_intervals_overlap": ia[0] < ib[1] and ib[0] < ia[1],
        "view_digest": view_digest,
    }


def _branch(branch, evidence, comparisons, cap, row_cap, boundary=False,
            insufficient=False, invalid=False, truncated=False,
            ambiguity_compatible=0, ambiguity_incompatible=0):
    if insufficient:
        status = "INSUFFICIENT_INFORMATION"
    elif invalid:
        status = "INPUT_INVALID"
    elif truncated:
        status = "TRUNCATED"
    elif boundary:
        status = "BOUNDARY_LIMITATION"
    elif evidence:
        status = "COMPLETED_MATCHES_REPORTED"
    else:
        status = "COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY"
    return {
        "branch_id": branch, "branch_status": status,
        "evidence_status": "EVIDENCE_FOUND" if evidence else "NO_EVIDENCE_REPORTED",
        "evidence": evidence, "evidence_rows": len(evidence),
        "accounted_comparisons": comparisons,
        "ambiguity_compatible_comparisons": ambiguity_compatible,
        "ambiguity_incompatible_comparisons": ambiguity_incompatible,
        "full_accounting_proven": status in {
            "COMPLETED_MATCHES_REPORTED",
            "COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY",
        },
        "effective_limits": {
            "max_symbol_comparisons_per_branch": cap,
            "max_evidence_rows_per_branch": row_cap,
            "max_candidate_symbols": None,
        },
        "evidence_ordering_policy": (
            "M10-PRECAP-TRAVERSAL-V1" if truncated
            else "M10-CANONICAL-SERIALIZATION-V1"
        ),
    }


def analyze_sequence(sequence, *, candidate_id, sequence_id, molecule_type,
                     terminal_boundaries_resolved, limits):
    """Analyze one immutable sequence and return a JSON-serializable result."""
    if not isinstance(limits, M10Limits):
        raise TypeError("limits must be an M10Limits instance")
    identity_ok = isinstance(candidate_id, str) and bool(candidate_id) and \
        isinstance(sequence_id, str) and bool(sequence_id)
    if not isinstance(terminal_boundaries_resolved, bool):
        identity_ok = False
    if sequence is None:
        if not identity_ok:
            branches = {b: _branch(
                b, [], 0, limits.max_symbol_comparisons_per_branch,
                limits.max_evidence_rows_per_branch, invalid=True,
            ) for b in _BRANCHES}
            for item in branches.values():
                item["effective_limits"]["max_candidate_symbols"] = limits.max_candidate_symbols
            return {"candidate_id": candidate_id, "sequence_id": sequence_id,
                    "input_status": "INPUT_INVALID", "aggregate_status": "PARTIAL",
                    "branches": branches, "evidence": []}
        branches = {b: _branch(b, [], 0, limits.max_symbol_comparisons_per_branch,
                               limits.max_evidence_rows_per_branch,
                               insufficient=False) for b in _BRANCHES}
        for item in branches.values():
            item["branch_status"] = "SEQUENCE_UNAVAILABLE"
            item["full_accounting_proven"] = False
            item["effective_limits"]["max_candidate_symbols"] = limits.max_candidate_symbols
        return {"candidate_id": candidate_id, "sequence_id": sequence_id,
                "input_status": "SEQUENCE_UNAVAILABLE", "aggregate_status": "PARTIAL",
                "branches": branches, "evidence": []}
    if isinstance(sequence, bytes):
        try:
            source = sequence.decode("ascii")
        except UnicodeDecodeError:
            source = ""
            identity_ok = False
        source_bytes = sequence
    elif isinstance(sequence, str):
        source = sequence
        try:
            source_bytes = sequence.encode("ascii")
        except UnicodeEncodeError:
            source_bytes = sequence.encode("utf-8")
            identity_ok = False
    else:
        source, source_bytes, identity_ok = "", b"", False
    digest = _digest(source_bytes)
    upper = source.upper()
    valid = identity_ok and bool(source) and all(c in _SYMBOLS for c in upper)
    base = {"candidate_id": candidate_id, "sequence_id": sequence_id,
            "source_sequence": source, "source_sha256": digest,
            "source_length": len(source), "molecule_type": molecule_type,
            "comparison_view": {
                "digest": _digest(b"M10-COMPARE-IUPAC-v1\0" + upper.encode("ascii", "ignore")),
                "length": len(source), "policy": "M10-COMPARE-IUPAC-v1",
            }}
    if not valid:
        branches = {b: _branch(b, [], 0, limits.max_symbol_comparisons_per_branch,
                               limits.max_evidence_rows_per_branch, invalid=True)
                    for b in _BRANCHES}
        for item in branches.values():
            item["effective_limits"]["max_candidate_symbols"] = limits.max_candidate_symbols
        return {**base, "input_status": "INPUT_INVALID", "aggregate_status": "PARTIAL",
                "branches": branches, "evidence": []}
    if len(source) > limits.max_candidate_symbols:
        branches = {b: _branch(b, [], 0, limits.max_symbol_comparisons_per_branch,
                               limits.max_evidence_rows_per_branch, truncated=True)
                    for b in _BRANCHES}
        for item in branches.values():
            item["effective_limits"]["max_candidate_symbols"] = limits.max_candidate_symbols
        return {**base, "input_status": "INPUT_VALID", "aggregate_status": "PARTIAL",
                "branches": branches, "evidence": []}
    molecule = molecule_type.upper() if isinstance(molecule_type, str) else ""
    single = molecule in {"DNA", "RNA"} and not (
        ("U" in upper and molecule == "DNA") or
        ("T" in upper and molecule == "RNA") or ("T" in upper and "U" in upper))
    rc = _reverse_view(upper, molecule) if single else None
    rc_digest = (_digest(b"M10-REVERSE-COMPLEMENT-v1\0" + molecule.encode() +
                         b"\0" + rc.encode()) if rc is not None else None)
    if rc is not None:
        base["reverse_complement_view"] = {
            "digest": rc_digest, "length": len(rc),
            "alphabet_id": molecule, "policy": "M10-REVERSE-COMPLEMENT-v1",
            "coordinate_map": "view interval [a,b) -> source [n-b,n-a)",
        }
    results = {}
    all_evidence = []
    for branch_index, branch in enumerate(_BRANCHES):
        inverted = branch_index in (1, 3)
        if inverted and rc is None:
            results[branch] = _branch(branch, [], 0, limits.max_symbol_comparisons_per_branch,
                                      limits.max_evidence_rows_per_branch, insufficient=True)
            results[branch]["effective_limits"]["max_candidate_symbols"] = limits.max_candidate_symbols
            continue
        evidence, comparisons, truncated = [], 0, False
        ambiguity_compatible = ambiguity_incompatible = 0
        view = rc if inverted else upper
        view_digest = rc_digest if inverted else base["comparison_view"]["digest"]
        if branch_index < 2:
            for k in range(1, len(source)):
                ok = True
                for x in range(k):
                    if comparisons >= limits.max_symbol_comparisons_per_branch:
                        truncated = True
                        break
                    comparisons += 1
                    # The reverse-complement view's prefix is the
                    # reverse-complement of the source suffix.
                    aligned = view[x] if inverted else upper[len(source)-k+x]
                    exact, compatible, incompatible = _comparison(
                        upper[x], aligned, molecule)
                    ambiguity_compatible += compatible
                    ambiguity_incompatible += incompatible
                    if not exact:
                        ok = False
                if truncated:
                    break
                if ok:
                    if len(evidence) >= limits.max_evidence_rows_per_branch:
                        truncated = True
                        break
                    evidence.append(_row(candidate_id, sequence_id, digest, branch,
                                         "REVERSE_COMPLEMENT" if inverted else "DIRECT",
                                         0, len(source)-k, k,
                                          "INVERTED_TERMINAL" if inverted else "SUFFIX_PREFIX",
                                         view_digest))
                if truncated:
                    break
            boundary = not terminal_boundaries_resolved
        else:
            seen = set()
            n = len(source)
            # A one-base seed discovers every maximal run while preserving
            # first-start/second-start traversal and deterministic accounting.
            for i in range(1, n - 1):
                for j in range(i + 1, n - 1):
                    if comparisons >= limits.max_symbol_comparisons_per_branch:
                        truncated = True; break
                    if inverted:
                        ok, compatible, incompatible = _comparison(
                            upper[i], view[n - 1 - j], molecule)
                    else:
                        ok, compatible, incompatible = _comparison(
                            upper[i], upper[j], molecule)
                    ambiguity_compatible += compatible
                    ambiguity_incompatible += incompatible
                    comparisons += 1
                    if not ok: continue
                    left_a = left_b = right_a = right_b = 0
                    while (i-left_a-1 > 0 and
                           (j+right_b+1 < n-1 if inverted else
                            j-left_b-1 > 0)):
                        if comparisons >= limits.max_symbol_comparisons_per_branch:
                            truncated = True; break
                        x = upper[i-left_a-1]
                        y = (view[n-1-(j+right_b+1)] if inverted
                             else upper[j-left_b-1])
                        comparisons += 1
                        exact, compatible, incompatible = _comparison(x, y, molecule)
                        ambiguity_compatible += compatible
                        ambiguity_incompatible += incompatible
                        if not exact: break
                        left_a += 1
                        if inverted:
                            right_b += 1
                        else:
                            left_b += 1
                    while (not truncated and i+right_a+1 < n-1 and
                           (j-left_b-1 > 0 if inverted else
                            j+right_b+1 < n-1)):
                        if comparisons >= limits.max_symbol_comparisons_per_branch:
                            truncated = True; break
                        x = upper[i+right_a+1]
                        y = (view[n-1-(j-left_b-1)] if inverted
                             else upper[j+right_b+1])
                        comparisons += 1
                        exact, compatible, incompatible = _comparison(x, y, molecule)
                        ambiguity_compatible += compatible
                        ambiguity_incompatible += incompatible
                        if not exact: break
                        right_a += 1
                        if inverted:
                            left_b += 1
                        else:
                            right_b += 1
                    if truncated:
                        break
                    a, b, span = i-left_a, j-left_b, left_a+right_a+1
                    if a > 0 and a+span < n and b > 0 and b+span < n:
                        intervals = tuple(sorted(((a, a+span), (b, b+span))))
                        if intervals[0] == intervals[1]:
                            continue
                        key = (intervals, branch)
                        if key not in seen:
                            if len(evidence) >= limits.max_evidence_rows_per_branch:
                                truncated = True
                                break
                            seen.add(key)
                            evidence.append(_row(candidate_id, sequence_id, digest, branch,
                                                 "REVERSE_COMPLEMENT" if inverted else "DIRECT",
                                                 intervals[0][0], intervals[1][0], span,
                                                  "INTERNAL_REVERSE_COMPLEMENT_REPEAT"
                                                  if inverted else "INTERNAL_DIRECT_REPEAT",
                                                 view_digest))
                    if truncated: break
                if truncated: break
            boundary = False
        results[branch] = _branch(branch, evidence, comparisons,
                                  limits.max_symbol_comparisons_per_branch,
                                  limits.max_evidence_rows_per_branch,
                                  boundary=boundary, truncated=truncated,
                                  ambiguity_compatible=ambiguity_compatible,
                                  ambiguity_incompatible=ambiguity_incompatible)
        if not truncated:
            evidence.sort(key=lambda row: (
                tuple(row["source_intervals"][0]),
                tuple(row["source_intervals"][1]),
                -row["span"], row["relationship_class"], row["method_id"],
            ))
            results[branch]["evidence"] = evidence
        results[branch]["effective_limits"]["max_candidate_symbols"] = limits.max_candidate_symbols
        all_evidence.extend(evidence)
    aggregate = "COMPLETE" if all(
        r["branch_status"] in {"COMPLETED_MATCHES_REPORTED",
                               "COMPLETED_NO_MATCH_WITHIN_TESTED_POLICY"}
        for r in results.values()) else "PARTIAL"
    return {**base, "input_status": "INPUT_VALID", "aggregate_status": aggregate,
            "branches": results, "evidence": all_evidence}