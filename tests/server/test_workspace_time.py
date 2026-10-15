"""Calendar boundaries, DST and retained offline dates in different regions."""
import os
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch
import test_app as base
from app import app, db
import billing
import workspace_time


class WorkspaceTimeTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login
    expense = base.AppTest.expense

    def select(self, zone):
        r = self.call(self.owner, 'workspace/settings', {'timezone': zone}, 'PUT')
        self.assertEqual(r.status_code, 200, r.json)

    def test_upgrade_default_permissions_validation_and_preserved_dates(self):
        with app.app_context():
            db().execute("DELETE FROM billing_settings WHERE key='workspace'"); db().commit()
        with patch.dict(os.environ, {'TZ': 'America/Los_Angeles'}):
            self.assertEqual(self.owner.get('/api/session').json['timezone'], 'Australia/Brisbane')
        self.expense(self.owner, date='2026-10-08')
        self.assertIn('Europe/London', app.test_client().get('/api/timezones').json['timezones'])
        for value in ('../etc/passwd', 'Not/AZone', None, 10, 'UTC+10'):
            self.assertEqual(self.call(self.owner, 'workspace/settings', {'timezone': value}, 'PUT').status_code, 400)
        self.assertEqual(self.call(self.agent, 'workspace/settings', {'timezone': 'UTC'}, 'PUT').status_code, 403)
        self.assertEqual(app.test_client().get('/api/workspace/settings').status_code, 401)
        self.select('Europe/London')
        self.assertEqual(self.agent.get('/api/session').json['timezone'], 'Europe/London')
        self.assertEqual(self.owner.get('/api/expenses').json[0]['date'], '2026-10-08')
        self.assertEqual(self.owner.get('/api/workspace/settings').json['timezone'], 'Europe/London')

    def test_new_setup_records_the_selected_region_atomically(self):
        self.call(self.owner, 'account', {'password': 'Owner-password-123', 'confirmation': 'DELETE WORKSPACE'}, 'DELETE')
        data = dict(token=os.environ['SETUP_TOKEN'], name='New owner', email='new@example.test', password='New-owner-password-123', timezone='Invalid/Timezone')
        self.assertEqual(self.call(self.owner, 'setup', data).status_code, 400)
        self.assertTrue(self.owner.get('/api/session').json['setup'])
        data['timezone'] = 'Pacific/Auckland'
        self.assertEqual(self.call(self.owner, 'setup', data).status_code, 200)
        self.assertEqual(self.owner.get('/api/session').json['timezone'], 'Pacific/Auckland')

    def test_calendar_day_and_daylight_saving_ignore_host_region(self):
        for zone, instant, expected in [
            ('Australia/Brisbane', '2026-01-01T13:30:00+00:00', '2026-01-01'),
            ('Australia/Sydney', '2026-01-01T13:30:00+00:00', '2026-01-02'),
            ('Australia/Sydney', '2026-07-01T13:30:00+00:00', '2026-07-01'),
            ('America/Los_Angeles', '2026-01-01T01:00:00+00:00', '2025-12-31'),
            ('Pacific/Auckland', '2026-01-01T13:30:00+00:00', '2026-01-02'),
        ]:
            self.select(zone)
            with app.app_context(), patch('workspace_time.datetime') as clock:
                clock.now.side_effect = lambda tz: datetime.fromisoformat(instant).astimezone(tz)
                self.assertEqual(billing.local_today(), expected)

    def test_odometer_dst_gap_and_repeated_hour(self):
        self.select('America/New_York')
        vid = self.call(self.owner, 'vehicles', {'name': 'DST test'}).json['id']
        path = f'vehicles/{vid}/odometer'
        for value in ('2026-03-08T02:30', '2025-11-02T01:30'):
            self.assertEqual(self.call(self.owner, path, {'reading': '100', 'recorded_local': value}).status_code, 400)
        first = self.call(self.owner, path, {'reading': '100', 'recorded_local': '2025-11-02T01:30', 'occurrence': 'first'})
        second = self.call(self.owner, path, {'reading': '101', 'recorded_local': '2025-11-02T01:30', 'occurrence': 'second'})
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(second.json['readings'][-1]['recorded_at'] - first.json['readings'][0]['recorded_at'], 3600)

    def test_offline_trip_timezone_survives_settings_change_and_retry(self):
        vid = self.call(self.owner, 'vehicles', {'name': 'Regional car'}).json['id']
        start = datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc).timestamp()
        self.call(self.owner, f'vehicles/{vid}/odometer', {'reading': '100', 'recorded_at': start-100})
        data = dict(vehicle_id=vid, date='2026-01-02', date_timezone='Australia/Sydney', scope='personal', distance='10', started_at=start, ended_at=start+600, client_ref=str(uuid.uuid4()))
        self.select('America/Los_Angeles')
        result = self.call(self.owner, 'vehicle-journeys', data)
        self.assertEqual(result.status_code, 200, result.json)
        self.select('Europe/London')
        self.assertEqual(self.call(self.owner, 'vehicle-journeys', data).json, result.json)
        saved = self.owner.get('/api/vehicle-journeys/'+str(result.json['id'])).json
        self.assertEqual((saved['date'], saved['date_timezone']), ('2026-01-02', 'Australia/Sydney'))
        with patch('vehicle_logbook.time.time', return_value=start+3600):
            self.assertEqual(self.owner.get(f'/api/vehicles/{vid}/odometer').json['estimate_m'], 110000)
        old = dict(data, date='2026-01-01', client_ref=str(uuid.uuid4())); old.pop('date_timezone')
        legacy = self.call(self.owner, 'vehicle-journeys', old)
        self.assertEqual(legacy.status_code, 200, legacy.json)
        self.assertEqual(self.owner.get('/api/vehicle-journeys/'+str(legacy.json['id'])).json['date_timezone'], 'Australia/Brisbane')


import test_billing as billing_base
from billing_emails import run_reminders


class ScheduledTimezoneTest(unittest.TestCase):
    setUp = billing_base.BillingTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login
    create = billing_base.BillingTest.create
    get = billing_base.BillingTest.get
    action = billing_base.BillingTest.action
    issue = billing_base.BillingTest.issue
    email_config = billing_base.BillingTest.email_config

    def test_reminders_and_recurring_drafts_wait_for_workspace_midnight(self):
        self.email_config()
        self.call(self.owner, 'billing/reminder-settings', dict(enabled=True, before_days=0, on_due_date=True, after_days=[]), 'PUT')
        doc = self.issue(self.create(issue_date='2026-01-01', due_date='2026-01-02'))
        instant = datetime(2026, 1, 1, 13, 30, tzinfo=timezone.utc)
        with patch('workspace_time.datetime') as clock, patch('billing_emails.deliver_queued') as deliver:
            clock.now.side_effect = lambda tz: instant.astimezone(tz)
            self.call(self.owner, 'workspace/settings', {'timezone': 'Europe/London'}, 'PUT')
            result = self.call(self.owner, 'billing/schedules', dict(document_id=doc['id'], interval='monthly', start_date='2026-01-02', terms=14))
            self.assertEqual(result.status_code, 200, result.json)
            with app.app_context():
                self.assertEqual(billing.run_due(), 0)
                self.assertEqual(run_reminders(), 0)
            deliver.assert_not_called()
            self.call(self.owner, 'workspace/settings', {'timezone': 'Australia/Sydney'}, 'PUT')
            with app.app_context():
                self.assertEqual(billing.run_due(), 1)
                self.assertEqual(run_reminders(), 1)
                self.assertEqual(run_reminders(), 0)
                self.assertEqual(billing.run_due(), 0)
            deliver.assert_called_once()
