"""Finance routes endpoints and services."""
from app import app, auth

def csv_rows(file):
    from app import csv, fail, io
    try:
        content=file.read().decode('utf-8-sig'); dialect=csv.Sniffer().sniff(content[:8192],delimiters=',;\t');data=list(csv.reader(io.StringIO(content),dialect))
    except Exception: fail('Cannot parse CSV. Export as UTF-8 CSV with a header row.')
    if len(data)>5001 or len(data)<2: fail('Use a header and 1–5,000 transaction rows.')
    return data


@app.post('/api/import/preview')
@auth('owner','tax_agent')
def import_preview():
    from app import csv_rows, fail, jsonify, request
    f=request.files.get('file')
    if not f: fail('Choose a CSV file.')
    data=csv_rows(f);return jsonify(headers=data[0],sample=data[1:7],count=len(data)-1)


@app.post('/api/import')
@auth('owner','tax_agent')
def bank_import():
    from app import HTTPException, audit, csv_rows, datetime, db, fail, hashlib, json, jsonify, money, one, record_user_id, request, textval
    f=request.files.get('file')
    if not f: fail('Choose a CSV file.')
    data=csv_rows(f)
    try: m=json.loads(request.form.get('mapping','{}'));aid=int(m['account_id']);dc=int(m['date']);mc=int(m['merchant']);ac=int(m['amount'])
    except Exception: fail('Map account, date, description and amount columns.')
    if not one('SELECT * FROM accounts WHERE id=?',(aid,)): fail('Choose a bank account.')
    if min(dc,mc,ac)<0 or max(dc,mc,ac)>=len(data[0]): fail('Invalid column mapping.')
    mode=m.get('sign');fmt=m.get('date_format')
    if mode not in ('negative','positive') or fmt not in ('%d/%m/%Y','%d/%m/%y','%Y-%m-%d','%m/%d/%Y'): fail('Choose date format and debit sign.')
    parsed=[];seen={};skipped=0
    for idx,row in enumerate(data[1:],2):
        if not any(x.strip() for x in row): continue
        try:
            when=datetime.strptime(row[dc].strip(),fmt).date().isoformat();merchant=textval(row[mc],200);value=row[ac].strip().replace('(','-').replace(')','')
            amount=money(value) if value else 0
            if not merchant: raise ValueError()
        except (ValueError,IndexError,HTTPException): fail(f'Row {idx} is invalid. Nothing was imported. Check dates and amounts.')
        amount=-amount if mode=='negative' else amount
        if amount<=0: skipped+=1;continue
        canonical=json.dumps([aid,when,merchant,amount]);seen[canonical]=seen.get(canonical,0)+1;key=hashlib.sha256((canonical+'|'+str(seen[canonical])).encode()).hexdigest();parsed.append((when,merchant,amount,key))
    added=duplicate=0
    for when,merchant,amount,key in parsed:
        c=db().execute("INSERT OR IGNORE INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,account_id,import_key) VALUES (?,?,?,?,'personal','Uncategorised',0,?,?)",(record_user_id(),when,merchant,amount,aid,key))
        if c.rowcount: added+=1
        else: duplicate+=1
    audit('bank CSV imported',json.dumps({'account':aid,'added':added,'duplicates':duplicate,'credits_skipped':skipped}));db().commit();return jsonify(added=added,duplicates=duplicate,credits_skipped=skipped)


@app.get('/api/export')
@auth('owner','tax_agent')
def export():
    from app import Decimal, allocations, csv, date, day, io, one, percentages, request, rows, send_file, visible
    w,a=visible();start=request.args.get('start');end=request.args.get('end')
    if start: w+=' AND e.date>=?';a.append(day(start))
    if end: w+=' AND e.date<=?';a.append(day(end))
    data=rows(f'SELECT e.*,u.name AS owner,t.location FROM expenses e JOIN users u ON u.id=e.user_id LEFT JOIN trips t ON t.id=e.trip_id WHERE {w} ORDER BY date',a)
    from overnights import is_overnight
    ledger=request.args.get('ledger','all')
    if ledger not in ('all','ordinary','overnight'):
        from app import fail
        fail('Choose a valid expense ledger.')
    if ledger!='all': data=[e for e in data if is_overnight(e)==(ledger=='overnight')]
    out=io.StringIO();writer=csv.writer(out);writer.writerow(['ID','Date','Person','Merchant','Scope','Category','Amount AUD','Use %','Reimbursed','Allocated amount AUD (not tax determination)','Status','Overnight location','Meal','Receipt ID','Notes','Vehicle','Vehicle registration','Employment %','Business %','Personal %','Employment allocation AUD','Business allocation AUD'])
    def safe(v):
        s=str(v or '')
        return "'"+s if s.lstrip().startswith(('=','+','-','@','\t','\r')) else s
    from expense_workflows import components
    for e in [part for original in data for part in components(original)]:
        vehicle_record=one('SELECT name,registration FROM vehicles WHERE id=?',(e.get('vehicle_id'),)) or {}
        work,business=allocations(e);wp,bp=percentages(e);alloc=Decimal(work+business)/100
        writer.writerow([e['id'],date.fromisoformat(e['date']).strftime('%d/%m/%Y'),safe(e['owner']),safe(e['merchant']),e['scope'],e['category'],f"{e['amount_cents']/100:.2f}",e['percent'],e['reimbursed'],f'{alloc:.2f}',e['status'],safe(e['location']),e['meal'],e['receipt_id'],safe(e['notes']),safe(vehicle_record.get('name','')),safe(vehicle_record.get('registration','')),wp,bp,100-wp-bp,f'{work/100:.2f}',f'{business/100:.2f}'])
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='expense-pilot-expenses.csv')


