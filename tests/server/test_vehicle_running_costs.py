import csv
import io
import unittest
from datetime import timedelta
import test_app as base
import workspace_time
from app import app


class VehicleRunningCostsTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login

    def test_running_costs_join_expenses_fillups_and_odometer(self):
        vid = self.call(self.owner, 'vehicles', {'name': 'Test vehicle'}).json['id']
        today = workspace_time.today()

        def cost(days, amount, merchant, **overrides):
            data = dict(date=(today - timedelta(days=days)).isoformat(), scope='personal',
                        category='Vehicle expenses', status='ready', vehicle_id=vid, amount=amount,
                        merchant=merchant)
            data.update(overrides)
            result = self.call(self.owner, 'expenses', data)
            self.assertEqual(result.status_code, 200, result.json)
            return result.json['id']

        def fill(days, amount, volume, reading, full):
            return cost(days, amount, 'Test fill-up',
                        fuel_details=dict(litres=volume, odometer_km=reading, full_tank=full))

        fill(5, '50', '30', '1000', True)
        partial = fill(3, '30', '15', '1200', False)
        fill(1, '60', '30', '1500', True)
        service = cost(3, '100', 'Test service')
        purchase = cost(3, '1000', 'Test purchase')
        cost(3, '15', 'Reimbursed', reimbursed=True)
        cost(2, '-10', 'Test refund')
        for eid, kind in ((service, 'servicing'), (purchase, 'purchase')):
            result = self.call(self.owner, f'vehicle-costs/{eid}', dict(kind=kind, included=True), 'PUT')
            self.assertEqual(result.status_code, 200, result.json)

        path = f'/api/vehicles/{vid}/running-costs'
        result = self.owner.get(path)
        self.assertEqual(result.status_code, 200, result.json)
        report = result.json
        self.assertEqual((report['running_cents'], report['fuel_cents'], report['cents_per_km']), (23000, 14000, 46))
        self.assertEqual(report['breakdown'], {'fuel': 14000, 'servicing': 10000, 'running': -1000})
        self.assertEqual((report['litres_per_100_km'], report['economy_distance_m']), (9.0, 500000))
        self.assertEqual(report['fuel'][1]['price_per_litre'], 2)
        self.assertEqual(report['fuel'][1]['id'], partial)
        self.assertEqual(self.owner.get('/api/expenses').json[0]['fuel_odometer_m'], 1500000)

        limited = self.owner.get(path, query_string={'from': (today - timedelta(days=3)).isoformat()}).json
        self.assertIsNone(limited['litres_per_100_km'])
        self.assertEqual(self.owner.get(path, query_string={'from': '2026-12-01', 'to': '2026-01-01'}).status_code, 400)
        exported = self.owner.get(path + '.csv')
        rows = list(csv.DictReader(io.StringIO(exported.data.decode('utf-8-sig'))))
        self.assertEqual(len(rows), 7)
        self.assertEqual(next(row for row in rows if row['Expense ID'] == str(partial))['Litres'], '15.000')
        self.assertEqual(self.agent.get(path).status_code, 403)
        self.assertEqual(app.test_client().get(path).status_code, 401)

        invalid = dict(date=(today - timedelta(days=2)).isoformat(), merchant='Invalid fill-up',
                       scope='personal', category='Vehicle expenses', vehicle_id=vid, amount='10',
                       fuel_details=dict(litres='5', odometer_km='900', full_tank=False))
        self.assertEqual(self.call(self.owner, 'expenses', invalid).status_code, 400)
        self.assertEqual(len(self.owner.get('/api/expenses').json), 7)
        self.assertEqual(self.call(self.owner, f'expenses/{partial}', {}, 'DELETE').status_code, 200)
        self.assertEqual(len(self.owner.get(path).json['fuel']), 2)
