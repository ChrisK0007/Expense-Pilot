"""Expense allocations shared by reports, exports and the tax forecast."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

def migrate(connection):
    columns={r[1] for r in connection.execute('PRAGMA table_info(expenses)')}
    for name in ('work_percent','business_percent'):
        if name not in columns:
            connection.execute(f'ALTER TABLE expenses ADD COLUMN {name} INTEGER')
    connection.execute("UPDATE expenses SET work_percent=CASE WHEN scope='work' THEN percent ELSE 0 END,business_percent=CASE WHEN scope='business' THEN percent ELSE 0 END WHERE work_percent IS NULL OR business_percent IS NULL")

def percent(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n != int(n) or not 0 <= n <= 100:
            raise ValueError()
        return int(n)
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise ValueError('Percentages must be whole numbers from 0–100.')

def split_values(data):
    if 'work_percent' in data or 'business_percent' in data:
        if data.get('work_percent') is None or data.get('business_percent') is None:
            raise ValueError('Enter both employment and business percentages.')
        work, business = percent(data['work_percent']), percent(data['business_percent'])
    else:
        scope = data.get('scope')
        if scope == 'split':
            raise ValueError('Enter both employment and business percentages for a split expense.')
        use = percent(data.get('percent', 100))
        work, business = (use if scope == 'work' else 0), (use if scope == 'business' else 0)
    if work + business > 100:
        raise ValueError('Employment and business percentages cannot total more than 100%.')
    return work, business

def percentages(expense):
    if expense.get('work_percent') is not None and expense.get('business_percent') is not None:
        return expense['work_percent'], expense['business_percent']
    return split_values({k: expense[k] for k in ('scope', 'percent')})

def allocations(expense):
    if expense.get('reimbursed'):
        return 0, 0
    import json
    lines = json.loads(expense.get('items_json') or '[]')
    if lines:
        parts = [allocations({**expense, **line, 'items_json':'[]'}) for line in lines]
        return sum(p[0] for p in parts), sum(p[1] for p in parts)
    work, business = percentages(expense)
    amount = expense['amount_cents']
    total = int((Decimal(amount) * (work + business) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    employment = int((Decimal(amount) * work / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    # Assign any rounding remainder to business so the parts always equal the total.
    return employment, total - employment
