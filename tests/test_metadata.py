import hashlib
import json
import tempfile
import shutil
import uuid
from contextlib import contextmanager
import unittest
from pathlib import Path
from unittest.mock import patch

from satellite_discovery.database_query import Client, helper_query
from satellite_discovery.metadata import parse_packages
from satellite_discovery.metadata_filter import assess
from satellite_discovery.report_generator import write_reports
from satellite_discovery.workflow import discover

@contextmanager
def scratch_directory():
    # Inherit directory permissions; Python's mode-700 Windows ACL conflicts with this sandbox.
    root = Path(tempfile.gettempdir()).resolve()
    path = root / ("satellite-test-" + uuid.uuid4().hex)
    path.mkdir(mode=0o755)
    try:
        yield str(path)
    finally:
        if path.resolve().parent != root:
            raise RuntimeError("Test scratch path escaped its parent")
        shutil.rmtree(path)

XML = '''<EXPERIMENT_PACKAGE_SET><EXPERIMENT_PACKAGE>
<STUDY accession="SRPTEST"><DESCRIPTOR><STUDY_TITLE>Example</STUDY_TITLE></DESCRIPTOR>
<IDENTIFIERS><EXTERNAL_ID namespace="BioProject">PRJNATEST</EXTERNAL_ID></IDENTIFIERS></STUDY>
<EXPERIMENT accession="SRXTEST" center_name="Example centre"><TITLE>Example experiment</TITLE>
<DESIGN><LIBRARY_DESCRIPTOR><LIBRARY_STRATEGY>RNA-Seq</LIBRARY_STRATEGY><LIBRARY_SOURCE>TRANSCRIPTOMIC</LIBRARY_SOURCE><LIBRARY_LAYOUT><PAIRED/></LIBRARY_LAYOUT></LIBRARY_DESCRIPTOR></DESIGN>
<PLATFORM><ILLUMINA/></PLATFORM></EXPERIMENT>
<SAMPLE accession="SRSTEST"><TITLE>=1+1</TITLE><SAMPLE_NAME><SCIENTIFIC_NAME>Homo sapiens</SCIENTIFIC_NAME></SAMPLE_NAME>
<IDENTIFIERS><EXTERNAL_ID namespace="BioSample">SAMNTEST</EXTERNAL_ID></IDENTIFIERS>
<SAMPLE_ATTRIBUTES><SAMPLE_ATTRIBUTE><TAG>host</TAG><VALUE>Homo sapiens</VALUE></SAMPLE_ATTRIBUTE></SAMPLE_ATTRIBUTES></SAMPLE>
<RUN_SET><RUN accession="SRRTEST1" total_spots="2000000" total_bases="600000000"/><RUN accession="SRRTEST2"/></RUN_SET>
</EXPERIMENT_PACKAGE></EXPERIMENT_PACKAGE_SET>'''


class MetadataTests(unittest.TestCase):
    def test_one_experiment_multiple_runs(self):
        rows = parse_packages(XML, "influenza-a")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["bioproject"], "PRJNATEST")
        self.assertEqual(rows[0]["biosample"], "SAMNTEST")
        self.assertEqual(rows[0]["total_spots"], 2000000)
        self.assertIsNone(rows[1]["total_spots"])
        self.assertEqual(rows[0]["helper_status"], "unknown")

    def test_namespace_and_single_package(self):
        xml = XML.replace('<EXPERIMENT_PACKAGE_SET>', '<EXPERIMENT_PACKAGE_SET xmlns="urn:sra">')
        self.assertEqual(len(parse_packages(xml, "x")), 2)
        self.assertEqual(len(parse_packages(XML.split('<EXPERIMENT_PACKAGE_SET>')[1].split('</EXPERIMENT_PACKAGE_SET>')[0], 'x')), 2)

    def test_amplicons_excluded(self):
        row = parse_packages(XML.replace("RNA-Seq", "AMPLICON"), "sars-cov-2")[0]
        self.assertEqual(assess(row)["selection"], "excluded")

    def test_missing_depth_not_zero(self):
        row = assess(parse_packages(XML, "x")[1])
        self.assertIn("sequencing_depth_unknown", row["warnings"])
        self.assertNotIn("below_minimum_sequencing_spots", row["exclusion_reasons"])

    def test_low_depth_excluded(self):
        row = assess(parse_packages(XML, "x")[0], min_spots=3000000)
        self.assertIn("below_minimum_sequencing_spots", row["exclusion_reasons"])

    def test_context_is_not_negative(self):
        row = assess(parse_packages(XML, "x", "study_context")[0])
        self.assertEqual(row["helper_status"], "unknown")
        self.assertIn("study_context_sample_not_a_confirmed_negative_control", row["warnings"])

    def test_html_and_csv_escape_metadata(self):
        rows = [assess(parse_packages(XML, "<script>evil</script>")[0])]
        with scratch_directory() as tmp:
            write_reports(tmp, rows)
            self.assertNotIn("<script>", Path(tmp, "report.html").read_text())
            self.assertIn("'=1+1", Path(tmp, "datasets.csv").read_text(encoding="utf-8-sig"))

    def test_empty_result_has_report(self):
        with scratch_directory() as tmp:
            write_reports(tmp, [])
            self.assertEqual(json.loads(Path(tmp, "datasets.json").read_text()), [])

    def test_query_is_not_taxonomy_only(self):
        self.assertIn("[All Fields]", helper_query("oc43-vr1558"))

    def test_default_query_targets_supported_broad_libraries(self):
        query = helper_query("oc43-vr1558")
        self.assertIn('"ILLUMINA"[Platform]', query)
        self.assertIn('"RNA-Seq"[Strategy]', query)
        self.assertIn('NOT "PCR"[Selection]', query)
        self.assertIn('[Publication Date]', query)


