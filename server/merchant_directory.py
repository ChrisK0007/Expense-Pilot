"""Saved payee names and explicit aliases for expense entry and reporting."""
from unicodedata import normalize


def merchant_key(value):
    return ' '.join(normalize('NFKC', str(value or '')).casefold().split())


def lookup(connection, user_id, name):
    return connection.execute(
        '''SELECT m.id, m.name FROM merchant_names n
           JOIN merchants m ON m.id=n.merchant_id AND m.user_id=n.user_id
           WHERE n.user_id=? AND n.match_key=?''',
        (user_id, merchant_key(name))
    ).fetchone()


def remember(connection, user_id, name):
    key = merchant_key(name)
    if not key:
        return name
    match = lookup(connection, user_id, name)
    if match:
        return match[1]
    merchant_id = connection.execute('INSERT INTO merchants(user_id,name) VALUES (?,?)',
                                     (user_id, name)).lastrowid
    connection.execute('INSERT INTO merchant_names(user_id,match_key,merchant_id,label) VALUES (?,?,?,?)',
                       (user_id, key, merchant_id, name))
    return name


def register(app, auth):
    from flask import g, jsonify, request
    from app import audit, db, fail, one, rows, textval

    @app.get('/api/merchants')
    @auth('owner')
    def merchant_list():
        uid = g.user['id']
        query = textval(request.args.get('q'), 200)
        key = merchant_key(query)
        match = lookup(db(), uid, query) if key else None
        items = rows(
            '''SELECT m.id,m.name FROM merchants m
               WHERE m.user_id=? AND EXISTS(
                   SELECT 1 FROM merchant_names n
                   WHERE n.user_id=m.user_id AND n.merchant_id=m.id AND instr(n.match_key,?)>0)
               ORDER BY m.name COLLATE NOCASE,m.id LIMIT 30''',
            (uid, key)
        ) if key else rows('SELECT id,name FROM merchants WHERE user_id=? ORDER BY name COLLATE NOCASE,id LIMIT 30', (uid,))
        return jsonify(items=items, match=dict(match) if match else None)

    @app.route('/api/merchants/<int:mid>', methods=['GET','PUT'])
    @auth('owner')
    def merchant_detail(mid):
        uid = g.user['id']
        if request.method == 'PUT':
            db().execute('BEGIN IMMEDIATE')
        merchant = one('SELECT id,name FROM merchants WHERE id=? AND user_id=?', (mid, uid))
        if not merchant:
            fail('Merchant not found.', 404)
        if request.method == 'PUT':
            data = request.get_json()
            if not isinstance(data, dict):
                fail('Enter a merchant name.')
            name = textval(data.get('name'), 200)
            alias = textval(data.get('alias'), 200)
            if not merchant_key(name):
                fail('Enter a merchant name.')
            existing = lookup(db(), uid, name)
            if existing and existing['id'] != mid:
                fail('That name already belongs to another merchant. Add it as an alternate name to group those records.', 409)
            if alias:
                previous = lookup(db(), uid, alias)
                if previous and previous['id'] != mid:
                    db().execute('UPDATE merchant_names SET merchant_id=? WHERE user_id=? AND merchant_id=?',
                                 (mid, uid, previous['id']))
                    db().execute('DELETE FROM merchants WHERE id=? AND user_id=?', (previous['id'], uid))
                db().execute('INSERT OR IGNORE INTO merchant_names(user_id,match_key,merchant_id,label) VALUES (?,?,?,?)',
                             (uid, merchant_key(alias), mid, alias))
            db().execute('UPDATE merchants SET name=? WHERE id=? AND user_id=?', (name, mid, uid))
            db().execute('''INSERT INTO merchant_names(user_id,match_key,merchant_id,label) VALUES (?,?,?,?)
                           ON CONFLICT(user_id,match_key) DO UPDATE SET label=excluded.label''',
                         (uid, merchant_key(name), mid, name))
            audit('merchant names updated', mid)
            db().commit()
            merchant['name'] = name
        aliases = rows('SELECT label FROM merchant_names WHERE user_id=? AND merchant_id=? AND match_key!=? ORDER BY label COLLATE NOCASE',
                       (uid, mid, merchant_key(merchant['name'])))
        return jsonify(**merchant, aliases=[entry['label'] for entry in aliases])
