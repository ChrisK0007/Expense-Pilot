"""Overnight spending, reasonable-amount comparisons and reviewed claims.

ATO amounts are substantiation benchmarks, never automatically booked deductions.
Rates: TD 2025/4 and TD 2026/4, domestic tables 1–3. High-cost centres use
capital-city meal amounts. Overseas meal benchmarks are published as daily amounts.
"""
import json
from datetime import date, timedelta
from flask import Blueprint, g, jsonify, request
from expense_core import allocations
from workflow_core import digest
from overnight_rates import CAPITALS, HIGH_COST, COUNTRY_GROUPS, OVERSEAS, options

bp = Blueprint('overnights', __name__, url_prefix='/api')
MEALS = ('Breakfast', 'Lunch', 'Dinner', 'Incidentals')
# Integer cents: rows = salary bands; columns = breakfast/lunch/dinner/incidentals.
RATES = {
    2025: dict(bands=(148250, 263850), capital=((3475,3910,6665,2450),(3785,5345,7500,3505),(4215,5960,8340,3505)),
               country=((3115,3555,6130,2450),(3475,3555,6900,3505),(4215,5960,8340,3505)), determination='TD 2025/4'),
    2026: dict(bands=(153210, 272680), capital=((3600,4045,6900,2540),(3920,5535,7765,3630),(4365,6170,8635,3630)),
               country=((3225,3680,6345,2540),(3600,3680,7145,3630),(4365,6170,8635,3630)), determination='TD 2026/4'),
}
NOTICE = ('ATO reasonable amounts are record-keeping thresholds, not automatic deductions or a cap on a substantiated claim. '
          'Only eligible expenses actually incurred, paid by you and not reimbursed can be claimed. '
          'A genuine employer allowance and the applicable tax-return treatment are required for the allowance substantiation exception. '
          'Keep evidence of the trip, allowance and how spending was calculated. Only reviewed actual costs you explicitly confirm are included in the tax forecast.')


def is_overnight(expense):
    return bool(expense.get('trip_id') or expense.get('meal') or expense.get('category') == 'Meals')


def days(start, end):
    current, last = date.fromisoformat(start), date.fromisoformat(end)
    if (last-current).days > 366:
        raise ValueError('Split comparisons longer than one year into shorter trips.')
    while current <= last:
        yield current.isoformat()
        current += timedelta(days=1)


def year_for(when):
    return int(when[:4]) - (int(when[5:7]) < 7)


def band_for(year, salary_cents):
    lower, upper = RATES[year]['bands']
    return 0 if salary_cents <= lower * 100 else 1 if salary_cents <= upper * 100 else 2


def salary_context(trip, years):
    from app import rows
    options = {}
    for year in sorted(years & RATES.keys()):
        lower, upper = RATES[year]['bands']
        options[year] = [f'Up to ${lower:,}', f'${lower+1:,} to ${upper:,}', f'Over ${upper:,}']
    employers = {}
    if trip['scope'] == 'work':
        for record in rows('SELECT employer,year,band FROM overnight_salary_bands WHERE user_id=? ORDER BY year DESC',
                           (trip['user_id'],)):
            value = employers.setdefault(record['employer'].casefold(), dict(name=record['employer'], saved={}, suggested={}))
            if record['year'] in options:
                value['saved'][record['year']] = record['band']
        for record in rows("SELECT employer,date,annual_base_cents,record_kind,receipt_id FROM employment_income ORDER BY date DESC,id DESC"):
            name = record['employer'].strip()
            if not name:
                continue
            value = employers.setdefault(name.casefold(), dict(name=name, saved={}, suggested={}))
            year = year_for(record['date'])
            if year in options and record['record_kind'] == 'payslip' and record['receipt_id'] and record['annual_base_cents']:
                value['suggested'].setdefault(year, band_for(year, record['annual_base_cents']))
    return dict(years=options, employers=sorted(employers.values(), key=lambda item: item['name'].casefold()))


