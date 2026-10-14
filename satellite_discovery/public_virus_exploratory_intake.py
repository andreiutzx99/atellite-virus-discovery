"""Inactive, non-authorizing review pathway for one HCoV-229E technical pilot."""
import hashlib
import json
from pathlib import Path

from . import metadata_filter, public_virus, sequence_downloader
from .public_virus_acquisition_preflight import fastq_manifest_sha256
from .public_virus_exposure_proposal import evaluate_exposure_record


POLICY_PATH = Path(__file__).with_name("public_virus_exploratory_intake_policy.json")
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
POLICY_SHA256 = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
POLICY_ID = "public-virus-exploratory-229e-gse155986-v1"
TARGET = {
    "virus": "HCoV-229E", "geo_series": "GSE155986",
    "bioproject": "PRJNA656274", "study": "SRP276927",
    "run": "SRR12424250", "experiment": "SRX8920123",
    "biosample": "SAMN15776099", "geo_sample": "GSM4718636",
}
MAX_BYTES = 1_000_000_000
APPROVAL_SCHEMA = "hcov-229e-exploratory-scientific-approval-v1"
EVIDENCE_SCHEMA = "hcov-229e-exploratory-evidence-v1"


def _digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _reason(code, detail):
    return {"code": code, "detail": detail}


def _result(status, reasons, *, evidence="NOT_ASSESSED", approval="NOT_APPROVED",
            strict_identity="NOT_ASSESSED", strict_reason=None,
            manifest_sha256=None):
    return {
        "schema": "hcov-229e-exploratory-intake-result-v1",
        "policy": {"identifier": POLICY_ID, "sha256": POLICY_SHA256},
        "result": status,
        "scope": dict(TARGET),
        "original_strict_policy": {
            "version": public_virus.POLICY["policy_version"],
            "sha256": public_virus.POLICY_SHA256,
            "identity_status": strict_identity,
            "identity_reason": strict_reason,
            "eligibility": "HELD",
        },
        "exploratory_evidence_result": evidence,
        "scientific_approval_status": approval,
        "sequence_confirmation_status": "NOT_ASSESSED",
        "fastq_manifest_sha256": manifest_sha256,
        "current_eligibility": "HELD",
        "eligibility_effect": "NONE",
        "authorizing": False,
        "acquisition_authorized": False,
        "download_enabled": False,
        "may_download": False,
        "reasons": sorted(reasons, key=lambda item: item["code"]),
        "limitations": [
            "Exposure evidence is not archive-declared virus identity or sequence confirmation.",
            "Local source and manifest digests establish consistency, not source authenticity or freshness.",
            "Scientific approval is not authenticated in this offline review pathway.",
            "Acquisition remains disabled and requires a separate future implementation and operator authorization.",
        ],
    }


