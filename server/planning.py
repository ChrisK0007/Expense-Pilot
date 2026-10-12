"""Monthly category budgets and non-posting Australian car-method comparisons."""
import re
from datetime import date
from decimal import Decimal
from flask import Blueprint, jsonify, request
from expense_core import allocations, percent
from tax_core import rounded
from tracking import access

bp = Blueprint('planning', __name__, url_prefix='/api')
RATES = {2022: 78, 2023: 85, 2024: 88, 2025: 88, 2026: 91}
COST_KINDS = ('running', 'fuel', 'charging', 'servicing', 'registration', 'insurance', 'interest', 'lease', 'parking_tolls', 'purchase', 'other')
SOURCES = [
    'https://www.legislation.gov.au/F2026L00785/asmade/text',
    'https://www.ato.gov.au/api/public/content/bc562d4d-fcaf-4e15-b595-cca75e30f8bc_Taxtimetoolkit_Keepingrecordsforworkrelatedexpenses_pdf',
]


def month_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'20\d\d-(0[1-9]|1[0-2])', value):
        fail('Choose a month in YYYY-MM format.')
    return value


def scope_amount(expense, scope):
    # Budgets measure recorded spending, including bank-review entries and refunds.
    # Reimbursed costs are excluded; tax deductibility is a separate calculation.
    if expense['reimbursed']: return 0
    work,business=allocations(expense)
    return {'all':expense['amount_cents'],'work':work,'business':business,'personal':expense['amount_cents']-work-business}[scope]


def budget_list(month):
    expenses = rows('SELECT * FROM expenses WHERE date>=? AND date<=?', (month+'-01', month+'-31'))
    result = rows('SELECT * FROM category_budgets WHERE month=? ORDER BY category,scope', (month,))
    for item in result:
        spent = sum(scope_amount(e, item['scope']) for e in expenses if e['category']==item['category'])
        item.update(spent_cents=spent, remaining_cents=item['amount_cents']-spent)
    return result


@bp.route('/budgets', methods=['GET', 'POST'])
@access
def budgets():
    if request.method == 'GET':
        return jsonify(budget_list(month_value(request.args.get('month'))))
    d=body(); values=budget_values(d)
    db().execute('BEGIN IMMEDIATE')
    if one('SELECT id FROM category_budgets WHERE month=? AND category=? AND scope=?',values[:3]):
        fail('A budget already exists for this category, month and allocation.',409)
    bid=db().execute('INSERT INTO category_budgets(month,category,scope,amount_cents) VALUES (?,?,?,?)',values).lastrowid
    audit('category budget created',bid);db().commit();return jsonify(id=bid)


def budget_values(d):
    month=month_value(d.get('month')); category=d.get('category'); scope=d.get('scope','all')
    if category not in category_names() or scope not in ('all','work','business','personal'): fail('Choose a category and allocation.')
    amount=money(d.get('amount'))
    if amount<=0: fail('Enter a budget greater than zero.')
    return month,category,scope,amount


@bp.route('/budgets/<int:bid>', methods=['PUT','DELETE'])
@access
def budget(bid):
    d=body();db().execute('BEGIN IMMEDIATE')
    old=one('SELECT * FROM category_budgets WHERE id=?',(bid,))
    if not old: fail('Budget not found.',404)
    if type(d.get('version')) is not int or d['version']!=old['version']: fail('This budget changed. Refresh before editing.',409)
    if request.method=='DELETE': db().execute('DELETE FROM category_budgets WHERE id=?',(bid,))
    else:
        values=budget_values(d)
        if one('SELECT id FROM category_budgets WHERE month=? AND category=? AND scope=? AND id!=?',values[:3]+(bid,)): fail('That budget already exists.',409)
        db().execute('UPDATE category_budgets SET month=?,category=?,scope=?,amount_cents=?,version=version+1 WHERE id=?',values+(bid,))
    audit('category budget updated',bid);db().commit();return jsonify(ok=True)


