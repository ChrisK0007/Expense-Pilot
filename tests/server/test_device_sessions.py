"""Remembered-device expiry, authentication, isolation and push regressions."""
import hashlib
import os
import time
import unittest
from unittest.mock import patch
from test_app import AppTest
from app import app, db, one
import notifications
import security


class DeviceSessionTest(unittest.TestCase):
    setUp = AppTest.setUp
    call = AppTest.call
    login = AppTest.login

    def phone(self, email='owner@example.test', password='Owner-password-123'):
        client = app.test_client()
        result = self.call(client, 'login', dict(email=email, password=password, device_name='Test iPhone'))
        self.assertEqual(result.status_code, 200, result.json)
        return client

    def row(self, client):
        with client.session_transaction() as state:
            digest = hashlib.sha256(state['sid'].encode()).hexdigest()
        with app.app_context():
            return one('SELECT * FROM login_sessions WHERE token_hash=?', (digest,))

    def test_device_and_browser_survive_12_hours_and_renew(self):
        now = time.time()
        with patch('security.clock', return_value=now):
            phone = self.phone()
        original = self.row(phone)
        cookie = phone.get_cookie('session')
        self.assertGreater(cookie.expires.timestamp(), now + 29*86400)
        self.assertGreater(self.owner.get_cookie('session').expires.timestamp(), now + 29*86400)
        with patch('security.clock', return_value=now + 13*3600):
            self.assertIsNotNone(phone.get('/api/session').json['user'])
            browser = self.owner.get('/api/session').json
            self.assertIsNotNone(browser['user'])
            self.assertFalse(browser['device_session'])
        renewed = self.row(phone)
        self.assertEqual(self.row(self.owner)['expires'], now + 13*3600 + security.BROWSER_IDLE_SECONDS)
        self.assertEqual(renewed['expires'], now + 13*3600 + security.DEVICE_IDLE_SECONDS)
        self.assertGreater(renewed['expires'], original['expires'])
        with patch('security.clock', return_value=renewed['expires']):
            self.assertEqual(phone.get('/api/expenses').status_code, 401)
            self.assertIsNone(phone.get('/api/session').json['user'])
            self.assertEqual(self.owner.get('/api/expenses').status_code, 401)
        with app.app_context():
            self.assertEqual(one('SELECT expires FROM login_sessions WHERE token_hash=?', (original['token_hash'],))['expires'], renewed['expires'])

    def test_browser_reopens_and_renews_cookie_signature_and_database_over_months(self):
        now = time.time()
        browser = app.test_client()
        with patch('itsdangerous.timed.time.time', return_value=now):
            self.login(browser, 'owner@example.test', 'Owner-password-123')
            cookie = browser.get_cookie('session')
            self.assertTrue(cookie.http_only)
            self.assertEqual(cookie.same_site, 'Strict')
        for day in (29, 58):
            # Reopening with only the saved cookie represents a new browser process.
            reopened = app.test_client()
            reopened.set_cookie('session', cookie.value)
            with patch('itsdangerous.timed.time.time', return_value=now + day*86400):
                result = reopened.get('/api/session')
                self.assertIsNotNone(result.json['user'])
                self.assertFalse(result.json['device_session'])
                row = self.row(reopened)
                cookie = reopened.get_cookie('session')
                deadline = now + (day+30)*86400
                self.assertEqual(row['expires'], deadline)
                self.assertAlmostEqual(cookie.expires.timestamp(), deadline, delta=1)
                self.assertEqual(reopened.get('/api/security/devices').json, [])
        with patch('itsdangerous.timed.time.time', return_value=now + 89*86400):
            self.assertEqual(reopened.get('/api/expenses').status_code, 401)
        with app.app_context():
            self.assertEqual(one('SELECT expires FROM login_sessions WHERE token_hash=?', (row['token_hash'],))['expires'], deadline)

    def test_valid_legacy_browser_session_renews_without_making_it_a_phone(self):
        now = time.time()
        original = self.row(self.owner)
        with app.app_context():
            db().execute('UPDATE login_sessions SET expires=?,user_version=0 WHERE token_hash=?',
                         (now + 3600, original['token_hash']))
            db().commit()
        with patch('security.clock', return_value=now):
            result = self.owner.get('/api/session')
            self.assertIsNotNone(result.json['user'])
            self.assertFalse(result.json['device_session'])
        renewed = self.row(self.owner)
        self.assertEqual(renewed['token_hash'], original['token_hash'])
        self.assertEqual(renewed['expires'], now + security.BROWSER_IDLE_SECONDS)

    def test_browser_agent_permissions_still_apply_after_renewal(self):
        with patch('security.clock', return_value=time.time() + 2*86400):
            self.assertEqual(self.agent.get('/api/adviser').status_code, 200)
            self.assertEqual(self.call(self.agent, 'expenses', {}).status_code, 403)

    def test_signature_age_accepts_device_after_twelve_hours(self):
        # Exercise the cookie signature clock as well as the database deadline.
        phone = self.phone(); cookie = phone.get_cookie('session').value
        replay = app.test_client(); replay.set_cookie('session', cookie)
        future = time.time() + 13*3600
        with patch('itsdangerous.timed.time.time', return_value=future):
            self.assertIsNotNone(replay.get('/api/session').json['user'])

    def test_existing_login_upgrade_rotates_token_and_requires_auth_and_csrf(self):
        old = self.owner.get_cookie('session').value
        copied = app.test_client(); copied.set_cookie('session', old)
        self.assertEqual(self.owner.post('/api/security/device-session', json={'device_name':'Phone'}).status_code, 403)
        self.assertEqual(self.call(self.owner, 'security/device-session', {'device_name':'Phone'}).status_code, 200)
        self.assertTrue(self.owner.get('/api/session').json['device_session'])
        self.assertIsNone(copied.get('/api/session').json['user'])
        first = self.row(self.owner)['token_hash']
        self.assertEqual(self.call(self.owner, 'security/device-session', {'device_name':'Phone'}).status_code, 200)
        self.assertEqual(self.row(self.owner)['token_hash'], first)
        anonymous = app.test_client()
        self.assertEqual(self.call(anonymous,'security/device-session',{'device_name':'Phone'}).status_code,401)
        self.assertEqual(self.call(self.agent,'security/device-session',{'device_name':'Agent phone'}).status_code,200)
        self.assertEqual(self.call(self.agent,'expenses',{}).status_code,403)

    def test_mfa_required_and_device_preference_survives_challenge(self):
        now = time.time(); secret = 'JBSWY3DPEHPK3PXP'
        with app.app_context():
            db().execute("UPDATE users SET totp_enabled=1,totp_secret=?,totp_last_step=-1 WHERE role='owner'", (security.box().encrypt(secret.encode()).decode(),)); db().commit()
        with patch('security.clock', return_value=now):
            phone = self.phone()
            self.assertTrue(phone.get('/api/session').json['mfa_required'])
            self.assertFalse(phone.get('/api/session').json['device_session'])
            self.assertEqual(self.call(phone,'security/device-session',{'device_name':'Phone'}).status_code,401)
            self.assertEqual(self.call(phone,'login/2fa',{'code':security.totp(secret,int(now)//30)}).status_code,200)
            self.assertTrue(phone.get('/api/session').json['device_session'])
        self.assertEqual(self.row(phone)['expires'], now + security.DEVICE_IDLE_SECONDS)
        pending = self.phone()
        with patch('security.clock', return_value=now + 600):
            self.assertEqual(self.call(pending,'login/2fa',{'code':security.totp(secret,int(now+600)//30)}).status_code,401)

    def test_devices_are_account_scoped_and_revocation_is_immediate(self):
        phone = self.phone(); another = self.phone()
        device = self.row(phone)['token_hash']
        other = self.row(another)['token_hash']
        self.assertEqual(len(self.owner.get('/api/security/devices').json),2)
        self.assertEqual(self.agent.get('/api/security/devices').json,[])
        self.assertEqual(self.call(self.agent,'security/devices',{'id':device},'DELETE').status_code,404)
        self.assertEqual(self.owner.delete('/api/security/devices',json={'id':device}).status_code,403)
        self.assertEqual(self.call(self.owner,'security/devices',{'id':device},'DELETE').status_code,200)
        self.assertIsNone(phone.get('/api/session').json['user'])
        self.assertIsNotNone(another.get('/api/session').json['user'])
        self.assertEqual(self.call(another,'security/devices',{'id':other},'DELETE').status_code,200)
        self.assertIsNone(another.get('/api/session').json['user'])

    def test_password_change_disable_and_logout_revoke_remembered_access(self):
        phone = self.phone()
        self.assertEqual(self.call(self.owner,'password',{'current':'Owner-password-123','password':'Owner-new-password-123'}).status_code,200)
        self.assertIsNone(phone.get('/api/session').json['user'])
        self.login(self.owner,'owner@example.test','Owner-new-password-123')
        self.assertEqual(self.owner.get('/api/security/devices').json,[])
        agent = self.phone('agent@example.test','Testing-password-123')
        uid = agent.get('/api/session').json['user']['id']
        self.assertEqual(self.call(self.owner,f'users/{uid}/access',{'active':False}).status_code,200)
        self.assertIsNone(agent.get('/api/session').json['user'])
        phone = self.phone(password='Owner-new-password-123')
        copied=app.test_client();copied.set_cookie('session',phone.get_cookie('session').value)
        self.assertEqual(self.call(phone,'logout',{}).status_code,200)
        self.assertIsNone(copied.get('/api/session').json['user'])

    @patch.dict(os.environ, {'PUSH_RELAY_URL':'https://relay.example/notify','PUSH_RELAY_TOKEN':'x'*40})
    def test_push_follows_device_session_without_extending_inactivity(self):
        now = time.time(); phone = self.phone()
        registration = dict(installation='00000000-0000-4000-8000-000000000001',token='a'*64,context='b'*64,
                            enabled=True,remote=True,quietHours=False,sounds=False,timezone='Australia/Brisbane',
                            quietStart=1320,quietEnd=420,receipts=True)
        self.assertEqual(self.call(phone,'notifications/device',registration,'PUT').status_code,200)
        before = self.row(phone)
        event = notifications.event('receipt-test','receipts','receipts')
        with app.app_context(), patch('notifications.time.time',return_value=now+13*3600), patch.object(notifications,'collect',return_value=[event]), patch.object(notifications,'deliver') as send:
            notifications.run_once(); send.assert_called_once()
            self.assertEqual(one('SELECT expires FROM login_sessions WHERE token_hash=?',(before['token_hash'],))['expires'],before['expires'])
        self.assertEqual(self.call(self.owner,'security/devices',{'id':before['token_hash']},'DELETE').status_code,200)
        with app.app_context():
            self.assertIsNone(one('SELECT 1 FROM notification_devices'))
