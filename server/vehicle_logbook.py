"""Odometer estimates are derived from actual readings, never accumulated counters."""
import math
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import tracking as t
from flask import request, jsonify

BRISBANE = ZoneInfo('Australia/Brisbane')


def timestamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= time.time() + 86400:
        t.fail('Enter a valid reading or trip time.')
    return float(value)


def metadata(d, existing=None):
    start, end = d.get('started_at'), d.get('ended_at')
    if (start is None) != (end is None): t.fail('Provide both the trip start and finish times.')
    if start is not None:
        start, end = timestamp(start), timestamp(end)
        if start > end: t.fail('Trip finish must be after its start.')
        if not datetime.fromtimestamp(start, BRISBANE).date().isoformat() <= d.get('date','') <= datetime.fromtimestamp(end, BRISBANE).date().isoformat(): t.fail('Trip date must fall within its start and finish dates in Queensland.')
    # Old clients editing a trip's details retain timestamps unless they move its date.
    elif existing and existing['date'] == d.get('date'):
        start, end = existing['started_at'], existing['ended_at']
    ref = d.get('client_ref') or (existing or {}).get('client_ref')
    if ref is not None:
        try: ref = str(uuid.UUID(str(ref)))
        except (ValueError, AttributeError): t.fail('Invalid journey reference.')
    if existing and ref != existing['client_ref']: t.fail('A saved journey reference cannot be changed.',409)
    return start, end, ref


def estimate(reading, journeys):
    if not reading: return None, 0
    total, unknown = reading['reading_m'], 0
    reading_day = datetime.fromtimestamp(reading['recorded_at'], BRISBANE).date().isoformat()
    now=time.time(); today=datetime.fromtimestamp(now,BRISBANE).date().isoformat()
    for j in journeys:
        if j['date']>today or j['ended_at'] is not None and j['ended_at']>now: continue
        if j['ended_at'] is None:
            if j['date'] > reading_day: total += j['distance_m']
            elif j['date'] == reading_day: unknown += 1
        elif j['ended_at'] > reading['recorded_at']:
            if j['started_at'] < reading['recorded_at']: unknown += 1
            else: total += j['distance_m']
    return total, unknown


def logbook(vid):
    readings = t.rows('SELECT * FROM vehicle_odometer WHERE vehicle_id=? ORDER BY recorded_at,id', (vid,))
    journeys = t.rows('SELECT id,date,started_at,ended_at,client_ref,distance_m FROM vehicle_journeys WHERE vehicle_id=? ORDER BY date,id', (vid,))
    for i, reading in enumerate(readings):
        previous = readings[i-1] if i else None
        before, ambiguous = estimate(previous, [j for j in journeys if (j['ended_at'] is not None and j['ended_at'] <= reading['recorded_at']) or (j['ended_at'] is None and j['date'] < datetime.fromtimestamp(reading['recorded_at'], BRISBANE).date().isoformat())])
        reading['difference_m'] = reading['reading_m'] - before if before is not None else None
        reading['ambiguous_trips'] = ambiguous
    latest = readings[-1] if readings else None
    value, ambiguous = estimate(latest, journeys)
    return dict(readings=readings, journeys=journeys, estimate_m=value, ambiguous_trips=ambiguous)


def reading_values(d, vid, exclude=None):
    recorded = timestamp(d.get('recorded_at'))
    if recorded > time.time() + 60: t.fail('An actual odometer reading cannot be in the future.')
    metres = t.meters(d.get('reading'))
    if d.get('reading') in ('', None): t.fail('Enter the odometer reading.')
    others = t.rows('SELECT id,recorded_at,reading_m FROM vehicle_odometer WHERE vehicle_id=? AND id<>? ORDER BY recorded_at', (vid, exclude or -1))
    for other in others:
        if other['recorded_at'] == recorded: t.fail('A reading already exists at this time. Refresh the logbook.',409)
        if other['recorded_at'] < recorded and other['reading_m'] > metres or other['recorded_at'] > recorded and other['reading_m'] < metres:
            t.fail('Actual odometer readings must increase over time. Check the date and reading.')
    return recorded, metres, t.textval(d.get('notes'),1000)


def register():
    @t.bp.route('/vehicles/<int:vid>/odometer', methods=['GET','POST'])
    @t.access
    def odometer_api(vid):
        t.vehicle(vid)
        if request.method == 'POST':
            t.db().execute('BEGIN IMMEDIATE')
            values = reading_values(t.body(), vid)
            t.db().execute('INSERT INTO vehicle_odometer(vehicle_id,recorded_at,reading_m,notes) VALUES (?,?,?,?)', (vid,)+values)
            t.audit('vehicle odometer reading created',vid); t.db().commit()
        return jsonify(logbook(vid))

    @t.bp.route('/vehicles/<int:vid>/odometer/<int:rid>', methods=['PUT','DELETE'])
    @t.access
    def odometer_reading_api(vid,rid):
        t.vehicle(vid); d=t.body(); t.db().execute('BEGIN IMMEDIATE')
        old=t.one('SELECT * FROM vehicle_odometer WHERE id=? AND vehicle_id=?',(rid,vid))
        if not old: t.fail('Odometer reading not found.',404)
        if d.get('version') != old['version']: t.fail('This reading changed. Refresh before editing.',409)
        if request.method=='DELETE': t.db().execute('DELETE FROM vehicle_odometer WHERE id=?',(rid,))
        else:
            values=reading_values(d,vid,rid)
            t.db().execute('UPDATE vehicle_odometer SET recorded_at=?,reading_m=?,notes=?,version=version+1 WHERE id=?',values+(rid,))
        t.audit('vehicle odometer reading updated',rid); t.db().commit()
        return jsonify(logbook(vid))
