"""Reviewed routes survive uploads; retry receipts cannot duplicate or resurrect trips."""
import copy
import unittest
import uuid
import test_app as base
from app import app, db

class JourneyRoutesTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login

    def payload(self):
        vid=self.call(self.owner,'vehicles',dict(name='Car')).json['id']
        a=dict(latitude=-27.47,longitude=153.02);b=dict(latitude=-27.471,longitude=153.021)
        place=dict(name='Home',address='Test address',point=a)
        route=dict(version=1,recorded=[[a,b],[b]],planned=[dict(id=str(uuid.uuid4()),name='Correction',**{'from':place,'to':place},points=[a,b],metres=200,seconds=30)],start=a,finish=b,interrupted=True)
        return dict(vehicle_id=vid,date='2026-10-10',origin='Home',destination='Work',purpose='',scope='personal',distance='1.234',client_ref=str(uuid.uuid4()),route=route)

    def test_route_roundtrip_permissions_and_lightweight_list(self):
        data=self.payload();result=self.call(self.owner,'vehicle-journeys',data)
        self.assertEqual(result.status_code,200,result.json)
        self.assertTrue(result.json['route_saved']);self.assertEqual(result.json['client_ref'],data['client_ref'])
        path='/api/vehicle-journeys/'+str(result.json['id'])
        self.assertEqual(self.owner.get(path).json['route'],data['route'])
        row=self.owner.get('/api/vehicle-journeys').json[0]
        self.assertTrue(row['has_route']);self.assertNotIn('route_json',row);self.assertNotIn('route',row)
        self.assertEqual(self.agent.get(path).status_code,403)
        self.assertEqual(app.test_client().get(path).status_code,401)
        self.assertEqual(self.call(self.agent,path[5:],{},'DELETE').status_code,403)
        # An ordinary web edit does not discard the phone's uploaded geometry.
        update={k:v for k,v in data.items() if k!='route'};update['origin']='Updated start'
        self.assertEqual(self.call(self.owner,path[5:],update,'PUT').status_code,200)
        self.assertEqual(self.owner.get(path).json['route'],data['route'])
        self.assertEqual(self.call(self.owner,'vehicle-journeys',data).status_code,409)

    def test_exact_retry_and_delete_tombstone(self):
        data=self.payload();a=self.call(self.owner,'vehicle-journeys',data)
        self.assertEqual(self.call(self.owner,'vehicle-journeys',data).json,a.json)
        self.assertEqual(len(self.owner.get('/api/vehicle-journeys').json),1)
        changed=copy.deepcopy(data);changed['route']['recorded'][0][0]['latitude']=-28
        self.assertEqual(self.call(self.owner,'vehicle-journeys',changed).status_code,409)
        self.assertEqual(self.call(self.owner,'vehicle-journeys/'+str(a.json['id']),{},'DELETE').status_code,200)
        self.assertEqual(self.call(self.owner,'vehicle-journeys',data).status_code,409)
        self.assertEqual(self.owner.get('/api/vehicle-journeys').json,[])

    def test_legacy_delete_also_blocks_delayed_retry(self):
        data=self.payload();data.pop('route');a=self.call(self.owner,'vehicle-journeys',data)
        self.assertFalse(a.json['route_saved'])
        with app.app_context(): db().execute('DELETE FROM journey_upload_receipts');db().commit()
        self.call(self.owner,'vehicle-journeys/'+str(a.json['id']),{},'DELETE')
        self.assertEqual(self.call(self.owner,'vehicle-journeys',data).status_code,409)

    def test_invalid_routes_never_create_a_journey(self):
        original=self.payload()
        bad=[None, True, 91, float('inf')]
        for latitude in bad:
            data=copy.deepcopy(original);data['route']['recorded'][0][0]['latitude']=latitude
            self.assertEqual(self.call(self.owner,'vehicle-journeys',data).status_code,400)
        for route in [{}, {'version':True,'recorded':[],'planned':[],'interrupted':False},dict(original['route'],secret='unexpected'),dict(original['route'],recorded=[[]]),dict(original['route'],planned=[{}]),dict(original['route'],recorded=[[dict(latitude=0,longitude=0)]*100001])]:
            self.assertEqual(self.call(self.owner,'vehicle-journeys',dict(original,route=route)).status_code,400)
        self.assertEqual(self.owner.get('/api/vehicle-journeys').json,[])

    def test_categories_sorted_across_builtin_and_custom(self):
        for name in ['zebra','aaa custom','Mixed case']:
            self.assertEqual(self.call(self.owner,'categories',{'name':name}).status_code,200)
        cats=self.owner.get('/api/categories').json
        self.assertEqual(cats,sorted(cats,key=lambda name:(name.casefold(),name)))
        self.assertEqual(self.owner.get('/api/session').json['categories'],cats)
        self.assertTrue(self.owner.get('/api/session').json['capabilities']['journey_routes'])
