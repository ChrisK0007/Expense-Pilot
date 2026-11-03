"""Automatic receipt matching and atomic historical matching, using a fake feed."""
import unittest
from unittest.mock import patch
import test_pocketsmith as feeds
from test_pocketsmith import FakeClient, purchase, TODAY
import test_receipts as receipts
from app import app, db
from bank_matching import same_merchant


class MatchingTests(unittest.TestCase):
    setUp=feeds.FeedTest.setUp
    login=feeds.FeedTest.login
    call=feeds.FeedTest.call
    expense=feeds.FeedTest.expense
    connect=feeds.FeedTest.connect
    sync=feeds.FeedTest.sync
    ledger=feeds.FeedTest.ledger
    upload=receipts.ReceiptTest.upload

    def ready(self):
        self.connect();self.assertEqual(self.sync().status_code,200)
        return self.upload().json['id']

    def data(self,**updates):
        d=dict(date=TODAY,merchant='PocketSmith cafe',amount=12.50,scope='personal',work_percent=0,business_percent=0,category='Other',status='ready');d.update(updates);return d

    def test_match_at_filing_and_fallback_only_when_no_match(self):
        rid=self.ready();preview=self.call(self.owner,f'receipts/{rid}/bank-matches',self.data()).json
        self.assertEqual(preview['status'],'matched');self.assertIsNone(self.ledger()[0]['expense_id'])
        result=self.call(self.owner,f'receipts/{rid}/expense',self.data());self.assertEqual(result.status_code,200,result.json)
        e=self.owner.get('/api/expenses').json[0];self.assertEqual(e['account_id'],self.aid);self.assertEqual(self.ledger()[0]['expense_id'],e['id'])
        rid2=self.upload(color='red').json['id']
        self.assertEqual(self.call(self.owner,f'receipts/{rid2}/expense',self.data()).status_code,409)
        missed=self.call(self.owner,f'receipts/{rid2}/expense',self.data(merchant='Unrelated supplier',amount=30));self.assertEqual(missed.status_code,200,missed.json)
        self.assertIsNone(next(e for e in self.owner.get('/api/expenses').json if e['id']==missed.json['id'])['account_id'])

    def test_linked_or_manual_existing_expense_gets_original_without_duplicate(self):
        rid=self.ready();e=self.expense(self.owner,**self.data()).json['id']
        # A pre-existing manual/CSV expense gets reused and linked.
        result=self.call(self.owner,f'receipts/{rid}/expense',self.data());self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['id'],e);self.assertEqual(len(self.owner.get('/api/expenses').json),1)
        self.assertEqual(self.ledger()[0]['expense_id'],e)

    def test_ambiguous_pending_ignored_foreign_and_explicit_cash(self):
        rid=self.ready()
        with app.app_context():
            db().execute("UPDATE bank_transactions SET source_status='pending'");db().commit()
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/bank-matches',self.data()).json['status'],'none')
        with app.app_context():
            db().execute("UPDATE bank_transactions SET source_status='posted',state='ignored'");db().commit()
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/bank-matches',self.data()).json['status'],'none')
        with app.app_context():
            db().execute("UPDATE bank_transactions SET state='review',currency='USD'");db().commit()
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/bank-matches',self.data()).json['status'],'none')
        with app.app_context():
            db().execute("UPDATE bank_transactions SET currency='AUD'");db().commit()
        FakeClient.transactions=[purchase(),purchase(902)];self.assertEqual(self.sync().status_code,200)
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/bank-matches',self.data()).json['status'],'review')
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/expense',self.data()).status_code,409)
        saved=self.call(self.owner,f'receipts/{rid}/expense',self.data(bank_choice='cash'));self.assertEqual(saved.status_code,200,saved.json)
        e=self.owner.get('/api/expenses').json[0];self.assertIsNone(e['account_id']);self.assertEqual(e['bank_match_excluded'],1)
        self.assertEqual(self.owner.get('/api/bank-matches/previous').json['checked'],0)

    def test_previous_matches_are_bidirectionally_unique_and_revalidated_atomically(self):
        self.ready();eid=self.expense(self.owner,**self.data()).json['id']
        plan=self.owner.get('/api/bank-matches/previous').json
        self.assertEqual(len(plan['matches']),1)
        with app.app_context():
            db().execute('UPDATE expenses SET amount_cents=999 WHERE id=?',(eid,));db().commit()
        self.assertEqual(self.call(self.owner,'bank-matches/previous',plan).status_code,409)
        self.assertIsNone(self.ledger()[0]['expense_id'])
        with app.app_context():
            db().execute('UPDATE expenses SET amount_cents=1250 WHERE id=?',(eid,));db().commit()
        other=self.expense(self.owner,**self.data()).json['id']
        plan=self.owner.get('/api/bank-matches/previous').json;self.assertEqual(plan['matches'],[]);self.assertEqual(plan['ambiguous'],2)
        self.call(self.owner,'expenses/'+str(other),{},'DELETE')
        plan=self.owner.get('/api/bank-matches/previous').json
        self.assertEqual(self.call(self.agent,'bank-matches/previous',plan).status_code,403)
        self.assertEqual(self.call(self.owner,'bank-matches/previous',plan).json['matched'],1)
        self.assertEqual(self.ledger()[0]['expense_id'],eid)
        self.assertEqual(self.call(self.owner,'bank-matches/previous',plan).status_code,409)
        self.assertEqual(self.owner.get('/api/bank-matches/previous').json['checked'],0)

    def test_home_office_bill_is_classified_and_matched_in_same_transaction(self):
        rid=self.ready();d=self.data(document_kind='home_office',home_office_kind='internet',personally_paid=True)
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/expense',{**d,'personally_paid':False}).status_code,400)
        with patch('home_office.history',side_effect=RuntimeError('injected failure')):
            with self.assertRaises(RuntimeError):self.call(self.owner,f'receipts/{rid}/expense',d)
        self.assertEqual(self.owner.get('/api/expenses').json,[]);self.assertIsNone(self.ledger()[0]['expense_id'])
        result=self.call(self.owner,f'receipts/{rid}/expense',d);self.assertEqual(result.status_code,200,result.json)
        e=self.owner.get('/api/expenses').json[0]
        self.assertEqual(e['work_percent']+e['business_percent'],0);self.assertEqual(e['account_id'],self.aid)
        with app.app_context():self.assertEqual(db().execute('SELECT kind FROM home_office_costs WHERE expense_id=?',(e['id'],)).fetchone()[0],'internet')

    def test_changed_linked_expense_and_stale_selected_transaction_are_rejected(self):
        rid=self.ready();t=self.ledger()[0]
        result=self.call(self.owner,f'receipts/{rid}/expense',self.data(bank_choice=str(t['id']),bank_version=t['version']-1))
        self.assertEqual(result.status_code,409);self.assertEqual(self.owner.get('/api/expenses').json,[])
        eid=self.expense(self.owner,**self.data()).json['id']
        self.assertEqual(self.call(self.owner,'bank-transactions/'+str(t['id']),{'action':'link','version':t['version'],'expense_id':eid}).status_code,200)
        with app.app_context():
            db().execute('UPDATE expenses SET amount_cents=999 WHERE id=?',(eid,));db().commit()
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/bank-matches',self.data()).json['status'],'review')
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/expense',self.data()).status_code,409)
        self.assertIsNone(self.owner.get('/api/expenses').json[0]['receipt_id'])

    def test_merchant_identity_is_required(self):
        self.assertTrue(same_merchant('Telstra','VISA TELSTRA PTY LTD AU'))
        self.assertFalse(same_merchant('Cafe','Different restaurant'))
        self.assertFalse(same_merchant('Supplier Alpha','Supplier Beta'))
