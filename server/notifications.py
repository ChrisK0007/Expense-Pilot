"""Current actionable events and optional, private push delivery.

No Apple credentials belong in the application container. The optional relay
accepts only fixed, generic alert types; amounts, names, addresses and receipts
never leave this server through this channel.
"""
import hashlib
import json
import os
import re
import threading
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from flask import g, jsonify, request, session
import workspace_time

KINDS = {'receipts', 'invoicePaid', 'invoiceOverdue', 'emailFailure', 'budgets', 'bank'}
TITLES = {'receipts': 'Documents ready for review', 'invoicePaid': 'Invoice marked paid',
          'invoiceOverdue': 'Invoice overdue', 'emailFailure': 'Email delivery needs attention',
          'budgets': 'Budget threshold reached', 'bank': 'Bank feed needs attention'}
BODIES = {'receipts': 'Open your document inbox to review the details.',
          'invoicePaid': 'An invoice has been marked paid. Tap to view it.',
          'invoiceOverdue': 'An invoice has an overdue balance. Tap to view it.',
          'emailFailure': 'An invoice email was not confirmed sent. Review its delivery status.',
          'budgets': 'A category budget has reached a spending threshold.',
          'bank': 'Open Bank feeds to review the connection and retry syncing.'}


def configured():
    url = os.environ.get('PUSH_RELAY_URL', '')
    from urllib.parse import urlsplit
    p = urlsplit(url)
    return bool(p.scheme == 'https' and p.hostname and not p.username and not p.password and not p.query and not p.fragment and len(os.environ.get('PUSH_RELAY_TOKEN', '')) >= 32)


def event(key, kind, screen, item='', details=None):
    return dict(key=key, kind=kind, screen=screen, item=str(item), title=TITLES[kind], body=BODIES[kind], details=details or BODIES[kind])


def collect(user):
    from app import rows, one
    from billing import hydrate
    from planning import budget_bounds, budget_list
    today = workspace_time.today()
    result = []
    # Batch receipts; accepting/deleting all receipts resolves the alert. A new
    # batch or a newly completed extraction gets a distinct fingerprint.
    receipts = rows('''SELECT r.id, d.scan_status FROM receipts r JOIN receipt_details d ON d.receipt_id=r.id
        WHERE r.user_id=? AND d.scan_status IN ('scanned','failed')
        AND NOT EXISTS (SELECT 1 FROM expenses e WHERE e.receipt_id=r.id)
        AND NOT EXISTS (SELECT 1 FROM employment_income i WHERE i.receipt_id=r.id) ORDER BY r.id''', (user['id'],))
    if receipts:
        fingerprint = hashlib.sha256(json.dumps(receipts, sort_keys=True).encode()).hexdigest()[:24]
        result.append(event('receipts.' + fingerprint, 'receipts', 'receipts', details=f"{len(receipts)} documents need review. Open your inbox."))
    if user['role'] not in ('owner', 'tax_agent'):
        return result
    for raw in rows("SELECT * FROM billing_documents WHERE kind='invoice' AND state='issued' ORDER BY id DESC"):
        doc = hydrate(raw)
        if doc['status'] == 'paid' and doc['paid_date'] and doc['paid_date'] >= (today - timedelta(days=7)).isoformat():
            result.append(event(f"paid.{doc['id']}.{doc['created_at']}", 'invoicePaid', 'invoice', doc['id'], f"Invoice {doc['number']} has been marked paid."))
        elif doc['status'] == 'overdue':
            result.append(event(f"overdue.{doc['id']}.{doc['created_at']}", 'invoiceOverdue', 'invoice', doc['id'], f"Invoice {doc['number']} has ${doc['balance_cents']/100:,.2f} outstanding."))
    if user['role'] == 'owner':
        for row in rows("SELECT id,document_id,created_at FROM billing_outbox WHERE state IN ('failed','unknown') ORDER BY id DESC LIMIT 50"):
            result.append(event(f"email.{row['id']}.{row['created_at']}", 'emailFailure', 'invoice', row['document_id']))
        connection = one('SELECT key_encrypted,last_error FROM pocketsmith_connection WHERE id=1')
        if connection and connection['key_encrypted'] and connection['last_error']:
            # Do not send raw provider errors, account numbers or provider keys.
            result.append(event('bank.connection', 'bank', 'bank'))
    for group in rows('SELECT DISTINCT month,period FROM category_budgets'):
        start, end = budget_bounds(group['month'], group['period'])
        if not start <= today.isoformat() < end:
            continue
        for budget in budget_list(group['month'], group['period']):
            threshold = 100 if budget['spent_cents'] >= budget['amount_cents'] else 80 if budget['spent_cents'] * 100 >= budget['amount_cents'] * 80 else 0
            if threshold:
                result.append(event(f"budget.{budget['id']}.{start}.{threshold}", 'budgets', 'budgets', budget['id'], f"{budget['category']} has reached {threshold}% of its {budget['period']} budget."))
    return result


