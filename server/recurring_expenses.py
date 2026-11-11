"""Expected payments stay outside the ledger until a posted charge is reviewed."""
import json
from datetime import date, timedelta

from flask import jsonify, request
from bank_matching import same_merchant
from billing_core import advance_date
from expense_core import split_values
from workflow_core import body, checked, fiscal, integer, preview, write_access

INTERVALS = ('weekly', 'fortnightly', 'monthly', 'quarterly', 'yearly')


def dates(rule, first, last):
    due = rule['start']
    anchor = int(due[8:])
    while due <= last:
        if due >= first:
            yield due
        if due >= '9998-12-01':
            return
        due = advance_date(due, rule['interval'], anchor)


def lookup(rule, due):
    from app import rows
    when = date.fromisoformat(due)
    return [b for b in rows("""SELECT b.id,b.date,b.payee,b.amount_cents,b.version,b.expense_id,a.name AS account_name,a.local_account_id
        FROM bank_transactions b JOIN pocketsmith_accounts a ON a.id=b.feed_account_id
        WHERE a.local_account_id=? AND a.enabled=1 AND a.available=1 AND b.currency='AUD' AND b.amount_cents<0
          AND b.date BETWEEN ? AND ? AND b.source_status='posted' AND b.missing=0 AND b.changed=0 AND b.is_transfer=0
          AND (b.state='review' OR (b.state='linked' AND b.expense_id IS NOT NULL))
          AND NOT EXISTS(SELECT 1 FROM recurring_expense_occurrences o WHERE o.bank_id=b.id)
        ORDER BY b.date,b.id""", (rule['account_id'], (when-timedelta(days=3)).isoformat(),
                                 (when+timedelta(days=3)).isoformat()))
            if same_merchant(rule['merchant'], b['payee'])]


def expense_choices(bank, uid, merchant):
    from app import one
    import pocketsmith
    if bank['expense_id']:
        existing = one('SELECT * FROM expenses WHERE id=? AND user_id=?', (bank['expense_id'], uid))
        return [existing] if existing else []
    return [e for e in pocketsmith.matches(bank) if e['user_id']==uid and not e['bank_match_excluded']
            and same_merchant(merchant,e['merchant'])]


