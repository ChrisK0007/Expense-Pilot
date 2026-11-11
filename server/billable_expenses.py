"""Link a business expense to a client and reserve it on one invoice."""
from flask import jsonify, request
from expense_core import allocations
from workflow_core import body, integer, write_access


def available(e):
    return e['status']=='ready' and not e['reimbursed'] and allocations(e)[1]>0


def validate_links(values, did=None):
    from app import fail, one
    linked=[line['source_expense_id'] for line in values['lines'] if line.get('source_expense_id')]
    if not linked:
        return linked
    if values['kind']!='invoice' or len(set(linked))!=len(linked):
        fail('A billable expense can appear only once on an invoice.')
    for eid in linked:
        entry=one('''SELECT e.*,b.client_id,b.document_id FROM billable_expenses b
                     JOIN expenses e ON e.id=b.expense_id WHERE b.expense_id=?''',(eid,))
        if not entry or entry['client_id']!=values['client_id'] or entry['document_id'] not in (None,did):
            fail('A linked expense belongs to another client or invoice. Review the invoice lines.',409)
        if entry['document_id'] is None and not available(entry):
            fail('A linked expense is no longer eligible to bill. Review the expense first.',409)
    return linked


def save_links(did, linked):
    from app import db
    reserved = {row[0] for row in db().execute('SELECT expense_id FROM billable_expenses WHERE document_id=?',(did,))}
    for eid in reserved-set(linked):
        db().execute('UPDATE billable_expenses SET document_id=NULL WHERE expense_id=?',(eid,))
    for eid in set(linked)-reserved:
        db().execute('UPDATE billable_expenses SET document_id=? WHERE expense_id=?',(did,eid))


def register(app,auth):
    from app import audit, db, fail, one, rows, record_user_id

    @app.get('/api/billing/billable-expenses')
    @auth('owner','tax_agent')
    def unbilled_expenses():
        client=integer(request.args.get('client_id'),'client',1)
        data=rows('''SELECT e.*,b.client_id FROM billable_expenses b JOIN expenses e ON e.id=b.expense_id
                     WHERE e.user_id=? AND b.client_id=? AND b.document_id IS NULL ORDER BY e.date DESC,e.id DESC''',
                  (record_user_id(),client))
        return jsonify([dict(id=e['id'],date=e['date'],merchant=e['merchant'],amount_cents=allocations(e)[1]) for e in data if available(e)])

    @app.route('/api/expenses/<int:eid>/billable',methods=['GET','PUT'])
    @auth('owner','tax_agent')
    def expense_billable(eid):
        if request.method=='PUT':
            write_access()
            db().execute('BEGIN IMMEDIATE')
        e=one('SELECT * FROM expenses WHERE id=? AND user_id=?',(eid,record_user_id()))
        if not e:
            fail('Expense not found.',404)
        current=one('SELECT b.*,d.number FROM billable_expenses b LEFT JOIN billing_documents d ON d.id=b.document_id WHERE b.expense_id=?',(eid,))
        if request.method=='GET':
            return jsonify(available=available(e),link=current,
                           clients=rows('SELECT id,name FROM billing_clients WHERE archived=0 ORDER BY name,id'))
        client=body().get('client_id')
        if current and current['document_id'] is not None:
            fail('Remove the link from the draft invoice or void the issued invoice first.',409)
        if client is None:
            db().execute('DELETE FROM billable_expenses WHERE expense_id=?',(eid,))
        else:
            client=integer(client,'client',1)
            if not available(e) or not one('SELECT 1 FROM billing_clients WHERE id=? AND archived=0',(client,)):
                fail('Choose a reviewed business expense and an active client.')
            db().execute('''INSERT INTO billable_expenses(expense_id,client_id) VALUES (?,?)
                            ON CONFLICT(expense_id) DO UPDATE SET client_id=excluded.client_id''',(eid,client))
        audit('billable expense updated',eid)
        db().commit()
        return jsonify(ok=True)
