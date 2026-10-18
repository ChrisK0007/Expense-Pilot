"""Email workflows use mocked SMTP only; no test sends network email."""
import io
import secrets
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from unittest.mock import patch

import test_billing as base
from app import app, db
import billing
from billing_email_core import DEFAULT_TEMPLATES, clean_signature
from billing_emails import run_reminders


class BillingEmailTest(unittest.TestCase):
    setUp = base.BillingTest.setUp
    call = base.BillingTest.call
    login = base.BillingTest.login
    create = base.BillingTest.create
    get = base.BillingTest.get
    action = base.BillingTest.action
    issue = base.BillingTest.issue
    pay = base.BillingTest.pay
    email_config = base.BillingTest.email_config

    def day(self, offset):
        return (date.fromisoformat(self.today) + timedelta(days=offset)).isoformat()

    def draft(self, doc, kind='document'):
        result = self.owner.get(f"/api/billing/documents/{doc['id']}/email-draft?kind={kind}")
        self.assertEqual(result.status_code, 200, result.json)
        return result.json

    def text(self, raw):
        from pypdf import PdfReader
        return '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages)

    def test_reference_templates_and_personalised_fields(self):
        settings = self.owner.get('/api/billing/email-templates').json
        self.assertEqual(settings['templates'], DEFAULT_TEMPLATES)
        self.assertEqual(settings['signature_html'], '')
        self.call(self.owner, f'billing/clients/{self.cid}', dict(name='Aviation Company', contact='Alex', email='alex@example.test'), 'PUT')
        for kind in ('invoice', 'quote'):
            doc = self.create(kind=kind)
            draft = self.draft(doc)
            self.assertEqual(draft['subject'], kind.capitalize() + ' from Example Flight Testing')
            self.assertIn('Hi Alex,', draft['body'])
            self.assertTrue(draft['body'].endswith('Best regards,\nOwner'))
            self.assertNotIn('{', draft['body'])
        doc = self.issue(self.create())
        before = self.draft(doc, 'reminder_manual')
        self.assertNotIn('overdue', before['subject'])
        self.assertIn('is due on', before['body'])
        late = self.issue(self.create(issue_date=self.day(-10), due_date=self.day(-1)))
        self.assertIn('overdue', self.draft(late, 'reminder_manual')['subject'])

    def test_templates_validation_and_legacy_defaults_stay_in_sync(self):
        saved = dict(subject='Invoice {number}', body='Dear {client}, balance {balance}. {full_name}')
        self.assertEqual(self.call(self.owner, 'billing/email-templates', {'templates':{'invoice':saved}}, 'PUT').status_code, 200)
        self.assertEqual(self.owner.get('/api/billing/settings').json['defaults']['invoice_email_body'], saved['body'])
        self.call(self.owner, 'billing/document-defaults', {'invoice_email_body':'Legacy {number}'}, 'PUT')
        self.assertEqual(self.owner.get('/api/billing/email-templates').json['templates']['invoice']['body'], 'Legacy {number}')
        before = self.owner.get('/api/billing/email-templates').json
        for invalid in ({'subject':'Hi\nBcc: bad', 'body':'Message'}, {'subject':'Hi', 'body':'{unknown}'},
                        {'subject':'Hi', 'body':''}, {'subject':'x'*201, 'body':'Message'}, {'subject':'Hi', 'body':['not text']}):
            self.assertEqual(self.call(self.owner, 'billing/email-templates', {'templates':{'invoice':invalid}}, 'PUT').status_code, 400)
        self.assertEqual(self.call(self.owner, 'billing/email-templates', {'templates':{'statement_all':{'subject':'Hi', 'body':'{latest_payment}'}}}, 'PUT').status_code, 400)
        self.assertEqual(self.owner.get('/api/billing/email-templates').json, before)

    def test_existing_factory_templates_upgrade_without_overwriting_custom_text(self):
        from migrations.m007_billing_email import upgrade
        with app.app_context():
            defaults = billing.document_defaults()
            defaults.update(invoice_email_subject=billing.DEFAULT_MAIL['subject'], invoice_email_body=billing.DEFAULT_MAIL['body'],
                            quote_email_subject='My custom quote', quote_email_body='Please review {number}.')
            billing.save_settings('document_defaults', defaults)
            db().commit()
            upgrade(db()); db().commit()
        templates = self.owner.get('/api/billing/email-templates').json['templates']
        self.assertEqual(templates['invoice'], DEFAULT_TEMPLATES['invoice'])
        self.assertEqual(templates['quote'], dict(subject='My custom quote', body='Please review {number}.'))

    @patch('billing.smtplib.SMTP_SSL')
    def test_signature_is_sanitised_and_sent_as_html_with_inline_image(self, smtp):
        from PIL import Image
        self.email_config()
        raw = io.BytesIO(); Image.new('RGB', (40, 20), 'blue').save(raw, 'PNG')
        token = self.owner.get('/api/session').json['csrf']
        result = self.owner.post('/api/billing/signature-image', data={'file':(io.BytesIO(raw.getvalue()), 'logo.png')}, headers={'X-CSRF-Token':token})
        self.assertEqual(result.status_code, 200)
        signature = '<div><b>Chris &amp; Co</b><br><font color="#123456" size="4">Pilot</font><br><a href="https://example.test">Website</a><img src="' + result.json['src'] + '" alt="Business logo"></div><script>alert(1)</script><img src="https://tracker.invalid/pixel" onerror="alert(1)"><a href="javascript:alert(1)">Bad link</a>'
        result = self.call(self.owner, 'billing/email-templates', {'signature_html':signature}, 'PUT')
        self.assertEqual(result.status_code, 200, result.json)
        cleaned = result.json['signature_html']
        for unsafe in ('<script', 'javascript:', 'onerror', 'tracker.invalid', 'alert('):
            self.assertNotIn(unsafe, cleaned)
        self.assertIn('<b>Chris &amp; Co</b>', cleaned)
        self.assertEqual(clean_signature(cleaned)[0], cleaned)
        doc = self.create(); draft = self.draft(doc)
        self.assertEqual(draft['signature_html'], cleaned)
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}/send", draft).json['state'], 'sent')
        message = smtp.return_value.send_message.call_args.args[0]
        self.assertIn('Chris & Co', message.get_body(preferencelist=('plain',)).get_content())
        html = message.get_body(preferencelist=('html',)).get_content()
        self.assertIn('cid:expense-pilot-signature-0', html)
        self.assertNotIn('data:image', html)
        self.assertEqual(len([part for part in message.walk() if part.get_content_type()=='image/png']), 1)
        self.assertEqual(len([part for part in message.walk() if part.get_content_type()=='application/pdf']), 1)

    @patch('billing.smtplib.SMTP_SSL')
    def test_partial_full_and_reversed_payment_receipts(self, smtp):
        self.email_config(); doc = self.issue(self.create())
        self.assertEqual(self.owner.get(f"/api/billing/documents/{doc['id']}/receipt").status_code, 409)
        self.assertEqual(self.pay(doc, '40').status_code, 200)
        doc = self.get(doc['id']); draft = self.draft(doc, 'receipt')
        self.assertEqual(draft['subject'], '$40.00 payment receipt')
        self.assertIn('outstanding balance of $70.00', draft['body'])
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}/send", draft).json['state'], 'sent')
        outgoing = smtp.return_value.send_message.call_args.args[0]
        pdf = next(part for part in outgoing.walk() if part.get_content_type()=='application/pdf')
        self.assertEqual(pdf.get_filename(), doc['number'] + '-receipt.pdf')
        text = self.text(pdf.get_payload(decode=True))
        for expected in ('PAYMENT RECEIPT', 'PAYMENTS RECEIVED', '$40.00', '$70.00', 'Test transfer'):
            self.assertIn(expected, text)
        doc = self.get(doc['id']); last = self.pay(doc, '70').json['id']
        doc = self.get(doc['id']); draft = self.draft(doc, 'receipt')
        self.assertEqual(draft['subject'], '$110.00 payment receipt')
        self.assertNotIn('outstanding balance', draft['body'])
        self.assertEqual(self.agent.get(f"/api/billing/documents/{doc['id']}/receipt").status_code, 200)
        self.assertEqual(self.call(self.owner, f'billing/payments/{last}/reverse', dict(version=doc['version'],reason='Correction')).status_code, 200)
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}/send", draft).status_code, 409)
        self.assertEqual(self.draft(self.get(doc['id']), 'receipt')['subject'], '$40.00 payment receipt')

    def test_statement_opening_activity_and_outstanding_balances(self):
        older = self.issue(self.create(issue_date=self.day(-20), due_date=self.day(-10)))
        for offset, amount in ((-15, '11'), (-2, '22')):
            result = self.call(self.owner, f"billing/documents/{older['id']}/payments", dict(version=older['version'], amount=amount, date=self.day(offset), reference='Transfer', request_key=secrets.token_hex(24)))
            self.assertEqual(result.status_code, 200); older = self.get(older['id'])
        recent = self.issue(self.create(issue_date=self.day(-5)))
        self.assertEqual(self.pay(recent, '11').status_code, 200)
        self.create(); voided = self.issue(self.create()); self.action(voided, 'void')
        self.issue(self.create(issue_date=self.day(1), due_date=self.day(2)))
        start = self.day(-10)
        url = f'/api/billing/clients/{self.cid}/statement?mode=all&start={start}&end={self.today}'
        result = self.agent.get(url)
        self.assertEqual(result.status_code, 200)
        statement = result.json
        self.assertEqual((statement['opening_cents'], statement['invoice_cents'], statement['payment_cents'], statement['closing_cents']), (9900,11000,3300,17600))
        self.assertEqual([row['balance_cents'] for row in statement['rows']], [20900,18700,17600])
        outstanding = self.owner.get(f'/api/billing/clients/{self.cid}/statement?mode=outstanding').json
        self.assertEqual(outstanding['closing_cents'], 17600)
        self.assertEqual(len(outstanding['rows']), 2)
        for mode in ('all', 'outstanding'):
            pdf = self.owner.get(f'/api/billing/clients/{self.cid}/statement/pdf?mode={mode}&start={start}&end={self.today}')
            self.assertEqual(pdf.status_code, 200)
            text = self.text(pdf.data)
            self.assertIn('Statement of account', text); self.assertIn('$176.00', text)
            self.assertNotIn(voided['number'], text)
        self.assertEqual(self.owner.get(url.replace(start, self.day(1))).status_code, 400)

    @patch('billing.smtplib.SMTP_SSL')
    def test_statement_email_preview_staleness_and_duplicate_guard(self, smtp):
        self.email_config(); doc = self.issue(self.create())
        path = f'billing/clients/{self.cid}/statement'
        draft = self.owner.get('/api/' + path + '/email-draft?mode=all').json
        self.assertIn('for the period', draft['body']); self.assertTrue(draft['body'].endswith('Owner'))
        self.pay(doc, '40')
        self.assertEqual(self.call(self.owner, path + '/send', {**draft,'mode':'all'}).status_code, 409)
        draft = self.owner.get('/api/' + path + '/email-draft?mode=outstanding').json
        self.assertNotIn('for the period', draft['body'])
        response = self.call(self.owner, path + '/send', {**draft,'mode':'outstanding'})
        self.assertEqual(response.json['state'], 'sent', response.json)
        self.assertEqual(self.call(self.owner, path + '/send', {**draft,'mode':'outstanding'}).json['state'], 'sent')
        smtp.return_value.send_message.assert_called_once()
        outgoing = smtp.return_value.send_message.call_args.args[0]
        pdf = next(part for part in outgoing.walk() if part.get_content_type()=='application/pdf')
        self.assertIn('$70.00', self.text(pdf.get_payload(decode=True)))
        self.assertEqual(len(self.owner.get(f'/api/billing/clients/{self.cid}/statement-emails').json), 1)

    @patch('billing.smtplib.SMTP_SSL')
    def test_uncertain_statement_delivery_requires_reconciliation(self, smtp):
        self.email_config(); self.issue(self.create())
        smtp.return_value.send_message.side_effect = TimeoutError()
        path = f'billing/clients/{self.cid}/statement'
        draft = self.owner.get('/api/' + path + '/email-draft').json
        self.assertEqual(self.call(self.owner, path + '/send', draft).json['state'], 'unknown')
        another = self.owner.get('/api/' + path + '/email-draft').json
        self.assertEqual(self.call(self.owner, path + '/send', another).status_code, 409)
        record = self.owner.get(f'/api/billing/clients/{self.cid}/statement-emails').json[0]
        self.assertEqual(self.call(self.owner, f"billing/statement-emails/{record['id']}/resolve", {'state':'failed'}).status_code, 200)
        smtp.return_value.send_message.side_effect = None
        self.assertEqual(self.call(self.owner, path + '/send', another).json['state'], 'sent')

    def enable_reminders(self, **overrides):
        config = dict(enabled=True, before_days=3, on_due_date=True, after_days=[7,14]); config.update(overrides)
        response = self.call(self.owner, 'billing/reminder-settings', config, 'PUT')
        self.assertEqual(response.status_code, 200, response.json)

    @patch('billing.smtplib.SMTP_SSL')
    def test_automatic_reminder_dates_exclusions_and_no_repeat(self, smtp):
        self.email_config()
        for due in (3, 0, -7, -2):
            self.issue(self.create(issue_date=self.day(-20), due_date=self.day(due)))
        paid = self.issue(self.create()); self.pay(paid, '110')
        paused = self.issue(self.create())
        self.call(self.owner, f"billing/documents/{paused['id']}/reminders", {'version':paused['version'], 'enabled':False}, 'PUT')
        voided = self.issue(self.create()); self.action(voided,'void')
        self.create()
        with app.app_context():
            self.assertEqual(run_reminders(), 0)
        self.enable_reminders()
        with app.app_context():
            self.assertEqual(run_reminders(), 3)
            self.assertEqual(run_reminders(), 0)
            records = billing.rows('SELECT * FROM billing_outbox')
        self.assertEqual(smtp.return_value.send_message.call_count, 3)
        self.assertEqual([r['message_kind'] for r in records], ['reminder_due', 'reminder_due', 'reminder_overdue'])
        self.assertTrue(all(r['automation_key'] and r['state']=='sent' for r in records))
        self.assertIn('from Owner for $110.00', records[0]['body'])
        self.enable_reminders(enabled=False)
        with app.app_context():
            self.assertEqual(run_reminders(self.day(7)), 0)

    def test_concurrent_reminder_worker_claims_once(self):
        self.email_config(); self.issue(self.create()); self.enable_reminders()
        queued, release = threading.Event(), threading.Event()
        def delivery(*args, **kwargs):
            queued.set(); self.assertTrue(release.wait(5)); return 'sent', ''
        def work():
            with app.app_context():
                return run_reminders()
        with patch('billing.deliver', side_effect=delivery) as send, ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(work)
            try:
                self.assertTrue(queued.wait(5))
                self.assertEqual(work(), 0)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=5), 1)
            send.assert_called_once()

    @patch('billing.smtplib.SMTP_SSL')
    def test_unknown_reminder_is_not_retried_or_deleted(self, smtp):
        self.email_config(); doc = self.issue(self.create()); self.enable_reminders()
        smtp.return_value.send_message.side_effect = TimeoutError()
        with app.app_context():
            self.assertEqual(run_reminders(), 1)
            self.assertEqual(run_reminders(), 0)
            self.assertEqual(run_reminders(self.day(7)), 0)
        doc = self.get(doc['id'])
        self.assertEqual(doc['emails'][0]['state'], 'unknown')
        self.assertEqual(self.call(self.owner, f"billing/documents/{doc['id']}", {'version':doc['version']}, 'DELETE').status_code, 409)
        smtp.return_value.send_message.assert_called_once()

    def test_email_controls_are_owner_only_and_require_valid_settings(self):
        doc = self.issue(self.create())
        uid = next(u['id'] for u in self.owner.get('/api/users').json if u['email']=='agent@example.test')
        self.call(self.owner, f'users/{uid}/permission', {'permission':'read_write'}, 'PUT')
        for path in ('email-templates','reminder-settings',f"documents/{doc['id']}/email-draft",f'clients/{self.cid}/statement/email-draft',f'clients/{self.cid}/statement-emails'):
            self.assertEqual(self.agent.get('/api/billing/' + path).status_code, 403, path)
        for path, method in (('email-templates','PUT'),('reminder-settings','PUT'),('signature-image','POST'),(f"documents/{doc['id']}/reminders",'PUT'),(f'clients/{self.cid}/statement/send','POST')):
            self.assertEqual(self.call(self.agent, 'billing/' + path, {}, method).status_code, 403)
        self.assertEqual(self.owner.put('/api/billing/email-templates',json={}).status_code,403)
        config = dict(enabled=True,before_days=3,on_due_date=True,after_days=[7])
        self.assertEqual(self.call(self.owner, 'billing/reminder-settings', config, 'PUT').status_code, 400)
        self.email_config()
        for change in ({'after_days':[0]}, {'after_days':['bad']}, {'before_days':31}, {'enabled':'true'}, {'before_days':0,'on_due_date':False,'after_days':[]}):
            self.assertEqual(self.call(self.owner, 'billing/reminder-settings', {**config,**change}, 'PUT').status_code, 400)


if __name__ == '__main__':
    unittest.main()
