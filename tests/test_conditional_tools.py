import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import tarfile
import unittest
from unittest.mock import patch
from test_metadata import scratch_directory
from test_review_infrastructure import write_csv
from satellite_discovery import alignment_adapter,artifact_workflow,context_review,local_comparison,portable_setup,reference_snapshot,sequence_quality

class ContextTests(unittest.TestCase):
    def test_quantitative_strata_missing_constant_and_nonfinite(self):
        rows=[{'sample_id':str(i),'feature_id':'f','study_id':'s','assay':'a','x_unit':'u','y_unit':'v','x':str(i),'y':str(i*2)} for i in range(4)]
        result=context_review.correlate(rows)[0]
        self.assertAlmostEqual(result['pearson_r'],1)
        rows[0]['x']='unknown'
        self.assertEqual(context_review.correlate(rows)[0]['missing_pairs'],1)
        for r in rows:r['y']='2'
        self.assertEqual(context_review.correlate(rows)[0]['status'],'constant_measurement')
        rows[0]['x']='NaN'
        with self.assertRaises(ValueError):context_review.correlate(rows)
    def test_unknown_context_does_not_become_absence(self):
        sample={'sample_id':'s','study_id':'unknown','laboratory':'unknown','country':'unknown','lane':'unknown','control_status':'unknown','library_molecule':'RNA','strand':'unknown'}
        result=context_review.context([sample,{**sample,'sample_id':'t'}],[{'sample_id':'s','feature_id':'f','detection':'present'}])[0]
        self.assertEqual((result['present'],result['absent'],result['unknown']),(1,0,1))
    def test_control_labels_require_sources(self):
        with scratch_directory() as root:
            root=Path(root)
            write_csv(root/'s.csv',[dict(sample_id='s',study_id='x',laboratory='unknown',country='unknown',lane='unknown',control_status='negative',control_source='unknown',library_molecule='RNA',strand='unknown')])
            write_csv(root/'o.csv',[dict(sample_id='s',feature_id='f',detection='absent')])
            with self.assertRaisesRegex(ValueError,'evidence source'):context_review.run_context(root/'s.csv',root/'o.csv',root/'out')
    def test_repeat_descriptors_do_not_reject(self):
        a,b=sequence_quality.measures([('a','a','AAAAAA'),('b','b','NN')])
        self.assertEqual(a['longest_identical_symbol_run'],6)
        self.assertEqual(a['most_frequent_dinucleotide_fraction'],1)
        self.assertIsNone(b['most_frequent_dinucleotide_fraction'])
        self.assertEqual(a['rejection_status'],'not_assessed')

class SnapshotTests(unittest.TestCase):
    def fixture(self,root):
        (root/'input.fa').write_bytes(b'>fixture\nACGT\n')
        return {'files':[dict(name='fixture.fa',path='input.fa',sha256=hashlib.sha256((root/'input.fa').read_bytes()).hexdigest(),bytes=(root/'input.fa').stat().st_size,source='artificial',version='1',role='technical')]}
    def test_local_verified_reuse_and_corruption(self):
        with scratch_directory() as root:
            root=Path(root);spec=self.fixture(root);(root/'spec.json').write_text(json.dumps(spec))
            reference_snapshot.snapshot(root/'spec.json',root/'out')
            with patch.object(reference_snapshot.shutil,'copyfile',side_effect=AssertionError('must reuse')):reference_snapshot.snapshot(root/'spec.json',root/'out')
            (root/'out/fixture.fa').write_text('changed')
            with self.assertRaisesRegex(ValueError,'integrity'):reference_snapshot.snapshot(root/'spec.json',root/'out')
    def test_reserved_path_and_checksum_rejected(self):
        with scratch_directory() as root:
            root=Path(root)
            for index,name in enumerate(['../file.fa','references.csv','manifest.json','summary.json']):
                spec=self.fixture(root);spec['files'][0]['name']=name;(root/'spec.json').write_text(json.dumps(spec))
                with self.assertRaises(ValueError):reference_snapshot.snapshot(root/'spec.json',root/str(index))
            spec=self.fixture(root);spec['files'][0]['sha256']='0'*64;(root/'spec.json').write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError,'checksum'):reference_snapshot.snapshot(root/'spec.json',root/'bad')
    def test_offline_url_explicitly_blocked(self):
        with scratch_directory() as root:
            root=Path(root);spec=self.fixture(root);del spec['files'][0]['path'];spec['files'][0]['url']='https://example.org/fixture.fa';(root/'spec.json').write_text(json.dumps(spec))
            with self.assertRaisesRegex(RuntimeError,'offline'):reference_snapshot.snapshot(root/'spec.json',root/'out',offline=True)

