"""Client statements with a dated ledger, PDF attachment and explicit email preview."""
import hashlib
import io
import json
import secrets
from datetime import datetime, timedelta, timezone

from billing import bp, owner, reader


def statement_data(cid, args):
    from billing import business, day, fail, local_today, one, rows
    client = one('SELECT * FROM billing_clients WHERE id=?', (cid,))
    if not client:
        fail('Client not found.', 404)
    client.pop('notes', None)
    mode = args.get('mode', 'all')
    if mode not in ('all', 'outstanding'):
        fail('Choose all invoices and payments or outstanding invoices.')
    today = local_today()
    year = int(today[:4]) - (int(today[5:7]) < 7)
    start = day(args.get('start') or f'{year}-07-01') if mode == 'all' else None
    end = day(args.get('end') or today) if mode == 'all' else today
    if end > today or (start and start > end):
        fail('Choose a statement period ending no later than today, with the start before the end.')
    documents = rows("SELECT id,number,issue_date,due_date,total_cents FROM billing_documents WHERE client_id=? AND kind='invoice' AND state='issued' AND issue_date<=? ORDER BY issue_date,id", (cid, end))
    entries, opening, charges, received = [], 0, 0, 0
    for doc in documents:
        payments = rows('SELECT id,date,reference,amount_cents FROM billing_payments WHERE document_id=? AND reversed_at IS NULL AND date<=? ORDER BY date,id', (doc['id'], end))
        paid = sum(p['amount_cents'] for p in payments)
        if mode == 'outstanding':
            balance = doc['total_cents'] - paid
            if balance > 0:
                entries.append(dict(date=doc['issue_date'], number=doc['number'], due_date=doc['due_date'],
                                    amount_cents=doc['total_cents'], paid_cents=paid, balance_cents=balance))
                charges += doc['total_cents']
                received += paid
            continue
        if doc['issue_date'] < start:
            opening += doc['total_cents']
        else:
            charges += doc['total_cents']
            entries.append(dict(date=doc['issue_date'], number=doc['number'], description='Invoice',
                                debit_cents=doc['total_cents'], credit_cents=0, order=[0, doc['id']]))
        for payment in payments:
            if payment['date'] < start:
                opening -= payment['amount_cents']
            else:
                received += payment['amount_cents']
                entries.append(dict(date=payment['date'], number=doc['number'], description='Payment' + (' - ' + payment['reference'] if payment['reference'] else ''),
                                    debit_cents=0, credit_cents=payment['amount_cents'], order=[1, payment['id']]))
    if mode == 'all':
        entries.sort(key=lambda row: (row['date'], row['order']))
        running = opening
        for row in entries:
            running += row['debit_cents'] - row['credit_cents']
            row['balance_cents'] = running
            del row['order']
    result = dict(client=client, business=business(), mode=mode, start=start, end=end, rows=entries,
                  opening_cents=opening, invoice_cents=charges, payment_cents=received,
                  closing_cents=opening + charges - received)
    result['version'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def statement_filename(statement):
    return f"statement-{statement['client']['id']}-{statement['mode']}-{statement['end']}.pdf"


@bp.get('/clients/<int:cid>/statement')
@reader
def view_statement(cid):
    from billing import jsonify, request
    return jsonify(statement_data(cid, request.args))


@bp.get('/clients/<int:cid>/statement/pdf')
@reader
def download_statement(cid):
    from billing import request, send_file
    from billing_core import pdf_statement
    statement = statement_data(cid, request.args)
    return send_file(io.BytesIO(pdf_statement(statement)), mimetype='application/pdf', as_attachment=True,
                     download_name=statement_filename(statement))


@bp.get('/clients/<int:cid>/statement/email-draft')
@owner
def statement_email_draft(cid):
    from billing import date_au, jsonify, mail_settings, request, template_text
    from billing_emails import email_templates, sender_full_name
    statement, config = statement_data(cid, request.args), mail_settings()
    client, seller = statement['client'], statement['business']
    templates = email_templates()
    template = templates['templates']['statement_' + statement['mode']]
    values = dict(client=client['contact'] or client['name'], business=seller['name'], full_name=sender_full_name(),
                  date_range=(date_au(statement['start']) + ' to ' + date_au(statement['end'])) if statement['start'] else '')
    return jsonify(recipient=client['email'], subject=template_text(template['subject'], values), body=template_text(template['body'], values),
                   signature_html=templates['signature_html'], from_email=config['from_email'], ready=bool(config['host'] and config['from_email']),
                   request_key=secrets.token_hex(24), version=statement['version'], filename=statement_filename(statement))


@bp.post('/clients/<int:cid>/statement/send')
@owner
def send_statement(cid):
    from billing import audit, body, db, deliver, email, fail, header, jsonify, mail_settings, now, one, request_key, txt
    from billing_core import pdf_statement
    from billing_emails import clean_signature, email_templates
    payload = body()
    key = request_key(payload.get('request_key'))
    recipient, subject, message = email(payload.get('recipient'), True), header(payload.get('subject')), txt(payload.get('body'), 20000)
    if not subject or not message:
        fail('Email subject and message are required.')
    config = mail_settings()
    if not (config['host'] and config['from_email']):
        fail('Configure your email account before sending.')
    db().execute('BEGIN IMMEDIATE')
    previous = one('SELECT * FROM billing_statement_outbox WHERE request_key=?', (key,))
    if previous:
        if previous['client_id'] != cid:
            fail('Request key already used.', 409)
        return jsonify(state=previous['state'], error=previous['error'])
    if one("SELECT id FROM billing_statement_outbox WHERE client_id=? AND state IN ('sending','unknown')", (cid,)):
        fail('A statement email is pending or uncertain. Check its delivery history before retrying.', 409)
    statement = statement_data(cid, payload)
    if payload.get('version') != statement['version']:
        fail('The client statement changed. Reload it before sending.', 409)
    attachment = pdf_statement(statement)
    signature = clean_signature(email_templates()['signature_html'])[0] if payload.get('include_signature', True) else ''
    oid = db().execute("INSERT INTO billing_statement_outbox(client_id,recipient,subject,body,signature_html,state,request_key,created_at,snapshot) VALUES (?,?,?,?,?,'sending',?,?,?)",
                       (cid, recipient, subject, message, signature, key, now(), json.dumps(statement))).lastrowid
    audit('statement email queued', cid)
    db().commit()
    state, error = deliver(recipient, subject, message, attachment, statement_filename(statement), signature_html=signature)
    db().execute('UPDATE billing_statement_outbox SET state=?,error=? WHERE id=?', (state, error, oid))
    audit('statement email ' + state, cid)
    db().commit()
    return jsonify(state=state, error=error)


@bp.get('/clients/<int:cid>/statement-emails')
@owner
def statement_history(cid):
    from billing import jsonify, rows
    return jsonify(rows('SELECT id,recipient,subject,state,error,created_at FROM billing_statement_outbox WHERE client_id=? ORDER BY id DESC', (cid,)))


@bp.post('/statement-emails/<int:oid>/resolve')
@owner
def resolve_statement_email(oid):
    from billing import audit, body, db, fail, jsonify, one
    state = body().get('state')
    if state not in ('sent', 'failed'):
        fail('Choose confirmed sent or confirmed not sent.')
    db().execute('BEGIN IMMEDIATE')
    outgoing = one('SELECT * FROM billing_statement_outbox WHERE id=?', (oid,))
    if not outgoing or outgoing['state'] not in ('unknown', 'sending'):
        fail('This email does not need reconciliation.', 409)
    if outgoing['state'] == 'sending' and datetime.fromisoformat(outgoing['created_at']) > datetime.now(timezone.utc) - timedelta(minutes=5):
        fail('Delivery may still be running. Wait five minutes before checking this record.', 409)
    db().execute('UPDATE billing_statement_outbox SET state=?,error=? WHERE id=?', (state, 'Delivery status manually confirmed by owner.', oid))
    audit('statement email reconciled: ' + state, oid)
    db().commit()
    return jsonify(ok=True)
