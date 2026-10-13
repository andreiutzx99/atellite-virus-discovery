"""Offline conservative review gate for public-virus accession packets.

This module prepares runs for human consideration only. It never downloads
reads, runs QC, authorizes acquisition, or establishes biological validation.
"""
import hashlib
import json
import math
import re
import tempfile
from pathlib import Path

from . import metadata_filter, public_virus
from .public_virus_provenance import ProvenanceValidationError, validate_document
from .sequence_downloader import files_for_run


MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_PACKET_BYTES = 256 * 1024
PILOT_BUDGET_BYTES = 1_000_000_000
SUPPORTED_STRATEGIES = {"RNA-SEQ", "WGS"}
ARCHIVE_FIELDS = {
    "run_accession": "sra_run",
    "experiment_accession": "sra_experiment",
    "sample_accession": "sra_sample",
    "biosample": "biosample",
    "study_accession": "sra_study",
    "bioproject": "bioproject",
}
ARCHIVE_IDENTIFIER_KEYS = {
    "run_accession", "sra_run", "sra_accession",
    "experiment_accession", "sra_experiment",
    "sample_accession", "sra_sample",
    "biosample", "biosample_accession",
    "study_accession", "sra_study",
    "bioproject", "bioproject_accession",
}
RUN_RE = re.compile(r"^[SED]RR[0-9]+$")
TRACEABLE_RELATION_TYPES = {"derived_from", "aliquot_of"}


class AcquisitionReviewError(ValueError):
    """Raised when a review packet itself cannot be serialized safely."""


