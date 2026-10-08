"""Receipt inbox regression tests. Ollama is mocked; no external data is sent."""
import io
import json
import os
import unittest
from unittest.mock import patch, MagicMock
from PIL import Image
import test_app as base
from app import app, db

class ReceiptTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login
    expense=base.AppTest.expense

    def upload(self,client=None,color='white'):
        client=client or self.owner
        buf=io.BytesIO();Image.new('RGB',(40,40),color).save(buf,'PNG');buf.seek(0)
        return client.post('/api/receipts',data={'file':(buf,'receipt.png')},headers={'X-CSRF-Token':client.get('/api/session').json['csrf']})

    def scan(self,rid,result):
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps({'message':{'content':json.dumps(result)}}).encode()
        with patch.dict(os.environ,{'OLLAMA_URL':'http://ollama.example.test:11434','OLLAMA_MODEL':'vision-test'}),patch('app.urllib.request.urlopen',return_value=response):
            return self.call(self.owner,'receipts/'+rid+'/extract',{})

    def test_capture_is_persistent_without_creating_expense(self):
        rid=self.upload().json['id']
        self.assertEqual(self.owner.get('/api/expenses').json,[])
        row=self.owner.get('/api/receipts').json[0]
        self.assertEqual(row['id'],rid);self.assertEqual(row['scan_status'],'captured')
        self.assertIsNone(row['expense_id'])
        self.assertEqual(self.agent.get('/api/receipts').status_code,200)

    def test_duplicate_upload_same_user_only(self):
        first=self.upload().json;second=self.upload().json
        self.assertEqual(first['id'],second['id']);self.assertTrue(second['duplicate'])
        self.assertNotEqual(self.upload(self.staff).json['id'],first['id'])

    def test_receipts_are_isolated_and_owner_can_file_staff_receipt(self):
        rid=self.upload(self.staff).json['id']
        self.assertEqual(self.staff2.get('/api/receipts').json,[])
        self.assertEqual(self.call(self.staff2,'receipts/'+rid+'/expense',{}).status_code,403)
        payload=dict(date='2026-10-08',merchant='Cafe',amount=25,scope='business',category='Meals',percent=100)
        result=self.call(self.owner,'receipts/'+rid+'/expense',payload)
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(len(self.staff.get('/api/expenses').json),1)
        self.assertEqual(len(self.agent.get('/api/expenses').json),1)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/expense',payload).status_code,409)

    def test_ai_result_survives_refresh_and_bad_values_are_not_trusted(self):
        rid=self.upload().json['id']
        result=self.scan(rid,dict(merchant='Cafe',date='not-a-date',amount='NaN',currency='USD',category='Made up',notes='Check purpose'))
        self.assertEqual(result.status_code,200,result.json)
        row=self.owner.get('/api/receipts').json[0]
        self.assertEqual(row['scan_status'],'scanned')
        self.assertEqual(row['extraction']['merchant'],'Cafe')
        self.assertIsNone(row['extraction']['amount']);self.assertIsNone(row['extraction']['date'])
        self.assertEqual(row['extraction']['category'],'Uncategorised')
        self.assertEqual(self.owner.get('/api/expenses').json,[])

    def test_ai_failure_keeps_original_and_supports_manual_entry(self):
        rid=self.upload().json['id']
        with patch.dict(os.environ,{'OLLAMA_URL':'http://ollama.example.test','OLLAMA_MODEL':'vision'}),patch('app.urllib.request.urlopen',side_effect=TimeoutError):
            self.assertEqual(self.call(self.owner,'receipts/'+rid+'/extract',{}).status_code,502)
        self.assertEqual(self.owner.get('/api/receipts').json[0]['scan_status'],'failed')
        self.assertEqual(self.owner.get('/api/receipts/'+rid).status_code,200)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/expense',dict(date='2026-10-08',merchant='Cafe',amount=10,scope='work',category='Other',percent=0)).status_code,200)

    def test_suggestions_use_reviewed_history_for_same_person(self):
        self.expense(self.owner,merchant='Cafe',status='ready',category='Meals',scope='work')
        self.expense(self.owner,merchant='Cafe',category='Other',status='review')
        self.expense(self.staff,merchant='Cafe',category='Subscriptions',status='ready')
        rid=self.upload().json['id'];self.scan(rid,dict(merchant='Cafe',date='2026-10-08',amount=23.45,currency='AUD',category='Other'))
        row=next(r for r in self.owner.get('/api/receipts').json if r['id']==rid)
        self.assertEqual(row['suggestion'],{'category':'Meals','scope':'work'})
        self.assertEqual(len(row['matches']),2)
        self.assertTrue(all(x['merchant']=='Cafe' for x in row['matches']))

    def test_matching_transaction_links_once_without_new_expense(self):
        eid=self.expense(self.owner).json['id'];rid=self.upload().json['id']
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/expense',{'existing_expense_id':eid}).status_code,200)
        self.assertEqual(len(self.owner.get('/api/expenses').json),1)
        self.assertEqual(self.owner.get('/api/expenses').json[0]['receipt_id'],rid)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/expense',{'existing_expense_id':eid}).status_code,409)
        self.assertEqual(self.call(self.owner,'receipts/'+rid,{},'DELETE').status_code,409)

    def test_delete_unfiled_and_no_cross_user_match(self):
        eid=self.expense(self.staff).json['id'];rid=self.upload().json['id']
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/expense',{'existing_expense_id':eid}).status_code,409)
        self.assertEqual(self.call(self.staff,'receipts/'+rid,{},'DELETE').status_code,403)
        self.assertEqual(self.call(self.owner,'receipts/'+rid,{},'DELETE').status_code,200)
        self.assertEqual(self.owner.get('/api/receipts/'+rid).status_code,404)
