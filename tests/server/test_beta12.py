"""Simplified review and invoice amendments, using synthetic data and fake bank feeds."""
import json
import unittest
from datetime import date, timedelta
from unittest.mock import patch
import test_billing, test_bank_matching, test_workflows
from test_pocketsmith import FakeClient, purchase, TODAY
from app import app, db, one


class InvoiceAmendmentTest(unittest.TestCase):
    setUp=test_billing.BillingTest.setUp
    call=test_billing.BillingTest.call
    login=test_billing.BillingTest.login
    create=test_billing.BillingTest.create
    get=test_billing.BillingTest.get
    action=test_billing.BillingTest.action
    issue=test_billing.BillingTest.issue
    pay=test_billing.BillingTest.pay
    email_config=test_billing.BillingTest.email_config

    def amend(self,doc,**updates):
        payload=dict(version=doc['version'],kind='invoice',client_id=self.cid,issue_date=doc['issue_date'],due_date=doc['due_date'],tax_mode='exclusive',number=doc['number'],lines=[dict(description='Corrected service',quantity=2,unit_price=60,tax='gst')])
        payload.update(updates)
        return self.call(self.owner,f"billing/documents/{doc['id']}",payload,'PUT')

    def test_amend_reissue_retains_snapshot_and_rejects_stale_edits(self):
        old=self.issue(self.create())
        r=self.amend(old,number='CORRECTED-1');self.assertEqual(r.status_code,200,r.json)
        new=self.get(old['id']);self.assertEqual((new['needs_reissue'],new['total_cents'],new['number']),(1,13200,'CORRECTED-1'))
        with app.app_context():
            saved=json.loads(one('SELECT previous FROM billing_revision_history WHERE document_id=?',(old['id'],))['previous'])
            self.assertEqual(saved['lines'],old['lines']);self.assertEqual(saved['number'],old['number'])
        self.assertEqual(self.amend(old).status_code,409)
        self.assertEqual(self.pay(new,10).status_code,409)
        self.assertEqual(self.owner.get(f"/api/billing/documents/{old['id']}/email-draft?kind=reminder_manual").status_code,409)
        new=self.issue(new);self.assertEqual(new['needs_reissue'],0)
        self.assertEqual(self.pay(new,132).status_code,200)

    def test_paid_invoice_locked_for_all_edit_routes_and_readonly_user(self):
        d=self.issue(self.create());self.assertEqual(self.pay(d,110).status_code,200);d=self.get(d['id'])
        self.assertEqual(self.amend(d).status_code,409)
        for route,data in [('number',dict(number='PAID-CHANGE')),('wording',dict(descriptions=['No change']))]:
            self.assertEqual(self.call(self.owner,f"billing/documents/{d['id']}/{route}",{**data,'version':d['version']},'PUT').status_code,409)
        self.assertEqual(self.call(self.agent,f"billing/documents/{d['id']}",dict(version=d['version']),'PUT').status_code,403)
        with app.app_context(): self.assertEqual(one('SELECT count(*) n FROM billing_revision_history')['n'],0)

    def test_partial_payments_preserved_and_constrain_edits(self):
        d=self.issue(self.create());self.assertEqual(self.pay(d,50).status_code,200);d=self.get(d['id'])
        low=[dict(description='Too small',quantity=1,unit_price=40,tax='gst')]
        self.assertEqual(self.amend(d,lines=low).status_code,409)
        other=self.call(self.owner,'billing/clients',dict(name='Other client',terms=7)).json['id']
        self.assertEqual(self.amend(d,client_id=other).status_code,409)
        later=(date.fromisoformat(self.today)+timedelta(days=1)).isoformat()
        self.assertEqual(self.amend(d,issue_date=later,due_date=later).status_code,409)
        self.assertEqual(self.amend(d).status_code,200)
        new=self.get(d['id']);self.assertEqual((new['paid_cents'],new['balance_cents'],len(new['payments'])),(5000,8200,1))

    def test_due_date_auto_manual_and_legacy_clients(self):
        d=self.create(due_date_manual=False,issue_date='2024-02-20',due_date='ignored')
        self.assertEqual(d['due_date'],'2024-03-05')
        self.assertEqual(self.amend(d,issue_date='2024-02-29').status_code,200)
        d=self.get(d['id']);self.assertEqual(d['due_date'],'2024-03-14')
        self.assertEqual(self.amend(d,due_date_manual=True,due_date='2024-04-15').status_code,200)
        d=self.get(d['id']);self.assertEqual(self.amend(d,issue_date='2024-03-02').status_code,200)
        d=self.get(d['id']);self.assertEqual((d['due_date'],d['due_date_manual']),('2024-04-15',1))
        self.assertEqual(self.amend(d,due_date_manual=False).status_code,200)
        self.assertEqual(self.get(d['id'])['due_date'],'2024-03-16')
        legacy=self.create(issue_date='2024-02-20',due_date='2024-04-01')
        self.assertEqual((legacy['due_date_manual'],legacy['due_date']),(1,'2024-04-01'))

    def test_uncertain_delivery_and_void_cannot_be_amended(self):
        d=self.issue(self.create())
        with app.app_context():
            db().execute("INSERT INTO billing_outbox(document_id,recipient,subject,body,state,created_at,request_key) VALUES (?,'client@example.test','Test','Test','unknown','now','synthetic-unknown')",(d['id'],));db().commit()
        self.assertEqual(self.amend(d).status_code,409)
        with app.app_context(): db().execute('DELETE FROM billing_outbox');db().commit()
        self.assertEqual(self.action(d,'void').status_code,200)
        self.assertEqual(self.amend(self.get(d['id'])).status_code,409)

    def test_reissue_email_uses_new_version_and_clears_pending(self):
        self.email_config();d=self.issue(self.create());self.assertEqual(self.amend(d).status_code,200)
        draft=self.owner.get(f"/api/billing/documents/{d['id']}/email-draft").json
        with patch('billing.deliver',return_value=('sent','')) as deliver:
            response=self.call(self.owner,f"billing/documents/{d['id']}/send",draft)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.get(d['id'])['needs_reissue'],0)
        deliver.assert_called_once()


