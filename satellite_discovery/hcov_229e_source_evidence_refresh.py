"""Fixed-scope, bounded refresh of public HCoV-229E pilot metadata."""
import csv
import hashlib
import io
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import metadata_filter, public_virus, sequence_downloader
from .metadata import parse_packages
from .public_virus_acquisition_preflight import fastq_manifest_sha256

TARGET = {
    "virus": "HCoV-229E", "geo_series": "GSE155986",
    "bioproject": "PRJNA656274", "study": "SRP276927",
    "run": "SRR12424250", "experiment": "SRX8920123",
    "biosample": "SAMN15776099", "geo_sample": "GSM4718636",
}
DOI = "10.1371/journal.pone.0247128"
MAX_RESPONSE_BYTES = 2_000_000
TIMEOUT_SECONDS = 20
RETRIES = 2
ALLOWED_HOSTS = {"www.ncbi.nlm.nih.gov", "eutils.ncbi.nlm.nih.gov", "www.ebi.ac.uk"}
_USER_AGENT = "satellite-discovery/0.3.0 metadata-only"
_FIELDS = (
    "run_accession,experiment_accession,sample_accession,study_accession,"
    "secondary_study_accession,fastq_ftp,fastq_md5,fastq_bytes"
)


class SourceEvidenceError(ValueError):
    def __init__(self, code, detail):
        super().__init__(detail)
        self.code = code


def _safe_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS
            or parts.username or parts.password or parts.port or parts.fragment):
        raise SourceEvidenceError("unsafe_source_url", "Source URL is outside the HTTPS allowlist.")
    allowed_paths = {
        "www.ncbi.nlm.nih.gov": {"/geo/query/acc.cgi"},
        "eutils.ncbi.nlm.nih.gov": {"/entrez/eutils/esearch.fcgi", "/entrez/eutils/efetch.fcgi"},
        "www.ebi.ac.uk": {"/ena/portal/api/filereport"},
    }
    if parts.path not in allowed_paths[parts.hostname]:
        raise SourceEvidenceError("unsafe_source_path", "Source path is outside the endpoint allowlist.")
    return url


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = build_opener(_Redirects())


