"""Non-authorizing offline evaluator for proposed reported-exposure evidence.

This module is deliberately isolated from public-virus intake and acquisition.
It consumes only supplied evidence records and cannot retrieve data or change
the existing identity/eligibility decision.
"""
from datetime import date
import re
from urllib.parse import urlparse


SCHEMA = "study-reported-experimental-exposure-evidence-v1"
SCHEMA_VERSION = 1
EVIDENCE_STATUSES = {"SUPPORTED", "INSUFFICIENT", "CONFLICTED", "NOT_ASSESSED"}
CONDITIONS = {
    "REPORTED_INFECTED", "REPORTED_MOCK", "REPORTED_UNTREATED",
    "UNRESOLVED_BASELINE", "OTHER", "UNKNOWN",
}
RELATIONSHIPS = ("run_experiment", "experiment_biosample", "biosample_geo_sample")
ACCESSION_PATTERNS = {
    "run": re.compile(r"^[SED]RR[0-9]+$"),
    "experiment": re.compile(r"^[SED]RX[0-9]+$"),
    "biosample": re.compile(r"^SAM(?:N|D|EA)[0-9]+$"),
    "geo_sample": re.compile(r"^GSM[0-9]+$"),
}


def _valid_reference(value):
    if not isinstance(value, dict):
        return False
    url = value.get("url")
    parsed = urlparse(url) if isinstance(url, str) else None
    return bool(
        parsed and parsed.scheme in {"https", "http"} and parsed.netloc
        and isinstance(value.get("retrieved_at"), str)
        and _valid_date(value["retrieved_at"])
    )


def _valid_date(value):
    try:
        date.fromisoformat(value)
        return True
    except (TypeError, ValueError):
        return False


