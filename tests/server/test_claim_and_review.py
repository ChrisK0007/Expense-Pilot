"""Confirm review actions preserve source amounts and prevent double counting."""
from datetime import date
import unittest
from unittest.mock import patch

import test_app
from app import app, db, one


class ClaimAndReviewTest(unittest.TestCase):
    call = test_app.AppTest.call
    login = test_app.AppTest.login
    expense = test_app.AppTest.expense

    def setUp(self):
        test_app.AppTest.setUp(self)
        self.addCleanup(self.clear_review_links)

    def clear_review_links(self):
        # Several integration suites share the fixture database and reset its
        # original parent tables. Remove the new child records first.
        with app.app_context():
            for table in ('recurring_expense_occurrences', 'recurring_expense_rules',
                          'bank_transfer_pairs', 'billable_expenses', 'handover_revisions'):
                db().execute('DELETE FROM ' + table)
            db().commit()

    def bank(self, name, cents, payee):
        with app.app_context():
            account = db().execute("INSERT INTO accounts(name,bank) VALUES (?,'Test')",(name,)).lastrowid
            feed = db().execute("""INSERT INTO pocketsmith_accounts(remote_user_id,remote_id,name,currency,local_account_id,enabled)
                               VALUES ('1',?,?,'AUD',?,1)""",(str(account),name,account)).lastrowid
            bank = db().execute("""INSERT INTO bank_transactions(feed_account_id,remote_user_id,remote_id,date,payee,amount_cents,
                                currency,source_status,fingerprint,last_seen)
                                VALUES (?,'1',?,'2026-10-08',?,?,'AUD','posted','test','now')""",
                                (feed,str(feed),payee,cents)).lastrowid
            db().commit()
            return account, bank

    def test_posted_charge_reuses_existing_expense(self):
        aid,bid=self.bank('Checking',-1230,'GitHub')
        e=self.expense(self.owner,merchant='GitHub',category='Subscriptions',amount='12.30',account_id=aid)
        self.assertEqual(e.status_code,200,e.json)
        rule=self.call(self.owner,'recurring-expenses',dict(merchant='GitHub',start='2026-10-08',interval='monthly',
            category='Subscriptions',amount='10',account_id=aid,work_percent=20,business_percent=60))
        self.assertEqual(rule.status_code,200,rule.json)
        path=f"recurring-expenses/{rule.json['id']}/2026-10-08"
        with patch('workspace_time.today',return_value=date(2026,10,10)):
            preview=self.call(self.owner,path+'/preview',dict(bank_id=bid))
            self.assertEqual(preview.status_code,200,preview.json)
            self.assertEqual(preview.json['bank']['amount_cents'],-1230)
            payload=dict(bank_id=bid,expense_id=e.json['id'],token=preview.json['token'])
            for _ in range(2):
                result=self.call(self.owner,path+'/apply',payload)
                self.assertEqual(result.json['expense_id'],e.json['id'])
        self.assertEqual(len(self.owner.get('/api/expenses').json),1)

    def test_transfer_pair_reserves_both_sides_and_undo_restores_review(self):
        _,debit=self.bank('Checking',-5000,'Credit card repayment')
        _,credit=self.bank('Amex',5000,'Card repayment')
        payload=dict(debit_id=debit,credit_id=credit,debit_version=1,credit_version=1)
        result=self.call(self.owner,'bank-transfers',payload)
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.call(self.owner,'bank-transfers',payload).status_code,409)
        self.assertEqual(self.owner.get('/api/bank-transactions?state=review').json['total'],0)
        self.assertEqual(len(self.owner.get('/api/expenses').json),0)
        self.assertEqual(self.call(self.owner,'bank-transfers/'+str(result.json['id']),{},'DELETE').status_code,200)
        self.assertEqual(self.owner.get('/api/bank-transactions?state=review').json['total'],2)

    def test_billable_expense_is_reserved_to_one_invoice_and_released_on_delete(self):
        client=self.call(self.owner,'billing/clients',dict(name='Example client')).json['id']
        eid=self.expense(self.owner,scope='business',category='Other',amount='50',status='ready').json['id']
        self.assertEqual(self.call(self.owner,f'expenses/{eid}/billable',dict(client_id=client),'PUT').status_code,200)
        payload=dict(kind='invoice',client_id=client,issue_date='2026-10-08',due_date='2026-10-22',tax_mode='none',
                     lines=[dict(description='Travel',quantity='1',unit_price='50.00',source_expense_id=eid)])
        doc=self.call(self.owner,'billing/documents',payload)
        self.assertEqual(doc.status_code,200,doc.json)
        did=doc.json['id']
        self.assertEqual(self.call(self.owner,'billing/documents',payload).status_code,409)
        version=self.owner.get(f'/api/billing/documents/{did}').json['version']
        self.assertEqual(self.call(self.owner,f'billing/documents/{did}',dict(version=version),'DELETE').status_code,200)
        self.assertEqual(self.owner.get(f'/api/billing/billable-expenses?client_id={client}').json[0]['id'],eid)

    def test_handover_retains_prior_figures_and_rejects_a_stale_preview(self):
        path='workflows/handover/2026/review'
        previous=self.owner.get('/api/'+path).json
        self.expense(self.owner,scope='work',category='Other',amount='12',status='ready')
        self.assertEqual(self.call(self.owner,path,dict(note='First review',token=previous['token'])).status_code,409)
        first=self.owner.get('/api/'+path).json
        self.assertEqual(self.call(self.owner,path,dict(note='First review',token=first['token'])).status_code,200)
        self.expense(self.owner,scope='work',category='Other',amount='15',status='ready')
        next_state=self.owner.get('/api/'+path).json
        self.assertIn(dict(key='work_deductions_cents',before=1200,after=2700),next_state['changes'])
        self.assertEqual(self.call(self.owner,path,dict(note='Late receipt',token=next_state['token'])).json['revision'],2)
        history=self.owner.get('/api/'+path).json['history']
        self.assertEqual([h['revision'] for h in history],[2,1])

    def test_overnight_forecast_includes_actual_cost_and_reopens_after_edit(self):
        trip=self.call(self.owner,'trips',dict(location='Vanuatu',start='2026-10-07',end='2026-10-09',
                                                scope='work',purpose='Flight duties',allowance=160)).json['id']
        expense=self.expense(self.owner,category='Meals',scope='work',trip_id=trip,meal='Dinner',amount=42,status='ready').json['id']
        days=[dict(date='2026-10-08',Breakfast=True,Lunch=True,Dinner=True,Incidentals=True)]
        version=self.owner.get(f'/api/trips/{trip}/overnight').json['version']
        result=self.call(self.owner,f'trips/{trip}/overnight',dict(version=version,salary=170000,destination_class='overseas',
                         destination='Vanuatu',allowance_received=True,allowance_declared=True,days=days,confirm_claim=True),'PUT')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['reasonable_cents'],26000)
        self.assertTrue(result.json['claim_current'])
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded']['work_deductions_cents'],4200)
        with app.app_context():
            db().execute('UPDATE expenses SET amount_cents=4400 WHERE id=?',(expense,))
            db().commit()
        self.assertTrue(self.owner.get(f'/api/trips/{trip}/overnight').json['claim_stale'])
        self.assertEqual(self.owner.get('/api/tax/2026').json['recorded']['work_deductions_cents'],0)
