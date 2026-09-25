"""Contract tests for registered arbitrary-input assembly adapters."""
import gzip
import json
import os
from pathlib import Path
import random
import shutil
import sys
import unittest
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery import artifact_workflow
from satellite_discovery.assembly_adapters import (
    AssemblyWorkflowAdapter,
    SpadesAssemblyAdapter,
    TadpoleAssemblyAdapter,
)
from satellite_discovery.external_tool import DependencyMissingError, ExternalToolAdapter
from satellite_discovery.sequence_downloader import checksum


def write_fastq(path, rows):
    opener = gzip.open if str(path).lower().endswith('.gz') else open
    with opener(path, 'wt', encoding='ascii', newline='') as target:
        for name, sequence in rows:
            target.write(f'@{name}\n{sequence}\n+\n' + 'I' * len(sequence) + '\n')


def fixture_reads(root, paired=False, compressed=False):
    suffix = '.fastq.gz' if compressed else '.fastq'
    first = root / ('custom_R1' + suffix)
    second = root / ('custom_R2' + suffix)
    sequence = 'ACGTTGCA' * 15
    if paired:
        write_fastq(first, [(f'pair-{index}/1', sequence) for index in range(2)])
        write_fastq(second, [(f'pair-{index}/2', sequence[::-1]) for index in range(2)])
        return {'read1': first, 'read2': second}
    write_fastq(first, [('single-0', sequence), ('single-1', sequence[::-1])])
    return {'read1': first}


_FAKE_RUNNER = (
    'import pathlib,sys,time\n'
    'behavior=sys.argv[1]\n'
    'out=pathlib.Path(sys.argv[2])\n'
    'if behavior=="timeout": time.sleep(30)\n'
    'if behavior=="fail": raise SystemExit(7)\n'
    'out.parent.mkdir(parents=True,exist_ok=True)\n'
    'if behavior=="missing": raise SystemExit(0)\n'
    'if behavior=="empty": out.write_text("")\n'
    'elif behavior=="malformed": out.write_text("not-fasta"+chr(10))\n'
    'elif behavior=="budget": out.write_text(">contig"+chr(10)+"A"*30000+chr(10))\n'
    'elif behavior=="tadpole-header": out.write_text(">contig_0,len=120,cov=52.2"+chr(10)+"ACGT"*30+chr(10))\n'
    'else: out.write_text(">fixture_contig"+chr(10)+"ACGT"*30+chr(10))\n'
)


class FixtureSpadesAdapter(SpadesAssemblyAdapter):
    """Cross-platform test tool invoked through the current Python executable."""
    def __init__(self, behavior='success', *, timeout=180, max_bytes=400_000_000):
        self.behavior = behavior
        super().__init__(timeout=timeout, max_bytes=max_bytes)
        self.dependencies = ({
            'name': 'python',
            'command': sys.executable,
            'version_args': ['--version'],
        },)

    def inspect_dependency(self, config=None):
        dependency = ExternalToolAdapter.inspect_dependency(self, config)
        dependency['assembler'] = 'spades'
        return dependency

    def _tool_version(self, dependency):
        return 'SPAdes fixture 4.1.0'

    def build_command(self, executables, inputs, output, config):
        return [
            executables['python'], '-c', _FAKE_RUNNER, self.behavior,
            str(output / self.raw_contigs),
        ]


class FixtureTadpoleAdapter(TadpoleAssemblyAdapter):
    """Cross-platform test tool invoked through the current Python executable."""
    def __init__(self, behavior='success'):
        self.behavior = behavior
        super().__init__()
        self.dependencies = ({
            'name': 'python',
            'command': sys.executable,
            'version_args': ['--version'],
        },)

    def inspect_dependency(self, config=None):
        dependency = ExternalToolAdapter.inspect_dependency(self, config)
        dependency.update(
            assembler='tadpole',
            runtime={
                'status': 'available',
                'version': 'BBTools 40.01',
                'commit': 'fixture-runtime',
                'archive_sha256': 'fixture',
                'installation_sha256': 'fixture',
                'verified_runtime_files': 1,
                'classpath': str(self.classpath),
            },
        )
        return dependency

    def build_command(self, executables, inputs, output, config):
        return [
            executables['python'], '-c', _FAKE_RUNNER, self.behavior,
            str(output / self.raw_contigs),
        ]


