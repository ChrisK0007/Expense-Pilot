"""Separate overnight spending records and domestic reasonable-amount comparisons.

ATO amounts are substantiation benchmarks, never automatically booked deductions.
Rates: TD 2025/4 and TD 2026/4, domestic tables 1–3. High-cost centres use
capital-city meal amounts. Accommodation and overseas rates are not inferred.
"""
import json
from datetime import date, timedelta
from flask import Blueprint, g, jsonify, request
from expense_core import allocations

bp = Blueprint('overnights', __name__, url_prefix='/api')
MEALS = ('Breakfast', 'Lunch', 'Dinner', 'Incidentals')
# Integer cents: rows = salary bands; columns = breakfast/lunch/dinner/incidentals.
RATES = {
    2025: dict(bands=(148250, 263850), capital=((3475,3910,6665,2455),(3780,5340,7495,3505),(4215,5960,8340,3505)),
               country=((3115,3555,6125,2455),(3475,3555,6900,3505),(4215,5960,8340,3505)), determination='TD 2025/4'),
    2026: dict(bands=(153210, 272680), capital=((3600,4045,6900,2540),(3920,5535,7765,3630),(4365,6170,8635,3630)),
               country=((3225,3680,6345,2540),(3600,3680,7145,3630),(4365,6170,8635,3630)), determination='TD 2026/4'),
}
NOTICE = ('ATO reasonable amounts are record-keeping thresholds, not automatic deductions or a cap on a substantiated claim. '
          'Only eligible expenses actually incurred, paid by you and not reimbursed can be claimed. '
          'A genuine employer allowance and the applicable tax-return treatment are required for the allowance substantiation exception. '
          'Keep evidence of the trip, allowance and how spending was calculated. This comparison is excluded from the automatic tax forecast.')


def is_overnight(expense):
    return bool(expense.get('trip_id') or expense.get('meal') or expense.get('category') == 'Meals')


def days(start, end):
    current, last = date.fromisoformat(start), date.fromisoformat(end)
    if (last-current).days > 366:
        raise ValueError('Split comparisons longer than one year into shorter trips.')
    while current <= last:
        yield current.isoformat()
        current += timedelta(days=1)


def validate_settings(payload, trip, money):
    if not isinstance(payload, dict): raise ValueError('Provide comparison details as an object.')
    salary = money(payload.get('salary', 0))
    if salary <= 0: raise ValueError('Enter your annual salary excluding allowances (full-time equivalent if part-time).')
    destination = payload.get('destination_class')
    if destination not in ('capital', 'country', 'high_cost', 'custom'):
        raise ValueError('Choose a destination class, or enter custom verified amounts for overseas travel.')
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
    return dict(salary_cents=salary, destination_class=destination, days=result, custom_rates=custom,
                source=str(payload.get('source', '')).strip()[:1000], **flags)


def comparison(trip, expenses):
    settings = json.loads(trip.get('comparison_json') or '{}')
    selected = {row['date']: row for row in settings.get('days', [])}
    salary = settings.get('salary_cents', 0)
    destination = settings.get('destination_class', '')
    result, missing, sources = [], [], set()
    for when in days(trip['start'], trip['end']):
        year = int(when[:4]) - (int(when[5:7]) < 7)
        table = RATES.get(year)
        rates = None
        if destination == 'custom':
            rates = [settings['custom_rates'].get(meal, 0) for meal in MEALS]
            sources.add(settings.get('source', 'Custom amounts'))
        elif table and salary and destination:
            band = 0 if salary <= table['bands'][0]*100 else 1 if salary <= table['bands'][1]*100 else 2
            rates = table['country' if destination == 'country' else 'capital'][band]
            sources.add(table['determination'])
        elif destination:
            missing.append(f'{year}–{year+1}')
        for index, meal in enumerate(MEALS):
            included = selected.get(when, {}).get(meal, False)
            matching = [e for e in expenses if e['date'] == when and e['meal'] == meal]
            actual = sum(e['amount_cents'] for e in matching)
            allocated = sum(allocations(e)[0 if trip['scope'] == 'work' else 1] for e in matching if e['status'] == 'ready')
            result.append(dict(date=when, meal=meal, selected=included, actual_cents=actual, recorded_unreimbursed_cents=allocated,
                               reasonable_cents=rates[index] if rates is not None and included else 0 if not included else None))
    actual = sum(e['amount_cents'] for e in expenses)
    reimbursed = sum(e['amount_cents'] for e in expenses if e['reimbursed'])
    comparable = sum(r['recorded_unreimbursed_cents'] for r in result if r['selected'])
    reasonable = None if missing or not settings else sum(r['reasonable_cents'] or 0 for r in result)
    return dict(trip_id=trip['id'], version=trip['comparison_version'], settings=settings, rows=result,
                actual_cents=actual, reimbursed_cents=reimbursed, allowance_cents=trip['allowance_cents'],
                allowance_less_spending_cents=trip['allowance_cents']-actual+reimbursed,
                recorded_unreimbursed_cents=sum(allocations(e)[0 if trip['scope']=='work' else 1] for e in expenses if e['status']=='ready'),
                comparable_cents=comparable, reasonable_cents=reasonable,
                over_benchmark_cents=None if reasonable is None else comparable-reasonable,
                unclassified_cents=sum(e['amount_cents'] for e in expenses if not e['meal']),
                missing_years=sorted(set(missing)), sources=sorted(sources), notice=NOTICE,
                allowance_exception_may_apply=trip['scope']=='work' and settings.get('allowance_received', False) and settings.get('allowance_declared', False))


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
            db().execute('BEGIN IMMEDIATE')
            trip = one('SELECT * FROM trips WHERE id=?', (tid,))
            if payload.get('version') != trip['comparison_version']: fail('This comparison changed. Reload it before saving.',409)
            try: settings = validate_settings(payload, trip, money)
            except (ValueError, TypeError) as exc: fail(str(exc))
            db().execute('UPDATE trips SET comparison_json=?,comparison_version=comparison_version+1 WHERE id=?', (json.dumps(settings),tid))
            audit('overnight comparison updated',tid); db().commit()
            trip = one('SELECT * FROM trips WHERE id=?', (tid,))
        try: return jsonify(comparison(trip, rows('SELECT * FROM expenses WHERE trip_id=?', (tid,))))
        except ValueError as exc: fail(str(exc))
    app.register_blueprint(bp)
