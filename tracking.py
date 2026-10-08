"""Custom categories, vehicle records and reviewable receipt drafts."""
import csv
import io
import json
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from flask import Blueprint, g, request, jsonify, send_file

bp = Blueprint('tracking', __name__, url_prefix='/api')
MEALS = ('Breakfast', 'Lunch', 'Dinner', 'Incidentals')

def access(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not g.user: fail('Please sign in.', 401)
        if request.method not in ('GET', 'HEAD') and not can_write(): fail('Read-only access.', 403)
        return fn(*args, **kwargs)
    return wrapped

def body():
    d = request.get_json()
    if not isinstance(d, dict): fail('Expected a JSON object.')
    return d

def norm(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value).casefold()).strip()

def category_names():
    return BASE_CATEGORIES + [r['name'] for r in rows('SELECT name FROM custom_categories ORDER BY name COLLATE NOCASE')]

@bp.route('/categories', methods=['GET', 'POST'])
@access
def categories_api():
    if request.method == 'POST':
        if g.user['role'] == 'employee': fail('Only the owner or a write-enabled tax agent can create categories.', 403)
        name = str(body().get('name') or '').strip()
        if not name or len(name) > 80 or any(ord(c) < 32 for c in name): fail('Enter a category name of 1–80 characters.')
        db().execute('BEGIN IMMEDIATE')
        if name.casefold() in {c.casefold() for c in category_names()}: fail('That category already exists.', 409)
        db().execute('INSERT INTO custom_categories(name) VALUES (?)', (name,))
        audit('expense category created', name); db().commit()
    return jsonify(category_names())

def profile(uid):
    row = one('SELECT data FROM receipt_preferences WHERE user_id=?', (uid,))
    person = one('SELECT role FROM users WHERE id=?', (uid,))
    defaults=dict(home_base='', home_aliases='', scope='business' if person and person['role']=='employee' else 'work')
    return {**defaults, **(json.loads(row['data']) if row else {})}


@bp.route('/receipt-preferences', methods=['GET', 'PUT'])
@access
def preferences_api():
    uid = record_user_id()
    if request.method == 'PUT':
        if g.user['role'] == 'tax_agent': fail('The account holder sets their home base.', 403)
        d = body(); scope = d.get('scope', 'work')
        if scope not in ('work', 'business') or g.user['role']=='employee' and scope!='business': fail('Choose a valid default workspace.')
        values = dict(home_base=textval(d.get('home_base'), 100), home_aliases=textval(d.get('home_aliases'), 1000), scope=scope)
        db().execute('INSERT INTO receipt_preferences(user_id,data) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data', (uid, json.dumps(values)))
        audit('receipt preferences updated', uid); db().commit()
    return jsonify(profile(uid))

def draft_for(rid):
    row = one('SELECT data FROM receipt_drafts WHERE receipt_id=?', (rid,))
    return json.loads(row['data']) if row else {}

def receipt_values(rid):
    row = one('SELECT extraction FROM receipt_details WHERE receipt_id=?', (rid,))
    extracted = json.loads(row['extraction'] or '{}') if row else {}
    if not extracted.get('currency') and extracted.get('currency_status') != 'unknown':
        extracted.update(currency='AUD', currency_status='default', currency_evidence='AUD default; no other currency specified.')
    return {**extracted, **draft_for(rid)}

def clean_draft(d):
    allowed = {'merchant','date','amount','currency','scope','category','percent','notes','meal','merchant_city','merchant_address','trip_id','vehicle_id','exclude_trip'}
    if set(d)-allowed: fail('Unknown receipt draft field.')
    result = {}
    for key, value in d.items():
        if key=='date': result[key] = day(value) if value else ''
        elif key=='amount': result[key] = money(value)/100 if value not in ('',None) else None
        elif key=='percent':
            try: n = Decimal(str(value))
            except InvalidOperation: fail('Enter a valid use percentage.')
            if not n.is_finite() or n!=int(n) or not 0<=n<=100: fail('Use percentage must be a whole number from 0–100.')
            result[key] = int(n)
        elif key=='currency':
            code = str(value or '').upper().strip()
            if code and not re.fullmatch('[A-Z]{3}', code): fail('Enter a three-letter currency code.')
            result[key] = code
        elif key=='category':
            if value not in category_names(): fail('Invalid expense category.')
            result[key] = value
        elif key=='scope':
            if value not in ('','work','business','personal'): fail('Invalid workspace.')
            result[key] = value
        elif key=='meal':
            if value and value not in MEALS: fail('Invalid meal type.')
            result[key] = value
        elif key in ('trip_id','vehicle_id'):
            try: result[key] = int(value) if value else None
            except (ValueError, TypeError): fail('Invalid linked record.')
        elif key=='exclude_trip': result[key] = value is True
        else: result[key] = textval(value, 3000 if key=='notes' else 500 if key=='merchant_address' else 200)
    return result

