"""Verified-mailbox recovery; MFA, account roles and terminal recovery survive."""
import hashlib
import hmac
import ipaddress
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from flask import g, jsonify, request, session

_workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix='recovery-mail')
_slots = threading.BoundedSemaphore(8)
MESSAGE = 'If this account is eligible, a password reset email will be sent. Check your inbox or contact the server owner for terminal recovery.'


def link_base():
    import security
    value = security.invite_config().get('login_url', '')
    try:
        parsed = urlsplit(value)
        local = parsed.hostname == 'localhost'
        try:
            local = local or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            pass
        if (parsed.scheme != 'https' and not (parsed.scheme == 'http' and local)) or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
            return None
    except (ValueError, TypeError):
        return None
    return value.rstrip('/')


def eligible(user):
    from app import one
    import billing
    if not user or not user['active'] or user['role'] not in ('owner', 'tax_agent'):
        return False
    proof = one('SELECT email,verified_at FROM email_verification WHERE user_id=?', (user['id'],))
    mail = billing.mail_settings()
    return bool(proof and proof['verified_at'] and proof['email'] == user['email'] and mail['host'] and mail['from_email'] and link_base())


def reserve(identity, source):
    from app import db, one, app
    now = time.time()
    db().execute('DELETE FROM recovery_requests WHERE until<=?', (now,))
    keys = [(identity, 3)] + ([(source, 10)] if source else [])
    hashed = [(hmac.new(app.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest(), limit) for value, limit in keys]
    if any((row := one('SELECT count FROM recovery_requests WHERE key=?', (key,))) and row['count'] >= limit for key, limit in hashed):
        return False
    for key, _ in hashed:
        db().execute('INSERT INTO recovery_requests VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key, now + 3600))
    return True


def deliver(app, user_id, email, verifier, token, base):
    import billing
    from app import db
    with app.app_context():
        try:
            state, _ = billing.deliver(email, 'Reset your Expense Pilot password',
                'A password reset was requested for your account.\n\n' + base + '/#/reset-password?token=' + token +
                '\n\nThis link expires in 15 minutes and works once. Your authenticator or an unused recovery code is still required if two-factor authentication is enabled. '
                'Your password and sessions are unchanged until you complete the reset. If you did not request this, ignore this email.')
        except Exception:
            state = 'failed'
        if state != 'sent':
            db().execute('DELETE FROM password_resets WHERE user_id=? AND verifier=?', (user_id, verifier))
            db().commit()


def enqueue(*args):
    # Bound outstanding SMTP work; do not expose account existence through SMTP
    # response latency. Tokens exist only in memory until delivery finishes.
    if not _slots.acquire(blocking=False):
        return False
    def run():
        try:
            deliver(*args)
        finally:
            _slots.release()
    try:
        _workers.submit(run)
    except RuntimeError:
        _slots.release()
        return False
    return True


def issue(user):
    from app import app, db
    token = secrets.token_urlsafe(32)
    verifier = hashlib.sha256(token.encode()).hexdigest()
    db().execute('INSERT INTO password_resets VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET verifier=excluded.verifier,email=excluded.email,user_version=excluded.user_version,expires=excluded.expires',
                 (user['id'], verifier, user['email'], user['version'], time.time() + 900))
    db().commit()
    if not enqueue(app, user['id'], user['email'], verifier, token, link_base()):
        db().execute('DELETE FROM password_resets WHERE user_id=? AND verifier=?', (user['id'], verifier))
        db().commit()
        return False
    return True


def register(app, auth):
    from app import db, one, fail, newpass, audit
    import security

    @app.post('/api/password-reset/request')
    def request_reset():
        data = request.get_json()
        email = data.get('email')
        if not isinstance(email, str) or len(email) > 200:
            return jsonify(message=MESSAGE)
        email = email.strip().lower()
        db().execute('BEGIN IMMEDIATE')
        allowed = reserve('recovery-account|' + email, 'recovery-source|' + str(request.remote_addr))
        user = one('SELECT * FROM users WHERE email=?', (email,))
        if allowed and eligible(user):
            issue(user)
        else:
            db().commit()
        return jsonify(message=MESSAGE)

    @app.post('/api/users/<int:uid>/password-reset')
    @auth('owner')
    def owner_reset(uid):
        data = request.get_json()
        db().execute('BEGIN IMMEDIATE')
        owner = security.current_user()
        security.check_password(owner, data.get('password'))
        if owner['totp_enabled']:
            security.factor(owner, data.get('code'))
        user = one('SELECT * FROM users WHERE id=? AND role=?', (uid, 'tax_agent'))
        if not eligible(user):
            fail('Web recovery requires an active tax agent with a verified mailbox, configured SMTP and a secure login address. Terminal recovery remains available.', 409)
        if not reserve('recovery-account|' + user['email'], None):
            fail('Reset requests are limited to three per hour. Try later.', 429)
        audit('tax agent password reset requested', uid)
        queued = issue(user)
        if not queued:
            fail('Email delivery capacity is busy. Try later; existing access is unchanged.', 503)
        return jsonify(message='A reset email has been queued. Existing access remains unchanged until the agent completes the reset.')

    @app.post('/api/password-reset/confirm')
    def confirm_reset():
        data = request.get_json()
        token = data.get('token')
        if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            fail('This reset link is invalid or expired. Request a new link.')
        verifier = hashlib.sha256(token.encode()).hexdigest()
        db().execute('BEGIN IMMEDIATE')
        reset = one('SELECT * FROM password_resets WHERE verifier=?', (verifier,))
        user = one('SELECT * FROM users WHERE id=?', (reset['user_id'],)) if reset else None
        if not reset or reset['expires'] <= time.time() or not user or user['email'] != reset['email'] or user['version'] != reset['user_version'] or not eligible(user):
            fail('This reset link is invalid or expired. Request a new link.')
        hashed = newpass(data.get('password'))
        if security.password_matches(user['password'], data.get('password')):
            fail('Choose a new password different from your current password.')
        if user['totp_enabled']:
            security.factor(user, data.get('code'))
        db().execute("UPDATE users SET password=?,version=version+1,must_change_password=0,invite_expires=0 WHERE id=?", (hashed, user['id']))
        db().execute('DELETE FROM notification_devices WHERE user_id=?', (user['id'],))
        db().execute('DELETE FROM login_sessions WHERE user_id=?', (user['id'],))
        db().execute('DELETE FROM password_resets WHERE user_id=?', (user['id'],))
        audit('password recovered; sessions revoked', user['id'])
        db().commit()
        session.clear()
        return jsonify(ok=True)