class WorkflowTests(unittest.TestCase):
    def fixture(self,root):
        (root/'input.fa').write_text('>fixture\nACGTACGT\n')
        spec={'schema':'artifact-workflow-v1','stages':[{'id':'inventory','kind':'inventory','inputs':{'fasta':'input.fa'}},{'id':'quality','kind':'sequence_quality','inputs':{'fasta':{'stage':'inventory','artifact':'sequences.fasta'}}}]}
        (root/'workflow.json').write_text(json.dumps(spec));return spec
    def test_resume_and_changed_source_or_output_rejected(self):
        with scratch_directory() as root:
            root=Path(root);self.fixture(root);artifact_workflow.run(root/'workflow.json',root/'out')
            with patch('satellite_discovery.sequence_quality.measures',side_effect=AssertionError('must reuse')):artifact_workflow.run(root/'workflow.json',root/'out')
            (root/'out/inventory/sequences.fasta').write_text('changed')
            with self.assertRaises(ValueError):artifact_workflow.run(root/'workflow.json',root/'out')
    def test_failure_recovery_preserves_completed_stage(self):
        with scratch_directory() as root:
            root=Path(root);self.fixture(root)
            with patch('satellite_discovery.sequence_quality.measures',side_effect=RuntimeError('injected')):
                with self.assertRaises(RuntimeError):artifact_workflow.run(root/'workflow.json',root/'out')
            first=(root/'out/inventory/manifest.json').read_bytes()
            artifact_workflow.run(root/'workflow.json',root/'out')
            self.assertEqual(first,(root/'out/inventory/manifest.json').read_bytes())
    def test_unsupported_step_and_forward_reference_fail_before_execution(self):
        with scratch_directory() as root:
            root=Path(root);spec=self.fixture(root)
            spec['stages'][0]['kind']='shell'
            with self.assertRaises(ValueError):artifact_workflow.validate(spec)
            spec=self.fixture(root);spec['stages'][0]['inputs']['fasta']={'stage':'quality','artifact':'output.fa'}
            with self.assertRaises(ValueError):artifact_workflow.validate(spec)

