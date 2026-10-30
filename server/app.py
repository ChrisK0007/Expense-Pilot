import sys
if __name__ == "__main__":
    sys.modules["app"] = sys.modules[__name__]
import os, sqlite3, secrets, hashlib, json, csv, io, base64, urllib.request, urllib.error, re, subprocess, tempfile
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from flask import Flask, request, session, jsonify, g, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from pdf_safety import inspect_pdf
from werkzeug.exceptions import HTTPException
from expense_core import split_values, percentages, allocations
import features
import workspace_time
from version import VERSION

DATA=Path(os.environ.get('DATA_DIR','./data')); DATA.mkdir(parents=True,exist_ok=True)
(DATA/'receipts').mkdir(exist_ok=True)
# Expose the bundled icon through the persistent host appdata mount for Unraid.
# Keep an existing file so a user's replacement icon survives container updates.
logo=DATA/'expense-pilot-logo.png'
if not logo.exists():
    logo_bytes=(Path(__file__).parent/'static'/'expense-pilot-logo.png').read_bytes()
    try:
        with logo.open('xb') as f: f.write(logo_bytes)
        logo.chmod(0o644)
    except FileExistsError: pass
key=DATA/'session.key'
if not key.exists():
    try:
        with key.open('x') as f: f.write(secrets.token_hex(32))
        key.chmod(0o600)
    except FileExistsError: pass
