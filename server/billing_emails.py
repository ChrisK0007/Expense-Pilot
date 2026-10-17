"""Client email templates, signatures, receipts and opt-in scheduled reminders."""
import copy
import io
import secrets
from datetime import date

from billing import bp, owner, reader
from billing_email_core import DEFAULT_TEMPLATES, FIELD_LABELS, TEMPLATE_FIELDS, clean_signature, signature_image, validate_template

DEFAULT_REMINDERS = dict(enabled=False, before_days=3, on_due_date=True, after_days=[7, 14])


def email_templates():
    from billing import document_defaults, settings
    defaults = document_defaults()
    saved = settings('email_templates', {})
    result = copy.deepcopy(DEFAULT_TEMPLATES)
    result.update(saved.get('templates', {}))
    # Keep the existing document-defaults API compatible with older clients.
    for kind in ('invoice', 'quote'):
        result[kind] = dict(subject=defaults[kind + '_email_subject'], body=defaults[kind + '_email_body'])
    return dict(templates=result, signature_html=saved.get('signature_html', ''))


def reminder_settings():
    from billing import settings
    return settings('reminders', DEFAULT_REMINDERS)


REMINDER_KINDS = ('reminder_due', 'reminder_overdue', 'reminder_manual')


def validate_schedule(payload):
    from billing import integer
    if not isinstance(payload, dict) or set(payload) != {'before_days', 'on_due_date', 'after_days'}:
        raise ValueError('Provide before-due, due-date and overdue reminder settings.')
    if not isinstance(payload['on_due_date'], bool):
        raise ValueError('Choose whether to send a reminder on the due date.')
    after = payload['after_days']
    if not isinstance(after, list) or len(after) > 6:
        raise ValueError('Choose up to six overdue reminder dates.')
    # Avoid treating JSON booleans as numeric day counts.
    days = [payload['before_days'], *after]
    if any(isinstance(value, bool) for value in days):
        raise ValueError('Reminder days must be whole numbers.')
    return dict(before_days=integer(payload['before_days'], 'days before due', 0, 30),
                on_due_date=payload['on_due_date'],
                after_days=sorted(set(integer(n, 'days overdue', 1, 365) for n in after)))


def validate_reminder_options(options):
    if not isinstance(options, dict) or set(options) - {'schedule', 'templates'}:
        raise ValueError('Choose valid invoice reminder settings.')
    result = {}
    if options.get('schedule') is not None:
        schedule = validate_schedule(options['schedule'])
        if not (schedule['before_days'] or schedule['on_due_date'] or schedule['after_days']):
            raise ValueError('Choose at least one custom reminder date, or use the shared schedule.')
        result['schedule'] = schedule
    templates = options.get('templates', {})
    if not isinstance(templates, dict) or set(templates) - set(REMINDER_KINDS):
        raise ValueError('Only reminder email templates can be customised for an invoice.')
    if templates:
        result['templates'] = {key: validate_template(key, value) for key, value in templates.items()}
    return result


def effective_reminder_schedule(doc, shared=None):
    shared = shared if shared is not None else reminder_settings()
    return {**shared, **doc.get('reminder_options', {}).get('schedule', {})}


@bp.route('/email-templates', methods=['GET', 'PUT'])
@owner
def configure_templates():
    from billing import audit, body, db, document_defaults, fail, jsonify, request, save_settings
    values = email_templates()
    if request.method == 'PUT':
        payload = body()
        if set(payload) - {'templates', 'signature_html'}:
            fail('Unknown email template setting.')
        changes = payload.get('templates', {})
        if not isinstance(changes, dict):
            fail('Choose valid email templates.')
        for kind, template in changes.items():
            values['templates'][kind] = validate_template(kind, template)
        if 'signature_html' in payload:
            values['signature_html'] = clean_signature(payload['signature_html'])[0]
        db().execute('BEGIN IMMEDIATE')
        defaults = document_defaults()
        for kind in ('invoice', 'quote'):
            if kind in changes:
                for field in ('subject', 'body'):
                    defaults[kind + '_email_' + field] = values['templates'][kind][field]
        save_settings('document_defaults', defaults)
        save_settings('email_templates', values)
        audit('email templates updated', ', '.join(changes) or 'signature')
        db().commit()
    return jsonify(**values, defaults=DEFAULT_TEMPLATES, fields=FIELD_LABELS,
                   template_fields={key: sorted(value - ({'balance'} if key == 'quote' else set())) for key, value in TEMPLATE_FIELDS.items()})


@bp.post('/signature-image')
@owner
def upload_signature_image():
    from billing import fail, jsonify, request
    upload = request.files.get('file')
    if not upload:
        fail('Choose a signature image.')
    return jsonify(src=signature_image(upload.read(100 * 1024 + 1)))


