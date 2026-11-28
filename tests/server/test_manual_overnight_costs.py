"""Manual costs use the existing ledger without implying substantiation eligibility."""
import unittest
import uuid
import test_app as base


class ManualOvernightTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login

    def test_domestic_overseas_and_business_manual_costs_are_not_claimed_or_duplicated(self):
        for location, scope in [('Brisbane', 'work'), ('Singapore', 'work'), ('London', 'business')]:
            trip = self.call(self.owner, 'trips', dict(location=location, scope=scope,
                start='2026-10-07', end='2026-10-09', purpose='Synthetic overnight work', allowance=150)).json['id']
            data = dict(client_ref=str(uuid.uuid4()), trip_id=trip, date='2026-10-08', merchant='Manual hotel '+location,
                amount='50.25', scope=scope, percent=100, category='Accommodation', meal='', status='review',
                receipt_id=None, reimbursed=False, notes='Original payment: 40 SGD. AUD paid: 50.25.\nConversion basis: Card statement')
            first = self.call(self.owner, 'expenses', data)
            self.assertEqual(first.status_code, 200, first.json)
            replay = self.call(self.owner, 'expenses', data)
            self.assertEqual(replay.status_code, 200, replay.json)
            self.assertEqual(first.json['id'], replay.json['id'])
            records = [r for r in self.owner.get('/api/expenses').json if r['trip_id']==trip]
            self.assertEqual(len(records), 1)
            self.assertIsNone(records[0]['receipt_id'])
            self.assertEqual(records[0]['notes'], data['notes'])
            self.assertEqual(records[0]['status'], 'review')
            result = self.owner.get(f'/api/trips/{trip}/overnight').json
            self.assertEqual((result['actual_cents'],result['allowance_cents']), (5025,15000))
            self.assertFalse(result['claim_current'])
            self.assertEqual(result['claim_cents'], 0)
            self.assertIsNone(result['reasonable_cents'])
            # Editing the same record preserves its identity and source notes.
            edited = dict(data, amount='51.25')
            self.assertEqual(self.call(self.owner, f"expenses/{first.json['id']}", edited, 'PUT').status_code, 200)
            self.assertEqual(len([r for r in self.owner.get('/api/expenses').json if r['trip_id']==trip]), 1)
            invalid = dict(data, client_ref=str(uuid.uuid4()), date='2026-10-10')
            self.assertEqual(self.call(self.owner, 'expenses', invalid).status_code, 400)
            self.assertEqual(self.call(self.agent, 'expenses', dict(data,client_ref=str(uuid.uuid4()))).status_code, 403)

    def test_no_receipt_and_no_notes_are_valid_for_actual_meals(self):
        trip = self.call(self.owner, 'trips', dict(location='Perth',scope='work',start='2026-10-07',end='2026-10-09',purpose='Work')).json['id']
        data = dict(trip_id=trip,date='2026-10-08',merchant='Cafe',amount='18',scope='work',percent=100,
                    category='Meals',meal='Lunch',status='review',receipt_id=None,notes='')
        self.assertEqual(self.call(self.owner,'expenses',data).status_code,200)
        result=self.owner.get(f'/api/trips/{trip}/overnight').json
        self.assertEqual(result['actual_cents'],1800)
        self.assertFalse(result['claim_current'])