class MissingFixtureSpadesAdapter(FixtureSpadesAdapter):
    def inspect_dependency(self, config=None):
        return {
            'status': 'dependency_missing',
            'assembler': 'spades',
            'dependencies': [{'tool': 'spades', 'path': '', 'status': 'not_found'}],
        }


class FinalizationBudgetFixtureAdapter(FixtureSpadesAdapter):
    def finalize_outputs(self, output, config, process_result, manifest):
        super().finalize_outputs(output, config, process_result, manifest)
        with (Path(output) / self.stderr_name).open('ab') as target:
            target.write(b'x' * 12000)


class LinkedOutputFixtureAdapter(FixtureSpadesAdapter):
    def finalize_outputs(self, output, config, process_result, manifest):
        super().finalize_outputs(output, config, process_result, manifest)
        (Path(output) / 'raw' / 'linked.txt').symlink_to(Path(__file__).resolve())


class AssemblyInputTests(unittest.TestCase):
    def test_single_and_paired_fastq_inputs_are_stream_validated(self):
        with scratch_directory() as folder:
            root = Path(folder)
            adapter = SpadesAssemblyAdapter()
            single = fixture_reads(root, compressed=True)
            self.assertEqual(set(adapter.validate_inputs(single, root / 'out', {
                'assembler': 'spades', 'layout': 'single-end', 'threads': 2, 'memory_mb': 2048,
            })), {'read1'})
            paired = fixture_reads(root, paired=True)
            self.assertEqual(set(adapter.validate_inputs(paired, root / 'paired-out', {
                'assembler': 'spades', 'layout': 'paired-end', 'threads': 2, 'memory_mb': 2048,
            })), {'read1', 'read2'})

    def test_missing_empty_malformed_and_unsupported_inputs_fail_before_execution(self):
        with scratch_directory() as folder:
            root = Path(folder)
            adapter = SpadesAssemblyAdapter()
            config = {'assembler': 'spades', 'layout': 'single-end'}
            with self.assertRaises((OSError, ValueError)):
                adapter.validate_inputs({'read1': root / 'missing.fastq'}, root / 'out', config)
            empty = root / 'empty.fastq'
            empty.touch()
            with self.assertRaisesRegex(ValueError, 'empty'):
                adapter.validate_inputs({'read1': empty}, root / 'out', config)
            malformed = root / 'broken.fastq'
            malformed.write_text('@r' + chr(10) + 'ACGT' + chr(10) + '+' + chr(10) + 'I' + chr(10) + 'extra' + chr(10), encoding='ascii')
            with self.assertRaises(ValueError):
                adapter.validate_inputs({'read1': malformed}, root / 'out', config)
            unsupported = root / 'reads.txt'
            write_fastq(unsupported, [('r', 'ACGT')])
            with self.assertRaisesRegex(ValueError, 'extension'):
                adapter.validate_inputs({'read1': unsupported}, root / 'out', config)

    def test_declared_paired_layout_requires_distinct_matching_mates(self):
        with scratch_directory() as folder:
            root = Path(folder)
            adapter = SpadesAssemblyAdapter()
            config = {'assembler': 'spades', 'layout': 'paired-end'}
            first = root / 'r1.fastq'
            second = root / 'r2.fastq'
            write_fastq(first, [('read/1', 'ACGT')])
            write_fastq(second, [('read/2', 'TGCA'), ('extra/2', 'TGCA')])
            with self.assertRaisesRegex(ValueError, 'different record counts'):
                adapter.validate_inputs({'read1': first, 'read2': second}, root / 'out', config)
            write_fastq(second, [('other/2', 'TGCA')])
            with self.assertRaisesRegex(ValueError, 'identifiers'):
                adapter.validate_inputs({'read1': first, 'read2': second}, root / 'out', config)
            with self.assertRaisesRegex(ValueError, 'distinct'):
                adapter.validate_inputs({'read1': first, 'read2': first}, root / 'out', config)
            with self.assertRaisesRegex(ValueError, 'layout'):
                adapter.validate_inputs({'read1': first}, root / 'out', config)