@bp.route('/reminder-settings', methods=['GET', 'PUT'])
@owner
def configure_reminders():
    from billing import audit, body, db, fail, integer, jsonify, mail_settings, request, save_settings
    values = reminder_settings()
    if request.method == 'PUT':
        payload = body()
        if set(payload) != set(DEFAULT_REMINDERS):
            fail('Provide the automatic reminder settings.')
        if not isinstance(payload['enabled'], bool):
            fail('Choose whether automatic reminders are enabled.')
        values = dict(enabled=payload['enabled'], **validate_schedule({k: payload[k] for k in ('before_days', 'on_due_date', 'after_days')}))
        if values['enabled'] and not (values['before_days'] or values['on_due_date'] or values['after_days']):
            fail('Choose at least one reminder date.')
        config = mail_settings()
        if values['enabled'] and not (config['host'] and config['from_email']):
            fail('Configure Email delivery before enabling automatic reminders.')
        save_settings('reminders', values)
        audit('automatic reminder settings updated', 'enabled' if values['enabled'] else 'disabled')
        db().commit()
    return jsonify(values)


@bp.route('/documents/<int:did>/reminders', methods=['GET', 'PUT'])
@owner
def invoice_reminders(did):
    from billing import audit, body, db, document, fail, json, jsonify, request, revision
    if request.method == 'GET':
        doc = document(did)
        if doc['kind'] != 'invoice':
            fail('Reminders are available for invoices only.')
        templates = email_templates()['templates']
        return jsonify(enabled=bool(doc['reminders_enabled']), version=doc['version'], options=doc['reminder_options'],
                       shared_schedule=reminder_settings(), effective_schedule=effective_reminder_schedule(doc),
                       shared_templates={key: templates[key] for key in REMINDER_KINDS},
                       fields=FIELD_LABELS, template_fields={key: sorted(TEMPLATE_FIELDS[key]) for key in REMINDER_KINDS},
                       preview_values=document_email_values(doc))
    payload = body()
    if set(payload) - {'enabled', 'version', 'options'}:
        fail('Unknown invoice reminder setting.')
    if not isinstance(payload.get('enabled'), bool):
        fail('Choose whether this invoice receives automatic reminders.')
    options = validate_reminder_options(payload['options']) if 'options' in payload else None
    db().execute('BEGIN IMMEDIATE')
    doc = document(did)
    revision(doc, payload)
    if doc['kind'] != 'invoice':
        fail('Reminders are available for invoices only.')
    if options is None:
        options = doc['reminder_options']
    db().execute('UPDATE billing_documents SET reminders_enabled=?,reminder_options=?,version=version+1 WHERE id=?',
                 (int(payload['enabled']), json.dumps(options), did))
    audit('invoice reminders updated', did)
    db().commit()
    return jsonify(ok=True)


def sender_full_name():
    from billing import one
    user = one("SELECT name FROM users WHERE role='owner' AND active=1 ORDER BY id LIMIT 1")
    return user['name'] if user else ''


def document_email_values(doc):
    from billing import aud, date_au, one
    payment = one('SELECT amount_cents FROM billing_payments WHERE document_id=? AND reversed_at IS NULL ORDER BY id DESC LIMIT 1', (doc['id'],))
    return dict(kind=doc['kind'], number=doc['number'], business=doc['business']['name'], full_name=sender_full_name(),
                client=doc['client']['contact'] or doc['client']['name'], total=aud(doc['total_cents']),
                balance=aud(doc['balance_cents']), due_date=date_au(doc['due_date']),
                latest_payment=aud(payment['amount_cents'] if payment else 0))


def validate_message_kind(doc, kind):
    from billing import fail
    if kind not in ('document', 'reminder_manual', 'reminder_due', 'reminder_overdue', 'receipt'):
        fail('Choose an invoice, reminder or payment receipt email.')
    if kind != 'document' and (doc['kind'] != 'invoice' or doc['state'] != 'issued'):
        fail('Reminders and receipts require an issued invoice.', 409)
    if kind.startswith('reminder_') and doc['balance_cents'] <= 0:
        fail('This invoice has no outstanding balance.', 409)
    if kind == 'receipt' and doc['paid_cents'] <= 0:
        fail('Record a payment before emailing a receipt.', 409)


def document_message(doc, kind='document'):
    from billing import local_today, template_text
    validate_message_kind(doc, kind)
    key = doc['kind'] if kind == 'document' else ('receipt_full' if doc['balance_cents'] == 0 else 'receipt_partial') if kind == 'receipt' else kind
    templates = email_templates()
    template = dict(doc.get('reminder_options', {}).get('templates', {}).get(key, templates['templates'][key]))
    # The supplied manual default says "overdue". Do not make that claim before it is true.
    if kind == 'reminder_manual' and doc['due_date'] >= local_today() and template == DEFAULT_TEMPLATES['reminder_manual']:
        template['subject'] = 'Invoice from {business} is due {due_date}'
        template['body'] = template['body'].replace('was due on', 'is due on')
    values = document_email_values(doc)
    return dict(subject=template_text(template['subject'], values), body=template_text(template['body'], values),
                signature_html=templates['signature_html'], message_kind=kind)


