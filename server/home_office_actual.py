"""Calculate reviewed WFH bill allocations without changing the expense ledger."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

ACTUAL_SOURCE = ('https://www.ato.gov.au/individuals-and-families/income-deductions-offsets-and-records/'
                 'deductions-you-can-claim/work-related-deductions/working-from-home-expenses/actual-cost-method')
SCOPES = ('work', 'business')


def numeric(value, maximum):
    try:
        result = Decimal(str(value))
        if result.is_finite() and 0 <= result <= maximum:
            return result
    except ArithmeticError:
        pass
    raise ValueError('Enter valid non-negative work and usage figures.')


def validate(value, kind, year):
    if not value:
        return {}
    if not isinstance(value, dict):
        raise ValueError('Enter a valid cost calculation.')
    mode = value.get('mode')
    if mode == 'power' and kind == 'electricity':
        start, end = (date.fromisoformat(value.get(k) or '').isoformat() for k in ('start', 'end'))
        if not f'{year}-07-01' <= start <= end <= f'{year+1}-06-30':
            raise ValueError('Use the bill coverage dates within the selected financial year.')
        result = dict(mode=mode, start=start, end=end,
                      watts=str(numeric(value.get('watts'), 10000)),
                      cents_per_kwh=str(numeric(value.get('cents_per_kwh'), 1000)))
    elif mode in ('share', 'usage') and (mode == 'share' or kind in ('phone', 'internet', 'phone_internet')):
        total = Decimal(100) if mode == 'share' else numeric(value.get('total'), 1000000)
        portions = {scope: numeric(value.get(scope, 0), total) for scope in SCOPES}
        if not total or sum(portions.values()) > total:
            raise ValueError('Work usage cannot exceed the total bill percentage or usage.')
        result = dict(mode=mode, total=str(total), **{scope: str(n) for scope, n in portions.items()})
    else:
        raise ValueError('Choose a calculation suited to this running cost.')
    return result


def evaluate(cost, entries):
    calculation = cost['actual_calculation']
    if not calculation:
        return dict(work=0, business=0)
    if calculation['mode'] == 'power':
        rate = Decimal(calculation['watts']) * Decimal(calculation['cents_per_kwh']) / 60000
        raw = {scope: rate * sum((e['end_at'] - e['start_at']) // 60 - e['break_minutes']
                                 for e in entries if e['scope'] == scope
                                 and calculation['start'] <= e['date'] <= calculation['end']) for scope in SCOPES}
    else:
        raw = {scope: Decimal(cost['amount_cents']) * Decimal(calculation[scope]) / Decimal(calculation['total'])
               for scope in SCOPES}
    # Allocate the rounding remainder so the two claims cannot exceed the bill.
    work = int(raw['work'].quantize(Decimal(1), rounding=ROUND_HALF_UP))
    total = int(sum(raw.values()).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return dict(work=work, business=total-work)


def assess(costs, entries, extra):
    from home_office import COVERED
    total = dict(extra)
    errors = []
    power_periods = []
    assessed = 0
    for cost in costs:
        if cost['home_office_kind'] not in COVERED:
            continue
        cost['running_actual'] = dict(work=0, business=0)
        calc = cost['actual_calculation']
        if not calc or cost['reimbursed']:
            continue
        if not cost['receipt_id'] or not cost['basis'] or cost['status'] != 'ready':
            errors.append(f"{cost['merchant']}: review the bill, attach evidence and describe the calculation.")
            continue
        if cost['amount_cents'] <= 0:
            errors.append(f"{cost['merchant']}: review the net bill after credits or refunds before claiming.")
            continue
        if calc['mode'] == 'power':
            start, end = calc['start'], calc['end']
            if any(start <= previous_end and previous_start <= end for previous_start, previous_end in power_periods):
                errors.append(f"{cost['merchant']}: electricity coverage overlaps another bill.")
                continue
            power_periods.append((start, end))
        result = evaluate(cost, entries)
        if sum(result.values()) > cost['amount_cents']:
            errors.append(f"{cost['merchant']}: the work-related amount exceeds the bill.")
            continue
        cost['running_actual'] = result
        for scope in SCOPES:
            total[scope] += result[scope]
        assessed += 1
    return total, errors, assessed
