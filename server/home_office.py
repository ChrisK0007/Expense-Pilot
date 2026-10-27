"""Owner's WFH records; employee and sole-trader claims share one annual election.

Source: ATO PCG 2023/1, paragraphs 18–28 and 56–66, checked 27 October 2026.
This module never changes a receipt's spend or silently creates an expense.
"""
import csv
import hashlib
import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from flask import g, jsonify, request, send_file
from expense_core import allocations
import workspace_time

SOURCE = 'https://www.ato.gov.au/law/view/document?DocID=COG/PCG20231/NAT/ATO/00001'
KINDS = dict(electricity='Electricity', gas='Gas', phone='Phone usage', internet='Internet',
             phone_internet='Combined phone / internet', stationery='Stationery',
             consumables='Computer consumables', asset='Equipment / depreciation',
             cleaning='Dedicated office cleaning', occupancy='Occupancy — adviser reviewed',
             other='Other — outside the fixed rate')
COVERED = {'electricity', 'gas', 'phone', 'internet', 'phone_internet', 'stationery', 'consumables'}
EVIDENCE_TYPES = COVERED - {'phone_internet'}
RATES = {2022: 67, 2023: 67, 2024: 70, 2025: 70, 2026: 70}
DEFAULTS = dict(method='none', eligible=False, hours_complete=False, costs_complete=False, incurred_types=[])


def owner_id():
    from app import one
    return one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")['id']


def bounds(year):
    from app import fail
    if not 2022 <= year <= 2099: fail('Choose a financial year from 2022 onwards.')
    return f'{year}-07-01', f'{year+1}-06-30'


def financial_year(day):
    return int(day[:4]) - (int(day[5:7]) < 7)


def integer(value, minimum=0, maximum=1000000):
    from app import fail
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number != int(number) or not minimum <= number <= maximum: raise ValueError()
        return int(number)
    except (ValueError, ArithmeticError): fail('Enter a valid whole number.')


def data():
    from app import fail
    value = request.get_json()
    if not isinstance(value, dict): fail('Enter a valid record.')
    return value


def history(entity, action, before=None, after=None):
    from app import db, audit
    db().execute('INSERT INTO home_office_history(owner_id,actor_id,entity,action,before_json,after_json) VALUES (?,?,?,?,?,?)',
                 (owner_id(), g.user['id'], entity, action, json.dumps(before) if before else None, json.dumps(after) if after else None))
    audit('home office '+action, entity)


def check_version(record, payload):
    from app import fail
    if integer(payload.get('version')) != record['version']:
        fail('This record changed. Reload it before saving.', 409)


def settings(year):
    from app import one
    row = one('SELECT * FROM home_office_settings WHERE user_id=? AND year=?', (owner_id(), year))
    saved = json.loads(row['data']) if row else {}
    result = {**DEFAULTS, **saved, 'version': row['version'] if row else 0}
    # Preserve the stored election and its evidence. A retired method must not
    # silently become an eligible fixed-rate claim or ordinary bill deductions.
    result['needs_fixed_review'] = result['method'] not in ('none', 'fixed')
    if result['needs_fixed_review']:
        result.update(method='fixed', eligible=False, hours_complete=False, costs_complete=False)
    return result


def kind_for(expense):
    from overnights import is_overnight
    if is_overnight(expense) or expense.get('vehicle_id'): return ''
    # The established category is usage. A handset can be explicitly classified as an asset.
    return expense.get('home_office_kind') or ('phone_internet' if expense['category'] == 'Phone & internet' else '')


def costs(year):
    from app import rows
    start, end = bounds(year)
    records = rows('''SELECT e.*, c.kind AS home_office_kind,c.claim_base_cents,c.basis,
                      c.reviewed AS cost_reviewed,COALESCE(c.version,0) AS cost_version
                      FROM expenses e LEFT JOIN home_office_costs c ON c.expense_id=e.id
                      WHERE e.user_id=? AND e.date BETWEEN ? AND ? ORDER BY e.date,e.id''', (owner_id(),start,end))
    for row in records:
        row['classification_confirmed'] = bool(row['home_office_kind'])
        row['home_office_kind'] = kind_for(row)
        row['cost_version'] = row['cost_version'] or 0
        row['basis'] = row['basis'] or ''
        row['actual_work_cents'], row['actual_business_cents'] = cost_allocations(row)
    return records