def evaluate_exposure_record(record):
    """Classify one explicitly mapped sample; never promotes eligibility.

    Malformed, missing, stale, or contradictory evidence fails closed. This
    function does not authenticate source content or reviewer identity.
    """
    if not isinstance(record, dict):
        record = {}
    accessions = record.get("accessions")
    accessions = accessions if isinstance(accessions, dict) else {}
    run = accessions.get("run")
    experiment = accessions.get("experiment")
    biosample = accessions.get("biosample")
    geo_sample = accessions.get("geo_sample")
    references = record.get("source_references")
    references = references if isinstance(references, dict) else {}
    valid_refs = {
        key for key, value in references.items() if _valid_reference(value)
    }
    reasons = []
    conflicts = record.get("conflict_assessment")
    conflict_state = conflicts.get("status") if isinstance(conflicts, dict) else None
    metadata_state = record.get("metadata_state")
    treatment = record.get("sample_treatment")
    treatment = treatment if isinstance(treatment, dict) else {}
    condition = treatment.get("condition")
    raw_condition = treatment.get("archive_annotation")
    timepoint = treatment.get("timepoint_hours")
    virus = treatment.get("reported_virus")
    evidence_refs = treatment.get("source_references")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    has_treatment_refs = bool(evidence_refs) and all(
        isinstance(ref, str) and ref in valid_refs for ref in evidence_refs
    )
    publication_refs = treatment.get("publication_references")
    if not isinstance(publication_refs, list):
        publication_refs = []
    has_publication = bool(publication_refs) and all(
        isinstance(ref, str) and ref in valid_refs for ref in publication_refs
    )
    protocol_refs = treatment.get("protocol_references")
    if not isinstance(protocol_refs, list):
        protocol_refs = []
    has_primary_source = has_publication or (
        bool(protocol_refs) and all(
            isinstance(ref, str) and ref in valid_refs for ref in protocol_refs
        )
    )

    expected_pairs = {
        "run_experiment": (run, experiment),
        "experiment_biosample": (experiment, biosample),
        "biosample_geo_sample": (biosample, geo_sample),
    }
    links = record.get("accession_relationships")
    links = links if isinstance(links, dict) else {}
    mapping_ok = all(
        isinstance(accessions.get(field), str)
        and pattern.fullmatch(accessions[field])
        for field, pattern in ACCESSION_PATTERNS.items()
    )
    for name in RELATIONSHIPS:
        link = links.get(name)
        expected = expected_pairs[name]
        link_refs = link.get("source_references") if isinstance(link, dict) else None
        if (not isinstance(link, dict) or link.get("status") != "SUPPORTED"
                or (link.get("subject"), link.get("object")) != expected
                or not isinstance(link_refs, list) or not link_refs
                or any(not isinstance(ref, str) or ref not in valid_refs
                       for ref in link_refs)):
            mapping_ok = False
    if not mapping_ok:
        reasons.append("accession_relationships_missing_or_conflicted")

    if conflict_state == "CONFLICTED":
        exposure_status = "CONFLICTED"
        reasons.append("source_conflict_requires_human_resolution")
    elif isinstance(metadata_state, str) and metadata_state in {"CHANGED", "WITHDRAWN"}:
        exposure_status = "CONFLICTED"
        reasons.append("source_metadata_changed_or_withdrawn")
    elif conflict_state != "NONE":
        exposure_status = "INSUFFICIENT"
        reasons.append("conflict_assessment_missing_or_invalid")
    elif metadata_state != "CURRENT":
        exposure_status = "INSUFFICIENT"
        reasons.append("source_metadata_freshness_not_established")
    elif not mapping_ok:
        exposure_status = "INSUFFICIENT"
    elif not isinstance(condition, str) or condition not in CONDITIONS or condition in {"UNKNOWN", "OTHER"}:
        exposure_status = "INSUFFICIENT"
        reasons.append("experimental_condition_not_specific")
    elif condition == "REPORTED_INFECTED":
        condition_text = raw_condition.casefold() if isinstance(raw_condition, str) else ""
        if (virus != "HCoV-229E" or not isinstance(raw_condition, str)
                or "hcov-229e" not in condition_text
                or "infect" not in condition_text
                or any(term in condition_text for term in ("not infected", "uninfected", "mock"))
                or not isinstance(timepoint, int) or isinstance(timepoint, bool)
                or timepoint <= 0):
            exposure_status = "CONFLICTED"
            reasons.append("reported_infection_condition_is_inconsistent")
        elif not has_treatment_refs or not has_primary_source:
            exposure_status = "INSUFFICIENT"
            reasons.append("sample_level_treatment_or_primary_source_missing")
        else:
            exposure_status = "SUPPORTED"
    elif condition == "UNRESOLVED_BASELINE":
        if (raw_condition != "Untreated" or not isinstance(timepoint, int)
                or isinstance(timepoint, bool) or timepoint != 0):
            exposure_status = "CONFLICTED"
            reasons.append("baseline_condition_does_not_match_archive_record")
        else:
            exposure_status = "INSUFFICIENT"
            reasons.append("zero_hour_inoculation_status_unresolved")
    elif condition == "REPORTED_UNTREATED":
        exposure_status = "INSUFFICIENT"
        reasons.append("untreated_is_not_mock_or_infected")
    elif condition == "REPORTED_MOCK":
        if not isinstance(raw_condition, str) or "mock" not in raw_condition.casefold():
            exposure_status = "CONFLICTED"
            reasons.append("mock_condition_lacks_explicit_sample_annotation")
        elif not has_treatment_refs or not has_primary_source:
            exposure_status = "INSUFFICIENT"
            reasons.append("sample_level_mock_evidence_missing")
        else:
            exposure_status = "INSUFFICIENT"
            reasons.append("mock_condition_is_not_viral_exposure")
    else:
        exposure_status = "INSUFFICIENT"

    if not mapping_ok and exposure_status == "SUPPORTED":
        exposure_status = "INSUFFICIENT"

    independence = record.get("biological_independence")
    independence = independence if isinstance(independence, dict) else {}
    independence_status = independence.get("status")
    if (not isinstance(independence_status, str) or independence_status not in
            {"INDEPENDENT", "NOT_INDEPENDENT", "UNKNOWN", "CONFLICTED"}):
        independence_status = "UNKNOWN"

    review = record.get("review")
    review = review if isinstance(review, dict) else {}
    review_status = review.get("status")
    if not isinstance(review_status, str) or review_status not in {
        "NOT_REVIEWED", "PENDING", "AGREEMENT", "DISAGREEMENT", "REJECTED",
    }:
        review_status = "NOT_REVIEWED"
    reviewers = review.get("reviewers")
    reviewers = reviewers if isinstance(reviewers, list) else []
    if len({item for item in reviewers if isinstance(item, str) and item.strip()}) < 2:
        if review_status == "AGREEMENT":
            review_status = "NOT_REVIEWED"
            reasons.append("two_distinct_reviewer_records_missing")

    requested_eligibility = record.get("requested_eligibility")
    if requested_eligibility not in (None, "HELD"):
        reasons.append("proposal_cannot_change_current_eligibility")

    current_identity = record.get("current_identity_status")
    if not isinstance(current_identity, str) or current_identity not in EVIDENCE_STATUSES:
        current_identity = "NOT_ASSESSED"
    claimed_sequence = record.get("sequence_confirmation_status")
    sequence_status = "NOT_ASSESSED"
    if claimed_sequence == "SUPPORTED":
        reasons.append("sequence_confirmation_claim_not_evaluated_by_metadata_proposal")

    return {
        "run_accession": run,
        "archive_declared_identity": current_identity,
        "study_reported_experimental_exposure": exposure_status,
        "experimental_condition": (
            condition if isinstance(condition, str) and condition in CONDITIONS else "UNKNOWN"
        ),
        "sequence_confirmed_viral_presence": sequence_status,
        "biological_independence": independence_status,
        "review_status": review_status,
        "current_eligibility": "HELD",
        "eligibility_effect": "NONE",
        "authorizing": False,
        "acquisition_enabled": False,
        "reasons": sorted(set(reasons)),
    }


