"""Synthetic tests for the versioned M5 execution-outcome handoff."""
import hashlib
import inspect
import json
from pathlib import Path
import unittest

from test_metadata import scratch_directory

from satellite_discovery import dvg_evidence, execution_outcome
from satellite_discovery.external_tool import ExternalToolAdapter
from satellite_discovery.virema_adapter import (
    ViReMaDVGAdapter,
    _compatible_m5_source_hashes,
)


def _workflow(*, workflow_status='complete', stage_status='complete',
              m5_status=dvg_evidence.DVG_EVIDENCE_DETECTED):
    return {
        'schema': 'artifact-workflow-manifest-v2',
        'workflow_id': 'synthetic-workflow',
        'configuration_sha256': 'a' * 64,
        'status': workflow_status,
        'stages': [{
            'id': 'dvg',
            'kind': 'fixture_dvg_virema',
            'evidence_family': 'dvg',
            'status': stage_status,
            'dvg_evidence': {'status': m5_status},
        }],
    }


def _write_workflow(output, workflow):
    output.mkdir(parents=True, exist_ok=True)
    path = output / 'workflow.json'
    path.write_text(json.dumps(workflow, sort_keys=True), encoding='utf-8')
    return path


class ExecutionOutcomeTests(unittest.TestCase):
    def test_terminal_sidecar_binds_raw_statuses_and_explicit_references(self):
        with scratch_directory() as directory:
            root = Path(directory)
            producer = root / 'producer'
            workflow_path = _write_workflow(producer, _workflow())
            (root / 'input.json').write_text('{}', encoding='utf-8')

            written = execution_outcome.write_final_outcomes(producer)
            self.assertEqual(written, ['execution-outcomes/dvg.json'])
            record_path = producer / written[0]
            record_bytes = record_path.read_bytes()
            record = json.loads(record_bytes)
            workflow_bytes = workflow_path.read_bytes()

            self.assertEqual(record['schema'], execution_outcome.SCHEMA)
            self.assertEqual(record['producer_execution_status_raw'], 'complete')
            self.assertEqual(
                record['producer_status_raw'],
                dvg_evidence.DVG_EVIDENCE_DETECTED,
            )
            self.assertEqual(record['outcome_code'], 'COMPLETED_EVENTS')
            self.assertEqual(
                record['workflow_manifest_sha256'],
                hashlib.sha256(workflow_bytes).hexdigest(),
            )

            result = execution_outcome.verify_execution_outcome_refs(
                root / 'input.json',
                {
                    'path': 'producer/workflow.json',
                    'sha256': hashlib.sha256(workflow_bytes).hexdigest(),
                    'workflow_id': 'synthetic-workflow',
                },
                {
                    'path': 'producer/execution-outcomes/dvg.json',
                    'sha256': hashlib.sha256(record_bytes).hexdigest(),
                    'schema': execution_outcome.SCHEMA,
                },
                expected_stage_id='dvg',
            )
            self.assertEqual(result['record'], record)

    def test_nonterminal_workflow_does_not_emit_final_sidecar(self):
        with scratch_directory() as directory:
            output = Path(directory)
            _write_workflow(
                output,
                _workflow(workflow_status='running', stage_status='running'),
            )
            self.assertEqual(execution_outcome.write_final_outcomes(output), [])
            self.assertFalse((output / 'execution-outcomes').exists())

    def test_skipped_and_invalid_results_have_distinct_outcome_classes(self):
        with scratch_directory() as directory:
            output = Path(directory) / 'skipped'
            _write_workflow(
                output,
                _workflow(
                    workflow_status='partial',
                    stage_status='skipped',
                    m5_status=dvg_evidence.NOT_EVALUATED,
                ),
            )
            execution_outcome.write_final_outcomes(output)
            skipped = json.loads(
                (output / 'execution-outcomes/dvg.json').read_text(encoding='utf-8')
            )
            self.assertEqual(skipped['outcome_code'], 'NOT_STARTED')

            for failure_code, expected in (
                (dvg_evidence.TRUNCATED_OUTPUT, 'INCOMPLETE_OUTPUT'),
                (dvg_evidence.CORRUPT_OUTPUT, 'INVALID_OUTPUT'),
            ):
                with self.subTest(failure_code=failure_code):
                    workflow = _workflow(
                        workflow_status='failed',
                        stage_status='failed',
                        m5_status=dvg_evidence.INVALID_RESULT,
                    )
                    workflow['stages'][0]['error_type'] = 'InvalidDVGResultError'
                    failure_codes = {'dvg': failure_code}
                    _write_workflow(output, workflow)
                    execution_outcome.write_final_outcomes(
                        output, failure_codes=failure_codes
                    )
                    record = json.loads(
                        (output / 'execution-outcomes/dvg.json').read_text(
                            encoding='utf-8'
                        )
                    )
                    self.assertEqual(record['failure_code'], failure_code)
                    self.assertEqual(record['outcome_code'], expected)

    def test_record_cannot_be_reused_after_workflow_manifest_changes(self):
        with scratch_directory() as directory:
            root = Path(directory)
            producer = root / 'producer'
            workflow_path = _write_workflow(producer, _workflow())
            (root / 'input.json').write_text('{}', encoding='utf-8')
            execution_outcome.write_final_outcomes(producer)
            record_path = producer / 'execution-outcomes/dvg.json'
            workflow_bytes = workflow_path.read_bytes()
            record_bytes = record_path.read_bytes()

            workflow_path.write_bytes(workflow_bytes + b'\n')
            with self.assertRaises(execution_outcome.ExecutionOutcomeInvalidError):
                execution_outcome.verify_execution_outcome_refs(
                    root / 'input.json',
                    {
                        'path': 'producer/workflow.json',
                        'sha256': hashlib.sha256(workflow_bytes).hexdigest(),
                        'workflow_id': 'synthetic-workflow',
                    },
                    {
                        'path': 'producer/execution-outcomes/dvg.json',
                        'sha256': hashlib.sha256(record_bytes).hexdigest(),
                        'schema': execution_outcome.SCHEMA,
                    },
                )

    def test_explicit_references_reject_traversal_and_symlinks(self):
        with scratch_directory() as directory:
            root = Path(directory)
            producer = root / 'producer'
            workflow_path = _write_workflow(producer, _workflow())
            (root / 'input.json').write_text('{}', encoding='utf-8')
            execution_outcome.write_final_outcomes(producer)
            record_path = producer / 'execution-outcomes/dvg.json'
            workflow_bytes = workflow_path.read_bytes()
            record_bytes = record_path.read_bytes()
            workflow_sha = hashlib.sha256(workflow_bytes).hexdigest()
            record_sha = hashlib.sha256(record_bytes).hexdigest()
            outcome_ref = {
                'path': 'producer/execution-outcomes/dvg.json',
                'sha256': record_sha,
                'schema': execution_outcome.SCHEMA,
            }

            with self.assertRaises(execution_outcome.ExecutionOutcomeInvalidError):
                execution_outcome.verify_execution_outcome_refs(
                    root / 'input.json',
                    {
                        'path': '../producer/workflow.json',
                        'sha256': workflow_sha,
                        'workflow_id': 'synthetic-workflow',
                    },
                    outcome_ref,
                )

            alias = producer / 'workflow-alias.json'
            try:
                alias.symlink_to(workflow_path)
            except (OSError, NotImplementedError):
                self.skipTest('Creating symlinks requires platform privileges')
            with self.assertRaises(execution_outcome.ExecutionOutcomeInvalidError):
                execution_outcome.verify_execution_outcome_refs(
                    root / 'input.json',
                    {
                        'path': 'producer/workflow-alias.json',
                        'sha256': workflow_sha,
                        'workflow_id': 'synthetic-workflow',
                    },
                    outcome_ref,
                )

    def test_nonterminal_referenced_workflow_is_incomplete(self):
        with scratch_directory() as directory:
            root = Path(directory)
            producer = root / 'producer'
            workflow_path = _write_workflow(
                producer,
                _workflow(workflow_status='running', stage_status='running'),
            )
            (root / 'input.json').write_text('{}', encoding='utf-8')
            workflow_bytes = workflow_path.read_bytes()
            with self.assertRaises(execution_outcome.ExecutionOutcomeIncompleteError):
                execution_outcome.verify_execution_outcome_refs(
                    root / 'input.json',
                    {
                        'path': 'producer/workflow.json',
                        'sha256': hashlib.sha256(workflow_bytes).hexdigest(),
                        'workflow_id': 'synthetic-workflow',
                    },
                    {
                        'path': 'producer/execution-outcomes/dvg.json',
                        'sha256': 'b' * 64,
                        'schema': execution_outcome.SCHEMA,
                    },
                )

    def test_cache_aliases_are_exact_and_fail_closed(self):
        old = ('1' * 64, '2' * 64, '3' * 64)
        current = ('a' * 64, 'b' * 64, 'c' * 64)
        compatibility = (
            'schema=m5-execution-outcome-cache-compat-v1\n'
            f'entry={",".join(current)};{",".join(old)}\n'
        )
        self.assertEqual(
            _compatible_m5_source_hashes(current, compatibility),
            old,
        )
        changed = ('d' * 64, current[1], current[2])
        self.assertEqual(
            _compatible_m5_source_hashes(changed, compatibility),
            changed,
        )

    def test_production_m5_cache_identity_uses_only_the_exact_legacy_alias(self):
        adapter = ViReMaDVGAdapter()
        source_paths = (
            Path(inspect.getsourcefile(ViReMaDVGAdapter)),
            Path(inspect.getsourcefile(ExternalToolAdapter)),
            Path(dvg_evidence.__file__),
        )
        actual = tuple(
            hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths
        )
        legacy = {
            (
                '83e875b54b5c2679e0fce889ecb6eacbb8864eb8597b75cd2f3eb34fc0f164bd',
                '066a69ab58ddb83663be035cedbc3a7e927524b9d3ea2f9b80438e4aa9dcead5',
                '82f6caacac559647bcef8dfbd3f18c001fe71053670eb3077cb4415b66df13d8',
            ): (
                '669b1c99a3eb163d1a485635f0b7f1ec247cf375951247eabb368306171be5f9',
                'a9520633d5f6939e608deac89fb1d5c5ca00a46dba9eb0666c1fda6d2a3b9e2e',
                '5ca01c7b1b706fbff8fa4e5015bad30ecc4d461b4dd69e02e348301e905069f8',
            ),
            (
                '78dca36b55df1bb33db1597d1d98e2d3b7afad0273e0a64f7f4a26d08ac5b007',
                '41deb66d3966e143bec635cc195d9f21a5ee8676c1108116dbd6212a724b2304',
                'a95e00ef989adb669d3b76bd4ea04d18fcb9e319ac0449b5c4302adc250bda7c',
            ): (
                'e82196a7691ee422666f50aab89eede0212735e3c12bcaec45a00237a87b047b',
                '1993666f4e849fdfe91eb60b7ba4fbbd42ea080e9ec7ac1281e645ece3721662',
                '509aba54e0120e8674d1ab27d85e26fe799791816614c4e101ee9b335cbe4fb8',
            ),
        }
        self.assertIn(actual, legacy)
        implementation = adapter.cache_implementation_identity()
        self.assertEqual(
            (
                implementation['adapter_source_sha256'],
                implementation['executor_source_sha256'],
                implementation['parser_source_sha256'],
            ),
            legacy[actual],
        )
        identity = adapter._identity(
            {}, {}, {'dependencies': [], 'source_sha256': {}}, [],
            {'python': 'synthetic', 'platform': 'synthetic'},
        )
        self.assertEqual(
            identity['adapter']['source_sha256'],
            legacy[actual][0],
        )


if __name__ == '__main__':
    unittest.main()