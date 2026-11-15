"""Owner-issued quote links and durable client acceptance."""
import hashlib
import io
import re
import secrets
from urllib.parse import urlsplit

from flask import Blueprint, jsonify, make_response, redirect, render_template, request, send_file, url_for
from billing import bp, owner

public = Blueprint('quote_acceptance', __name__, url_prefix='/quote')


def public_origin():
    from billing import settings
    address = settings('access', {}).get('login_url', '')
    try:
        url = urlsplit(address)
        if url.scheme == 'https' and url.hostname and not (
            url.username or url.password or url.query or url.fragment or url.path not in ('', '/')
        ):
            return address.rstrip('/')
    except ValueError:
        pass
    return ''


def pending(doc):
    from billing import local_today
    return (doc['kind'] == 'quote' and doc['state'] in ('draft', 'issued')
            and doc['issue_date'] <= local_today() <= doc['due_date'])


def email_link(doc, recipient):
    from billing import db, fail
    origin = public_origin()
    if not pending(doc) or not origin:
        fail('An online acceptance link requires a current quote and an HTTPS Expense Pilot address.', 409)
    token = secrets.token_urlsafe(32)
    db().execute("""
        INSERT INTO billing_quote_acceptance(document_id,token_hash,recipient)
        VALUES (?,?,?)
        ON CONFLICT(document_id) DO UPDATE SET token_hash=excluded.token_hash,recipient=excluded.recipient
    """, (doc['id'], token_hash(token), recipient))
    return origin + url_for('quote_acceptance.view', token=token)


def token_hash(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def active_link(doc):
    from billing import local_today
    return doc['state'] == 'accepted' or (doc['state'] == 'issued' and doc['due_date'] >= local_today())


def details(doc):
    from billing import one
    if doc['kind'] != 'quote':
        return None
    row = one("""
        SELECT recipient,accepted_name,accepted_at,token_hash IS NOT NULL AS linked
        FROM billing_quote_acceptance WHERE document_id=?
    """, (doc['id'],))
    if row:
        row['linked'] = bool(row['linked'] and active_link(doc))
    return row


def revoke(did):
    from billing import db
    return db().execute("""
        UPDATE billing_quote_acceptance SET token_hash=NULL WHERE document_id=? AND token_hash IS NOT NULL
    """, (did,)).rowcount


@bp.delete('/documents/<int:did>/acceptance-link')
@owner
def revoke_link(did):
    from billing import audit, body, db, document, fail, revision
    data = body()
    db().execute('BEGIN IMMEDIATE')
    doc = document(did)
    revision(doc, data)
    if doc['kind'] != 'quote':
        fail('Quote not found.', 404)
    if revoke(did):
        db().execute('UPDATE billing_documents SET version=version+1 WHERE id=?', (did,))
        audit('quote acceptance link revoked', did)
    db().commit()
    return jsonify(ok=True)


def find(token):
    from billing import document, one
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None, None
    link = one('SELECT * FROM billing_quote_acceptance WHERE token_hash=?', (token_hash(token),))
    if not link:
        return None, None
    doc = document(link['document_id'])
    if not active_link(doc):
        return None, None
    return doc, link


def page(doc=None, link=None, *, message='', status=200):
    from billing import aud, date_au
    response = make_response(render_template('quote.html', doc=doc, link=link,
                                             message=message, aud=aud, date_au=date_au), status)
    return response


@public.after_request
def privacy(response):
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response


@public.route('/<token>', methods=['GET', 'POST'])
def view(token):
    from billing import audit, db, now
    if request.method == 'GET':
        doc, link = find(token)
        return page(doc, link) if doc else page(status=404)

    # The unguessable link authorises this one quote. Email scanners only perform GET.
    if request.headers.get('Sec-Fetch-Site') in ('cross-site', 'same-site'):
        return page(status=403)
    form = request.form
    name = form.get('full_name', '').strip()
    consent = form.get('authorised') == 'yes'
    db().execute('BEGIN IMMEDIATE')
    doc, link = find(token)
    if not doc:
        return page(status=404)
    if doc['state'] == 'accepted':
        db().rollback()
        return redirect(url_for('quote_acceptance.view', token=token), code=303)
    if not consent or not 1 <= len(name) <= 120 or any(ord(char) < 32 or ord(char) == 127 for char in name):
        db().rollback()
        return page(doc, link, message='Enter your full name and confirm you are authorised to accept.', status=400)

    db().execute('UPDATE billing_quote_acceptance SET accepted_name=?,accepted_at=? WHERE document_id=?',
                 (name, now(), doc['id']))
    db().execute("UPDATE billing_documents SET state='accepted',version=version+1 WHERE id=?", (doc['id'],))
    audit('quote accepted online', doc['id'])
    db().commit()
    return redirect(url_for('quote_acceptance.view', token=token), code=303)


@public.get('/<token>/pdf')
def pdf(token):
    from billing import pdf_document
    doc, _ = find(token)
    if not doc:
        return page(status=404)
    return send_file(io.BytesIO(pdf_document(doc)), mimetype='application/pdf',
                     as_attachment=True, download_name=doc['number'] + '.pdf')
