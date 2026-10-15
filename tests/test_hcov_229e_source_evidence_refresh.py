import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

from satellite_discovery import hcov_229e_source_evidence_refresh as refresh
from satellite_discovery.public_virus_exploratory_intake import evaluate_exploratory_intake
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


def fixture_responder(requested, mutate=None, fail_at=None):
    fixtures = {
        name: (FIXTURES / filename).read_bytes()
        for name, filename in {
            "geo_sample": "geo_sample.soft", "geo_series": "geo_series.soft",
            "biosample": "biosample.xml", "sra": "sra.xml",
            "ena_run": "ena_run.tsv", "pubmed": "pubmed.xml",
        }.items()
    }
    search_ids = {"biosample": "15776099", "sra": "11593710", "pubmed": "33630927"}

    def fake_get(url):
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if parts.path.endswith("/geo/query/acc.cgi"):
            name = "geo_sample" if query["acc"][0] == refresh.TARGET["geo_sample"] else "geo_series"
            body = fixtures[name]
        elif parts.path.endswith("/filereport"):
            name, body = "ena_run", fixtures["ena_run"]
        elif parts.path.endswith("/esearch.fcgi"):
            db = query["db"][0]
            name = db + "_search"
            body = json.dumps({"esearchresult": {
                "count": "1", "idlist": [search_ids[db]],
            }}).encode()
        elif parts.path.endswith("/efetch.fcgi"):
            name = query["db"][0]
            body = fixtures[name]
        else:
            raise AssertionError("Unexpected URL reached metadata refresher: " + url)
        requested.append(url)
        if fail_at == name:
            raise refresh.SourceEvidenceError("source_unavailable", "Synthetic source failure.")
        if mutate is not None:
            body = mutate(name, body)
        return {
            "url": url, "final_url": url, "http_status": 200,
            "content_type": "application/xml",
            "headers": {"date": "Wed, 14 Oct 2026 22:00:00 GMT"},
            "retrieved_utc": "2026-10-14T22:00:00+00:00", "bytes": body,
            "byte_count": len(body), "sha256": hashlib.sha256(body).hexdigest(),
        }

    return fake_get


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

    def test_malformed_sra_and_publication_records_have_structured_errors(self):
        with self.assertRaisesRegex(refresh.SourceEvidenceError, "missing experiment"):
            refresh.parse_sra(
                b"<EXPERIMENT_PACKAGE_SET><EXPERIMENT_PACKAGE><RUN accession='SRR12424250'/>"
                b"</EXPERIMENT_PACKAGE></EXPERIMENT_PACKAGE_SET>"
            )
        with self.assertRaisesRegex(refresh.SourceEvidenceError, "no Article element"):
            refresh.parse_pubmed(
                b"<PubmedArticleSet><PubmedArticle><MedlineCitation/></PubmedArticle></PubmedArticleSet>"
            )

    def test_full_refresh_blocks_changed_treatment_and_accession_links(self):
        evidence = evidence_document()
        scenarios = [
            (
                "treatment",
                lambda name, body: body.replace(b"24 hours", b"48 hours")
                if name == "geo_sample" else body,
                "biosample_relationship_or_treatment_conflict",
            ),
            (
                "accession",
                lambda name, body: body.replace(b"SRX8920123", b"SRX00000000")
                if name == "geo_sample" else body,
                "geo_relationship_conflict",
            ),
        ]
        for label, mutate, error_code in scenarios:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                requested = []
                target = Path(temp) / "snapshot"
                with patch.object(refresh, "_get", side_effect=fixture_responder(requested, mutate)):
                    with self.assertRaises(refresh.SourceEvidenceError) as caught:
                        refresh.refresh_source_evidence(evidence, target)
                self.assertEqual(caught.exception.code, error_code)
                self.assertFalse((target / "source_manifest.json").exists())

    def test_source_timeout_and_metadata_failure_fail_closed(self):
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra"
        with patch.object(refresh, "RETRIES", 0), patch.object(
            refresh._OPENER, "open", side_effect=TimeoutError("fixture timeout"),
        ):
            with self.assertRaises(refresh.SourceEvidenceError) as caught:
                refresh._get(url)
        self.assertEqual(caught.exception.code, "source_unavailable")

        with tempfile.TemporaryDirectory() as temp:
            requested = []
            target = Path(temp) / "snapshot"
            with patch.object(refresh, "_get", side_effect=fixture_responder(
                requested, fail_at="geo_sample",
            )):
                with self.assertRaises(refresh.SourceEvidenceError) as caught:
                    refresh.refresh_source_evidence(evidence_document(), target)
            self.assertEqual(caught.exception.code, "source_unavailable")
            self.assertFalse((target / "source_manifest.json").exists())
            self.assertFalse(any(target.iterdir()))

    def test_invalid_content_length_is_a_structured_source_error(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.status = 200
        response.geturl.return_value = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=sra"
        response.headers.get.side_effect = lambda key, default=None: {
            "Content-Length": "not-a-number", "Content-Encoding": "identity",
        }.get(key, default)
        with patch.object(refresh, "_OPENER", MagicMock(open=MagicMock(return_value=response))):
            with self.assertRaises(refresh.SourceEvidenceError) as caught:
                refresh._get(response.geturl.return_value)
        self.assertEqual(caught.exception.code, "source_content_length_invalid")

    def test_bounded_refresh_preserves_exact_metadata_bytes_and_never_fetches_reads(self):
        requested = []
        docs = Path(__file__).parent.parent / "docs"
        signed_evidence = json.loads(
            (docs / "hcov-229e-exploratory-intake-evidence-v1.json").read_text()
        )
        approval_template = json.loads(
            (docs / "hcov-229e-exploratory-scientific-approval-v1.json").read_text()
        )

        with tempfile.TemporaryDirectory() as temp:
            target_dir = Path(temp) / "snapshots"
            with patch.object(refresh, "_get", side_effect=fixture_responder(requested)):
                result = refresh.refresh_source_evidence(signed_evidence, target_dir)
            review = evaluate_exploratory_intake(
                result["document"], target_dir, signed_evidence, approval_template,
            )
            self.assertEqual(result["metadata"]["fastq_manifest_sha256"],
                             signed_evidence["fastq_manifest_sha256"])
            self.assertEqual(review["result"], "candidate_for_scientific_review")
            self.assertEqual(review["original_strict_policy"]["identity_status"], "insufficient")
            self.assertEqual(review["sequence_confirmation_status"], "NOT_ASSESSED")
            self.assertFalse(review["authorizing"])
            self.assertEqual(review["current_eligibility"], "HELD")
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
