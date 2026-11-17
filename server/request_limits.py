"""Durable per-account/per-source API quotas, shared by Gunicorn workers."""
import hashlib
import time
from flask import current_app, g, jsonify, request


def check():
    from app import db, one
    if not request.path.startswith('/api/') or request.method == 'OPTIONS':
        return None
    user = getattr(g, 'user', None)
    kind = 'account' if user else 'source'
    identity = str(user['id']) if user else str(request.remote_addr)
    limit = current_app.config['API_USER_LIMIT'] if user else current_app.config['API_ANONYMOUS_LIMIT']
    key = hashlib.sha256(('api|' + kind + '|' + identity).encode()).hexdigest()
    now = time.time()
    connection = db()
    connection.execute('BEGIN IMMEDIATE')
    try:
        connection.execute('DELETE FROM request_limits WHERE until<=?', (now,))
        row = one('SELECT count,until FROM request_limits WHERE key=?', (key,))
        if row and row['count'] >= limit:
            connection.rollback()
            response = jsonify(error='Too many requests. Wait before retrying.')
            response.status_code = 429
            response.headers['Retry-After'] = str(max(1, int(row['until'] - now) + 1))
            return response
        connection.execute('INSERT INTO request_limits(key,count,until) VALUES (?,1,?) '
                           'ON CONFLICT(key) DO UPDATE SET count=count+1', (key, now + 60))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return None
