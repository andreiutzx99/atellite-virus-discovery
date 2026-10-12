"""Opt-in, metadata-only intake for the public-virus-v1 profile."""
import hashlib
import json
import re
from pathlib import Path

from .database_query import Client
from .metadata import parse_packages, enrich_ena
from .metadata_filter import assess
from .model_scope import mentions
from .sequence_downloader import make_plan

POLICY_PATH = Path(__file__).with_name("public_virus_policy.json")
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
POLICY_SHA256 = hashlib.sha256(POLICY_PATH.read_bytes()).hexdigest()
RUN_ACCESSION = re.compile(r"^[SED]RR[0-9]+$")


def assess_identity(row, virus):
    if virus not in POLICY["viruses"]:
        raise ValueError("Unsupported public-virus-v1 virus")
    item = POLICY["viruses"][virus]
    attrs = row.get("attributes") or {}
    if not isinstance(attrs, dict):
        raise ValueError("Sample attributes must be a dictionary")
    context = "\n".join(str(row.get(k) or "") for k in
                        ("organism", "sample_title", "experiment_title", "study_title"))
    context += "\n" + "\n".join(str(v) for v in attrs.values())
    excluded = [term for term in POLICY["excluded_mentions"] if mentions(context, term)]
    if excluded:
        status, reason = "excluded", "excluded_pathogen_mentioned_in_metadata"
    else:
        terms = item["identity_terms"]
        organism = str(row.get("organism") or "")
        # Sample taxonomy can establish virus identity only when it names the virus;
        # host taxonomy and free-text titles never do.
        organism_evidence = [term for term in terms if mentions(organism, term)]
        accepted_keys = {k.casefold() for k in item["identity_attribute_keys"]}
        attribute_evidence = [
            {"key": str(key), "term": term}
            for key, value in attrs.items()
            if str(key).strip().casefold() in accepted_keys
            for term in terms if mentions(str(value), term)
        ]
        other_virus_evidence = []
        for other_key, other in POLICY["viruses"].items():
            if other_key == virus:
                continue
            if any(mentions(organism, term) for term in other["identity_terms"]) or any(
                    str(key).strip().casefold() in accepted_keys and
                    any(mentions(str(value), term) for term in other["identity_terms"])
                    for key, value in attrs.items()):
                other_virus_evidence.append(other_key)
        if (organism_evidence or attribute_evidence) and other_virus_evidence:
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
            "organism_terms": locals().get("organism_evidence", []) if not excluded else [],
            "attributes": locals().get("attribute_evidence", []) if not excluded else [],
        },
        "strain": _attribute_value(attrs, {"strain", "virus strain", "viral strain", "strain designation"}),
        "isolate": _attribute_value(attrs, {"isolate", "isolate name"}),
        "laboratory_stock_catalogue": _attribute_value(
            attrs, {"stock", "catalogue", "catalog", "strain designation"}),
        "laboratory": row.get("laboratory"),
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
    required = ("experiment_accession", "sample_accession", "study_accession")
    if any(not row.get(field) for field in required):
        raise ValueError("Archive run/experiment/sample/study linkage is incomplete")
    archive_errors = []
    try:
        enrich_ena(client, row)
    except (RuntimeError, ValueError) as exc:
        row["ena_status"] = "failed"
        archive_errors.append({"source": "ENA", "reason": str(exc)})
    assessed = assess(dict(row), min_spots=0)
    row.update({key: assessed[key] for key in ("selection", "exclusion_reasons", "warnings")})
    identity = assess_identity(row, virus)
    if offline and identity["status"] == "accepted_for_technical_review":
        identity = {
            **identity, "status": "unresolved",
            "reason": "offline_archive_snapshot_not_independently_authenticated",
        }
    reasons = list(assessed["exclusion_reasons"])
    if identity["status"] != "accepted_for_technical_review":
        reasons.append(identity["reason"])
    row["public_virus"] = identity
    plan = make_plan([row], 1, 1_000_000_000)
    exact_size = row.get("fastq_bytes") and row.get("raw_read_availability") == "ena_fastq_listed"
    fits_budget = bool(plan["selected"] and exact_size
                       and plan["selected"][0]["accession"] not in plan.get("unknown_size_accessions", []))
    technical_status = "eligible_for_review" if fits_budget else "excluded"
    if not fits_budget:
        reasons.extend(item.get("reason", "No verified complete run fits the budget")
                       for item in plan["skipped"])
        if not reasons:
            reasons.append("verified_fastq_size_or_availability_missing")
    pilot_readiness = (
        "eligible_for_review"
        if identity["status"] == "accepted_for_technical_review" and fits_budget
        else "held_for_identity_review"
        if identity["status"] == "insufficient"
        else "excluded"
    )
    row["technical_suitability"] = {
        "status": technical_status, "fits_1gb_budget": fits_budget,
        "reasons": list(dict.fromkeys(reasons)),
        "warnings": assessed["warnings"], "archive_errors": archive_errors,
    }
    row["pilot_readiness"] = {
        "status": pilot_readiness,
        "reason": identity["reason"] if pilot_readiness != "eligible_for_review" else "identity_and_metadata_budget_gates_passed",
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
