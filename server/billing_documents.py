"""Billing documents endpoints and services."""
from billing import bp, owner, reader

@bp.route('/documents', methods=['GET', 'POST'])
@reader
def documents():
    from billing import body, can_write, db, fail, hydrate, insert_document, jsonify, request, rows, validate_document
    if request.method == 'POST':
        if not can_write():
            fail('Read-only access.', 403)
        values = validate_document(body())
        db().execute('BEGIN IMMEDIATE')
        did = insert_document(values)
        db().commit()
        return jsonify(id=did)
    where = '1=1'
    results = [hydrate(r) for r in rows(f'SELECT * FROM billing_documents WHERE {where} ORDER BY issue_date DESC,id DESC')]
    for doc in results:
        doc['business'].pop('logo', None)
        doc['description'] = ' · '.join(line['description'] for line in doc['lines'])
        doc.pop('lines', None)
    return jsonify(results)


@bp.route('/documents/<int:did>', methods=['GET', 'PUT', 'DELETE'])
@reader
def document_detail(did):
    from billing import audit, body, can_write, db, document, fail, g, json, jsonify, one, request, revision, rows, validate_document
    if request.method == 'GET':
        doc = document(did)
        doc['payments'] = rows('SELECT * FROM billing_payments WHERE document_id=? ORDER BY id', (did,))
        doc['emails'] = rows('SELECT id,recipient,subject,state,error,created_at FROM billing_outbox WHERE document_id=? ORDER BY id DESC', (did,)) if g.user['role'] == 'owner' else []
        return jsonify(doc)
    if not can_write():
        fail('Read-only access.', 403)
    payload = body()
    db().execute('BEGIN IMMEDIATE')
    doc = document(did)
    revision(doc, payload)
    if doc['state'] != 'draft':
        fail('Issued amounts and details are locked. Use Edit wording for text corrections, or duplicate or void the document for other changes.', 409)
    if request.method == 'DELETE':
        if doc['source_quote']:
            db().execute("UPDATE billing_documents SET state='accepted',version=version+1 WHERE id=?", (doc['source_quote'],))
        db().execute('UPDATE billing_time SET document_id=NULL WHERE document_id=?', (did,))
        db().execute('DELETE FROM billing_documents WHERE id=?', (did,))
        audit('draft deleted', did)
    else:
        values = validate_document(payload)
        if values['kind'] != doc['kind']:
            fail('Document type cannot be changed.')
        if one('SELECT id FROM billing_time WHERE document_id=?', (did,)) and values['client_id'] != doc['client_id']:
            fail('This invoice contains linked time entries for its current client.')
        columns = ['client_id', 'client', 'business', 'tax_mode', 'issue_date', 'due_date', 'notes', 'reference',
                   'payment_details', 'lines', 'subtotal_cents', 'gst_cents', 'total_cents']
        data = [json.dumps(values[k]) if k in ('client', 'business', 'lines') else values[k] for k in columns]
        db().execute('UPDATE billing_documents SET ' + ','.join(k + '=?' for k in columns) + ',version=version+1 WHERE id=?', data + [did])
        audit('draft updated', did)
    db().commit()
    return jsonify(ok=True)


@bp.put('/documents/<int:did>/wording')
@reader
def document_wording(did):
    from billing import audit, body, db, document, fail, g, json, jsonify, now, revision, txt
    payload = body()
    if set(payload) - {'version', 'descriptions', 'reference', 'notes', 'payment_details'}:
        fail('Only document wording can be changed here.')
    db().execute('BEGIN IMMEDIATE')
    doc = document(did)
    revision(doc, payload)
    if doc['state'] in ('void', 'converted'):
        fail('Void or converted documents cannot be amended.', 409)
    descriptions = payload.get('descriptions')
    if not isinstance(descriptions, list) or len(descriptions) != len(doc['lines']):
        fail('Provide a description for each existing line.')
    if any(not isinstance(v, str) or not v.strip() for v in descriptions):
        fail('Every line needs a description.')
    descriptions = [txt(v, 1000) for v in descriptions]
    values = {key: txt(payload.get(key, doc[key]), limit) for key, limit in [('reference', 100), ('notes', 5000), ('payment_details', 2000)]}
    # Preserve the previous wording and full line values before changing the displayed PDF.
    previous = {key: doc[key] for key in ('lines', 'reference', 'notes', 'payment_details')}
    db().execute('INSERT INTO billing_wording_history(document_id,version,user_id,previous,changed_at) VALUES (?,?,?,?,?)',
                 (did, doc['version'], g.user['id'], json.dumps(previous), now()))
    for line, description in zip(doc['lines'], descriptions):
        line['description'] = description
    db().execute('UPDATE billing_documents SET lines=?,reference=?,notes=?,payment_details=?,version=version+1 WHERE id=?',
                 (json.dumps(doc['lines']), values['reference'], values['notes'], values['payment_details'], did))
    audit('document wording updated', did)
    db().commit()
    return jsonify(ok=True)


