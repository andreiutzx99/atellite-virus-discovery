from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from test_metadata import scratch_directory
from satellite_discovery import coverage_review, contamination_review, catalogue_linker, review_stage, review_ui
from satellite_discovery.sequence_catalogue import run as inventory
from satellite_discovery.observation_report import run as observations


def write_csv(path, rows, columns=None):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class CoverageTests(unittest.TestCase):
    def test_overlap_blocks_and_uncovered_reference_tail(self):
        rows = coverage_review.calculate([{'reference_id':'r','length':'10'}], [{'sample_id':'a'},{'sample_id':'b'}],
            [{'sample_id':'a','reference_id':'r','alignment_id':aid,'start':str(start),'end':str(end)} for aid,start,end in [('one',0,3),('one',2,5),('two',3,8)]])
        a,b = rows
        self.assertEqual(a['alignment_count'],2)
        self.assertEqual(a['covered_bases'],8)
        self.assertEqual(a['mean_block_depth'],1)
        self.assertEqual(a['maximum_block_depth'],2)
        self.assertAlmostEqual(a['depth_standard_deviation'], .4 ** .5)
        self.assertEqual(b['mean_block_depth'],0)

    def test_gapped_alignment_does_not_cover_gap(self):
        row = coverage_review.calculate([{'reference_id':'r','length':'10'}], [{'sample_id':'a'}],
            [{'sample_id':'a','reference_id':'r','alignment_id':'one','start':str(a),'end':str(b)} for a,b in [(0,2),(8,10)]])[0]
        self.assertEqual(row['covered_bases'],4)
        self.assertEqual(row['mean_block_depth'],.4)

    def test_invalid_coordinates_unknown_samples_and_duplicate_references(self):
        for start,end,sample in [(-1,2,'a'),(1,1,'a'),(0,11,'a'),(0,2,'unknown')]:
            with self.subTest(start=start,end=end,sample=sample), self.assertRaises(ValueError):
                coverage_review.calculate([{'reference_id':'r','length':'10'}],[{'sample_id':'a'}],
                    [{'sample_id':sample,'reference_id':'r','alignment_id':'x','start':str(start),'end':str(end)}])
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            coverage_review.calculate([{'reference_id':'r','length':'10'}]*2,[{'sample_id':'a'}],[])

    def test_report_and_verified_reuse(self):
        with scratch_directory() as root:
            root=Path(root)
            write_csv(root/'refs.csv',[{'reference_id':'r','length':'10'}])
            write_csv(root/'samples.csv',[{'sample_id':'a'}])
            write_csv(root/'blocks.csv',[],['sample_id','reference_id','alignment_id','start','end'])
            result=coverage_review.run(root/'refs.csv',root/'samples.csv',root/'blocks.csv',root/'output')
            with patch('satellite_discovery.coverage_review.calculate',side_effect=AssertionError('must reuse')):
                self.assertEqual(coverage_review.run(root/'refs.csv',root/'samples.csv',root/'blocks.csv',root/'output'),result)


class ContaminationTests(unittest.TestCase):
    def match(self, start, end, identity='99'):
        return {'feature_id':'f','reference_id':'v','reference_role':'vector','query_start':str(start),'query_end':str(end),'percent_identity':identity,'reference_source':'fixture','reference_version':'v1'}

    def test_union_coverage_and_controls_are_evidence_not_rejection(self):
        rows,evidence=contamination_review.summarize([{'feature_id':'f','length':'10'}],[self.match(0,5),self.match(3,8)],
            [{'sample_id':'blank','feature_id':'f','detection':'present'}])
        self.assertEqual(evidence[0]['union_query_coverage'],.8)
        self.assertEqual(rows[0]['technical_controls_present'],1)
        self.assertIsNone(rows[0]['contamination_probability'])
        self.assertEqual(rows[0]['review_status'],'evidence_requires_review')

    def test_no_matches_or_controls_does_not_mean_clean(self):
        rows,_=contamination_review.summarize([{'feature_id':'f','length':'10'}],[],[])
        self.assertEqual(rows[0]['review_status'],'insufficient_evidence')
        self.assertEqual(rows[0]['technical_controls_supplied'],0)

    def test_invalid_numbers_and_duplicate_control_rejected(self):
        for identity in ['nan','inf','101','-1']:
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                contamination_review.summarize([{'feature_id':'f','length':'10'}],[self.match(0,5,identity)],[])
        with self.assertRaises(ValueError):
            contamination_review.summarize([{'feature_id':'f','length':'10'}],[],[{'sample_id':'b','feature_id':'f','detection':'unknown'}]*2)


