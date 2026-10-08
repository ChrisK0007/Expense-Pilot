"""Security integration tests with simulated email delivery and deterministic clocks."""
import hashlib
import json
import time
import unittest
from unittest.mock import patch
import test_app as base
from app import app, db, one
import billing
import security

class SecurityTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login

    def config(self):
        self.assertEqual(self.call(self.owner,'security/invitations',{'login_url':'https://expenses.example.test'},'PUT').status_code,200)
        with app.app_context():
            billing.save_settings('email',{**billing.DEFAULT_MAIL,'host':'smtp.example.test','from_email':'owner@example.test'})
            db().commit()

    def invite(self,status='sent'):
        self.config()
        with patch('billing.deliver',return_value=(status,'Simulated mail failure.' if status!='sent' else '')) as send:
            r=self.call(self.owner,'users',{'name':'Invited','email':'invited@example.test','role':'tax_agent','password':'Must-be-ignored-123'})
        self.assertEqual(r.status_code,200,r.json)
        message=send.call_args.args[2]
        temp=message.split('Temporary password: ')[1].splitlines()[0]
        return r.json,temp

    def enable(self,client=None):
        client=client or self.owner
        password='Owner-password-123' if client==self.owner else 'Testing-password-123'
        with patch('security.clock',return_value=1800000000):
            result=self.call(client,'security/2fa/setup',{'password':password})
        self.assertEqual(result.status_code,200,result.json); secret=result.json['secret']
        self.assertTrue(result.json['qr'].startswith('data:image/png;base64,'))
        with patch('security.clock',return_value=1800000000):
            code=security.totp(secret,1800000000//30)
            result=self.call(client,'security/2fa/confirm',{'code':code})
        self.assertEqual(result.status_code,200,result.json)
        return secret,result.json['recovery_codes']

    def test_invitation_requires_configuration_and_valid_url(self):
        self.assertEqual(self.call(self.owner,'users',{'name':'New','email':'new@example.test','role':'employee'}).status_code,409)
        for url in ['javascript:alert(1)','https://user:pass@example.test','https://example.test/?token=x','https://example.test/path','https://example.test:bad']:
            self.assertEqual(self.call(self.owner,'security/invitations',{'login_url':url},'PUT').status_code,400)
        self.assertEqual(self.call(self.staff,'security/invitations',{'login_url':'https://example.test'},'PUT').status_code,403)

    def test_invitation_forces_change_and_never_exposes_temp_password(self):
        result,temp=self.invite()
        self.assertEqual(result['invitation_status'],'sent');self.assertNotIn(temp,json.dumps(result))
        self.assertNotEqual(temp,'Must-be-ignored-123');self.assertGreaterEqual(len(temp),20)
        client=app.test_client();self.login(client,'invited@example.test',temp)
        self.assertTrue(client.get('/api/session').json['user']['must_change_password'])
        for path in ['expenses','receipts','trips','billing/documents','security','export']:
            self.assertEqual(client.get('/api/'+path).status_code,403,path)
        self.assertEqual(self.call(client,'password',{'current':temp,'password':temp}).status_code,400)
        self.assertEqual(self.call(client,'password',{'current':temp,'password':'My-permanent-pass-123'}).status_code,200)
        self.assertEqual(self.call(client,'login',{'email':'invited@example.test','password':temp}).status_code,401)
        self.login(client,'invited@example.test','My-permanent-pass-123')
        self.assertEqual(client.get('/api/expenses').status_code,200)
        with app.app_context():
            row=one('SELECT * FROM users WHERE id=?',(result['id'],))
            self.assertFalse(row['must_change_password']);self.assertEqual(row['invite_status'],'accepted')
            self.assertNotIn(temp,row['password'])

    def test_invitation_failure_resend_expiry_and_disable(self):
        result,temp=self.invite('failed');uid=result['id']
        self.assertEqual(result['invitation_status'],'failed')
        client=app.test_client()
        with app.app_context():
            db().execute('UPDATE users SET invite_expires=1 WHERE id=?',(uid,));db().commit()
        self.assertEqual(self.call(client,'login',{'email':'invited@example.test','password':temp}).status_code,401)
        with patch('billing.deliver',return_value=('sent','')) as send:
            self.assertEqual(self.call(self.owner,f'users/{uid}/invite',{}).status_code,200)
        temp2=send.call_args.args[2].split('Temporary password: ')[1].splitlines()[0]
        self.assertNotEqual(temp,temp2)
        self.assertEqual(self.call(client,'login',{'email':'invited@example.test','password':temp}).status_code,401)
        self.login(client,'invited@example.test',temp2)
        self.call(self.owner,f'users/{uid}/access',{'active':False})
        self.assertIsNone(client.get('/api/session').json['user'])
        self.assertEqual(self.call(self.owner,f'users/{uid}/invite',{}).status_code,409)

    def test_unknown_mail_delivery_is_recorded_and_not_auto_retried(self):
        result,_=self.invite('unknown');self.assertEqual(result['invitation_status'],'unknown')
        self.assertEqual(sum(u['email']=='invited@example.test' for u in self.owner.get('/api/users').json),1)

    def test_totp_rfc_vectors(self):
        import base64
        secret=base64.b32encode(b'12345678901234567890').decode()
        for timestamp,expected in [(59,'287082'),(1111111109,'081804'),(1111111111,'050471'),(1234567890,'005924'),(2000000000,'279037'),(20000000000,'353130')]:
            self.assertEqual(security.totp(secret,timestamp//30),expected)

    def test_2fa_login_replay_recovery_and_encrypted_storage(self):
        secret,codes=self.enable()
        with app.app_context():
            user=one("SELECT * FROM users WHERE email='owner@example.test'")
            self.assertNotIn(secret,user['totp_secret']);self.assertEqual(len(json.loads(user['recovery_hashes'])),10)
            self.assertNotIn(codes[0].replace('-',''),user['recovery_hashes'])
        other=app.test_client()
        with patch('security.clock',return_value=1800000030):
            result=self.call(other,'login',{'email':'owner@example.test','password':'Owner-password-123'})
            self.assertTrue(result.json['mfa_required']);self.assertIsNone(other.get('/api/session').json['user'])
            self.assertEqual(other.get('/api/expenses').status_code,401)
            code=security.totp(secret,1800000030//30)
            self.assertEqual(self.call(other,'login/2fa',{'code':code}).status_code,200)
            self.assertEqual(other.get('/api/expenses').status_code,200)
            self.call(other,'logout',{})
            self.login(other,'owner@example.test','Owner-password-123')
            self.assertEqual(self.call(other,'login/2fa',{'code':code}).status_code,401)
            self.assertEqual(self.call(other,'login/2fa',{'code':codes[0]}).status_code,200)
            self.call(other,'logout',{});self.login(other,'owner@example.test','Owner-password-123')
            self.assertEqual(self.call(other,'login/2fa',{'code':codes[0]}).status_code,401)
            self.assertEqual(self.call(other,'login/2fa',{'code':codes[1]}).status_code,200)

    def test_2fa_throttling_survives_new_password_challenge(self):
        _,codes=self.enable();client=app.test_client()
        self.login(client,'owner@example.test','Owner-password-123')
        for _ in range(8):self.assertEqual(self.call(client,'login/2fa',{'code':'not-a-code'}).status_code,401)
        self.login(client,'owner@example.test','Owner-password-123')
        self.assertEqual(self.call(client,'login/2fa',{'code':codes[0]}).status_code,429)

    def test_expired_challenge_and_disabled_account_cannot_verify(self):
        _,codes=self.enable(self.staff);client=app.test_client();self.login(client,'staff@example.test','Testing-password-123')
        with client.session_transaction() as s:s['mfa_until']=1
        self.assertEqual(self.call(client,'login/2fa',{'code':codes[0]}).status_code,401)
        self.login(client,'staff@example.test','Testing-password-123')
        uid=self.staff.get('/api/session').json['user']['id']
        self.call(self.owner,f'users/{uid}/access',{'active':False})
        self.assertEqual(self.call(client,'login/2fa',{'code':codes[0]}).status_code,401)

    def test_readonly_agent_can_manage_own_2fa_and_setup_revokes_sessions(self):
        other=app.test_client();self.login(other,'agent@example.test','Testing-password-123')
        _,codes=self.enable(self.agent)
        self.assertEqual(other.get('/api/expenses').status_code,401)
        self.assertEqual(self.call(self.agent,'security/2fa/disable',{'password':'Testing-password-123','code':'wrong'}).status_code,401)
        self.assertEqual(self.call(self.agent,'security/2fa/disable',{'password':'Testing-password-123','code':codes[0]}).status_code,200)
        self.assertFalse(self.agent.get('/api/security').json['enabled'])
        self.assertEqual(self.call(self.agent,'expenses',{}).status_code,403)

    def test_setup_confirmation_expiry_and_password_change_requires_factor(self):
        self.call(self.owner,'security/2fa/setup',{'password':'Owner-password-123'})
        with app.app_context():
            db().execute('UPDATE users SET totp_pending_until=1');db().commit()
        self.assertEqual(self.call(self.owner,'security/2fa/confirm',{'code':'000000'}).status_code,409)
        _,codes=self.enable()
        self.assertEqual(self.call(self.owner,'password',{'current':'Owner-password-123','password':'Owner-new-password-123'}).status_code,401)
        self.assertEqual(self.call(self.owner,'password',{'current':'Owner-password-123','password':'Owner-new-password-123','code':codes[0]}).status_code,200)
