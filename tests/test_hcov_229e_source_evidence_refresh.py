import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from satellite_discovery import hcov_229e_source_evidence_refresh as refresh
from satellite_discovery.sequence_downloader import files_for_run
from satellite_discovery.public_virus_acquisition_preflight import fastq_manifest_sha256


FIXTURES = Path(__file__).parent / "fixtures" / "hcov229e_sources" / "real_reduced"


def evidence_document():
    ena = refresh.parse_ena((FIXTURES / "ena_run.tsv").read_bytes())
    files = files_for_run({"run_accession": refresh.TARGET["run"], "layout": "SINGLE", **ena})
    return {
        "scope": refresh.TARGET,
        "exposure_record": {"sample_treatment": {
            "archive_annotation": "Infected with HCoV-229E virus for 24 hours",
            "reported_virus": "HCoV-229E", "condition": "REPORTED_INFECTED",
            "timepoint_hours": 24,
        }},
        "fastq_files": files,
        "fastq_manifest_sha256": fastq_manifest_sha256(files),
    }


class HCoV229ESourceRefreshTests(unittest.TestCase):
    def test_reduced_real_sources_reconcile_exact_scope(self):
        sample = refresh.parse_geo_soft(
            (FIXTURES / "geo_sample.soft").read_bytes(), "sample", refresh.TARGET["geo_sample"],
        )
        series = refresh.parse_geo_soft(
            (FIXTURES / "geo_series.soft").read_bytes(), "series", refresh.TARGET["geo_series"],
        )
        biosample = refresh.parse_biosample((FIXTURES / "biosample.xml").read_bytes())
        sra = refresh.parse_sra((FIXTURES / "sra.xml").read_bytes())
        ena = refresh.parse_ena((FIXTURES / "ena_run.tsv").read_bytes())
        publication = refresh.parse_pubmed((FIXTURES / "pubmed.xml").read_bytes())

        refresh._material_check(evidence_document(), sample, series, biosample, sra, ena, publication)
        self.assertEqual(sra["run"], "SRR12424250")
        self.assertEqual(publication["doi"], refresh.DOI)
        self.assertEqual(sample["characteristics"]["treatment"],
                         ["Infected with HCoV-229E virus for 24 hours"])

    def test_withdrawn_geo_record_is_rejected(self):
        data = (FIXTURES / "geo_sample.soft").read_bytes().replace(
            b"Public on Mar 03 2021", b"Withdrawn on Mar 03 2021",
        )
        sample = refresh.parse_geo_soft(data, "sample", refresh.TARGET["geo_sample"])
        series = refresh.parse_geo_soft(
            (FIXTURES / "geo_series.soft").read_bytes(), "series", refresh.TARGET["geo_series"],
        )
        biosample = refresh.parse_biosample((FIXTURES / "biosample.xml").read_bytes())
        sra = refresh.parse_sra((FIXTURES / "sra.xml").read_bytes())
        ena = refresh.parse_ena((FIXTURES / "ena_run.tsv").read_bytes())
        publication = refresh.parse_pubmed((FIXTURES / "pubmed.xml").read_bytes())
        with self.assertRaisesRegex(refresh.SourceEvidenceError, "GEO sample/series links"):
            refresh._material_check(evidence_document(), sample, series, biosample, sra, ena, publication)

    def test_source_payloads_reject_duplicate_or_mismatched_records(self):
        data = (FIXTURES / "geo_sample.soft").read_bytes()
        with self.assertRaisesRegex(refresh.SourceEvidenceError, "GEO response"):
            refresh.parse_geo_soft(data, "sample", "GSM0000000")
        with self.assertRaisesRegex(refresh.SourceEvidenceError, "entity declarations"):
            refresh.parse_biosample(b"<!DOCTYPE x [<!ENTITY y 'z'>]><x>&y;</x>")
        ena = (FIXTURES / "ena_run.tsv").read_bytes()
        with self.assertRaisesRegex(refresh.SourceEvidenceError, "exactly the requested run"):
            refresh.parse_ena(ena + ena.splitlines(keepends=True)[1])

    def test_bounded_refresh_preserves_exact_metadata_bytes_and_never_fetches_reads(self):
        fixtures = {
            "geo_sample": (FIXTURES / "geo_sample.soft").read_bytes(),
            "geo_series": (FIXTURES / "geo_series.soft").read_bytes(),
            "biosample": (FIXTURES / "biosample.xml").read_bytes(),
            "sra": (FIXTURES / "sra.xml").read_bytes(),
            "ena_run": (FIXTURES / "ena_run.tsv").read_bytes(),
            "pubmed": (FIXTURES / "pubmed.xml").read_bytes(),
        }
        search_ids = {"biosample": "15776099", "sra": "11593710", "pubmed": "33630927"}
        requested = []

        def fake_get(url):
            parts = urlsplit(url)
            query = parse_qs(parts.query)
            requested.append(url)
            if parts.path.endswith("/geo/query/acc.cgi"):
                key = "geo_sample" if query["acc"][0] == refresh.TARGET["geo_sample"] else "geo_series"
                body = fixtures[key]
            elif parts.path.endswith("/filereport"):
                body = fixtures["ena_run"]
            elif parts.path.endswith("/esearch.fcgi"):
                db = query["db"][0]
                body = json.dumps({"esearchresult": {
                    "count": "1", "idlist": [search_ids[db]],
                }}).encode()
            elif parts.path.endswith("/efetch.fcgi"):
                body = fixtures[query["db"][0]]
            else:
                self.fail("Unexpected URL reached the metadata refresher: " + url)
            return {
                "url": url, "final_url": url, "http_status": 200,
                "content_type": "application/xml", "headers": {"date": "Wed, 14 Oct 2026 22:00:00 GMT"},
                "retrieved_utc": "2026-10-14T22:00:00+00:00", "bytes": body,
                "byte_count": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            }

        with tempfile.TemporaryDirectory() as temp:
            target_dir = Path(temp) / "snapshots"
            with patch.object(refresh, "_get", side_effect=fake_get):
                result = refresh.refresh_source_evidence(evidence_document(), target_dir)
            self.assertEqual(result["metadata"]["fastq_manifest_sha256"],
                             evidence_document()["fastq_manifest_sha256"])
            self.assertEqual(len(result["document"]["manifest"]["snapshot_index"]), 9)
            manifest = json.loads((target_dir / "source_manifest.json").read_text())
            self.assertEqual(len(manifest["sources"]), 9)
            for entry in result["document"]["manifest"]["snapshot_index"]:
                self.assertEqual(
                    hashlib.sha256((target_dir / entry["name"]).read_bytes()).hexdigest(),
                    entry["sha256"],
                )
            self.assertFalse(any(
                "ftp.ebi.ac.uk" in url or "ftp.sra.ebi.ac.uk" in url
                for url in requested
            ))
            self.assertEqual(len(requested), 9)


if __name__ == "__main__":
    unittest.main()