def document_attachment(doc, kind):
    from billing import pdf_document, rows
    if kind == 'receipt':
        doc = {**doc, 'receipt': True, 'payments': rows('SELECT date,amount_cents,reference FROM billing_payments WHERE document_id=? AND reversed_at IS NULL ORDER BY id', (doc['id'],))}
    return pdf_document(doc), doc['number'] + ('-receipt' if kind == 'receipt' else '') + '.pdf'


@bp.get('/documents/<int:did>/receipt')
@reader
def download_receipt(did):
    from billing import document, send_file
    doc = document(did)
    validate_message_kind(doc, 'receipt')
    attachment, filename = document_attachment(doc, 'receipt')
    return send_file(io.BytesIO(attachment), mimetype='application/pdf', as_attachment=True, download_name=filename)


def queue_document_email(doc, recipient, subject, message, key, kind='document', signature='', automation_key=None):
    """Called while holding BEGIN IMMEDIATE, before releasing the lock for SMTP."""
    from billing import audit, db, fail, now, one, ready_to_issue
    validate_message_kind(doc, kind)
    if doc['state'] in ('void', 'declined', 'converted'):
        fail('This document cannot be sent.', 409)
    if one("SELECT id FROM billing_outbox WHERE document_id=? AND state IN ('sending','unknown')", (doc['id'],)):
        fail('An email is pending or its delivery is uncertain. Review email history before retrying.', 409)
    ready_to_issue(doc)
    if doc['state'] == 'draft':
        db().execute("UPDATE billing_documents SET state='issued' WHERE id=?", (doc['id'],))
        doc['state'] = 'issued'
    attachment, filename = document_attachment(doc, kind)
    cur = db().execute("INSERT INTO billing_outbox(document_id,recipient,subject,body,state,request_key,created_at,message_kind,signature_html,automation_key) VALUES (?,?,?,?,'sending',?,?,?,?,?)",
                       (doc['id'], recipient, subject, message, key, now(), kind, signature, automation_key))
    db().execute('UPDATE billing_documents SET version=version+1 WHERE id=?', (doc['id'],))
    audit(kind + ' email queued', doc['id'])
    return cur.lastrowid, attachment, filename


def deliver_queued(oid, recipient, subject, message, attachment, filename, signature):
    from billing import audit, db, deliver
    state, error = deliver(recipient, subject, message, attachment, filename, signature_html=signature, copy=True)
    db().execute('UPDATE billing_outbox SET state=?,error=? WHERE id=?', (state, error, oid))
    audit('client email ' + state, oid)
    db().commit()
    return state, error


def run_reminders(today=None):
    from billing import db, document, email, header, local_today, mail_settings, one, rows, txt
    from werkzeug.exceptions import HTTPException
    today = today or local_today()
    config = reminder_settings()
    mail = mail_settings()
    if not config['enabled'] or not (mail['host'] and mail['from_email']):
        return 0
    count = 0
    for item in rows("SELECT id FROM billing_documents WHERE kind='invoice' AND state='issued' AND reminders_enabled=1 AND issue_date<=?", (today,)):
        try:
            db().execute('BEGIN IMMEDIATE')
            config = reminder_settings()
            row = one('SELECT id FROM billing_documents WHERE id=?', (item['id'],))
            if not row or not config['enabled']:
                db().rollback()
                continue
            doc = document(item['id'])
            schedule = effective_reminder_schedule(doc, config)
            difference = (date.fromisoformat(today) - date.fromisoformat(doc['due_date'])).days
            scheduled = (schedule['before_days'] > 0 and difference == -schedule['before_days']) or (schedule['on_due_date'] and difference == 0) or difference in schedule['after_days']
            if not scheduled or not doc['reminders_enabled'] or doc['state'] != 'issued' or doc['balance_cents'] <= 0 or not doc['client']['email']:
                db().rollback()
                continue
            key = f"invoice:{doc['id']}:{doc['due_date']}:{today}"
            # Claim once per scheduled date across workers/restarts, including failed/unknown sends.
            if one('SELECT id FROM billing_outbox WHERE automation_key=?', (key,)):
                db().rollback()
                continue
            kind = 'reminder_overdue' if difference > 0 else 'reminder_due'
            draft = document_message(doc, kind)
            recipient = email(doc['client']['email'], True)
            subject, message = header(draft['subject']), txt(draft['body'], 20000)
            signature = clean_signature(draft['signature_html'])[0]
            oid, attachment, filename = queue_document_email(doc, recipient, subject, message, secrets.token_hex(24), kind, signature, key)
            db().commit()
        except (ValueError, HTTPException):
            db().rollback()
            continue
        deliver_queued(oid, recipient, subject, message, attachment, filename, signature)
        count += 1
    return count