class AutomaticMatchTest(unittest.TestCase):
    setUp=test_bank_matching.MatchingTests.setUp
    login=test_bank_matching.MatchingTests.login
    call=test_bank_matching.MatchingTests.call
    expense=test_bank_matching.MatchingTests.expense
    connect=test_bank_matching.MatchingTests.connect
    sync=test_bank_matching.MatchingTests.sync
    ledger=test_bank_matching.MatchingTests.ledger
    data=test_bank_matching.MatchingTests.data
    upload=test_bank_matching.MatchingTests.upload

    def attention(self):
        year=int(TODAY[:4])-(int(TODAY[5:7])<7)
        r=self.owner.get('/api/workflows/attention/'+str(year));self.assertEqual(r.status_code,200,r.json);return r.json['items']

    def test_receipt_first_later_sync_links_once_without_changing_allocations(self):
        rid=self.upload().json['id'];r=self.call(self.owner,f'receipts/{rid}/expense',self.data());self.assertEqual(r.status_code,200,r.json)
        eid=r.json['id'];self.connect();r=self.sync();self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['matched'],1)
        self.assertEqual(self.ledger()[0]['expense_id'],eid)
        self.assertEqual(self.sync().json['matched'],0)
        e=self.owner.get('/api/expenses').json[0];self.assertEqual(e['receipt_id'],rid);self.assertEqual(e['amount_cents'],1250);self.assertEqual(e['work_percent']+e['business_percent'],0)
        self.assertFalse([i for i in self.attention() if i['kind'].startswith('bank')])

    def test_only_matching_conflicts_and_changed_links_need_attention(self):
        self.connect();self.sync();self.assertFalse([i for i in self.attention() if i['kind']=='bank'])
        a=self.expense(self.owner,**self.data()).json['id'];b=self.expense(self.owner,**self.data()).json['id']
        self.assertEqual(self.sync().json['matched'],0);self.assertIsNone(self.ledger()[0]['expense_id'])
        self.assertEqual({i['id'] for i in self.attention() if i['kind']=='bank_match'},{a,b})
        self.call(self.owner,'expenses/'+str(b),{},'DELETE');self.assertEqual(self.sync().json['matched'],1)
        FakeClient.transactions=[{**purchase(),'amount':-13}];self.sync()
        self.assertEqual(len([i for i in self.attention() if i['kind']=='bank']),1)
        self.assertEqual(self.owner.get('/api/expenses').json[0]['amount_cents'],1250)

    def test_explicit_cash_and_ignored_transactions_are_never_auto_matched(self):
        self.connect();self.sync();rid=self.upload().json['id']
        self.assertEqual(self.call(self.owner,f'receipts/{rid}/expense',self.data(bank_choice='cash')).status_code,200)
        self.assertEqual(self.sync().json['matched'],0)
        with app.app_context(): db().execute("UPDATE bank_transactions SET state='ignored'");db().commit()
        self.expense(self.owner,**self.data());self.assertEqual(self.sync().json['matched'],0)

    def test_changed_or_missing_reconciled_purchase_is_flagged(self):
        self.connect();self.sync();eid=self.expense(self.owner,**self.data()).json['id'];bid=self.ledger()[0]['id']
        payload=dict(bank_id=bid,kind='expense',allocations=[dict(id=eid,amount=12.50)])
        p=self.call(self.owner,'workflows/reconciliation/preview',payload);self.assertEqual(p.status_code,200,p.json)
        r=self.call(self.owner,'workflows/reconciliation/apply',{**payload,'token':p.json['token']});self.assertEqual(r.status_code,200,r.json)
        FakeClient.transactions=[{**purchase(),'amount':-14}];self.assertEqual(self.sync().status_code,200)
        self.assertEqual(len([i for i in self.attention() if i['kind']=='bank']),1)
        for change in [dict(status='pending'),dict(is_transfer=True)]:
            FakeClient.transactions=[{**purchase(),**change}];self.assertEqual(self.sync().status_code,200)
            self.assertEqual(len([i for i in self.attention() if i['kind']=='bank']),1)
        FakeClient.transactions=[];self.assertEqual(self.sync().status_code,200)
        self.assertEqual(len([i for i in self.attention() if i['kind']=='bank']),1)


