"""Mileage report estimates keep reimbursements separate from deduction methods."""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

CAP_METRES = Decimal(5_000_000)


def financial_year(day):
    value = date.fromisoformat(day)
    return value.year - (value.month < 7)


def allocated(journey):
    return Decimal(journey['distance_m']) * journey['percent'] / 100 if journey['scope'] in ('work', 'business') else Decimal(0)


def capped_report_metres(journeys, start, end, scope):
    """Consume the car's shared FY cap in trip order, even for filtered reports."""
    remaining = CAP_METRES
    total = Decimal(0)
    for journey in journeys:
        used = min(remaining, allocated(journey))
        remaining -= used
        if start <= journey['date'] <= end and scope in ('all', journey['scope']):
            total += used
    return total


def logbook_use(readings, journeys, start, end, zone, *, require_end=False):
    """Use actual odometer readings at the boundaries of a recorded period."""
    day = lambda r: datetime.fromtimestamp(r['recorded_at'], zone).date().isoformat()
    opening = [r for r in readings if day(r) == start]
    closing = [r for r in readings if start < day(r) <= end and (not require_end or day(r) == end)]
    if not opening or not closing:
        return None
    first, last = opening[0], closing[-1]
    final_day = day(last)
    duration = (date.fromisoformat(final_day) - date.fromisoformat(start)).days + 1
    total = last['reading_m'] - first['reading_m']
    if duration < 84 or total <= 0:
        return None
    used = {'work': Decimal(0), 'business': Decimal(0)}
    recorded = 0
    for journey in journeys:
        if not start <= journey['date'] <= final_day:
            continue
        began, finished = journey['started_at'], journey['ended_at']
        if began is None or finished is None:
            if journey['date'] in (start, final_day):
                return None  # An untimed boundary trip cannot be placed safely.
        else:
            if finished <= first['recorded_at'] or began >= last['recorded_at']:
                continue
            if began < first['recorded_at'] or finished > last['recorded_at']:
                return None
        recorded += journey['distance_m']
        if journey['scope'] in used:
            used[journey['scope']] += allocated(journey)
    if not recorded or recorded > total or sum(used.values()) > total:
        return None
    percentages = {key + '_percent': int(value * 100 / total) for key, value in used.items()}
    return dict(**percentages, start=start, end=final_day, days=duration, total_metres=total,
                recorded_metres=recorded, source='odometer')


def financial_year_logbook(readings, journeys, start, end, zone, *, closed):
    """Prefer year boundaries, then suggest the recorded period within the year."""
    use = logbook_use(readings, journeys, start, end, zone, require_end=closed)
    if use:
        return use
    days = (datetime.fromtimestamp(reading['recorded_at'], zone).date().isoformat() for reading in readings)
    first_day = next((day for day in days if start <= day <= end), None)
    if first_day:
        return logbook_use(readings, journeys, first_day, end, zone)


def estimate(vid, start, end, scope):
    from planning import RATES, comparison
    from tracking import rows
    year = financial_year(start)
    if year != financial_year(end) or year not in RATES:
        return dict(available=False, reason='Choose dates within one supported financial year.')
    comparison_data = comparison(vid, year)
    journeys = rows('SELECT * FROM vehicle_journeys WHERE vehicle_id=? AND date BETWEEN ? AND ? ORDER BY date,COALESCE(started_at,0),id',
                    (vid, comparison_data['start'], comparison_data['end']))
    cpk_metres = capped_report_metres(journeys, start, end, scope)
    cpk_amount = int((cpk_metres * RATES[year] / 1000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    settings = comparison_data['settings']
    saved = settings['version'] and comparison_data['logbook_days'] >= 84
    use = dict(work_percent=settings['work_percent'], business_percent=settings['business_percent'],
               start=settings['logbook_start'], end=settings['logbook_end'], source='saved') if saved else comparison_data['suggested_logbook']
    base = comparison_data['cost_base_cents']
    if use:
        percentage = sum(use[s + '_percent'] for s in ('work', 'business') if scope in ('all', s))
        use = dict(use, amount_cents=int((Decimal(base) * percentage / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)))
    return dict(available=True, year=year, rate_cents=RATES[year], cap_km=int(CAP_METRES / 1000),
                cents_metres=float(cpk_metres), cents_amount=cpk_amount, logbook=use, cost_base_cents=base)
