"""Bank-feed API and persistence checks; no live credentials or bank calls."""
import io
import json
import time
import unittest
from datetime import date
from unittest.mock import patch
from urllib.error import HTTPError
import test_app
from test_app import app, db
import pocketsmith as ps
from pocketsmith_client import Client, FeedError

TODAY = date.today().isoformat()
KEY = 'test-key-not-a-real-credential'


def purchase(tid=901, **updates):
    return dict(id=tid, date=TODAY, payee='PocketSmith cafe', amount=-12.50, status='posted', is_transfer=False, **updates)


class FakeClient:
    accounts = [dict(id=21, name='Everyday', currency_code='aud', institution={'title':'Test bank'})]
    transactions = []
    failure = False
    callback = None
    def __init__(self, key):
        if key != KEY:
            raise FeedError('PocketSmith access was denied. Check or replace your developer key.')
    def get(self, path):
        return {'id':11,'name':'Test person'}, {}
    def collection(self, path, params=None):
        if 'users' in path:
            return self.accounts
        if self.callback:
            self.callback()
        if self.failure:
            raise FeedError('PocketSmith is limiting requests.', 900)
        return self.transactions


class FeedTest(unittest.TestCase):
    call=test_app.AppTest.call
    login=test_app.AppTest.login
    expense=test_app.AppTest.expense
    def setUp(self):
        test_app.AppTest.setUp(self)
        FakeClient.accounts=[dict(id=21,name='Everyday',currency_code='aud',institution={'title':'Test bank'})]
        FakeClient.transactions=[purchase()]
        FakeClient.failure=False
        FakeClient.callback=None
        self.mock=patch.object(ps,'Client',FakeClient)
        self.mock.start()
        self.addCleanup(self.mock.stop)
    def connect(self, auto=False):
        r=self.call(self.owner,'pocketsmith',{'key':KEY})
        self.assertEqual(r.status_code,200,r.json)
        c=r.json
        self.fid=c['accounts'][0]['id']
        r=self.call(self.owner,'pocketsmith',{'version':c['version'],'start_date':TODAY,'auto_sync':auto,'accounts':[{'id':self.fid}]},'PUT')
        self.assertEqual(r.status_code,200,r.json)
        self.aid=r.json['accounts'][0]['local_account_id']
        return r.json
    def sync(self):
        with app.app_context():
            db().execute('UPDATE pocketsmith_connection SET last_attempt=0,retry_after=0');db().commit()
        return self.call(self.owner,'pocketsmith/sync',{})
    def ledger(self):
        return self.owner.get('/api/bank-transactions?state=all').json['items']
    def add(self,t,**kw):
        return self.expense(self.owner,date=t['date'],amount=str(-t['amount_cents']/100),account_id=self.aid,category='Other',bank_transaction_id=t['id'],bank_transaction_version=t['version'],**kw)
    def test_connection_secrets_permissions_and_csrf(self):
        c=self.connect()
        with app.app_context():
            stored=ps.connection()['key_encrypted']
            self.assertNotIn(KEY,stored)
            self.assertEqual(ps.key_for(ps.connection()),KEY)
        for response in (c,self.owner.get('/api/audit').json,self.owner.get('/api/pocketsmith').json):
            self.assertNotIn(KEY,json.dumps(response));self.assertNotIn(stored,json.dumps(response))
        self.assertEqual(self.owner.post('/api/pocketsmith/sync',json={}).status_code,403)
        self.assertEqual(self.agent.get('/api/pocketsmith').status_code,403)
        self.assertEqual(self.call(self.agent,'pocketsmith/sync',{}).status_code,403)
        self.assertEqual(self.agent.get('/api/bank-transactions').status_code,200)
        self.assertEqual(app.test_client().get('/api/bank-transactions').status_code,401)
        self.assertEqual(self.call(self.owner,'pocketsmith',{'key':'bad-key-invalid'}).status_code,400)
        self.assertTrue(self.owner.get('/api/pocketsmith').json['connected'])
    def test_sync_idempotent_create_link_delete_tombstone(self):
        self.connect();self.assertEqual(self.sync().json,{'added':1,'received':1})
        t=self.ledger()[0];r=self.add(t);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.add(t).status_code,409)
        self.assertEqual(self.sync().json['added'],0)
        self.assertEqual(len(self.owner.get('/api/expenses').json),1)
        self.assertEqual(self.ledger()[0]['expense_id'],r.json['id'])
        self.call(self.owner,'expenses/'+str(r.json['id']),{},'DELETE')
        self.sync();self.assertEqual(self.ledger()[0]['state'],'ignored')
        self.assertEqual(self.owner.get('/api/expenses').json,[])
    def test_pending_replaced_and_transfer_never_create(self):
        self.connect();FakeClient.transactions=[{**purchase(), 'status':'pending'}, {**purchase(902),'is_transfer':True}]
        self.sync()
        for t in self.ledger():self.assertEqual(self.add(t).status_code,409)
        FakeClient.transactions=[purchase(903)]
        self.sync();records=self.ledger()
        self.assertEqual(sum(t['missing'] for t in records),2)
        self.assertEqual(len(self.owner.get('/api/bank-transactions').json['items']),1)
        self.assertEqual(len(self.owner.get('/api/expenses').json),0)
    def test_match_receipt_or_csv_and_prevent_duplicate(self):
        self.connect();self.sync();t=self.ledger()[0]
        eid=self.expense(self.owner,date=TODAY,amount='12.50',account_id=self.aid,merchant='Receipt purchase').json['id']
        candidates=self.owner.get('/api/bank-transactions/'+str(t['id'])).json['matches']
        self.assertEqual([e['id'] for e in candidates],[eid])
        self.assertEqual(self.add(t).status_code,409)
        self.assertEqual(len(self.owner.get('/api/expenses').json),1)
        r=self.call(self.owner,'bank-transactions/'+str(t['id']),{'version':t['version'],'action':'link','expense_id':eid})
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.ledger()[0]['expense_id'],eid)
    def test_source_change_preserves_expense_and_rejects_stale_review(self):
        self.connect();self.sync();t=self.ledger()[0];eid=self.add(t).json['id']
        FakeClient.transactions=[{**purchase(),'amount':-19}]
        self.sync();changed=self.ledger()[0]
        self.assertEqual(changed['changed'],1)
        self.assertEqual(self.owner.get('/api/expenses').json[0]['amount_cents'],1250)
        self.assertEqual(self.call(self.owner,'bank-transactions/'+str(t['id']),{'version':t['version'],'action':'unlink'}).status_code,409)
        FakeClient.transactions=[];self.sync()
        self.assertEqual(self.ledger()[0]['missing'],1)
        self.assertEqual(self.ledger()[0]['expense_id'],eid)
    def test_sync_atomic_failure_and_retry_delay(self):
        self.connect();self.sync();before=self.ledger()
        FakeClient.transactions=[purchase(902),{**purchase(903),'amount':'NaN'}]
        self.assertEqual(self.sync().status_code,400)
        self.assertEqual(self.ledger(),before)
        FakeClient.failure=True
        self.assertEqual(self.sync().status_code,400)
        c=self.owner.get('/api/pocketsmith').json
        self.assertGreater(c['retry_after'],time.time()+850)
        FakeClient.failure=False
        self.assertEqual(self.call(self.owner,'pocketsmith/sync',{}).status_code,400)
        self.assertEqual(self.ledger(),before)
    def test_disconnect_fences_inflight_sync_and_preserves_history(self):
        self.connect();self.sync();before=self.ledger()
        def disconnect(_client):
            db().execute("UPDATE pocketsmith_connection SET key_encrypted='',auto_sync=0,version=version+1,lock_token='',lock_until=0");db().commit()
        FakeClient.callback=disconnect
        FakeClient.transactions=[purchase(902)]
        self.assertEqual(self.sync().status_code,400)
        self.assertEqual(self.ledger(),before)
        self.assertFalse(self.owner.get('/api/pocketsmith').json['connected'])
    def test_refunds_and_foreign_currency_require_explicit_review(self):
        self.connect();FakeClient.transactions=[{**purchase(),'amount':12.5}];self.sync();t=self.ledger()[0]
        self.assertEqual(self.add(t).status_code,400)
        self.assertEqual(self.add(t,bank_confirm_refund=True).status_code,200)
        with app.app_context():
            db().execute("UPDATE pocketsmith_accounts SET currency='USD'");db().commit()
        FakeClient.transactions=[purchase(902)];self.sync();t=next(x for x in self.ledger() if x['remote_id']=='902')
        r=self.expense(self.owner,date=TODAY,amount='20',account_id=self.aid,category='Other',bank_transaction_id=t['id'],bank_transaction_version=t['version'])
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.owner.get('/api/expenses').json[0]['amount_cents'],2000)
    def test_scheduled_sync_and_lock(self):
        self.connect(auto=True)
        with app.app_context():
            self.assertEqual(ps.sync()['added'],1)
            self.assertIsNone(ps.sync())
            db().execute('UPDATE pocketsmith_connection SET next_sync=0,last_attempt=0,lock_until=?',(time.time()+100,));db().commit()
            self.assertIsNone(ps.sync())
        self.assertEqual(len(self.ledger()),1)
    def test_read_write_agent_review_but_not_credentials(self):
        self.connect();self.sync();t=self.ledger()[0]
        with app.app_context():
            db().execute("UPDATE users SET permission='read_write' WHERE email='staff@example.test'");db().commit()
        data={'version':t['version'],'action':'ignore'}
        self.assertEqual(self.call(self.agent,'bank-transactions/'+str(t['id']),data).status_code,403)
        self.assertEqual(self.call(self.staff,'bank-transactions/'+str(t['id']),data).status_code,200)
        self.assertEqual(self.call(self.staff,'pocketsmith/sync',{}).status_code,403)
        self.assertEqual(self.staff.get('/api/pocketsmith').status_code,403)
    def test_duplicate_ids_and_invalid_mapping_atomic(self):
        c=self.connect();FakeClient.transactions=[purchase(),purchase()]
        self.assertEqual(self.sync().status_code,400)
        self.assertEqual(self.ledger(),[])
        before=self.owner.get('/api/pocketsmith').json
        r=self.call(self.owner,'pocketsmith',{'version':c['version'],'start_date':TODAY,'accounts':[{'id':self.fid},{'id':self.fid}]},'PUT')
        self.assertEqual(r.status_code,400)
        self.assertEqual(self.owner.get('/api/pocketsmith').json['accounts'],before['accounts'])
        FakeClient.transactions=[{**purchase(), 'transaction_account':{'id':21,'currency_code':'USD'}}]
        self.assertEqual(self.sync().status_code,400)
        self.assertEqual(self.ledger(),[])


