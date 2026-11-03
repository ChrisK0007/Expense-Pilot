"""Conservative, local matching against the already-synced bank ledger.

Suggestions do not write financial records. Every acceptance is recalculated
inside the caller's SQLite write transaction; nothing is sent to PocketSmith.
"""
import hashlib
import json
import re
from datetime import date, timedelta
from flask import jsonify, request

STOP = {'pos', 'eftpos', 'visa', 'mastercard', 'debit', 'credit', 'purchase',
        'payment', 'card', 'pty', 'ltd', 'limited', 'au', 'aus', 'australia',
        'cafe','restaurant','shop','store','services','online','the'}


def merchant_tokens(value):
    return {x for x in re.findall(r'[a-z0-9]+', str(value).lower())
            if len(x) > 2 and not x.isdigit() and x not in STOP}


def same_merchant(left, right):
    a, b = merchant_tokens(left), merchant_tokens(right)
    return bool(a and b and (a <= b or b <= a))


def expense_stamp(e):
    return hashlib.sha256(json.dumps(e, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def candidates(uid, when, cents, merchant, account_id=None, include_linked=False):
    from app import rows
    if cents <= 0 or not merchant_tokens(merchant):
        return []
    day = date.fromisoformat(when)
    result = rows('''SELECT b.*,a.local_account_id,a.name AS account_name,
        e.user_id AS expense_user_id,e.receipt_id AS expense_receipt_id,
        e.amount_cents AS expense_amount,e.account_id AS expense_account,e.merchant AS expense_merchant
        FROM bank_transactions b JOIN pocketsmith_accounts a ON a.id=b.feed_account_id
        LEFT JOIN expenses e ON e.id=b.expense_id
        WHERE b.currency='AUD' AND a.currency='AUD' AND a.enabled=1 AND a.available=1
          AND a.local_account_id IS NOT NULL AND b.amount_cents=? AND b.date BETWEEN ? AND ?
          AND b.source_status='posted' AND b.missing=0 AND b.changed=0 AND b.is_transfer=0
          AND (b.state='review' AND b.expense_id IS NULL OR b.state='linked' AND b.expense_id IS NOT NULL)
        ORDER BY b.date,b.id''', (-cents, (day-timedelta(days=3)).isoformat(), (day+timedelta(days=3)).isoformat()))
    return [t for t in result if same_merchant(merchant, t['payee'])
            and (not account_id or t['local_account_id'] == int(account_id))
            and (not t['expense_id'] or include_linked and t['expense_user_id'] == uid)]


def suggestions(uid, d):
    from app import money, rows
    if not d.get('date') or d.get('amount') in ('', None) or not d.get('merchant'):
        return dict(status='incomplete', candidates=[])
    try:
        found = candidates(uid, d['date'], money(d['amount']), d['merchant'], d.get('account_id'), True)
    except (ValueError, TypeError):
        return dict(status='incomplete', candidates=[])
    public=[]
    for t in found:
        item={k:t[k] for k in ('id','version','date','payee','amount_cents','account_name',
                              'local_account_id','expense_id','expense_receipt_id')}
        item['linked_expense_id']=t['expense_id'];item['existing_conflict']=False
        if t['expense_id'] and (t['expense_amount'] != -t['amount_cents']
                or t['expense_account'] != t['local_account_id']
                or not same_merchant(t['expense_merchant'],d['merchant'])):
            item['existing_conflict']=True
        if not t['expense_id']:
            # A CSV/manual expense may predate this feed. Reuse a single exact
            # receipt-date match, rather than silently create the expense twice.
            existing=rows('''SELECT e.* FROM expenses e WHERE user_id=? AND date=? AND amount_cents=?
                AND (account_id IS NULL OR account_id=?) AND bank_match_excluded=0
                AND NOT EXISTS(SELECT 1 FROM bank_transactions b WHERE b.expense_id=e.id) AND NOT EXISTS(SELECT 1 FROM bank_reconciliations r WHERE r.expense_id=e.id)''',
                (uid,d['date'],-t['amount_cents'],t['local_account_id']))
            existing=[e for e in existing if same_merchant(e['merchant'],d['merchant'])]
            if len(existing)==1:
                item['expense_id']=existing[0]['id'];item['expense_receipt_id']=existing[0]['receipt_id']
            elif len(existing)>1: item['existing_conflict']=True
        public.append(item)
    status = 'none' if not public else 'matched' if len(public)==1 and not public[0]['expense_receipt_id'] and not public[0]['existing_conflict'] else 'review'
    return dict(status=status, candidates=public)


def choose(uid, d):
    """Return a current match, or None for a genuine miss / explicit cash choice."""
    from app import fail
    choice = str(d.get('bank_choice') or 'auto')
    if choice == 'cash':
        return None
    result = suggestions(uid, d)
    found = result['candidates']
    if choice == 'auto':
        if result['status'] in ('none','incomplete'):
            return None
        if result['status'] != 'matched':
            fail('Several bank matches or an already-filed expense need review. Choose a transaction or Cash / other explicitly.',409)
        selected = found[0]
    else:
        selected = next((t for t in found if str(t['id']) == choice), None)
        if not selected:
            fail('The selected bank match has changed. Check the amount, date and merchant, then refresh matches.',409)
        if d.get('bank_version') is not None and str(d['bank_version']) != str(selected['version']):
            fail('This bank transaction changed. Refresh its match before saving.',409)
    if selected['existing_conflict']:
        fail('Existing expense details need review. Attach this document to the correct expense before matching it from Bank accounts.',409)
    if selected['expense_receipt_id']:
        fail('This bank transaction already has an expense with a document. Review that expense to avoid a duplicate.',409)
    return selected


def attach(eid, match, cash=False):
    from app import db
    import pocketsmith
    if match and not match.get('linked_expense_id'):
        pocketsmith.attach(match, eid)
    if cash:
        db().execute('UPDATE expenses SET bank_match_excluded=1 WHERE id=?',(eid,))


def backfill_plan(account_id=None, user_id=None, strict=True):
    from app import record_user_id, rows, fail
    uid = user_id if user_id is not None else record_user_id()
    expenses = rows('''SELECT e.* FROM expenses e WHERE e.user_id=? AND e.bank_match_excluded=0
        AND e.amount_cents>0 AND NOT EXISTS(SELECT 1 FROM bank_transactions b WHERE b.expense_id=e.id) AND NOT EXISTS(SELECT 1 FROM bank_reconciliations r WHERE r.expense_id=e.id)
        AND (? IS NULL OR e.account_id=? OR e.account_id IS NULL) ORDER BY e.date,e.id LIMIT 2001''', (uid,account_id,account_id))
    if len(expenses)>2000:
        if not strict: return None
        fail('More than 2,000 unmatched expenses. Select a bank account or match older records in smaller groups.',400)
    plans=[]; uses={}
    for e in expenses:
        matches=candidates(uid,e['date'],e['amount_cents'],e['merchant'],e['account_id'] or account_id)
        for t in matches: uses[t['id']]=uses.get(t['id'],0)+1
        plans.append((e,matches))
    clear=[];conflicts=[];ambiguous=0;unmatched=0
    for e,matches in plans:
        if len(matches)==1 and uses[matches[0]['id']]==1:
            t=matches[0]
            clear.append(dict(expense_id=e['id'],expense_stamp=expense_stamp(e),merchant=e['merchant'],
                date=e['date'],amount_cents=e['amount_cents'],transaction_id=t['id'],version=t['version'],
                bank_date=t['date'],payee=t['payee'],account_name=t['account_name']))
        elif matches:
            ambiguous+=1
            conflicts.append({k:e[k] for k in ('id','merchant','date','amount_cents')})
        else: unmatched+=1
    return dict(matches=clear,conflicts=conflicts,ambiguous=ambiguous,unmatched=unmatched,checked=len(expenses))


def link_after_sync():
    """Caller holds the sync write lock; ambiguous matches never write a link."""
    from app import one
    import pocketsmith
    owner=one("SELECT id FROM users WHERE role='owner' AND active=1 ORDER BY id LIMIT 1")
    if not owner: return 0
    plan=backfill_plan(user_id=owner['id'], strict=False)
    if plan is None: return 0
    for match in plan['matches']:
        pocketsmith.attach(pocketsmith.transaction(match['transaction_id']), match['expense_id'])
    return len(plan['matches'])


def register(app, auth):
    from app import db, fail, receipt, record_user_id, one

    @app.post('/api/receipts/<rid>/bank-matches')
    @auth('owner','tax_agent')
    def receipt_matches(rid):
        r=receipt(rid)
        d=request.get_json() or {}
        if not isinstance(d,dict): fail('Expected document fields.')
        return jsonify(suggestions(r['user_id'],d))

    @app.route('/api/bank-matches/previous',methods=['GET','POST'])
    @auth('owner','tax_agent')
    def previous():
        d=request.get_json(silent=True) or {}
        if not isinstance(d,dict): fail('Expected matching options.')
        aid=request.args.get('account_id') if request.method=='GET' else d.get('account_id')
        try: aid=int(aid) if aid else None
        except (ValueError,TypeError): fail('Choose a bank account.')
        if aid and not one('SELECT id FROM accounts WHERE id=?',(aid,)): fail('Account not found.',404)
        if request.method=='GET': return jsonify(backfill_plan(aid))
        selected=d.get('matches')
        if not isinstance(selected,list) or not 1<=len(selected)<=2000 or any(not isinstance(x,dict) or type(x.get('expense_id')) is not int for x in selected):
            fail('Choose the suggested expenses to match.')
        db().execute('BEGIN IMMEDIATE')
        plan=backfill_plan(aid);current={x['expense_id']:x for x in plan['matches']};seen=set()
        for item in selected:
            old=current.get(item.get('expense_id'))
            if not old or old['expense_id'] in seen or any(item.get(k)!=old[k] for k in ('expense_stamp','transaction_id','version')):
                fail('Expenses or bank matches changed. Refresh the preview before applying any matches.',409)
            seen.add(old['expense_id'])
        import pocketsmith
        for item in selected:
            t=one(pocketsmith.LEDGER+'WHERE b.id=?',(item['transaction_id'],))
            pocketsmith.attach(t,item['expense_id'])
        db().commit()
        return jsonify(matched=len(selected))