@bp.put('/receipts/<rid>/draft')
@access
def save_receipt_draft(rid):
    db().execute('BEGIN IMMEDIATE'); r=receipt(rid)
    if one('SELECT id FROM expenses WHERE receipt_id=?',(rid,)): fail('This receipt is already filed.',409)
    values={**draft_for(rid),**clean_draft(body())}
    if one('SELECT role FROM users WHERE id=?',(r['user_id'],))['role']=='employee' and values.get('scope') not in ('',None,'business'): fail('Employee receipts must remain business expenses.')
    if values.get('vehicle_id'): vehicle(values['vehicle_id'],r['user_id'])
    db().execute('INSERT INTO receipt_drafts(receipt_id,data) VALUES (?,?) ON CONFLICT(receipt_id) DO UPDATE SET data=excluded.data,saved_at=CURRENT_TIMESTAMP',(rid,json.dumps(values)))
    audit('receipt draft saved',rid); db().commit(); return jsonify(draft=values)

def proposals():
    where, args = ('r.user_id=?',[g.user['id']]) if g.user['role']=='employee' else ('1=1',[])
    receipts = rows(f'SELECT r.*,u.name AS owner FROM receipts r JOIN users u ON u.id=r.user_id WHERE {where} AND NOT EXISTS (SELECT 1 FROM expenses e WHERE e.receipt_id=r.id)',args)
    groups=[]
    for r in receipts:
        d=receipt_values(r['id']); prefs=profile(r['user_id']); city=d.get('merchant_city','')
        homes={norm(x) for x in [prefs['home_base'],*prefs['home_aliases'].split(',')] if norm(x)}
        if not prefs['home_base'] or not city or norm(city) in homes or not d.get('date') or d.get('category')!='Meals' or d.get('exclude_trip') or d.get('scope')=='personal': continue
        scope=d.get('scope') or prefs['scope']; when=d['date']
        existing=next((t for t in rows('SELECT * FROM trips WHERE user_id=? AND scope=? AND start<=? AND end>=? ORDER BY start DESC',(r['user_id'],scope,when,when)) if norm(t['location'])==norm(city)),None)
        entry=dict(id=r['id'],filename=r['filename'],values=d,aud_amount=draft_for(r['id']).get('amount',d.get('amount') if d.get('currency')=='AUD' else None))
        groups.append(dict(user_id=r['user_id'],owner=r['owner'],location=city,scope=scope,first=when,last=when,existing_trip_id=existing['id'] if existing else None,receipts=[entry],home_base=prefs['home_base'],existing=existing))
    # Chronological grouping is independent of upload order and never crosses people/workspaces.
    groups.sort(key=lambda x:(x['user_id'],x['scope'],norm(x['location']),x['existing_trip_id'] or 0,x['first']))
    merged=[]
    for item in groups:
        last=merged[-1] if merged else None
        if last and (last['user_id'],last['scope'],norm(last['location']),last['existing_trip_id'])==(item['user_id'],item['scope'],norm(item['location']),item['existing_trip_id']) and (item['existing_trip_id'] or date.fromisoformat(item['first'])<=date.fromisoformat(last['last'])+timedelta(days=1)):
            last['last']=max(last['last'],item['last']);last['receipts']+=item['receipts']
        else: merged.append(item)
    for group in merged:
        existing=group.pop('existing')
        group['start']=existing['start'] if existing else group['first']
        group['end']=existing['end'] if existing else max(group['last'],(date.fromisoformat(group['first'])+timedelta(days=1)).isoformat())
        group['purpose']=existing['purpose'] if existing else ''
    return merged

@bp.get('/receipt-trip-proposals')
@access
def proposal_api(): return jsonify(proposals())