def reviewed_bands(payload, trip, money, destination):
    years = {year_for(day) for day in days(trip['start'], trip['end'])} & RATES.keys()
    year_keys = {str(year) for year in years}
    provided = payload.get('salary_bands', {})
    if not isinstance(provided, dict) or any(
        key not in year_keys or type(band) is not int or not 0 <= band <= 2
        for key, band in provided.items()
    ):
        raise ValueError('Choose a valid ATO salary band for each financial year.')
    salary = money(payload['salary']) if payload.get('salary') not in (None, '') else 0
    if salary < 0:
        raise ValueError('Enter a positive annual salary excluding allowances.')
    bands = {**provided}
    if salary:
        bands = {str(year): band_for(year, salary) for year in years}
    if trip['scope'] == 'work' and destination != 'custom' and len(bands) != len(years):
        raise ValueError('Choose a salary band for each travel year or enter your annual salary excluding allowances.')
    employer = payload.get('employer', '')
    if not isinstance(employer, str) or len(employer.strip()) > 200:
        raise ValueError('Enter an employer name of up to 200 characters.')
    return salary, bands, employer.strip()


def validate_settings(payload, trip, money):
    if not isinstance(payload, dict): raise ValueError('Provide comparison details as an object.')
    destination = payload.get('destination_class')
    if destination not in ('capital', 'country', 'high_cost', 'custom', 'domestic', 'overseas'):
        raise ValueError('Choose a destination class, or enter custom verified amounts for overseas travel.')
    location = str(payload.get('destination') or '').strip()
    if destination in ('domestic','overseas') and location not in options({year_for(d) for d in days(trip['start'],trip['end'])})[destination]:
        raise ValueError('Choose an Australian locality or an overseas country from the list.')
    selected = payload.get('days')
    allowed = set(days(trip['start'], trip['end']))
    if not isinstance(selected, list) or len(selected) > len(allowed): raise ValueError('Choose meals for valid travel days.')
    result, seen = [], set()
    for row in selected:
        if not isinstance(row, dict) or row.get('date') not in allowed or row['date'] in seen: raise ValueError('Each travel day must appear once and fall inside the trip.')
        seen.add(row['date'])
        if any(not isinstance(row.get(meal, False), bool) for meal in MEALS): raise ValueError('Meal selections must be on or off.')
        result.append({'date': row['date'], **{meal: row.get(meal, False) for meal in MEALS}})
    custom = {}
    if destination == 'custom':
        if not isinstance(payload.get('custom_rates', {}), dict): raise ValueError('Provide custom amounts for each meal.')
        for meal in MEALS:
            value = money(payload.get('custom_rates', {}).get(meal, 0))
            if value < 0: raise ValueError('Custom amounts cannot be negative.')
            custom[meal] = value
        if not str(payload.get('source', '')).strip(): raise ValueError('Record the source and financial year of your custom amounts.')
    flags = {}
    for name in ('allowance_received', 'allowance_declared'):
        if not isinstance(payload.get(name, False), bool): raise ValueError('Allowance selections must be on or off.')
        flags[name] = payload.get(name, False)
    salary, bands, employer = reviewed_bands(payload, trip, money, destination)
    return dict(salary_cents=salary, salary_bands=bands, employer=employer,
                destination_class=destination, destination=location, days=result, custom_rates=custom,
                source=str(payload.get('source', '')).strip()[:1000], **flags)


def claim_records(trip, expenses):
    if trip['scope'] not in ('work','business') or trip['start'] >= trip['end']:
        return []
    return [e for e in expenses if e['status']=='ready' and not e['reimbursed']
            and e.get('user_id')==trip.get('user_id') and trip['start']<=e['date']<=trip['end']]


def claim_stamp(trip, expenses):
    trip_fields = {k:trip[k] for k in ('id','user_id','scope','location','start','end','purpose','allowance_cents')}
    expense_fields = ('id','date','amount_cents','scope','percent','work_percent','business_percent','items_json','receipt_id','meal','notes')
    records = [{k:e.get(k) for k in expense_fields} for e in sorted(claim_records(trip,expenses),key=lambda row:row['id'])]
    return digest([trip_fields,records])


