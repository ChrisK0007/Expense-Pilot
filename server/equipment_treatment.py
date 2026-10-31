"""Explainable equipment suggestions; saving revalidates all inputs in the expense transaction."""
import json
import re
from flask import g, jsonify, request
from decimal import Decimal
from expense_core import split_values
import equipment_calculations as calc
from workflow_core import body, integer


def profile(year):
    from app import one, record_user_id
    row=one('SELECT * FROM equipment_tax_profiles WHERE user_id=? AND year=?',(record_user_id(),year))
    return dict(year=year,version=row['version'] if row else 0,**(json.loads(row['data']) if row else {'mode':'unknown'}))


def suggest(d):
    from app import day, money, fail, textval
    when=day(d.get('date'));first=day(d.get('first_use') or when);cost=money(d.get('amount'));credit=money(d.get('gst_credit',0))
    if first<when: fail('First use cannot precede acquisition.')
    if credit<0 or credit>=cost: fail('GST credit must be non-negative and less than the original cost.')
    try: work,business=split_values(d)
    except ValueError as exc: fail(str(exc))
    net=cost-credit;year=integer(calc.fy(first),'financial year',1900,2098);settings=profile(year)
    result=dict(year=year,profile=settings,ruleset=calc.RULESET,full_cost_cents=net,work_cents=calc.cents(Decimal(net)*work/100),business_cents=calc.cents(Decimal(net)*business/100),method=None,ready=False,reason='',life_suggestion=None)
    def stop(reason,status='needs_information'):
        return dict(result,reason=reason,status=status)
    if cost<=0 or not work+business or d.get('reimbursed') or d.get('trip_id') or d.get('meal') or d.get('vehicle_id') or d.get('category')=='Meals':
        return stop('Use this check for a personally incurred, standalone equipment purchase with income-producing use.','manual_review')
    if d.get('asset_confirmed') is not True or d.get('purpose_confirmed') is not True:
        return stop('Confirm the actual equipment purchased and its income-producing use. A label such as “hearing protection” does not establish deductibility or approved protective equipment.')
    if d.get('previous_use') is True:
        return stop('Previous private use, existing deductions or a pooled asset need a reviewed opening balance. Use the equipment register or schedule import.','manual_review')
    if settings['mode']=='unknown': return stop('Set your tax treatment for this financial year once, then this check can use it for future purchases.')
    if d.get('eligible_asset') is not True: return stop('Confirm ordinary depreciating equipment eligibility. Vehicles, buildings, software development pools and other special assets need separate review.')
    method=None
    if settings['mode']=='simplified':
        limit=calc.instant_limit(year)
        if not limit or net>=limit: return stop('The full asset cost is outside the supported instant write-off threshold. Small-business pooling needs accountant review; do not split the price to qualify.','manual_review')
        method='immediate_business'
        reason='Eligible sole trader using simplified depreciation: the full asset cost is below $20,000. The income-producing portion can be written off in the year first used, including employment use.'
    elif net<=30000 and work>50:
        if d.get('not_grouped') is not True: return stop('Confirm it is not part of a set or substantially identical items acquired this year costing more than $300 in total.')
        method='immediate_employee';reason='The full asset cost is $300 or less, mainly used for non-business income, with the set and identical-item restrictions confirmed.'
    else:
        reason='Use depreciation under the general rules. The $300 test uses the full asset cost before the employment/business split; mainly non-business income use is also required. Low-value pooling remains a separate reviewed choice.'
        method=d.get('depreciation_method','diminishing_value')
        if method not in ('prime_cost','diminishing_value'): fail('Choose prime cost or diminishing value.')
        if re.search(r'\b(ipad|tablet|laptop|macbook)\b',str(d.get('name','')),re.I): result['life_suggestion']=2
        if not d.get('life') or not textval(d.get('basis'),2000): return dict(result,status='depreciation',method=method,reason=reason+' Confirm an effective life and its basis to automate the schedule.')
    config=dict(method=method,first_use=first,income_use=first,life=d.get('life') or 0,gst_credit=d.get('gst_credit',0),basis=textval(d.get('basis'),2000) or reason,
                confirmed=True,eligible_asset=True,not_grouped=d.get('not_grouped') is True,small_business=settings['mode']=='simplified')
    asset=dict(acquired=when,cost_cents=cost,work_percent=work,business_percent=business)
    validated=calc.validate(asset,config,[])
    return dict(result,method=method,status='immediate' if method.startswith('immediate_') else 'depreciation',ready=True,reason=reason,calculation=validated)


