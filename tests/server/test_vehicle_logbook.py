"""Actual baselines, personal kilometres, correction/delete recalculation and upload replay."""
import unittest
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import test_app as base
from app import app

class VehicleLogbookTest(unittest.TestCase):
    setUp=base.AppTest.setUp
    call=base.AppTest.call
    login=base.AppTest.login

    def prepare(self):
        self.vid=self.call(self.owner,'vehicles',dict(name='Kia Cerato')).json['id']
        self.path=f'vehicles/{self.vid}/odometer'
        self.when=datetime.now(ZoneInfo('Australia/Brisbane')).replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=3)
        self.start=self.when.timestamp()
        result=self.call(self.owner,self.path,dict(recorded_at=self.start,reading='52000'))
        self.assertEqual(result.status_code,200,result.json)
        return result.json

    def journey(self, **overrides):
        data=dict(vehicle_id=self.vid,date=self.when.date().isoformat(),origin='Home',destination='Airport',purpose='Travel',scope='business',percent=50,distance='28.6',started_at=self.start+100,ended_at=self.start+200,client_ref=str(uuid.uuid4()))
        data.update(overrides)
        return data

    def get(self): return self.owner.get('/api/'+self.path).json

    def test_full_distance_deduplication_edits_and_deletion(self):
        self.prepare();data=self.journey(scope='personal')
        a=self.call(self.owner,'vehicle-journeys',data);self.assertEqual(a.status_code,200,a.json)
        b=self.call(self.owner,'vehicle-journeys',data);self.assertEqual(a.json,b.json)
        self.assertEqual(self.get()['estimate_m'],52028600)
        self.assertEqual(len(self.get()['journeys']),1)
        self.assertEqual(self.call(self.owner,'vehicle-journeys',{**data,'distance':'30'}).status_code,409)
        self.assertEqual(self.call(self.owner,'vehicle-journeys/'+str(a.json['id']),{**data,'distance':'30'},'PUT').status_code,200)
        self.assertEqual(self.get()['estimate_m'],52030000)
        self.assertEqual(self.owner.get('/api/vehicles').json[0]['odometer_estimate_m'],52030000)
        self.call(self.owner,'vehicle-journeys/'+str(a.json['id']),{},'DELETE')
        self.assertEqual(self.get()['estimate_m'],52000000)

    def test_new_actual_reading_reconciles_preserves_history_and_supports_backdating(self):
        self.prepare();original=self.journey();a=self.call(self.owner,'vehicle-journeys',original)
        second=self.call(self.owner,self.path,dict(recorded_at=self.start+300,reading='52030',notes='Dashboard'))
        self.assertEqual(second.status_code,200,second.json)
        self.assertEqual(second.json['estimate_m'],52030000)
        self.assertEqual(second.json['readings'][-1]['difference_m'],1400)
        self.call(self.owner,'vehicle-journeys',self.journey(started_at=self.start+400,ended_at=self.start+600,distance='12'))
        self.assertEqual(self.get()['estimate_m'],52042000)
        # Historical correction changes the reconciliation difference, not the actual baseline.
        self.call(self.owner,'vehicle-journeys/'+str(a.json['id']),{**original,'distance':'29'},'PUT')
        self.assertEqual(self.get()['estimate_m'],52042000)
        self.assertEqual(self.get()['readings'][-1]['difference_m'],1000)
        old=self.get()['readings'][-1]
        self.assertEqual(self.call(self.owner,self.path+'/'+str(old['id']),dict(version=old['version'],recorded_at=self.start+300,reading='52031'),'PUT').status_code,200)
        self.assertEqual(self.get()['estimate_m'],52043000)
        self.assertEqual(self.call(self.owner,self.path+'/'+str(old['id']),dict(version=old['version']),'DELETE').status_code,409)
        self.assertEqual(self.call(self.owner,self.path+'/'+str(old['id']),dict(version=old['version']+1),'DELETE').status_code,200)
        self.assertEqual(self.get()['estimate_m'],52041000)

    def test_unknown_times_and_crossing_trips_are_not_guessed(self):
        self.prepare()
        self.call(self.owner,'vehicle-journeys',self.journey(started_at=None,ended_at=None,client_ref=None))
        self.assertEqual((self.get()['estimate_m'],self.get()['ambiguous_trips']),(52000000,1))
        self.call(self.owner,'vehicle-journeys',self.journey(date=(self.when+timedelta(days=1)).date().isoformat(),started_at=None,ended_at=None,client_ref=None,distance='10'))
        self.assertEqual(self.get()['estimate_m'],52010000)
        self.call(self.owner,'vehicle-journeys',self.journey(started_at=self.start-100,ended_at=self.start+100))
        self.assertEqual(self.get()['ambiguous_trips'],2)

    def test_trip_crossing_midnight_keeps_its_departure_date(self):
        self.prepare()
        result=self.call(self.owner,'vehicle-journeys',self.journey(started_at=self.start+23*3600,ended_at=self.start+25*3600))
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.get()['estimate_m'],52028600)

    def test_permissions_invalid_readings_and_vehicle_isolation(self):
        self.prepare()
        self.assertEqual(app.test_client().get('/api/'+self.path).status_code,401)
        self.assertEqual(self.agent.get('/api/'+self.path).status_code,403)
        self.assertEqual(self.call(self.agent,self.path,dict(recorded_at=self.start+1,reading='52001')).status_code,403)
        for data in [dict(recorded_at=True,reading='1'),dict(recorded_at=self.start+1,reading='-1'),dict(recorded_at=self.start+1,reading='nan'),dict(recorded_at=self.start+1,reading='51999'),dict(recorded_at=self.start+1,reading=''),dict(recorded_at=self.start-1,reading='53000')]:
            self.assertEqual(self.call(self.owner,self.path,data).status_code,400,data)
        self.assertEqual(self.call(self.owner,self.path,dict(recorded_at=self.start,reading='52000')).status_code,409)
        other=self.call(self.owner,'vehicles',dict(name='Other vehicle')).json['id']
        self.assertIsNone(self.owner.get(f'/api/vehicles/{other}/odometer').json['estimate_m'])
        self.assertEqual(self.call(self.owner,f'vehicles/{other}/odometer/1',dict(version=1),'DELETE').status_code,404)
        self.assertEqual(self.call(self.owner,f'vehicles/{self.vid}',{},'DELETE').status_code,409)
        self.assertEqual(self.call(self.owner,'vehicle-journeys',self.journey(ended_at=self.start-1)).status_code,400)
        self.assertEqual(self.call(self.owner,'vehicle-journeys',self.journey(client_ref='bad')).status_code,400)
