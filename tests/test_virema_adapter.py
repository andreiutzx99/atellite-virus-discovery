"""Artificial ViReMa adapter tests; no upstream software or user data required."""
import json
import hashlib
from types import SimpleNamespace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery import bounded_process, dvg_evidence
from satellite_discovery.external_tool import ExternalToolExitError
from satellite_discovery.sequence_downloader import checksum
from satellite_discovery.virema_adapter import (
    BOWTIE_SHA256, CALLER_NAME, CALLER_VERSION, SOURCE_HASHES, ViReMaDVGAdapter,
)


class FixtureViReMaAdapter(ViReMaDVGAdapter):
    """Use Python as a trusted artificial caller while retaining adapter logic."""

    def __init__(self, behavior='positive', *, timeout=5, max_bytes=1_000_000):
        self.behavior = behavior
        self.identity_tag = 'fixture-source-v1'
        self.dual_reads_staged = False
        super().__init__(timeout=timeout, max_bytes=max_bytes)

    def prepare_execution(self, output, inputs, config, manifest):
        super().prepare_execution(output, inputs, config, manifest)
        raw_name = 'reads.fastq.gz' if inputs['reads'].name.endswith('.gz') else 'reads.fastq'
        self.dual_reads_staged = (
            (Path(output) / raw_name).is_file()
            and (Path(output) / 'raw' / raw_name).is_file()
        )

    def inspect_dependency(self, config=None):
        dependencies = []
        for name, path in (
                ('python', sys.executable), ('bowtie', '/fixture/bin/bowtie'),
                ('bowtie-build', '/fixture/bin/bowtie-build'),
                ('bowtie-inspect', '/fixture/bin/bowtie-inspect')):
            dependencies.append({
                'tool': name, 'path': path, 'sha256': 'a' * 64,
                'status': 'version_check_passed',
                'version_output': 'fixture 0.12.9' if name != 'python' else 'Python fixture',
            })
        return {
            'status': 'available',
            'source_commit': 'fixture-commit',
            'source_sha256': {
                'ViReMa.py': 'b' * 64,
                'fixture': hashlib.sha256(self.identity_tag.encode()).hexdigest(),
            },
            'dependencies': dependencies,
        }

    def build_command(self, executables, inputs, output, config):
        behavior = self.behavior
        code = (
            "from pathlib import Path; import sys,time; "
            "out=Path(sys.argv[1]); mode=sys.argv[2]; "
            "time.sleep(30) if mode=='timeout' else None; "
            "sys.exit(7) if mode=='nonzero' else None; "
            "Path(out/'Virus_Recombination_Results.txt').write_text("
            "('@NewLibrary: REF_to_REF\\n1_to_2_#_1\\t\\n@EndofLibrary\\n' "
            "if mode in ('positive','malformed','partial') else ''), encoding='utf-8'); "
            "print('Total of 0 reads have been analysed:' if mode in "
            "('partial','zero_analysed') else 'Total of 1 reads have been analysed:'); "
            "print('of which 1 were Viral Recombinations, 0 were Host Recombinations "
            "and 0 were Virus-to-Host Recombinations' if mode in "
            "('positive','malformed','partial') else 'of which 0 were Viral Recombinations, "
            "0 were Host Recombinations and 0 were Virus-to-Host Recombinations'); "
            "print('Time to complete in seconds:  0.1')"
        )
        if behavior == 'malformed':
            code = (
                "from pathlib import Path; import sys; "
                "(Path(sys.argv[1])/'Virus_Recombination_Results.txt').write_text("
                "'@NewLibrary: REF_to_REF\\n1_to_2_#_1\\n@EndofLibrary\\n'); "
                "print('Total of 1 reads have been analysed:'); "
                "print('of which 1 were Viral Recombinations, 0 were Host Recombinations "
                "and 0 were Virus-to-Host Recombinations'); "
                "print('Time to complete in seconds:  0.1')"
            )
        if behavior == 'large':
            code = (
                "from pathlib import Path; import sys; "
                "(Path(sys.argv[1])/'Virus_Recombination_Results.txt').write_text('X'*20000); "
                "print('Total of 1 reads have been analysed:'); "
                "print('of which 0 were Viral Recombinations, 0 were Host Recombinations "
                "and 0 were Virus-to-Host Recombinations'); "
                "print('Time to complete in seconds:  0.1')"
            )
        if behavior == 'missing':
            code = (
                "print('Total of 1 reads have been analysed:'); "
                "print('of which 0 were Viral Recombinations, 0 were Host Recombinations "
                "and 0 were Virus-to-Host Recombinations'); "
                "print('Time to complete in seconds:  0.1')"
            )
        return [executables['python'], '-c', code, str(Path(output) / 'raw'), behavior]

    def cache_implementation_identity(self):
        result = super().cache_implementation_identity()
        result['fixture_identity'] = self.identity_tag
        return result


