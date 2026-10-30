"""Tax-preparation workspace. Old operational APIs are denied to advisers by default."""
import io
import json
import zipfile
import sqlite3
from flask import g, request, jsonify, send_file
from workflow_core import fiscal, integer, body, digest, now
from expense_core import allocations

SELF_ENDPOINTS={'security.security_status','current','logout','password','delete_account','security.setup_totp','security.confirm_totp',
 'security.disable_totp','security.remember_device','security.devices','signin_alerts_sessions','signin_alerts_signins'}


def guard():
    from app import fail
    if not g.user or g.user['role']!='tax_agent' or not request.path.startswith('/api/'): return
    if request.endpoint in SELF_ENDPOINTS or (request.endpoint or '').startswith('adviser_'): return
    fail('This account has access to the shared tax workspace only.',403)


def owner_id():
    from app import one
    return one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")['id']


def scope(agent_id=None):
    from app import rows,one,fail
    aid=g.user['id'] if g.user['role']=='tax_agent' else agent_id
    if aid is None: return None
    if not one("SELECT 1 FROM users WHERE id=? AND role='tax_agent'",(aid,)): fail('Tax agent not found.',404)
    return dict(years=[r['year'] for r in rows('SELECT year FROM adviser_years WHERE agent_id=? ORDER BY year DESC',(aid,))],
                documents=[r['document_id'] for r in rows('SELECT document_id FROM adviser_documents WHERE agent_id=?',(aid,))])


def allowed_year(year,agent_id=None):
    from app import fail
    year,start,end=fiscal(year);access=scope(agent_id)
    if access is not None and year not in access['years']: fail('This financial year has not been shared.',403)
    return year,start,end,access


def fields(record,names): return {k:record[k] for k in names.split() if k in record}