def preferences(data):
    from app import fail
    keys = KINDS | {'enabled', 'remote', 'sounds', 'quietHours'}
    result = {k: data.get(k, False) for k in keys}
    if any(type(v) is not bool for v in result.values()):
        fail('Use on/off notification settings.')
    for k in ('quietStart', 'quietEnd'):
        v = data.get(k, 0)
        if type(v) is not int or not 0 <= v < 1440:
            fail('Choose a valid notification time.')
        result[k] = v
    zone = data.get('timezone', '')
    try: ZoneInfo(zone)
    except (ValueError, TypeError, ZoneInfoNotFoundError): fail('Choose a valid notification timezone.')
    result['timezone'] = zone
    return result


def register(app, auth):
    from app import db, fail, one

    @app.get('/api/notifications/events')
    @auth()
    def events():
        return jsonify(collect(g.user))

    @app.get('/api/notifications/budget/<int:bid>')
    @auth('owner', 'tax_agent')
    def budget_detail(bid):
        from planning import budget_list
        row = one('SELECT month,period FROM category_budgets WHERE id=?', (bid,))
        if not row: fail('This budget was deleted.', 404)
        return jsonify(next(x for x in budget_list(row['month'], row['period']) if x['id'] == bid))

    @app.route('/api/notifications/device', methods=['PUT', 'DELETE'])
    @auth()
    def device():
        data = request.get_json()
        if not isinstance(data, dict): fail('Expected notification settings.')
        try: installation = str(uuid.UUID(data.get('installation', '')))
        except (ValueError, TypeError, AttributeError): fail('Use a valid installation reference.')
        uid = g.user['id']
        if request.method == 'DELETE':
            db().execute('DELETE FROM notification_devices WHERE installation=? AND user_id=?', (installation, uid)); db().commit()
            return jsonify(ok=True)
        if not configured(): fail('This server has no push relay configured.', 409)
        token, context = data.get('token'), data.get('context')
        if not isinstance(token, str) or not re.fullmatch('[0-9a-f]{64,512}', token): fail('Use a valid push token.')
        if not isinstance(context, str) or not re.fullmatch('[0-9a-f]{64}', context): fail('Use a valid notification account reference.')
        prefs = preferences(data)
        db().execute('BEGIN IMMEDIATE')
        prior = one('SELECT * FROM notification_devices WHERE installation=?', (installation,))
        if prior and prior['user_id'] != uid: fail('This installation belongs to another account. Sign out there first.', 409)
        if not prior and one('SELECT COUNT(*) AS n FROM notification_devices WHERE user_id=?', (uid,))['n'] >= 20:
            fail('Too many notification devices.', 409)
        # Token rotation keeps delivered-event history; a workspace/account change
        # starts a fresh history and never inherits a different user's events.
        db().execute('DELETE FROM notification_devices WHERE token=? AND user_id=? AND installation!=?', (token, uid, installation))
        if one('SELECT 1 FROM notification_devices WHERE token=? AND user_id!=?', (token, uid)):
            fail('Sign out of the previous notification account first.', 409)
        sid = hashlib.sha256(session['sid'].encode()).hexdigest()
        db().execute('''INSERT INTO notification_devices(installation,user_id,user_version,session_hash,context,token,preferences,expires)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(installation) DO UPDATE SET
            user_version=excluded.user_version,session_hash=excluded.session_hash,context=excluded.context,
            token=excluded.token,preferences=excluded.preferences,expires=excluded.expires''',
            (installation, uid, g.user['version'], sid, context, token, json.dumps(prefs), time.time() + 30*86400))
        db().commit()
        return jsonify(ok=True)


