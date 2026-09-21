import json
import unittest
from pathlib import Path
from test_metadata import scratch_directory
from satellite_discovery.library_review import assess_library, review


class LibraryReviewTests(unittest.TestCase):
    def test_rna_and_dna_supported_sources(self):
        for source, strategy, molecule in [('TRANSCRIPTOMIC','RNA-Seq','RNA'), ('GENOMIC','WGS','DNA'), ('VIRAL RNA','WGS','RNA'), ('METATRANSCRIPTOMIC','RNA-Seq','RNA')]:
            with self.subTest(source=source):
                r = assess_library({'library_source':source,'library_strategy':strategy,'layout':'PAIRED'})
                self.assertEqual(r['assay_molecule'], molecule)
                self.assertEqual(r['metadata_status'], 'supported')
                self.assertFalse(r['automatic_tool_selection'])

    def test_conflict_is_unknown_not_mixed(self):
        r = assess_library({'library_source':'GENOMIC','library_strategy':'RNA-Seq'})
        self.assertEqual(r['assay_molecule'], 'unknown')
        self.assertEqual(r['metadata_status'], 'conflicting')

    def test_wgs_and_helper_name_do_not_prove_dna_or_rna(self):
        r = assess_library({'library_strategy':'WGS','proposed_helper':'rsv-long','library_source':'METAGENOMIC'})
        self.assertEqual(r['assay_molecule'], 'unknown')
        self.assertEqual(r['strand_orientation'], 'unknown')

    def test_targeted_and_single_cell_warnings(self):
        r = assess_library({'library_source':'genomic_single_cell','library_strategy':'AMPLICON','library_selection':'PCR','layout':'other'})
        self.assertIn('targeted_assay_not_whole_sample_representation', r['warnings'])
        self.assertIn('cell_or_barcode_layout_requires_review', r['warnings'])
        self.assertIn('read_layout_unresolved', r['warnings'])

    def test_review_preserves_input_and_reuses_completed_artifacts(self):
        with scratch_directory() as root:
            root = Path(root)
            source = root/'datasets.json'
            source.write_text(json.dumps([{'run_accession':'SRR1','library_source':'TRANSCRIPTOMIC','library_strategy':'RNA-Seq'}]))
            original = source.read_bytes()
            result = review(source, root/'review')
            self.assertEqual(review(source, root/'review'), result)
            self.assertEqual(source.read_bytes(), original)
            (root/'review/report.html').write_text('modified')
            with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
                review(source, root/'review')

    def test_duplicate_ids_and_bad_json_shape_rejected(self):
        with scratch_directory() as root:
            root = Path(root)
            source = root/'datasets.json'
            source.write_text(json.dumps([{'run_accession':'SRR1'},{'run_accession':'SRR1'}]))
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                review(source, root/'review')
            source.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'JSON array'):
                review(source, root/'review')

    def test_empty_dataset_report_is_explicit(self):
        with scratch_directory() as root:
            root = Path(root)
            source = root/'datasets.json'
            source.write_text('[]')
            self.assertEqual(review(source, root/'review')['records'], 0)