def approved(trip, expenses, settings=None):
    settings = settings if settings is not None else json.loads(trip.get('comparison_json') or '{}')
    return bool(settings.get('claim_stamp') and settings['claim_stamp']==claim_stamp(trip,expenses))


def reviewed_totals(year, trips):
    from app import rows
    eligible=dict(work=0,business=0)
    for trip in trips:
        expenses=rows('SELECT * FROM expenses WHERE trip_id=?',(trip['id'],))
        if not approved(trip,expenses):
            continue
        scope=trip['scope']
        part=0 if scope=='work' else 1
        eligible[scope]+=sum(allocations(e)[part] for e in claim_records(trip,expenses) if year_for(e['date'])==year)
    return eligible


def comparison(trip, expenses):
    settings = json.loads(trip.get('comparison_json') or '{}')
    selected = {row['date']: row for row in settings.get('days', [])}
    salary = settings.get('salary_cents', 0)
    destination = settings.get('destination_class', '')
    location = settings.get('destination','')
    result, missing, sources, daily, partial_days = [], [], set(), [], []
    for when in days(trip['start'], trip['end']):
        year = year_for(when)
        table = RATES.get(year)
        rates = None
        selected_day = selected.get(when,{})
        if destination == 'custom':
            rates = [settings['custom_rates'].get(meal, 0) for meal in MEALS]
            sources.add(settings.get('source', 'Custom amounts'))
        elif table and destination and (str(year) in settings.get('salary_bands', {}) or salary):
            band = settings.get('salary_bands', {}).get(str(year))
            if band is None:
                band = band_for(year, salary)
            if destination == 'overseas':
                group=COUNTRY_GROUPS[year].get(location,3)
                meal, incidental=OVERSEAS[band][group-1]
                selections=sum(bool(selected_day.get(k)) for k in MEALS[:3])
                if selections not in (0,3):
                    partial_days.append(when)
                daily.append(dict(date=when,group=group,meals_cents=meal*100,
                                  selected_meals_cents=meal*100 if selections==3 else 0, incidentals_cents=incidental*100))
                rates=[None,None,None,incidental*100]
            else:
                regional=destination=='country' or destination=='domestic' and location not in CAPITALS and location not in HIGH_COST[year]
                rates = table['country' if regional else 'capital'][band]
            sources.add(table['determination'])
        elif destination:
            missing.append(f'{year}–{year+1}')
        for index, meal in enumerate(MEALS):
            included = selected_day.get(meal,False)
            matching = [e for e in expenses if e['date'] == when and e['meal'] == meal]
            actual = sum(e['amount_cents'] for e in matching)
            allocated = sum(allocations(e)[0 if trip['scope'] == 'work' else 1] for e in matching if e['status'] == 'ready')
            result.append(dict(date=when, meal=meal, selected=included, actual_cents=actual, recorded_unreimbursed_cents=allocated,
                               reasonable_cents=rates[index] if rates is not None and included else 0 if not included else None))
    actual = sum(e['amount_cents'] for e in expenses)
    reimbursed = sum(e['amount_cents'] for e in expenses if e['reimbursed'])
    comparable = sum(r['recorded_unreimbursed_cents'] for r in result if r['selected'])
    reasonable = None if missing or partial_days or not settings else sum(r['reasonable_cents'] or 0 for r in result)+sum(d['selected_meals_cents'] for d in daily)
    recorded=sum(allocations(e)[0 if trip['scope']=='work' else 1] for e in claim_records(trip,expenses))
    current=approved(trip,expenses,settings)
    years={year_for(d) for d in days(trip['start'],trip['end'])}
    return dict(trip_id=trip['id'], version=trip['comparison_version'], settings=settings, rows=result,
                actual_cents=actual, reimbursed_cents=reimbursed, allowance_cents=trip['allowance_cents'],
                allowance_less_spending_cents=trip['allowance_cents']-actual+reimbursed,
                recorded_unreimbursed_cents=sum(allocations(e)[0 if trip['scope']=='work' else 1] for e in expenses if e['status']=='ready'),
                comparable_cents=comparable, reasonable_cents=reasonable,
                over_benchmark_cents=None if reasonable is None else comparable-reasonable,
                destinations=options(years), overseas_days=daily, partial_days=partial_days, claim_cents=recorded, claim_current=current,
                claim_stale=bool(settings.get('claim_stamp')) and not current,
                unclassified_cents=sum(e['amount_cents'] for e in expenses if not e['meal']),
                missing_years=sorted(set(missing)), sources=sorted(sources), notice=NOTICE,
                allowance_exception_may_apply=trip['scope']=='work' and trip['start']<trip['end'] and trip['allowance_cents']>0
                and reasonable is not None and reasonable>0 and 0<comparable<=reasonable
                and settings.get('allowance_received', False) and settings.get('allowance_declared', False))