@bp.post('/documents/<int:did>/action')
@reader
def document_action(did):
    from billing import audit, body, date, db, document, fail, insert_document, jsonify, local_today, one, ready_to_issue, revision, timedelta, validate_document
    payload = body()
    action = payload.get('action')
    db().execute('BEGIN IMMEDIATE')
    doc = document(did)
    revision(doc, payload)
    result_id = did
    if action == 'issue':
        if doc['state'] != 'draft':
            fail('Only drafts can be issued.', 409)
        ready_to_issue(doc)
        db().execute("UPDATE billing_documents SET state='issued',version=version+1 WHERE id=?", (did,))
    elif action in ('accepted', 'declined'):
        if doc['kind'] != 'quote' or doc['state'] != 'issued':
            fail('Only issued quotes can be marked accepted or declined.', 409)
        db().execute('UPDATE billing_documents SET state=?,version=version+1 WHERE id=?', (action, did))
    elif action == 'convert':
        if doc['kind'] != 'quote' or doc['state'] != 'accepted':
            fail('Mark the quote accepted before converting it.', 409)
        payload = {**doc, 'kind': 'invoice', 'issue_date': local_today(),
                   'due_date': (date.fromisoformat(local_today()) + timedelta(days=doc['client']['terms'])).isoformat()}
        values = validate_document(payload)
        result_id = insert_document(values, source_quote=did)
        db().execute("UPDATE billing_documents SET state='converted',version=version+1 WHERE id=?", (did,))
    elif action == 'duplicate':
        payload = {**doc, 'issue_date': local_today(), 'due_date': (date.fromisoformat(local_today()) + timedelta(days=doc['client']['terms'])).isoformat()}
        result_id = insert_document(validate_document(payload))
    elif action == 'void':
        if doc['paid_cents'] or doc['state'] in ('void', 'converted', 'draft'):
            fail('Only issued, unpaid documents can be voided. Reverse recorded payments first.', 409)
        if one("SELECT id FROM billing_outbox WHERE document_id=? AND state IN ('sending','unknown')", (did,)):
            fail('Resolve the pending or uncertain email delivery before voiding this document.', 409)
        db().execute("UPDATE billing_documents SET state='void',version=version+1 WHERE id=?", (did,))
        db().execute('UPDATE billing_time SET document_id=NULL WHERE document_id=?', (did,))
    else:
        fail('Unknown document action.')
    audit('document ' + str(action), did)
    db().commit()
    return jsonify(id=result_id)


@bp.put('/documents/<int:did>/sharing')
@owner
def sharing(did):
    from billing import audit, body, db, document, jsonify, revision
    payload = body()
    db().execute('BEGIN IMMEDIATE')
    doc = document(did)
    revision(doc, payload)
    db().execute('UPDATE billing_documents SET shared=?,version=version+1 WHERE id=?', (int(payload.get('shared') is True), did))
    audit('document sharing updated', did)
    db().commit()
    return jsonify(ok=True)


@bp.get('/documents/<int:did>/pdf')
@reader
def download_pdf(did):
    from billing import document, io, pdf_document, send_file
    doc = document(did)
    return send_file(io.BytesIO(pdf_document(doc)), mimetype='application/pdf', as_attachment=True, download_name=doc['number'] + '.pdf')


