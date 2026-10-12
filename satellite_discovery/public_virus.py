"""Opt-in, metadata-only intake for the public-virus-v1 profile."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .database_query import Client
from .metadata import parse_packages, enrich_ena
from .metadata_filter import assess
from .model_scope import mentions
from .sequence_downloader import files_for_run

POLICY_PATH = Path(__file__).with_name("public_virus_policy.json")
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
POLICY_SHA256 = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
RUN_ACCESSION = re.compile(r"^[SED]RR[0-9]+$")
ACCESSION_PATTERNS = {
    "run_accession": RUN_ACCESSION,
    "experiment_accession": re.compile(r"^[SED]RX[0-9]+$"),
    "sample_accession": re.compile(r"^[SED]RS[0-9]+$"),
    "study_accession": re.compile(r"^[SED]RP[0-9]+$"),
    "biosample": re.compile(r"^SAM[END][0-9]+$"),
    "bioproject": re.compile(r"^PRJ(?:NA|EB|DB)[0-9]+$"),
}
TYPED_PATHOGEN_KEYS = {
    "pathogen", "virus", "virus species", "infecting virus", "viral species",
}
PATHOGEN_SEPARATORS = re.compile(r"\s*(?:\+|;|,|/|\band\b)\s*", re.I)
STRAIN_QUALIFIER = re.compile(
    r"^(?:strain|isolate|variant|lineage|serotype|subtype|genotype|clade|mutant)\b",
    re.I,
)


def assess_identity(row, virus):
    if virus not in POLICY["viruses"]:
        raise ValueError("Unsupported public-virus-v1 virus")
    item = POLICY["viruses"][virus]
    attrs = row.get("attributes")
    if attrs is None:
        attrs = {}
    if not isinstance(attrs, dict):
        raise ValueError("Sample attributes must be a dictionary")
    attribute_entries = row.get("public_virus_attribute_entries")
    if attribute_entries is None:
        attribute_entries = [{"key": key, "value": value} for key, value in attrs.items()]
    if not isinstance(attribute_entries, list) or any(
            not isinstance(entry, dict) or "key" not in entry or "value" not in entry
            for entry in attribute_entries):
        raise ValueError("Public-virus sample attribute evidence must be a list of key/value records")
    context = "\n".join(str(row.get(k) or "") for k in
                        ("organism", "sample_title", "experiment_title", "study_title"))
    context += "\n" + "\n".join(str(entry["value"]) for entry in attribute_entries)
    excluded = [term for term in POLICY["excluded_mentions"] if mentions(context, term)]
    terms = item["identity_terms"]
    organism = str(row.get("organism") or "")
    organism_evidence = [term for term in terms if mentions(organism, term)]
    accepted_keys = {_normalize_attribute_key(k) for k in item["identity_attribute_keys"]}
    attribute_evidence = [
        {"key": str(entry["key"]), "term": term}
        for entry in attribute_entries
        for key, value in [(entry["key"], entry["value"])]
        if _normalize_attribute_key(key) in accepted_keys
        for term in terms if mentions(str(value), term)
    ]
    review_evidence = []
    review_terms = POLICY.get("review_mentions", [])
    def add_review_text(field, value):
        for term in review_terms:
            if mentions(str(value), term):
                review_evidence.append({
                    "field": field, "term": term,
                    "reason": "mixed_or_modified_sample_metadata",
                })
    sample_context_fields = ("organism", "sample_title", "experiment_title")
    for field in sample_context_fields:
        add_review_text(field, row.get(field) or "")
    for entry in attribute_entries:
        key, value = entry["key"], entry["value"]
        add_review_text("attribute:" + str(key), value)
    # Study titles are broad context, not sample-level evidence. Only explicit
    # mixed/modified terms there trigger review; ordinary multi-virus discussion
    # does not prove a mixed sample.
    study_title = str(row.get("study_title") or "")
    add_review_text("study_title", study_title)
    flag_keys = {
        "infection type", "infection", "coinfection", "co infection",
        "mixed infection", "mixed infection status", "sample composition",
    }
    flag_values = {"yes", "true", "1", "mixed", "coinfection", "co-infection",
                   "co infection", "mixed infection", "multiple infections"}
    for entry in attribute_entries:
        key, value = entry["key"], entry["value"]
        normalized_key = _normalize_attribute_key(key)
        normalized_value = str(value).strip().casefold()
        if normalized_key in flag_keys and (
                normalized_value in flag_values or
                any(mentions(normalized_value, term) for term in review_terms)):
            review_evidence.append({
                "field": "attribute:" + str(key), "term": "explicit_mixed_flag",
                "reason": "explicit_mixed_flag", "value": str(value),
            })
        if normalized_key in {"additional pathogen", "co infecting pathogen",
                              "coinfecting pathogen", "secondary pathogen"} and normalized_value:
            review_evidence.append({
                "field": "attribute:" + str(key), "term": "additional_pathogen",
                "reason": "explicit_additional_pathogen", "value": str(value),
            })
    # An explicitly typed pathogen/virus field naming multiple agents is
    # ambiguous even when the second agent is outside this two-virus profile.
    typed_values = {}
    for entry in attribute_entries:
        key, value = entry["key"], entry["value"]
        normalized_key = _normalize_attribute_key(key)
        if normalized_key in TYPED_PATHOGEN_KEYS and str(value).strip():
            typed_values.setdefault(normalized_key, []).append(str(value).strip())
            if _explicit_multiple_pathogens(str(value)):
                review_evidence.append({
                    "field": "attribute:" + str(key),
                    "term": "multiple_pathogens_in_typed_field",
                    "reason": "explicit_multiple_pathogens",
                    "value": str(value),
                })
    for normalized_key, values in typed_values.items():
        if len(set(value.casefold() for value in values)) > 1 and _explicit_multiple_pathogens(
                " ; ".join(values)):
            review_evidence.append({
                "field": "attribute:" + normalized_key,
                "term": "multiple_pathogens_in_typed_field",
                "reason": "conflicting_repeated_typed_pathogen_values",
                "value": values,
            })
    if excluded:
        status, reason = "excluded", "excluded_pathogen_mentioned_in_metadata"
    else:
        # Sample taxonomy can establish virus identity only when it names the virus;
        # host taxonomy and free-text titles never do.
        other_virus_evidence = []
        for other_key, other in POLICY["viruses"].items():
            if other_key == virus:
                continue
            if any(mentions(organism, term) for term in other["identity_terms"]) or any(
                    _normalize_attribute_key(key) in accepted_keys and
                    any(mentions(str(value), term) for term in other["identity_terms"])
                    for key, value in attrs.items()):
                other_virus_evidence.append(other_key)
        if review_evidence:
            status, reason = "review_required", "mixed_or_modified_sample_metadata_requires_review"
        elif (organism_evidence or attribute_evidence) and other_virus_evidence:
            status, reason = "conflicting", "multiple_public_virus_identities"
        elif other_virus_evidence:
            status, reason = "conflicting", "archive_identity_conflicts_with_selected_virus"
        elif organism_evidence or attribute_evidence:
            status, reason = "accepted_for_technical_review", "archive_sample_level_virus_identity"
        else:
            status, reason = "insufficient", "sample_level_virus_identity_missing"
    return {
        "profile": POLICY["policy_version"], "policy_sha256": POLICY_SHA256,
        "virus": virus, "status": status, "reason": reason,
        "archive_identity_evidence": {
            "organism_terms": organism_evidence if not excluded else [],
            "attributes": attribute_evidence if not excluded else [],
        },
        "review_evidence": review_evidence,
        "strain": _attribute_value(attrs, {"strain", "virus strain", "viral strain", "strain designation"}),
        "isolate": _attribute_value(attrs, {"isolate", "isolate name"}),
        "laboratory_stock_catalogue": _attribute_value(
            attrs, {"stock", "stock number", "catalogue", "catalog", "catalogue number", "catalog number"}),
        "archive_center_name": row.get("archive_center_name") or row.get("laboratory") or "UNKNOWN",
        "experimental_laboratory": _attribute_value(
            attrs, {"experimental laboratory", "sample preparation laboratory", "laboratory that prepared sample"}),
        "preparation": _attribute_value(attrs, {"preparation", "preparation method"}),
        "passage": _attribute_value(attrs, {"passage", "passage history"}),
        "batch": _attribute_value(attrs, {"batch", "preparation batch"}),
        "replicate": _replicate_metadata(attrs),
        "uncertainty": "Archive metadata screening only; not biological confirmation or infection evidence.",
    }


def _normalize_attribute_key(key):
    return " ".join(str(key).strip().casefold().replace("_", " ").replace("-", " ").split())


def _explicit_multiple_pathogens(value):
    """Detect explicit typed lists without treating strain labels as pathogens."""
    if not PATHOGEN_SEPARATORS.search(value):
        return False
    # A common notation lists strains/isolates of the same virus with a slash;
    # do not turn the suffix labels into a second pathogen.
    if re.search(
            r"\b(?:strain|isolate|variant|lineage)\s+[A-Za-z0-9.-]+\s*"
            r"(?:[/,;+]|\band\b)\s*(?:(?:strain|isolate|variant|lineage)\s+)?"
            r"[A-Za-z0-9.-]+\s*$", value, re.I):
        return False
    segments = [part.strip(" \t\r\n()[]{}") for part in PATHOGEN_SEPARATORS.split(value)]
    segments = [part for part in segments if part]
    if len(segments) < 2:
        # A dangling delimiter in a typed identity field is unresolved input.
        return bool(segments)
    meaningful = [part for part in segments if not STRAIN_QUALIFIER.match(part)]
    if len(meaningful) < 2:
        return False
    virus_hits = []
    for part in meaningful:
        hits = {
            key for key, config in POLICY["viruses"].items()
            if any(mentions(part, term) for term in config["identity_terms"])
        }
        virus_hits.append(hits)
    recognized = set().union(*virus_hits)
    if len(recognized) > 1:
        return True
    # Repeated mentions of one configured virus are not evidence of multiple
    # pathogens; additional unrecognized labels in a typed field are.
    if len(recognized) == 1:
        matching_parts = sum(bool(hits) for hits in virus_hits)
        return matching_parts < len(meaningful)
    return True


def _sample_attribute_entries(xml, run_accession):
    """Retain repeated raw sample attributes for public-virus identity review."""
    root = ET.fromstring(xml)
    packages = [root] if root.tag.split("}")[-1] == "EXPERIMENT_PACKAGE" else [
        node for node in root.iter() if node.tag.split("}")[-1] == "EXPERIMENT_PACKAGE"
    ]
    matches = []
    for package in packages:
        runs = [node for node in package.iter() if node.tag.split("}")[-1] == "RUN"]
        if not any(run.get("accession") == run_accession for run in runs):
            continue
        sample = next((node for node in package.iter() if node.tag.split("}")[-1] == "SAMPLE"), None)
        if sample is None:
            continue
        for node in sample.iter():
            if node.tag.split("}")[-1] != "SAMPLE_ATTRIBUTE":
                continue
            key = next((child.text or "" for child in node
                        if child.tag.split("}")[-1] == "TAG"), "")
            value = next((child.text or "" for child in node
                          if child.tag.split("}")[-1] == "VALUE"), "")
            matches.append({"key": key.strip().lower(), "value": value})
    return matches


def _validate_accession_relationships(row):
    required = ("run_accession", "experiment_accession", "sample_accession", "study_accession")
    if any(not row.get(field) for field in required):
        raise ValueError("Archive run/experiment/sample/study linkage is incomplete")
    for field, pattern in ACCESSION_PATTERNS.items():
        value = row.get(field)
        if value and not pattern.fullmatch(str(value)):
            raise ValueError(f"Invalid {field} accession namespace or format")


def _attribute_value(attrs, names):
    names = {name.casefold() for name in names}
    values = [str(value).strip() for key, value in attrs.items()
              if str(key).strip().casefold() in names and str(value).strip()]
    return values[0] if values else "UNKNOWN"


def _replicate_metadata(attrs):
    result = {"biological": "UNKNOWN", "technical": "UNKNOWN"}
    for key, value in attrs.items():
        name = str(key).strip().casefold().replace("_", " ")
        if name in {"biological replicate", "biological replicate number"}:
            result["biological"] = str(value).strip() or "UNKNOWN"
        elif name in {"technical replicate", "technical replicate number"}:
            result["technical"] = str(value).strip() or "UNKNOWN"
    return result


def _snapshot_index(raw_directory):
    entries = []
    for path in sorted(Path(raw_directory).glob("*")):
        if path.is_file() and path.suffix in {".txt", ".json"}:
            entries.append({"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    return entries


def verify_snapshot_index(raw_directory, entries):
    """Detect changed/missing snapshots relative to the intake manifest."""
    root = Path(raw_directory)
    for entry in entries:
        path = root / entry["name"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Archive response snapshot missing or changed")
    return True


def verify_public_record(document, raw_directory):
    """Check local digest consistency only; this is not authentication or authorization.

    The verifier does not rederive normalized metadata or identity decisions from
    original archive responses and must never gate read download or QC.
    """
    manifest = document.get("manifest") or {}
    row = document.get("record") or {}
    if manifest.get("schema") != "public-virus-accession-manifest-v1":
        raise ValueError("Unsupported public accession manifest")
    if manifest.get("profile") != POLICY["policy_version"] or manifest.get("policy_sha256") != POLICY_SHA256:
        raise ValueError("Public-virus policy version or digest changed")
    expected = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected != manifest.get("record_sha256"):
        raise ValueError("Normalized archive record changed")
    verify_snapshot_index(raw_directory, manifest.get("snapshot_index", []))
    return True


def retrieve_accession(accession, virus, output, offline=False):
    if not isinstance(accession, str) or not RUN_ACCESSION.fullmatch(accession):
        raise ValueError("Expected a public SRA run accession (SRR, ERR or DRR)")
    if virus not in POLICY["viruses"]:
        raise ValueError("Unsupported public-virus-v1 virus")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    client = Client(output / "raw_metadata", offline=offline)
    search = client.search(f"{accession}[ACCN]", limit=5)
    if len(search["ids"]) != 1:
        raise ValueError("Run accession did not resolve to exactly one SRA record")
    xml = client.fetch(search["ids"])
    rows = parse_packages(xml, helper=None)
    matches = [row for row in rows if row.get("run_accession") == accession]
    if len(matches) != 1:
        raise ValueError("SRA response does not contain exactly one matching run")
    row = matches[0]
    _validate_accession_relationships(row)
    attribute_entries = _sample_attribute_entries(xml, accession)
    archive_errors = []
    try:
        enrich_ena(client, row)
    except (RuntimeError, ValueError) as exc:
        row["ena_status"] = "failed"
        archive_errors.append({"source": "ENA", "reason": str(exc)})
    # Preserve the archive submitter centre separately without changing the
    # legacy parser's source field or its exact-model behavior.
    row["archive_center_name"] = row.get("laboratory") or "UNKNOWN"
    row.pop("laboratory", None)
    assessed = assess(dict(row), min_spots=0)
    row.update({key: assessed[key] for key in ("selection", "exclusion_reasons", "warnings")})
    identity = assess_identity({
        **row, "public_virus_attribute_entries": attribute_entries,
    }, virus)
    if offline and identity["status"] == "accepted_for_technical_review":
        identity = {
            **identity, "status": "unresolved",
            "reason": "offline_archive_snapshot_not_independently_authenticated",
        }
    row["public_virus"] = identity
    library_reasons = list(assessed["exclusion_reasons"])
    library_ok = not library_reasons
    fastq_reasons = []
    fastq_files = []
    try:
        if row.get("raw_read_availability") != "ena_fastq_listed":
            raise ValueError("ena_fastq_not_listed")
        fastq_files = files_for_run(row)
    except ValueError as exc:
        fastq_reasons.append(str(exc) if str(exc) else "fastq_metadata_incomplete")
    total_fastq_bytes = sum(item["bytes"] for item in fastq_files)
    fastq_complete = bool(fastq_files)
    fits_budget = fastq_complete and total_fastq_bytes <= 1_000_000_000
    if fastq_complete and not fits_budget:
        fastq_reasons.append("complete_fastq_exceeds_1gb_budget")
    elif not fastq_reasons and not fastq_complete:
        fastq_reasons.append("verified_fastq_size_or_availability_missing")
    failed_gates = []
    if identity["status"] != "accepted_for_technical_review":
        failed_gates.append(identity["reason"])
    failed_gates.extend(library_reasons)
    failed_gates.extend(fastq_reasons)
    pilot_readiness = (
        "eligible_for_review" if not failed_gates else
        "held_for_identity_review" if identity["status"] in {"insufficient", "unresolved", "review_required"} else
        "excluded" if library_reasons or fastq_reasons or identity["status"] in {"excluded", "conflicting"} else
        "review_required"
    )
    row["technical_suitability"] = {
        "status": "eligible_for_review" if library_ok else "excluded",
        "reasons": library_reasons,
        "warnings": assessed["warnings"], "archive_errors": archive_errors,
    }
    row["fastq_assessment"] = {
        "status": "complete_within_budget" if fastq_complete and fits_budget else
                  "complete_over_budget" if fastq_complete else "unverified_or_incomplete",
        "complete": fastq_complete, "total_bytes": total_fastq_bytes if fastq_complete else None,
        "budget_bytes": 1_000_000_000, "fits_budget": bool(fits_budget),
        "reasons": fastq_reasons,
    }
    row["pilot_readiness"] = {
        "status": pilot_readiness,
        "reasons": list(dict.fromkeys(failed_gates)),
    }
    row["curator_evidence"] = {
        "status": "pending_review", "may_authorize": False,
        "limitation": "No authenticated external trust anchor is implemented.",
    }
    snapshot_index = _snapshot_index(output / "raw_metadata")
    manifest = {
        "schema": "public-virus-accession-manifest-v1",
        "profile": POLICY["policy_version"], "policy_sha256": POLICY_SHA256,
        "archive_source": "NCBI SRA / ENA",
        "retrieval_mode": "offline_snapshot" if offline else "archive_client",
        "snapshot_index": snapshot_index,
        "archive_errors": archive_errors,
        "archive_snapshot_integrity": "digest_checked_against_local_manifest_only",
        "biological_confirmation": "not_performed",
        "read_download_enabled": False, "qc_enabled": False,
    }
    document = {"manifest": manifest, "record": row}
    document["manifest"]["record_sha256"] = hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (output / "public_accession.json").write_text(json.dumps(document, indent=2), encoding="utf-8")
    return document
