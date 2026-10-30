"""Reviewable links from the imported bank ledger to existing financial records."""
from flask import jsonify, request
from workflow_core import body, integer, preview, checked, now, write_access


def plan(data):
    from app import one, rows, fail, money, record_user_id
    import billing
    bank=one('SELECT b.*,a.enabled,a.available,a.local_account_id FROM bank_transactions b JOIN pocketsmith_accounts a ON a.id=b.feed_account_id WHERE b.id=?',(integer(data.get('bank_id'),'bank transaction',1),))
    if not bank or bank['currency']!='AUD' or bank['source_status']!='posted' or bank['is_transfer'] or bank['missing'] or bank['changed'] or not bank['enabled'] or not bank['available']:
        fail('Choose an unchanged, posted AUD transaction from an enabled bank account.')
    if bank['expense_id'] or bank['state']=='linked' or one('SELECT 1 FROM bank_reconciliations WHERE bank_id=?',(bank['id'],)):
        fail('This bank transaction is already linked. Undo that link first.',409)
    kind=data.get('kind');values=data.get('allocations')
    if kind not in ('invoice','salary','expense','refund') or not isinstance(values,list) or not 1<=len(values)<=50:
        fail('Choose a match type and 1–50 allocations.')
    if (bank['amount_cents']<0)!=(kind=='expense'): fail('Only purchases match debits. Invoices, pay and refunds match credits.')
    if kind in ('salary','refund') and len(values)!=1: fail('Choose one payslip or original purchase.')
    allocations=[];seen=set()
    for item in values:
        if not isinstance(item,dict): fail('Invalid allocation.')
        ident=integer(item.get('id'),'record ID',1);amount=money(item.get('amount'))
        if ident in seen or amount<=0: fail('Use each record once with a positive allocation.')
        seen.add(ident)
        if kind=='invoice':
            record=billing.document(ident)
            if record['kind']!='invoice' or record['state'] not in ('issued','sent') or amount>record['balance_cents']:
                fail('Choose an issued invoice and do not exceed its unpaid balance.')
            if bank['date']<record['issue_date']: fail('Payment predates this invoice. Check the document and bank date.')
        elif kind=='salary':
            record=one('SELECT e.*,d.net_cents,d.version AS details_version FROM employment_income e JOIN income_details d ON d.income_id=e.id WHERE e.id=?',(ident,))
            if not record or record['record_kind']=='income_statement' or record['net_cents']!=amount or one('SELECT 1 FROM bank_reconciliations WHERE income_id=?',(ident,)):
                fail('Record this payment’s actual net pay before matching it; it must equal the deposit and not already be matched.')
        else:
            record=one('SELECT * FROM expenses WHERE id=? AND user_id=?',(ident,record_user_id()))
            if not record or record['amount_cents']<=0: fail('Choose a positive purchase in this workspace.')
            if kind=='expense':
                used=one("SELECT COALESCE(SUM(amount_cents),0) n FROM bank_reconciliations WHERE expense_id=? AND kind='expense'",(ident,))['n']
                if record['bank_match_excluded'] or one('SELECT 1 FROM bank_transactions WHERE expense_id=?',(ident,)) or used+amount>record['amount_cents']:
                    fail('This allocation exceeds the unmatched purchase balance or conflicts with its existing bank/cash choice.')
                if record['account_id'] and record['account_id']!=bank['local_account_id']: fail('The purchase uses a different payment account.')
                record['matched_cents']=used
            else:
                refunded=one("SELECT COALESCE(SUM(amount_cents),0) n FROM bank_reconciliations WHERE expense_id=? AND kind='refund'",(ident,))['n']
                if record['items_json']!='[]' or record['trip_id'] or record['vehicle_id'] or one('SELECT 1 FROM equipment_assets WHERE expense_id=?',(ident,)):
                    fail('For itemised, trip, vehicle or equipment purchases, enter and review the refund in Expenses first.')
                if refunded+amount>record['amount_cents']: fail('Refunds exceed the original purchase.')
                record['refunded_cents']=refunded
        allocations.append(dict(id=ident,amount_cents=amount,record=record))
    if sum(x['amount_cents'] for x in allocations)!=abs(bank['amount_cents']): fail('Allocations must exactly equal the bank transaction. Adjust the partial payment amounts.')
    return dict(bank=bank,kind=kind,allocations=allocations)


