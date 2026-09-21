import unittest
import json
from pathlib import Path
from test_metadata import scratch_directory
from unittest.mock import patch
from satellite_discovery.model_scope import MODELS, evaluate, enforce, search_terms, mapping_scope
from satellite_discovery.workflow import discover


class ScopeTests(unittest.TestCase):
    def test_mapping_is_bound_to_source_metadata_and_reference_model(self):
        with scratch_directory() as root:
            root = Path(root)
            qc = root / 'phase3/SRR123/qc'
            qc.mkdir(parents=True)
            (root / 'datasets.json').write_text(json.dumps([{'run_accession': 'SRR123', 'sample_title': 'ATCC VR-1558'}]))
            references = root / 'references.json'
            references.write_text(json.dumps({'model_id': 'oc43-vr1558', 'references': [{'role': 'helper', 'model_id': 'oc43-vr1558'}]}))
            self.assertEqual(mapping_scope(qc, references, 'oc43-vr1558')['run_accession'], 'SRR123')
            references.write_text(json.dumps({'model_id': 'pr8-vr1469'}))
            with self.assertRaisesRegex(ValueError, 'same exact model'):
                mapping_scope(qc, references, 'oc43-vr1558')
    def test_only_eight_named_models(self):
        self.assertEqual(len(MODELS), 8)
        for old in ('sars-cov-2', 'influenza-a', 'human-coronavirus', 'influenza-b'):
            with self.assertRaisesRegex(ValueError, 'exact model'):
                search_terms(old)

    def test_catalog_match_for_each_model(self):
        for key, model in MODELS.items():
            with self.subTest(key=key):
                self.assertEqual(evaluate({'attributes': {'stock': 'ATCC ' + model['catalog']}}, key)['status'], 'metadata_match')

    def test_catalog_prefix_is_not_a_match(self):
        self.assertEqual(evaluate({'sample_title': 'VR-260'}, 'rsv-long')['status'], 'review_required')

    def test_study_title_cannot_establish_sample_identity(self):
        self.assertEqual(evaluate({'study_title': 'ATCC VR-1558'}, 'oc43-vr1558')['status'], 'review_required')

    def test_organism_only_is_not_exact_stock(self):
        self.assertEqual(evaluate({'organism': 'Human coronavirus OC43'}, 'oc43-vr1558')['status'], 'review_required')

    def test_ambiguous_word_long_is_not_rsv_strain(self):
        self.assertEqual(evaluate({'sample_title': 'RSV long read sequencing'}, 'rsv-long')['status'], 'review_required')

    def test_structured_strain_and_organism(self):
        row = {'organism': 'Human respiratory syncytial virus', 'attributes': {'strain': 'Long'}}
        self.assertEqual(evaluate(row, 'rsv-long')['status'], 'metadata_match')

    def test_pr8_requires_exact_strain_and_no_modified_flags(self):
        row = {'organism': 'Influenza A virus', 'attributes': {'strain': 'PR8'}}
        self.assertEqual(evaluate(row, 'pr8-vr1469')['status'], 'metadata_match')
        row['sample_title'] = 'reassortant comparison'
        self.assertEqual(evaluate(row, 'pr8-vr1469')['status'], 'review_required')

    def test_excluded_mention_overrides_allowed_catalog(self):
        row = {'sample_title': 'OC43 ATCC VR-1558', 'study_title': 'SARS-CoV-2 comparison'}
        self.assertEqual(evaluate(row, 'oc43-vr1558')['status'], 'excluded')

    def test_multiple_catalogs_are_held(self):
        row = {'sample_title': 'VR-1558 and VR-740'}
        self.assertEqual(evaluate(row, 'oc43-vr1558')['status'], 'review_required')

    def test_old_rows_cannot_enter_new_download_plan(self):
        row = {'proposed_helper': 'influenza-a', 'selection': 'eligible_for_review'}
        self.assertEqual(enforce(row)['selection'], 'excluded')

    def test_excluded_model_rejected_before_client_or_output_creation(self):
        with patch('satellite_discovery.workflow.Client') as client:
            with self.assertRaises(ValueError):
                discover('sars-cov-2', 1, 0, False, 'must-not-be-created')
            client.assert_not_called()