def _bounded_json_size(value, limit=MAX_INPUT_BYTES):
    """Count compact canonical JSON bytes without constructing the whole JSON."""
    size = 0
    nodes = 0

    def add(amount):
        nonlocal size
        size += amount
        if size > limit:
            raise AcquisitionReviewError("JSON document exceeds configured size limit")

    def walk(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > 250_000 or depth > 64:
            raise AcquisitionReviewError("JSON document exceeds structural limits")
        if item is None:
            add(4)
        elif item is True:
            add(4)
        elif item is False:
            add(5)
        elif isinstance(item, str):
            if len(item) > limit:
                raise AcquisitionReviewError("JSON document exceeds configured size limit")
            try:
                item.encode("utf-8")
                encoded = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                add(len(encoded.encode("utf-8")))
            except (UnicodeEncodeError, ValueError) as exc:
                raise AcquisitionReviewError("JSON contains invalid text") from exc
        elif isinstance(item, int):
            add(len(str(item)))
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise AcquisitionReviewError("JSON numbers must be finite")
            add(len(json.dumps(item, allow_nan=False)))
        elif isinstance(item, list):
            add(2)
            for index, child in enumerate(item):
                if index:
                    add(1)
                walk(child, depth + 1)
        elif isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise AcquisitionReviewError("JSON object keys must be strings")
            add(2)
            for index, key in enumerate(sorted(item)):
                if index:
                    add(1)
                walk(key, depth + 1)
                add(1)
                walk(item[key], depth + 1)
        else:
            raise AcquisitionReviewError("Value is not JSON-compatible")

    walk(value, 0)
    return size


def _reason(code, detail):
    return {"code": code, "detail": detail}


def _initial_packet(run_accession=None, virus=None):
    return {
        "schema": "public-virus-acquisition-review-v1",
        "outcome": "held_for_review",
        "run_accession": run_accession,
        "selected_virus": virus,
        "policy": {"version": None, "sha256": None},
        "references": {"archive_accessions": {}, "provenance_entities": []},
        "identity_assessment": {
            "status": "UNKNOWN", "reason": "not_assessed",
            "provenance_supplied": False, "provenance_valid": False,
            "curator_evidence_missing": True,
        },
        "biological_independence": {
            "status": "UNKNOWN",
            "reason": "single-run review; no comparison pair was supplied",
        },
        "library_suitability": {"status": "unknown", "reasons": []},
        "fastq": {"file_count": None, "estimated_total_bytes": None},
        "pilot_budget": {
            "budget_bytes": PILOT_BUDGET_BYTES, "status": "unknown",
        },
        "curator_review_requirements": [],
        "reasons": [],
        "evidence_limitations": [
            "Technical eligibility is not biological validation.",
            "Local SHA256 consistency is integrity checking, not archive authentication.",
            "No acquisition authorization or external trust anchor is implemented.",
            "Metadata freshness cannot be independently established from this packet.",
        ],
        "download_enabled": False,
        "may_download": False,
    }


def _finish(packet, reasons, outcome=None):
    unique = {item["code"]: item for item in reasons}
    packet["reasons"] = [unique[key] for key in sorted(unique)]
    if outcome is not None:
        packet["outcome"] = outcome
    elif packet["reasons"]:
        packet["outcome"] = "held_for_review"
    else:
        packet["outcome"] = "eligible_for_curator_review"
    _bounded_json_size(packet, MAX_PACKET_BYTES)
    return packet


def _record_identity_matches(record, virus):
    expected = public_virus.assess_identity(record, virus)
    actual = record.get("public_virus")
    if not isinstance(actual, dict):
        return False
    return all(actual.get(key) == expected.get(key) for key in (
        "profile", "policy_sha256", "virus", "status", "reason",
        "archive_identity_evidence", "review_evidence",
    ))


def _verify_local_manifest(document, manifest, raw_metadata_directory):
    snapshot_index = manifest.get("snapshot_index")
    if not isinstance(snapshot_index, list):
        raise ValueError("snapshot_index_missing_or_malformed")
    for entry in snapshot_index:
        if not isinstance(entry, dict):
            raise ValueError("snapshot_index_missing_or_malformed")
        name, digest = entry.get("name"), entry.get("sha256")
        if (not isinstance(name, str) or name in {"", ".", ".."}
                or Path(name).name != name
                or not re.fullmatch(r"[A-Za-z0-9._-]{1,255}", name)
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("snapshot_index_missing_or_malformed")
    if raw_metadata_directory is None and snapshot_index:
        raise ValueError("snapshot_files_not_verified")
    if raw_metadata_directory is not None:
        root = Path(raw_metadata_directory)
        for entry in snapshot_index:
            path = root / entry["name"]
            try:
                if path.is_symlink() or not path.is_file() or path.resolve().parent != root.resolve():
                    raise ValueError("snapshot_index_missing_or_malformed")
            except OSError as exc:
                raise ValueError("snapshot_index_missing_or_malformed") from exc
        public_virus.verify_public_record(document, raw_metadata_directory)
        return
    with tempfile.TemporaryDirectory(prefix="public-virus-review-") as empty_snapshot:
        public_virus.verify_public_record(document, empty_snapshot)


def _find_archive_entities(graph, accessions):
    found = []
    for entity in graph["entities"]:
        entity_id = entity["entity_id"]
        identifiers = entity.get("identifiers", {})
        for field, expected_type in ARCHIVE_FIELDS.items():
            accession = accessions.get(field)
            if not accession or entity["entity_type"] != expected_type:
                continue
            direct_id = entity_id == accession
            mapped_id = any(
                key.casefold() in ARCHIVE_IDENTIFIER_KEYS and value == accession
                for key, value in identifiers.items()
            )
            if direct_id or mapped_id:
                found.append({
                    "entity_id": entity_id, "entity_type": entity["entity_type"],
                    "matched_accession_type": field, "accession": accession,
                })
                break
    return sorted(found, key=lambda item: (
        item["matched_accession_type"], item["entity_id"],
    ))


def _provenance_assessment(graph, archive_entities):
    archive_ids = {entity["entity_id"] for entity in archive_entities}
    linked_material_ids = set()
    conflict = False
    traceable_material_ids = set()
    for entity in graph["entities"]:
        if entity["entity_type"] == "biological_material" and any(
                evidence.get("review_state") == "conflicting"
                for evidence in entity.get("identity_evidence", [])):
            if entity["entity_id"] in linked_material_ids:
                conflict = True
    material_by_id = {
        entity["entity_id"]: entity for entity in graph["entities"]
        if entity["entity_type"] == "biological_material"
    }
    for relationship in graph["relationships"]:
        left, right = relationship["subject"], relationship["object"]
        if left in archive_ids and right in material_by_id:
            archive_id, material_id = left, right
        elif right in archive_ids and left in material_by_id:
            archive_id, material_id = right, left
        else:
            continue
        if relationship["relationship_type"] not in TRACEABLE_RELATION_TYPES:
            continue
        linked_material_ids.add(material_id)
        evidence = relationship["evidence"]
        if any(item.get("review_state") == "conflicting" for item in evidence):
            conflict = True
        material = material_by_id[material_id]
        if material.get("identity_state") == "confirmed" and any(
                item.get("source") == "curator_decision"
                and item.get("review_state") == "accepted"
                and "audit_reference" in item
                for item in material.get("identity_evidence", [])
        ) and any(
                item.get("review_state") == "accepted"
                and item.get("source") in {"curator_decision", "publication_assertion"}
                and "audit_reference" in item
                for item in evidence
        ):
            traceable_material_ids.add(material_id)
    for material_id in linked_material_ids:
        material = material_by_id[material_id]
        if any(item.get("review_state") == "conflicting"
               for item in material.get("identity_evidence", [])):
            conflict = True
    if conflict:
        status, reason = "CONFLICTING", "directly linked identity evidence is unresolved"
    elif traceable_material_ids:
        status, reason = (
            "ESTABLISHED_BY_TRACEABLE_ASSERTIONS",
            "direct archive-to-material links and identity claims carry accepted audit references",
        )
    else:
        status, reason = (
            "UNKNOWN",
            "no directly linked confirmed material has both traceable identity and relationship evidence",
        )
    relevant = sorted(
        archive_ids | linked_material_ids,
    )
    return {
        "status": status, "reason": reason,
        "curator_evidence_missing": not bool(traceable_material_ids),
    }, relevant


def build_review_packet(document, provenance_document=None, *,
                        raw_metadata_directory=None):
    """Build a deterministic, bounded review packet from an existing intake document.

    ``raw_metadata_directory`` is optional; when omitted, packets with nonempty
    archive snapshots are held because the local snapshot files cannot be checked.
    Every outcome is review-only. ``may_download`` and ``download_enabled`` are
    always false.
    """
    packet = _initial_packet()
    reasons = []
    try:
        _bounded_json_size(document)
        if not isinstance(document, dict):
            raise ValueError("accession_document_must_be_an_object")
        manifest = document.get("manifest")
        record = document.get("record")
        if not isinstance(manifest, dict) or not isinstance(record, dict):
            raise ValueError("accession_manifest_or_record_missing")
        run = record.get("run_accession")
        virus = (record.get("public_virus") or {}).get("virus")
        packet["run_accession"] = run if isinstance(run, str) else None
        packet["selected_virus"] = virus if isinstance(virus, str) else None
        packet["policy"] = {
            "version": manifest.get("profile"),
            "sha256": manifest.get("policy_sha256"),
            "current_version": public_virus.POLICY["policy_version"],
            "current_sha256": public_virus.POLICY_SHA256,
        }
        if not isinstance(run, str) or not RUN_RE.fullmatch(run):
            raise ValueError("run_accession_invalid")
        if virus not in public_virus.POLICY["viruses"]:
            _finish(packet, [_reason("unsupported_or_missing_virus",
                                     "Selected virus is missing or outside the current policy.")],
                    "excluded")
            return packet
        if manifest.get("schema") != "public-virus-accession-manifest-v1":
            raise ValueError("manifest_schema_invalid")
        if (manifest.get("profile") != public_virus.POLICY["policy_version"]
                or manifest.get("policy_sha256") != public_virus.POLICY_SHA256):
            reasons.append(_reason("stale_or_changed_policy",
                                   "Intake policy version or digest does not match the current policy."))
        if manifest.get("retrieval_mode") != "archive_client":
            reasons.append(_reason("offline_or_unverified_metadata",
                                   "Offline snapshot metadata is not eligible for technical review."))
        if manifest.get("archive_errors"):
            reasons.append(_reason("archive_metadata_incomplete",
                                   "One or more archive metadata sources failed during intake."))
        if manifest.get("read_download_enabled") is not False or manifest.get("qc_enabled") is not False:
            reasons.append(_reason("intake_boundary_inconsistent",
                                   "Intake flags must keep download and QC disabled."))
        if (manifest.get("archive_source") != "NCBI SRA / ENA"
                or manifest.get("biological_confirmation") != "not_performed"
                or manifest.get("archive_snapshot_integrity")
                != "digest_checked_against_local_manifest_only"):
            reasons.append(_reason("manifest_claims_inconsistent",
                                   "Manifest source or evidence-boundary declarations are inconsistent."))
        curator_record = record.get("curator_evidence")
        if (not isinstance(curator_record, dict)
                or curator_record.get("may_authorize") is not False):
            reasons.append(_reason("curator_authorization_flag_inconsistent",
                                   "Intake curator metadata must not grant acquisition authority."))
        try:
            _verify_local_manifest(document, manifest, raw_metadata_directory)
        except (ValueError, OSError, TypeError, KeyError) as exc:
            code = str(exc) if str(exc) in {
                "snapshot_files_not_verified", "snapshot_index_missing_or_malformed",
            } else "intake_manifest_inconsistent"
            reasons.append(_reason(code, "Local manifest, record digest, or snapshot verification failed."))
        accessions = {}
        for field, entity_type in ARCHIVE_FIELDS.items():
            value = record.get(field)
            if value is not None:
                accessions[field] = value
            if field in {"run_accession", "experiment_accession",
                         "sample_accession", "study_accession"} and not value:
                reasons.append(_reason("archive_linkage_incomplete",
                                       "Required run, experiment, sample, or study linkage is missing."))
        packet["references"]["archive_accessions"] = accessions
        try:
            public_virus._validate_archive_accessions(record)
        except (ValueError, TypeError):
            reasons.append(_reason("archive_linkage_inconsistent",
                                   "Archive accessions are malformed or use inconsistent namespaces."))
        if not _record_identity_matches(record, virus):
            reasons.append(_reason("identity_assessment_inconsistent",
                                   "Stored identity status or evidence differs from the current policy assessment."))
        identity = record.get("public_virus", {})
        identity_status = identity.get("status")
        if identity_status in {"excluded", "conflicting"}:
            reasons.append(_reason("virus_identity_excluded_or_conflicting",
                                   "Archive sample identity is excluded or conflicts with the selected virus."))
        elif identity_status != "accepted_for_technical_review":
            reasons.append(_reason("sample_virus_identity_unresolved",
                                   "Sample-level virus identity is insufficient or requires curator review."))

        assessed = metadata_filter.assess(dict(record), min_spots=0)
        technical = record.get("technical_suitability")
        if (not isinstance(technical, dict)
                or technical.get("reasons") != assessed["exclusion_reasons"]
                or technical.get("warnings") != assessed["warnings"]
                or technical.get("status") != (
                    "eligible_for_review" if not assessed["exclusion_reasons"] else "excluded"
                )):
            reasons.append(_reason("library_assessment_inconsistent",
                                   "Stored technical-suitability results do not match current intake rules."))
        library_reasons = list(assessed["exclusion_reasons"])
        warnings = set(assessed["warnings"])
        if library_reasons:
            packet["library_suitability"] = {"status": "excluded", "reasons": sorted(library_reasons)}
            reasons.append(_reason("library_unsuitable", "Intake library exclusions apply."))
        elif (record.get("platform") != "ILLUMINA"
              or (record.get("library_strategy") or "").upper() not in SUPPORTED_STRATEGIES
              or warnings.intersection({
                  "library_strategy_requires_review", "capture_bias_requires_review",
                  "library_selection_bias_possible", "platform_requires_review",
                  "sequencing_depth_unknown",
              })):
            packet["library_suitability"] = {
                "status": "held", "reasons": sorted(warnings),
            }
            reasons.append(_reason("library_requires_review",
                                   "Library strategy, platform, or selection is not in the conservative pilot set."))
        else:
            packet["library_suitability"] = {"status": "suitable_for_review", "reasons": []}

        try:
            files = files_for_run(record)
            total_bytes = sum(item["bytes"] for item in files)
            packet["fastq"] = {
                "file_count": len(files), "estimated_total_bytes": total_bytes,
            }
            packet["pilot_budget"] = {
                "budget_bytes": PILOT_BUDGET_BYTES,
                "status": "within_budget" if total_bytes <= PILOT_BUDGET_BYTES else "over_budget",
            }
            if record.get("raw_read_availability") != "ena_fastq_listed":
                raise ValueError("FASTQ availability flag is inconsistent")
            fastq = record.get("fastq_assessment")
            expected_status = (
                "complete_within_budget" if total_bytes <= PILOT_BUDGET_BYTES
                else "complete_over_budget"
            )
            if (not isinstance(fastq, dict) or fastq.get("status") != expected_status
                    or fastq.get("complete") is not True
                    or fastq.get("total_bytes") != total_bytes
                    or fastq.get("budget_bytes") != PILOT_BUDGET_BYTES
                    or fastq.get("fits_budget") != (total_bytes <= PILOT_BUDGET_BYTES)
                    or fastq.get("reasons") != (
                        [] if total_bytes <= PILOT_BUDGET_BYTES
                        else ["complete_fastq_exceeds_1gb_budget"]
                    )):
                raise ValueError("FASTQ assessment is inconsistent")
            if total_bytes > PILOT_BUDGET_BYTES:
                reasons.append(_reason("fastq_over_pilot_budget",
                                       "Complete FASTQ size exceeds the 1 GB decimal pilot budget."))
                packet["pilot_budget"]["status"] = "excluded"
        except (ValueError, TypeError, KeyError):
            packet["fastq"] = {"file_count": None, "estimated_total_bytes": None}
            packet["pilot_budget"] = {
                "budget_bytes": PILOT_BUDGET_BYTES, "status": "unknown",
            }
            reasons.append(_reason("fastq_metadata_missing_or_inconsistent",
                                   "Complete FASTQ file set, sizes, availability, or assessment is missing or inconsistent."))

        if provenance_document is not None:
            packet["identity_assessment"]["provenance_supplied"] = True
            try:
                _bounded_json_size(provenance_document)
                graph = validate_document(provenance_document)
            except (AcquisitionReviewError, ProvenanceValidationError, TypeError, ValueError):
                packet["identity_assessment"]["provenance_valid"] = False
                reasons.append(_reason("provenance_invalid",
                                       "Supplied provenance graph failed canonical validation."))
            else:
                packet["identity_assessment"]["provenance_valid"] = True
                archive_entities = _find_archive_entities(graph, accessions)
                assessment, relevant_ids = _provenance_assessment(graph, archive_entities)
                entities_by_id = {row["entity_id"]: row for row in graph["entities"]}
                packet["references"]["provenance_entities"] = [
                    {
                        "entity_id": entity_id,
                        "entity_type": entities_by_id[entity_id]["entity_type"],
                    }
                    for entity_id in relevant_ids
                ]
                packet["identity_assessment"].update(assessment)
                if assessment["status"] == "CONFLICTING":
                    reasons.append(_reason("provenance_identity_conflicting",
                                           "Directly linked provenance contains unresolved identity conflict."))
        else:
            packet["identity_assessment"]["provenance_supplied"] = False
            packet["identity_assessment"]["provenance_valid"] = False
            packet["identity_assessment"]["status"] = "UNKNOWN"
            packet["identity_assessment"]["reason"] = "no provenance graph supplied"
            packet["identity_assessment"]["curator_evidence_missing"] = True

        packet["curator_review_requirements"] = sorted({
            reason["code"] for reason in reasons
        })
        if packet["identity_assessment"]["status"] == "UNKNOWN":
            packet["curator_review_requirements"].extend([
                "traceable_biological_material_identity",
            ])
        packet["curator_review_requirements"].append(
            "pairwise_biological_independence_evidence"
        )
        packet["curator_review_requirements"] = sorted(
            set(packet["curator_review_requirements"])
        )
        outcome = None
        if any(reason["code"] in {
            "unsupported_or_missing_virus", "virus_identity_excluded_or_conflicting",
            "library_unsuitable", "fastq_over_pilot_budget",
        } for reason in reasons):
            outcome = "excluded"
        return _finish(packet, reasons, outcome)
    except (AcquisitionReviewError, ValueError, TypeError, KeyError, RecursionError):
        return _finish(packet, [_reason(
            "malformed_or_oversized_input",
            "Accession input is malformed, non-canonical, or exceeds the review-gate size bound.",
        )], "held_for_review")


def serialize_review_packet(packet):
    """Serialize a bounded review result as deterministic compact JSON."""
    _bounded_json_size(packet, MAX_PACKET_BYTES)
    return json.dumps(
        packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )
