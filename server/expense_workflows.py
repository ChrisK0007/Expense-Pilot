"""Itemised receipts and explicitly applied, reversible categorisation rules."""
import json
from flask import jsonify, request
from expense_core import split_values, allocations
from workflow_core import body, integer, preview, checked, record_change, selected_ids, write_access


def components(expense):
    lines=json.loads(expense.get('items_json') or '[]')
    return [{**expense, **line, 'items_json':'[]'} for line in lines] if lines else [expense]


def validate_items(value, expense):
    from app import fail, category_names, money, one, textval
    if not isinstance(value,list) or len(value)>100: fail('Use at most 100 receipt items.')
    if not value: return []
    if expense['trip_id'] or expense['meal'] or expense['vehicle_id'] or expense['category']=='Meals' or one('SELECT 1 FROM home_office_costs WHERE expense_id=?',(expense['id'],)) or one('SELECT 1 FROM equipment_assets WHERE expense_id=?',(expense['id'],)):
        fail('This expense has a trip, vehicle, home-office or equipment treatment. Remove that treatment before itemising it.')
    lines=[]
    for row in value:
        if not isinstance(row,dict): fail('Invalid receipt item.')
        try: work,business=split_values(row)
        except ValueError as exc: fail(str(exc))
        category=row.get('category');description=textval(row.get('description'),300)
        if not description or category not in category_names() or category=='Meals': fail('Give each item a description and ordinary expense category.')
        amount=money(row.get('amount'))
        if amount==0: fail('Receipt items must have a non-zero amount.')
        lines.append(dict(description=description,category=category,amount_cents=amount,work_percent=work,business_percent=business,percent=work+business,
                          scope='split' if work and business else 'work' if work else 'business' if business else 'personal'))
    if sum(r['amount_cents'] for r in lines)!=expense['amount_cents']: fail('Item amounts must add up exactly to the payment total.')
    return lines


def guard_edit(existing, values, data=None):
    from app import fail, one
    if one('SELECT 1 FROM bank_reconciliations WHERE expense_id=? OR refund_id=?',(existing['id'],existing['id'])):
        if any(existing[k]!=values[i] for k,i in [('amount_cents',2),('account_id',11)]): fail('Undo the bank reconciliation before changing the matched amount or account.',409)
    if (existing.get('items_json','[]')!='[]' or one('SELECT 1 FROM equipment_assets WHERE expense_id=?',(existing['id'],))) and (data or {}).get('vehicle_id'):
        fail('Remove itemisation or equipment treatment before linking a vehicle.',409)
    if existing.get('items_json','[]')!='[]':
        for key,index in [('amount_cents',2),('scope',3),('category',4),('percent',5),('trip_id',8),('meal',9),('work_percent',14),('business_percent',15)]:
            if existing[key]!=values[index]: fail('Edit the item breakdown first, or clear it before changing the payment amount or allocation.',409)
    if one('SELECT 1 FROM equipment_assets WHERE expense_id=?',(existing['id'],)):
        if any(existing[k]!=values[i] for k,i in [('date',0),('amount_cents',2),('reimbursed',6),('trip_id',8),('meal',9),('work_percent',14),('business_percent',15)]):
            fail('This purchase is in the equipment register. Remove its register entry before changing its cost, date or use.',409)


def rules_data():
    from app import rows, record_user_id
    rules=rows('SELECT * FROM categorisation_rules WHERE user_id=? ORDER BY merchant,id',(record_user_id(),))
    suggestions=rows("SELECT ep_casefold(merchant) AS merchant,category,work_percent,business_percent,COUNT(*) AS count FROM expenses WHERE user_id=? AND status='ready' AND items_json='[]' AND trip_id IS NULL AND meal='' AND category NOT IN ('Meals','Uncategorised') GROUP BY ep_casefold(merchant),category,work_percent,business_percent HAVING COUNT(*)>=2 ORDER BY count DESC LIMIT 30",(record_user_id(),))
    known={r['merchant'].casefold() for r in rules}
    return dict(rules=rules,suggestions=[r for r in suggestions if r['merchant'].casefold() not in known],
                history=rows("SELECT id,kind,at,undone FROM workflow_changes WHERE user_id=? AND kind='categorisation rule applied' ORDER BY id DESC LIMIT 30",(record_user_id(),)))


def rule_plan(rid, ids):
    from app import one, rows, fail, record_user_id
    rule=one('SELECT * FROM categorisation_rules WHERE id=? AND user_id=?',(rid,record_user_id()))
    if not rule or not rule['enabled']: fail('Choose an enabled rule.',404)
    from app import category_names
    if rule['category'] not in category_names(): fail('The rule category no longer exists. Edit the rule first.',409)
    candidates=rows("SELECT * FROM expenses WHERE user_id=? AND ep_casefold(merchant)=? AND items_json='[]' AND trip_id IS NULL AND meal='' AND vehicle_id IS NULL AND category!='Meals' AND NOT EXISTS(SELECT 1 FROM home_office_costs h WHERE h.expense_id=expenses.id) AND NOT EXISTS(SELECT 1 FROM equipment_assets a WHERE a.expense_id=expenses.id) ORDER BY date,id LIMIT 501",(record_user_id(),rule['merchant']))
    if ids is not None:
        ids=selected_ids(ids);candidates=[r for r in candidates if r['id'] in ids]
        if len(candidates)!=len(ids): fail('Some selected expenses no longer match this rule.',409)
    if len(candidates)>500: fail('Select at most 500 expenses for one application.')
    before=[];after=[]
    work,business=rule['work_percent'],rule['business_percent']
    for e in candidates:
        changed=dict(e,category=rule['category'],work_percent=work,business_percent=business,percent=work+business,
                     scope='split' if work and business else 'work' if work else 'business' if business else 'personal',status='review')
        if changed!=e: before.append(e);after.append(changed)
    return dict(rule=rule,before=before,after=after)


