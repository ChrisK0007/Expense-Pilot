import json
import os
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import patch
from test_app import AppTest
from app import app, db
import notifications as n


class NotificationTest(AppTest):
    def registration(self, **kw):
        value = dict(installation=str(uuid.uuid4()), token='a'*64, context='b'*64,
                     enabled=True, remote=True, quietHours=False, sounds=False,
                     timezone='Australia/Brisbane', quietStart=1320, quietEnd=420,
                     receipts=True, invoicePaid=True, invoiceOverdue=True, emailFailure=True, budgets=True, bank=True)
        value.update(kw); return value

    def test_feed_auth_and_receipt_isolation_resolution(self):
        self.assertEqual(app.test_client().get('/api/notifications/events').status_code, 401)
        with app.app_context():
            uid = db().execute("SELECT id FROM users WHERE role='owner'").fetchone()['id']
            db().execute("INSERT INTO receipts VALUES ('receipt',?,'private.pdf','application/pdf')", (uid,))
            db().execute("INSERT INTO receipt_details(receipt_id,scan_status) VALUES ('receipt','scanned')")
            db().commit()
        events = self.owner.get('/api/notifications/events').json
        self.assertEqual([x['kind'] for x in events], ['receipts'])
        self.assertNotIn('private.pdf', json.dumps(events))
        self.assertEqual(self.agent.get('/api/notifications/events').json, [])
        with app.app_context():
            db().execute("DELETE FROM receipts WHERE id='receipt'"); db().commit()
        self.assertEqual(self.owner.get('/api/notifications/events').json, [])

    def test_budgets_cover_quarter_and_year_without_repeat_keys(self):
        today = n.workspace_time.today().isoformat(); month = today[:7]
        for period in ('monthly', 'quarterly', 'yearly'):
            result = self.call(self.owner, 'budgets', dict(month=month,period=period,category='Meals',scope='all',amount='100'))
            self.assertEqual(result.status_code, 200)
        self.expense(self.owner, date=today, amount='81')
        first = [x for x in self.owner.get('/api/notifications/events').json if x['kind']=='budgets']
        self.assertEqual(len(first), 3)
        self.assertTrue(all('80%' in x['details'] for x in first))
        self.assertEqual(first, self.owner.get('/api/notifications/events').json)
        self.expense(self.owner, date=today, amount='20')
        second = self.owner.get('/api/notifications/events').json
        self.assertTrue(all('100%' in x['details'] for x in second))
        self.assertFalse(set(x['key'] for x in first) & set(x['key'] for x in second))

    @patch.dict(os.environ, {'PUSH_RELAY_URL': 'https://relay.example/notify', 'PUSH_RELAY_TOKEN': 'x'*40})
    def test_device_validation_scope_and_csrf(self):
        value = self.registration()
        self.assertEqual(self.owner.put('/api/notifications/device', json=value).status_code, 403)
        self.assertEqual(self.call(self.owner, 'notifications/device', value, 'PUT').status_code, 200)
        self.assertEqual(self.call(self.agent, 'notifications/device', value, 'PUT').status_code, 409)
        self.assertEqual(self.call(self.agent, 'notifications/device', value, 'DELETE').status_code, 200)
        with app.app_context(): self.assertEqual(db().execute('SELECT COUNT(*) FROM notification_devices').fetchone()[0], 1)
        for change in ({'token':'bad'}, {'quietStart':True}, {'enabled':'true'}, {'timezone':'Missing/Place'}):
            self.assertEqual(self.call(self.owner,'notifications/device',{**value,**change},'PUT').status_code,400)
        self.assertEqual(self.call(self.owner,'notifications/device',value,'DELETE').status_code,200)
        with app.app_context(): self.assertEqual(db().execute('SELECT COUNT(*) FROM notification_devices').fetchone()[0],0)

    @patch.dict(os.environ, {'PUSH_RELAY_URL': 'https://relay.example/notify', 'PUSH_RELAY_TOKEN': 'x'*40})
    def test_worker_dedup_retries_quiet_hours_and_logout(self):
        value = self.registration()
        self.call(self.owner, 'notifications/device', value, 'PUT')
        item = n.event('test', 'invoiceOverdue', 'invoice', 1)
        with app.app_context(), patch.object(n, 'collect', return_value=[item]), patch.object(n, 'deliver') as send:
            n.run_once(); self.assertEqual(send.call_count, 1)
            db().execute('UPDATE notification_devices SET next_attempt=0'); db().commit()
            n.run_once(); self.assertEqual(send.call_count, 1)
            db().execute("UPDATE notification_devices SET next_attempt=0,seen='{}'"); db().commit()
            send.side_effect = OSError('offline'); n.run_once()
            row = dict(db().execute('SELECT * FROM notification_devices').fetchone())
            self.assertEqual(json.loads(row['seen']), {}); self.assertGreater(row['next_attempt'], time.time())
            self.assertEqual(row['lease_until'], 0)
        self.call(self.owner,'logout',{})
        with app.app_context(), patch.object(n, 'collect', return_value=[item]), patch.object(n, 'deliver') as send:
            db().execute('UPDATE notification_devices SET next_attempt=0'); db().commit(); n.run_once(); send.assert_not_called()
        prefs = n.preferences({**value,'quietHours':True})
        self.assertTrue(n.quiet(prefs, datetime(2026,10,16,13,tzinfo=timezone.utc).timestamp()))
        self.assertFalse(n.quiet(prefs, datetime(2026,10,16,21,tzinfo=timezone.utc).timestamp()))
