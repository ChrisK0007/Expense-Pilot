"""Tax workspace isolation, deterministic equipment schedules and signature import."""
import unittest
import io
import json
import zipfile
from unittest.mock import patch
import test_app
from app import app,db,one
import equipment_calculations as calc
from billing_email_core import clean_signature


class Beta13Test(unittest.TestCase):
    setUp=test_app.AppTest.setUp
    call=test_app.AppTest.call
    login=test_app.AppTest.login
    expense=test_app.AppTest.expense
    def aid(self):
        with app.app_context(): return one("SELECT id FROM users WHERE email='agent@example.test'")['id']

    def share(self,years=(2026,),documents=()):
        r=self.call(self.owner,f'users/{self.aid()}/sharing',dict(years=list(years),documents=list(documents)),'PUT')
        self.assertEqual(r.status_code,200,r.json)

    def asset(self,**kw):
        config=dict(method='prime_cost',first_use='2026-07-01',income_use='2026-07-01',life=2,gst_credit=0,basis='Tablet: Table B effective life 2 years',confirmed=True)
        config.update(kw.pop('calculation',{}))
        data=dict(name='iPad',acquired='2026-07-01',cost=1200,work_percent=60,business_percent=20,confirm_capital=True,calculation=config);data.update(kw)
        r=self.call(self.owner,'workflows/equipment',data);self.assertEqual(r.status_code,200,r.json);return r.json['id']

    def test_scope_defaults_closed_and_cannot_bypass_with_old_api(self):
        self.expense(self.owner,category='Other',merchant='Private secret',scope='personal')
        public=self.expense(self.owner,category='Other',merchant='Work equipment').json['id']
        self.assertEqual(self.agent.get('/api/adviser').json['years'],[])
        self.assertEqual(self.agent.get('/api/adviser/2026').status_code,403)
        for path in ['expenses','accounts','trips','vehicles','receipts/inbox','documents','billing/documents','billing/clients','tax/2026','workflows/handover/2026','workflows/attention/2026','audit','workflows/questions','home-office/2026']:
            self.assertEqual(self.agent.get('/api/'+path).status_code,403,path)
        self.share();data=self.agent.get('/api/adviser/2026');self.assertEqual(data.status_code,200,data.json)
        self.assertEqual([e['id'] for e in data.json['records']['expenses']],[public]);self.assertNotIn('Private secret',data.get_data(as_text=True))
        self.assertEqual(self.agent.get('/api/adviser/2025').status_code,403)
        self.assertEqual(self.agent.get('/api/adviser/2025?agent_id=1').status_code,403)
        self.share([]);self.assertEqual(self.agent.get('/api/adviser/2026').status_code,403)

    def test_agent_questions_allowed_only_for_shared_records(self):
        work=self.expense(self.owner,category='Other').json['id'];personal=self.expense(self.owner,scope='personal',category='Other').json['id'];self.share()
        self.assertEqual(self.call(self.agent,'adviser/2026/questions',dict(record_type='expense',record_id=work,question='Purpose?')).status_code,200)
        self.assertEqual(self.call(self.agent,'adviser/2026/questions',dict(record_type='expense',record_id=personal,question='Private?')).status_code,404)
        self.assertEqual(self.call(self.agent,'adviser/2026/expense/'+str(work),{},'PUT').status_code,403)
        with app.app_context(): db().execute("UPDATE users SET permission='read_write' WHERE id=?",(self.aid(),));db().commit()
        e=self.agent.get('/api/adviser/2026').json['records']['expenses'][0]
        values=dict(token=e['token'],category=e['category'],notes='Business purpose confirmed',status='ready',work_percent=25,business_percent=50)
        self.assertEqual(self.call(self.agent,'adviser/2026/expense/'+str(work),values,'PUT').status_code,200)
        self.assertEqual(self.call(self.agent,'adviser/2026/expense/'+str(work),values,'PUT').status_code,409)
        self.assertEqual(self.call(self.agent,'expenses/'+str(work),values,'PUT').status_code,403)

    def test_remove_agent_revokes_sessions_and_preserves_records_questions(self):
        work=self.expense(self.owner,category='Other').json['id'];self.share()
        self.call(self.agent,'adviser/2026/questions',dict(record_type='expense',record_id=work,question='Keep this question'))
        aid=self.aid()
        self.assertEqual(self.call(self.owner,f'users/{aid}',dict(confirmation='wrong'),'DELETE').status_code,400)
        self.assertEqual(self.call(self.owner,f'users/{aid}',dict(confirmation='agent@example.test'),'DELETE').status_code,200)
        self.assertIsNone(self.agent.get('/api/session').json['user'])
        with app.app_context():
            self.assertIsNone(one('SELECT id FROM users WHERE id=?',(aid,)))
            self.assertIsNotNone(one('SELECT id FROM expenses WHERE id=?',(work,)))
            self.assertIsNone(one("SELECT author_id FROM record_questions WHERE question='Keep this question'")['author_id'])
        self.assertEqual(self.call(self.owner,'users/1',dict(confirmation='owner@example.test'),'DELETE').status_code,404)

    def test_export_and_originals_exclude_unshared_data(self):
        from PIL import Image
        def receipt(name):
            image=io.BytesIO();Image.new('RGB',(12,12),name).save(image,'PNG');image.seek(0)
            token=self.owner.get('/api/session').json['csrf'];r=self.owner.post('/api/receipts',data={'file':(image,name+'.png')},headers={'X-CSRF-Token':token});self.assertEqual(r.status_code,200,r.json);return r.json['id']
        work=receipt('red');private=receipt('blue');unfiled=receipt('green')
        self.expense(self.owner,category='Other',merchant='Allowed',receipt_id=work);self.expense(self.owner,scope='personal',category='Other',merchant='Private secret',receipt_id=private)
        self.share()
        self.assertEqual(self.agent.get(f'/api/adviser/2026/source/receipt/{work}').status_code,200)
        for rid in (private,unfiled):
            self.assertEqual(self.agent.get(f'/api/adviser/2026/source/receipt/{rid}').status_code,404)
            self.assertEqual(self.agent.get('/api/receipts/'+rid).status_code,403)
        r=self.agent.get('/api/adviser/2026/export');self.assertEqual(r.status_code,200,r.json)
        with zipfile.ZipFile(io.BytesIO(r.data)) as z:
            self.assertNotIn('Private secret',z.read('records.json').decode())
            self.assertTrue(any(work in name for name in z.namelist()))
            self.assertFalse(any(private in name or unfiled in name for name in z.namelist()))
            self.assertFalse(any('bank_transactions' in name for name in z.namelist()))

    def test_automatic_schedule_and_forecast_no_double_count(self):
        eid=self.expense(self.owner,date='2026-07-01',amount=1200,category='Other',work_percent=60,business_percent=20,status='ready').json['id']
        self.asset(expense_id=eid)
        a=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]
        self.assertEqual(a['current']['amount_cents'],60000);self.assertEqual(a['closing_cents'],60000);self.assertFalse(a['needs_review'])
        f=self.owner.get('/api/tax/2026').json
        self.assertEqual(f['recorded']['work_deductions_cents'],0);self.assertEqual(f['forecast']['work_deductions_cents'],36000);self.assertEqual(f['forecast']['business_deductions_cents'],12000)
        self.assertEqual(f['equipment']['estimated_work_cents'],36000)
        self.assertEqual(self.owner.get('/api/workflows/equipment?year=2027').json['assets'][0]['closing_cents'],0)
        aid=a['id'];r=self.call(self.owner,f'workflows/equipment/{aid}/year/2026',dict(version=a['version'],amount=500,notes='Accountant override',confirmed=True),'PUT');self.assertEqual(r.status_code,200,r.json)
        f=self.owner.get('/api/tax/2026').json;self.assertEqual(f['recorded']['work_deductions_cents'],30000)
        a=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]
        r=self.call(self.owner,f'workflows/equipment/{aid}/use/2026',dict(version=a['version'],work_percent=20,business_percent=60,notes='Changed duties'),'PUT');self.assertEqual(r.status_code,200,r.json)
        a=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0];self.assertEqual(a['current']['work_percent'],60)
        a=self.owner.get('/api/workflows/equipment?year=2027').json['assets'][0];self.assertEqual(a['current']['work_percent'],20)

    def test_immediate_deduction_checks_full_cost_eligibility_and_year(self):
        a=self.asset(calculation=dict(method='immediate_business',eligible_asset=True,small_business=True))
        self.assertEqual(self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]['current']['amount_cents'],120000)
        data=dict(name='Tablet',acquired='2026-07-01',cost=1200,work_percent=20,business_percent=0,confirm_capital=True,calculation=dict(method='immediate_employee',first_use='2026-07-01',income_use='2026-07-01',life=2,gst_credit=0,basis='Test',confirmed=True,eligible_asset=True,not_grouped=True))
        self.assertEqual(self.call(self.owner,'workflows/equipment',data).status_code,400)
        data['cost']=300;data['work_percent']=60
        self.assertEqual(self.call(self.owner,'workflows/equipment',data).status_code,200)
        data['calculation'].update(method='immediate_business',small_business=True,first_use='2027-07-01',income_use='2027-07-01')
        self.assertEqual(self.call(self.owner,'workflows/equipment',data).status_code,400)

    def test_pasted_signature_preserves_layout_and_sanitises(self):
        raw='<table cellpadding="0"><tr><td style="padding-right:12px;border-right:1px solid #123456"><b>Name</b></td><td><span style="font-family:Arial;font-size:12pt;color:#123456">Pilot</span><br><a href="mailto:pilot@example.test">Email</a></td></tr></table><script>private()</script><img src="http://127.0.0.1/secrets" onerror="alert(1)">'
        r=self.call(self.owner,'billing/signature-paste',dict(html=raw));self.assertEqual(r.status_code,200,r.json);clean=r.json['html']
        self.assertIn('<table',clean);self.assertIn('font-family:arial',clean);self.assertIn('mailto:',clean);self.assertNotIn('127.0.0.1',clean);self.assertNotIn('script',clean);self.assertEqual(r.json['missing_images'],1)
        self.assertEqual(clean_signature(clean)[0],clean)
        self.assertEqual(self.call(self.agent,'billing/signature-paste',dict(html=raw)).status_code,403)


    def test_document_selection_year_boundary_and_revocation(self):
        def upload(year,title):
            token=self.owner.get('/api/session').json['csrf']
            r=self.owner.post('/api/documents',data={'file':(io.BytesIO(('Evidence '+title).encode()),title+'.txt'),'title':title,'year':str(year),'category':'other'},headers={'X-CSRF-Token':token})
            self.assertEqual(r.status_code,200,r.json);return r.json['id']
        selected=upload(2026,'Selected');hidden=upload(2026,'Hidden');previous=upload(2025,'Prior year')
        self.share(documents=[selected,previous])
        r=self.agent.get('/api/adviser/2026');self.assertEqual([d['id'] for d in r.json['records']['documents']],[selected])
        for did,status in [(selected,200),(hidden,404),(previous,404)]:
            response=self.agent.get(f'/api/adviser/2026/source/document/{did}');self.assertEqual(response.status_code,status);response.close()
        self.share(documents=[])
        self.assertEqual(self.agent.get(f'/api/adviser/2026/source/document/{selected}').status_code,404)
        self.assertEqual(self.call(self.agent,'users/'+str(self.aid())+'/sharing',dict(years=[2025],documents=[previous]),'PUT').status_code,403)

    def test_legacy_financial_history_survives_agent_removal(self):
        aid=self.aid()
        with app.app_context():
            db().execute("INSERT INTO home_office_allowances(user_id,date,employer,amount_cents) VALUES (?,'2026-08-01','Legacy employer',10000)",(aid,))
            db().execute("INSERT INTO workflow_changes(user_id,kind,before_json,after_json,at) VALUES (?,'legacy','{}','{}','2026-08-01')",(aid,))
            db().execute("INSERT INTO annual_income_checks(user_id,year,employer,gross_cents,withheld_cents) VALUES (?,2026,'Legacy employer',10000,1000)",(aid,));db().commit()
        self.assertEqual(self.call(self.owner,f'users/{aid}',dict(confirmation='agent@example.test'),'DELETE').status_code,200)
        with app.app_context():
            uid=one("SELECT id FROM users WHERE role='owner'")['id']
            for table in ['home_office_allowances','workflow_changes','annual_income_checks']:
                self.assertEqual(one('SELECT user_id FROM '+table)['user_id'],uid)

    def test_clipboard_file_replaces_missing_image_and_roundtrips(self):
        from PIL import Image
        raw=io.BytesIO();Image.new('RGB',(40,20),'blue').save(raw,'PNG');raw.seek(0)
        token=self.owner.get('/api/session').json['csrf']
        r=self.owner.post('/api/billing/signature-paste',data={'html':'<table><tr><td><img src="cid:logo" alt="Logo"></td><td style="font-family:Arial">Name</td></tr></table>','images':(raw,'logo.png')},headers={'X-CSRF-Token':token})
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['missing_images'],0);self.assertIn('data:image/png;base64,',r.json['html'])
        saved=self.call(self.owner,'billing/email-templates',dict(signature_html=r.json['html']),'PUT');self.assertEqual(saved.status_code,200,saved.json)
        self.assertEqual(saved.json['signature_html'],r.json['html']);self.assertIn('Name',clean_signature(saved.json['signature_html'])[1])

    def test_private_use_override_disposal_and_history_lock(self):
        aid=self.asset(calculation=dict(income_use='2027-01-01'))
        a=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]
        self.assertEqual(a['current']['amount_cents'],60000);self.assertEqual(a['current']['claimable_cents'],29753)
        d=dict(version=a['version'],amount=600,notes='Reviewed tax period',confirmed=True)
        self.assertEqual(self.call(self.owner,f'workflows/equipment/{aid}/year/2026',d,'PUT').status_code,400)
        d['income_use_amount']=297.53;self.assertEqual(self.call(self.owner,f'workflows/equipment/{aid}/year/2026',d,'PUT').status_code,200)
        a=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]
        cfg=dict(method='prime_cost',first_use='2026-07-01',income_use='2027-01-01',life=3,gst_credit=0,basis='Changed',confirmed=True,preserve_history=True)
        self.assertEqual(self.call(self.owner,f'workflows/equipment/{aid}/calculation',dict(version=a['version'],calculation=cfg),'PUT').status_code,409)
        self.assertEqual(self.call(self.owner,f'workflows/equipment/{aid}',dict(version=a['version'],disposal_date='2027-08-01',proceeds=100),'PUT').status_code,200)
        a=self.owner.get('/api/workflows/equipment?year=2027').json['assets'][0];self.assertTrue(a['needs_review'])
        self.assertEqual(self.owner.get('/api/tax/2027').json['equipment']['estimated_work_cents'],0)

    def test_private_routes_hidden_but_claim_distances_and_odometer_shared(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        vid=self.call(self.owner,'vehicles',dict(name='Test car')).json['id']
        for scope,origin,distance in [('personal','Private appointment',30),('business','Office',20)]:
            r=self.call(self.owner,'vehicle-journeys',dict(vehicle_id=vid,date='2026-10-08',origin=origin,destination='Destination',purpose='Test duty' if scope=='business' else '',scope=scope,percent=100,distance=distance))
            self.assertEqual(r.status_code,200,r.json)
        stamp=datetime(2026,10,9,tzinfo=ZoneInfo('Australia/Brisbane')).timestamp()
        self.assertEqual(self.call(self.owner,f'vehicles/{vid}/odometer',dict(recorded_at=stamp,reading=12000)).status_code,200)
        self.share();r=self.agent.get('/api/adviser/2026');self.assertNotIn('Private appointment',r.get_data(as_text=True));data=r.json['records']
        self.assertEqual(len(data['mileage']),1);self.assertEqual(data['vehicles'][0]['personal_logged_m'],30000);self.assertEqual(data['vehicles'][0]['total_logged_m'],50000)
        self.assertEqual(data['odometer'][0]['reading_m'],12000000);self.assertNotIn('route_json',str(data))
        self.assertEqual(self.agent.get('/api/vehicle-journeys').status_code,403)

    def test_scoped_invoice_evidence_and_own_security(self):
        self.call(self.owner,'billing/settings',dict(name='Test business'),'PUT')
        cid=self.call(self.owner,'billing/clients',dict(name='Test client',notes='Internal contact secret')).json['id']
        def create(kind,day,issue):
            r=self.call(self.owner,'billing/documents',dict(kind=kind,client_id=cid,issue_date=day,due_date=day,tax_mode='none',lines=[dict(description='Test services',quantity=1,unit_price=100,tax='none')]))
            self.assertEqual(r.status_code,200,r.json);did=r.json['id']
            if issue:
                doc=self.owner.get(f'/api/billing/documents/{did}').json
                self.assertEqual(self.call(self.owner,f'billing/documents/{did}/action',dict(action='issue',version=doc['version'])).status_code,200)
            return did
        shared=create('invoice','2026-08-01',True);draft=create('invoice','2026-08-02',False);prior=create('invoice','2025-08-01',True);quote=create('quote','2026-08-03',True)
        self.share();r=self.agent.get('/api/adviser/2026');self.assertNotIn('Internal contact secret',r.get_data(as_text=True));self.assertEqual([d['id'] for d in r.json['records']['invoices']],[shared])
        for did,status in [(shared,200),(draft,404),(prior,404),(quote,404)]:
            result=self.agent.get(f'/api/adviser/2026/source/invoice/{did}');self.assertEqual(result.status_code,status);result.close()
        for path in ('security','security/sessions','security/signins','security/devices'):
            self.assertEqual(self.agent.get('/api/'+path).status_code,200,path)
        self.assertEqual(self.agent.get('/api/security/invitations').status_code,403)

    def test_removing_override_cannot_invalidate_later_confirmed_year(self):
        aid=self.asset()
        for year,amount in [(2026,300),(2027,900)]:
            a=self.owner.get('/api/workflows/equipment?year='+str(year)).json['assets'][0]
            result=self.call(self.owner,f'workflows/equipment/{aid}/year/{year}',dict(version=a['version'],amount=amount,notes='Reviewed schedule',confirmed=True),'PUT')
            self.assertEqual(result.status_code,200,result.json)
        a=self.owner.get('/api/workflows/equipment?year=2026').json['assets'][0]
        r=self.call(self.owner,f'workflows/equipment/{aid}/year/2026',dict(version=a['version']),'DELETE')
        self.assertEqual(r.status_code,400,r.json)
        self.assertEqual(self.owner.get('/api/workflows/equipment?year=2027').json['assets'][0]['current']['amount_cents'],90000)

    def test_wfh_classified_bill_is_tax_evidence_without_general_allocation(self):
        eid=self.expense(self.owner,scope='personal',category='Phone & internet',merchant='Tax evidence internet',status='ready').json['id']
        self.expense(self.owner,scope='personal',category='Other',merchant='Unrelated personal')
        with app.app_context():
            db().execute("INSERT INTO home_office_costs(expense_id,kind,reviewed,basis) VALUES (?,'internet',1,'Personally paid running cost')",(eid,));db().commit()
        self.share();data=self.agent.get('/api/adviser/2026').json['records']
        self.assertEqual([e['id'] for e in data['expenses']],[eid]);self.assertEqual(data['expenses'][0]['employment_cents'],0)
        self.assertEqual(data['expenses'][0]['home_office_treatment']['kind'],'internet')
        self.assertIn('rate_cents',data['home_office_summary'])


class ScheduleMathTest(unittest.TestCase):
    def schedule(self,**changes):
        a=dict(id=1,cost_cents=110000,acquired='2027-07-01',work_percent=60,business_percent=20,disposal_date='',calculation_json='{}')
        cfg=dict(method='prime_cost',first_use='2027-07-01',income_use='2027-07-01',life='2',gst_credit_cents=10000,basis='Reviewed')
        cfg.update(changes);a['calculation_json']=json.dumps(cfg)
        return calc.schedule(a,[],[],2029)
    def test_leap_year_uses_365_denominator_and_never_exceeds_cost(self):
        rows=self.schedule();self.assertEqual(rows[0]['days'],366);self.assertEqual(rows[0]['amount_cents'],50137)
        self.assertEqual(rows[1]['amount_cents'],49863);self.assertEqual(rows[2]['amount_cents'],0);self.assertEqual(sum(r['amount_cents'] for r in rows),100000)
    def test_diminishing_value_and_partial_first_year(self):
        rows=self.schedule(method='diminishing_value',life='4',first_use='2028-01-01',income_use='2028-01-01')
        self.assertEqual(rows[0]['days'],182);self.assertEqual(rows[0]['amount_cents'],24932)
        self.assertEqual(rows[1]['opening_cents'],75068);self.assertEqual(rows[1]['amount_cents'],37534)
