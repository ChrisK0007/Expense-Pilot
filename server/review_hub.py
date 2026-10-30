"""One actionable queue and record-linked adviser questions."""
import json
from flask import jsonify, request, g
from workflow_core import body, integer, fiscal, now

RECORDS={'expense':('expenses','merchant'),'income':('employment_income','employer'),'receipt':('receipts','filename'),
         'document':('tax_documents','title'),'journey':('vehicle_journeys','purpose'),'asset':('equipment_assets','name'),'invoice':('billing_documents','number')}


def question_record(kind,ident):
    from app import one, fail, record_user_id
    if kind not in RECORDS: fail('Choose a supported record type.')
    table,label=RECORDS[kind];record=one('SELECT * FROM '+table+' WHERE id=?',(str(ident),))
    if not record or record.get('user_id',record_user_id())!=record_user_id(): fail('Record not found.',404)
    if kind=='journey' and not one('SELECT 1 FROM vehicles WHERE id=? AND user_id=?',(record['vehicle_id'],record_user_id())): fail('Record not found.',404)
    return record[label]


def attention(year):
    from app import rows, one, record_user_id
    year,start,end=fiscal(year);uid=record_user_id();items=[]
    def add(kind,ident,label,detail,when='',amount=0,priority=2,page='receipts'):
        items.append(dict(kind=kind,id=ident,title=label,detail=detail,date=when,amount_cents=amount,priority=priority,page=page))
    for r in rows("SELECT r.id,r.filename,d.uploaded_at,d.scan_status,d.scan_error FROM receipts r LEFT JOIN receipt_details d ON d.receipt_id=r.id WHERE r.user_id=? AND COALESCE(d.scan_error,'')<>'' AND NOT EXISTS(SELECT 1 FROM expenses e WHERE e.receipt_id=r.id) AND NOT EXISTS(SELECT 1 FROM employment_income i WHERE i.receipt_id=r.id)",(uid,)):
        add('receipt',r['id'],r['filename'],r['scan_error'] or 'Review the saved original and extracted draft.',(r['uploaded_at'] or '')[:10],priority=1 if r['scan_error'] else 2)
    for e in rows("SELECT * FROM expenses WHERE status='review' AND date BETWEEN ? AND ?",(start,end)):
        add('expense',e['id'],e['merchant'],'Check category, allocations and evidence.',e['date'],e['amount_cents'],page='expenses')
    for b in rows("SELECT b.* FROM bank_transactions b JOIN pocketsmith_accounts a ON a.id=b.feed_account_id WHERE a.enabled=1 AND (b.changed=1 OR b.missing=1) AND (b.expense_id IS NOT NULL OR EXISTS(SELECT 1 FROM bank_reconciliations r WHERE r.bank_id=b.id)) AND b.date BETWEEN ? AND ? AND b.source_status='posted' AND b.is_transfer=0",(start,end)):
        add('bank',b['id'],b['payee'],'Bank source changed or disappeared; review the linked record.' if b['changed'] or b['missing'] else 'Match, categorise or ignore this transaction.',b['date'],abs(b['amount_cents']),1 if b['changed'] or b['missing'] else 2,'banks')
    for j in rows("SELECT j.* FROM vehicle_journeys j JOIN vehicles v ON v.id=j.vehicle_id WHERE v.user_id=? AND j.date BETWEEN ? AND ? AND j.scope IN ('work','business') AND trim(j.purpose)=''",(uid,start,end)):
        add('journey',j['id'],j['origin']+' → '+j['destination'],'Employment or business travel is missing its purpose.',j['date'],page='drive_review')
    import home_office
    if year in (2024,2025,2026,2027):
        h=home_office.summary(year)
        if h['status']=='needs_review': add('home_office',year,'Home-office annual confirmations','Complete the chosen method’s evidence and eligibility checks.',priority=1,page='home_office')
    import bank_matching, equipment
    plan=bank_matching.backfill_plan(strict=False)
    for conflict in (plan or {}).get('conflicts',[]):
        if start<=conflict['date']<=end: add('bank_match',conflict['id'],conflict['merchant'],'More than one expense or bank transaction could match. Choose the correct link.',conflict['date'],conflict['amount_cents'],page='banks')
    for asset in equipment.listing(year):
        if asset['needs_review']: add('asset',asset['id'],asset['name'],'Review the annual depreciation record.',asset['acquired'],page='equipment')
    for q in rows('SELECT * FROM record_questions WHERE user_id=? AND resolved=0',(uid,)):
        add('question',q['id'],'Open question: '+q['record_type']+' #'+q['record_id'],q['question'],q['created_at'][:10],priority=1,page='adviser_questions')
    for e in rows("SELECT * FROM signin_events WHERE user_id=? AND state IN ('failed','unknown') ORDER BY id DESC LIMIT 5",(g.user['id'],)):
        add('security',e['id'],'Sign-in email needs attention',e['error'],priority=1,page='settings')
    return sorted(items,key=lambda r:(r['priority'],r['date'] or '9999',-r['amount_cents'],str(r['id'])))


