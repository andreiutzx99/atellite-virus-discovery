"""Versioned, conservative provenance graph for public-virus archive records.

This module records evidence; it does not resolve biological identity from
archive accessions and does not perform acquisition or sequence analysis.
"""
import hashlib
import json
import re


SCHEMA = "public-virus-provenance-v1"
SCHEMA_VERSION = 1
MAX_ENTITIES = 20_000
MAX_RELATIONSHIPS = 50_000
MAX_EVIDENCE = 100_000
MAX_TEXT = 2_000
MAX_IDENTIFIER = 128

ENTITY_TYPES = frozenset({
    "sra_run", "sra_experiment", "sra_sample", "biosample", "sra_study",
    "bioproject", "biological_material", "viral_isolate_or_stock",
    "preparation_event", "infection_event", "sequencing_event",
    "publication",
})
RELATIONSHIP_TYPES = frozenset({
    "run_of_experiment", "experiment_uses_archive_sample", "derived_from",
    "aliquot_of", "prepared_from_stock", "technical_replicate_of",
    "biological_replicate_of", "reported_in_publication",
    "independence_assessment",
})
EVIDENCE_SOURCES = frozenset({
    "direct_archive_assertion", "publication_assertion", "curator_decision",
    "software_derived_interpretation",
})
REVIEW_STATES = frozenset({"accepted", "proposed", "rejected", "conflicting"})
INDEPENDENCE_DIMENSIONS = frozenset({
    "sequencing", "library_preparation", "biological_sample",
    "experimental_or_infection", "viral_stock_or_lineage",
    "original_viral_isolate",
})
ASSESSMENTS = frozenset({"same", "different", "unknown"})
RELATIONSHIP_ENDPOINT_TYPES = {
    "run_of_experiment": ({"sra_run"}, {"sra_experiment"}),
    "experiment_uses_archive_sample": ({"sra_experiment"}, {"sra_sample"}),
    "reported_in_publication": (ENTITY_TYPES - {"publication"}, {"publication"}),
    "prepared_from_stock": (
        {"preparation_event", "infection_event"}, {"viral_isolate_or_stock"}),
    "technical_replicate_of": (
        {"sra_run", "sequencing_event", "preparation_event"},
        {"sra_run", "sequencing_event", "preparation_event"}),
    "biological_replicate_of": (
        {"biological_material", "infection_event"},
        {"biological_material", "infection_event"}),
    "aliquot_of": (
        {"biological_material", "viral_isolate_or_stock"},
        {"biological_material", "viral_isolate_or_stock"}),
}
_AUDIT_REFERENCE_MAX = 256
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_ACCESSION_RE = re.compile(
    r"(?:[SED]R[RSXP]|SAM(?:N|D|EA)|PRJ(?:NA|EB|DB))[0-9]+\Z",
    re.IGNORECASE,
)
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class ProvenanceValidationError(ValueError):
    """Raised when a provenance document violates the v1 contract."""


def _fail(message):
    raise ProvenanceValidationError(message)


def _text(value, field, *, maximum=MAX_TEXT, allow_empty=False):
    if not isinstance(value, str):
        _fail(f"{field} must be a string")
    value = value.strip()
    if len(value) > maximum or (not value and not allow_empty):
        _fail(f"{field} must contain 1..{maximum} characters")
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        _fail(f"{field} contains control characters")
    return value


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    )


def stable_evidence_id(evidence):
    """Return a content-addressed evidence ID independent of dict key order."""
    if not isinstance(evidence, dict):
        _fail("evidence must be an object")
    payload = {key: value for key, value in evidence.items() if key != "evidence_id"}
    try:
        encoded = _canonical(payload).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProvenanceValidationError("evidence is not deterministic JSON") from exc
    return "ev-" + hashlib.sha256(encoded).hexdigest()


