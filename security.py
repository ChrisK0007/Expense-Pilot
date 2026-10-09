"""Invitations and TOTP authentication. Secrets never enter session cookies or logs."""
import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import sqlite3
import struct
import time
from functools import wraps
from urllib.parse import quote, urlsplit
from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, g, request, jsonify, session, current_app
from PIL import Image, ImageDraw
from reportlab.graphics.barcode.qr import QrCodeWidget
from werkzeug.security import check_password_hash
import billing

bp = Blueprint('security', __name__, url_prefix='/api')
INVITE_HOURS = 48
CHALLENGE_SECONDS = 300


def clock():
    return time.time()


def migrate():
    columns = {
        'must_change_password': 'INTEGER NOT NULL DEFAULT 0',
        'invite_expires': 'REAL NOT NULL DEFAULT 0',
        'invite_status': "TEXT NOT NULL DEFAULT ''",
        'totp_enabled': 'INTEGER NOT NULL DEFAULT 0',
        'totp_secret': "TEXT NOT NULL DEFAULT ''",
        'totp_pending': "TEXT NOT NULL DEFAULT ''",
        'totp_pending_until': 'REAL NOT NULL DEFAULT 0',
        'totp_last_step': 'INTEGER NOT NULL DEFAULT -1',
        'recovery_hashes': "TEXT NOT NULL DEFAULT '[]'",
    }
    existing = {r['name'] for r in db().execute('PRAGMA table_info(users)')}
    for name, definition in columns.items():
        if name not in existing:
            db().execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
    db().execute("CREATE TABLE IF NOT EXISTS login_sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,kind TEXT NOT NULL,expires REAL NOT NULL)")
    db().execute("UPDATE users SET active=0,version=version+1 WHERE role='employee' AND active=1")
    db().commit()


