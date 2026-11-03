"""Reviewable amendments of issued invoices, with previous revisions retained."""

def editable(doc):
    from billing import fail, one
    if doc['kind']=='invoice' and doc['paid_cents']>0 and doc['balance_cents']<=0:
        fail('Paid invoices cannot be edited. Reverse an incorrect payment record first.',409)
    if doc['state'] in ('void','converted'):
        fail('Void or converted documents cannot be edited.',409)
    if one("SELECT id FROM billing_outbox WHERE document_id=? AND state IN ('sending','unknown')",(doc['id'],)):
        fail('Resolve the pending or uncertain email delivery before editing this document.',409)


def remember(doc):
    from billing import db, g, json, now
    db().execute('INSERT INTO billing_revision_history(document_id,version,user_id,previous,changed_at) VALUES (?,?,?,?,?)',
                 (doc['id'],doc['version'],g.user['id'],json.dumps(doc),now()))


def check_payments(doc, values):
    from billing import fail, one
    if not doc['paid_cents']: return
    if values['client_id']!=doc['client_id']:
        fail('Keep the client while this invoice has payments.',409)
    if values['total_cents']<doc['paid_cents']:
        fail('The revised total cannot be less than payments already received.',409)
    first=one('SELECT MIN(date) AS date FROM billing_payments WHERE document_id=? AND reversed_at IS NULL',(doc['id'],))['date']
    if first and values['issue_date']>first:
        fail('The issue date cannot be after a recorded payment.',409)
