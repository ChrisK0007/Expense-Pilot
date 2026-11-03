"""Synthetic components-layout payslips; no private payroll data or AI calls."""
import unittest
from unittest.mock import patch
import test_app as base
from income_documents import local_payslip
import test_document_income as income_tests
payslip_pdf = income_tests.payslip_pdf

COMPONENTS = '''SYNTHETIC FLIGHT SERVICES PTY.
LTD.
ABN: 11111111111
Period Starting: 01/09/2026
Period Ending: 14/09/2026
Date Paid: 15/09/2026
Employee Id: 12345
Gross Earnings: $4,200.00
Net Payment: $3,150.00
Super Payments: $654.00
Pay Slip Components Hours/Units Rate This Pay Year To Date
Wages and Earnings
Salary 80.00 $50.00 $4,000.00 $20,000.00
Allowances - Meal 2.00 $100.00 $200.00 $1,000.00
Notes: Synthetic test data
$4,200.00 $21,000.00
Taxes
PAYG $900.00 $4,500.00
$900.00 $4,500.00
Superannuation Breakdown
SG $504.00 $2,520.00
Salary Sacrifice Super $150.00 $750.00
$654.00 $3,270.00
Bank Payments Account This Pay
Test Person 000000 - ****0000 $3,150.00
'''


class PayrollTableTests(unittest.TestCase):
    def test_current_columns_reconcile_with_salary_sacrifice_and_wrapped_employer(self):
        for text in (COMPONENTS, COMPONENTS.replace(' ', '   ')):
            with self.subTest(spaced=text != COMPONENTS):
                result = local_payslip(text)
                self.assertTrue(result['local_complete'])
                self.assertEqual(result['employer'], 'SYNTHETIC FLIGHT SERVICES PTY. LTD.')
                self.assertEqual(result['date'], '2026-09-15')
                self.assertEqual(result['period_start'], '2026-09-01')
                self.assertEqual(result['period_end'], '2026-09-14')
                self.assertEqual(result['gross'], 4050)
                self.assertEqual(result['withheld'], 900)
                self.assertEqual(result['net'], 3150)
                self.assertEqual(result['super'], 504)
                self.assertEqual(result['ytd_gross'], 20250)
                self.assertEqual(result['ytd_withheld'], 4500)
                self.assertIn('salary-sacrifice super ($150.00)', result['extraction_note'])

    def test_without_salary_sacrifice_and_zero_payg(self):
        text = COMPONENTS.replace('Salary Sacrifice Super $150.00 $750.00\n', '')
        text = text.replace('$654.00', '$504.00').replace('$3,270.00', '$2,520.00')
        text = text.replace('$900.00', '$0.00').replace('$3,150.00', '$4,200.00')
        result = local_payslip(text)
        self.assertTrue(result['local_complete'])
        self.assertEqual(result['gross'], 4200)
        self.assertEqual(result['withheld'], 0)
        self.assertNotIn('extraction_note', result)

    def test_ambiguous_columns_deductions_dates_and_totals_do_not_bypass_ai(self):
        variants = [
            COMPONENTS.replace('This Pay Year To Date', 'Year To Date This Pay'),
            COMPONENTS.replace('This Pay Year To Date', 'Year To Date'),
            COMPONENTS.replace('Net Payment: $3,150.00', 'Net Payment: $3,100.00'),
            COMPONENTS.replace('Gross Earnings: $4,200.00', 'Gross Earnings: $4,050.00'),
            COMPONENTS.replace('$4,200.00 $21,000.00', '$4,100.00 $21,000.00'),
            COMPONENTS.replace('$900.00 $4,500.00\nSuperannuation', '$901.00 $4,500.00\nSuperannuation'),
            COMPONENTS.replace('SG $504.00', 'SG $503.00'),
            COMPONENTS.replace('Salary Sacrifice Super', 'After-tax Super'),
            COMPONENTS.replace('Allowances - Meal', 'Non-taxable reimbursement'),
            COMPONENTS.replace('15/09/2026', '31/09/2026'),
            COMPONENTS.replace('01/09/2026', '20/09/2026'),
            COMPONENTS + 'Payment date: 30/09/2026\n',
            COMPONENTS + COMPONENTS.replace('15/09/2026', '30/09/2026'),
            COMPONENTS.replace('Date Paid:', 'Date Paid: 16/09/2026\nDate Paid:'),
            COMPONENTS.replace('Net Payment:', 'Net Payment: $3,100.00\nNet Payment:'),
        ]
        for index, text in enumerate(variants):
            with self.subTest(variant=index):
                result = local_payslip(text)
                self.assertFalse(result['local_complete'])
                self.assertIsNone(result['gross'])
                self.assertIsNone(result['withheld'])


class PayrollTableRouteTests(unittest.TestCase):
    setUp = base.AppTest.setUp
    login = base.AppTest.login
    call = base.AppTest.call
    upload = income_tests.IncomeDocumentTests.upload

    def test_pdf_retries_fill_empty_drafts_keep_manual_edits_and_never_call_ai(self):
        raw = payslip_pdf(COMPONENTS)
        rid = self.upload(raw).json['id']
        self.call(self.owner, f'receipts/{rid}/draft', dict(
            document_kind='payslip', employer='Reviewed name', date='', gross=None,
            withheld=0, period_start='', period_end='', notes='Keep my note'), 'PUT')
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract') as ai:
            result = self.call(self.owner, f'receipts/{rid}/extract', {})
        self.assertEqual(result.status_code, 200, result.json)
        ai.assert_not_called()
        self.assertEqual(result.json['gross'], 4050)
        self.assertEqual(result.json['withheld'], 900)
        self.assertEqual(result.json['currency'], 'AUD')
        self.assertIn('salary-sacrifice super', result.json['extraction_note'])
        row = self.owner.get('/api/receipts').json[0]
        shown = {**row['extraction'], **row['draft']}
        self.assertEqual(shown['gross'], 4050)
        self.assertEqual(shown['date'], '2026-09-15')
        self.assertEqual(shown['period_start'], '2026-09-01')
        self.assertEqual(shown['withheld'], 0)
        self.assertEqual(shown['employer'], 'Reviewed name')
        self.assertEqual(shown['notes'], 'Keep my note')
        self.assertEqual(self.owner.get('/api/employment').json, [])
        original = self.owner.get('/api/receipts/' + rid)
        self.assertEqual(original.data, raw)
        original.close()

    def test_ai_cannot_supply_a_local_calculation_note(self):
        rid = self.upload(payslip_pdf('PAYSLIP\nUnreadable synthetic columns')).json['id']
        with patch('ai_providers.configured', return_value=True), patch('ai_providers.extract', return_value=dict(
                document_kind='payslip', amounts_basis='period', extraction_note='Unverified model note')):
            result = self.call(self.owner, f'receipts/{rid}/extract', {})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('extraction_note', result.json)
