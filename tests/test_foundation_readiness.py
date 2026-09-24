import copy
import errno
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
from urllib.error import URLError

from test_metadata import scratch_directory
from satellite_discovery import acquisition_fallback as fallback
from satellite_discovery import artifact_workflow, dependency_review, reference_snapshot, review_ui, sra_conversion
from satellite_discovery.sequence_downloader import checksum


class FallbackTests(unittest.TestCase):
    def test_transient_primary_uses_only_configured_verified_alternative(self):
        history=[]
        def missing():raise URLError('fixture unavailable')
        result=fallback.run(['primary','local'],{'primary':missing,'local':lambda:'fixture'},
                            lambda artifact:{'verified':True,'sha256':'fixture-hash'},lambda state:history.append(copy.deepcopy(state)))
        self.assertEqual(result,'fixture')
        self.assertEqual(history[-1][0]['failure_class'],'remote_unavailable')
        self.assertEqual(history[-1][1]['status'],'complete')
        self.assertTrue(any(h[-1]['status']=='verifying' for h in history))

    def test_verification_failure_does_not_try_another_backend(self):
        with patch.object(fallback,'classify',wraps=fallback.classify):
            calls=[]
            def invalid(artifact):raise FileNotFoundError('vanished during verification')
            with self.assertRaises(fallback.AcquisitionFailed) as caught:
                fallback.run(['first','second'],{'first':lambda:'bad','second':lambda:calls.append(True)},invalid,lambda s:None)
            self.assertFalse(calls)
            self.assertEqual(caught.exception.attempts[0]['failure_class'],'integrity_failure')

    def test_interruption_is_recorded_and_propagated(self):
        history=[]
        def interrupted():raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):fallback.run(['first'],{'first':interrupted},lambda x:{},lambda s:history.append(copy.deepcopy(s)))
        self.assertEqual(history[-1][0]['status'],'interrupted')

    def test_unknown_configuration_fails_before_any_attempt(self):
        with self.assertRaisesRegex(ValueError,'Unknown'):fallback.run(['unregistered'],{},lambda x:{},lambda s:self.fail('must not record'))

    def test_failure_classes_are_explicit(self):
        for error,expected in [(PermissionError(),'permission_denied'),(OSError(errno.ENOSPC,'full'),'insufficient_disk'),
                               (TimeoutError(),'timeout'),(ValueError(),'invalid_input_or_integrity')]:
            self.assertEqual(fallback.diagnostic(error)['failure_class'],expected)
            self.assertEqual(fallback.diagnostic(error)['automatic_alternative'],'not_configured')


class WorkflowBundleTests(unittest.TestCase):
    def fixture(self,root):
        (root/'data.fa').write_text('>fixture\nACGT\n')
        path=root/'spec.json'
        path.write_text(json.dumps({'schema':'artifact-workflow-v1','stages':[{'id':'inventory','kind':'inventory','inputs':{'fasta':'data.fa'}}]}))
        return path

    def test_bundle_includes_inputs_outputs_configuration_environment_and_reuse(self):
        with scratch_directory() as folder:
            root=Path(folder);spec=self.fixture(root);out=root/'out'
            artifact_workflow.run(spec,out)
            data=json.loads((out/'reproducibility.json').read_text())
            self.assertEqual(data['status'],'complete')
            self.assertEqual(data['configuration']['stages'][0]['id'],'inventory')
            self.assertEqual(data['stages'][0]['inputs']['fasta']['sha256'],checksum(root/'data.fa'))
            self.assertIn('platform',data['environment'])
            self.assertIn('git_revision',data['environment'])
            self.assertIn('manifest.json',data['stages'][0]['records'])
            self.assertEqual(len(data['environment']['source_sha256']),64)
            old=(out/'inventory/manifest.json').read_bytes()
            artifact_workflow.run(spec,out)
            self.assertEqual(old,(out/'inventory/manifest.json').read_bytes())
            self.assertEqual(json.loads((out/'reproducibility.json').read_text())['stages'][0]['execution'],'verified_reuse')

    def test_bundle_failure_does_not_become_empty_success(self):
        with scratch_directory() as folder:
            root=Path(folder);spec=self.fixture(root)
            (root/'data.fa').unlink()
            with self.assertRaises(FileNotFoundError):artifact_workflow.run(spec,root/'out')
            data=json.loads((root/'out/reproducibility.json').read_text())
            self.assertEqual(data['status'],'failed')
            self.assertEqual(data['stages'][0]['status'],'failed')

    def test_preview_resolves_relative_paths_without_running_or_writing(self):
        with scratch_directory() as folder:
            root=Path(folder);spec=self.fixture(root);before=set(root.iterdir())
            with patch.object(artifact_workflow,'dispatch',side_effect=AssertionError('must not run')):
                data=artifact_workflow.inspect_configuration(spec)
            self.assertEqual(before,set(root.iterdir()))
            self.assertEqual(data['stages'][0]['inputs']['fasta']['status'],'available')
            (root/'data.fa').unlink()
            self.assertEqual(artifact_workflow.inspect_configuration(spec)['stages'][0]['inputs']['fasta']['status'],'missing')

    def test_inaccessible_output_does_not_change_input(self):
        with scratch_directory() as folder:
            root=Path(folder);spec=self.fixture(root);before=spec.read_bytes()
            original=Path.mkdir
            def denied(path,*a,**kw):
                if path.name=='out':raise PermissionError('fixture output denied')
                return original(path,*a,**kw)
            with patch.object(Path,'mkdir',denied),self.assertRaises(PermissionError):artifact_workflow.run(spec,root/'out')
            self.assertEqual(before,spec.read_bytes())

    def test_unknown_configuration_fields_are_not_silently_ignored(self):
        with scratch_directory() as folder:
            root=Path(folder);spec=self.fixture(root);data=json.loads(spec.read_text())
            data['stages'][0]['threadz']=8
            spec.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'configuration fields'):artifact_workflow.inspect_configuration(spec)


