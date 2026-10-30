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

from cryptography.fernet import Fernet, InvalidToken
from flask import Blueprint, g, jsonify, request, send_file
from billing_core import calculate_lines, decimal_value, cents, advance_date, display_status, pdf_document, aud, date_au

bp = Blueprint('billing', __name__, url_prefix='/api/billing')
DEFAULT_BUSINESS = dict(name='', abn='', address='', email='', phone='', gst_registered=False,
                        payment_details='', notes='Thank you for your business.', terms=14,
                        invoice_prefix='INV-', quote_prefix='QUO-', accent='#355c46', logo='')
DEFAULT_MAIL = dict(host='', port=587, security='starttls', username='', from_email='',
                    from_name='', reply_to='', password_encrypted='', copy_self=False, copy_email='',
                    subject='{kind} {number} from {business}',
                    body='Hi {client},\n\nPlease find your {kind} {number} attached.\nTotal: {total}\nDue / valid until: {due_date}\n\nThank you,\n{business}')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def local_today():
    from workspace_time import today
    return today().isoformat()


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


def document_defaults():
    seller, mail = business(), mail_settings()
    defaults = dict(invoice_notes=seller['notes'], quote_notes=seller['notes'],
                    invoice_payment_details=seller['payment_details'], quote_valid_days=seller['terms'])
    from billing_email_core import DEFAULT_TEMPLATES
    for kind in ('invoice', 'quote'):
        for field in ('subject', 'body'):
            defaults[kind + '_email_' + field] = DEFAULT_TEMPLATES[kind][field] if mail[field] == DEFAULT_MAIL[field] else mail[field]
    return settings('document_defaults', defaults)


@bp.put('/document-defaults')
@owner
def configure_document_defaults():
    payload, values = body(), document_defaults()
    if set(payload) - set(values):
        fail('Unknown document default.')
    for key, value in payload.items():
        if key == 'quote_valid_days':
            values[key] = integer(value, 'quote validity', 0, 365)
        elif key.endswith('_subject'):
            values[key] = header(value)
        else:
            values[key] = txt(value, 10000 if key.endswith('_body') else 2000 if key == 'invoice_payment_details' else 5000)
        if key.endswith(('_subject', '_body')) and not values[key]:
            fail('Email subject and message defaults are required.')
    save_settings('document_defaults', values)
    audit('document defaults updated', 'billing')
    db().commit()
    return jsonify(values)


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
    for key in ('client', 'business', 'lines', 'reminder_options'):
        doc[key] = json.loads(doc[key])
    doc['paid_cents'] = one('SELECT COALESCE(SUM(amount_cents),0) AS n FROM billing_payments WHERE document_id=? AND reversed_at IS NULL', (doc['id'],))['n']
    doc['paid_date'] = one('SELECT MAX(date) AS value FROM billing_payments WHERE document_id=? AND reversed_at IS NULL', (doc['id'],))['value'] if doc['paid_cents'] >= doc['total_cents'] and doc['paid_cents'] > 0 else None
    doc['balance_cents'] = doc['total_cents'] - doc['paid_cents']
    schedule=one('SELECT terms FROM billing_schedules WHERE id=?',(doc['schedule_id'],)) if doc.get('schedule_id') else None
    doc['due_terms_days']=schedule['terms'] if schedule else doc['client'].get('terms',14)
    doc['status'] = display_status(doc, local_today())
    return doc


def document(did):
    row = one('SELECT * FROM billing_documents WHERE id=?', (did,))
    if not row:
        fail('Document not found.', 404)
    return hydrate(row)