def _validate_evidence(item, index, *, independence_assessment=False):
    field = f"evidence[{index}]"
    if not isinstance(item, dict):
        _fail(f"{field} must be an object")
    allowed = {
        "evidence_id", "source", "evidence_type", "review_state",
        "uncertainty", "statement", "dimension", "assessment",
        "source_digest", "digest_semantics", "audit_reference",
    }
    if set(item) - allowed:
        _fail(f"{field} has unknown fields: {', '.join(sorted(set(item)-allowed))}")
    source = item.get("source")
    if not isinstance(source, str) or source not in EVIDENCE_SOURCES:
        _fail(f"{field}.source is invalid")
    review = item.get("review_state")
    if not isinstance(review, str) or review not in REVIEW_STATES:
        _fail(f"{field}.review_state is invalid")
    result = {
        "source": source,
        "evidence_type": _text(item.get("evidence_type"), f"{field}.evidence_type", maximum=128),
        "review_state": review,
        "uncertainty": _text(item.get("uncertainty"), f"{field}.uncertainty"),
        "statement": _text(item.get("statement"), f"{field}.statement"),
    }
    digest = item.get("source_digest")
    if digest is not None:
        if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
            _fail(f"{field}.source_digest must be a lowercase SHA256 digest")
        if item.get("digest_semantics") not in (
                None, "local_integrity_only_not_source_authentication"):
            _fail(f"{field}.digest_semantics is invalid")
        result["source_digest"] = digest
        result["digest_semantics"] = "local_integrity_only_not_source_authentication"
    dimension = item.get("dimension")
    assessment = item.get("assessment")
    if dimension is not None or assessment is not None:
        if not independence_assessment:
            _fail(f"{field} independence assessment fields require an independence_assessment relationship")
        if not isinstance(dimension, str) or dimension not in INDEPENDENCE_DIMENSIONS:
            _fail(f"{field}.dimension is invalid")
        if not isinstance(assessment, str) or assessment not in ASSESSMENTS:
            _fail(f"{field}.assessment is invalid")
        if source not in {"publication_assertion", "curator_decision"}:
            _fail(f"{field} independence assessment requires publication or curator evidence")
        result["dimension"] = dimension
        result["assessment"] = assessment
    elif independence_assessment:
        _fail(f"{field} independence assessment requires a valid dimension and assessment")
    reference = item.get("audit_reference")
    if reference is not None:
        if not isinstance(reference, dict):
            _fail(f"{field}.audit_reference must be an object")
        if source == "publication_assertion":
            required = {"publication_ref", "source_locator"}
            if set(reference) != required:
                _fail(f"{field}.audit_reference requires publication_ref and source_locator")
            result["audit_reference"] = {
                "publication_ref": _text(
                    reference["publication_ref"], f"{field}.audit_reference.publication_ref",
                    maximum=_AUDIT_REFERENCE_MAX),
                "source_locator": _text(
                    reference["source_locator"], f"{field}.audit_reference.source_locator",
                    maximum=_AUDIT_REFERENCE_MAX),
            }
        elif source == "curator_decision":
            required = {"reviewer_id", "decision_id", "decision_rationale"}
            if set(reference) != required:
                _fail(f"{field}.audit_reference requires reviewer_id, decision_id, and decision_rationale")
            result["audit_reference"] = {
                "reviewer_id": _text(
                    reference["reviewer_id"], f"{field}.audit_reference.reviewer_id",
                    maximum=MAX_IDENTIFIER),
                "decision_id": _text(
                    reference["decision_id"], f"{field}.audit_reference.decision_id",
                    maximum=MAX_IDENTIFIER),
                "decision_rationale": _text(
                    reference["decision_rationale"], f"{field}.audit_reference.decision_rationale"),
            }
        else:
            _fail(f"{field}.audit_reference requires publication or curator evidence")
    if (independence_assessment and review == "accepted"
            and source in {"publication_assertion", "curator_decision"}
            and "audit_reference" not in result):
        _fail(f"{field} accepted independence evidence requires an audit_reference")
    evidence_id = stable_evidence_id(result)
    supplied_id = item.get("evidence_id")
    if supplied_id is not None and supplied_id != evidence_id:
        _fail(f"{field}.evidence_id does not match its content")
    return {"evidence_id": evidence_id, **result}


