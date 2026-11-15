import csv
import io
import unittest
from datetime import datetime, time, timedelta
import test_app as base
import test_receipts
import workspace_time
from app import app


class VehicleRunningCostsTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login
    upload = test_receipts.ReceiptTest.upload
    scan = test_receipts.ReceiptTest.scan

    def test_prefill_and_save_fuel_in_the_receipt_inbox(self):
        vid = self.call(self.owner, 'vehicles', {'name': 'Test vehicle'}).json['id']
        with app.app_context():
            zone = workspace_time.zone()
        day = datetime.now(zone).date() - timedelta(days=3)
        midnight = datetime.combine(day, time.min, zone)
        odometer = f'vehicles/{vid}/odometer'
        lookup = f'/api/{odometer}/estimate'

        def estimate(clock=None):
            args = {'date': day.isoformat()}
            if clock is not None:
                args['time'] = clock
            response = self.owner.get(lookup, query_string=args)
            self.assertEqual(response.status_code, 200, response.json)
            return response.json

        self.assertEqual(estimate()['reason'], 'no_baseline')
        baseline = self.call(self.owner, odometer, {'recorded_at': (midnight - timedelta(hours=2)).timestamp(), 'reading': '1000'})
        self.assertEqual(baseline.status_code, 200, baseline.json)
        self.assertEqual(estimate(), {'estimate_m': 1000000})
        for start, end, distance in [(9, 10, '15.5'), (12, 13, '26.25')]:
            trip = self.call(self.owner, 'vehicle-journeys', dict(
                vehicle_id=vid, date=day.isoformat(), origin='A', destination='B', scope='personal',
                started_at=(midnight + timedelta(hours=start)).timestamp(),
                ended_at=(midnight + timedelta(hours=end)).timestamp(), distance=distance))
            self.assertEqual(trip.status_code, 200, trip.json)
        self.assertEqual(estimate()['reason'], 'time_needed')
        self.assertEqual(estimate('09:30')['reason'], 'trip_timing')
        self.assertEqual(estimate('11:30'), {'estimate_m': 1015500})
        self.assertEqual(estimate('13:00'), {'estimate_m': 1041750})
        self.assertEqual(self.agent.get(lookup, query_string={'date': day.isoformat()}).status_code, 403)
        self.assertEqual(self.owner.get(lookup, query_string={'date': day.isoformat(), 'time': '24:12'}).status_code, 400)

        rid = self.upload().json['id']
        response = self.scan(rid, dict(merchant='Example fuel', date=day.isoformat(), amount='81.30',
                                       category='Vehicle expenses', fuel_litres='40.625', fuel_time='11:30'))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual((response.json['fuel_litres'], response.json['fuel_time']), (40.625, '11:30'))
        data = dict(date=day.isoformat(), merchant='Example fuel', amount='81.30', category='Vehicle expenses', scope='personal',
                    vehicle_id=vid, fuel_details=dict(litres=response.json['fuel_litres'], odometer_km='', full_tank=None),
                    fuel_time=response.json['fuel_time'])
        draft = self.call(self.owner, f'receipts/{rid}/draft', data, 'PUT')
        self.assertEqual(draft.status_code, 200, draft.json)
        self.assertEqual(draft.json['draft']['fuel_details'], dict(litres=40.625, odometer_km=None, full_tank=None))
        self.assertEqual(self.owner.get('/api/expenses').json, [])
        data['fuel_details'].update(odometer_km=estimate(data['fuel_time'])['estimate_m'] / 1000, full_tank=False)
        saved = self.call(self.owner, f'receipts/{rid}/expense', data)
        self.assertEqual(saved.status_code, 200, saved.json)
        expense = self.owner.get('/api/expenses').json[0]
        self.assertEqual(expense['receipt_id'], rid)
        self.assertEqual((expense['fuel_volume_ml'], expense['fuel_odometer_m'], expense['fuel_full_tank']), (40625, 1015500, 0))
        report = self.owner.get(f'/api/vehicles/{vid}/running-costs?from={day}&to={day}').json
        self.assertEqual(report['fuel_cents'], 8130)

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
