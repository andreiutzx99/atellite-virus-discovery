"""Normalize experiment packages, preserving unknowns and original attributes."""
import csv
import io
import xml.etree.ElementTree as ET


def number(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def parse_packages(xml, helper, cohort="helper_search"):
    root = ET.fromstring(xml)
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    if root.find(".//ERROR") is not None:
        raise ValueError("NCBI XML contains an error")
    packages = [root] if root.tag == "EXPERIMENT_PACKAGE" else root.findall(".//EXPERIMENT_PACKAGE")
    rows = []
    for package in packages:
        sample = package.find("SAMPLE")
        experiment = package.find("EXPERIMENT")
        study = package.find("STUDY")
        if sample is None or experiment is None:
            continue
        attrs = {a.findtext("TAG", "").strip().lower(): a.findtext("VALUE", "")
                 for a in sample.findall(".//SAMPLE_ATTRIBUTE")}
        def attr(*names):
            return next((attrs[n] for n in names if attrs.get(n)), None)
        external = {n.get("namespace", "").lower(): n.text for n in package.findall(".//EXTERNAL_ID")}
        platform = experiment.find("PLATFORM")
        layout = experiment.find(".//LIBRARY_LAYOUT")
        for run in package.findall(".//RUN_SET/RUN"):
            accession = run.get("accession")
            if not accession:
                continue
            rows.append({
                "run_accession": accession, "experiment_accession": experiment.get("accession"),
                "bioproject": external.get("bioproject"), "biosample": external.get("biosample"),
                "sample_accession": sample.get("accession"),
                "study_accession": study.get("accession") if study is not None else None,
                "study_title": package.findtext(".//STUDY_TITLE"),
                "sample_title": sample.findtext("TITLE"), "experiment_title": experiment.findtext("TITLE"),
                "organism": sample.findtext(".//SCIENTIFIC_NAME"),
                "host": attr("host", "host scientific name", "host organism"),
                "tissue": attr("tissue", "tissue type", "isolation_source", "host_body_site"),
                "country": attr("geo_loc_name", "geographic location (country and/or sea)", "country"),
                "collection_date": attr("collection_date", "collection date"),
                "laboratory": experiment.get("center_name") or (study.get("center_name") if study is not None else None),
                "platform": platform[0].tag if platform is not None and len(platform) else None,
                "library_strategy": experiment.findtext(".//LIBRARY_STRATEGY"),
                "library_source": experiment.findtext(".//LIBRARY_SOURCE"),
                "library_selection": experiment.findtext(".//LIBRARY_SELECTION"),
                "layout": layout[0].tag if layout is not None and len(layout) else None,
                "total_spots": number(run.get("total_spots")), "total_bases": number(run.get("total_bases")),
                "proposed_helper": helper, "helper_status": "unknown",
                "retrieval_cohort": cohort, "attributes": attrs,
                "fastq_ftp": None, "fastq_md5": None, "fastq_bytes": None,
                "raw_read_availability": "unverified", "ena_status": "not_checked"})
    return rows


def enrich_ena(client, row):
    text = client.get("https://www.ebi.ac.uk/ena/portal/api/filereport", {
        "accession": row["run_accession"], "result": "read_run", "format": "tsv",
        "fields": "run_accession,fastq_ftp,fastq_md5,fastq_bytes"})
    matches = [r for r in csv.DictReader(io.StringIO(text), delimiter="\t")
               if r.get("run_accession") == row["run_accession"]]
    row["ena_status"] = "checked"
    if matches:
        row.update({k: matches[0].get(k) or None for k in ("fastq_ftp", "fastq_md5", "fastq_bytes")})
        if row["fastq_ftp"]:
            row["raw_read_availability"] = "ena_fastq_listed"
