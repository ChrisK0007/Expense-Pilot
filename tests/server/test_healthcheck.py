"""Real file corruption must fail health without creating/replacing user data."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import healthcheck


class DatabaseHealthTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'rounded.sqlite'

    def fixture(self):
        with closing(sqlite3.connect(self.path)) as connection:
            for table in ('users', 'login_sessions', 'expenses', 'schema_migrations'):
                connection.execute(f'CREATE TABLE {table}(id INTEGER PRIMARY KEY, value TEXT)')
                connection.execute(f'INSERT INTO {table}(value) VALUES (?)', ('kept record',))
            connection.commit()

    def test_healthy_file_is_not_changed(self):
        self.fixture()
        before = self.path.read_bytes()
        healthcheck.check_database(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_missing_and_empty_databases_fail_without_creation(self):
        with self.assertRaises(sqlite3.DatabaseError):
            healthcheck.check_database(self.path)
        self.assertFalse(self.path.exists())
        self.path.touch()
        with self.assertRaises(sqlite3.DatabaseError):
            healthcheck.check_database(self.path)
        self.assertEqual(self.path.stat().st_size, 0)

    def test_bad_session_page_fails_even_if_http_is_available(self):
        self.fixture()
        with closing(sqlite3.connect(self.path)) as connection:
            size = connection.execute('PRAGMA page_size').fetchone()[0]
            page = connection.execute("SELECT rootpage FROM sqlite_schema WHERE name='login_sessions'").fetchone()[0]
        # On this disposable closed database only, invalidate the session B-tree header.
        with self.path.open('r+b') as stream:
            stream.seek((page - 1) * size)
            stream.write(b'\x00')
        before = hashlib.sha256(self.path.read_bytes()).digest()
        with patch.object(healthcheck, 'check_runtime', return_value='3.54.1'), \
             patch.object(healthcheck, 'urlopen') as http, \
             patch.dict('os.environ', DATA_DIR=self.folder.name), \
             patch('sys.stderr') as error:
            http.return_value.__enter__.return_value.status = 200
            self.assertEqual(healthcheck.main(), 1)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), before)
        self.assertNotIn(self.folder.name, str(error.write.call_args_list))

    def test_live_wal_is_observed_while_another_connection_writes(self):
        self.fixture()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute("INSERT INTO expenses(value) VALUES ('committed in WAL')")
            connection.commit()
            connection.execute('BEGIN IMMEDIATE')
            connection.execute("INSERT INTO expenses(value) VALUES ('uncommitted')")
            healthcheck.check_database(self.path)
            connection.rollback()
            self.assertEqual(connection.execute('SELECT count(*) FROM expenses').fetchone()[0], 2)

    def test_loaded_library_must_match_manifest(self):
        manifest = Path(self.folder.name) / 'runtime.json'
        with closing(sqlite3.connect(':memory:')) as connection:
            source = connection.execute('SELECT sqlite_source_id()').fetchone()[0]
        manifest.write_text(json.dumps(dict(version=sqlite3.sqlite_version, source_id=source)))
        self.assertEqual(healthcheck.check_runtime(manifest), sqlite3.sqlite_version)
        manifest.write_text(json.dumps(dict(version='3.54.1', source_id='wrong build')))
        with self.assertRaises(RuntimeError):
            healthcheck.check_runtime(manifest)

    def test_expired_execution_budget_stops_large_check(self):
        self.fixture()
        with closing(sqlite3.connect(self.path)) as connection:
            connection.executemany('INSERT INTO expenses(value) VALUES (?)', [('test',)] * 5000)
            connection.commit()
        with self.assertRaisesRegex(sqlite3.OperationalError, 'interrupted'):
            healthcheck.check_database(self.path, seconds=0)

    def test_http_failure_is_unhealthy(self):
        with patch.object(healthcheck, 'check_runtime', return_value='3.54.1'), \
             patch.object(healthcheck, 'urlopen', side_effect=OSError), patch('sys.stderr'):
            self.assertEqual(healthcheck.main(), 1)


if __name__ == '__main__':
    unittest.main()
