"""Regression checks for revocation, retired accounts and bounded untrusted input."""
import hashlib
import io
import subprocess
import unittest
from unittest.mock import patch
import test_app as base
from app import app, db
import security
from pdf_safety import inspect_pdf

class HardeningTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login

    def test_logout_revokes_copied_cookie_without_logging_out_other_device(self):
        other=app.test_client();self.login(other,'owner@example.test','Owner-password-123')
        copied=self.owner.get_cookie('session').value
        self.assertEqual(self.call(self.owner,'logout',{}).status_code,200)
        replay=app.test_client();replay.set_cookie('session',copied)
        self.assertEqual(replay.get('/api/expenses').status_code,401)
        self.assertEqual(other.get('/api/expenses').status_code,200)

    def test_old_cookie_and_absolute_expiry_are_rejected(self):
        with self.owner.session_transaction() as state: state.pop('sid')
        self.assertEqual(self.owner.get('/api/expenses').status_code,401)
        self.login(self.owner,'owner@example.test','Owner-password-123')
        with app.app_context(): db().execute('UPDATE login_sessions SET expires=1');db().commit()
        self.assertEqual(self.owner.get('/api/expenses').status_code,401)

    def test_pending_factor_cookie_is_revoked_on_logout(self):
        uid=self.owner.get('/api/session').json['user']['id']
        with app.app_context(): db().execute('UPDATE users SET totp_enabled=1 WHERE id=?',(uid,));db().commit()
        pending=app.test_client();self.login(pending,'owner@example.test','Owner-password-123')
        copied=pending.get_cookie('session').value
        self.call(pending,'logout',{})
        replay=app.test_client();replay.set_cookie('session',copied)
        with patch('security.factor') as factor:
            self.assertEqual(self.call(replay,'login/2fa',{'code':'123456'}).status_code,401)
            factor.assert_not_called()

    def test_account_rate_limit_survives_ip_rotation(self):
        c=app.test_client()
        for n in range(8):
            token=c.get('/api/session').json['csrf']
            self.assertEqual(c.post('/api/login',json={'email':'owner@example.test','password':'wrong'},headers={'X-CSRF-Token':token},environ_overrides={'REMOTE_ADDR':f'192.0.2.{n+1}'}).status_code,401)
        self.assertEqual(self.call(c,'login',{'email':'owner@example.test','password':'Owner-password-123'}).status_code,429)
        with app.app_context():db().execute('UPDATE attempts SET until=1');db().commit()
        self.login(c,'owner@example.test','Owner-password-123')

    def test_source_rate_limit_survives_changing_email_and_forwarding_header(self):
        c=app.test_client()
        for n in range(40):
            token=c.get('/api/session').json['csrf']
            response=c.post('/api/login',json={'email':f'unknown{n}@example.test','password':'wrong'},headers={'X-CSRF-Token':token,'X-Forwarded-For':f'192.0.2.{n+1}'},environ_overrides={'REMOTE_ADDR':'192.0.2.200'})
            self.assertEqual(response.status_code,401)
        token=c.get('/api/session').json['csrf']
        self.assertEqual(c.post('/api/login',json={'email':'new@example.test','password':'wrong'},headers={'X-CSRF-Token':token},environ_overrides={'REMOTE_ADDR':'192.0.2.200'}).status_code,429)

    def test_employee_invitation_and_existing_cookie_are_rejected(self):
        with patch('security.invite_ready',return_value={}):
            self.assertEqual(self.call(self.owner,'users',{'role':'employee','name':'Removed role','email':'removed@example.test'}).status_code,400)
        with app.app_context():
            uid=db().execute("SELECT id FROM users WHERE role='employee'").fetchone()['id']
        token='synthetic-retired-session'
        with app.app_context():
            db().execute('INSERT INTO login_sessions(token_hash,user_id,kind,expires) VALUES (?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,'auth',security.clock()+3600));db().commit()
        with self.staff2.session_transaction() as state:state.update(uid=uid,version=1,sid=token)
        self.assertEqual(self.staff2.get('/api/expenses').status_code,401)

    def test_pdf_limits_and_invalid_input(self):
        from pypdf import PdfWriter
        for count in (1,9):
            pdf=PdfWriter()
            for _ in range(count):pdf.add_blank_page(width=100,height=100)
            buf=io.BytesIO();pdf.write(buf)
            if count==1:self.assertEqual(inspect_pdf(buf.getvalue())['pages'],1)
            else:
                with self.assertRaises(ValueError):inspect_pdf(buf.getvalue())
        with self.assertRaises(ValueError):inspect_pdf(b'not a PDF')
        with patch('pdf_safety.subprocess.run',side_effect=subprocess.TimeoutExpired('pdf',15)):
            with self.assertRaises(ValueError):inspect_pdf(b'%PDF')

    def test_secure_cookie_configuration_and_hsts(self):
        with patch.dict(app.config,{'SESSION_COOKIE_SECURE':True}):
            response=app.test_client().get('/api/session')
            self.assertIn('Secure',response.headers['Set-Cookie'])
            self.assertEqual(response.headers['Strict-Transport-Security'],'max-age=31536000')

    def test_parallel_pdf_requests_wait_for_bounded_workers(self):
        from concurrent.futures import ThreadPoolExecutor
        from pypdf import PdfWriter
        pdf=PdfWriter();pdf.add_blank_page(width=100,height=100)
        buf=io.BytesIO();pdf.write(buf)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(inspect_pdf,[buf.getvalue()]*4))
        self.assertEqual([r['pages'] for r in results],[1,1,1,1])
