"""Encrypted backup copies to an operator-mounted external destination."""
import base64
import hashlib
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from flask import jsonify
from workflow_core import body, now

MAGIC=b'EXPENSE-PILOT-BACKUP-1\n'
NAME=re.compile(r'expense-pilot-\d{8}T\d{6}Z-[0-9a-f]{8}\.epb')


def folder():
    from app import DATA
    value=os.environ.get('OFFSITE_BACKUP_DIR','').strip()
    if not value: return None
    if not Path(value).is_absolute(): raise ValueError('OFFSITE_BACKUP_DIR must be an absolute mounted path.')
    destination=Path(value).resolve()
    if not destination.is_absolute() or destination.is_relative_to(DATA.resolve()): raise ValueError('OFFSITE_BACKUP_DIR must be outside the app data directory.')
    if not destination.is_dir(): raise ValueError('The external backup mount is unavailable. Mount it before enabling copies.')
    return destination


def config():
    from billing import settings
    return settings('offsite_backup',dict(enabled=False,key_encrypted='',last_attempt=0,last_success='',last_file='',error='',test_requested=False,test_at='',test_result=''))


def encrypt(source,target,key):
    nonce=secrets.token_bytes(12);header=MAGIC+nonce
    encryptor=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor();encryptor.authenticate_additional_data(header)
    with open(source,'rb') as inp,open(target,'xb') as out:
        os.chmod(target,0o600);out.write(header)
        for chunk in iter(lambda:inp.read(1024*1024),b''): out.write(encryptor.update(chunk))
        out.write(encryptor.finalize());out.write(encryptor.tag);out.flush();os.fsync(out.fileno())


def decrypt(source,target,key):
    with open(source,'rb') as inp:
        length=os.fstat(inp.fileno()).st_size
        if length<len(MAGIC)+12+16 or length>100*1024**3: raise ValueError('Invalid encrypted backup size.')
        header=inp.read(len(MAGIC)+12)
        if not header.startswith(MAGIC): raise ValueError('Unsupported encrypted backup format.')
        inp.seek(-16,2);tag=inp.read(16);inp.seek(len(header))
        decryptor=Cipher(algorithms.AES(key),modes.GCM(header[-12:],tag)).decryptor();decryptor.authenticate_additional_data(header)
        remaining=length-len(header)-16
        try:
            with open(target,'xb') as out:
                os.chmod(target,0o600)
                while remaining:
                    chunk=inp.read(min(1024*1024,remaining))
                    if not chunk: raise ValueError('Encrypted backup is incomplete.')
                    remaining-=len(chunk);out.write(decryptor.update(chunk))
                out.write(decryptor.finalize())
        except Exception:
            Path(target).unlink(missing_ok=True);raise


def restore_test(path,key,staging):
    from restore_backup import restore
    import sqlite3
    decrypted=Path(staging)/'restore.zip';destination=Path(staging)/'restored'
    decrypt(path,decrypted,key);restore(decrypted,destination)
    with sqlite3.connect(destination/'rounded.sqlite') as connection:
        connection.execute('PRAGMA foreign_keys=ON')
        count=connection.execute('SELECT COUNT(*) FROM expenses').fetchone()[0]
        if connection.execute('SELECT COUNT(*) FROM login_sessions').fetchone()[0]: raise ValueError('Restored sessions were not revoked.')
    return f'Restored into an isolated temporary directory; database, attachment checksums and {count} expense record(s) verified. Live records were not changed.'