def box():
    key = hashlib.sha256(b'Expense Pilot TOTP v1\0' + (DATA / 'session.key').read_bytes()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def totp(secret, step):
    """RFC 4226 dynamic truncation with RFC 6238's 30-second time counter."""
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f'{(struct.unpack(">I", digest[offset:offset+4])[0] & 0x7fffffff) % 1000000:06d}'


def valid_step(secret, code, last=-1):
    code = str(code or '').strip()
    if not re.fullmatch(r'[0-9]{6}', code):
        return None
    current = int(clock()) // 30
    for step in (current, current - 1, current + 1):
        if step > last and secrets.compare_digest(totp(secret, step), code):
            return step
    return None


def rate_key(kind, identity):
    return hashlib.sha256(f'{kind}|{identity}'.encode()).hexdigest()


def rate_check(key):
    row = one('SELECT * FROM attempts WHERE key=?', (key,))
    if row and row['until'] > clock() and row['count'] >= 8:
        fail('Too many attempts. Try again in 15 minutes.', 429)


def rate_failure(key):
    now = clock()
    db().execute('''INSERT INTO attempts(key,count,until) VALUES (?,1,?)
        ON CONFLICT(key) DO UPDATE SET count=CASE WHEN until>? THEN count+1 ELSE 1 END,
        until=CASE WHEN until>? THEN until ELSE excluded.until END''', (key, now + 900, now, now))
    db().commit()


def clear_rate(key):
    db().execute('DELETE FROM attempts WHERE key=?', (key,))


def revoke_session():
    token = session.get('sid')
    if isinstance(token, str):
        db().execute('DELETE FROM login_sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
    session.clear()


def session_valid(kind='auth'):
    token = session.get('sid')
    uid = session.get('uid' if kind == 'auth' else 'mfa_uid')
    if not isinstance(token, str) or not uid:
        return False
    return bool(one('SELECT 1 FROM login_sessions WHERE token_hash=? AND user_id=? AND kind=? AND expires>?',
                    (hashlib.sha256(token.encode()).hexdigest(), uid, kind, clock())))


def start_session(user, pending=False):
    revoke_session()
    token = secrets.token_urlsafe(32)
    expiry = clock() + (CHALLENGE_SECONDS if pending else 12 * 3600)
    db().execute('DELETE FROM login_sessions WHERE expires<=?', (clock(),))
    db().execute('INSERT INTO login_sessions VALUES (?,?,?,?)',
                 (hashlib.sha256(token.encode()).hexdigest(), user['id'], 'mfa' if pending else 'auth', expiry))
    db().commit()
    session.update(sid=token, csrf=secrets.token_hex(24))
    if pending:
        session.update(mfa_uid=user['id'], mfa_version=user['version'], mfa_until=expiry)
    else:
        session.update(uid=user['id'], version=user['version'])
        session.permanent = True


def reserve_password_attempt(email):
    # Reserve before the expensive hash check, atomically across concurrent requests.
    # Never trust a client-supplied forwarding header as a source address.
    keys = [(rate_key('password-account', email), 8),
            (rate_key('password-source', str(request.remote_addr)), 40)]
    db().execute('BEGIN IMMEDIATE')
    db().execute('DELETE FROM attempts WHERE until<=?', (clock(),))
    for key, limit in keys:
        row = one('SELECT * FROM attempts WHERE key=?', (key,))
        if row and row['count'] >= limit:
            db().rollback()
            fail('Too many attempts. Try again in 15 minutes.', 429)
    for key, _ in keys:
        db().execute("INSERT INTO attempts VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1", (key, clock()+900))
    db().commit()
    return keys[0][0]


def login_response():
    data = request.get_json() or {}
    email = str(data.get('email') or '').strip().lower()[:200]
    account_key = reserve_password_attempt(email)
    user = one('SELECT * FROM users WHERE email=?', (email,))
    if not user or not user['active'] or user['role'] not in ('owner', 'tax_agent') or not check_password_hash(user['password'], str(data.get('password', ''))[:256]):
        fail('Incorrect email or password.', 401)
    if user['must_change_password'] and user['invite_expires'] <= clock():
        fail('This temporary password has expired. Ask the owner to resend your invitation.', 401)
    clear_rate(account_key); db().commit()
    start_session(user, pending=bool(user['totp_enabled']))
    if user['totp_enabled']:
        return jsonify(mfa_required=True)
    return jsonify(ok=True, password_change_required=bool(user['must_change_password']))


def current_user():
    return one('SELECT * FROM users WHERE id=?', (g.user['id'],))


def check_password(user, value):
    key = rate_key('security-password', user['id'])
    rate_check(key)
    if not check_password_hash(user['password'], str(value or '')[:256]):
        rate_failure(key); fail('Current password is incorrect.', 403)
    clear_rate(key)


def factor(user, code):
    """Caller holds a write transaction, so replay and recovery use are atomic."""
    key = rate_key('factor', user['id']); rate_check(key)
    code = str(code or '').strip()
    try:
        secret = box().decrypt(user['totp_secret'].encode()).decode()
        step = valid_step(secret, code, user['totp_last_step'])
    except (InvalidToken, ValueError):
        fail('Authenticator settings could not be read. Use terminal account recovery.', 503)
    if step is not None:
        db().execute('UPDATE users SET totp_last_step=? WHERE id=?', (step, user['id']))
    else:
        digest = hashlib.sha256(code.replace('-', '').replace(' ', '').upper().encode()).hexdigest()
        hashes = json.loads(user['recovery_hashes'])
        match = next((v for v in hashes if secrets.compare_digest(v, digest)), None)
        if match is None:
            rate_failure(key); fail('Invalid or already used code. Try the next authenticator code or an unused recovery code.', 401)
        hashes.remove(match)
        db().execute('UPDATE users SET recovery_hashes=? WHERE id=?', (json.dumps(hashes), user['id']))
        audit('2FA recovery code used', user['id'])
    clear_rate(key)


@bp.post('/login/2fa')
def verify_login():
    if not session_valid('mfa') or session.get('mfa_until', 0) <= clock():
        session.clear(); fail('Sign-in expired. Enter your email and password again.', 401)
    db().execute('BEGIN IMMEDIATE')
    user = one('SELECT * FROM users WHERE id=?', (session['mfa_uid'],))
    if not user or not user['active'] or user['version'] != session.get('mfa_version') or not user['totp_enabled'] or user['role'] not in ('owner', 'tax_agent'):
        session.clear(); fail('Sign-in changed. Enter your email and password again.', 401)
    factor(user, (request.get_json() or {}).get('code'))
    db().commit(); start_session(user)
    return jsonify(ok=True, password_change_required=bool(user['must_change_password']))


def password_response():
    data = request.get_json() or {}
    db().execute('BEGIN IMMEDIATE'); user = current_user()
    check_password(user, data.get('current'))
    if check_password_hash(user['password'], str(data.get('password') or '')[:256]):
        fail('Choose a new password different from your current password.')
    hashed = newpass(data.get('password'))
    if user['totp_enabled']:
        factor(user, data.get('code'))
    db().execute("UPDATE users SET password=?,version=version+1,must_change_password=0,invite_expires=0,invite_status=CASE WHEN must_change_password=1 THEN 'accepted' ELSE invite_status END WHERE id=?", (hashed, user['id']))
    audit('password changed', user['id']); db().commit(); session.clear()
    return jsonify(ok=True)


def signed_in(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not g.user:
            fail('Please sign in.', 401)
        return fn(*args, **kwargs)
    return wrapped


@bp.get('/security')
@signed_in
def security_status():
    user = current_user()
    return jsonify(enabled=bool(user['totp_enabled']), recovery_remaining=len(json.loads(user['recovery_hashes'])), secure_cookies=bool(current_app.config['SESSION_COOKIE_SECURE']))


@bp.post('/security/2fa/setup')
@signed_in
def setup_totp():
    db().execute('BEGIN IMMEDIATE'); user = current_user()
    check_password(user, (request.get_json() or {}).get('password'))
    if user['totp_enabled']:
        fail('Two-factor authentication is already enabled.', 409)
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    db().execute('UPDATE users SET totp_pending=?,totp_pending_until=? WHERE id=?', (box().encrypt(secret.encode()).decode(), clock() + 600, user['id']))
    db().commit()
    uri = 'otpauth://totp/' + quote('Expense Pilot:' + user['email'], safe='') + '?secret=' + secret + '&issuer=Expense%20Pilot&algorithm=SHA1&digits=6&period=30'
    # Use the existing ReportLab QR implementation and render locally to PNG.
    qr = QrCodeWidget(uri, barLevel='M'); qr.qr.make(); count = qr.qr.getModuleCount(); scale = 6
    img = Image.new('RGB', ((count+8)*scale, (count+8)*scale), 'white'); draw = ImageDraw.Draw(img)
    for y in range(count):
        for x in range(count):
            if qr.qr.isDark(y, x):
                draw.rectangle(((x+4)*scale, (y+4)*scale, (x+5)*scale-1, (y+5)*scale-1), fill='black')
    out = io.BytesIO(); img.save(out, format='PNG')
    return jsonify(secret=secret, qr='data:image/png;base64,'+base64.b64encode(out.getvalue()).decode())


@bp.post('/security/2fa/confirm')
@signed_in
def confirm_totp():
    db().execute('BEGIN IMMEDIATE'); user = current_user()
    if user['totp_enabled'] or not user['totp_pending'] or user['totp_pending_until'] <= clock():
        fail('Setup expired or already completed. Start setup again.', 409)
    key = rate_key('factor', user['id']); rate_check(key)
    secret = box().decrypt(user['totp_pending'].encode()).decode()
    step = valid_step(secret, (request.get_json() or {}).get('code'))
    if step is None:
        rate_failure(key); fail('Enter the current six-digit code from your authenticator.', 400)
    codes = [secrets.token_hex(8).upper() for _ in range(10)]
    hashes = [hashlib.sha256(code.encode()).hexdigest() for code in codes]
    db().execute("UPDATE users SET totp_enabled=1,totp_secret=totp_pending,totp_pending='',totp_pending_until=0,totp_last_step=?,recovery_hashes=?,version=version+1 WHERE id=?", (step, json.dumps(hashes), user['id']))
    clear_rate(key); audit('2FA enabled', user['id']); db().commit()
    start_session(current_user())
    return jsonify(ok=True, recovery_codes=['-'.join(code[i:i+4] for i in range(0,16,4)) for code in codes], csrf=session['csrf'])


@bp.post('/security/2fa/disable')
@signed_in
def disable_totp():
    data = request.get_json() or {}; db().execute('BEGIN IMMEDIATE'); user = current_user()
    check_password(user, data.get('password'))
    if not user['totp_enabled']:
        fail('Two-factor authentication is not enabled.', 409)
    factor(user, data.get('code'))
    db().execute("UPDATE users SET totp_enabled=0,totp_secret='',totp_pending='',totp_pending_until=0,totp_last_step=-1,recovery_hashes='[]',version=version+1 WHERE id=?", (user['id'],))
    audit('2FA disabled', user['id']); db().commit(); start_session(current_user())
    return jsonify(ok=True, csrf=session['csrf'])


def invite_config():
    return billing.settings('access', {'login_url': ''})


@bp.route('/security/invitations', methods=['GET', 'PUT'])
@signed_in
def configure_invitations():
    if g.user['role'] != 'owner':
        fail('Only the owner can configure invitations.', 403)
    if request.method == 'PUT':
        url = str((request.get_json() or {}).get('login_url') or '').strip().rstrip('/')
        try:
            parsed = urlsplit(url); port = parsed.port
            if len(url)>500 or parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/') or any(c.isspace() or ord(c)<32 for c in url):
                raise ValueError()
        except ValueError:
            fail('Enter your Expense Pilot address, for example https://expenses.example.com, without a path or login details.')
        billing.save_settings('access', {'login_url': url}); audit('invitation address updated','security'); db().commit()
    config = invite_config(); mail = billing.mail_settings()
    return jsonify(**config, smtp_configured=bool(mail['host'] and mail['from_email']))


def invite_ready():
    config = invite_config(); mail = billing.mail_settings()
    if not config['login_url'] or not mail['host'] or not mail['from_email']:
        fail('Set your Expense Pilot login address and configure Email delivery in Settings before adding people.', 409)
    return config


def send_invitation(uid, password, config, version):
    user = one('SELECT * FROM users WHERE id=?',(uid,))
    message = (f"Hi {user['name']},\n\nYou have been invited to Expense Pilot.\n\n"
               f"Sign in: {config['login_url']}\nEmail: {user['email']}\nTemporary password: {password}\n\n"
               f"This password expires in {INVITE_HOURS} hours. You must choose a new password before accessing the workspace.\n"
               "You can then enable two-factor authentication in Settings using an authenticator app.\n\nExpense Pilot")
    try:
        status, error = billing.deliver(user['email'], 'Your Expense Pilot invitation', message)
    except ValueError:
        status, error = 'failed', 'Email delivery is not configured. Update Email delivery in Settings and resend the invitation.'
    db().execute('UPDATE users SET invite_status=? WHERE id=? AND version=? AND must_change_password=1', (status,uid,version))
    audit('account invitation '+status,uid); db().commit()
    return jsonify(ok=True, id=uid, invitation_status=status, message='Invitation sent.' if status=='sent' else 'Account created. '+error+' Resend generates a new temporary password.')


def create_user_response():
    config = invite_ready(); d = request.get_json() or {}; role = d.get('role')
    if role != 'tax_agent':
        fail('Invalid role.')
    name = textval(d.get('name'), 100)
    try:
        email = billing.email(d.get('email'), True)
    except ValueError as exc:
        fail(str(exc))
    if not name or any(ord(c)<32 for c in name):
        fail('Name is required.')
    permission = d.get('permission','read_only') if role=='tax_agent' else 'read_only'
    if permission not in ('read_only','read_write'):
        fail('Invalid tax-agent permission.')
    password = secrets.token_urlsafe(18)
    try:
        cursor = db().execute("INSERT INTO users(name,email,password,role,permission,must_change_password,invite_expires,invite_status) VALUES (?,?,?,?,?,1,?,'sending')", (name,email.lower(),newpass(password),role,permission,clock()+INVITE_HOURS*3600))
    except sqlite3.IntegrityError:
        fail('Email already exists. Resend the pending invitation from People & access.',409)
    uid = cursor.lastrowid; audit('user invited',uid); db().commit()
    return send_invitation(uid,password,config,1)


@bp.post('/users/<int:uid>/invite')
@signed_in
def resend_invitation(uid):
    if g.user['role']!='owner':
        fail('Only the owner can invite people.',403)
    config = invite_ready(); db().execute('BEGIN IMMEDIATE')
    user = one('SELECT * FROM users WHERE id=?',(uid,))
    if not user or user['role']!='tax_agent' or not user['active'] or not user['must_change_password']:
        fail('Only an active account with a pending invitation can be re-invited.',409)
    password = secrets.token_urlsafe(18)
    db().execute("UPDATE users SET password=?,version=version+1,invite_expires=?,invite_status='sending' WHERE id=?", (newpass(password),clock()+INVITE_HOURS*3600,uid))
    audit('account invitation resent',uid); db().commit()
    return send_invitation(uid,password,config,user['version']+1)


def register(app, **deps):
    globals().update(deps)
    with app.app_context():
        migrate()
    app.register_blueprint(bp)
