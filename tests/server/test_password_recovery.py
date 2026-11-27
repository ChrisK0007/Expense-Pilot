"""Ordinary recovery flows using synthetic accounts and captured SMTP only."""
import hashlib
import json
import re
import time
import unittest
import runpy
from pathlib import Path
from unittest.mock import patch
import test_app as base
from app import app, db
import billing
import password_recovery as recovery
import security


class RecoveryTest(unittest.TestCase):
    call = base.AppTest.call
    login = base.AppTest.login

    def setUp(self):
        base.AppTest.setUp(self)
        with app.app_context():
            billing.save_settings('email', {**billing.DEFAULT_MAIL, 'host': 'smtp.example.test', 'from_email': 'owner@example.test'})
            billing.save_settings('access', {'login_url': 'https://expenses.example.test'})
            db().execute("INSERT INTO email_verification(user_id,email,verified_at) SELECT id,email,1 FROM users WHERE role IN ('owner','tax_agent')")
            db().commit()
        self.mail = patch('billing.deliver', return_value=('sent', '')).start()
        self.addCleanup(patch.stopall)
        def inline(*args):
            recovery.deliver(*args)
            return True
        patch('password_recovery.enqueue', side_effect=inline).start()
        self.anonymous = app.test_client()

    def request(self, email='owner@example.test'):
        return self.call(self.anonymous, 'password-reset/request', {'email': email})

    def token(self):
        return re.search(r'token=([A-Za-z0-9_-]{43})', self.mail.call_args.args[2])[1]

    def test_neutral_request_verified_mailbox_and_single_use_session_revocation(self):
        neutral = self.request('unknown@example.test')
        self.mail.assert_not_called()
        response = self.request()
        self.assertEqual(response.json, neutral.json)
        token = self.token()
        self.assertNotIn(token, json.dumps(response.json))
        with app.app_context():
            row = db().execute('SELECT * FROM password_resets').fetchone()
            self.assertEqual(row['verifier'], hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(self.owner.get('/api/session').json['user']['role'], 'owner')
        self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', {'token': token, 'password': 'short'}).status_code, 400)
        good = {'token': token, 'password': 'Recovered-password-123'}
        self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', good).status_code, 200)
        self.assertIsNone(self.owner.get('/api/session').json['user'])
        self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', good).status_code, 400)
        self.login(self.owner, 'owner@example.test', good['password'])

    def test_expiry_resend_account_change_and_delivery_failure(self):
        self.request(); first = self.token()
        self.request(); second = self.token()
        self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', {'token': first, 'password': 'Recovered-password-123'}).status_code, 400)
        with patch('password_recovery.time.time', return_value=time.time() + 901):
            self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', {'token': second, 'password': 'Recovered-password-123'}).status_code, 400)
        with app.app_context():
            db().execute("UPDATE users SET email='changed@example.test' WHERE role='owner'"); db().commit()
        self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', {'token': second, 'password': 'Recovered-password-123'}).status_code, 400)
        self.mail.return_value = ('unknown', 'private provider detail')
        response = self.request('agent@example.test')
        self.assertNotIn('private provider detail', json.dumps(response.json))
        with app.app_context():
            self.assertEqual(db().execute('SELECT count(*) FROM password_resets WHERE email=?', ('agent@example.test',)).fetchone()[0], 0)

    def test_unverified_disabled_accounts_and_request_limit_stay_neutral(self):
        expected = self.request('unknown@example.test').json
        with app.app_context():
            db().execute("DELETE FROM email_verification WHERE email='owner@example.test'")
            db().execute("UPDATE users SET active=0 WHERE email='agent@example.test'"); db().commit()
        self.assertEqual(self.request().json, expected)
        self.assertEqual(self.request('agent@example.test').json, expected)
        self.mail.assert_not_called()
        for _ in range(4):
            self.assertEqual(self.request('staff@example.test').json, expected)
        self.assertEqual(self.mail.call_count, 3)

    def test_owner_initiation_requires_reauthentication_and_preserves_agent_mfa(self):
        with app.app_context():
            agent = db().execute("SELECT * FROM users WHERE email='agent@example.test'").fetchone()
            uid = agent['id']
            code = 'SYNTHETICRECOVERY'
            digest = hashlib.sha256(code.encode()).hexdigest()
            secret = security.box().encrypt(b'JBSWY3DPEHPK3PXP').decode()
            db().execute('UPDATE users SET totp_enabled=1,totp_secret=?,recovery_hashes=? WHERE id=?', (secret, json.dumps([digest]), uid)); db().commit()
        path = f'users/{uid}/password-reset'
        self.assertEqual(self.call(self.agent, path, {'password': 'Testing-password-123'}).status_code, 403)
        self.assertEqual(self.call(self.owner, path, {'password': 'wrong'}).status_code, 403)
        self.assertEqual(self.call(self.owner, path, {'password': 'Owner-password-123'}).status_code, 200)
        self.assertEqual(self.mail.call_args.args[0], 'agent@example.test')
        token = self.token()
        data = {'token': token, 'password': 'Recovered-agent-password-123'}
        self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', data).status_code, 401)
        self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', dict(data, code=code)).status_code, 200)
        self.assertIsNone(self.agent.get('/api/session').json['user'])
        with app.app_context():
            user = db().execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            self.assertEqual((user['role'], user['permission'], user['totp_enabled'], user['totp_secret']), (agent['role'], agent['permission'], 1, secret))
            self.assertEqual(json.loads(user['recovery_hashes']), [])
            self.assertEqual(db().execute('SELECT count(*) FROM login_sessions WHERE user_id=?', (uid,)).fetchone()[0], 0)
            self.assertNotIn(token, str([tuple(row) for row in db().execute('SELECT action,entity FROM audit')]))

    def test_changed_version_and_insecure_login_address_prevent_reset(self):
        self.request(); token = self.token()
        with app.app_context():
            db().execute("UPDATE users SET version=version+1 WHERE role='owner'"); db().commit()
        self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', {'token': token, 'password': 'Recovered-password-123'}).status_code, 400)
        self.mail.reset_mock()
        with app.app_context():
            billing.save_settings('access', {'login_url': 'http://expenses.example.test'}); db().commit()
        self.request('agent@example.test'); self.mail.assert_not_called()

    def test_terminal_fallback_still_revokes_sessions_and_old_links(self):
        self.request(); token = self.token()
        with patch('builtins.input', side_effect=['owner@example.test', 'n']), patch('getpass.getpass', return_value='Terminal-password-123'):
            runpy.run_path(str(Path(recovery.__file__).with_name('reset_password.py')))
        self.assertIsNone(self.owner.get('/api/session').json['user'])
        self.assertEqual(self.call(self.anonymous, 'password-reset/confirm', {'token': token, 'password': 'Recovered-password-123'}).status_code, 400)
        self.login(self.owner, 'owner@example.test', 'Terminal-password-123')

    def test_queue_failure_is_neutral_publicly_and_truthful_to_owner(self):
        with app.app_context():
            uid = db().execute("SELECT id FROM users WHERE email='agent@example.test'").fetchone()[0]
        with patch('password_recovery.enqueue', return_value=False):
            self.assertEqual(self.request().json, {'message': recovery.MESSAGE})
            response = self.call(self.owner, f'users/{uid}/password-reset', {'password': 'Owner-password-123'})
            self.assertEqual(response.status_code, 503)
            with app.app_context():
                self.assertEqual(db().execute('SELECT count(*) FROM password_resets').fetchone()[0], 0)
                self.assertEqual(db().execute('SELECT sum(count) FROM recovery_requests').fetchone()[0], 3)
        self.assertEqual(self.owner.get('/api/session').json['user']['role'], 'owner')
        self.assertEqual(self.agent.get('/api/session').json['user']['role'], 'tax_agent')

    def test_owner_mfa_required_to_initiate_reset(self):
        secret = 'JBSWY3DPEHPK3PXP'
        with app.app_context():
            db().execute("UPDATE users SET totp_enabled=1,totp_secret=? WHERE role='owner'", (security.box().encrypt(secret.encode()).decode(),))
            uid = db().execute("SELECT id FROM users WHERE email='agent@example.test'").fetchone()[0]
            db().commit()
        path = f'users/{uid}/password-reset'
        data = {'password': 'Owner-password-123'}
        self.assertEqual(self.call(self.owner, path, data).status_code, 401)
        data['code'] = security.totp(secret, int(security.clock()) // 30)
        self.assertEqual(self.call(self.owner, path, data).status_code, 200)