@bp.post('/receipt-trip-proposals/accept')
@access
def accept_proposal():
    d=body(); entries=d.get('receipts')
    if not isinstance(entries,list) or not 1<=len(entries)<=100 or any(not isinstance(x,dict) for x in entries): fail('Choose 1–100 receipt drafts.')
    ids=[str(x.get('id','')) for x in entries]
    if len(set(ids))!=len(ids): fail('A receipt can only appear once.')
    db().execute('BEGIN IMMEDIATE')
    originals=[receipt(rid) for rid in ids]; uid=originals[0]['user_id']
    if any(r['user_id']!=uid for r in originals): fail('A trip can only contain receipts for one person.')
    if any(one('SELECT id FROM expenses WHERE receipt_id=?',(rid,)) for rid in ids): fail('A receipt was already filed. Reload the draft trips.',409)
    start,end=day(d.get('start')),day(d.get('end'));location=textval(d.get('location'),100);purpose=textval(d.get('purpose'),500);scope=d.get('scope')
    if end<=start or not location or not purpose: fail('Confirm an overnight date range, location and purpose.')
    if scope not in ('work','business') or one('SELECT role FROM users WHERE id=?',(uid,))['role']=='employee' and scope!='business': fail('Invalid trip workspace.')
    tid=d.get('existing_trip_id')
    if tid:
        t=one('SELECT * FROM trips WHERE id=?',(tid,))
        if not t or t['user_id']!=uid or t['scope']!=scope: fail('Choose an existing trip for the same person and workspace.')
        start,end=t['start'],t['end']
    else:
        t=next((t for t in rows('SELECT * FROM trips WHERE user_id=? AND scope=? AND start<=? AND end>=?',(uid,scope,start,end)) if norm(t['location'])==norm(location)),None)
        tid=t['id'] if t else db().execute('INSERT INTO trips(user_id,scope,location,start,end,purpose) VALUES (?,?,?,?,?,?)',(uid,scope,location,start,end,purpose)).lastrowid
    saved=[]
    for entry in entries:
        if entry.get('amount') in ('',None): fail('Confirm the actual AUD amount paid for every receipt.')
        # These are user-reviewed AUD amounts, never an automatic currency conversion.
        values={**receipt_values(entry['id']),**entry,'scope':scope,'category':'Meals','trip_id':tid,'receipt_id':entry['id'],'status':'ready'}
        if not values.get('meal'): fail('Confirm a meal type for each receipt.')
        if values.get('percent') in ('',None): values['percent']=100
        p=payload(values,{'user_id':uid,'account_id':None})
        eid=db().execute('INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,reimbursed,notes,trip_id,meal,receipt_id,account_id,status,shared) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(uid,)+p).lastrowid
        saved.append(eid);audit('receipt trip meal accepted',eid)
    audit('receipt trip accepted',tid);db().commit();return jsonify(trip_id=tid,expense_ids=saved)

def vehicle(vid, uid=None):
    v=one('SELECT * FROM vehicles WHERE id=?',(vid,))
    if not v or uid is not None and v['user_id']!=uid or g.user['role']=='employee' and v['user_id']!=g.user['id']: fail('Vehicle not found for this person.',404)
    return v

def link_vehicle(eid,uid,d,existing=None):
    vid=d.get('vehicle_id',existing.get('vehicle_id') if existing else None) or None
    if vid:
        vehicle(vid,uid)
        if one('SELECT role FROM users WHERE id=?',(uid,))['role']=='employee' and one('SELECT scope FROM expenses WHERE id=?',(eid,))['scope']!='business': fail('Employee vehicle expenses must remain in Business.')
    db().execute('UPDATE expenses SET vehicle_id=? WHERE id=?',(vid,eid))

@bp.route('/vehicles',methods=['GET','POST'])
@access
def vehicles_api():
    if request.method=='GET':
        where,args=('v.user_id=?',[g.user['id']]) if g.user['role']=='employee' else ('1=1',[])
        return jsonify(rows(f'SELECT v.*,u.name AS owner,u.role AS owner_role FROM vehicles v JOIN users u ON u.id=v.user_id WHERE {where} ORDER BY v.name',args))
    d=body();name=textval(d.get('name'),100)
    if not name: fail('Enter a vehicle name.')
    vid=db().execute('INSERT INTO vehicles(user_id,name,registration,notes) VALUES (?,?,?,?)',(record_user_id(),name,textval(d.get('registration'),30),textval(d.get('notes'),1000))).lastrowid
    audit('vehicle created',vid);db().commit();return jsonify(id=vid)

@bp.route('/vehicles/<int:vid>',methods=['PUT','DELETE'])
@access
def vehicle_api(vid):
    vehicle(vid)
    if request.method=='DELETE':
        if one('SELECT id FROM expenses WHERE vehicle_id=?',(vid,)) or one('SELECT id FROM vehicle_journeys WHERE vehicle_id=?',(vid,)): fail('Remove or unlink this vehicle’s records before deleting it.',409)
        db().execute('DELETE FROM vehicles WHERE id=?',(vid,))
    else:
        d=body();name=textval(d.get('name'),100)
        if not name: fail('Enter a vehicle name.')
        db().execute('UPDATE vehicles SET name=?,registration=?,notes=? WHERE id=?',(name,textval(d.get('registration'),30),textval(d.get('notes'),1000),vid))
    audit('vehicle updated',vid);db().commit();return jsonify(ok=True)

def meters(value):
    try:
        n=Decimal(str(value))
        if not n.is_finite() or not 0<=n<=10000000: raise ValueError()
        return int((n*1000).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    except (ValueError,InvalidOperation,TypeError): fail('Enter a valid kilometre reading.')

def journey_values(d):
    v=vehicle(d.get('vehicle_id'));scope=d.get('scope','business');purpose=textval(d.get('purpose'),1000)
    if scope not in ('work','business','personal') or one('SELECT role FROM users WHERE id=?',(v['user_id'],))['role']=='employee' and scope!='business': fail('Invalid journey workspace.')
    if not purpose: fail('Enter the journey purpose.')
    a,b=d.get('odometer_start'),d.get('odometer_end')
    if (a in ('',None))!=(b in ('',None)): fail('Enter both odometer readings, or a distance instead.')
    a,b=(None,None) if a in ('',None) else (meters(a),meters(b))
    distance=meters(d.get('distance')) if a is None else b-a
    if not 0<distance<=100000000: fail('Journey distance must be greater than zero and at most 100,000 km.')
    percent=clean_draft({'percent':d.get('percent',100)})['percent'] if scope!='personal' else 0
    return (v['id'],day(d.get('date')),textval(d.get('origin'),200),textval(d.get('destination'),200),purpose,scope,a,b,distance,percent)

@bp.route('/vehicle-journeys',methods=['GET','POST'])
@access
def journeys_api():
    if request.method=='POST':
        values=journey_values(body());jid=db().execute('INSERT INTO vehicle_journeys(vehicle_id,date,origin,destination,purpose,scope,odometer_start,odometer_end,distance_m,percent) VALUES (?,?,?,?,?,?,?,?,?,?)',values).lastrowid
        audit('vehicle journey created',jid);db().commit();return jsonify(id=jid)
    where,args=('v.user_id=?',[g.user['id']]) if g.user['role']=='employee' else ('1=1',[])
    data=rows(f'SELECT j.*,v.name AS vehicle,v.registration,v.user_id,u.name AS owner FROM vehicle_journeys j JOIN vehicles v ON v.id=j.vehicle_id JOIN users u ON u.id=v.user_id WHERE {where} ORDER BY j.date DESC,j.id DESC',args)
    if request.args.get('format')=='csv':
        out=io.StringIO();writer=csv.writer(out);writer.writerow(['Date','Vehicle','Registration','Person','From','To','Purpose','Workspace','Odometer start km','Odometer end km','Distance km','Use %','Allocated km'])
        def safe(s): return "'"+s if str(s).lstrip().startswith(('=','+','-','@')) else s
        for x in data: writer.writerow([date.fromisoformat(x['date']).strftime('%d/%m/%Y'),*[safe(x[k]) for k in ('vehicle','registration','owner','origin','destination','purpose')],x['scope'],'' if x['odometer_start'] is None else x['odometer_start']/1000,'' if x['odometer_end'] is None else x['odometer_end']/1000,x['distance_m']/1000,x['percent'],x['distance_m']*x['percent']/100000])
        return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')),mimetype='text/csv',as_attachment=True,download_name='expense-pilot-vehicle-journeys.csv')
    return jsonify(data)

@bp.route('/vehicle-journeys/<int:jid>',methods=['PUT','DELETE'])
@access
def journey_api(jid):
    j=one('SELECT * FROM vehicle_journeys WHERE id=?',(jid,))
    if not j: fail('Journey not found.',404)
    old=vehicle(j['vehicle_id'])
    if request.method=='DELETE': db().execute('DELETE FROM vehicle_journeys WHERE id=?',(jid,))
    else:
        d=body();values=journey_values(d)
        vehicle(values[0],old['user_id'])
        db().execute('UPDATE vehicle_journeys SET vehicle_id=?,date=?,origin=?,destination=?,purpose=?,scope=?,odometer_start=?,odometer_end=?,distance_m=?,percent=? WHERE id=?',values+(jid,))
    audit('vehicle journey updated',jid);db().commit();return jsonify(ok=True)

def register(app, **deps):
    globals().update(deps)
    with app.app_context():
        db().executescript('''
        CREATE TABLE IF NOT EXISTS custom_categories(name TEXT PRIMARY KEY COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS receipt_preferences(user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS receipt_drafts(receipt_id TEXT PRIMARY KEY REFERENCES receipts(id) ON DELETE CASCADE,data TEXT NOT NULL,saved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),name TEXT NOT NULL,registration TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS vehicle_journeys(id INTEGER PRIMARY KEY,vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),date TEXT NOT NULL,origin TEXT NOT NULL,destination TEXT NOT NULL,purpose TEXT NOT NULL,scope TEXT NOT NULL,odometer_start INTEGER,odometer_end INTEGER,distance_m INTEGER NOT NULL,percent INTEGER NOT NULL DEFAULT 100);
        ''')
        if 'vehicle_id' not in {r['name'] for r in db().execute('PRAGMA table_info(expenses)')}:
            db().execute('ALTER TABLE expenses ADD COLUMN vehicle_id INTEGER REFERENCES vehicles(id)')
        db().commit()
    app.register_blueprint(bp)