def tick():
    from app import DATA, VERSION, db
    from billing import save_settings, secret_box
    from auto_backup import write_archive, verify_archive, _required_bytes
    import shutil
    from datetime import datetime, timezone
    saved=config()
    if not saved.get('enabled') or not saved.get('key_encrypted'): return
    test=bool(saved.get('test_requested'))
    if not test and time.time()-saved.get('last_attempt',0)<86400: return
    saved.update(last_attempt=time.time(),test_requested=False);save_settings('offsite_backup',saved);db().commit()
    temporary=None
    try:
        destination=folder()
        if not destination: raise ValueError('Configure an external backup mount first.')
        key=base64.urlsafe_b64decode(secret_box().decrypt(saved['key_encrypted'].encode()))
        needed=_required_bytes(DATA)*3
        if shutil.disk_usage(DATA).free<needed or shutil.disk_usage(destination).free<needed//3: raise ValueError('Insufficient free space for an encrypted copy and isolated restore test.')
        with tempfile.TemporaryDirectory(prefix='.offsite-',dir=DATA) as staging:
            if test:
                name=saved.get('last_file','')
                if not NAME.fullmatch(name) or not (destination/name).is_file() or (destination/name).is_symlink(): raise ValueError('Create an encrypted copy before testing restore.')
                saved['test_result']=restore_test(destination/name,key,staging);saved['test_at']=now()
            else:
                source=Path(staging)/'snapshot.zip';manifest=write_archive(source,DATA,VERSION,verify=True);verify_archive(source,manifest)
                name='expense-pilot-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+secrets.token_hex(4)+'.epb'
                temporary=destination/(name+'.partial');encrypt(source,temporary,key)
                saved['test_result']=restore_test(temporary,key,staging);saved['test_at']=now()
                os.replace(temporary,destination/name);temporary=None
                saved.update(last_file=name,last_success=now())
                copies=sorted((p for p in destination.iterdir() if NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()),key=lambda p:p.name,reverse=True)
                for old in copies[7:]: old.unlink()
        saved['error']=''
    except Exception as exc:
        saved['error']=str(exc)[:500] if isinstance(exc,ValueError) else 'Encrypted copy or restore verification failed. Check the external mount, free space and recovery key. Existing copies were kept.'
    finally:
        if temporary: temporary.unlink(missing_ok=True)
        current=config();current.update({k:saved.get(k,'') for k in ('last_attempt','last_success','last_file','error','test_at','test_result')})
        save_settings('offsite_backup',current);db().commit()


def register(app,auth):
    @app.get('/api/workflows/offsite-backup', endpoint='offsite_backup_status')
    @auth('owner')
    def status():
        saved=config();saved.pop('key_encrypted',None)
        try: mounted=folder() is not None;error=''
        except ValueError as exc: mounted=False;error=str(exc)
        return jsonify(**saved,mounted=mounted,mount_error=error,key_saved=bool(config().get('key_encrypted')))

    @app.post('/api/workflows/offsite-backup/key', endpoint='offsite_backup_key')
    @auth('owner')
    def key():
        from app import db
        from billing import save_settings, secret_box
        import security
        d=body();db().execute('BEGIN IMMEDIATE');user=security.current_user();security.check_password(user,d.get('password'))
        if user['totp_enabled']: security.factor(user,d.get('code'))
        saved=config()
        if saved.get('key_encrypted'): key=secret_box().decrypt(saved['key_encrypted'].encode()).decode()
        else:
            key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode();saved['key_encrypted']=secret_box().encrypt(key.encode()).decode()
            save_settings('offsite_backup',saved)
        db().commit();return jsonify(key=key)

    @app.post('/api/workflows/offsite-backup/<action>', endpoint='offsite_backup_change')
    @auth('owner')
    def change(action):
        from app import db, fail, audit
        from billing import save_settings
        d=body();saved=config()
        if action=='disable': saved['enabled']=False
        elif action in ('enable','copy','test'):
            try: mounted=folder()
            except ValueError as exc: fail(str(exc))
            if not mounted or not saved.get('key_encrypted'): fail('Mount the external destination and save your recovery key first.')
            if action=='enable':
                if d.get('key_saved') is not True: fail('Confirm you saved the recovery key outside this server.')
                saved.update(enabled=True,last_attempt=0)
            else:
                if not saved.get('enabled'): fail('Enable encrypted copies first.')
                if action=='copy': saved['last_attempt']=0
                else: saved['test_requested']=True
        else: fail('Unknown backup action.',404)
        save_settings('offsite_backup',saved);audit('external backup '+action,'encrypted');db().commit();return jsonify(ok=True)


if __name__=='__main__':
    import argparse
    import getpass
    parser=argparse.ArgumentParser(description='Decrypt an Expense Pilot backup. Then use restore_backup.py with an empty data directory.')
    parser.add_argument('archive');parser.add_argument('output');args=parser.parse_args()
    try:
        key=base64.urlsafe_b64decode(getpass.getpass('Recovery key: ').strip());decrypt(args.archive,args.output,key)
    except Exception: parser.exit(1,'Decryption failed. Check the recovery key and encrypted archive.\n')
    print('Decrypted ZIP written. Keep it private and use restore_backup.py to restore it.')
