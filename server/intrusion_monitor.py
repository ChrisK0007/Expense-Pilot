"""Passive fixed decoys only; never scan, retaliate or inspect request bodies."""
import hashlib
import hmac
import ipaddress
import time
from flask import current_app, g, jsonify, request

DECOYS = {'/.env': 'environment-file decoy', '/.git/config': 'repository-file decoy',
          '/wp-login.php': 'unused-login decoy', '/xmlrpc.php': 'unused-service decoy'}
AUTH_PATHS = {'/api/session', '/api/server-info', '/api/setup', '/api/login', '/api/login/2fa', '/api/logout',
              '/api/password-reset/request', '/api/password-reset/confirm'}


def source_key():
    try:
        address = ipaddress.ip_address(request.remote_addr)
        if getattr(address, 'ipv4_mapped', None):
            address = address.ipv4_mapped
    except (ValueError, TypeError):
        return None
    return hmac.new(current_app.secret_key.encode(), ('intrusion-source|' + str(address)).encode(), hashlib.sha256).hexdigest()


def mode():
    import billing
    value = billing.settings('intrusion', {'mode': 'monitor'}).get('mode')
    return value if value in ('off', 'monitor', 'block') else 'monitor'


def check():
    from app import db, one
    # Signed-in users and recovery/sign-in entry points are never IP-blocked.
    # This limits damage to legitimate people sharing a NAT or proxy address.
    if getattr(g, 'user', None):
        return None
    policy = mode()
    key = source_key()
    if policy == 'off' or not key:
        return None
    now = time.time()
    row = one('SELECT * FROM intrusion_sources WHERE key=?', (key,))
    exempt = request.path in AUTH_PATHS or not (request.path.startswith('/api/') or request.path.startswith('/quote/') or request.path in DECOYS)
    if policy == 'block' and row and row['blocked_until'] > now and not exempt:
        response = jsonify(error='Requests from this source are temporarily limited. Try later or sign in.')
        response.status_code = 429
        response.headers['Retry-After'] = str(max(1, int(row['blocked_until'] - now) + 1))
        return response
    if request.path not in DECOYS or request.method not in ('GET', 'HEAD'):
        return None
    db().execute('BEGIN IMMEDIATE')
    try:
        # Re-read under the write lock so thresholds are consistent across workers.
        row = one('SELECT * FROM intrusion_sources WHERE key=?', (key,))
        hits = row['hits'] + 1 if row and row['window_until'] > now else 1
        until = row['window_until'] if row and row['window_until'] > now else now + 600
        blocked = now + 900 if policy == 'block' and hits >= 5 else 0
        db().execute('DELETE FROM intrusion_sources WHERE last_seen<? AND blocked_until<=?', (now - 86400, now))
        db().execute('INSERT INTO intrusion_sources VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET hits=excluded.hits,window_until=excluded.window_until,blocked_until=excluded.blocked_until,last_seen=excluded.last_seen', (key, hits, until, blocked, now))
        db().execute('INSERT INTO intrusion_events(source_key,at,kind,action) VALUES (?,?,?,?)', (key, now, DECOYS[request.path], 'temporary block' if blocked else 'observed'))
        db().execute('DELETE FROM intrusion_events WHERE at<? OR id NOT IN (SELECT id FROM intrusion_events ORDER BY id DESC LIMIT 500)', (now - 7 * 86400,))
        db().execute('DELETE FROM intrusion_sources WHERE key NOT IN (SELECT key FROM intrusion_sources ORDER BY last_seen DESC LIMIT 1000)')
        db().commit()
    except BaseException:
        db().rollback()
        raise
    # All decoys remain ordinary not-found responses, with no secret content.
    return jsonify(error='Not found.'), 404


def register(app, auth):
    from app import db, rows, audit, fail
    import security
    import billing

    def reauthenticate(data):
        user = security.current_user()
        security.check_password(user, data.get('password'))
        if user['totp_enabled']:
            security.factor(user, data.get('code'))

    @app.route('/api/security/intrusion', methods=['GET', 'PUT'])
    @auth('owner')
    def settings():
        if request.method == 'PUT':
            data = request.get_json()
            value = data.get('mode')
            if value not in ('off', 'monitor', 'block'):
                fail('Choose Off, Monitor or Temporary blocks.')
            db().execute('BEGIN IMMEDIATE')
            reauthenticate(data)
            billing.save_settings('intrusion', {'mode': value})
            # Changing modes never revives earlier blocks or stale thresholds.
            db().execute('DELETE FROM intrusion_sources')
            if value == 'off':
                db().execute('DELETE FROM intrusion_events')
            audit('intrusion policy changed: ' + value, 'security')
            db().commit()
        db().execute('DELETE FROM intrusion_events WHERE at<?', (time.time() - 7 * 86400,))
        db().commit()
        return jsonify(mode=mode(), events=rows('SELECT id,source_key,at,kind,action FROM intrusion_events ORDER BY id DESC LIMIT 100'),
                       blocks=rows('SELECT key,blocked_until FROM intrusion_sources WHERE blocked_until>? ORDER BY blocked_until DESC', (time.time(),)))

    @app.post('/api/security/intrusion/unblock')
    @auth('owner')
    def unblock():
        data = request.get_json()
        key = data.get('source_key')
        if not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            fail('Select a recorded source.')
        db().execute('BEGIN IMMEDIATE')
        reauthenticate(data)
        db().execute('DELETE FROM intrusion_sources WHERE key=?', (key,))
        audit('intrusion source unblocked', 'security')
        db().commit()
        return jsonify(ok=True)