class SnapshotComparisonTests(unittest.TestCase):
    def make(self,root,name,version,sequence='ACGT',reference_name='fixture.fa'):
        source=root/(name+'.fa');source.write_text('>fixture\n'+sequence+'\n')
        spec=root/(name+'.json')
        spec.write_text(json.dumps({'files':[{'name':reference_name,'path':source.name,'bytes':source.stat().st_size,
                         'sha256':checksum(source),'source':'artificial','version':version,'role':'technical'}]}))
        reference_snapshot.snapshot(spec,root/name)
        return root/name

    def test_added_removed_and_unchanged_references(self):
        with scratch_directory() as folder:
            root=Path(folder);a=self.make(root,'a','1');b=self.make(root,'b','1');c=self.make(root,'c','1',reference_name='other.fa')
            reference_snapshot.compare_snapshots(a,b,root/'same')
            rows=json.loads((root/'same/summary.json').read_text())['tables']['changes']
            self.assertEqual(rows[0]['status'],'unchanged')
            reference_snapshot.compare_snapshots(a,c,root/'different')
            rows=json.loads((root/'different/summary.json').read_text())['tables']['changes']
            self.assertEqual({r['status'] for r in rows},{'added','removed'})

    def test_content_and_version_changes_are_reported_without_replacing_sources(self):
        with scratch_directory() as folder:
            root=Path(folder);a=self.make(root,'a','1');b=self.make(root,'b','2','AAAA')
            before=(a/'fixture.fa').read_bytes()
            reference_snapshot.compare_snapshots(a,b,root/'comparison')
            summary=json.loads((root/'comparison/summary.json').read_text())
            row=summary['tables']['changes'][0]
            self.assertEqual(row['status'],'changed');self.assertIn('version',row['changed_fields'])
            self.assertEqual(before,(a/'fixture.fa').read_bytes())
            reference_snapshot.compare_snapshots(a,b,root/'comparison')

    def test_corrupt_snapshot_blocks_comparison_and_cached_reuse(self):
        with scratch_directory() as folder:
            root=Path(folder);a=self.make(root,'a','1');b=self.make(root,'b','1')
            reference_snapshot.compare_snapshots(a,b,root/'comparison')
            (a/'fixture.fa').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'integrity'):reference_snapshot.compare_snapshots(a,b,root/'comparison')
            state=json.loads((a/'manifest.json').read_text());state['identity']=[]
            (a/'manifest.json').write_text(json.dumps(state))
            with self.assertRaisesRegex(ValueError,'completed reference snapshot'):reference_snapshot.verified_snapshot(a)


class LauncherTests(unittest.TestCase):
    def test_open_report_headless_returns_exact_existing_path(self):
        with scratch_directory() as folder:
            report=Path(folder)/'report.html';report.write_text('<h1>fixture</h1>')
            with patch.object(review_ui.webbrowser,'open',return_value=False) as browser:
                self.assertEqual(review_ui.open_report(report),report.resolve())
                browser.assert_called_once_with(report.resolve().as_uri())

    def test_open_report_refuses_nonhtml_and_missing_files(self):
        with scratch_directory() as folder:
            root=Path(folder);(root/'data.json').write_text('{}')
            with patch.object(review_ui.webbrowser,'open') as browser:
                with self.assertRaises(ValueError):review_ui.open_report(root/'data.json')
                with self.assertRaises(FileNotFoundError):review_ui.open_report(root/'missing.html')
                browser.assert_not_called()


