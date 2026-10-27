"""Exercise upgrade from the image's Debian SQLite to the pinned runtime."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from healthcheck import check_database, check_runtime
from migrations import apply


@unittest.skipUnless(Path('/opt/sqlite/share/sqlite-runtime.json').exists(), 'requires the built Docker image')
class SQLiteRuntimeTests(unittest.TestCase):
    def test_python_loads_pinned_library_and_preserves_older_database(self):
        self.assertEqual(check_runtime(), '3.54.1')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'rounded.sqlite'
            # Empty LD_LIBRARY_PATH deliberately selects the Debian library only
            # in this disposable child process, representing the previous image.
            environment = dict(os.environ, LD_LIBRARY_PATH='')
            environment['PYTHONPATH'] = str(Path(__file__).resolve().parents[2])
            create = '''
import json, sqlite3, sys
from migrations import apply
db = sqlite3.connect(sys.argv[1])
apply(db)
db.execute("INSERT INTO users(id,name,email,password,role) VALUES (1,'Test owner','owner@example.test','kept-password-hash','owner')")
db.execute("INSERT INTO receipts(id,user_id,filename,mime) VALUES ('receipt',1,'kept.png','image/png')")
db.execute("INSERT INTO expenses(id,user_id,date,merchant,amount_cents,scope,category,work_percent,business_percent,receipt_id) VALUES (1,1,'2026-10-01','Test bill',12345,'split','Other',30,20,'receipt')")
db.execute("INSERT INTO login_sessions(token_hash,user_id,kind,expires) VALUES ('existing-session',1,'auth',9999999999)")
db.commit()
print(json.dumps({'version': sqlite3.sqlite_version, 'dump': list(db.iterdump())}))
db.close()
'''
            previous = json.loads(subprocess.check_output([sys.executable, '-c', create, str(path)], env=environment, text=True))
            self.assertNotEqual(previous['version'], sqlite3.sqlite_version)
            with closing(sqlite3.connect(path)) as connection:
                apply(connection)
                self.assertEqual(list(connection.iterdump()), previous['dump'])
                connection.execute("UPDATE expenses SET amount_cents=17999 WHERE id=1")
                connection.commit()
                backup = Path(folder) / 'backup.sqlite'
                with closing(sqlite3.connect(backup)) as target:
                    connection.backup(target)
                    self.assertEqual(target.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
                    self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(), [])
            check_database(path)
            check_database(backup)
            # The update introduces no schema migration or new SQLite-only SQL.
            read = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('SELECT amount_cents FROM expenses WHERE id=1').fetchone()[0]); c.close()"
            self.assertEqual(subprocess.check_output([sys.executable, '-c', read, str(backup)], env=environment, text=True).strip(), '17999')
