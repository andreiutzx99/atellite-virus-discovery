"""Deterministic, six-frame M9 ORF hypotheses.

This module deliberately produces technical hypotheses only.  It does not
select a biological coding model, infer expression, or classify a candidate.
"""

import hashlib
import json


TRANSLATION_TABLE = 1
POLICY_ID = "m9-orf-enumerator-v1"
START_CODONS = ("ATG",)
STOP_CODONS = ("TAA", "TAG", "TGA")
_DNA = frozenset("ACGTURYSWKMBDHVN")
_COMPLEMENT = str.maketrans(
    "ACGTURYSWKMBDHVNacgturyswkmbdhvn",
    "TGCAAYRSWMKVHDBNtgcaayrswmkvhdbn",
)


def _standard_table():
    rows = {
        "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L",
        "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S",
        "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*",
        "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W",
        "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
        "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
        "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
        "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
        "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M",
        "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T",
        "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K",
        "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R",
        "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
        "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
        "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
        "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
    }
    return rows


_TABLE = _standard_table()


def _digest(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _reverse_complement(sequence):
    return sequence.translate(_COMPLEMENT)[::-1]


def _codon_residue(codon):
    """Translate an oriented, T-view codon without resolving ambiguity."""
    return _TABLE.get(codon, "X")


def _original_span(start, end, strand, length):
    return [start, end] if strand == "+" else [length - end, length - start]


def _stable_id(candidate_id, sequence_id, strand, frame, start, end, kind):
    material = json.dumps(
        [candidate_id, sequence_id, strand, frame, start, end, kind, POLICY_ID,
         TRANSLATION_TABLE, START_CODONS, STOP_CODONS],
        separators=(",", ":"), ensure_ascii=True,
    )
    return "orf-" + _digest(material)[:32]


def _row(
    *, sequence, source_oriented, translation_oriented, candidate_id, sequence_id,
    sequence_sha256,
    molecule_type, strand, frame, start, end, kind, stop_start=None,
    stop_end=None, stop_codon=None, initiator=False, length=None,
):
    peptide = []
    ambiguous = []
    codons = []
    for position in range(start, end - 2, 3):
        source_codon = source_oriented[position:position + 3]
        translation_codon = translation_oriented[position:position + 3]
        residue = (
            "M" if initiator and position == start
            else _codon_residue(translation_codon)
        )
        peptide.append(residue)
        span = _original_span(position, position + 3, strand, length)
        codons.append({
            "codon": source_codon,
            "source_codon": source_codon,
            "translation_codon": translation_codon,
            "oriented_position": position,
            "original_span": span,
        })
        if residue == "X":
            ambiguous.append({
                "codon": source_codon,
                "source_codon": source_codon,
                "translation_codon": translation_codon,
                "oriented_position": position,
                "original_span": span,
            })
    protein = "".join(peptide)
    if not protein:
        return None
    peptide_span = _original_span(start, end, strand, length)
    full_end = stop_end if stop_end is not None else end
    original_span = _original_span(start, full_end, strand, length)
    row = {
        "orf_id": _stable_id(
            candidate_id, sequence_id, strand, frame, start, end, kind,
        ),
        "candidate_id": candidate_id,
        "sequence_id": sequence_id,
        "source_sequence_sha256": sequence_sha256,
        "source_sequence_length": length,
        "strand": strand,
        "frame": frame,
        "coordinates": original_span,
        "original_span": original_span,
        "oriented_span": [start, end],
        "partial": kind != "complete",
        "partial_5_prime": kind == "5_prime_partial",
        "partial_3_prime": kind == "3_prime_partial",
        "start_codon": source_oriented[start:start + 3] if initiator else None,
        "start_translation_codon": (
            translation_oriented[start:start + 3] if initiator else None
        ),
        "start_coordinates": (
            _original_span(start, start + 3, strand, length)
            if initiator else None
        ),
        "stop_codon": stop_codon,
        "stop_coordinates": (
            _original_span(stop_start, stop_end, strand, length)
            if stop_start is not None else None
        ),
        "stop_span": (
            _original_span(stop_start, stop_end, strand, length)
            if stop_start is not None else None
        ),
        "peptide_span": peptide_span,
        "protein_sequence": protein,
        "protein_sha256": _digest(protein),
        "protein_length": len(protein),
        "ambiguous_source_codons": ambiguous,
        "ambiguous_codon_positions": [item["oriented_position"] for item in ambiguous],
        "source_codons": codons,
        "translation_table": TRANSLATION_TABLE,
        "molecule_type": molecule_type,
        "derivation_policy": POLICY_ID,
    }
    return row


def _frame_rows(sequence, candidate_id, sequence_id, sequence_sha256,
                molecule_type, strand, frame):
    source_oriented = sequence if strand == "+" else _reverse_complement(sequence)
    translation_oriented = source_oriented.upper().replace("U", "T")
    length = len(sequence)
    first_stop = None
    starts = []
    codon_positions = list(range(frame, len(source_oriented) - 2, 3))
    for position in codon_positions:
        codon = translation_oriented[position:position + 3]
        if codon in START_CODONS:
            starts.append(position)
        if first_stop is None and codon in STOP_CODONS:
            first_stop = (position, position + 3, codon)

    rows = []
    for start in starts:
        downstream_stop = next(
            (position for position in codon_positions
             if position > start
             and translation_oriented[position:position + 3] in STOP_CODONS),
            None,
        )
        if downstream_stop is not None:
            stop = (
                downstream_stop, downstream_stop + 3,
                translation_oriented[downstream_stop:downstream_stop + 3],
            )
            item = _row(
                sequence=sequence, source_oriented=source_oriented,
                translation_oriented=translation_oriented,
                candidate_id=candidate_id,
                sequence_id=sequence_id, sequence_sha256=sequence_sha256,
                molecule_type=molecule_type, strand=strand, frame=frame,
                start=start, end=stop[0], kind="complete",
                stop_start=stop[0], stop_end=stop[1],
                stop_codon=source_oriented[stop[0]:stop[1]],
                initiator=True, length=length,
            )
        else:
            final = frame + ((len(source_oriented) - frame) // 3) * 3
            item = _row(
                sequence=sequence, source_oriented=source_oriented,
                translation_oriented=translation_oriented,
                candidate_id=candidate_id,
                sequence_id=sequence_id, sequence_sha256=sequence_sha256,
                molecule_type=molecule_type, strand=strand, frame=frame,
                start=start, end=final, kind="3_prime_partial",
                initiator=True, length=length,
            )
        if item is not None:
            rows.append(item)

    if first_stop is not None and not any(start < first_stop[0] for start in starts):
        item = _row(
            sequence=sequence, source_oriented=source_oriented,
            translation_oriented=translation_oriented,
            candidate_id=candidate_id,
            sequence_id=sequence_id, sequence_sha256=sequence_sha256,
            molecule_type=molecule_type, strand=strand, frame=frame,
            start=frame, end=first_stop[0], kind="5_prime_partial",
            stop_start=first_stop[0], stop_end=first_stop[1],
            stop_codon=source_oriented[first_stop[0]:first_stop[1]], length=length,
        )
        if item is not None:
            rows.append(item)
    return rows


def enumerate_orfs(
    sequence, *, candidate_id, sequence_id, sequence_sha256, molecule_type=None,
):
    """Enumerate all non-empty baseline ORF hypotheses in stable order."""
    if not isinstance(sequence, str) or not sequence:
        raise ValueError("sequence must be non-empty text")
    if any(letter.upper() not in _DNA for letter in sequence):
        raise ValueError("sequence contains a non-IUPAC nucleotide")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise ValueError("candidate_id must be non-empty text")
    if not isinstance(sequence_id, str) or not sequence_id:
        raise ValueError("sequence_id must be non-empty text")
    if molecule_type is not None and (
        not isinstance(molecule_type, str) or not molecule_type
    ):
        raise ValueError("molecule_type must be text or null")
    if not isinstance(sequence_sha256, str) or sequence_sha256 != _digest(sequence):
        raise ValueError("sequence_sha256 does not match the exact sequence letters")

    view = sequence.upper().replace("U", "T")
    u_to_t_applied = "U" in sequence.upper()
    rows = []
    for strand in ("+", "-"):
        for frame in range(3):
            rows.extend(_frame_rows(
                sequence, candidate_id, sequence_id, sequence_sha256,
                molecule_type, strand, frame,
            ))
    rows.sort(key=lambda row: (
        0 if row["strand"] == "+" else 1, row["frame"],
        row["oriented_span"][0], row["oriented_span"][1],
        row["partial_5_prime"], row["partial_3_prime"], row["orf_id"],
    ))
    return {
        "schema": "m9-orf-enumeration-v1",
        "policy": {
            "id": POLICY_ID,
            "translation_table": TRANSLATION_TABLE,
            "start_codons": list(START_CODONS),
            "stop_codons": list(STOP_CODONS),
            "strands": ["+", "-"],
            "frames": [0, 1, 2],
            "coordinate_system": "zero-based-half-open-original-sequence",
            "partial_boundary_policy": {
                "five_prime": "leading_complete_codons_through_first_stop_without_prior_start",
                "three_prime": "each_start_without_downstream_stop_to_final_complete_codon",
            },
            "ambiguous_codon_policy": "X; never start or stop",
            "minimum_length": None,
            "topology": "linear",
        },
        "candidate_id": candidate_id,
        "sequence_id": sequence_id,
        "sequence": sequence,
        "sequence_sha256": sequence_sha256,
        "sequence_length": len(sequence),
        "molecule_type": molecule_type,
        "translation_view": {
            "source_alphabet": "RNA" if "U" in sequence.upper() else "DNA_OR_UNKNOWN",
            "u_to_t": "U interpreted as T in temporary translation view",
            "u_to_t_applied": u_to_t_applied,
            "normalization_applied": u_to_t_applied,
            "sequence": view,
            "sha256": _digest(view),
        },
        "trailing_nucleotides": {
            strand: {str(frame): (len(view) - frame) % 3 for frame in range(3)}
            for strand in ("+", "-")
        },
        "derivation_policy": POLICY_ID,
        "translation_table": TRANSLATION_TABLE,
        "status": "ORF_PREDICTED" if rows else "NO_ORF_PREDICTED_WITHIN_POLICY",
        "expected_orf_count": len(rows),
        "observed_orf_count": len(rows),
        "orfs": rows,
    }