@app.route('/api/employment',methods=['GET','POST'])
@auth('owner','tax_agent')
def employment_income():
    from app import audit, db, employment_values, jsonify, request, rows
    if request.method=='GET': return jsonify(rows('SELECT * FROM employment_income ORDER BY date DESC,id DESC'))
    import income_documents
    d=request.get_json();values=employment_values(d);meta=income_documents.metadata(d)
    db().execute('BEGIN IMMEDIATE');income_documents.check_overlap(values,meta)
    c=db().execute('INSERT INTO employment_income(date,employer,gross_cents,withheld_cents,notes,record_kind,period_start,period_end) VALUES (?,?,?,?,?,?,?,?)',values+meta)
    audit('employment income created',c.lastrowid);db().commit();return jsonify(id=c.lastrowid)


def employment_values(d):
    from app import day, fail, money, textval
    employer=textval(d.get('employer'),200);gross=money(d.get('gross'));withheld=money(d.get('withheld',0))
    if not employer or gross<0 or not 0<=withheld<=gross: fail('Enter employer, non-negative gross pay, and withholding no greater than gross pay.')
    return day(d.get('date')),employer,gross,withheld,textval(d.get('notes'),2000)


@app.route('/api/employment/<int:eid>',methods=['PUT','DELETE'])
@auth('owner','tax_agent')
def edit_employment(eid):
    from app import audit, db, employment_values, fail, jsonify, one, request
    import income_documents
    db().execute('BEGIN IMMEDIATE')
    existing=one('SELECT * FROM employment_income WHERE id=?',(eid,))
    if not existing: fail('Income record not found.',404)
    if one('SELECT 1 FROM bank_reconciliations WHERE income_id=?',(eid,)): fail('Undo the bank deposit match before changing this payment.',409)
    if request.method=='DELETE': db().execute('DELETE FROM employment_income WHERE id=?',(eid,))
    else:
        d=request.get_json() or {}
        if 'version' in d and d['version']!=existing['version']: fail('Income changed. Reopen it before saving.',409)
        values=employment_values(d);meta=income_documents.metadata(d,existing)
        income_documents.check_overlap(values,meta,eid)
        db().execute('UPDATE employment_income SET date=?,employer=?,gross_cents=?,withheld_cents=?,notes=?,record_kind=?,period_start=?,period_end=?,version=version+1 WHERE id=?',values+meta+(eid,))
    audit('employment income updated',eid);db().commit();return jsonify(ok=True)


