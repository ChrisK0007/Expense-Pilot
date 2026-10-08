"""Record integrity and permissions for categories, vehicles and receipt sorting."""
import csv
import io
import unittest
import test_app as base
import test_receipts as receipt_tests
from app import app, db

class TrackingTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login
    expense=base.AppTest.expense
    upload=receipt_tests.ReceiptTest.upload
    scan=receipt_tests.ReceiptTest.scan

    def prefs(self,client=None):
        r=self.call(client or self.owner,'receipt-preferences',dict(home_base='Sunshine Coast',home_aliases='Maroochydore, Caloundra',scope='business'),'PUT')
        self.assertEqual(r.status_code,200,r.json)

    def meal(self,color,when='2026-10-08',city='Cairns',amount=35,client=None):
        rid=self.upload(client,color).json['id']
        result=self.scan(rid,dict(merchant='Cafe '+color,date=when,amount=amount,category='Meals',meal='Dinner',merchant_city=city))
        self.assertEqual(result.status_code,200,result.json)
        return rid

    def accept_data(self,group):
        return {k:group[k] for k in ('location','scope','start','end','existing_trip_id')} | dict(purpose='Flying duties',receipts=[dict(id=r['id'],merchant=r['values']['merchant'],date=r['values']['date'],amount=r['aud_amount'],meal='Dinner',percent=100) for r in group['receipts']])

    def test_categories_are_persistent_validated_and_permissioned(self):
        result=self.call(self.owner,'categories',{'name':'Flight test fees'})
        self.assertEqual(result.status_code,200);self.assertIn('Flight test fees',result.json)
        self.assertIn('Flight test fees',self.staff.get('/api/session').json['categories'])
        self.assertEqual(self.call(self.owner,'categories',{'name':'flight TEST fees'}).status_code,409)
        self.assertEqual(self.call(self.owner,'categories',{'name':'Meals'}).status_code,409)
        self.assertEqual(self.call(self.owner,'categories',{'name':''}).status_code,400)
        self.assertEqual(self.call(self.staff,'categories',{'name':'Staff category'}).status_code,403)
        self.assertEqual(self.call(self.agent,'categories',{'name':'Agent category'}).status_code,403)
        self.assertEqual(self.expense(self.owner,category='Flight test fees').status_code,200)
        self.assertEqual(self.expense(self.owner,category='Unknown category').status_code,400)

    def test_receipt_draft_keeps_manual_edits_and_filed_amount_is_current(self):
        rid=self.meal('white',amount=100)
        saved=self.call(self.owner,'receipts/'+rid+'/draft',dict(amount='179.99',category='Equipment',percent=0,notes='My correction'),'PUT')
        self.assertEqual(saved.status_code,200,saved.json)
        self.scan(rid,dict(merchant='New scan',date='2026-10-08',amount=100,category='Equipment'))
        row=self.owner.get('/api/receipts').json[0]
        self.assertEqual(row['draft']['amount'],179.99);self.assertEqual(row['draft']['percent'],0)
        self.assertEqual(self.owner.get('/api/expenses').json,[])
        result=self.call(self.owner,'receipts/'+rid+'/expense',dict(merchant='Corrected',date='2026-10-08',amount='179.99',category='Equipment',scope='business',status='ready'))
        self.assertEqual(result.status_code,200,result.json);eid=result.json['id']
        self.assertEqual(self.owner.get('/api/receipts').json[0]['saved_expense']['amount_cents'],17999)
        self.assertEqual(self.call(self.owner,'expenses/'+str(eid),dict(merchant='Corrected',date='2026-10-08',amount='189.99',category='Equipment',scope='business',status='ready',receipt_id=rid),'PUT').status_code,200)
        row=self.owner.get('/api/receipts').json[0]
        self.assertEqual(row['saved_expense']['amount_cents'],18999);self.assertEqual(row['extraction']['amount'],100)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/draft',{'amount':50},'PUT').status_code,409)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/extract',{'unfiled_only':True}).status_code,409)

    def test_partial_drafts_and_currency_override(self):
        rid=self.upload().json['id']
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/draft',{'merchant':'','date':'','amount':None,'percent':100},'PUT').status_code,200)
        self.assertEqual(self.call(self.owner,'receipts/'+rid+'/draft',{'percent':101},'PUT').status_code,400)
        self.assertEqual(self.call(self.staff,'receipts/'+rid+'/draft',{'amount':10},'PUT').status_code,403)
        self.call(self.owner,'receipts/'+rid+'/draft',{'currency':'USD'},'PUT')
        self.call(self.owner,'receipts/'+rid+'/currency',{'currency':'AUD'},'PUT')
        self.scan(rid,{'amount':25,'currency':'USD','currency_evidence':'USD'})
        row=self.owner.get('/api/receipts').json[0]
        self.assertEqual(row['extraction']['currency'],'AUD');self.assertEqual(row['draft']['currency'],'AUD')

    def test_grouping_requires_home_base_and_excludes_local_missing_and_personal(self):
        self.meal('red','2026-10-09');self.meal('blue','2026-10-07');self.meal('green','2026-10-08')
        self.assertEqual(self.owner.get('/api/receipt-trip-proposals').json,[])
        self.prefs();self.meal('yellow',city='Maroochydore');self.meal('purple',city='');personal=self.meal('orange',city='Sydney')
        self.call(self.owner,'receipts/'+personal+'/draft',{'scope':'personal'},'PUT')
        self.prefs(self.staff);staff=self.meal('black',client=self.staff)
        groups=self.owner.get('/api/receipt-trip-proposals').json
        self.assertEqual(len(groups),2)
        owner=next(g for g in groups if len(g['receipts'])==3)
        self.assertEqual((owner['start'],owner['end']),('2026-10-07','2026-10-09'))
        self.assertEqual(len(self.staff.get('/api/receipt-trip-proposals').json),1)
        self.assertEqual(self.staff2.get('/api/receipt-trip-proposals').json,[])
        self.assertEqual(self.owner.get('/api/trips').json,[]);self.assertEqual(self.owner.get('/api/expenses').json,[])
        self.assertEqual(self.call(self.staff,'receipt-trip-proposals/accept',self.accept_data(owner)).status_code,403)
        self.assertEqual(self.call(self.agent,'receipt-trip-proposals/accept',self.accept_data(owner)).status_code,403)

    def test_trip_acceptance_is_atomic_and_existing_trip_is_reused(self):
        self.prefs();self.meal('red','2026-10-08');self.meal('green','2026-10-09')
        group=self.owner.get('/api/receipt-trip-proposals').json[0];payload=self.accept_data(group)
        payload['receipts'][1]['date']='2026-10-15'
        self.assertEqual(self.call(self.owner,'receipt-trip-proposals/accept',payload).status_code,400)
        self.assertEqual(self.owner.get('/api/trips').json,[]);self.assertEqual(self.owner.get('/api/expenses').json,[])
        payload=self.accept_data(group);payload['receipts'][0]['amount']='179.99'
        accepted=self.call(self.owner,'receipt-trip-proposals/accept',payload)
        self.assertEqual(accepted.status_code,200,accepted.json)
        records=self.owner.get('/api/expenses').json
        self.assertEqual(sum(e['amount_cents'] for e in records),21499)
        self.assertTrue(all(e['status']=='ready' and e['percent']==100 for e in records))
        self.assertEqual(self.call(self.owner,'receipt-trip-proposals/accept',payload).status_code,409)
        self.meal('blue','2026-10-09')
        group=self.owner.get('/api/receipt-trip-proposals').json[0]
        self.assertEqual(group['existing_trip_id'],accepted.json['trip_id'])
        self.assertEqual(self.call(self.owner,'receipt-trip-proposals/accept',self.accept_data(group)).status_code,200)
        self.assertEqual(len(self.owner.get('/api/trips').json),1)
        self.assertEqual(len(self.owner.get('/api/expenses').json),3)

    def test_foreign_meal_amount_needs_manual_aud_and_dismissal_survives_scan(self):
        self.prefs();rid=self.upload().json['id']
        self.scan(rid,dict(merchant='Foreign cafe',date='2026-10-08',amount=100,currency_evidence='USD',category='Meals',merchant_city='New York',meal='Dinner'))
        group=self.owner.get('/api/receipt-trip-proposals').json[0]
        self.assertIsNone(group['receipts'][0]['aud_amount'])
        self.assertEqual(self.call(self.owner,'receipt-trip-proposals/accept',self.accept_data(group)).status_code,400)
        self.call(self.owner,'receipts/'+rid+'/draft',{'exclude_trip':True},'PUT')
        self.assertEqual(self.owner.get('/api/receipt-trip-proposals').json,[])
        self.assertEqual(len(self.owner.get('/api/receipts').json),1)

    def test_vehicle_journeys_cost_links_and_isolation(self):
        vid=self.call(self.owner,'vehicles',dict(name='Kia Cerato',registration='TEST123')).json['id']
        staffvid=self.call(self.staff,'vehicles',dict(name='Staff car')).json['id']
        self.assertEqual(len(self.owner.get('/api/vehicles').json),2)
        self.assertEqual(len(self.staff.get('/api/vehicles').json),1)
        d=dict(vehicle_id=vid,date='2026-10-08',origin='Home base',destination='Airport',purpose='Flight test',scope='business',odometer_start='50000',odometer_end='50062.5',percent=100)
        r=self.call(self.owner,'vehicle-journeys',d);self.assertEqual(r.status_code,200,r.json)
        row=self.owner.get('/api/vehicle-journeys').json[0];self.assertEqual(row['distance_m'],62500)
        self.assertEqual(self.call(self.staff,'vehicle-journeys',d).status_code,404)
        self.assertEqual(self.call(self.agent,'vehicle-journeys',d).status_code,403)
        self.assertEqual(self.call(self.owner,'vehicle-journeys',{**d,'odometer_end':'49999'}).status_code,400)
        self.assertEqual(self.call(self.owner,'vehicle-journeys',{**d,'odometer_end':''}).status_code,400)
        eid=self.expense(self.owner,vehicle_id=vid,category='Vehicle expenses',amount=80).json['id']
        self.assertEqual(self.owner.get('/api/expenses').json[0]['vehicle_id'],vid)
        self.assertEqual(self.expense(self.staff,vehicle_id=vid,category='Vehicle expenses').status_code,404)
        self.assertEqual(self.staff.get('/api/expenses').json,[])
        self.assertEqual(self.call(self.owner,'vehicles/'+str(vid),{},'DELETE').status_code,409)
        exported=list(csv.reader(io.StringIO(self.owner.get('/api/vehicle-journeys?format=csv').data.decode('utf-8-sig'))))
        self.assertEqual(exported[1][0],'08/10/2026');self.assertIn('62.5',exported[1])
        self.assertEqual(self.staff.get('/api/vehicle-journeys').json,[])
        self.assertEqual(len(self.agent.get('/api/vehicle-journeys').json),1)
