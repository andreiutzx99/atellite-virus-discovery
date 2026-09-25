"""SQLite artifact validators must release their handles before returning."""
from contextlib import closing
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch

from test_metadata import scratch_directory
from satellite_discovery import artifact_contracts, sequence_catalogue


class SQLiteResourceLifetimeTests(unittest.TestCase):
    def assert_validator_closes_database(self, path, artifact_type, error=None):
        held_connections = []
        real_connect = sqlite3.connect

        def track_connection(*args, **kwargs):
            connection = real_connect(*args, **kwargs)
            held_connections.append(connection)
            return connection

        try:
            with patch.object(artifact_contracts.sqlite3, 'connect', side_effect=track_connection):
                if error is None:
                    artifact_contracts.validate_artifact(path, artifact_type)
                else:
                    with self.assertRaises(error):
                        artifact_contracts.validate_artifact(path, artifact_type)

            self.assertEqual(len(held_connections), 1)
            with self.assertRaises(sqlite3.ProgrammingError):
                held_connections[0].execute('SELECT 1')
            path.unlink()
            self.assertFalse(path.exists())
        finally:
            for connection in held_connections:
                connection.close()

    def test_valid_catalogue_contracts_close_connections(self):
        with scratch_directory() as folder:
            root = Path(folder)
            source = root / 'input.fa'
            source.write_text('>fixture\nACGT\n', encoding='utf-8')
            for artifact_type in ('sequence_catalogue', 'reference_record_database'):
                with self.subTest(artifact_type=artifact_type):
                    output = root / artifact_type
                    sequence_catalogue.run(source, output)
                    self.assert_validator_closes_database(
                        output / 'catalogue.sqlite', artifact_type)

    def test_invalid_catalogue_contracts_close_connections(self):
        with scratch_directory() as folder:
            root = Path(folder)
            for artifact_type, error in (
                ('sequence_catalogue', sqlite3.OperationalError),
                ('reference_record_database', ValueError),
            ):
                with self.subTest(artifact_type=artifact_type):
                    path = root / (artifact_type + '.sqlite')
                    with closing(sqlite3.connect(path)) as db, db:
                        db.execute('CREATE TABLE unrelated (id INTEGER)')
                    self.assert_validator_closes_database(path, artifact_type, error)