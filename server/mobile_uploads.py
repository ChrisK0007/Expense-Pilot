"""Durable mobile request acknowledgements, including deletion tombstones."""
import hashlib
import json
import uuid


def reference(value):
    from app import fail
    if value is None: return None
    try: return str(uuid.UUID(str(value)))
    except ValueError: fail('Invalid mobile upload reference.')


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def previous(uid, kind, ref, digest):
    from app import one, fail
    if not ref: return None
    row = one('SELECT * FROM mobile_upload_receipts WHERE user_id=? AND kind=? AND client_ref=?', (uid, kind, ref))
    if not row: return None
    if row['fingerprint'] != digest: fail('This upload reference was already used for different data. Keep the phone draft and review it.', 409)
    table = {'expense': 'expenses', 'receipt': 'receipts'}[kind]
    record = one(f'SELECT * FROM {table} WHERE id=? AND user_id=?', (row['record_id'], uid))
    if not record: fail('This record was deleted on the server. The delayed upload will not recreate it.', 409)
    return record


def remember(uid, kind, ref, digest, record_id):
    from app import db
    if ref:
        db().execute('INSERT INTO mobile_upload_receipts VALUES (?,?,?,?,?)', (uid, kind, ref, str(record_id), digest))


def ack(record_id, ref):
    return dict(id=record_id, client_ref=ref, stored=True)