class AdapterTests(unittest.TestCase):
    def test_missing_binary_dependencies_are_actionable(self):
        with patch.object(alignment_adapter.importlib.util,'find_spec',return_value=None),patch.object(alignment_adapter.shutil,'which',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'pysam or samtools'):alignment_adapter.backend()
    def test_cram_requires_reference_before_subprocess(self):
        with scratch_directory() as root:
            root=Path(root);(root/'x.cram').write_bytes(b'CRAM')
            with patch.object(alignment_adapter.subprocess,'Popen',side_effect=AssertionError('must not execute')):
                with self.assertRaisesRegex(ValueError,'reference'):alignment_adapter.decode(root/'x.cram',root/'decoded.sam',{'name':'samtools','path':'unused'})
    def test_blast_role_mismatch_fails_before_search(self):
        with scratch_directory() as root:
            root=Path(root);(root/'q.fa').write_text('>q\nACGT\n');(root/'r.fa').write_text('>r\nACGT\n')
            write_csv(root/'roles.csv',[dict(reference_id='other',reference_role='vector',reference_source='fixture',reference_version='1')])
            with patch.object(local_comparison,'tools',return_value={'fixture':'1'}),patch.object(local_comparison.subprocess,'run',side_effect=AssertionError('no search')):
                with self.assertRaisesRegex(ValueError,'Every supplied reference'):local_comparison.compare(root/'q.fa',root/'r.fa',root/'roles.csv',root/'out')
    def test_portable_archive_checksum_and_traversal_rejected(self):
        with scratch_directory() as root:
            root=Path(root);archive=root/portable_setup.ARCHIVE
            archive.write_bytes(b'bad')
            with patch.object(portable_setup,'WINDOWS',True):
                with self.assertRaisesRegex(ValueError,'checksum'):portable_setup.install(root,offline=True)
            with tarfile.open(archive,'w:gz') as tar:
                member=tarfile.TarInfo('../escape');member.size=1;tar.addfile(member,io.BytesIO(b'x'))
            with patch.object(portable_setup,'WINDOWS',True),patch.object(portable_setup,'SHA256',hashlib.sha256(archive.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(ValueError,'Unsafe'):portable_setup.install(root,offline=True)

@unittest.skipUnless(os.environ.get('RUN_OPTIONAL_TOOL_TESTS')=='1','Optional live-tool job')
class OptionalToolTests(unittest.TestCase):
    def fixture(self,root):
        sequence='ACGT'*25
        (root/'reference.fa').write_text('>r\n'+sequence+'\n')
        (root/'reads.sam').write_text('@HD\tVN:1.6\n@SQ\tSN:r\tLN:100\nq\t0\tr\t1\t60\t4M\t*\t0\t0\tACGT\tIIII\n')
        return root/'reference.fa'
    def test_real_pysam_and_samtools_bam_cram_equivalence(self):
        import pysam
        with scratch_directory() as root:
            root=Path(root);ref=self.fixture(root);pysam.faidx(str(ref))
            expected=alignment_adapter.read_sam(root/'reads.sam')
            for extension,mode in [('bam','wb'),('cram','wc')]:
                path=root/('reads.'+extension)
                with pysam.AlignmentFile(str(root/'reads.sam'),'r') as src,pysam.AlignmentFile(str(path),mode,template=src,reference_filename=str(ref)) as dest:
                    for record in src:dest.write(record)
                for decoder in [{'name':'pysam'}, {'name':'samtools','path':shutil.which('samtools')}]:
                    destination=root/(extension+'-'+decoder['name']+'.sam')
                    alignment_adapter.decode(path,destination,decoder,ref if extension=='cram' else None)
                    actual=alignment_adapter.read_sam(destination)
                    # Decoder headers can add lines; compare coverage rather than line-based IDs.
                    self.assertEqual(alignment_adapter.calculate(actual[0],[{'sample_id':'sam_sample'}],actual[1]),alignment_adapter.calculate(expected[0],[{'sample_id':'sam_sample'}],expected[1]))
                alignment_adapter.run(path,root/('report-'+extension),ref if extension=='cram' else None)
    def test_real_matplotlib_scatter_export(self):
        with scratch_directory() as root:
            root=Path(root)
            write_csv(root/'m.csv',[dict(sample_id=str(i),feature_id='f',study_id='s',assay='a',x_unit='u',y_unit='v',x=i,y=i*2) for i in range(4)])
            context_review.run_quantitative(root/'m.csv',root/'out')
            self.assertTrue((root/'out/scatter-0.svg').is_file())
            self.assertIn('Axes scaled explicitly',(root/'out/report.html').read_text())
    def test_real_blast_matching_unrelated_and_verified_resume(self):
        with scratch_directory() as root:
            root=Path(root);rng=random.Random(44)
            ref=''.join(rng.choice('ACGT') for _ in range(800));other=''.join(rng.choice('ACGT') for _ in range(400))
            (root/'ref.fa').write_text('>fixture_ref\n'+ref+'\n');(root/'query.fa').write_text('>match\n'+ref[100:500]+'\n>unrelated\n'+other+'\n')
            write_csv(root/'roles.csv',[dict(reference_id='fixture_ref',reference_role='vector',reference_source='artificial fixture',reference_version='1')])
            local_comparison.compare(root/'query.fa',root/'ref.fa',root/'roles.csv',root/'out')
            with (root/'out/hit_status.csv').open(encoding='utf-8-sig') as f:status={r['feature_id']:r['reported_hit_status'] for r in csv.DictReader(f)}
            self.assertEqual(status,{'match':'reported_match','unrelated':'no_reported_hit'})
            with patch.object(local_comparison.subprocess,'run',wraps=subprocess.run) as calls:
                local_comparison.compare(root/'query.fa',root/'ref.fa',root/'roles.csv',root/'out')
                self.assertEqual(calls.call_count,2) # executable version checks only

class ConversionTests(unittest.TestCase):
    def test_conditional_sra_conversion_compression_validation_and_reuse(self):
        from satellite_discovery import sra_conversion
        with scratch_directory() as root:
            root=Path(root);(root/'fixture.sra').write_bytes(b'not a biological archive');(root/'tool').write_bytes(b'fake executable')
            def fake_process(command,directory,log_name,**kwargs):
                (directory/'fixture_1.fastq').write_text('@r/1\nACGT\n+\nIIII\n')
                (directory/'fixture_2.fastq').write_text('@r/2\nACGT\n+\nIIII\n')
                (directory/log_name).write_text('fixture')
            with patch.object(sra_conversion.shutil,'which',return_value=str(root/'tool')),patch.object(sra_conversion.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'fixture 1','')),patch.object(sra_conversion.shutil,'disk_usage',return_value=shutil._ntuple_diskusage(10**10,0,10**10)),patch.object(sra_conversion,'process',side_effect=fake_process) as process:
                result=sra_conversion.convert(root/'fixture.sra',root/'out')
                self.assertEqual(result['status'],'complete')
                self.assertTrue((root/'out/fixture_1.fastq.gz').exists())
                sra_conversion.convert(root/'fixture.sra',root/'out')
                self.assertEqual(process.call_count,1)
    def test_missing_tool_is_explicit(self):
        from satellite_discovery import sra_conversion
        with scratch_directory() as root:
            path=Path(root)/'fixture.sra';path.write_bytes(b'fixture')
            with patch.object(sra_conversion.shutil,'which',return_value=None):
                with self.assertRaisesRegex(RuntimeError,'fasterq-dump'):sra_conversion.convert(path,Path(root)/'out')

class BoundedProcessTests(unittest.TestCase):
    def test_failure_and_output_limit(self):
        from satellite_discovery.bounded_process import run
        import sys
        with scratch_directory() as root:
            root=Path(root)
            with self.assertRaisesRegex(RuntimeError,'failed'):run([sys.executable,'-c','raise SystemExit(2)'],root,'failed.log')
            with self.assertRaisesRegex(ValueError,'byte budget'):run([sys.executable,'-c','print("x"*1000)'],root,'large.log',max_bytes=100)

class PairFlagTests(unittest.TestCase):
    def test_descriptive_flags_exclude_duplicates_and_do_not_claim_pairs(self):
        with scratch_directory() as root:
            root=Path(root);path=root/'input.sam'
            path.write_text('@SQ\tSN:r\tLN:10\na\t67\tr\t1\t60\t4M\t*\t0\t0\tACGT\tIIII\nb\t1155\tr\t1\t60\t4M\t*\t0\t0\tACGT\tIIII\n')
            alignment_adapter.run(path,root/'report')
            with (root/'report/alignment_flags.csv').open(encoding='utf-8-sig') as source:counts={r['metric']:int(r['records']) for r in csv.DictReader(source)}
            self.assertEqual(counts['accepted_primary_records'],1)
            self.assertEqual(counts['proper_pair_flag_records'],1)
            self.assertEqual(counts['second_mate_flag_records'],0)