class ClientTest(unittest.TestCase):
    def test_pagination_uses_same_path_and_original_filters(self):
        client=Client(KEY)
        link='<https://api.pocketsmith.com/v2/transaction_accounts/21/transactions?page=2>; rel="next"'
        with patch.object(client,'get',side_effect=[([{'id':1}],{'Link':link}),([{'id':2}],{})]) as get:
            self.assertEqual(client.collection('/transaction_accounts/21/transactions',{'start_date':TODAY,'end_date':TODAY}),[{'id':1},{'id':2}])
            self.assertEqual(get.call_args.args[1]['page'],2)
            self.assertEqual(get.call_args.args[1]['start_date'],TODAY)
    def test_hostile_pagination_never_receives_key(self):
        for url in ['https://evil.test/v2/transaction_accounts/21/transactions?page=2','https://api.pocketsmith.com/v2/me?page=2','https://api.pocketsmith.com/v2/transaction_accounts/21/transactions?page=1']:
            client=Client(KEY)
            with patch.object(client,'get',return_value=([{'id':1}],{'Link':f'<{url}>; rel="next"'})) as get:
                with self.assertRaises(FeedError):client.collection('/transaction_accounts/21/transactions')
                self.assertEqual(get.call_count,1)
    def test_errors_never_include_upstream_body_or_key(self):
        for code in [301,401,403,429,500]:
            client=Client(KEY)
            with patch.object(client.opener,'open',side_effect=HTTPError('https://api.pocketsmith.com',code,KEY,{'Retry-After':'600'},io.BytesIO(KEY.encode()))):
                with self.assertRaises(FeedError) as caught:client.get('/me')
                self.assertNotIn(KEY,str(caught.exception))
                if code==429:self.assertEqual(caught.exception.retry_seconds,600)
    def test_auth_header_and_redirect_handler(self):
        from pocketsmith_client import NoRedirect
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://evil.test'))
        client=Client(KEY)
        response=unittest.mock.MagicMock();response.__enter__.return_value=response;response.read.return_value=b'{"id":11}';response.headers={}
        with patch.object(client.opener,'open',return_value=response) as opened:
            self.assertEqual(client.get('/me')[0],{'id':11})
            req=opened.call_args.args[0]
            self.assertEqual(req.full_url,'https://api.pocketsmith.com/v2/me')
            self.assertEqual(req.get_method(),'GET')
            self.assertEqual(req.get_header('X-developer-key'),KEY)
    def test_incomplete_collection_rejected(self):
        client=Client(KEY)
        with patch.object(client,'get',side_effect=[([{'id':1}],{'Total':'2'}),([],{'Total':'2'})]):
            with self.assertRaises(FeedError):client.collection('/users/11/transaction_accounts')
