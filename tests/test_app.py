"""Integration tests. Run: python -m unittest discover -s tests -v"""
import os, tempfile, unittest, io, csv
_test_data=tempfile.TemporaryDirectory()
os.environ['DATA_DIR']=_test_data.name
os.environ['SETUP_TOKEN']='integration-test-setup-token-123456789'
from app import app, db
from werkzeug.security import generate_password_hash

class AppTest(unittest.TestCase):
    def setUp(self):
        app.config['TESTING']=True
        with app.app_context():
            for table in ['billing_outbox','billing_payments','billing_time','billing_documents','billing_schedules','billing_services','billing_clients','billing_settings','employment_income','tax_settings','vehicle_journeys','expenses','vehicles','trips','receipt_drafts','receipt_preferences','custom_categories','receipt_details','receipts','accounts','audit','users','attempts']: db().execute('DELETE FROM '+table)
            db().execute('UPDATE billing_counters SET next_number=1')
            db().commit()
        self.owner=app.test_client();self.call(self.owner,'setup',{'token':os.environ['SETUP_TOKEN'],'name':'Owner','email':'owner@example.test','password':'Owner-password-123'})
        self.login(self.owner,'owner@example.test','Owner-password-123')
        for email,role in [('staff@example.test','employee'),('staff2@example.test','employee'),('agent@example.test','tax_agent')]:
            # Existing-account fixtures; invitation delivery and onboarding have dedicated tests.
            with app.app_context():
                db().execute('INSERT INTO users(name,email,password,role) VALUES (?,?,?,?)',(role,email,generate_password_hash('Testing-password-123'),role));db().commit()
        self.staff=app.test_client();self.login(self.staff,'staff@example.test','Testing-password-123')
        self.staff2=app.test_client();self.login(self.staff2,'staff2@example.test','Testing-password-123')
        self.agent=app.test_client();self.login(self.agent,'agent@example.test','Testing-password-123')
    def call(self,c,path,data,method='POST'):
        token=c.get('/api/session').json['csrf']
        return c.open('/api/'+path,method=method,json=data,headers={'X-CSRF-Token':token})
    def login(self,c,email,password): self.assertEqual(self.call(c,'login',{'email':email,'password':password}).status_code,200)
    def expense(self,c,**kw):
        d={'date':'2026-10-08','merchant':'Cafe','amount':'23.45','scope':'business','category':'Meals','percent':100,'status':'review'};d.update(kw)
        return self.call(c,'expenses',d)
    def test_csrf_and_anonymous(self):
        self.assertEqual(self.owner.post('/api/expenses',json={}).status_code,403)
        c=app.test_client();self.assertEqual(c.get('/api/expenses').status_code,401)
    def test_owner_setup_cannot_repeat(self):
        self.assertEqual(self.call(self.owner,'setup',{'token':os.environ['SETUP_TOKEN']}).status_code,409)
    def test_employee_isolation(self):
        eid=self.expense(self.staff).json['id'];self.expense(self.owner,scope='work')
        self.assertEqual(len(self.staff.get('/api/expenses').json),1)
        self.assertEqual(len(self.staff2.get('/api/expenses').json),0)
        self.assertEqual(self.call(self.staff2,f'expenses/{eid}',{},'DELETE').status_code,404)
        self.assertEqual(self.staff.get('/api/accounts').status_code,403)
        self.assertEqual(self.staff.get('/api/users').status_code,403)
        self.assertEqual(self.staff.get('/api/export').status_code,403)
        self.assertEqual(self.expense(self.staff,scope='work').status_code,400)
    def test_agent_all_records_read_only(self):
        self.expense(self.owner,shared=False);eid=self.expense(self.owner,shared=True).json['id']
        self.assertEqual(len(self.agent.get('/api/expenses').json),2)
        self.assertEqual(self.expense(self.agent).status_code,403)
        self.assertEqual(self.call(self.agent,f'expenses/{eid}',{},'DELETE').status_code,403)
        self.assertEqual(self.agent.get('/api/accounts').status_code,200)
        self.assertEqual(len(list(csv.reader(io.StringIO(self.agent.get('/api/export').data.decode('utf-8-sig'))))),3)
    def test_employee_records_visible_to_agent(self):
        self.expense(self.staff,shared=True)
        self.assertEqual(len(self.agent.get('/api/expenses').json),1)
    def test_personal_visible_but_not_allocated(self):
        self.expense(self.owner,scope='personal',shared=True,percent=100)
        e=self.owner.get('/api/expenses').json[0];self.assertEqual(e['shared'],1);self.assertEqual(e['percent'],0)
    def test_disable_revokes_session(self):
        uid=next(u['id'] for u in self.owner.get('/api/users').json if u['email']=='staff@example.test')
        self.call(self.owner,f'users/{uid}/access',{'active':False})
        self.assertEqual(self.staff.get('/api/expenses').status_code,401)
    def test_password_change_revokes_other_sessions(self):
        other=app.test_client();self.login(other,'staff@example.test','Testing-password-123')
        self.assertEqual(self.call(self.staff,'password',{'current':'Testing-password-123','password':'Changed-password-123'}).status_code,200)
        self.assertEqual(other.get('/api/expenses').status_code,401)
    def test_trip_validation_and_edit_guard(self):
        t={'location':'Cairns','start':'2026-10-07','end':'2026-10-09','purpose':'Flying duties','scope':'business','allowance':100}
        tid=self.call(self.staff,'trips',t).json['id']
        self.assertEqual(self.expense(self.staff,trip_id=tid,meal='Dinner').status_code,200)
        self.assertEqual(self.expense(self.owner,trip_id=tid).status_code,400)
        self.assertEqual(self.expense(self.staff,trip_id=tid,date='2026-10-10').status_code,400)
        self.assertEqual(self.expense(self.staff,meal='Dinner').status_code,400)
        self.assertEqual(self.call(self.staff,f'trips/{tid}',{},'DELETE').status_code,409)
        t['end']='2026-10-08';t['start']='2026-10-06'
        self.assertEqual(self.call(self.staff,f'trips/{tid}',t,'PUT').status_code,200)
        t['end']='2026-10-07'
        self.assertEqual(self.call(self.staff,f'trips/{tid}',t,'PUT').status_code,409)
    def test_currency_rounding_and_invalid_numbers(self):
        self.expense(self.owner,amount='12.345');self.assertEqual(self.owner.get('/api/expenses').json[0]['amount_cents'],1235)
        self.assertEqual(self.expense(self.owner,amount='NaN').status_code,400)
        self.assertEqual(self.expense(self.owner,percent=101).status_code,400)
        self.assertEqual(self.expense(self.owner,amount='-12.30').status_code,200)
    def import_file(self,text):
        import json
        token=self.owner.get('/api/session').json['csrf']
        return self.owner.post('/api/import',data={'file':(io.BytesIO(text.encode()),'statement.csv'),'mapping':json.dumps({'account_id':self.aid,'date':0,'merchant':1,'amount':2,'sign':'negative','date_format':'%d/%m/%Y'})},headers={'X-CSRF-Token':token})
    def test_import_duplicate_and_credit_handling(self):
        self.aid=self.call(self.owner,'accounts',{'name':'Everyday','bank':'CommBank'}).json['id']
        text='Date,Description,Amount\n08/10/2026,Cafe,-12.50\n08/10/2026,Cafe,-12.50\n08/10/2026,Deposit,100\n'
        r=self.import_file(text);self.assertEqual(r.json,{'added':2,'duplicates':0,'credits_skipped':1})
        self.assertEqual(self.import_file(text).json['duplicates'],2)
        self.assertEqual(len(self.owner.get('/api/expenses').json),2)
        self.assertTrue(all(e['scope']=='personal' and e['status']=='review' for e in self.owner.get('/api/expenses').json))
    def test_import_atomic_validation(self):
        self.aid=self.call(self.owner,'accounts',{'name':'Everyday','bank':'Macquarie'}).json['id']
        r=self.import_file('Date,Description,Amount\n08/10/2026,Cafe,-12\nbad,Cafe,-20\n')
        self.assertEqual(r.status_code,400);self.assertEqual(self.owner.get('/api/expenses').json,[])
    def test_csv_formula_escaping_and_reimbursement(self):
        self.expense(self.owner,merchant='=HYPERLINK("bad")',reimbursed=True,shared=True)
        data=list(csv.reader(io.StringIO(self.agent.get('/api/export').data.decode('utf-8-sig'))))
        self.assertTrue(data[1][3].startswith("'="));self.assertEqual(data[1][9],'0.00')
    def test_receipt_access_and_ai_not_configured(self):
        from PIL import Image
        buf=io.BytesIO();Image.new('RGB',(20,20),'white').save(buf,'PNG');buf.seek(0)
        csrf=self.staff.get('/api/session').json['csrf']
        r=self.staff.post('/api/receipts',data={'file':(buf,'receipt.png')},headers={'X-CSRF-Token':csrf});self.assertEqual(r.status_code,200);rid=r.json['id']
        self.assertEqual(self.staff2.get('/api/receipts/'+rid).status_code,403)
        self.assertEqual(self.agent.get('/api/receipts/'+rid).status_code,200)
        self.assertEqual(self.expense(self.owner,receipt_id=rid).status_code,400)
        self.assertEqual(self.staff.get('/api/receipts/'+rid).status_code,200)
        eid=self.expense(self.staff,receipt_id=rid).json['id'];e=self.owner.get('/api/expenses').json[0];e['amount']=e['amount_cents']/100;e['shared']=True
        self.call(self.owner,'expenses/'+str(eid),e,'PUT')
        self.assertEqual(self.agent.get('/api/receipts/'+rid).status_code,200)
    def test_export_date_filter(self):
        self.expense(self.owner,date='2026-06-30');self.expense(self.owner,date='2026-07-01')
        data=list(csv.reader(io.StringIO(self.owner.get('/api/export?start=2026-07-01&end=2027-06-30').data.decode('utf-8-sig'))))
        self.assertEqual(len(data),2);self.assertEqual(data[1][1],'01/07/2026')
if __name__=='__main__': unittest.main()