def register(app, auth):
    from app import audit, category_names, day, db, fail, money, one, payload, record_user_id, rows, textval
    import pocketsmith
    import workspace_time

    def rule_for(rid):
        row = one('SELECT * FROM recurring_expense_rules WHERE id=? AND user_id=?', (rid, record_user_id()))
        if not row:
            fail('Recurring expense not found.',404)
        return {**json.loads(row['data']), **{k:row[k] for k in ('id','version','active')}}

    @app.get('/api/recurring-expenses')
    @auth('owner','tax_agent')
    def recurring_index():
        current = workspace_time.today()
        fy = current.year - (current.month < 7)
        year, start, end = fiscal(request.args.get('year', fy))
        rules = [rule_for(r['id']) for r in rows('SELECT id FROM recurring_expense_rules WHERE user_id=? ORDER BY id', (record_user_id(),))]
        settled = rows("""SELECT o.*,e.merchant,e.amount_cents FROM recurring_expense_occurrences o
                          JOIN recurring_expense_rules r ON r.id=o.rule_id LEFT JOIN expenses e ON e.id=o.expense_id
                          WHERE r.user_id=? AND o.due_date BETWEEN ? AND ? ORDER BY o.due_date DESC""",
                       (record_user_id(),start,end))
        done = {(r['rule_id'],r['due_date']) for r in settled}
        pending = [dict(rule_id=r['id'], due_date=due, merchant=r['merchant'], expected_cents=r['amount_cents'],
                        matches=lookup(r,due))
                   for r in rules if r['active']
                   for due in dates(r,start,min(end,current.isoformat())) if (r['id'],due) not in done]
        return jsonify(year=year,rules=rules,pending=sorted(pending,key=lambda x:x['due_date'],reverse=True),settled=settled)

    @app.post('/api/recurring-expenses')
    @app.put('/api/recurring-expenses/<int:rid>')
    @auth('owner','tax_agent')
    def recurring_save(rid=None):
        write_access()
        d=body()
        db().execute('BEGIN IMMEDIATE')
        old=rule_for(rid) if rid is not None else None
        if old and d.get('version')!=old['version']:
            fail('This schedule changed. Reload before saving.',409)
        active=d.get('active',True)
        if type(active) is not bool:
            fail('Choose whether this schedule is active.')
        merchant=textval(d.get('merchant'),200)
        amount=money(d.get('amount'))
        start=day(d.get('start'))
        interval=d.get('interval')
        category=d.get('category')
        account=integer(d.get('account_id'),'bank account',1)
        try: work,business=split_values(d)
        except ValueError as exc: fail(str(exc))
        if not merchant or amount<=0 or interval not in INTERVALS or category not in category_names() or category=='Meals':
            fail('Enter a merchant, positive amount, repeat interval and ordinary expense category.')
        if not '1900-01-01' <= start <= '2098-12-31':
            fail('Choose a start date from 1900 to 2098.')
        if not one('SELECT id FROM accounts WHERE id=?',(account,)):
            fail('Choose an existing bank account.')
        value=dict(merchant=merchant,amount_cents=amount,start=start,interval=interval,category=category,
                   account_id=account,work_percent=work,business_percent=business)
        if old:
            db().execute('UPDATE recurring_expense_rules SET data=?,active=?,version=version+1 WHERE id=?',
                         (json.dumps(value),int(active),rid))
        else:
            rid=db().execute('INSERT INTO recurring_expense_rules(user_id,data,active) VALUES (?,?,?)',
                             (record_user_id(),json.dumps(value),int(active))).lastrowid
        audit('recurring expense schedule saved',rid)
        db().commit()
        return jsonify(id=rid)

    @app.post('/api/recurring-expenses/<int:rid>/<due>/<action>')
    @auth('owner','tax_agent')
    def recurring_match(rid,due,action):
        write_access()
        if action not in ('preview','apply','skip'):
            fail('Unknown recurring expense action.',404)
        d=body()
        if action!='preview':
            db().execute('BEGIN IMMEDIATE')
        rule=rule_for(rid)
        due=day(due)
        if not rule['active'] or due>workspace_time.today().isoformat() or not next(dates(rule,due,due),None):
            fail('This payment is no longer due on the schedule.',409)
        uid=record_user_id()
        existing=one('SELECT * FROM recurring_expense_occurrences WHERE rule_id=? AND due_date=?',(rid,due))
        if existing:
            if action=='apply' and d.get('bank_id')==existing['bank_id']:
                return jsonify(expense_id=existing['expense_id'])
            fail('This scheduled payment was already reviewed.',409)
        if action=='skip':
            db().execute('INSERT INTO recurring_expense_occurrences(rule_id,due_date) VALUES (?,?)',(rid,due))
            audit('recurring expense occurrence skipped',f'{rid}:{due}')
            db().commit()
            return jsonify(ok=True)
        bank_id=integer(d.get('bank_id'),'bank transaction',1)
        match=next((b for b in lookup(rule,due) if b['id']==bank_id),None)
        if not match:
            fail('This posted charge is no longer a candidate.',409)
        bank=pocketsmith.transaction(bank_id)
        expenses=expense_choices(bank,uid,rule['merchant'])
        if bank['expense_id'] and not expenses:
            fail('The linked purchase does not belong to this workspace.',409)
        plan=dict(rule=rule,bank=match,due_date=due,expenses=expenses)
        if action=='preview':
            return jsonify(**plan,token=preview('recurring expense',plan))
        checked(d.get('token'),'recurring expense',plan)
        eid=d.get('expense_id')
        if expenses:
            if type(eid) is not int or not any(e['id']==eid for e in expenses):
                fail('Select the recorded purchase to prevent a duplicate.')
            if one('SELECT 1 FROM recurring_expense_occurrences WHERE expense_id=?',(eid,)):
                fail('This expense is already assigned to another scheduled payment.',409)
        elif eid is not None:
            fail('The selected purchase is no longer available.',409)
        else:
            values=payload(dict(rule,date=bank['date'],scope='personal',amount=f"{-bank['amount_cents']/100:.2f}",
                                notes='Matched to recurring expense schedule',status='review'))
            eid=db().execute("""INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,reimbursed,
                notes,trip_id,meal,receipt_id,account_id,status,shared,work_percent,business_percent)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (uid,)+values).lastrowid
            audit('expense created',eid)
        if not bank['expense_id']:
            pocketsmith.eligible(bank)
            pocketsmith.attach(bank,eid)
        db().execute('INSERT INTO recurring_expense_occurrences(rule_id,due_date,bank_id,expense_id) VALUES (?,?,?,?)',
                     (rid,due,bank_id,eid))
        audit('recurring expense matched',f'{rid}:{due}')
        db().commit()
        return jsonify(expense_id=eid)
