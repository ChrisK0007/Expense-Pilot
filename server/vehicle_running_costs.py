"""Operating-cost reporting from existing expenses and physical readings."""
import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal, DecimalException
from flask import jsonify, request, send_file
import tracking
import workspace_time

EXCLUDED_KINDS = ('purchase', 'parking_tolls')


def measurement(value, maximum, label):
    try:
        scaled = Decimal(str(value)) * 1000
        if not scaled.is_finite() or not 0 <= scaled <= maximum or scaled != scaled.to_integral_value():
            raise ValueError
    except (DecimalException, ValueError):
        tracking.fail(f'Enter a valid {label} with up to three decimal places.')
    return int(scaled)


def clean_fuel_draft(details):
    if details is None:
        return None
    if not isinstance(details, dict) or details.get('full_tank') is not None and type(details['full_tank']) is not bool:
        tracking.fail('Enter valid fuel details.')
    litres, odometer = details.get('litres'), details.get('odometer_km')
    return dict(
        litres=measurement(litres, 1000000, 'fuel volume') / 1000 if litres not in ('', None) else None,
        odometer_km=measurement(odometer, 10000000000, 'odometer reading') / 1000 if odometer not in ('', None) else None,
        full_tank=details.get('full_tank'),
    )


def save_fuel(connection, eid, payload, previous=None):
    """Keep fuel data attached to the expense in the same transaction."""
    if 'fuel_details' not in payload and not (previous and previous['vehicle_id']):
        return
    expense = connection.execute(
        'SELECT vehicle_id,date,amount_cents,meal,trip_id,category FROM expenses WHERE id=?', (eid,)
    ).fetchone()
    linked = bool(expense['vehicle_id'] and expense['amount_cents'] > 0 and not (
        expense['meal'] or expense['trip_id'] or expense['category'] == 'Meals'
    ))
    if 'fuel_details' not in payload:
        if previous and (not linked or previous['vehicle_id'] != expense['vehicle_id']):
            connection.execute('DELETE FROM vehicle_fuel WHERE expense_id=?', (eid,))
        elif previous and expense['date'] != previous['date']:
            saved = connection.execute('SELECT * FROM vehicle_fuel WHERE expense_id=?', (eid,)).fetchone()
            if saved:
                check_reading(connection, eid, expense, saved['odometer_m'])
        return
    details = payload['fuel_details']
    if details is None:
        connection.execute('DELETE FROM vehicle_fuel WHERE expense_id=?', (eid,))
        return
    if not isinstance(details, dict) or type(details.get('full_tank')) is not bool:
        tracking.fail('Choose whether this fill-up left the tank full.')
    if not linked:
        tracking.fail('Fuel details require a positive expense linked to a vehicle.')
    volume = measurement(details.get('litres'), 1000000, 'fuel volume')
    odometer = measurement(details.get('odometer_km'), 10000000000, 'odometer reading')
    if not volume:
        tracking.fail('Enter a fuel volume greater than zero.')
    check_reading(connection, eid, expense, odometer)
    connection.execute("""
        INSERT INTO vehicle_fuel(expense_id,volume_ml,odometer_m,full_tank) VALUES (?,?,?,?)
        ON CONFLICT(expense_id) DO UPDATE SET
            volume_ml=excluded.volume_ml,odometer_m=excluded.odometer_m,full_tank=excluded.full_tank
    """, (eid, volume, odometer, int(details['full_tank'])))


def check_reading(connection, eid, expense, odometer):
    if expense['date'] > workspace_time.today().isoformat():
        tracking.fail('A fill-up cannot be in the future.')
    inconsistent = connection.execute("""
        SELECT 1 FROM vehicle_fuel f JOIN expenses e ON f.expense_id=e.id
        WHERE e.vehicle_id=? AND e.id<>? AND
        ((e.date<? AND f.odometer_m>?) OR (e.date>? AND f.odometer_m<?))
    """, (expense['vehicle_id'], eid, expense['date'], odometer, expense['date'], odometer)).fetchone()
    if inconsistent:
        tracking.fail('Fuel odometer readings must increase over time. Check the date and reading.')


def fuel_economy(fuel, start, end):
    anchor = None
    volume = metres = pending_ml = 0
    for row in fuel:
        if row['volume_ml'] is None:
            # A known fuel expense without a volume makes this interval incomplete.
            anchor = None
            pending_ml = 0
            continue
        pending_ml += row['volume_ml']
        if not row['full_tank']:
            continue
        if anchor and start <= anchor['date'] <= row['date'] <= end and row['odometer_m'] > anchor['odometer_m']:
            volume += pending_ml
            metres += row['odometer_m'] - anchor['odometer_m']
        anchor, pending_ml = row, 0
    return (round(volume * 100 / metres, 2) if metres else None), metres