def evaluate_exploratory_intake(accession_document, raw_metadata_directory,
                                evidence_document, approval_record):
    """Assess only the nominated run; never changes strict eligibility or authorizes I/O."""
    reasons = []
    strict_identity = "NOT_ASSESSED"
    strict_reason = None
    manifest_digest = None
    try:
        if not isinstance(accession_document, dict):
            raise ValueError("accession_document_malformed")
        manifest = accession_document.get("manifest")
        record = accession_document.get("record")
        if not isinstance(manifest, dict) or not isinstance(record, dict):
            raise ValueError("accession_manifest_or_record_missing")
        if any(accession_document.get(key) is True for key in
               ("authorizing", "acquisition_authorized", "download_enabled")):
            raise ValueError("accession_document_activation_claim_invalid")
        public_virus.verify_public_record(accession_document, raw_metadata_directory)
        if (manifest.get("retrieval_mode") != "archive_client"
                or manifest.get("archive_errors")
                or manifest.get("read_download_enabled") is not False
                or manifest.get("qc_enabled") is not False):
            raise ValueError("archive_metadata_not_current_validated_or_read_only")
        if (POLICY.get("policy_identifier") != POLICY_ID
                or POLICY.get("schema") != "public-virus-exploratory-intake-policy-v1"
                or POLICY.get("schema_version") != 1
                or POLICY.get("status") != "INACTIVE_REVIEW_ONLY"
                or POLICY.get("scope") != {
                    **TARGET, "max_runs": 1, "max_compressed_bytes": MAX_BYTES,
                }
                or POLICY.get("non_authorizing") != {
                    "changes_strict_public_virus_policy": False,
                    "changes_eligibility": False,
                    "sequence_confirms_virus": False,
                    "scientific_approval_is_authenticated": False,
                    "acquisition_authorized": False,
                    "download_enabled": False,
                }):
            raise ValueError("exploratory_policy_definition_invalid")
        links = {
            "run_accession": TARGET["run"],
            "experiment_accession": TARGET["experiment"],
            "biosample": TARGET["biosample"],
            "study_accession": TARGET["study"],
            "bioproject": TARGET["bioproject"],
        }
        if any(record.get(key) != value for key, value in links.items()):
            raise ValueError("exact_archive_accession_scope_mismatch")
        if record.get("public_virus", {}).get("virus") != "hcov-229e":
            raise ValueError("archive_virus_scope_mismatch")
        strict = public_virus.assess_identity(record, "hcov-229e")
        strict_identity = strict["status"]
        strict_reason = strict["reason"]
        if (record.get("public_virus") != strict
                or strict["status"] != "insufficient"
                or record.get("pilot_readiness", {}).get("status") != "held_for_identity_review"):
            raise ValueError("strict_identity_hold_not_preserved")

        assessed = metadata_filter.assess(dict(record), min_spots=0)
        technical = record.get("technical_suitability")
        if (assessed.get("exclusion_reasons")
                or not isinstance(technical, dict)
                or technical.get("status") != "eligible_for_review"
                or technical.get("reasons") != assessed.get("exclusion_reasons")
                or technical.get("warnings") != assessed.get("warnings")
                or record.get("platform") != "ILLUMINA"
                or str(record.get("library_strategy", "")).upper() != "RNA-SEQ"
                or str(record.get("library_source", "")).upper() != "TRANSCRIPTOMIC"
                or str(record.get("library_selection", "")).upper() != "CDNA"
                or record.get("layout") != "SINGLE"):
            raise ValueError("existing_library_or_technical_suitability_check_failed")

        files = sequence_downloader.files_for_run(record)
        if len(files) != 1 or sum(item["bytes"] for item in files) > MAX_BYTES:
            raise ValueError("complete_single_run_fastq_manifest_invalid_or_over_limit")
        total_bytes = sum(item["bytes"] for item in files)
        fastq_assessment = record.get("fastq_assessment")
        if (record.get("raw_read_availability") != "ena_fastq_listed"
                or not isinstance(fastq_assessment, dict)
                or fastq_assessment.get("status") != "complete_within_budget"
                or fastq_assessment.get("complete") is not True
                or fastq_assessment.get("total_bytes") != total_bytes
                or fastq_assessment.get("budget_bytes") != MAX_BYTES
                or fastq_assessment.get("fits_budget") is not True):
            raise ValueError("existing_fastq_technical_assessment_failed")
        manifest_digest = fastq_manifest_sha256(files)

        if (not isinstance(evidence_document, dict)
                or evidence_document.get("schema") != EVIDENCE_SCHEMA
                or evidence_document.get("schema_version") != 1
                or evidence_document.get("authorizing") is not False
                or evidence_document.get("acquisition_enabled") is not False
                or evidence_document.get("sequence_confirmation_status", "NOT_ASSESSED") != "NOT_ASSESSED"
                or evidence_document.get("scope") != TARGET):
            raise ValueError("evidence_document_schema_or_scope_invalid")
        evidence = evidence_document.get("exposure_record")
        if (not isinstance(evidence, dict)
                or evidence.get("current_identity_status") != "INSUFFICIENT"
                or evidence.get("sequence_confirmation_status") != "NOT_ASSESSED"
                or evidence.get("requested_eligibility") != "HELD"):
            raise ValueError("evidence_identity_or_sequence_status_invalid")
        evaluation = evaluate_exposure_record(evidence)
        if evaluation["study_reported_experimental_exposure"] != "SUPPORTED":
            raise ValueError("sample_level_exposure_or_accession_relationship_not_supported")
        if (not isinstance(evidence, dict)
                or evidence.get("accessions") != {
                    "run": TARGET["run"], "experiment": TARGET["experiment"],
                    "biosample": TARGET["biosample"], "geo_sample": TARGET["geo_sample"],
                }):
            raise ValueError("evidence_accession_scope_mismatch")
        treatment = evidence.get("sample_treatment", {})
        if (treatment.get("reported_virus") != TARGET["virus"]
                or treatment.get("condition") != "REPORTED_INFECTED"
                or treatment.get("timepoint_hours") != 24
                or not isinstance(treatment.get("archive_annotation"), str)
                or "hcov-229e" not in treatment["archive_annotation"].casefold()
                or "infect" not in treatment["archive_annotation"].casefold()):
            raise ValueError("sample_treatment_scope_mismatch")
        if (evidence_document.get("fastq_files") != files
                or evidence_document.get("fastq_manifest_sha256") != manifest_digest
                or manifest_digest != POLICY.get("expected_fastq_manifest_sha256")):
            raise ValueError("complete_fastq_manifest_or_digest_mismatch")
        if evidence_document.get("metadata_state") != "CURRENT":
            raise ValueError("archive_metadata_changed_or_withdrawn")
    except (AttributeError, KeyError, TypeError, ValueError, OSError, RecursionError) as exc:
        code = str(exc) if str(exc) else "exploratory_intake_invalid"
        reasons.append(_reason(code, "Required exact-scope evidence or a current validation check failed."))
        return _result("blocked", reasons, strict_identity=strict_identity,
                       strict_reason=strict_reason,
                       manifest_sha256=manifest_digest)

    if not isinstance(approval_record, dict):
        return _result("held_pending_approval",
                       [_reason("scientific_approval_record_missing",
                                "The exact-scope scientific approval record is required.")],
                       evidence="SUPPORTED", strict_identity=strict_identity,
                       strict_reason=strict_reason,
                       manifest_sha256=manifest_digest)
    approval_status = approval_record.get("decision_status")
    if approval_status == "APPROVED" or approval_status == "REJECTED":
        return _result("blocked",
                       [_reason("scientific_approval_claim_unsupported",
                                "This offline pathway cannot authenticate or act on approval claims.")],
                       evidence="SUPPORTED", approval="NOT_AUTHENTICATED",
                       strict_identity=strict_identity, strict_reason=strict_reason,
                       manifest_sha256=manifest_digest)
    if approval_status != "NOT_APPROVED":
        return _result("held_pending_approval",
                       [_reason("scientific_approval_pending",
                                "Owner and independent reviewer decisions have not been recorded.")],
                       evidence="SUPPORTED", strict_identity=strict_identity,
                       strict_reason=strict_reason,
                       manifest_sha256=manifest_digest)
    try:
        evidence_digest = _digest(evidence_document)
    except (TypeError, ValueError, RecursionError):
        return _result("blocked",
                       [_reason("scientific_approval_evidence_digest_invalid",
                                "The evidence document cannot be canonically hashed.")],
                       evidence="SUPPORTED", strict_identity=strict_identity,
                       strict_reason=strict_reason,
                       manifest_sha256=manifest_digest)
    if (approval_record.get("schema") != APPROVAL_SCHEMA
            or approval_record.get("schema_version") != 1
            or approval_record.get("scope") != TARGET
            or approval_record.get("policy_identifier") != POLICY_ID
            or approval_record.get("policy_sha256") != POLICY_SHA256
            or approval_record.get("evidence_document_sha256") != evidence_digest
            or approval_record.get("fastq_manifest_sha256") != manifest_digest
            or approval_record.get("purpose") != "single-run technical pilot"
            or approval_record.get("owner_decision") != "NOT_RECORDED"
            or approval_record.get("owner_identifier") is not None
            or approval_record.get("owner_rationale") is not None
            or approval_record.get("independent_reviewer_decision") != "NOT_RECORDED"
            or approval_record.get("independent_reviewer_identifier") is not None
            or approval_record.get("independent_reviewer_rationale") is not None
            or approval_record.get("decision_rationale") is not None
            or approval_record.get("decision_date") is not None
            or approval_record.get("authorizing") is not False
            or approval_record.get("acquisition_authorized") is not False):
        return _result("blocked",
                       [_reason("scientific_approval_record_binding_invalid",
                                "Approval template is not bound to this exact policy, evidence, and manifest.")],
                       evidence="SUPPORTED", strict_identity=strict_identity,
                       strict_reason=strict_reason,
                       manifest_sha256=manifest_digest)
    return _result("candidate_for_scientific_review",
                   [_reason("human_scientific_approval_pending",
                            "Owner and independent scientific review are pending; no approval is inferred.")],
                   evidence="SUPPORTED", strict_identity=strict_identity,
                   strict_reason=strict_reason,
                   manifest_sha256=manifest_digest)
