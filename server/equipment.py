"""Equipment costs and explicit annual depreciation; no inferred tax rates."""
import json
from flask import jsonify, request
import equipment_calculations as calc
from expense_core import allocations, split_values
from workflow_core import body, fiscal, integer, write_access


def listing(year):
    from app import rows, record_user_id
    year,_,end=fiscal(year)
    assets=rows('SELECT a.*,e.receipt_id FROM equipment_assets a LEFT JOIN expenses e ON e.id=a.expense_id WHERE a.user_id=? ORDER BY acquired,id',(record_user_id(),))
    for a in assets:
        history=rows('SELECT * FROM equipment_depreciation WHERE asset_id=? ORDER BY year',(a['id'],))
        opening=a['cost_cents']-sum(h['amount_cents'] for h in history if h['year']<year)
        current=next((h for h in history if h['year']==year),None)
        a.update(history=history,opening_cents=opening,closing_cents=opening-(current['amount_cents'] if current else 0),current=current,
                 needs_review=a['acquired']<=end and (not a['disposal_date'] or a['disposal_date']>=f'{year}-07-01') and opening>0 and (not current or not current['confirmed']))
        usage=rows('SELECT * FROM equipment_usage WHERE asset_id=? ORDER BY year',(a['id'],))
        a['calculation']=json.loads(a['calculation_json']);a['usage']=usage
        a['schedule']=calc.schedule(a,history,usage,min(2098,max(year+5,calc.fy(a['acquired'])+5)))
        estimated=next((r for r in a['schedule'] if r['year']==year),None)
        if estimated:
            a.update(opening_cents=estimated['opening_cents'],closing_cents=estimated['closing_cents'],current=estimated,
                     needs_review=estimated['needs_review'] or bool(current and not current['confirmed']))
    return assets


def deductions(year):
    return deduction_details(year)['totals']


def deduction_details(year):
    from app import rows
    parts=[];estimates=[]
    for a in listing(year):
        current=a['current']
        if not current: continue
        if a['calculation']:
            if not current.get('include_forecast') or current['needs_review'] and not current['confirmed']: continue
            record={**a,**current,'amount_cents':current['claimable_cents']}
        else:
            if not current['confirmed']: continue
            record={**a,**current,'amount_cents':current['claimable_cents'] if current.get('claimable_cents') is not None else current['amount_cents'],'work_percent':current.get('work_percent') if current.get('work_percent') is not None else a['work_percent'],
                    'business_percent':current.get('business_percent') if current.get('business_percent') is not None else a['business_percent']}
        part=allocations(record);parts.append(part)
        if a['calculation'] and not current['confirmed']: estimates.append(part)
    return dict(totals=(sum(p[0] for p in parts),sum(p[1] for p in parts)),
                estimated_work_cents=sum(p[0] for p in estimates),estimated_business_cents=sum(p[1] for p in estimates))


