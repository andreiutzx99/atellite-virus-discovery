"""Artificial fixtures for the trusted stage registry and CLI adapter contract."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery import artifact_workflow, bounded_process
from satellite_discovery.example_transform_adapter import ExampleTextTransformAdapter
from satellite_discovery.external_tool import ExternalToolAdapter, ExternalToolExitError
from satellite_discovery.sequence_downloader import checksum
from satellite_discovery.stage_registry import WorkflowStageRegistry
from satellite_discovery.workflow_states import (
    STAGE_STATES, STAGE_TRANSITIONS, WORKFLOW_TRANSITIONS, transition,
)


class CommandFixtureAdapter(ExternalToolAdapter):
    def __init__(self, behavior='copy', *, command='python', timeout=20):
        self.behavior = behavior
        super().__init__(
            kind='fixture_external',
            module_name='fixture.external',
            adapter_name='test-fixture-adapter',
            adapter_version='1',
            tool_name='test fixture command',
            dependencies=[{
                'name': 'python',
                'command': sys.executable if command == 'python' else command,
                'version_args': ['--version'],
            }],
            input_fields={'source'},
            optional_input_fields={'annotation'},
            output_files=['result.txt'] if behavior == 'copy' else [],
            timeout=timeout,
            max_bytes=1_000_000,
        )

    def validate_config(self, config):
        if not isinstance(config, dict) or set(config) - {'prefix'}:
            raise ValueError('Only prefix is accepted')
        prefix = config.get('prefix', 'fixture:')
        if not isinstance(prefix, str) or len(prefix) > 128:
            raise ValueError('Invalid prefix')
        return {'prefix': prefix}

    def build_command(self, executables, inputs, output, config):
        python = executables['python']
        if self.behavior == 'fail':
            return [python, '-c', "import sys; print('fixture failure', file=sys.stderr); sys.exit(7)"]
        if self.behavior == 'timeout':
            return [python, '-c', 'import time; time.sleep(60)']
        if self.behavior == 'interrupt':
            return [python, '-c', 'pass']
        return [
            python, '-c',
            "from pathlib import Path; import sys; Path(sys.argv[2]).write_text(sys.argv[3]+Path(sys.argv[1]).read_text())",
            str(inputs['source']), str(output/'result.txt'), config['prefix'],
        ]


class ExternalToolAdapterTests(unittest.TestCase):
    def fixture(self, root):
        source = root/'input.txt'
        source.write_text('artificial text\n', encoding='utf-8')
        return source

    def test_example_adapter_runs_and_records_provenance_and_outputs(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            specification = root/'workflow.json'
            specification.write_text(json.dumps({
                'schema': 'artifact-workflow-v1',
                'stages': [{
                    'id': 'transform',
                    'kind': 'example_text_transform',
                    'inputs': {'source': source.name},
                    'config': {'prefix': 'unit:'},
                }],
            }))
            report = artifact_workflow.run(specification, root/'out')
            output = root/'out'
            workflow = json.loads((output/'workflow.json').read_text())
            stage = workflow['stages'][0]
            manifest_path = output/'transform/manifest.json'
            stage_manifest = json.loads(manifest_path.read_text())
            self.assertEqual(report, output/'report.html')
            self.assertEqual(workflow['status'], 'complete')
            self.assertEqual(stage['status'], 'complete')
            self.assertEqual(stage['execution'], 'executed')
            self.assertEqual((output/'transform/transformed.txt').read_text(), 'unit:artificial text\n')
            self.assertEqual((output/'transform/stdout.log').read_text().strip(), 'fixture text transform complete')
            self.assertEqual(stage_manifest['schema'], 'external-tool-stage-v1')
            self.assertEqual(stage_manifest['status'], 'complete')
            self.assertEqual(stage_manifest['exit_status'], 0)
            self.assertGreaterEqual(stage_manifest['duration_seconds'], 0)
            self.assertEqual(stage_manifest['adapter']['name'], 'fixture-text-transform')
            self.assertTrue(stage_manifest['adapter']['source_sha256'])
            self.assertEqual(stage_manifest['configuration'], {'prefix': 'unit:'})
            self.assertIn('git_revision', stage_manifest['environment'])
            self.assertEqual(stage_manifest['inputs']['source']['sha256'], checksum(source))
            self.assertEqual(stage_manifest['output_sha256']['transformed.txt'],
                             checksum(output/'transform/transformed.txt'))
            self.assertEqual(
                {row['path'] for row in stage_manifest['output_inventory']},
                {'transformed.txt', 'stdout.log', 'stderr.log'},
            )
            self.assertIn('example_text_transform', {row['kind'] for row in workflow['registry']})
            report_html = (output/'report.html').read_text()
            self.assertIn('COMPLETE', report_html)

            saved_manifest = manifest_path.read_bytes()
            artifact_workflow.run(specification, output)
            workflow = json.loads((output/'workflow.json').read_text())
            self.assertEqual(workflow['stages'][0]['execution'], 'verified_reuse')
            self.assertEqual(saved_manifest, manifest_path.read_bytes())

    def test_dependency_inspection_reports_available_python(self):
        dependency = ExampleTextTransformAdapter().inspect_dependency()
        self.assertEqual(dependency['status'], 'available')
        self.assertTrue(dependency['dependencies'][0]['path'])
        self.assertEqual(len(dependency['dependencies'][0]['sha256']), 64)
        self.assertTrue(dependency['dependencies'][0]['version_output'])

    def test_missing_dependency_is_an_infrastructure_state_and_preserves_prior_files(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            fasta = root/'fixture.fa'
            fasta.write_text('>fixture\nACGT\n', encoding='utf-8')
            adapter = CommandFixtureAdapter(command='no-such-fixture-executable-9876')
            registry = artifact_workflow.build_default_registry()
            registry.register_external_adapter(adapter)
            specification = root/'workflow.json'
            specification.write_text(json.dumps({
                'schema': 'artifact-workflow-v1',
                'stages': [
                    {'id': 'inventory', 'kind': 'inventory', 'inputs': {'fasta': fasta.name}},
                    {'id': 'external', 'kind': 'fixture_external', 'inputs': {'source': source.name}},
                ],
            }))
            output = root/'out'
            report = artifact_workflow.run(specification, output, registry)
            workflow = json.loads((output/'workflow.json').read_text())
            self.assertEqual(report, output/'report.html')
            self.assertEqual(workflow['status'], 'dependency_missing')
            self.assertEqual(workflow['stages'][0]['status'], 'complete')
            self.assertEqual(workflow['stages'][1]['status'], 'dependency_missing')
            self.assertTrue((output/'inventory/manifest.json').is_file())
            self.assertFalse((output/'external').exists())
            self.assertIn('DEPENDENCY MISSING', (output/'report.html').read_text())

    def test_external_module_placeholder_reports_unregistered_requirement(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            specification = root/'workflow.json'
            specification.write_text(json.dumps({
                'schema': 'artifact-workflow-v1',
                'stages': [{
                    'id': 'future',
                    'kind': 'external_module',
                    'module': 'future.adapter',
                    'inputs': {'source': source.name},
                }],
            }))
            output = root/'out'
            artifact_workflow.run(specification, output)
            workflow = json.loads((output/'workflow.json').read_text())
            self.assertEqual(workflow['status'], 'external_module_required')
            self.assertEqual(workflow['stages'][0]['status'], 'external_module_required')
            self.assertEqual(workflow['stages'][0]['required_module'], 'future.adapter')
            self.assertFalse((output/'future').exists())
            report = (output/'report.html').read_text()
            self.assertIn('EXTERNAL MODULE REQUIRED', report)
            self.assertIn('future.adapter', report)

    def test_registered_module_placeholder_invokes_trusted_adapter(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            registry = artifact_workflow.build_default_registry()
            adapter = CommandFixtureAdapter()
            registry.register_external_adapter(adapter)
            specification = root/'workflow.json'
            specification.write_text(json.dumps({
                'schema': 'artifact-workflow-v1',
                'stages': [{
                    'id': 'future',
                    'kind': 'external_module',
                    'module': 'fixture.external',
                    'inputs': {'source': source.name},
                    'config': {'prefix': 'trusted:'},
                }],
            }))
            output = root/'out'
            artifact_workflow.run(specification, output, registry)
            workflow = json.loads((output/'workflow.json').read_text())
            self.assertEqual(workflow['status'], 'complete')
            self.assertEqual(workflow['stages'][0]['registered_module'], 'fixture.external')
            self.assertEqual((output/'future/result.txt').read_text(), 'trusted:artificial text\n')

    def test_nonzero_tool_exit_is_recorded_with_separate_stderr(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            adapter = CommandFixtureAdapter('fail')
            with self.assertRaises(ExternalToolExitError) as raised:
                adapter.execute({'source': source}, root/'out', {})
            self.assertEqual(raised.exception.returncode, 7)
            manifest = json.loads((root/'out/manifest.json').read_text())
            self.assertEqual(manifest['status'], 'failed')
            self.assertEqual(manifest['exit_status'], 7)
            self.assertIn('fixture failure', (root/'out/stderr.log').read_text())
            self.assertEqual(manifest['output_inventory'][0]['path'], 'stderr.log')

    def test_timeout_cleans_up_and_records_failure(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            adapter = CommandFixtureAdapter('timeout', timeout=.15)
            with self.assertRaisesRegex(TimeoutError, 'time budget'):
                adapter.execute({'source': source}, root/'out', {})
            manifest = json.loads((root/'out/manifest.json').read_text())
            self.assertEqual(manifest['status'], 'failed')
            self.assertEqual(manifest['error_type'], 'TimeoutError')
            self.assertTrue((root/'out/stdout.log').is_file())
            self.assertTrue((root/'out/stderr.log').is_file())

    def test_interruption_is_recorded_and_lock_released(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            adapter = CommandFixtureAdapter('interrupt')
            with patch.object(bounded_process, 'run_captured', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    adapter.execute({'source': source}, root/'out', {})
            manifest = json.loads((root/'out/manifest.json').read_text())
            self.assertEqual(manifest['status'], 'interrupted')
            self.assertFalse((root/'out/.external-tool.lock').exists())

    def test_missing_required_input_and_malformed_config_rejected(self):
        with scratch_directory() as folder:
            root = Path(folder)
            adapter = ExampleTextTransformAdapter()
            missing = root/'missing.txt'
            with self.assertRaises(FileNotFoundError):
                adapter.execute({'source': missing}, root/'out', {})
            with self.assertRaisesRegex(ValueError, 'prefix'):
                adapter.validate_config({'prefix': ['not', 'text']})
            with self.assertRaisesRegex(ValueError, 'prefix'):
                adapter.validate_config({'command': 'arbitrary shell'})
            self.assertFalse((root/'out').exists())

    def test_optional_inputs_may_be_omitted_but_unknown_inputs_are_rejected(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            annotation = root/'annotation.txt'
            annotation.write_text('optional fixture\n', encoding='utf-8')
            adapter = CommandFixtureAdapter()
            self.assertEqual(
                set(adapter.validate_inputs({'source': source}, root/'out')),
                {'source'},
            )
            self.assertEqual(
                set(adapter.validate_inputs(
                    {'source': source, 'annotation': annotation}, root/'out')),
                {'source', 'annotation'},
            )
            with self.assertRaisesRegex(ValueError, 'incorrect input fields'):
                adapter.validate_inputs(
                    {'source': source, 'unknown': annotation}, root/'out')

    def test_changed_input_or_configuration_invalidates_reuse(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            adapter = CommandFixtureAdapter()
            output = root/'out'
            adapter.execute({'source': source}, output, {'prefix': 'one:'})
            source.write_text('changed input\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'changed'):
                adapter.execute({'source': source}, output, {'prefix': 'one:'})

        with scratch_directory() as folder:
            root = Path(folder)
            source = self.fixture(root)
            adapter = CommandFixtureAdapter()
            output = root/'out'
            adapter.execute({'source': source}, output, {'prefix': 'one:'})
            with self.assertRaisesRegex(ValueError, 'configuration'):
                adapter.execute({'source': source}, output, {'prefix': 'two:'})


class WorkflowRegistryAndStateTests(unittest.TestCase):
    def test_default_registry_is_deterministic_and_includes_legacy_and_example_stages(self):
        registry = artifact_workflow.build_default_registry()
        rows = registry.describe()
        self.assertEqual(rows, sorted(rows, key=lambda row: row['kind']))
        self.assertEqual(registry.fields, artifact_workflow.FIELDS)
        for kind in ('inventory', 'cram', 'artifact_benchmark', 'example_text_transform'):
            self.assertIn(kind, registry.fields)
        self.assertEqual(registry.get('example_text_transform').module_name, 'example.text_transform')

    def test_duplicate_registration_and_unknown_stage_are_rejected(self):
        registry = WorkflowStageRegistry()
        registry.register('fixture', {'source'}, lambda inputs, output, config: None)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            registry.register('fixture', {'source'}, lambda inputs, output, config: None)
        with self.assertRaisesRegex(ValueError, 'Unknown workflow stage'):
            registry.get('not_registered')

    def test_unknown_stage_and_arbitrary_command_config_rejected(self):
        for kind, extra in (('not_registered', {}), ('inventory', {'command': 'echo unsafe'})):
            with self.subTest(kind=kind):
                spec = {'schema': 'artifact-workflow-v1', 'stages': [{
                    'id': 'stage', 'kind': kind, 'inputs': {'fasta': 'input.fa'}, **extra,
                }]}
                with self.assertRaises(ValueError):
                    artifact_workflow.validate(spec)

    def test_v1_manifests_without_new_fields_remain_valid(self):
        spec = {'schema': 'artifact-workflow-v1', 'stages': [
            {'id': 'legacy', 'kind': 'inventory', 'inputs': {'fasta': 'input.fa'}},
        ]}
        self.assertEqual(artifact_workflow.validate(spec), spec['stages'])

    def test_skip_is_distinct_from_complete_and_not_executed(self):
        with scratch_directory() as folder:
            root = Path(folder)
            spec = root/'workflow.json'
            spec.write_text(json.dumps({
                'schema': 'artifact-workflow-v1',
                'stages': [{
                    'id': 'later',
                    'kind': 'inventory',
                    'inputs': {'fasta': 'does-not-exist.fa'},
                    'skip': True,
                }],
            }))
            output = root/'out'
            artifact_workflow.run(spec, output)
            workflow = json.loads((output/'workflow.json').read_text())
            self.assertEqual(workflow['status'], 'skipped')
            self.assertEqual(workflow['stages'][0]['status'], 'skipped')
            self.assertFalse((output/'later').exists())
            report = (output/'report.html').read_text()
            self.assertIn('SKIPPED', report)
            self.assertNotIn('COMPLETE', report)

    def test_all_stage_states_have_explicit_valid_transition_paths(self):
        self.assertEqual(STAGE_STATES, set(STAGE_TRANSITIONS))
        for target in STAGE_STATES - {'pending', 'running'}:
            record = {'status': 'pending'}
            if target != 'skipped':
                transition(record, 'running', STAGE_TRANSITIONS)
            transition(record, target, STAGE_TRANSITIONS)
            self.assertEqual(record['status'], target)
        for state in STAGE_STATES:
            self.assertIn(state, STAGE_TRANSITIONS)
        with self.assertRaisesRegex(ValueError, 'Invalid workflow state transition'):
            transition({'status': 'complete'}, 'running', STAGE_TRANSITIONS)
        self.assertEqual(set(WORKFLOW_TRANSITIONS), set(STAGE_STATES) | {'partial'})
