"""Daily drive review, reversible classification, and conservative merge/split."""
import json
from flask import jsonify, request
from workflow_core import body, selected_ids, integer, preview, checked, record_change, write_access


def get_records(ids):
    from app import rows, fail, record_user_id
    records=rows('SELECT j.* FROM vehicle_journeys j JOIN vehicles v ON v.id=j.vehicle_id WHERE v.user_id=? AND j.id IN ('+','.join('?' for _ in ids)+') ORDER BY j.date,j.started_at,j.id',[record_user_id()]+ids)
    if len(records)!=len(ids): fail('Some drives were removed or do not belong to this workspace.',409)
    return records


def plan(data):
    from app import fail, textval
    from expense_core import percent
    from tracking import meters
    ids=selected_ids(data.get('ids'),200);records=get_records(ids);action=data.get('action')
    after=[]
    if action=='classify':
        scope=data.get('scope');purpose=textval(data.get('purpose'),1000)
        if scope not in ('work','business','personal') or scope!='personal' and not purpose: fail('Choose a workspace and enter the work/business purpose.')
        try: use=percent(data.get('percent',100)) if scope!='personal' else 0
        except ValueError as exc: fail(str(exc))
        after=[dict(r,scope=scope,purpose=purpose,percent=use,review_confirmed=1) for r in records]
    elif action=='merge':
        if len(records)<2: fail('Select at least two drives to merge.')
        first,last=records[0],records[-1]
        if any(any(r[k]!=first[k] for k in ('vehicle_id','date','date_timezone','scope','percent','purpose')) for r in records): fail('Merged drives must have the same vehicle, day, timezone, classification and purpose.')
        for previous,current in zip(records,records[1:]):
            if previous['ended_at'] and current['started_at'] and previous['ended_at']>current['started_at']: fail('Overlapping drives cannot be merged.')
        merged=dict(first,id=None,client_ref=None,destination=last['destination'],ended_at=last['ended_at'],distance_m=sum(r['distance_m'] for r in records),odometer_start=None,odometer_end=None)
        if all(r['odometer_start'] is not None for r in records) and all(a['odometer_end']==b['odometer_start'] for a,b in zip(records,records[1:])):
            merged.update(odometer_start=first['odometer_start'],odometer_end=last['odometer_end'])
        routes=[json.loads(r['route_json']) for r in records if r['route_json']]
        if routes:
            route=dict(version=1,recorded=[seg for r in routes for seg in r['recorded']],planned=[seg for r in routes for seg in r['planned']],interrupted=True)
            if routes[0].get('start'): route['start']=routes[0]['start']
            if routes[-1].get('finish'): route['finish']=routes[-1]['finish']
            from journey_routes import archive
            merged['route_json']=archive(route)
        after=[merged]
    elif action=='split':
        if len(records)!=1: fail('Select one drive to split.')
        original=records[0];distance=meters(data.get('first_distance'));place=textval(data.get('split_place'),200)
        if not 0<distance<original['distance_m'] or not place: fail('Enter the split location and a distance smaller than the original drive.')
        parts=[dict(original,id=None,client_ref=None,destination=place,distance_m=distance,ended_at=None),
               dict(original,id=None,client_ref=None,origin=place,distance_m=original['distance_m']-distance,started_at=None)]
        if original['started_at'] is not None and original['ended_at'] is not None:
            cut=integer(data.get('split_at'),'split time',int(original['started_at'])+1,int(original['ended_at'])-1)
            parts[0]['ended_at']=parts[1]['started_at']=cut
        if original['odometer_start'] is not None:
            parts[0]['odometer_end']=parts[1]['odometer_start']=original['odometer_start']+distance
        if original['route_json']:
            route=json.loads(original['route_json'])
            if route['planned']: fail('This drive contains estimated route sections. Split its route in the recording app, or keep it whole; estimated sections cannot be assigned to a timestamp reliably.')
            total=sum(len(s) for s in route['recorded']);index=integer(data.get('point_index'),'route split point',1,total-2)
            left=[];right=[];offset=0
            for segment in route['recorded']:
                if offset+len(segment)<=index: left.append(segment)
                elif offset>index: right.append(segment)
                else:
                    boundary=index-offset;left.append(segment[:boundary+1]);right.append(segment[boundary:])
                offset+=len(segment)
            from journey_routes import archive
            for part,segments in zip(parts,(left,right)):
                part['route_json']=archive(dict(version=1,recorded=segments,planned=[],interrupted=route['interrupted'],start=segments[0][0],finish=segments[-1][-1]))
        after=parts
    else: fail('Choose classification, merge or split.')
    if any(r['distance_m']>100000000 for r in after): fail('The merged distance exceeds the journey limit.')
    return dict(action=action,before=records,after=after)


