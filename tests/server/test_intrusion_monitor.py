"""Passive canary-policy tests against disposable Flask clients, not live services."""
import time
import unittest
from unittest.mock import patch
import test_app as base
from app import app
import client_address


class IntrusionTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login

    def mode(self, value):
        result = self.call(self.owner, 'security/intrusion', {'mode': value, 'password': 'Owner-password-123'}, 'PUT')
        self.assertEqual(result.status_code, 200, result.json)

    def test_monitor_default_ordinary_navigation_and_private_events(self):
        client = app.test_client()
        self.assertEqual(self.owner.get('/api/security/intrusion').json['mode'], 'monitor')
        for path in ('/', '/static/app.js', '/ordinary-missing-page'):
            client.get(path)
        self.assertEqual(self.owner.get('/api/security/intrusion').json['events'], [])
        for _ in range(6):
            self.assertEqual(client.get('/.env', headers={'X-Forwarded-For': '192.0.2.123'}).status_code, 404)
        result = self.owner.get('/api/security/intrusion').json
        self.assertEqual(len(result['events']), 6)
        self.assertEqual(len({e['source_key'] for e in result['events']}), 1)
        self.assertEqual(result['blocks'], [])
        self.assertNotIn('192.0.2.123', str(result))
        self.assertNotIn('127.0.0.1', str(result))
        self.assertEqual(self.agent.get('/api/security/intrusion').status_code, 403)
        self.assertEqual(client.get('/api/security/intrusion').status_code, 401)

    def test_temporary_blocks_expiry_authentication_and_owner_unblock(self):
        self.mode('block'); client = app.test_client()
        for _ in range(5):
            self.assertEqual(client.get('/.env').status_code, 404)
        blocked = client.get('/api/expenses')
        self.assertEqual(blocked.status_code, 429)
        self.assertIn('Retry-After', blocked.headers)
        self.assertEqual(client.get('/api/session').status_code, 200)
        self.assertEqual(self.owner.get('/api/expenses').status_code, 200)
        with patch('intrusion_monitor.time.time', return_value=time.time() + 901):
            self.assertEqual(client.get('/api/expenses').status_code, 401)
        key = self.owner.get('/api/security/intrusion').json['blocks'][0]['key']
        path = 'security/intrusion/unblock'
        self.assertEqual(self.call(self.owner, path, {'source_key': key, 'password': 'wrong'}).status_code, 403)
        self.assertEqual(self.call(self.owner, path, {'source_key': key, 'password': 'Owner-password-123'}).status_code, 200)
        self.assertEqual(client.get('/api/expenses').status_code, 401)
        self.mode('off')
        client.get('/.env')
        self.assertEqual(self.owner.get('/api/security/intrusion').json['events'], [])

    def test_trusted_proxy_source_separation(self):
        self.mode('block')
        original = app.wsgi_app
        app.wsgi_app = client_address.TrustedProxyMiddleware(original, client_address.networks('192.0.2.10'))
        self.addCleanup(setattr, app, 'wsgi_app', original)
        client = app.test_client()
        peer = {'REMOTE_ADDR': '192.0.2.10'}
        for _ in range(5):
            client.get('/.env', environ_overrides=peer, headers={'X-Forwarded-For': '198.51.100.1'})
        self.assertEqual(client.get('/api/expenses', environ_overrides=peer, headers={'X-Forwarded-For': '198.51.100.1'}).status_code, 429)
        self.assertEqual(client.get('/api/expenses', environ_overrides=peer, headers={'X-Forwarded-For': '198.51.100.2'}).status_code, 401)