app=Flask(__name__,static_folder='static')
import client_address; client_address.install(app)
app.config.update(SECRET_KEY=key.read_text(), MAX_CONTENT_LENGTH=12*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','false').lower()=='true',PERMANENT_SESSION_LIFETIME=timedelta(days=30))
CATEGORIES=['Uncategorised','Meals','Accommodation','Transport','Vehicle expenses','Bank fees','Phone & internet','Equipment','Uniform','Training','Insurance','Subscriptions','Other']

def db():
    if 'db' not in g:
        g.db=sqlite3.connect(DATA/'rounded.sqlite',timeout=30); g.db.row_factory=sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
        g.db.create_function('ep_casefold',1,lambda value:str(value or '').strip().casefold(),deterministic=True)
    return g.db
@app.teardown_appcontext
def close(_):
    if 'db' in g: g.db.close()
def rows(sql,args=()): return [dict(x) for x in db().execute(sql,args).fetchall()]
def one(sql,args=()):
    x=db().execute(sql,args).fetchone(); return dict(x) if x else None
def fail(msg,status=400):
    from flask import abort
    abort(status,description=msg)
def audit(action,entity): db().execute('INSERT INTO audit(user_id,action,entity) VALUES (?,?,?)',(g.user['id'] if getattr(g,'user',None) else None,action,str(entity)))
with app.app_context():
    from migrations import apply
    apply(db())
@app.errorhandler(HTTPException)
def errors(e): return jsonify(error=e.description),e.code
@app.after_request
def headers(r):
    r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY';r.headers['Referrer-Policy']='same-origin'
    r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    r.headers['Cache-Control']='no-store'
    if app.config['SESSION_COOKIE_SECURE']: r.headers['Strict-Transport-Security']='max-age=31536000'
    return r
@app.before_request
def guard():
    g.user=None
    if session.get('uid'):
        g.user=one('SELECT id,name,email,role,active,version,permission,must_change_password,invite_expires,totp_enabled FROM users WHERE id=?',(session['uid'],))
        if not g.user or not g.user['active'] or g.user['role'] not in ('owner','tax_agent') or g.user['version']!=session.get('version') or not security.session_valid(): session.clear(); g.user=None
    if g.user and g.user['must_change_password'] and g.user['invite_expires']<=datetime.now().timestamp():
        session.clear(); g.user=None
    if g.user and g.user['must_change_password'] and request.path.startswith('/api/') and request.path not in ('/api/session','/api/logout','/api/password'):
        fail('Change your temporary password before accessing the workspace.',403)
    if request.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
        if g.user and g.user['role']=='tax_agent' and g.user['permission']!='read_write' and request.path not in ('/api/logout','/api/password','/api/security/2fa/setup','/api/security/2fa/confirm','/api/security/2fa/disable','/api/features','/api/account','/api/notifications/device','/api/security/device-session','/api/security/devices','/api/security/sessions','/api/security/signins','/api/workflows/questions'):
            fail('Read-only access.',403)
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','!')): fail('Reload the page and try again.',403)
def auth(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapped(*a,**kw):
            if not g.user: fail('Please sign in.',401)
            if roles and g.user['role'] not in roles and not (roles==('owner','employee') and can_write()): fail('Access denied.',403)
            return fn(*a,**kw)
        return wrapped
    return deco
def textval(v,n=500): return str(v or '').strip()[:n]
def money(v):
    try:
        d=Decimal(str(v).replace(',','').replace('$',''))
        if not d.is_finite() or abs(d)>Decimal('10000000'): raise ValueError()
        return int((d*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    except (ValueError,InvalidOperation): fail('Enter a valid amount.')
def day(v):
    from date_core import normalise_date
    try: return normalise_date(v)
    except ValueError as exc: fail(str(exc))
def newpass(p):
    if not isinstance(p,str) or len(p)<12 or len(p)>256: fail('Use a password between 12 and 256 characters.')
    return generate_password_hash(p)
def can_write():
    return bool(g.user and (g.user['role'] in ('owner','employee') or g.user.get('permission')=='read_write'))
def record_user_id():
    return one("SELECT id FROM users WHERE role='owner' ORDER BY id LIMIT 1")['id'] if g.user['role']=='tax_agent' else g.user['id']
def visible(alias='e'):
    if g.user['role'] in ('owner','tax_agent'): return '1=1',[]
    return f"{alias}.user_id=? AND {alias}.scope='business'",[g.user['id']]
def expense(eid,write=False):
    where,args=visible(); e=one(f'SELECT e.* FROM expenses e WHERE e.id=? AND {where}',[eid]+args)
    if not e: fail('Expense not found.',404)
    if write and not can_write(): fail('Read-only access.',403)
    return e
@app.get('/')
def index(): return app.send_static_file('index.html')
@app.get('/api/session')
def current():
    if 'csrf' not in session: session['csrf']=secrets.token_hex(24)
    return jsonify(user=g.user,device_session=bool(g.user and session.get('device_name')),csrf=session['csrf'],setup=not bool(one('SELECT id FROM users LIMIT 1')),setup_token_required=bool(os.environ.get('SETUP_TOKEN','')),categories=category_names() if g.user else sorted(CATEGORIES,key=str.casefold),ai_configured=ai_providers.configured(),ai_mode=ai_providers.config()['mode'],ai_label=ai_providers.MODES[ai_providers.config()['mode']],api_version=1,minimum_client_api=1,instance_id=public_release.instance_id(),timezone=workspace_time.name(),business_name=billing_business()['name'] if g.user else '',version=VERSION,capabilities={'review_workflows':True,'receipt_items':True,'signin_alerts':True,'documents':True,'home_office':True,'invoice_request_keys':True,'overnight_comparison':True,'journey_routes':True,'journey_upload_receipts':True,'expense_upload_receipts':True,'receipt_upload_receipts':True,'public_setup':True,'account_deletion':True,'workspace_timezone':True,'journey_places':True,'persistent_device_sessions':True,'notification_events':True,'notification_push':notifications.configured()},features=features.preferences(),mfa_required=bool(session.get('mfa_uid') and session.get('mfa_until',0)>datetime.now().timestamp()))
@app.post('/api/setup')
def setup():
    d=request.get_json(); token=os.environ.get('SETUP_TOKEN','')
    db().execute('BEGIN IMMEDIATE')
    if one('SELECT id FROM users LIMIT 1'): fail('Setup already complete.',409)
    if token and (len(token)<24 or not secrets.compare_digest(textval(d.get('token')).encode(),token.encode())):
        fail('Invalid setup token. Use the token from your Docker configuration or .env file. Configured tokens must contain at least 24 characters.',403)
    name=textval(d.get('name'),100);email=textval(d.get('email'),200).lower()
    if not name or '@' not in email: fail('Name and email are required.')
    from billing import settings, save_settings
    selected_timezone = workspace_time.validate(d.get('timezone', workspace_time.DEFAULT))
    save_settings('workspace', {'timezone': selected_timezone})
    uid = settings('instance', {}).get('owner_id_floor', 1)
    db().execute('INSERT INTO users(id,name,email,password,role) VALUES (?,?,?,?,?)',(uid,name,email,newpass(d.get('password')),'owner'));db().commit()
    return jsonify(ok=True)
@app.post('/api/login')
def login(): return security.login_response()
@app.post('/api/logout')
def logout(): security.revoke_session();db().commit();return jsonify(ok=True)
@app.post('/api/password')
@auth()
def password(): return security.password_response()
@app.route('/api/users',methods=['GET','POST'])
@auth('owner')
def users():
    if request.method=='GET': return jsonify(rows("SELECT id,name,email,role,active,permission,must_change_password,invite_status,invite_expires,totp_enabled FROM users WHERE role IN ('owner','tax_agent')"))
    return security.create_user_response()
@app.put('/api/users/<int:uid>/permission')
@auth('owner')
def user_permission(uid):
    user=one('SELECT * FROM users WHERE id=?',(uid,));permission=request.get_json().get('permission')
    if not user or user['role']!='tax_agent' or permission not in ('read_only','read_write'): fail('Choose a tax agent and a valid permission.')
    db().execute('UPDATE users SET permission=? WHERE id=?',(permission,uid));audit('tax agent permission changed',uid);db().commit()
    return jsonify(ok=True)
@app.post('/api/users/<int:uid>/access')
@auth('owner')
def access(uid):
    u=one('SELECT * FROM users WHERE id=?',(uid,))
    if not u or u['role']!='tax_agent': fail('Cannot change this account.')
    db().execute('UPDATE users SET active=?,version=version+1 WHERE id=?',(int(bool(request.get_json().get('active'))),uid));audit('user access changed',uid);db().commit();return jsonify(ok=True)
@app.route('/api/accounts',methods=['GET','POST'])
@auth('owner','tax_agent')
def accounts():
    if request.method=='GET': return jsonify(rows('SELECT * FROM accounts'))
    d=request.get_json()
    if d.get('bank') not in ('CommBank','Macquarie','American Express','Other') or not textval(d.get('name')): fail('Choose a bank and enter an account label.')
    c=db().execute('INSERT INTO accounts(name,bank) VALUES (?,?)',(textval(d['name'],100),d['bank']));audit('account created',c.lastrowid);db().commit();return jsonify(id=c.lastrowid)
@app.route('/api/trips',methods=['GET','POST'])
@auth()
def trips():
    if request.method=='GET':
        if g.user['role'] in ('owner','tax_agent'): return jsonify(rows('SELECT t.*,u.name AS owner FROM trips t JOIN users u ON u.id=t.user_id ORDER BY start DESC'))
        return jsonify(rows('SELECT * FROM trips WHERE user_id=? ORDER BY start DESC',(g.user['id'],)))
    if not can_write(): fail('Read-only access.',403)
    d=request.get_json();s=day(d.get('start'));e=day(d.get('end'));scope=d.get('scope')
    if e<=s: fail('An overnight trip must end after its start date.')
    if scope not in ('work','business') or (g.user['role']=='employee' and scope!='business'): fail('Invalid trip scope.')
    if not textval(d.get('location')) or not textval(d.get('purpose')): fail('Location and purpose are required.')
    c=db().execute('INSERT INTO trips(user_id,scope,location,start,end,purpose,allowance_cents) VALUES (?,?,?,?,?,?,?)',(record_user_id(),scope,textval(d['location'],100),s,e,textval(d['purpose']),money(d.get('allowance',0))));audit('trip created',c.lastrowid);db().commit();return jsonify(id=c.lastrowid)
def payload(d,existing=None):
    scope=d.get('scope');cat=d.get('category');status=d.get('status','review');uid=existing['user_id'] if existing else record_user_id()
    if scope not in ('work','business','personal','split') or (g.user['role']=='employee' and scope!='business'): fail('Invalid expense scope.')
    if cat not in category_names() or status not in ('review','ready'): fail('Invalid category or status.')
    try: work_pct,business_pct=split_values(d)
    except ValueError as exc: fail(str(exc))
    employee_record=one('SELECT role FROM users WHERE id=?',(uid,))['role']=='employee'
    if employee_record and (work_pct or scope!='business'): fail('Employee expenses must remain in Business.')
    if 'work_percent' in d or 'business_percent' in d:
        scope='split' if work_pct and business_pct else 'work' if work_pct else 'business' if business_pct or employee_record else 'personal'
    percent=work_pct+business_pct
    when=day(d.get('date'));merchant=textval(d.get('merchant'),200)
    if not merchant: fail('Merchant is required.')
    tid=d.get('trip_id') or None;rid=d.get('receipt_id') or None;aid=d.get('account_id') or None;meal=d.get('meal','')
    if meal not in ('','Breakfast','Lunch','Dinner','Incidentals'): fail('Invalid meal type.')
    if meal and (not tid or cat!='Meals'): fail('Link a trip and use the Meals category for an overnight meal.')
    if tid:
        t=one('SELECT * FROM trips WHERE id=?',(tid,))
        if not t or t['user_id']!=uid or (t['scope']!=scope and not (scope=='split' and (work_pct if t['scope']=='work' else business_pct)>0)) or not t['start']<=when<=t['end']: fail('Trip must match the person, expense scope and date.')
    if rid:
        r=one('SELECT * FROM receipts WHERE id=?',(rid,))
        if not r or r['user_id']!=uid: fail('Receipt does not belong to this person.')
        if one('SELECT id FROM employment_income WHERE receipt_id=?',(rid,)): fail('This document is already filed as employment income.',409)
        linked=one('SELECT id FROM expenses WHERE receipt_id=?',(rid,))
        if linked and (not existing or linked['id']!=existing.get('id')): fail('This receipt is already linked to another expense.',409)
    if aid and (not one('SELECT id FROM accounts WHERE id=?',(aid,)) or (g.user['role']=='employee' and (not existing or aid!=existing['account_id']))): fail('Invalid bank account.')
    shared=1
    if scope=='personal': percent=0
    return (when,merchant,money(d.get('amount')),scope,cat,percent,int(bool(d.get('reimbursed'))),textval(d.get('notes'),3000),tid,meal,rid,aid,status,shared,work_pct,business_pct)
@app.route('/api/expenses',methods=['GET','POST'])
@auth()
def expenses():
    if request.method=='GET':
        w,a=visible();return jsonify(rows(f'SELECT e.*,u.name AS owner,t.location FROM expenses e JOIN users u ON u.id=e.user_id LEFT JOIN trips t ON t.id=e.trip_id WHERE {w} ORDER BY e.date DESC,e.id DESC',a))
    if not can_write(): fail('Read-only access.',403)
    db().execute('BEGIN IMMEDIATE')
    d=request.get_json();uid=record_user_id();existing=None
    import mobile_uploads
    ref=mobile_uploads.reference(d.get('client_ref'))
    digest=mobile_uploads.fingerprint(d) if ref else ''
    prior=mobile_uploads.previous(uid,'expense',ref,digest)
    if prior:
        db().commit();return jsonify(mobile_uploads.ack(prior['id'],ref))
    if d.get('meal') and d.get('trip_id'):
        t=one('SELECT * FROM trips WHERE id=?',(d['trip_id'],))
        if not t or (g.user['role']=='employee' and t['user_id']!=g.user['id']): fail('Trip not found.',404)
        uid=t['user_id'];existing={'user_id':uid,'account_id':None}
    if not existing and d.get('vehicle_id'):
        v=tracking_vehicle(d['vehicle_id']);uid=v['user_id'];existing={'user_id':uid,'account_id':None}
    automatic=None
    if d.get('receipt_id') and not d.get('bank_transaction_id'):
        automatic=bank_matching.choose(uid,d)
        if automatic and automatic['expense_id']: fail('This document matches a bank-linked expense. Attach it from Document inbox to avoid a duplicate.',409)
        if automatic: d['account_id']=automatic['local_account_id']
    p=payload(d,existing);c=db().execute('INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,reimbursed,notes,trip_id,meal,receipt_id,account_id,status,shared,work_percent,business_percent) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(uid,)+p);link_vehicle(c.lastrowid,uid,d);bank_matching.attach(c.lastrowid,automatic,d.get('bank_choice')=='cash');pocketsmith.link_created(d,c.lastrowid);mobile_uploads.remember(record_user_id(),'expense',ref,digest,c.lastrowid);audit('expense created',c.lastrowid);db().commit();return jsonify(mobile_uploads.ack(c.lastrowid,ref))
@app.route('/api/expenses/<int:eid>',methods=['PUT','DELETE'])
@auth('owner','employee')
def update_expense(eid):
    db().execute('BEGIN IMMEDIATE')
    e=expense(eid,True)
    if request.method=='DELETE':
        from receipt_routes import delete_receipt_record, remove_receipt_files
        if one('SELECT 1 FROM equipment_assets WHERE expense_id=?',(eid,)) or one('SELECT 1 FROM bank_reconciliations WHERE expense_id=? OR refund_id=?',(eid,eid)): fail('Remove the equipment or reconciliation link before deleting this expense.',409)
        db().execute('DELETE FROM expenses WHERE id=?',(eid,));audit('expense deleted',eid)
        if e['receipt_id']: delete_receipt_record(e['receipt_id'])
    else:
        d=request.get_json();p=payload(d,e);expense_workflows.guard_edit(e,p,d);db().execute('UPDATE expenses SET date=?,merchant=?,amount_cents=?,scope=?,category=?,percent=?,reimbursed=?,notes=?,trip_id=?,meal=?,receipt_id=?,account_id=?,status=?,shared=?,work_percent=?,business_percent=? WHERE id=?',p+(eid,));link_vehicle(eid,e['user_id'],d,e);audit('expense updated',eid)
    db().commit()
    if request.method=='DELETE' and e['receipt_id']: remove_receipt_files(e['receipt_id'])
    return jsonify(ok=True)


@app.get('/api/audit')
@auth('owner')
def history(): return jsonify(rows('SELECT a.*,u.name FROM audit a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200'))

@app.route('/api/trips/<int:tid>',methods=['PUT','DELETE'])
@auth('owner','employee')
def update_trip(tid):
    t=one('SELECT * FROM trips WHERE id=?',(tid,))
    if not t or (g.user['role']=='employee' and t['user_id']!=g.user['id']): fail('Trip not found.',404)
    linked=rows('SELECT * FROM expenses WHERE trip_id=?',(tid,))
    if request.method=='DELETE':
        if linked: fail('Unlink expenses before deleting this trip.',409)
        db().execute('DELETE FROM trips WHERE id=?',(tid,));audit('trip deleted',tid)
    else:
        d=request.get_json();start=day(d.get('start'));end=day(d.get('end'));scope=d.get('scope')
        if end<=start: fail('An overnight trip must end after its start date.')
        if scope not in ('work','business') or (g.user['role']=='employee' and scope!='business'): fail('Invalid scope.')
        if any((e['scope']!=scope and not (e['scope']=='split' and percentages(e)[0 if scope=='work' else 1]>0)) or not start<=e['date']<=end for e in linked): fail('This change would exclude linked expenses. Update or unlink those expenses first.',409)
        if not textval(d.get('location')) or not textval(d.get('purpose')): fail('Location and purpose are required.')
        db().execute('UPDATE trips SET scope=?,location=?,start=?,end=?,purpose=?,allowance_cents=?,comparison_version=comparison_version+1 WHERE id=?',(scope,textval(d['location'],100),start,end,textval(d['purpose']),money(d.get('allowance',0)),tid));audit('trip updated',tid)
    db().commit();return jsonify(ok=True)

import overnights
overnights.register(app, auth)

# Employment ledger and one resident/sole-trader tax forecast for the owner's workspace.


TAX_FIELDS=('annual_salary','annual_withheld','annual_business_income','annual_business_deductions','annual_work_deductions','other_income','other_deductions','gst_credits','instalments','medicare_override','other_tax','set_aside')

from receipt_routes import upload, receipt, download, receipt_info, preview_receipt, extract, confirm_receipt_currency, receipt_inbox, categorise_receipt, delete_receipt

from finance_routes import csv_rows, import_preview, bank_import, export, employment_income, employment_values, edit_employment, tax_forecast

from tracking import body as tracking_body, register as register_tracking, category_names, draft_for, link_vehicle, profile as receipt_profile, vehicle as tracking_vehicle
register_tracking(app, db=db, one=one, rows=rows, fail=fail, audit=audit, can_write=can_write, record_user_id=record_user_id, textval=textval, money=money, day=day, receipt=receipt, payload=payload, BASE_CATEGORIES=CATEGORIES)

from billing import register as register_billing, business as billing_business
register_billing(app, db, one, rows, fail, audit, DATA)

import security
app.session_interface=security.DeviceSessionInterface()
security.register(app, db=db, one=one, fail=fail, audit=audit, newpass=newpass, textval=textval, DATA=DATA)

features.register(app, db=db, one=one, fail=fail)

import pocketsmith
pocketsmith.register(app, db=db, one=one, rows=rows, fail=fail, audit=audit, auth=auth, can_write=can_write, day=day, DATA=DATA)


import bank_matching
bank_matching.register(app, auth)
import income_documents
income_documents.register(app, auth)

import planning
planning.register(app, db=db, rows=rows, one=one, fail=fail, audit=audit, body=tracking_body, category_names=category_names, money=money, day=day, textval=textval, vehicle=tracking_vehicle, expense=expense)

import home_office
home_office.register(app, auth)
import tax_documents
tax_documents.register(app, auth)

if __name__=='__main__': app.run(host='0.0.0.0',port=8788)

import ai_providers
ai_providers.register(app, auth)
import public_release
public_release.register(app, auth)
import auto_backup
auto_backup.register(app, auth)
import source_access
source_access.register(app, VERSION)
workspace_time.register(app, auth)

import notifications
notifications.register(app, auth)

import signin_alerts
signin_alerts.register(app, auth)

import expense_workflows
expense_workflows.register(app, auth)

import reconciliation
reconciliation.register(app, auth)
import income_checks
income_checks.register(app, auth)

import equipment
equipment.register(app, auth)

import journey_review
journey_review.register(app, auth)
import review_hub
review_hub.register(app, auth)
import document_evidence
document_evidence.register(app, auth)

import mail_intake
mail_intake.register(app, auth)
import offsite_backup
offsite_backup.register(app, auth)

import annual_handover
annual_handover.register(app, auth)
