"""Synthetic end-to-end workflow handoffs and DVG evaluation states."""
import json
import os
from pathlib import Path
import unittest

from test_metadata import scratch_directory
from test_virema_adapter import FixtureViReMaAdapter

from satellite_discovery.artifact_workflow import build_default_registry, run
from satellite_discovery import dvg_evidence


def _fixture(root):
    (root / 'reads.fastq').write_text('@synthetic\nACGT\n+\nIIII\n', encoding='ascii')
    (root / 'reference.fasta').write_text('>REF\nACGTACGT\n', encoding='ascii')


def _registry(behavior):
    registry = build_default_registry()
    caller = FixtureViReMaAdapter(behavior=behavior)
    caller.kind = 'fixture_dvg_virema'
    caller.module_name = 'dvg.fixture'
    registry.register_external_adapter(caller)
    return registry, caller


def _spec(root, *, skip=False, include_report=True):
    stages = [
        {
            'id': 'reads', 'kind': 'fastq_validate',
            'inputs': {'read1': 'reads.fastq'}, 'config': {'layout': 'single-end'},
        },
        {
            'id': 'catalogue', 'kind': 'inventory',
            'inputs': {'fasta': 'reference.fasta'},
        },
        {
            'id': 'dvg', 'kind': 'fixture_dvg_virema',
            'inputs': {
                'reads': {'stage': 'reads', 'artifact': 'read1.fastq.gz'},
                'reference': {'stage': 'catalogue', 'artifact': 'sequences.fasta'},
                'catalogue_records': {'stage': 'catalogue', 'artifact': 'records.csv'},
            },
            'config': {'sample_id': 'artificial_sample'},
            **({'skip': True} if skip else {}),
        },
    ]
    if include_report:
        stages.append({
            'id': 'consolidated', 'kind': 'workflow_report',
            'inputs': {
                'evidence_summary': {'stage': 'dvg', 'artifact': 'summary.json'},
                'evidence': {'stage': 'dvg', 'artifact': 'evidence.json'},
            },
            'config': {'title': 'Artificial DVG evidence'},
        })
    manifest = root / 'workflow-spec.json'
    manifest.write_text(json.dumps({'schema': 'artifact-workflow-v1', 'stages': stages}),
                        encoding='utf-8')
    return manifest


def _result(output):
    return json.loads((output / 'workflow.json').read_text(encoding='utf-8'))