def register(app,auth):
    @app.get('/api/workflows/reconciliation', endpoint='reconciliation_choices')
    @auth('owner','tax_agent')
    def choices():
        from app import rows, record_user_id
        import billing
        return jsonify(banks=rows("SELECT b.* FROM bank_transactions b JOIN pocketsmith_accounts a ON a.id=b.feed_account_id WHERE a.enabled=1 AND a.available=1 AND b.currency='AUD' AND b.state='review' AND b.expense_id IS NULL AND b.changed=0 AND b.missing=0 AND b.source_status='posted' AND b.is_transfer=0 ORDER BY b.date DESC,b.id DESC LIMIT 500"),
                       invoices=[billing.hydrate(r) for r in rows("SELECT * FROM billing_documents WHERE kind='invoice' AND state='issued' ORDER BY issue_date DESC LIMIT 500")],
                       income=rows("SELECT e.*,d.net_cents FROM employment_income e LEFT JOIN income_details d ON d.income_id=e.id WHERE record_kind!='income_statement' AND NOT EXISTS(SELECT 1 FROM bank_reconciliations b WHERE b.income_id=e.id) ORDER BY date DESC LIMIT 500"),
                       expenses=rows('SELECT * FROM expenses WHERE user_id=? AND amount_cents>0 ORDER BY date DESC,id DESC LIMIT 1000',(record_user_id(),)),
                       links=rows('SELECT r.*,b.payee,b.date,b.changed,b.missing FROM bank_reconciliations r JOIN bank_transactions b ON b.id=r.bank_id ORDER BY r.id DESC LIMIT 300'))

    @app.post('/api/workflows/reconciliation/<action>', endpoint='reconciliation_reconcile')
    @auth('owner','tax_agent')
    def reconcile(action):
        from app import db, fail, audit, record_user_id
        write_access();d=body()
        if action not in ('preview','apply'): fail('Unknown reconciliation action.',404)
        if action=='apply': db().execute('BEGIN IMMEDIATE')
        result=plan(d)
        if action=='preview': return jsonify(**result,token=preview('reconciliation',result))
        checked(d.get('token'),'reconciliation',result)
        bank=result['bank'];kind=result['kind']
        for item in result['allocations']:
            invoice=income=expense=payment=refund=None
            if kind=='invoice':
                invoice=item['id']
                payment=db().execute('INSERT INTO billing_payments(document_id,date,amount_cents,reference,request_key,created_at) VALUES (?,?,?,?,?,?)',
                                     (invoice,bank['date'],item['amount_cents'],'Bank match: '+bank['payee'],'bank:'+str(bank['id'])+':'+str(invoice)+':'+now(),now())).lastrowid
                db().execute('UPDATE billing_documents SET version=version+1 WHERE id=?',(invoice,))
            elif kind=='salary': income=item['id']
            else:
                expense=item['id']
                if kind=='refund':
                    e=item['record']
                    refund=db().execute("INSERT INTO expenses(user_id,date,merchant,amount_cents,scope,category,percent,work_percent,business_percent,account_id,notes,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,'review')",
                                        (record_user_id(),bank['date'],bank['payee'],-item['amount_cents'],e['scope'],e['category'],e['percent'],e['work_percent'],e['business_percent'],bank['local_account_id'],'Refund of expense #'+str(expense))).lastrowid
            db().execute('INSERT INTO bank_reconciliations(bank_id,kind,amount_cents,income_id,invoice_id,payment_id,expense_id,refund_id,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                         (bank['id'],kind,item['amount_cents'],income,invoice,payment,expense,refund,now()))
        db().execute("UPDATE bank_transactions SET state='linked',version=version+1 WHERE id=?",(bank['id'],))
        audit('bank reconciliation applied',bank['id']);db().commit();return jsonify(ok=True)

    @app.post('/api/workflows/reconciliation/<int:bid>/undo', endpoint='reconciliation_undo')
    @auth('owner','tax_agent')
    def undo(bid):
        from app import db, rows, one, fail, audit
        write_access();d=body()
        reason=str(d.get('reason') or '').strip()[:500]
        if not reason: fail('Enter a reason for undoing this reconciliation.')
        db().execute('BEGIN IMMEDIATE');links=rows('SELECT * FROM bank_reconciliations WHERE bank_id=?',(bid,))
        if not links: fail('No reconciliation found.',404)
        for link in links:
            if link['refund_id'] and not d.get('keep_refund'):
                refund=one('SELECT * FROM expenses WHERE id=?',(link['refund_id'],))
                if refund and (refund['status']!='review' or refund['receipt_id'] or refund['items_json']!='[]' or refund['amount_cents']!=-link['amount_cents']):
                    fail('The refund was reviewed or edited. Choose to keep the refund expense when undoing this match.',409)
        db().execute('DELETE FROM bank_reconciliations WHERE bank_id=?',(bid,))
        for link in links:
            if link['payment_id']:
                db().execute('UPDATE billing_payments SET reversed_at=?,reversal_reason=? WHERE id=? AND reversed_at IS NULL',(now(),reason,link['payment_id']))
                db().execute('UPDATE billing_documents SET version=version+1 WHERE id=?',(link['invoice_id'],))
            if link['refund_id'] and not d.get('keep_refund'): db().execute('DELETE FROM expenses WHERE id=?',(link['refund_id'],))
        db().execute("UPDATE bank_transactions SET state='review',version=version+1 WHERE id=?",(bid,));audit('bank reconciliation undone',bid);db().commit();return jsonify(ok=True)