@bp.post('/budgets/copy')
@access
def copy_budgets():
    d=body(); source=month_value(d.get('from')); target=month_value(d.get('to'))
    if source==target: fail('Choose different months.')
    db().execute('BEGIN IMMEDIATE')
    count=db().execute('INSERT OR IGNORE INTO category_budgets(month,category,scope,amount_cents) SELECT ?,category,scope,amount_cents FROM category_budgets WHERE month=?',(target,source)).rowcount
    audit('category budgets copied',target);db().commit();return jsonify(added=count)


def comparison(vid,year):
    vehicle(vid)
    if year not in RATES: fail('Choose a supported financial year from 2022–23 to 2026–27.')
    start=f'{year}-07-01';end=f'{year+1}-06-30'
    settings=one('SELECT * FROM vehicle_comparison_settings WHERE vehicle_id=? AND year=?',(vid,year)) or dict(vehicle_id=vid,year=year,work_percent=0,business_percent=0,depreciation_cents=0,logbook_start='',logbook_end='',notes='',version=0)
    costs=rows('SELECT e.id,e.date,e.merchant,e.amount_cents,e.reimbursed,e.receipt_id,e.status,e.notes,COALESCE(c.kind,\'running\') kind,COALESCE(c.included,1) included,COALESCE(c.gst_credit_cents,0) gst_credit_cents,COALESCE(c.version,0) version FROM expenses e LEFT JOIN vehicle_cost_details c ON c.expense_id=e.id WHERE e.vehicle_id=? AND e.date BETWEEN ? AND ? ORDER BY e.date DESC,e.id DESC',(vid,start,end))
    base=0
    for cost in costs:
        cost['counted']=bool(cost['included'] and not cost['reimbursed'] and cost['kind'] not in ('parking_tolls','purchase'))
        cost['net_cents']=cost['amount_cents']-cost['gst_credit_cents']
        if cost['counted']: base+=cost['net_cents']
    js=rows('SELECT * FROM vehicle_journeys WHERE vehicle_id=? AND date BETWEEN ? AND ?',(vid,start,end))
    work=sum(Decimal(j['distance_m'])*j['percent']/100 for j in js if j['scope']=='work')
    business=sum(Decimal(j['distance_m'])*j['percent']/100 for j in js if j['scope']=='business')
    eligible=work+business; capped=min(eligible,Decimal(5000000)); cpk=rounded(capped*RATES[year]/1000)
    cpk_work=rounded(Decimal(cpk)*work/eligible) if eligible else 0
    expense_base=max(0,base)+settings['depreciation_cents']
    log_total=rounded(Decimal(expense_base)*(settings['work_percent']+settings['business_percent'])/100)
    log_work=rounded(Decimal(expense_base)*settings['work_percent']/100)
    period_days=(date.fromisoformat(settings['logbook_end'])-date.fromisoformat(settings['logbook_start'])).days+1 if settings['logbook_start'] and settings['logbook_end'] else 0
    warnings=[]
    if not settings['version']: warnings.append('Enter your representative logbook percentages to estimate the logbook method.')
    if period_days<84: warnings.append('A representative logbook normally covers at least 12 continuous weeks. The entered dates do not establish a full period.')
    if any(c['counted'] and not c['receipt_id'] for c in costs): warnings.append('Some included costs have no attached receipt. Fuel/oil estimates require supporting records; retain evidence for other costs.')
    if any(c['counted'] and c['status']!='ready' for c in costs): warnings.append('Included costs contain records still awaiting review.')
    if base<0: warnings.append('Net running costs are negative after refunds. Review the records; the comparison uses zero running costs.')
    return dict(vehicle_id=vid,year=year,start=start,end=end,rate_cents=RATES[year],cap_km=5000,settings=settings,costs=costs,
                recorded_metres=sum(j['distance_m'] for j in js),eligible_metres=float(eligible),capped_metres=float(capped),
                running_costs_cents=base,depreciation_cents=settings['depreciation_cents'],cost_base_cents=expense_base,
                cents_per_km=dict(total_cents=cpk,work_cents=cpk_work,business_cents=cpk-cpk_work),
                logbook=dict(total_cents=log_total,work_cents=log_work,business_cents=log_total-log_work),
                difference_cents=log_total-cpk,logbook_days=period_days,warnings=warnings,sources=SOURCES,
                note='Comparison only: these estimates are not added to your tax forecast. Existing expense allocations remain as entered. Cents/km already covers fuel, servicing, registration, insurance and depreciation; do not claim those costs again. Logbook percentages must reflect eligible use, supported by your logbook and odometer records. Amounts are deductions, not tax refunds.')


