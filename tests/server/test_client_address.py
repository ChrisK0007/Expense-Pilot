"""Sign-in throttling must not let one visitor lock out everyone behind a reverse proxy."""
import os
import tempfile
import unittest

if 'DATA_DIR' not in os.environ:
    _test_data = tempfile.TemporaryDirectory()
    os.environ['DATA_DIR'] = _test_data.name
os.environ.setdefault('SETUP_TOKEN', 'integration-test-setup-token-123456789')

from app import app, db
import client_address
from client_address import networks, resolve, TrustedProxyMiddleware
from werkzeug.security import generate_password_hash

PROXY = '172.18.0.2'
TRUSTED = networks('172.18.0.0/16')


class ResolveTests(unittest.TestCase):
    def test_untrusted_peer_ignores_forwarded_header(self):
        self.assertEqual(resolve('203.0.113.9', '198.51.100.1', TRUSTED), '203.0.113.9')

    def test_no_configuration_keeps_peer(self):
        self.assertEqual(resolve(PROXY, '198.51.100.1', ()), PROXY)

    def test_trusted_proxy_uses_recorded_client(self):
        self.assertEqual(resolve(PROXY, '198.51.100.1', TRUSTED), '198.51.100.1')

    def test_client_cannot_spoof_by_prepending(self):
        # The client sent "1.2.3.4"; the proxy appended the real address.
        self.assertEqual(resolve(PROXY, '1.2.3.4, 198.51.100.1', TRUSTED), '198.51.100.1')

    def test_chained_trusted_proxies_are_skipped(self):
        self.assertEqual(resolve(PROXY, '198.51.100.1, 172.18.0.7', TRUSTED), '198.51.100.1')

    def test_malformed_hop_stops_at_last_vouched_address(self):
        self.assertEqual(resolve(PROXY, '198.51.100.1, not-an-ip', TRUSTED), PROXY)

    def test_ports_and_ipv6(self):
        self.assertEqual(resolve(PROXY, '198.51.100.1:5555', TRUSTED), '198.51.100.1')
        self.assertEqual(resolve(PROXY, '[2001:db8::1]:443', TRUSTED), '2001:db8::1')
        self.assertEqual(resolve('::1', '2001:db8::2', networks('::1')), '2001:db8::2')

    def test_invalid_configuration_is_reported(self):
        with self.assertRaises(ValueError):
            networks('172.18.0.0/16, nonsense')


class LockoutTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.original = app.wsgi_app
        with app.app_context():
            for table in ('login_sessions', 'attempts', 'users'):
                db().execute('DELETE FROM ' + table)
            db().execute('INSERT INTO users(name,email,password,role) VALUES (?,?,?,?)',
                          ('Owner', 'owner@example.test', generate_password_hash('Owner-password-123'), 'owner'))
            db().commit()

    def tearDown(self):
        app.wsgi_app = self.original
        with app.app_context():
            db().execute('DELETE FROM attempts'); db().commit()

    def login(self, email, password, client_ip):
        c = app.test_client()
        environ = {'REMOTE_ADDR': PROXY, 'HTTP_X_FORWARDED_FOR': client_ip}
        token = c.get('/api/session', environ_base=environ).json['csrf']
        return c.post('/api/login', json={'email': email, 'password': password},
                      headers={'X-CSRF-Token': token}, environ_base=environ)

    def flood(self):
        for i in range(40):
            self.login(f'random{i}@example.test', 'wrong-password-xx', '203.0.113.66')

    def test_without_trusted_proxy_a_stranger_can_lock_out_the_owner(self):
        # Documents the default behaviour this change makes configurable.
        self.flood()
        self.assertEqual(self.login('owner@example.test', 'Owner-password-123', '198.51.100.1').status_code, 429)

    def test_trusted_proxy_isolates_visitors(self):
        app.wsgi_app = TrustedProxyMiddleware(self.original, TRUSTED)
        self.flood()
        self.assertEqual(self.login('random0@example.test', 'wrong-password-xx', '203.0.113.66').status_code, 429)
        self.assertEqual(self.login('owner@example.test', 'Owner-password-123', '198.51.100.1').status_code, 200)

    def test_install_reads_environment(self):
        class Dummy:
            wsgi_app = object()
        dummy = Dummy()
        self.assertEqual(client_address.install(dummy, ''), ())
        self.assertNotIsInstance(dummy.wsgi_app, TrustedProxyMiddleware)
        self.assertTrue(client_address.install(dummy, '10.0.0.1'))
        self.assertIsInstance(dummy.wsgi_app, TrustedProxyMiddleware)


if __name__ == '__main__':
    unittest.main()