class DVGWorkflowTests(unittest.TestCase):
    def test_positive_handoff_reports_raw_link_and_resolved_catalogue_identity(self):
        with scratch_directory() as directory:
            root = Path(directory)
            _fixture(root)
            registry, _caller = _registry('positive')
            output = root / 'workflow'
            run(_spec(root), output, registry=registry)

            result = _result(output)
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(result['stage_order'], [
                'reads', 'catalogue', 'dvg', 'consolidated',
            ])
            self.assertEqual(result['dvg_evaluations']['dvg']['status'],
                             dvg_evidence.DVG_EVIDENCE_DETECTED)
            self.assertEqual(result['dvg_evaluations']['dvg']['event_count'], 1)
            self.assertEqual(result['dvg_evaluations']['dvg']['caller_version'], '0.25')
            evidence = json.loads((output / 'dvg/evidence.json').read_text(encoding='utf-8'))
            event = evidence['events'][0]
            self.assertEqual(result['dvg_evaluations']['dvg']['event_references'],
                             [event['evidence_id']])
            self.assertEqual(event['catalogue_linkage']['status'], 'resolved')
            self.assertEqual(event['catalogue_linkage']['record_id'], 'REF')
            self.assertEqual(event['raw_output_reference']['path'],
                             'raw/Virus_Recombination_Results.txt')
            self.assertEqual(event['raw_output_reference']['line'], 2)
            self.assertEqual(
                result['stage_graph'][-1]['artifact_type'], 'dvg_evidence')
            consolidated = json.loads(
                (output / 'consolidated/report.json').read_text(encoding='utf-8'))
            self.assertEqual(consolidated['artifacts']['evidence_summary']['summary']['status'],
                             dvg_evidence.DVG_EVIDENCE_DETECTED)
            root_report = (output / 'report.html').read_text(encoding='utf-8')
            self.assertIn('ViReMa detected 1 junction events', root_report)
            self.assertIn('Caller version: 0.25', root_report)
            self.assertIn('href="dvg/raw/Virus_Recombination_Results.txt"', root_report)
            self.assertIn(event['evidence_id'], root_report)
            self.assertIn(event['evidence_id'],
                          (output / 'dvg/report.html').read_text(encoding='utf-8'))
            self.assertIn('Evidence references',
                          (output / 'consolidated/report.html').read_text(encoding='utf-8'))

    def test_zero_events_are_not_a_non_dvg_classification(self):
        with scratch_directory() as directory:
            root = Path(directory)
            _fixture(root)
            registry, _caller = _registry('negative')
            output = root / 'workflow'
            run(_spec(root), output, registry=registry)
            result = _result(output)
            self.assertEqual(result['dvg_evaluations']['dvg']['status'],
                             dvg_evidence.NO_DVG_EVIDENCE_DETECTED)
            self.assertEqual(result['dvg_evaluations']['dvg']['event_count'], 0)
            self.assertEqual(json.loads((output / 'dvg/evidence.json').read_text())['events'], [])
            for report in (output / 'report.html', output / 'dvg/report.html',
                           output / 'consolidated/report.html'):
                text = report.read_text(encoding='utf-8')
                self.assertNotIn('CONFIRMED_NON_DVG', text)
                self.assertNotIn('This sequence is not a DVG', text)
            self.assertIn('No DVG evidence detected by the configured caller',
                          (output / 'report.html').read_text(encoding='utf-8'))

    def test_missing_dependency_preserves_completed_m4_work(self):
        with scratch_directory() as directory:
            root = Path(directory)
            _fixture(root)
            registry, caller = _registry('positive')
            caller.inspect_dependency = lambda config=None: {
                'status': 'dependency_missing', 'dependencies': [],
            }
            output = root / 'workflow'
            run(_spec(root), output, registry=registry)
            result = _result(output)
            self.assertEqual(result['status'], 'dependency_missing')
            self.assertEqual([row['status'] for row in result['stages']],
                             ['complete', 'complete', 'dependency_missing', 'pending'])
            self.assertEqual(result['dvg_evaluations']['dvg']['status'],
                             dvg_evidence.ANALYSIS_UNAVAILABLE)
            self.assertEqual(result['dvg_evaluations']['dvg']['event_count'], None)
            self.assertFalse((output / 'dvg/evidence.json').exists())
            self.assertIn('analysis was not performed because the dependency was unavailable',
                          (output / 'report.html').read_text(encoding='utf-8'))

    def test_skip_is_not_evaluated_and_malformed_and_exit_failure_are_distinct(self):
        with scratch_directory() as directory:
            root = Path(directory)
            _fixture(root)
            registry, _caller = _registry('positive')
            output = root / 'skipped'
            run(_spec(root, skip=True, include_report=False), output, registry=registry)
            result = _result(output)
            self.assertEqual(result['stages'][-1]['status'], 'skipped')
            self.assertEqual(result['dvg_evaluations']['dvg']['status'],
                             dvg_evidence.NOT_EVALUATED)

        for behavior, expected in (
                ('malformed', dvg_evidence.INVALID_RESULT),
                ('nonzero', dvg_evidence.ANALYSIS_FAILED)):
            with self.subTest(behavior=behavior), scratch_directory() as directory:
                root = Path(directory)
                _fixture(root)
                registry, _caller = _registry(behavior)
                output = root / 'workflow'
                with self.assertRaises((ValueError, RuntimeError)):
                    run(_spec(root), output, registry=registry)
                result = _result(output)
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['dvg_evaluations']['dvg']['status'], expected)
                self.assertFalse((output / 'dvg/evidence.json').exists())

    def test_verified_reuse_and_reference_change_invalidate_evidence(self):
        with scratch_directory() as directory:
            root = Path(directory)
            _fixture(root)
            registry, _caller = _registry('positive')
            spec = _spec(root, include_report=False)
            output = root / 'workflow'
            run(spec, output, registry=registry)
            first = _result(output)['stages'][-1]
            run(spec, output, registry=registry)
            reused = _result(output)['stages'][-1]
            self.assertEqual(reused['execution'], 'verified_reuse')
            self.assertEqual(reused['cache_key'], first['cache_key'])
            (root / 'reference.fasta').write_text('>REF\nACGTACGA\n', encoding='ascii')
            run(spec, output, registry=registry)
            changed = _result(output)['stages'][-1]
            self.assertEqual(changed['execution'], 'executed')
            self.assertNotEqual(changed['cache_key'], first['cache_key'])
            self.assertNotEqual(changed['output_path'], first['output_path'])

    def test_corrupted_saved_summary_is_invalid_not_an_absence_claim(self):
        with scratch_directory() as directory:
            root = Path(directory)
            _fixture(root)
            registry, _caller = _registry('positive')
            spec = _spec(root, include_report=False)
            output = root / 'workflow'
            run(spec, output, registry=registry)
            (output / 'dvg/summary.json').write_text('{incomplete', encoding='utf-8')
            with self.assertRaises(dvg_evidence.InvalidDVGResultError):
                run(spec, output, registry=registry)
            result = _result(output)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['dvg_evaluations']['dvg']['status'],
                             dvg_evidence.INVALID_RESULT)
            self.assertEqual(result['dvg_evaluations']['dvg']['event_count'], None)
            self.assertIn('result is invalid or incomplete',
                          (output / 'report.html').read_text(encoding='utf-8'))

    def test_corrupted_inventoried_diagnostics_are_invalid_not_execution_failures(self):
        with scratch_directory() as directory:
            root = Path(directory)
            _fixture(root)
            registry, _caller = _registry('positive')
            spec = _spec(root, include_report=False)
            output = root / 'workflow'
            run(spec, output, registry=registry)
            # This retained log is inventoried but does not affect the parsed
            # event and its normalized summary.
            with (output / 'dvg/stderr.log').open('a', encoding='utf-8') as log:
                log.write('changed after completion\n')
            with self.assertRaises(dvg_evidence.InvalidDVGResultError):
                run(spec, output, registry=registry)
            result = _result(output)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['dvg_evaluations']['dvg']['status'],
                             dvg_evidence.INVALID_RESULT)
            self.assertEqual(result['dvg_evaluations']['dvg']['event_count'], None)

    def test_replaced_inventoried_log_symlink_is_an_invalid_saved_result(self):
        with scratch_directory() as directory:
            root = Path(directory)
            _fixture(root)
            registry, _caller = _registry('positive')
            spec = _spec(root, include_report=False)
            output = root / 'workflow'
            run(spec, output, registry=registry)
            retained_log = output / 'dvg/stderr.log'
            retained_log.unlink()
            try:
                os.symlink(root / 'reads.fastq', retained_log)
            except (OSError, NotImplementedError):
                self.skipTest('Creating symlinks requires platform privileges')
            with self.assertRaises(dvg_evidence.InvalidDVGResultError):
                run(spec, output, registry=registry)
            result = _result(output)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['dvg_evaluations']['dvg']['status'],
                             dvg_evidence.INVALID_RESULT)


if __name__ == '__main__':
    unittest.main()