def register(app,auth):
    @app.route('/api/workflows/items/<int:eid>',methods=['GET','PUT'], endpoint='expense_workflows_items')
    @auth('owner','tax_agent')
    def items(eid):
        from app import db, expense, audit, one, fail
        if request.method=='GET':
            e=expense(eid)
            return jsonify(expense=e,items=json.loads(e['items_json']),token=preview('items',e))
        write_access();d=body();db().execute('BEGIN IMMEDIATE');e=expense(eid,True)
        checked(d.get('token'),'items',e);lines=validate_items(d.get('items'),e)
        # Parent percentages are a UI summary; exact allocations always use the lines.
        work=sum(allocations(x)[0] for x in lines);business=sum(allocations(x)[1] for x in lines)
        wp=round(100*work/e['amount_cents']) if lines and e['amount_cents'] else e['work_percent']
        bp=round(100*business/e['amount_cents']) if lines and e['amount_cents'] else e['business_percent']
        if not 0<=wp<=100 or not 0<=bp<=100 or wp+bp>100: fail('The signed item allocations are inconsistent with the payment. Check discounts and refunds.')
        scope=('split' if any(x['work_percent'] for x in lines) and any(x['business_percent'] for x in lines) else 'work' if any(x['work_percent'] for x in lines) else 'business' if any(x['business_percent'] for x in lines) else 'personal') if lines else e['scope']
        db().execute("UPDATE expenses SET items_json=?,scope=?,percent=?,work_percent=?,business_percent=?,status='review' WHERE id=?",(json.dumps(lines),scope,wp+bp,wp,bp,eid))
        audit('receipt items updated',eid);db().commit();return jsonify(ok=True)

    @app.route('/api/workflows/rules',methods=['GET','POST'], endpoint='expense_workflows_rules')
    @auth('owner','tax_agent')
    def rules():
        from app import db, one, fail, textval, category_names, record_user_id, audit
        if request.method=='GET': return jsonify(rules_data())
        write_access();d=body();merchant=textval(d.get('merchant'),200).casefold()
        try: work,business=split_values(d)
        except ValueError as exc: fail(str(exc))
        if not merchant or d.get('category') not in category_names() or d['category']=='Meals': fail('Choose a merchant and an ordinary expense category.')
        db().execute('BEGIN IMMEDIATE');ident=d.get('id')
        if ident:
            old=one('SELECT * FROM categorisation_rules WHERE id=? AND user_id=?',(integer(ident,'rule ID',1),record_user_id()))
            if not old: fail('Rule not found.',404)
            if d.get('version')!=old['version']: fail('Rule changed. Reload it.',409)
            db().execute('UPDATE categorisation_rules SET merchant=?,category=?,work_percent=?,business_percent=?,enabled=?,version=version+1 WHERE id=?',(merchant,d['category'],work,business,int(d.get('enabled',True) is True),ident))
        else:
            ident=db().execute('INSERT INTO categorisation_rules(user_id,merchant,category,work_percent,business_percent) VALUES (?,?,?,?,?)',(record_user_id(),merchant,d['category'],work,business)).lastrowid
        audit('categorisation rule saved',ident);db().commit();return jsonify(id=ident)

    @app.post('/api/workflows/rules/<int:rid>/<action>', endpoint='expense_workflows_apply_rule')
    @auth('owner','tax_agent')
    def apply_rule(rid,action):
        from app import db, fail
        write_access();d=body()
        if action not in ('preview','apply'): fail('Unknown rule action.',404)
        if action=='apply': db().execute('BEGIN IMMEDIATE')
        plan=rule_plan(rid,d.get('ids'))
        if action=='preview': return jsonify(**plan,token=preview('rule',plan))
        checked(d.get('token'),'rule',plan)
        for e in plan['after']:
            db().execute('UPDATE expenses SET category=?,work_percent=?,business_percent=?,percent=?,scope=?,status=? WHERE id=?',tuple(e[k] for k in ('category','work_percent','business_percent','percent','scope','status','id')))
        ident=record_change('categorisation rule applied',plan['before'],plan['after']);db().commit()
        return jsonify(ok=True,change_id=ident,count=len(plan['after']))

    @app.post('/api/workflows/rules/undo/<int:cid>', endpoint='expense_workflows_undo')
    @auth('owner','tax_agent')
    def undo(cid):
        from app import db, one, fail, record_user_id, audit
        write_access();db().execute('BEGIN IMMEDIATE')
        change=one("SELECT * FROM workflow_changes WHERE id=? AND user_id=? AND kind='categorisation rule applied' AND undone=0",(cid,record_user_id()))
        if not change: fail('Change not found or already undone.',404)
        for saved in json.loads(change['after_json']):
            if one('SELECT * FROM expenses WHERE id=?',(saved['id'],))!=saved: fail('An affected expense changed after applying this rule. Undo would overwrite it.',409)
        for e in json.loads(change['before_json']):
            db().execute('UPDATE expenses SET category=?,work_percent=?,business_percent=?,percent=?,scope=?,status=? WHERE id=?',tuple(e[k] for k in ('category','work_percent','business_percent','percent','scope','status','id')))
        db().execute('UPDATE workflow_changes SET undone=1 WHERE id=?',(cid,));audit('categorisation rule undone',cid);db().commit();return jsonify(ok=True)
