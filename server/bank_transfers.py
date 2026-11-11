"""Pair opposite posted ledger entries without creating income or expenses."""
from flask import jsonify
from workflow_core import body, integer, write_access

AVAILABLE = """b.currency='AUD' AND b.source_status='posted' AND b.missing=0 AND b.changed=0
    AND b.expense_id IS NULL AND b.state IN ('review','ignored') AND b.amount_cents!=0
    AND a.enabled=1 AND a.available=1
    AND NOT EXISTS(SELECT 1 FROM bank_reconciliations r WHERE r.bank_id=b.id)
    AND NOT EXISTS(SELECT 1 FROM bank_transfer_pairs p WHERE p.debit_id=b.id OR p.credit_id=b.id)"""
SELECT = 'SELECT b.id,b.date,b.payee,b.amount_cents,b.version,b.state,b.feed_account_id,a.name AS account_name FROM bank_transactions b JOIN pocketsmith_accounts a ON a.id=b.feed_account_id '


def register(app, auth):
    from app import audit, db, fail, one, rows

    @app.get('/api/bank-transfers')
    @auth('owner','tax_agent')
    def transfer_list():
        candidates=rows(SELECT+'WHERE '+AVAILABLE+' ORDER BY b.date DESC,b.id DESC LIMIT 500')
        pairs=rows("""SELECT p.id,d.date AS debit_date,c.date AS credit_date,d.payee AS debit_payee,c.payee AS credit_payee,
                          da.name AS debit_account,ca.name AS credit_account,-d.amount_cents AS amount_cents,
                          d.changed OR c.changed OR d.missing OR c.missing AS needs_review
                       FROM bank_transfer_pairs p JOIN bank_transactions d ON d.id=p.debit_id
                       JOIN bank_transactions c ON c.id=p.credit_id
                       JOIN pocketsmith_accounts da ON da.id=d.feed_account_id
                       JOIN pocketsmith_accounts ca ON ca.id=c.feed_account_id
                       ORDER BY d.date DESC,p.id DESC LIMIT 200""")
        return jsonify(candidates=candidates,pairs=pairs)

    @app.post('/api/bank-transfers')
    @auth('owner','tax_agent')
    def transfer_pair():
        write_access()
        d=body()
        debit_id=integer(d.get('debit_id'),'debit',1)
        credit_id=integer(d.get('credit_id'),'credit',1)
        db().execute('BEGIN IMMEDIATE')
        debit=one(SELECT+'WHERE b.id=? AND '+AVAILABLE,(debit_id,))
        credit=one(SELECT+'WHERE b.id=? AND '+AVAILABLE,(credit_id,))
        if not debit or not credit or debit['version']!=d.get('debit_version') or credit['version']!=d.get('credit_version'):
            fail('A transaction changed or was linked. Refresh before pairing it.',409)
        if debit['amount_cents']>=0 or debit['amount_cents']!=-credit['amount_cents'] or debit['feed_account_id']==credit['feed_account_id']:
            fail('Choose an equal AUD debit and credit from different accounts.')
        pair=db().execute('INSERT INTO bank_transfer_pairs(debit_id,credit_id,debit_state,credit_state) VALUES (?,?,?,?)',
                          (debit_id,credit_id,debit['state'],credit['state'])).lastrowid
        db().execute("UPDATE bank_transactions SET state='linked',version=version+1 WHERE id IN (?,?)",(debit_id,credit_id))
        audit('bank transfer paired',pair)
        db().commit()
        return jsonify(id=pair)

    @app.delete('/api/bank-transfers/<int:pid>')
    @auth('owner','tax_agent')
    def transfer_unpair(pid):
        write_access()
        db().execute('BEGIN IMMEDIATE')
        pair=one('SELECT * FROM bank_transfer_pairs WHERE id=?',(pid,))
        if not pair:
            fail('Transfer pair not found.',404)
        for side in ('debit','credit'):
            db().execute("""UPDATE bank_transactions SET state=CASE WHEN changed OR missing THEN 'review' ELSE ? END,
                            changed=0,version=version+1 WHERE id=?""",(pair[side+'_state'],pair[side+'_id']))
        db().execute('DELETE FROM bank_transfer_pairs WHERE id=?',(pid,))
        audit('bank transfer unpaired',pid)
        db().commit()
        return jsonify(ok=True)