def validate_document(payload, terms=None):
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
    due_manual=payload.get('due_date_manual', True)
    if type(due_manual) not in (bool,int) or due_manual not in (0,1):
        raise ValueError('Choose automatic or manual due date.')
    if terms is None: terms=client['terms'] if kind=='invoice' else document_defaults()['quote_valid_days']
    due = day(payload.get('due_date')) if due_manual else (date.fromisoformat(issued)+timedelta(days=terms)).isoformat()
    if due < issued:
        raise ValueError('Due date / valid until must be on or after the issue date.')
    reminders = payload.get('reminders_enabled', True)
    if type(reminders) not in (bool, int) or reminders not in (0, 1):
        raise ValueError('Choose whether automatic reminders are on or off for this invoice.')
    snapshot = {k: client[k] for k in ('id', 'name', 'contact', 'email', 'address', 'abn', 'terms')}
    from billing_emails import validate_reminder_options
    options = validate_reminder_options(payload.get('reminder_options', {})) if kind == 'invoice' else {}
    return dict(kind=kind, reminders_enabled=int(reminders), reminder_options=options, client_id=client['id'], client=snapshot, business=seller, tax_mode=mode,
                issue_date=issued, due_date=due, due_date_manual=int(due_manual), notes=txt(payload.get('notes', document_defaults()[kind + '_notes']), 5000),
                reference=txt(payload.get('reference'), 100),
                payment_details=txt(payload.get('payment_details', document_defaults()['invoice_payment_details'] if kind == 'invoice' else ''), 2000), **amounts)


def insert_document(values, source_quote=None, schedule_id=None, occurrence=None, custom_number=None):
    # Caller holds BEGIN IMMEDIATE: allocation, reuse and creation are atomic.
    from billing_numbers import allocate_number
    kind = values['kind']
    number = allocate_number(values, custom_number)
    columns = ['kind', 'client_id', 'client', 'business', 'tax_mode', 'issue_date', 'due_date', 'notes',
               'reference', 'payment_details', 'lines', 'subtotal_cents', 'gst_cents', 'total_cents', 'reminders_enabled', 'reminder_options', 'due_date_manual']
    data = [json.dumps(values[k]) if k in ('client', 'business', 'lines', 'reminder_options') else values[k] for k in columns]
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
        return jsonify(business=business(), defaults=document_defaults())
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
    return jsonify(business=business(), defaults=document_defaults(), email={k: v for k, v in mail_settings().items() if k != 'password_encrypted'},
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
                  reply_to=email(payload.get('reply_to')), subject=header(payload.get('subject', old['subject'])),
                  body=txt(payload.get('body', old['body']), 10000), password_encrypted=old['password_encrypted'],
                  copy_self=payload.get('copy_self', old['copy_self']) is True, copy_email=email(payload.get('copy_email', old['copy_email'])))
    if config['copy_self'] and not config['copy_email']:
        config['copy_email'] = email(one("SELECT email FROM users WHERE role='owner' ORDER BY id LIMIT 1")['email'], True)
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


def deliver(recipient, subject, message, attachment=None, filename=None, signature_html='', copy=False):
    config = mail_settings()
    if not config['host'] or not config['from_email']:
        raise ValueError('Configure your SMTP account in Email settings first.')
    outgoing = EmailMessage()
    outgoing['From'] = formataddr((header(config['from_name']), email(config['from_email'], True)))
    outgoing['To'] = email(recipient, True)
    outgoing['Subject'] = header(subject)
    if copy and config['copy_self'] and config['copy_email'] and config['copy_email'].lower() != recipient.lower():
        outgoing['Bcc'] = email(config['copy_email'], True)
    outgoing['Date'] = formatdate(localtime=False)
    outgoing['Message-ID'] = make_msgid()
    if config['reply_to']:
        outgoing['Reply-To'] = email(config['reply_to'])
    from billing_email_core import add_message_content
    add_message_content(outgoing, message, signature_html)
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
        refused = connection.send_message(outgoing)
        if isinstance(refused, dict) and refused:
            if any(address.lower() == recipient.lower() for address in refused):
                return 'failed', 'The client address was rejected. Your copy may have been delivered.'
            return 'sent', 'Client email sent, but the copy address was rejected. Check the copy address in Email settings.'
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


