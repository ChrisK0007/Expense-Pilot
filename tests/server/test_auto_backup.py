import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
import zipfile
import errno
from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo
from PIL import Image
import test_app as base
from app import app, db, DATA
import auto_backup
from restore_backup import restore

BRISBANE = ZoneInfo('Australia/Brisbane')


class AutoBackupTest(unittest.TestCase):
    call = base.AppTest.call
    login = base.AppTest.login
    expense = base.AppTest.expense

    def setUp(self):
        base.AppTest.setUp(self)
        auto_backup._memory.clear()
        self.folder = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'BACKUP_DIR': self.folder.name, 'BACKUP_KEEP': '3', 'BACKUP_TIME': '02:30'})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.folder.cleanup()

    def backup_dir(self):
        with app.app_context():
            return auto_backup.directory()[0]

    def upload(self):
        data = io.BytesIO(); Image.new('RGB', (20, 20), 'green').save(data, 'PNG'); data.seek(0)
        return self.owner.post('/api/receipts', data={'file': (data, 'test.png'), 'client_ref': str(uuid.uuid4())},
                               headers={'X-CSRF-Token': self.owner.get('/api/session').json['csrf']})

    def run_now(self, client=None):
        return self.call(client or self.owner, 'data/auto-backup/run', {})

    def test_automatic_backup_restores_with_existing_tool(self):
        self.expense(self.owner)
        self.assertEqual(self.upload().status_code, 200)
        response = self.run_now()
        self.assertEqual(response.status_code, 200, response.json)
        files = auto_backup.archives(self.backup_dir())
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(response.json['status']['last_file'], files[0].name)
        self.assertEqual(response.json['status']['last_error'], '')
        with tempfile.TemporaryDirectory() as target:
            restore(files[0], target)
            con = sqlite3.connect(Path(target) / 'rounded.sqlite')
            self.assertEqual(con.execute('SELECT count(*) FROM expenses').fetchone()[0], 1)
            self.assertEqual(con.execute('SELECT count(*) FROM receipts').fetchone()[0], 1)
            con.close()
        # No partial files or snapshot folders are left behind.
        leftovers = [p.name for p in self.backup_dir().iterdir() if p.name != '.expense-pilot-backup.lock']
        self.assertEqual(leftovers, [files[0].name])

    def test_rotation_keeps_newest_and_ignores_other_files(self):
        folder = self.backup_dir(); folder.mkdir(parents=True, exist_ok=True)
        old = [folder / f'expense-pilot-auto-2026010{i}T023000Z.zip' for i in range(1, 6)]
        for path in old:
            path.write_bytes(b'old')
        (folder / 'my-notes.txt').write_text('keep me')
        self.assertEqual(self.run_now().status_code, 200)
        names = [p.name for p in auto_backup.archives(folder)]
        self.assertEqual(len(names), 3)
        self.assertNotIn(old[0].name, names)
        self.assertIn(old[4].name, names)
        self.assertTrue((folder / 'my-notes.txt').exists())

    def test_damaged_database_never_rotates_out_good_backups(self):
        folder = self.backup_dir(); folder.mkdir(parents=True, exist_ok=True)
        good = [folder / f'expense-pilot-auto-2026010{i}T023000Z.zip' for i in range(1, 4)]
        for path in good:
            path.write_bytes(b'good')
        with app.app_context():
            # A record pointing at a user that does not exist, as corruption could leave.
            con = sqlite3.connect(DATA / 'rounded.sqlite')
            con.execute('PRAGMA foreign_keys=OFF')
            con.execute("INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,status) VALUES (99999,'2026-10-01','Ghost',100,'business','Meals',100,'review')")
            con.commit(); con.close()
        try:
            response = self.run_now()
            self.assertEqual(response.status_code, 503)
            self.assertIn('Earlier backups were kept', response.json['error'])
            self.assertEqual(sorted(p.name for p in auto_backup.archives(folder)), sorted(p.name for p in good))
            self.assertFalse(list(folder.glob('.expense-pilot-auto-*.partial')))
            status = self.owner.get('/api/data/auto-backup').json['status']
            self.assertIn('broken record links', status['last_error'])
            self.assertEqual(status['attempts'], 1)
        finally:
            with app.app_context():
                db().execute("DELETE FROM expenses WHERE merchant='Ghost'"); db().commit()

    def test_truncated_finished_archive_does_not_displace_good_backup(self):
        with patch.dict(os.environ, {'BACKUP_KEEP': '1'}):
            self.assertEqual(self.run_now().status_code, 200)
            good = auto_backup.archives(self.backup_dir())[0]
            original = good.read_bytes()
            writer = auto_backup.write_archive
            def truncate(out, *args, **kwargs):
                manifest = writer(out, *args, **kwargs)
                out.truncate(0)
                return manifest
            with patch('auto_backup.write_archive', side_effect=truncate):
                response = self.run_now()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(good.read_bytes(), original)
            self.assertEqual(auto_backup.archives(self.backup_dir()), [good])
            self.assertTrue(response.json['error'])

    def test_checksum_failure_preserves_last_good_archive(self):
        self.assertEqual(self.run_now().status_code, 200)
        good = auto_backup.archives(self.backup_dir())[0]
        writer = auto_backup.write_archive
        def wrong_manifest(out, *args, **kwargs):
            manifest = writer(out, *args, **kwargs)
            manifest['sha256']['data/rounded.sqlite'] = '0' * 64
            return manifest
        with patch('auto_backup.write_archive', side_effect=wrong_manifest):
            self.assertEqual(self.run_now().status_code, 503)
        self.assertEqual(auto_backup.archives(self.backup_dir()), [good])

    def test_compression_allows_writes_and_retains_concurrently_deleted_receipt(self):
        receipt = self.upload().json['id']
        original = (DATA / 'receipts' / receipt).read_bytes()
        constructor = zipfile.ZipFile
        def during_compression(*args, **kwargs):
            # This fails immediately if the backup still owns a write reservation.
            with sqlite3.connect(DATA / 'rounded.sqlite', timeout=0.01) as con:
                con.execute('BEGIN IMMEDIATE')
                con.execute('DELETE FROM receipts WHERE id=?', (receipt,))
                con.commit()
            (DATA / 'receipts' / receipt).unlink()
            return constructor(*args, **kwargs)
        # Only the writer constructor is intercepted, not readback validation.
        with patch('auto_backup.zipfile.ZipFile', side_effect=lambda *a, **kw: during_compression(*a, **kw) if len(a)>1 and a[1]=='w' else constructor(*a, **kw)):
            self.assertEqual(self.run_now().status_code, 200)
        with tempfile.TemporaryDirectory() as target:
            restore(auto_backup.archives(self.backup_dir())[0], target)
            self.assertEqual((Path(target) / 'receipts' / receipt).read_bytes(), original)

    def test_hard_link_fallback_still_restores(self):
        receipt = self.upload().json['id']
        with patch('auto_backup.os.link', side_effect=OSError(errno.EOPNOTSUPP, 'No hard links')):
            self.assertEqual(self.run_now().status_code, 200)
        with tempfile.TemporaryDirectory() as target:
            restore(auto_backup.archives(self.backup_dir())[0], target)
            self.assertTrue((Path(target) / 'receipts' / receipt).is_file())

    def test_shared_destination_never_rotates_another_installation(self):
        with patch('auto_backup.installation_id', return_value='installation-one'), patch.dict(os.environ, {'BACKUP_KEEP': '1'}):
            self.assertEqual(self.run_now().status_code, 200)
            first = auto_backup.archives(self.backup_dir())[0]
        with patch('auto_backup.installation_id', return_value='installation-two'), patch.dict(os.environ, {'BACKUP_KEEP': '1'}):
            self.assertEqual(self.run_now().status_code, 200)
            self.assertEqual(self.run_now().status_code, 200)
            self.assertEqual(len(auto_backup.archives(self.backup_dir())), 1)
        self.assertTrue(first.exists())

    def test_rotation_orders_same_second_suffix_numerically(self):
        folder = self.backup_dir(); folder.mkdir(parents=True, exist_ok=True)
        for suffix in ('', '-1', '-2', '-9', '-10'):
            (folder / ('expense-pilot-auto-20261027T023000Z' + suffix + '.zip')).touch()
        auto_backup.rotate(folder, 1)
        self.assertEqual([p.name for p in auto_backup.archives(folder)], ['expense-pilot-auto-20261027T023000Z-10.zip'])

    def test_unwritable_folder_is_reported(self):
        with patch.dict(os.environ, {'BACKUP_DIR': '/proc/expense-pilot-backups'}):
            response = self.run_now()
        self.assertEqual(response.status_code, 503)
        self.assertIn('not writable', response.json['error'])

    def test_owner_only_and_status(self):
        self.assertEqual(self.agent.get('/api/data/auto-backup').status_code, 403)
        self.assertEqual(self.run_now(self.agent).status_code, 403)
        info = self.owner.get('/api/data/auto-backup').json
        self.assertEqual((info['enabled'], info['keep'], info['time'], info['count']), (True, 3, '02:30', 0))
        self.assertTrue(info['separate'])
        with patch.dict(os.environ, {'BACKUP_DIR': ''}):
            info = self.owner.get('/api/data/auto-backup').json
            self.assertFalse(info['separate'])  # Defaults inside the data folder.
        with patch.dict(os.environ, {'BACKUP_KEEP': '0'}):
            self.assertFalse(self.owner.get('/api/data/auto-backup').json['enabled'])
            self.assertEqual(self.run_now().status_code, 503)

    def test_schedule(self):
        due = auto_backup.due
        at = lambda h, m=0, day=27: datetime(2026, 10, day, h, m, tzinfo=BRISBANE)
        self.assertFalse(due({}, at(2, 29), (2, 30)))
        self.assertTrue(due({}, at(2, 30), (2, 30)))
        self.assertTrue(due({}, at(23, 0), (2, 30)))  # Catches up if the server was off at 2:30.
        self.assertFalse(due({}, at(3), (2, 30), enabled=False))
        self.assertFalse(due({'success_day': '2026-10-27'}, at(3), (2, 30)))
        self.assertTrue(due({'success_day': '2026-10-26'}, at(3), (2, 30)))
        failed = at(3).astimezone(timezone.utc)
        state = {'attempt_day': '2026-10-27', 'attempts': 1, 'last_attempt': failed.isoformat()}
        self.assertFalse(due(state, at(3, 30), (2, 30)))  # Retries hourly after a failure.
        self.assertTrue(due(state, at(4, 1), (2, 30)))
        self.assertFalse(due(dict(state, attempts=3), at(9), (2, 30)))
        self.assertTrue(due(dict(state, attempts=3), at(3, day=28), (2, 30)))

    def test_settings_parsing(self):
        with patch.dict(os.environ, {'BACKUP_KEEP': 'lots', 'BACKUP_TIME': '25:99'}):
            self.assertEqual(auto_backup.keep(), auto_backup.DEFAULT_KEEP)
            self.assertEqual(auto_backup.scheduled_time(), (2, 30))
        with patch.dict(os.environ, {'BACKUP_KEEP': '1000', 'BACKUP_TIME': '23:05'}):
            self.assertEqual(auto_backup.keep(), 365)
            self.assertEqual(auto_backup.scheduled_time(), (23, 5))

    def test_tick_runs_once_per_day(self):
        with app.app_context(), patch('auto_backup.datetime') as clock:
            clock.now.side_effect = lambda tz=None: datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc).astimezone(tz) if tz else datetime(2026, 10, 27, 3, 0)
            clock.fromisoformat = datetime.fromisoformat
            with patch('workspace_time.today', return_value=datetime(2026, 10, 27).date()), \
                 patch('workspace_time.zone', return_value=timezone.utc):
                auto_backup.tick(); auto_backup.tick()
        self.assertEqual(len(auto_backup.archives(self.backup_dir())), 1)


if __name__ == '__main__':
    unittest.main()
