"""Owner-managed billing, durable payment records and explicit SMTP delivery."""
import base64
import csv
import hashlib
import io
import json
import re
import secrets
import smtplib
import ssl
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from functools import wraps
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, g, jsonify, request, send_file
from billing_core import calculate_lines, decimal_value, cents, advance_date, display_status, pdf_document, aud

bp = Blueprint('billing', __name__, url_prefix='/api/billing')
DEFAULT_BUSINESS = dict(name='', abn='', address='', email='', phone='', gst_registered=False,
                        payment_details='', notes='Thank you for your business.', terms=14,
                        invoice_prefix='INV-', quote_prefix='QUO-', accent='#355c46', logo='')
DEFAULT_MAIL = dict(host='', port=587, security='starttls', username='', from_email='',
                    from_name='', reply_to='', password_encrypted='',
                    subject='{kind} {number} from {business}',
                    body='Hi {client},\n\nPlease find your {kind} {number} attached.\nTotal: {total}\nDue / valid until: {due_date}\n\nThank you,\n{business}')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def local_today():
    return datetime.now(ZoneInfo('Australia/Brisbane')).date().isoformat()


def owner(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not g.user:
            fail('Please sign in.', 401)
        if g.user['role'] != 'owner':
            fail('Only the owner can manage billing.', 403)
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            fail(str(exc))
    return wrapped


def can_write():
    return g.user['role']=='owner' or (g.user['role']=='tax_agent' and g.user.get('permission')=='read_write')

def reader(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not g.user:
            fail('Please sign in.', 401)
        if g.user['role'] not in ('owner', 'tax_agent'):
            fail('Access denied.', 403)
        if request.method not in ('GET','HEAD') and not can_write():
            fail('Read-only access.',403)
        try:
            return fn(*args, **kwargs)
        except ValueError as exc:
            fail(str(exc))
    return wrapped


def body():
    value = request.get_json()
    if not isinstance(value, dict):
        fail('Expected a JSON object.')
    return value


def txt(value, maximum=500):
    value = str(value or '').strip()
    if len(value) > maximum:
        raise ValueError(f'Text cannot exceed {maximum} characters.')
    return value


def integer(value, label, minimum=0, maximum=365):
    n = decimal_value(value, label, minimum, maximum)
    if n != int(n):
        raise ValueError(f'{label} must be a whole number.')
    return int(n)


def day(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValueError('Enter a valid date (YYYY-MM-DD).') from None


def email(value, required=False):
    value = txt(value, 254)
    if not value and not required:
        return ''
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}", value):
        raise ValueError('Enter a single valid email address.')
    return value


def header(value, maximum=200):
    value = txt(value, maximum)
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError('Email headers cannot contain line breaks or control characters.')
    return value


def settings(key, defaults):
    row = one('SELECT value FROM billing_settings WHERE key=?', (key,))
    return {**defaults, **(json.loads(row['value']) if row else {})}


def save_settings(key, value):
    db().execute('INSERT INTO billing_settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                 (key, json.dumps(value)))


def business():
    return settings('business', DEFAULT_BUSINESS)


def mail_settings():
    return settings('email', DEFAULT_MAIL)


def secret_box():
    # The existing backed-up session key also protects mail secrets, with domain separation.
    material = hashlib.sha256(b'Expense Pilot SMTP v1\0' + (DATA / 'session.key').read_bytes()).digest()
    return Fernet(base64.urlsafe_b64encode(material))


def revision(doc, payload):
    if integer(payload.get('version', -1), 'document version', -1, 1000000000) != doc['version']:
        fail('This document changed in another tab. Reload it before continuing.', 409)


def hydrate(row):
    doc = dict(row)
    for key in ('client', 'business', 'lines'):
        doc[key] = json.loads(doc[key])
    doc['paid_cents'] = one('SELECT COALESCE(SUM(amount_cents),0) AS n FROM billing_payments WHERE document_id=? AND reversed_at IS NULL', (doc['id'],))['n']
    doc['paid_date'] = one('SELECT MAX(date) AS value FROM billing_payments WHERE document_id=? AND reversed_at IS NULL', (doc['id'],))['value'] if doc['paid_cents'] >= doc['total_cents'] and doc['paid_cents'] > 0 else None
    doc['balance_cents'] = doc['total_cents'] - doc['paid_cents']
    doc['status'] = display_status(doc, local_today())
    return doc


def document(did):
    row = one('SELECT * FROM billing_documents WHERE id=?', (did,))
    if not row:
        fail('Document not found.', 404)
    return hydrate(row)


def validate_document(payload):
    kind = payload.get('kind', 'invoice')
    if kind not in ('invoice', 'quote'):
        raise ValueError('Choose an invoice or quote.')
    client = one('SELECT * FROM billing_clients WHERE id=? AND archived=0', (payload.get('client_id'),))
    if not client:
        raise ValueError('Choose an active client.')
    seller = business()
    mode = payload.get('tax_mode', 'none')
    amounts = calculate_lines(payload.get('lines'), mode, seller['gst_registered'])
    issued = day(payload.get('issue_date', local_today()))
    due = day(payload.get('due_date'))
    if due < issued:
        raise ValueError('Due date / valid until must be on or after the issue date.')
    snapshot = {k: client[k] for k in ('id', 'name', 'contact', 'email', 'address', 'abn', 'terms')}
    return dict(kind=kind, client_id=client['id'], client=snapshot, business=seller, tax_mode=mode,
                issue_date=issued, due_date=due, notes=txt(payload.get('notes', seller['notes']), 5000),
                reference=txt(payload.get('reference'), 100),
                payment_details=txt(payload.get('payment_details', seller['payment_details']), 2000), **amounts)


def insert_document(values, source_quote=None, schedule_id=None, occurrence=None):
    # Caller holds BEGIN IMMEDIATE: number allocation and creation are one transaction.
    kind = values['kind']
    n = one('SELECT next_number FROM billing_counters WHERE kind=?', (kind,))['next_number']
    prefix = values['business'][kind + '_prefix']
    number = f'{prefix}{n:04d}'
    while one('SELECT id FROM billing_documents WHERE number=?', (number,)):
        n += 1
        number = f'{prefix}{n:04d}'
    db().execute('UPDATE billing_counters SET next_number=? WHERE kind=?', (n + 1, kind))
    columns = ['kind', 'client_id', 'client', 'business', 'tax_mode', 'issue_date', 'due_date', 'notes',
               'reference', 'payment_details', 'lines', 'subtotal_cents', 'gst_cents', 'total_cents']
    data = [json.dumps(values[k]) if k in ('client', 'business', 'lines') else values[k] for k in columns]
    cur = db().execute('INSERT INTO billing_documents(' + ','.join(columns) + ',number,source_quote,schedule_id,occurrence,created_at) VALUES (' + ','.join('?' for _ in range(len(columns) + 5)) + ')',
                       data + [number, source_quote, schedule_id, occurrence, now()])
    audit(kind + ' draft created', cur.lastrowid)
    return cur.lastrowid


def ready_to_issue(doc):
    if not doc['business']['name']:
        fail('Set your business name, then edit and save the draft to apply it.')
    if doc['business']['gst_registered'] and len(re.sub(r'\D', '', doc['business']['abn'])) != 11:
        fail('An 11-digit business ABN is required for GST invoices. Update Business settings and save the draft.')
    if doc['total_cents'] <= 0:
        fail('The document total must be greater than zero.')


@bp.route('/settings', methods=['GET', 'PUT'])
@reader
def configure():
    if g.user['role']!='owner':
        if request.method!='GET': fail('Only the owner can change business settings.',403)
        return jsonify(business=business())
    if request.method == 'PUT':
        payload = body()
        old = business()
        seller = {k: txt(payload.get(k, old[k]), 5000 if k == 'notes' else 2000 if k in ('address', 'payment_details') else 200)
                  for k in ('name', 'abn', 'address', 'email', 'phone', 'payment_details', 'notes', 'invoice_prefix', 'quote_prefix', 'accent')}
        seller['email'] = email(seller['email'])
        seller['gst_registered'] = payload.get('gst_registered') is True
        seller['terms'] = integer(payload.get('terms', 14), 'payment terms', 0, 365)
        seller['logo'] = old['logo']
        digits = re.sub(r'\s', '', seller['abn'])
        if digits and not re.fullmatch(r'\d{11}', digits):
            fail('ABN must contain 11 digits, optionally separated by spaces.')
        if seller['gst_registered'] and not digits:
            fail('Enter your ABN before enabling GST.')
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', seller['accent']):
            fail('Choose a valid brand colour.')
        for key in ('invoice_prefix', 'quote_prefix'):
            if not re.fullmatch(r'[A-Za-z0-9-]{1,12}', seller[key]):
                fail('Number prefixes must use 1–12 letters, numbers or hyphens.')
        save_settings('business', seller)
        audit('business settings updated', 'billing')
        db().commit()
    return jsonify(business=business(), email={k: v for k, v in mail_settings().items() if k != 'password_encrypted'},
                   password_saved=bool(mail_settings()['password_encrypted']))


@bp.route('/logo', methods=['POST', 'DELETE'])
@owner
def logo():
    seller = business()
    if request.method == 'DELETE':
        seller['logo'] = ''
    else:
        from PIL import Image, ImageOps
        upload = request.files.get('file')
        if not upload:
            fail('Choose a logo image.')
        raw = upload.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            fail('Logo images must be under 2 MB.')
        try:
            image = Image.open(io.BytesIO(raw))
            if image.width * image.height > 16000000:
                fail('Logo image is too large.')
            image = ImageOps.exif_transpose(image).convert('RGBA')
            image.thumbnail((600, 240))
            out = io.BytesIO()
            image.save(out, format='PNG')
            seller['logo'] = base64.b64encode(out.getvalue()).decode()
        except (OSError, ValueError):
            fail('Use a readable PNG, JPEG or WebP logo.')
    save_settings('business', seller)
    audit('business logo updated', 'billing')
    db().commit()
    return jsonify(ok=True)


@bp.put('/email-settings')
@owner
def configure_email():
    payload, old = body(), mail_settings()
    config = dict(host=header(payload.get('host'), 253), port=integer(payload.get('port', 587), 'SMTP port', 1, 65535),
                  security=payload.get('security', 'starttls'), username=header(payload.get('username'), 254),
                  from_email=email(payload.get('from_email')), from_name=header(payload.get('from_name')),
                  reply_to=email(payload.get('reply_to')), subject=header(payload.get('subject', DEFAULT_MAIL['subject'])),
                  body=txt(payload.get('body', DEFAULT_MAIL['body']), 10000), password_encrypted=old['password_encrypted'])
    if config['host'] and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]*', config['host']):
        fail('Enter the SMTP hostname without http:// or a path.')
    if config['security'] not in ('starttls', 'ssl'):
        fail('Choose STARTTLS or SSL/TLS.')
    if config['host'] and not config['from_email']:
        fail('A sender email is required.')
    password = payload.get('password', '')
    if not isinstance(password, str) or len(password) > 2048:
        fail('Invalid SMTP password.')
    if payload.get('clear_password') is True:
        config['password_encrypted'] = ''
    elif password:
        config['password_encrypted'] = secret_box().encrypt(password.encode()).decode()
    save_settings('email', config)
    audit('email settings updated', 'billing')
    db().commit()
    return jsonify(ok=True)


def deliver(recipient, subject, message, attachment=None, filename=None):
    config = mail_settings()
    if not config['host'] or not config['from_email']:
        raise ValueError('Configure your SMTP account in Email settings first.')
    outgoing = EmailMessage()
    outgoing['From'] = formataddr((header(config['from_name']), email(config['from_email'], True)))
    outgoing['To'] = email(recipient, True)
    outgoing['Subject'] = header(subject)
    outgoing['Date'] = formatdate(localtime=False)
    outgoing['Message-ID'] = make_msgid()
    if config['reply_to']:
        outgoing['Reply-To'] = email(config['reply_to'])
    outgoing.set_content(message)
    if attachment:
        outgoing.add_attachment(attachment, maintype='application', subtype='pdf', filename=filename)
    context = ssl.create_default_context()
    connection = None
    phase = 'connect'
    try:
        if config['security'] == 'ssl':
            connection = smtplib.SMTP_SSL(config['host'], config['port'], timeout=25, context=context)
        else:
            connection = smtplib.SMTP(config['host'], config['port'], timeout=25)
            connection.ehlo()
            connection.starttls(context=context)
            connection.ehlo()
        if config['username']:
            password = secret_box().decrypt(config['password_encrypted'].encode()).decode() if config['password_encrypted'] else ''
            connection.login(config['username'], password)
        phase = 'send'
        connection.send_message(outgoing)
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        return 'failed', 'The mail server rejected the message. Check the recipient and sender permissions.'
    except (smtplib.SMTPException, OSError, InvalidToken, ValueError):
        if phase == 'send':
            return 'unknown', 'The connection ended during delivery. Check your mail provider before retrying to avoid duplicates.'
        return 'failed', 'Could not connect or authenticate. Check SMTP settings, TLS, and your app password or relay permissions.'
    finally:
        if connection:
            # Delivery was accepted before QUIT; a disconnect at QUIT must not imply failure.
            try:
                connection.quit()
            except (smtplib.SMTPException, OSError):
                connection.close()
    return 'sent', ''


@bp.post('/email-test')
@owner
def email_test():
    config = mail_settings()
    recipient = email(config['from_email'], True)
    state, error = deliver(recipient, 'Expense Pilot email test', 'Your Expense Pilot email settings are working.')
    audit('email connection test: ' + state, recipient)
    db().commit()
    return jsonify(state=state, error=error), 200 if state == 'sent' else 502


@bp.route('/clients', methods=['GET', 'POST'])
@reader
def clients():
    if request.method == 'POST':
        values = client_values(body())
        cur = db().execute('INSERT INTO billing_clients(name,contact,email,address,abn,terms,notes,archived) VALUES (?,?,?,?,?,?,?,?)', values)
        audit('client created', cur.lastrowid)
        db().commit()
        return jsonify(id=cur.lastrowid)
    return jsonify(rows('SELECT * FROM billing_clients ORDER BY archived,name'))


def client_values(payload):
    name = txt(payload.get('name'), 200)
    if not name:
        fail('Client name is required.')
    return (name, txt(payload.get('contact'), 200), email(payload.get('email')), txt(payload.get('address'), 2000),
            txt(payload.get('abn'), 50), integer(payload.get('terms', 14), 'payment terms'),
            txt(payload.get('notes'), 3000), int(payload.get('archived') is True))


@bp.put('/clients/<int:cid>')
@reader
def edit_client(cid):
    if not one('SELECT id FROM billing_clients WHERE id=?', (cid,)):
        fail('Client not found.', 404)
    values = client_values(body())
    db().execute('UPDATE billing_clients SET name=?,contact=?,email=?,address=?,abn=?,terms=?,notes=?,archived=? WHERE id=?', values + (cid,))
    audit('client updated', cid)
    db().commit()
    return jsonify(ok=True)


@bp.route('/services', methods=['GET', 'POST'])
@reader
def services():
    if request.method == 'GET':
        return jsonify(rows('SELECT * FROM billing_services ORDER BY description'))
    payload = body()
    description = txt(payload.get('description'), 1000)
    if not description:
        fail('Enter a service description.')
    rate = cents(decimal_value(payload.get('unit_price'), 'unit price') * 100)
    tax = payload.get('tax', 'none')
    if tax not in ('gst', 'gst_free', 'none'):
        fail('Invalid GST treatment.')
    cur = db().execute('INSERT INTO billing_services(description,unit_cents,tax) VALUES (?,?,?)', (description, rate, tax))
    db().commit()
    return jsonify(id=cur.lastrowid)


@bp.delete('/services/<int:sid>')
@reader
def delete_service(sid):
    db().execute('DELETE FROM billing_services WHERE id=?', (sid,))
    db().commit()
    return jsonify(ok=True)


@bp.route('/documents', methods=['GET', 'POST'])
@reader
def documents():
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
        fail('Issued documents are locked. Duplicate or void the document to make a correction.', 409)
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


@bp.post('/documents/<int:did>/action')
@reader
def document_action(did):
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
    doc = document(did)
    return send_file(io.BytesIO(pdf_document(doc)), mimetype='application/pdf', as_attachment=True, download_name=doc['number'] + '.pdf')


def request_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9-]{20,100}', value):
        fail('Reload the form before trying again.')
    return value


@bp.post('/documents/<int:did>/payments')
@reader
def add_payment(did):
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


@bp.post('/payments/<int:pid>/reverse')
@reader
def reverse_payment(pid):
    payload = body()
    reason = txt(payload.get('reason'), 500)
    if not reason:
        fail('Enter a reason for reversing this payment record.')
    db().execute('BEGIN IMMEDIATE')
    payment = one('SELECT * FROM billing_payments WHERE id=?', (pid,))
    if not payment or payment['reversed_at']:
        fail('Payment is missing or already reversed.', 409)
    doc = document(payment['document_id'])
    revision(doc, payload)
    db().execute('UPDATE billing_payments SET reversed_at=?,reversal_reason=? WHERE id=?', (now(), reason, pid))
    db().execute('UPDATE billing_documents SET version=version+1 WHERE id=?', (doc['id'],))
    audit('payment record reversed', pid)
    db().commit()
    return jsonify(ok=True)


def template_text(template, values):
    # Replace only known tags; no Python format expression evaluation.
    return re.sub(r'\{([a-z_]+)\}', lambda match: str(values.get(match.group(1), match.group(0))), template)


@bp.get('/documents/<int:did>/email-draft')
@owner
def email_draft(did):
    doc, config = document(did), mail_settings()
    values = dict(kind=doc['kind'], number=doc['number'], business=doc['business']['name'], client=doc['client']['contact'] or doc['client']['name'],
                  total=aud(doc['total_cents']), balance=aud(doc['balance_cents']), due_date=doc['due_date'])
    reminder = request.args.get('reminder') == '1'
    subject = 'Payment reminder: {number}' if reminder else config['subject']
    message = 'Hi {client},\n\nA reminder that invoice {number}, due {due_date}, has an outstanding balance of {balance}. A copy is attached.\n\nThank you,\n{business}' if reminder else config['body']
    return jsonify(recipient=doc['client']['email'], subject=template_text(subject, values), body=template_text(message, values),
                   from_email=config['from_email'], ready=bool(config['host'] and config['from_email']), request_key=secrets.token_hex(24), version=doc['version'])


@bp.post('/documents/<int:did>/send')
@owner
def send_document(did):
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


@bp.post('/emails/<int:oid>/resolve')
@owner
def resolve_email(oid):
    payload = body()
    state = payload.get('state')
    if state not in ('sent', 'failed'):
        fail('Choose confirmed sent or confirmed not sent.')
    db().execute('BEGIN IMMEDIATE')
    outgoing = one('SELECT * FROM billing_outbox WHERE id=?', (oid,))
    if not outgoing or outgoing['state'] not in ('unknown', 'sending'):
        fail('This email does not need reconciliation.', 409)
    if outgoing['state'] == 'sending' and datetime.fromisoformat(outgoing['created_at']) > datetime.now(timezone.utc) - timedelta(minutes=5):
        fail('Delivery may still be running. Wait five minutes before checking this record.', 409)
    db().execute('UPDATE billing_outbox SET state=?,error=? WHERE id=?', (state, 'Delivery status manually confirmed by owner.', oid))
    audit('email delivery reconciled: ' + state, oid)
    db().commit()
    return jsonify(ok=True)


@bp.route('/time', methods=['GET', 'POST'])
@reader
def time_entries():
    if request.method == 'GET':
        return jsonify(rows('SELECT t.*,c.name AS client_name,d.number AS document_number FROM billing_time t JOIN billing_clients c ON c.id=t.client_id LEFT JOIN billing_documents d ON d.id=t.document_id ORDER BY t.date DESC,t.id DESC'))
    payload = body()
    client = one('SELECT id FROM billing_clients WHERE id=? AND archived=0', (payload.get('client_id'),))
    if not client:
        fail('Choose an active client.')
    description = txt(payload.get('description'), 1000)
    if not description:
        fail('Enter a description of the work.')
    hours = decimal_value(payload.get('hours'), 'hours', '.0001', 10000)
    if hours.as_tuple().exponent < -4:
        fail('Hours support up to four decimal places.')
    rate = cents(decimal_value(payload.get('rate'), 'hourly rate') * 100)
    cur = db().execute('INSERT INTO billing_time(client_id,date,description,hours,rate_cents,billable) VALUES (?,?,?,?,?,?)',
                       (client['id'], day(payload.get('date')), description, str(hours), rate, int(payload.get('billable') is True)))
    audit('time entry created', cur.lastrowid)
    db().commit()
    return jsonify(id=cur.lastrowid)


@bp.delete('/time/<int:tid>')
@reader
def delete_time(tid):
    db().execute('BEGIN IMMEDIATE')
    entry = one('SELECT * FROM billing_time WHERE id=?', (tid,))
    if not entry or entry['document_id']:
        fail('Only unbilled time entries can be deleted.', 409)
    db().execute('DELETE FROM billing_time WHERE id=?', (tid,))
    audit('time entry deleted', tid)
    db().commit()
    return jsonify(ok=True)


@bp.post('/time/invoice')
@reader
def invoice_time():
    payload = body()
    ids = payload.get('ids')
    if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
        fail('Select between 1 and 100 time entries.')
    db().execute('BEGIN IMMEDIATE')
    entries = rows('SELECT * FROM billing_time WHERE id IN (' + ','.join('?' for _ in ids) + ')', ids)
    if len(entries) != len(ids) or any(e['document_id'] or not e['billable'] for e in entries) or len({e['client_id'] for e in entries}) != 1:
        fail('Choose unbilled, billable entries for one client.', 409)
    client = one('SELECT * FROM billing_clients WHERE id=?', (entries[0]['client_id'],))
    mode = 'exclusive' if business()['gst_registered'] else 'none'
    data = dict(client_id=client['id'], tax_mode=mode, issue_date=local_today(),
                due_date=(date.fromisoformat(local_today()) + timedelta(days=client['terms'])).isoformat(),
                lines=[dict(description=e['date'] + ' - ' + e['description'], quantity=e['hours'], unit_price=f"{e['rate_cents']/100:.2f}") for e in entries])
    did = insert_document(validate_document(data))
    db().execute('UPDATE billing_time SET document_id=? WHERE id IN (' + ','.join('?' for _ in ids) + ')', [did] + ids)
    db().commit()
    return jsonify(id=did)


@bp.route('/schedules', methods=['GET', 'POST'])
@reader
def schedules():
    if request.method == 'GET':
        return jsonify(rows('SELECT s.*,c.name AS client_name FROM billing_schedules s JOIN billing_clients c ON c.id=s.client_id ORDER BY s.active DESC,s.next_date'))
    payload = body()
    doc = document(integer(payload.get('document_id'), 'invoice ID', 1, 1000000000))
    if doc['kind'] != 'invoice' or doc['state'] == 'void':
        fail('Choose an invoice as the recurring template.')
    interval = payload.get('interval')
    if interval not in ('weekly', 'fortnightly', 'monthly', 'quarterly', 'yearly'):
        fail('Choose a recurrence interval.')
    start = day(payload.get('start_date'))
    if start < local_today():
        fail('Start a new schedule today or later.')
    end = day(payload['end_date']) if payload.get('end_date') else None
    if end and end < start:
        fail('End date must follow start date.')
    terms = integer(payload.get('terms', 14), 'payment terms')
    template = {k: doc[k] for k in ('lines', 'tax_mode', 'notes', 'reference', 'payment_details')}
    cur = db().execute('INSERT INTO billing_schedules(client_id,template,interval,next_date,anchor_day,end_date,terms) VALUES (?,?,?,?,?,?,?)',
                       (doc['client_id'], json.dumps(template), interval, start, date.fromisoformat(start).day, end, terms))
    audit('recurring draft schedule created', cur.lastrowid)
    db().commit()
    return jsonify(id=cur.lastrowid)


@bp.put('/schedules/<int:sid>')
@reader
def pause_schedule(sid):
    payload = body()
    row = one('SELECT * FROM billing_schedules WHERE id=?', (sid,))
    if not row:
        fail('Schedule not found.', 404)
    active = payload.get('active') is True
    next_date = day(payload.get('next_date', row['next_date']))
    if active and next_date < local_today():
        fail('Choose today or a future next date when resuming a paused schedule.')
    if active and row['end_date'] and next_date > row['end_date']:
        fail('This schedule has passed its end date.')
    db().execute('UPDATE billing_schedules SET active=?,next_date=?,last_error=? WHERE id=?', (int(active), next_date, '', sid))
    audit('recurring schedule updated', sid)
    db().commit()
    return jsonify(ok=True)


def run_due(today=None):
    today = today or local_today()
    count = 0
    for item in rows('SELECT id FROM billing_schedules WHERE active=1 AND next_date<=?', (today,)):
        for _ in range(24):
            db().execute('BEGIN IMMEDIATE')
            schedule = one('SELECT * FROM billing_schedules WHERE id=?', (item['id'],))
            if not schedule['active'] or schedule['next_date'] > today:
                db().rollback()
                break
            when = schedule['next_date']
            if schedule['end_date'] and when > schedule['end_date']:
                db().execute('UPDATE billing_schedules SET active=0 WHERE id=?', (schedule['id'],))
                db().commit()
                break
            try:
                template = json.loads(schedule['template'])
                values = validate_document({**template, 'kind': 'invoice', 'client_id': schedule['client_id'],
                                            'issue_date': when, 'due_date': (date.fromisoformat(when) + timedelta(days=schedule['terms'])).isoformat()})
                if not one('SELECT id FROM billing_documents WHERE schedule_id=? AND occurrence=?', (schedule['id'], when)):
                    insert_document(values, schedule_id=schedule['id'], occurrence=when)
                    count += 1
                next_date = advance_date(when, schedule['interval'], schedule['anchor_day'])
                db().execute('UPDATE billing_schedules SET next_date=?,last_error=? WHERE id=?', (next_date, '', schedule['id']))
                db().commit()
            except (ValueError, OverflowError) as exc:
                db().rollback()
                db().execute('UPDATE billing_schedules SET last_error=? WHERE id=?', (str(exc)[:300], schedule['id']))
                db().commit()
                break
    return count


@bp.post('/schedules/run')
@reader
def generate_due():
    return jsonify(created=run_due())


def start_scheduler(app):
    def work():
        while True:
            try:
                with app.app_context():
                    run_due()
            except Exception:
                app.logger.error('Recurring draft generation failed; check schedule status in Billing.')
            threading.Event().wait(60)
    threading.Thread(target=work, daemon=True, name='recurring-drafts').start()


@bp.get('/report')
@reader
def report():
    start = day(request.args.get('start') or (str(date.fromisoformat(local_today()).year - (date.fromisoformat(local_today()).month < 7)) + '-07-01'))
    end = day(request.args.get('end') or local_today())
    if end < start:
        fail('End date must follow start date.')
    where = '1=1'
    # Include earlier receipts when assigning GST rounding, then apply the report date filter.
    payments = rows(f'''SELECT p.*,d.number,d.client,d.total_cents,d.gst_cents FROM billing_payments p
                      JOIN billing_documents d ON d.id=p.document_id WHERE p.reversed_at IS NULL AND {where} ORDER BY p.document_id,p.id''')
    running, records = {}, []
    for p in payments:
        cumulative = running.get(p['document_id'], 0)
        before = cents(Decimal(p['gst_cents']) * cumulative / p['total_cents'])
        after = cents(Decimal(p['gst_cents']) * (cumulative + p['amount_cents']) / p['total_cents'])
        running[p['document_id']] = cumulative + p['amount_cents']
        if start <= p['date'] <= end:
            records.append(dict(date=p['date'], invoice=p['number'], client=json.loads(p['client'])['name'],
                                amount_cents=p['amount_cents'], gst_cents=after - before,
                                net_cents=p['amount_cents'] - (after - before), reference=p['reference']))
    if request.args.get('format') == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date', 'Invoice', 'Client', 'Received AUD', 'GST portion AUD', 'Ex GST AUD', 'Payment reference'])
        def safe(value):
            return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value
        for p in records:
            writer.writerow([p['date'], p['invoice'], safe(p['client']), f"{p['amount_cents']/100:.2f}", f"{p['gst_cents']/100:.2f}", f"{p['net_cents']/100:.2f}", safe(p['reference'])])
        return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name='expense-pilot-income.csv')
    return jsonify(start=start, end=end, records=records, received_cents=sum(p['amount_cents'] for p in records),
                   gst_cents=sum(p['gst_cents'] for p in records), net_cents=sum(p['net_cents'] for p in records))


