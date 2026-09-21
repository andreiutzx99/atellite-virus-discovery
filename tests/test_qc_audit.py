import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_metadata import scratch_directory
from test_reads import gz, fixture_read
from satellite_discovery.qc_audit import audit, render_report
from satellite_discovery.quality_control import run_qc
from satellite_discovery.sequence_downloader import checksum, write_json
from satellite_discovery import audit_wizard


class AuditTests(unittest.TestCase):
    def test_wizard_full_audit_and_browser_report(self):
        with scratch_directory() as root:
            root = Path(root)
            directory = self.fixture(root)
            with patch('builtins.input', side_effect=[str(directory), '2']), patch('builtins.print'), \
                    patch.object(audit_wizard, '__file__', str(root / 'package' / 'audit_wizard.py')), \
                    patch.object(audit_wizard.webbrowser, 'open') as browser:
                self.assertEqual(audit_wizard.main(), 0)
            reports = list(root.glob('audits/*/audit.json'))
            self.assertEqual(len(reports), 1)
            self.assertTrue(json.loads(reports[0].read_text())['fastq_records_recounted'])
            self.assertTrue(reports[0].with_name('report.html').is_file())
            browser.assert_called_once()

    def test_wizard_invalid_mode_does_not_audit(self):
        with scratch_directory() as root:
            directory = self.fixture(root)
            with patch('builtins.input', side_effect=[str(directory), '3']), patch('builtins.print'), \
                    patch.object(audit_wizard, 'audit') as check:
                self.assertEqual(audit_wizard.main(), 1)
                check.assert_not_called()

    def test_run_folder_discovery(self):
        with scratch_directory() as root:
            parent = Path(root) / 'phase3' / 'SRR123'
            parent.mkdir(parents=True)
            directory = self.fixture(parent)
            self.assertEqual(audit_wizard.find_qc_folders(root), [directory.resolve()])

    def test_html_distinguishes_checksum_only_and_full_audit(self):
        with scratch_directory() as root:
            result = audit(self.fixture(root), progress=lambda _: None)
            result['qc_directory'] = '<script>example</script>'
            report = render_report(result)
            self.assertIn('FASTQ records not recounted', report)
            self.assertIn('&lt;script&gt;', report)
            self.assertNotIn('<script>', report)
            result['fastq_records_recounted'] = True
            self.assertIn('paired identifiers', render_report(result))

    def fixture(self, root):
        root = Path(root)
        inputs = {role: gz(root / (role + '.gz'), fixture_read('pair/' + mate))
                  for role, mate in [('R1', '1'), ('R2', '2')]}
        directory = root / 'qc'
        run_qc(inputs, directory, progress=lambda _: None)
        return directory

    def test_old_version_full_audit_does_not_modify_sources(self):
        with scratch_directory() as root:
            directory = self.fixture(root)
            marker = directory / 'qc.json'
            data = json.loads(marker.read_text())
            data['fingerprint']['software_version'] = '0.2.0'
            write_json(marker, data)
            before = {p.name: (checksum(p), p.stat().st_mtime_ns) for p in directory.iterdir()}
            result = audit(directory, full=True, progress=lambda _: None)
            self.assertEqual(result['retained_reads_reported'], 2)
            self.assertEqual(result['source_version'], '0.2.0')
            self.assertEqual(result['observed_reads_by_file']['clean_R1.fastq.gz'], 1)
            self.assertEqual(before, {p.name: (checksum(p), p.stat().st_mtime_ns) for p in directory.iterdir()})

    def test_corrupted_file_rejected(self):
        with scratch_directory() as root:
            directory = self.fixture(root)
            (directory / 'clean_R1.fastq.gz').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                audit(directory, progress=lambda _: None)

    def test_unsafe_names_rejected(self):
        with scratch_directory() as root:
            directory = self.fixture(root)
            data = json.loads((directory / 'qc.json').read_text())
            data['output_sha256']['../outside'] = 'a' * 64
            write_json(directory / 'qc.json', data)
            with self.assertRaisesRegex(ValueError, 'filenames'):
                audit(directory, progress=lambda _: None)

    def test_accounting_rejected(self):
        with scratch_directory() as root:
            directory = self.fixture(root)
            data = json.loads((directory / 'qc.json').read_text())
            data['before']['reads'] += 1
            write_json(directory / 'qc.json', data)
            with self.assertRaisesRegex(ValueError, 'accounting'):
                audit(directory, progress=lambda _: None)

    def test_full_mode_detects_mate_mismatch_even_with_updated_hash(self):
        with scratch_directory() as root:
            directory = self.fixture(root)
            path = gz(directory / 'clean_R2.fastq.gz', fixture_read('other/2'))
            data = json.loads((directory / 'qc.json').read_text())
            data['output_sha256'][path.name] = checksum(path)
            write_json(directory / 'qc.json', data)
            with self.assertRaisesRegex(ValueError, 'identifiers'):
                audit(directory, full=True, progress=lambda _: None)

    def test_full_mode_detects_count_mismatch(self):
        with scratch_directory() as root:
            directory = self.fixture(root)
            path = gz(directory / 'clean_single.fastq.gz', fixture_read())
            data = json.loads((directory / 'qc.json').read_text())
            data['output_sha256'][path.name] = checksum(path)
            write_json(directory / 'qc.json', data)
            with self.assertRaisesRegex(ValueError, 'Observed FASTQ counts'):
                audit(directory, full=True, progress=lambda _: None)
