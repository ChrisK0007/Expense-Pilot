"""Read-only revision history: access boundaries and exact saved snapshots."""
import unittest
import test_billing
from app import app, db


class RevisionHistoryTest(unittest.TestCase):
    setUp = test_billing.BillingTest.setUp
    call = test_billing.BillingTest.call
    login = test_billing.BillingTest.login
    create = test_billing.BillingTest.create
    get = test_billing.BillingTest.get
    action = test_billing.BillingTest.action
    issue = test_billing.BillingTest.issue

    def test_history_retains_before_values_and_does_not_change_document(self):
        original = self.issue(self.create(reference='Original reference'))
        path = f"/api/billing/documents/{original['id']}/revisions"
        self.assertEqual(self.owner.get(path).json['items'], [])
        values = {key:original[key] for key in ('kind','client_id','issue_date','due_date','tax_mode','lines','version')}
        values['reference'] = 'Corrected reference'
        values['lines'][0]['quantity_type'] = 'Hours'
        result = self.call(self.owner, f"billing/documents/{original['id']}", values, 'PUT')
        self.assertEqual(result.status_code, 200, result.json)
        current = self.get(original['id'])
        response = self.owner.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.json['current_version'], current['version'])
        self.assertEqual(len(response.json['items']), 1)
        saved = response.json['items'][0]
        self.assertEqual(saved['version'], original['version'])
        self.assertEqual(saved['document']['reference'], 'Original reference')
        self.assertEqual(saved['document']['lines'][0]['quantity_type'], 'Units')
        self.assertEqual(saved['document']['total_cents'], original['total_cents'])
        self.assertNotIn('notes', saved['document']['client'])
        self.assertNotIn('business', saved['document'])
        self.assertEqual(self.get(original['id']), current, 'History GET must never amend or reissue')
        other = self.create()
        self.assertEqual(self.owner.get(f"/api/billing/documents/{other['id']}/revisions").json['items'], [])

    def test_owner_only_and_missing_documents(self):
        doc = self.create()
        path = f"/api/billing/documents/{doc['id']}/revisions"
        self.assertEqual(app.test_client().get(path).status_code, 401)
        self.assertEqual(self.agent.get(path).status_code, 403)
        with app.app_context():
            db().execute("UPDATE users SET permission='read_write' WHERE email='staff@example.test'"); db().commit()
        self.assertEqual(self.staff.get(path).status_code, 403)
        self.assertEqual(self.owner.get('/api/billing/documents/999999/revisions').status_code, 404)
        self.assertTrue(self.owner.get('/api/session').json['capabilities']['billing_revision_history'])
        self.assertNotIn('billing_revision_history', self.agent.get('/api/session').json['capabilities'])


if __name__ == '__main__': unittest.main()
