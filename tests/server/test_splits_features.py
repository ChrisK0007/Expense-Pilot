import csv
import io
import sqlite3
import unittest
import test_app as base
from app import app, db
from expense_core import allocations, migrate

class AllocationMathTest(unittest.TestCase):
    def test_migration_keeps_existing_allocations_and_is_idempotent(self):
        connection=sqlite3.connect(':memory:')
        connection.execute('CREATE TABLE expenses(scope TEXT,percent INTEGER)')
        connection.executemany('INSERT INTO expenses VALUES (?,?)',[('work',30),('business',20),('personal',0)])
        migrate(connection)
        self.assertEqual(connection.execute('SELECT work_percent,business_percent FROM expenses').fetchall(),[(30,0),(0,20),(0,0)])
        connection.execute("UPDATE expenses SET work_percent=30,business_percent=20 WHERE scope='work'")
        migrate(connection)
        self.assertEqual(connection.execute("SELECT work_percent,business_percent FROM expenses WHERE scope='work'").fetchone(),(30,20))

    def test_rounding_reconciles_and_refunds_are_symmetric(self):
        for amount in (1,3,101,17999):
            positive=allocations(dict(amount_cents=amount,work_percent=50,business_percent=50))
            negative=allocations(dict(amount_cents=-amount,work_percent=50,business_percent=50))
            self.assertEqual(sum(positive),amount)
            self.assertEqual(negative,tuple(-x for x in positive))

class SplitsFeaturesTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login
    expense=base.AppTest.expense

    def test_split_flows_into_expense_forecast_and_csv_once(self):
        result=self.expense(self.owner,merchant='Split phone',category='Phone & internet',amount=100,scope='split',work_percent=30,business_percent=20,status='ready')
        self.assertEqual(result.status_code,200,result.json)
        record=self.owner.get('/api/expenses').json[0]
        self.assertEqual((record['scope'],record['percent'],record['work_percent'],record['business_percent']),('split',50,30,20))
        report=self.owner.get('/api/tax/2026').json['recorded']
        self.assertEqual((report['work_deductions_cents'],report['business_deductions_cents']),(3000,2000))
        export=list(csv.DictReader(io.StringIO(self.owner.get('/api/export').data.decode('utf-8-sig'))))
        self.assertEqual(len(export),1)
        self.assertEqual([export[0][x] for x in ('Employment %','Business %','Personal %','Employment allocation AUD','Business allocation AUD','Allocated amount AUD (not tax determination)')],['30','20','50','30.00','20.00','50.00'])
        for extra in ({'amount':-10},{'amount':1000,'reimbursed':True},{'amount':1000,'status':'review'}):
            values=dict(category='Phone & internet',scope='split',work_percent=30,business_percent=20,status='ready');values.update(extra)
            self.expense(self.owner,**values)
        report=self.owner.get('/api/tax/2026').json['recorded']
        self.assertEqual((report['work_deductions_cents'],report['business_deductions_cents']),(2700,1800))

    def test_invalid_and_employee_splits_are_rejected(self):
        for values in ({'work_percent':80,'business_percent':30},{'work_percent':-1,'business_percent':20},{'work_percent':30.5,'business_percent':20},{'work_percent':'NaN','business_percent':20},{'work_percent':30}):
            self.assertEqual(self.expense(self.owner,**values).status_code,400,values)
        self.assertEqual(self.expense(self.agent,work_percent=30,business_percent=20).status_code,403)

    def test_receipt_draft_split_and_edit_survive(self):
        from PIL import Image
        data=io.BytesIO();Image.new('RGB',(30,30),'white').save(data,'PNG');data.seek(0)
        response=self.owner.post('/api/receipts',data={'file':(data,'split.png')},headers={'X-CSRF-Token':self.owner.get('/api/session').json['csrf']})
        rid=response.json['id'];values=dict(date='2026-10-08',merchant='Receipt split',scope='split',category='Other',amount=100,work_percent=30,business_percent=20)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/draft',values,'PUT').status_code,200)
        self.assertEqual(self.owner.get('/api/receipts').json[0]['draft']['business_percent'],20)
        response=self.call(self.owner,'receipts/'+rid+'/expense',dict(**values,status='ready'))
        self.assertEqual(response.status_code,200,response.json)
        eid=response.json['id'];values.update(amount=200,work_percent=10,business_percent=40)
        self.assertEqual(self.call(self.owner,'expenses/'+str(eid),dict(**values,receipt_id=rid,status='ready'),'PUT').status_code,200)
        saved=self.owner.get('/api/receipts').json[0]['saved_expense']
        self.assertEqual((saved['amount_cents'],saved['work_percent'],saved['business_percent']),(20000,10,40))

    def test_feature_preferences_are_per_login_and_keep_records(self):
        self.expense(self.owner,amount=100,status='ready')
        before=self.owner.get('/api/tax/2026').json['recorded']
        response=self.call(self.owner,'features',{'business':False,'employment':True,'tax':False},'PUT')
        self.assertEqual(response.status_code,200,response.json)
        self.assertFalse(self.owner.get('/api/session').json['features']['business'])
        self.assertTrue(self.agent.get('/api/features').json['business'])
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded'],before)
        self.assertEqual(len(self.owner.get('/api/expenses').json),1)
        self.assertEqual(self.call(self.owner,'features',{'employment':False},'PUT').status_code,400)
        self.assertEqual(self.call(self.owner,'features',{'business':'false'},'PUT').status_code,400)
        self.assertEqual(self.call(self.agent,'features',{'vehicles':False},'PUT').status_code,200)
        self.assertEqual(self.call(self.staff,'features',{'employment':True},'PUT').status_code,200)
