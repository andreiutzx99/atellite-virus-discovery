"""Frozen M8 BLASTN settings only; this module does not run searches.

The supported runtime is intentionally limited to the independently verified
NCBI Linux x86-64 archive. Other platforms must be reported as
DEPENDENCY_UNAVAILABLE until they are validated separately.
"""

BLAST_PROFILE_ID = "m8-blastn-linux-x86_64-v1"
BLAST_RELEASE = "2.17.0+"
BLAST_ARCHIVE_URL = (
    "https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.17.0/"
    "ncbi-blast-2.17.0+-x64-linux.tar.gz"
)
BLAST_ARCHIVE_MD5 = "bdec166721de3b55f90a3badc83538e8"
BLAST_ARCHIVE_SHA256 = (
    "3888112d8207831aa47371d93583c601f058f88b5db22dc782438b039a3a411b"
)
BLASTN_BINARY_SHA256 = (
    "33b64bc67d3149cee2459b2f7766b363323df632cf12c099546de00aea9698b5"
)
MAKEBLASTDB_BINARY_SHA256 = (
    "c1ffdcf6f15d1d8d75377cc9f37afa42bc9fa06678903bad77c2641e60778fce"
)

QUERY_LENGTH_CUTOFF = 50
MAX_TARGET_SEQS = 1000
MAX_HSPS = 1000
NUM_THREADS = 1
EVALUE = "1000"
STRAND = "both"
SOFT_MASKING = "true"
OUTFMT_FIELDS = (
    "qseqid", "sseqid", "pident", "length", "mismatch", "gapopen",
    "qstart", "qend", "sstart", "send", "evalue", "bitscore",
    "qlen", "slen", "sstrand",
)
OUTFMT = "6 " + " ".join(OUTFMT_FIELDS)
MASKING_BRANCHES = {
    "dust_masked": "yes",
    "dust_unmasked": "no",
}
TASK_SETTINGS = {
    "blastn-short": {
        "word_size": 7,
        "reward": 1,
        "penalty": -3,
        "gapopen": 5,
        "gapextend": 2,
    },
    "blastn": {
        "word_size": 11,
        "reward": 2,
        "penalty": -3,
        "gapopen": 5,
        "gapextend": 2,
    },
}


def task_for_query_length(length):
    """Select a BLAST task; the selector is not an eligibility threshold."""
    if type(length) is not int or length < 1:
        raise ValueError("Sequence length must be a positive integer")
    return "blastn-short" if length < QUERY_LENGTH_CUTOFF else "blastn"


def method_applicability(query_length):
    """Return a technical seed-window result without changing eligibility."""
    task = task_for_query_length(query_length)
    word_size = TASK_SETTINGS[task]["word_size"]
    if query_length < word_size:
        return {
            "informative": False,
            "reason": "QUERY_SHORTER_THAN_WORD_SIZE",
            "task": task,
            "word_size": word_size,
        }
    return {
        "informative": True,
        "reason": None,
        "task": task,
        "word_size": word_size,
    }


def is_supported_runtime(system, machine, blastn_version, makeblastdb_version):
    """Return whether the exact independently tested toolchain is available."""
    return (
        isinstance(system, str)
        and system.lower() == "linux"
        and isinstance(machine, str)
        and machine.lower() == "x86_64"
        and blastn_version == BLAST_RELEASE
        and makeblastdb_version == BLAST_RELEASE
    )


def build_blastn_args(
    executable,
    query_path,
    database_prefix,
    output_path,
    query_length,
    masking_branch,
    *,
    max_target_seqs=MAX_TARGET_SEQS,
    max_hsps=MAX_HSPS,
):
    """Build an argv list from the frozen profile; does not spawn a process."""
    if masking_branch not in MASKING_BRANCHES:
        raise ValueError(f"Unknown M8 masking branch: {masking_branch!r}")
    for value, label in (
        (max_target_seqs, "max_target_seqs"),
        (max_hsps, "max_hsps"),
    ):
        if type(value) is not int or value < 1:
            raise ValueError(f"{label} must be a positive integer")

    task = task_for_query_length(query_length)
    settings = TASK_SETTINGS[task]
    return [
        str(executable),
        "-query", str(query_path),
        "-db", str(database_prefix),
        "-task", task,
        "-strand", STRAND,
        "-dust", MASKING_BRANCHES[masking_branch],
        "-soft_masking", SOFT_MASKING,
        "-word_size", str(settings["word_size"]),
        "-reward", str(settings["reward"]),
        "-penalty", str(settings["penalty"]),
        "-gapopen", str(settings["gapopen"]),
        "-gapextend", str(settings["gapextend"]),
        "-evalue", EVALUE,
        "-max_target_seqs", str(max_target_seqs),
        "-max_hsps", str(max_hsps),
        "-num_threads", str(NUM_THREADS),
        "-outfmt", OUTFMT,
        "-out", str(output_path),
    ]


def output_cap_reached(rows, *, max_target_seqs=MAX_TARGET_SEQS,
                       max_hsps=MAX_HSPS):
    """Conservatively detect a branch that reaches either configured cap.

    A cap hit is treated as truncation even when the returned output happens to
    contain the entire set of biologically possible hits.
    """
    for value, label in (
        (max_target_seqs, "max_target_seqs"),
        (max_hsps, "max_hsps"),
    ):
        if type(value) is not int or value < 1:
            raise ValueError(f"{label} must be a positive integer")

    per_query = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Normalized BLAST rows must be mappings")
        query_id = row.get("query_id")
        reference_id = row.get("reference_id")
        if not isinstance(query_id, str) or not query_id:
            raise ValueError("Normalized BLAST rows require query_id")
        if not isinstance(reference_id, str) or not reference_id:
            raise ValueError("Normalized BLAST rows require reference_id")
        by_reference = per_query.setdefault(query_id, {})
        by_reference[reference_id] = by_reference.get(reference_id, 0) + 1

    return any(
        len(by_reference) >= max_target_seqs
        or any(hsp_count >= max_hsps for hsp_count in by_reference.values())
        for by_reference in per_query.values()
    )