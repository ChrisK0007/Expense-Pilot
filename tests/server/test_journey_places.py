import uuid
from test_app import AppTest
from app import app, db


class JourneyPlaceTest(AppTest):
    def change(self, pid=None, version=0, **kw):
        payload = dict(expected_version=version, mutation_id=str(uuid.uuid4()), deleted=False,
                       name='Home', address='10 Test Street, Brisbane',
                       point=dict(latitude=-27.4, longitude=153.1))
        payload.update(kw)
        pid = pid or str(uuid.uuid4())
        return pid, payload, self.call(self.owner, 'journey-places/' + pid, payload, 'PUT')

    def test_places_sync_retry_conflict_and_delete(self):
        self.assertTrue(self.owner.get('/api/session').json['capabilities']['journey_places'])
        pid, payload, created = self.change()
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json['version'], 1)
        other = app.test_client(); self.login(other, 'owner@example.test', 'Owner-password-123')
        self.assertEqual(other.get('/api/journey-places').json, [created.json])
        retry = self.call(other, 'journey-places/' + pid, payload, 'PUT')
        self.assertEqual(retry.json, created.json)
        _, _, conflict = self.change(pid, name='Old device edit')
        self.assertEqual(conflict.status_code, 409)
        _, _, updated = self.change(pid, version=1, name='Work')
        self.assertEqual(updated.json['version'], 2)
        # A lost acknowledgement can still be retried after another device edits.
        self.assertEqual(self.call(other, 'journey-places/' + pid, payload, 'PUT').json, created.json)
        self.assertEqual(other.get('/api/journey-places').json[0]['name'], 'Work')
        _, _, deleted = self.change(pid, version=2, deleted=True)
        self.assertTrue(deleted.json['deleted']); self.assertEqual(deleted.json['address'], '')
        self.assertEqual(self.change(pid, version=1)[2].status_code, 409)
        self.assertTrue(other.get('/api/journey-places').json[0]['deleted'])
        payload['name'] = 'Different request'
        self.assertEqual(self.call(other, 'journey-places/' + pid, payload, 'PUT').status_code, 409)

    def test_places_auth_scope_and_validation(self):
        self.assertEqual(app.test_client().get('/api/journey-places').status_code, 401)
        pid, payload, _ = self.change()
        self.assertEqual(self.agent.get('/api/journey-places').json, [])
        self.assertEqual(self.call(self.agent, 'journey-places/' + pid, payload, 'PUT').status_code, 403)
        self.assertEqual(self.owner.put('/api/journey-places/' + pid, json=payload).status_code, 403)
        with app.app_context():
            db().execute("UPDATE users SET permission='read_write' WHERE email='agent@example.test'"); db().commit()
        # A write-enabled tax agent still has a distinct address collection.
        self.assertEqual(self.call(self.agent, 'journey-places/' + pid, payload, 'PUT').status_code, 200)
        self.assertEqual(len(self.owner.get('/api/journey-places').json), 1)
        for invalid in [dict(name=''), dict(name='x'*61), dict(address='x'*201),
                        dict(point={'latitude': 91, 'longitude': 0}),
                        dict(point={'latitude': True, 'longitude': 0}),
                        dict(expected_version=True), dict(deleted=1), dict(mutation_id='bad')]:
            self.assertEqual(self.change(**invalid)[2].status_code, 400)

    def test_place_limit_and_tombstone_capacity(self):
        for i in range(100):
            self.assertEqual(self.change(name=f'Place {i}')[2].status_code, 200)
        self.assertEqual(self.change()[2].status_code, 400)
        first = self.owner.get('/api/journey-places').json[0]
        self.assertEqual(self.change(first['id'], version=1, deleted=True)[2].status_code, 200)
        self.assertEqual(self.change()[2].status_code, 200)