def report(vid, start, end):
    costs = tracking.rows("""
        SELECT e.id,e.date,e.merchant,e.amount_cents,e.receipt_id,e.reimbursed,
            CASE WHEN f.expense_id IS NOT NULL THEN 'fuel' ELSE COALESCE(c.kind,'running') END AS kind,
            f.volume_ml,f.odometer_m,f.full_tank
        FROM expenses e LEFT JOIN vehicle_fuel f ON f.expense_id=e.id
        LEFT JOIN vehicle_cost_details c ON c.expense_id=e.id
        WHERE e.vehicle_id=? AND e.date BETWEEN ? AND ?
          AND e.trip_id IS NULL AND e.meal='' AND e.category<>'Meals'
        ORDER BY e.date,e.id
    """, (vid, start, end))
    fuel = [row for row in costs if row['kind'] == 'fuel' and row['amount_cents'] > 0]
    fuel.sort(key=lambda row: (row['date'], row['odometer_m'] if row['odometer_m'] is not None else -1, row['id']))
    for row in fuel:
        row['price_per_litre'] = round(row['amount_cents'] * 10 / row['volume_ml'], 3) if row['volume_ml'] else None

    included = [row for row in costs if not row['reimbursed'] and row['kind'] not in EXCLUDED_KINDS]
    amounts = {}
    for row in included:
        amounts[row['kind']] = amounts.get(row['kind'], 0) + row['amount_cents']

    readings = [(row['date'], row['odometer_m']) for row in fuel if row['odometer_m'] is not None]
    zone = workspace_time.zone()
    for record in tracking.rows('SELECT recorded_at,reading_m FROM vehicle_odometer WHERE vehicle_id=?', (vid,)):
        day = datetime.fromtimestamp(record['recorded_at'], zone).date().isoformat()
        if start <= day <= end:
            readings.append((day, record['reading_m']))
    readings.sort()
    distance = 0
    measured = None
    per_km = None
    if len(readings) >= 2 and readings[-1][1] > readings[0][1]:
        first, last = readings[0][0], readings[-1][0]
        distance = readings[-1][1] - readings[0][1]
        measured = {'from': first, 'to': last}
        measured_cents = sum(row['amount_cents'] for row in included if first <= row['date'] <= last)
        per_km = round(measured_cents * 1000 / distance, 2)

    economy, economy_m = fuel_economy(fuel, start, end)
    return dict(start=start, end=end, costs=costs[::-1], fuel=fuel[::-1],
                running_cents=sum(amounts.values()), fuel_cents=amounts.get('fuel', 0),
                breakdown=amounts, distance_m=distance, measured=measured,
                cents_per_km=per_km, litres_per_100_km=economy, economy_distance_m=economy_m)


def requested_report(vid):
    tracking.db().execute('BEGIN')
    tracking.vehicle(vid)
    today = workspace_time.today()
    start = tracking.day(request.args.get('from') or (today - timedelta(days=29)).isoformat())
    end = tracking.day(request.args.get('to') or today.isoformat())
    if end < start:
        tracking.fail('To date must be on or after From date.')
    return report(vid, start, end)


@tracking.bp.get('/vehicles/<int:vid>/running-costs')
@tracking.access
def running_costs(vid):
    return jsonify(requested_report(vid))


@tracking.bp.get('/vehicles/<int:vid>/running-costs.csv')
@tracking.access
def running_costs_csv(vid):
    result = requested_report(vid)
    fuel = {row['id']: row for row in result['fuel']}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Merchant', 'Type', 'Amount AUD', 'Reimbursed', 'Included in running costs',
                     'Litres', 'Odometer km', 'AUD per litre', 'Full tank', 'Expense ID'])
    for row in result['costs']:
        item = fuel.get(row['id'], {})
        merchant = row['merchant']
        if merchant.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
            merchant = "'" + merchant
        writer.writerow([
            row['date'], merchant, row['kind'], f"{row['amount_cents']/100:.2f}",
            'Yes' if row['reimbursed'] else 'No',
            'Yes' if not row['reimbursed'] and row['kind'] not in EXCLUDED_KINDS else 'No',
            f"{item['volume_ml']/1000:.3f}" if item.get('volume_ml') is not None else '',
            f"{item['odometer_m']/1000:.3f}" if item.get('odometer_m') is not None else '',
            item.get('price_per_litre'),
            ('Yes' if item['full_tank'] else 'No') if item.get('full_tank') is not None else '',
            row['id'],
        ])
    return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv',
                     as_attachment=True, download_name=f"vehicle-running-costs-{result['start']}-{result['end']}.csv")