def register(app,auth):
    @app.get('/api/workflows/question-records',endpoint='workflow_question_choices')
    @auth('owner','tax_agent')
    def records():
        from app import rows,fail,record_user_id
        kind=request.args.get('kind')
        if kind not in RECORDS: fail('Choose a supported record type.')
        table,label=RECORDS[kind]
        if kind=='journey':
            result=rows('SELECT j.id,j.purpose AS label FROM vehicle_journeys j JOIN vehicles v ON v.id=j.vehicle_id WHERE v.user_id=? ORDER BY j.id DESC LIMIT 500',(record_user_id(),))
        else:
            where=' WHERE user_id=?' if kind in ('expense','receipt','document','asset') else ''
            result=rows('SELECT id,'+label+' AS label FROM '+table+where+' ORDER BY id DESC LIMIT 500',(record_user_id(),) if where else ())
        for r in result: r['label']=str(r['id'])+' · '+r['label']
        return jsonify(result)

    @app.get('/api/workflows/attention/<int:year>', endpoint='review_hub_queue')
    @auth('owner','tax_agent')
    def queue(year): return jsonify(items=attention(year),notice='This queue covers records received by the server. Check the phone for uploads still waiting on the device.')

    @app.route('/api/workflows/questions',methods=['GET','POST','PUT'], endpoint='review_hub_questions')
    @auth('owner','tax_agent')
    def questions():
        from app import db, rows, one, fail, record_user_id, textval, audit
        uid=record_user_id()
        if request.method=='GET': return jsonify(rows('SELECT q.*,u.name AS author FROM record_questions q LEFT JOIN users u ON u.id=q.author_id WHERE q.user_id=? ORDER BY q.resolved,q.id DESC',(uid,)))
        d=body();db().execute('BEGIN IMMEDIATE')
        if request.method=='POST':
            kind=d.get('record_type');ident=str(d.get('record_id') or '');question_record(kind,ident);text=textval(d.get('question'),3000)
            if not text: fail('Enter a question.')
            ident=db().execute('INSERT INTO record_questions(user_id,record_type,record_id,author_id,question,created_at) VALUES (?,?,?,?,?,?)',(uid,kind,ident,g.user['id'],text,now())).lastrowid
        else:
            ident=integer(d.get('id'),'question ID',1);old=one('SELECT * FROM record_questions WHERE id=? AND user_id=?',(ident,uid))
            if not old: fail('Question not found.',404)
            if d.get('version')!=old['version']: fail('This question changed. Reload it.',409)
            answer=textval(d.get('answer'),3000)
            if not isinstance(d.get('resolved'),bool): fail('Choose whether the question is resolved.')
            db().execute('UPDATE record_questions SET answer=?,resolved=?,version=version+1 WHERE id=?',(answer,int(d['resolved']),ident))
        audit('record question updated',ident);db().commit();return jsonify(id=ident)
