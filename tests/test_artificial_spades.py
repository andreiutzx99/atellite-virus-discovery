import gzip
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery import artificial_spades as diagnostic


class SpadesDiagnosticTests(unittest.TestCase):
    def invoke(self,root,paired=False,failure=None,contigs=None):
        tool=root/'spades.py';tool.write_text('artificial executable')
        def process(command,directory,log_name,**limits):
            if log_name=='version.log':
                (directory/log_name).write_text('SPAdes artificial mock version')
                return
            (directory/log_name).write_text('mock execution')
            if failure is not None:raise failure
            output=directory/'assembly';output.mkdir()
            (output/'contigs.fasta').write_text(contigs if contigs is not None else (directory/'truth.fasta').read_text())
            (output/'raw.txt').write_text('raw fixture evidence')
        with patch.object(diagnostic.shutil,'which',return_value=str(tool)),patch.object(diagnostic.bounded_process,'run',side_effect=process):
            return diagnostic.run(root/'out',paired)

    def test_single_and_paired_success_and_provenance(self):
        for paired in (False,True):
            with self.subTest(paired=paired),scratch_directory() as folder:
                root=Path(folder);result=self.invoke(root,paired)
                self.assertEqual(result['status'],'complete')
                data=json.loads((root/'out/diagnostic.json').read_text())
                self.assertEqual(data['status'],'passed')
                self.assertEqual(data['paired'],paired)
                self.assertEqual(data['contig_length'],2000)
                self.assertIn('assembly/raw.txt',data['raw_output_sha256'])
                self.assertEqual(data['exit_status'],0)
                self.assertIn('started_utc',data)
                self.assertFalse(data['scientific_validation'])

    def test_verified_reuse_and_corrupt_raw_file(self):
        with scratch_directory() as folder:
            root=Path(folder);self.invoke(root)
            before=(root/'out/manifest.json').read_bytes()
            with patch.object(diagnostic.shutil,'which',return_value=str(root/'spades.py')),patch.object(diagnostic.bounded_process,'run',side_effect=AssertionError('must not execute')):
                diagnostic.run(root/'out')
                self.assertEqual(before,(root/'out/manifest.json').read_bytes())
                (root/'out/assembly/raw.txt').write_text('tamper')
                with self.assertRaisesRegex(ValueError,'integrity'):diagnostic.run(root/'out')
                (root/'out/assembly/raw.txt').write_text('raw fixture evidence')
                (root/'out/assembly/unexpected.txt').write_text('extra output')
                with self.assertRaisesRegex(ValueError,'inventory changed'):diagnostic.run(root/'out')

    def test_missing_dependency_writes_failed_report(self):
        with scratch_directory() as folder,patch.object(diagnostic.shutil,'which',return_value=None):
            root=Path(folder)
            with self.assertRaisesRegex(FileNotFoundError,'SPAdes unavailable'):diagnostic.run(root/'out')
            self.assertEqual(json.loads((root/'out/manifest.json').read_text())['status'],'failed')
            self.assertTrue((root/'out/report.html').exists())

    def test_timeout_interruption_and_resource_failures_are_not_success(self):
        for error in (TimeoutError('fixture timeout'),KeyboardInterrupt(),ValueError('byte budget'),RuntimeError('exit 7')):
            with self.subTest(error=type(error).__name__),scratch_directory() as folder:
                root=Path(folder)
                with self.assertRaises(type(error)):self.invoke(root,failure=error)
                data=json.loads((root/'out/diagnostic.json').read_text())
                self.assertEqual(data['status'],'interrupted' if isinstance(error,KeyboardInterrupt) else 'failed')
                self.assertNotIn('exact_match_allowing_reverse_complement',data)
                with self.assertRaisesRegex(ValueError,'new output folder'):self.invoke(root)

    def test_empty_and_malformed_contigs_fail(self):
        for contigs in ('','ACGT\n','>fixture\n','>fixture\nNOT_DNA\n','>fixture\nACGT\n'):
            with self.subTest(contigs=contigs),scratch_directory() as folder:
                with self.assertRaises(ValueError):self.invoke(Path(folder),contigs=contigs)

    def test_invalid_generated_input_is_rejected_before_assembly(self):
        original=diagnostic.fixture
        def malformed(directory,paired):
            truth,names=original(directory,paired)
            with gzip.open(directory/names[0],'wt') as f:f.write('@a\nACGT\n+\nI\n')
            return truth,names
        with scratch_directory() as folder,patch.object(diagnostic,'fixture',side_effect=malformed):
            root=Path(folder)
            with self.assertRaisesRegex(ValueError,'lengths'):self.invoke(root)
            self.assertFalse((root/'out/assembly.log').exists())

    def test_changed_layout_or_executable_cannot_reuse(self):
        with scratch_directory() as folder:
            root=Path(folder);self.invoke(root)
            with patch.object(diagnostic.shutil,'which',return_value=str(root/'spades.py')):
                with self.assertRaisesRegex(ValueError,'changed'):diagnostic.run(root/'out',True)
                (root/'spades.py').write_text('updated executable')
                with self.assertRaisesRegex(ValueError,'changed'):diagnostic.run(root/'out')

    def test_top_level_report_integrity_blocks_reuse(self):
        with scratch_directory() as folder:
            root=Path(folder);self.invoke(root)
            (root/'out/diagnostic.json').write_text('{}')
            with patch.object(diagnostic.shutil,'which',return_value=str(root/'spades.py')):
                with self.assertRaisesRegex(ValueError,'integrity'):diagnostic.run(root/'out')
