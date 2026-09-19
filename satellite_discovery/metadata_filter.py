"""Suitability for future read analysis, never a satellite confidence score."""


def assess(row, min_spots=1_000_000):
    excluded, warnings = [], []
    strategy = (row.get("library_strategy") or "").upper()
    if strategy in {"AMPLICON", "CHIP-SEQ", "ATAC-SEQ", "BISULFITE-SEQ"}:
        excluded.append("library_strategy_unsuitable_for_unbiased_discovery")
    elif strategy not in {"RNA-SEQ", "WGS", "METAGENOMIC", "WXS"}:
        warnings.append("library_strategy_requires_review")
    if strategy == "WXS":
        warnings.append("capture_bias_requires_review")
    if (row.get("library_selection") or "").upper() in {"PCR", "RANDOM PCR", "C_DNA", "POLYA"}:
        warnings.append("library_selection_bias_possible")
    if row.get("total_spots") is None:
        warnings.append("sequencing_depth_unknown")
    elif row["total_spots"] < min_spots:
        excluded.append("below_minimum_sequencing_spots")
    if row.get("platform") != "ILLUMINA":
        warnings.append("platform_requires_review")
    if row.get("raw_read_availability") != "ena_fastq_listed":
        warnings.append("raw_read_access_requires_verification_or_sra_toolkit")
    for key in ("host", "tissue", "country", "collection_date", "bioproject"):
        if not row.get(key):
            warnings.append(key + "_missing")
    warnings.append("helper_infection_not_verified_from_reads")
    if row.get("retrieval_cohort") == "study_context":
        warnings.append("study_context_sample_not_a_confirmed_negative_control")
    row.update({"selection": "excluded" if excluded else "eligible_for_review",
                "exclusion_reasons": excluded, "warnings": warnings})
    return row
