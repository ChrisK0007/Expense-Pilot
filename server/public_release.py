"""Public-client discovery, onboarding and explicit data lifecycle controls."""
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path
from flask import Response, g, jsonify, request, session


def instance_id():
    from billing import settings, save_settings
    from app import db
    value = settings('instance', {}).get('id')
    if not value:
        # Called at startup, outside request mutations.
        value = str(uuid.uuid4()); save_settings('instance', {'id': value}); db().commit()
    return value


def reauthenticate():
    import security
    data = request.get_json() or {}
    user = security.current_user()
    security.check_password(user, data.get('password'))
    if user['totp_enabled']: security.factor(user, data.get('code'))
    return data


def register(app, auth):
    from app import DATA, VERSION, audit, db, fail, one, rows
    with app.app_context(): instance_id()

    @app.get('/privacy')
    def privacy():
        return app.send_static_file('privacy.html')

    @app.get('/api/server-info')
    def server_info():
        return jsonify(product='Expense Pilot', api_version=1, minimum_client_api=1,
                       version=VERSION, setup=not bool(one('SELECT id FROM users LIMIT 1')),
                       setup_token_required=bool(os.environ.get('SETUP_TOKEN','')), privacy_path='/privacy', instance_id=instance_id())

    @app.get('/api/setup/checklist')
    @auth('owner')
    def checklist():
        from billing import business
        import ai_providers
        return jsonify(items=[
            dict(key='account', label='Owner account created', complete=True),
            dict(key='timezone', label='Confirm workspace timezone', complete=bool(one("SELECT key FROM billing_settings WHERE key='workspace'"))),
            dict(key='ai', label='Choose receipt AI or manual entry', complete=bool(one("SELECT key FROM billing_settings WHERE key='receipt_ai'")) or ai_providers.configured()),
            dict(key='business', label='Business details (if issuing invoices)', complete=bool(business()['name']), optional=True),
        ])

    @app.post('/api/data/backup')
    @auth('owner')
    def backup():
        from billing import save_settings
        db().execute('BEGIN IMMEDIATE'); reauthenticate()
        # Consume a recovery code before snapshotting through the read connection.
        # The archive must not restore a recovery code already used for this backup.
        db().commit(); db().execute('BEGIN IMMEDIATE')
        archive = tempfile.TemporaryFile()
        try:
            with tempfile.TemporaryDirectory() as directory:
                snapshot = Path(directory)/'rounded.sqlite'
                # A separate read connection observes the last committed state
                # while the write reservation prevents concurrent file deletion.
                source = sqlite3.connect(DATA/'rounded.sqlite')
                target = sqlite3.connect(snapshot)
                try: source.backup(target)
                finally: source.close(); target.close()
                checksums = {}
                with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
                    files = [('rounded.sqlite', snapshot), ('session.key', DATA/'session.key')]
                    files += [('receipts/'+x['id'], DATA/'receipts'/x['id']) for x in rows('SELECT id FROM receipts')]
                    for name, path in files:
                        digest = hashlib.sha256()
                        with path.open('rb') as source, zipped.open('data/'+name, 'w') as out:
                            for chunk in iter(lambda: source.read(1024*1024), b''): digest.update(chunk); out.write(chunk)
                        checksums['data/'+name] = digest.hexdigest()
                    zipped.writestr('manifest.json', json.dumps(dict(format=1, product='Expense Pilot', version=VERSION, sha256=checksums)))
            save_settings('release_setup', {'backup_downloaded': True}); audit('workspace backup downloaded', 'workspace'); db().commit()
        except Exception:
            archive.close(); db().rollback(); fail('Could not create a complete backup. Check server storage and receipt files.', 503)
        archive.seek(0)
        def stream():
            try:
                for chunk in iter(lambda: archive.read(1024*1024), b''): yield chunk
            finally: archive.close()
        return Response(stream(), mimetype='application/zip', headers={'Content-Disposition': 'attachment; filename="expense-pilot-backup.zip"'})

    @app.delete('/api/account')
    @auth()
    def delete_account():
        db().execute('BEGIN IMMEDIATE'); data = reauthenticate()
        if g.user['role'] == 'owner':
            if data.get('confirmation') != 'DELETE WORKSPACE': fail('Type DELETE WORKSPACE to permanently delete the owner account and all workspace records.')
            # No cascading overwrite of a live database file. One transaction
            # removes the workspace, revokes sessions and preserves schema history.
            floor = one('SELECT COALESCE(MAX(id),0)+1 AS n FROM users')['n']
            receipt_ids = [x['id'] for x in rows('SELECT id FROM receipts')]
            db().execute('PRAGMA defer_foreign_keys=ON')
            tables = [x['name'] for x in rows("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='schema_migrations'")]
            for table in tables:
                db().execute('DELETE FROM "'+table.replace('"', '""')+'"')
            from billing import save_settings
            save_settings('instance', {'id': str(uuid.uuid4()), 'owner_id_floor': floor})
            db().execute("INSERT INTO billing_counters VALUES ('invoice',1),('quote',1)")
            db().execute('INSERT INTO pocketsmith_connection(id) VALUES (1)')
            db().commit(); session.clear()
            from receipt_routes import remove_receipt_files
            for rid in receipt_ids: remove_receipt_files(rid)
        else:
            if data.get('confirmation') != 'DELETE ACCOUNT': fail('Type DELETE ACCOUNT to permanently remove your login.')
            # Tax agents share the owner's records; deleting a login does not
            # delete those records or the owner's evidence of financial changes.
            uid = g.user['id']
            try:
                db().execute('DELETE FROM users WHERE id=?', (uid,)); db().commit()
            except sqlite3.IntegrityError:
                db().rollback(); fail('This account owns records. Ask the server administrator to export and remove those records before deleting the account.', 409)
            session.clear()
        return jsonify(ok=True)
