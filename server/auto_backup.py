"""Verified, rotated automatic backups in the same format as the manual download.

Archives are written to BACKUP_DIR, else a mounted /backups folder, else
/data/backups. Each archive's database snapshot must pass SQLite's integrity
and foreign-key checks before it is kept, and older archives are only rotated
out after a new one has been fully written and verified. A damaged database
therefore can never push the last good backups out of the rotation.

Restore an automatic archive exactly like a downloaded one (restore_backup.py).
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import errno
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
import uuid

log = logging.getLogger('expense_pilot.backup')
NAME = re.compile(r'expense-pilot-auto-\d{8}T\d{6}Z(?:-\d+)?\.zip')
DEFAULT_KEEP, DEFAULT_TIME, MAX_ATTEMPTS = 7, '02:30', 3
_memory = {}  # Fallback when status cannot be saved (for example, a damaged database).


class BackupError(RuntimeError):
    pass


def verify_snapshot(path):
    """The same database checks restore_backup.py applies before installing data."""
    try:
        with closing(sqlite3.connect(path)) as con:
            if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise BackupError('The database failed its integrity check. Earlier backups were kept.')
            if con.execute('PRAGMA foreign_key_check').fetchone():
                raise BackupError('The database has broken record links. Earlier backups were kept.')
            con.execute('SELECT version FROM schema_migrations LIMIT 1')
    except sqlite3.DatabaseError as exc:
        raise BackupError('The database could not be read for checking. Earlier backups were kept.') from exc


def _stage(data_dir, root):
    """Reserve a committed snapshot and pin immutable receipt files, then unlock.

    Uploads create unique receipt names and never modify their bytes. Hard links
    keep those bytes alive after a concurrent deletion; filesystems without link
    support use a copy while the reservation is held. Compression and validation
    happen after releasing it, so they cannot stall authenticated requests.
    """
    snapshot = root / 'rounded.sqlite'
    with closing(sqlite3.connect(data_dir / 'rounded.sqlite', timeout=30)) as reservation:
        reservation.execute('BEGIN IMMEDIATE')
        try:
            with closing(sqlite3.connect(data_dir / 'rounded.sqlite')) as source, \
                    closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
            with closing(sqlite3.connect(snapshot)) as con:
                receipt_ids = [row[0] for row in con.execute('SELECT id FROM receipts')]
            files = [('rounded.sqlite', snapshot)]
            # session.key is small and may be rotated outside normal receipt writes.
            shutil.copyfile(data_dir / 'session.key', root / 'session.key')
            files.append(('session.key', root / 'session.key'))
            (root / 'receipts').mkdir()
            for rid in receipt_ids:
                if not re.fullmatch(r'[0-9a-f]{40}', rid):
                    raise BackupError('Invalid receipt identifier. Earlier backups were kept.')
                source, target = data_dir / 'receipts' / rid, root / 'receipts' / rid
                try:
                    os.link(source, target)
                except OSError as exc:
                    if exc.errno not in (errno.EXDEV, errno.EPERM, errno.EOPNOTSUPP, errno.ENOSYS):
                        raise
                    shutil.copyfile(source, target)
                files.append(('receipts/' + rid, target))
            return files
        finally:
            reservation.rollback()


def write_archive(archive, data_dir, version, verify=False):
    """Write a restorable ZIP, returning the manifest for independent readback.

    Staging on /data permits cheap receipt hard links even when /backups is on
    another disk. Callers must not hold an existing database write transaction.
    """
    data_dir = Path(data_dir)
    with tempfile.TemporaryDirectory(prefix='.backup-stage-', dir=data_dir) as directory:
        files = _stage(data_dir, Path(directory))
        if verify:
            verify_snapshot(Path(directory) / 'rounded.sqlite')
        checksums = {}
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
            for name, path in files:
                digest = hashlib.sha256()
                with path.open('rb') as inp, zipped.open('data/' + name, 'w', force_zip64=True) as out:
                    for chunk in iter(lambda: inp.read(1024 * 1024), b''):
                        digest.update(chunk)
                        out.write(chunk)
                checksums['data/' + name] = digest.hexdigest()
            manifest = dict(format=1, product='Expense Pilot', version=version, sha256=checksums)
            zipped.writestr('manifest.json', json.dumps(manifest))
        return manifest


def verify_archive(path, expected):
    """Read every finished ZIP member back before publishing or deleting backups.

    Matching the checked snapshot's SHA-256 also verifies the database bytes in
    the archive without another database-sized extraction. ZipFile checks CRCs.
    """
    with zipfile.ZipFile(path) as zipped:
        names = zipped.namelist()
        checks = expected['sha256']
        if len(names) != len(set(names)) or set(names) != set(checks) | {'manifest.json'}:
            raise BackupError('The completed backup has missing or duplicate files. Earlier backups were kept.')
        if json.loads(zipped.read('manifest.json')) != expected:
            raise BackupError('The completed backup manifest changed. Earlier backups were kept.')
        for name, wanted in checks.items():
            digest = hashlib.sha256()
            with zipped.open(name) as inp:
                for chunk in iter(lambda: inp.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != wanted:
                raise BackupError('The completed backup failed checksum verification. Earlier backups were kept.')


def installation_id():
    """Local identity, deliberately excluded from downloadable/restorable backups."""
    from app import DATA
    with open(DATA / '.backup-identity.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = DATA / 'backup-id'
        if path.exists():
            return str(uuid.UUID(path.read_text().strip()))
        value = str(uuid.uuid4())
        # Publish atomically so an interrupted first run cannot leave a partial ID.
        fd, temporary = tempfile.mkstemp(prefix='.backup-id-', dir=DATA)
        try:
            with os.fdopen(fd, 'w') as out:
                out.write(value)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(DATA, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return value


def directory():
    """Return (folder, separate_from_data)."""
    from app import DATA
    value = os.environ.get('BACKUP_DIR', '').strip()
    folder = Path(value) if value else Path('/backups') if Path('/backups').is_dir() else DATA / 'backups'
    try:
        inside = folder.resolve().is_relative_to(Path(DATA).resolve())
    except OSError:
        inside = True
    return folder / installation_id(), not inside


def keep():
    value = os.environ.get('BACKUP_KEEP', str(DEFAULT_KEEP)).strip()
    return max(0, min(365, int(value))) if value.isdigit() else DEFAULT_KEEP


def scheduled_time():
    value = os.environ.get('BACKUP_TIME', DEFAULT_TIME).strip()
    match = re.fullmatch(r'([01]?\d|2[0-3]):([0-5]\d)', value)
    return (int(match[1]), int(match[2])) if match else (2, 30)


def archives(folder):
    try:
        found = [p for p in folder.iterdir() if NAME.fullmatch(p.name) and p.is_file()]
    except FileNotFoundError:
        return []
    def order(path):
        match = re.fullmatch(r'expense-pilot-auto-(\d{8}T\d{6}Z)(?:-(\d+))?\.zip', path.name)
        return match[1], int(match[2] or 0)
    return sorted(found, key=order, reverse=True)


def rotate(folder, count, newest=None):
    removed = []
    ordered = archives(folder)
    if newest in ordered:
        ordered.remove(newest)
        ordered.insert(0, newest)
    for old in ordered[count:]:
        old.unlink(missing_ok=True); removed.append(old.name)
    return removed


def _required_bytes(data_dir):
    total = sum(p.stat().st_size for p in (data_dir / 'rounded.sqlite', data_dir / 'rounded.sqlite-wal') if p.exists())
    for path in (data_dir / 'receipts').iterdir():
        if path.is_file():
            total += path.stat().st_size
    return int(total * 1.1) + 64 * 1024 * 1024


def create():
    """Write one verified archive and rotate. Raises BackupError with a user-facing reason."""
    from app import DATA, VERSION
    count = keep()
    if not count:
        raise BackupError('Automatic backups are turned off (BACKUP_KEEP=0).')
    folder, _ = directory()
    try:
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = open(folder / '.expense-pilot-backup.lock', 'a')
    except OSError as exc:
        raise BackupError(f'The backup folder {folder} is not writable by the container (UID 99).') from exc
    with lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BackupError('Another backup is already running.') from None
        for stale in folder.glob('.expense-pilot-auto-*.partial'):
            stale.unlink(missing_ok=True)
        # Allow both the staging copy (including hard-link fallback) and output ZIP.
        required = _required_bytes(DATA)
        if shutil.disk_usage(folder).free < 2 * required or shutil.disk_usage(DATA).free < 2 * required:
            raise BackupError('Not enough free space in the backup folder. Earlier backups were kept.')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        final, n = folder / f'expense-pilot-auto-{stamp}.zip', 1
        while final.exists():
            final, n = folder / f'expense-pilot-auto-{stamp}-{n}.zip', n + 1
        fd, partial = tempfile.mkstemp(prefix='.expense-pilot-auto-', suffix='.partial', dir=folder)
        try:
            with os.fdopen(fd, 'w+b') as out:
                manifest = write_archive(out, DATA, VERSION, verify=True)
                out.flush(); os.fsync(out.fileno())
            verify_archive(partial, manifest)
            os.chmod(partial, 0o600)
            os.replace(partial, final)
            dirfd = os.open(folder, os.O_RDONLY)
            try: os.fsync(dirfd)
            finally: os.close(dirfd)
        except BaseException as exc:
            Path(partial).unlink(missing_ok=True)
            if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
                raise BackupError('The backup folder ran out of space. Earlier backups were kept.') from exc
            raise
        removed = rotate(folder, count, newest=final)
    return dict(file=final.name, bytes=final.stat().st_size, removed=removed)


def status():
    from billing import settings
    try:
        saved = settings('auto_backup', {})
    except sqlite3.Error:
        saved = {}
    return {**saved, **_memory}


def _record(**changes):
    from billing import save_settings
    from app import db
    _memory.update(changes)
    try:
        current = status()
        save_settings('auto_backup', current); db().commit()
        _memory.clear()
    except sqlite3.Error:
        log.exception('Could not save automatic backup status.')


def run():
    """Run one backup and record the outcome. Returns the saved status."""
    import workspace_time
    now = datetime.now(timezone.utc)
    today = str(workspace_time.today())
    state = status()
    attempts = state.get('attempts', 0) + 1 if state.get('attempt_day') == today else 1
    try:
        result = create()
    except BackupError as exc:
        log.error('Automatic backup failed: %s', exc)
        _record(attempt_day=today, attempts=attempts, last_attempt=now.isoformat(), last_failure=now.isoformat(), last_error=str(exc))
        raise
    except Exception as exc:
        log.exception('Automatic backup failed.')
        message = f'Backup failed ({type(exc).__name__}). Earlier backups were kept; check the container log.'
        _record(attempt_day=today, attempts=attempts, last_attempt=now.isoformat(), last_failure=now.isoformat(), last_error=message)
        raise BackupError(message) from exc
    log.info('Automatic backup saved: %s (%d bytes)', result['file'], result['bytes'])
    _record(attempt_day=today, attempts=attempts, last_attempt=now.isoformat(), last_success=now.isoformat(),
            success_day=today, last_file=result['file'], last_bytes=result['bytes'], last_error='')
    return status()


def due(state, now_local, scheduled, enabled=True):
    """Once per local day after the scheduled time; failures retry hourly, up to three attempts."""
    if not enabled:
        return False
    today = str(now_local.date())
    if (now_local.hour, now_local.minute) < scheduled or state.get('success_day') == today:
        return False
    if state.get('attempt_day') != today:
        return True
    if state.get('attempts', 0) >= MAX_ATTEMPTS:
        return False
    try:
        last = datetime.fromisoformat(state['last_attempt'])
    except (KeyError, TypeError, ValueError):
        return True
    return now_local.astimezone(timezone.utc) - last >= timedelta(hours=1)


def tick():
    import workspace_time
    if due(status(), datetime.now(workspace_time.zone()), scheduled_time(), keep() > 0):
        try:
            run()
        except BackupError:
            pass  # Already logged and recorded for the Settings page.


def start_scheduler(app):
    def loop():
        while True:
            time.sleep(60)
            try:
                with app.app_context():
                    tick()
            except Exception:
                app.logger.exception('Automatic backup scheduling failed; it will retry.')
    threading.Thread(target=loop, daemon=True, name='automatic-backups').start()


def register(app, auth):
    from app import fail
    from flask import jsonify

    def summary():
        folder, separate = directory()
        hour, minute = scheduled_time()
        found = archives(folder)
        return dict(enabled=keep() > 0, keep=keep(), time=f'{hour:02d}:{minute:02d}', directory=str(folder),
                    separate=separate, status=status(), count=len(found),
                    total_bytes=sum(p.stat().st_size for p in found),
                    latest=[dict(name=p.name, bytes=p.stat().st_size) for p in found[:3]])

    @app.get('/api/data/auto-backup')
    @auth('owner')
    def auto_backup_status():
        return jsonify(summary())

    @app.post('/api/data/auto-backup/run')
    @auth('owner')
    def auto_backup_now():
        try:
            run()
        except BackupError as exc:
            fail(str(exc), 503)
        return jsonify(summary())
