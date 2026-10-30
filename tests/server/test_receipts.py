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
        with patch.dict(os.environ,{'OLLAMA_URL':'http://ollama.example.test:11434','OLLAMA_MODEL':'vision-test'}),patch('ai_providers.urllib.request.OpenerDirector.open',return_value=response):
            return self.call(self.owner,'receipts/'+rid+'/extract',{})

    def test_capture_is_persistent_without_creating_expense(self):
        rid=self.upload().json['id']
        self.assertEqual(self.owner.get('/api/expenses').json,[])
        row=self.owner.get('/api/receipts').json[0]
        self.assertEqual(row['id'],rid);self.assertEqual(row['scan_status'],'captured')
        self.assertIsNone(row['expense_id'])
        self.assertEqual(self.agent.get('/api/receipts').status_code,403)

    def test_duplicate_upload_same_user_only(self):
        first=self.upload().json;second=self.upload().json
        self.assertEqual(first['id'],second['id']);self.assertTrue(second['duplicate'])
        self.assertEqual(self.upload(self.staff).status_code,403)

    def test_receipts_are_isolated_and_owner_can_file_staff_receipt(self):
        rid=self.upload(self.owner).json['id']
        self.assertEqual(self.staff2.get('/api/receipts').status_code,401)
        self.assertEqual(self.call(self.staff2,'receipts/'+rid+'/expense',{}).status_code,401)
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
        with patch.dict(os.environ,{'OLLAMA_URL':'http://ollama.example.test','OLLAMA_MODEL':'vision'}),patch('ai_providers.urllib.request.OpenerDirector.open',side_effect=TimeoutError):
            self.assertEqual(self.call(self.owner,'receipts/'+rid+'/extract',{}).status_code,502)
        self.assertEqual(self.owner.get('/api/receipts').json[0]['scan_status'],'failed')
        self.assertEqual(self.owner.get('/api/receipts/'+rid).status_code,200)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/expense',dict(date='2026-10-08',merchant='Cafe',amount=10,scope='work',category='Other',percent=0)).status_code,200)

    def test_suggestions_use_reviewed_history_for_same_person(self):
        self.expense(self.owner,merchant='Cafe',status='ready',category='Meals',scope='work')
        self.expense(self.owner,merchant='Cafe',category='Other',status='review')
        self.assertEqual(self.expense(self.staff,merchant='Cafe',category='Subscriptions',status='ready').status_code,403)
        rid=self.upload().json['id'];self.scan(rid,dict(merchant='Cafe',date='2026-10-08',amount=23.45,currency='AUD',currency_evidence='AUD',category='Other'))
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

    def test_draft_inbox_excludes_accepted_receipts_and_keeps_expense_access(self):
        rid=self.upload().json['id'];pending=self.upload(color='blue').json['id']
        eid=self.expense(self.owner,category='Equipment').json['id']
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/expense',{'existing_expense_id':eid}).status_code,200)
        self.assertEqual([r['id'] for r in self.owner.get('/api/receipts?unfiled=1').json],[pending])
        self.assertEqual(len(self.owner.get('/api/receipts').json),2)
        expense=next(e for e in self.owner.get('/api/expenses').json if e['id']==eid)
        self.assertEqual(expense['receipt_id'],rid)
        self.assertEqual(self.owner.get('/api/receipts/'+rid+'/info').status_code,200)

    def test_filing_preserves_reviewed_location_and_original_address(self):
        rid=self.upload().json['id'];address='Example Street, Richmond NSW 2753'
        self.scan(rid,dict(merchant='Shop',date='2026-10-08',amount=20,currency='AUD',category='Equipment',merchant_city='Richmond',merchant_address=address))
        response=self.call(self.owner,'receipts/'+rid+'/expense',dict(merchant='Shop',date='2026-10-08',amount=20,scope='work',category='Equipment',merchant_location='Richmond, QLD 4822'))
        self.assertEqual(response.status_code,200,response.json)
        row=self.owner.get('/api/receipts').json[0]
        self.assertEqual(row['location'],'Richmond, QLD 4822')
        self.assertEqual(row['extraction']['merchant_address'],address)

    def test_match_uses_corrected_draft_amount_and_retains_already_attached_candidate(self):
        rid=self.upload().json['id'];attached=self.upload(color='red').json['id']
        first=self.expense(self.owner,category='Equipment',date='2026-10-08',amount=21.43,receipt_id=attached).json['id']
        second=self.expense(self.owner,category='Equipment',date='2026-10-08',amount=21.43).json['id']
        self.scan(rid,dict(merchant='Cafe',date='2026-10-09',amount=20.25,currency='AUD',category='Equipment'))
        self.call(self.owner,'receipts/'+rid+'/draft',{'date':'2026-10-08','amount':21.43},'PUT')
        row=next(r for r in self.owner.get('/api/receipts?unfiled=1').json if r['id']==rid)
        self.assertEqual({e['id'] for e in row['matches']},{first,second})
        self.assertEqual(next(e for e in row['matches'] if e['id']==first)['receipt_id'],attached)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/expense',{'existing_expense_id':first}).status_code,409)

    def test_delete_unfiled_and_readonly_cannot_delete(self):
        rid=self.upload().json['id']
        self.assertEqual(self.call(self.staff,'receipts/'+rid,{},'DELETE').status_code,403)
        self.assertEqual(self.call(self.owner,'receipts/'+rid,{},'DELETE').status_code,200)
        self.assertEqual(self.owner.get('/api/receipts/'+rid).status_code,404)

    def test_manual_currency_survives_rescan_and_does_not_convert_amount(self):
        rid=self.upload().json['id']
        self.scan(rid,dict(merchant='Cafe',amount=25,currency='USD',currency_evidence='USD'))
        response=self.call(self.owner,'receipts/'+rid+'/currency',{'currency':'aud'},'PUT')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['extraction']['currency'],'AUD')
        self.assertEqual(response.json['extraction']['amount'],25)
        self.assertEqual(self.owner.get('/api/expenses').json,[])
        self.scan(rid,dict(merchant='Cafe',amount=25,currency='USD',currency_evidence='USD'))
        extracted=self.owner.get('/api/receipts').json[0]['extraction']
        self.assertEqual(extracted['currency'],'AUD');self.assertEqual(extracted['currency_status'],'confirmed')
        self.assertEqual(self.call(self.agent,'receipts/'+rid+'/currency',{'currency':'USD'},'PUT').status_code,403)
        self.assertEqual(self.call(self.staff,'receipts/'+rid+'/currency',{'currency':'USD'},'PUT').status_code,403)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/currency',{'currency':'dollars'},'PUT').status_code,400)
        eid=self.call(self.owner,'receipts/'+rid+'/expense',dict(date='2026-10-08',merchant='Cafe',amount=25,scope='work',category='Other',percent=100)).json['id']
        self.call(self.owner,'receipts/'+rid+'/currency',{'currency':'USD'},'PUT')
        self.assertEqual(next(e for e in self.owner.get('/api/expenses').json if e['id']==eid)['amount_cents'],2500)

    def test_pdf_thumbnail_cache_still_enforces_receipt_access(self):
        from pypdf import PdfWriter
        from app import DATA
        pdf=PdfWriter();pdf.add_blank_page(width=200,height=300);buf=io.BytesIO();pdf.write(buf);buf.seek(0)
        rid=self.owner.post('/api/receipts',data={'file':(buf,'receipt.pdf')},headers={'X-CSRF-Token':self.owner.get('/api/session').json['csrf']}).json['id']
        route='/api/receipts/'+rid+'/preview?page=1&thumbnail=1'
        response=self.owner.get(route);self.assertEqual(response.status_code,200)
        im=Image.open(io.BytesIO(response.data));self.assertLessEqual(max(im.size),420)
        with patch('app.subprocess.run',side_effect=AssertionError('Cached thumbnail must not re-render')):
            self.assertEqual(self.owner.get(route).data,response.data)
            self.assertEqual(self.agent.get(route).status_code,403)
            self.assertEqual(self.staff2.get(route).status_code,401)
            self.assertEqual(app.test_client().get(route).status_code,401)
        self.assertTrue((DATA/'receipt_previews'/(rid+'-thumb-v1.png')).exists())
        self.call(self.owner,'receipts/'+rid,{},'DELETE')
        self.assertFalse((DATA/'receipt_previews'/(rid+'-thumb-v1.png')).exists())