@bp.route('/vehicles/<int:vid>/comparison/<int:year>',methods=['GET','PUT'])
@access
def vehicle_comparison(vid,year):
    vehicle(vid)
    if year not in RATES: fail('Choose a supported financial year from 2022–23 to 2026–27.')
    if request.method=='PUT':
        d=body()
        try: wp,bpctl=percent(d.get('work_percent',0)),percent(d.get('business_percent',0))
        except ValueError as exc: fail(str(exc))
        if wp+bpctl>100: fail('Employment and business use cannot total more than 100%.')
        depreciation=money(d.get('depreciation',0))
        if depreciation<0: fail('Depreciation cannot be negative. Enter the annual deductible decline in value before allocation, not the purchase price.')
        start=day(d['logbook_start']) if d.get('logbook_start') else '';end=day(d['logbook_end']) if d.get('logbook_end') else ''
        if bool(start)!=bool(end) or (start and end<start): fail('Enter both logbook dates in chronological order.')
        db().execute('BEGIN IMMEDIATE')
        old=one('SELECT version FROM vehicle_comparison_settings WHERE vehicle_id=? AND year=?',(vid,year))
        if type(d.get('version',0)) is not int or d.get('version',0)!=(old['version'] if old else 0): fail('Comparison settings changed. Refresh before editing.',409)
        db().execute('INSERT INTO vehicle_comparison_settings(vehicle_id,year,work_percent,business_percent,depreciation_cents,logbook_start,logbook_end,notes) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(vehicle_id,year) DO UPDATE SET work_percent=excluded.work_percent,business_percent=excluded.business_percent,depreciation_cents=excluded.depreciation_cents,logbook_start=excluded.logbook_start,logbook_end=excluded.logbook_end,notes=excluded.notes,version=vehicle_comparison_settings.version+1',(vid,year,wp,bpctl,depreciation,start,end,textval(d.get('notes'),2000)))
        audit('vehicle comparison assumptions updated',f'{vid}/{year}');db().commit()
    return jsonify(comparison(vid,year))


@bp.put('/vehicle-costs/<int:eid>')
@access
def cost_details(eid):
    e=expense(eid,True)
    if not e.get('vehicle_id'): fail('Link this expense to a vehicle first.')
    d=body();kind=d.get('kind','running');gst=money(d.get('gst_credit',0))
    if kind not in COST_KINDS or type(d.get('included')) is not bool: fail('Choose a cost type and whether it is included.')
    if not 0<=gst<=max(0,e['amount_cents']): fail('GST credit must be between zero and the expense amount.')
    db().execute('BEGIN IMMEDIATE')
    old=one('SELECT version FROM vehicle_cost_details WHERE expense_id=?',(eid,))
    if type(d.get('version',0)) is not int or d.get('version',0)!=(old['version'] if old else 0): fail('Cost settings changed. Refresh before editing.',409)
    db().execute('INSERT INTO vehicle_cost_details(expense_id,kind,included,gst_credit_cents) VALUES (?,?,?,?) ON CONFLICT(expense_id) DO UPDATE SET kind=excluded.kind,included=excluded.included,gst_credit_cents=excluded.gst_credit_cents,version=vehicle_cost_details.version+1',(eid,kind,int(d['included']),gst))
    audit('vehicle comparison cost updated',eid);db().commit();return jsonify(ok=True)


def register(app, **deps):
    globals().update(deps)
    app.register_blueprint(bp)
