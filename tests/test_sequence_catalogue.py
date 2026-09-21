from contextlib import closing
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from test_metadata import scratch_directory
from satellite_discovery.sequence_catalogue import read_fasta, measurements, run


class SequenceCatalogueTests(unittest.TestCase):
    def fixture(self, root):
        source = Path(root) / 'input.fasta'
        source.write_text('>a first\nACGTNN\n>b duplicate\nacgtnn\n>c unknown\nNN\n>d RNA\nACGU\n')
        return source, Path(root) / 'inventory'

    def test_composition_unknowns_and_exact_groups(self):
        with scratch_directory() as root:
            source, _ = self.fixture(root)
            rows = measurements(read_fasta(source))
            self.assertEqual(rows[0]['gc_fraction_called_bases'], 0.5)
            self.assertAlmostEqual(rows[0]['ambiguous_fraction'], 2/6)
            self.assertEqual(rows[0]['single_symbol_entropy_bits'], 2.0)
            self.assertEqual(rows[0]['exact_duplicate_group_size'], 2)
            self.assertEqual(rows[0]['sequence_sha256'], rows[1]['sequence_sha256'])
            self.assertIsNone(rows[2]['gc_fraction_called_bases'])
            self.assertIsNone(rows[2]['single_symbol_entropy_bits'])
            self.assertEqual(rows[3]['gc_fraction_called_bases'], 0.5)

    def test_export_roundtrip_database_and_verified_resume(self):
        with scratch_directory() as root:
            source, output = self.fixture(root)
            original = source.read_bytes()
            result = run(source, output)
            self.assertEqual(read_fasta(source), read_fasta(output/'sequences.fasta'))
            self.assertEqual(source.read_bytes(), original)
            with closing(sqlite3.connect(output/'catalogue.sqlite')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM sequences').fetchone()[0], 3)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0], 4)
            with patch('satellite_discovery.sequence_catalogue.create_database', side_effect=AssertionError('no rebuild')):
                self.assertEqual(run(source, output), result)

    def test_invalid_fasta_and_duplicate_identifiers(self):
        for content in ('ACGT', '>a\n', '>a\nACGT\n>a\nACGT', '>a\nACGZ', '>a\nAC-GT', '>\nACGT'):
            with self.subTest(content=content), scratch_directory() as root:
                source = Path(root)/'bad.fa'
                source.write_text(content)
                with self.assertRaises(ValueError):
                    read_fasta(source)

    def test_alphabet_and_strand_are_not_silently_collapsed(self):
        rows = measurements([('a','a','AACG'),('b','b','CGTT'),('c','c','AACU'),('d','d','AUTG')])
        self.assertEqual(len({r['sequence_sha256'] for r in rows}), 4)
        self.assertIn('both_T_and_U_present', rows[3]['warnings'])

    def test_corruption_and_changed_input_block_reuse(self):
        with scratch_directory() as root:
            source, output = self.fixture(root)
            run(source, output)
            (output/'sequences.fasta').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'integrity failure'):
                run(source, output)
            source.write_text('>new\nACGT')
            with self.assertRaisesRegex(ValueError, 'Inputs or implementation changed'):
                run(source, output)

    def test_failed_export_can_resume(self):
        with scratch_directory() as root:
            source, output = self.fixture(root)
            with patch('satellite_discovery.sequence_catalogue.create_database', side_effect=RuntimeError('disk failure')):
                with self.assertRaises(RuntimeError):
                    run(source, output)
            self.assertEqual(json.loads((output/'manifest.json').read_text())['status'], 'failed')
            self.assertEqual(run(source, output)['status'], 'complete')

    def test_input_resource_limit(self):
        with scratch_directory() as root:
            source, _ = self.fixture(root)
            with patch('satellite_discovery.sequence_catalogue.MAX_BASES', 3):
                with self.assertRaisesRegex(ValueError, 'base limit'):
                    read_fasta(source)

    def test_active_lock_and_unmanaged_output_preserved(self):
        with scratch_directory() as root:
            source, output = self.fixture(root)
            output.mkdir()
            lock = output/'.catalogue.lock'
            lock.write_text('')
            with self.assertRaisesRegex(ValueError, 'locked'):
                run(source, output)
            lock.unlink()
            sentinel = output/'keep.txt'
            sentinel.write_text('keep')
            with self.assertRaisesRegex(ValueError, 'not empty'):
                run(source, output)
            self.assertEqual(sentinel.read_text(), 'keep')
