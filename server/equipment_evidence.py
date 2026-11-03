"""Versioned, owner-only evidence links. No purchase or deduction amounts are changed."""
import json
from flask import jsonify, request
from workflow_core import body, integer


def eligible_purchase(a, e):
    from app import one
    return bool(e and e['user_id']==a['user_id'] and e['amount_cents']==a['cost_cents'] and e['date']==a['acquired']
        and (e['work_percent'],e['business_percent'])==(a['work_percent'],a['business_percent'])
        and not (e['reimbursed'] or e['items_json']!='[]' or e['trip_id'] or e['meal'] or e['vehicle_id'] or e['category']=='Meals')
        and not one('SELECT 1 FROM home_office_costs WHERE expense_id=?',(e['id'],))
        and not one('SELECT 1 FROM equipment_assets WHERE expense_id=? AND id!=?',(e['id'],a['id'])))


def register(app, auth):
    @app.route('/api/workflows/equipment/<int:aid>/evidence', methods=['GET','PUT','DELETE'])
    @auth('owner')
    def evidence(aid):
        from app import db, one, rows, fail, record_user_id, audit
        if request.method!='GET': db().execute('BEGIN IMMEDIATE')
        a=one('SELECT * FROM equipment_assets WHERE id=? AND user_id=?',(aid,record_user_id()))
        if not a: fail('Equipment not found.',404)
        purchase=one('SELECT * FROM expenses WHERE id=?',(a['expense_id'],)) if a['expense_id'] else None
        rid=a['evidence_receipt_id'] or (purchase['receipt_id'] if purchase else None)
        if request.method=='GET':
            candidates=rows('SELECT * FROM expenses WHERE user_id=? AND date=? AND amount_cents=? ORDER BY id DESC',(a['user_id'],a['acquired'],a['cost_cents']))
            purchases=[dict(id=e['id'],merchant=e['merchant'],date=e['date'],amount_cents=e['amount_cents'],receipt_id=e['receipt_id']) for e in candidates if eligible_purchase(a,e)]
            originals=rows('''SELECT r.id,r.filename,e.id AS expense_id,e.merchant FROM receipts r
                LEFT JOIN expenses e ON e.receipt_id=r.id WHERE r.user_id=?
                AND NOT EXISTS(SELECT 1 FROM employment_income i WHERE i.receipt_id=r.id)
                AND NOT EXISTS(SELECT 1 FROM equipment_assets x WHERE x.evidence_receipt_id=r.id AND x.id!=?)
                ORDER BY r.rowid DESC''',(a['user_id'],aid))
            originals=[r for r in originals if not r['expense_id'] or any(e['id']==r['expense_id'] for e in purchases)]
            return jsonify(version=a['version'],receipt_id=rid,expense_id=a['expense_id'],receipts=originals,purchases=purchases)
        d=body()
        if d.get('version')!=a['version']: fail('This deduction changed. Reopen its receipt links.',409)
        if request.method=='DELETE':
            if not rid: fail('There is no receipt to unlink.',409)
            db().execute('UPDATE equipment_assets SET evidence_receipt_id=NULL WHERE id=?',(aid,))
            if purchase and purchase['receipt_id']: db().execute('UPDATE expenses SET receipt_id=NULL WHERE id=?',(purchase['id'],))
            action='equipment receipt unlinked'
        else:
            selected=d.get('receipt_id') or None;eid=d.get('expense_id') or None
            if not selected and not eid: fail('Choose a receipt or an existing purchase.')
            if selected:
                original=one('SELECT * FROM receipts WHERE id=? AND user_id=?',(selected,a['user_id']))
                if not original: fail('Receipt not found.',404)
                if one('SELECT 1 FROM employment_income WHERE receipt_id=?',(selected,)) or one('SELECT 1 FROM equipment_assets WHERE evidence_receipt_id=? AND id!=?',(selected,aid)):
                    fail('This receipt is already attached to another record.',409)
                filed=one('SELECT * FROM expenses WHERE receipt_id=?',(selected,))
                if filed:
                    if eid and integer(eid,'purchase',1)!=filed['id']: fail('The receipt belongs to a different purchase.',409)
                    eid=filed['id']
            target=one('SELECT * FROM expenses WHERE id=?',(integer(eid,'purchase',1),)) if eid else purchase
            if target:
                if not eligible_purchase(a,target): fail('The purchase must match this asset’s original cost, date and use, without another deduction treatment.',409)
                if purchase and purchase['id']!=target['id']: fail('This deduction is already linked to a different purchase.',409)
                new_rid=selected or rid or target['receipt_id']
                if rid and new_rid!=rid or target['receipt_id'] and new_rid!=target['receipt_id']:
                    fail('Unlink the existing receipt before choosing another.',409)
                # Move direct evidence onto the real purchase inside this transaction.
                db().execute('UPDATE equipment_assets SET evidence_receipt_id=NULL,expense_id=? WHERE id=?',(target['id'],aid))
                if new_rid: db().execute('UPDATE expenses SET receipt_id=? WHERE id=?',(new_rid,target['id']))
            else:
                if rid and rid!=selected: fail('Unlink the existing receipt before choosing another.',409)
                db().execute('UPDATE equipment_assets SET evidence_receipt_id=? WHERE id=?',(selected,aid))
            action='equipment evidence linked'
        db().execute('UPDATE equipment_assets SET version=version+1 WHERE id=?',(aid,))
        audit(action,json.dumps(dict(asset_id=aid,previous_receipt=rid,request=d)));db().commit()
        return jsonify(ok=True)
