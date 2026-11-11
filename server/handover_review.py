"""Version the recorded financial-year figures delivered to an adviser."""
import json
from flask import jsonify, request
from workflow_core import body, checked, digest, fiscal, preview, write_access


def figures(year, start, end):
    from app import one, rows
    if year in (2024,2025,2026,2027):
        from finance_routes import tax_forecast
        return tax_forecast(year).get_json()['recorded']
    from expense_core import allocations
    income=one('SELECT COALESCE(SUM(gross_cents),0) gross,COALESCE(SUM(withheld_cents),0) withheld FROM employment_income WHERE date BETWEEN ? AND ?',(start,end))
    expenses=[allocations(e) for e in rows("SELECT * FROM expenses WHERE date BETWEEN ? AND ? AND status='ready'",(start,end))]
    return dict(salary_cents=income['gross'],withheld_cents=income['withheld'],
                work_allocations_cents=sum(e[0] for e in expenses),business_allocations_cents=sum(e[1] for e in expenses))


def records(year,start,end):
    from app import rows
    registers = {
        'expenses': rows("SELECT * FROM expenses WHERE date BETWEEN ? AND ? AND scope!='personal'",(start,end)),
        'employment': rows('SELECT * FROM employment_income WHERE date BETWEEN ? AND ?',(start,end)),
        'invoice_payments': rows('SELECT * FROM billing_payments WHERE date BETWEEN ? AND ?',(start,end)),
        'documents': rows('SELECT id,title,version,sha256 FROM tax_documents WHERE year=?',(year,)),
        'home_office_costs': rows('SELECT h.* FROM home_office_costs h JOIN expenses e ON e.id=h.expense_id WHERE e.date BETWEEN ? AND ?',(start,end)),
    }
    return {name:{str(r.get('id',r.get('expense_id'))):dict(label=r.get('merchant',r.get('employer',r.get('title',''))),stamp=digest(r))
                  for r in entries} for name,entries in registers.items()}


def record_changes(old,current):
    changes=[]
    for register, entries in current.items():
        previous=old.get(register,{})
        for ident in sorted(entries.keys() | previous.keys()):
            before, after=previous.get(ident), entries.get(ident)
            if before==after:
                continue
            changes.append(dict(register=register,id=ident,label=(after or before)['label'],
                                change='added' if not before else 'removed' if not after else 'updated'))
    return changes


def state(year):
    from app import rows, record_user_id
    _,start,end=fiscal(year)
    history = rows('SELECT revision,created_at,note,figures FROM handover_revisions WHERE user_id=? AND year=? ORDER BY revision DESC',
                   (record_user_id(),year))
    last={}
    for entry in history:
        stored=json.loads(entry['figures'])
        entry['figures']=stored.get('amounts',stored)
        if not last:
            last=stored
    current = figures(year,start,end)
    source_records=records(year,start,end)
    saved = history[0]['figures'] if history else {}
    changes = [dict(key=k,before=saved.get(k,0),after=value) for k,value in current.items()
               if value!=saved.get(k,0)] if history else []
    updated=record_changes(last.get('records',{}),source_records) if history and 'records' in last else []
    snapshot=dict(amounts=current,records=source_records)
    return dict(year=year,revision=history[0]['revision'] if history else 0,current=current,
                history=history,changes=changes,record_changes=updated), snapshot


def register(app,auth):
    from app import audit, db, fail, record_user_id, textval

    @app.route('/api/workflows/handover/<int:year>/review', methods=['GET','POST'])
    @auth('owner','tax_agent')
    def handover_review(year):
        fiscal(year)
        if request.method=='GET':
            value,snapshot=state(year)
            return jsonify(**value,token=preview('annual handover', [value,snapshot]))
        write_access()
        d=body()
        note=textval(d.get('note'),500)
        if not note:
            fail('Record who reviewed the figures or why the handover is being revised.')
        db().execute('BEGIN IMMEDIATE')
        value,snapshot=state(year)
        checked(d.get('token'),'annual handover',[value,snapshot])
        if value['revision'] and not (value['changes'] or value['record_changes']):
            fail('The recorded figures match the saved handover.',409)
        revision=value['revision']+1
        db().execute('INSERT INTO handover_revisions(year,revision,user_id,note,figures) VALUES (?,?,?,?,?)',
                     (year,revision,record_user_id(),note,json.dumps(snapshot,sort_keys=True)))
        audit('annual handover figures confirmed',f'{year}:{revision}')
        db().commit()
        return jsonify(revision=revision)