class ViReMaAdapterTests(unittest.TestCase):
    def fixture_inputs(self, root, *, catalogue=False):
        reads = root / 'reads.fastq'
        reads.write_text('@read1\nACGT\n+\n!!!!\n', encoding='ascii')
        reference = root / 'reference.fa'
        reference.write_text('>REF\nACGTACGT\n', encoding='ascii')
        inputs = {'reads': reads, 'reference': reference}
        if catalogue:
            table = root / 'records.csv'
            table.write_text(
                'record_id,sequence_sha256,length\n'
                f'REF,{checksum_bytes(b"ACGTACGT")},8\n',
                encoding='ascii',
            )
            inputs['catalogue_records'] = table
        return inputs

    def config(self):
        return {'sample_id': 'sample-1'}

    def test_declared_contract_and_strict_config(self):
        adapter = ViReMaDVGAdapter()
        self.assertEqual(adapter.kind, 'dvg_virema')
        self.assertEqual(adapter.module_name, 'dvg.virema')
        self.assertEqual(adapter.evidence_family, 'dvg')
        self.assertEqual(adapter.input_contracts['reads'], ('validated_fastq',))
        self.assertEqual(adapter.input_contracts['reference'], (
            'raw_fasta', 'canonical_contig_fasta', 'catalogue_fasta',
            'reference_records_fasta',
        ))
        self.assertEqual(adapter.output_files, (
            'raw/Virus_Recombination_Results.txt', 'evidence.json',
            'summary.json', 'parameters.json', 'report.html',
        ))
        self.assertEqual(adapter.output_contracts, {
            '*Virus_Recombination_Results.txt': 'dvg_raw_output',
            'evidence.json': 'dvg_evidence',
            'summary.json': 'dvg_evidence_summary',
            'parameters.json': 'dvg_parameters',
            'report.html': 'report',
        })
        self.assertEqual(adapter.validate_config({'sample_id': 'S1'}), {
            'sample_id': 'S1', 'seed': 25, 'mismatches': 1, 'threads': 1,
        })
        for invalid in (
                {'sample_id': '../x'}, {'sample_id': 'S', 'args': ['unsafe']},
                {'sample_id': 'S', 'seed': True}, {'sample_id': 'S', 'seed': 11},
                {'sample_id': 'S', 'mismatches': 4}, {'sample_id': 'S', 'threads': 0},
                {'sample_id': 'S', 'executable': '/tmp/tool'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                adapter.validate_config(invalid)

    def test_positive_result_has_normalized_provenance_and_preserves_inputs(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = self.fixture_inputs(root, catalogue=True)
            before = {name: path.read_bytes() for name, path in inputs.items()}
            adapter = FixtureViReMaAdapter()
            result = adapter.execute(inputs, root / 'out', self.config())
            self.assertEqual(result.execution, 'executed')
            self.assertTrue(adapter.dual_reads_staged)
            self.assertEqual({name: path.read_bytes() for name, path in inputs.items()}, before)
            evidence = json.loads((root / 'out/evidence.json').read_text())
            summary = json.loads((root / 'out/summary.json').read_text())
            parameters = json.loads((root / 'out/parameters.json').read_text())
            event = evidence['events'][0]
            self.assertEqual(evidence['status'], dvg_evidence.DVG_EVIDENCE_DETECTED)
            self.assertEqual(event['caller'], CALLER_NAME)
            self.assertEqual(event['caller_version'], CALLER_VERSION)
            self.assertEqual(event['sample_id'], 'sample-1')
            self.assertEqual(event['breakpoint_1'], 1)
            self.assertIsNone(event['score'])
            self.assertIsNone(event['junction_sequence'])
            self.assertEqual(event['raw_output_reference']['sha256'],
                             checksum(root / 'out/raw/Virus_Recombination_Results.txt'))
            self.assertEqual(event['catalogue_linkage']['status'], 'resolved')
            self.assertEqual(summary['event_count'], 1)
            self.assertEqual(summary['raw_output']['path'],
                             'raw/Virus_Recombination_Results.txt')
            self.assertEqual(parameters['schema'], 'dvg-parameters-v1')
            self.assertEqual(parameters['caller'], CALLER_NAME)
            self.assertIn('ViReMa.py', parameters['source_sha256'])
            self.assertTrue((root / 'out/report.html').is_file())
            self.assertTrue((root / 'out/reference.fasta').is_file())
            self.assertTrue((root / 'out/raw/reads.fastq').is_file())
            self.assertFalse((root / 'out/reads.fastq').exists())
            report = (root / 'out/report.html').read_text()
            self.assertIn('ViReMa 0.25', report)
            self.assertIn(event['evidence_id'], report)
            self.assertIn('href="evidence.json"', report)
            self.assertIn('href="raw/Virus_Recombination_Results.txt"', report)
            self.assertIn('not a biological classification', report)

    def test_empty_native_result_is_scoped_no_evidence(self):
        with scratch_directory() as folder:
            root = Path(folder)
            result = FixtureViReMaAdapter('empty').execute(
                self.fixture_inputs(root), root / 'out', self.config())
            evidence = json.loads((root / 'out/evidence.json').read_text())
            self.assertEqual(result.execution, 'executed')
            self.assertEqual(evidence['status'], dvg_evidence.NO_DVG_EVIDENCE_DETECTED)
            report = (root / 'out/report.html').read_text()
            self.assertIn('under these run settings', report)
            self.assertIn('do not establish', report)
            self.assertNotIn('NON_DVG', report)

    def test_malformed_native_result_fails_and_is_not_zero_event_evidence(self):
        with scratch_directory() as folder:
            root = Path(folder)
            with self.assertRaises(dvg_evidence.InvalidDVGResultError):
                FixtureViReMaAdapter('malformed').execute(
                    self.fixture_inputs(root), root / 'out', self.config())
            manifest = json.loads((root / 'out/manifest.json').read_text())
            self.assertEqual(manifest['status'], 'failed')
            self.assertFalse((root / 'out/evidence.json').exists())

    def test_partial_or_zero_analysed_stdout_is_invalid_for_nonempty_fastq(self):
        for mode in ('partial', 'zero_analysed'):
            with self.subTest(mode=mode), scratch_directory() as folder:
                root = Path(folder)
                with self.assertRaises(dvg_evidence.InvalidDVGResultError):
                    FixtureViReMaAdapter(mode).execute(
                        self.fixture_inputs(root), root / 'out', self.config())
                self.assertFalse((root / 'out/evidence.json').exists())

    def test_missing_native_result_fails_without_a_zero_event_claim(self):
        with scratch_directory() as folder:
            root = Path(folder)
            with self.assertRaisesRegex(dvg_evidence.InvalidDVGResultError, 'missing'):
                FixtureViReMaAdapter('missing').execute(
                    self.fixture_inputs(root), root / 'out', self.config())
            self.assertFalse((root / 'out/evidence.json').exists())

    def test_nonzero_timeout_and_size_limit_record_failures(self):
        scenarios = (
            ('nonzero', 1_000_000, ExternalToolExitError),
            ('timeout', 1_000_000, TimeoutError),
            ('large', 10_000, ValueError),
        )
        for mode, budget, error_type in scenarios:
            with self.subTest(mode=mode), scratch_directory() as folder:
                root = Path(folder)
                adapter = FixtureViReMaAdapter(mode, timeout=.15, max_bytes=budget)
                with self.assertRaises(error_type):
                    adapter.execute(self.fixture_inputs(root), root / 'out', self.config())
                manifest = json.loads((root / 'out/manifest.json').read_text())
                self.assertEqual(manifest['status'], 'failed')
                self.assertFalse((root / 'out/evidence.json').exists())

    def test_interruption_is_recorded_and_lock_released(self):
        with scratch_directory() as folder:
            root = Path(folder)
            with patch.object(bounded_process, 'run_captured', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    FixtureViReMaAdapter().execute(
                        self.fixture_inputs(root), root / 'out', self.config())
            manifest = json.loads((root / 'out/manifest.json').read_text())
            self.assertEqual(manifest['status'], 'interrupted')
            self.assertFalse((root / 'out/.external-tool.lock').exists())

    def test_reuse_checks_inventory_semantics_and_implementation_identity(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = self.fixture_inputs(root)
            output = root / 'out'
            adapter = FixtureViReMaAdapter()
            adapter.execute(inputs, output, self.config())
            self.assertEqual(adapter.execute(inputs, output, self.config()).execution,
                             'verified_reuse')
            (output / 'raw/Virus_Recombination_Results.txt').write_text('corrupt\n')
            with self.assertRaises(dvg_evidence.InvalidDVGResultError):
                adapter.execute(inputs, output, self.config())
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = self.fixture_inputs(root)
            output = root / 'out'
            adapter = FixtureViReMaAdapter()
            adapter.execute(inputs, output, self.config())
            adapter.identity_tag = 'fixture-source-v2'
            with self.assertRaisesRegex(ValueError, 'changed'):
                adapter.execute(inputs, output, self.config())

    def test_relocated_identical_inputs_reuse_and_manifest_keeps_original_paths(self):
        with scratch_directory() as folder:
            root = Path(folder)
            original = self.fixture_inputs(root)
            output = root / 'out'
            adapter = FixtureViReMaAdapter()
            adapter.execute(original, output, self.config())
            manifest_path = output / 'manifest.json'
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest['inputs']['reads']['path'], str(original['reads'].resolve()))
            self.assertEqual(
                manifest['inputs']['reference']['path'],
                str(original['reference'].resolve()),
            )

            rematerialized = root / 'rematerialized'
            rematerialized.mkdir()
            relocated = {}
            for name, source in original.items():
                destination = rematerialized / ('new-' + source.name)
                destination.write_bytes(source.read_bytes())
                relocated[name] = destination
            reused = adapter.execute(relocated, output, self.config())
            self.assertEqual(reused.execution, 'verified_reuse')

            # Reuse does not rewrite provenance: the completed record continues
            # to identify the original files that produced these artifacts.
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest['inputs']['reads']['path'], str(original['reads'].resolve()))
            self.assertEqual(
                manifest['inputs']['reference']['path'],
                str(original['reference'].resolve()),
            )

            changed = dict(relocated)
            changed_reads = rematerialized / 'changed.fastq'
            changed_reads.write_text('@other\nTGCA\n+\n!!!!\n', encoding='ascii')
            changed['reads'] = changed_reads
            with self.assertRaisesRegex(ValueError, 'changed'):
                adapter.execute(changed, output, self.config())

    def test_native_hash_or_normalized_semantics_are_rechecked(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = self.fixture_inputs(root)
            output = root / 'out'
            FixtureViReMaAdapter().execute(inputs, output, self.config())
            evidence_path = output / 'evidence.json'
            evidence = json.loads(evidence_path.read_text())
            evidence['events'][0]['breakpoint_1'] = 3
            evidence_path.write_text(json.dumps(evidence))
            with self.assertRaises(dvg_evidence.InvalidDVGResultError):
                FixtureViReMaAdapter().execute(inputs, output, self.config())

    def test_malformed_normalized_json_is_invalid_result_on_reuse(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = self.fixture_inputs(root)
            output = root / 'out'
            FixtureViReMaAdapter().execute(inputs, output, self.config())
            (output / 'evidence.json').write_text('{bad json', encoding='utf-8')
            with self.assertRaises(dvg_evidence.InvalidDVGResultError):
                FixtureViReMaAdapter().execute(inputs, output, self.config())

    def test_reference_parser_and_caller_implementation_changes_invalidate_reuse(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = self.fixture_inputs(root)
            output = root / 'out'
            adapter = FixtureViReMaAdapter()
            adapter.execute(inputs, output, self.config())
            (output / 'reference.fasta').write_text('>REF\nTTTTTTTT\n')
            with self.assertRaisesRegex(ValueError, 'integrity'):
                adapter.execute(inputs, output, self.config())

        with scratch_directory() as folder:
            root = Path(folder)
            inputs = self.fixture_inputs(root)
            output = root / 'out'
            adapter = FixtureViReMaAdapter()
            adapter.execute(inputs, output, self.config())
            with patch('satellite_discovery.dvg_evidence.PARSER_VERSION', 'next'):
                with self.assertRaisesRegex(ValueError, 'changed|contract|provenance'):
                    adapter.execute(inputs, output, self.config())

        with scratch_directory() as folder:
            root = Path(folder)
            inputs = self.fixture_inputs(root)
            output = root / 'out'
            adapter = FixtureViReMaAdapter()
            adapter.execute(inputs, output, self.config())
            with patch('satellite_discovery.virema_adapter.CALLER_VERSION', '0.26'):
                with self.assertRaisesRegex(ValueError, 'changed|contract|provenance'):
                    adapter.execute(inputs, output, self.config())

    def test_missing_fastq_records_and_reference_copy_are_rejected(self):
        with scratch_directory() as folder:
            root = Path(folder)
            inputs = self.fixture_inputs(root)
            inputs['reads'].write_text('', encoding='ascii')
            with self.assertRaises(ValueError):
                FixtureViReMaAdapter().execute(inputs, root / 'out', self.config())

    def test_dependency_inspector_rejects_wrong_pinned_bowtie_binary_hash(self):
        with scratch_directory() as folder:
            home = Path(folder) / 'virema'
            home.mkdir()
            for name in SOURCE_HASHES:
                (home / name).write_text('artificial pinned source fixture')

            def inspect(name, command, version_args):
                digest = ('0' * 64 if name == 'bowtie' else
                          BOWTIE_SHA256.get(name, 'a' * 64))
                return {
                    'tool': name,
                    'path': sys.executable if name == 'python' else f'/fixture/bin/{name}',
                    'sha256': digest,
                    'status': 'version_check_passed',
                    'version_output': 'Python 3' if name == 'python' else 'bowtie version 0.12.9',
                }

            with (
                patch.dict('os.environ', {'VIREMA_HOME': str(home)}),
                patch('satellite_discovery.virema_adapter.platform.system', return_value='Linux'),
                patch('satellite_discovery.virema_adapter.platform.machine', return_value='x86_64'),
                patch('satellite_discovery.virema_adapter._sha',
                      side_effect=lambda path: SOURCE_HASHES[Path(path).name]),
                patch('satellite_discovery.virema_adapter.inspect_executable', side_effect=inspect),
                patch('satellite_discovery.virema_adapter.shutil.which',
                      side_effect=lambda command: f'/fixture/bin/{Path(command).name}'),
                patch('satellite_discovery.virema_adapter.subprocess.run',
                      return_value=SimpleNamespace(returncode=0)),
            ):
                dependency = ViReMaDVGAdapter().inspect_dependency()
            self.assertEqual(dependency['status'], 'dependency_missing')
            bowtie = next(row for row in dependency['dependencies'] if row['tool'] == 'bowtie')
            self.assertFalse(bowtie['pinned_sha256_match'])


def checksum_bytes(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


if __name__ == '__main__':
    unittest.main()