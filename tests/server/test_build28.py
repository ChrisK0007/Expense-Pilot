"""Regression checks for report calculations and device schedule ownership."""
import unittest
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from mileage_calculation import capped_report_metres, financial_year, financial_year_logbook, logbook_use


class MileageTest(unittest.TestCase):
    def test_filtered_report_uses_existing_annual_car_cap(self):
        journeys = [
            dict(date='2026-07-01', scope='business', percent=75, distance_m=6_000_000),
            dict(date='2026-08-01', scope='personal', percent=100, distance_m=1_000_000),
            dict(date='2026-08-02', scope='work', percent=100, distance_m=800_000),
        ]
        self.assertEqual(capped_report_metres(journeys, '2026-08-01', '2026-08-31', 'work'), 500_000)
        self.assertEqual(capped_report_metres(journeys, '2026-08-01', '2026-08-31', 'business'), 0)
        self.assertEqual(financial_year('2026-06-30'), 2025)
        self.assertEqual(financial_year('2026-07-01'), 2026)

    def test_logbook_uses_odometer_total_and_actual_work_allocation(self):
        zone = ZoneInfo('Australia/Brisbane')
        def reading(day, metres):
            return dict(recorded_at=datetime.fromisoformat(day).replace(tzinfo=zone).timestamp(), reading_m=metres)

        first = reading('2026-07-01T07:00', 1_000_000)
        short = reading('2026-09-21T19:00', 2_000_000)
        last = reading('2026-09-22T19:00', 2_000_000)
        journeys = [dict(date='2026-07-02', scope='work', percent=50, distance_m=800_000, started_at=None, ended_at=None)]
        self.assertIsNone(logbook_use([first, short], journeys, '2026-07-01', '2026-09-22', zone))
        value = logbook_use([first, last], journeys, '2026-07-01', '2026-09-22', zone)
        self.assertEqual((value['days'], value['work_percent'], value['business_percent']), (84, 40, 0))
        self.assertEqual(financial_year_logbook([first, last], journeys, '2026-07-01', '2027-06-30', zone, closed=True), value)
        journeys[0]['date'] = '2026-07-01'
        self.assertIsNone(logbook_use([first, last], journeys, '2026-07-01', '2026-09-22', zone))


class ScheduleTest(unittest.TestCase):
    def test_schedule_transfer_and_skip_preserve_version(self):
        from test_app import AppTest
        self.call = AppTest.call.__get__(self)
        self.login = AppTest.login.__get__(self)
        AppTest.setUp(self)
        def call(path, payload, method):
            return self.call(self.owner, path, payload, method)
        path = 'home-office/schedule'
        days = [dict(id=i, enabled=i <= 5, start=540, end=1020, breaks=30, scope='work') for i in range(1, 8)]
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        data = dict(version=0, days=days, timezone='Australia/Brisbane', reminders=True, device=first)
        self.assertEqual(self.agent.get('/api/' + path).status_code, 403)
        response = call(path, data, 'PUT')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['reminder_device'], first)
        self.assertEqual(call(path, {**data, 'device': second}, 'PUT').status_code, 409)
        skipped = call(path + '/skip', dict(day='2026-07-01'), 'POST').json
        self.assertEqual(skipped['version'], 1)
        updated = call(path, {**data, 'version': 1, 'device': second}, 'PUT').json
        self.assertEqual((updated['reminder_device'], updated['declined']), (second, ['2026-07-01']))
        read_only_device = call(path, {**data, 'version': 2, 'reminders': False}, 'PUT').json
        self.assertEqual(read_only_device['reminder_device'], second)
