"""Validate and restore an Expense Pilot ZIP into a new, empty data volume.

Run in a one-off container with the app stopped; existing databases are never replaced.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import zipfile


def restore(archive, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()): raise ValueError('Restore requires an empty data directory. Keep the original volume as your rollback copy.')
    with zipfile.ZipFile(archive) as source, tempfile.TemporaryDirectory(dir=destination.parent) as folder:
        root = Path(folder)
        names = source.namelist()
        if len(names) != len(set(names)) or 'manifest.json' not in names: raise ValueError('Invalid backup manifest or duplicate files.')
        if source.getinfo('manifest.json').file_size > 8 * 1024 * 1024: raise ValueError('Backup manifest is too large.')
        manifest = json.loads(source.read('manifest.json'))
        checks = manifest.get('sha256', {})
        if manifest.get('format') != 1 or manifest.get('product') != 'Expense Pilot' or not isinstance(checks, dict): raise ValueError('Unsupported backup format.')
        if set(names) != set(checks) | {'manifest.json'} or not {'data/rounded.sqlite', 'data/session.key'} <= set(checks): raise ValueError('Incomplete backup.')
        if sum(x.file_size for x in source.infolist()) > 100 * 1024**3: raise ValueError('Backup exceeds the 100 GB restore limit.')
        for name, expected in checks.items():
            if name not in ('data/rounded.sqlite', 'data/session.key') and not re.fullmatch(r'data/receipts/[0-9a-f]{40}', name): raise ValueError('Unexpected backup path.')
            target = root/name; target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with source.open(name) as inp, target.open('xb') as out:
                for chunk in iter(lambda: inp.read(1024*1024), b''): digest.update(chunk); out.write(chunk)
            if digest.hexdigest() != expected: raise ValueError('Backup checksum failed.')
        con = sqlite3.connect(root/'data/rounded.sqlite')
        try:
            if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or con.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Backup database failed integrity validation.')
            known = {p.stem: hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).parent/'migrations').glob('m[0-9]*.py')}
            for name, checksum in con.execute('SELECT version,checksum FROM schema_migrations'):
                if known.get(name) != checksum: raise ValueError('Use an application image compatible with this backup version.')
            receipts = {row[0] for row in con.execute('SELECT id FROM receipts')}
            if receipts != {name.split('/')[-1] for name in checks if name.startswith('data/receipts/')}: raise ValueError('Receipt files do not match the backup database.')
            # Restored sessions must sign in again; credentials and 2FA remain valid.
            con.execute('DELETE FROM login_sessions'); con.commit()
        finally: con.close()
        (root/'data/receipts').mkdir(exist_ok=True)
        created = []
        try:
            for item in (root/'data').iterdir():
                target = destination/item.name
                if item.is_dir(): shutil.copytree(item, target)
                else: shutil.copyfile(item, target); target.chmod(0o600)
                created.append(target)
        except Exception:
            for item in created:
                if item.is_dir(): shutil.rmtree(item)
                else: item.unlink(missing_ok=True)
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive'); parser.add_argument('--data', default=os.environ.get('DATA_DIR', '/data'))
    args = parser.parse_args()
    try: restore(args.archive, args.data)
    except (ValueError, OSError, zipfile.BadZipFile, sqlite3.DatabaseError) as exc: parser.exit(1, str(exc)+'\n')
    print('Backup verified and restored. Start Expense Pilot and sign in again.')
