"""Mailbox proof without changing login/recovery or existing session contracts."""
import hashlib
import hmac
import secrets
import time
from flask import current_app, g, jsonify, request


def digest(user, code):
    material = 'Expense Pilot email verification v1\\0' + str(user['id']) + '|' + str(user['version']) + '|' + user['email'] + '|' + code
    return hmac.new(current_app.secret_key.encode(), material.encode(), hashlib.sha256).hexdigest()


def register(app, auth):
    from app import db, one, fail, audit
    import billing
    import security

    @app.get('/api/security/email', endpoint='email_verification_status')
    @auth()
    def status():
        row = one('SELECT email,verified_at FROM email_verification WHERE user_id=?', (g.user['id'],))
        verified = bool(row and row['email'] == g.user['email'] and row['verified_at'])
        mail = billing.mail_settings()
        return jsonify(verified=verified, email=g.user['email'],
                       smtp_configured=bool(mail['host'] and mail['from_email']))

    @app.post('/api/security/email/send', endpoint='email_verification_send')
    @auth()
    def send():
        data = request.get_json()
        db().execute('BEGIN IMMEDIATE')
        user = security.current_user()
        security.check_password(user, data.get('password'))
        if user['totp_enabled']:
            security.factor(user, data.get('code'))
        mail = billing.mail_settings()
        if not mail['host'] or not mail['from_email']:
            fail('Configure email delivery before verifying your address.', 409)
        try:
            billing.email(user['email'], True)
        except ValueError:
            fail('Your account email is not valid. Use account recovery to correct it.', 409)
        now = time.time()
        row = one('SELECT * FROM email_verification WHERE user_id=?', (user['id'],))
        if row and row['email'] == user['email'] and row['verified_at']:
            db().commit()
            return jsonify(ok=True, verified=True)
        if row and row['send_until'] > now and row['send_count'] >= 3:
            fail('Verification emails are limited to three per hour. Try again later.', 429)
        count = row['send_count'] + 1 if row and row['send_until'] > now else 1
        until = row['send_until'] if row and row['send_until'] > now else now + 3600
        code = str(secrets.randbelow(100000000)).zfill(8)
        hashed = digest(user, code)
        db().execute('''INSERT INTO email_verification
            (user_id,email,challenge_hash,challenge_version,expires,send_count,send_until)
            VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            email=excluded.email,verified_at=0,challenge_hash=excluded.challenge_hash,
            challenge_version=excluded.challenge_version,expires=excluded.expires,
            attempts=0,send_count=excluded.send_count,send_until=excluded.send_until''',
            (user['id'], user['email'], hashed, user['version'], now + 900, count, until))
        db().commit()
        try:
            state, _ = billing.deliver(user['email'], 'Verify your Expense Pilot email address',
                'Your verification code is: ' + code + '\n\nIt expires in 15 minutes. '
                'Enter it in Settings → Security on your usual Expense Pilot server. '
                'Do not share this code. If you did not request it, ignore this email.')
        except Exception:
            state = 'failed'
        if state != 'sent':
            db().execute("UPDATE email_verification SET challenge_hash='',expires=0 WHERE user_id=? AND challenge_hash=?",
                         (user['id'], hashed))
            db().commit()
            fail('Verification delivery could not be confirmed. Check email settings before requesting another code.', 502)
        audit('email verification requested', user['id'])
        db().commit()
        return jsonify(ok=True)

    @app.post('/api/security/email/confirm', endpoint='email_verification_confirm')
    @auth()
    def confirm():
        data = request.get_json()
        code = data.get('code')
        db().execute('BEGIN IMMEDIATE')
        user = security.current_user()
        row = one('SELECT * FROM email_verification WHERE user_id=?', (user['id'],))
        if not row or not row['challenge_hash'] or row['email'] != user['email'] or row['challenge_version'] != user['version'] or row['expires'] <= time.time() or row['attempts'] >= 5:
            fail('Verification expired. Request a new code.', 400)
        valid = isinstance(code, str) and len(code) == 8 and code.isascii() and code.isdigit()
        if not valid or not secrets.compare_digest(row['challenge_hash'], digest(user, code)):
            db().execute('UPDATE email_verification SET attempts=attempts+1 WHERE user_id=?', (user['id'],))
            db().commit()
            fail('Incorrect verification code.', 400)
        db().execute("UPDATE email_verification SET verified_at=?,challenge_hash='',expires=0,attempts=0 WHERE user_id=?",
                     (time.time(), user['id']))
        audit('email ownership verified', user['id'])
        db().commit()
        return jsonify(ok=True, verified=True)