class SAMCoverageTests(unittest.TestCase):
    def test_cigar_gaps_clipping_insertions_and_excluded_records(self):
        with scratch_directory() as root:
            root=Path(root); sam=root/'example.sam'
            sam.write_text('@SQ\tSN:r\tLN:20\n'
                'read\t0\tr\t2\t255\t2S3M1I2M2D1M3N2M1H\t*\t0\t0\tAACGTACGTAA\tIIIIIIIIIII\n'
                'secondary\t256\tr\t1\t60\t5M\t*\t0\t0\tAAAAA\tIIIII\n'
                'duplicate\t1024\tr\t1\t60\t5M\t*\t0\t0\tAAAAA\tIIIII\n')
            refs,blocks,skipped=coverage_review.read_sam(sam)
            self.assertEqual([(int(b['start']),int(b['end'])) for b in blocks],[(1,4),(4,6),(8,9),(12,14)])
            self.assertEqual(skipped,{'secondary':1,'duplicate':1})
            result=coverage_review.run_sam(sam,root/'report')
            self.assertEqual(result['status'],'complete')
            row=json.loads((root/'report/summary.json').read_text())['tables']['coverage'][0]
            self.assertEqual(row['covered_bases'],8)

    def test_invalid_cigar_length_coordinates_and_missing_references(self):
        cases=[('@SQ\tSN:r\tLN:10\n','2M1S2M','AAAAA',1),
               ('@SQ\tSN:r\tLN:10\n','5M','AAAA',1),
               ('@SQ\tSN:r\tLN:10\n','5M','AAAAA',8),
               ('','5M','AAAAA',1)]
        for header,cigar,sequence,position in cases:
            with self.subTest(cigar=cigar,sequence=sequence,position=position),scratch_directory() as root:
                path=Path(root)/'bad.sam'
                path.write_text(header+f'read\t0\tr\t{position}\t60\t{cigar}\t*\t0\t0\t{sequence}\t*\n')
                with self.assertRaises(ValueError): coverage_review.read_sam(path)


class LifecycleTests(unittest.TestCase):
    def test_failure_recovery_hash_tampering_and_path_traversal(self):
        with scratch_directory() as root:
            root=Path(root)
            source=root/'input.txt'; source.write_text('fixture')
            def produce(paths,out):
                (out/'result.txt').write_text('complete')
                return ['result.txt']
            with self.assertRaises(OSError):
                review_stage.execute('test',{'source':source},root/'out',__file__,lambda p,o: (_ for _ in ()).throw(OSError('disk full')))
            self.assertFalse((root/'out/.review.lock').exists())
            result=review_stage.execute('test',{'source':source},root/'out',__file__,produce)
            self.assertEqual(result['status'],'complete')
            manifest=root/'out/manifest.json'
            data=json.loads(manifest.read_text()); data['output_sha256']={'../input.txt':'bad'}
            manifest.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'output paths'):
                review_stage.execute('test',{'source':source},root/'out',__file__,produce)

    def test_changed_input_during_production_is_not_complete(self):
        with scratch_directory() as root:
            root=Path(root); source=root/'input'; source.write_text('before')
            def produce(paths,out):
                source.write_text('after'); (out/'result').write_text('output'); return ['result']
            with self.assertRaisesRegex(ValueError,'Input changed'):
                review_stage.execute('test',{'source':source},root/'out',__file__,produce)
            self.assertEqual(json.loads((root/'out/manifest.json').read_text())['status'],'failed')

    def test_table_limit(self):
        with scratch_directory() as root:
            path=Path(root)/'rows.csv'; write_csv(path,[{'id':'one'},{'id':'two'}])
            with self.assertRaisesRegex(ValueError,'oversized'):
                review_stage.table(path,('id',),limit=1)


