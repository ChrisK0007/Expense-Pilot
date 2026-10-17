"""Budgets and vehicle comparisons: money, permissions, receipts and no double posting."""
import io
import unittest
from PIL import Image
import test_app as base
from app import app, DATA


class PlanningTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login
    expense=base.AppTest.expense

    def test_budget_splits_refunds_reimbursements_and_month_isolation(self):
        self.expense(self.owner,amount='100',category='Vehicle expenses',work_percent=30,business_percent=50,status='ready')
        self.expense(self.owner,amount='-20',category='Vehicle expenses',work_percent=30,business_percent=50)
        self.expense(self.owner,amount='1000',category='Vehicle expenses',reimbursed=True)
        self.expense(self.owner,amount='1000',category='Vehicle expenses',date='2026-09-30')
        for scope,spent in [('all',8000),('work',2400),('business',4000),('personal',1600)]:
            r=self.call(self.owner,'budgets',dict(month='2026-10',category='Vehicle expenses',scope=scope,amount='50'))
            self.assertEqual(r.status_code,200,r.json)
            b=next(x for x in self.owner.get('/api/budgets?month=2026-10').json if x['scope']==scope)
            self.assertEqual((b['spent_cents'],b['remaining_cents']),(spent,5000-spent))
        self.assertEqual(self.owner.get('/api/budgets?month=2026-09').json,[])
        self.assertEqual(self.call(self.owner,'budgets',dict(month='2026-10',category='Vehicle expenses',scope='all',amount=50)).status_code,409)

    def test_budget_edit_delete_copy_and_validation(self):
        data=dict(month='2026-10',category='Other',scope='all',amount='100')
        bid=self.call(self.owner,'budgets',data).json['id']
        self.assertEqual(self.call(self.owner,f'budgets/{bid}',{**data,'amount':'200','version':1},'PUT').status_code,200)
        self.assertEqual(self.call(self.owner,f'budgets/{bid}',{**data,'version':1},'PUT').status_code,409)
        self.assertEqual(self.call(self.owner,'budgets/copy',{'from':'2026-10','to':'2026-11'}).json['added'],1)
        self.assertEqual(self.call(self.owner,'budgets/copy',{'from':'2026-10','to':'2026-11'}).json['added'],0)
        self.assertEqual(self.call(self.owner,f'budgets/{bid}',{'version':2},'DELETE').status_code,200)
        for field,value in [('month','2026-13'),('period','weekly'),('period',None),('period',[]),('category','missing'),('scope','invalid'),('amount','NaN'),('amount',0)]:
            self.assertEqual(self.call(self.owner,'budgets',{**data,field:value}).status_code,400)
        self.assertEqual(self.agent.get('/api/budgets?month=2026-11').status_code,200)
        self.assertEqual(self.call(self.agent,'budgets',data).status_code,403)
        self.assertEqual(app.test_client().get('/api/budgets?month=2026-11').status_code,401)
        self.assertEqual(self.owner.post('/api/budgets',json=data).status_code,403)

    def test_period_boundaries_leap_year_and_allocations(self):
        # A quarter starting in December crosses a year and includes leap day.
        for day,amount in [('2027-11-30','999'),('2027-12-01','100'),('2028-01-31','100'),
                           ('2028-02-29','100'),('2028-03-01','100'),('2028-11-30','100'),('2028-12-01','999')]:
            self.expense(self.owner,date=day,amount=amount,category='Other',work_percent=30,business_percent=50)
        self.expense(self.owner,date='2028-02-29',amount='-20',category='Other',work_percent=30,business_percent=50)
        self.expense(self.owner,date='2028-02-29',amount='5000',category='Other',reimbursed=True)
        self.expense(self.owner,date='2028-02-29',amount='7000',category='Vehicle expenses')
        for period,total,end in [('monthly',10000,'2027-12-31'),('quarterly',28000,'2028-02-29'),('yearly',48000,'2028-11-30')]:
            for scope,percent in [('all',100),('work',30),('business',50),('personal',20)]:
                data=dict(month='2027-12',period=period,category='Other',scope=scope,amount=400)
                self.assertEqual(self.call(self.owner,'budgets',data).status_code,200)
                self.assertEqual(self.call(self.owner,'budgets',data).status_code,409)
                items=self.owner.get('/api/budgets?month=2027-12&period='+period).json
                budget=next(b for b in items if b['scope']==scope)
                self.assertEqual((budget['start_date'],budget['end_date']),('2027-12-01',end))
                self.assertEqual(budget['spent_cents'],total*percent//100)
                self.assertEqual(budget['remaining_cents'],40000-total*percent//100)
        legacy=self.owner.get('/api/budgets?month=2027-12').json
        self.assertEqual(len(legacy),4)
        self.assertTrue(all(b['period']=='monthly' for b in legacy))
        self.assertEqual(self.owner.get('/api/budgets?month=2027-12&period=weekly').status_code,400)

    def test_duration_edit_copy_isolation_and_financial_year(self):
        data=dict(month='2026-07',category='Other',scope='all',amount=1200)
        monthly=self.call(self.owner,'budgets',data).json['id']
        annual=self.call(self.owner,'budgets',{**data,'period':'yearly'}).json['id']
        self.expense(self.owner,date='2026-06-30',amount=999,category='Other')
        self.expense(self.owner,date='2026-07-01',amount=100,category='Other')
        self.expense(self.owner,date='2027-06-30',amount=200,category='Other')
        self.expense(self.owner,date='2027-07-01',amount=999,category='Other')
        annual_budget=self.owner.get('/api/budgets?month=2026-07&period=yearly').json[0]
        self.assertEqual((annual_budget['spent_cents'],annual_budget['end_date']),(30000,'2027-06-30'))
        # Older clients omitting period cannot silently change an existing duration.
        self.assertEqual(self.call(self.owner,f'budgets/{annual}',{**data,'amount':1500,'version':1},'PUT').status_code,200)
        self.assertEqual(self.owner.get('/api/budgets?month=2026-07&period=yearly').json[0]['amount_cents'],150000)
        self.assertEqual(self.call(self.owner,f'budgets/{annual}',{**data,'period':'monthly','version':2},'PUT').status_code,409)
        copy={'from':'2026-07','to':'2027-07','period':'yearly'}
        self.assertEqual(self.call(self.owner,'budgets/copy',copy).json['added'],1)
        self.assertEqual(self.call(self.owner,'budgets/copy',copy).json['added'],0)
        self.assertEqual(self.owner.get('/api/budgets?month=2027-07').json,[])
        self.assertEqual(self.call(self.owner,f'budgets/{monthly}',{**data,'period':'quarterly','version':1},'PUT').status_code,200)
        self.assertEqual(self.owner.get('/api/budgets?month=2026-07').json,[])
        quarterly=self.owner.get('/api/budgets?month=2026-07&period=quarterly').json[0]
        self.assertEqual((quarterly['id'],quarterly['version'],quarterly['end_date']),(monthly,2,'2026-09-30'))
        self.assertEqual(self.call(self.owner,f'budgets/{monthly}',{'version':1},'DELETE').status_code,409)
        self.assertEqual(self.call(self.owner,f'budgets/{monthly}',{'version':2},'DELETE').status_code,200)

    def prepare_vehicle(self):
        self.vid=self.call(self.owner,'vehicles',{'name':'Kia Cerato'}).json['id']
        self.path=f'vehicles/{self.vid}/comparison/2026'
        return self.vid

    def journey(self,scope,distance,purpose='Flight test'):
        return self.call(self.owner,'vehicle-journeys',dict(vehicle_id=self.vid,date='2026-10-10',origin='Home',destination='Airport',scope=scope,percent=100,distance=distance,purpose=purpose))

    def test_personal_purpose_and_combined_cap(self):
        self.prepare_vehicle()
        self.assertEqual(self.journey('personal','12.345','').status_code,200)
        self.assertEqual(self.journey('work','12.3','').status_code,400)
        self.assertEqual(self.journey('business','12.3',' ').status_code,400)
        self.journey('work','4000');self.journey('business','2000')
        r=self.owner.get('/api/'+self.path).json
        self.assertEqual(r['rate_cents'],91)
        self.assertEqual(r['eligible_metres'],6000000)
        self.assertEqual(r['cents_per_km']['total_cents'],455000)
        self.assertEqual(r['cents_per_km']['work_cents']+r['cents_per_km']['business_cents'],455000)
        self.assertEqual(self.owner.get(f'/api/vehicles/{self.vid}/comparison/2025').json['rate_cents'],88)
        self.assertEqual(self.owner.get(f'/api/vehicles/{self.vid}/comparison/2027').status_code,400)
        self.assertEqual(self.owner.get('/api/vehicle-journeys').json[-1]['distance_m'],12345)

    def test_costs_receipts_gst_depreciation_and_comparison_only(self):
        self.prepare_vehicle();image=io.BytesIO();Image.new('RGB',(5,5),'red').save(image,format='PNG');image.seek(0)
        token=self.owner.get('/api/session').json['csrf']
        rid=self.owner.post('/api/receipts',data={'file':(image,'fuel.png')},headers={'X-CSRF-Token':token}).json['id']
        eid=self.expense(self.owner,amount='1000',category='Vehicle expenses',vehicle_id=self.vid,receipt_id=rid,status='ready',work_percent=40,business_percent=10).json['id']
        parking=self.expense(self.owner,amount='100',category='Vehicle expenses',vehicle_id=self.vid).json['id']
        self.expense(self.owner,amount='500',vehicle_id=self.vid,reimbursed=True)
        self.expense(self.owner,amount='800',vehicle_id=self.vid,date='2025-10-10')
        other=self.call(self.owner,'vehicles',{'name':'Other car'}).json['id'];self.expense(self.owner,amount='700',vehicle_id=other)
        self.call(self.owner,f'vehicle-costs/{eid}',dict(kind='fuel',included=True,gst_credit='100',version=0),'PUT')
        self.call(self.owner,f'vehicle-costs/{parking}',dict(kind='parking_tolls',included=True,gst_credit=0,version=0),'PUT')
        before=self.owner.get('/api/tax/2026').json['recorded']
        d=dict(work_percent=30,business_percent=20,depreciation='1000',logbook_start='2026-07-01',logbook_end='2026-09-22',version=0)
        r=self.call(self.owner,self.path,d,'PUT');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['running_costs_cents'],90000)
        self.assertEqual(r.json['logbook']['total_cents'],95000)
        self.assertEqual(r.json['logbook_days'],84)
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded'],before)
        self.assertEqual(self.owner.get('/api/receipts/'+rid).status_code,200)
        self.assertTrue((DATA/'receipts'/rid).exists())
        self.assertEqual(self.call(self.owner,self.path,d,'PUT').status_code,409)
        self.assertEqual(self.call(self.owner,f'vehicle-costs/{eid}',dict(kind='fuel',included=True,gst_credit=0,version=0),'PUT').status_code,409)
        # An amount correction must not leave an impossible saved GST credit in the estimate.
        from app import db
        with app.app_context():
            db().execute('UPDATE expenses SET amount_cents=5000 WHERE id=?',(eid,));db().commit()
        changed=self.owner.get('/api/'+self.path).json
        self.assertEqual(changed['running_costs_cents'],0)
        self.assertTrue(any('GST credit exceeds' in w for w in changed['warnings']))
        self.call(self.owner,f'expenses/{eid}',{},'DELETE')
        self.assertFalse((DATA/'receipts'/rid).exists())
        self.assertEqual(self.owner.get('/api/'+self.path).json['running_costs_cents'],0)

    def test_comparison_invalid_inputs_and_permissions(self):
        self.prepare_vehicle()
        for data in [dict(work_percent=60,business_percent=50),dict(work_percent='nan'),dict(depreciation=-1),dict(logbook_start='2026-07-01'),dict(logbook_start='2026-09-01',logbook_end='2026-07-01')]:
            self.assertEqual(self.call(self.owner,self.path,data,'PUT').status_code,400)
        self.assertEqual(self.call(self.agent,self.path,{},'PUT').status_code,403)
        self.assertEqual(self.agent.get('/api/'+self.path).status_code,200)
        self.assertEqual(app.test_client().get('/api/'+self.path).status_code,401)
        self.assertEqual(self.owner.get('/api/vehicles/99999/comparison/2026').status_code,404)
