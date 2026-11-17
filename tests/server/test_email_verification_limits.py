"""Mailbox proof and durable request quota regression coverage."""
import re
import time
import unittest
from unittest.mock import patch
import test_app as base
from app import app, db
import security


class VerificationTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login

    def send(self, client=None, password='Owner-password-123'):
        client = client or self.owner
        with patch('billing.mail_settings', return_value={'host': 'mail.example.test', 'from_email': 'sender@example.test'}), patch('billing.deliver', return_value=('sent', '')) as delivery:
            response = self.call(client, 'security/email/send', {'password': password})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertNotIn('code', response.json)
        code = re.search(r'code is: ([0-9]{8})', delivery.call_args.args[2])[1]
        return code

    def test_email_proof_single_use_and_no_cleartext_storage(self):
        self.assertFalse(self.owner.get('/api/security/email').json['verified'])
        code = self.send()
        with app.app_context():
            row = dict(db().execute('SELECT * FROM email_verification').fetchone())
        self.assertNotEqual(row['challenge_hash'], code)
        self.assertEqual(len(row['challenge_hash']), 64)
        response = self.call(self.owner, 'security/email/confirm', {'code': code})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(self.owner.get('/api/security/email').json['verified'])
        self.assertEqual(self.call(self.owner, 'security/email/confirm', {'code': code}).status_code, 400)
        self.assertEqual(self.owner.get('/api/expenses').status_code, 200)

    def test_email_attempts_expiry_and_resend_invalidation(self):
        previous = self.send()
        code = self.send()
        self.assertEqual(self.call(self.owner, 'security/email/confirm', {'code': previous}).status_code, 400)
        for _ in range(4):
            self.assertEqual(self.call(self.owner, 'security/email/confirm', {'code': 'invalid'}).status_code, 400)
        self.assertEqual(self.call(self.owner, 'security/email/confirm', {'code': code}).status_code, 400)
        code = self.send()
        with app.app_context():
            db().execute('UPDATE email_verification SET expires=1'); db().commit()
        self.assertEqual(self.call(self.owner, 'security/email/confirm', {'code': code}).status_code, 400)
        with patch('billing.mail_settings', return_value={'host': 'mail.example.test', 'from_email': 'sender@example.test'}), patch('billing.deliver') as delivery:
            self.assertEqual(self.call(self.owner, 'security/email/send', {'password': 'Owner-password-123'}).status_code, 429)
            delivery.assert_not_called()

    def test_wrong_password_no_mail_failed_delivery_cannot_verify(self):
        with patch('billing.deliver') as delivery:
            self.assertEqual(self.call(self.owner, 'security/email/send', {'password': 'wrong'}).status_code, 403)
            delivery.assert_not_called()
        with patch('billing.mail_settings', return_value={'host': 'mail.example.test', 'from_email': 'sender@example.test'}), patch('billing.deliver', return_value=('unknown', 'synthetic-provider-secret')):
            response = self.call(self.owner, 'security/email/send', {'password': 'Owner-password-123'})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('synthetic-provider-secret', response.get_data(as_text=True))
        with app.app_context():
            self.assertEqual(db().execute('SELECT challenge_hash FROM email_verification').fetchone()[0], '')

    def test_proof_is_bound_to_account_email_and_account_version(self):
        code = self.send()
        self.assertEqual(self.call(self.agent, 'security/email/confirm', {'code': code}).status_code, 400)
        with app.app_context():
            db().execute("UPDATE users SET version=version+1 WHERE role='owner'"); db().commit()
        self.login(self.owner, 'owner@example.test', 'Owner-password-123')
        self.assertEqual(self.call(self.owner, 'security/email/confirm', {'code': code}).status_code, 400)
        code = self.send()
        self.assertEqual(self.call(self.owner, 'security/email/confirm', {'code': code}).status_code, 200)
        with app.app_context():
            db().execute("UPDATE users SET email='changed@example.test' WHERE role='owner'"); db().commit()
        self.assertFalse(self.owner.get('/api/security/email').json['verified'])

    def test_tax_agent_can_verify_only_their_own_mailbox(self):
        code = self.send(self.agent, 'Testing-password-123')
        self.assertEqual(self.call(self.agent, 'security/email/confirm', {'code': code}).status_code, 200)
        self.assertTrue(self.agent.get('/api/security/email').json['verified'])
        self.assertFalse(self.owner.get('/api/security/email').json['verified'])
        self.assertEqual(self.agent.get('/api/users').status_code, 403)


class RequestQuotaTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login

    def clear(self):
        with app.app_context():
            db().execute('DELETE FROM request_limits'); db().commit()

    def test_account_quota_is_shared_across_endpoints_and_recovers(self):
        self.clear()
        with patch.dict(app.config, API_USER_LIMIT=2):
            self.assertEqual(self.owner.get('/api/expenses').status_code, 200)
            self.assertEqual(self.owner.get('/api/accounts').status_code, 200)
            denied = self.owner.get('/api/session')
            self.assertEqual(denied.status_code, 429)
            self.assertIn('Retry-After', denied.headers)
            self.assertEqual(self.agent.get('/api/session').status_code, 200)
            with patch('request_limits.time.time', return_value=time.time()+61):
                self.assertEqual(self.owner.get('/api/session').status_code, 200)

    def test_anonymous_quota_ignores_untrusted_forwarding_headers(self):
        self.clear()
        client = app.test_client()
        with patch.dict(app.config, API_ANONYMOUS_LIMIT=2):
            for ip in ('192.0.2.1', '192.0.2.2'):
                self.assertEqual(client.get('/api/session', headers={'X-Forwarded-For': ip}).status_code, 200)
            denied = client.get('/api/server-info', headers={'X-Forwarded-For': '192.0.2.3'})
            self.assertEqual(denied.status_code, 429)
            self.assertEqual(client.get('/api/session', environ_overrides={'REMOTE_ADDR': '192.0.2.50'}).status_code, 200)