class FocusedAttentionTest(unittest.TestCase):
    setUp=test_workflows.WorkflowTest.setUp
    call=test_workflows.WorkflowTest.call
    login=test_workflows.WorkflowTest.login
    expense=test_workflows.WorkflowTest.expense
    bank=test_workflows.WorkflowTest.bank
    invoice=test_workflows.WorkflowTest.invoice
    match=test_workflows.WorkflowTest.match

    def test_phone_classification_is_not_repeated_and_missing_purpose_is_visible(self):
        with app.app_context():
            uid=one("SELECT id FROM users WHERE role='owner'")['id']
            vid=db().execute("INSERT INTO vehicles(user_id,name) VALUES (?,'Car')",(uid,)).lastrowid
            for scope,purpose in [('personal',''),('business','Client meeting'),('work','Training'),('work','')]:
                db().execute("INSERT INTO vehicle_journeys(vehicle_id,date,origin,destination,purpose,scope,distance_m) VALUES (?,'2026-10-08','A','B',?,?,1000)",(vid,purpose,scope))
            db().commit()
        r=self.owner.get('/api/workflows/attention/2026');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(len([i for i in r.json['items'] if i['kind']=='journey']),1)

    def test_reconciliation_refuses_an_amended_invoice_until_reissued(self):
        did=self.invoice(10000);bid=self.bank(10000)
        with app.app_context(): db().execute('UPDATE billing_documents SET needs_reissue=1 WHERE id=?',(did,));db().commit()
        result=self.call(self.owner,'workflows/reconciliation/preview',dict(bank_id=bid,kind='invoice',allocations=[dict(id=did,amount=100)]))
        self.assertEqual(result.status_code,400,result.json)