@app.route('/api/tax/<int:year>',methods=['GET','PUT'])
@auth('owner','tax_agent')
def tax_forecast(year):
    from app import Decimal, TAX_FIELDS, allocations, audit, date, datetime, db, fail, json, jsonify, money, one, request, rows, timedelta, timezone
    if year not in (2024,2025,2026,2027): fail('Choose FY 2024–25 to FY 2027–28.')
    if request.method=='PUT':
        d=request.get_json();settings={}
        for key in TAX_FIELDS:
            value=d.get(key)
            settings[key]=None if value in ('',None) else money(value)
            if settings[key] is not None and settings[key]<0: fail('Forecast inputs cannot be negative.')
        settings['annualise']=d.get('annualise') is True
        db().execute('INSERT INTO tax_settings(year,settings) VALUES (?,?) ON CONFLICT(year) DO UPDATE SET settings=excluded.settings',(year,json.dumps(settings)))
        audit('tax forecast assumptions updated',year);db().commit()
    saved=one('SELECT settings FROM tax_settings WHERE year=?',(year,));settings=json.loads(saved['settings']) if saved else {}
    start=f'{year}-07-01';end=f'{year+1}-06-30'
    salary=one('SELECT COALESCE(SUM(gross_cents),0) gross,COALESCE(SUM(withheld_cents),0) withheld FROM employment_income WHERE date BETWEEN ? AND ?',(start,end))
    # Allocate GST consistently across partial payments before filtering the year.
    payments=rows('SELECT p.*,d.gst_cents,d.total_cents FROM billing_payments p JOIN billing_documents d ON d.id=p.document_id WHERE p.reversed_at IS NULL ORDER BY p.document_id,p.id')
    running={};business_income=0
    from tax_core import rounded,estimate
    for payment in payments:
        before=running.get(payment['document_id'],0);after=before+payment['amount_cents'];running[payment['document_id']]=after
        gst=rounded(Decimal(payment['gst_cents'])*after/payment['total_cents'])-rounded(Decimal(payment['gst_cents'])*before/payment['total_cents'])
        if start<=payment['date']<=end: business_income+=payment['amount_cents']-gst
    expenses=rows("SELECT e.* FROM expenses e JOIN users u ON u.id=e.user_id WHERE e.date BETWEEN ? AND ? AND e.status='ready' AND e.scope!='personal' AND e.reimbursed=0 AND (e.scope='business' OR u.role='owner')",(start,end))
    from overnights import is_overnight
    overnight_expenses=[e for e in expenses if is_overnight(e)]
    from expense_workflows import components
    capitalised={r['expense_id'] for r in rows('SELECT expense_id FROM equipment_assets WHERE expense_id IS NOT NULL')}
    expenses=[part for e in expenses if not is_overnight(e) and e['id'] not in capitalised for part in components(e)]
    from home_office import forecast_adjustments
    home_office,work_deductions,business_deductions=forecast_adjustments(year,expenses)
    salary['gross']+=home_office['allowance_income_cents']
    unreviewed=one("SELECT COUNT(*) n FROM expenses WHERE date BETWEEN ? AND ? AND scope!='personal' AND status='review' AND trip_id IS NULL AND meal='' AND category!='Meals'",(start,end))['n']
    import workspace_time
    current=workspace_time.today();begin=date.fromisoformat(start);finish=date.fromisoformat(end)
    elapsed=max(1,min((current-begin).days+1,(finish-begin).days+1));factor=Decimal((finish-begin).days+1)/elapsed if settings.get('annualise') and begin<=current<=finish else Decimal(1)
    def value(key,recorded=0):
        v=settings.get(key)
        return v if v is not None else rounded(Decimal(recorded)*factor)
    forecast=dict(salary_cents=value('annual_salary',salary['gross']),withheld_cents=value('annual_withheld',salary['withheld']),business_income_cents=value('annual_business_income',business_income),business_deductions_cents=value('annual_business_deductions',business_deductions),work_deductions_cents=value('annual_work_deductions',work_deductions))
    import equipment
    equipment_work,equipment_business=equipment.deductions(year)
    work_deductions+=equipment_work;business_deductions+=equipment_business
    if settings.get('annual_work_deductions') is None: forecast['work_deductions_cents']+=equipment_work
    if settings.get('annual_business_deductions') is None: forecast['business_deductions_cents']+=equipment_business
    # A loss is carried for adviser review rather than silently offsetting salary.
    profit=forecast['business_income_cents']-forecast['business_deductions_cents']+(settings.get('gst_credits') or 0)
    taxable=forecast['salary_cents']+max(0,profit)-forecast['work_deductions_cents']+(settings.get('other_income') or 0)-(settings.get('other_deductions') or 0)
    result=estimate(taxable,year,forecast['withheld_cents'],settings.get('instalments') or 0,settings.get('medicare_override'),settings.get('other_tax') or 0,settings.get('set_aside') or 0)
    return jsonify(year=year,start=start,end=end,settings=settings,recorded=dict(salary_cents=salary['gross'],withheld_cents=salary['withheld'],business_income_cents=business_income,business_deductions_cents=business_deductions,work_deductions_cents=work_deductions,overnight_work_cents=sum(allocations(e)[0] for e in overnight_expenses),overnight_business_cents=sum(allocations(e)[1] for e in overnight_expenses)),forecast=forecast,estimate=result,business_loss_cents=max(0,-profit),unreviewed=unreviewed,projection_factor=float(factor),as_of=current.isoformat(),home_office=dict(status=home_office['status'],method=home_office['settings']['method'],active=home_office['active'],hourly=home_office['hourly'] if home_office['active'] and home_office['settings']['method']=='fixed' else dict(work=0,business=0),allowance_income_cents=home_office['allowance_income_cents']))
