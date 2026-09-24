import copy
import hashlib
import json
from pathlib import Path
import unittest
import subprocess
import zipfile
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery import acquisition_fallback as fallback
from satellite_discovery import artifact_benchmark, artifact_workflow, reference_snapshot
from satellite_discovery.sequence_downloader import checksum
from scripts import test_tadpole_runtime as tadpole


class ArtifactBenchmarkTests(unittest.TestCase):
    def fixture(self, root):
        digest = hashlib.sha256(b'artificial text fixture').hexdigest()
        (root/'datasets.csv').write_text('dataset_id,role,processing_status,reference_version\np,positive,complete,fixture-v1\nn,negative,complete,fixture-v1\nz,negative,complete,fixture-v1\n')
        (root/'expectations.csv').write_text('benchmark_id,artifact_sha256\nfixture,'+digest+'\n')
        (root/'artifacts.csv').write_text('dataset_id,artifact_id,artifact_sha256,classification\np,a,'+digest+',classified\nn,a,'+digest+',unclassified\nn,b,'+digest+',unclassified\n')
        return root/'datasets.csv',root/'expectations.csv',root/'artifacts.csv',root/'out'

    def test_positive_negative_empty_and_recurrence(self):
        with scratch_directory() as folder:
            root=Path(folder); args=self.fixture(root)
            artifact_benchmark.run(*args)
            data=json.loads((root/'out/summary.json').read_text())['tables']
            self.assertEqual([r['exact_digest_observed'] for r in data['comparisons']],[True,True,False])
            self.assertEqual(data['counts'][1]['unclassified'],2)
            self.assertEqual(data['counts'][2]['produced'],0)
            self.assertEqual(data['recurrence'][0]['dataset_count'],2)
            self.assertEqual(data['recurrence'][0]['negative_dataset_count'],1)
            self.assertEqual(data['comparisons'][0]['withheld_identity'],'not_verified')
            first=(root/'out/manifest.json').read_bytes()
            artifact_benchmark.run(*args)
            self.assertEqual(first,(root/'out/manifest.json').read_bytes())
            (root/'out/counts.csv').write_text('corruption')
            with self.assertRaisesRegex(ValueError,'integrity'):artifact_benchmark.run(*args)

    def test_empty_artifact_table_is_explicit_zero(self):
        with scratch_directory() as folder:
            root=Path(folder);args=self.fixture(root)
            args[2].write_text('dataset_id,artifact_id,artifact_sha256,classification\n')
            artifact_benchmark.run(*args)
            rows=json.loads((root/'out/summary.json').read_text())['tables']['counts']
            self.assertTrue(all(r['produced']==0 for r in rows))

    def test_invalid_inputs_fail_without_negative_report(self):
        for file,old,new in [('datasets.csv','complete','failed'),('datasets.csv','positive','invalid'),
                             ('artifacts.csv','p,a,','missing,a,'),('artifacts.csv',',classified',',unknown'),
                             ('expectations.csv','fixture,','fixture,invalid'),('datasets.csv','p,positive','z,positive')]:
            with self.subTest(file=file,new=new),scratch_directory() as folder:
                root=Path(folder);args=self.fixture(root);path=root/file
                path.write_text(path.read_text().replace(old,new))
                with self.assertRaises(ValueError):artifact_benchmark.run(*args)
                self.assertEqual(json.loads((root/'out/manifest.json').read_text())['status'],'failed')
                self.assertFalse((root/'out/report.html').exists())

    def test_duplicate_artifacts_and_missing_inputs(self):
        with scratch_directory() as folder:
            root=Path(folder);args=self.fixture(root)
            args[2].write_text(args[2].read_text().replace('n,b,','n,a,'))
            with self.assertRaisesRegex(ValueError,'duplicate'):artifact_benchmark.run(*args)
            args[0].unlink()
            with self.assertRaises(FileNotFoundError):artifact_benchmark.run(*args)

    def test_workflow_execution_and_verified_reuse(self):
        with scratch_directory() as folder:
            root=Path(folder);self.fixture(root)
            spec=root/'workflow.json'
            spec.write_text(json.dumps({'schema':'artifact-workflow-v1','stages':[{
                'id':'assessment','kind':'artifact_benchmark','inputs':{n:n+'.csv' for n in ('datasets','expectations','artifacts')}}]}))
            artifact_workflow.run(spec,root/'workflow')
            artifact_workflow.run(spec,root/'workflow')
            data=json.loads((root/'workflow/reproducibility.json').read_text())
            self.assertEqual(data['stages'][0]['execution'],'verified_reuse')


