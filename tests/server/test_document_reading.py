"""Slow reads never hold the browser request or create financial records."""
import threading
import time
import unittest
from unittest.mock import patch
import test_app as base
import test_document_income as income_tests
from app import app, db
import ai_providers
import document_reading
payslip_pdf = income_tests.payslip_pdf


class DocumentReadingTests(unittest.TestCase):
    setUp = base.AppTest.setUp
    login = base.AppTest.login
    call = base.AppTest.call
    upload = income_tests.IncomeDocumentTests.upload

    def wait(self, rid, token):
        for _ in range(300):
            response = self.owner.get(f'/api/receipts/{rid}/extract?job={token}')
            self.assertEqual(response.status_code, 200, response.json)
            if response.json['status'] != 'reading': return response.json
            time.sleep(.01)
        self.fail('Background read did not finish')

    def blocked(self, callback):
        entered, release = threading.Event(), threading.Event()
        def extract(*args):
            entered.set()
            if not release.wait(10): raise RuntimeError('Test failed to release reader')
            return callback()
        return entered, release, extract

    def test_slow_read_returns_job_deduplicates_and_keeps_results_private(self):
        rid = self.upload().json['id']
        other = self.upload(payslip_pdf('PAYSLIP\nOther synthetic original')).json['id']
        entered, release, extract = self.blocked(lambda: dict(document_kind='payslip', amounts_basis='period', gross=3000, withheld=650))
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', side_effect=extract) as remote:
            try:
                response = self.call(self.owner, f'receipts/{rid}/extract', {'background': True, 'unfiled_only': True})
                self.assertEqual(response.status_code, 202, response.json)
                token = response.json['job_id']
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.owner.get(f'/api/receipts/{rid}/extract?job={token}').json['status'], 'reading')
                self.assertEqual(self.call(self.owner, f'receipts/{rid}/extract', {'background': True}).json['job_id'], token)
                self.assertEqual(self.call(self.owner, f'receipts/{rid}/extract', {}).status_code, 409)
                self.assertEqual(app.test_client().get(f'/api/receipts/{rid}/extract?job={token}').status_code, 401)
                self.assertEqual(self.agent.get(f'/api/receipts/{rid}/extract?job={token}').status_code, 403)
                self.assertEqual(self.owner.get(f'/api/receipts/{other}/extract?job={token}').status_code, 404)
                self.assertEqual(self.owner.get('/api/employment').json, [])
            finally:
                release.set()
                result = self.wait(rid, token)
            self.assertEqual(remote.call_count, 1)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['result']['gross'], 3000)
        self.assertEqual(self.owner.get('/api/employment').json, [])
        self.assertEqual(self.owner.get('/api/expenses').json, [])

    def test_failure_preserves_original_and_draft_then_allows_retry(self):
        raw = payslip_pdf(); rid = self.upload(raw).json['id']
        self.call(self.owner, f'receipts/{rid}/draft', {'document_kind': 'payslip', 'notes': 'Keep my correction'}, 'PUT')
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', side_effect=ai_providers.AIError('AI provider timed out. Retry later.')):
            job = self.call(self.owner, f'receipts/{rid}/extract', {'background': True}).json
            result = self.wait(rid, job['job_id'])
        self.assertEqual(result['status'], 'failed'); self.assertEqual(result['error_status'], 502)
        original = self.owner.get(f'/api/receipts/{rid}'); self.assertEqual(original.data, raw); original.close()
        row = self.owner.get('/api/receipts').json[0]
        self.assertEqual(row['scan_status'], 'failed'); self.assertEqual(row['draft']['notes'], 'Keep my correction')
        with patch('ai_providers.configured', return_value=False):
            retry = self.call(self.owner, f'receipts/{rid}/extract', {'background': True}).json
            self.assertNotEqual(retry['job_id'], job['job_id'])
            self.assertEqual(self.wait(rid, retry['job_id'])['status'], 'complete')

    def test_unexpected_exception_has_safe_error_and_does_not_leave_reading(self):
        rid = self.upload().json['id']
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', side_effect=RuntimeError('private provider response')):
            with self.assertLogs(app.logger, level='ERROR'):
                job = self.call(self.owner, f'receipts/{rid}/extract', {'background': True}).json
                result = self.wait(rid, job['job_id'])
        self.assertEqual(result['status'], 'failed'); self.assertEqual(result['error_status'], 500)
        self.assertNotIn('private provider response', result['error'])
        self.assertEqual(self.owner.get('/api/receipts').json[0]['scan_status'], 'failed')

    def test_filed_during_background_read_is_not_overwritten(self):
        rid = self.upload().json['id']
        entered, release, extract = self.blocked(lambda: dict(document_kind='payslip', amounts_basis='period', gross=9999, withheld=999))
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', side_effect=extract):
            try:
                job = self.call(self.owner, f'receipts/{rid}/extract', {'background': True, 'unfiled_only': True}).json
                self.assertTrue(entered.wait(5))
                with app.app_context():
                    db().execute('INSERT INTO employment_income(date,employer,gross_cents,withheld_cents,receipt_id) VALUES (?,?,?,?,?)', ('2026-10-16', 'Synthetic', 1000, 200, rid)); db().commit()
            finally:
                release.set(); result = self.wait(rid, job['job_id'])
        self.assertEqual(result['error_status'], 409)
        self.assertEqual(self.owner.get('/api/employment').json[0]['gross_cents'], 1000)

    def test_reader_capacity_is_bounded_and_restart_status_is_actionable(self):
        first = self.upload().json['id']; second = self.upload(payslip_pdf('PAYSLIP\nSecond synthetic document')).json['id']
        entered, release, extract = self.blocked(lambda: {})
        with patch.object(document_reading, 'MAX_ACTIVE', 1), patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', side_effect=extract):
            try:
                job = self.call(self.owner, f'receipts/{first}/extract', {'background': True}).json
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.call(self.owner, f'receipts/{second}/extract', {'background': True}).status_code, 429)
            finally:
                release.set(); self.wait(first, job['job_id'])
        response = self.owner.get(f'/api/receipts/{first}/extract?job=unknown-after-restart')
        self.assertEqual(response.status_code, 404)
        self.assertIn('Check the saved draft', response.json['error'])

    def test_revoked_permission_cannot_save_background_suggestions(self):
        rid = self.upload().json['id']
        def revoke(*args):
            db().execute("UPDATE users SET version=version+1 WHERE email='owner@example.test'"); db().commit()
            return dict(document_kind='payslip', amounts_basis='period', gross=9999, withheld=999)
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', side_effect=revoke):
            job = self.call(self.owner, f'receipts/{rid}/extract', {'background': True}).json
            for _ in range(300):
                with app.app_context(): result = document_reading.status(rid, job['job_id'])
                if result['status'] != 'reading': break
                time.sleep(.01)
            else: self.fail('Read did not finish')
        self.assertEqual(result['error_status'], 403)
        self.assertEqual(self.owner.get(f'/api/receipts/{rid}/extract?job='+job['job_id']).status_code, 401)
        with app.app_context():
            record = db().execute('SELECT extraction,scan_status FROM receipt_details WHERE receipt_id=?', (rid,)).fetchone()
            self.assertNotIn('9999', record['extraction'])
            self.assertEqual(record['scan_status'], 'failed')
