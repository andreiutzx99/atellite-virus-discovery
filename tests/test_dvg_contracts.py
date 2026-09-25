import hashlib
import html as html_lib
import json
from pathlib import Path
import tempfile
import unittest

from satellite_discovery import artifact_contracts, artifact_stage_handlers
from satellite_discovery import dvg_evidence


class DVGArtifactContractTests(unittest.TestCase):
    def write_json(self, path, value):
        path.write_text(json.dumps(value), encoding='utf-8')
        return path

    def test_raw_native_output_allows_zero_bytes_and_requires_bounded_utf8_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            native = root / 'Virus_Recombination_Results.txt'
            native.write_bytes(b'')
            self.assertIsNone(
                artifact_contracts.validate_artifact(native, 'dvg_raw_output')['record_count'])
            descriptor = artifact_contracts.describe_artifact(native, 'dvg_raw_output')
            self.assertEqual(descriptor['size_bytes'], 0)
            self.assertEqual(descriptor['validation_state'], 'valid')

            native.write_bytes(b'\xff')
            with self.assertRaisesRegex(ValueError, 'UTF-8'):
                artifact_contracts.validate_artifact(native, 'dvg_raw_output')
            native.write_bytes(b'a\x00b')
            with self.assertRaisesRegex(ValueError, 'NUL'):
                artifact_contracts.validate_artifact(native, 'dvg_raw_output')
            native.write_bytes(b'valid')
            renamed = root / 'results.txt'
            renamed.write_bytes(native.read_bytes())
            with self.assertRaisesRegex(ValueError, 'named'):
                artifact_contracts.validate_artifact(renamed, 'dvg_raw_output')

    def test_evidence_and_summary_contracts_delegate_strict_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = {
                'schema': 'dvg-evidence-v1',
                'caller': 'caller-a',
                'caller_version': '2.1',
                'status': dvg_evidence.NO_DVG_EVIDENCE_DETECTED,
                'events': [],
            }
            summary = {
                'schema': 'dvg-summary-v1',
                'caller': 'caller-a',
                'caller_version': '2.1',
                'status': dvg_evidence.NO_DVG_EVIDENCE_DETECTED,
                'event_count': 0,
            }
            evidence_path = self.write_json(root / 'evidence.json', evidence)
            summary_path = self.write_json(root / 'summary.json', summary)
            self.assertEqual(
                artifact_contracts.validate_artifact(evidence_path, 'dvg_evidence')['record_count'],
                0,
            )
            self.assertEqual(
                artifact_contracts.validate_artifact(summary_path, 'dvg_evidence_summary')['record_count'],
                0,
            )

            evidence['status'] = dvg_evidence.DVG_EVIDENCE_DETECTED
            self.write_json(evidence_path, evidence)
            with self.assertRaises(ValueError):
                artifact_contracts.validate_artifact(evidence_path, 'dvg_evidence')
            summary['event_count'] = True
            self.write_json(summary_path, summary)
            with self.assertRaises(ValueError):
                artifact_contracts.validate_artifact(summary_path, 'dvg_evidence_summary')

    def test_parameters_contract_requires_source_input_hashes_and_argv(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'parameters.json'
            value = {
                'schema': 'dvg-parameters-v1',
                'caller': 'caller-a',
                'caller_version': '2.1',
                'upstream_commit': 'a' * 40,
                'source_sha256': {'caller.py': hashlib.sha256(b'source').hexdigest()},
                'configuration': {'threshold': 2},
                'input_sha256': {'reads': hashlib.sha256(b'reads').hexdigest()},
                'command': ['caller', '--input', 'reads.fastq'],
            }
            self.write_json(path, value)
            self.assertEqual(
                artifact_contracts.validate_artifact(path, 'dvg_parameters')['source_count'],
                1,
            )
            for key, malformed in (
                    ('source_sha256', {}),
                    ('input_sha256', {'reads': 'bad'}),
                    ('command', ['caller', '']),
                    ('configuration', [])):
                broken = dict(value)
                broken[key] = malformed
                self.write_json(path, broken)
                with self.subTest(key=key), self.assertRaises(ValueError):
                    artifact_contracts.validate_artifact(path, 'dvg_parameters')

    def test_dvg_summary_report_is_concise_and_preserves_negative_limitation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = {
                'schema': 'dvg-summary-v1',
                'caller': 'caller-a',
                'caller_version': '2.1',
                'status': dvg_evidence.NO_DVG_EVIDENCE_DETECTED,
                'event_count': 0,
                'raw_output_location': 'raw/Virus_Recombination_Results.txt',
                'limitations': ['Configured caller output only.'],
            }
            source = self.write_json(root / 'summary.json', summary)
            artifact_stage_handlers.workflow_report(
                {'evaluation': source}, root / 'report', {'title': 'DVG report'})
            report = json.loads((root / 'report' / 'report.json').read_text(encoding='utf-8'))
            self.assertIn('does not establish that the sequence is not a DVG',
                          ' '.join(report['limitations']))
            html = (root / 'report' / 'report.html').read_text(encoding='utf-8')
            for visible in (
                    'caller-a', '2.1', dvg_evidence.NO_DVG_EVIDENCE_DETECTED,
                    'Event count', 'raw/Virus_Recombination_Results.txt',
                    'Configured caller output only.'):
                self.assertIn(visible, html)
            self.assertNotIn('<pre>', html)

    def test_evidence_report_uses_hash_bound_reference_not_event_dump(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            event = {
                'reference_id': 'REF',
                'acceptor_reference_id': 'REF',
                'breakpoint_1': 1,
                'breakpoint_2': 2,
                'raw_entry': 'PRIVATE_EVENT_DETAILS',
            }
            evidence = {
                'schema': 'dvg-evidence-v1',
                'caller': 'caller-a',
                'status': dvg_evidence.DVG_EVIDENCE_DETECTED,
                'events': [event],
            }
            source = self.write_json(root / 'evidence.json', evidence)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            artifact_stage_handlers.workflow_report(
                {'evidence': source}, root / 'report', {'title': 'Evidence report'})
            html = (root / 'report' / 'report.html').read_text(encoding='utf-8')
            report = json.loads((root / 'report' / 'report.json').read_text(encoding='utf-8'))
            reference = report['artifacts']['evidence']
            self.assertIn('event count: 1', html)
            self.assertIn(digest, html)
            self.assertEqual(reference['sha256'], digest)
            self.assertEqual(
                Path(reference['path']).resolve(strict=True),
                source.resolve(strict=True),
            )
            self.assertIn(html_lib.escape(reference['path']), html)
            self.assertNotIn('PRIVATE_EVENT_DETAILS', html)

    def test_other_json_schemas_keep_existing_full_summary_consolidation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            value = {'schema': 'ordinary-v1', 'payload': {'kept': True}}
            source = self.write_json(root / 'ordinary.json', value)
            artifact_stage_handlers.workflow_report(
                {'ordinary': source}, root / 'report', {'title': 'Ordinary report'})
            report = json.loads((root / 'report' / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['artifacts']['ordinary']['summary'], value)
            html = (root / 'report' / 'report.html').read_text(encoding='utf-8')
            self.assertIn('&quot;kept&quot;: true', html)


if __name__ == '__main__':
    unittest.main()