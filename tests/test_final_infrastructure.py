import gzip
from pathlib import Path
import unittest
from unittest.mock import patch
from test_metadata import scratch_directory
from test_review_infrastructure import write_csv
from satellite_discovery import blast_import, coverage_review, contamination_review

class FinalInfrastructureTests(unittest.TestCase):
    def test_gzip_sam_equivalent_and_corruption_rejected(self):
        with scratch_directory() as root:
            root=Path(root)
            data=b'@SQ\tSN:r\tLN:10\nq\t0\tr\t2\t60\t3M\t*\t0\t0\tACG\tIII\n'
            plain=root/'reads.sam'; compressed=root/'reads.dat'
            plain.write_bytes(data); compressed.write_bytes(gzip.compress(data))
            self.assertEqual(coverage_review.read_sam(plain),coverage_review.read_sam(compressed))
            compressed.write_bytes(gzip.compress(data)[:-6])
            with self.assertRaisesRegex(ValueError,'Invalid or truncated'):
                coverage_review.read_sam(compressed)
            plain.write_bytes(b'BAM\x01\x00')
            with self.assertRaises(ValueError):
                coverage_review.read_sam(plain)

    def test_sam_line_limit(self):
        with scratch_directory() as root:
            path=Path(root)/'long.sam'
            path.write_bytes(b'@CO\t'+b'a'*1_000_001)
            with self.assertRaises(ValueError): coverage_review.read_sam(path)

    def fixtures(self,root):
        write_csv(root/'features.csv',[{'feature_id':'q','length':10}])
        write_csv(root/'refs.csv',[{'reference_id':'r','reference_role':'vector','reference_source':'artificial','reference_version':'1'}])
        (root/'hits.tsv').write_text('q\tr\t100\t5\t0\t0\t8\t4\t1\t5\t1e-5\t20\n')

    def test_blast_reverse_import_contamination_roundtrip_reuse(self):
        with scratch_directory() as root:
            root=Path(root); self.fixtures(root)
            args=(root/'features.csv',root/'refs.csv',root/'hits.tsv',root/'import')
            result=blast_import.run(*args)
            from satellite_discovery.review_stage import table
            hits=table(root/'import/matches.csv',('feature_id','reference_id'))
            self.assertEqual((hits[0]['query_start'],hits[0]['query_end']),('3','8'))
            self.assertEqual(hits[0]['query_orientation'],'reverse')
            _, evidence=contamination_review.summarize([{'feature_id':'q','length':'10'}],hits,[])
            self.assertEqual(evidence[0]['union_query_coverage'],.5)
            with patch('satellite_discovery.blast_import.normalize_hits',side_effect=AssertionError('must reuse')):
                self.assertEqual(blast_import.run(*args),result)

    def test_blast_empty_preserves_schema_and_unknown_status(self):
        with scratch_directory() as root:
            root=Path(root); self.fixtures(root); (root/'hits.tsv').write_text('')
            blast_import.run(root/'features.csv',root/'refs.csv',root/'hits.tsv',root/'import')
            from satellite_discovery.review_stage import table
            self.assertEqual(table(root/'import/matches.csv',('query_start','reference_source')),[])
            self.assertEqual(table(root/'import/features.csv',('reported_hit_status',))[0]['reported_hit_status'],'no_reported_hit')

    def test_blast_rejects_bad_ids_numeric_and_coordinates(self):
        features=[{'feature_id':'q','length':'10'}]
        refs=[{'reference_id':'r','reference_role':'vector','reference_source':'artificial','reference_version':'1'}]
        base=['q','r','100','5','0','0','1','5','1','5','0','20']
        with scratch_directory() as root:
            path=Path(root)/'hits.tsv'
            for index,value in [(0,'other'),(1,'other'),(2,'nan'),(10,'inf'),(11,'-1'),(6,'0'),(7,'11'),(3,'0')]:
                row=base.copy(); row[index]=value; path.write_text('\t'.join(row)+'\n')
                with self.subTest(index=index,value=value), self.assertRaises(ValueError):
                    blast_import.normalize_hits(path,features,refs)

class DependencyReviewTests(unittest.TestCase):
    def test_version_success_failure_missing_and_report(self):
        from satellite_discovery import dependency_review
        import subprocess
        with scratch_directory() as root:
            root=Path(root); binary=root/'fake.exe'; binary.write_bytes(b'artificial')
            completed=subprocess.CompletedProcess([],0,'fixture version 1','')
            with patch.object(dependency_review.shutil,'which',return_value=str(binary)), patch.object(dependency_review.subprocess,'run',return_value=completed):
                rows=dependency_review.inspect_tools(root)
                self.assertEqual(rows[0]['status'],'version_check_passed')
                self.assertEqual(len(rows[0]['sha256']),64)
                self.assertTrue(dependency_review.run(root,root/'report').is_file())
                with self.assertRaises(FileExistsError): dependency_review.run(root,root/'report')
            with patch.object(dependency_review.shutil,'which',return_value=str(binary)), patch.object(dependency_review.subprocess,'run',side_effect=subprocess.TimeoutExpired('fixture',15)):
                self.assertEqual(dependency_review.inspect_tools(root)[0]['status'],'version_check_failed')
            with patch.object(dependency_review.shutil,'which',return_value=None):
                self.assertEqual(dependency_review.inspect_tools(root)[0]['status'],'not_found')

class DescriptiveVisualTests(unittest.TestCase):
    def test_heatmap_keeps_unassessed_distinct_from_zero_and_escapes_labels(self):
        from satellite_discovery.observation_report import summarize, render_heatmap
        samples=[{'sample_id':str(i),'study_id':'<study>'+str(i),'library_molecule':'RNA','sample_type':'biological','condition':'negative'} for i in range(200)]
        observations=[{'sample_id':'0','feature_id':'<feature>','detection':'absent'}]
        summary=summarize(samples,observations)
        self.assertEqual(len(summary['comparisons']),200)
        self.assertEqual(sum(r['unknown'] for r in summary['comparisons']),199)
        rendered=render_heatmap(summary['comparisons'])
        self.assertIn('0/1 (0.0%)',rendered)
        self.assertIn('not assessed',rendered)
        self.assertIn('&lt;feature&gt;',rendered)
        self.assertNotIn('<study>',rendered)

    def test_coverage_graph_labels_are_escaped(self):
        from satellite_discovery.review_stage import report
        with scratch_directory() as root:
            root=Path(root)
            report(root,'Coverage',{'coverage':[{'sample_id':'<a>','reference_id':'r','breadth_fraction':.5}]},[])
            html=(root/'report.html').read_text()
            self.assertIn('50.0%',html)
            self.assertIn('&lt;a&gt;',html)
            self.assertIn('<meter',html)
