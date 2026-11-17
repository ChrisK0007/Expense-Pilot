"""Exercise hardening through the real API; requires the pinned server dependencies."""
import io
import json
import os
import unittest
import test_app as base
from app import app, db
from werkzeug.security import generate_password_hash


class SecurityInputsTest(unittest.TestCase):
    setUp = base.AppTest.setUp
    call = base.AppTest.call
    login = base.AppTest.login

    def test_json_scalars_fail_cleanly(self):
        for path in ("login", "accounts", "expenses", "users/1/access"):
            for value in (None, [], ["bad"], "bad", 1, True):
                with self.subTest(path=path, value=value):
                    csrf = self.owner.get("/api/session").json["csrf"]
                    response = self.owner.post("/api/" + path, data=json.dumps(value),
                                               content_type="application/json", headers={"X-CSRF-Token": csrf})
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("error", response.json)

    def test_malformed_and_vendor_json_and_same_origin(self):
        csrf = self.owner.get('/api/session').json['csrf']
        for body in ('{', 'null', '[]', '"scalar"'):
            response = self.owner.post('/api/accounts', data=body,
                content_type='application/vnd.expense-pilot+json', headers={'X-CSRF-Token': csrf})
            self.assertEqual(response.status_code, 400)
        response = self.owner.post('/api/accounts', json={'name': 'Valid account', 'bank': 'Other'},
            headers={'X-CSRF-Token': csrf, 'Sec-Fetch-Site': 'same-origin'})
        self.assertEqual(response.status_code, 200)

    def test_cross_site_mutation_rejected_and_cors_stays_closed(self):
        csrf = self.owner.get("/api/session").json["csrf"]
        response = self.owner.post("/api/accounts", json={"name": "Injected", "bank": "Other"},
                                   headers={"X-CSRF-Token": csrf, "Sec-Fetch-Site": "cross-site",
                                            "Origin": "https://untrusted.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.owner.get("/api/accounts").json, [])
        for response in (response, self.owner.options("/api/accounts", headers={
                "Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"})):
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_password_suffix_is_not_silently_discarded(self):
        password = "X" * 256
        with app.app_context():
            db().execute("UPDATE users SET password=? WHERE role='owner'", (generate_password_hash(password),))
            db().commit()
        other = app.test_client()
        self.assertEqual(self.call(other, "login", {"email": "owner@example.test", "password": password + "extra"}).status_code, 401)
        self.assertEqual(self.call(other, "login", {"email": "owner@example.test", "password": password}).status_code, 200)
        self.assertEqual(self.call(other, "password", {"current": password + "extra", "password": "replacement-password-123"}).status_code, 403)

    def test_setup_rejects_malformed_email_without_creating_owner(self):
        with app.app_context():
            db().execute("DELETE FROM users")
            db().commit()
        for email in ("name@", "name@example", "name@example.test\\r\\nBcc:other@example.test"):
            response = self.call(app.test_client(), "setup", {"token": os.environ["SETUP_TOKEN"],
                "name": "Owner", "email": email, "password": "Owner-password-123"})
            self.assertEqual(response.status_code, 400)
        with app.app_context():
            self.assertEqual(db().execute("SELECT count(*) FROM users").fetchone()[0], 0)

    def test_upload_bad_reference_returns_validation_error(self):
        from PIL import Image
        data = io.BytesIO()
        Image.new("RGB", (2, 2)).save(data, format="PNG")
        for reference in ("not-an-id", "-1"):
            csrf = self.owner.get("/api/session").json["csrf"]
            response = self.owner.post("/api/receipts", data={"expense_id": reference,
                "file": (io.BytesIO(data.getvalue()), "receipt.png")}, headers={"X-CSRF-Token": csrf})
            self.assertEqual(response.status_code, 400)

    def test_sql_payloads_remain_data_and_filters_are_allowlisted(self):
        merchant = "Synthetic '; DROP TABLE users; --"
        response = self.call(self.owner, 'expenses', {'date': '2026-10-08', 'merchant': merchant,
            'amount': '12.34', 'scope': 'business', 'category': 'Other', 'percent': 100})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.owner.get('/api/expenses').json[0]['merchant'], merchant)
        self.assertGreater(len(self.owner.get('/api/users').json), 0)
        self.assertEqual(self.owner.get('/api/bank-transactions', query_string={'state': "review') OR 1=1--"}).status_code, 400)

    def test_upload_rejects_html_disguised_as_an_image(self):
        csrf = self.owner.get('/api/session').json['csrf']
        response = self.owner.post('/api/receipts', data={
            'file': (io.BytesIO(b'<html><script>synthetic()</script></html>'), 'receipt.png', 'image/png')},
            headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 400)
