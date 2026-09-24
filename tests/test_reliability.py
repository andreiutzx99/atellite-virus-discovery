"""Platform-independent regression tests using only artificial local artifacts."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery import artifact_workflow, dependency_review, reference_snapshot
from satellite_discovery.portable_paths import portable_name
from satellite_discovery.sequence_downloader import checksum
from satellite_discovery import alignment_adapter, bounded_process, review_stage


class WorkflowDiagnosticsTests(unittest.TestCase):
    def fixture(self, root):
        (root/'input.fa').write_text('>fixture\nACGTACGT\n')
        spec = {'schema': 'artifact-workflow-v1', 'stages': [
            {'id': 'inventory', 'kind': 'inventory', 'inputs': {'fasta': 'input.fa'}},
            {'id': 'quality', 'kind': 'sequence_quality', 'inputs': {
                'fasta': {'stage': 'inventory', 'artifact': 'sequences.fasta'}}},
            {'id': 'last', 'kind': 'sequence_quality', 'inputs': {'fasta': 'input.fa'}}]}
        path = root/'workflow.json'
        path.write_text(json.dumps(spec))
        return path

    def test_failure_reports_stage_error_and_pending_work_then_resumes(self):
        with scratch_directory() as folder:
            root = Path(folder); spec = self.fixture(root); output = root/'out'
            with patch('satellite_discovery.sequence_quality.measures', side_effect=RuntimeError('<fixture failure>')):
                with self.assertRaises(RuntimeError):
                    artifact_workflow.run(spec, output)
            failed = json.loads((output/'workflow.json').read_text())
            self.assertEqual([s['status'] for s in failed['stages']], ['complete', 'failed', 'pending'])
            self.assertEqual(failed['stages'][1]['error_type'], 'RuntimeError')
            self.assertIn('finished_utc', failed['stages'][1])
            report = (output/'report.html').read_text()
            self.assertIn('&lt;fixture failure&gt;', report)
            self.assertNotIn('<fixture failure>', report)
            self.assertIn('href="inventory/report.html"', report)
            self.assertNotIn('file:', report)
            self.assertEqual(failed['report_sha256'], checksum(output/'report.html'))
            first = (output/'inventory/manifest.json').read_bytes()
            artifact_workflow.run(spec, output)
            self.assertEqual(first, (output/'inventory/manifest.json').read_bytes())
            self.assertEqual(json.loads((output/'workflow.json').read_text())['status'], 'complete')

    def test_interrupt_has_named_stage_and_releases_lock(self):
        with scratch_directory() as folder:
            root = Path(folder); spec = self.fixture(root); output = root/'out'
            with patch('satellite_discovery.sequence_quality.measures', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    artifact_workflow.run(spec, output)
            result = json.loads((output/'workflow.json').read_text())
            self.assertEqual(result['status'], 'interrupted')
            self.assertEqual(result['stages'][1]['status'], 'interrupted')
            self.assertEqual(result['error'], 'KeyboardInterrupt')
            self.assertFalse((output/'.workflow.lock').exists())
            artifact_workflow.run(spec, output)

    def test_missing_input_reports_stage_before_dispatch(self):
        with scratch_directory() as folder:
            root = Path(folder); spec = self.fixture(root)
            (root/'input.fa').unlink()
            with patch.object(artifact_workflow, 'dispatch') as dispatch:
                with self.assertRaises(FileNotFoundError):
                    artifact_workflow.run(spec, root/'out')
                dispatch.assert_not_called()
            result = json.loads((root/'out/workflow.json').read_text())
            self.assertEqual(result['stages'][0]['error_type'], 'FileNotFoundError')
            self.assertEqual(result['stages'][1]['status'], 'pending')

    def test_identity_rejection_preserves_existing_reports(self):
        with scratch_directory() as folder:
            root = Path(folder); spec = self.fixture(root); output = root/'out'
            artifact_workflow.run(spec, output)
            saved = {n: (output/n).read_bytes() for n in ('report.html', 'workflow.json')}
            spec.write_text(spec.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'changed'):
                artifact_workflow.run(spec, output)
            self.assertEqual(saved, {n: (output/n).read_bytes() for n in saved})


class PortableNamesTests(unittest.TestCase):
    def test_reserved_devices_and_trailing_dots_are_rejected(self):
        for name in ['CON', 'aux.fa', 'NUL.json', 'com1.csv', 'LPT9', 'foo.', '..', '../foo', 'a:b', None]:
            with self.subTest(name=name):
                self.assertFalse(portable_name(name))
        for name in ['inventory', 'fixture.fa', 'com10', 'sample-1']:
            self.assertTrue(portable_name(name))

    def test_stage_case_collisions_and_devices_fail_before_output_creation(self):
        with scratch_directory() as folder:
            root = Path(folder)
            for names in [('Inventory', 'inventory'), ('con',), ('LPT1',)]:
                spec = {'schema': 'artifact-workflow-v1', 'stages': [
                    {'id': name, 'kind': 'inventory', 'inputs': {'fasta': 'missing.fa'}} for name in names]}
                (root/'spec.json').write_text(json.dumps(spec))
                with self.subTest(names=names), self.assertRaisesRegex(ValueError, 'portable stage ID'):
                    artifact_workflow.run(root/'spec.json', root/'out')
                self.assertFalse((root/'out').exists())

    def test_snapshot_collisions_cannot_overwrite_reserved_reports(self):
        with scratch_directory() as folder:
            root = Path(folder); (root/'fixture.fa').write_bytes(b'>f\nACGT\n')
            row = {'path': 'fixture.fa', 'bytes': 8, 'sha256': checksum(root/'fixture.fa'),
                   'source': 'artificial', 'version': '1', 'role': 'technical'}
            for names in [('References.csv',), ('Summary.json',), ('CON.fa',), ('Data.fa', 'data.fa')]:
                (root/'spec.json').write_text(json.dumps({'files': [{**row, 'name': n} for n in names]}))
                with self.subTest(names=names), self.assertRaisesRegex(ValueError, 'Unsafe'):
                    reference_snapshot.snapshot(root/'spec.json', root/'out')
                self.assertFalse((root/'out').exists())


class DependencyInventoryTests(unittest.TestCase):
    def test_sra_toolkit_version_and_missing_state_are_reported(self):
        with scratch_directory() as folder:
            root = Path(folder); tool = root/'fixture-tool'; tool.write_bytes(b'fixture')
            with patch.object(dependency_review.shutil, 'which', side_effect=lambda name: str(tool) if name == 'fasterq-dump' else None), \
                 patch.object(dependency_review.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'fixture version', '')) as run:
                row = next(r for r in dependency_review.inspect_tools(root) if r['tool'] == 'fasterq-dump')
                self.assertEqual(row['status'], 'version_check_passed')
                self.assertEqual(row['sha256'], checksum(tool))
                self.assertIn([str(tool), '--version'], [call.args[0] for call in run.call_args_list])
            with patch.object(dependency_review.shutil, 'which', return_value=None):
                row = next(r for r in dependency_review.inspect_tools(root) if r['tool'] == 'fasterq-dump')
                self.assertEqual(row['status'], 'not_found')


class ResourceLimitsTests(unittest.TestCase):
    def test_subprocess_runs_in_owned_directory_with_spaces(self):
        with scratch_directory() as folder:
            root = Path(folder)/'stage with spaces'; root.mkdir()
            bounded_process.run([sys.executable, '-c', "from pathlib import Path; Path('child.txt').write_text('fixture')"], root, 'tool.log')
            self.assertEqual((root/'child.txt').read_text(), 'fixture')

    def test_invalid_limits_never_launch_subprocess(self):
        with scratch_directory() as folder:
            root = Path(folder)
            for kwargs in [{'timeout': 0}, {'timeout': float('nan')}, {'timeout': float('inf')},
                           {'max_bytes': -1}, {'max_bytes': True}]:
                with self.subTest(kwargs=kwargs), patch.object(bounded_process.subprocess, 'Popen') as start:
                    with self.assertRaises(ValueError):
                        bounded_process.run(['unused'], root, 'tool.log', **kwargs)
                    start.assert_not_called()
            self.assertFalse((root/'tool.log').exists())

    def test_timeout_terminates_child_and_retains_log(self):
        with scratch_directory() as folder:
            root = Path(folder)
            with patch.object(bounded_process.subprocess, 'Popen', wraps=subprocess.Popen) as start:
                with self.assertRaisesRegex(TimeoutError, 'time budget'):
                    bounded_process.run([sys.executable, '-c', 'import time; time.sleep(60)'], root, 'timeout.log', timeout=.1)
                self.assertEqual(start.call_count, 1)
            self.assertTrue((root/'timeout.log').is_file())

    def test_existing_overbudget_stage_is_preserved_without_start(self):
        with scratch_directory() as folder:
            root = Path(folder); (root/'tool.log').write_bytes(b'previous log')
            with patch.object(bounded_process.subprocess, 'Popen') as start:
                with self.assertRaisesRegex(ValueError, 'Existing stage'):
                    bounded_process.run(['unused'], root, 'tool.log', max_bytes=1)
                start.assert_not_called()
            self.assertEqual((root/'tool.log').read_bytes(), b'previous log')

    def test_fast_decoder_cannot_bypass_final_log_limit(self):
        with scratch_directory() as folder:
            root = Path(folder); (root/'fixture.bam').write_bytes(b'fixture')
            def start(command, **kwargs):
                kwargs['stderr'].write(b'x'*2_000_001)
                kwargs['stderr'].flush()
                from unittest.mock import Mock
                process = Mock(returncode=0)
                process.poll.return_value = 0
                return process
            with patch.object(alignment_adapter.subprocess, 'Popen', side_effect=start):
                with self.assertRaisesRegex(ValueError, 'log exceeds'):
                    alignment_adapter.decode(root/'fixture.bam', root/'decoded.sam', {'name': 'samtools', 'path': 'fixture'})


class SnapshotProvenanceTests(unittest.TestCase):
    def fixture(self, root):
        path = root/'fixture.fa'; path.write_bytes(b'>f\nACGT\n')
        return {'name': 'reference.fa', 'path': 'fixture.fa', 'bytes': path.stat().st_size,
                'sha256': checksum(path), 'source': 'artificial', 'version': '1', 'role': 'technical'}

    def test_supplied_accession_version_and_retrieval_time_survive_reuse(self):
        with scratch_directory() as folder:
            root = Path(folder); row = self.fixture(root)
            row.update(accession='ARTIFICIAL.1', database_version='fixture-release-1')
            (root/'spec.json').write_text(json.dumps({'files': [row]}))
            reference_snapshot.snapshot(root/'spec.json', root/'out')
            before = (root/'out/references.csv').read_bytes()
            rows = review_stage.table(root/'out/references.csv', ['retrieved_utc', 'accession', 'database_version'])
            self.assertEqual(rows[0]['accession'], 'ARTIFICIAL.1')
            self.assertEqual(rows[0]['database_version'], 'fixture-release-1')
            from datetime import datetime
            self.assertIsNotNone(datetime.fromisoformat(rows[0]['retrieved_utc']).tzinfo)
            reference_snapshot.snapshot(root/'spec.json', root/'out')
            self.assertEqual(before, (root/'out/references.csv').read_bytes())

    def test_local_size_mismatch_rejected_before_copy_or_output_creation(self):
        with scratch_directory() as folder:
            root = Path(folder); row = self.fixture(root); row['bytes'] = 1
            (root/'spec.json').write_text(json.dumps({'files': [row]}))
            with patch.object(reference_snapshot.shutil, 'copyfile') as copy:
                with self.assertRaisesRegex(ValueError, 'size or checksum'):
                    reference_snapshot.snapshot(root/'spec.json', root/'out')
                copy.assert_not_called()
            self.assertFalse((root/'out').exists())

    def test_missing_optional_metadata_remains_unknown(self):
        with scratch_directory() as folder:
            root = Path(folder); row = self.fixture(root)
            (root/'spec.json').write_text(json.dumps({'files': [row]}))
            reference_snapshot.snapshot(root/'spec.json', root/'out')
            result = review_stage.table(root/'out/references.csv', ['accession', 'database_version'])[0]
            self.assertEqual((result['accession'], result['database_version']), ('unknown', 'unknown'))


class ReviewArtifactTests(unittest.TestCase):
    def test_case_colliding_producer_outputs_do_not_complete(self):
        with scratch_directory() as folder:
            root = Path(folder); source = root/'input'; source.write_text('fixture')
            with self.assertRaisesRegex(ValueError, 'Invalid producer output'):
                review_stage.execute('fixture', {'input': source}, root/'out', __file__, lambda p, d: ['Data.csv', 'data.csv'])
            self.assertEqual(json.loads((root/'out/manifest.json').read_text())['status'], 'failed')