def archive_upload(r):
    from app import db
    import journey_routes
    if r['client_ref']:
        values=tuple(r[k] for k in ('vehicle_id','date','origin','destination','purpose','scope','odometer_start','odometer_end','distance_m','percent'))
        meta=tuple(r[k] for k in ('started_at','ended_at','client_ref'))
        db().execute('INSERT OR IGNORE INTO journey_upload_receipts VALUES (?,?,?)',(r['client_ref'],r['id'],journey_routes.fingerprint(values,meta,r['route_json'])))


def register(app,auth):
    @app.get('/api/workflows/journeys', endpoint='journey_review_timeline')
    @auth('owner','tax_agent')
    def timeline():
        from app import rows, day, record_user_id
        when=day(request.args.get('date'))
        records=rows('SELECT j.*,v.name AS vehicle FROM vehicle_journeys j JOIN vehicles v ON v.id=j.vehicle_id WHERE v.user_id=? AND j.date=? ORDER BY j.started_at,j.id',(record_user_id(),when))
        for r in records:
            route=json.loads(r.pop('route_json') or 'null')
            r['route_summary']=dict(recorded_points=sum(len(s) for s in route['recorded']),recorded_sections=len(route['recorded']),estimated_sections=len(route['planned']),interrupted=route['interrupted']) if route else None
        return jsonify(date=when,journeys=records,history=rows("SELECT id,kind,at,undone FROM workflow_changes WHERE user_id=? AND kind LIKE 'journey %' ORDER BY id DESC LIMIT 30",(record_user_id(),)))

    @app.post('/api/workflows/journeys/<action>', endpoint='journey_review_apply')
    @auth('owner','tax_agent')
    def apply(action):
        from app import db, one, fail
        write_access();d=body()
        if action not in ('preview','apply'): fail('Unknown drive review action.',404)
        if action=='apply': db().execute('BEGIN IMMEDIATE')
        result=plan(d)
        if action=='preview': return jsonify(**result,token=preview('journeys',result))
        checked(d.get('token'),'journeys',result)
        if result['action']=='classify':
            for r in result['after']: db().execute('UPDATE vehicle_journeys SET scope=?,percent=?,purpose=?,review_confirmed=1 WHERE id=?',(r['scope'],r['percent'],r['purpose'],r['id']))
        else:
            for r in result['before']:
                archive_upload(r);db().execute('DELETE FROM vehicle_journeys WHERE id=?',(r['id'],))
            # Reserve IDs above both the live ledger and deleted IDs: never reuse a
            # phone's acknowledged ID for a different drive.
            max_id=max([r['id'] for r in result['before']]+[one('SELECT COALESCE(MAX(id),0) n FROM vehicle_journeys')['n'],one('SELECT COALESCE(MAX(journey_id),0) n FROM journey_upload_receipts')['n']])
            for index,r in enumerate(result['after'],1):
                r['id']=max_id+index
                keys=list(r);db().execute('INSERT INTO vehicle_journeys('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',tuple(r[k] for k in keys))
        ident=record_change('journey '+result['action'],result['before'],result['after']);db().commit();return jsonify(ok=True,change_id=ident)

    @app.post('/api/workflows/journeys/undo/<int:cid>', endpoint='journey_review_undo')
    @auth('owner','tax_agent')
    def undo(cid):
        from app import db, one, fail, record_user_id, audit
        write_access();db().execute('BEGIN IMMEDIATE')
        change=one("SELECT * FROM workflow_changes WHERE id=? AND user_id=? AND kind LIKE 'journey %' AND undone=0",(cid,record_user_id()))
        if not change: fail('Drive change not found.',404)
        after=json.loads(change['after_json']);before=json.loads(change['before_json'])
        for r in after:
            if one('SELECT * FROM vehicle_journeys WHERE id=?',(r['id'],))!=r: fail('A resulting drive changed. Undo would overwrite those changes.',409)
        for r in before:
            if r['id'] not in [v['id'] for v in after] and one('SELECT 1 FROM vehicle_journeys WHERE id=?',(r['id'],)): fail('A previous drive ID is occupied.',409)
        for r in after: db().execute('DELETE FROM vehicle_journeys WHERE id=?',(r['id'],))
        for r in before:
            keys=list(r);db().execute('INSERT INTO vehicle_journeys('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',tuple(r[k] for k in keys))
        db().execute('UPDATE workflow_changes SET undone=1 WHERE id=?',(cid,));audit('journey change undone',cid);db().commit();return jsonify(ok=True)
