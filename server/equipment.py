"""Equipment costs and explicit annual depreciation; no inferred tax rates."""
from flask import jsonify, request
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
    return assets


def deductions(year):
    from app import rows
    records=rows('SELECT a.*,d.amount_cents FROM equipment_assets a JOIN equipment_depreciation d ON d.asset_id=a.id WHERE d.year=? AND d.confirmed=1',(year,))
    parts=[allocations(r) for r in records]
    return sum(p[0] for p in parts),sum(p[1] for p in parts)


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
        if request.method=='DELETE': db().execute('DELETE FROM equipment_depreciation WHERE asset_id=? AND year=?',(aid,year))
        else:
            amount=money(d.get('amount'));basis=textval(d.get('notes'),2000)
            others=one('SELECT COALESCE(SUM(amount_cents),0) AS total FROM equipment_depreciation WHERE asset_id=? AND year!=?',(aid,year))['total']
            if a['acquired']>end or a['disposal_date'] and a['disposal_date']<start: fail('Choose a year when the equipment was held.')
            if amount<0 or amount+others>a['cost_cents'] or not basis: fail('Enter the depreciation basis and an amount within the remaining original cost.')
            if not isinstance(d.get('confirmed'),bool): fail('Choose whether this annual amount is confirmed.')
            db().execute('INSERT INTO equipment_depreciation VALUES (?,?,?,?,?) ON CONFLICT(asset_id,year) DO UPDATE SET amount_cents=excluded.amount_cents,notes=excluded.notes,confirmed=excluded.confirmed',
                         (aid,year,amount,basis,int(d['confirmed'])))
        db().execute('UPDATE equipment_assets SET version=version+1 WHERE id=?',(aid,));audit('equipment annual depreciation updated',aid);db().commit();return jsonify(ok=True)