def _get(url):
    url = _safe_url(url)
    last_error = None
    for attempt in range(RETRIES + 1):
        try:
            request = Request(url, headers={
                "User-Agent": _USER_AGENT, "Accept-Encoding": "identity",
                "Accept": "application/xml, application/json, text/plain, text/*",
            })
            with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
                final_url = _safe_url(response.geturl())
                if response.status != 200:
                    raise SourceEvidenceError("source_http_status", f"Source returned HTTP {response.status}.")
                encoding = response.headers.get("Content-Encoding", "identity").lower()
                if encoding not in {"", "identity"}:
                    raise SourceEvidenceError("source_content_encoding", "Compressed metadata response rejected.")
                declared = response.headers.get("Content-Length")
                if declared is not None:
                    try:
                        declared_size = int(declared)
                    except (TypeError, ValueError):
                        raise SourceEvidenceError("source_content_length_invalid", "Metadata Content-Length is invalid.") from None
                    if declared_size < 0:
                        raise SourceEvidenceError("source_content_length_invalid", "Metadata Content-Length is invalid.")
                    if declared_size > MAX_RESPONSE_BYTES:
                        raise SourceEvidenceError("source_response_oversized", "Metadata response exceeds byte limit.")
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise SourceEvidenceError("source_response_oversized", "Metadata response exceeds byte limit.")
                if not body:
                    raise SourceEvidenceError("source_response_empty", "Metadata response is empty.")
                return {
                    "url": url, "final_url": final_url, "http_status": response.status,
                    "content_type": response.headers.get("Content-Type", ""),
                    "headers": {key.lower(): response.headers.get(key) for key in
                                ("Date", "Content-Type", "Content-Length", "ETag", "Last-Modified")},
                    "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                    "bytes": body, "byte_count": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == RETRIES:
                raise SourceEvidenceError("source_http_status", f"Source returned HTTP {exc.code}.") from None
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == RETRIES:
                raise SourceEvidenceError("source_unavailable", "Metadata source request failed.") from None
        time.sleep(min(4, 2 ** attempt))
    raise SourceEvidenceError("source_unavailable", str(last_error))


def _eutils_url(script, params):
    return "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/" + script + "?" + urlencode(params)


def _search(db, term, snapshots, name, capture):
    result = _get(_eutils_url("esearch.fcgi", {
        "db": db, "term": term, "retmode": "json",
    }))
    snapshots[name] = result
    capture(name, result)
    try:
        data = json.loads(result["bytes"])
        search = data["esearchresult"]
        if search["count"] != "1" or len(search["idlist"]) != 1:
            raise ValueError
        return search["idlist"][0]
    except (ValueError, KeyError, TypeError):
        raise SourceEvidenceError("source_accession_not_unique", f"{name} did not resolve exactly once.") from None


def _fetch_eutils(db, uid, snapshots, name, capture):
    result = _get(_eutils_url("efetch.fcgi", {
        "db": db, "id": uid, "retmode": "xml",
    }))
    snapshots[name] = result
    capture(name, result)
    return result["bytes"]


def _xml(data):
    upper = data.upper()
    if b"<!ENTITY" in upper:
        raise SourceEvidenceError("source_xml_unsafe", "XML entity declarations are not accepted.")
    doctype = re.search(rb"<!DOCTYPE\b", upper)
    if doctype:
        end = data.find(b">", doctype.start())
        if end < 0 or b"[" in data[doctype.start():end]:
            raise SourceEvidenceError("source_xml_unsafe", "XML internal DTD subsets are not accepted.")
        data = data[:doctype.start()] + data[end + 1:]
        if re.search(rb"<!DOCTYPE\b", data, re.I):
            raise SourceEvidenceError("source_xml_unsafe", "Multiple XML DTD declarations are not accepted.")
    try:
        return ET.fromstring(data)
    except ET.ParseError:
        raise SourceEvidenceError("source_xml_malformed", "Source XML is malformed.") from None


def parse_geo_soft(data, record_kind, expected_accession):
    if record_kind not in {"sample", "series"}:
        raise SourceEvidenceError("geo_record_kind_invalid", "GEO record kind is not supported.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise SourceEvidenceError("source_text_encoding", "GEO response is not UTF-8.") from None
    values, characteristics = {}, {}
    for line in text.splitlines():
        match = re.match(r"^!(?:Sample|Series)_([A-Za-z0-9_]+) = (.*)$", line)
        if not match:
            continue
        key, value = match.groups()
        if key == "characteristics_ch1":
            if ": " in value:
                k, v = value.split(": ", 1)
                characteristics.setdefault(k.strip().casefold(), []).append(v.strip())
        else:
            values.setdefault(key, []).append(value.strip())
    if values.get("geo_accession") != [expected_accession]:
        raise SourceEvidenceError("geo_accession_mismatch", "GEO response did not contain exactly the requested record.")
    return {"values": values, "characteristics": characteristics}


def _geo_relations(relations):
    """Extract exact accession targets from labelled GEO relation links."""
    result = {}
    for relation in relations:
        label, separator, target = relation.partition(":")
        if not separator:
            continue
        label = label.strip().casefold()
        target = target.strip()
        parts = urlsplit(target)
        if parts.scheme or parts.netloc:
            if parts.scheme != "https" or parts.hostname not in {
                "www.ncbi.nlm.nih.gov", "ncbi.nlm.nih.gov",
            }:
                continue
            if label in {"biosample", "bioproject"}:
                accession = parts.path.rstrip("/").rsplit("/", 1)[-1]
            elif label == "sra":
                terms = parse_qs(parts.query).get("term", [])
                accession = terms[0] if len(terms) == 1 else ""
            else:
                continue
        else:
            accession = target
        if accession:
            result.setdefault(label, set()).add(accession)
    return result


def parse_biosample(data):
    root = _xml(data)
    samples = [e for e in root.iter() if e.tag.split("}")[-1] == "BioSample"]
    if len(samples) != 1:
        raise SourceEvidenceError("biosample_cardinality", "BioSample response must contain exactly one record.")
    sample = samples[0]
    ids = {}
    for element in sample.iter():
        if element.tag.split("}")[-1] == "Id" and element.get("db"):
            ids[element.get("db").casefold()] = " ".join("".join(element.itertext()).split())
    attrs = {}
    for element in sample.iter():
        if element.tag.split("}")[-1] == "Attribute":
            name = element.get("harmonized_name") or element.get("attribute_name") or ""
            attrs.setdefault(name.casefold(), []).append(" ".join("".join(element.itertext()).split()))
    links = [
        {"label": e.get("label", ""), "type": e.get("type", ""),
         "target": e.get("target", ""), "value": " ".join("".join(e.itertext()).split())}
        for e in sample.iter() if e.tag.split("}")[-1] == "Link"
    ]
    return {"accession": sample.get("accession"), "status": sample.get("access"),
            "ids": ids, "attributes": attrs, "links": links,
            "last_update": sample.get("last_update")}


def parse_sra(data):
    root = _xml(data)
    packages = [e for e in root.iter() if e.tag.split("}")[-1] == "EXPERIMENT_PACKAGE"]
    found = []
    for package in packages:
        run = next((e for e in package.iter() if e.tag.split("}")[-1] == "RUN"), None)
        if run is None or run.get("accession") != TARGET["run"]:
            continue
        experiment = next((e for e in package.iter() if e.tag.split("}")[-1] == "EXPERIMENT"), None)
        sample = next((e for e in package.iter() if e.tag.split("}")[-1] == "SAMPLE"), None)
        study = next((e for e in package.iter() if e.tag.split("}")[-1] == "STUDY"), None)
        if experiment is None or sample is None or study is None:
            raise SourceEvidenceError("sra_package_incomplete", "SRA run package is missing experiment, sample, or study links.")
        external = {}
        for element in package.iter():
            if element.tag.split("}")[-1] == "EXTERNAL_ID" and element.get("namespace"):
                external.setdefault(element.get("namespace").casefold(), set()).add(
                    " ".join("".join(element.itertext()).split())
                )
        attrs = {}
        for element in package.iter():
            if element.tag.split("}")[-1] == "SAMPLE_ATTRIBUTE":
                tag = element.findtext("TAG", "")
                value = element.findtext("VALUE", "")
                attrs.setdefault(tag.strip().casefold(), []).append(value.strip())
        platform = next((e for e in experiment.iter() if e.tag.split("}")[-1] == "PLATFORM"), None)
        library = next((e for e in experiment.iter() if e.tag.split("}")[-1] == "LIBRARY_DESCRIPTOR"), None)
        layout_node = next((e for e in library.iter() if e.tag.split("}")[-1] == "LIBRARY_LAYOUT"), None) if library is not None else None
        layout = layout_node[0].tag.split("}")[-1] if layout_node is not None and len(layout_node) else None
        library_fields = {
            key: library.findtext(key, "") if library is not None else ""
            for key in ("LIBRARY_STRATEGY", "LIBRARY_SOURCE", "LIBRARY_SELECTION")
        }
        found.append({
            "run": run.get("accession"), "experiment": experiment.get("accession"),
            "sample": sample.get("accession"), "study": study.get("accession"),
            "external": {k: sorted(v) for k, v in external.items()},
            "attributes": attrs, "platform": platform[0].tag.split("}")[-1] if platform is not None and len(platform) else None,
            "library": {"strategy": library_fields["LIBRARY_STRATEGY"],
                        "source": library_fields["LIBRARY_SOURCE"],
                        "selection": library_fields["LIBRARY_SELECTION"]},
            "layout": layout, "is_public": run.get("is_public"),
        })
    if len(found) != 1:
        raise SourceEvidenceError("sra_run_cardinality", "SRA response must contain exactly one requested run package.")
    return found[0]


def parse_ena(data):
    try:
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8")), delimiter="\t"))
    except (UnicodeDecodeError, csv.Error):
        raise SourceEvidenceError("ena_tsv_malformed", "ENA run report is malformed.") from None
    if len(rows) != 1 or rows[0].get("run_accession") != TARGET["run"]:
        raise SourceEvidenceError("ena_run_cardinality", "ENA must return exactly the requested run.")
    return rows[0]


def parse_pubmed(data):
    root = _xml(data)
    articles = [e for e in root.iter() if e.tag.split("}")[-1] == "PubmedArticle"]
    if len(articles) != 1:
        raise SourceEvidenceError("publication_cardinality", "PubMed response must contain exactly one article.")
    article = next((e for e in articles[0].iter() if e.tag.split("}")[-1] == "Article"), None)
    if article is None:
        raise SourceEvidenceError("publication_article_missing", "PubMed record has no Article element.")
    dois = [e.text for e in article.findall("ELocationID") if e.get("EIdType") == "doi"]
    title = " ".join("".join(article.find("ArticleTitle").itertext()).split()) if article.find("ArticleTitle") is not None else ""
    abstract = " ".join(" ".join("".join(e.itertext()).split()) for e in article.findall(".//Abstract/AbstractText"))
    if dois != [DOI] or "HCoV-229E" not in abstract and "HCoV-229E" not in title:
        raise SourceEvidenceError("publication_identity_mismatch", "PubMed DOI or HCoV-229E study context does not match.")
    return {"doi": DOI, "title": title, "journal": article.findtext("Journal/Title"),
            "year": article.findtext("Journal/JournalIssue/PubDate/Year"), "study_level_only": True}


def _material_check(evidence, geo_sample, geo_series, biosample, sra, ena, publication):
    wanted = evidence.get("scope", {})
    if wanted != TARGET:
        raise SourceEvidenceError("signed_scope_mismatch", "Signed evidence scope is not the one-run target.")
    sample_rel = _geo_relations(geo_sample["values"].get("relation", []))
    series_rel = _geo_relations(geo_series["values"].get("relation", []))
    if (geo_sample["values"].get("geo_accession") != [TARGET["geo_sample"]]
            or not any(x.startswith("Public on ") for x in geo_sample["values"].get("status", []))
            or not any(x.startswith("Public on ") for x in geo_series["values"].get("status", []))
            or TARGET["geo_series"] not in geo_sample["values"].get("series_id", [])
            or TARGET["geo_sample"] not in geo_series["values"].get("sample_id", [])
            or sample_rel.get("biosample") != {TARGET["biosample"]}
            or sample_rel.get("sra") != {TARGET["experiment"]}
            or series_rel.get("bioproject") != {TARGET["bioproject"]}
            or series_rel.get("sra") != {TARGET["study"]}):
        raise SourceEvidenceError("geo_relationship_conflict", "GEO sample/series links are missing or contradictory.")
    treatment = " ".join(geo_sample["characteristics"].get("treatment", []))
    cell = " ".join(geo_sample["characteristics"].get("cell line", []))
    if (biosample["accession"] != TARGET["biosample"] or biosample["status"] != "public"
            or biosample["ids"].get("geo") != TARGET["geo_sample"]
            or biosample["ids"].get("sra") != sra["sample"]
            or not any(
                x["label"] == TARGET["bioproject"]
                and x["target"].casefold() == "bioproject"
                and x["value"] == TARGET["bioproject"][5:]
                for x in biosample["links"]
            )
            or biosample["attributes"].get("treatment") != [treatment]
            or biosample["attributes"].get("cell_line") != [cell]):
        raise SourceEvidenceError("biosample_relationship_or_treatment_conflict", "BioSample is missing or conflicts with GEO.")
    ext = sra["external"]
    if (sra["run"] != TARGET["run"] or sra["is_public"] != "true"
            or sra["experiment"] != TARGET["experiment"]
            or sra["study"] != TARGET["study"] or ext.get("biosample") != [TARGET["biosample"]]
            or ext.get("bioproject") != [TARGET["bioproject"]]
            or TARGET["geo_sample"] not in ext.get("geo", set())
            or TARGET["geo_series"] not in ext.get("geo", set())):
        raise SourceEvidenceError("sra_relationship_conflict", "SRA accession relationships are missing or contradictory.")
    if (ena.get("experiment_accession") != TARGET["experiment"]
            or ena.get("sample_accession") != TARGET["biosample"]
            or ena.get("study_accession") != TARGET["bioproject"]
            or ena.get("secondary_study_accession") != TARGET["study"]):
        raise SourceEvidenceError("ena_relationship_conflict", "ENA run relationships are missing or contradictory.")
    library = sra["library"]
    if (sra["platform"] != "ILLUMINA"
            or library.get("strategy") != "RNA-Seq"
            or library.get("source") != "TRANSCRIPTOMIC"
            or library.get("selection") != "cDNA"
            or sra.get("layout") != "SINGLE"):
        raise SourceEvidenceError("library_material_changed", "Fresh SRA library metadata changed.")
    exp = evidence.get("exposure_record", {})
    signed_treatment = exp.get("sample_treatment", {})
    if (signed_treatment.get("archive_annotation") != treatment
            or signed_treatment.get("reported_virus") != TARGET["virus"]
            or signed_treatment.get("condition") != "REPORTED_INFECTED"
            or signed_treatment.get("timepoint_hours") != 24
            or not re.search(r"\b24\s+hours?\b", treatment, re.I)
            or not re.search(r"hcov[- ]229e", treatment, re.I)
            or not re.search(r"mrc-?5", cell, re.I)):
        raise SourceEvidenceError("treatment_material_changed", "Fresh sample-level treatment or cell-line evidence changed.")
    if publication["doi"] != DOI:
        raise SourceEvidenceError("publication_link_conflict", "Primary publication DOI is not the reviewed DOI.")


def refresh_source_evidence(evidence, snapshot_directory):
    """Fetch fixed public metadata endpoints, preserve exact bytes, and compare claims."""
    target_dir = Path(snapshot_directory)
    if target_dir.is_symlink():
        raise SourceEvidenceError("snapshot_path_unsafe", "Evidence snapshot directory must not be a symlink.")
    if target_dir.exists() and (not target_dir.is_dir() or any(target_dir.iterdir())):
        raise SourceEvidenceError("snapshot_collision", "Evidence snapshot directory must be new or empty.")
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        target_dir.chmod(0o700)
    snapshots = {}
    index = []
    manifest_sources = []

    def capture(name, response):
        filename = name + (".json" if name.endswith("_search") else ".txt")
        path = target_dir / filename
        if path.exists() or path.is_symlink():
            raise SourceEvidenceError("snapshot_collision", "Refusing to overwrite an evidence snapshot.")
        with path.open("xb") as handle:
            handle.write(response["bytes"])
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            path.chmod(0o600)
        index.append({"name": filename, "sha256": response["sha256"]})
        accession = (
            TARGET["geo_sample"] if name == "geo_sample" else
            TARGET["geo_series"] if name == "geo_series" else
            TARGET["biosample"] if name.startswith("biosample") else
            TARGET["run"] if name in {"sra_search", "sra", "ena_run"} else DOI
        )
        manifest_sources.append({
            "name": name, "source_accession": accession,
            **{k: response[k] for k in
               ("url", "final_url", "http_status", "content_type", "headers",
                "retrieved_utc", "byte_count", "sha256")},
        })
        meta_path = target_dir / (filename + ".meta.json")
        meta_path.write_text(json.dumps(manifest_sources[-1], indent=2), encoding="utf-8")
        if os.name != "nt":
            meta_path.chmod(0o600)

    def get(name, url):
        response = _get(url)
        snapshots[name] = response
        capture(name, response)
        return response["bytes"]

    sample_raw = get("geo_sample", "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?" +
        urlencode({"acc": TARGET["geo_sample"], "targ": "self", "form": "text", "view": "full"}))
    series_raw = get("geo_series", "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?" +
        urlencode({"acc": TARGET["geo_series"], "targ": "self", "form": "text", "view": "full"}))
    bs_id = _search("biosample", TARGET["biosample"] + "[ACCN]", snapshots, "biosample_search", capture)
    biosample_raw = _fetch_eutils("biosample", bs_id, snapshots, "biosample", capture)
    sra_id = _search("sra", TARGET["run"] + "[ACCN]", snapshots, "sra_search", capture)
    sra_raw = _fetch_eutils("sra", sra_id, snapshots, "sra", capture)
    ena_url = "https://www.ebi.ac.uk/ena/portal/api/filereport?" + urlencode({
        "accession": TARGET["run"], "result": "read_run", "format": "tsv", "fields": _FIELDS,
    })
    ena_raw = get("ena_run", ena_url)
    pm_id = _search("pubmed", DOI + "[DOI]", snapshots, "pubmed_search", capture)
    pub_raw = _fetch_eutils("pubmed", pm_id, snapshots, "pubmed", capture)
    sample = parse_geo_soft(sample_raw, "sample", TARGET["geo_sample"])
    series = parse_geo_soft(series_raw, "series", TARGET["geo_series"])
    biosample = parse_biosample(biosample_raw)
    sra = parse_sra(sra_raw)
    ena = parse_ena(ena_raw)
    pub = parse_pubmed(pub_raw)
    _material_check(evidence, sample, series, biosample, sra, ena, pub)

    manifest_path = target_dir / "source_manifest.json"
    with manifest_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps({
        "schema": "hcov229e-source-snapshot-manifest-v1",
        "scope": TARGET, "sources": manifest_sources,
        }, indent=2))
        handle.flush()
        os.fsync(handle.fileno())
    if os.name != "nt":
        manifest_path.chmod(0o600)
    rowset = parse_packages(sra_raw.decode("utf-8"), helper=None)
    rows = [r for r in rowset if r.get("run_accession") == TARGET["run"]]
    if len(rows) != 1:
        raise SourceEvidenceError("sra_normalization_failed", "SRA run could not be normalized uniquely.")
    row = rows[0]
    row["raw_sample_attributes"] = public_virus._sample_attribute_entries(
        sra_raw.decode("utf-8"), TARGET["run"], row,
    )
    row.update({
        "fastq_ftp": ena.get("fastq_ftp"), "fastq_md5": ena.get("fastq_md5"),
        "fastq_bytes": ena.get("fastq_bytes"), "ena_status": "checked",
        "raw_read_availability": "ena_fastq_listed",
        "archive_center_name": row.get("laboratory") or "UNKNOWN",
    })
    assessed = metadata_filter.assess(dict(row), min_spots=0)
    row.update({k: assessed[k] for k in ("selection", "exclusion_reasons", "warnings")})
    row.pop("laboratory", None)
    identity = public_virus.assess_identity(row, "hcov-229e")
    row["public_virus"] = identity
    files = sequence_downloader.files_for_run(row)
    if (evidence.get("fastq_files") != files
            or evidence.get("fastq_manifest_sha256") != fastq_manifest_sha256(files)):
        raise SourceEvidenceError("fastq_manifest_material_changed", "Fresh ENA file manifest differs from signed evidence.")
    fastq_bytes = sum(f["bytes"] for f in files)
    row["technical_suitability"] = {
        "status": "eligible_for_review" if not assessed["exclusion_reasons"] else "excluded",
        "reasons": assessed["exclusion_reasons"], "warnings": assessed["warnings"],
        "archive_errors": [],
    }
    row["fastq_assessment"] = {
        "status": "complete_within_budget" if fastq_bytes <= 1_000_000_000 else "complete_over_budget",
        "complete": True, "total_bytes": fastq_bytes, "budget_bytes": 1_000_000_000,
        "fits_budget": fastq_bytes <= 1_000_000_000, "reasons": [],
    }
    row["pilot_readiness"] = {"status": "held_for_identity_review", "reasons": [identity["reason"]]}
    row["curator_evidence"] = {"status": "pending_review", "may_authorize": False,
                               "limitation": "No authenticated external trust anchor is implemented."}
    manifest = {
        "schema": "public-virus-accession-manifest-v1", "profile": public_virus.POLICY["policy_version"],
        "policy_sha256": public_virus.POLICY_SHA256, "archive_source": "NCBI SRA / ENA",
        "retrieval_mode": "archive_client", "snapshot_index": index,
        "archive_errors": [], "archive_snapshot_integrity": "digest_checked_against_local_manifest_only",
        "biological_confirmation": "not_performed", "read_download_enabled": False, "qc_enabled": False,
    }
    document = {"manifest": manifest, "record": row}
    document["manifest"]["record_sha256"] = hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"document": document, "metadata": {
        "accessions": TARGET, "treatment": sample["characteristics"].get("treatment", []),
        "cell_line": sample["characteristics"].get("cell line", []),
        "publication": pub, "fastq_files": files,
        "fastq_manifest_sha256": fastq_manifest_sha256(files),
        "snapshot_manifest": str(target_dir / "source_manifest.json"),
    }}
