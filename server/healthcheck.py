"""Container health: HTTP availability, loaded SQLite and database structure.

Runs independently of Flask and never imports app or applies migrations.
An unhealthy database is reported, never rebuilt or replaced automatically.
"""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from urllib.request import urlopen


def check_runtime(manifest_path=Path('/opt/sqlite/share/sqlite-runtime.json')):
    manifest = json.loads(manifest_path.read_text())
    with closing(sqlite3.connect(':memory:')) as connection:
        version, source = connection.execute('SELECT sqlite_version(),sqlite_source_id()').fetchone()
    if version != manifest['version'] or source != manifest['source_id'] or not sqlite3.threadsafety:
        raise RuntimeError('Python is not using the packaged SQLite runtime')
    return version


def check_database(path, seconds=5):
    # mode=ro fails for a missing database rather than creating an empty one.
    # Do not use immutable=1: the server may have committed data in its WAL.
    deadline = time.monotonic() + seconds
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.set_progress_handler(lambda: time.monotonic() > deadline, 1000)
        if connection.execute('PRAGMA quick_check(1)').fetchall() != [('ok',)]:
            raise RuntimeError('Database structure check failed')
        # Also reject an empty/wrong database that passes quick_check.
        for table in ('users', 'login_sessions', 'expenses', 'schema_migrations'):
            connection.execute(f'SELECT * FROM "{table}" NOT INDEXED LIMIT 1').fetchone()


def main():
    try:
        version = check_runtime()
        with urlopen('http://127.0.0.1:8788/api/session', timeout=2) as response:
            if response.status != 200:
                raise RuntimeError('Application HTTP check failed')
        check_database(Path(os.environ.get('DATA_DIR', '/data')) / 'rounded.sqlite')
    except Exception as exc:
        # Docker exposes health output; never include database contents or paths.
        print('Expense Pilot health check failed (' + type(exc).__name__ + ').', file=sys.stderr)
        return 1
    print('HTTP and database checks passed; SQLite ' + version)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
