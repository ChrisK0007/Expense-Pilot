import csv
import io
import unittest
import test_app as base
from app import db, app
from overnights import comparison, RATES


class NativeOvernightTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login
    expense = base.AppTest.expense

    def trip(self, **changes):
        data=dict(location='Brisbane',start='2026-10-07',end='2026-10-09',purpose='Flight duties',scope='work',allowance=200)
        data.update(changes)
        result=self.call(self.owner,'trips',data)
        self.assertEqual(result.status_code,200,result.json)
        return result.json['id']

    def settings(self, tid, **changes):
        data=dict(version=self.owner.get(f'/api/trips/{tid}/overnight').json['version'],salary=100000,destination_class='capital',allowance_received=True,allowance_declared=True,
                  days=[dict(date='2026-10-08',Breakfast=True,Lunch=False,Dinner=True,Incidentals=True)])
        data.update(changes)
        return self.call(self.owner,f'trips/{tid}/overnight',data,'PUT')

    def test_separate_ledgers_forecast_and_actual_spending(self):
        tid=self.trip()
        for amount,meal,extra in [(50,'Dinner',{}),(-10,'Dinner',{}),(20,'Breakfast',{'reimbursed':True}),(99,'Lunch',{'status':'review'})]:
            result=self.expense(self.owner,scope='work',trip_id=tid,meal=meal,amount=amount,status=extra.get('status','ready'),reimbursed=extra.get('reimbursed',False))
            self.assertEqual(result.status_code,200,result.json)
        self.expense(self.owner,category='Equipment',scope='work',amount=100,status='ready')
        self.expense(self.owner,category='Meals',scope='work',amount=15,status='ready')
        result=self.settings(tid)
        self.assertEqual(result.status_code,200,result.json)
        c=result.json
        self.assertEqual(c['actual_cents'],15900)
        self.assertEqual(c['reimbursed_cents'],2000)
        self.assertEqual(c['recorded_unreimbursed_cents'],4000)
        self.assertEqual(c['comparable_cents'],4000)
        self.assertEqual(c['reasonable_cents'],3600+6900+2540)
        self.assertEqual(c['allowance_less_spending_cents'],6100)
        self.assertTrue(c['allowance_exception_may_apply'])
        forecast=self.owner.get('/api/tax/2026').json
        self.assertEqual(forecast['recorded']['work_deductions_cents'],10000)
        self.assertEqual(forecast['recorded']['overnight_work_cents'],5500)
        self.assertEqual(forecast['unreviewed'],0)
        def count(ledger):return len(list(csv.DictReader(io.StringIO(self.owner.get('/api/export?ledger='+ledger).data.decode('utf-8-sig')))))
        self.assertEqual((count('ordinary'),count('overnight'),count('all')),(1,5,6))
        self.assertEqual(self.owner.get('/api/export?ledger=invalid').status_code,400)
        self.assertEqual(len(self.owner.get('/api/expenses').json),6,'Separation must not delete records')

    def test_date_salary_boundaries_permissions_and_stale_versions(self):
        tid=self.trip(start='2026-06-30',end='2026-07-01')
        days=[dict(date=d,Dinner=True) for d in ['2026-06-30','2026-07-01']]
        c=self.settings(tid,days=days,salary=150000).json
        self.assertEqual(c['reasonable_cents'],7495+6900,'The salary band must be chosen for each financial year')
        self.assertEqual(c['sources'],['TD 2025/4','TD 2026/4'])
        self.assertEqual(self.settings(tid,version=1,days=days).status_code,409)
        self.assertEqual(self.settings(tid,days=[dict(date='2026-10-08',Dinner=True)]).status_code,400)
        self.assertEqual(self.settings(tid,days=[dict(date='2026-06-30',Dinner='yes')]).status_code,400)
        self.assertEqual(self.settings(tid,days=[days[0],days[0]]).status_code,400)
        self.assertEqual(self.call(self.agent,f'trips/{tid}/overnight',{},'PUT').status_code,403)
        self.assertEqual(app.test_client().get(f'/api/trips/{tid}/overnight').status_code,401)

    def test_unsupported_year_and_custom_overseas_rates(self):
        tid=self.trip(start='2028-01-01',end='2028-01-02')
        data=dict(days=[dict(date='2028-01-01',Dinner=True)])
        c=self.settings(tid,**data).json
        self.assertIsNone(c['reasonable_cents']);self.assertEqual(c['missing_years'],['2027–2028'])
        c=self.settings(tid,**data,destination_class='custom',custom_rates={'Dinner':75},source='Verified overseas destination / FY 2027-28').json
        self.assertEqual(c['reasonable_cents'],7500)
        self.assertEqual(self.settings(tid,**data,destination_class='custom',source='').status_code,400)

    def test_invoice_retry_is_atomic_and_keeps_deleted_tombstone(self):
        cid=self.call(self.owner,'billing/clients',{'name':'Native client'}).json['id']
        self.call(self.owner,'billing/settings',{'name':'Business','gst_registered':True,'abn':'12345678901'},'PUT')
        payload=dict(kind='invoice',client_id=cid,issue_date='2026-10-08',due_date='2026-10-22',tax_mode='exclusive',
                     lines=[dict(description='Native service',quantity='2',unit_price='50.00',tax='gst')],request_key='native-request-key-01234567')
        first=self.call(self.owner,'billing/documents',payload)
        self.assertEqual(first.status_code,200,first.json)
        again=self.call(self.owner,'billing/documents',payload)
        self.assertEqual(again.json,first.json)
        self.assertEqual(len(self.owner.get('/api/billing/documents').json),1)
        doc=self.owner.get('/api/billing/documents/'+str(first.json['id'])).json
        self.assertEqual(doc['total_cents'],11000);self.assertEqual(doc['state'],'draft')
        self.assertEqual(self.call(self.owner,'billing/documents',{**payload,'reference':'changed'}).status_code,409)
        self.assertEqual(self.call(self.owner,'billing/documents/'+str(doc['id']),{'version':doc['version']},'DELETE').status_code,200)
        self.assertEqual(self.call(self.owner,'billing/documents',payload).status_code,409)
        self.assertEqual(self.call(self.owner,'billing/documents',{**payload,'request_key':'short'}).status_code,400)
        self.assertEqual(self.call(self.agent,'billing/documents',payload).status_code,403)
        with app.app_context():self.assertEqual(db().execute('SELECT COUNT(*) FROM billing_outbox').fetchone()[0],0)
