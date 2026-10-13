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
SRA_ACCESSION_PATTERNS = {
    "run_accession": re.compile(r"^[SED]RR[0-9]+$"),
    "experiment_accession": re.compile(r"^[SED]RX[0-9]+$"),
    "sample_accession": re.compile(r"^[SED]RS[0-9]+$"),
    "study_accession": re.compile(r"^[SED]RP[0-9]+$"),
}
BIOSAMPLE_ACCESSION = re.compile(r"^SAM(?:N|D|EA)[0-9]+$")
BIOPROJECT_ACCESSION = re.compile(r"^PRJ(?:NA|EB|DB)[0-9]+$")
TYPED_PATHOGEN_KEYS = {
    "pathogen", "virus", "virus species", "infecting virus", "viral species",
}
MULTI_AGENT_SEPARATORS = re.compile(
    r"\s*(?:\+\s*|\band\b|\bwith\b|\balongside\b|\btogether\s+with\b|"
    r"\bplus\b|[;,/&])\s*",
    re.IGNORECASE,
)
STRAIN_DESCRIPTORS = (
    "strain", "isolate", "lineage", "variant", "genotype", "serotype",
    "subtype", "sublineage", "clade", "passage",
)
UNKNOWN_METADATA_VALUES = {"", "unknown", "unspecified", "not specified", "none", "na", "n/a"}
NON_PATHOGEN_CONTEXT_SEGMENTS = {
    "infected", "infection", "infected sample", "sample", "specimen",
    "positive", "positive for", "isolated from",
}


def _typed_pathogen_review(attribute_entries, virus, terms, target_supported):
    """Return evidence for explicit or ambiguous multi-agent typed metadata."""
    evidence = []
    typed_values = [
        (str(key), str(value).strip())
        for key, value in attribute_entries
        if str(key).strip().casefold().replace("_", " ") in TYPED_PATHOGEN_KEYS
        and str(value).strip().casefold() not in UNKNOWN_METADATA_VALUES
    ]
    all_terms = {
        key: item["identity_terms"] for key, item in POLICY["viruses"].items()
    }
    for field, value in typed_values:
        normalized = value.casefold()
        target_hits = [term for term in terms if mentions(value, term)]
        other_hits = [
            term for other_key, other_terms in all_terms.items() if other_key != virus
            for term in other_terms if mentions(value, term)
        ]
        if target_hits and other_hits:
            evidence.append({
                "field": "attribute:" + field, "value": value,
                "term": "multiple_known_pathogens", "evidence_type": "typed_pathogen",
            })
            continue
        # Strip explicit strain/isolate descriptors before interpreting a
        # connected remainder as another pathogen (e.g. "with strain VR-740").
        for descriptor in STRAIN_DESCRIPTORS:
            normalized = re.sub(
                rf"\b{descriptor}(?:\s+(?:designation|number|name|id))?\s+[a-z0-9._/-]+\b",
                " ", normalized, flags=re.IGNORECASE,
            )
            normalized = re.sub(
                rf"\b[\w.-]+\s+{descriptor}\b", " ", normalized, flags=re.IGNORECASE,
            )
        segments = [
            part.strip() for part in MULTI_AGENT_SEPARATORS.split(normalized)
            if part.strip() and part.strip() not in NON_PATHOGEN_CONTEXT_SEGMENTS
        ]
        if len(segments) > 1:
            target_segments = [
                part for part in segments
                if any(mentions(part, term) for term in terms)
            ]
            other_segments = [part for part in segments if part not in target_segments]
            if target_segments and other_segments:
                # Repeated names/isolates of the same supported virus are not
                # treated as multiple pathogen species.
                same_virus_only = all(
                    any(mentions(part, term) for term in terms)
                    for part in other_segments
                )
                if not same_virus_only:
                    evidence.append({
                        "field": "attribute:" + field, "value": value,
                        "term": "multiple_or_ambiguous_pathogens_in_typed_field",
                        "evidence_type": "typed_pathogen",
                    })
                    continue
        if target_supported and not target_hits and not other_hits:
            evidence.append({
                "field": "attribute:" + field, "value": value,
                "term": "ambiguous_additional_typed_pathogen",
                "evidence_type": "typed_pathogen",
            })
    return evidence


def _sample_attribute_entries(xml, run_accession, expected_row):
    """Read repeated attributes from the exact SRA package containing this run."""
    root = ET.fromstring(xml)
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    packages = ([root] if root.tag == "EXPERIMENT_PACKAGE"
                else root.findall(".//EXPERIMENT_PACKAGE"))
    matches = []
    for package in packages:
        runs = package.findall(".//RUN_SET/RUN")
        if not any(run.get("accession") == run_accession for run in runs):
            continue
        links = {
            "experiment_accession": package.find("EXPERIMENT").get("accession")
            if package.find("EXPERIMENT") is not None else None,
            "sample_accession": package.find("SAMPLE").get("accession")
            if package.find("SAMPLE") is not None else None,
            "study_accession": package.find("STUDY").get("accession")
            if package.find("STUDY") is not None else None,
        }
        if any(links[key] != expected_row.get(key) for key in links):
            raise ValueError("Raw sample attributes do not match run relationships")
        sample = package.find("SAMPLE")
        if sample is None:
            raise ValueError("SRA package has no sample for raw attribute evidence")
        entries = []
        for attribute in sample.findall(".//SAMPLE_ATTRIBUTE"):
            tag = attribute.findtext("TAG")
            value = attribute.findtext("VALUE")
            if tag is not None:
                entries.append({"key": tag.strip(), "value": value or ""})
        matches.append(entries)
    if len(matches) != 1:
        raise ValueError("Raw sample attributes are not uniquely bound to the requested run")
    return matches[0]


