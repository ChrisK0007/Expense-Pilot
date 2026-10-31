"""Names can change without changing category identities or historical allocations."""
from flask import g, jsonify


def labels():
    from app import rows
    return {r['category']:r['label'] for r in rows('SELECT * FROM category_labels')}


def label(category):
    return labels().get(category,category)


def register(app,auth):
    @app.put('/api/categories/rename')
    @auth('owner')
    def rename():
        from app import db,fail,audit,category_names
        from workflow_core import body
        d=body();key=d.get('category');name=str(d.get('name') or '').strip()
        if not name or len(name)>80 or any(ord(c)<32 or ord(c)==127 for c in name): fail('Enter a category name of 1–80 characters.')
        db().execute('BEGIN IMMEDIATE');keys=category_names();names=labels()
        if key not in keys: fail('Category not found.',404)
        if d.get('previous')!=names.get(key,key): fail('The category was renamed elsewhere. Reload and try again.',409)
        # Reserve identities as well as current labels, avoiding ambiguous old mobile clients.
        if any(k!=key and name.casefold() in (k.casefold(),names.get(k,k).casefold()) for k in keys): fail('That category name is already used.',409)
        db().execute('INSERT INTO category_labels VALUES (?,?) ON CONFLICT(category) DO UPDATE SET label=excluded.label',(key,name))
        audit('expense category renamed',{'category':key,'before':names.get(key,key),'after':name});db().commit()
        return jsonify(labels=labels())
