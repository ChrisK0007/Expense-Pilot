"""Ordered, transactional SQLite migrations for new and existing installations."""
import hashlib
import importlib
import sqlite3
from pathlib import Path


def execute_script(connection, script):
    """Execute SQL without sqlite3.executescript's implicit transaction commit."""
    statement = ''
    for char in script:
        statement += char
        if char == ';' and sqlite3.complete_statement(statement):
            connection.execute(statement)
            statement = ''
    if statement.strip():
        raise ValueError('Migration SQL must end in a semicolon')


def apply(connection):
    if connection.in_transaction:
        raise RuntimeError('Migrations require a connection outside a transaction')
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
    files = sorted(Path(__file__).parent.glob('m[0-9][0-9][0-9]_*.py'))
    known = {path.stem for path in files}
    if any(row[0] not in known for row in connection.execute('SELECT version FROM schema_migrations')):
        raise RuntimeError('Database has newer migrations; use the matching application version')
    for path in files:
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        connection.execute('BEGIN IMMEDIATE')
        try:
            previous = connection.execute('SELECT checksum FROM schema_migrations WHERE version=?', (path.stem,)).fetchone()
            if previous:
                if previous[0] != checksum:
                    raise RuntimeError(f'Applied migration was modified: {path.stem}')
            else:
                importlib.import_module(f'migrations.{path.stem}').upgrade(connection)
                connection.execute('INSERT INTO schema_migrations(version,checksum) VALUES (?,?)', (path.stem, checksum))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
