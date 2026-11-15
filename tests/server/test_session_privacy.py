"""Public bootstrap stays minimal through every authentication state."""
import os
import unittest
from unittest.mock import patch
import test_app as base
from app import app, db

PUBLIC = {'user', 'csrf', 'setup', 'setup_token_required', 'mfa_required',
          'product', 'api_version', 'minimum_client_api'}


class SessionPrivacyTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login

    def minimal(self, client, setup=False):
        response = client.get('/api/session')
        self.assertEqual(response.status_code, 200)
        data = response.json
        self.assertEqual(set(data), PUBLIC)
        self.assertIsNone(data['user'])
        self.assertEqual(data['setup'], setup)
        self.assertEqual(data['product'], 'Expense Pilot')
        self.assertEqual((data['api_version'], data['minimum_client_api']), (1, 1))
        self.assertTrue(data['csrf'])
        return data

    def test_public_bootstrap_before_and_after_setup(self):
        self.minimal(app.test_client())
        self.call(self.owner, 'account', dict(password='Owner-password-123', confirmation='DELETE WORKSPACE'), 'DELETE')
        for token in ('', 'protected-setup-token-123456789'):
            with patch.dict(os.environ, SETUP_TOKEN=token):
                data = self.minimal(app.test_client(), setup=True)
                self.assertEqual(data['setup_token_required'], bool(token))
        self.assertEqual(app.test_client().get('/api/timezones').status_code, 200)

    def test_pending_and_expired_mfa_are_anonymous(self):
        client = app.test_client()
        for expiry, required in ((9999999999, True), (1, False)):
            with client.session_transaction() as state:
                state.update(mfa_uid=1, mfa_until=expiry)
            self.assertEqual(self.minimal(client)['mfa_required'], required)

    def test_revoked_disabled_and_expired_sessions(self):
        for change in ('UPDATE users SET active=0', 'UPDATE users SET version=version+1',
                       'DELETE FROM login_sessions', 'UPDATE login_sessions SET expires=1'):
            with self.subTest(change=change):
                self.setUp()
                with app.app_context():
                    db().execute(change); db().commit()
                self.minimal(self.owner)

    def test_temporary_password_only_gets_password_bootstrap(self):
        uid = self.agent.get('/api/session').json['user']['id']
        with app.app_context():
            db().execute('UPDATE users SET must_change_password=1,invite_expires=9999999999 WHERE id=?', (uid,)); db().commit()
        data = self.agent.get('/api/session').json
        self.assertEqual(set(data), PUBLIC)
        self.assertEqual(data['user'], {'id': uid, 'must_change_password': 1})
        self.assertEqual(self.agent.get('/api/expenses').status_code, 403)
        with app.app_context():
            db().execute('UPDATE users SET invite_expires=1 WHERE id=?', (uid,)); db().commit()
        self.minimal(self.agent)

    def test_discovery_and_authenticated_identity(self):
        expected = {'product', 'api_version', 'minimum_client_api', 'privacy_path', 'setup', 'setup_token_required'}
        for client in (app.test_client(), self.owner):
            data = client.get('/api/server-info').json
            self.assertEqual(set(data), expected)
            self.assertEqual(data['product'], 'Expense Pilot')
        original = self.owner.get('/api/session').json
        self.assertTrue(original['instance_id'])
        self.call(self.owner, 'logout', {})
        self.minimal(self.owner)
        self.login(self.owner, 'owner@example.test', 'Owner-password-123')
        self.assertEqual(self.owner.get('/api/session').json['instance_id'], original['instance_id'])
        self.assertEqual(self.agent.get('/api/session').json['features'], {})
        self.assertEqual(self.agent.get('/api/session').json['capabilities'], {'tax_workspace': True, 'account_deletion': True})

    def test_flask_error_logging_redacts_request_and_exception_url(self):
        import io
        import logging
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        app.logger.addHandler(handler)
        self.addCleanup(app.logger.removeHandler, handler)
        with patch.dict(app.config, TESTING=False), patch('quote_acceptance.find', side_effect=RuntimeError('Failed /quote/private-bearer/pdf?copy=private-bearer')):
            for path in ('/quote/private-bearer', '/quote/private-bearer/pdf'):
                self.assertEqual(app.test_client().get(path).status_code, 500)
        self.assertNotIn('private-bearer', output.getvalue())
        self.assertIn('RuntimeError', output.getvalue())
        self.assertIn('/quote/[REDACTED]', output.getvalue())
