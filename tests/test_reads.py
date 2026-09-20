import gzip
import hashlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery.quality_control import QCConfig, records, run_qc, trim
from satellite_discovery.sequence_downloader import download_file, files_for_run, make_plan
from satellite_discovery.read_workflow import prepare_reads
from satellite_discovery.report_generator import write_reports


def fixture_read(name='r1', sequence='ACGT' * 10, quality=None):
    return f'@{name}\n{sequence}\n+\n{quality if quality is not None else "I" * len(sequence)}\n'


def gz(path, content):
    Path(path).write_bytes(gzip.compress(content.encode('ascii'), mtime=0))
    return Path(path)


def spec_for(content=b'example', name='SRR123.fastq.gz'):
    return {'url': 'https://ftp.sra.ebi.ac.uk/vol1/fastq/' + name,
            'name': name, 'bytes': len(content), 'md5': hashlib.md5(content).hexdigest(), 'role': 'single'}


def row_for(content=b'example'):
    spec = spec_for(content)
    return {'run_accession': 'SRR123', 'selection': 'eligible_for_review', 'platform': 'ILLUMINA',
            'library_strategy': 'RNA-Seq', 'total_spots': 1000000, 'layout': 'SINGLE',
            'study_accession': 'SRP1', 'fastq_ftp': spec['url'], 'fastq_md5': spec['md5'],
            'fastq_bytes': str(spec['bytes'])}


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status, self.headers = status, headers or {}


class DownloadTests(unittest.TestCase):
    def test_success_and_verified_offline_reuse(self):
        content = b'archive data'
        with scratch_directory() as tmp, patch('satellite_discovery.sequence_downloader.urlopen', return_value=Response(content)) as net:
            path = download_file(spec_for(content), tmp, progress=lambda _: None)
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(download_file(spec_for(content), tmp, offline=True, progress=lambda _: None), path)
            self.assertEqual(net.call_count, 1)

    def test_valid_range_resume(self):
        data = b'0123456789'
        with scratch_directory() as tmp:
            Path(tmp, 'SRR123.fastq.gz.part').write_bytes(data[:4])
            with patch('satellite_discovery.sequence_downloader.urlopen', return_value=Response(data[4:], 206, {'Content-Range': 'bytes 4-9/10'})) as net:
                self.assertEqual(download_file(spec_for(data), tmp).read_bytes(), data)
                self.assertEqual(net.call_args.args[0].headers['Range'], 'bytes=4-')

    def test_range_ignored_restarts_instead_of_appending(self):
        data = b'0123456789'
        with scratch_directory() as tmp:
            Path(tmp, 'SRR123.fastq.gz.part').write_bytes(data[:4])
            with patch('satellite_discovery.sequence_downloader.urlopen', return_value=Response(data)):
                self.assertEqual(download_file(spec_for(data), tmp).read_bytes(), data)

    def test_wrong_content_range_is_rejected(self):
        with scratch_directory() as tmp, patch('satellite_discovery.sequence_downloader.urlopen', return_value=Response(b'example', 206, {'Content-Range': 'bytes 2-8/9'})):
            with self.assertRaisesRegex(ValueError, 'Content-Range'):
                download_file(spec_for(), tmp)
            self.assertFalse(Path(tmp, 'SRR123.fastq.gz').exists())

    def test_wrong_checksum_never_commits_file(self):
        with scratch_directory() as tmp, patch('satellite_discovery.sequence_downloader.urlopen', return_value=Response(b'changed')):
            with self.assertRaisesRegex(ValueError, 'MD5'):
                download_file(spec_for(), tmp)
            self.assertFalse(Path(tmp, 'SRR123.fastq.gz').exists())

    def test_oversized_response_never_commits_file(self):
        with scratch_directory() as tmp, patch('satellite_discovery.sequence_downloader.urlopen', return_value=Response(b'far too much data')):
            with self.assertRaisesRegex(ValueError, 'byte budget'):
                download_file(spec_for(), tmp)

    def test_partial_short_response_can_retry(self):
        with scratch_directory() as tmp, patch('satellite_discovery.sequence_downloader.time.sleep'), patch('satellite_discovery.sequence_downloader.urlopen', side_effect=[Response(b'ex'), Response(b'ample', 206, {'Content-Range': 'bytes 2-6/7'})]):
            self.assertEqual(download_file(spec_for(), tmp).read_bytes(), b'example')

    def test_existing_corrupt_file_refused(self):
        with scratch_directory() as tmp:
            Path(tmp, 'SRR123.fastq.gz').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                download_file(spec_for(), tmp)

    def test_budget_never_splits_pairs(self):
        row = row_for()
        row.update({'layout': 'PAIRED', 'fastq_ftp': 'ftp.sra.ebi.ac.uk/SRR123_1.fastq.gz;ftp.sra.ebi.ac.uk/SRR123_2.fastq.gz',
                    'fastq_md5': 'a' * 32 + ';' + 'b' * 32, 'fastq_bytes': '60;60'})
        self.assertEqual(make_plan([row], 1, 100)['selected'], [])
        self.assertEqual(make_plan([row], 1, 120)['planned_bytes'], 120)

    def test_file_roles_not_dependent_on_ena_order(self):
        row = row_for()
        row.update({'layout': 'PAIRED', 'fastq_ftp': 'ftp.sra.ebi.ac.uk/SRR123_2.fastq.gz;ftp.sra.ebi.ac.uk/SRR123_1.fastq.gz;ftp.sra.ebi.ac.uk/SRR123.fastq.gz',
                    'fastq_md5': ';'.join(['a' * 32] * 3), 'fastq_bytes': '60;60;10'})
        self.assertEqual([f['role'] for f in files_for_run(row)], ['R1', 'R2', 'single'])

    def test_malicious_or_inconsistent_metadata_rejected(self):
        for update in [{'run_accession': '../escape'}, {'fastq_ftp': 'https://evil.test/SRR123.fastq.gz'},
                       {'fastq_md5': 'invalid'}, {'fastq_bytes': '-10'}, {'layout': 'PAIRED'}]:
            row = row_for()
            row.update(update)
            with self.assertRaises(ValueError):
                files_for_run(row)