def evaluate_document(document):
    """Evaluate the versioned review document without external I/O."""
    if (not isinstance(document, dict) or document.get("schema") != SCHEMA
            or document.get("schema_version") != SCHEMA_VERSION
            or document.get("authorizing") is not False
            or document.get("acquisition_enabled") is not False
            or document.get("proposal_status") != "PROPOSED_NOT_APPROVED_NOT_ACTIVE"
            or document.get("evidence_vocabulary_only") is not True
            or document.get("active_eligibility_effect") != "NONE"):
        raise ValueError("unsupported or authorizing exposure evidence document")
    current_policy = document.get("current_policy")
    if (not isinstance(current_policy, dict)
            or current_policy.get("name") != "public-virus-v1"
            or current_policy.get("unchanged") is not True
            or current_policy.get("compressed_byte_limit_per_complete_run") != 1_000_000_000
            or current_policy.get("sequence_reads_downloaded_or_inspected") is not False):
        raise ValueError("proposal must preserve current policy and acquisition boundary")
    records = document.get("records")
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    catalog = document.get("source_catalog")
    retrieved_at = document.get("evidence_retrieved_at")
    if not isinstance(catalog, dict) or not _valid_date(retrieved_at):
        raise ValueError("source catalog and evidence retrieval date are required")
    expanded = []
    for record in records:
        if not isinstance(record, dict):
            expanded.append({})
            continue
        refs = {}
        accessions = record.get("accessions")
        accessions = accessions if isinstance(accessions, dict) else {}
        ref_ids = record.get("source_reference_ids")
        if not isinstance(ref_ids, list):
            ref_ids = []
        for ref_id in ref_ids:
            source = catalog.get(ref_id)
            if not isinstance(source, dict) or not isinstance(source.get("url"), str):
                continue
            try:
                url = source["url"].format(**accessions)
            except (KeyError, ValueError, IndexError):
                continue
            refs[ref_id] = {"url": url, "retrieved_at": retrieved_at}
        expanded.append({**record, "source_references": refs})
    results = [evaluate_exposure_record(record) for record in expanded]
    accessions = [result["run_accession"] for result in results]
    if len(accessions) != len(set(accessions)):
        raise ValueError("duplicate run accession")
    return results
