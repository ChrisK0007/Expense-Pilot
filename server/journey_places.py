"""Private, versioned saved addresses, with retry receipts and deletion tombstones."""
import hashlib
import json
import math
import uuid
from flask import g, jsonify
import tracking as t


def identifier(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        t.fail('Use a valid saved-address reference.')


def public(row):
    return dict(id=row['id'], version=row['version'], mutation_id=row['mutation_id'],
                deleted=bool(row['deleted']), name=row['name'], address=row['address'],
                point=dict(latitude=row['latitude'], longitude=row['longitude']))


def register():
    @t.bp.get('/journey-places')
    @t.access
    def list_places():
        # Never use record_user_id(): a tax agent must not inherit an owner's
        # private home/work addresses merely by having access to their accounts.
        return jsonify([public(r) for r in t.rows(
            'SELECT * FROM journey_places WHERE user_id=? ORDER BY id', (g.user['id'],))])

    @t.bp.put('/journey-places/<place_id>')
    @t.access
    def save_place(place_id):
        place_id = identifier(place_id)
        d = t.body()
        mutation = identifier(d.get('mutation_id'))
        expected = d.get('expected_version')
        if type(expected) is not int or not 0 <= expected < 2**53:
            t.fail('Use a valid saved-address version.')
        if type(d.get('deleted')) is not bool:
            t.fail('Specify whether this address is deleted.')
        deleted = d['deleted']
        name, address, lat, lon = '', '', 0.0, 0.0
        if not deleted:
            name, address = d.get('name'), d.get('address')
            if not isinstance(name, str) or not isinstance(address, str):
                t.fail('Enter a name and address.')
            name, address = name.strip(), address.strip()
            if not 1 <= len(name) <= 60 or not 1 <= len(address) <= 200 or any(ord(c) < 32 for c in name + address):
                t.fail('Use a name of 1–60 characters and an address of 1–200 characters.')
            point = d.get('point')
            if not isinstance(point, dict):
                t.fail('Choose a valid address location.')
            lat, lon = point.get('latitude'), point.get('longitude')
            if (type(lat) not in (int, float) or type(lon) not in (int, float)
                    or not math.isfinite(lat) or not math.isfinite(lon)
                    or not -90 <= lat <= 90 or not -180 <= lon <= 180):
                t.fail('Choose a valid address location.')
        fingerprint = hashlib.sha256(json.dumps([place_id, expected, deleted, name, address, lat, lon],
                                                separators=(',', ':')).encode()).hexdigest()
        uid = g.user['id']
        t.db().execute('BEGIN IMMEDIATE')
        previous = t.one('SELECT * FROM journey_place_mutations WHERE user_id=? AND mutation_id=?', (uid, mutation))
        if previous:
            if previous['fingerprint'] != fingerprint:
                t.fail('This address change reference was already used. Refresh and try again.', 409)
            return jsonify(json.loads(previous['response']))
        current = t.one('SELECT * FROM journey_places WHERE user_id=? AND id=?', (uid, place_id))
        if expected != (current['version'] if current else 0):
            t.fail('This address changed on another device. Choose which version to keep.', 409)
        if not deleted and (not current or current['deleted']):
            count = t.one('SELECT COUNT(*) AS n FROM journey_places WHERE user_id=? AND deleted=0', (uid,))['n']
            if count >= 100:
                t.fail('Save no more than 100 addresses.')
        t.db().execute('''INSERT INTO journey_places VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id,id) DO UPDATE SET version=excluded.version,mutation_id=excluded.mutation_id,
            deleted=excluded.deleted,name=excluded.name,address=excluded.address,
            latitude=excluded.latitude,longitude=excluded.longitude''',
            (uid, place_id, expected + 1, mutation, int(deleted), name, address, lat, lon))
        result = public(t.one('SELECT * FROM journey_places WHERE user_id=? AND id=?', (uid, place_id)))
        t.db().execute('INSERT INTO journey_place_mutations VALUES (?,?,?,?)',
                       (uid, mutation, fingerprint, json.dumps(result)))
        t.audit('saved address deleted' if deleted else 'saved address updated', place_id)
        t.db().commit()
        return jsonify(result)