def quiet(prefs, now):
    if not prefs['quietHours'] or prefs['quietStart'] == prefs['quietEnd']: return False
    local = datetime.fromtimestamp(now, ZoneInfo(prefs['timezone']))
    value = local.hour * 60 + local.minute
    start, end = prefs['quietStart'], prefs['quietEnd']
    return start <= value < end if start < end else value >= start or value < end


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def deliver(device, item):
    # Generic text is selected by the relay. No URLs or arbitrary message text.
    payload = dict(token=device['token'], context=device['context'], key=item['key'],
                   kind=item['kind'], screen=item['screen'], item=item['item'],
                   sound=json.loads(device['preferences'])['sounds'])
    req = urllib.request.Request(os.environ['PUSH_RELAY_URL'], data=json.dumps(payload).encode(), method='POST',
                                 headers={'Authorization': 'Bearer ' + os.environ['PUSH_RELAY_TOKEN'], 'Content-Type': 'application/json'})
    with urllib.request.build_opener(NoRedirect).open(req, timeout=10) as response:
        result = json.loads(response.read(4096))
        if result.get('accepted') is not True: raise ValueError('Push was not accepted')


def run_once():
    from app import db, rows, one
    if not configured(): return
    now = time.time()
    db().execute('DELETE FROM notification_devices WHERE expires<? OR user_id IN (SELECT id FROM users WHERE active=0 OR version!=notification_devices.user_version)', (now,))
    db().commit()
    for candidate in rows('SELECT installation FROM notification_devices WHERE next_attempt<=? AND lease_until<=?', (now, now)):
        db().execute('BEGIN IMMEDIATE')
        changed = db().execute('UPDATE notification_devices SET lease_until=? WHERE installation=? AND lease_until<=? AND next_attempt<=?', (now+300, candidate['installation'], now, now)).rowcount
        db().commit()
        if not changed: continue
        device = one('SELECT * FROM notification_devices WHERE installation=?', (candidate['installation'],))
        if not device: continue
        retry = 60
        try:
            user = one("SELECT * FROM users WHERE id=? AND active=1 AND version=? AND role IN ('owner','tax_agent')", (device['user_id'], device['user_version']))
            # Session revocation (logout/password change) immediately stops pushes.
            # Expired sessions require opening/signing into the app again.
            valid_session = one('SELECT 1 FROM login_sessions WHERE token_hash=? AND user_id=? AND kind=? AND expires>?', (device['session_hash'], device['user_id'], 'auth', now))
            prefs = json.loads(device['preferences'])
            if not user or not valid_session or not prefs['enabled'] or not prefs['remote'] or quiet(prefs, now): continue
            seen = json.loads(device['seen'])
            items = collect(user)
            active = {item['key'] for item in items}
            # Keep historical one-shot keys for 90 days. Bank errors can recur
            # after a successful sync and should alert again when that happens.
            if 'bank.connection' not in active: seen.pop('bank.connection', None)
            seen = {k: v for k,v in seen.items() if v >= now-90*86400}
            for item in [x for x in items if prefs[x['kind']] and x['key'] not in seen][:10]:
                # Recheck registration after potentially slow previous deliveries.
                if not one('SELECT 1 FROM notification_devices WHERE installation=? AND token=? AND preferences=?', (device['installation'], device['token'], device['preferences'])): break
                try:
                    deliver(device, item)
                except urllib.error.HTTPError as exc:
                    if exc.code == 410:
                        db().execute('DELETE FROM notification_devices WHERE installation=? AND token=?', (device['installation'], device['token'])); db().commit(); break
                    raise
                seen[item['key']] = now
                db().execute('UPDATE notification_devices SET seen=?,failures=0 WHERE installation=? AND token=?', (json.dumps(seen), device['installation'], device['token'])); db().commit()
        except Exception:
            db().rollback()
            retry = min(3600, 60 * 2**min(device['failures']+1, 6))
            db().execute('UPDATE notification_devices SET failures=failures+1 WHERE installation=?', (device['installation'],)); db().commit()
        finally:
            db().execute('UPDATE notification_devices SET next_attempt=?,lease_until=0 WHERE installation=?', (time.time()+retry, device['installation'])); db().commit()


def start_scheduler(app):
    def run():
        while True:
            try:
                with app.app_context(): run_once()
            except Exception:
                app.logger.warning('Notification delivery will retry; no records were changed.')
            time.sleep(60)
    threading.Thread(target=run, daemon=True, name='notification-delivery').start()