def register(app, database, single, many, failure, activity, data_path):
    global db, one, rows, fail, audit, DATA
    db, one, rows, fail, audit, DATA = database, single, many, failure, activity, data_path
    with app.app_context():
        db().executescript('''
        CREATE TABLE IF NOT EXISTS billing_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS billing_counters(kind TEXT PRIMARY KEY,next_number INTEGER NOT NULL);
        INSERT OR IGNORE INTO billing_counters VALUES ('invoice',1),('quote',1);
        CREATE TABLE IF NOT EXISTS billing_clients(id INTEGER PRIMARY KEY,name TEXT NOT NULL,contact TEXT NOT NULL DEFAULT '',email TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '',abn TEXT NOT NULL DEFAULT '',terms INTEGER NOT NULL DEFAULT 14,notes TEXT NOT NULL DEFAULT '',archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS billing_services(id INTEGER PRIMARY KEY,description TEXT NOT NULL,unit_cents INTEGER NOT NULL,tax TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS billing_schedules(id INTEGER PRIMARY KEY,client_id INTEGER NOT NULL REFERENCES billing_clients(id),template TEXT NOT NULL,interval TEXT NOT NULL,next_date TEXT NOT NULL,anchor_day INTEGER NOT NULL,end_date TEXT,terms INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1,last_error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS billing_documents(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,number TEXT NOT NULL UNIQUE,state TEXT NOT NULL DEFAULT 'draft',version INTEGER NOT NULL DEFAULT 1,client_id INTEGER NOT NULL REFERENCES billing_clients(id),client TEXT NOT NULL,business TEXT NOT NULL,issue_date TEXT NOT NULL,due_date TEXT NOT NULL,tax_mode TEXT NOT NULL,lines TEXT NOT NULL,subtotal_cents INTEGER NOT NULL,gst_cents INTEGER NOT NULL,total_cents INTEGER NOT NULL,reference TEXT NOT NULL DEFAULT '',notes TEXT NOT NULL DEFAULT '',payment_details TEXT NOT NULL DEFAULT '',shared INTEGER NOT NULL DEFAULT 0,source_quote INTEGER UNIQUE REFERENCES billing_documents(id),schedule_id INTEGER REFERENCES billing_schedules(id),occurrence TEXT,created_at TEXT NOT NULL,UNIQUE(schedule_id,occurrence));
        CREATE TABLE IF NOT EXISTS billing_payments(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES billing_documents(id),date TEXT NOT NULL,amount_cents INTEGER NOT NULL CHECK(amount_cents>0),reference TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,reversed_at TEXT,reversal_reason TEXT);
        CREATE TABLE IF NOT EXISTS billing_outbox(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES billing_documents(id),recipient TEXT NOT NULL,subject TEXT NOT NULL,body TEXT NOT NULL,state TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS billing_time(id INTEGER PRIMARY KEY,client_id INTEGER NOT NULL REFERENCES billing_clients(id),date TEXT NOT NULL,description TEXT NOT NULL,hours TEXT NOT NULL,rate_cents INTEGER NOT NULL,billable INTEGER NOT NULL DEFAULT 1,document_id INTEGER REFERENCES billing_documents(id));
        CREATE INDEX IF NOT EXISTS billing_payment_document ON billing_payments(document_id);
        CREATE INDEX IF NOT EXISTS billing_outbox_document ON billing_outbox(document_id);
        CREATE INDEX IF NOT EXISTS billing_due_schedule ON billing_schedules(active,next_date);
        ''')
        db().commit()
    app.register_blueprint(bp)