def service_values(payload):
    description = txt(payload.get('description'), 1000)
    if not description:
        fail('Enter a service description.')
    rate = cents(decimal_value(payload.get('unit_price'), 'unit price') * 100)
    tax = payload.get('tax', 'none')
    if tax not in ('gst', 'gst_free', 'none'):
        fail('Invalid GST treatment.')
    return description, rate, tax


@bp.route('/services', methods=['GET', 'POST'])
@reader
def services():
    if request.method == 'GET':
        return jsonify(rows('SELECT * FROM billing_services ORDER BY description'))
    values = service_values(body())
    cur = db().execute('INSERT INTO billing_services(description,unit_cents,tax) VALUES (?,?,?)', values)
    audit('service created', cur.lastrowid)
    db().commit()
    return jsonify(id=cur.lastrowid)


@bp.route('/services/<int:sid>', methods=['PUT', 'DELETE'])
@reader
def service_detail(sid):
    payload = body()
    values = service_values(payload) if request.method == 'PUT' else None
    db().execute('BEGIN IMMEDIATE')
    service = one('SELECT * FROM billing_services WHERE id=?', (sid,))
    if not service:
        fail('Service not found.', 404)
    if request.method == 'PUT' or 'version' in payload:
        if payload.get('version') != service['version']:
            fail('This service changed in another tab. Reload it before continuing.', 409)
    if request.method == 'PUT':
        db().execute('UPDATE billing_services SET description=?,unit_cents=?,tax=?,version=version+1 WHERE id=?', values + (sid,))
        audit('service updated', sid)
    else:
        db().execute('DELETE FROM billing_services WHERE id=?', (sid,))
        audit('service deleted', sid)
    db().commit()
    return jsonify(ok=True)


def request_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9-]{20,100}', value):
        fail('Reload the form before trying again.')
    return value


@bp.post('/payments/<int:pid>/reverse')
@reader
def reverse_payment(pid):
    payload = body()
    reason = txt(payload.get('reason'), 500)
    if not reason:
        fail('Enter a reason for reversing this payment record.')
    db().execute('BEGIN IMMEDIATE')
    if one('SELECT 1 FROM bank_reconciliations WHERE payment_id=?',(pid,)): fail('Undo this payment from Bank reconciliation first.',409)
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
                due_date_manual=False, due_date=(date.fromisoformat(local_today()) + timedelta(days=client['terms'])).isoformat(),
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
    template['reminders_enabled'] = bool(doc['reminders_enabled'])
    template['reminder_options'] = doc['reminder_options']
    if 'reminders_enabled' in payload:
        if g.user['role'] != 'owner':
            fail('Only the owner can change automatic reminder preferences.', 403)
        if not isinstance(payload['reminders_enabled'], bool):
            fail('Choose whether generated invoices allow automatic reminders.')
        template['reminders_enabled'] = payload['reminders_enabled']
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
                                            'issue_date': when, 'due_date_manual':False}, terms=schedule['terms'])
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
                    from billing_emails import run_reminders
                    run_reminders()
            except Exception:
                app.logger.exception('Billing background processing failed; check schedules and email history.')
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
            writer.writerow([date_au(p['date']), p['invoice'], safe(p['client']), f"{p['amount_cents']/100:.2f}", f"{p['gst_cents']/100:.2f}", f"{p['net_cents']/100:.2f}", safe(p['reference'])])
        return send_file(io.BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name='expense-pilot-income.csv')
    return jsonify(start=start, end=end, records=records, received_cents=sum(p['amount_cents'] for p in records),
                   gst_cents=sum(p['gst_cents'] for p in records), net_cents=sum(p['net_cents'] for p in records))

from billing_documents import documents, document_detail, document_wording, document_action, sharing, download_pdf, add_payment, email_draft, send_document

import billing_emails
import billing_statements


def register(app, database, single, many, failure, activity, data_path):
    global db, one, rows, fail, audit, DATA
    db, one, rows, fail, audit, DATA = database, single, many, failure, activity, data_path
    app.register_blueprint(bp)
