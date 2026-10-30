"""Successful sign-in history and a durable, coalesced SMTP outbox."""
import hashlib
import ipaddress
import time
from datetime import datetime, timezone
from flask import g, jsonify, request, session


def address():
    # Trusted-proxy middleware has already established remote_addr.
    try:
        return str(ipaddress.ip_address(request.remote_addr))
    except ValueError:
        return 'unknown'


def record(user, token_hash, device, at, sign_in):
    from app import db, one
    agent = ''.join(c for c in request.user_agent.string if c.isprintable())[:300]
    ip = address()
    db().execute('UPDATE login_sessions SET ip_address=?,user_agent=? WHERE token_hash=?', (ip, agent, token_hash))
    if not sign_in:
        return
    db().execute('DELETE FROM known_signin_ips WHERE last_seen<?',(at-180*86400,))
    previous = one('SELECT last_seen FROM known_signin_ips WHERE user_id=? AND ip=?', (user['id'], ip))
    fresh = not previous or previous['last_seen'] < at - 180*86400
    pref = one('SELECT signin_emails FROM security_preferences WHERE user_id=?', (user['id'],))
    enabled = not pref or pref['signin_emails']
    db().execute('INSERT INTO known_signin_ips VALUES (?,?,?,?) ON CONFLICT(user_id,ip) DO UPDATE SET last_seen=excluded.last_seen', (user['id'], ip, at, at))
    db().execute('INSERT INTO signin_events(user_id,ip,device,user_agent,at,is_new,state) VALUES (?,?,?,?,?,?,?)',
                 (user['id'], ip, device or 'Browser', agent, at, int(fresh), 'pending' if fresh and enabled else 'recorded'))
    db().execute('DELETE FROM signin_events WHERE at<? AND state NOT IN (\'pending\',\'sending\')', (at-180*86400,))


def process():
    """Reserve before network I/O. A crashed/ambiguous send is never retried."""
    from app import db, rows, one
    import billing
    now = time.time()
    db().execute('BEGIN IMMEDIATE')
    db().execute("UPDATE signin_events SET state='unknown',error='Delivery was interrupted; it may have arrived.' WHERE state='sending' AND sent_at<?", (now-300,))
    db().execute("UPDATE signin_events SET state='expired',error='Notification expired after 24 hours.' WHERE state='pending' AND at<?", (now-86400,))
    candidates = rows("SELECT DISTINCT user_id FROM signin_events WHERE state='pending' ORDER BY user_id LIMIT 20")
    db().commit()
    for candidate in candidates:
        uid = candidate['user_id']
        config = billing.mail_settings()
        if not config.get('host') or not config.get('from_email'):
            return
        db().execute('BEGIN IMMEDIATE')
        events = rows("SELECT * FROM signin_events WHERE user_id=? AND state='pending' ORDER BY at LIMIT 30", (uid,))
        user = one('SELECT * FROM users WHERE id=? AND active=1', (uid,))
        pref = one('SELECT signin_emails FROM security_preferences WHERE user_id=?', (uid,))
        if not user or pref and not pref['signin_emails']:
            db().execute("UPDATE signin_events SET state='disabled' WHERE user_id=? AND state='pending'", (uid,))
            db().commit(); continue
        last = one("SELECT MAX(sent_at) AS at FROM signin_events WHERE user_id=? AND state IN ('sent','sending','unknown','failed')", (uid,))['at'] or 0
        if not events or last > now-3600:
            db().commit(); continue
        ids = [e['id'] for e in events]
        marks = ','.join('?' for _ in ids)
        db().execute("UPDATE signin_events SET state='sending',sent_at=? WHERE id IN ("+marks+')', [now]+ids)
        db().commit()
        lines = ['A successful sign-in to your Expense Pilot account used a new IP address.', '', 'Account: '+user['email'], '']
        for e in events:
            lines += [datetime.fromtimestamp(e['at'], timezone.utc).isoformat()+' (UTC)', 'IP: '+e['ip'], 'Device: '+e['device'], 'Browser/app: '+e['user_agent'], '']
        lines += ['If this was you, no action is needed. Mobile networks and VPNs can change your IP.',
                  'Otherwise, open your usual Expense Pilot address, review Settings → Security, sign out unfamiliar sessions and change your password.']
        try:
            state, error = billing.deliver(user['email'], 'Expense Pilot: sign-in from a new IP address', '\n'.join(lines))
        except Exception:
            state, error = 'unknown', 'Delivery could not be confirmed. Check your mail delivery configuration.'
        if state not in ('sent','failed','unknown'):
            state = 'unknown'
        db().execute('UPDATE signin_events SET state=?,error=? WHERE id IN ('+marks+')', [state, str(error)[:500]]+ids)
        db().commit()


def register(app, auth):
    @app.route('/api/security/sessions', methods=['GET','DELETE'], endpoint='signin_alerts_sessions')
    @auth()
    def sessions():
        from app import db, rows, one, fail, audit
        digest = hashlib.sha256(session['sid'].encode()).hexdigest()
        if request.method == 'DELETE':
            target = (request.get_json() or {}).get('id')
            if not isinstance(target, str) or not one("SELECT 1 FROM login_sessions WHERE token_hash=? AND user_id=? AND kind='auth'", (target, g.user['id'])):
                fail('Session not found.', 404)
            db().execute('DELETE FROM notification_devices WHERE session_hash=? AND user_id=?', (target, g.user['id']))
            db().execute('DELETE FROM login_sessions WHERE token_hash=? AND user_id=?', (target, g.user['id']))
            audit('session signed out', target[:12]); db().commit()
            if target == digest: session.clear()
            return jsonify(ok=True)
        records = rows("SELECT token_hash AS id,device_name,ip_address,user_agent,created_at,last_used,expires FROM login_sessions WHERE user_id=? AND kind='auth' AND expires>? AND (user_version=? OR (device_name='' AND user_version=0)) ORDER BY last_used DESC", (g.user['id'], time.time(), g.user['version']))
        for r in records: r['current'] = r['id'] == digest
        return jsonify(records)

    @app.route('/api/security/signins', methods=['GET','PUT'], endpoint='signin_alerts_signins')
    @auth()
    def signins():
        from app import db, rows, one, fail
        if request.method == 'PUT':
            enabled = (request.get_json() or {}).get('enabled')
            if not isinstance(enabled, bool): fail('Choose whether to email new-IP sign-ins.')
            db().execute('INSERT INTO security_preferences VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET signin_emails=excluded.signin_emails', (g.user['id'], int(enabled)))
            if not enabled: db().execute("UPDATE signin_events SET state='disabled' WHERE user_id=? AND state='pending'", (g.user['id'],))
            db().commit()
        pref = one('SELECT signin_emails FROM security_preferences WHERE user_id=?', (g.user['id'],))
        import billing
        config = billing.mail_settings()
        return jsonify(enabled=not pref or bool(pref['signin_emails']), smtp_configured=bool(config.get('host') and config.get('from_email')),
                       events=rows('SELECT id,ip,device,user_agent,at,is_new,state,error FROM signin_events WHERE user_id=? ORDER BY id DESC LIMIT 100', (g.user['id'],)))
