"""Workspace calendar dates are independent of the host/container timezone."""
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

DEFAULT = 'Australia/Brisbane'


@lru_cache(maxsize=1)
def choices():
    return sorted(available_timezones() - {'localtime', 'posixrules'})


def validate(value):
    from app import fail
    if not isinstance(value, str) or value not in choices():
        fail('Choose a valid timezone, for example Australia/Brisbane or Europe/London.')
    return value


def name():
    from flask import has_app_context
    if not has_app_context():
        return DEFAULT
    from billing import settings
    return settings('workspace', {'timezone': DEFAULT})['timezone']


def display_name():
    from billing import settings
    return settings('workspace', {}).get('name', '')


def zone():
    return ZoneInfo(name())


def today():
    return datetime.now(zone()).date()


def local_timestamp(value, occurrence=None):
    """Reject nonexistent DST times; explicitly resolve repeated clock times."""
    from app import fail
    try:
        naive = datetime.strptime(value, '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        fail('Enter a valid date and time.')
    candidates = sorted({naive.replace(tzinfo=zone(), fold=fold).timestamp() for fold in (0, 1)
                         if naive.replace(tzinfo=zone(), fold=fold).astimezone(timezone.utc).astimezone(zone()).replace(tzinfo=None) == naive})
    if not candidates:
        fail('This local time does not exist because the clocks move forward. Choose another time.')
    if len(candidates) > 1 and occurrence not in ('first', 'second'):
        fail('This local time occurs twice because the clocks move back. Choose the first or second occurrence.')
    return candidates[-1] if occurrence == 'second' else candidates[0]


def register(app, auth):
    from flask import jsonify, request
    from app import audit, db, fail
    from billing import settings, save_settings

    @app.get('/api/timezones')
    def timezones():
        return jsonify(timezones=choices())

    @app.route('/api/workspace/settings', methods=['GET', 'PUT'])
    @auth('owner')
    def workspace_settings():
        if request.method == 'PUT':
            data = request.get_json() or {}
            if not isinstance(data, dict):
                fail('Enter valid workspace settings.')
            value = validate(data.get('timezone'))
            label = data.get('name')
            if label is not None and (not isinstance(label, str) or len(label.strip()) > 100):
                fail('Use up to 100 characters for the workspace name.')
            db().execute('BEGIN IMMEDIATE')
            workspace = {**settings('workspace', {}), 'timezone': value}
            if label is not None:
                workspace['name'] = label.strip()
            save_settings('workspace', workspace)
            audit('workspace timezone changed to '+value, 'workspace'); db().commit()
        return jsonify(timezone=name(), name=display_name())