def snapshot(year,agent_id=None):
    from app import rows,one
    import equipment
    year,start,end,access=allowed_year(year,agent_id);uid=owner_id()
    expense_keys='id date merchant amount_cents scope category work_percent business_percent reimbursed notes trip_id meal receipt_id status vehicle_id items_json'
    classified={c['expense_id']:c for c in rows('SELECT h.* FROM home_office_costs h JOIN expenses e ON e.id=h.expense_id WHERE e.user_id=? AND e.date BETWEEN ? AND ?',(uid,start,end))}
    expenses=[]
    for e in rows('SELECT * FROM expenses WHERE user_id=? AND date BETWEEN ? AND ? ORDER BY date,id',(uid,start,end)):
        parts=allocations({**e,'reimbursed':False})
        if not any(parts) and e['id'] not in classified: continue
        value=fields(e,expense_keys);value['token']=digest(value)
        value['employment_cents'],value['business_cents']=allocations(e)
        value['home_office_treatment']=classified.get(e['id']);expenses.append(value)
    employment=[fields(r,'id date employer gross_cents withheld_cents notes receipt_id record_kind period_start period_end version') for r in rows('SELECT * FROM employment_income WHERE date BETWEEN ? AND ? ORDER BY date,id',(start,end))]
    invoices=[fields(r,'id number state issue_date due_date subtotal_cents gst_cents total_cents tax_mode') for r in rows("SELECT * FROM billing_documents WHERE kind='invoice' AND state NOT IN ('draft','void') AND (issue_date BETWEEN ? AND ? OR id IN (SELECT document_id FROM billing_payments WHERE date BETWEEN ? AND ? AND reversed_at IS NULL)) ORDER BY issue_date,id",(start,end,start,end))]
    invoice_ids={r['id'] for r in invoices}
    payments=[fields(r,'id document_id date amount_cents reference') for r in rows('SELECT * FROM billing_payments WHERE date BETWEEN ? AND ? AND reversed_at IS NULL ORDER BY date,id',(start,end)) if r['document_id'] in invoice_ids]
    assets=[]
    for a in equipment.listing(year):
        if a['acquired']>end or a['disposal_date'] and a['disposal_date']<start: continue
        if not a['work_percent']+a['business_percent'] and not any(u['work_percent']+u['business_percent'] for u in a['usage'] if u['year']<=year): continue
        value=fields(a,'id name acquired cost_cents work_percent business_percent disposal_date proceeds_cents notes receipt_id version opening_cents closing_cents current calculation')
        if a['disposal_date']>end: value.update(disposal_date='',proceeds_cents=0)
        value['history']=[r for r in a['history'] if r['year']<=year];value['schedule']=[r for r in a['schedule'] if r['year']<=year]
        assets.append(value)
    docs=[fields(r,'id title filename content_type category year notes version') for r in rows('SELECT * FROM tax_documents WHERE user_id=? AND (year=? OR year IS NULL) ORDER BY title,id',(uid,year)) if access is None or r['id'] in access['documents']]
    receipts={r['receipt_id'] for r in expenses+employment+assets if r.get('receipt_id')}
    originals=[fields(r,'id filename mime') for r in rows('SELECT * FROM receipts WHERE user_id=?',(uid,)) if r['id'] in receipts]
    journeys=rows('SELECT j.* FROM vehicle_journeys j JOIN vehicles v ON v.id=j.vehicle_id WHERE v.user_id=? AND j.date BETWEEN ? AND ? ORDER BY j.date,j.id',(uid,start,end))
    mileage=[fields(r,'id vehicle_id date origin destination purpose scope odometer_start odometer_end distance_m percent') for r in journeys if r['scope'] in ('work','business')]
    vehicles=[]
    for v in rows('SELECT id,name,registration FROM vehicles WHERE user_id=?',(uid,)):
        logged=[j for j in journeys if j['vehicle_id']==v['id']]
        if not any(j['scope'] in ('work','business') for j in logged) and not any(e['vehicle_id']==v['id'] for e in expenses): continue
        v.update(total_logged_m=sum(j['distance_m'] for j in logged),personal_logged_m=sum(j['distance_m'] for j in logged if j['scope']=='personal'))
        vehicles.append(v)
    data=dict(expenses=expenses,employment=employment,invoices=invoices,payments=payments,equipment=assets,documents=docs,originals=originals,mileage=mileage,vehicles=vehicles,
              home_office=[fields(r,'id date start_time end_time break_minutes scope activity version') for r in rows('SELECT * FROM home_office_entries WHERE user_id=? AND deleted=0 AND date BETWEEN ? AND ? ORDER BY date,id',(uid,start,end))],
              home_office_allowances=[fields(r,'id date employer amount_cents included_in_pay notes') for r in rows('SELECT * FROM home_office_allowances WHERE user_id=? AND date BETWEEN ? AND ?',(uid,start,end))],
              annual_income_comparisons=[fields(r,'employer gross_cents withheld_cents notes') for r in rows('SELECT * FROM annual_income_checks WHERE user_id=? AND year=?',(uid,year))])
    vehicle_ids={v['id'] for v in vehicles}
    data['vehicle_claim_settings']=[fields(v,'vehicle_id year work_percent business_percent depreciation_cents logbook_start logbook_end notes') for v in rows('SELECT * FROM vehicle_comparison_settings WHERE year=?',(year,)) if v['vehicle_id'] in vehicle_ids]
    from datetime import datetime
    import workspace_time
    data['odometer']=[fields(o,'vehicle_id recorded_at reading_m') for o in rows('SELECT * FROM vehicle_odometer') if o['vehicle_id'] in vehicle_ids and start<=datetime.fromtimestamp(o['recorded_at'],workspace_time.zone()).date().isoformat()<=end]
    trip_ids={e['trip_id'] for e in expenses if e['trip_id']}
    data['overnight_trips']=[fields(t,'id scope location start end purpose allowance_cents') for t in rows('SELECT * FROM trips WHERE user_id=?',(uid,)) if t['id'] in trip_ids]
    import home_office
    if year in (2024,2025,2026,2027):
        h=home_office.summary(year);data['home_office_summary']=fields(h,'status hourly active minutes rate_cents fixed extras fixed_issues warnings allowance_income_cents')
        data['home_office_summary']['settings']=h.get('settings',{})
    else: data['home_office_summary']={}
    # Tax assumptions are relevant; savings/set-aside targets are personal budgeting.
    raw=one('SELECT settings FROM tax_settings WHERE year=?',(year,));settings=json.loads(raw['settings']) if raw else {}
    data['tax_assumptions']={k:v for k,v in settings.items() if k!='set_aside'}
    relevant={'expense':{str(e['id']) for e in expenses},'income':{str(e['id']) for e in employment},'invoice':{str(e['id']) for e in invoices},
              'asset':{str(e['id']) for e in assets},'document':{e['id'] for e in docs},'receipt':receipts,'journey':{str(e['id']) for e in mileage}}
    data['questions']=[fields(q,'id record_type record_id question answer resolved version created_at author') for q in rows("SELECT q.*,COALESCE(u.name,'Former account') AS author FROM record_questions q LEFT JOIN users u ON u.id=q.author_id WHERE q.user_id=? ORDER BY q.resolved,q.id DESC",(uid,)) if str(q['record_id']) in relevant.get(q['record_type'],set())]
    return dict(year=year,start=start,end=end,owner=one('SELECT name FROM users WHERE id=?',(uid,))['name'],records=data)


def permitted_record(data,kind,ident):
    from app import fail
    group={'expense':'expenses','income':'employment','asset':'equipment','invoice':'invoices','document':'documents','receipt':'originals','journey':'mileage'}.get(kind)
    record=next((r for r in data['records'].get(group,[]) if str(r['id'])==str(ident)),None)
    if not record: fail('Record not shared in this financial year.',404)
    return record


