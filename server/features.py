"""Per-login interface preferences. These never alter permissions or records."""
import json
from flask import g, request, jsonify

DEFAULTS = dict(employment=True, business=True, trips=True, vehicles=True, banks=True, tax=True)

def preferences():
    if not g.user:
        return DEFAULTS.copy()
    row = one('SELECT data FROM feature_preferences WHERE user_id=?', (g.user['id'],))
    result = {**DEFAULTS, **(json.loads(row['data']) if row else {})}
    if g.user['role'] == 'employee':
        result.update(employment=False, business=True, banks=False, tax=False)
    return result

def register(app, **deps):
    globals().update(deps)

    @app.route('/api/features', methods=['GET', 'PUT'])
    def feature_preferences():
        if not g.user: fail('Please sign in.', 401)
        if request.method == 'PUT':
            data = request.get_json()
            if not isinstance(data, dict) or set(data) - set(DEFAULTS) or any(type(v) is not bool for v in data.values()):
                fail('Choose valid feature switches.')
            values = {**preferences(), **data}
            if not values['employment'] and not values['business']:
                fail('Keep employment or business tracking enabled.')
            if g.user['role'] == 'employee' and (not values['business'] or any(values[k] for k in ('employment','banks','tax'))):
                fail('These features are not available for employee accounts.', 403)
            db().execute('INSERT INTO feature_preferences(user_id,data) VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data', (g.user['id'], json.dumps(values)))
            db().commit()
        return jsonify(preferences())