@bp.post('/documents/<int:did>/payments')
@reader
def add_payment(did):
    from billing import audit, body, cents, day, db, decimal_value, document, fail, jsonify, local_today, now, one, request_key, revision, txt
    payload = body()
    key = request_key(payload.get('request_key'))
    db().execute('BEGIN IMMEDIATE')
    existing = one('SELECT id,document_id FROM billing_payments WHERE request_key=?', (key,))
    if existing:
        if existing['document_id'] != did:
            fail('Request key already used.', 409)
        return jsonify(id=existing['id'])
    doc = document(did)
    revision(doc, payload)
    amount = cents(decimal_value(payload.get('amount'), 'payment amount', '0.01') * 100)
    when = day(payload.get('date'))
    if when > local_today() or when < doc['issue_date']:
        fail('Payment date must be between the issue date and today.')
    if doc['kind'] != 'invoice' or doc['state'] != 'issued' or amount > doc['balance_cents']:
        fail('Record payments only on issued invoices and up to the remaining balance.', 409)
    cur = db().execute('INSERT INTO billing_payments(document_id,date,amount_cents,reference,request_key,created_at) VALUES (?,?,?,?,?,?)',
                       (did, when, amount, txt(payload.get('reference'), 200), key, now()))
    db().execute('UPDATE billing_documents SET version=version+1 WHERE id=?', (did,))
    audit('invoice payment recorded', did)
    db().commit()
    return jsonify(id=cur.lastrowid)


@bp.get('/documents/<int:did>/email-draft')
@owner
def email_draft(did):
    from billing import aud, date_au, document, document_defaults, jsonify, mail_settings, request, secrets, template_text
    doc, config = document(did), mail_settings()
    values = dict(kind=doc['kind'], number=doc['number'], business=doc['business']['name'], client=doc['client']['contact'] or doc['client']['name'],
                  total=aud(doc['total_cents']), balance=aud(doc['balance_cents']), due_date=date_au(doc['due_date']))
    reminder = request.args.get('reminder') == '1'
    subject = 'Payment reminder: {number}' if reminder else document_defaults()[doc['kind'] + '_email_subject']
    message = 'Hi {client},\n\nA reminder that invoice {number}, due {due_date}, has an outstanding balance of {balance}. A copy is attached.\n\nThank you,\n{business}' if reminder else document_defaults()[doc['kind'] + '_email_body']
    return jsonify(recipient=doc['client']['email'], subject=template_text(subject, values), body=template_text(message, values),
                   from_email=config['from_email'], ready=bool(config['host'] and config['from_email']), request_key=secrets.token_hex(24), version=doc['version'])


@bp.post('/documents/<int:did>/send')
@owner
def send_document(did):
    from billing import audit, body, db, deliver, document, email, fail, header, jsonify, mail_settings, now, one, pdf_document, ready_to_issue, request_key, revision, txt
    payload = body()
    key = request_key(payload.get('request_key'))
    recipient, subject, message = email(payload.get('recipient'), True), header(payload.get('subject')), txt(payload.get('body'), 20000)
    if not subject or not message:
        fail('Email subject and message are required.')
    if not mail_settings()['host'] or not mail_settings()['from_email']:
        fail('Configure your email account before sending.')
    db().execute('BEGIN IMMEDIATE')
    previous = one('SELECT * FROM billing_outbox WHERE request_key=?', (key,))
    if previous:
        if previous['document_id'] != did:
            fail('Request key already used.', 409)
        return jsonify(state=previous['state'], error=previous['error'])
    doc = document(did)
    revision(doc, payload)
    if doc['state'] in ('void', 'declined', 'converted'):
        fail('This document cannot be sent.', 409)
    if one("SELECT id FROM billing_outbox WHERE document_id=? AND state IN ('sending','unknown')", (did,)):
        fail('An email is pending or its delivery is uncertain. Review email history before retrying.', 409)
    ready_to_issue(doc)
    if doc['state'] == 'draft':
        db().execute("UPDATE billing_documents SET state='issued' WHERE id=?", (did,))
        doc['state'] = 'issued'
    attachment = pdf_document(doc)
    cur = db().execute("INSERT INTO billing_outbox(document_id,recipient,subject,body,state,request_key,created_at) VALUES (?,?,?,?,'sending',?,?)",
                       (did, recipient, subject, message, key, now()))
    oid = cur.lastrowid
    db().execute('UPDATE billing_documents SET version=version+1 WHERE id=?', (did,))
    audit('document email queued', did)
    db().commit()
    state, error = deliver(recipient, subject, message, attachment, doc['number'] + '.pdf')
    db().execute('UPDATE billing_outbox SET state=?,error=? WHERE id=?', (state, error, oid))
    audit('document email ' + state, did)
    db().commit()
    return jsonify(state=state, error=error)