def export(year,agent_id=None):
    from app import DATA,db,fail
    from annual_handover import csv_bytes
    from record_reports import Report,aud
    import hashlib
    stream=io.BytesIO();db().execute('BEGIN IMMEDIATE')
    try:
        data=snapshot(year,agent_id);records=data['records'];report=Report('Tax return records',f"1 July {year} – 30 June {year+1}");report.cover(data['owner'])
        report.add('Shared tax-preparation records. Allocations and calculated estimates require tax-treatment assessment. Originals can contain private details on mixed-use documents.')
        report.table(['Measure','AUD'],[['Employment gross',aud(sum(r['gross_cents'] for r in records['employment']))],['PAYG withheld',aud(sum(r['withheld_cents'] for r in records['employment']))],['Employment expense allocations',aud(sum(r['employment_cents'] for r in records['expenses']))],['Business expense allocations',aud(sum(r['business_cents'] for r in records['expenses']))]],[130,44])
        report.add('Equipment purchases remain in spending and must not be deducted twice. See annual equipment calculations, WFH records, invoice payments and tax assumptions for the selected treatment. The package does not lodge a return.')
        with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as out:
            checks={};total=0
            def add(name,content): out.writestr(name,content);checks[name]=hashlib.sha256(content).hexdigest()
            add('tax-summary.pdf',report.build())
            for name,values in records.items(): add('registers/'+name+'.csv',csv_bytes(values if isinstance(values,list) else [values]))
            for group,values in [('receipts',records['originals']),('documents',records['documents'])]:
                for r in values:
                    path=DATA/group/r['id']
                    if not path.is_file(): fail('A shared original is missing. Restore it before exporting.',409)
                    total+=path.stat().st_size
                    if total>256*1024*1024: fail('Shared evidence exceeds 256 MB. Download documents individually.',413)
                    add('originals/'+group+'/'+r['id']+('.pdf' if r.get('mime',r.get('content_type'))=='application/pdf' else '.bin'),path.read_bytes())
            add('records.json',json.dumps(data).encode())
            out.writestr('manifest.json',json.dumps(dict(year=year,created_at=now(),sha256=checks)))
        db().commit()
    except BaseException: db().rollback();raise
    stream.seek(0);return stream


