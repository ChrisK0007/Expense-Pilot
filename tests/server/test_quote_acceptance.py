import re
import unittest
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import urlsplit
import test_billing
from app import app
import workspace_time


class QuoteAcceptanceTest(unittest.TestCase):
    call = test_billing.BillingTest.call
    login = test_billing.BillingTest.login
    create = test_billing.BillingTest.create
    get = test_billing.BillingTest.get
    action = test_billing.BillingTest.action
    email_config = test_billing.BillingTest.email_config

    def setUp(self):
        test_billing.BillingTest.setUp(self)
        self.email_config()
        response = self.call(self.owner, 'security/invitations', {'login_url': 'https://expenses.example.test'}, 'PUT')
        self.assertEqual(response.status_code, 200, response.json)
        self.client = app.test_client()

    def send(self, quote):
        path = 'billing/documents/' + str(quote['id'])
        draft = self.owner.get('/api/' + path + '/email-draft').json
        self.assertTrue(draft['acceptance_available'])
        with patch('billing.deliver', return_value=('sent', '')) as mail:
            result = self.call(self.owner, path + '/send', {
                'recipient': draft['recipient'], 'subject': draft['subject'], 'body': draft['body'],
                'version': draft['version'], 'request_key': draft['request_key'], 'include_acceptance_link': True,
            })
        self.assertEqual(result.status_code, 200, result.json)
        message = mail.call_args.args[2]
        url = re.search(r'https://expenses\.example\.test/quote/[A-Za-z0-9_-]{43}', message)
        self.assertIsNotNone(url, message)
        return urlsplit(url.group()).path

    def test_client_accepts_issued_document_once_and_owner_converts(self):
        quote = self.create(kind='quote', reference='Cessna training', notes='Client-visible scope')
        path = self.send(quote)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Cessna training', response.data)
        self.assertNotIn(b'Private internal note', response.data)
        self.assertIn(b'Awaiting acceptance', response.data)
        self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        pdf = self.client.get(path + '/pdf')
        self.assertEqual(pdf.mimetype, 'application/pdf')
        self.assertTrue(pdf.data.startswith(b'%PDF'))
        self.assertEqual(self.get(quote['id'])['state'], 'issued')
        self.assertEqual(self.client.post(path, data={'full_name': 'Alex Taylor'}).status_code, 400)
        self.assertEqual(self.client.post(path, data={'full_name': 'Alex Taylor', 'authorised': 'yes'},
                                          headers={'Sec-Fetch-Site': 'cross-site'}).status_code, 403)

        result = self.client.post(path, data={'full_name': 'Alex <Taylor>', 'authorised': 'yes'}, follow_redirects=True)
        self.assertEqual(result.status_code, 200)
        self.assertIn(b'Alex &lt;Taylor&gt;', result.data)
        accepted = self.get(quote['id'])
        self.assertEqual(accepted['state'], 'accepted')
        self.assertEqual(accepted['online_acceptance']['accepted_name'], 'Alex <Taylor>')
        self.assertTrue(accepted['online_acceptance']['accepted_at'])
        self.assertEqual(accepted['online_acceptance']['recipient'], 'client@example.test')
        self.assertEqual(self.client.post(path, data={'full_name': 'Someone else', 'authorised': 'yes'}).status_code, 303)
        self.assertEqual(self.get(quote['id'])['online_acceptance'], accepted['online_acceptance'])
        notices = self.owner.get('/api/workspace-notifications').json['items']
        self.assertTrue(any(item['kind'] == 'quoteAccepted' and item['item'] == str(quote['id']) for item in notices))
        document_path = f"billing/documents/{quote['id']}"
        self.assertEqual(self.call(self.owner, document_path + '/wording',
                                   {'version': accepted['version'], 'descriptions': ['Changed']}, 'PUT').status_code, 409)

        with patch('workspace_time.today', return_value=workspace_time.today() + timedelta(days=1)):
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(self.client.get(path + '/pdf').status_code, 200)
            self.assertTrue(self.get(quote['id'])['online_acceptance']['linked'])

        invoice = self.action(accepted, 'convert')
        self.assertEqual(invoice.status_code, 200, invoice.json)
        saved = self.get(invoice.json['id'])
        self.assertEqual((saved['kind'], saved['state'], saved['total_cents']), ('invoice', 'draft', quote['total_cents']))
        self.assertEqual(self.get(quote['id'])['state'], 'converted')
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get(path + '/pdf').status_code, 404)
        self.assertEqual(self.call(self.owner, f"billing/documents/{saved['id']}",
                                   {'version': saved['version']}, 'DELETE').status_code, 200)
        restored = self.get(quote['id'])
        self.assertEqual(restored['state'], 'accepted')
        self.assertFalse(restored['online_acceptance']['linked'])
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_delete_accepted_quote_closes_the_client_link(self):
        quote = self.create(kind='quote')
        path = self.send(quote)
        self.assertEqual(self.client.post(path, data={'full_name': 'Alex Taylor', 'authorised': 'yes'}).status_code, 303)
        accepted = self.get(quote['id'])
        self.assertEqual(self.call(self.owner, f"billing/documents/{quote['id']}",
                                   {'version': accepted['version']}, 'DELETE').status_code, 200)
        self.assertEqual(self.owner.get(f"/api/billing/documents/{quote['id']}").status_code, 404)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get(path + '/pdf').status_code, 404)

    def test_manually_accepted_quote_link_becomes_read_only(self):
        quote = self.create(kind='quote')
        path = self.send(quote)
        self.assertEqual(self.action(self.get(quote['id']), 'accepted').status_code, 200)
        with patch('workspace_time.today', return_value=workspace_time.today() + timedelta(days=1)):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'The sender recorded acceptance', page.data)
            self.assertNotIn(b'Accept this quote', page.data)
        self.assertEqual(self.client.post(path, data={'full_name': 'Alex Taylor', 'authorised': 'yes'}).status_code, 303)
        self.assertIsNone(self.get(quote['id'])['online_acceptance']['accepted_at'])

    def test_sender_can_rotate_or_revoke_links_and_expired_links_cannot_accept(self):
        quote = self.create(kind='quote')
        old, current = self.send(quote), self.send(quote)
        self.assertNotEqual(old, current)
        self.assertEqual(self.client.get(old).status_code, 404)
        doc = self.get(quote['id'])
        revoke = f"billing/documents/{quote['id']}/acceptance-link"
        self.assertEqual(self.call(self.agent, revoke, {'version': doc['version']}, 'DELETE').status_code, 403)
        self.assertEqual(self.call(self.owner, revoke, {'version': doc['version']}, 'DELETE').status_code, 200)
        self.assertEqual(self.client.get(current + '/pdf').status_code, 404)

        replacement = self.send(quote)
        with patch('workspace_time.today', return_value=workspace_time.today() + timedelta(days=30)):
            self.assertEqual(self.client.get(replacement).status_code, 404)
            self.assertEqual(self.client.post(replacement, data={'full_name': 'Alex Taylor', 'authorised': 'yes'}).status_code, 404)

        doc = self.get(quote['id'])
        wording = self.call(self.owner, f"billing/documents/{doc['id']}/wording",
                            {'version': doc['version'], 'descriptions': ['Updated line']}, 'PUT')
        self.assertEqual(wording.status_code, 200, wording.json)
        self.assertEqual(self.client.get(replacement).status_code, 404)
        self.assertEqual(self.get(quote['id'])['state'], 'issued')
