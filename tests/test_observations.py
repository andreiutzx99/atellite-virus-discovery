import csv
from contextlib import closing
import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from test_metadata import scratch_directory
from satellite_discovery.observation_report import run, validate, summarize


class ObservationTests(unittest.TestCase):
    def fixture(self, root):
        root = Path(root)
        samples = root / 'samples.csv'
        observations = root / 'observations.csv'
        samples.write_text('sample_id,study_id,condition,sample_type,library_molecule\n'
                           'a,study1,positive,biological,RNA\n'
                           'b,study1,negative,biological,RNA\n'
                           'c,study2,positive,biological,DNA\n'
                           'blank,study1,unknown,technical_control,RNA\n', encoding='utf-8')
        observations.write_text('sample_id,feature_id,detection\n'
                                'a,feature1,present\nb,feature1,absent\n'
                                'blank,feature1,present\n', encoding='utf-8')
        return samples, observations, root / 'report'

    def test_missing_not_absent_controls_not_biological_and_assays_separate(self):
        with scratch_directory() as root:
            samples, obs, _ = self.fixture(root)
            summary = summarize(*validate(samples, obs))
            feature = summary['recurrence'][0]
            self.assertEqual(feature['present_biological_samples'], 1)
            self.assertEqual(feature['absent_biological_samples'], 1)
            self.assertEqual(feature['unknown_biological_samples'], 1)
            self.assertEqual(feature['distinct_studies_with_detection'], 1)
            dna = next(r for r in summary['comparisons'] if r['library_molecule'] == 'DNA')
            self.assertEqual(dna['assessed_samples'], 0)
            self.assertIsNone(dna['observed_fraction'])

    def test_duplicate_biological_sample_rejected(self):
        with scratch_directory() as root:
            samples, obs, _ = self.fixture(root)
            with samples.open('a') as f:
                f.write('a,study1,positive,biological,RNA\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate biological'):
                validate(samples, obs)

    def test_duplicate_observation_and_unknown_sample_rejected(self):
        for line in ('a,feature1,present\n', 'missing,feature2,present\n'):
            with self.subTest(line=line), scratch_directory() as root:
                samples, obs, _ = self.fixture(root)
                with obs.open('a') as f:
                    f.write(line)
                with self.assertRaisesRegex(ValueError, 'Unknown sample or duplicate'):
                    validate(samples, obs)

    def test_database_and_verified_resume(self):
        with scratch_directory() as root:
            samples, obs, output = self.fixture(root)
            result = run(samples, obs, output)
            with closing(sqlite3.connect(output / 'observations.sqlite')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM samples').fetchone()[0], 4)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 3)
            with patch('satellite_discovery.observation_report.export_database', side_effect=AssertionError('must not rewrite')):
                self.assertEqual(run(samples, obs, output), result)

    def test_corrupted_output_and_changed_inputs_rejected(self):
        with scratch_directory() as root:
            samples, obs, output = self.fixture(root)
            run(samples, obs, output)
            (output / 'report.html').write_text('corruption')
            with self.assertRaisesRegex(ValueError, 'integrity failure'):
                run(samples, obs, output)
            with obs.open('a') as f:
                f.write('c,feature1,absent\n')
            with self.assertRaisesRegex(ValueError, 'Inputs or engine changed'):
                run(samples, obs, output)

    def test_failure_can_resume_without_duplicate_database_rows(self):
        with scratch_directory() as root:
            samples, obs, output = self.fixture(root)
            with patch('satellite_discovery.observation_report.render', side_effect=RuntimeError('interrupted')):
                with self.assertRaises(RuntimeError):
                    run(samples, obs, output)
            self.assertEqual(json.loads((output / 'manifest.json').read_text())['status'], 'failed')
            self.assertFalse((output / '.observations.lock').exists())
            self.assertEqual(run(samples, obs, output)['status'], 'complete')

    def test_html_and_csv_are_escaped(self):
        with scratch_directory() as root:
            samples, obs, output = self.fixture(root)
            obs.write_text(obs.read_text().replace('feature1', '=1+<script>'))
            run(samples, obs, output)
            report = (output / 'report.html').read_text()
            self.assertNotIn('<script>', report)
            self.assertIn('&lt;script&gt;', report)
            with (output / 'recurrence.csv').open(encoding='utf-8-sig', newline='') as f:
                self.assertTrue(next(csv.DictReader(f))['feature_id'].startswith("'="))

    def test_lock_blocks_concurrent_writer(self):
        with scratch_directory() as root:
            samples, obs, output = self.fixture(root)
            output.mkdir()
            (output / '.observations.lock').write_text('')
            with self.assertRaisesRegex(ValueError, 'locked'):
                run(samples, obs, output)
            self.assertTrue((output / '.observations.lock').exists())

    def test_unmanaged_existing_directory_preserved(self):
        with scratch_directory() as root:
            samples, obs, output = self.fixture(root)
            output.mkdir()
            sentinel = output / 'keep.txt'
            sentinel.write_text('original')
            with self.assertRaisesRegex(ValueError, 'not empty'):
                run(samples, obs, output)
            self.assertEqual(sentinel.read_text(), 'original')
