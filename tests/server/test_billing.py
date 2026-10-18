"""Billing regression tests. SMTP is mocked: no test sends real email."""
import csv
import io
import json
import os
import secrets
import smtplib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import test_app as base
from app import app, db
import billing
from billing_core import calculate_lines, advance_date, pdf_document


class BillingTest(unittest.TestCase):
    call = base.AppTest.call
    login = base.AppTest.login
    expense = base.AppTest.expense

    def setUp(self):
        base.AppTest.setUp(self)
        self.today = billing.local_today()
        result = self.call(self.owner, 'billing/settings', dict(name='Example Flight Testing', abn='12 345 678 901', gst_registered=True,
                          payment_details='Example bank details', email='owner@example.test'), 'PUT')
        self.assertEqual(result.status_code, 200, result.json)
        self.cid = self.call(self.owner, 'billing/clients', dict(name='Example Client', email='client@example.test', terms=14,
                                                               notes='Private internal note')).json['id']

    def create(self, **kw):
        data = dict(kind='invoice', client_id=self.cid, issue_date=self.today, due_date=self.today, tax_mode='exclusive',
                    lines=[dict(description='Testing services', quantity='2', unit_price='50.00', tax='gst')])
        data.update(kw)
        response = self.call(self.owner, 'billing/documents', data)
        self.assertEqual(response.status_code, 200, response.json)
        return self.get(response.json['id'])

    def get(self, did):
        result = self.owner.get(f'/api/billing/documents/{did}')
        self.assertEqual(result.status_code, 200, result.json)
        return result.json

    def action(self, doc, action):
        return self.call(self.owner, f"billing/documents/{doc['id']}/action", dict(version=doc['version'], action=action))

    def issue(self, doc):
        response = self.action(doc, 'issue')
        self.assertEqual(response.status_code, 200, response.json)
        return self.get(doc['id'])

    def pay(self, doc, amount, key=None):
        return self.call(self.owner, f"billing/documents/{doc['id']}/payments", dict(version=doc['version'], amount=amount,
                         date=self.today, reference='Test transfer', request_key=key or secrets.token_hex(24)))

    def email_config(self):
        data = dict(host='smtp.example.test', port=465, security='ssl', username='owner@example.test',
                    from_email='owner@example.test', from_name='Example Business', password='smtp-test-secret-123')
        result = self.call(self.owner, 'billing/email-settings', data, 'PUT')
        self.assertEqual(result.status_code, 200, result.json)
        return data

    def test_separate_wording_defaults_and_existing_document_retention(self):
        legacy = self.create()
        self.assertEqual(legacy['notes'], 'Thank you for your business.')
        defaults = self.owner.get('/api/billing/settings').json['defaults']
        self.assertEqual(defaults['invoice_payment_details'], 'Example bank details')
        values = dict(invoice_notes='Invoice terms', quote_notes='Quote acceptance terms',
                      invoice_payment_details='New bank details', quote_valid_days=30,
                      invoice_email_subject='Invoice {number}', invoice_email_body='Pay by {due_date}',
                      quote_email_subject='Quote {number}', quote_email_body='Accept by {due_date}')
        self.assertEqual(self.call(self.owner, 'billing/document-defaults', values, 'PUT').status_code, 200)
        self.assertEqual(self.get(legacy['id'])['notes'], legacy['notes'])
        invoice, quote = self.create(), self.create(kind='quote')
        self.assertEqual(invoice['notes'], 'Invoice terms')
        self.assertEqual(invoice['payment_details'], 'New bank details')
        self.assertEqual(quote['notes'], 'Quote acceptance terms')
        self.assertEqual(quote['payment_details'], '')
        self.assertEqual(self.create(notes='')['notes'], '')
        for doc, prefix in ((invoice, 'Pay'), (quote, 'Accept')):
            draft = self.owner.get(f"/api/billing/documents/{doc['id']}/email-draft").json
            self.assertEqual(draft['body'], prefix + ' by ' + date.fromisoformat(self.today).strftime('%d/%m/%Y'))
        for client in (self.agent, self.staff):
            self.assertEqual(self.call(client, 'billing/document-defaults', values, 'PUT').status_code, 403)
        for bad in ({'quote_valid_days': -1}, {'invoice_notes': 'x'*5001}, {'quote_email_subject': 'a\nb'}, {'quote_email_body': ''}):
            self.assertEqual(self.call(self.owner, 'billing/document-defaults', bad, 'PUT').status_code, 400)
        self.assertEqual(self.owner.get('/api/billing/settings').json['defaults'], values)
        self.assertNotIn('password_encrypted', str(self.agent.get('/api/billing/settings').json))
        from pypdf import PdfReader
        pdf = self.owner.get(f"/api/billing/documents/{quote['id']}/pdf")
        text = ''.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf.data)).pages)
        self.assertIn(date.fromisoformat(self.today).strftime('%d/%m/%Y'), text)
        self.assertIn('Quote acceptance terms', text)
        self.assertNotIn('Thank you for your business.', text)

    def test_smtp_edit_preserves_legacy_wording(self):
        config = self.email_config()
        config.update(subject='Existing custom subject', body='Existing custom message')
        self.assertEqual(self.call(self.owner, 'billing/email-settings', config, 'PUT').status_code, 200)
        config.pop('subject'); config.pop('body')
        self.assertEqual(self.call(self.owner, 'billing/email-settings', config, 'PUT').status_code, 200)
        defaults = self.owner.get('/api/billing/settings').json['defaults']
        self.assertEqual(defaults['invoice_email_subject'], 'Existing custom subject')
        self.assertEqual(defaults['quote_email_body'], 'Existing custom message')

    def test_billing_permissions_and_csrf(self):
        did = self.create()['id']
        for client in (self.staff2,):
            for path in ('documents', f'documents/{did}', f'documents/{did}/pdf', 'clients', 'settings', 'report', 'time', 'schedules'):
                self.assertEqual(client.get('/api/billing/' + path).status_code, 401, path)
        self.assertEqual(app.test_client().get('/api/billing/documents').status_code, 401)
        self.assertEqual(self.owner.post('/api/billing/documents', json={}).status_code, 403)
        for path in ('settings', 'clients', 'time', 'schedules', 'services'):
            self.assertEqual(self.agent.get('/api/billing/' + path).status_code, 200)
        self.assertEqual(self.call(self.agent, 'billing/documents', {}).status_code, 403)

    def test_agent_all_documents_and_internal_notes(self):
        doc = self.issue(self.create())
        self.assertEqual(self.agent.get(f"/api/billing/documents/{doc['id']}").status_code, 200)
        self.assertEqual(self.agent.get(f"/api/billing/documents/{doc['id']}/pdf").status_code, 200)
        listed = self.agent.get('/api/billing/documents').json
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]['description'], 'Testing services')
        self.assertNotIn('lines', listed[0])
        self.assertEqual(self.pay(doc, '20').status_code, 200)
        doc = self.get(doc['id'])
        self.call(self.owner, f"billing/documents/{doc['id']}/sharing", dict(version=doc['version'], shared=True), 'PUT')
        result = self.agent.get(f"/api/billing/documents/{doc['id']}")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('Private internal note', result.data.decode())
        self.assertNotIn('notes', result.json['client'])
        self.assertEqual(result.json['paid_cents'], 2000)
        self.assertEqual(result.json['emails'], [])
        self.assertEqual(self.agent.get('/api/billing/report').json['received_cents'], 2000)
        self.assertEqual(self.call(self.agent, f"billing/documents/{doc['id']}/send", {}).status_code, 403)

    def test_gst_rounding_inclusive_exclusive_discounts(self):
        values = calculate_lines([dict(description='A', quantity=3, unit_price='33.33', tax='gst', discount=10),
                                  dict(description='B', quantity=1, unit_price='20.00', tax='gst_free')], 'exclusive', True)
        self.assertEqual((values['subtotal_cents'], values['gst_cents'], values['total_cents']), (10999, 900, 11899))
        values = calculate_lines([dict(description='A', quantity=1, unit_price='110.00', tax='gst')], 'inclusive', True)
        self.assertEqual((values['subtotal_cents'], values['gst_cents'], values['total_cents']), (10000, 1000, 11000))
        values = calculate_lines([dict(description='A', quantity=1, unit_price='0.05', tax='gst')], 'exclusive', True)
        self.assertEqual(values['gst_cents'], 1)

    def test_reject_invalid_billing_numbers(self):
        for change in ({'quantity':'NaN'}, {'unit_price':'Infinity'}, {'quantity':-1}, {'unit_price':'1.001'}, {'discount':101}):
            with self.assertRaises(ValueError):
                calculate_lines([{**dict(description='A', quantity=1, unit_price='10'), **change}], 'exclusive', True)
        with self.assertRaises(ValueError):
            calculate_lines([dict(description='A', unit_price=20)], 'exclusive', False)
        data = dict(client_id=self.cid, issue_date=self.today, due_date='not-a-date', lines=[])
        self.assertEqual(self.call(self.owner, 'billing/documents', data).status_code, 400)

    def test_numbering_unique_and_reuses_deleted_invoice(self):
        first = self.create()
        second = self.create(kind='quote')
        self.assertEqual(first['number'], 'INV-0001')
        self.assertEqual(second['number'], 'QUO-0001')
        self.assertEqual(self.call(self.owner, f"billing/documents/{first['id']}", {'version':first['version']}, 'DELETE').status_code, 200)
        self.assertEqual(self.create()['number'], 'INV-0001')

    def test_issued_snapshot_is_immutable(self):
        doc = self.issue(self.create())
        self.call(self.owner, 'billing/settings', {'name':'Changed Business'}, 'PUT')
        self.call(self.owner, f'billing/clients/{self.cid}', {'name':'Changed Client', 'email':'other@example.test', 'terms':7}, 'PUT')
        saved = self.get(doc['id'])
        self.assertEqual(saved['business']['name'], 'Example Flight Testing')
        self.assertEqual(saved['client']['name'], 'Example Client')
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}", {**saved,'version':saved['version']}, 'PUT').status_code, 409)

    def test_deleted_issued_and_void_invoice_numbers_become_reusable(self):
        for state in ('issued', 'void'):
            with self.subTest(state=state):
                doc = self.issue(self.create())
                if state == 'void':
                    self.assertEqual(self.action(doc, 'void').status_code, 200)
                    doc = self.get(doc['id'])
                path = f"billing/documents/{doc['id']}"
                self.assertEqual(self.call(self.owner, path, {'version':doc['version']}, 'DELETE').status_code, 200)
                self.assertEqual(self.owner.get('/api/' + path).status_code, 404)
                self.assertEqual(self.owner.get('/api/' + path + '/pdf').status_code, 404)
                self.assertEqual(self.owner.get('/api/billing/documents').json, [])
                with app.app_context():
                    record = db().execute("SELECT entity FROM audit WHERE action='invoice deleted' ORDER BY id DESC LIMIT 1").fetchone()
                    self.assertIn(doc['number'], record['entity'])
        self.assertEqual(self.create()['number'], 'INV-0001')

    @patch('billing.smtplib.SMTP_SSL')
    def test_delete_paid_invoice_cleans_history_and_updates_income(self, smtp):
        self.email_config()
        kept = self.issue(self.create())
        self.assertEqual(self.pay(kept, '11').status_code, 200)
        for amount in ('40', '110'):
            with self.subTest(amount=amount):
                doc = self.create()
                path = f"billing/documents/{doc['id']}"
                draft = self.owner.get('/api/' + path + '/email-draft').json
                self.assertEqual(self.call(self.owner, path + '/send', draft).json['state'], 'sent')
                doc = self.get(doc['id'])
                payment = self.pay(doc, '10').json['id']
                doc = self.get(doc['id'])
                self.assertEqual(self.call(self.owner, f'billing/payments/{payment}/reverse',
                                          dict(version=doc['version'], reason='Incorrect record')).status_code, 200)
                doc = self.get(doc['id'])
                self.assertEqual(self.pay(doc, amount).status_code, 200)
                doc = self.get(doc['id'])
                self.assertEqual(self.call(self.owner, path + '/wording',
                                          dict(version=doc['version'], descriptions=['Corrected wording']), 'PUT').status_code, 200)
                doc = self.get(doc['id'])
                self.assertEqual(len(doc['payments']), 2)
                self.assertEqual(len(doc['emails']), 1)
                self.assertGreater(self.owner.get('/api/billing/report').json['received_cents'], 1100)
                self.assertEqual(self.call(self.owner, path, {'version':doc['version']}, 'DELETE').status_code, 200)
                report = self.owner.get('/api/billing/report').json
                self.assertEqual((report['received_cents'], report['gst_cents'], report['net_cents']), (1100, 100, 1000))
                self.assertEqual([r['invoice'] for r in report['records']], [kept['number']])
                self.assertEqual(self.get(kept['id'])['paid_cents'], 1100)
                with app.app_context():
                    for table in ('billing_payments', 'billing_outbox', 'billing_wording_history'):
                        self.assertEqual(db().execute(f'SELECT count(*) FROM {table} WHERE document_id=?', (doc['id'],)).fetchone()[0], 0)
                    self.assertEqual(db().execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_delete_invoice_checks_permissions_and_revision(self):
        stale = self.issue(self.create())
        self.assertEqual(self.pay(stale, '40').status_code, 200)
        doc = self.get(stale['id'])
        path = f"billing/documents/{doc['id']}"
        payload = {'version':doc['version']}
        self.assertEqual(self.owner.delete('/api/' + path, json=payload).status_code, 403)
        self.assertEqual(self.call(app.test_client(), path, payload, 'DELETE').status_code, 401)
        self.assertEqual(self.call(self.agent, path, payload, 'DELETE').status_code, 403)
        self.assertEqual(self.call(self.owner, path, {'version':stale['version']}, 'DELETE').status_code, 409)
        self.assertEqual(self.get(doc['id']), doc)
        uid = next(u['id'] for u in self.owner.get('/api/users').json if u['email']=='agent@example.test')
        self.assertEqual(self.call(self.owner, f'users/{uid}/permission', {'permission':'read_write'}, 'PUT').status_code, 200)
        self.assertEqual(self.call(self.agent, path, payload, 'DELETE').status_code, 200)

    def test_delete_blocks_unresolved_delivery_and_issued_quotes(self):
        doc = self.issue(self.create())
        self.assertEqual(self.pay(doc, '40').status_code, 200)
        doc = self.get(doc['id'])
        with app.app_context():
            oid = db().execute('INSERT INTO billing_outbox(document_id,recipient,subject,body,state,request_key,created_at) VALUES (?,?,?,?,?,?,?)',
                               (doc['id'], 'client@example.test', 'Invoice', 'Attached', 'sending', secrets.token_hex(24), billing.now())).lastrowid
            db().commit()
        for state in ('sending', 'unknown'):
            with app.app_context():
                db().execute('UPDATE billing_outbox SET state=? WHERE id=?', (state, oid))
                db().commit()
            before = self.get(doc['id'])
            response = self.call(self.owner, f"billing/documents/{doc['id']}", {'version':doc['version']}, 'DELETE')
            self.assertEqual(response.status_code, 409)
            self.assertIn('email delivery', response.json['error'])
            self.assertEqual(self.get(doc['id']), before)
        self.assertEqual(self.call(self.owner, f'billing/emails/{oid}/resolve', {'state':'failed'}).status_code, 200)
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}", {'version':doc['version']}, 'DELETE').status_code, 200)
        quote = self.issue(self.create(kind='quote'))
        self.assertEqual(self.call(self.owner, f"billing/documents/{quote['id']}", {'version':quote['version']}, 'DELETE').status_code, 409)
        self.assertEqual(self.get(quote['id']), quote)

    def test_wording_updates_pdf_without_changing_financial_records(self):
        for kind in ('invoice', 'quote'):
            doc = self.issue(self.create(kind=kind))
            if kind == 'invoice':
                self.assertEqual(self.pay(doc, '40').status_code, 200)
                doc = self.get(doc['id'])
            payload = dict(version=doc['version'], descriptions=['Updated examiner services'], reference='Corrected reference', notes='Updated terms', payment_details='Updated payment instructions')
            path = f"billing/documents/{doc['id']}/wording"
            self.assertEqual(self.call(self.agent, path, payload, 'PUT').status_code, 403)
            self.assertEqual(self.call(self.staff, path, payload, 'PUT').status_code, 403)
            self.assertEqual(self.call(self.owner, path, {**payload, 'total_cents':1}, 'PUT').status_code, 400)
            self.assertEqual(self.call(self.owner, path, {**payload, 'descriptions':[]}, 'PUT').status_code, 400)
            self.assertEqual(self.call(self.owner, path, payload, 'PUT').status_code, 200)
            saved = self.get(doc['id'])
            for key in ('number','state','client','business','issue_date','due_date','tax_mode','subtotal_cents','gst_cents','total_cents','paid_cents','balance_cents','payments'):
                self.assertEqual(saved[key], doc[key], key)
            self.assertEqual(saved['lines'][0]['description'], 'Updated examiner services')
            self.assertEqual(saved['lines'][0]['unit_price'], doc['lines'][0]['unit_price'])
            self.assertEqual(self.call(self.owner, path, payload, 'PUT').status_code, 409)
            from pypdf import PdfReader
            pdf = self.owner.get(f"/api/billing/documents/{doc['id']}/pdf")
            text = ''.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf.data)).pages)
            self.assertIn('Updated examiner services', text)
            self.assertIn('Updated terms', text)
            with app.app_context():
                previous = json.loads(db().execute('SELECT previous FROM billing_wording_history WHERE document_id=?', (doc['id'],)).fetchone()['previous'])
                self.assertEqual(previous['lines'][0]['description'], doc['lines'][0]['description'])
            if kind == 'quote':
                self.assertEqual(self.action(saved, 'accepted').status_code, 200)
                saved = self.get(doc['id'])
                self.assertEqual(self.action(saved, 'convert').status_code, 200)
                payload['version'] = self.get(doc['id'])['version']
                self.assertEqual(self.call(self.owner, path, payload, 'PUT').status_code, 409)

    def test_business_name_in_authenticated_session(self):
        for client in (self.owner, self.staff, self.agent):
            self.assertEqual(client.get('/api/session').json['business_name'], 'Example Flight Testing')
        self.assertEqual(app.test_client().get('/api/session').json['business_name'], '')

    def test_stale_draft_update_does_not_overwrite(self):
        doc = self.create()
        data = {**doc, 'notes':'Updated once'}
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}", data, 'PUT').status_code, 200)
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}", data, 'PUT').status_code, 409)

    def test_quote_conversion_and_duplicate_guard(self):
        quote = self.issue(self.create(kind='quote'))
        self.assertEqual(self.action(quote, 'convert').status_code, 409)
        self.assertEqual(self.action(quote, 'accepted').status_code, 200)
        quote = self.get(quote['id'])
        response = self.action(quote, 'convert')
        self.assertEqual(response.status_code, 200)
        invoice = self.get(response.json['id'])
        self.assertEqual(invoice['kind'], 'invoice')
        self.assertEqual(invoice['total_cents'], quote['total_cents'])
        self.assertEqual(self.action(quote, 'convert').status_code, 409)
        self.assertEqual(self.call(self.owner, f"billing/documents/{invoice['id']}", {'version':invoice['version']}, 'DELETE').status_code, 200)
        self.assertEqual(self.get(quote['id'])['state'], 'accepted')
        response = self.action(self.get(quote['id']), 'convert')
        invoice = self.issue(self.get(response.json['id']))
        self.assertEqual(self.call(self.owner, f"billing/documents/{invoice['id']}", {'version':invoice['version']}, 'DELETE').status_code, 200)
        self.assertEqual(self.get(quote['id'])['state'], 'accepted')

    def test_partial_full_payment_and_idempotency(self):
        doc = self.issue(self.create())
        key = secrets.token_hex(24)
        first = self.pay(doc, '40', key)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.pay(doc, '40', key).json['id'], first.json['id'])
        doc = self.get(doc['id'])
        self.assertEqual((doc['paid_cents'],doc['balance_cents'],doc['status']), (4000,7000,'part_paid'))
        self.assertIsNone(doc['paid_date'])
        self.assertEqual(self.pay(doc, '71').status_code, 409)
        self.assertEqual(self.pay(doc, '70').status_code, 200)
        doc = self.get(doc['id'])
        self.assertEqual(doc['status'], 'paid')
        self.assertEqual(doc['paid_date'], self.today)
        self.assertEqual(len(doc['payments']), 2)

    def test_reverse_payment_audit_then_void(self):
        doc = self.issue(self.create())
        payment = self.pay(doc, '110').json['id']
        doc = self.get(doc['id'])
        self.assertEqual(self.action(doc, 'void').status_code, 409)
        self.assertEqual(self.call(self.owner, f'billing/payments/{payment}/reverse', dict(version=doc['version'], reason='Incorrect entry')).status_code, 200)
        doc = self.get(doc['id'])
        self.assertEqual(doc['balance_cents'], 11000)
        self.assertIsNone(doc['paid_date'])
        self.assertEqual(self.action(doc, 'void').status_code, 200)
        self.assertEqual(self.owner.get('/api/billing/report').json['received_cents'], 0)

    def test_income_report_dates_and_gst_partial_rounding(self):
        doc = self.issue(self.create(lines=[dict(description='Small amount', quantity=1, unit_price='.05', tax='gst')]))
        for _ in range(6):
            self.assertEqual(self.pay(doc, '.01').status_code, 200)
            doc = self.get(doc['id'])
        report = self.owner.get('/api/billing/report').json
        self.assertEqual((report['received_cents'],report['gst_cents'],report['net_cents']), (6,1,5))
        yesterday = (date.fromisoformat(self.today)-timedelta(days=1)).isoformat()
        self.assertEqual(self.owner.get('/api/billing/report?start='+yesterday+'&end='+yesterday).json['received_cents'], 0)
        csv_data = list(csv.reader(io.StringIO(self.owner.get('/api/billing/report?format=csv').data.decode('utf-8-sig'))))
        self.assertEqual(len(csv_data), 7)
        self.assertEqual(csv_data[1][0], date.fromisoformat(self.today).strftime('%d/%m/%Y'))

    def test_email_secret_encryption_retention_and_clear(self):
        config = self.email_config()
        returned = self.owner.get('/api/billing/settings')
        self.assertTrue(returned.json['password_saved'])
        self.assertNotIn(config['password'], returned.data.decode())
        with app.app_context():
            encrypted = billing.mail_settings()['password_encrypted']
            self.assertNotIn(config['password'], encrypted)
            self.assertEqual(billing.secret_box().decrypt(encrypted.encode()).decode(), config['password'])
        config['password'] = ''
        self.call(self.owner, 'billing/email-settings', config, 'PUT')
        self.assertTrue(self.owner.get('/api/billing/settings').json['password_saved'])
        config['clear_password'] = True
        self.call(self.owner, 'billing/email-settings', config, 'PUT')
        self.assertFalse(self.owner.get('/api/billing/settings').json['password_saved'])

    def test_email_header_injection_blocked(self):
        config = self.email_config()
        config['from_name'] = 'Business\nBcc: attacker@example.test'
        self.assertEqual(self.call(self.owner, 'billing/email-settings', config, 'PUT').status_code, 400)
        doc = self.create()
        draft = self.owner.get(f"/api/billing/documents/{doc['id']}/email-draft").json
        draft['recipient'] = 'one@example.test,two@example.test'
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}/send", draft).status_code, 400)

    @patch('billing.smtplib.SMTP_SSL')
    def test_email_pdf_delivery_and_duplicate_click(self, smtp):
        self.email_config()
        doc = self.create()
        draft = self.owner.get(f"/api/billing/documents/{doc['id']}/email-draft").json
        response = self.call(self.owner, f"billing/documents/{doc['id']}/send", draft)
        self.assertEqual(response.json['state'], 'sent', response.json)
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}/send", draft).json['state'], 'sent')
        smtp.return_value.send_message.assert_called_once()
        outgoing = smtp.return_value.send_message.call_args.args[0]
        attachment = list(outgoing.iter_attachments())[0]
        self.assertTrue(attachment.get_payload(decode=True).startswith(b'%PDF'))
        self.assertEqual(attachment.get_content_type(), 'application/pdf')
        self.assertEqual(attachment.get_filename(), doc['number']+'.pdf')
        from pypdf import PdfReader
        attached_text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(attachment.get_payload(decode=True))).pages)
        for text in ('TAX INVOICE',doc['number'],'Example Flight Testing','Example Client','PAYMENT DETAILS'):
            self.assertIn(text,attached_text)
        self.assertEqual(outgoing['To'], 'client@example.test')
        smtp.return_value.login.assert_called_once_with('owner@example.test','smtp-test-secret-123')
        self.assertEqual(self.get(doc['id'])['state'], 'issued')

    @patch('billing.smtplib.SMTP_SSL')
    def test_email_uncertainty_requires_reconciliation(self, smtp):
        self.email_config()
        doc = self.create()
        smtp.return_value.send_message.side_effect = TimeoutError()
        draft = self.owner.get(f"/api/billing/documents/{doc['id']}/email-draft").json
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}/send", draft).json['state'], 'unknown')
        another = self.owner.get(f"/api/billing/documents/{doc['id']}/email-draft").json
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}/send", another).status_code, 409)
        record = self.get(doc['id'])['emails'][0]
        self.assertEqual(self.call(self.owner, f"billing/emails/{record['id']}/resolve", {'state':'sent'}).status_code, 200)

    @patch('billing.smtplib.SMTP_SSL')
    def test_mail_quit_failure_does_not_mark_sent_message_failed(self, smtp):
        self.email_config()
        smtp.return_value.quit.side_effect = smtplib.SMTPServerDisconnected()
        response = self.call(self.owner, 'billing/email-test', {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['state'], 'sent')

    @patch('billing.smtplib.SMTP')
    def test_starttls_precedes_authentication(self, smtp):
        config = self.email_config()
        config.update(security='starttls', port=587)
        self.call(self.owner, 'billing/email-settings', config, 'PUT')
        self.assertEqual(self.call(self.owner, 'billing/email-test', {}).status_code, 200)
        names = [x[0] for x in smtp.return_value.method_calls]
        self.assertLess(names.index('starttls'), names.index('login'))
        self.assertLess(names.index('login'), names.index('send_message'))

    def test_recurring_month_end_and_duplicate_generation(self):
        self.assertEqual(advance_date('2026-01-31','monthly',31),'2026-02-28')
        self.assertEqual(advance_date('2026-02-28','monthly',31),'2026-03-31')
        doc = self.create()
        result = self.call(self.owner, 'billing/schedules', dict(document_id=doc['id'], interval='monthly', start_date=self.today, terms=14))
        self.assertEqual(result.status_code, 200)
        first = self.call(self.owner, 'billing/schedules/run', {})
        self.assertEqual(first.json['created'], 1)
        self.assertEqual(self.call(self.owner, 'billing/schedules/run', {}).json['created'], 0)
        self.assertEqual(len(self.owner.get('/api/billing/documents').json), 2)
        self.assertTrue(all(d['state']=='draft' for d in self.owner.get('/api/billing/documents').json))
        generated = next(d for d in self.owner.get('/api/billing/documents').json if d['schedule_id'])
        generated = self.issue(self.get(generated['id']))
        schedules = self.owner.get('/api/billing/schedules').json
        self.assertEqual(self.call(self.owner, f"billing/documents/{generated['id']}", {'version':generated['version']}, 'DELETE').status_code, 200)
        self.assertEqual(self.owner.get('/api/billing/schedules').json, schedules)
        self.assertEqual(self.call(self.owner, 'billing/schedules/run', {}).json['created'], 0)
        with app.app_context():
            self.assertEqual(db().execute('SELECT count(*) FROM billing_outbox').fetchone()[0], 0)

    def test_time_invoicing_and_double_billing_guard(self):
        response = self.call(self.owner, 'billing/time', dict(client_id=self.cid, date=self.today, description='Briefing', hours='1.5', rate='100', billable=True))
        tid = response.json['id']
        response = self.call(self.owner, 'billing/time/invoice', {'ids':[tid]})
        self.assertEqual(response.status_code, 200, response.json)
        doc = self.get(response.json['id'])
        self.assertEqual(doc['total_cents'], 16500)
        self.assertEqual(self.call(self.owner, 'billing/time/invoice', {'ids':[tid]}).status_code, 409)
        self.assertEqual(self.call(self.owner, f'billing/time/{tid}', {}, 'DELETE').status_code, 409)
        doc = self.issue(doc)
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}", {'version':doc['version']}, 'DELETE').status_code, 200)
        self.assertEqual(self.call(self.owner, 'billing/time/invoice', {'ids':[tid]}).status_code, 200)

    def test_pdf_contains_invoice_details_and_multiple_pages(self):
        from pypdf import PdfReader
        doc = self.issue(self.create(lines=[dict(description='Service '+str(i)+'\nLong description <safe> & accurate', quantity=1,unit_price=100) for i in range(50)]))
        response = self.owner.get(f"/api/billing/documents/{doc['id']}/pdf")
        self.assertEqual(response.status_code, 200)
        pdf = PdfReader(io.BytesIO(response.data))
        self.assertGreater(len(pdf.pages), 1)
        text = '\n'.join(p.extract_text() for p in pdf.pages)
        for value in ('TAX INVOICE','INV-0001','Example Flight Testing','12 345 678 901','Example Client','Service 49','Total'):
            self.assertIn(value, text)

    def test_existing_database_and_receipt_survive_restart_migration(self):
        # Restart against a copy with all new billing tables removed: equivalent to a 0.1 database.
        self.expense(self.owner, merchant='Pre-upgrade expense', amount='45.67')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            with app.app_context():
                target = sqlite3.connect(path/'rounded.sqlite')
                db().backup(target)
                target.execute('PRAGMA foreign_keys=OFF')
                target.execute('DROP TABLE schema_migrations')
                for row in target.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'billing_%'").fetchall():
                    target.execute('DROP TABLE '+row[0])
                target.execute('ALTER TABLE users DROP COLUMN permission')
                target.execute('DROP TABLE employment_income')
                target.execute('DROP TABLE tax_settings')
                target.commit();target.close()
            (path/'session.key').write_text('existing-session-key')
            (path/'receipts').mkdir()
            (path/'receipts'/'kept-receipt').write_bytes(b'original receipt bytes')
            command = "import app; c=app.app.app_context(); c.push(); assert app.one(\"SELECT amount_cents FROM expenses WHERE merchant='Pre-upgrade expense'\")['amount_cents']==4567; assert app.one(\"SELECT next_number FROM billing_counters WHERE kind='invoice'\")['next_number']==1"
            result = subprocess.run([sys.executable,'-c',command],env={**os.environ,'DATA_DIR':folder},capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((path/'session.key').read_text(),'existing-session-key')
            self.assertEqual((path/'receipts'/'kept-receipt').read_bytes(),b'original receipt bytes')


if __name__ == '__main__':
    unittest.main()
