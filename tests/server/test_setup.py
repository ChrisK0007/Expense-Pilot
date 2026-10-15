"""Optional owner setup protects configured installations and closes after first use."""
import os
import unittest
from unittest.mock import patch
import test_app as base
from app import app, db


class SetupTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login

    def empty_workspace(self):
        response = self.call(self.owner, 'account', dict(password='Owner-password-123', confirmation='DELETE WORKSPACE'), 'DELETE')
        self.assertEqual(response.status_code, 200)
        return app.test_client()

    def payload(self, **values):
        return dict(name='Owner', email='owner@example.test', password='Owner-password-123', **values)

    def test_empty_and_unset_token_allow_setup_once_with_csrf(self):
        for value in ('', None):
            with self.subTest(value=value):
                client = self.empty_workspace()
                with patch.dict(os.environ):
                    if value is None: os.environ.pop('SETUP_TOKEN', None)
                    else: os.environ['SETUP_TOKEN'] = value
                    self.assertFalse(client.get('/api/session').json['setup_token_required'])
                    self.assertFalse(client.get('/api/server-info').json['setup_token_required'])
                    self.assertEqual(client.post('/api/setup', json=self.payload()).status_code, 403)
                    data = self.payload(); data['password'] = 'short'
                    self.assertEqual(self.call(client, 'setup', data).status_code, 400)
                    self.assertTrue(client.get('/api/session').json['setup'])
                    self.assertEqual(self.call(client, 'setup', self.payload()).status_code, 200)
                    self.assertFalse(client.get('/api/session').json['setup'])
                    self.assertEqual(self.call(client, 'setup', self.payload()).status_code, 409)
                    with app.app_context(): self.assertEqual(db().execute('SELECT count(*) FROM users').fetchone()[0], 1)
                    self.login(client, 'owner@example.test', 'Owner-password-123')
                    self.owner = client

    def test_configured_token_cannot_be_skipped_or_replaced(self):
        client = self.empty_workspace()
        with patch.dict(os.environ, {'SETUP_TOKEN': 'a-protected-setup-token-123456789'}):
            self.assertTrue(client.get('/api/session').json['setup_token_required'])
            for token in ('', 'wrong', 'non-ascii-🔑'):
                self.assertEqual(self.call(client, 'setup', self.payload(token=token)).status_code, 403)
                self.assertTrue(client.get('/api/session').json['setup'])
            self.assertEqual(self.call(client, 'setup', self.payload(token=os.environ['SETUP_TOKEN'])).status_code, 200)
        with patch.dict(os.environ, {'SETUP_TOKEN': ''}):
            self.assertEqual(self.call(client, 'setup', self.payload()).status_code, 409)
            self.login(client, 'owner@example.test', 'Owner-password-123')

    def test_short_configured_token_fails_closed(self):
        client = self.empty_workspace()
        with patch.dict(os.environ, {'SETUP_TOKEN': 'short'}):
            self.assertTrue(client.get('/api/session').json['setup_token_required'])
            self.assertEqual(self.call(client, 'setup', self.payload(token='short')).status_code, 403)
            self.assertTrue(client.get('/api/session').json['setup'])

    def test_backups_are_not_setup_requirements(self):
        items = self.owner.get('/api/setup/checklist').json['items']
        self.assertNotIn('backup', [x['key'] for x in items])
        self.assertIn('timezone', [x['key'] for x in items])
        self.assertEqual(self.agent.get('/api/setup/checklist').status_code, 403)