def register(app, auth):
    @bp.route('/trips/<int:tid>/overnight', methods=['GET','PUT'])
    @auth()
    def overnight(tid):
        from app import one, rows, db, fail, can_write, money, audit
        trip = one('SELECT * FROM trips WHERE id=?', (tid,))
        if not trip or (g.user['role'] not in ('owner','tax_agent') and trip['user_id'] != g.user['id']): fail('Trip not found.',404)
        if request.method == 'PUT':
            if not can_write(): fail('Read-only access.',403)
            payload = request.get_json()
            if not isinstance(payload,dict): fail('Enter valid trip review details.')
            db().execute('BEGIN IMMEDIATE')
            trip = one('SELECT * FROM trips WHERE id=?', (tid,))
            if payload.get('version') != trip['comparison_version']: fail('This comparison changed. Reload it before saving.',409)
            try: settings = validate_settings(payload, trip, money)
            except (ValueError, TypeError) as exc: fail(str(exc))
            remember = payload.get('remember_salary', False)
            if type(remember) is not bool:
                fail('Choose whether to reuse this salary band.')
            if remember:
                employer = settings['employer']
                if trip['scope'] != 'work' or not employer or not settings['salary_bands']:
                    fail('Choose an employer and a salary band before saving a default.')
                db().executemany("""INSERT INTO overnight_salary_bands(user_id,year,employer_key,employer,band)
                    VALUES (?,?,?,?,?) ON CONFLICT(user_id,year,employer_key)
                    DO UPDATE SET employer=excluded.employer,band=excluded.band""",
                    [(trip['user_id'], int(year), employer.casefold(), employer, band)
                     for year, band in settings['salary_bands'].items()])
            confirm=payload.get('confirm_claim',False)
            if type(confirm) is not bool: fail('Use a valid claim confirmation.')
            if confirm:
                expenses=rows('SELECT * FROM expenses WHERE trip_id=?',(tid,))
                records=claim_records(trip,expenses)
                part=0 if trip['scope']=='work' else 1
                if sum(allocations(e)[part] for e in records)<=0:
                    fail('Review the eligible unreimbursed expenses before confirming this trip.')
                settings['claim_stamp']=claim_stamp(trip,expenses)
            db().execute('UPDATE trips SET comparison_json=?,comparison_version=comparison_version+1 WHERE id=?', (json.dumps(settings),tid))
            audit('overnight comparison updated',tid); db().commit()
            trip = one('SELECT * FROM trips WHERE id=?', (tid,))
        try:
            result = comparison(trip, rows('SELECT * FROM expenses WHERE trip_id=?', (tid,)))
            result['salary_context'] = salary_context(trip, {year_for(day) for day in days(trip['start'], trip['end'])})
            return jsonify(result)
        except ValueError as exc: fail(str(exc))
    app.register_blueprint(bp)
