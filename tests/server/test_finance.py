"""Tax calculations, whole-workspace adviser access and inline receipt rendering."""
import io
import unittest
from pypdf import PdfWriter
import test_app as base
from app import app, db
from tax_core import estimate

class TaxMathTest(unittest.TestCase):
    def test_resident_rate_changes_and_boundaries(self):
        # Published bracket bases, plus the 2% Medicare provision (LITO is zero here).
        for year,bases in [(2025,[31288,51638]),(2026,[31020,51370]),(2027,[30752,51102])]:
            for income,base in zip([135000,190000],bases):
                e=estimate(income*100,year)
                self.assertEqual(e['income_tax_cents'],base*100)
                self.assertEqual(e['total_tax_cents'],(base+income*.02)*100)
        self.assertEqual(estimate(20000000,2026)['income_tax_cents'],5587000)
    def test_lito_whole_dollars_and_explicit_provisions(self):
        self.assertEqual(estimate(3750099,2026)['lito_cents'],70000)
        self.assertEqual(estimate(4500000,2026)['lito_cents'],32500)
        self.assertEqual(estimate(6666700,2026)['lito_cents'],0)
        self.assertEqual(estimate(1820000,2026,medicare_override=0)['total_tax_cents'],0)
        e=estimate(10000000,2026,withheld_cents=2000000,instalments_cents=100000,medicare_override=0,other_tax_cents=50000,set_aside_cents=100000)
        self.assertEqual(e['total_tax_cents'],2102000)
        self.assertEqual(e['balance_cents'],2000)
        self.assertEqual(e['additional_to_save_cents'],0)
        self.assertEqual(estimate(-100,2026)['total_tax_cents'],0)
        with self.assertRaises(ValueError):estimate(100,2030)

class FinanceTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login
    expense=base.AppTest.expense
    def permission(self,value):
        uid=next(u['id'] for u in self.owner.get('/api/users').json if u['email']=='agent@example.test')
        self.assertEqual(self.call(self.owner,f'users/{uid}/permission',{'permission':value},'PUT').status_code,200)
    def test_permissions_apply_immediately_and_protect_owner_settings(self):
        income={'date':'2026-10-08','employer':'Employer','gross':10000,'withheld':2500}
        for path in ['employment','tax/2026','receipts','accounts','billing/clients']:
            self.assertEqual(self.agent.get('/api/'+path).status_code,200,path)
        for path in ['employment','tax/2026']:
            self.assertEqual(self.staff2.get('/api/'+path).status_code,401,path)
        self.assertEqual(self.call(self.agent,'employment',income).status_code,403)
        self.permission('read_write')
        self.assertEqual(self.call(self.agent,'employment',income).status_code,200)
        eid=self.expense(self.agent,category='Other',scope='personal').json['id']
        self.assertEqual(self.call(self.agent,f'expenses/{eid}',{},'DELETE').status_code,200)
        self.call(self.owner,'billing/settings',{'name':'Example Business'},'PUT')
        cid=self.call(self.agent,'billing/clients',{'name':'Agent-created client','email':'client@example.test'}).json['id']
        r=self.call(self.agent,'billing/documents',{'kind':'invoice','client_id':cid,'issue_date':'2026-10-08','due_date':'2026-10-22','tax_mode':'none','lines':[{'description':'Work','quantity':1,'unit_price':100,'tax':'none'}]})
        self.assertEqual(r.status_code,200,r.json)
        did=r.json['id'];doc=self.agent.get(f'/api/billing/documents/{did}').json
        self.assertEqual(self.call(self.agent,f'billing/documents/{did}/action',{'version':doc['version'],'action':'issue'}).status_code,200)
        for path in ['users','billing/email-settings','billing/settings']:
            self.assertEqual(self.call(self.agent,path,{},'PUT' if path!='users' else 'POST').status_code,403,path)
        self.assertNotIn('email',self.agent.get('/api/billing/settings').json)
        self.permission('read_only')
        self.assertEqual(self.call(self.agent,'employment',income).status_code,403)
        self.assertEqual(self.call(self.agent,f'billing/documents/{did}/payments',{}).status_code,403)
        self.assertEqual(self.agent.get(f'/api/billing/documents/{did}/pdf').status_code,200)
    def test_combined_forecast_review_filters_refunds_and_annual_replacement(self):
        self.call(self.owner,'employment',{'date':'2026-10-08','employer':'Employer','gross':100000,'withheld':20000})
        self.call(self.owner,'employment',{'date':'2026-06-30','employer':'Old year','gross':20000,'withheld':0})
        self.expense(self.owner,category='Equipment',scope='work',amount=1000,percent=50,status='ready')
        self.expense(self.owner,category='Equipment',scope='work',amount=-100,percent=50,status='ready')
        self.expense(self.owner,category='Equipment',scope='work',amount=999,status='review')
        self.expense(self.owner,category='Equipment',scope='personal',amount=999,status='ready')
        self.expense(self.owner,category='Equipment',scope='work',amount=999,status='ready',reimbursed=True)
        d=self.owner.get('/api/tax/2026').json
        self.assertEqual(d['recorded']['salary_cents'],10000000)
        self.assertEqual(d['recorded']['work_deductions_cents'],45000)
        self.assertEqual(d['unreviewed'],1)
        self.assertEqual(d['estimate']['taxable_cents'],9955000)
        d=self.call(self.owner,'tax/2026',{'annual_salary':120000,'annual_withheld':30000,'annual_business_income':10000,'annual_business_deductions':1100,'gst_credits':100,'annualise':True},'PUT').json
        self.assertEqual(d['forecast']['salary_cents'],12000000)
        self.assertEqual(d['forecast']['withheld_cents'],3000000)
        self.assertEqual(d['forecast']['business_income_cents'],1000000)
        self.assertEqual(d['estimate']['taxable_cents'],(12900000-d['forecast']['work_deductions_cents'])//100*100)
        self.assertEqual(self.call(self.owner,'tax/2026',{'annual_salary':-1},'PUT').status_code,400)
        d=self.call(self.owner,'tax/2026',{'annual_salary':100000,'annual_business_income':0,'annual_business_deductions':5000},'PUT').json
        self.assertEqual(d['business_loss_cents'],500000)
        self.assertEqual(d['estimate']['taxable_cents'],9955000)
    def test_payments_exclude_gst_and_unpaid_invoices(self):
        self.call(self.owner,'billing/settings',{'name':'Business','abn':'12 345 678 901','gst_registered':True},'PUT')
        cid=self.call(self.owner,'billing/clients',{'name':'Client'}).json['id']
        did=self.call(self.owner,'billing/documents',{'kind':'invoice','client_id':cid,'issue_date':'2026-06-20','due_date':'2026-07-20','tax_mode':'exclusive','lines':[{'description':'Work','quantity':1,'unit_price':100,'tax':'gst'}]}).json['id']
        def doc():return self.owner.get(f'/api/billing/documents/{did}').json
        self.call(self.owner,f'billing/documents/{did}/action',{'version':doc()['version'],'action':'issue'})
        for day,amount in [('2026-06-30',55),('2026-07-01',22)]:
            result=self.call(self.owner,f'billing/documents/{did}/payments',{'version':doc()['version'],'amount':amount,'date':day,'request_key':'unique-payment-request-key-'+day})
            self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.owner.get('/api/tax/2025').json['recorded']['business_income_cents'],5000)
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded']['business_income_cents'],2000)
    def test_pdf_preview_pages_and_acl(self):
        pdf=PdfWriter();pdf.add_blank_page(width=200,height=200);pdf.add_blank_page(width=300,height=300);buf=io.BytesIO();pdf.write(buf);buf.seek(0)
        r=self.owner.post('/api/receipts',data={'file':(buf,'two-pages.pdf')},headers={'X-CSRF-Token':self.owner.get('/api/session').json['csrf']})
        rid=r.json['id']
        self.assertEqual(self.agent.get(f'/api/receipts/{rid}/info').json['pages'],2)
        for page in [1,2]:
            r=self.agent.get(f'/api/receipts/{rid}/preview?page={page}')
            self.assertEqual(r.status_code,200);self.assertTrue(r.data.startswith(b'\x89PNG'))
            self.assertNotIn('attachment',r.headers.get('Content-Disposition',''))
        self.assertEqual(self.agent.get(f'/api/receipts/{rid}/preview?page=3').status_code,404)
        self.assertEqual(self.staff2.get(f'/api/receipts/{rid}/preview').status_code,401)
        self.assertEqual(app.test_client().get(f'/api/receipts/{rid}/preview').status_code,401)
    def test_owner_can_record_meal_and_readonly_agent_cannot(self):
        tid=self.call(self.owner,'trips',{'location':'Cairns','start':'2026-10-07','end':'2026-10-09','purpose':'Work','scope':'business'}).json['id']
        self.assertEqual(self.expense(self.agent,trip_id=tid,meal='Dinner').status_code,403)
        self.assertEqual(self.expense(self.owner,trip_id=tid,meal='Dinner').status_code,200)
        self.assertEqual(len(self.agent.get('/api/expenses').json),1)