def _validate_archive_accessions(row):
    for field, pattern in SRA_ACCESSION_PATTERNS.items():
        value = row.get(field)
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise ValueError(f"Invalid or missing SRA {field}")
    for field, pattern in (
        ("biosample", BIOSAMPLE_ACCESSION),
        ("bioproject", BIOPROJECT_ACCESSION),
    ):
        value = row.get(field)
        if value and (not isinstance(value, str) or not pattern.fullmatch(value)):
            raise ValueError(f"Invalid {field} accession namespace")


def assess_identity(row, virus):
    if virus not in POLICY["viruses"]:
        raise ValueError("Unsupported public-virus-v1 virus")
    item = POLICY["viruses"][virus]
    attrs = row.get("attributes") or {}
    if not isinstance(attrs, dict):
        raise ValueError("Sample attributes must be a dictionary")
    raw_entries = row.get("raw_sample_attributes")
    if raw_entries is None:
        attribute_entries = list(attrs.items())
    else:
        if not isinstance(raw_entries, list) or any(
                not isinstance(entry, dict) or "key" not in entry or "value" not in entry
                for entry in raw_entries):
            raise ValueError("Raw sample attribute evidence must be a list of key/value records")
        attribute_entries = [(entry["key"], entry["value"]) for entry in raw_entries]
    context = "\n".join(str(row.get(k) or "") for k in
                        ("organism", "sample_title", "experiment_title", "study_title"))
    context += "\n" + "\n".join(str(value) for _, value in attribute_entries)
    excluded = [term for term in POLICY["excluded_mentions"] if mentions(context, term)]
    terms = item["identity_terms"]
    organism = str(row.get("organism") or "")
    organism_evidence = [term for term in terms if mentions(organism, term)]
    accepted_keys = {k.casefold() for k in item["identity_attribute_keys"]}
    attribute_evidence = [
        {"key": str(key), "term": term}
        for key, value in attribute_entries
        if str(key).strip().casefold() in accepted_keys
        for term in terms if mentions(str(value), term)
    ]
    review_evidence = []
    review_terms = POLICY.get("review_mentions", [])
    def add_review_text(field, value):
        for term in review_terms:
            if mentions(str(value), term):
                review_evidence.append({
                    "field": field, "value": str(value), "term": term,
                    "evidence_type": "sample_or_study_text",
                })
    sample_context_fields = ("organism", "sample_title", "experiment_title")
    for field in sample_context_fields:
        add_review_text(field, row.get(field) or "")
    for key, value in attribute_entries:
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
    target_supported = bool(organism_evidence or attribute_evidence)
    for key, value in attribute_entries:
        normalized_key = str(key).strip().casefold().replace("_", " ").replace("-", " ")
        normalized_value = str(value).strip().casefold()
        if normalized_key in flag_keys and (
                normalized_value in flag_values or
                any(mentions(normalized_value, term) for term in review_terms)):
            review_evidence.append({
                "field": "attribute:" + str(key), "value": str(value),
                "term": "explicit_mixed_flag", "evidence_type": "structured_flag",
            })
        if normalized_key in {"additional pathogen", "co infecting pathogen",
                              "coinfecting pathogen", "secondary pathogen"} and normalized_value:
            review_evidence.append({
                "field": "attribute:" + str(key), "value": str(value),
                "term": "additional_pathogen", "evidence_type": "structured_pathogen",
            })
    review_evidence.extend(
        _typed_pathogen_review(attribute_entries, virus, terms, target_supported)
    )
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
                    str(key).strip().casefold() in accepted_keys and
                    any(mentions(str(value), term) for term in other["identity_terms"])
                    for key, value in attribute_entries):
                other_virus_evidence.append(other_key)
        if review_evidence:
            status = "review_required"
            if any(item["term"] in {
                    "explicit_mixed_flag", "additional_pathogen",
                    "multiple_known_pathogens",
                    "multiple_or_ambiguous_pathogens_in_typed_field",
                    "ambiguous_additional_typed_pathogen",
            } for item in review_evidence):
                reason = "multiple_or_ambiguous_pathogen_metadata_requires_review"
            else:
                reason = "mixed_or_modified_sample_metadata_requires_review"
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
    row["raw_sample_attributes"] = _sample_attribute_entries(xml, accession, row)
    required = ("experiment_accession", "sample_accession", "study_accession")
    if any(not row.get(field) for field in required):
        raise ValueError("Archive run/experiment/sample/study linkage is incomplete")
    _validate_archive_accessions(row)
    archive_errors = []
    try:
        enrich_ena(client, row)
    except (RuntimeError, ValueError) as exc:
        row["ena_status"] = "failed"
        archive_errors.append({"source": "ENA", "reason": str(exc)})
    # Preserve the archive submitter centre separately without changing the
    # legacy parser's source field or its exact-model behavior.
    row["archive_center_name"] = row.get("laboratory") or "UNKNOWN"
    assessed = assess(dict(row), min_spots=0)
    row.update({key: assessed[key] for key in ("selection", "exclusion_reasons", "warnings")})
    row.pop("laboratory", None)
    identity = assess_identity(row, virus)
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
