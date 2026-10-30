"""Deterministic general depreciation and confirmed immediate-deduction eligibility.

Rules checked 2026-10-30. See docs/equipment-calculations.md for scope/sources.
Money is integer cents, with Decimal intermediate arithmetic and annual rounding.
"""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json

RULESET = 'AU-equipment-2026-10-31'
# Temporary thresholds plus the permanent threshold enacted from 1 July 2026.
INSTANT_LIMITS = {2024: 2000000, 2025: 2000000, 2026: 2000000}
METHODS = {'prime_cost', 'diminishing_value', 'immediate_employee', 'immediate_business'}


def instant_limit(year):
    return 2000000 if 2026<=year<=2098 else INSTANT_LIMITS.get(year)


def fy(value):
    d=date.fromisoformat(value); return d.year-(d.month<7)


def cents(value):
    return int(Decimal(value).quantize(Decimal('1'),rounding=ROUND_HALF_UP))


def validate(asset, payload, history):
    from app import day, money, fail, textval
    if not isinstance(payload,dict): fail('Choose equipment calculation settings.')
    if json.loads(asset.get('import_json') or '{}'): fail('Imported method, rate and opening balance are retained from the reviewed schedule. Use annual overrides or remove and re-import the record.',409)
    method=payload.get('method')
    if method not in METHODS: fail('Choose a supported calculation method.')
    first=day(payload.get('first_use'));tax=day(payload.get('income_use'))
    if first<asset['acquired'] or tax<first: fail('First use must follow acquisition; income use must follow first use.')
    if payload.get('confirmed') is not True: fail('Confirm the calculation setup and eligibility.')
    credit=money(payload.get('gst_credit',0));cost=asset['cost_cents']-credit
    if credit<0 or cost<=0: fail('GST credits must be non-negative and less than the purchase cost.')
    notes=textval(payload.get('basis'),2000)
    if not notes: fail('Record the effective-life or eligibility basis.')
    if any(h['year']<fy(first) for h in history): fail('First use cannot follow an existing annual record.')
    if sum(h['amount_cents'] for h in history)>cost: fail('Existing annual amounts exceed the GST-adjusted cost.')
    if history and payload.get('preserve_history') is not True: fail('Confirm that existing annual amounts will be preserved.')
    try: life=Decimal(str(payload.get('life',0)))
    except Exception: fail('Enter an effective life in years.')
    if not life.is_finite() or method in ('prime_cost','diminishing_value') and not Decimal('0.1')<=life<=100: fail('Enter an effective life between 0.1 and 100 years.')
    if method=='diminishing_value' and asset['acquired']<'2006-05-10': fail('Use manual calculation for assets acquired before 10 May 2006.')
    if method.startswith('immediate_'):
        if first!=tax or history: fail('Immediate deductions with previous private use or annual history need manual review.')
        if payload.get('eligible_asset') is not True: fail('Confirm this asset is eligible for the selected treatment.')
    if method=='immediate_employee':
        if cost>30000 or asset['work_percent']<=50: fail('Employee immediate deduction requires cost of $300 or less and mainly non-business income use.')
        if payload.get('not_grouped') is not True: fail('Confirm this is not part of a set or identical-item group costing over $300.')
    if method=='immediate_business':
        limit=instant_limit(fy(first))
        if not limit or cost>=limit: fail('This year/cost is outside supported instant write-off rules. Use reviewed manual treatment or pooling.')
        if payload.get('small_business') is not True: fail('Confirm eligibility as a small business and election to use simplified depreciation.')
    if asset.get('calculation_json','{}')!='{}' and any(h['confirmed'] for h in history): fail('Confirmed annual history locks the setup. Use an annual override with a reason.',409)
    return dict(method=method,first_use=first,income_use=tax,life=str(life),gst_credit_cents=credit,
                basis=notes,ruleset=RULESET,confirmed=True)


def schedule(asset, history, usage, through):
    config=json.loads(asset.get('calculation_json') or '{}')
    if not config: return []
    carried=json.loads(asset.get('import_json') or '{}')
    start=carried.get('year',fy(config['first_use']));cost=asset['cost_cents']-config['gst_credit_cents'];remaining=carried.get('opening_cents',cost)
    existing={h['year']:h for h in history};result=[];work=asset['work_percent'];business=asset['business_percent']
    use={u['year']:u for u in usage}
    for year in range(start, min(through,2098)+1):
        if year in use: work,business=use[year]['work_percent'],use[year]['business_percent']
        opening=remaining;begin=max(date(year,7,1),date.fromisoformat(config['first_use']));end=date(year+1,6,30)
        if asset['disposal_date']: end=min(end,date.fromisoformat(asset['disposal_date'])-timedelta(days=1))
        days=max(0,(end-begin).days+1);taxdays=max(0,(end-max(begin,date.fromisoformat(config['income_use']))).days+1)
        method=config['method'];note=config['basis'];gross=claim=0
        if days and remaining:
            if method.startswith('immediate_'):
                gross=remaining if year==start else 0;claim=gross
            else:
                rate=(Decimal(cost if method=='prime_cost' else opening)*Decimal(carried['rate'])/100/365 if carried.get('rate') else Decimal(cost if method=='prime_cost' else opening)/Decimal(config['life'])/365*(2 if method=='diminishing_value' else 1))
                gross=min(opening,cents(rate*days))
                private_before=min(gross,cents(rate*(days-taxdays)))
                claim=max(0,gross-private_before)
        stored=existing.get(year);confirmed=False;source='estimate'
        if stored:
            gross=stored['amount_cents'];claim=stored.get('claimable_cents') if stored.get('claimable_cents') is not None else gross;confirmed=bool(stored['confirmed']);source='confirmed override' if confirmed else 'draft override';note=stored['notes']
        # A draft override reserves its stated balance but never enters a forecast.
        remaining=max(0,opening-gross)
        wp=stored.get('work_percent') if stored else None;bp=stored.get('business_percent') if stored else None
        wp=work if wp is None else wp;bp=business if bp is None else bp
        result.append(dict(asset_id=asset['id'],year=year,amount_cents=gross,claimable_cents=claim,opening_cents=opening,closing_cents=remaining,
                           work_percent=wp,business_percent=bp,confirmed=confirmed,source=source,notes=note,days=days,taxable_days=taxdays,
                           include_forecast=bool(confirmed or not stored),needs_review=bool(asset['disposal_date'] and fy(asset['disposal_date'])==year and not confirmed)))
        if not remaining and year>=max(existing,default=start) and year>=through: break
    return result