class CatalogueLinkTests(unittest.TestCase):
    def fixture(self, root, same_sample=False):
        root=Path(root)
        imports=[]
        for i,sequence in enumerate(['ACGT','ACGT']):
            fasta=root/f'input{i}.fa'; fasta.write_text(f'>id{i}\n{sequence}\n')
            output=root/f'inventory{i}'; inventory(fasta,output)
            imports.append({'catalogue_dir':str(output),'sample_id':'a' if same_sample else str(i),
                            'study_id':'study','condition':'unknown','sample_type':'biological','library_molecule':'unknown'})
        path=root/'imports.csv'; write_csv(path,imports)
        return path,imports

    def test_link_roundtrip_to_existing_observation_module_and_resume(self):
        with scratch_directory() as root:
            root=Path(root); source,_=self.fixture(root)
            result=catalogue_linker.run(source,root/'linked')
            with closing(sqlite3.connect(root/'linked/linked.sqlite')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM sequences').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],2)
            self.assertEqual(catalogue_linker.run(source,root/'linked'),result)
            self.assertEqual(observations(root/'linked/samples.csv',root/'linked/observations.csv',root/'report')['status'],'complete')

    def test_same_sample_counted_once(self):
        with scratch_directory() as root:
            root=Path(root); source,_=self.fixture(root,same_sample=True)
            catalogue_linker.run(source,root/'linked')
            row=json.loads((root/'linked/summary.json').read_text())['tables']['recurrence'][0]
            self.assertEqual(row['present_biological_samples'],1)

    def test_conflicting_sample_metadata_and_copied_exports_rejected(self):
        with scratch_directory() as root:
            root=Path(root); source,rows=self.fixture(root,same_sample=True)
            rows[1]['library_molecule']='DNA'; write_csv(source,rows)
            with self.assertRaisesRegex(ValueError,'Conflicting metadata'):
                catalogue_linker.run(source,root/'linked')
        with scratch_directory() as root:
            root=Path(root); source,rows=self.fixture(root)
            import shutil
            shutil.copytree(root/'inventory0',root/'copied')
            rows[1]['catalogue_dir']=str(root/'copied'); write_csv(source,rows)
            with self.assertRaisesRegex(ValueError,'Identical input bytes'):
                catalogue_linker.run(source,root/'linked')

    def test_corrupted_catalogue_rejected(self):
        with scratch_directory() as root:
            root=Path(root); source,_=self.fixture(root)
            (root/'inventory0/catalogue.sqlite').write_bytes(b'broken')
            with self.assertRaisesRegex(ValueError,'integrity failure'):
                catalogue_linker.run(source,root/'linked')
            (root/'inventory0/manifest.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'manifest must be an object'):
                catalogue_linker.run(source,root/'linked')

    def test_interrupted_link_report_rebuilds_without_duplicate_rows(self):
        with scratch_directory() as root:
            root=Path(root); source,_=self.fixture(root)
            with patch('satellite_discovery.catalogue_linker.report',side_effect=OSError('out of space')):
                with self.assertRaises(OSError): catalogue_linker.run(source,root/'linked')
            self.assertEqual(catalogue_linker.run(source,root/'linked')['status'],'complete')
            with closing(sqlite3.connect(root/'linked/linked.sqlite')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM provenance').fetchone()[0],2)


class LauncherTests(unittest.TestCase):
    def test_dashboard_escapes_manifest_status_and_refuses_overwrite(self):
        with scratch_directory() as root:
            root=Path(root); stage=root/'stage'; stage.mkdir()
            (stage/'manifest.json').write_text(json.dumps({'status':'<script>alert(1)</script>'}))
            (stage/'report.html').write_text('test')
            report=review_ui.dashboard(root,root/'dashboard.html')
            self.assertNotIn('<script>',report.read_text())
            self.assertIn('does not verify artifact hashes',report.read_text())
            with self.assertRaises(ValueError):
                review_ui.dashboard(root,report)

    def test_unknown_menu_choice_does_not_execute(self):
        with self.assertRaises(ValueError):
            review_ui.launch('99')