class AssemblyExecutionTests(unittest.TestCase):
    def test_registered_spades_single_and_paired_execution_records_complete_manifest(self):
        with scratch_directory() as folder:
            root = Path(folder)
            router = AssemblyWorkflowAdapter(adapters=(FixtureSpadesAdapter(), FixtureTadpoleAdapter()))
            for paired in (False, True):
                case = root / f'case-{paired}'
                case.mkdir()
                inputs = fixture_reads(case, paired=paired, compressed=True)
                output = case / 'assembly'
                config = {
                    'assembler': 'spades',
                    'layout': 'paired-end' if paired else 'single-end',
                    'threads': 2,
                    'memory_mb': 2048,
                }
                result = router.execute(inputs, output, config, context={'stage_id': 'assembly'})
                record = json.loads((output / 'assembly_manifest.json').read_text(encoding='utf-8'))
                self.assertEqual(result.execution, 'executed')
                self.assertEqual(record['stage_id'], 'assembly')
                self.assertEqual(record['assembler'], 'spades')
                self.assertEqual(record['input_layout'], config['layout'])
                self.assertEqual(record['contig_count'], 1)
                self.assertEqual(record['contig_sha256'], checksum(output / 'contigs.fasta'))
                self.assertEqual(record['workflow_status'], 'complete')
                self.assertTrue((output / 'raw' / 'contigs.fasta').is_file())
                self.assertTrue((output / 'stdout.log').is_file())
                self.assertTrue((output / 'stderr.log').is_file())
                self.assertTrue(record['output_inventory'])

    def test_tadpole_registered_adapter_command_and_output_wrapper(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = fixture_reads(root, paired=True)
            output = root / 'assembly'
            adapter = FixtureTadpoleAdapter('tadpole-header')
            result = adapter.execute(inputs, output, {
                'assembler': 'tadpole', 'layout': 'paired-end', 'threads': 2, 'memory_mb': 512,
            })
            record = json.loads((output / 'assembly_manifest.json').read_text(encoding='utf-8'))
            raw_header = (output / 'raw' / 'contigs.fasta').read_text(encoding='ascii').splitlines()[0]
            canonical_header = (output / 'contigs.fasta').read_text(encoding='ascii').splitlines()[0]
            self.assertEqual(result.execution, 'executed')
            self.assertEqual(record['assembler'], 'tadpole')
            self.assertIn('BBTools 40.01', record['external_tool_version'])
            self.assertEqual(record['input_layout'], 'paired-end')
            self.assertEqual(record['contig_count'], 1)
            self.assertIn(',', raw_header)
            self.assertEqual(canonical_header, '>contig_0')
            self.assertEqual(record['contig_header_map'][0]['canonical_id'], 'contig_0')

    def test_unknown_assembler_arbitrary_command_and_layout_mismatch_rejected(self):
        router = AssemblyWorkflowAdapter()
        for config in (
            {'assembler': 'made-up', 'layout': 'single-end'},
            {'assembler': 'spades', 'layout': 'single-end', 'command': 'echo unsafe'},
            {'assembler': 'spades', 'layout': 'neither'},
        ):
            with self.assertRaises(ValueError):
                router.validate_config(config)

    def test_dependency_missing_is_reported_as_workflow_state(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = fixture_reads(root)
            adapter = FixtureSpadesAdapter()
            missing = {'status': 'dependency_missing', 'assembler': 'spades', 'dependencies': [
                {'tool': 'spades', 'path': '', 'status': 'not_found'},
            ]}
            with patch.object(adapter, 'inspect_dependency', return_value=missing):
                with self.assertRaises(DependencyMissingError):
                    adapter.execute(inputs, root / 'out', {
                        'assembler': 'spades', 'layout': 'single-end',
                    })

    def test_interruption_is_recorded_and_manifest_is_not_complete(self):
        with scratch_directory() as folder:
            root = Path(folder)
            adapter = FixtureSpadesAdapter()
            with patch('satellite_discovery.external_tool.bounded_process.run_captured',
                       side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    adapter.execute(fixture_reads(root), root / 'out', {
                        'assembler': 'spades', 'layout': 'single-end',
                    })
            manifest = json.loads((root / 'out' / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['status'], 'interrupted')

    def test_nonzero_exit_timeout_and_bad_or_empty_contigs_are_not_complete(self):
        cases = (
            ('fail', FixtureSpadesAdapter('fail'), 180, 400_000_000, 'exit status 7'),
            ('timeout', FixtureSpadesAdapter('timeout', timeout=0.2), 0.2, 400_000_000, 'time budget'),
            ('missing', FixtureSpadesAdapter('missing'), 180, 400_000_000, 'contig FASTA'),
            ('malformed', FixtureSpadesAdapter('malformed'), 180, 400_000_000, 'FASTA'),
            ('empty', FixtureSpadesAdapter('empty'), 180, 400_000_000, 'FASTA'),
        )
        for behavior, adapter, _, _, expected in cases:
            with self.subTest(behavior=behavior), scratch_directory() as folder:
                root = Path(folder)
                inputs = fixture_reads(root)
                with self.assertRaisesRegex((RuntimeError, ValueError, OSError), expected):
                    adapter.execute(inputs, root / 'out', {
                        'assembler': 'spades', 'layout': 'single-end',
                    })
                marker = root / 'out' / 'manifest.json'
                self.assertTrue(marker.is_file())
                self.assertNotEqual(json.loads(marker.read_text())['status'], 'complete')

    def test_output_budget_and_verified_reuse_invalidation_and_corruption(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = fixture_reads(root)
            config = {'assembler': 'spades', 'layout': 'single-end'}
            output = root / 'stage'
            adapter = FixtureSpadesAdapter()
            first = adapter.execute(inputs, output, config)
            reused = adapter.execute(inputs, output, config)
            self.assertEqual(first.execution, 'executed')
            self.assertEqual(reused.execution, 'verified_reuse')
            changed = root / 'changed.fastq'
            write_fastq(changed, [('new', 'ACGTACGT')])
            with self.assertRaisesRegex(ValueError, 'changed'):
                adapter.execute({'read1': changed}, output, config)
            with self.assertRaisesRegex(ValueError, 'changed'):
                adapter.execute(inputs, output, {**config, 'threads': 3})
            router = AssemblyWorkflowAdapter(adapters=(adapter, FixtureTadpoleAdapter()))
            with self.assertRaises(ValueError):
                router.execute(inputs, output, {
                    'assembler': 'tadpole', 'layout': 'single-end', 'threads': 2, 'memory_mb': 512,
                })

            contigs = output / 'contigs.fasta'
            contigs.write_text('>tampered\\nACGT\\n', encoding='ascii')
            with self.assertRaises(ValueError):
                adapter.execute(inputs, output, config)

            budget = FixtureSpadesAdapter('budget', max_bytes=10000)
            with self.assertRaisesRegex(ValueError, 'budget'):
                budget.execute(inputs, root / 'budget-stage', config)
            finalization_budget = FinalizationBudgetFixtureAdapter(max_bytes=15000)
            with self.assertRaisesRegex(ValueError, 'budget exceeded after output finalization'):
                finalization_budget.execute(inputs, root / 'finalization-budget-stage', config)
            failed_assembly = json.loads(
                (root / 'finalization-budget-stage' / 'assembly_manifest.json').read_text(encoding='utf-8')
            )
            self.assertEqual(failed_assembly['workflow_status'], 'failed')
            self.assertTrue(failed_assembly['errors'])

    def test_final_completion_manifest_cannot_exceed_output_budget(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = fixture_reads(root)
            config = {'assembler': 'spades', 'layout': 'single-end'}
            probe = FixtureSpadesAdapter()
            probe_output = root / 'probe'
            probe.execute(inputs, probe_output, config)
            completed_size = probe._output_bytes(probe_output)

            limited = FixtureSpadesAdapter(max_bytes=completed_size - 1)
            limited_output = root / 'limit'
            with self.assertRaisesRegex(ValueError, 'after completion manifest'):
                limited.execute(inputs, limited_output, config)
            external_manifest = json.loads(
                (limited_output / 'manifest.json').read_text(encoding='utf-8')
            )
            assembly_manifest = json.loads(
                (limited_output / 'assembly_manifest.json').read_text(encoding='utf-8')
            )
            self.assertEqual(external_manifest['status'], 'failed')
            self.assertEqual(assembly_manifest['workflow_status'], 'failed')

    def test_linked_tool_output_is_rejected_and_failure_is_recorded(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = fixture_reads(root)
            probe = root / 'link-probe'
            try:
                probe.symlink_to(inputs['read1'])
                probe.unlink()
            except (OSError, NotImplementedError):
                self.skipTest('Symbolic links are unavailable in this environment')

            output = root / 'linked-output'
            adapter = LinkedOutputFixtureAdapter()
            with self.assertRaisesRegex(ValueError, 'link'):
                adapter.execute(inputs, output, {
                    'assembler': 'spades', 'layout': 'single-end',
                })
            external_manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
            assembly_manifest = json.loads(
                (output / 'assembly_manifest.json').read_text(encoding='utf-8')
            )
            self.assertEqual(external_manifest['status'], 'failed')
            self.assertIn('link', external_manifest['output_inventory_error'])
            self.assertEqual(assembly_manifest['workflow_status'], 'failed')

    def test_corrupted_assembly_manifest_and_missing_raw_output_invalidate_reuse(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = fixture_reads(root)
            config = {'assembler': 'spades', 'layout': 'single-end'}
            first = root / 'first'
            adapter = FixtureSpadesAdapter()
            adapter.execute(inputs, first, config)
            record_path = first / 'assembly_manifest.json'
            record_path.write_text(record_path.read_text() + ' ', encoding='utf-8')
            with self.assertRaises(ValueError):
                adapter.execute(inputs, first, config)

            second = root / 'second'
            adapter.execute(inputs, second, config)
            (second / 'raw' / 'contigs.fasta').unlink()
            with self.assertRaises(ValueError):
                adapter.execute(inputs, second, config)

    def test_workflow_handoff_to_existing_fasta_catalogue_and_resume(self):
        with scratch_directory() as folder:
            root = Path(folder)
            reads = fixture_reads(root, compressed=True)
            specification = root / 'workflow.json'
            specification.write_text(json.dumps({
                'schema': 'artifact-workflow-v1',
                'stages': [
                    {
                        'id': 'assemble',
                        'kind': 'assembly',
                        'inputs': {'read1': reads['read1'].name},
                        'config': {'assembler': 'spades', 'layout': 'single-end'},
                    },
                    {
                        'id': 'catalogue',
                        'kind': 'inventory',
                        'inputs': {'fasta': {'stage': 'assemble', 'artifact': 'contigs.fasta'}},
                    },
                ],
            }), encoding='utf-8')
            output = root / 'workflow-output'
            router = AssemblyWorkflowAdapter(adapters=(FixtureSpadesAdapter(), FixtureTadpoleAdapter()))
            with patch('satellite_discovery.artifact_workflow.AssemblyWorkflowAdapter', return_value=router):
                registry = artifact_workflow.build_default_registry()
            artifact_workflow.run(specification, output, registry)
            first = json.loads((output / 'workflow.json').read_text(encoding='utf-8'))
            self.assertEqual(first['status'], 'complete')
            self.assertEqual(first['stages'][0]['assembly']['contig_count'], 1)
            self.assertEqual(first['stages'][0]['assembly']['contig_path'], 'contigs.fasta')
            self.assertTrue((output / 'catalogue' / 'catalogue.sqlite').is_file())
            artifact_workflow.run(specification, output, registry)
            second = json.loads((output / 'workflow.json').read_text(encoding='utf-8'))
            self.assertEqual(second['stages'][0]['assembly']['reuse_status'], 'verified_reuse')
            report = (output / 'report.html').read_text(encoding='utf-8')
            self.assertIn('Assembler: spades', report)
            self.assertIn('Contig count: 1', report)

    def test_workflow_reports_selected_missing_assembler_without_contig_count(self):
        with scratch_directory() as folder:
            root = Path(folder)
            reads = fixture_reads(root)
            specification = root / 'workflow.json'
            specification.write_text(json.dumps({
                'schema': 'artifact-workflow-v1',
                'stages': [{
                    'id': 'assemble',
                    'kind': 'assembly',
                    'inputs': {'read1': reads['read1'].name},
                    'config': {'assembler': 'spades', 'layout': 'single-end'},
                }],
            }), encoding='utf-8')
            router = AssemblyWorkflowAdapter(
                adapters=(MissingFixtureSpadesAdapter(), FixtureTadpoleAdapter()),
            )
            with patch('satellite_discovery.artifact_workflow.AssemblyWorkflowAdapter', return_value=router):
                registry = artifact_workflow.build_default_registry()
            output = root / 'workflow-output'
            artifact_workflow.run(specification, output, registry)
            result = json.loads((output / 'workflow.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'dependency_missing')
            self.assertEqual(result['stages'][0]['status'], 'dependency_missing')
            report = (output / 'report.html').read_text(encoding='utf-8')
            self.assertIn('DEPENDENCY MISSING', report)
            self.assertNotIn('Contig count: 0', report)


@unittest.skipUnless(os.environ.get('RUN_OPTIONAL_TOOL_TESTS') == '1', 'Optional live-tool job')
class RealAssemblyRuntimeTests(unittest.TestCase):
    def test_real_spades_single_and_paired_compressed_fastq(self):
        if not (shutil.which('spades.py') or shutil.which('spades')):
            self.skipTest('SPAdes is not installed')
        self._run_real('spades', paired=False)
        self._run_real('spades', paired=True)

    def test_real_tadpole_single_and_paired_fastq(self):
        if not shutil.which('java'):
            self.skipTest('Java is not installed')
        self._run_real('tadpole', paired=False)
        self._run_real('tadpole', paired=True)

    def _run_real(self, assembler, paired):
        with scratch_directory() as folder:
            root = Path(folder)
            rng = random.Random(17292026)
            truth = ''.join(rng.choice('ACGT') for _ in range(1000))
            first, second = [], []
            for repeat in range(4):
                for start in range(0, 901 if not paired else 801, 5):
                    first.append((f'fixture_{repeat}_{start}/1' if paired else f'fixture_{repeat}_{start}',
                                  truth[start:start + 100]))
                    if paired:
                        mate = truth[start + 100:start + 200].translate(str.maketrans('ACGT', 'TGCA'))[::-1]
                        second.append((f'fixture_{repeat}_{start}/2', mate))
            r1 = root / 'reads_R1.fastq.gz'
            write_fastq(r1, first)
            inputs = {'read1': r1}
            if paired:
                r2 = root / 'reads_R2.fastq.gz'
                write_fastq(r2, second)
                inputs['read2'] = r2
            config = {
                'assembler': assembler,
                'layout': 'paired-end' if paired else 'single-end',
                'threads': 2,
                'memory_mb': 2048 if assembler == 'spades' else 512,
            }
            result = AssemblyWorkflowAdapter().execute(inputs, root / 'assembly', config)
            record = json.loads((root / 'assembly' / 'assembly_manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(result.execution, 'executed')
            self.assertIn('version_check_passed', json.dumps(record['executable_identity']))
            self.assertGreater(record['contig_count'], 0)
            self.assertTrue(record['contig_sha256'])
            if assembler == 'tadpole':
                self.assertIn(',', (root / 'assembly' / 'raw' / 'contigs.fasta')
                              .read_text(encoding='ascii').splitlines()[0])
                self.assertTrue(record['contig_header_map'])


if __name__ == '__main__':
    unittest.main()