def attach(eid,d):
    """Optional new API field; old mobile clients keep their existing behaviour."""
    from app import db, one, fail, record_user_id, textval, audit, money
    treatment=d.get('tax_treatment')
    if not treatment: return
    if g.user['role']!='owner' or not isinstance(treatment,dict): fail('Only the owner can confirm equipment tax treatment.',403)
    e=one('SELECT * FROM expenses WHERE id=?',(eid,))
    if e['user_id']!=record_user_id(): fail('Equipment must belong to the owner.',403)
    if one('SELECT 1 FROM equipment_assets WHERE expense_id=?',(eid,)): fail('This expense already has an equipment record. Edit its schedule in Equipment.',409)
    if e['items_json']!='[]' or one('SELECT 1 FROM home_office_costs WHERE expense_id=?',(eid,)): fail('This purchase already has another deduction treatment.',409)
    inputs={**treatment,**{k:e[k] for k in ('date','category','work_percent','business_percent','reimbursed','trip_id','meal','vehicle_id')},'amount':str(Decimal(e['amount_cents'])/100)}
    basis=treatment.get('expense_basis')
    if not isinstance(basis,dict): fail('Check the expense basis again.',409)
    try: shares=split_values(basis)
    except ValueError as exc: fail(str(exc))
    if basis.get('date')!=e['date'] or money(basis.get('amount'))!=e['amount_cents'] or shares!=(e['work_percent'],e['business_percent']): fail('The matched expense differs from the reviewed amount, date or use. Open that expense and check its treatment there.',409)
    decision=suggest(inputs)
    if treatment.get('confirmed') is not True or not decision['ready']: fail(decision['reason'])
    if treatment.get('profile_version')!=decision['profile']['version'] or treatment.get('method')!=decision['method']: fail('Tax settings or treatment changed. Check the suggestion again.',409)
    name=textval(treatment.get('name'),200)
    if not name: fail('Name the equipment purchased.')
    aid=db().execute('INSERT INTO equipment_assets(user_id,expense_id,name,acquired,cost_cents,work_percent,business_percent,notes,calculation_json) VALUES (?,?,?,?,?,?,?,?,?)',
        (e['user_id'],eid,name,e['date'],e['amount_cents'],e['work_percent'],e['business_percent'],textval(treatment.get('purpose'),2000),json.dumps(decision['calculation']))).lastrowid
    audit('expense equipment treatment confirmed',json.dumps(dict(asset_id=aid,expense_id=eid,profile=decision['profile'],reason=decision['reason'])))


def register(app,auth):
    @app.route('/api/workflows/equipment/tax-profile/<int:year>',methods=['GET','PUT'])
    @auth('owner')
    def tax_profile(year):
        from app import db,fail,record_user_id,audit
        integer(year,'financial year',1900,2098)
        if request.method=='PUT':
            d=body();mode=d.get('mode')
            if mode not in ('general','simplified') or d.get('confirmed') is not True: fail('Confirm the annual tax treatment.')
            if mode=='simplified' and not all(d.get(k) is True for k in ('sole_trader','small_business','whole_regime')): fail('Confirm eligible sole-trader status, turnover under $10 million and use of the entire simplified depreciation regime.')
            db().execute('BEGIN IMMEDIATE');old=profile(year)
            if d.get('version')!=old['version']: fail('Tax settings changed. Reload.',409)
            data=dict(mode=mode,confirmed=True,sole_trader=d.get('sole_trader') is True,small_business=d.get('small_business') is True,whole_regime=d.get('whole_regime') is True)
            db().execute('INSERT INTO equipment_tax_profiles(user_id,year,data) VALUES (?,?,?) ON CONFLICT(user_id,year) DO UPDATE SET data=excluded.data,version=version+1',(record_user_id(),year,json.dumps(data)))
            audit('equipment annual tax settings',json.dumps(dict(year=year,before=old,after=data)));db().commit()
        return jsonify(profile(year))

    @app.post('/api/workflows/equipment/suggest')
    @auth('owner')
    def suggestion():
        return jsonify(suggest(body()))
