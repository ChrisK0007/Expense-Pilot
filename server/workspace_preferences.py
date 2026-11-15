"""Owner dashboard and notification choices, with durable one-time email delivery."""
import hashlib
import json
import re
from flask import g, jsonify, request

EVENTS = ('quoteAccepted', 'invoicePaid', 'invoiceOverdue', 'emailFailure', 'receipts', 'bank', 'budgets')
DISMISSIBLE = {'invoicePaid', 'quoteAccepted', 'budgets'}
PANELS = ('chart', 'incoming', 'income', 'expenses', 'tax', 'invoices', 'allocation')


def defaults():
    return dict(dashboard=dict(basis='calendar', period='full', hidden=[]),
                notifications={key: dict(bell=True, email=False) for key in EVENTS})


def get(uid):
    from app import one
    row = one('SELECT * FROM workspace_preferences WHERE user_id=?', (uid,))
    data = defaults()
    if row:
        saved = json.loads(row['data'])
        data['dashboard'].update(saved.get('dashboard', {}))
        data['notifications'].update(saved.get('notifications', {}))
    return dict(**data, version=row['version'] if row else 0)


def validate(data):
    from app import fail
    dashboard = data.get('dashboard', {})
    alerts = data.get('notifications', {})
    if not isinstance(dashboard, dict) or not isinstance(alerts, dict): fail('Choose workspace preferences.')
    dashboard = {**defaults()['dashboard'], **{k:v for k,v in dashboard.items() if k in defaults()['dashboard']}}
    hidden = dashboard['hidden']
    if dashboard['basis'] not in ('calendar', 'financial') or dashboard['period'] not in ('full', 'ytd') or not isinstance(hidden, list) or any(x not in PANELS for x in hidden):
        fail('Choose supported dashboard options.')
    choices = {}
    for key in EVENTS:
        value = alerts.get(key, defaults()['notifications'][key])
        if not isinstance(value, dict) or any(type(value.get(k)) is not bool for k in ('bell','email')):
            fail('Choose email and bell notification options.')
        choices[key] = {k:value[k] for k in ('bell','email')}
    return dict(dashboard=dashboard, notifications=choices)


def process_emails():
    from app import rows, db
    from billing import deliver, mail_settings, now
    from notifications import collect
    if not mail_settings()['host']: return
    for user in rows("SELECT * FROM users WHERE role='owner' AND active=1"):
        config = get(user['id'])['notifications']
        for event in collect(user):
            if not config.get(event['kind'], {}).get('email'): continue
            cur = db().execute("INSERT OR IGNORE INTO owner_notification_emails(user_id,event_key,state,created_at) VALUES (?,?,'sending',?)", (user['id'], event['key'], now()))
            db().commit()
            if not cur.rowcount: continue
            # Reserve before SMTP. An uncertain result is never blindly retried.
            try:
                state, error = deliver(user['email'], 'Expense Pilot: ' + event['title'], event['details'] + '\n\nOpen Expense Pilot to view the record.', copy=False)
            except Exception:
                state, error = 'unknown', 'Check your mail provider before retrying.'
            db().execute('UPDATE owner_notification_emails SET state=?,error=? WHERE user_id=? AND event_key=?', (state, error, user['id'], event['key']))
            db().commit()


def bell_events(user):
    from app import one
    from notifications import collect

    config = get(user['id'])['notifications']
    for alert in collect(user):
        kind = alert['kind']
        if not config.get(kind, {}).get('bell'):
            continue
        if kind not in DISMISSIBLE:
            yield alert
            continue
        identity = alert['key']
        if kind == 'invoicePaid' and alert.get('item'):
            payment = one('''SELECT id,created_at FROM billing_payments
                WHERE document_id=? AND reversed_at IS NULL ORDER BY id DESC LIMIT 1''', (alert['item'],))
            if payment:
                # A later payment can make a corrected invoice paid again.
                identity += f".{payment['id']}.{payment['created_at']}"
        yield {**alert, 'dismiss_key': hashlib.sha256(identity.encode()).hexdigest()}


def register(app, auth):
    @app.route('/api/workspace-preferences', methods=['GET', 'PUT'], endpoint='workspace_preference_options')
    @auth('owner')
    def preferences():
        from app import db, fail, audit
        from billing import body, mail_settings, now
        if request.method == 'PUT':
            payload = body(); data = validate(payload)
            db().execute('BEGIN IMMEDIATE'); old = get(g.user['id'])
            if payload.get('version') != old['version']: fail('Preferences changed. Reload this page.', 409)
            from notifications import collect
            # Enabling email applies to new events, without emailing a backlog.
            enabled = {k for k in EVENTS if data['notifications'][k]['email'] and not old['notifications'][k]['email']}
            if enabled:
                for event in collect(g.user):
                    if event['kind'] in enabled:
                        db().execute("INSERT OR IGNORE INTO owner_notification_emails(user_id,event_key,state,created_at) VALUES (?,?,'existing',?)", (g.user['id'], event['key'], now()))
            db().execute('INSERT INTO workspace_preferences(user_id,data) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data,version=version+1', (g.user['id'], json.dumps(data)))
            audit('workspace preferences updated', g.user['id']); db().commit()
        return jsonify(**get(g.user['id']), smtp_configured=bool(mail_settings()['host']))

    @app.get('/api/workspace-notifications', endpoint='workspace_notification_events')
    @auth('owner')
    def events():
        from app import rows

        cleared = {row['event_key'] for row in rows(
            'SELECT event_key FROM owner_bell_dismissals WHERE user_id=?', (g.user['id'],)
        )}
        return jsonify(items=[event for event in bell_events(g.user) if event.get('dismiss_key') not in cleared])

    @app.post('/api/workspace-notifications/dismiss')
    @auth('owner')
    def dismiss():
        from app import db, fail
        from billing import body

        key = body().get('key')
        if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key):
            fail('Choose a notification to dismiss.')
        db().execute('BEGIN IMMEDIATE')
        if any(event.get('dismiss_key') == key for event in bell_events(g.user)):
            db().execute('INSERT OR IGNORE INTO owner_bell_dismissals(user_id,event_key) VALUES (?,?)',
                         (g.user['id'], key))
        db().commit()
        return jsonify(ok=True)