class QCTests(unittest.TestCase):
    def test_adapter_and_low_quality_ends(self):
        config = QCConfig(min_length=10)
        seq = 'T' + 'ACGT' * 10 + config.adapters[0]
        record, reason, hit = trim(('@x', seq, '!' + 'I' * (len(seq) - 1)), config)
        self.assertIsNone(reason)
        self.assertTrue(hit)
        self.assertEqual(record[1], 'ACGT' * 10)

    def test_short_suffix_adapter(self):
        seq = 'C' * 40 + 'AGATCGGAAGAG'
        result, reason, hit = trim(('@x', seq, 'I' * len(seq)), QCConfig())
        self.assertTrue(hit)
        self.assertEqual(result[1], 'C' * 40)

    def test_internal_short_match_not_trimmed(self):
        seq = 'C' * 20 + 'AGATCGGAAGAG' + 'G' * 20
        result, _, hit = trim(('@x', seq, 'I' * len(seq)), QCConfig())
        self.assertFalse(hit)
        self.assertEqual(result[1], seq)

    def test_paired_filter_preserves_good_orphan_and_original_reject(self):
        with scratch_directory() as tmp:
            r1 = gz(Path(tmp, 'r1.gz'), fixture_read('a/1') + fixture_read('b/1'))
            r2 = gz(Path(tmp, 'r2.gz'), fixture_read('a/2') + fixture_read('b/2', quality='!' * 40))
            result = run_qc({'R1': r1, 'R2': r2}, Path(tmp, 'out'))
            self.assertEqual(result['counts']['retained_pairs'], 1)
            self.assertEqual(result['counts']['retained_orphans'], 1)
            self.assertEqual(result['before']['reads'], 4)
            self.assertEqual(result['after']['reads'], 3)
            self.assertEqual(len(list(records(Path(tmp, 'out/rejected.fastq.gz')))), 1)
            self.assertEqual(len(list(records(Path(tmp, 'out/orphan_R1.fastq.gz')))), 1)

    def test_pair_mismatch_fails_without_completion_marker(self):
        with scratch_directory() as tmp:
            a = gz(Path(tmp, 'a.gz'), fixture_read('a/1'))
            b = gz(Path(tmp, 'b.gz'), fixture_read('b/2'))
            with self.assertRaisesRegex(ValueError, 'identifiers'):
                run_qc({'R1': a, 'R2': b}, Path(tmp, 'out'))
            self.assertFalse(Path(tmp, 'out/qc.json').exists())

    def test_unequal_pairs_fail(self):
        with scratch_directory() as tmp:
            a = gz(Path(tmp, 'a.gz'), fixture_read('a/1') + fixture_read('b/1'))
            b = gz(Path(tmp, 'b.gz'), fixture_read('a/2'))
            with self.assertRaisesRegex(ValueError, 'different record counts'):
                run_qc({'R1': a, 'R2': b}, Path(tmp, 'out'))

    def test_wrong_mate_orientation_fails(self):
        with scratch_directory() as tmp:
            a = gz(Path(tmp, 'a.gz'), fixture_read('a/2'))
            b = gz(Path(tmp, 'b.gz'), fixture_read('a/1'))
            with self.assertRaisesRegex(ValueError, 'wrong'):
                run_qc({'R1': a, 'R2': b}, Path(tmp, 'out'))

    def test_bad_fastq_rejected(self):
        for content in ['@r\nACGT\n+\nII\n', '@r\nACGT\n+\n', '@r\nACXT\n+\nIIII\n']:
            with scratch_directory() as tmp:
                path = gz(Path(tmp, 'bad.gz'), content)
                with self.assertRaises(ValueError):
                    list(records(path))

    def test_optional_separator_identifier_with_header_description(self):
        with scratch_directory() as tmp:
            path = gz(Path(tmp, 'valid.gz'), '@r description\nACGT\n+r\nIIII\n')
            self.assertEqual(len(list(records(path))), 1)

    def test_qc_reuse_and_parameter_invalidation(self):
        with scratch_directory() as tmp:
            path = gz(Path(tmp, 'input.gz'), fixture_read())
            first = run_qc({'single': path}, Path(tmp, 'qc'))
            with patch('satellite_discovery.quality_control.records', side_effect=AssertionError('Must reuse')):
                second = run_qc({'single': path}, Path(tmp, 'qc'))
            self.assertEqual(first['output_sha256'], second['output_sha256'])
            with self.assertRaisesRegex(ValueError, 'parameters changed'):
                run_qc({'single': path}, Path(tmp, 'qc'), QCConfig(min_length=20))

    def test_no_surviving_reads_visible(self):
        with scratch_directory() as tmp:
            path = gz(Path(tmp, 'input.gz'), fixture_read(quality='!' * 40))
            result = run_qc({'single': path}, Path(tmp, 'qc'))
            self.assertEqual(result['warnings'], ['No reads survived QC'])
            self.assertIsNone(result['after']['q30_fraction'])

    def test_n_fraction_and_metrics(self):
        with scratch_directory() as tmp:
            path = gz(Path(tmp, 'input.gz'), fixture_read(sequence='N' * 40) + fixture_read(sequence='GC' * 20))
            result = run_qc({'single': path}, Path(tmp, 'qc'))
            self.assertEqual(result['after']['gc_fraction_all_bases'], 1)
            self.assertEqual(result['rejection_reasons']['too_many_N_bases'], 1)