def register(app,auth):
    @app.route('/api/workflows/equipment',methods=['GET','POST'], endpoint='equipment_assets')
    @auth('owner','tax_agent')
    def assets():
        from app import db, one, fail, money, day, textval, record_user_id, audit
        if request.method=='GET':
            year=integer(request.args.get('year'),'financial year',1900,2098)
            return jsonify(assets=listing(year))
        write_access();d=body();name=textval(d.get('name'),200);acquired=day(d.get('acquired'));cost=money(d.get('cost'))
        try: work,business=split_values(d)
        except ValueError as exc: fail(str(exc))
        if not name or cost<=0: fail('Enter a name, acquisition date and positive original cost.')
        if d.get('confirm_capital') is not True: fail('Confirm the linked purchase will be excluded from ordinary tax deductions.')
        eid=d.get('expense_id') or None;db().execute('BEGIN IMMEDIATE')
        if eid:
            e=one('SELECT * FROM expenses WHERE id=? AND user_id=?',(integer(eid,'expense ID',1),record_user_id()))
            if not e or e['amount_cents']!=cost or e['date']!=acquired or (e['work_percent'],e['business_percent'])!=(work,business): fail('The linked purchase must have the same cost, date and use percentages.')
            if e['reimbursed'] or e['items_json']!='[]' or e['trip_id'] or e['meal'] or e['vehicle_id'] or one('SELECT 1 FROM home_office_costs WHERE expense_id=?',(eid,)): fail('Choose a standalone equipment purchase without another claim treatment.')
            if one('SELECT 1 FROM equipment_assets WHERE expense_id=?',(eid,)): fail('This purchase is already in the equipment register.',409)
        ident=db().execute('INSERT INTO equipment_assets(user_id,expense_id,name,acquired,cost_cents,work_percent,business_percent,notes) VALUES (?,?,?,?,?,?,?,?)',
                           (record_user_id(),eid,name,acquired,cost,work,business,textval(d.get('notes'),2000))).lastrowid
        if d.get('calculation'):
            a=one('SELECT * FROM equipment_assets WHERE id=?',(ident,))
            config=calc.validate(a,d['calculation'],[])
            db().execute('UPDATE equipment_assets SET calculation_json=? WHERE id=?',(json.dumps(config),ident))
        audit('equipment registered',ident);db().commit();return jsonify(id=ident)

    @app.route('/api/workflows/equipment/<int:aid>',methods=['PUT','DELETE'], endpoint='equipment_change')
    @auth('owner','tax_agent')
    def change(aid):
        from app import db, one, fail, day, money, textval, record_user_id, audit
        write_access();d=body();db().execute('BEGIN IMMEDIATE')
        a=one('SELECT * FROM equipment_assets WHERE id=? AND user_id=?',(aid,record_user_id()))
        if not a: fail('Equipment not found.',404)
        if d.get('version')!=a['version']: fail('Equipment changed. Reload the register.',409)
        if request.method=='DELETE':
            if one('SELECT 1 FROM equipment_depreciation WHERE asset_id=?',(aid,)): fail('Remove the annual depreciation records before removing this asset.',409)
            db().execute('DELETE FROM equipment_assets WHERE id=?',(aid,))
        else:
            disposal=day(d['disposal_date']) if d.get('disposal_date') else '';proceeds=money(d.get('proceeds',0))
            if disposal and disposal<a['acquired'] or proceeds<0 or proceeds and not disposal: fail('Check disposal date and proceeds.')
            last=one('SELECT MAX(year) AS year FROM equipment_depreciation WHERE asset_id=?',(aid,))['year']
            if disposal and last is not None and f'{last}-07-01'>disposal: fail('Remove depreciation records after disposal first.')
            db().execute('UPDATE equipment_assets SET disposal_date=?,proceeds_cents=?,notes=?,version=version+1 WHERE id=?',(disposal,proceeds,textval(d.get('notes'),2000),aid))
        audit('equipment updated',aid);db().commit();return jsonify(ok=True)

    @app.route('/api/workflows/equipment/<int:aid>/year/<int:year>',methods=['PUT','DELETE'], endpoint='equipment_annual')
    @auth('owner','tax_agent')
    def annual(aid,year):
        from app import db, one, fail, money, textval, record_user_id, audit
        write_access();d=body();year,start,end=fiscal(year);db().execute('BEGIN IMMEDIATE')
        a=one('SELECT * FROM equipment_assets WHERE id=? AND user_id=?',(aid,record_user_id()))
        if not a: fail('Equipment not found.',404)
        if d.get('version')!=a['version']: fail('Equipment changed. Reload the register.',409)
        before=one('SELECT * FROM equipment_depreciation WHERE asset_id=? AND year=?',(aid,year))
        if request.method=='DELETE':
            if json.loads(a['calculation_json']):
                view=next(x for x in listing(year) if x['id']==aid)
                proposed=[h for h in view['history'] if h['year']!=year]
                future=calc.schedule(a,proposed,view['usage'],max([year]+[h['year'] for h in proposed]))
                if any(h['amount_cents']>h['opening_cents'] for h in future): fail('Removing this override would invalidate a later annual record. Review the later record first.')
            db().execute('DELETE FROM equipment_depreciation WHERE asset_id=? AND year=?',(aid,year))
        else:
            amount=money(d.get('amount'));claimable=money(d.get('income_use_amount',d.get('amount')));basis=textval(d.get('notes'),2000)
            others=one('SELECT COALESCE(SUM(amount_cents),0) AS total FROM equipment_depreciation WHERE asset_id=? AND year!=?',(aid,year))['total']
            if a['acquired']>end or a['disposal_date'] and a['disposal_date']<start: fail('Choose a year when the equipment was held.')
            if amount<0 or claimable<0 or claimable>amount or amount+others>a['cost_cents'] or not basis: fail('Enter the depreciation basis and an amount within the remaining original cost.')
            if json.loads(a['calculation_json']):
                view=next(x for x in listing(year) if x['id']==aid)
                current=view['current']
                if current and current['taxable_days']<current['days'] and 'income_use_amount' not in d: fail('Enter the amount for the income-use period separately from total decline in value.')
                if not current or amount>current['opening_cents']: fail('Annual amount exceeds the remaining calculated value.')
                a['work_percent'],a['business_percent']=current['work_percent'],current['business_percent']
            if not isinstance(d.get('confirmed'),bool): fail('Choose whether this annual amount is confirmed.')
            if json.loads(a['calculation_json']):
                proposed=[h for h in view['history'] if h['year']!=year]+[dict(asset_id=aid,year=year,amount_cents=amount,claimable_cents=claimable,notes=basis,confirmed=int(d['confirmed']),work_percent=a['work_percent'],business_percent=a['business_percent'])]
                future=calc.schedule(a,proposed,view['usage'],max([year]+[h['year'] for h in proposed]))
                if any(h['amount_cents']>h['opening_cents'] for h in future): fail('This override would exceed the remaining value of a later annual record.')
            db().execute('INSERT INTO equipment_depreciation(asset_id,year,amount_cents,notes,confirmed,work_percent,business_percent,claimable_cents) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(asset_id,year) DO UPDATE SET amount_cents=excluded.amount_cents,notes=excluded.notes,confirmed=excluded.confirmed,work_percent=excluded.work_percent,business_percent=excluded.business_percent,claimable_cents=excluded.claimable_cents',
                         (aid,year,amount,basis,int(d['confirmed']),a['work_percent'],a['business_percent'],claimable))
        db().execute('UPDATE equipment_assets SET version=version+1 WHERE id=?',(aid,));audit('equipment annual depreciation updated',json.dumps(dict(asset_id=aid,year=year,before=before,after=d)));db().commit();return jsonify(ok=True)

    @app.put('/api/workflows/equipment/<int:aid>/calculation',endpoint='equipment_calculation')
    @auth('owner','tax_agent')
    def calculation(aid):
        from app import db,one,rows,record_user_id,fail,audit
        write_access();d=body();db().execute('BEGIN IMMEDIATE')
        a=one('SELECT * FROM equipment_assets WHERE id=? AND user_id=?',(aid,record_user_id()))
        if not a: fail('Equipment not found.',404)
        if d.get('version')!=a['version']: fail('Equipment changed. Reload.',409)
        history=rows('SELECT * FROM equipment_depreciation WHERE asset_id=?',(aid,))
        config=calc.validate(a,d.get('calculation'),history)
        proposed=calc.schedule(dict(a,calculation_json=json.dumps(config)),history,[],max((h['year'] for h in history),default=calc.fy(config['first_use'])))
        if any(h['amount_cents']>h['opening_cents'] for h in proposed): fail('Existing annual amounts exceed the calculated remaining value. Review them before enabling automatic calculation.')
        db().execute('UPDATE equipment_assets SET calculation_json=?,version=version+1 WHERE id=?',(json.dumps(config),aid))
        audit('equipment calculation setup',json.dumps(dict(asset_id=aid,before=a['calculation_json'],after=config)));db().commit();return jsonify(ok=True)

    @app.put('/api/workflows/equipment/<int:aid>/use/<int:year>',endpoint='equipment_annual_usage')
    @auth('owner','tax_agent')
    def annual_usage(aid,year):
        from app import db,one,record_user_id,fail,textval,audit
        write_access();d=body();fiscal(year);db().execute('BEGIN IMMEDIATE')
        a=one('SELECT * FROM equipment_assets WHERE id=? AND user_id=?',(aid,record_user_id()))
        if not a: fail('Equipment not found.',404)
        if d.get('version')!=a['version']: fail('Equipment changed. Reload.',409)
        config=json.loads(a['calculation_json'])
        if not config: fail('Set up automatic calculation first.')
        if config['method'].startswith('immediate_'): fail('Changed use after an immediate deduction needs a reviewed annual adjustment.')
        if year<calc.fy(config['first_use']): fail('Choose a year from first use onward.')
        try: work,business=split_values(d)
        except ValueError as exc: fail(str(exc))
        notes=textval(d.get('notes'),2000)
        if not notes: fail('Record the reason for changed usage.')
        before=one('SELECT * FROM equipment_usage WHERE asset_id=? AND year=?',(aid,year))
        db().execute('INSERT INTO equipment_usage VALUES (?,?,?,?,?) ON CONFLICT(asset_id,year) DO UPDATE SET work_percent=excluded.work_percent,business_percent=excluded.business_percent,notes=excluded.notes',(aid,year,work,business,notes))
        db().execute('UPDATE equipment_assets SET version=version+1 WHERE id=?',(aid,))
        audit('equipment use changed',json.dumps(dict(asset_id=aid,year=year,before=before,after=d)));db().commit();return jsonify(ok=True)