class TransportTests(unittest.TestCase):
    def test_offline_never_requests_network(self):
        with scratch_directory() as tmp, patch("satellite_discovery.database_query.urlopen") as network:
            with self.assertRaises(RuntimeError):
                Client(tmp, offline=True).get("https://example.org", {})
            network.assert_not_called()

    def test_corrupt_snapshot_rejected(self):
        with scratch_directory() as tmp:
            key = hashlib.sha256(b"https://example.org?").hexdigest()
            Path(tmp, key + ".txt").write_text("tampered")
            Path(tmp, key + ".json").write_text(json.dumps({"sha256": "wrong"}))
            with self.assertRaisesRegex(ValueError, "checksum"):
                Client(tmp, offline=True).get("https://example.org", {})

    def test_pagination_and_dedup(self):
        with scratch_directory() as tmp:
            client = Client(tmp)
            responses = [json.dumps({"esearchresult": {"count": "101", "idlist": [str(i) for i in range(100)]}}),
                         json.dumps({"esearchresult": {"count": "101", "idlist": ["100"]}})]
            with patch.object(client, "get", side_effect=responses) as get:
                self.assertEqual(len(client.search("x", 101)["ids"]), 101)
                self.assertEqual(get.call_args_list[1].args[1]["retstart"], 100)

    def test_workflow_end_to_end_and_parameter_guard(self):
        with scratch_directory() as tmp, patch.object(Client, "search", return_value={"ids": ["1"], "count": 1}), \
             patch.object(Client, "fetch", return_value=XML), \
             patch("satellite_discovery.workflow.enrich_ena"):
            self.assertEqual(discover("oc43-vr1558", 1, 0, False, tmp)["status"], "complete")
            self.assertEqual(len(json.loads(Path(tmp, "datasets.json").read_text())), 2)
            with self.assertRaisesRegex(ValueError, "different parameters"):
                discover("229e-vr740", 1, 0, False, tmp)

    def test_failed_ena_is_partial(self):
        with scratch_directory() as tmp, patch.object(Client, "search", return_value={"ids": ["1"], "count": 1}), \
             patch.object(Client, "fetch", return_value=XML), \
             patch("satellite_discovery.workflow.enrich_ena", side_effect=RuntimeError("unavailable")):
            result = discover("oc43-vr1558", 1, 0, False, tmp)
            self.assertEqual(result["status"], "partial")
            self.assertEqual(len(result["errors"]), 2)

    def test_failure_writes_manifest(self):
        with scratch_directory() as tmp, patch.object(Client, "search", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                discover("oc43-vr1558", 1, 0, False, tmp)
            self.assertEqual(json.loads(Path(tmp, "manifest.json").read_text())["status"], "failed")

    def test_study_diverse_search_stays_within_experiment_budget(self):
        with scratch_directory() as tmp, patch.object(Client, 'search', side_effect=[{'ids': ['1', '2'], 'count': 9}, {'ids': ['3'], 'count': 7}]) as search, \
             patch.object(Client, 'fetch', return_value=XML), patch('satellite_discovery.workflow.enrich_ena'):
            result = discover('oc43-vr1558', 3, 0, False, tmp)
            self.assertEqual(result['examined_experiment_ids'], ['1', '2', '3'])
            self.assertEqual(search.call_args_list[1].args[1], 1)
            self.assertIn('NOT (', search.call_args_list[1].args[0])
            self.assertIn('SRPTEST[All Fields]', search.call_args_list[1].args[0])

    def test_resume_reuses_frozen_query_cutoff(self):
        with scratch_directory() as tmp, patch.object(Client, 'search', return_value={'ids': [], 'count': 0}):
            first = discover('oc43-vr1558', 1, 0, False, tmp)
            with patch('satellite_discovery.workflow.helper_query', side_effect=AssertionError('Must retain old cutoff')):
                second = discover('oc43-vr1558', 1, 0, False, tmp)
            self.assertEqual(first['parameters'], second['parameters'])


if __name__ == "__main__":
    unittest.main()
