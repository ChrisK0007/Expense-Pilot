"""Local/AI boundaries use synthetic payroll text and mocked network calls."""
import unittest
import urllib.error
from unittest.mock import MagicMock, patch
import test_app as base
import ai_providers
from income_documents import local_payslip
import test_document_income as income_tests
payslip_pdf = income_tests.payslip_pdf


class PayslipTimeoutTests(unittest.TestCase):
    setUp = base.AppTest.setUp
    login = base.AppTest.login
    call = base.AppTest.call
    upload = income_tests.IncomeDocumentTests.upload

    def test_complete_current_pay_bypasses_unavailable_ai(self):
        raw = payslip_pdf(); rid = self.upload(raw).json['id']
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', side_effect=ai_providers.AIError('timeout')) as remote:
            result = self.call(self.owner, f'receipts/{rid}/extract', {})
        self.assertEqual(result.status_code, 200, result.json)
        remote.assert_not_called()
        self.assertEqual(result.json['gross'], 3000)
        self.assertEqual(result.json['withheld'], 650)
        self.assertEqual(result.json['extraction_method'], 'local labels')
        self.assertNotIn('local_complete', result.json)
        self.assertEqual(self.owner.get('/api/employment').json, [])
        original = self.owner.get(f'/api/receipts/{rid}')
        self.assertEqual(original.data, raw); original.close()

    def test_timeout_retains_partial_fields_and_manual_draft_for_review(self):
        raw = payslip_pdf('PAYSLIP\nEmployer: Synthetic Aviation Pty Ltd\nPayment date: 16/10/2026\nThis pay Gross taxable pay: AUD 3000.00\nPAYG column not readable')
        rid = self.upload(raw).json['id']
        self.call(self.owner, f'receipts/{rid}/draft', {'document_kind': 'payslip', 'notes': 'My correction', 'withheld': 650}, 'PUT')
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', side_effect=ai_providers.AIError('timeout')) as remote:
            result = self.call(self.owner, f'receipts/{rid}/extract', {})
        remote.assert_called_once()
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['gross'], 3000)
        self.assertIsNone(result.json['withheld'])
        self.assertIn('AI reading was unavailable', result.json['extraction_warning'])
        row = self.owner.get('/api/receipts').json[0]
        self.assertEqual(row['scan_status'], 'scanned')
        self.assertEqual(row['draft']['withheld'], 650)
        self.assertEqual(row['draft']['notes'], 'My correction')
        self.assertEqual(self.owner.get('/api/employment').json, [])

    def test_ytd_heading_elsewhere_cannot_enable_current_pay_shortcut(self):
        result = local_payslip('PAYSLIP\nEmployer: Synthetic\nPayment date: 16/10/2026\nThis pay hours 40\nYTD\nGross pay: 21000.00\nPAYG: 4550.00')
        self.assertFalse(result['local_complete'])
        self.assertIsNone(result['gross']); self.assertIsNone(result['withheld'])

    def test_zero_withholding_is_complete_but_ambiguous_amounts_are_not(self):
        header = 'PAYSLIP\nEmployer: Synthetic\nPayment date: 16/10/2026\nThis pay Gross taxable pay: AUD 100.00\n'
        self.assertTrue(local_payslip(header + 'This pay PAYG: AUD 0.00')['local_complete'])
        self.assertFalse(local_payslip(header + 'This pay PAYG: AUD 101.00')['local_complete'])
        self.assertFalse(local_payslip(header + 'This pay PAYG: AUD 20.00\nThis pay Gross taxable pay: AUD 200.00')['local_complete'])

    def test_employment_prompt_omits_unrelated_expense_fields(self):
        rid = self.upload(payslip_pdf('PAYSLIP\nSynthetic multi-column payroll document.')).json['id']
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', return_value={'document_kind': 'payslip'}) as remote:
            self.assertEqual(self.call(self.owner, f'receipts/{rid}/extract', {}).status_code, 200)
        prompt = remote.call_args.args[0]
        self.assertIn('NEVER YTD', prompt)
        self.assertIn('Synthetic multi-column', prompt)
        self.assertNotIn('merchant_city', prompt)
        self.assertNotIn('Breakfast', prompt)

    def test_annual_statement_cannot_use_local_payslip_shortcut(self):
        rid = self.upload().json['id']
        self.call(self.owner, f'receipts/{rid}/draft', {'document_kind': 'income_statement'}, 'PUT')
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', side_effect=ai_providers.AIError('timeout')) as remote:
            result = self.call(self.owner, f'receipts/{rid}/extract', {})
        remote.assert_called_once(); self.assertEqual(result.status_code, 502)


class OllamaRequestTests(unittest.TestCase):
    config = dict(mode='remote_ollama', url='http://ollama:11434', model='qwen3:4b', key_encrypted='', provider='openai')

    def test_ollama_request_disables_thinking_and_bounds_output(self):
        with patch('ai_providers.config', return_value=self.config), patch('ai_providers.fetch', return_value={'message': {'content': '{"gross": 3000}'}}) as remote:
            self.assertEqual(ai_providers.extract('Return JSON', [])['gross'], 3000)
        payload = remote.call_args.args[2]
        self.assertIs(payload['think'], False)
        self.assertEqual(payload['options']['num_predict'], 2048)
        self.assertEqual(payload['format'], 'json')

    def test_truncated_json_is_not_accepted_even_if_parseable(self):
        with patch('ai_providers.config', return_value=self.config), patch('ai_providers.fetch', return_value={'done_reason': 'length', 'message': {'content': '{"gross": 3000}'}}):
            with self.assertRaisesRegex(ai_providers.AIError, 'response limit'):
                ai_providers.extract('Return JSON', [])

    def test_timeouts_are_provider_specific_and_models_check_stays_short(self):
        response = MagicMock(); response.__enter__.return_value.read.return_value = b'{}'
        for config, payload, expected in [(self.config, {'model': 'test'}, 300), (self.config, None, 20), ({**self.config, 'mode': 'cloud'}, {'model': 'test'}, 150)]:
            with self.subTest(timeout=expected), patch('ai_providers.urllib.request.OpenerDirector.open', return_value=response) as request:
                ai_providers.fetch(config, '/api/chat', payload)
                self.assertEqual(request.call_args.kwargs['timeout'], expected)

    def test_direct_and_wrapped_socket_timeouts_are_actionable(self):
        for error in (TimeoutError(), urllib.error.URLError(TimeoutError())):
            with self.subTest(error=type(error)), patch('ai_providers.urllib.request.OpenerDirector.open', side_effect=error):
                with self.assertRaisesRegex(ai_providers.AIError, 'Ollama.*5 minutes'):
                    ai_providers.fetch(self.config, '/api/chat', {'model': 'test'})


if __name__ == '__main__':
    unittest.main()