class RetryTests(unittest.TestCase):
    def test_bounded_retries_order_history_and_timestamps(self):
        history=[{'method':'old','status':'failed'}]; saved=[]; calls=[]
        def primary():
            calls.append('primary');raise TimeoutError('artificial timeout')
        def alternative():calls.append('alternative');return 'artifact'
        fallback.run(['primary','alternative'],{'primary':primary,'alternative':alternative},
                     lambda a:{'verified':True},lambda a:saved.append(copy.deepcopy(a)),retries=2,history=history)
        self.assertEqual(calls,['primary']*3+['alternative'])
        self.assertEqual(len(history),1)
        self.assertEqual(len(saved[-1]),5)
        self.assertIn('finished_utc',saved[-1][-1])

    def test_integrity_never_retries(self):
        calls=[]
        with self.assertRaises(fallback.AcquisitionFailed):
            fallback.run(['a'],{'a':lambda:calls.append(1)},lambda a:{'verified':False},lambda a:None,retries=2)
        self.assertEqual(calls,[1])

    def test_bad_retry_and_history_rejected(self):
        for kwargs in ({'retries':True},{'retries':-1},{'retries':3},{'history':[None]}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                fallback.run(['a'],{'a':lambda:None},lambda a:None,lambda a:None,**kwargs)


class ReferenceMetadataTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'fixture.fa';source.write_text('>artificial\nACGT\n')
        row={'name':'fixture.fa','path':'fixture.fa','bytes':source.stat().st_size,'sha256':checksum(source),
             'source':'artificial fixture','version':'1','role':'technical','reference_id':'ref-1',
             'display_name':'Artificial','category':'technical','provenance':'generated fixture',
             'update_status':'current','accession':'fixture.1','database_version':'fixture-v1'}
        spec=root/'spec.json';spec.write_text(json.dumps({'snapshot_id':'fixture-snapshot','files':[row]}))
        return spec,row

    def test_metadata_is_preserved_and_change_detected(self):
        with scratch_directory() as folder:
            root=Path(folder);spec,row=self.fixture(root)
            reference_snapshot.snapshot(spec,root/'a')
            rows,_=reference_snapshot.verified_snapshot(root/'a')
            self.assertEqual(rows[0]['snapshot_id'],'fixture-snapshot')
            self.assertEqual(rows[0]['reference_id'],'ref-1')
            row['update_status']='superseded';spec.write_text(json.dumps({'files':[row]}))
            reference_snapshot.snapshot(spec,root/'b')
            reference_snapshot.compare_snapshots(root/'a',root/'b',root/'comparison')
            changed=json.loads((root/'comparison/summary.json').read_text())['tables']['changes'][0]
            self.assertIn('update_status',changed['changed_fields'])

    def test_invalid_metadata_and_duplicate_ids(self):
        for change in ('status','duplicate','snapshot'):
            with self.subTest(change=change),scratch_directory() as folder:
                root=Path(folder);spec,row=self.fixture(root);data=json.loads(spec.read_text())
                if change=='status':data['files'][0]['update_status']='invented'
                elif change=='snapshot':data['snapshot_id']='../escape'
                else:data['files'].append({**row,'name':'second.fa'})
                spec.write_text(json.dumps(data))
                with self.assertRaises(ValueError):reference_snapshot.snapshot(spec,root/'out')


class ArtificialAssemblerTests(unittest.TestCase):
    def test_cached_diagnostic_corruption_is_rejected(self):
        with scratch_directory() as folder:
            root=Path(folder);artifact=root/'fixture.txt';artifact.write_text('fixture')
            identity={'script_sha256':checksum(tadpole.__file__),'paired':False,'archive_sha256':tadpole.ARCHIVE_SHA256,
                      'runner_sha256':checksum(tadpole.PROJECT/'satellite_discovery/bounded_process.py')}
            (root/'test_result.json').write_text(json.dumps({'status':'passed','identity':identity,'sha256':{'fixture.txt':checksum(artifact)}}))
            with patch.object(tadpole.shutil,'which',side_effect=AssertionError('cached result must not rerun Java')):
                self.assertTrue(tadpole.run(root))
            artifact.write_text('changed')
            with self.assertRaisesRegex(ValueError,'integrity'):tadpole.run(root)

    def test_timeout_interruption_and_invalid_output_are_reported(self):
        for failure in (TimeoutError('fixture timeout'),KeyboardInterrupt(),ValueError('stage byte budget'),None):
            with self.subTest(failure=type(failure).__name__),scratch_directory() as folder:
                root=Path(folder);(root/'satellite_discovery').mkdir()
                (root/'satellite_discovery/bounded_process.py').write_text('fixture')
                archive=root/'.tools/BBTools-40.01.zip';archive.parent.mkdir()
                member='BBTools-'+tadpole.COMMIT+'/current/fixture.class'
                with zipfile.ZipFile(archive,'w') as z:z.writestr(member,b'fixture')
                installed=root/'.tools/bbtools-40.01'/member;installed.parent.mkdir(parents=True);installed.write_bytes(b'fixture')
                def process(command,directory,*args,**kwargs):
                    (directory/'assembly.log').write_text('fixture')
                    if failure is not None:raise failure
                    (directory/'contigs.fasta').write_text('')
                with patch.object(tadpole,'PROJECT',root),patch.object(tadpole,'ARCHIVE_SHA256',checksum(archive)), \
                     patch.object(tadpole.shutil,'which',return_value='java'), \
                     patch.object(tadpole.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'fixture','')), \
                     patch.object(tadpole,'bounded_run',side_effect=process):
                    self.assertFalse(tadpole.run(root/'out',paired=True))
                result=json.loads((root/'out/test_result.json').read_text())
                self.assertEqual(result['status'],'interrupted' if isinstance(failure,KeyboardInterrupt) else 'failed')
                self.assertNotIn('exact_match_allowing_reverse_complement',result)

    def test_missing_java_records_failure(self):
        with scratch_directory() as folder,patch.object(tadpole.shutil,'which',return_value=None):
            out=Path(folder)/'out'
            self.assertFalse(tadpole.run(out))
            self.assertEqual(json.loads((out/'test_result.json').read_text())['status'],'failed')
            with self.assertRaisesRegex(ValueError,'new folder'):tadpole.run(out)

    def test_missing_or_corrupt_archive_records_failure(self):
        with scratch_directory() as folder:
            root=Path(folder);(root/'scripts').mkdir();(root/'satellite_discovery').mkdir()
            (root/'satellite_discovery/bounded_process.py').write_text('fixture')
            with patch.object(tadpole,'PROJECT',root),patch.object(tadpole.shutil,'which',return_value='java'):
                self.assertFalse(tadpole.run(root/'out'))
                self.assertIn('archive',json.loads((root/'out/test_result.json').read_text())['error'])