class ConversionFailureTests(unittest.TestCase):
    def fixture(self,root):
        archive=root/'fixture.sra';archive.write_bytes(b'artificial archive')
        tool=root/'tool';tool.write_bytes(b'fixture executable')
        return archive,tool

    def convert(self,root,produce):
        archive,tool=self.fixture(root)
        with patch.object(sra_conversion.shutil,'which',return_value=str(tool)), \
             patch.object(sra_conversion.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'fixture version','')), \
             patch.object(sra_conversion.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(10**10,0,10**10)), \
             patch.object(sra_conversion,'process',side_effect=produce):
            return sra_conversion.convert(archive,root/'out')

    def test_single_end_success_and_scratch_cleanup(self):
        with scratch_directory() as folder:
            root=Path(folder)
            def produce(command,directory,log_name,**kw):
                (directory/'fixture.fastq').write_text('@r\nACGT\n+\nIIII\n')
                (directory/log_name).write_text('fixture')
                (directory/'temporary').mkdir();(directory/'temporary/scratch').write_text('scratch')
            result=self.convert(root,produce)
            self.assertEqual(result['status'],'complete')
            self.assertFalse((root/'out/temporary').exists())
            self.assertTrue((root/'out/fixture.fastq').exists())

    def test_missing_mate_bad_syntax_empty_and_identifiers_never_complete(self):
        cases=[{'fixture_1.fastq':'@r/1\nACGT\n+\nIIII\n'},
               {'fixture.fastq':'@r\nACGT\n+\nI\n'}, {'fixture.fastq':''},
               {'fixture_1.fastq':'@r/1\nACGT\n+\nIIII\n','fixture_2.fastq':'@different/2\nACGT\n+\nIIII\n'}]
        for outputs in cases:
            with self.subTest(outputs=outputs),scratch_directory() as folder:
                root=Path(folder)
                def produce(command,directory,log_name,**kw):
                    for name,data in outputs.items():(directory/name).write_text(data)
                    (directory/log_name).write_text('fixture')
                with self.assertRaises(ValueError):self.convert(root,produce)
                self.assertEqual(json.loads((root/'out/manifest.json').read_text())['status'],'failed')

    def test_retry_cannot_reuse_stale_mate_from_failed_attempt(self):
        with scratch_directory() as folder:
            root=Path(folder)
            def failed(command,directory,log_name,**kw):
                (directory/'fixture_2.fastq').write_text('@r/2\nACGT\n+\nIIII\n')
                (directory/log_name).write_text('failed fixture')
                raise TimeoutError('fixture interruption')
            with self.assertRaises(TimeoutError):self.convert(root,failed)
            def incomplete(command,directory,log_name,**kw):
                (directory/'fixture_1.fastq').write_text('@r/1\nACGT\n+\nIIII\n')
                (directory/log_name).write_text('missing mate')
            with self.assertRaisesRegex(ValueError,'mate is missing'):self.convert(root,incomplete)
            self.assertTrue((root/'out/previous_attempts/1/fixture_2.fastq').exists())

    def test_invalid_executable_and_low_disk_are_explicit(self):
        with scratch_directory() as folder:
            root=Path(folder);archive,tool=self.fixture(root)
            with patch.object(sra_conversion.shutil,'which',return_value=str(tool)),patch.object(sra_conversion.subprocess,'run',side_effect=OSError('Invalid executable')):
                with self.assertRaisesRegex(OSError,'Invalid executable'):sra_conversion.convert(archive,root/'invalid')
            with patch.object(sra_conversion.shutil,'which',return_value=str(tool)),patch.object(sra_conversion.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'fixture','')),patch.object(sra_conversion.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(1000,999,1)),patch.object(sra_conversion,'process') as process:
                with self.assertRaisesRegex(RuntimeError,'free space'):sra_conversion.convert(archive,root/'disk')
                process.assert_not_called()


class OptionalReadinessTests(unittest.TestCase):
    def test_linux_portable_discovery_uses_native_executable_names(self):
        with scratch_directory() as folder:
            root=Path(folder);tool=root/'.tools/blast-test/ncbi-blast-test/bin/blastn'
            tool.parent.mkdir(parents=True);tool.write_bytes(b'fixture')
            with patch.object(dependency_review.sys,'platform','linux'),patch.object(dependency_review.shutil,'which',return_value=None),patch.object(dependency_review.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'fixture version','')):
                row=dependency_review.inspect_tools(root)[0]
            self.assertEqual(row['path'],str(tool.resolve()))
            self.assertEqual(row['status'],'version_check_passed')

    def test_broken_native_import_is_reported_without_hiding_other_tools(self):
        with scratch_directory() as folder:
            with patch.object(dependency_review.shutil,'which',return_value=None),patch.object(dependency_review.importlib.util,'find_spec',return_value=True),patch.object(dependency_review.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','fixture native import failed')):
                rows={r['tool']:r for r in dependency_review.inspect_tools(folder)}
            self.assertEqual(rows['pysam']['status'],'import_check_failed')
            self.assertEqual(rows['matplotlib']['status'],'import_check_failed')
            for name in ('tadpole','spades','prefetch','vdb-validate'):
                self.assertEqual(rows[name]['capability_test'],'not_performed')