def cost_allocations(expense):
    kind = kind_for(expense)
    if expense.get('reimbursed'): return 0, 0
    # Annual asset deductions and occupancy must be explicitly assessed, not inferred from purchase price.
    if kind in ('asset', 'occupancy') and (not expense.get('cost_reviewed') or expense.get('claim_base_cents') is None): return 0, 0
    if expense.get('claim_base_cents') is not None:
        if not valid_base(expense): return 0, 0
        return allocations({**expense, 'amount_cents': expense['claim_base_cents']})
    return allocations(expense)


def valid_base(expense):
    base=expense.get('claim_base_cents');amount=expense['amount_cents']
    return base is None or abs(base)<=abs(amount) and base*amount>=0


def summary(year):
    from app import rows
    start, end = bounds(year); s = settings(year); rate = RATES.get(year)
    entries = rows('SELECT * FROM home_office_entries WHERE user_id=? AND deleted=0 AND date BETWEEN ? AND ? ORDER BY date DESC,start_at DESC', (owner_id(),start,end))
    minutes = {scope: sum((e['end_at']-e['start_at'])//60-e['break_minutes'] for e in entries if e['scope']==scope) for scope in ('work','business')}
    fixed = {scope: int((Decimal(minutes[scope])*rate/60).quantize(Decimal(1), rounding=ROUND_HALF_UP)) if rate is not None else None for scope in minutes}
    all_costs = costs(year); classified = [e for e in all_costs if e['home_office_kind']]
    extras = dict(work=0,business=0); evidence=set(); warnings=[]
    for e in classified:
        k=e['home_office_kind']
        if k in COVERED and e['classification_confirmed'] and e.get('receipt_id') and not e['reimbursed'] and e['amount_cents']>0 and e['status']=='ready':
            evidence.update(('phone','internet') if k=='phone_internet' else (k,))
        if e['status'] != 'ready': continue
        for scope in extras:
            if k not in COVERED: extras[scope]+=e['actual_'+scope+'_cents']
        if k in ('asset','occupancy') and not e.get('cost_reviewed'):
            warnings.append(f"{e['merchant']}: enter the assessed annual amount and confirm review before including this {k} cost.")
    missing=sorted(set(s['incurred_types'])-evidence)
    fixed_issues=[]
    if s['needs_fixed_review']: fixed_issues.append('Home office now uses fixed rate only. Review and save your claim settings; your existing records are retained.')
    if not s['eligible']: fixed_issues.append('Confirm you performed income-producing duties at home and personally incurred additional running costs.')
    if not s['hours_complete']: fixed_issues.append('Confirm all actual home-working hours to date are recorded as they occurred.')
    if not s['costs_complete']: fixed_issues.append('Confirm all covered running costs in Expenses are classified here, including phone use away from home.')
    if not s['incurred_types']: fixed_issues.append('Select the running costs you personally incurred.')
    if missing: fixed_issues.append('Attach a bill for: '+', '.join(KINDS[k] for k in missing)+'.')
    if rate is None: fixed_issues.append('The fixed rate for this year needs a rule update; no rate has been assumed.')
    if not entries: fixed_issues.append('Record your actual working-from-home hours.')
    for e in classified:
        if e['home_office_kind'] not in COVERED and not valid_base(e):
            issue=f"{e['merchant']}: the original bill changed. Review its assessed amount."
            fixed_issues.append(issue)
    # Assets / occupancy are outside the hourly rate but must also be substantiated.
    extra_issues=[f"{e['merchant']}: attach evidence and an apportionment basis for this additional deduction." for e in classified
                  if e['home_office_kind'] not in COVERED and e['status']=='ready' and not e['reimbursed']
                  and (e['actual_work_cents'] or e['actual_business_cents']) and (not e['receipt_id'] or not e['basis'])]
    fixed_issues+=extra_issues
    fixed_total={scope: (fixed[scope]+extras[scope] if fixed[scope] is not None else None) for scope in minutes}
    method=s['method']
    active=method=='fixed' and not fixed_issues
    allowances=rows('SELECT * FROM home_office_allowances WHERE user_id=? AND date BETWEEN ? AND ? ORDER BY date,id', (owner_id(),start,end))
    return dict(year=year,start=start,end=end,settings=s,entries=entries,minutes=minutes,rate_cents=rate,
                fixed=fixed_total,hourly=fixed,extras=extras,costs=classified,available_costs=all_costs,
                fixed_issues=fixed_issues,warnings=warnings,active=active,
                status='not_selected' if method=='none' else 'active' if active else 'needs_review',
                allowances=allowances,allowance_income_cents=sum(a['amount_cents'] for a in allowances if not a['included_in_pay']),
                source=SOURCE,rules_checked='2026-10-27')


def adjusted(expense, annual):
    """Effective forecast amount; bookkeeping allocation remains intact."""
    if expense['user_id'] != owner_id() or annual['settings']['method']=='none': return allocations(expense)
    kind=kind_for(expense)
    if not kind: return allocations(expense)
    # Once elected, ineligible/incomplete WFH costs stay pending, never fall back to
    # ordinary allocations or a different method without an explicit choice.
    if not annual['active']: return 0,0
    if annual['settings']['method']=='fixed' and kind in COVERED: return 0,0
    return cost_allocations(expense)


def forecast_adjustments(year, expenses):
    annual=summary(year); by_id={e['id']:e for e in annual['costs']};out=[]
    for e in expenses:
        out.append(adjusted(by_id.get(e['id'],e),annual))
    addition=annual['hourly'] if annual['active'] and annual['settings']['method']=='fixed' else dict(work=0,business=0)
    return annual,sum(a[0] for a in out)+(addition['work'] or 0),sum(a[1] for a in out)+(addition['business'] or 0)


def entry_values(payload):
    from app import day, fail, textval
    when=day(payload.get('date'));start=payload.get('start_time');end=payload.get('end_time')
    bounds(financial_year(when))
    scope=payload.get('scope');activity=textval(payload.get('activity'),1000)
    if scope not in ('work','business') or not activity: fail('Choose Employment or Business and describe the work performed.')
    zone=workspace_time.validate(payload.get('timezone',workspace_time.name()))
    def stamp(clock, occurrence):
        try:
            if clock=='24:00': naive=datetime.fromisoformat(when)+timedelta(days=1)
            else: naive=datetime.strptime(when+'T'+clock,'%Y-%m-%dT%H:%M')
        except (ValueError,TypeError): fail('Enter start and finish times as HH:MM.')
        z=ZoneInfo(zone)
        candidates=sorted({int(naive.replace(tzinfo=z,fold=f).timestamp()) for f in (0,1)
                           if naive.replace(tzinfo=z,fold=f).astimezone(timezone.utc).astimezone(z).replace(tzinfo=None)==naive})
        if not candidates: fail('This time does not exist because daylight saving starts. Choose another time.')
        if len(candidates)>1 and occurrence not in ('first','second'): fail('This time occurs twice. Select its first or second occurrence.')
        return candidates[-1] if occurrence=='second' else candidates[0]
    first=stamp(start,payload.get('start_occurrence'));last=stamp(end,payload.get('end_occurrence'))
    if start=='24:00' or last<=first: fail('Finish must follow start on the same date. Split overnight work into separate days; use 24:00 for midnight.')
    if last>datetime.now(timezone.utc).timestamp(): fail('Only log hours already worked, not a future schedule.')
    breaks=integer(payload.get('break_minutes',0),0,1500)
    if breaks*60>=last-first: fail('Breaks must be shorter than the session.')
    return dict(date=when,start_at=first,end_at=last,timezone=zone,start_time=start,end_time=end,break_minutes=breaks,scope=scope,activity=activity)


def register(app, auth):
    from app import audit, db, fail, money, one, rows, day, textval

    @app.get('/api/home-office/<int:year>')
    @auth('owner','tax_agent')
    def get_summary(year):
        return jsonify(summary(year))

    @app.route('/api/home-office/<int:year>/settings',methods=['PUT'])
    @auth('owner','tax_agent')
    def save_settings(year):
        bounds(year);p=data();db().execute('BEGIN IMMEDIATE');old=settings(year);check_version(old,p)
        if p.get('method') not in ('none','fixed'): fail('Home office supports the fixed-rate method only. Reload and review your claim settings.')
        value={k:p.get(k,False) for k in ('eligible','hours_complete','costs_complete')}
        if any(type(v) is not bool for v in value.values()): fail('Use valid eligibility confirmations.')
        types=p.get('incurred_types',[])
        if not isinstance(types,list) or any(not isinstance(k,str) or k not in EVIDENCE_TYPES for k in types): fail('Choose valid running costs.')
        value.update(method=p['method'],incurred_types=sorted(set(types)))
        # Keep retired settings in history when an older beta election is replaced.
        saved=one('SELECT data FROM home_office_settings WHERE user_id=? AND year=?',(owner_id(),year))
        if saved: old={**json.loads(saved['data']), 'version':old['version']}
        db().execute('INSERT INTO home_office_settings(user_id,year,data) VALUES (?,?,?) ON CONFLICT(user_id,year) DO UPDATE SET data=excluded.data,version=version+1',(owner_id(),year,json.dumps(value)))
        history('year:'+str(year),'settings updated',old,value);db().commit()
        return jsonify(summary(year))

    @app.post('/api/home-office/entries')
    @auth('owner','tax_agent')
    def create_entry():
        p=data();db().execute('BEGIN IMMEDIATE')
        try: ref=str(uuid.UUID(str(p.get('client_ref'))))
        except ValueError: fail('Reload the entry form and try again.')
        fingerprint=hashlib.sha256(json.dumps({k:v for k,v in p.items() if k!='client_ref'},sort_keys=True).encode()).hexdigest()
        old=one('SELECT * FROM home_office_entries WHERE user_id=? AND client_ref=?',(owner_id(),ref))
        if old:
            if old['deleted'] or old['version']!=1 or old['fingerprint']!=fingerprint: fail('This entry was changed or removed. Reload before retrying.',409)
            return jsonify(id=old['id'],version=old['version'])
        v=entry_values(p);overlap(v)
        names=','.join(v);marks=','.join('?' for _ in v)
        c=db().execute(f'INSERT INTO home_office_entries(user_id,client_ref,fingerprint,{names}) VALUES (?,?,?,{marks})',(owner_id(),ref,fingerprint,*v.values()))
        history('entry:'+str(c.lastrowid),'entry created',after=v);db().commit()
        return jsonify(id=c.lastrowid,version=1)

    def overlap(v, exclude=0):
        if one('SELECT id FROM home_office_entries WHERE user_id=? AND deleted=0 AND id!=? AND start_at<? AND end_at>?', (owner_id(),exclude,v['end_at'],v['start_at'])):
            fail('This session overlaps another employment or business entry. Split the time so each hour is counted once.',409)

    @app.route('/api/home-office/entries/<int:eid>',methods=['PUT','DELETE'])
    @auth('owner','tax_agent')
    def update_entry(eid):
        p=data();db().execute('BEGIN IMMEDIATE');old=one('SELECT * FROM home_office_entries WHERE id=? AND user_id=? AND deleted=0',(eid,owner_id()))
        if not old: fail('Home-office entry not found.',404)
        check_version(old,p)
        if request.method=='DELETE':
            db().execute('UPDATE home_office_entries SET deleted=1,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(eid,));v=None
        else:
            v=entry_values(p);overlap(v,eid)
            db().execute('UPDATE home_office_entries SET '+','.join(k+'=?' for k in v)+',version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(*v.values(),eid))
        history('entry:'+str(eid),'entry deleted' if v is None else 'entry updated',old,v);db().commit()
        return jsonify(ok=True)

    @app.post('/api/home-office/bills')
    @auth('owner','tax_agent')
    def create_bill():
        """Save fixed-rate evidence atomically, with no separate allocation."""
        from app import payload
        import mobile_uploads
        p=data();kind=p.get('kind')
        if kind not in COVERED: fail('Choose a cost covered by the fixed rate.')
        ref=mobile_uploads.reference(p.get('client_ref'))
        if not ref: fail('Reload the bill form and try again.')
        digest=mobile_uploads.fingerprint(p);uid=owner_id()
        db().execute('BEGIN IMMEDIATE')
        prior=mobile_uploads.previous(uid,'expense',ref,digest)
        if prior:
            db().commit();return jsonify(mobile_uploads.ack(prior['id'],ref))
        if p.get('personally_paid') is not True: fail('Confirm that you personally incurred the cost and it was not reimbursed.')
        if not p.get('receipt_id') or money(p.get('amount'))<=0: fail('Attach the bill and enter a positive amount you personally paid.')
        when=day(p.get('date'));bounds(financial_year(when))
        basis=textval(p.get('notes'),2000)
        values=payload(dict(date=when,merchant=p.get('merchant'),amount=p.get('amount'),receipt_id=p['receipt_id'],
                            category='Phone & internet' if kind in ('phone','internet','phone_internet') else 'Other',
                            scope='personal',work_percent=0,business_percent=0,status='ready',
                            notes='Fixed-rate home-office evidence; no separate bill deduction.\n'+basis))
        c=db().execute('INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,reimbursed,notes,trip_id,meal,receipt_id,account_id,status,shared,work_percent,business_percent) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(uid,)+values)
        eid=c.lastrowid
        db().execute('INSERT INTO home_office_costs(expense_id,kind,basis) VALUES (?,?,?)',(eid,kind,basis))
        mobile_uploads.remember(uid,'expense',ref,digest,eid)
        audit('expense created',eid)
        history('cost:'+str(eid),'fixed-rate bill added',after=dict(date=when,kind=kind,basis=basis))
        db().commit();return jsonify(mobile_uploads.ack(eid,ref))

    @app.route('/api/home-office/costs/<int:eid>', methods=['PUT','DELETE'])
    @auth('owner','tax_agent')
    def save_cost(eid):
        p=data();db().execute('BEGIN IMMEDIATE');e=one('SELECT * FROM expenses WHERE id=? AND user_id=?',(eid,owner_id()))
        if not e: fail('Choose an expense belonging to the owner.',404)
        from overnights import is_overnight
        if is_overnight(e) or e.get('vehicle_id'): fail('Choose a home-office bill, not an overnight or vehicle expense.')
        old=one('SELECT * FROM home_office_costs WHERE expense_id=?',(eid,)) or {'version':0}
        check_version(old,p);kind=p.get('kind');basis=textval(p.get('basis'),2000)
        if request.method=='DELETE':
            if not old.get('kind'): fail('This bill has no saved classification.',409)
            db().execute("UPDATE home_office_costs SET kind='',claim_base_cents=NULL,basis='',reviewed=0,version=version+1 WHERE expense_id=?",(eid,))
            history('cost:'+str(eid),'bill classification removed',{**old,'date':e['date']},dict(date=e['date']))
            db().commit();return jsonify(ok=True)
        if kind not in KINDS: fail('Choose a home-office cost type.')
        value=p.get('claim_base');base=None if value in ('',None) else money(value)
        if base is not None and (abs(base)>abs(e['amount_cents']) or base*e['amount_cents']<0): fail('The assessed amount must have the same sign and be no larger than the original bill.')
        reviewed=p.get('reviewed',False)
        if type(reviewed) is not bool: fail('Use a valid review confirmation.')
        if kind in ('asset','occupancy') and reviewed and (base is None or not basis): fail('Enter the assessed annual amount and explain its calculation.')
        v=dict(kind=kind,claim_base_cents=base,basis=basis,reviewed=reviewed)
        db().execute('INSERT INTO home_office_costs(expense_id,kind,claim_base_cents,basis,reviewed) VALUES (?,?,?,?,?) ON CONFLICT(expense_id) DO UPDATE SET kind=excluded.kind,claim_base_cents=excluded.claim_base_cents,basis=excluded.basis,reviewed=excluded.reviewed,version=version+1',(eid,kind,base,basis,int(reviewed)))
        history('cost:'+str(eid),'bill classified',{**old,'date':e['date']},{**v,'date':e['date']});db().commit();return jsonify(ok=True)

    @app.route('/api/home-office/allowances',methods=['POST'])
    @auth('owner','tax_agent')
    def create_allowance():
        p=data();v=allowance_values(p);db().execute('BEGIN IMMEDIATE')
        c=db().execute('INSERT INTO home_office_allowances(user_id,date,employer,amount_cents,included_in_pay,notes) VALUES (?,?,?,?,?,?)',(owner_id(),*v))
        history('allowance:'+str(c.lastrowid),'allowance created',after=p);db().commit();return jsonify(id=c.lastrowid)

    def allowance_values(p):
        employer=textval(p.get('employer'),200);amount=money(p.get('amount'));included=p.get('included_in_pay',True)
        if not employer or amount<=0 or type(included) is not bool: fail('Enter employer, positive allowance amount and whether it is already in gross pay.')
        when=day(p.get('date'));bounds(financial_year(when))
        return when,employer,amount,int(included),textval(p.get('notes'),2000)

    @app.route('/api/home-office/allowances/<int:aid>',methods=['PUT','DELETE'])
    @auth('owner','tax_agent')
    def change_allowance(aid):
        p=data();db().execute('BEGIN IMMEDIATE');old=one('SELECT * FROM home_office_allowances WHERE id=? AND user_id=?',(aid,owner_id()))
        if not old: fail('Allowance not found.',404)
        check_version(old,p)
        if request.method=='DELETE': db().execute('DELETE FROM home_office_allowances WHERE id=?',(aid,))
        else: db().execute('UPDATE home_office_allowances SET date=?,employer=?,amount_cents=?,included_in_pay=?,notes=?,version=version+1 WHERE id=?',(*allowance_values(p),aid))
        history('allowance:'+str(aid),'allowance '+('deleted' if request.method=='DELETE' else 'updated'),old,p);db().commit();return jsonify(ok=True)

    @app.get('/api/home-office/history')
    @auth('owner','tax_agent')
    def get_history():
        return jsonify(rows('SELECT h.*,u.name AS actor FROM home_office_history h LEFT JOIN users u ON u.id=h.actor_id WHERE owner_id=? ORDER BY h.id DESC LIMIT 500',(owner_id(),)))

    @app.get('/api/home-office/<int:year>/report.pdf')
    @auth('owner','tax_agent')
    def logbook_pdf(year):
        from record_reports import home_office_pdf
        result=summary(year)
        person=one('SELECT name FROM users WHERE id=?',(owner_id(),))['name']
        return send_file(io.BytesIO(home_office_pdf(result,person)),mimetype='application/pdf',as_attachment=True,download_name=f'expense-pilot-wfh-logbook-{year}-{year+1}.pdf')

    @app.get('/api/home-office/<int:year>/export', endpoint='home_office_export')
    @auth('owner','tax_agent')
    def export(year):
        s=summary(year);out=io.StringIO();w=csv.writer(out)
        def write(*values):
            w.writerow(["'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')) else v for v in values])
        write('Expense Pilot home-office record',f'FY {year}–{year+1}','Deduction estimate, not a tax refund')
        write('Method',s['settings']['method'],'Status',s['status'],'Hourly rate (cents)',s['rate_cents'])
        write('Scope','Recorded minutes','Fixed-rate hours estimate AUD','Separate deductions estimate AUD')
        for scope in ('work','business'): write(scope,s['minutes'][scope],None if s['hourly'][scope] is None else s['hourly'][scope]/100,s['extras'][scope]/100)
        write('Hourly deduction included in recorded forecast AUD',
              s['hourly']['work']/100 if s['active'] and s['settings']['method']=='fixed' else 0,
              s['hourly']['business']/100 if s['active'] and s['settings']['method']=='fixed' else 0)
        for issue in s['fixed_issues']+s['warnings']: write('Review',issue)
        write('Diary ID','Date','Start','End','Timezone','Break minutes','Scope','Activity','Created UTC','Updated UTC')
        for e in s['entries']: write(e['id'],e['date'],e['start_time'],e['end_time'],e['timezone'],e['break_minutes'],e['scope'],e['activity'],e['created_at'],e['updated_at'])
        write('Bill ID','Date','Merchant','Type','Original AUD','Assessed base AUD','Assessed employment amount AUD','Assessed business amount AUD','Receipt ID','Reimbursed','Review status','Notes / separate deduction basis','Recorded forecast employment AUD','Recorded forecast business AUD')
        for e in s['costs']:
            effective=adjusted(e,s) if e['status']=='ready' else (0,0)
            write(e['id'],e['date'],e['merchant'],e['home_office_kind'],e['amount_cents']/100,None if e['claim_base_cents'] is None else e['claim_base_cents']/100,e['actual_work_cents']/100,e['actual_business_cents']/100,e['receipt_id'],e['reimbursed'],e['status'],e['basis'],effective[0]/100,effective[1]/100)
        write('Allowance ID','Date','Employer','Amount AUD','Already in recorded gross pay','Notes')
        for a in s['allowances']: write(a['id'],a['date'],a['employer'],a['amount_cents']/100,bool(a['included_in_pay']),a['notes'])
        write('Source',SOURCE,'Checked',s['rules_checked'])
        write('History UTC','Actor ID','Record','Action','Before JSON','After JSON')
        # Preserve the complete audit trail, including removed entries; no 500-row display limit in exports.
        for h in rows('SELECT * FROM home_office_history WHERE owner_id=? ORDER BY id',(owner_id(),)):
            before=json.loads(h['before_json'] or '{}');after=json.loads(h['after_json'] or '{}')
            dates=[v.get('date','') for v in (before,after)]
            if h['entity']==f'year:{year}' or any(d and financial_year(d)==year for d in dates):
                write(h['at'],h['actor_id'],h['entity'],h['action'],h['before_json'],h['after_json'])
        return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name=f'expense-pilot-home-office-{year}-{year+1}.csv')