def _validate_entity(item):
    if not isinstance(item, dict):
        _fail("entity must be an object")
    allowed = {
        "entity_id", "entity_type", "identifiers", "identity_state", "label",
        "identity_evidence",
    }
    if set(item) - allowed:
        _fail("entity has unknown fields")
    entity_id = item.get("entity_id")
    if not isinstance(entity_id, str) or not _IDENTIFIER_RE.fullmatch(entity_id):
        _fail("entity_id is malformed")
    entity_type = item.get("entity_type")
    if not isinstance(entity_type, str) or entity_type not in ENTITY_TYPES:
        _fail(f"entity {entity_id} has invalid entity_type")
    if entity_type == "biological_material" and _ACCESSION_RE.fullmatch(entity_id):
        _fail("archive accessions cannot identify biological material")
    identity_state = item.get("identity_state", "unknown")
    if not isinstance(identity_state, str) or identity_state not in {
            "unknown", "provisional", "confirmed"}:
        _fail(f"entity {entity_id} has invalid identity_state")
    identifiers = item.get("identifiers", {})
    if not isinstance(identifiers, dict) or len(identifiers) > 16:
        _fail(f"entity {entity_id}.identifiers must be a bounded object")
    normalized_identifiers = {}
    for namespace, value in identifiers.items():
        ns = _text(namespace, "identifier namespace", maximum=64)
        val = _text(value, f"identifier {ns}", maximum=MAX_IDENTIFIER)
        if entity_type == "biological_material" and _ACCESSION_RE.fullmatch(val):
            _fail("archive accessions cannot identify biological material")
        normalized_identifiers[ns] = val
    if entity_type == "biological_material" and identity_state == "confirmed" and not identifiers:
        _fail("confirmed biological_material requires a non-archive identifier")
    result = {
        "entity_id": entity_id, "entity_type": entity_type,
        "identity_state": identity_state,
        "identifiers": normalized_identifiers,
    }
    raw_identity_evidence = item.get("identity_evidence", [])
    if not isinstance(raw_identity_evidence, list) or len(raw_identity_evidence) > 100:
        _fail(f"entity {entity_id}.identity_evidence must be a bounded list")
    identity_evidence = [
        _validate_evidence(evidence, index)
        for index, evidence in enumerate(raw_identity_evidence)
    ]
    if identity_state == "confirmed" and entity_type == "biological_material":
        if not any(e.get("source") == "curator_decision"
                   and e.get("review_state") == "accepted"
                   for e in identity_evidence):
            _fail("confirmed biological_material requires accepted curator identity evidence")
        if any(e.get("review_state") == "conflicting" for e in identity_evidence):
            _fail("conflicting identity evidence prevents confirmed biological_material identity")
    if identity_evidence:
        evidence_ids = [e["evidence_id"] for e in identity_evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            _fail(f"entity {entity_id} contains duplicate identity evidence")
        result["identity_evidence"] = sorted(
            identity_evidence, key=lambda row: row["evidence_id"])
    if "label" in item and item["label"] is not None:
        result["label"] = _text(item["label"], f"entity {entity_id}.label")
    return result


def _validate_relationship(item, entity_map):
    if not isinstance(item, dict):
        _fail("relationship must be an object")
    allowed = {"relationship_id", "relationship_type", "subject", "object", "evidence"}
    if set(item) - allowed:
        _fail("relationship has unknown fields")
    rid = item.get("relationship_id")
    if not isinstance(rid, str) or not _IDENTIFIER_RE.fullmatch(rid):
        _fail("relationship_id is malformed")
    kind = item.get("relationship_type")
    if not isinstance(kind, str) or kind not in RELATIONSHIP_TYPES:
        _fail(f"relationship {rid} has invalid relationship_type")
    subject, obj = item.get("subject"), item.get("object")
    if not isinstance(subject, str) or not isinstance(obj, str):
        _fail(f"relationship {rid} references must be entity IDs")
    if subject not in entity_map or obj not in entity_map:
        _fail(f"relationship {rid} references a missing entity")
    if subject == obj:
        _fail(f"relationship {rid} cannot reference itself")
    endpoint_types = RELATIONSHIP_ENDPOINT_TYPES.get(kind)
    if endpoint_types:
        subject_type, object_type = entity_map[subject], entity_map[obj]
        if subject_type not in endpoint_types[0] or object_type not in endpoint_types[1]:
            _fail(
                f"relationship {rid} has incompatible endpoint types "
                f"{subject_type} -> {object_type}")
        if (kind in {"technical_replicate_of", "biological_replicate_of"}
                and subject_type != object_type):
            _fail(f"relationship {rid} replicate endpoints must have matching entity types")
    elif kind == "independence_assessment":
        if any(entity_map[entity_id] == "publication" for entity_id in (subject, obj)):
            _fail(f"relationship {rid} independence assessment cannot use a publication entity")
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        _fail(f"relationship {rid} requires evidence, including for uncertainty or conflict")
    normalized_evidence = [
        _validate_evidence(value, i, independence_assessment=(kind == "independence_assessment"))
        for i, value in enumerate(evidence)
    ]
    ids = [entry["evidence_id"] for entry in normalized_evidence]
    if len(ids) != len(set(ids)):
        _fail(f"relationship {rid} contains duplicate evidence")
    return {
        "relationship_id": rid, "relationship_type": kind,
        "subject": subject, "object": obj,
        "evidence": sorted(normalized_evidence, key=lambda row: row["evidence_id"]),
    }


def create_document(entities, relationships):
    """Validate and canonicalize a graph; archive IDs remain archive entities."""
    if not isinstance(entities, list) or len(entities) > MAX_ENTITIES:
        _fail(f"entities must be a list of at most {MAX_ENTITIES}")
    if not isinstance(relationships, list) or len(relationships) > MAX_RELATIONSHIPS:
        _fail(f"relationships must be a list of at most {MAX_RELATIONSHIPS}")
    evidence_count = 0
    for entity in entities:
        if isinstance(entity, dict) and isinstance(entity.get("identity_evidence"), list):
            evidence_count += len(entity["identity_evidence"])
            if evidence_count > MAX_EVIDENCE:
                _fail(f"evidence exceeds {MAX_EVIDENCE} records")
    for relationship in relationships:
        if isinstance(relationship, dict) and isinstance(relationship.get("evidence"), list):
            evidence_count += len(relationship["evidence"])
            if evidence_count > MAX_EVIDENCE:
                _fail(f"evidence exceeds {MAX_EVIDENCE} records")
    clean_entities = [_validate_entity(item) for item in entities]
    entity_ids = [item["entity_id"] for item in clean_entities]
    if len(entity_ids) != len(set(entity_ids)):
        _fail("duplicate entity_id")
    entity_map = {item["entity_id"]: item["entity_type"] for item in clean_entities}
    clean_relationships = [
        _validate_relationship(item, entity_map) for item in relationships
    ]
    relation_ids = [item["relationship_id"] for item in clean_relationships]
    if len(relation_ids) != len(set(relation_ids)):
        _fail("duplicate relationship_id")
    validated_evidence_count = sum(
        len(item.get("identity_evidence", [])) for item in clean_entities
    ) + sum(len(relationship["evidence"]) for relationship in clean_relationships)
    if validated_evidence_count > MAX_EVIDENCE:
        _fail(f"evidence exceeds {MAX_EVIDENCE} records")
    doc = {
        "schema": SCHEMA, "schema_version": SCHEMA_VERSION,
        "entities": sorted(clean_entities, key=lambda row: row["entity_id"]),
        "relationships": sorted(clean_relationships, key=lambda row: row["relationship_id"]),
    }
    return doc


def validate_document(document):
    """Strictly validate an existing serialized v1 document."""
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        _fail("unsupported provenance schema")
    if document.get("schema_version") != SCHEMA_VERSION:
        _fail("unsupported provenance schema_version")
    if set(document) != {"schema", "schema_version", "entities", "relationships"}:
        _fail("document has missing or unknown fields")
    canonical = create_document(document["entities"], document["relationships"])
    if canonical != document:
        _fail("document is not in canonical v1 form")
    return canonical


def serialize_document(document):
    """Return deterministic UTF-8-compatible JSON text."""
    return _canonical(validate_document(document))


def assess_independence(document, left, right, dimension):
    """Assess only direct, accepted evidence for the exact pair; never traverse."""
    if not isinstance(left, str) or not isinstance(right, str):
        _fail("independence entity IDs must be strings")
    if not isinstance(dimension, str) or dimension not in INDEPENDENCE_DIMENSIONS:
        _fail("independence assessment requires two entities and a valid dimension")
    doc = validate_document(document)
    if left == right:
        _fail("independence assessment requires two entities and a valid dimension")
    ids = {entity["entity_id"] for entity in doc["entities"]}
    if left not in ids or right not in ids:
        _fail("independence assessment references a missing entity")
    outcomes = set()
    for rel in doc["relationships"]:
        if rel["relationship_type"] != "independence_assessment":
            continue
        if {rel["subject"], rel["object"]} != {left, right}:
            continue
        for evidence in rel["evidence"]:
            if (evidence.get("dimension") == dimension
                    and evidence.get("review_state") == "accepted"
                    and evidence.get("assessment") in {"same", "different"}):
                outcomes.add(evidence["assessment"])
    if outcomes == {"same", "different"}:
        return "CONFLICTING"
    if outcomes == {"same"}:
        return "NOT_INDEPENDENT"
    if outcomes == {"different"}:
        return "INDEPENDENT"
    return "UNKNOWN"
