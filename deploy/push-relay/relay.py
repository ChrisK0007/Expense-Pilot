"""Optional APNs relay. Deploy privately with one app topic/environment per relay."""
import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from flask import Flask, request, jsonify

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4096
TITLES = {'receipts': 'Receipts ready for review', 'invoicePaid': 'Invoice marked paid',
          'invoiceOverdue': 'Invoice overdue', 'emailFailure': 'Email delivery needs attention',
          'budgets': 'Budget threshold reached', 'bank': 'Bank feed needs attention'}
SCREENS = {'receipts': 'receipts', 'invoicePaid': 'invoice', 'invoiceOverdue': 'invoice',
           'emailFailure': 'invoice', 'budgets': 'budgets', 'bank': 'bank'}
_lock = threading.Lock()
_jwt = ('', 0)
_client = httpx.Client(http2=True, timeout=10, follow_redirects=False)


def jwt():
    global _jwt
    with _lock:
        if _jwt[1] > time.time()-1200: return _jwt[0]
        def encode(value): return base64.urlsafe_b64encode(value).decode().rstrip('=')
        header = encode(json.dumps({'alg': 'ES256', 'kid': os.environ['APNS_KEY_ID']}).encode())
        claims = encode(json.dumps({'iss': os.environ['APNS_TEAM_ID'], 'iat': int(time.time())}).encode())
        signing = (header+'.'+claims).encode()
        key = serialization.load_pem_private_key(Path(os.environ['APNS_KEY_FILE']).read_bytes(), password=None)
        r, s = decode_dss_signature(key.sign(signing, ec.ECDSA(hashes.SHA256())))
        token = signing.decode()+'.'+encode(r.to_bytes(32, 'big')+s.to_bytes(32, 'big'))
        _jwt = (token, time.time()); return token


def db():
    path = Path(os.environ.get('RELAY_DATA', '/data')); path.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path/'relay.sqlite', timeout=10)
    conn.execute('CREATE TABLE IF NOT EXISTS deliveries(id TEXT PRIMARY KEY, sent REAL NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS limits(client TEXT PRIMARY KEY, window INTEGER NOT NULL, count INTEGER NOT NULL)')
    return conn


@app.post('/notify')
def notify():
    supplied = request.headers.get('Authorization', '').removeprefix('Bearer ')
    # A different random >=32-character token per container; keep this mapping
    # only on the relay. Revoking one container does not affect others.
    clients = json.loads(os.environ.get('PUSH_RELAY_CLIENTS', '{}'))
    client = next((name for name, token in clients.items() if len(token) >= 32 and secrets.compare_digest(token, supplied)), None)
    if client is None: return jsonify(error='Unauthorised'), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict): return jsonify(error='Invalid request'), 400
    for field, pattern in [('token', '[0-9a-f]{64,512}'), ('context', '[0-9a-f]{64}'), ('key', '[A-Za-z0-9_.:+ -]{1,160}'), ('item', '[A-Za-z0-9-]{0,80}')]:
        if not isinstance(data.get(field), str) or not re.fullmatch(pattern, data[field]): return jsonify(error='Invalid request'), 400
    kind = data.get('kind')
    if kind not in TITLES or data.get('screen') != SCREENS[kind] or type(data.get('sound')) is not bool: return jsonify(error='Invalid alert'), 400
    identity = hashlib.sha256((client+'|'+data['token']+'|'+data['context']+'|'+data['key']).encode()).hexdigest()
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM deliveries WHERE id=?', (identity,)).fetchone(): return jsonify(accepted=True)
        window = int(time.time()/3600)
        conn.execute('INSERT INTO limits VALUES (?,?,1) ON CONFLICT(client) DO UPDATE SET window=excluded.window,count=CASE WHEN limits.window=excluded.window THEN limits.count+1 ELSE 1 END', (client, window))
        if conn.execute('SELECT count FROM limits WHERE client=?', (client,)).fetchone()[0] > 300: return jsonify(error='Rate limited'), 429
    payload = {'aps': {'alert': {'title': TITLES[kind], 'body': 'Open Expense Pilot to review this update.'},
                       'thread-id': data['context']+'.'+data['screen']},
               'context': data['context'], 'screen': data['screen'], 'item': data['item'], 'kind': kind}
    if data['sound']: payload['aps']['sound'] = 'default'
    environment = os.environ.get('APNS_ENVIRONMENT', 'production')
    if environment not in ('production', 'development'): return jsonify(error='Relay configuration'), 503
    host = 'api.push.apple.com' if environment == 'production' else 'api.sandbox.push.apple.com'
    try:
        response = _client.post('https://'+host+'/3/device/'+data['token'], json=payload,
            headers={'authorization': 'bearer '+jwt(), 'apns-topic': os.environ['APNS_TOPIC'],
                     'apns-push-type': 'alert', 'apns-priority': '5', 'apns-expiration': str(int(time.time()+3600)),
                     'apns-collapse-id': identity})
        if response.status_code != 200:
            invalid = response.status_code == 410 or (response.status_code == 400 and response.json().get('reason') in ('BadDeviceToken', 'DeviceTokenNotForTopic'))
            return jsonify(error='Device registration expired' if invalid else 'Push rejected'), 410 if invalid else 502
    except Exception:
        return jsonify(error='Push service unavailable'), 503
    with db() as conn:
        conn.execute('INSERT OR REPLACE INTO deliveries VALUES (?,?)', (identity, time.time()))
        conn.execute('DELETE FROM deliveries WHERE sent<?', (time.time()-90*86400,))
    return jsonify(accepted=True)
