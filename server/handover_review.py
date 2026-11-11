"""Version the recorded financial-year figures delivered to an adviser."""
import json
from flask import jsonify, request
from workflow_core import body, checked, fiscal, preview, write_access


def figures(year):
    from finance_routes import tax_forecast
    data = tax_forecast(year).get_json()
    return data['recorded']


def state(year):
    from app import rows, record_user_id
    history = rows('SELECT revision,created_at,note,figures FROM handover_revisions WHERE user_id=? AND year=? ORDER BY revision DESC',
                   (record_user_id(),year))
    for entry in history:
        entry['figures'] = json.loads(entry['figures'])
    current = figures(year)
    saved = history[0]['figures'] if history else {}
    changes = [dict(key=k,before=saved.get(k,0),after=value) for k,value in current.items()
               if value!=saved.get(k,0)] if history else []
    return dict(year=year,revision=history[0]['revision'] if history else 0,current=current,history=history,changes=changes)


def register(app,auth):
    from app import audit, db, fail, record_user_id, textval

    @app.route('/api/workflows/handover/<int:year>/review', methods=['GET','POST'])
    @auth('owner','tax_agent')
    def handover_review(year):
        fiscal(year)
        if request.method=='GET':
            value=state(year)
            return jsonify(**value,token=preview('annual handover',value))
        write_access()
        d=body()
        note=textval(d.get('note'),500)
        if not note:
            fail('Record who reviewed the figures or why the handover is being revised.')
        db().execute('BEGIN IMMEDIATE')
        value=state(year)
        checked(d.get('token'),'annual handover',value)
        if value['revision'] and not value['changes']:
            fail('The recorded figures match the saved handover.',409)
        revision=value['revision']+1
        db().execute('INSERT INTO handover_revisions(year,revision,user_id,note,figures) VALUES (?,?,?,?,?)',
                     (year,revision,record_user_id(),note,json.dumps(value['current'],sort_keys=True)))
        audit('annual handover figures confirmed',f'{year}:{revision}')
        db().commit()
        return jsonify(revision=revision)