def register(app,auth):
    @app.route('/api/users/<int:aid>/sharing',methods=['GET','PUT'],endpoint='owner_adviser_sharing')
    @auth('owner')
    def sharing(aid):
        from app import db,rows,fail,audit
        old=scope(aid)
        if request.method=='PUT':
            d=body();years=d.get('years');documents=d.get('documents')
            if not isinstance(years,list) or len(years)>100 or not isinstance(documents,list): fail('Choose shared years and supporting documents.')
            years=sorted({integer(y,'financial year',1900,2098) for y in years})
            valid={r['id'] for r in rows('SELECT id FROM tax_documents WHERE user_id=?',(owner_id(),))}
            if not all(isinstance(v,str) and v in valid for v in documents): fail('Choose existing supporting documents.')
            db().execute('BEGIN IMMEDIATE');db().execute('DELETE FROM adviser_years WHERE agent_id=?',(aid,));db().execute('DELETE FROM adviser_documents WHERE agent_id=?',(aid,))
            db().executemany('INSERT INTO adviser_years VALUES (?,?)',[(aid,y) for y in years]);db().executemany('INSERT INTO adviser_documents VALUES (?,?)',[(aid,x) for x in set(documents)])
            audit('tax agent sharing updated',json.dumps(dict(agent_id=aid,years=years,documents=documents)));db().commit();old=scope(aid)
        return jsonify(**old,available_documents=rows('SELECT id,title,year FROM tax_documents WHERE user_id=? ORDER BY title',(owner_id(),)))

    @app.delete('/api/users/<int:aid>',endpoint='owner_remove_adviser')
    @auth('owner')
    def remove_agent(aid):
        from app import db,one,fail,audit
        d=body();agent=one("SELECT * FROM users WHERE id=? AND role='tax_agent'",(aid,))
        if not agent: fail('Tax agent not found.',404)
        if d.get('confirmation')!=agent['email']: fail('Enter the tax agent email address to confirm removal.')
        db().execute('BEGIN IMMEDIATE')
        try:
            # Preserve rare legacy records created in the agent's own name.
            for table in ('expenses','trips','receipts','vehicles','equipment_assets','tax_documents','home_office_entries','home_office_allowances','home_office_settings','workflow_changes','record_questions','annual_income_checks','billing_document_requests'):
                db().execute('UPDATE '+table+' SET user_id=? WHERE user_id=?',(owner_id(),aid))
            db().execute('UPDATE home_office_history SET owner_id=? WHERE owner_id=?',(owner_id(),aid))
            audit('tax agent removed',json.dumps(dict(id=aid,name=agent['name'],email=agent['email'])))
            db().execute('DELETE FROM users WHERE id=?',(aid,));db().commit()
        except sqlite3.IntegrityError:
            db().rollback();fail('This legacy login still owns dependent records. Its financial records were preserved.',409)
        return jsonify(ok=True)

    @app.get('/api/adviser',endpoint='adviser_scope')
    @auth('owner','tax_agent')
    def get_scope(): return jsonify(**(scope() or dict(years=[],documents=[])),permission=g.user.get('permission'))

    @app.get('/api/adviser/<int:year>',endpoint='adviser_snapshot')
    @auth('owner','tax_agent')
    def get_snapshot(year):
        agent=integer(request.args['agent_id'],'tax agent ID',1) if g.user['role']=='owner' and 'agent_id' in request.args else None
        return jsonify(snapshot(year,agent))

    @app.get('/api/adviser/<int:year>/export',endpoint='adviser_export')
    @auth('owner','tax_agent')
    def download_export(year):
        agent=integer(request.args['agent_id'],'tax agent ID',1) if g.user['role']=='owner' and 'agent_id' in request.args else None
        stream=export(year,agent);return send_file(stream,mimetype='application/zip',as_attachment=True,download_name=f'expense-pilot-tax-{year}-{year+1}.zip')

    @app.get('/api/adviser/<int:year>/source/<kind>/<ident>',endpoint='adviser_source')
    @auth('owner','tax_agent')
    def source(year,kind,ident):
        from app import fail
        permitted_record(snapshot(year),kind,ident)
        if kind=='receipt': return app.view_functions['download'](rid=ident)
        if kind=='document': return app.view_functions['document_download'](did=ident)
        if kind=='invoice': return app.view_functions['billing.download_pdf'](did=int(ident))
        fail('Choose a shared source document.',404)

    @app.route('/api/adviser/<int:year>/questions',methods=['POST','PUT'],endpoint='adviser_questions')
    @auth('owner','tax_agent')
    def questions(year):
        from app import db,one,fail,record_user_id
        d=body();data=snapshot(year)
        if request.method=='PUT':
            q=next((q for q in data['records']['questions'] if q['id']==d.get('id')),None)
            if not q: fail('Question not shared.',404)
        else: permitted_record(data,d.get('record_type'),d.get('record_id'))
        return app.view_functions['review_hub_questions']()

    @app.put('/api/adviser/<int:year>/<kind>/<int:ident>',endpoint='adviser_adjustment')
    @auth('owner','tax_agent')
    def adjustment(year,kind,ident):
        from app import db,one,fail,can_write,textval,audit,category_names
        from expense_core import split_values
        if not can_write(): fail('Read-only access.',403)
        d=body();db().execute('BEGIN IMMEDIATE');old=permitted_record(snapshot(year),kind,ident)
        if kind=='expense':
            if set(d)-{'token','category','notes','status','work_percent','business_percent'}: fail('Only tax classification can be adjusted here.')
            if d.get('token')!=old['token']: fail('Expense changed. Reload before saving.',409)
            if json.loads(old['items_json']): fail('Ask the owner to adjust an itemised receipt.')
            if old['trip_id'] or old['meal'] or old['vehicle_id'] or old['category']=='Meals' or d.get('category')=='Meals' or one('SELECT 1 FROM home_office_costs WHERE expense_id=?',(ident,)):
                fail('Ask the owner to adjust expenses with meals, trip, vehicle or home-office treatment.')
            if one('SELECT 1 FROM equipment_assets WHERE expense_id=?',(ident,)): fail('Use equipment annual records for this purchase.')
            try: work,business=split_values(d)
            except ValueError as exc: fail(str(exc))
            if work+business==0: fail('Ask the owner to move this record to personal spending.')
            if d.get('category') not in category_names() or d.get('status') not in ('review','ready'): fail('Choose a valid category and review state.')
            target='split' if work and business else 'work' if work else 'business'
            db().execute('UPDATE expenses SET category=?,notes=?,status=?,work_percent=?,business_percent=?,scope=?,percent=? WHERE id=?',(d['category'],textval(d.get('notes'),2000),d['status'],work,business,target,work+business,ident))
            audit('tax agent expense adjustment',json.dumps(dict(id=ident,before=old,after=d)));db().commit();return jsonify(ok=True)
        if kind=='asset':
            if set(d)-{'version','amount','income_use_amount','notes','confirmed'}: fail('Only the annual equipment record can be adjusted here.')
            db().rollback()
            return app.view_functions['equipment_annual'](aid=ident,year=year)
        fail('This record is view-only. Ask the owner to correct its source.',403)