class ReadWorkflowTests(unittest.TestCase):
    def test_download_qc_and_offline_replay(self):
        content = gzip.compress(fixture_read().encode(), mtime=0)
        with scratch_directory() as tmp:
            Path(tmp, 'datasets.json').write_text(json.dumps([row_for(content)]))
            with patch('satellite_discovery.sequence_downloader.urlopen', return_value=Response(content)):
                result = prepare_reads(tmp)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['runs'][0]['retained_reads'], 1)
            with patch('satellite_discovery.sequence_downloader.urlopen', side_effect=AssertionError('No network')):
                self.assertEqual(prepare_reads(tmp, offline=True)['status'], 'complete')
            self.assertFalse(Path(tmp, 'phase3/.running.lock').exists())

    def test_empty_plan_is_not_successful_qc(self):
        with scratch_directory() as tmp:
            Path(tmp, 'datasets.json').write_text('[]')
            self.assertEqual(prepare_reads(tmp)['status'], 'no_suitable_downloads')

    def test_download_failure_recorded(self):
        with scratch_directory() as tmp:
            Path(tmp, 'datasets.json').write_text(json.dumps([row_for()]))
            with patch('satellite_discovery.read_workflow.download_file', side_effect=RuntimeError('connection failure')):
                result = prepare_reads(tmp)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['errors'][0]['accession'], 'SRR123')

    def test_running_lock_prevents_second_writer(self):
        with scratch_directory() as tmp:
            Path(tmp, 'datasets.json').write_text('[]')
            Path(tmp, 'phase3').mkdir()
            Path(tmp, 'phase3/.running.lock').write_text('123')
            with self.assertRaisesRegex(RuntimeError, 'already running'):
                prepare_reads(tmp)

    def test_user_interrupt_records_stage_and_releases_lock(self):
        with scratch_directory() as tmp:
            Path(tmp, 'datasets.json').write_text(json.dumps([row_for()]))
            with patch('satellite_discovery.read_workflow.download_file', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    prepare_reads(tmp)
            result = json.loads(Path(tmp, 'phase3/manifest.json').read_text())
            self.assertEqual(result['status'], 'interrupted')
            self.assertFalse(Path(tmp, 'phase3/.running.lock').exists())

    def test_report_displays_read_stage_and_keeps_checksums_current(self):
        with scratch_directory() as tmp:
            Path(tmp, 'manifest.json').write_text(json.dumps({'status': 'complete'}))
            Path(tmp, 'phase3').mkdir()
            Path(tmp, 'phase3/manifest.json').write_text(json.dumps({'status': 'complete', 'runs': [{'accession': 'SRR123', 'status': 'complete', 'input_reads': 20, 'retained_reads': 18}], 'errors': []}))
            write_reports(tmp, [])
            report = Path(tmp, 'report.html').read_text()
            self.assertIn('Download and QC: complete', report)
            self.assertNotIn('Reads have not been downloaded', report)
            manifest = json.loads(Path(tmp, 'manifest.json').read_text())
            self.assertEqual(manifest['output_sha256']['report.html'], hashlib.sha256(Path(tmp, 'report.html').read_bytes()).hexdigest())
