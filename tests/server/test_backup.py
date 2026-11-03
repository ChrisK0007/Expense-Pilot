"""Exercise the real backup script against a mocked Docker CLI and real archives."""
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest


class BackupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = Path(__file__).resolve().parents[2] / 'scripts' / 'backup.sh'
        if not cls.script.exists():
            raise unittest.SkipTest('Host deployment scripts are tested outside the production image')

    def run_backup(self, running='true', destination='backup', fail_archive=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data = root/'custom appdata';data.mkdir()
            (data/'rounded.sqlite').write_bytes(b'database')
            (data/'session.key').write_text('preserved-key')
            (data/'receipts').mkdir();(data/'receipts'/'receipt').write_bytes(b'receipt')
            (root/'.env').write_text('CONFIG=test\n')
            (data/'backup-id').write_text('not-cloned')
            (data/'backups').mkdir();(data/'backups'/'older.zip').write_bytes(b'old backup')
            (data/'.backup-stage-old').mkdir();(data/'.backup-stage-old'/'rounded.sqlite').write_bytes(b'stale staging')
            binary = root/'bin';binary.mkdir()
            docker = binary/'docker'
            docker.write_text('''#!/usr/bin/env bash
printf '%s\\n' "$1" >> "$CALLS"
if [ "$1" = inspect ]; then
  case "$3" in *Mounts*) printf '%s\\n' "$MOUNT";; *) printf '%s\\n' "$RUNNING";; esac
fi
''')
            docker.chmod(0o755)
            if fail_archive:
                tar = binary/'tar';tar.write_text('#!/usr/bin/env bash\nexit 2\n');tar.chmod(0o755)
            output = data/'backup' if destination=='inside' else root/'backup'
            result = subprocess.run(['bash',str(self.script),str(output)],capture_output=True,text=True,env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],'CALLS':str(root/'calls'),'MOUNT':str(data),'RUNNING':running,'EXPENSE_PILOT_ENV_FILE':str(root/'.env'),'EXPENSE_PILOT_DATA_DIR':''})
            calls=(root/'calls').read_text().splitlines()
            if destination=='inside' or fail_archive:
                self.assertNotEqual(result.returncode,0)
                self.assertEqual(list(output.glob('*.tar.gz')),[])
            else:
                self.assertEqual(result.returncode,0,result.stderr)
                archive=next(output.glob('*.tar.gz'))
                self.assertEqual(archive.stat().st_mode & 0o777,0o600)
                with tarfile.open(archive) as saved:
                    self.assertEqual(saved.extractfile('data/session.key').read(),b'preserved-key')
                    self.assertEqual(saved.extractfile('data/receipts/receipt').read(),b'receipt')
                    self.assertEqual(saved.extractfile('.env').read(),b'CONFIG=test\n')
                    self.assertFalse(any(name.startswith(('data/backups', 'data/.backup-stage-', 'data/backup-id')) for name in saved.getnames()))
            return calls

    def test_custom_mount_and_running_container(self):
        self.assertEqual(self.run_backup(),['inspect','inspect','stop','start'])

    def test_stopped_container_stays_stopped(self):
        self.assertEqual(self.run_backup(running='false'),['inspect','inspect'])

    def test_restart_after_archive_failure(self):
        self.assertEqual(self.run_backup(fail_archive=True),['inspect','inspect','stop','start'])

    def test_reject_destination_inside_data_before_stopping(self):
        self.assertEqual(self.run_backup(destination='inside'),['inspect','inspect'])
