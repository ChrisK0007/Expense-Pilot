"""Synthetic payslips and document filing. Never sends payroll data externally."""
import io
import unittest
from unittest.mock import patch
from reportlab.pdfgen import canvas
import test_app as base
from app import app, db
from income_documents import local_payslip, clean


def payslip_pdf(text=None):
    content=text or 'PAYSLIP\nEmployer: Synthetic Aviation Pty Ltd\nPayment date: 16/10/2026\nPay period: 01/10/2026 to 14/10/2026\nThis pay Gross taxable pay: AUD 3000.00\nThis pay PAYG tax withheld: AUD 650.00\nNet pay: AUD 2350.00\nYTD gross: AUD 21000.00\nYTD tax: AUD 4550.00'
    out=io.BytesIO();pdf=canvas.Canvas(out);y=800
    for line in content.splitlines():pdf.drawString(40,y,line);y-=18
    pdf.save();return out.getvalue()


class IncomeDocumentTests(unittest.TestCase):
    setUp=base.AppTest.setUp
    login=base.AppTest.login
    call=base.AppTest.call
    expense=base.AppTest.expense

    def upload(self,raw=None):
        return self.owner.post('/api/receipts',data={'file':(io.BytesIO(raw or payslip_pdf()),'synthetic-payslip.pdf'),'document_kind':'payslip'},headers={'X-CSRF-Token':self.owner.get('/api/session').json['csrf']})

    def values(self,**updates):
        return dict(date='2026-10-16',employer='Synthetic Aviation Pty Ltd',gross=3000,withheld=650,
                    period_start='2026-10-01',period_end='2026-10-14',record_kind='payslip',reviewed=True,currency='AUD',**updates)

    def test_local_text_extraction_requires_review_and_preserves_original(self):
        raw=payslip_pdf();rid=self.upload(raw).json['id']
        with patch('ai_providers.configured',return_value=False),patch('ai_providers.extract') as remote:
            result=self.call(self.owner,f'receipts/{rid}/extract',{'unfiled_only':True})
        self.assertEqual(result.status_code,200,result.json);remote.assert_not_called()
        self.assertEqual(result.json['gross'],3000);self.assertEqual(result.json['withheld'],650)
        self.assertEqual(result.json['date'],'2026-10-16');self.assertEqual(result.json['document_kind'],'payslip')
        self.assertEqual(self.owner.get('/api/employment').json,[])
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/income',{**self.values(),'reviewed':False}).status_code,400)
        for key in ('gross','withheld'):
            self.assertEqual(self.call(self.owner,f'receipts/{rid}/income',{**self.values(),key:None}).status_code,400)
        saved=self.call(self.owner,f'receipts/{rid}/income',self.values());self.assertEqual(saved.status_code,200,saved.json)
        self.assertEqual(self.owner.get('/api/receipts?unfiled=1').json,[])
        self.assertFalse(any(e['kind']=='receipts' for e in self.owner.get('/api/notifications/events').json))
        self.assertEqual(self.owner.get('/api/employment').json[0]['receipt_id'],rid)
        self.assertEqual(self.owner.get('/api/expenses').json,[])
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/income',self.values()).json['id'],saved.json['id'])
        self.assertEqual(len(self.owner.get('/api/employment').json),1)
        self.assertEqual(self.upload(raw).json['id'],rid)
        self.assertEqual(self.call(self.owner,f'receipts/{rid}',{},'DELETE').status_code,409)
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/draft',{'notes':'changed'},'PUT').status_code,409)
        self.assertEqual(self.expense(self.owner,receipt_id=rid).status_code,409)
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/expense',{}).status_code,409)
        self.assertEqual(self.call(self.owner,'employment/'+str(saved.json['id']),{},'DELETE').status_code,200)
        self.assertEqual(len(self.owner.get('/api/receipts?unfiled=1').json),1)
        response=self.owner.get('/api/receipts/'+rid);self.assertEqual(response.data,raw);response.close()

    def test_ytd_only_and_multi_column_values_are_not_current_pay(self):
        result=local_payslip('PAYSLIP\nGross pay: 3000.00\nPAYG: 650.00\nYear to date figures')
        self.assertIsNone(result['gross']);self.assertIsNone(result['withheld'])
        result=local_payslip('PAYSLIP\nThis pay  YTD\nGross pay 3000.00 21000.00\nPAYG 650.00 4550.00')
        self.assertIsNone(result['gross']);self.assertIsNone(result['withheld'])
        self.assertIsNone(clean(dict(document_kind='payslip',gross=3000,withheld=500,amounts_basis='annual'))['gross'])
        self.assertIsNone(clean(dict(document_kind='payslip',gross='NaN',withheld=True,amounts_basis='period'))['withheld'])

    def test_multiple_payments_and_disagreeing_totals_are_left_for_review(self):
        result=local_payslip('PAYSLIP\nPayment date: 01/10/2026\nGross pay: 1000.00\nPAYG: 100.00\nPayment date: 15/10/2026\nGross pay: 2000.00\nPAYG: 200.00')
        self.assertIsNone(result['date']);self.assertIsNone(result['gross']);self.assertIsNone(result['withheld'])

    def test_ai_keeps_current_pay_and_ytd_separate(self):
        rid=self.upload(payslip_pdf('PAYSLIP\nEmployer: Synthetic Aviation Pty Ltd\nCurrent and YTD amounts are in columns.')).json['id']
        result=dict(document_kind='payslip',employer='Synthetic Aviation Pty Ltd',date='2026-10-16',gross=3000,withheld=650,ytd_gross=21000,ytd_withheld=4550,amounts_basis='period',currency='AUD',currency_evidence='AUD')
        with patch('ai_providers.configured',return_value=True),patch('ai_providers.extract',return_value=result):
            read=self.call(self.owner,f'receipts/{rid}/extract',{})
        self.assertEqual(read.json['gross'],3000);self.assertEqual(read.json['ytd_gross'],21000)
        self.assertEqual(read.json['withheld'],650);self.assertEqual(self.owner.get('/api/employment').json,[])

    def test_duplicate_annual_overlap_permissions_and_existing_attachment(self):
        rid=self.upload().json['id']
        old=self.call(self.owner,'employment',self.values());self.assertEqual(old.status_code,200,old.json)
        duplicate=self.call(self.owner,f'receipts/{rid}/income',self.values());self.assertEqual(duplicate.status_code,409)
        attached=self.call(self.owner,f'receipts/{rid}/income',self.values(existing_income_id=old.json['id']))
        self.assertEqual(attached.status_code,200,attached.json)
        annual={**self.values(),'record_kind':'income_statement','date':'2027-06-30','period_start':'','period_end':''}
        self.assertEqual(self.call(self.owner,'employment',annual).status_code,409)
        self.assertEqual(self.call(self.agent,f'receipts/{rid}/income',self.values()).status_code,403)
        self.assertEqual(self.owner.post(f'/api/receipts/{rid}/income',json=self.values()).status_code,403)
        current=self.owner.get('/api/employment').json[0]
        self.assertEqual(self.call(self.owner,'employment/'+str(current['id']),{**self.values(),'version':0},'PUT').status_code,409)
        self.assertEqual(len(self.owner.get('/api/employment').json),1)

    def test_filed_during_extraction_cannot_update_record(self):
        rid=self.upload(payslip_pdf('PAYSLIP\nSynthetic layout requiring AI extraction.')).json['id']
        def race(*args):
            db().execute('INSERT INTO employment_income(date,employer,gross_cents,withheld_cents,receipt_id) VALUES (?,?,?,?,?)',('2026-10-16','Synthetic',1000,200,rid));db().commit()
            return dict(document_kind='payslip',amounts_basis='period',gross=9999,withheld=999)
        with patch('ai_providers.configured',return_value=True),patch('ai_providers.extract',side_effect=race):
            self.assertEqual(self.call(self.owner,f'receipts/{rid}/extract',{'unfiled_only':True}).status_code,409)
        self.assertEqual(self.owner.get('/api/employment').json[0]['gross_cents'],1000)
