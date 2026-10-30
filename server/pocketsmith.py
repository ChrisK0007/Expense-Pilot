"""PocketSmith connection, durable source ledger and expense matching."""
import base64
import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from cryptography.fernet import Fernet, InvalidToken
from flask import jsonify, request
from pocketsmith_client import Client, FeedError
import workspace_time


def connection():
    return one('SELECT * FROM pocketsmith_connection WHERE id=1')


def box():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b'pocketsmith-v1:' + (DATA/'session.key').read_bytes()).digest()))


def key_for(c):
    if not c['key_encrypted']:
        raise FeedError('Connect PocketSmith in Settings first.')
    try:
        return box().decrypt(c['key_encrypted'].encode()).decode()
    except (InvalidToken, ValueError):
        raise FeedError('Reconnect PocketSmith: the saved key cannot be decrypted.') from None


def identifier(value):
    value = str(value)
    if not re.fullmatch('[1-9][0-9]{0,19}', value):
        raise FeedError('PocketSmith returned an invalid identifier.')
    return value


def iso_date(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise FeedError('PocketSmith returned an invalid transaction date.') from None


def currency(value):
    value = str(value or '').upper()
    if not re.fullmatch('[A-Z]{3}', value):
        raise FeedError('PocketSmith returned an invalid account currency.')
    return value


def account_data(client):
    me, _ = client.get('/me')
    if not isinstance(me, dict):
        raise FeedError('PocketSmith returned an invalid user.')
    uid = identifier(me.get('id'))
    accounts = []
    seen = set()
    for a in client.collection(f'/users/{uid}/transaction_accounts'):
        rid = identifier(a.get('id'))
        if rid in seen:
            raise FeedError('PocketSmith returned duplicate accounts.')
        seen.add(rid)
        institution = a.get('institution') or {}
        if not isinstance(institution, dict):
            raise FeedError('PocketSmith returned an invalid institution.')
        accounts.append((uid, rid, str(a.get('name') or 'Bank account')[:200],
                         str(institution.get('title') or '')[:100], currency(a.get('currency_code'))))
    return uid, str(me.get('name') or me.get('login') or 'PocketSmith')[:100], accounts


def public_connection():
    c = connection()
    return dict(connected=bool(c['key_encrypted']), display_name=c['display_name'],
                start_date=c['start_date'] or workspace_time.today().replace(day=1).isoformat(),
                auto_sync=bool(c['auto_sync']), last_sync=c['last_sync'], last_error=c['last_error'],
                syncing=c['lock_until'] > time.time(), retry_after=c['retry_after'], next_sync=c['next_sync'],
                version=c['version'], accounts=rows('SELECT * FROM pocketsmith_accounts WHERE remote_user_id=? ORDER BY name', (c['remote_user_id'],)))


def normalise(raw, account):
    rid = identifier(raw.get('id'))
    source_account = raw.get('transaction_account') or {}
    if not isinstance(source_account, dict) or str(source_account.get('id', account['remote_id'])) != account['remote_id']:
        raise FeedError('PocketSmith returned a transaction from a different account.')
    if source_account.get('currency_code') and currency(source_account['currency_code']) != account['currency']:
        raise FeedError('An account currency changed in PocketSmith. Refresh accounts in connection settings before syncing.')
    try:
        amount = Decimal(str(raw.get('amount')))
        if not amount.is_finite() or abs(amount) > 10000000:
            raise ValueError()
        cents = int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        raise FeedError('PocketSmith returned an invalid transaction amount.') from None
    status = raw.get('status')
    if status not in ('pending', 'posted'):
        raise FeedError('PocketSmith returned an unsupported transaction status (expected pending or posted). Nothing was synced.')
    category = raw.get('category') or {}
    if not isinstance(category, dict):
        raise FeedError('PocketSmith returned an invalid category.')
    # An unset transfer marker is not an invalid transaction status. Retain a
    # category's transfer protection when the transaction marker is absent/null;
    # an explicit transaction boolean takes precedence over the category.
    transfer = raw.get('is_transfer')
    if transfer is None:
        transfer = category.get('is_transfer')
    if transfer is None:
        transfer = False
    if not isinstance(transfer, bool):
        raise FeedError('PocketSmith returned an invalid transfer flag (expected true, false or null). Nothing was synced.')
    result = dict(remote_id=rid, feed_account_id=account['id'], date=iso_date(raw.get('date')),
                  payee=str(raw.get('payee') or raw.get('original_payee') or 'Bank transaction')[:200],
                  amount_cents=cents, currency=account['currency'], memo=str(raw.get('memo') or raw.get('note') or '')[:3000],
                  source_category=str(category.get('title') or '')[:200], source_status=status,
                  is_transfer=int(transfer), source_updated_at=str(raw.get('updated_at') or '')[:60])
    # Source timestamps and annotations can change without altering the financial record.
    material = {k: v for k, v in result.items() if k not in ('source_updated_at', 'memo', 'source_category')}
    result['fingerprint'] = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
    return result


def sync(manual=False):
    now = time.time()
    db().execute('BEGIN IMMEDIATE')
    c = connection()
    if not c['key_encrypted'] or (not manual and (not c['auto_sync'] or c['next_sync'] > now)):
        db().rollback()
        if manual:
            raise FeedError('Connect PocketSmith in Settings first.')
        return None
    if c['lock_until'] > now or c['retry_after'] > now or c['last_attempt'] + 15 > now:
        db().rollback()
        if manual:
            raise FeedError('Sync is already running or waiting to retry. Try again shortly.')
        return None
    accounts = rows('SELECT * FROM pocketsmith_accounts WHERE remote_user_id=? AND enabled=1 AND available=1', (c['remote_user_id'],))
    if not accounts:
        db().rollback()
        if manual:
            raise FeedError('Select at least one account in PocketSmith settings.')
        return None
    token = secrets.token_hex(16)
    db().execute('UPDATE pocketsmith_connection SET lock_token=?,lock_until=?,last_attempt=? WHERE id=1', (token, now+300, now))
    db().commit()
    try:
        client = Client(key_for(c))
        end = workspace_time.today().isoformat()
        fetched, seen = [], set()
        for a in accounts:
            for raw in client.collection(f"/transaction_accounts/{a['remote_id']}/transactions", {'start_date': c['start_date'], 'end_date': end}):
                row = normalise(raw, a)
                if row['remote_id'] in seen or not c['start_date'] <= row['date'] <= end:
                    raise FeedError('PocketSmith returned duplicate or out-of-range transactions. Nothing was synced.')
                seen.add(row['remote_id'])
                fetched.append(row)
                if len(fetched)>50000:
                    raise FeedError('Too many transactions across the selected accounts. Choose a later start date.')
        stamp = datetime.now(timezone.utc).isoformat()
        db().execute('BEGIN IMMEDIATE')
        current = connection()
        if current['version'] != c['version'] or current['lock_token'] != token:
            raise FeedError('Connection settings changed during sync. Run sync again.')
        added = 0
        for row in fetched:
            old = one('SELECT * FROM bank_transactions WHERE remote_user_id=? AND remote_id=?', (c['remote_user_id'], row['remote_id']))
            if old:
                linked = old['expense_id'] or one('SELECT id FROM bank_reconciliations WHERE bank_id=?',(old['id'],))
                changed = old['fingerprint'] != row['fingerprint'] or old['missing']
                db().execute('UPDATE bank_transactions SET ' + ','.join(k+'=?' for k in row) + ',last_seen=?,missing=0,changed=?,state=?,version=version+? WHERE id=?',
                             tuple(row.values()) + (stamp, int(bool(old['changed'] or (changed and linked))),
                              'review' if changed and old['state']=='ignored' else old['state'], int(bool(changed)), old['id']))
            else:
                db().execute('INSERT INTO bank_transactions ('+','.join(row)+',remote_user_id,last_seen) VALUES ('+','.join('?' for _ in range(len(row)+2))+')', tuple(row.values())+(c['remote_user_id'], stamp))
                added += 1
        for a in accounts:
            db().execute("UPDATE bank_transactions SET missing=1,changed=CASE WHEN expense_id IS NOT NULL OR EXISTS(SELECT 1 FROM bank_reconciliations r WHERE r.bank_id=bank_transactions.id) THEN 1 ELSE changed END,version=version+1 WHERE feed_account_id=? AND date BETWEEN ? AND ? AND last_seen<>? AND missing=0", (a['id'], c['start_date'], end, stamp))
        db().execute("UPDATE pocketsmith_connection SET last_sync=?,next_sync=?,retry_after=0,last_error='',lock_token='',lock_until=0 WHERE id=1", (stamp, time.time()+3600))
        import bank_matching
        matched=bank_matching.link_after_sync()
        audit('PocketSmith synced', f'{len(fetched)} transactions; {added} new; {matched} matched')
        db().commit()
        return dict(received=len(fetched), added=added, matched=matched)
    except Exception as exc:
        db().rollback()
        problem = exc if isinstance(exc, FeedError) else FeedError('Sync could not be completed. Nothing was imported; try again later.')
        delay = max(300, problem.retry_seconds)
        db().execute("UPDATE pocketsmith_connection SET last_error=?,next_sync=?,retry_after=?,lock_token='',lock_until=0 WHERE id=1 AND version=? AND lock_token=?",
                     (str(problem), time.time()+delay, time.time()+delay, c['version'], token))
        db().commit()
        raise problem from None


LEDGER = 'SELECT b.*,a.name AS account_name,a.institution,a.local_account_id FROM bank_transactions b JOIN pocketsmith_accounts a ON a.id=b.feed_account_id '


def transaction(tid, version=None):
    t = one(LEDGER+'WHERE b.id=?', (tid,))
    if not t:
        fail('Bank transaction not found.', 404)
    if version is not None and version != t['version']:
        fail('This transaction changed. Close and reopen it before continuing.', 409)
    return t


def eligible(t):
    if one('SELECT 1 FROM bank_reconciliations WHERE bank_id=?',(t['id'],)): fail('This transaction has a reconciliation. Undo it from Bank accounts → Matching options first.',409)
    if t['expense_id'] or t['missing'] or t['source_status']!='posted' or t['is_transfer'] or not t['amount_cents']:
        fail('Only an unlinked, posted purchase or refund can be added or matched.', 409)
    if not t['local_account_id']:
        fail('Map this bank account in PocketSmith settings first.', 409)


def matches(t):
    if t['currency']!='AUD' or t['missing'] or t['source_status']!='posted' or t['is_transfer'] or not t['amount_cents']:
        return []
    return rows("SELECT e.* FROM expenses e WHERE e.amount_cents=? AND abs(julianday(e.date)-julianday(?))<=3 AND (e.account_id=? OR e.account_id IS NULL) AND NOT EXISTS(SELECT 1 FROM bank_transactions b WHERE b.expense_id=e.id) AND NOT EXISTS(SELECT 1 FROM bank_reconciliations r WHERE r.expense_id=e.id) ORDER BY abs(julianday(e.date)-julianday(?)),e.id DESC LIMIT 30", (-t['amount_cents'], t['date'], t['local_account_id'], t['date']))


def attach(t, eid):
    try:
        db().execute("UPDATE bank_transactions SET expense_id=?,state='linked',changed=0,version=version+1 WHERE id=?", (eid, t['id']))
    except sqlite3.IntegrityError:
        fail('That expense is already linked to a bank transaction.', 409)
    db().execute('UPDATE expenses SET account_id=? WHERE id=? AND account_id IS NULL', (t['local_account_id'], eid))
    audit('bank transaction linked', t['id'])


def link_created(d, eid):
    if not d.get('bank_transaction_id'):
        return
    if 'bank_transaction_version' not in d:
        fail('Reopen the bank transaction before saving.', 409)
    t = transaction(d['bank_transaction_id'], d['bank_transaction_version'])
    eligible(t)
    e = one('SELECT * FROM expenses WHERE id=?', (eid,))
    if t['currency']=='AUD' and e['amount_cents'] != -t['amount_cents']:
        fail('The amount must match the AUD bank transaction.')
    if (e['amount_cents'] > 0) != (t['amount_cents'] < 0) or not e['amount_cents']:
        fail('Purchases must be positive expenses and refunds must be negative expenses.')
    if e['account_id'] != t['local_account_id']:
        fail('Keep the mapped bank account when adding this transaction.')
    if t['amount_cents'] > 0 and d.get('bank_confirm_refund') is not True:
        fail('Confirm this credit is an expense refund before adding it.')
    # Exclude the just-created expense from the duplicate warning.
    if any(m['id'] != eid for m in matches(t)) and d.get('bank_confirm_new') is not True:
        fail('A possible existing expense was found. Review it before creating another.', 409)
    attach(t, eid)


def register(app, **helpers):
    globals().update(helpers)

    @app.errorhandler(FeedError)
    def feed_error(exc):
        return jsonify(error=str(exc)), 400

    @app.route('/api/pocketsmith', methods=['GET','POST','PUT','DELETE'])
    @auth('owner')
    def settings():
        if request.method=='GET':
            return jsonify(public_connection())
        d = request.get_json(silent=True) or {}
        c = connection()
        if request.method=='POST':
            key = d.get('key') or key_for(c)
            if not isinstance(key, str) or not re.fullmatch(r'[\x21-\x7e]{10,512}', key):
                fail('Enter a valid PocketSmith developer key.')
            uid, name, accounts = account_data(Client(key))
            db().execute('BEGIN IMMEDIATE')
            if connection()['version'] != c['version']:
                fail('Connection settings changed. Reopen settings and try again.', 409)
            db().execute('UPDATE pocketsmith_accounts SET available=0,enabled=CASE WHEN remote_user_id=? THEN enabled ELSE 0 END', (uid,))
            for a in accounts:
                db().execute('INSERT INTO pocketsmith_accounts(remote_user_id,remote_id,name,institution,currency) VALUES (?,?,?,?,?) ON CONFLICT(remote_user_id,remote_id) DO UPDATE SET name=excluded.name,institution=excluded.institution,currency=excluded.currency,available=1', a)
            start = c['start_date'] if uid==c['remote_user_id'] and c['start_date'] else workspace_time.today().replace(day=1).isoformat()
            db().execute("UPDATE pocketsmith_connection SET key_encrypted=?,remote_user_id=?,display_name=?,start_date=?,version=version+1,lock_token='',lock_until=0,last_error='',retry_after=0,next_sync=0,last_sync=CASE WHEN remote_user_id=? THEN last_sync ELSE '' END,auto_sync=CASE WHEN remote_user_id=? THEN auto_sync ELSE 0 END WHERE id=1", (box().encrypt(key.encode()).decode(), uid, name, start, uid, uid))
        else:
            db().execute('BEGIN IMMEDIATE')
            if d.get('version') != connection()['version']:
                fail('Connection settings changed. Reopen settings and try again.', 409)
            if request.method=='DELETE':
                db().execute("UPDATE pocketsmith_connection SET key_encrypted='',auto_sync=0,version=version+1,lock_token='',lock_until=0,last_error='',retry_after=0 WHERE id=1")
                db().execute('UPDATE pocketsmith_accounts SET enabled=0')
            else:
                if not c['key_encrypted']:
                    fail('Connect PocketSmith first.')
                start = day(d.get('start_date'))
                if not start or start > workspace_time.today().isoformat():
                    fail('Choose a sync start date on or before today.')
                selected = d.get('accounts')
                if not isinstance(selected, list) or not selected or len(selected)>100:
                    fail('Select between one and 100 accounts.')
                used = set()
                db().execute('UPDATE pocketsmith_accounts SET enabled=0')
                for item in selected:
                    if not isinstance(item, dict) or str(item.get('id')) in used:
                        fail('Invalid or repeated account selection.')
                    used.add(str(item.get('id')))
                    a = one('SELECT * FROM pocketsmith_accounts WHERE id=? AND remote_user_id=? AND available=1', (item.get('id'), c['remote_user_id']))
                    if not a:
                        fail('Refresh the PocketSmith account list.')
                    aid = item.get('local_account_id') or a['local_account_id']
                    if a['local_account_id'] and aid and str(aid)!=str(a['local_account_id']):
                        fail('An imported account cannot be remapped. Keep its existing account label.')
                    if aid:
                        if not one('SELECT id FROM accounts WHERE id=?', (aid,)):
                            fail('Choose an existing local account.')
                    else:
                        aid = db().execute("INSERT INTO accounts(name,bank) VALUES (?,'Other')", (a['name'],)).lastrowid
                    if one('SELECT id FROM pocketsmith_accounts WHERE local_account_id=? AND id<>?', (aid, a['id'])):
                        fail('Each PocketSmith account needs a separate local account label.')
                    db().execute('UPDATE pocketsmith_accounts SET enabled=1,local_account_id=? WHERE id=?', (aid, a['id']))
                db().execute("UPDATE pocketsmith_connection SET start_date=?,auto_sync=?,version=version+1,next_sync=0,lock_token='',lock_until=0 WHERE id=1", (start, int(d.get('auto_sync') is True)))
        audit('PocketSmith connection '+request.method.lower(), 'settings')
        db().commit()
        return jsonify(public_connection())

    @app.post('/api/pocketsmith/sync')
    @auth('owner')
    def sync_now():
        return jsonify(sync(manual=True))

    @app.get('/api/bank-transactions')
    @auth('owner','tax_agent')
    def ledger():
        filters = {'review':"b.state='review' AND b.source_status='posted' AND b.missing=0 AND b.is_transfer=0",
                   'linked':"b.state='linked'", 'ignored':"b.state='ignored'", 'pending':"b.source_status='pending' AND b.missing=0",
                   'other':"b.is_transfer=1 OR b.missing=1", 'all':'1=1'}
        where = filters.get(request.args.get('state','review'))
        if where is None:
            fail('Invalid bank transaction filter.')
        try:
            offset = max(0, int(request.args.get('offset',0)))
        except ValueError:
            fail('Invalid page.')
        return jsonify(items=rows(LEDGER+'WHERE ('+where+') ORDER BY b.date DESC,b.id DESC LIMIT 100 OFFSET ?', (offset,)),
                       total=one('SELECT count(*) AS n FROM bank_transactions b WHERE ('+where+')')['n'])

    @app.route('/api/bank-transactions/<int:tid>', methods=['GET','POST'])
    @auth('owner','tax_agent')
    def review(tid):
        if request.method=='GET':
            t = transaction(tid)
            return jsonify(transaction=t, matches=matches(t))
        if not can_write():
            fail('Read-only access.', 403)
        d = request.get_json(silent=True) or {}
        db().execute('BEGIN IMMEDIATE')
        if 'version' not in d:
            fail('Reopen the transaction before continuing.', 409)
        t = transaction(tid, d['version'])
        action = d.get('action')
        if action!='acknowledge' and one('SELECT 1 FROM bank_reconciliations WHERE bank_id=?',(tid,)): fail('Undo this match from Bank reconciliation first.',409)
        if action=='link':
            eligible(t)
            eid = d.get('expense_id')
            if not any(e['id']==eid for e in matches(t)):
                fail('Choose a matching unlinked expense with the same amount and account within three days.')
            attach(t, eid)
        elif action in ('ignore','restore','unlink','acknowledge'):
            if action in ('ignore','restore') and t['expense_id']:
                fail('Unlink the expense first.', 409)
            if action=='unlink':
                db().execute("UPDATE bank_transactions SET expense_id=NULL,state='review',changed=0,version=version+1 WHERE id=?", (tid,))
            elif action=='acknowledge':
                db().execute('UPDATE bank_transactions SET changed=0,version=version+1 WHERE id=?', (tid,))
            else:
                db().execute('UPDATE bank_transactions SET state=?,version=version+1 WHERE id=?', ('ignored' if action=='ignore' else 'review', tid))
        else:
            fail('Invalid review action.')
        audit('bank transaction '+action, tid)
        db().commit()
        return jsonify(ok=True)


def start_scheduler(app):
    def run():
        while True:
            with app.app_context():
                try:
                    sync()
                except Exception:
                    # Never log upstream exceptions or credentials. Status is available to the owner.
                    app.logger.warning('PocketSmith scheduled sync did not complete; see Bank feeds settings.')
            time.sleep(60)
    threading.Thread(target=run, daemon=True, name='pocketsmith-sync').start()
