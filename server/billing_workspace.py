"""Draft recovery, invoice presentation and explicitly selected supporting files."""
import hashlib
import io
import json
import re
import threading
from functools import wraps

_PREVIEW_SLOTS = threading.BoundedSemaphore(2)

def bounded_preview(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        from billing import fail
        if not _PREVIEW_SLOTS.acquire(blocking=False): fail("Preview busy. Make another change to retry.", 429)
        try: return fn(*args, **kwargs)
        finally: _PREVIEW_SLOTS.release()
    return wrapped
from flask import g, jsonify, request, send_file
from werkzeug.utils import secure_filename
from billing import bp, owner, reader

DESIGN = dict(layout='classic', font='sans', accent='', show_quantity=True, show_unit=True, show_rate=True,
              show_client_address=True, show_reference=True)
UNITS = ('Units', 'Hours', 'Days', 'Flight tests', 'Kilometres', 'Sessions', 'Jobs', 'Items')


def design_values(data):
    from billing import fail
    if not isinstance(data, dict): fail('Choose invoice design options.')
    result = {**DESIGN, **{k: v for k, v in data.items() if k in DESIGN}}
    if result['layout'] not in ('classic', 'modern', 'compact') or result['font'] not in ('sans', 'serif'):
        fail('Choose a supported layout and font.')
    if any(type(result[k]) is not bool for k in DESIGN if k.startswith('show_')):
        fail('Use on/off design options.')
    if result['accent'] and not re.fullmatch(r'#[0-9a-fA-F]{6}', str(result['accent'])): fail('Choose a brand colour.')
    return result


def quantity_type(value):
    from billing import txt, fail
    value = txt(value or 'Units', 30)
    if any(ord(c) < 32 or ord(c) == 127 for c in value): fail('Use a plain quantity label.')
    return value


def consume_draft(payload, key):
    from billing import one, db, fail
    saved = payload.get('editor_draft')
    if saved is None: return
    if not isinstance(saved, dict) or saved.get('key') != key: fail('Reload the invoice editor.', 409)
    old = one('SELECT version FROM billing_editor_drafts WHERE user_id=? AND draft_key=?', (g.user['id'], key))
    if saved.get('version') != (old['version'] if old else 0): fail('Your autosaved draft changed in another tab. Reload before saving.', 409)
    db().execute('DELETE FROM billing_editor_drafts WHERE user_id=? AND draft_key=?', (g.user['id'], key))


@bp.route('/design', methods=['GET', 'PUT'])
@owner
def design():
    from billing import business, save_settings, body, db, audit
    seller = business()
    if request.method == 'PUT':
        seller['design'] = design_values(body())
        save_settings('business', seller); audit('invoice design updated', 'billing'); db().commit()
    return jsonify(design_values(seller.get('design', {})))


@bp.post('/preview')
@reader
@bounded_preview
def preview():
    from billing import body, validate_document, pdf_document, fail, document
    payload = body()
    values = validate_document(payload)
    if payload.get('document_id'):
        old = document(payload['document_id'])
        values['number'] = old['number']; values['state'] = old['state']
    else:
        values.update(number=payload.get('number') or 'DRAFT', state='draft')
    paid = old['paid_cents'] if payload.get('document_id') else 0
    values.update(paid_cents=paid, balance_cents=values['total_cents']-paid, payments=[])
    if 'design' in payload:
        values['business'] = {**values['business'], 'design': design_values(payload['design'])}
    pdf = pdf_document(values)
    if request.args.get('format') == 'image':
        import base64
        import subprocess
        import tempfile
        from pathlib import Path
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory(prefix='invoice-preview-') as folder:
            source = Path(folder)/'preview.pdf'; target = Path(folder)/'page'
            source.write_bytes(pdf)
            try:
                subprocess.run(['pdftoppm','-f','1','-singlefile','-scale-to','1100','-png',str(source),str(target)], check=True, capture_output=True, timeout=15)
                image = target.with_suffix('.png').read_bytes()
            except (OSError, subprocess.SubprocessError): fail('The preview could not be rendered. Save the draft to download its PDF.', 503)
        return jsonify(image=base64.b64encode(image).decode(), pdf=base64.b64encode(pdf).decode(), pages=len(PdfReader(io.BytesIO(pdf)).pages))
    result = send_file(io.BytesIO(pdf), mimetype='application/pdf')
    result.headers['Cache-Control'] = 'no-store'
    return result


@bp.route('/editor-drafts/<key>', methods=['GET', 'PUT', 'DELETE'])
@owner
def editor_draft(key):
    from billing import one, db, body, fail, now
    if not re.fullmatch(r'(new-(invoice|quote)|document-[1-9][0-9]*)', key): fail('Invalid draft.', 404)
    if request.method != 'GET': db().execute('BEGIN IMMEDIATE')
    old = one('SELECT * FROM billing_editor_drafts WHERE user_id=? AND draft_key=?', (g.user['id'], key))
    if request.method != 'GET':
        data = body()
        if data.get('version') != (old['version'] if old else 0): fail('This draft changed in another tab. Reload to recover the latest changes.', 409)
        if request.method == 'DELETE':
            db().execute('DELETE FROM billing_editor_drafts WHERE user_id=? AND draft_key=?', (g.user['id'], key))
            db().commit(); return jsonify(ok=True)
        payload = data.get('payload')
        if not isinstance(payload, dict) or len(json.dumps(payload)) > 150000: fail('Draft is too large.')
        if payload.get('kind') not in ('invoice', 'quote'): fail('Choose an invoice or quote.')
        if key.startswith('document-'):
            from billing import document
            from billing_revisions import editable
            doc = document(int(key[9:])); editable(doc)
            if payload.get('version') != doc['version']: fail('The saved invoice changed. Reload it before continuing.', 409)
        db().execute('INSERT INTO billing_editor_drafts(user_id,draft_key,payload,updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id,draft_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at,version=version+1',
                     (g.user['id'], key, json.dumps(payload), now()))
        db().commit(); old = one('SELECT * FROM billing_editor_drafts WHERE user_id=? AND draft_key=?', (g.user['id'], key))
    return jsonify(payload=json.loads(old['payload']) if old else None, version=old['version'] if old else 0, updated_at=old['updated_at'] if old else None)


def attachment_list(did):
    from billing import rows
    return rows('SELECT id,filename,mime,length(content) AS size,sha256 FROM billing_attachments WHERE document_id=? ORDER BY id', (did,))


def selected_attachments(did, ids):
    from billing import fail, one
    if not isinstance(ids, list) or len(ids) > 5 or any(type(x) is not int for x in ids) or len(ids) != len(set(ids)):
        fail('Choose up to five supporting files.')
    result = []
    for aid in ids:
        row = one('SELECT * FROM billing_attachments WHERE id=? AND document_id=?', (aid, did))
        if not row: fail('A selected attachment is no longer available. Reload the email.', 409)
        result.append(row)
    return result


@bp.route('/documents/<int:did>/attachments', methods=['GET', 'POST'])
@owner
def attachments(did):
    from billing import db, document, fail, now, audit
    document(did)
    if request.method == 'GET': return jsonify(attachment_list(did))
    upload = request.files.get('file')
    if upload:
        data = upload.read(10 * 1024 * 1024 + 1); filename = upload.filename
    else:
        from billing import one, DATA
        receipt = one('SELECT * FROM receipts WHERE id=? AND user_id=?', (request.form.get('receipt_id'), g.user['id']))
        if not receipt: fail('Choose one of your saved receipts or upload a supporting file.')
        data = (DATA/'receipts'/receipt['id']).read_bytes(); filename = receipt['filename']
    if not data or len(data) > 10 * 1024 * 1024: fail('Use a supporting file no larger than 10 MB.')
    name = secure_filename(filename or '')[:150] or 'supporting-file'
    if data.startswith(b'%PDF-'):
        from pdf_safety import inspect_pdf
        inspect_pdf(data); mime = 'application/pdf'
        if not name.lower().endswith('.pdf'): name += '.pdf'
    else:
        from PIL import Image, ImageOps
        try:
            image = Image.open(io.BytesIO(data))
            if image.format not in ('JPEG', 'PNG') or image.width * image.height > 16000000: raise ValueError()
            image.load(); image = ImageOps.exif_transpose(image).convert('RGB')
            output = io.BytesIO(); image.save(output, format='JPEG', quality=90); data = output.getvalue()
        except Exception: fail('Use a valid PDF, JPG or PNG file.')
        name = name.rsplit('.', 1)[0] + '.jpg'; mime = 'image/jpeg'
    db().execute('BEGIN IMMEDIATE'); document(did)
    saved = attachment_list(did)
    if len(saved) >= 5 or sum(x['size'] for x in saved) + len(data) > 20 * 1024 * 1024:
        fail('Keep supporting files to five files and 20 MB in total.')
    db().execute('INSERT INTO billing_attachments(document_id,filename,mime,content,sha256,created_at) VALUES (?,?,?,?,?,?)',
                 (did, name, mime, data, hashlib.sha256(data).hexdigest(), now()))
    audit('invoice supporting file added', did); db().commit()
    return jsonify(attachment_list(did))


@bp.get('/attachment-receipts')
@owner
def receipt_choices():
    from billing import rows
    return jsonify(rows('SELECT id,filename FROM receipts WHERE user_id=? ORDER BY rowid DESC LIMIT 200', (g.user['id'],)))


@bp.route('/documents/<int:did>/attachments/<int:aid>', methods=['GET', 'DELETE'])
@owner
def attachment(did, aid):
    from billing import db, document, audit
    document(did); row = selected_attachments(did, [aid])[0]
    if request.method == 'DELETE':
        db().execute('DELETE FROM billing_attachments WHERE id=? AND document_id=?', (aid, did))
        audit('invoice supporting file removed', did); db().commit(); return jsonify(ok=True)
    result = send_file(io.BytesIO(row['content']), mimetype=row['mime'], as_attachment=True, download_name=row['filename'])
    result.headers['Cache-Control'] = 'no-store'
    return result
