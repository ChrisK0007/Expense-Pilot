import csv
import io
import unittest
from datetime import timedelta
import test_app as base
import workspace_time


class FuelSourceTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login

    def test_sources_survive_save_reopen_update_and_csv_without_promotion(self):
        vid = self.call(self.owner, 'vehicles', {'name': 'Source test'}).json['id']
        day = workspace_time.today()
        saved = []
        for index, source in enumerate(('dashboard', 'estimated', 'unknown', 'dashboard')):
            payload = dict(date=(day - timedelta(days=4-index)).isoformat(), merchant='Fuel '+source+str(index),
                amount='50', scope='personal', category='Vehicle expenses', vehicle_id=vid,
                fuel_details={'litres': '25', 'odometer_km': str(1000+index*100), 'odometer_source': source, 'full_tank': True})
            result = self.call(self.owner, 'expenses', payload)
            self.assertEqual(result.status_code, 200, result.json)
            saved.append((result.json['id'], payload))
        rows = {r['id']: r for r in self.owner.get('/api/expenses').json}
        for eid, payload in saved:
            self.assertEqual(rows[eid]['fuel_odometer_source'], payload['fuel_details']['odometer_source'])
        eid, payload = saved[1]
        # An old client updating an unchanged number must not promote or lose its source.
        legacy = dict(payload, fuel_details={k:v for k,v in payload['fuel_details'].items() if k!='odometer_source'})
        self.assertEqual(self.call(self.owner, f'expenses/{eid}', legacy, 'PUT').status_code, 200)
        path = f'/api/vehicles/{vid}/running-costs'
        report = self.owner.get(path).json
        self.assertEqual(next(r for r in report['fuel'] if r['id']==eid)['odometer_source'], 'estimated')
        self.assertIsNone(report['litres_per_100_km'])
        exported = list(csv.DictReader(io.StringIO(self.owner.get(path+'.csv').data.decode('utf-8-sig'))))
        self.assertEqual(next(r for r in exported if r['Expense ID']==str(eid))['Odometer source'], 'estimated')
        blank = dict(payload, merchant='Unknown reading', fuel_details={'litres': '25', 'odometer_km': '', 'odometer_source': 'unknown', 'full_tank': False})
        result = self.call(self.owner, 'expenses', blank)
        self.assertEqual(result.status_code, 200, result.json)
        record = next(r for r in self.owner.get('/api/expenses').json if r['id']==result.json['id'])
        self.assertIsNone(record['fuel_odometer_m'])
        self.assertEqual(record['fuel_odometer_source'], 'unknown')
        for source in ('dashboard', 'estimated', 'unrecognised'):
            bad = dict(blank, fuel_details=dict(blank['fuel_details'], odometer_source=source))
            self.assertEqual(self.call(self.owner, 'expenses', bad).status_code, 400)
