"""Invoice number allocation, reuse and amendment under the caller's write lock."""
import re


def validate_number(number, exclude=None):
    from billing import fail, one
    if not isinstance(number, str):
        fail('Enter an invoice number.')
    number = number.strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,49}', number):
        fail('Use 1–50 letters, numbers, spaces, full stops, underscores or hyphens for the invoice number.')
    if one('SELECT id FROM billing_documents WHERE number=? COLLATE NOCASE AND id<>?', (number, exclude or -1)):
        fail('That document number is already in use. Choose another number.', 409)
    return number


def allocate_number(values, custom_number=None):
    from billing import db, fail, one
    kind = values['kind']
    if custom_number not in (None, ''):
        if kind != 'invoice':
            fail('Custom numbers are available for invoices only.')
        number = validate_number(custom_number)
        db().execute('DELETE FROM billing_reusable_invoice_numbers WHERE number=? COLLATE NOCASE', (number,))
        return number
    if kind == 'invoice':
        while True:
            saved = one('SELECT * FROM billing_reusable_invoice_numbers ORDER BY id DESC LIMIT 1')
            if not saved:
                break
            db().execute('DELETE FROM billing_reusable_invoice_numbers WHERE id=?', (saved['id'],))
            if not one('SELECT id FROM billing_documents WHERE number=? COLLATE NOCASE', (saved['number'],)):
                return saved['number']
    n = one('SELECT next_number FROM billing_counters WHERE kind=?', (kind,))['next_number']
    prefix = values['business'][kind + '_prefix']
    number = f'{prefix}{n:04d}'
    while one('SELECT id FROM billing_documents WHERE number=? COLLATE NOCASE', (number,)):
        n += 1
        number = f'{prefix}{n:04d}'
    db().execute('UPDATE billing_counters SET next_number=? WHERE kind=?', (n + 1, kind))
    return number


def change_number(doc, number, bump_version=True):
    from billing import audit, db, fail, one
    if doc['kind'] != 'invoice':
        fail('Only invoice numbers can be changed.')
    number = validate_number(number, doc['id'])
    if number == doc['number']:
        return
    if one("SELECT id FROM billing_outbox WHERE document_id=? AND state IN ('sending','unknown')", (doc['id'],)):
        fail('Resolve the pending or uncertain email delivery before changing this invoice number.', 409)
    db().execute('DELETE FROM billing_reusable_invoice_numbers WHERE number=? COLLATE NOCASE', (number,))
    db().execute('UPDATE billing_documents SET number=?,version=version+? WHERE id=?', (number, int(bump_version), doc['id']))
    audit('invoice number changed', f"{doc['id']}: {doc['number']} → {number}")
