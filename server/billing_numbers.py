"""Invoice sequences under the caller's write lock."""
import re


def sequence_number(number, prefix, *, legacy=False):
    """A numeric invoice in the configured sequence, or a legacy bare number."""
    if number.lower().startswith(prefix.lower()):
        suffix = number[len(prefix):]
    elif legacy:
        suffix = number
    else:
        return None
    return int(suffix) if re.fullmatch(r'[0-9]{1,18}', suffix) else None


def manual_number(number, prefix):
    if not isinstance(number, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,49}', number.strip()):
        from billing import fail
        fail('Enter an invoice number with letters, numbers, spaces, full stops, underscores or hyphens.')
    number = number.strip()
    if number.lower().startswith(prefix.lower()):
        number = number[len(prefix):].strip()
    if not number:
        from billing import fail
        fail('Enter a number after the invoice prefix.')
    return prefix + number


def validate_number(number, exclude=None):
    from billing import fail, one
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,49}', number):
        fail('Use up to 50 letters, numbers, spaces, full stops, underscores or hyphens, including the prefix.')
    if one('SELECT id FROM billing_documents WHERE number=? COLLATE NOCASE AND id<>?', (number, exclude or -1)):
        fail('That document number is already in use. Choose another number.', 409)
    return number


def allocate_number(values, custom_number=None):
    from billing import db, fail, one
    kind = values['kind']
    prefix = values['business'][kind + '_prefix']
    if custom_number not in (None, ''):
        if kind != 'invoice':
            fail('Custom numbers are available for invoices only.')
        return validate_number(manual_number(custom_number, prefix))
    n = one('SELECT next_number FROM billing_counters WHERE kind=?', (kind,))['next_number']
    while one('SELECT id FROM billing_documents WHERE number=? COLLATE NOCASE', (f'{prefix}{n:04d}',)):
        n += 1
    if kind == 'quote':
        db().execute('UPDATE billing_counters SET next_number=? WHERE kind=?', (n + 1, kind))
    return f'{prefix}{n:04d}'


def record_issued(doc):
    from billing import db
    if doc['kind'] != 'invoice':
        return
    n = sequence_number(doc['number'], doc['business'].get('invoice_prefix', 'INV-'), legacy=True)
    if n is not None:
        db().execute("UPDATE billing_counters SET next_number=MAX(next_number,?) WHERE kind='invoice'", (n + 1,))


def change_number(doc, number, bump_version=True):
    from billing import audit, db, fail, one
    if doc['kind'] != 'invoice':
        fail('Only invoice numbers can be changed.')
    from billing_revisions import editable
    editable(doc)
    if isinstance(number, str) and number.strip() == doc['number']:
        return False
    number = validate_number(manual_number(number, doc['business'].get('invoice_prefix', 'INV-')), doc['id'])
    if number == doc['number']:
        return False
    if one("SELECT id FROM billing_outbox WHERE document_id=? AND state IN ('sending','unknown')", (doc['id'],)):
        fail('Resolve the pending or uncertain email delivery before changing this invoice number.', 409)
    db().execute('UPDATE billing_documents SET number=?,version=version+? WHERE id=?', (number, int(bump_version), doc['id']))
    audit('invoice number changed', f"{doc['id']}: {doc['number']} → {number}")
    return True
