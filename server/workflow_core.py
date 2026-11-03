"""Small validation and optimistic-concurrency helpers for review tools."""
import hashlib
import json
from datetime import datetime, timezone
from flask import request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired


def now():
    return datetime.now(timezone.utc).isoformat()


def body():
    from app import fail
    value = request.get_json(silent=True)
    if not isinstance(value, dict): fail('Send an object with the review choices.')
    return value


def integer(value, label, low=0, high=1000000000):
    from app import fail
    if isinstance(value, bool): fail('Invalid '+label+'.')
    try:
        number = int(value)
        if str(number) != str(value) or not low <= number <= high: raise ValueError()
    except (ValueError, TypeError, OverflowError): fail('Invalid '+label+'.')
    return number


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':')).encode()).hexdigest()


def preview(kind, value):
    from app import app, g
    return URLSafeTimedSerializer(app.secret_key, salt='workflow-preview-v1').dumps([g.user['id'],kind,digest(value)])


def checked(token, kind, value):
    from app import app, g, fail
    try:
        saved = URLSafeTimedSerializer(app.secret_key, salt='workflow-preview-v1').loads(token or '', max_age=900)
    except (BadSignature, SignatureExpired, TypeError): fail('Preview expired. Review the changes again.',409)
    if saved != [g.user['id'],kind,digest(value)]: fail('The records or choices changed. Preview again before applying.',409)


def write_access():
    from app import can_write, fail
    if not can_write(): fail('Read-only access.',403)


def record_change(kind, before, after):
    from app import db, record_user_id, audit
    ident = db().execute('INSERT INTO workflow_changes(user_id,kind,before_json,after_json,at) VALUES (?,?,?,?,?)',
                         (record_user_id(),kind,json.dumps(before),json.dumps(after),now())).lastrowid
    audit(kind,ident)
    return ident


def fiscal(year):
    year = integer(year,'financial year',1900,2098)
    return year, f'{year}-07-01', f'{year+1}-06-30'


def selected_ids(value, limit=500):
    from app import fail
    if not isinstance(value,list) or not 1<=len(value)<=limit: fail('Select 1–'+str(limit)+' records.')
    result=[integer(v,'record ID',1) for v in value]
    if len(set(result))!=len(result): fail('Choose each record only once.')
    return result
