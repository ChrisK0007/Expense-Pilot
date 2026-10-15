import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
import zipfile
from unittest.mock import patch
from PIL import Image
import test_app as base
from app import app, db
import ai_providers
import billing
from restore_backup import restore


class PublicReleaseTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login
    expense = base.AppTest.expense

    def upload(self, ref):
        data = io.BytesIO(); Image.new('RGB', (20, 20), 'blue').save(data, 'PNG'); data.seek(0)
        return self.owner.post('/api/receipts', data={'file': (data, 'test.png'), 'client_ref': ref}, headers={'X-CSRF-Token': self.owner.get('/api/session').json['csrf']})

    def test_ai_defaults_upgrade_and_secret_isolation(self):
        with patch.dict(os.environ, {'OLLAMA_URL': '', 'OLLAMA_MODEL': ''}):
            self.assertEqual(self.owner.get('/api/ai/settings').json['mode'], 'none')
        with patch.dict(os.environ, {'OLLAMA_URL': 'http://old-ollama:11434', 'OLLAMA_MODEL': 'gemma3:4b'}):
            self.assertEqual(self.owner.get('/api/ai/settings').json['model'], 'gemma3:4b')
        values = dict(mode='cloud', provider='openai', model='vision-test', api_key='test-secret', cloud_consent=False)
        self.assertEqual(self.call(self.owner, 'ai/settings', values, 'PUT').status_code, 400)
        values['cloud_consent'] = True
        result = self.call(self.owner, 'ai/settings', values, 'PUT')
        self.assertEqual(result.status_code, 200, result.json)
        self.assertNotIn('test-secret', result.data.decode()); self.assertTrue(result.json['key_saved'])
        with app.app_context(): self.assertNotIn('test-secret', db().execute("SELECT value FROM billing_settings WHERE key='receipt_ai'").fetchone()[0])
        self.assertEqual(self.agent.get('/api/ai/settings').status_code, 403)
        self.assertNotIn('key_encrypted', self.owner.get('/api/session').data.decode())
        self.assertEqual(self.call(self.owner, 'ai/settings', dict(values, provider='anthropic', api_key=''), 'PUT').status_code, 400)
        self.assertEqual(self.call(self.owner, 'ai/settings', {'mode': 'none'}, 'PUT').status_code, 200)
        with patch('ai_providers.fetch') as remote:
            with app.app_context(), self.assertRaises(ai_providers.AIError): ai_providers.extract('JSON', [])
            remote.assert_not_called()

    def test_cloud_request_shapes_and_no_fallback(self):
        for provider in ('openai', 'anthropic'):
            self.call(self.owner, 'ai/settings', dict(mode='cloud', provider=provider, model='vision-test', api_key='secret', cloud_consent=True), 'PUT')
            output = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': '{"merchant":"Cafe"}'}]}]} if provider == 'openai' else {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '{"merchant":"Cafe"}'}]}
            with app.app_context(), patch('ai_providers.fetch', return_value=output) as remote:
                self.assertEqual(ai_providers.extract('Return JSON', ['abc'])['merchant'], 'Cafe')
                payload = remote.call_args.args[2]
                self.assertEqual(payload['model'], 'vision-test')
                if provider == 'openai': self.assertFalse(payload['store']); self.assertEqual(payload['input'][0]['content'][1]['image_url'], 'data:image/jpeg;base64,abc')
            with app.app_context(), patch('ai_providers.fetch', side_effect=ai_providers.AIError('Quota reached')) as remote:
                with self.assertRaises(ai_providers.AIError): ai_providers.extract('JSON', [])
                remote.assert_called_once()

    def test_ollama_url_and_redirect_validation(self):
        for bad in ('http://example.com', 'https://user:pass@example.com', 'file:///etc/passwd', 'http://ollama/api/chat', 'http://ollama/#secret'):
            with self.assertRaises(ai_providers.AIError): ai_providers.validate_url(bad)
        self.assertEqual(ai_providers.validate_url('http://192.168.3.25:11434/'), 'http://192.168.3.25:11434')
        with self.assertRaises(ai_providers.AIError): ai_providers.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.example')

    def test_mobile_expense_retry_conflict_and_deletion(self):
        ref = str(uuid.uuid4())
        first = self.expense(self.owner, client_ref=ref)
        second = self.expense(self.owner, client_ref=ref)
        self.assertEqual(first.json, second.json); self.assertTrue(first.json['stored'])
        self.assertEqual(len(self.owner.get('/api/expenses').json), 1)
        self.assertEqual(self.expense(self.owner, client_ref=ref, amount=999).status_code, 409)
        self.call(self.owner, 'expenses/'+str(first.json['id']), {}, 'DELETE')
        self.assertEqual(self.expense(self.owner, client_ref=ref).status_code, 409)
        self.assertEqual(self.owner.get('/api/expenses').json, [])

    def test_mobile_receipt_retry_and_deletion(self):
        ref = str(uuid.uuid4()); first = self.upload(ref)
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(self.upload(ref).json['id'], first.json['id'])
        self.call(self.owner, 'receipts/'+first.json['id'], {}, 'DELETE')
        self.assertEqual(self.upload(ref).status_code, 409)

    @patch('billing.smtplib.SMTP_SSL')
    def test_bcc_copy_and_partial_rejection(self, smtp):
        values = dict(host='smtp.example.test', port=465, security='ssl', from_email='sender@example.test', copy_self=True, copy_email='owner@example.test')
        self.assertEqual(self.call(self.owner, 'billing/email-settings', values, 'PUT').status_code, 200)
        with app.app_context():
            smtp.return_value.send_message.return_value = {}
            billing.deliver('client@example.test', 'Invoice', 'Message', b'pdf', 'invoice.pdf', copy=True)
            outgoing = smtp.return_value.send_message.call_args.args[0]
            self.assertEqual(outgoing['Bcc'], 'owner@example.test'); self.assertEqual(outgoing['To'], 'client@example.test')
            self.assertTrue(any(x.get_filename() == 'invoice.pdf' for x in outgoing.walk()))
            billing.deliver('agent@example.test', 'Invitation', 'Private password')
            self.assertIsNone(smtp.return_value.send_message.call_args.args[0]['Bcc'])
            smtp.return_value.send_message.return_value = {'owner@example.test': (550, b'refused')}
            self.assertEqual(billing.deliver('client@example.test', 'Invoice', 'Message', copy=True)[0], 'sent')
            smtp.return_value.send_message.return_value = {'client@example.test': (550, b'refused')}
            self.assertEqual(billing.deliver('client@example.test', 'Invoice', 'Message', copy=True)[0], 'failed')

    def test_backup_restore_and_tamper_rejection(self):
        self.expense(self.owner); self.upload(str(uuid.uuid4()))
        self.assertEqual(self.call(self.agent, 'data/backup', {}).status_code, 403)
        self.assertEqual(self.call(self.owner, 'data/backup', {'password': 'wrong'}).status_code, 403)
        response = self.call(self.owner, 'data/backup', {'password': 'Owner-password-123'})
        self.assertEqual(response.status_code, 200)
        raw = response.data
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); archive = root/'backup.zip'; archive.write_bytes(raw)
            restore(archive, root/'restored')
            import sqlite3
            con = sqlite3.connect(root/'restored/rounded.sqlite')
            self.assertEqual(con.execute('SELECT count(*) FROM expenses').fetchone()[0], 1)
            self.assertEqual(con.execute('SELECT count(*) FROM login_sessions').fetchone()[0], 0); con.close()
            with self.assertRaises(ValueError): restore(archive, root/'restored')
            with zipfile.ZipFile(archive, 'a') as zipped: zipped.writestr('../outside', b'bad')
            with self.assertRaises(ValueError): restore(archive, root/'invalid')
            self.assertFalse((root/'outside').exists())

    def test_account_deletion_requires_reauth_and_removes_workspace(self):
        self.expense(self.owner); rid = self.upload(str(uuid.uuid4())).json['id']
        old_id = self.owner.get('/api/session').json['user']['id']
        old_instance = self.owner.get('/api/server-info').json['instance_id']
        self.assertEqual(self.call(self.owner, 'account', {'password': 'Owner-password-123'}, 'DELETE').status_code, 400)
        result = self.call(self.owner, 'account', {'password': 'Owner-password-123', 'confirmation': 'DELETE WORKSPACE'}, 'DELETE')
        self.assertEqual(result.status_code, 200, result.json)
        self.assertTrue(self.owner.get('/api/session').json['setup'])
        self.assertNotEqual(self.owner.get('/api/server-info').json['instance_id'], old_instance)
        self.assertEqual(self.agent.get('/api/expenses').status_code, 401)
        from app import DATA
        self.assertFalse((DATA/'receipts'/rid).exists())
        self.call(self.owner, 'setup', dict(token=os.environ['SETUP_TOKEN'], name='New owner', email='new@example.test', password='Owner-password-123'))
        self.login(self.owner, 'new@example.test', 'Owner-password-123')
        self.assertGreater(self.owner.get('/api/session').json['user']['id'], old_id)

    def test_tax_agent_can_delete_own_read_only_account(self):
        self.expense(self.owner)
        result = self.call(self.agent, 'account', dict(password='Testing-password-123', confirmation='DELETE ACCOUNT'), 'DELETE')
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(len(self.owner.get('/api/expenses').json), 1)
